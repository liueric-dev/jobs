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

#: PostGIS point from bound lat/lon parameters, NULL when either is missing.
#: Parameter-bound rather than interpolated: psycopg handles quoting and type
#: coercion, a None can't produce the literal text "None" inside SQL, and the
#: query plan is cacheable because the SQL text stops varying per row.
#:
#: The ::double precision casts are load-bearing, not decoration. A bare
#: placeholder in `%(latitude)s IS NOT NULL` gives the planner nothing to
#: infer a type from, and Postgres rejects the statement outright with
#: "could not determine data type of parameter" -- but only for the rows
#: where the value is actually NULL, which is exactly the geocoding-gap case.
GEOG_EXPR = """
    CASE WHEN %(latitude)s::double precision IS NOT NULL
          AND %(longitude)s::double precision IS NOT NULL
         THEN ST_SetSRID(ST_MakePoint(%(longitude)s::double precision,
                                      %(latitude)s::double precision),
                         4326)::geography
         ELSE NULL END
"""


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


def prune_expired(conn, table, sources, cutoff, until=None, *,
                  column="start_ts", source_column="source"):
    """Delete rows for `sources` outside the ingest window.

    Removes rows whose `column` is before `cutoff` and, when `until` is
    given, also those after it. The upper bound matters because a window
    enforced only at fetch time never removes what an earlier, wider run
    already stored: NYPL had 800 rows reaching to May 2027 while every other
    source stopped at 90 days, and filtering new rows alone would have left
    them there forever. Pruning both ends makes the window self-healing.

    Naming the sources is mandatory. Two of the three events scripts used to
    run an unscoped `DELETE FROM events WHERE start_datetime < %s`, so each
    silently deleted the other scripts' rows on every run -- the library
    script was the only one that scoped correctly.

    Defaults to the TIMESTAMPTZ column, so the comparison is a real instant
    comparison. The old TEXT comparison also mis-deleted date-only values by
    prefix ('2026-07-25' sorts before '2026-07-25T00:00:00.000'), which
    removed same-day events on the morning they happened.
    """
    _check_identifier(table)
    _check_identifier(column)
    _check_identifier(source_column)
    if not sources:
        raise ValueError("prune_expired requires an explicit source list")

    sql = (f"DELETE FROM {table} "
           f"WHERE {source_column} = ANY(%(sources)s) AND ({column} < %(cutoff)s")
    params = {"sources": list(sources), "cutoff": cutoff}
    if until is not None:
        sql += f" OR {column} > %(until)s"
        params["until"] = until
    sql += ")"

    cur = conn.execute(sql, params)
    conn.commit()
    return cur.rowcount
