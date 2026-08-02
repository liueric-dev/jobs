"""One interface over every Google Jobs provider. Task 23, sharply descoped.

WHAT THIS IS FOR, AND THE SEAM IT FILLS
    searchqueries.run_due(conn, provider=None) has taken a callable since task
    25 landed and every caller has passed None, so `search_query_results` is
    empty in production and the search screen task 32 built reads a table
    nothing writes. searchqueries.py's module docstring names the missing piece
    exactly: "a callable taking (text, location, chips, date_chip) and
    returning normalized Google Jobs records ... lifting it behind an interface
    is task 23." serp.dispatch.SearchQueryProvider is that callable and this
    module is the interface under it.

THE DESCOPE IS A DECISION, NOT AN OMISSION
    DECISIONS.md, "EXP -- Build task 23, sharply descoped": keep the single
    interface, the normalizer into lib/'s frozen shape, SerpResult provenance,
    the quota ledger, the cache and volume alerting. Cut the JobSpy adapter,
    its canary and router step 2 (task 22 dropped JobSpy), and six of the eight
    provider adapters. So `call()` reaches two providers, not eight, and
    23-serp-abstraction.md's "at least three providers" is reported UNMET with
    the descope named rather than tuned into being met.

WHAT AN ADAPTER IS ALLOWED TO BE
    One function, `fetch(query, location, creds, *, date_chip) -> raw`, plus
    module-level data describing the account it spends. Normalisation, routing,
    accounting and caching live out here, so adding a provider stays one small
    file. In particular NO adapter normalises: they return the provider's own
    payload and serp/normalize.py is the only route into google_jobs.py.

THE THREE FAILURE CLASSES, AND WHY A CALLER MUST BE ABLE TO TELL THEM APART
    ".claude/CLAUDE.md" states the rule this repo turns on -- "A deferral is not
    a failure" -- and searchqueries.record_run()'s own docstring repeats it: a
    provider that never answered "must not reach this function at all", or the
    query records a run that did not happen and goes quiet for the cadence
    window. So:

      Deferred        the endpoint never answered usably -- 429 after
                      lib/http.py exhausted its backoff, a 5xx, a timeout, a
                      dropped connection. Nothing is recorded, the query stays
                      due, and the next run retries it.
      RuntimeError    the provider answered, the credit is spent, and the
                      answer was unusable for THIS query. The run is recorded
                      with zero results -- pretending it did not happen would
                      spend the credit again tomorrow.
      ProviderRefused the account is the problem, not the query -- bad key,
                      exhausted plan. Raised, not swallowed, because it is
                      identical for every remaining query and nine silent
                      zeroes is exactly the "alert on volume, not errors"
                      failure this file's own task warns about.
"""

import time
import urllib.error

from serp import normalize
from serp.providers import apify as _apify
from serp.providers import serpapi as _serpapi


class Deferred(Exception):
    """The endpoint never answered usably. Write nothing; retry next run."""


class ProviderRefused(Exception):
    """The ACCOUNT is refused, not the query -- bad key, or plan exhausted.

    Separate from Deferred because retrying does not help and separate from
    RuntimeError because it is not about the query that happened to be first
    in the list. A caller that catches this per query turns one dead key into
    one quiet night per query; the intended handling is to stop.
    """


#: The two the descope keeps. Order is the router's fallthrough order, and it
#: is deliberately data rather than an if/elif -- ADDENDUM-google-jobs-providers.md
#: lists eight and the six that are cut are cut by not appearing here.
PROVIDERS = {
    _serpapi.NAME: _serpapi,
    _apify.NAME: _apify,
}

#: Cheapest renewable first. SerpApi bills one search per call against a
#: monthly allowance; Apify bills per RESULT out of a dollar balance, so a
#: 10-result query costs ten times what a 1-result query costs and it is the
#: wrong instrument for a routine nightly search.
ORDER = (_serpapi.NAME, _apify.NAME)


class SerpResult:
    """One provider answer, plus what it cost and where it came from.

    Shaped after llm.Completion (llm.py:167-184), which carries usage beside
    the text for the same reason: a number reported without the call that
    produced it cannot be checked later.

    `credits` is in the PROVIDER's unit and the unit travels with it, because
    the units genuinely differ and summing them would be wrong -- SerpApi
    counts searches, Apify counts results, and ADDENDUM-google-jobs-providers.md
    records two more that bill 25 credits for one Google request. A ledger that
    counted raw requests would be wrong by an order of magnitude for those.

    `from_cache` is what makes cost and latency unreportable -- see cost_line().
    """

    __slots__ = ("records", "provider", "credits", "unit", "from_cache",
                 "latency_s", "raw_count")

    def __init__(self, records, provider, *, credits=0, unit=None,
                 from_cache=False, latency_s=None, raw_count=None):
        self.records = records
        self.provider = provider
        self.credits = credits
        self.unit = unit
        self.from_cache = from_cache
        self.latency_s = latency_s
        self.raw_count = raw_count if raw_count is not None else len(records)

    def __repr__(self):
        return (f"SerpResult({len(self.records)} records, provider="
                f"{self.provider!r}, credits={self.credits} {self.unit}, "
                f"from_cache={self.from_cache})")


