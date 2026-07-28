"""The three-branch upsert, once instead of eight times.

Both pipelines write rows the same way: look up the stored content_hash by
primary key, then take one of three branches --

    absent       -> INSERT, count as new
    hash differs -> UPDATE the content columns, count as updated
    hash matches -> bump last_seen only, count as unchanged

That shape was duplicated in five jobs/ scripts and three events/ scripts,
and the copies had drifted in three ways that this module resolves by
picking the correct variant each time:

  * Per-record error isolation. nyc-events and nyc-library wrapped each
    record in try/except; ticketmaster-seatgeek did not, and its caller only
    guarded the HTTP call -- so one malformed record aborted an entire run
    rather than one row. Isolation wins: a bad row is counted and reported,
    never fatal.

  * lat/lon binding. nyc-events and nyc-library built the PostGIS geography
    by f-string-interpolating the floats straight into SQL; ticketmaster-
    seatgeek bound them as parameters. Parameter binding wins -- see
    GEOG_EXPR below.

  * Prune scope. Only nyc-library scoped its delete by source, so the other
    two each deleted rows belonging to the other scripts on every run.
    Scoped wins: prune_expired() requires the caller to name its sources.

WHAT STAYS OUT
    No table DDL lives here. `public.events` (in nyc_events) and `public.jobs`
    (in the separate jobs database) are owned by their pipelines; this module only needs a TableSpec describing which
    columns to write.
"""

import sys
from dataclasses import dataclass, field

from . import ids
from .timeparse import utc_now_str

def _check_identifier(name):
    # Column names are developer-supplied constants, never user input, but
    # they are interpolated into SQL so a cheap assertion is worth it.
    if not name.replace("_", "").isalnum():
        raise ValueError(f"unsafe SQL identifier: {name!r}")
    return name


@dataclass(frozen=True)
class TableSpec:
    """How to write one pipeline's rows.

    columns        -- written from the record, bound as %(name)s
    hash_fields    -- ordered keys fed to ids.content_hash (order is part of
                      the stored digest; changing it rewrites every row)
    computed       -- column -> raw SQL expression, applied on INSERT *and*
                      UPDATE. Expressions may reference %(param)s names.
                      events uses {"geog": GEOG_EXPR}; jobs uses
                      {"status": "'open'", "closed_at": "NULL"} so that a
                      row reappearing upstream is reopened, not left closed.
    revive_column  -- optional column whose value forces an UPDATE even when
                      the content hash matches. jobs sets this to "status"
                      with revive_value "open", so a job that was marked
                      closed and has now reappeared is treated as a reopen
                      rather than as unchanged.
    sticky         -- columns whose FIRST stored value wins. When the row
                      already exists, the stored value replaces the incoming
                      one before the content hash is computed, so a field that
                      cannot be re-derived stably neither drifts nor makes the
                      row look changed. See the note on the attribute below.
    """

    table: str
    columns: tuple
    hash_fields: tuple
    #: Keys whose falsy values hash as "" rather than "None". Required by the
    #: jobs scripts, which hashed `rec.get("description_text") or ""`.
    blank_if_falsy: tuple = ()
    computed: dict = field(default_factory=dict)
    revive_column: str = None
    revive_value: str = None
    id_column: str = "id"
    #: WHY THIS EXISTS -- the sliding `posted_at`.
    #:
    #: Google Jobs reports publication as a relative string ("23 days ago"),
    #: which text.parse_relative_posted_at resolves as `now - delta`. Because
    #: normalization runs on every ingest, the result is anchored to when the
    #: row was last written rather than to when the posting went up: re-ingest
    #: the same payload a week later and posted_at moves a week later too. The
    #: stored date drifts, the app view sorts on it, and since posted_at is a
    #: hash field a re-seen posting could never be counted "unchanged".
    #:
    #: The first observation is the closest one to the truth, so it wins. That
    #: is a general property of any field derived from a relative statement,
    #: which is why this is mechanism and lives here rather than in jobs.
    #:
    #: Note it must be applied BEFORE hashing, not merely omitted from the
    #: UPDATE. Dropping it from the write alone would leave the hash computed
    #: from the drifting value, so the row would still be counted changed on
    #: every run -- the churn, without even the corrected column.
    sticky: tuple = ()

    def __post_init__(self):
        _check_identifier(self.table)
        for name in (*self.columns, *self.computed, self.id_column):
            _check_identifier(name)
        if self.revive_column:
            _check_identifier(self.revive_column)
        for name in self.sticky:
            _check_identifier(name)
            if name not in self.columns:
                raise ValueError(
                    f"sticky column {name!r} is not in columns; it would be "
                    f"read back and then never written")

    # -- SQL built once per spec, not per row --------------------------------

    def insert_sql(self):
        cols = [self.id_column, *self.columns, *self.computed,
                "content_hash", "first_seen", "last_seen"]
        vals = ([f"%({self.id_column})s"]
                + [f"%({c})s" for c in self.columns]
                + [self.computed[c] for c in self.computed]
                + ["%(content_hash)s", "%(first_seen)s", "%(last_seen)s"])
        return (f"INSERT INTO {self.table} ({', '.join(cols)}) "
                f"VALUES ({', '.join(vals)})")

    def update_sql(self):
        # first_seen is deliberately absent: it records when we first saw the
        # row and must survive every later update.
        assignments = ([f"{c}=%({c})s" for c in self.columns]
                       + [f"{c}={expr}" for c, expr in self.computed.items()]
                       + ["content_hash=%(content_hash)s",
                          "last_seen=%(last_seen)s"])
        return (f"UPDATE {self.table} SET {', '.join(assignments)} "
                f"WHERE {self.id_column}=%({self.id_column})s")

    def select_sql(self):
        # Column order is the contract read by _existing_fields() below:
        # content_hash, then revive_column if set, then the sticky columns.
        cols = ["content_hash"]
        if self.revive_column:
            cols.append(self.revive_column)
        cols.extend(self.sticky)
        return (f"SELECT {', '.join(cols)} FROM {self.table} "
                f"WHERE {self.id_column} = %s")

    def sticky_offset(self):
        """Index of the first sticky column in a select_sql() row."""
        return 2 if self.revive_column else 1

    def touch_sql(self):
        return (f"UPDATE {self.table} SET last_seen = %s "
                f"WHERE {self.id_column} = %s")


