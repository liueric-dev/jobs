"""The callable searchqueries.run_due() takes. This is the seam task 23 fills.

run_due(conn, provider=None) has had this signature since task 25 landed and
every caller has passed None, so `search_query_results` is empty in production
and webapp/search.py's join returns nothing for every Builder. Its contract, in
its own words (searchqueries.py:389-414):

    provider(query) -> list of jobs.id values it wrote
                    -> None to DEFER: "nothing is recorded and the query stays
                       due"
    provider.name   -> stored on both search_query_results.provider and
                       search_queries.provider_last_used

SearchQueryProvider implements exactly that and nothing more. It does not
decide which queries are due (searchnorm.is_due), does not write the run
statistics (searchqueries.record_run is "THE ONLY WRITER") and does not link
results (searchqueries.attach_results). Those exist, are tested, and are not
re-implemented here.

WHY THE RETURNED IDS ARE READ BACK FROM `jobs` RATHER THAN COMPUTED
    search_query_results.job_id REFERENCES jobs(id) (schema.py:1104), so an id
    for a record the upsert rejected is a foreign key violation that takes the
    whole attach with it. lib/upsert.py isolates per record and collects
    failures in UpsertResult.errors, so "normalised" and "stored" are genuinely
    different sets and the difference is exactly the rows that must not be
    attached. Reading `SELECT id FROM jobs WHERE id = ANY(...)` after the write
    is one query and it is authoritative, where deriving the set from
    .errors would be a second opinion about what the database did.

    It reads the BASE TABLE, not jobs_app, and that is attach_results()'s
    decision restated rather than a new one: "NO GATE DECISION IS TAKEN HERE
    ... the gate is applied at the READ edge". Filtering here would bake
    today's relevance config into a stored link.

WHAT A ZERO-RESULT RUN MEANS, AND WHY IT IS NOT A DEFERRAL
    Returning [] records a run that found nothing: last_run_at moves,
    last_result_at does not, and searchnorm.should_retire()'s "no results in 14
    days" clock keeps ticking. That is correct when the provider answered --
    the credit is spent and pretending otherwise spends it again tomorrow.
    Returning None records nothing at all. The two are one keystroke apart in
    the code and a fortnight apart in what they mean, which is why the three
    failure classes in serp/__init__.py are raised as three exception types
    rather than returned as a status string.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import schema  # noqa: E402  (../schema.py)
import serp  # noqa: E402
from lib.upsert import UpsertErrorRate, upsert_checked  # noqa: E402
from serp import datechip  # noqa: E402

#: Where each provider's credential is read from. The read happens HERE, from
#: os.environ and nowhere else, which is the property tests/test_secrets_rotation.py
#: pins: no credential is a literal in tracked code and none is read from
#: anywhere but the process environment, so rotating one is `edit .env` plus a
#: restart rather than a commit.
#:
#: A provider missing from this map reads as UNCONFIGURED rather than raising,
#: and the coverage is asserted by a test instead (tests/test_serp.py,
#: test_credentials_are_read_from_the_environment_and_nowhere_else). Raising
#: here would put a KeyError on the nightly path to catch an omission that a
#: test catches at rest; being merely unconfigured is loud enough, because
#: build_provider() prints which credential is missing and dispatches nothing.
CRED_ENV = {
    "serpapi": "SERPAPI_API_KEY",
    "apify": "APIFY_API_TOKEN",
}


def credentials_for(name, env=None):
    """The key for a provider, or None. Never logged, never returned upward.

    `env is None` rather than `env or os.environ`: an EMPTY mapping is a
    legitimate argument meaning "an environment with no credentials in it", and
    the falsy-or idiom answers it from the real environment instead. A test
    asserting "no key configured -> None" would then pass or fail depending on
    the developer's own .env, which is the kind of test that is worse than none.
    """
    environ = os.environ if env is None else env
    var = CRED_ENV.get(name)
    return (environ.get(var) or None) if var else None


class SearchQueryProvider:
    """One provider, bound to one connection, callable per due query.

    Deliberately an object with a `.name` rather than a closure, because
    run_due() reads `provider.name` for two stored columns and
    getattr(fn, "name", None) on a bare function silently stores NULL -- a
    column that says which provider served a result, quietly not saying it.
    """

    def __init__(self, conn, *, provider=None, creds=None, cache=None,
                 ledger=None, debug=False, stats=None):
        self._mod = serp.resolve(provider)
        self.name = self._mod.NAME
        self._conn = conn
        self._creds = creds if creds is not None else credentials_for(self.name)
        #: Public, because main() prints the reconciliation after the loop and
        #: reaching into a private attribute to do it is how the caller ends up
        #: owning a detail of this class.
        self.cache = cache
        self.ledger = ledger
        self._debug = debug
        self._spec = schema.google_spec()
        #: Optional Counter. Same pattern as match.match_profile's `stats`
        #: (D20): an optional out-parameter rather than a fourth return value,
        #: because run_due()'s contract fixes the return type.
        self.stats = stats if stats is not None else {}

    @property
    def configured(self):
        """Whether a credential was found. The key itself is never exposed --
        a caller needs the boolean, and a property that returned the string
        would put it one f-string away from a log line."""
        return bool(self._creds)

    def __call__(self, query):
        """One due query. Returns written jobs.id values, or None to defer."""
        date_chip = datechip.choose(query.get("last_run_at"))
        try:
            result = serp.call(query["text"], query["location"],
                               date_chip=date_chip, provider=self.name,
                               creds=self._creds, cache=self.cache,
                               ledger=self.ledger)
        except serp.Deferred as e:
            self._bump("deferred")
            self._log(f"deferred {query['text']!r}: {e}")
            return None
        except serp.ProviderRefused:
            # NOT caught per query. The account is refused for every remaining
            # query too, and swallowing it here turns one dead key into a bank
            # of quiet zeroes -- "alert on volume, not errors" cannot see that,
            # because the volume is zero for a reason nothing recorded.
            self._bump("refused")
            raise
        except RuntimeError as e:
            # The provider answered and the answer was unusable for THIS query.
            # The credit is spent, so the run is recorded with no results.
            self._bump("unusable")
            self._log(f"unusable answer for {query['text']!r}: {e}")
            return []

        try:
            written = upsert_checked(self._conn, self._spec, result.records,
                                     schema.make_job_id, debug=self._debug)
        except UpsertErrorRate as e:
            # Counted, not raised. The error-rate ceiling is a run-level
            # judgement and one query is not a run -- the same disposition
            # ingest/google-serpapi.py:409-413 takes, for the same reason: the
            # credit is spent either way.
            written = e.result
            self._bump("error_rate")
            self._log(f"error rate exceeded on {query['text']!r}: {e}")

        self._bump("queries")
        self._bump("new", written.new)
        self._bump("updated", written.updated)
        self._bump("dropped", len(written.errors))
        self._bump("credits", result.credits)
        if result.from_cache:
            self._bump("cache_hits")

        ids = self._stored_ids(result.records)
        self._log(f"{query['text']!r} @ {query['location']} (chip={date_chip}): "
                  f"{result.raw_count} results -> {written.new} new, "
                  f"{written.updated} updated, {len(ids)} attachable")
        return ids

    def _stored_ids(self, records):
        """Which of these records are actually rows in `jobs`, in order."""
        if not records:
            return []
        candidates = [schema.make_job_id(rec) for rec in records]
        rows = self._conn.execute(
            "SELECT id FROM jobs WHERE id = ANY(%s)", (candidates,)).fetchall()
        stored = {row[0] for row in rows}
        # Order is preserved and duplicates dropped: one search can return the
        # same posting twice through two apply_options, and attach_results'
        # ON CONFLICT DO NOTHING would absorb it silently while record_run
        # counted it twice.
        seen, out = set(), []
        for job_id in candidates:
            if job_id in stored and job_id not in seen:
                seen.add(job_id)
                out.append(job_id)
        return out

    def _bump(self, key, n=1):
        self.stats[key] = self.stats.get(key, 0) + n

    def _log(self, message):
        if self._debug:
            print(f"[debug] {self.name}: {message}", file=sys.stderr)

    def __repr__(self):
        return f"SearchQueryProvider({self.name!r})"
