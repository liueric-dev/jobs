"""The nightly search-query step: seed, fold, decay, dispatch.

Four things, in that order, and the order is not arbitrary:

  1. SEED    config/search-queries.json into `search_queries`, one row per
             extract.ROLE_TRACK. First, so a track added since the last run is
             visible to everything below on the same night.
  2. FOLD    current watcher counts into `search_query_signal`, per cohort --
             suppressed below schema.SEARCH_MIN_WATCHERS and bucketed above it.
             This is the ONLY writer of that table, and the service role holds
             SELECT on it and nothing else. See ensure_search_query_schema()'s
             docstring in schema.py.
  3. DECAY   mark abandoned queries retired so they stop consuming quota.
             After the fold, so a query retiring tonight still had its badge
             computed from the watchers it had; before dispatch, so a retired
             query is not run one last time on the night it retires.
  4. RUN     dispatch the due queries to a provider.

WHAT STEP 4 DOES NOT DO YET, AND THE BLOCKER BY NAME. There is no provider to
dispatch to. tranche_four/23 is the provider abstraction (`backend/serp/`) and
is descoped; `ingest/google-serpapi.py` is the only thing in this repo that
talks to SerpApi and it reads its queries from config/google-queries.json, not
from a database table. So run_due() SELECTS and REPORTS and does not fetch.

That is a deferral and it is loud rather than silent, which matters more here
than anywhere: ".claude/CLAUDE.md" says silence is this system's failure mode
-- exhausted keys and changed endpoints all return zero rows rather than
raising -- and a search runner that quietly did nothing would be
indistinguishable from one whose provider had been cut off. main() prints the
due count and the reason it did not spend it, every run.

THE SMALLEST THING THAT UNBLOCKS IT: a callable taking (text, location,
chips, date_chip) and returning normalized Google Jobs records. The record
shape already exists and is deliberately de-duplicated -- google_jobs.py, and
`.claude/CLAUDE.md` forbids a second definition of it -- so the missing piece
is the dispatcher, not the parser. ingest/google-serpapi.py:273's
serpapi_search() is that function with its query source hard-wired to a config
file; lifting it behind an interface is task 23.

THIS IS cohort.py's SIBLING AND IS SHAPED LIKE IT ON PURPOSE. Both fold a
per-Builder fact into a suppressed, bucketed, per-cohort aggregate that the
surfacing service can only read; both apply the floor in the SQL's HAVING and
assert it again on the way out; both replace a cohort's rows wholesale rather
than upserting, so a badge can DISAPPEAR. Where they differ, the difference is
in the source and is annotated where it occurs: cohort.py folds an append-only
event log and needs DISTINCT ON to find the latest save/unsave, where a watch is
current state and its retraction is a column on the row.

USAGE
    python3 searchqueries.py                    # every active profile
    python3 searchqueries.py --profile pursuit  # one
    python3 searchqueries.py --dry-run          # report, write nothing
    DEBUG_PRINT_KEYS=1 python3 searchqueries.py # detail, the convention here
"""

import argparse
import json
import os
import sys

import schema
import searchnorm
from lib import dbconn
from lib.timeparse import utc_now_str

DEBUG_PRINT_KEYS = os.environ.get("DEBUG_PRINT_KEYS", "") == "1"

SEED_FILE = os.environ.get(
    "JOBS_SEARCH_QUERIES_FILE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 "config", "search-queries.json"),
)




def load_seeds(path=None):
    """The seed catalogue, as a list of dicts ready for REGISTER_QUERY_SQL.

    Keys beginning with `_` are documentation and are dropped here rather than
    tolerated downstream -- `_comment` fields in this repo's config JSON are
    load-bearing documentation (.claude/CLAUDE.md) and every reader has to know
    to skip them.
    """
    with open(path or SEED_FILE) as fh:
        cfg = json.load(fh)
    location = cfg["location"]
    seeds = []
    for entry in cfg["queries"]:
        seeds.append({
            "role_track": entry["role_track"],
            "text": entry["text"],
            "location": location,
        })
    return seeds


