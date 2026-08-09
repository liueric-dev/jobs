"""A fake psycopg connection, shared by the endpoint tests in this package.

WHY A FAKE AND NOT A SCRATCH DATABASE. The claims in this suite are about which
writes an endpoint decides to issue -- does an empty submit call mark_success,
does claim write a row the daily cap can see -- and those are decisions, not
WHERE clauses. A fake falsifies a decision exactly: `conn.marked` is empty or it
is not. It cannot falsify SQL semantics, and nothing here asserts any.

(The line webapp/tests draws in the same place, and for the same reason:
test_events.py and test_set_profile.py use fakes, test_event_replay.py uses a
scratch schema because its subject is a NOT EXISTS clause. The claim-protocol
SQL in query_claims.py -- try_claim_query's conditional update, holds_claim's
three conditions -- is on the scratch-schema side of that line and is NOT
covered here; see the task file's "What the work turned up".)

DISPATCH IS ON THE SQL TEXT, never on call order. Matching on order would keep
passing if two statements were swapped or one were dropped, and "one was
dropped" is the entire subject of two of the three defects this suite closes.
Unrecognised SQL raises rather than returning an empty result, so a new
statement in a request path arrives here as a test error rather than as a
silently empty fetchone().
"""

import os
import sys

API_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if API_DIR not in sys.path:
    sys.path.insert(0, API_DIR)


