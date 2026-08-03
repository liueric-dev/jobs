"""What a search query IS -- normalisation, cadence, decay, and the SQL that
registers one. Pure: stdlib only, no I/O, no database handle anywhere.

WHAT IS NOT HERE, AND WHERE IT WENT. The suppression threshold, the bucket
boundaries and search_watcher_bucket() live in schema.py, beside
COHORT_MIN_SAVERS / COHORT_BUCKETS / cohort_bucket() and shaped identically.
That is not tidiness: schema.py generates the CHECK constraint from the same
tuple the writer reads, so the vocabulary cannot be widened in Python while
Postgres keeps refusing the new value -- and putting one suppression rule in a
different file from the other is how two answers to "what is shared" start to
drift. This module cannot import schema.py anyway; schema.py is where a
psycopg import lives, and the point of this file is that it has none.

WHY THIS IS ITS OWN MODULE, AND WHY BOTH PROCESSES IMPORT IT
    Caching correctness is entirely a property of normalisation. Two Builders
    typing "AI Operations" and "ai  operations!" have to land on ONE row or
    the whole argument in `git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_four/25-search-queries.md` -- "the fifth
    Builder to search 'AI operations NYC' costs nothing" -- is false. A second
    implementation of `normalize()` in webapp/ would not fail loudly; it would
    quietly halve the hit rate, and the only symptom would be a provider bill.

    So this is the one definition, and it is shaped so that sharing it costs
    nothing: stdlib only, no psycopg import, no config file read, no network.
    `.claude/CLAUDE.md` says the three processes "share only schema.py and
    lib/"; the content of that rule is that no process imports another
    PROCESS -- webapp/ never imports api/, the pipeline never imports webapp/.
    This is a top-level pipeline module in the same position as schema.py, and
    the webapp reaches it through the same one-level-up sys.path insert
    (webapp/config.py) that already gives it `schema` and `evals.labels`
    (webapp/schema_web.py:28,73).

    The DATABASE half lives in searchqueries.py, which the webapp does not
    import and could not usefully run: the fold, the decay sweep and the
    provider dispatch all write columns the service role has no grant on.

    It also owns the SQL for find-or-create and watcher registration, for the
    same reason relevance.py owns SQL rather than a Python matcher: one
    implementation, two callers. webapp/search.py executes these statements;
    tests/test_search_queries.py executes the same strings against a scratch
    schema, so the property "two Builders, one row" is tested against the
    statement that actually ships.
"""

import re
import unicodedata

#: Characters that survive normalisation despite not being alphanumeric.
#:
#: WHY ANY EXCEPTION AT ALL, when the task file says "strip punctuation". A
#: blanket strip collapses "c#" onto "c" and "c++" onto "c", which is a cache
#: hit between two queries that mean different things -- precisely the failure
#: that file calls "worse than a cache miss". Two characters is the smallest
#: exception that closes it, and neither can start a real word, so keeping
#: them cannot merge anything that was previously distinct.
KEPT_SYMBOLS = "+#"

#: Longest raw query accepted. Not a storage limit -- the column is TEXT --
#: but a normalised key is a UNIQUE index entry, and Postgres btree tuples cap
#: at ~2704 bytes. 200 characters is far under that and is already longer than
#: any job search anyone types.
MAX_QUERY_CHARS = 200

#: Longest raw location accepted, same argument. Shorter because a location is
#: a place name, not a sentence.
MAX_LOCATION_CHARS = 120

#: What a Builder gets when they submit no location. NOT the empty string: ""
#: would make "any location" and "the location field was never filled in"
#: the same key, and the pipeline has to be able to hand a provider something.
#: The cohort is NYC by definition (see config/pursuit-persona.json), so the
#: default is the cohort's city rather than a wildcard.
DEFAULT_LOCATION = "New York, NY"

#: How many queries one Builder may watch at once. The cap the task file asks
#: for -- "so one enthusiastic person cannot consume the pool". 20 against
#: ~280 renewable searches/day and ~30 Builders is not a real ceiling for
#: anyone using the product; it is a ceiling on a script.
MAX_QUERIES_PER_BUILDER = 20


# --------------------------------------------------------------------------
# Normalisation
# --------------------------------------------------------------------------