def seed(conn, path=None, now=None):
    """Insert the catalogue. Idempotent, and returns how many rows are new.

    ON CONFLICT DO UPDATE assigning a column to itself, via the same statement
    the webapp uses. A seed run must never overwrite a query a Builder created
    first: if someone typed "data analyst" before the catalogue landed, the row
    is theirs, keeps source='builder', and the seed is a no-op on it. The
    alternative -- upgrading it to source='track' -- would make it undecayable
    for having been typed early, which is a rule nobody would guess.
    """
    now = now or utc_now_str()
    created = 0
    for entry in load_seeds(path):
        normalized_text, normalized_location = searchnorm.validate(
            entry["text"], entry["location"])
        before = conn.execute(
            "SELECT id FROM search_queries "
            "WHERE normalized_text = %s AND normalized_location = %s",
            (normalized_text, normalized_location)).fetchone()
        conn.execute(searchnorm.REGISTER_QUERY_SQL,
                     (normalized_text, normalized_location,
                      entry["text"], entry["location"], None,
                      "track", entry["role_track"], now))
        if before is None:
            created += 1
    conn.commit()
    return created


#: Distinct Builders currently watching each query, for one cohort, at or above
#: the threshold. Returns (query_id, watchers), query_id order.
#:
#: `removed_at IS NULL` IS THE DEFINITION OF A CURRENT WATCHER and it is in the
#: WHERE, not applied afterwards. This is the same hazard cohort.py's fold
#: solves with DISTINCT ON over the save/unsave log: a table that keeps
#: retracted rows and a count that forgets to exclude them pushes queries OVER
#: the threshold, which is the suppression failing open. It is cheaper here --
#: a watch is current state rather than an append-only log, so the retraction is
#: a column on the row instead of a later row -- but the failure mode is
#: identical and so is the fix.
#:
#: GROUPED BY COHORT AND FILTERED TO ONE. Cross-cohort aggregation would raise
#: the counts and improve the signal, and it is a different privacy promise than
#: the one made: a Builder's activity visible to people they have never met
#: (tranche_five/28, "Not across cohorts, initially").
_WATCHERS_SQL = f"""
    SELECT w.query_id, COUNT(DISTINCT w.app_user_id) AS watchers
      FROM {schema.SEARCH_WATCHERS_TABLE} w
     WHERE w.profile = %s
       AND w.removed_at IS NULL
     GROUP BY w.query_id
    HAVING COUNT(DISTINCT w.app_user_id) >= %s
     ORDER BY w.query_id
"""


def watchers_by_query(conn, profile, min_watchers=None):
    """[(query_id, distinct Builders currently watching)], threshold applied.

    min_watchers is a parameter so a test can ask what the query would say at a
    lower floor and prove the difference is the threshold rather than an empty
    table. NOTHING IN THE PIPELINE MAY PASS IT: refresh() does not, and the
    default is schema.SEARCH_MIN_WATCHERS. Lifted verbatim in shape from
    cohort.savers_by_job, including this restriction.
    """
    if min_watchers is None:
        min_watchers = schema.SEARCH_MIN_WATCHERS
    return conn.execute(_WATCHERS_SQL, (profile, min_watchers)).fetchall()


#: How many Builders this cohort has any live watch from, at all. THE VOLUME
#: INSTRUMENT, and the reason it exists is cohort.py's, unchanged: .claude
#: /CLAUDE.md says this system's failure mode is silence and to alert on volume
#: rather than errors, and at today's cohort of two this fold writes zero rows
#: on a completely healthy run. "0 searches" alone cannot tell a working fold
#: from a broken one; "0 searches, 2 builders, floor 4" can.
#:
#: A COHORT-LEVEL count, deliberately not a per-query one. It says how many
#: people use the feature, which is not a fact about any search and cannot
#: narrow anybody. "12 searches are below the threshold" would be a per-query
#: sub-threshold fact, which is the thing this module refuses to emit; it is
#: printed nowhere.
_ACTIVE_WATCHERS_SQL = f"""
    SELECT COUNT(DISTINCT w.app_user_id)
      FROM {schema.SEARCH_WATCHERS_TABLE} w
     WHERE w.profile = %s AND w.removed_at IS NULL
"""