@dataclass
class UpsertResult:
    new: int = 0
    updated: int = 0
    unchanged: int = 0
    errors: list = field(default_factory=list)

    def __iter__(self):
        # Lets callers keep the original `n, u, unc = upsert(...)` shape.
        return iter((self.new, self.updated, self.unchanged))

    def __add__(self, other):
        return UpsertResult(self.new + other.new,
                            self.updated + other.updated,
                            self.unchanged + other.unchanged,
                            self.errors + other.errors)


def upsert(conn, spec, records, id_fn, *, now=None, debug=False):
    """Write `records`, returning an UpsertResult.

    `id_fn(rec)` produces the primary key -- the two pipelines build it from
    different fields, so it stays a caller concern (see lib.ids.make_id).

    Commits once at the end. Individual record failures are isolated and
    collected rather than raised, so one malformed row can't lose a batch.
    """
    now = now or utc_now_str()
    result = UpsertResult()
    insert_sql, update_sql = spec.insert_sql(), spec.update_sql()
    select_sql, touch_sql = spec.select_sql(), spec.touch_sql()

    for rec in records:
        try:
            # SAVEPOINT per record. A plain try/except is NOT enough on
            # Postgres: a failed statement aborts the whole transaction, so
            # every subsequent record in the batch dies with "current
            # transaction is aborted" and one bad row still loses the batch
            # -- the exact failure the per-record guard was meant to prevent.
            # psycopg's nested transaction() issues a SAVEPOINT, so only the
            # offending record is rolled back.
            with conn.transaction():
                rec_id = id_fn(rec)
                # The lookup comes BEFORE hashing because sticky columns feed
                # the hash: a value that cannot be re-derived stably has to be
                # replaced by the stored one first, or the row hashes as
                # changed no matter what is written. See TableSpec.sticky.
                existing = conn.execute(select_sql, (rec_id,)).fetchone()
                if existing is not None and spec.sticky:
                    off = spec.sticky_offset()
                    rec = {**rec, **{name: existing[off + i]
                                     for i, name in enumerate(spec.sticky)}}

                new_hash = ids.content_hash(rec, spec.hash_fields,
                                            spec.blank_if_falsy)

                params = {**rec, spec.id_column: rec_id,
                          "content_hash": new_hash, "last_seen": now}

                if existing is None:
                    conn.execute(insert_sql, {**params, "first_seen": now})
                    result.new += 1
                elif existing[0] != new_hash or (
                    spec.revive_column and existing[1] != spec.revive_value
                ):
                    conn.execute(update_sql, params)
                    result.updated += 1
                else:
                    conn.execute(touch_sql, (now, rec_id))
                    result.unchanged += 1

        except Exception as e:
            result.errors.append(str(e)[:200])
            if debug:
                print(f"[debug] upsert error for "
                      f"{rec.get('title', '<untitled>')!r}: {e}",
                      file=sys.stderr)

    conn.commit()
    if result.errors and debug:
        print(f"[debug] {len(result.errors)} upsert errors "
              f"(samples: {result.errors[:3]})", file=sys.stderr)
    return result