def normalize(raw):
    """The normalised form of one piece of query text. Deterministic, total.

    THE RULES, in order, and each one is a decision:

      1. NFKD decompose, then DROP COMBINING MARKS, then recompose. This is
         what makes "cafe" and "café" one row, and it is the only rule here
         that changes letters rather than deleting characters. It is safe in
         the direction that matters: it can only merge, and the things it
         merges are spellings of the same word.
      2. casefold(), not lower(). lower() leaves "ß" alone; casefold folds it
         to "ss", which is what a German company name needs.
      3. Every character that is neither alphanumeric nor in KEPT_SYMBOLS
         becomes a SPACE, not nothing. "front-end" must become "front end"
         and not "frontend": deleting the separator would merge two distinct
         normalisations, and the whole design prefers a miss to a wrong hit.
      4. Collapse whitespace runs, strip the ends.

    WHAT IS DELIBERATELY NOT DONE, because each would produce a cache hit
    between queries that mean different things:

      * No word sorting. "operations ai" is not "ai operations"; word order
         carries meaning in a job search and the task file says so outright.
      * No stemming or lemmatising. "ai engineer" and "ai engineers" stay
         apart. They probably do mean the same thing -- and the cost of being
         wrong is one extra provider call, where the cost of over-merging is a
         Builder shown results for a search they did not run.
      * No stopword removal. "junior data analyst" is not "data analyst";
         dropping "junior" from an ENTRY-LEVEL cohort's query would be the
         single most damaging merge available.
      * No synonym or alias table. "nyc" does not become "new york ny". An
         alias list is the "too clever" normaliser the task file warns about,
         it needs curation nobody has scheduled, and every entry in it is a
         merge that cannot be undone once rows have collapsed.
      * No deduplication of repeated words.
    """
    if raw is None:
        return ""
    text = unicodedata.normalize("NFKD", str(raw))
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = unicodedata.normalize("NFC", text).casefold()
    text = "".join(c if (c.isalnum() or c in KEPT_SYMBOLS) else " " for c in text)
    return " ".join(text.split())


def normalize_query(text, location=None):
    """(normalized_text, normalized_location) -- the UNIQUE key of a query.

    Location is normalised by the SAME function, on purpose. A second
    normaliser for places would be a second thing to keep deterministic, and
    the one property that matters here -- "New York, NY" and "new york ny"
    are one row -- is exactly what `normalize()` already gives.
    """
    return normalize(text), normalize(location or DEFAULT_LOCATION)


class InvalidQuery(ValueError):
    """A query that cannot be stored. Carries a machine-readable `code` so the
    HTTP layer can put it in API-CONTRACT-v1.md's error envelope rather than
    re-deriving it from the message."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def validate(text, location=None):
    """Return (normalized_text, normalized_location) or raise InvalidQuery.

    Length is checked on the RAW input and emptiness on the NORMALISED one,
    which is the only combination that behaves: 300 characters of punctuation
    normalises to "" and must be rejected as empty, and a 300-character real
    query must be rejected as too long before it reaches the index.
    """
    if text is not None and len(str(text)) > MAX_QUERY_CHARS:
        raise InvalidQuery("query_too_long",
                           f"query text is capped at {MAX_QUERY_CHARS} characters")
    if location is not None and len(str(location)) > MAX_LOCATION_CHARS:
        raise InvalidQuery("location_too_long",
                           f"location is capped at {MAX_LOCATION_CHARS} characters")
    normalized_text, normalized_location = normalize_query(text, location)
    if not normalized_text:
        raise InvalidQuery("empty_query",
                           "query text normalises to nothing; type some words")
    if not normalized_location:
        raise InvalidQuery("empty_location",
                           "location normalises to nothing")
    return normalized_text, normalized_location


# --------------------------------------------------------------------------
# Cadence and decay
# --------------------------------------------------------------------------

#: Don't re-run a query that succeeded this recently. 20 hours rather than 24
#: for the reason ingest/google-serpapi.py:172-178 gives for the identical
#: constant: a fixed daily cron time drifting a few minutes must never skip a
#: legitimate next-day run.
RERUN_HOURS = 20

#: A query with no watchers and no results for this long stops running. The
#: task file's number.
DECAY_DAYS = 14

#: Sources that never decay, out of schema.SEARCH_SOURCES. A seeded query is
#: the answer to "a Builder who
#: does not yet know what role they want cannot write a good search term", so
#: it has to be there BEFORE anyone watches it -- and nobody can watch a
#: suggestion that has already been retired for having no watchers. Decaying
#: them would make the seeding feature switch itself off after two weeks.
#: Nine track queries a day against ~280 renewable searches/day is a fixed
#: cost of ~3% of the pool, which is what the catalogue costs.
UNDECAYABLE_SOURCES = ("seeded", "track")

def _hours_between(later, earlier):
    """Hours between two of this pipeline's TEXT timestamps.

    Deliberately a STRING-parse rather than a database interval: these
    predicates are pure so they can be unit-tested over a table of cases, and
    a predicate that needs a connection to answer "is this due" is a predicate
    nobody sweeps.
    """
    from datetime import datetime
    fmt = "%Y-%m-%dT%H:%M:%S"
    return (datetime.strptime(later, fmt)
            - datetime.strptime(earlier, fmt)).total_seconds() / 3600.0


def is_due(now, last_run_at, active_watchers, source, retired_at=None):
    """Should this query be sent to a provider on this run?

    Retired first, and unconditionally: retirement is the whole point of
    decay and a retired query that is still due would spend the quota the
    decay rule exists to stop spending.

    A never-run query is due immediately, whatever its source. That is the
    asynchronous promise in the task file -- "a query is submitted, queued,
    run on the nightly cycle" -- and a first run that waited a cadence window
    would make a Builder's first search the slowest one they ever do.

    An UNWATCHED builder query that has already run is NOT due. Nobody is
    waiting for it; it stays in the table (so a second Builder typing the same
    words still gets the cached row) and costs nothing until someone watches
    it. Seeded and track queries are always due, because the catalogue is what
    a Builder with no search term is shown.
    """
    if retired_at:
        return False
    if not last_run_at:
        return True
    if not (active_watchers or source in UNDECAYABLE_SOURCES):
        return False
    return _hours_between(now, last_run_at) >= RERUN_HOURS


def should_retire(now, source, active_watchers, first_requested_at,
                  last_result_at=None, retired_at=None):
    """Has this query been abandoned long enough to stop spending quota on?

    BOTH conditions, as the task file states them: zero watchers AND no
    results in DECAY_DAYS. A watched query that has found nothing is not
    abandoned -- somebody is still asking -- and an unwatched query that keeps
    returning postings is feeding the shared corpus every other Builder reads.

    `first_requested_at` is the fallback clock for a query that has never
    returned anything, so "created 14 days ago, never produced a result,
    nobody watching" retires rather than living forever on a NULL.
    """
    if retired_at or source in UNDECAYABLE_SOURCES:
        return False
    if active_watchers:
        return False
    since = last_result_at or first_requested_at
    if not since:
        return False
    return _hours_between(now, since) >= DECAY_DAYS * 24


# --------------------------------------------------------------------------
# The registration SQL -- one implementation, two callers
# --------------------------------------------------------------------------

#: Find-or-create, in ONE statement, and this is the load-bearing shape.
#:
#: A SELECT-then-INSERT would race: two Builders submitting the same words in
#: the same second both find nothing and both insert, and the second one gets
#: a unique violation that reads to the caller as a failed search. `ON
#: CONFLICT DO UPDATE` on the unique key returns the EXISTING row's id to the
#: loser instead, which is exactly "two Builders, one row".
#:
#: DO UPDATE rather than DO NOTHING because DO NOTHING returns no row at all
#: on conflict, so the caller would need the second SELECT this statement
#: exists to remove. The update is a no-op assignment of the column to itself:
#: nothing a second requester supplies may overwrite what the first stored.
#: display_text in particular is FIRST-WRITER-WINS -- see the read surface's
#: docstring in webapp/search.py for why the raw spelling is not re-attributed
#: on every request.
#:
#: The service role holds INSERT and SELECT on this table and NOT update. The
#: self-assignment is what lets that be true: no grant beyond INSERT is needed
#: for ON CONFLICT DO UPDATE to return the existing id, because the row it
#: "updates" is unchanged. If that ever stops being true, this statement is
#: the thing to change, not the grant.
REGISTER_QUERY_SQL = """
    INSERT INTO search_queries
        (normalized_text, normalized_location, display_text, display_location,
         chips, source, role_track, first_requested_at)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (normalized_text, normalized_location)
    DO UPDATE SET normalized_text = search_queries.normalized_text
    RETURNING id