def active_watchers(conn, profile):
    """Distinct Builders in this cohort with at least one live watch."""
    return conn.execute(_ACTIVE_WATCHERS_SQL, (profile,)).fetchone()[0]


def refresh(conn, profile, now=None, dry_run=False):
    """Rebuild this cohort's search_query_signal rows. Returns (rows, removed).

    A FULL REPLACE INSIDE ONE TRANSACTION, not an upsert -- cohort.refresh()'s
    argument, and it applies here for the same reason. The set can shrink: a
    Builder unwatches and a search drops below the floor, and that search must
    LOSE its row rather than keep a stale bucket. An upsert-only refresh would
    leave last night's badge up forever, which is a watch the Builder retracted
    still being published. The DELETE and the INSERTs commit together, so no
    reader observes the table mid-rebuild.

    Scoped to one cohort_profile, so refreshing one cohort never blanks another.
    """
    now = now or utc_now_str()
    counted = watchers_by_query(conn, profile)

    rows = []
    for query_id, watchers in counted:
        bucket = schema.search_watcher_bucket(watchers)
        # Unreachable: the query's HAVING already applied the same threshold.
        # Asserted rather than assumed because the two are the only places the
        # rule lives, and a silent disagreement between them writes a row the
        # suppression was supposed to withhold.
        assert bucket is not None, f"{query_id}: {watchers} watchers passed HAVING"
        rows.append((query_id, profile, bucket, now))

    if dry_run:
        return rows, 0

    removed = conn.execute(
        f"DELETE FROM {schema.SEARCH_SIGNAL_TABLE} WHERE cohort_profile = %s",
        (profile,)).rowcount
    for row in rows:
        conn.execute(
            f"INSERT INTO {schema.SEARCH_SIGNAL_TABLE} "
            f"(query_id, cohort_profile, watcher_bucket, computed_at) "
            f"VALUES (%s, %s, %s, %s)", row)
    conn.commit()
    # Rows that were there last night and are not now: somebody unwatched and
    # the search fell back under the floor. Reported because a badge
    # DISAPPEARING is the operator-visible half of the feature working.
    return rows, max(removed - len(rows), 0)


def summarise(profile, builders, rows):
    """One line per cohort. Buckets, never counts -- including in the log."""
    by_bucket = {label: 0 for label in schema.SEARCH_WATCHER_BUCKET_LABELS}
    for _, _, bucket, _ in rows:
        by_bucket[bucket] += 1
    spread = ", ".join(f"{label}={by_bucket[label]}"
                       for label in schema.SEARCH_WATCHER_BUCKET_LABELS)
    return (f"{profile}: {len(rows)} search(es) [{spread}], "
            f"{builders} builder(s) watching, floor={schema.SEARCH_MIN_WATCHERS}")


def active_watcher_counts(conn):
    """{query_id: current watchers}, ACROSS ALL COHORTS and with no threshold.

    A different grain from watchers_by_query() above, on purpose: decay and
    cadence are questions about the QUERY -- is anyone anywhere still asking,
    should a provider be paid -- not about one cohort's view of it, and they are
    not published to anybody. The suppressed, bucketed, per-cohort answer is the
    one that reaches a response, and it is the only one that does.
    """
    rows = conn.execute(
        "SELECT query_id, count(*) FROM search_query_watchers "
        "WHERE removed_at IS NULL GROUP BY query_id").fetchall()
    return {query_id: n for query_id, n in rows}


