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
#: The service-wide daily claim cap, and since T-34 the DEFAULT one rather than
#: the only one: `contributors.daily_cap` overrides it per contributor and NULL
#: there means this number. It stays an env var because a service with no
#: contributor rows configured still needs a cap, and because raising it for
#: everybody must not require thirty UPDATEs.
MAX_CLAIMS_PER_CONTRIBUTOR_PER_DAY = int(
    os.environ.get("MAX_CLAIMS_PER_CONTRIBUTOR_PER_DAY", "50")
)
#: How long a worker should wait before claiming again -- docs/adr/0007
#: decision 3, and the whole of the control layer this service holds over the
#: machines that poll it. It rides on the claim response (see `claim`), so the
#: operator moves every contributor's cadence by changing it HERE, and nothing
#: on thirty other people's machines has to be told. That is what made 0006
#: decision 4's deferred control layer unnecessary rather than merely deferred:
#: a number carried on a reply the worker already makes needs no local
#: listener, so Safari's mixed-content rules and Chrome's Private Network
#: Access rules never enter it.
#:
#: THE WORKER FLOORS THIS, AND CANNOT BE TALKED BELOW ITS FLOOR. Setting it to
#: 10 does not make thirty machines hammer this endpoint -- each raises it to
#: its own MIN_POLL_INTERVAL_SECONDS (contributor-worker/
#: google-serpapi-worker.py:206). Raising it is honoured; lowering it past the
#: floor is not, deliberately, and this end may not assume otherwise.
POLL_INTERVAL_SECONDS = int(os.environ.get("POLL_INTERVAL_SECONDS", "3600"))
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

    The check itself is qc.verify_schema(), and it moved there in T-39 so that
    ../tools/provision-database.py could run the same list against a database
    it has just created. What is left here is the half that is genuinely this
    process's: the connection, on this service's own credential. See
    qc.verify_schema()'s docstring for why every entry in those maps is
    checked -- the reasoning did not change, only where it lives.
    """
    with db() as conn:
        qc.verify_schema(conn)


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
    """A poll, and since T-35 the worker's check-in as well.

    THE THREE REPORTED FIELDS ARE ALL OPTIONAL AND NONE OF THEM CAN REFUSE THE
    REQUEST. A worker that predates T-35 sends `{"max": N}` and keeps working,
    exactly as one that predates 0007's poll interval does -- either end may be
    deployed first, which is the property this service has held since T-31 and
    is not giving up for a status field. Nothing here carries a `max_length`
    either: an over-long version string or a traceback with a newline in it
    would then be a 422, the worker would exit 1 (google-serpapi-worker.py:407-
    412), and reporting a machine's health would be the thing that broke it.
    Both are bounded and cleaned where they are stored instead
    (qc._reported_text).

    The types ARE enforced, and that is not the same trade. A worker sending a
    string where a count belongs is broken code rather than a broken machine,
    and a 422 naming the field is the most useful thing this end can say about
    it.
    """
    max: int = Field(default=1, ge=1, le=MAX_QUERIES_PER_CLAIM)
    #: What this machine is running. Operator-facing only, never checked
    #: against anything, and never used to decide what a worker is offered --
    #: this service has no notion of a supported version and must not grow one
    #: on the strength of a string the caller composes.
    worker_version: str | None = None
    #: SerpApi searches the contributor's own account says are left in the
    #: cycle. CONTRIBUTOR-REPORTED AND NEVER AUTHORITATIVE: this service cannot
    #: see a Builder's plan, has no way to check the number, and stores it with
    #: the time it arrived so that whatever reads it later can tell how old it
    #: is. `0007` decision 4 is the consumer this is for.
    quota_remaining: int | None = None
    #: Whatever went wrong on this machine since its last poll -- the worker
    #: reports it once and then forgets it, so a repeated error is repeatedly
    #: reported and a fixed one stops being.
    last_error: str | None = None


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

    A request that is granted NOTHING writes no submission_log row,
    deliberately. There is nothing to meter: it locked no query and cost no
    contributor anything, so charging for it would make "the bank is fully fresh
    today" indistinguishable from abuse and would exhaust an honest cron's daily
    allowance on the (common) days there is no work. Polling volume is a
    request-rate concern for whatever terminates TLS, not something this cap can
    express.

    THAT SENTENCE IS ABOUT submission_log AND NOT ABOUT THE POLL (T-35). Every
    authenticated poll now moves a check-in forward in `contributor_status`,
    including the ones that grant nothing, which is what makes an idle worker
    distinguishable from a stopped one at all. The two facts do not compete: a
    heartbeat is not work, so it is not in the table that records work and not
    in the count that meters it. See the check-in below, and
    qc.record_check_in().

    THE REPLY CARRIES THE NEXT INTERVAL (POLL_INTERVAL_SECONDS, docs/adr/0007
    decision 3). It is an ASK, not an enforcement: the worker floors it and this
    end has no way to make it poll faster, so nothing above may be relaxed on
    the strength of it. It is also not the rate limit the paragraph above says
    this cap cannot express -- a cooperating worker's cadence and a hostile
    one's request rate are different problems, and only the first is answered
    here.

    AND THE REST OF THE DESIRED STATE (T-34). `paused` rides on every reply
    beside the interval; the daily cap and the reserve floor are spent HERE and
    never sent, because a number the worker could act on is a number the worker
    could disagree about. That asymmetry is the point of decision 3 rather than
    an omission: the worker holds no policy of its own beyond T-31's clamp, so
    the only settings it is told are the ones it must REPORT (a paused machine
    that looked idle is indistinguishable from a broken one) rather than the
    ones it would have to ENFORCE. Enforcement of both numbers is the
    `allowance` arithmetic below, on this side of the wire, where a contributor
    running a patched worker gets exactly the same answer.
    """
    with db() as conn:
        contributor_id = authenticate(conn, authorization)

        # THE CHECK-IN, BEFORE ANYTHING THAT CAN DECIDE AGAINST THIS POLL
        # (T-35). Every authenticated poll moves it forward -- the paused one,
        # the one granted nothing, and the one refused at the daily cap -- and
        # it is written HERE, immediately after the credential is accepted, so
        # that no branch added below this line can be one a check-in skips. That
        # ordering is the whole distinction the row is built on: last check-in
        # is not last submission, a healthy worker submits nothing on most days,
        # and `0007`'s dormancy consequence turns on being able to tell those
        # apart from a machine that has stopped calling home.
        #
        # It writes NO submission_log row and is not metered as a claim: it
        # locked nothing and cost the contributor nothing, and charging for an
        # honest idle poll is the failure the paragraph above already refuses
        # for the granted-nothing case. record_check_in() commits, for the
        # reason its own docstring gives -- the 429 below raises, and a
        # rolled-back check-in would blind this report to exactly the
        # contributors an operator is looking for.
        qc.record_check_in(conn, contributor_id,
                           worker_version=req.worker_version,
                           quota_remaining=req.quota_remaining,
                           last_error=req.last_error)

        settings = qc.contributor_settings(conn, contributor_id)

        # PAUSE IS A NORMAL REPLY, NOT AN ERROR, AND THAT IS THE WHOLE DESIGN.
        # A 4xx here would be wrong three times over: the worker exits 1 on any
        # HTTPError from this route (contributor-worker/
        # google-serpapi-worker.py:407-412), so a deliberately quiet machine
        # would report itself broken; a Builder reading their own logs could not
        # tell "the operator paused me" from "my credential died"; and T-35's
        # check-in has to be recorded for a paused contributor above all others
        # -- 0007's dormancy consequence is precisely that pausing stops
        # SPENDING and not REPORTING. T-35 built that check-in above this
        # branch rather than inside it, so the property holds by position: a
        # paused poll cannot skip a write it has already made.
        #
        # It returns BEFORE claims_today() and before the query bank is opened,
        # and that ordering is deliberate rather than an optimisation: a paused
        # contributor is granted nothing, so there is nothing to meter, and
        # charging a paused poll against a cap would make a pause spend the
        # allowance it exists to stop spending. It returns AFTER authenticate(),
        # so a revoked key is still a 401 -- pause is policy for a contributor
        # this service recognises, not a way to answer one it does not.
        if settings.paused:
            return {"poll_interval_seconds": POLL_INTERVAL_SECONDS,
                    "paused": True, "queries": []}

        used = claims_today(conn, contributor_id)

        # THE BUILDER'S RESERVE, READ AGAINST THE BALANCE THEY REPORTED (T-54).
        # `reserve_floor` is a level their SerpApi credits must not drop below,
        # so the number it is subtracted from is the balance their own machine
        # last reported -- not the daily cap, which made it arithmetically a
        # second cap. quota_headroom() answers None when there is no report worth
        # acting on (none yet, or one too old for a working machine to have left
        # standing), and claim_allowance() then falls back to the cap reading
        # rather than to zero.
        #
        # ONE CLOCK FOR THE POLL. The cutoff is derived from this request's
        # `now_dt`, and the balance it is compared against may have been written
        # seconds ago by the check-in above -- a cutoff read from a second clock
        # could judge THIS poll's own report stale.
        now_dt = datetime.now(timezone.utc)
        headroom = qc.quota_headroom(
            qc.reported_quota(conn, contributor_id),
            settings.reserve_floor,
            qc.quota_fresh_since(POLL_INTERVAL_SECONDS, now_dt),
        )

        # The operator's cap and the Builder's reserve, resolved into the one
        # number the rest of this function spends. See qc.claim_allowance() for
        # why they are two settings and not one, and why `used` belongs inside
        # the arithmetic rather than only outside it.
        allowance = qc.claim_allowance(
            settings, MAX_CLAIMS_PER_CONTRIBUTOR_PER_DAY,
            used=used, headroom=headroom)
        # >=, AND THE BOUNDARY IS THE POINT. `used == allowance` is a
        # contributor who has spent exactly what they are allowed, and it must
        # refuse: with `>` they would be handed one more, so a reserve floor of
        # 2 would keep 1. The same edge is why `remaining` below is computed
        # from `allowance` and not from MAX_CLAIMS_PER_CONTRIBUTOR_PER_DAY --
        # subtracting the floor here and then forgetting it there would let a
        # single request walk straight through the reserve it just checked.
        if used >= allowance:
            raise HTTPException(
                status_code=429,
                detail=f"daily limit reached ({used}/{allowance})",
            )

        try:
            buckets = qc.load_query_buckets()
        except (OSError, ValueError, KeyError) as e:
            raise HTTPException(status_code=500, detail=f"query bank unavailable: {e}")

        remaining = allowance - used
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
            # ON EVERY CLAIM, INCLUDING THE ONES THAT GRANT NOTHING. The
            # granted-nothing reply is the COMMON one -- the bank is fresh most
            # days -- so a cadence carried only alongside work would reach a
            # quiet contributor never, and the quiet ones are exactly the
            # machines an operator needs to be able to slow down or wave off.
            "poll_interval_seconds": POLL_INTERVAL_SECONDS,
            # ON EVERY REPLY TOO, and false rather than absent. The worker asks
            # `claimed.get("paused")` and an empty query list is the common
            # honest answer, so a key that appeared only when it was true would
            # leave "paused" and "nothing stale right now" reading identically
            # to a client that had not been updated -- which is the one
            # distinction this flag exists to carry.
            "paused": False,
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
        raise HTTPException(status_code=413, detail=TOO_LARGE_DETAIL)
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


