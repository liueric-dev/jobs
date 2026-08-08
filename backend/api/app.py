"""
Crowdsourced job-query API.

WHAT THIS IS FOR: volunteers run a small worker script on their own machines,
each using their OWN SerpApi account, pulling search queries from this
server's priority queue and submitting the raw results back. That multiplies
effective search coverage without anyone but the operator holding database
credentials.

THE CORE SECURITY PREMISE: every caller here is untrusted. Contributors are
other people, running code on machines the operator does not control, and a
contributor's API key may leak or be used by someone hostile. Therefore:

  1. Postgres is NEVER reachable by contributors. This process is the only
     thing that talks to it, and it should be the only thing exposed publicly
     (behind a reverse proxy terminating TLS -- see README).
  2. Every stored field is DERIVED SERVER-SIDE from the raw posting payload
     via query_claims.normalize_job(). Client-supplied ids/hashes are ignored
     entirely -- see the security note in that function for why this matters
     (it's what prevents a hostile client from clobbering rows belonging to
     other sources).
  3. A contributor may only submit against a claim THEY currently hold and
     that hasn't expired -- otherwise two contributors could race to write
     results for the same query, or one could spray results at queries it
     never fetched.
  4. Payload size, per-request query count, and per-contributor daily volume
     are all capped, so a buggy or malicious worker cannot flood the table.

RUN LOCALLY:
    pip install -r requirements.txt
    uvicorn app:app --port 8420
Deployment (domain, TLS, reverse proxy, firewall) is a separate manual step --
see README.md. Do NOT bind this to 0.0.0.0 on an untrusted network without a
TLS-terminating proxy in front: API keys are bearer tokens, so plaintext HTTP
would expose them.
"""

import os
import hashlib
import secrets
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone

import psycopg
from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field

import query_claims as qc          # also puts the repo root on sys.path
from lib import text

MAX_JOBS_PER_SUBMIT = int(os.environ.get("MAX_JOBS_PER_SUBMIT", "50"))
MAX_QUERIES_PER_CLAIM = int(os.environ.get("MAX_QUERIES_PER_CLAIM", "5"))
MAX_CLAIMS_PER_CONTRIBUTOR_PER_DAY = int(
    os.environ.get("MAX_CLAIMS_PER_CONTRIBUTOR_PER_DAY", "50")
)
# Hard ceiling on request body size. SerpApi returns ~10 postings per query and
# each is a few KB, so a legitimate submit is well under 1MB; anything larger
# is a bug or an attack, and rejecting it before parsing avoids spending memory
# on a hostile payload.
MAX_BODY_BYTES = int(os.environ.get("MAX_BODY_BYTES", str(2 * 1024 * 1024)))