def apply_decay(conn, now=None):
    """Retire abandoned queries. Returns the list of retired ids.

    RETIREMENT IS A TIMESTAMP, NOT A DELETE. Nothing in this pipeline deletes
    a row to express a state change -- a closed posting is a status column, a
    dismissal is an event -- and here it also preserves the cache: a Builder
    typing the same words next month lands on the retired row, which un-retires
    the moment they watch it, rather than paying for a fresh provider call and
    losing the run history.

    The predicate is searchnorm.should_retire(), which is pure and swept by a
    table of cases in tests/test_search_queries.py. This function is the I/O
    around it and contains no rule of its own.
    """
    now = now or utc_now_str()
    watchers = active_watcher_counts(conn)
    rows = conn.execute(
        "SELECT id, source, first_requested_at, last_result_at, retired_at "
        "FROM search_queries WHERE retired_at IS NULL").fetchall()
    retired = []
    for query_id, source, first_requested_at, last_result_at, retired_at in rows:
        if searchnorm.should_retire(now, source, watchers.get(query_id, 0),
                                    first_requested_at, last_result_at,
                                    retired_at):
            conn.execute("UPDATE search_queries SET retired_at = %s WHERE id = %s",
                         (now, query_id))
            retired.append(query_id)
    conn.commit()
    return retired


def due_queries(conn, now=None):
    """Every query a provider should be asked about on this run.

    The cadence rule is searchnorm.is_due(), pure and swept. Ordered by
    last_run_at NULLS FIRST so a query nobody has ever run goes before one that
    ran yesterday -- the asynchronous promise is that a Builder's first search
    lands on the next cycle, and a fair-share order that put it behind eighty
    daily re-runs would not keep it.
    """
    now = now or utc_now_str()
    watchers = active_watcher_counts(conn)
    rows = conn.execute(
        """
        SELECT id, normalized_text, normalized_location, display_text,
               display_location, chips, source, last_run_at, retired_at
        FROM search_queries
        WHERE retired_at IS NULL
        ORDER BY last_run_at NULLS FIRST, id
        """
    ).fetchall()
    due = []
    for row in rows:
        (query_id, normalized_text, normalized_location, display_text,
         display_location, chips, source, last_run_at, retired_at) = row
        if searchnorm.is_due(now, last_run_at, watchers.get(query_id, 0),
                             source, retired_at):
            due.append({
                "id": query_id,
                "normalized_text": normalized_text,
                "normalized_location": normalized_location,
                "text": display_text,
                "location": display_location,
                "chips": json.loads(chips) if chips else None,
                "source": source,
                "watchers": watchers.get(query_id, 0),
            })
    return due


def record_run(conn, query_id, provider, result_count, now=None):
    """Mark one query as run. THE ONLY WRITER OF THE RUN STATISTICS.

    `last_result_at` moves only when the run actually returned something,
    which is what makes searchnorm.should_retire()'s "no results in 14 days"
    mean what it says. A run that returned zero rows advances last_run_at (so
    the cadence holds) and leaves last_result_at alone (so the decay clock
    keeps ticking) -- the two timestamps exist to be able to differ.

    A DEFERRAL IS NOT A FAILURE, the same rule the scoring path is built on:
    a provider that never answered (429, timeout, 5xx) must not reach this
    function at all. It writes nothing and the query stays due, rather than
    recording a run that did not happen and going quiet for 20 hours.
    """
    now = now or utc_now_str()
    conn.execute(
        """
        UPDATE search_queries
        SET last_run_at = %s,
            run_count = run_count + 1,
            provider_last_used = %s,
            result_count_last_run = %s,
            last_result_at = CASE WHEN %s > 0 THEN %s ELSE last_result_at END
        WHERE id = %s
        """,
        (now, provider, result_count, result_count, now, query_id))
    conn.commit()


