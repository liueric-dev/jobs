"""lib -- the mechanism layer of the jobs pipeline.

Fetching, retrying, hashing, checkpointing and writing rows. It never
describes what a row is: no table DDL, nothing source-specific. That belongs
to ../schema.py, the ingest scripts and api/.

    dbconn     connections; the DATABASE_URL rule and the two footguns
    envfile    .env loading, shell-compatible (systemd is NOT -- see below)
    http       get_json / get_text / post_json with backoff
    ids        make_id, content_hash, the Google posting identity helpers
    state      watermarks, plus the claim half api/ and the ingests use
    text       strip_html, bounded_json, the posted_at parsing, heuristics
    timeparse  utc_now, utc_now_str
    upsert     upsert(), upsert_checked(), TableSpec

Used by the nightly pipeline, by everything in ingest/ and tools/, and by
the contributor API under api/ -- which is the same package, imported the
same way, with no separate install.

GUIDING PRINCIPLE -- mechanism, not schema.
    `public.jobs` and the twelve tables around it are this pipeline's domain
    and their DDL lives in ../schema.py. This package covers *how* rows are
    fetched, retried, hashed, checkpointed and written -- never *what* a row
    is. Anything source-specific (Greenhouse/Lever/Ashby paging, the HN
    thread walk, Built In's card parsing, every normalize_* function) stays
    in the script that owns it. The per-source HASH_FIELDS_* tuples live in
    ../schema.py for the same reason.

THIS CODE WAS SHARED ONCE, AND THAT HISTORY EXPLAINS ITS SHAPE
    Until 2026-07-26 these modules were a single package, `pipelib`, installed
    editable and imported by this pipeline and by a second application. They
    were vendored into each so that every application is standalone: clone it,
    install psycopg, run it. See ~/apps/REORG.md slice G.

    That history is why some modules here look half-finished -- `state` has
    watermarks and TTL claims but no resumable pager, `upsert` has no
    PostGIS helpers, `dbconn` has no DATABASE_URL default at all. Those parts
    were dropped because nothing here ever called them, or because keeping
    them was actively unsafe. Each module says so in its own docstring.

    It is also why the drift risk is worth naming. A copy that nothing checks
    is how this project previously ended up with a `strip_html` truncating at
    5,000 characters where the original used 20,000 -- silently changing
    `content_hash`, which is row identity.

    Two things in THIS repo guard against that, and neither needs any other
    checkout to exist:

      - ../tests/test_row_identity.py pins, as literals, the digests of every
        function whose output reaches a stored value. It was generated from
        the shared library immediately before the split, so it encodes what
        this database actually holds.
      - ../tests/test_lib_contract.py specifies the behaviour of the parts
        that reach no digest -- the http retry policy, the watermark and TTL
        claim SQL, the DDL-avoidance rule in dbconn -- which otherwise had no
        tests at all.

    Read both before editing anything in here.

WHAT MUST NEVER CHANGE WITHOUT A DELIBERATE REWRITE
    `ids.content_hash` and anything feeding it -- notably `text.strip_html`
    and `text.posted_at_timestamp` -- determine whether a re-seen posting
    counts as changed, across ~11,400 stored digests here. Changing what
    they return recomputes every hash. That is survivable once and
    deliberately (see `TableSpec.sticky`, added for the sliding `posted_at`
    bug) but it is never a cosmetic edit.

    `text.strip_html`'s `unescape` parameter is the standing proof: the six
    copies of that function had drifted, and unifying on the wrong one
    reported 217 of 242 weworkremotely rows as updated when nothing
    upstream had changed.

HOW SCRIPTS FIND THIS PACKAGE
    Python puts the script's own directory on sys.path[0], and the systemd
    unit sets WorkingDirectory to the repo root, so `from lib import dbconn`
    resolves with no setup and no install step. The subdirectories insert
    the repo root in one line -- ingest/*.py, tools/*.py, api/query_claims.py
    and the test modules all already did this to reach ../schema.py, and
    that same insert is what reaches lib/.

    api/app.py imports query_claims BEFORE lib, because that import is what
    puts the repo root on sys.path. Keep that ordering.

    There is nothing to pip install. api/.venv sets
    include-system-site-packages = false, which used to mean the shared
    library needed a second editable install in there and an ImportError
    under uvicorn was the only symptom of forgetting. Vendoring removed that
    failure mode entirely.

DEPENDENCY
    psycopg 3 ("pip install --user 'psycopg[binary]'"; api/requirements.txt
    already pins it for the venv). Everything else is stdlib, matching the
    convention this pipeline already follows.
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