# --------------------------------------------------------------------------
# The body ceiling on every route that takes one -- T-56
# --------------------------------------------------------------------------
#
# AT THE BOTTOM FOR THE REASON THE SECTION ABOVE GIVES, and the placement is
# what decides the shape of the refusal below. `from starlette.responses import
# JSONResponse` would be the obvious way to write it and would have to go at the
# top of this file, which moves every one of the ~45 `backend/api/app.py:NNN`
# citations listed above to save five lines. So the 413 is sent as raw ASGI
# messages instead. That is a hand-built copy of what the framework would render,
# so it is pinned as one: tests/test_body_size_limit.py renders
# HTTPException(413, TOO_LARGE_DETAIL) through the handler `app` is actually
# configured with and asserts the bytes are identical. Nothing here is read at
# import time, so the placement costs nothing at runtime.

#: The one refusal wording, shared by the middleware below and by submit()'s own
#: pre-parse check. A caller must not be able to tell which of the two refused
#: it -- they are the same policy at two depths, and a client that could
#: distinguish them could map where the ceiling is enforced.
TOO_LARGE_DETAIL = "payload too large"


def _declared_length(scope):
    """The request's own claim about its size, or None if it makes none.

    Returns the LARGEST parseable Content-Length when a request carries more
    than one. A duplicate header is malformed and a real server will usually
    reject it before this runs; if one ever reaches here, believing the smallest
    value is the reading that lets a caller under-declare, and this check exists
    to be the pessimistic one. Anything unparseable or negative is treated as
    absent rather than as zero -- the counter below is what covers those, and a
    garbled header must not be able to switch the ceiling off.
    """
    declared = []
    for name, value in scope.get("headers") or ():
        if name != b"content-length":
            continue
        try:
            length = int(value)
        except (TypeError, ValueError):
            continue
        if length >= 0:
            declared.append(length)
    return max(declared) if declared else None


