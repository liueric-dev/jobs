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
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone

import psycopg
from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field

import query_claims as qc          # also puts the repo root on sys.path
from pipelib import text

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
    conn.execute("SET search_path TO jobs, public")
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
    """
    problems = []
    with db() as conn:
        for table, privileges in qc.REQUIRED_TABLES.items():
            qualified = f"jobs.{table}"
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
            qualified = f"jobs.{sequence}"
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
    log is written on every submit anyway."""
    day_start = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00")
    row = conn.execute(
        "SELECT COUNT(*) FROM submission_log WHERE contributor_id = %s AND submitted_at >= %s",
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


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------

@app.get("/v1/health")
def health():
    return {"ok": True}


@app.post("/v1/queries/claim")
def claim(req: ClaimRequest, authorization: str = Header(default=None)):
    """Hand out the stalest unclaimed queries this contributor may work on.

    SerpApi buckets only -- the Apify source is deliberately not offered here.
    It bills per result against the operator's own account, so letting
    contributors trigger it would spend the operator's money on someone else's
    request. Contributors spend their own SerpApi quota, which is the whole
    point of the arrangement.
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
        raise HTTPException(status_code=400, detail=f"malformed body: {e}")

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
            conn.execute(
                """
                INSERT INTO submission_log (contributor_id, dataset, submitted_at,
                    fetched_count, accepted_count, rejected_count, reason)
                VALUES (%s, %s, %s, %s, 0, %s, 'too many jobs')
                """,
                (contributor_id, dataset, qc.utc_now_str(), len(payload.jobs), len(payload.jobs)),
            )
            conn.commit()
            raise HTTPException(
                status_code=400,
                detail=f"too many jobs (max {MAX_JOBS_PER_SUBMIT})",
            )

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

        new, updated, unchanged = qc.upsert(conn, records)

        # Watermark advances only now, after results are actually stored --
        # this is what makes a failed submit safely retryable (see mark_success).
        last_run = _last_success(conn, dataset)
        qc.mark_success(conn, dataset, qc.utc_now_str())
        qc.log_query_stats(conn, slug, new, len(payload.jobs), text.days_since(last_run))

        conn.execute(
            """
            INSERT INTO submission_log (contributor_id, dataset, submitted_at,
                fetched_count, accepted_count, rejected_count, reason)
            VALUES (%s, %s, %s, %s, %s, %s, NULL)
            """,
            (contributor_id, dataset, qc.utc_now_str(), len(payload.jobs), len(records), rejected),
        )
        conn.commit()

        return {
            "accepted": len(records), "rejected": rejected,
            "new": new, "updated": updated, "unchanged": unchanged,
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
        conn.execute(
            """
            INSERT INTO submission_log (contributor_id, dataset, submitted_at,
                fetched_count, accepted_count, rejected_count, reason)
            VALUES (%s, %s, %s, 0, 0, 0, %s)
            """,
            (contributor_id, dataset, qc.utc_now_str(), (req.reason or "released")[:500]),
        )
        conn.commit()
        return {"released": True}


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _mode_for_slug(slug):
    """'mode' drives the location_is_remote heuristic in normalize_job. It's
    looked up from the server's own query bank rather than taken from the
    request, so a contributor can't mislabel a query's results."""
    try:
        buckets = qc.load_query_buckets()
    except (OSError, ValueError, KeyError):
        return "unknown"
    for bucket in buckets.values():
        for q in bucket["queries"]:
            if q["slug"] == slug:
                return q["mode"]
    return "unknown"


def _last_success(conn, dataset):
    row = conn.execute(
        "SELECT last_success_at FROM job_ingest_state WHERE dataset = %s", (dataset,)
    ).fetchone()
    if not row or not row[0]:
        return None
    return row[0]