"""

#: Register the caller as a watcher, or un-retire their own previous watch.
#:
#: KEYED ON app_user_id, NOT ON profile, AND THIS IS THE CORRECTION THAT MAKES
#: THE FEATURE POSSIBLE. `git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_four/25-search-queries.md` writes this table as
#: `(query_id, profile, created_at)`. `profile` in this system is the COHORT --
#: thirty Builders share one, which webapp/schema_web.py:297-301 states as the
#: reason builder_job_state exists at all -- so keying on it would make thirty
#: Builders watching the same search ONE row, and "a query submitted by two
#: Builders creates one row with two watchers" unsatisfiable by construction.
#: It is the same defect that blocks tranche_five/28: job_events has no
#: app_user_id and its counts are therefore cohort-wide.
#:
#: `profile` is still stored, as the COHORT the watch belongs to, because the
#: aggregation is deliberately within-cohort (28: "not across cohorts,
#: initially" -- a Builder's activity must not be visible to people they have
#: never met).
#:
#: UPDATE-ON-CONFLICT, NOT INSERT-OR-IGNORE, and not DELETE-then-INSERT. A
#: watcher row is per-Builder state in exactly the sense builder_job_state is
#: (webapp/schema_web.py:52-57), so unwatching sets `removed_at` and
#: re-watching clears it. The alternative -- deleting the row -- would need a
#: DELETE grant on a table whose whole content is "who is looking for what",
#: which is the one table this design is built to keep unreadable and
#: unmodifiable from the outside.
REGISTER_WATCHER_SQL = """
    INSERT INTO search_query_watchers
        (query_id, app_user_id, profile, created_at)
    VALUES (%s, %s, %s, %s)
    ON CONFLICT (query_id, app_user_id)
    DO UPDATE SET removed_at = NULL
"""

#: Unwatch. An UPDATE, and idempotent: a second call on an already-removed
#: watch must not move the timestamp, or "when did they stop watching" becomes
#: a value a client can rewrite at will.
UNWATCH_SQL = """
    UPDATE search_query_watchers SET removed_at = %s
    WHERE query_id = %s AND app_user_id = %s AND removed_at IS NULL
"""

#: How many queries this Builder currently watches, for MAX_QUERIES_PER_BUILDER.
COUNT_WATCHED_SQL = """
    SELECT count(*) FROM search_query_watchers
    WHERE app_user_id = %s AND removed_at IS NULL
"""
