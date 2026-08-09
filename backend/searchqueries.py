"""The nightly search-query step: seed, reconcile, fold, decay, dispatch.

Five things, in that order, and the order is not arbitrary:

  1. SEED    config/search-queries.json into `search_queries`, one row per
             extract.ROLE_TRACK. First, so a track added since the last run is
             visible to everything below on the same night.
  2. RECON   advance the run statistics of queries a CONTRIBUTOR ran, from the
             submission_log rows api/ wrote (docs/adr/0009). Before the decay,
             because should_retire() reads last_result_at and a query a
             contributor is actively feeding must not retire on a figure that
             has not been posted yet; before the dispatch, because the whole
             point is that a query somebody already spent a credit on is not
             due again tonight.
  3. FOLD    current watcher counts into `search_query_signal`, per cohort --
             suppressed below schema.SEARCH_MIN_WATCHERS and bucketed above it.
             This is the ONLY writer of that table, and the service role holds
             SELECT on it and nothing else. See ensure_search_query_schema()'s
             docstring in schema.py.
  4. DECAY   mark abandoned queries retired so they stop consuming quota.
             After the fold, so a query retiring tonight still had its badge
             computed from the watchers it had; before dispatch, so a retired
             query is not run one last time on the night it retires.
  5. RUN     dispatch the due queries to a provider.

~~WHAT STEP 5 DOES NOT DO YET, AND THE BLOCKER BY NAME.~~ STEP 5 DISPATCHES, as
of 2026-08-02. tranche_four/23 landed `backend/serp/`, and build_provider()
below hands run_due() a serp.dispatch.SearchQueryProvider -- the callable this
docstring used to describe as missing, which it named correctly: it takes a due
query and returns the jobs.id values it wrote.

IT CAN STILL DISPATCH NOTHING, and the reason is printed on stderr every run:
--dry-run, no credential for the chosen provider, or nothing due. That line is
not decoration. ".claude/CLAUDE.md" says silence is this system's failure mode
-- exhausted keys and changed endpoints all return zero rows rather than
raising -- and a search runner that quietly did nothing is indistinguishable
from one whose provider had been cut off.

STEP 5 NOW SPENDS METERED CREDIT, WHICH CHANGES WHAT --dry-run IS FOR. It was a
report; it is now also an estimate of what the next real run will cost, one
provider call per due query. That is why seed() takes a dry_run flag rather
than being skipped: an unseeded catalogue is nine never-run queries, is_due()
says a never-run query is due immediately, and a dry run that skipped the seed
answered `due=0` for a night that would have dispatched nine.

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

#: The five columns record_run() owns, named once so the boundary docs/adr/0009
#: draws can be ASSERTED rather than described.
#: backend/api/tests/test_run_statistics_boundary.py reads this tuple and fails
#: if any of these names turns up in a statement on the service side; a second
#: test parses record_run's own UPDATE and fails if this tuple and that SET
#: clause stop agreeing, so the guard cannot end up covering nothing (T-39's
#: lesson).
RUN_STATISTICS = ("last_run_at", "run_count", "provider_last_used",
                  "result_count_last_run", "last_result_at")

#: `submission_log.dataset`, for a `search_queries` row.
#:
#: WHY A PREFIX AND NOT AN ID COLUMN. submission_log's dataset is TEXT and
#: already carries "google_jobs:query:<slug>" for the other claim mode, so the
#: two modes are told apart by the prefix and nothing else. A `query_id` column
#: would be the tidier shape and is not available: the service holds no DDL
#: rights (api/query_claims.py:267), so adding one is an admin command on a
#: deployed database, and the prefix costs nothing that a column would buy.
#:
#: DEFINED HERE, ON THE PIPELINE SIDE, AND IMPORTED BY api/. That is the only
#: direction available -- .claude/CLAUDE.md's layout rule is that no pipeline
#: module imports api/ or webapp/, while api/ already imports google_jobs and
#: schema. It is also the right way round on the merits: the reader of these
#: rows is the reconciler below, and a convention owned by its writer is one
#: the reader has to keep guessing at.
CONTRIBUTOR_DATASET_PREFIX = "search_query:"

#: submission_log.action for "this contributor's submit advanced the watermark".
#:
#: A FOURTH ACTION RATHER THAN AN INFERENCE FROM THE `submit` ROW, and the
#: reason is that the inference is not available. api/app.py writes a `submit`
#: row on the success path AND on both refusal paths, and `reason` does not
#: separate them -- the success path sets a reason too when records failed to
#: write (api/app.py:493). Counting a refused submit as a run is exactly defect
#: D08 (an empty submission advancing a watermark) rebuilt one table over, so
#: the signal is written explicitly by the side that knows, on the same branch
#: mark_success sits on in the other mode.
CONTRIBUTOR_RUN_ACTION = "run"

#: provider_last_used, for a run performed on a contributor's own SerpApi key.
#: Distinct from the pipeline's own provider names on purpose: "who ran this"
#: is the question an operator asks of a query bank shared between one nightly
#: pipeline and ~30 Builders' machines, and provider_last_used is the only
#: column that can answer it.
CONTRIBUTOR_PROVIDER = "contributor:serpapi"




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


def seed(conn, path=None, now=None, dry_run=False):
    """Insert the catalogue. Idempotent, and returns how many rows are new.

    ON CONFLICT DO UPDATE assigning a column to itself, via the same statement
    the webapp uses. A seed run must never overwrite a query a Builder created
    first: if someone typed "data analyst" before the catalogue landed, the row
    is theirs, keeps source='builder', and the seed is a no-op on it. The
    alternative -- upgrading it to source='track' -- would make it undecayable
    for having been typed early, which is a rule nobody would guess.

    `dry_run` counts what WOULD be created and writes nothing. It exists
    because --dry-run became a spend estimate the day task 23 gave run_due() a
    real provider: a seeded query has never run, searchnorm.is_due() says a
    never-run query is due immediately whatever its source, and every due query
    is now one metered provider call. A dry run that skipped seeding reported
    `due=0` on a fresh database while the next real run would have dispatched
    the whole catalogue -- an estimate that is wrong in the expensive direction
    on exactly the night it is most likely to be consulted.
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
        if not dry_run:
            conn.execute(searchnorm.REGISTER_QUERY_SQL,
                         (normalized_text, normalized_location,
                          entry["text"], entry["location"], None,
                          "track", entry["role_track"], now))
        if before is None:
            created += 1
    if not dry_run:
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
"""  # noqa: S608 -- splices schema.SEARCH_WATCHERS_TABLE, a module-level constant


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
"""  # noqa: S608 -- splices schema.SEARCH_WATCHERS_TABLE, a module-level constant


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
        f"DELETE FROM {schema.SEARCH_SIGNAL_TABLE} WHERE cohort_profile = %s",  # noqa: S608 -- splices schema.SEARCH_SIGNAL_TABLE, a module-level constant
        (profile,)).rowcount
    for row in rows:
        conn.execute(
            f"INSERT INTO {schema.SEARCH_SIGNAL_TABLE} "  # noqa: S608 -- splices schema.SEARCH_SIGNAL_TABLE, a module-level constant
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
                # Selected all along and dropped on the floor until task 23.
                # serp/datechip.py needs it to narrow the run to the window
                # that actually elapsed for THIS query; without it every run
                # re-asks Google the same unfiltered question and pays for the
                # same relevance-ranked page again.
                "last_run_at": last_run_at,
                "source": source,
                "watchers": watchers.get(query_id, 0),
            })
    return due