def attach_results(conn, query_id, job_ids, provider=None, now=None):
    """Link postings to the query that surfaced them.

    NO GATE DECISION IS TAKEN HERE, deliberately. Every job_id a provider
    returned is linked, including the ones relevance.py will demote and the
    ones match.py will never write a match row for. The gate is applied at the
    READ edge, by the join to jobs_app in webapp/search.py -- which is the same
    placement, and the same argument, as the completeness filter in
    schema.ensure_app_view: "enforce completeness at the read edge, not the
    column".

    Doing it here instead would bake today's relevance config into a stored
    link, so raising max_tier or fixing a `\\y` pattern would not retroactively
    surface postings this pipeline already paid to fetch.
    """
    now = now or utc_now_str()
    written = 0
    for job_id in job_ids:
        conn.execute(
            "INSERT INTO search_query_results "
            "(query_id, job_id, first_seen_at, provider) VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (query_id, job_id) DO NOTHING",
            (query_id, job_id, now, provider))
        written += 1
    conn.commit()
    return written


def run_due(conn, provider=None, now=None):
    """Dispatch due queries to `provider`, or report the deferral.

    `provider` is a callable taking one due-query dict and returning a list of
    jobs.id values it wrote. None -- which is every caller today -- means
    tranche_four/23 has not landed and nothing is dispatched. See the module
    docstring for what unblocks it.

    Returns (dispatched, due_count).
    """
    due = due_queries(conn, now=now)
    if provider is None:
        return 0, len(due)
    dispatched = 0
    for query in due:
        job_ids = provider(query)
        # A provider that raised or returned None DEFERRED. Nothing is
        # recorded and the query stays due -- see record_run's docstring.
        if job_ids is None:
            continue
        attach_results(conn, query["id"], job_ids,
                       provider=getattr(provider, "name", None), now=now)
        record_run(conn, query["id"], getattr(provider, "name", None),
                   len(job_ids), now=now)
        dispatched += 1
    return dispatched, len(due)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--profile", help="only this cohort (default: all active)")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    # Imported here rather than at module scope, for cohort.py's reason: it
    # pulls in relevance.py and the pipeline's config, and this module is also
    # imported by webapp/tests/test_search_signal.py from the other venv, which
    # needs the SQL and the constants and nothing else.
    import profiles

    conn = dbconn.connect_or_exit("search-queries", schema=schema.SCHEMA)
    schema.ensure_schema(conn)

    if args.profile:
        one = profiles.load_one(conn, args.profile)
        if not one:
            print(f"search-queries FAILED: no profile named {args.profile!r}")
            sys.exit(1)
        active = [one]
    else:
        active = profiles.load_active(conn)

    now = utc_now_str()
    seeded = 0 if args.dry_run else seed(conn, now=now)

    parts = []
    for prof in active:
        rows, removed = refresh(conn, prof.profile, now=now, dry_run=args.dry_run)
        line = summarise(prof.profile, active_watchers(conn, prof.profile), rows)
        parts.append(line + (f", {removed} withdrawn" if removed else ""))

    retired = [] if args.dry_run else apply_decay(conn, now=now)
    dispatched, due = run_due(conn, now=now)

    # ALERT ON VOLUME, NOT ERRORS (.claude/CLAUDE.md). Every number is printed
    # every run, including the zeros, so a run that stopped seeding or stopped
    # folding is visible as a number that changed rather than as an absent line.
    print(f"search-queries{' [dry run]' if args.dry_run else ''}: "
          f"seeded={seeded} retired={len(retired)} due={due} "
          f"dispatched={dispatched}"
          + ("; " + "; ".join(parts) if parts else "; no active profiles"))
    if due and not dispatched:
        # Loud, on stderr, every single run. run-daily.py treats stdout as the
        # report and stderr as detail; a deferral that printed nothing would be
        # indistinguishable from a provider whose key had been revoked.
        print(f"search-queries: {due} queries are due and NO PROVIDER IS "
              f"CONFIGURED -- tranche_four/23 (backend/serp/) is descoped, so "
              f"nothing was fetched. This is a deferral, not a failure.",
              file=sys.stderr)
    if DEBUG_PRINT_KEYS and retired:
        print(f"[debug] retired query ids: {retired}", file=sys.stderr)
    conn.close()


if __name__ == "__main__":
    main()
