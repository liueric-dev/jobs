"""pipelib -- shared mechanism for the Hermes ingestion pipelines.

Two pipelines share one Postgres+PostGIS instance. Since slice C they no
longer share a directory:

    ~/apps/events        -> public.events (NYC events: Socrata, NYPL, QPL,
                                           ticketing APIs)
    ~/.hermes/scripts/jobs -> jobs.jobs   (job listings: ATS boards, WWR, HN,
                                           Google)

`jobs/` moves out in slice D; this module docstring is the thing to update
when it does.

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

    Four modules were moved out for exactly this reason -- `llm` and
    `ratelimit` to `jobs/`, `geocode` and `boroughs` to the events pipeline
    (which itself then moved to `~/apps/events` in slice C). Before
    adding a module, name its second consumer. Thin usage is not the same as
    single usage: `text` and `ids` stay because events uses a little of them
    and duplicating pure functions is the drift this package exists to
    prevent.

    `envfile` was evicted to `jobs/` in slice B and came back in slice C. The
    eviction counted current consumers; it should have counted correct ones.
    Its own docstring says the flaw it fixes belonged to *both* `run-daily.py`
    entry points -- jobs had adopted it and events had not, so the second
    consumer was missing rather than nonexistent. Slice C gave events the same
    fix, which is what makes it shared.

    Measured asymmetries that do NOT currently justify eviction but are worth
    knowing, because slice D revisits them: of 40 public functions here, only
    ~14 are called by both pipelines. `text` is 8-of-8 for jobs and 1-of-8 for
    events (`strip_html` alone). `state` splits cleanly into a jobs half
    (`try_claim`/`release_claim`/`mark_success`) and an events half
    (`get_progress`/`resume_page`/`save_progress`/`complete_progress`/
    `is_fresh`) with zero overlap. `upsert.prune_expired`, `upsert.GEOG_EXPR`
    and `timeparse.to_utc`/`day_bounds_utc` are events-only.

HOW CONSUMERS FIND THIS PACKAGE -- two mechanisms, one of them ending
    1. INSTALLED (out-of-tree consumers: `~/apps/events`, and `jobs-api`
       after slice D). `pyproject.toml` at the repo root makes this an
       editable install:

           python3 -m pip install --user -e ~/.hermes/scripts

       Then `from pipelib import dbconn` works from any directory, and the
       import resolves to *this* file -- editable means one copy on disk, not
       a synchronised second one. Out-of-tree scripts need no path
       manipulation at all.

    2. THE WALK-UP (in-tree consumers: `jobs/`, until slice D). Several jobs
       ingest scripts have hyphenated filenames (`builtin-nyc.py`,
       `google-serpapi.py`) so they are not importable as modules, and they
       sit at two depths (`jobs/x.py`, `jobs/ingest/x.py`). Each walks up
       from its own location looking for the directory containing `pipelib`:

           import os, sys
           _d = os.path.dirname(os.path.abspath(__file__))
           while _d != os.path.dirname(_d) and not os.path.isdir(os.path.join(_d, "pipelib")):
               _d = os.path.dirname(_d)
           sys.path.insert(0, _d)
           sys.path.insert(0, os.path.join(_d, "jobs"))   # <- the load-bearing line

       Note the second insert. In 22 files under `jobs/` this block supplies
       not just pipelib but `jobs/`'s own directory, which is how
       `import schema` resolves. That is why pipelib cannot simply move to
       `~/apps/pipelib`: `_d` would resolve to "/" and `import schema` would
       break in all 22, and installing pipelib would not fix it because the
       broken import is the sibling one. Slice D rewrites these; do not copy
       this block into anything new.

    Mechanism 1 is why the old claim here -- "the one piece of boilerplate
    pipelib cannot remove" -- is no longer true. It can, and for events it
    already is.

DEPENDENCY
    psycopg 3 ("pip install 'psycopg[binary]'"). Everything else is stdlib,
    matching the convention both pipelines already follow. Declared in
    `pyproject.toml`, so the editable install checks it for you.

    Caveat worth knowing: a user-site install is pinned to one Python minor
    version (currently 3.14). A Fedora bump to 3.15 drops pipelib off
    `sys.path` and every consumer fails at import. The fix is re-running the
    pip command; the reason it is written down is that the symptom -- total
    failure right after a routine `dnf upgrade` -- looks like something else.
"""

__all__ = [
    "dbconn",
    "envfile",
    "http",
    "ids",
    "state",
    "text",
    "timeparse",
    "upsert",
]