def record_run(conn, query_id, provider, result_count, now=None):
    """Mark one query as run. THE ONLY WRITER OF THE RUN STATISTICS.

    STILL THE ONLY ONE, AFTER docs/adr/0009 GAVE CONTRIBUTORS A SECOND WAY TO
    RUN A QUERY. reconcile_contributor_runs() below advances the statistics for
    a run a contributor performed, and it does so BY CALLING THIS FUNCTION --
    it holds no UPDATE of its own. That is not tidiness: the five columns are
    written in one place, so the last_result_at rule in the next paragraph
    applies to a contributor's run without anybody having to remember to copy
    it, and the GRANT that keeps api/ off these columns has exactly one
    function to be true about.

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


def dataset_for_query(query_id):
    """The submission_log.dataset string naming one `search_queries` row."""
    return f"{CONTRIBUTOR_DATASET_PREFIX}{query_id}"


def query_id_from_dataset(dataset):
    """The id `dataset` names, or None if it does not name one of these rows.

    None rather than a raise, because this parses a TEXT column that the other
    claim mode also writes to and that predates both -- "google_jobs:query:x"
    and a row written before this convention existed are both ordinary things
    to meet here, not corruption.
    """
    if not dataset or not dataset.startswith(CONTRIBUTOR_DATASET_PREFIX):
        return None
    try:
        return int(dataset[len(CONTRIBUTOR_DATASET_PREFIX):])
    except ValueError:
        return None


def reconcile_contributor_runs(conn):
    """Advance the run statistics for queries a CONTRIBUTOR ran. docs/adr/0009.

    THE PROBLEM THIS SOLVES, in one line: api/ can free a claim on a
    `search_queries` row but cannot record that the row was run, so without
    this the row is due again the moment it is released and the next cycle
    spends a second contributor's credit on a search that already happened.

    WHY THE PIPELINE DOES IT AND NOT api/. The five columns are the pipeline's
    and the split is enforced by GRANT rather than by comment (schema.py:992).
    Handing api/ UPDATE on them would let a submit forge a run history and
    silence a query for every Builder by writing a future last_run_at -- and a
    "narrow writer in api/ that only sets them from server-side values" buys
    the identical privilege and pays for it with a rule a person has to
    remember. So the fact crosses the boundary as a row in submission_log,
    which api/ already holds INSERT on and the pipeline already owns, and no
    grant changes in either direction. The full argument is docs/adr/0009.

    IDEMPOTENT WITH NO NEW STATE, which is why there is no watermark table
    here. A run row counts only if it is newer than the last_run_at it would
    advance, and advancing sets last_run_at TO THAT ROW'S OWN submitted_at --
    so the same row cannot count twice, a re-run reconciles nothing, and two
    submits since the last cycle are two runs rather than one. That also keeps
    ONE CLOCK: every timestamp written here comes off the log row, never off
    this process's wall clock, so nothing in this path can rot the way two
    tests in this repo already have by pairing a real clock with a frozen one.

    RETURNS (reconciled, skipped, table_present). `table_present` is False when
    submission_log does not exist, which is an ordinary state and not an error:
    api/query_claims.ensure_schema() creates that table and a database
    provisioned before T-39 -- or any scratch schema built from schema.py
    alone -- will not have it. main() prints all three every run rather than
    swallowing the third, because a reconciler that silently did nothing is
    indistinguishable from one with nothing to do.
    """
    present = conn.execute(
        "SELECT to_regclass('submission_log') IS NOT NULL").fetchone()[0]
    if not present:
        return 0, 0, False

    rows = conn.execute(
        """
        SELECT l.dataset, l.submitted_at, l.accepted_count
        FROM submission_log l
        WHERE l.action = %s
          AND l.dataset LIKE %s
        ORDER BY l.submitted_at, l.id
        """,
        (CONTRIBUTOR_RUN_ACTION, CONTRIBUTOR_DATASET_PREFIX + "%"),
    ).fetchall()

    reconciled, skipped = 0, 0
    for dataset, submitted_at, accepted_count in rows:
        query_id = query_id_from_dataset(dataset)
        if query_id is None or not submitted_at:
            skipped += 1
            continue
        # The comparison the docstring calls the watermark, done here rather
        # than in the SELECT's WHERE: last_run_at moves as this loop runs, so a
        # predicate evaluated once against the pre-loop value would let two run
        # rows for one query both pass and then write them in an order the
        # ORDER BY no longer guarantees anything about.
        current = conn.execute(
            "SELECT last_run_at FROM search_queries WHERE id = %s",
            (query_id,)).fetchone()
        if current is None:
            # A log row naming a query that is gone. Not corruption: the row
            # is an audit trail and outlives what it names.
            skipped += 1
            continue
        if current[0] and submitted_at <= current[0]:
            skipped += 1
            continue
        record_run(conn, query_id, CONTRIBUTOR_PROVIDER,
                   accepted_count or 0, now=submitted_at)
        reconciled += 1
    return reconciled, skipped, True


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


def build_provider(conn, *, dry_run=False, provider=None):
    """The dispatch callable for run_due(), or (None, why not).

    A PAIR RATHER THAN None ALONE, because "no provider" has three causes and
    the operator has to act differently on each: nothing is configured, the key
    is missing, or this is a dry run. All three used to print the same
    hard-coded sentence about task 23 being descoped -- which was true until
    today and would have gone on being printed after it stopped being true.

    The import is inside the function for the same reason `import profiles` is
    (see main): webapp/tests/test_search_signal.py imports this module from the
    other venv for the SQL and the constants, and serp/ reaches google_jobs.py
    and the pipeline's config.
    """
    if dry_run:
        return None, "--dry-run, so no credit was spent"
    from serp import cache, dispatch, quota  # noqa: PLC0415 -- see the docstring
    name = provider or os.environ.get("SEARCH_QUERY_PROVIDER") or None
    try:
        fn = dispatch.SearchQueryProvider(
            conn, provider=name, debug=DEBUG_PRINT_KEYS,
            cache=cache, ledger=quota.Ledger())
    except ValueError as e:
        return None, str(e)
    if not fn.configured:
        return None, (f"{fn.name} has no credential -- set "
                      f"{dispatch.CRED_ENV[fn.name]} in backend/.env")
    return fn, f"{fn.name} is configured"


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
    seeded = seed(conn, now=now, dry_run=args.dry_run)

    # STEP 2, AND ITS PLACE IN THE ORDER IS LOAD-BEARING -- see the module
    # docstring. --dry-run skips it for seed()'s reason inverted: this one
    # WRITES, and a report must not advance a watermark. The cost is stated in
    # the printed line rather than hidden, because a dry run that silently
    # under-counted `due` is the failure mode this file already carries a
    # paragraph about.
    reconciled, recon_skipped, log_present = (
        (0, 0, True) if args.dry_run else reconcile_contributor_runs(conn))

    parts = []
    for prof in active:
        rows, removed = refresh(conn, prof.profile, now=now, dry_run=args.dry_run)
        line = summarise(prof.profile, active_watchers(conn, prof.profile), rows)
        parts.append(line + (f", {removed} withdrawn" if removed else ""))

    retired = [] if args.dry_run else apply_decay(conn, now=now)

    # THE PROVIDER IS BUILT HERE AND NOWHERE ELSE. --dry-run must not spend a
    # metered credit, and a missing key is a deferral rather than a failure:
    # build_provider() returns None and the loud stderr line below says which
    # of the two it was.
    provider, why_not = build_provider(conn, dry_run=args.dry_run)
    dispatched, due = run_due(conn, provider=provider, now=now)

    # ALERT ON VOLUME, NOT ERRORS (.claude/CLAUDE.md). Every number is printed
    # every run, including the zeros, so a run that stopped seeding or stopped
    # folding is visible as a number that changed rather than as an absent line.
    # ON A DRY RUN, `due` UNDER-REPORTS AND THE ARITHMETIC IS SPELLED OUT.
    # Nothing was seeded, so run_due() could not see the rows the seed would
    # have created -- and every one of those is a never-run query, which
    # is_due() makes due immediately, which is now one metered provider call
    # each. Printing the sum is the difference between a report and an estimate.
    would_be_due = f" (+{seeded} once seeded)" if args.dry_run and seeded else ""
    print(f"search-queries{' [dry run]' if args.dry_run else ''}: "
          f"seeded={seeded} reconciled={reconciled} "
          f"retired={len(retired)} due={due}{would_be_due} "
          f"dispatched={dispatched}"
          + (f" via {provider.name}" if provider else "")
          + ("; " + "; ".join(parts) if parts else "; no active profiles"))
    if provider is not None and getattr(provider, "stats", None):
        # The spend, in the provider's own unit, every run. A search that costs
        # nothing is a cache hit or a query that did not run, and both are
        # things an operator should be able to see without turning on debug.
        print(f"search-queries spend: {provider.stats}")
        # And the vendor's own answer beside it, which is the whole point of
        # the ledger: DECISIONS.md records this pipeline's view of its SerpApi
        # spend being wrong by 3.3x in the dangerous direction, and it stayed
        # wrong because nothing ever printed the two numbers next to each other.
        if provider.ledger is not None:
            print(provider.ledger.report([provider.name]))
    if due and not dispatched:
        # Loud, on stderr, every single run. run-daily.py treats stdout as the
        # report and stderr as detail; a deferral that printed nothing would be
        # indistinguishable from a provider whose key had been revoked.
        print(f"search-queries: {due} queries are due and NOTHING WAS "
              f"DISPATCHED -- {why_not}. This is a deferral, not a failure.",
              file=sys.stderr)
    if not log_present:
        # LOUD, ON STDERR, for the reason the deferral line above is loud.
        # "reconciled=0" is what a night with no contributor runs prints and
        # also what a database missing the table prints, and the second is a
        # contributor's spent credit going unrecorded every night until
        # somebody notices. The two must not look the same.
        print("search-queries: submission_log is ABSENT, so no contributor "
              "run was reconciled -- run tools/provision-database.py (step 6) "
              "against this database. This is a deferral, not a failure.",
              file=sys.stderr)
    if DEBUG_PRINT_KEYS and recon_skipped:
        print(f"[debug] contributor run rows already reconciled or "
              f"unresolvable: {recon_skipped}", file=sys.stderr)
    if DEBUG_PRINT_KEYS and retired:
        print(f"[debug] retired query ids: {retired}", file=sys.stderr)
    conn.close()


if __name__ == "__main__":
    main()