# --------------------------------------------------------------------------
# upsert_checked -- making the correct call the easy one
# --------------------------------------------------------------------------
#
# WHY THIS EXISTS. UpsertResult.__iter__ above yields (new, updated,
# unchanged) and NOT .errors, so
#
#     n, u, unc = upsert(...)
#
# reads naturally, is what eight call sites wrote, and silently discards
# every per-record failure. A run that dropped a hundred records and hit no
# read errors reported success: no alert, no non-zero exit, no log line. The
# only symptom was a corpus quietly smaller than it should be, which is
# indistinguishable from a slow hiring week.
#
# __iter__ stays as it is -- it is the documented shape and rewriting it
# would only move the surprise. The fix is a wrapper that cannot be called
# without the error count being logged, so callers get the correct behaviour
# by writing the shorter thing.

class UpsertErrorRate(RuntimeError):
    """Raised when a batch's per-record failure rate exceeds the threshold.

    Carries `.result`, because upsert() commits before this is raised: the
    records that succeeded ARE written. A caller that catches this can still
    report and accumulate them, and several do -- see the per-unit loops in
    ingest/ats.py and the two Google scripts, which treat one bad batch the
    way they already treat one unreachable source.
    """

    def __init__(self, message, result):
        super().__init__(message)
        self.result = result


#: Prefix of the machine-readable line upsert_checked() emits on EVERY call.
#: run-daily.py scans step output for it to build the nightly per-step record
#: and error counts, which is what makes "ran and wrote nothing" distinct
#: from "ran and dropped everything". Keep the format stable, or update
#: run-daily.parse_upsert_summaries() in the same commit.
SUMMARY_PREFIX = "upsert-summary:"

#: Default per-run failure rate above which upsert_checked raises. 5% is a
#: starting guess, not a measurement -- there has never been a run with the
#: error count recorded, so there is no distribution to pick from yet. Tune
#: it once task 04's baseline exists.
DEFAULT_THRESHOLD = 0.05


def summary_line(result, table="?"):
    """The one line every upsert emits, in a form both a human reading
    journalctl and run-daily.py's parser can use."""
    return (f"{SUMMARY_PREFIX} table={table} new={result.new} "
            f"updated={result.updated} unchanged={result.unchanged} "
            f"errors={len(result.errors)}")


def _stderr_logger(line):
    print(line, file=sys.stderr)


def upsert_checked(*args, threshold=DEFAULT_THRESHOLD, logger=None, **kwargs):
    """Upsert, log any per-record errors, and raise if the failure rate
    exceeds `threshold`. Returns the full result including .errors.

    `logger` is any callable taking one string; it defaults to writing to
    stderr, which is where this pipeline's scripts already put log output and
    keeps the summary out of the stdout that the watchdog treats as an alert.

    The summary is logged ALWAYS, including when the error count is zero.
    That is deliberate: `errors=0` present on every run makes the field's
    ABSENCE the anomaly. A count that only appears when it is bad is a count
    nobody notices has stopped appearing.
    """
    result = upsert(*args, **kwargs)

    # The spec is positional in every caller (conn, spec, records, id_fn),
    # but accept it by keyword too rather than IndexError on a caller that
    # spells it differently.
    spec = args[1] if len(args) > 1 else kwargs.get("spec")
    table = getattr(spec, "table", "?")

    log = logger or _stderr_logger
    log(summary_line(result, table))
    check_error_rate(result, threshold=threshold, label=table, logger=log)
    return result


def check_error_rate(result, *, threshold=DEFAULT_THRESHOLD, label="",
                     logger=None):
    """Raise UpsertErrorRate if `result`'s failure rate exceeds `threshold`.

    Separate from upsert_checked because the scripts that upsert inside a
    per-source loop need the rule applied twice, at two different scopes:
    once per batch (where a single bad source is survivable and is recorded
    the way an unreachable source already is) and once over the accumulated
    total at the end of the run, where it is not.
    """
    if not result.errors:
        return result

    log = logger or _stderr_logger
    attempted = (result.new + result.updated + result.unchanged
                 + len(result.errors))
    rate = len(result.errors) / attempted
    log(f"upsert: {len(result.errors)}/{attempted} record(s) failed"
        f"{' on ' + label if label else ''} ({rate:.1%}); "
        f"samples: {result.errors[:3]}")
    if rate > threshold:
        raise UpsertErrorRate(
            f"{len(result.errors)}/{attempted} records failed to upsert"
            f"{' into ' + label if label else ''} "
            f"({rate:.1%} > {threshold:.1%} threshold); "
            f"samples: {result.errors[:3]}",
            result)
    return result