class BodySizeLimit:
    """MAX_BODY_BYTES on every route, rather than on the one that hand-reads.

    WHAT WAS WRONG (T-56). `submit` reads `await request.body()` itself and
    measures it before parsing, so the cap was a property of that function
    rather than of this service. `claim`, `release` and the mint route take a
    Pydantic body parameter instead, which means Starlette reads the whole body
    into memory before any code in this file runs, and uvicorn sets no ceiling
    below it. The exposure is authenticated and predates T-35; what T-35 changed
    is that `claim` now has an inviting shape, because a worker legitimately
    posts a version, a count and an error string to it every hour.

    WHY A MIDDLEWARE AND NOT THREE MORE COPIES OF submit()'s CHECK. Reading the
    body by hand costs a route its Pydantic parsing, which is why `submit` also
    hand-rolls _validation_detail; three more of those is three more places
    defect D73 can come back. A middleware is also the only shape that covers a
    route nobody has written yet, which is the actual defect -- the ceiling was
    per-function, so every new endpoint started without one.

    WHY NOT ONLY AT THE PROXY. A body limit belongs in whatever terminates TLS
    as well, and that is where request-rate already lives (see `claim`'s
    docstring on what this service's caps cannot express). It is not a
    substitute: it is a line in a config file on a machine this repo does not
    contain, added later by someone who will not have read this. That is the
    same trade D73 made -- a property here, a rule there -- and the reasoning is
    in _validation_detail's docstring rather than repeated.

    TWO CHECKS, AND THE SECOND IS NOT REDUNDANT. A declared Content-Length over
    the cap is refused without the app being entered at all, so the body is
    never pulled off the wire by this process. A request that declares nothing
    (HTTP/1.1 chunked) or declares less than it sends is refused by counting the
    chunks as they are handed over, which is a ceiling on what is HELD rather
    than on what is announced. With only the first check, `Transfer-Encoding:
    chunked` is a one-header bypass.

    WHAT THIS DOES NOT DO, STATED RATHER THAN IMPLIED: it does not stop the
    bytes ARRIVING. The refusal is before this process buffers them, not before
    the kernel receives them, so it bounds memory and not bandwidth. Bandwidth
    is the proxy's, and that is the half of this that is a deployment decision.

    THE OVERSIZE RAISES HTTPException RATHER THAN SENDING ITS OWN RESPONSE, and
    that is deliberate rather than inconsistent with the Content-Length branch
    above it. Raising from inside `receive` is the documented path: FastAPI's
    request handler re-raises an HTTPException from the body read untouched
    ("If a middleware raises an HTTPException, it should be raised again") while
    converting anything else into a 400 "There was an error parsing the body" --
    so a custom exception class here would arrive at the client as a 400 about
    parsing. The Content-Length branch cannot use it: nothing downstream is
    running yet to catch it.
    """

    def __init__(self, app, max_bytes=None):
        self.app = app
        self._max_bytes = max_bytes

    @property
    def max_bytes(self):
        """The cap, resolved per request and not frozen at construction.

        MAX_BODY_BYTES is read from the environment at import, and a test that
        patches the module attribute must move this too -- otherwise the
        registered instance keeps a copy nothing can reach and the two ceilings
        drift. An explicit max_bytes is for constructing this class directly in
        a test, which is the only caller that passes one.
        """
        return MAX_BODY_BYTES if self._max_bytes is None else self._max_bytes

    async def __call__(self, scope, receive, send):
        # Lifespan and websocket scopes have no request body and no
        # Content-Length; passing them through untouched is what keeps this
        # middleware out of the startup path, where verify_schema() runs.
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        cap = self.max_bytes

        declared = _declared_length(scope)
        if declared is not None and declared > cap:
            body = b'{"detail":"' + TOO_LARGE_DETAIL.encode() + b'"}'
            await send({
                "type": "http.response.start",
                "status": 413,
                "headers": [(b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode())],
            })
            await send({"type": "http.response.body", "body": body})
            return

        seen = 0

        async def counting_receive():
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body") or b"")
                if seen > cap:
                    raise HTTPException(status_code=413, detail=TOO_LARGE_DETAIL)
            return message

        await self.app(scope, counting_receive, send)


# Registered here, at the bottom, for the placement reason above -- and it is
# the last statement in the module because add_middleware() must run before the
# first request builds the stack, which import time always is.
app.add_middleware(BodySizeLimit)