class FakeResult:

    def __init__(self, rows=()):
        self._rows = list(rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class FakeConn:
    """Enough of a psycopg connection for one request against app.py.

    Everything a caller needs to assert is recorded on an attribute rather than
    reconstructed from the SQL: `log` is the submission_log rows, `marked` the
    mark_success calls, `released` the release_claim datasets, `claimed` the
    datasets try_claim_query won.
    """

    #: submission_log's column list, in the order log_submission binds them.
    LOG_COLUMNS = ("contributor_id", "dataset", "submitted_at", "fetched_count",
                   "accepted_count", "rejected_count", "reason", "action")

    #: contributor_status', in the order record_check_in binds them. Spelled out
    #: here rather than derived from qc.CONTRIBUTOR_STATUS_COLUMNS because that
    #: tuple is the TABLE's column order and this is the INSERT's -- they agree
    #: today, and a fake that assumed they always would could not fail when they
    #: stopped.
    CHECK_IN_COLUMNS = ("contributor_id", "last_check_in_at", "worker_version",
                        "quota_remaining", "quota_reported_at", "last_error",
                        "last_error_at")

    def __init__(self, *, contributor="c_test", revoked=None, claim_rows_today=0,
                 claim_state=None, last_success=None, claim_wins=True,
                 watermarks=None, settings=(None, None, None),
                 quota=(None, None)):
        self.contributor = contributor
        self.revoked = revoked
        self.claim_rows_today = claim_rows_today
        #: (paused, daily_cap, reserve_floor) as contributor_settings() reads
        #: them, straight off the row and NOT pre-resolved: all-NULL is the
        #: default and is what every test written before T-34 gets, so those
        #: tests keep asserting the behaviour of a contributor the operator has
        #: expressed no policy for. Pass None for a MISSING contributors row.
        self.settings = settings
        #: (quota_remaining, quota_reported_at) as reported_quota() reads them --
        #: what is STORED, which on a real poll may be what this very request
        #: reported. Pass None for a missing contributor_status row, which is a
        #: different fact from a row whose quota columns are NULL only to a test
        #: that cares, and the same fact to reported_quota().
        self.quota = quota
        #: (claimed_by, claimed_at, claim_granted_at), as holds_claim reads it.
        self.claim_state = claim_state
        self.last_success = last_success
        self.claim_wins = claim_wins
        #: {dataset: last_success_at} for pick_stale_queries_by_bucket.
        self.watermarks = watermarks or {}

        #: One dict per record_check_in() call, keyed by the column names it
        #: binds. A list and not a single value: "every poll checks in" is a
        #: claim about how MANY times it happened as well as with what, and a
        #: last-write-wins attribute could not tell one call from three.
        self.check_ins = []

        self.log = []
        self.marked = []
        self.released = []
        self.claimed = []
        self.stats = []
        self.commits = 0

    # psycopg's own context manager: yields the connection, does not close it.
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def commit(self):
        self.commits += 1

    def rows(self, action=None):
        """submission_log rows as dicts, optionally filtered by action."""
        out = [dict(zip(self.LOG_COLUMNS, r)) for r in self.log]
        return [r for r in out if action is None or r["action"] == action]

    def execute(self, sql, params=()):
        flat = " ".join(sql.split())

        if flat.startswith("SET search_path"):
            return FakeResult()

        # ---- reads ----------------------------------------------------
        if flat.startswith("SELECT contributor_id, revoked_at FROM api_keys"):
            return FakeResult([(self.contributor, self.revoked)]
                              if self.contributor else [])
        if flat.startswith("SELECT COUNT(*) FROM submission_log"):
            # The real column filter, applied here rather than assumed: a
            # claims_today() that stopped filtering on action must not keep
            # passing against a fake that filters for it.
            counted = self.claim_rows_today
            if "action = 'claim'" in flat:
                counted += len(self.rows("claim"))
            else:
                counted += len(self.log)
            return FakeResult([(counted,)])
        if flat.startswith("SELECT paused, daily_cap, reserve_floor FROM contributors"):
            return FakeResult([self.settings] if self.settings is not None else [])
        if flat.startswith("SELECT quota_remaining, quota_reported_at "
                           "FROM contributor_status"):
            return FakeResult([self.quota] if self.quota is not None else [])
        if flat.startswith("SELECT claimed_by, claimed_at, claim_granted_at"):
            return FakeResult([self.claim_state] if self.claim_state else [])
        if flat.startswith("SELECT last_success_at FROM job_ingest_state"):
            return FakeResult([(self.last_success,)])
        if flat.startswith("SELECT dataset, last_success_at FROM job_ingest_state"):
            return FakeResult([(d, ts) for d, ts in self.watermarks.items()])

        # ---- writes ---------------------------------------------------
        if flat.startswith("INSERT INTO submission_log"):
            self.log.append(tuple(params))
            return FakeResult()
        if flat.startswith("INSERT INTO contributor_status"):
            # Recorded as a dict rather than a tuple because the interesting
            # assertions are about WHICH facts a poll carried, and three of the
            # seven bound values are None on an ordinary check-in.
            row = dict(zip(self.CHECK_IN_COLUMNS, params))
            self.check_ins.append(row)
            # THE ONE PIECE OF SQL SEMANTICS THIS FAKE MODELS, and it is here
            # because leaving it out would make the fake actively wrong about
            # ORDER rather than merely silent about SQL. record_check_in()
            # COMMITS, and `claim` calls it before it reads the balance back --
            # so on a real poll that reported one, the read below returns what
            # this statement just wrote. A fake that kept returning the
            # constructor's value could only ever exercise the stale path, which
            # is the half of T-54 that does NOT bind. The COALESCE is mirrored
            # rather than assumed away: an unreported quota leaves the stored one
            # and its timestamp alone, which is the statement's own behaviour.
            # That the real UPSERT does this is pinned against Postgres by
            # test_contributor_status.py's TestAgainstARealDatabase.
            if row["quota_remaining"] is not None:
                self.quota = (row["quota_remaining"], row["quota_reported_at"])
            return FakeResult()
        if "RETURNING dataset" in flat:                      # try_claim_query
            if self.claim_wins:
                self.claimed.append(params["dataset"])
                return FakeResult([(params["dataset"],)])
            return FakeResult()
        if flat.startswith("INSERT INTO job_ingest_state"):   # mark_success
            self.marked.append(params)
            return FakeResult()
        if flat.startswith("UPDATE job_ingest_state SET claimed_at = NULL"):
            self.released.append(params[0])
            return FakeResult()
        if flat.startswith("INSERT INTO google_jobs_query_stats"):
            self.stats.append(params)
            return FakeResult()

        raise AssertionError(f"unexpected SQL: {flat}")


class FakeRequest:
    """Starlette's Request, reduced to the one method `submit` calls."""

    def __init__(self, body):
        self._body = body if isinstance(body, bytes) else body.encode()

    async def body(self):
        return self._body


def patch_db(app_module, conn):
    """Replace app.db() with one that yields `conn`. Returns a restorer.

    app.db() is what opens the socket; nothing else in a request path connects.
    Patching it rather than psycopg.connect keeps the fake out of
    query_claims.py's own connect path, which no test here exercises.
    """
    import contextlib

    original = app_module.db

    @contextlib.contextmanager
    def fake_db():
        yield conn

    app_module.db = fake_db

    def restore():
        app_module.db = original

    return restore
