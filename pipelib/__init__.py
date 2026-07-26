"""pipelib -- shared mechanism for the Hermes ingestion pipelines.

Two pipelines live under ~/.hermes/scripts/ and share one Postgres+PostGIS
instance:

    events/  -> public.events   (NYC events: Socrata, NYPL, QPL, ticketing APIs)
    jobs/    -> jobs.jobs       (job listings: ATS boards, WWR, HN, Google)

Before this package they shared *no* code. `make_id`, `content_hash`,
`upsert`, `ensure_schema`, `prune_*` and the watermark helpers were
copy-pasted 3x in events/ and 6x in jobs/, and had already drifted into
real bugs -- three different prune scopes, two DATABASE_URL defaults,
inconsistent per-record error handling, and two different (one unsafe)
lat/lon SQL binding strategies.

GUIDING PRINCIPLE -- share mechanism, not schema.
    `public.events` and `jobs.jobs` are different domains and stay separate
    tables with separate DDL owned by their own pipelines. pipelib covers
    *how* rows are fetched, retried, hashed, checkpointed and written --
    never *what* a row is. Anything source-specific (Socrata paging, the
    NYPL GraphQL query, QPL's WAF handling, every normalize_* function)
    stays in the pipeline that owns it.

MEMBERSHIP RULE -- two consumers, or it goes home.
    A module belongs here only while *both* pipelines import it. One
    consumer means it is that pipeline's code sitting behind a shared
    import path, which is strictly worse than living in the pipeline: it
    reads as infrastructure, so a local change gets reviewed as though it
    affected both.

    Five modules were moved out for exactly this reason -- `llm`,
    `ratelimit` and `envfile` to `jobs/`, `geocode` and `boroughs` to
    `events/`. Before adding a module, name its second consumer. Thin usage
    is not the same as single usage: `text` and `ids` stay because events
    uses a little of them and duplicating pure functions is the drift this
    package exists to prevent.

IMPORT BOOTSTRAP
    Several ingest scripts have hyphenated filenames (`builtin-nyc.py`,
    `google-serpapi.py`) so they are not importable as modules, and they sit
    at two different depths (`events/x.py`, `jobs/ingest/x.py`). Rather than
    hard-code a relative depth that breaks when a file moves, every script
    walks up from its own location until it finds the directory containing
    `pipelib`. Copy this block verbatim to the top of a script:

        import os, sys
        _d = os.path.dirname(os.path.abspath(__file__))
        while _d != os.path.dirname(_d) and not os.path.isdir(os.path.join(_d, "pipelib")):
            _d = os.path.dirname(_d)
        sys.path.insert(0, _d)

        from pipelib import ids, dbconn, http, upsert, state

    This is the one piece of boilerplate pipelib cannot remove, because
    finding pipelib is what it does.

DEPENDENCY
    psycopg 3 ("pip install 'psycopg[binary]'"). Everything else is stdlib,
    matching the convention both pipelines already follow.
"""

__all__ = [
    "dbconn",
    "http",
    "ids",
    "state",
    "text",
    "timeparse",
    "upsert",
]