@contextmanager
def db():
    """A connection that commits on success AND closes afterwards.

    psycopg's own `with conn:` commits or rolls back but deliberately does NOT
    close -- it is designed for reusing a long-lived connection. This service
    opens one per request, so every request was leaking a socket until GC got
    round to it. Nesting `with conn:` inside a finally-close keeps psycopg's
    transaction semantics exactly (several callers below rely on the implicit
    commit) and adds the close. contextlib.closing alone would NOT do: it
    closes without committing.
    """
    conn = psycopg.connect(qc.DATABASE_URL)
    conn.execute("SET search_path TO public")
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def verify_schema():
    """Fail fast if the database has not been initialised.

    This process deliberately holds no DDL rights: it connects as a role
    granted SELECT/INSERT/UPDATE on exactly the six tables in
    qc.REQUIRED_TABLES, and nothing else. Creating the schema here -- which is
    what this used to do -- would mean an internet-facing service permanently
    holding CREATE on the same schema the ingest pipeline owns.

    So a missing table is a deployment error to report, not damage to silently
    repair. Refusing to start is the point: a half-initialised database would
    otherwise surface later as a confusing 500 on a contributor's submit.

    Privileges are checked, not just existence. A table can exist and still be
    unusable if a GRANT was missed, and that failure mode is real -- INSERT
    without SELECT on google_jobs_query_stats looks fine until the first
    ON CONFLICT runs. has_table_privilege() turns that into a startup error
    naming the missing grant.

    The sequence is checked too. submission_log.id is BIGSERIAL, so an INSERT
    needs USAGE on submission_log_id_seq as well as INSERT on the table. That
    grant was in README's privilege table and in nothing that ran, which made
    it the one documented requirement a startup check could not catch -- it
    would have surfaced as a 500 on a contributor's first submit instead.

    And the columns, for the third instance of the same argument. A table can
    exist, be granted, and still be missing a column every INSERT names --
    init-schema is a separate admin command, so shipping this code ahead of it
    is one `git pull` away. qc.REQUIRED_COLUMNS lists only columns this service
    WRITES; reads that lose a column fail visibly at the query.
    """
    problems = []
    with db() as conn:
        for table, privileges in qc.REQUIRED_TABLES.items():
            qualified = f"public.{table}"
            if conn.execute("SELECT to_regclass(%s)", (qualified,)).fetchone()[0] is None:
                problems.append(f"{qualified}: missing")
                continue
            lacking = [
                p for p in privileges
                if not conn.execute(
                    "SELECT has_table_privilege(current_user, %s, %s)", (qualified, p)
                ).fetchone()[0]
            ]
            if lacking:
                problems.append(f"{qualified}: no {', '.join(lacking)}")

        for sequence, privileges in qc.REQUIRED_SEQUENCES.items():
            qualified = f"public.{sequence}"
            if conn.execute("SELECT to_regclass(%s)", (qualified,)).fetchone()[0] is None:
                problems.append(f"{qualified}: missing")
                continue
            lacking = [
                p for p in privileges
                if not conn.execute(
                    "SELECT has_sequence_privilege(current_user, %s, %s)", (qualified, p)
                ).fetchone()[0]
            ]
            if lacking:
                problems.append(f"{qualified}: no {', '.join(lacking)}")

        for table, columns in qc.REQUIRED_COLUMNS.items():
            qualified = f"public.{table}"
            if conn.execute("SELECT to_regclass(%s)", (qualified,)).fetchone()[0] is None:
                continue        # already reported as missing above
            present = {r[0] for r in conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = %s", (table,)
            ).fetchall()}
            absent = [c for c in columns if c not in present]
            if absent:
                problems.append(
                    f"{qualified}: missing column(s) {', '.join(absent)}")
    if problems:
        raise RuntimeError(
            "database is not ready for this service -- "
            + "; ".join(problems)
            + ". Run `python3 manage_users.py init-schema` with an admin "
              "credential (JOBS_ADMIN_DATABASE_URL), and check the GRANTs in "
              "README 'Deployment'."
        )


@asynccontextmanager
async def lifespan(app):
    verify_schema()
    yield


app = FastAPI(title="jobs-api", docs_url=None, redoc_url=None, lifespan=lifespan)


# --------------------------------------------------------------------------
# Auth
# --------------------------------------------------------------------------