def cost_line(results):
    """Render cost and latency, or say why they are absent. THE ONLY RENDERER.

    Enforced HERE rather than by asking each caller to remember, which is the
    rule evals/report.py:1-11 already applies to replayed LLM answers: "a
    replayed response carries the latency and token usage of the call that
    produced it ... mixing them produces a confident wrong number". A cached
    SERP answer is the same shape of lie -- it cost nothing today and took no
    time today, and a nightly report that averages it in reports a provider
    getting cheaper as its cache warms.

    So a run containing ANY cached result reports neither, and names the count.
    """
    results = list(results)
    if not results:
        return "no provider calls"
    cached = [r for r in results if r.from_cache]
    if cached:
        return (f"cost/latency not reported -- {len(cached)}/{len(results)} "
                f"answers were served from cache")
    by_unit = {}
    for r in results:
        by_unit[r.unit] = by_unit.get(r.unit, 0) + r.credits
    spend = ", ".join(f"{v} {k}" for k, v in sorted(by_unit.items()))
    lat = [r.latency_s for r in results if r.latency_s is not None]
    if not lat:
        return spend
    return f"{spend}, {sum(lat):.1f}s over {len(lat)} call(s)"


def resolve(provider=None):
    """The provider module for a name, or the first in ORDER.

    A name that is not in PROVIDERS raises rather than falling back to the
    default: six of the eight adapters are CUT, and silently serving
    "scrapingbee" from SerpApi would spend a metered credit against a config
    line that says not to.
    """
    if provider is None:
        return PROVIDERS[ORDER[0]]
    try:
        return PROVIDERS[provider]
    except KeyError:
        raise ValueError(
            f"unknown provider {provider!r}; the descope keeps "
            f"{sorted(PROVIDERS)} -- see DECISIONS.md, 'Build task 23, sharply "
            f"descoped'") from None


def _fetch(mod, text, location, creds, date_chip):
    """mod.fetch(), with every transport failure sorted into one of the three
    classes. THE ONLY PLACE THAT SORTING HAPPENS.

    It is here and not in each adapter because the classification is a property
    of what the CALLER may do about it, not of the vendor -- and because
    ingest/google-serpapi.py:385 shows the alternative: an except-tuple spelled
    out at the call site, which the next call site copies approximately.

    ORDER MATTERS AND IT IS NOT COSMETIC. urllib.error.HTTPError is a SUBCLASS
    of URLError, and URLError is in every adapter's DEFERRING_EXCEPTIONS. If
    the HTTPError clause came second, a 401 on a revoked key would be caught by
    the URLError clause, reported as a deferral, and retried every night
    forever with nothing ever recorded -- a dead key that looks exactly like a
    quiet one. That is this repo's named failure mode, reached through an
    ordering.

    lib/http.py has already retried anything retryable by the time an exception
    arrives here (429 and 5xx back off up to DEFAULT_MAX_RETRIES and then
    re-raise), so a 429 reaching this function means the backoff was exhausted,
    not that no wait was tried.
    """
    try:
        return mod.fetch(text, location, creds, date_chip=date_chip)
    except mod.AccountRefused as e:
        raise ProviderRefused(f"{mod.NAME}: {e}") from e
    except urllib.error.HTTPError as e:          # MUST precede URLError
        if e.code == 429 or 500 <= e.code < 600:
            raise Deferred(f"{mod.NAME}: HTTP {e.code} after backoff") from e
        raise
    except mod.DEFERRING_EXCEPTIONS as e:
        raise Deferred(f"{mod.NAME}: {type(e).__name__}: {e}") from e


def call(text, location, *, date_chip=None, provider=None, creds=None,
         cache=None, ledger=None, now=None):
    """One search, normalised into google_jobs.py's record shape.

    `date_chip` is Google's `chips=date_posted:X` bucket and None means no
    filter at all -- the deliberate backfill on a query's first ever run, per
    ingest/google-serpapi.py's DATE FILTER section. choose_date_chip() there
    owns picking it; this function only passes it down.

    Raises Deferred, RuntimeError or ProviderRefused per the three classes in
    the module docstring. Returns a SerpResult even when the provider answered
    with nothing, because zero results is an answer and the credit is spent.
    """
    mod = resolve(provider)
    key = None
    if cache is not None:
        key = cache.key(text, location, date_chip=date_chip,
                        provider=mod.NAME, now=now)
        hit = cache.get(key, now=now)
        if hit is not None:
            return SerpResult(normalize.records(hit, location), mod.NAME,
                              credits=0, unit=mod.UNIT, from_cache=True,
                              raw_count=len(hit))

    if ledger is not None:
        ledger.check(mod.NAME)          # raises ProviderRefused when exhausted

    started = time.monotonic()
    raw = _fetch(mod, text, location, creds, date_chip)
    latency = time.monotonic() - started

    if cache is not None:
        cache.put(key, raw, now=now)
    if ledger is not None:
        ledger.spend(mod.NAME, mod.credits_for(raw))

    return SerpResult(normalize.records(raw, location), mod.NAME,
                      credits=mod.credits_for(raw), unit=mod.UNIT,
                      from_cache=False, latency_s=latency, raw_count=len(raw))