def authenticate(conn, authorization):
    """Resolve a bearer token to a contributor id.

    The raw key is never stored -- only sha256(key) -- so a database leak does
    not hand out working credentials. Lookup is by hash, and a revoked key is
    rejected even though its row is kept (deliberate: the audit trail in
    submission_log references contributors, and keeping revoked rows means a
    revoked key can never be silently re-minted into validity).
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization[len("Bearer "):].strip()
    if not token:
        raise HTTPException(status_code=401, detail="missing bearer token")
    key_hash = hashlib.sha256(token.encode()).hexdigest()
    row = conn.execute(
        "SELECT contributor_id, revoked_at FROM api_keys WHERE key_hash = %s", (key_hash,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="invalid api key")
    contributor_id, revoked_at = row
    if revoked_at:
        raise HTTPException(status_code=401, detail="api key revoked")
    return contributor_id


def claims_today(conn, contributor_id):
    """Daily volume check, counted from the audit log rather than tracked in
    a counter -- one less piece of mutable state to get out of sync, and the
    log is written on every claim anyway.

    COUNTS CLAIM ROWS, NOT ALL ROWS (defect D41). It used to count every
    submission_log row for the contributor, and `claim` wrote none -- so the
    only endpoint that locks a query was the one endpoint the cap could not
    see, and a worker that claimed and never submitted was unmetered while
    holding rows out of the pool for CLAIM_TTL_MINUTES apiece. `claim` now
    writes one row per query it hands out (see the endpoint), and this counts
    exactly those.

    Filtering on the action is the other half of the fix and not decoration: if
    this still counted every row, an honest submit and an honest release would
    each burn a claim from a cap whose name is about CLAIMS, so doing the work
    would reduce how much work you were allowed. The
    callers below already read this number as a count of QUERIES -- `remaining
    = MAX - used` is passed straight to max_queries -- which is what it now is.
    """
    day_start = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00")
    row = conn.execute(
        "SELECT COUNT(*) FROM submission_log WHERE contributor_id = %s "
        "AND submitted_at >= %s AND action = 'claim'",
        (contributor_id, day_start),
    ).fetchone()
    return row[0] if row else 0


# --------------------------------------------------------------------------
# Models
# --------------------------------------------------------------------------

class ClaimRequest(BaseModel):
    max: int = Field(default=1, ge=1, le=MAX_QUERIES_PER_CLAIM)


class SubmitRequest(BaseModel):
    # Raw SerpApi job objects, exactly as returned. Everything stored is
    # recomputed from these server-side; no derived fields are accepted.
    jobs: list[dict] = Field(default_factory=list)


class ReleaseRequest(BaseModel):
    reason: str | None = None


class MintRequest(BaseModel):
    #: Whatever the calling service calls this contributor. It lands in
    #: `contributors.name`, is operator-facing only, and is never checked
    #: against anything -- this service has no user directory and must not
    #: grow one.
    name: str = Field(min_length=1, max_length=200)
    label: str | None = Field(default=None, max_length=200)
    #: Present on a RE-KEY. An existing contributor gets its live keys revoked
    #: and one new key issued; absent, a new contributor row is created. The
    #: caller owns this mapping -- see the route.
    contributor_id: str | None = Field(default=None, max_length=64)


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------

@app.get("/v1/health")
def health():
    return {"ok": True}


def authenticate_service(authorization):
    """The mint route's auth, and deliberately NOT authenticate() above.

    Two different kinds of caller, so two different credentials. A contributor
    bearer token identifies someone whose machine the operator does not
    control; this one identifies another of the operator's own processes. If
    they shared a mechanism, any contributor key would mint more keys.

    UNSET MEANS OFF, NOT OPEN. With no JOBS_MINT_SHARED_SECRET configured the
    route 503s: a credential-issuing endpoint whose auth a missing env var
    turns off is the failure this check is shaped around.
    """
    if not qc.MINT_SHARED_SECRET:
        raise HTTPException(status_code=503, detail="minting is not configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization[len("Bearer "):].strip()
    # compare_digest, not ==. The contributor path can afford a plain compare
    # because it compares hashes of a 256-bit secret; this compares the secret
    # itself, so the timing of a mismatch is worth not leaking.
    if not secrets.compare_digest(token, qc.MINT_SHARED_SECRET):
        raise HTTPException(status_code=401, detail="invalid service credential")


@app.post("/v1/internal/contributors", status_code=201)
def mint(req: MintRequest, authorization: str = Header(default=None)):
    """Mint a contributor credential on behalf of another operator process.

    WHY THIS ROUTE EXISTS, AND WHY IT IS HERE RATHER THAN IN ../webapp/.
    `api_keys` is this service's table and `jobs_api` is the only role granted
    INSERT on it. docs/adr/0006's consequences reject the alternative -- DEC-84
    option 1, granting `jobs_web` INSERT on this service's tables -- "outright,
    same blast-radius argument". 0007 decision 1 then made the mint an
    interactive act a Builder triggers, and the Builder's session lives in
    ../webapp/. So: webapp authenticates the person, this service issues the
    credential, and the two talk over exactly this one route, in one direction,
    on a shared secret. 0006's consequences list named that secret as an
    unscoped follow-up; this is it.

    THE RAW KEY IS IN THIS RESPONSE AND NOWHERE ELSE, EVER. Only sha256 is
    stored, there is no read-back route, and `manage_users.py list` prints a
    hash prefix. A caller that loses it re-mints, which revokes the lost one.

    NOT INTERNET-FACING. "internal" in the path is a statement of intent, not a
    control: README's deployment section is where the reverse proxy is told to
    refuse /v1/internal/ from outside. The shared secret is the control.
    """
    authenticate_service(authorization)
    with db() as conn:
        if req.contributor_id is not None:
            known = conn.execute(
                "SELECT 1 FROM contributors WHERE id = %s", (req.contributor_id,)
            ).fetchone()
            if known is None:
                # The caller believes it owns a contributor this service has
                # never heard of -- a restored webapp database against a fresh
                # api one, most likely. Refuse rather than silently creating
                # it: a re-key that quietly becomes a first mint would leave
                # the caller's stored id pointing at nothing.
                raise HTTPException(status_code=409,
                                    detail="unknown contributor_id")
        contributor_id, raw_key, key_hash, created_at = qc.mint_credential(
            conn, req.name, label=req.label, contributor_id=req.contributor_id)
    return {
        "contributor_id": contributor_id,
        "api_key": raw_key,
        "key_hash": key_hash,
        "created_at": created_at,
    }


@app.post("/v1/queries/claim")
def claim(req: ClaimRequest, authorization: str = Header(default=None)):
    """Hand out the stalest unclaimed queries this contributor may work on.

    SerpApi buckets only -- the Apify source is deliberately not offered here.
    It bills per result against the operator's own account, so letting
    contributors trigger it would spend the operator's money on someone else's
    request. Contributors spend their own SerpApi quota, which is the whole
    point of the arrangement.

    EVERY GRANTED QUERY IS METERED (defect D41). One submission_log row per
    query handed out, written before the response is built, because a claim is
    the thing that costs: it takes a row out of the pool for CLAIM_TTL_MINUTES
    whether or not anything is ever submitted against it. Until this was here,
    claims_today() counted a table `claim` never wrote, so a pure claim-loop
    could hold the whole query bank locked and starve the operator's own
    nightly pipeline -- README's own "known gaps" section said so, and nothing
    checked it.

    A request that is granted NOTHING writes nothing, deliberately. There is no
    row to meter: it locked no query and cost no contributor anything, so
    charging for it would make "the bank is fully fresh today" indistinguishable
    from abuse and would exhaust an honest cron's daily allowance on the
    (common) days there is no work. Polling volume is a request-rate concern for
    whatever terminates TLS, not something this cap can express.
    """
    with db() as conn:
        contributor_id = authenticate(conn, authorization)

        used = claims_today(conn, contributor_id)
        if used >= MAX_CLAIMS_PER_CONTRIBUTOR_PER_DAY:
            raise HTTPException(
                status_code=429,
                detail=f"daily limit reached ({used}/{MAX_CLAIMS_PER_CONTRIBUTOR_PER_DAY})",
            )

        try:
            buckets = qc.load_query_buckets()
        except (OSError, ValueError, KeyError) as e:
            raise HTTPException(status_code=500, detail=f"query bank unavailable: {e}")

        remaining = MAX_CLAIMS_PER_CONTRIBUTOR_PER_DAY - used
        picked = qc.pick_stale_queries_by_bucket(
            conn, buckets, claimed_by=contributor_id,
            max_queries=min(req.max, remaining),
        )

        for q, _ in picked:
            qc.log_submission(conn, "claim", contributor_id,
                              f"google_jobs:query:{q['slug']}")
        if picked:
            conn.commit()

        return {
            "queries": [
                {
                    "dataset": f"google_jobs:query:{q['slug']}",
                    "slug": q["slug"],
                    "query": q["query"],
                    "location": q["location"],
                    "mode": q["mode"],
                    # The contributor's worker passes this straight through to
                    # SerpApi as chips=date_posted:<chip>. Computed here, not
                    # client-side, because it depends on the server-side
                    # watermark the client can't see.
                    "date_chip": qc.choose_date_chip(last_run),
                }
                for q, last_run in picked
            ]
        }


@app.post("/v1/queries/{dataset:path}/submit")
async def submit(
    dataset: str,
    request: Request,
    authorization: str = Header(default=None),
):
    """Accept raw results for a query this contributor currently holds.

    Body is read manually (rather than via a Pydantic body param) so the size
    cap is enforced BEFORE parsing -- a 500MB JSON array should be rejected on
    sight, not after being deserialized into memory.
    """
    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="payload too large")
    try:
        payload = SubmitRequest.model_validate_json(raw)
    except Exception as e:
        raise HTTPException(status_code=400, detail=_validation_detail(e))

    with db() as conn:
        contributor_id = authenticate(conn, authorization)
        now_dt = datetime.now(timezone.utc)

        if not qc.holds_claim(conn, dataset, contributor_id, now_dt):
            # 409, not 403: the request is well-formed and the caller is
            # authenticated -- the claim simply isn't theirs (or expired while
            # they were fetching, and may now belong to someone else).
            raise HTTPException(
                status_code=409,
                detail="you do not hold a live claim on this dataset",
            )

        if len(payload.jobs) > MAX_JOBS_PER_SUBMIT:
            qc.log_submission(conn, "submit", contributor_id, dataset,
                              fetched_count=len(payload.jobs),
                              rejected_count=len(payload.jobs),
                              reason="too many jobs")
            conn.commit()
            raise HTTPException(
                status_code=400,
                detail=f"too many jobs (max {MAX_JOBS_PER_SUBMIT})",
            )

        # AN EMPTY SUBMISSION DOES NOT ADVANCE THE WATERMARK (defect D08).
        #
        # mark_success used to run unconditionally, so `{"jobs": []}` marked the
        # query covered for GOOGLE_JOBS_MIN_HOURS_BETWEEN_RUNS with zero rows
        # collected -- and every posting published in that window was skipped by
        # every path, permanently, with the run reporting success.
        #
        # WHY THIS IS NOT THE PIPELINE'S RULE. ingest/google-serpapi.py:335-351
        # DOES advance the watermark on zero results, correctly: it made the
        # SerpApi call itself, so it knows the fetch succeeded and the window is
        # genuinely empty. This endpoint knows nothing of the sort. An empty
        # array is what an exhausted key, a blocked worker, a wrong chip and a
        # genuinely quiet query all look like from here -- "silence is this
        # system's failure mode", and the caller is untrusted besides, so a
        # `fetch_ok: true` flag in the payload would just move the assertion to
        # the side that has the bug.
        #
        # So the claim is RELEASED rather than held: same shape as /release,
        # which exists for exactly "the fetch produced nothing usable, don't
        # advance the watermark". The query returns to the pool immediately for
        # a contributor with a different SerpApi account instead of being locked
        # for CLAIM_TTL_MINUTES.
        #
        # THE COST, STATED: a query that is honestly empty gets re-handed-out
        # and re-fetched. That is a credit, bounded by the per-contributor daily
        # cap (which D41's fix makes real) and by the per-bucket budgets. The
        # other direction is a posting nobody ever sees and no counter records.
        if not payload.jobs:
            qc.release_claim(conn, dataset)
            qc.log_submission(conn, "submit", contributor_id, dataset,
                              reason="empty submission -- watermark not advanced")
            conn.commit()
            return {
                "accepted": 0, "rejected": 0, "dropped": 0,
                "new": 0, "updated": 0, "unchanged": 0,
                "watermark_advanced": False,
            }

        slug = dataset.replace("google_jobs:query:", "")
        mode = _mode_for_slug(slug)

        # Everything stored is derived here, from the raw payload only.
        records, rejected = [], 0
        for job in payload.jobs:
            if not isinstance(job, dict):
                rejected += 1
                continue
            try:
                records.append(qc.normalize_job(job, mode))
            except (AttributeError, TypeError, ValueError):
                rejected += 1

        result = qc.upsert(conn, records)
        new, updated, unchanged = result.new, result.updated, result.unchanged
        #: Records that normalized cleanly and then failed to WRITE. Distinct
        #: from `rejected`, which counts payload entries this endpoint refused
        #: before ever reaching the database. Both go in the response and in
        #: submission_log, because a contributor whose rows silently vanished
        #: has no other way to find out.
        dropped = len(result.errors)

        # Watermark advances only now, after results are actually stored --
        # this is what makes a failed submit safely retryable (see mark_success).
        last_run = _last_success(conn, dataset)
        qc.mark_success(conn, dataset, qc.utc_now_str())
        qc.log_query_stats(conn, slug, new, len(payload.jobs), text.days_since(last_run))

        qc.log_submission(
            conn, "submit", contributor_id, dataset,
            fetched_count=len(payload.jobs),
            accepted_count=len(records) - dropped,
            rejected_count=rejected,
            reason=f"{dropped} record(s) failed to write" if dropped else None)
        conn.commit()

        return {
            "accepted": len(records) - dropped, "rejected": rejected,
            "dropped": dropped,
            "new": new, "updated": updated, "unchanged": unchanged,
            "watermark_advanced": True,
        }


@app.post("/v1/queries/{dataset:path}/release")
def release(dataset: str, req: ReleaseRequest, authorization: str = Header(default=None)):
    """Give a claim back after a failed fetch, without advancing the
    watermark -- so the next contributor to pick this query up gets a
    date_chip covering the window this attempt missed."""
    with db() as conn:
        contributor_id = authenticate(conn, authorization)
        now_dt = datetime.now(timezone.utc)
        if not qc.holds_claim(conn, dataset, contributor_id, now_dt):
            raise HTTPException(
                status_code=409, detail="you do not hold a live claim on this dataset"
            )
        qc.release_claim(conn, dataset)
        qc.log_submission(conn, "release", contributor_id, dataset,
                          reason=(req.reason or "released")[:500])
        conn.commit()
        return {"released": True}


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _mode_for_slug(slug):
    """'mode' drives the location_is_remote heuristic in normalize_job. It's
    looked up from the server's own query bank rather than taken from the
    request, so a contributor can't mislabel a query's results.

    RAISES RATHER THAN RETURNING A SENTINEL (defect D09). This used to swallow
    OSError/ValueError/KeyError and return "unknown", which normalize_job reads
    as `mode != "remote"` (google_jobs.py:99) -- so a config file that was
    briefly unreadable at submit time did not fail the request, it stored a
    batch of remote postings marked non-remote, and the rows are then
    indistinguishable from correct ones forever. A config read failure is the
    server's fault and the server's to report: refusing the submission leaves
    the claim held, the watermark unadvanced and the contributor's SerpApi
    credit re-spendable on a retry, which is recoverable. A wrong stored fact
    is not.

    500 and the same "query bank unavailable" wording as `claim`'s handler
    above, on purpose: one failure, one status, whichever endpoint meets it.

    A slug that is simply ABSENT from a readable bank is a different thing and
    keeps a different answer -- 409, because `claim` only ever issues slugs from
    this bank, so the only way to reach here is a dataset that was withdrawn
    between claim and submit (or a hand-crafted one). That is a claim that is no
    longer live, which is what 409 already means on this endpoint.
    """
    try:
        buckets = qc.load_query_buckets()
    except (OSError, ValueError, KeyError) as e:
        raise HTTPException(status_code=500, detail=f"query bank unavailable: {e}")
    for bucket in buckets.values():
        for q in bucket["queries"]:
            if q["slug"] == slug:
                return q["mode"]
    raise HTTPException(
        status_code=409,
        detail=f"{slug!r} is not in the server's query bank",
    )


def _last_success(conn, dataset):
    row = conn.execute(
        "SELECT last_success_at FROM job_ingest_state WHERE dataset = %s", (dataset,)
    ).fetchone()
    if not row or not row[0]:
        return None
    return row[0]


# --------------------------------------------------------------------------
# The 400 on a malformed body -- defect D73
# --------------------------------------------------------------------------
#
# WHY THIS IS AT THE BOTTOM AND NOT WITH THE OTHER MODULE CONSTANTS ABOVE. Both
# names below belong beside MAX_BODY_BYTES on every other consideration, and
# they are here for one: ~45 citations of the form `backend/api/app.py:NNN`
# live in `git show refactor-freeze-2026-08-02:docs/ingest/contributor-api.md`,
# `git show refactor-freeze-2026-08-02:docs/RUNBOOK.md` and three task files,
# and inserting anything above `submit()` invalidates all of them at once. That
# is not hypothetical -- task 24's own Definition of done records re-citing
# roughly thirty of them after the D01 fix shifted this file by eight lines.
# Neither name is read at import time (both are resolved when
# _validation_detail runs), so the placement costs nothing at runtime and saves
# a file of stale line numbers.

#: How many validation errors are named before the summary is truncated. A
#: malformed batch of fifty can produce fifty, and a response body that grows
#: with the request is its own small amplification.
MAX_REPORTED_ERRORS = 5

#: The longest error-location or error-type token that will be printed. Bounded
#: for the same reason as above, and because an unbounded "safe" string is only
#: safe until someone finds a long one.
MAX_TOKEN_LENGTH = 40


def _safe_token(value):
    """Whether `value` may appear verbatim in a response body.

    str.isidentifier() rather than a regex, and not only to avoid an import:
    the field names of this module's models and pydantic's own error types
    ('list_type', 'json_invalid') are exactly Python identifiers, so the
    built-in predicate IS the whitelist rather than an approximation of it.
    ASCII and a length bound on top, because isidentifier() accepts unicode and
    accepts any length.
    """
    text_value = str(value)
    return (len(text_value) <= MAX_TOKEN_LENGTH
            and text_value.isascii()
            and text_value.isidentifier())


def _validation_detail(exc):
    """A 400 detail that describes the failure without quoting the request.

    DEFECT D73. This used to be `detail=f"malformed body: {e}"` in submit(). A
    pydantic ValidationError's string form embeds `input_value=`, so the
    offending input was echoed back to the sender -- and for the `json_invalid`
    case, which is every syntactically broken body, `input_value` is the WHOLE
    REQUEST BODY, not one field of it. A submit body is a SerpApi response a
    contributor fetched with their own key, so whatever a worker sent came back
    out, up to MAX_BODY_BYTES of it.

    It leaks nothing to the sender, who already has the bytes. It becomes an
    exposure the moment anything in front of this service logs response bodies
    -- a reverse proxy, an error tracker, a tunnel's access log -- and that is a
    deployment decision made later by someone who will not be reading this file.
    So the fix is to make the response independent of the input rather than to
    write down that nobody may log it.
    `git show refactor-freeze-2026-08-02:docs/RUNBOOK.md` had done exactly
    that, which is a rule, not a property.

    WHY A WHITELIST AND NOT A REDACTION. Stripping `input` out of the dicts
    exc.errors() returns would work today and would rest on knowing which keys
    of a third-party library's error objects can carry caller bytes -- `input`,
    `ctx`, `msg` and `url` all vary by error type and across pydantic releases.
    This builds the detail from two fields instead and passes even those through
    _safe_token, so "no byte of the request body reaches the response" holds by
    construction rather than by having read pydantic's formatter. It is the same
    argument that makes this service recompute every stored field server-side
    instead of validating what a contributor sends.

    WHAT IS DELIBERATELY KEPT: which field failed and how, list indices
    included. An index is a position the server counted, not something the
    caller supplied, and it is what makes "the third posting in your batch"
    answerable. A redaction that said nothing would be its own defect -- a
    contributor whose worker is broken has no other channel.

    Anything unrecognised degrades to the bare string rather than raising. The
    `except Exception` this serves is deliberately broad, because
    model_validate_json can fail before pydantic builds a ValidationError at
    all, and a formatter that raised inside an exception handler would turn a
    400 into a 500.
    """
    errors = getattr(exc, "errors", None)
    if not callable(errors):
        return "malformed body"
    try:
        found = list(exc.errors())
    except Exception:
        return "malformed body"
    if not found:
        return "malformed body"

    parts = []
    for err in found[:MAX_REPORTED_ERRORS]:
        loc = ".".join(
            str(part) if isinstance(part, int)
            else (str(part) if _safe_token(part) else "?")
            for part in err.get("loc") or ()) or "body"
        kind = err.get("type")
        parts.append(f"{loc}: {kind if _safe_token(kind) else 'invalid'}")
    if len(found) > MAX_REPORTED_ERRORS:
        parts.append(f"and {len(found) - MAX_REPORTED_ERRORS} more")
    return "malformed body (" + "; ".join(parts) + ")"
