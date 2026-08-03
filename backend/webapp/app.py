"""
The application backend: what frontend/ talks to.

WHAT THIS IS FOR: the pipeline in ../ finds and scores jobs but delivers none
of them. This service is the delivery half. A person signs in with Google, gets their profile's ranked
jobs out of the `jobs_app` view, and their interactions land in `job_events`,
which nothing has ever written and which ../score.py already reads.

WHY THIS IS NOT PART OF ../api/. That directory is the CONTRIBUTOR api: a
machine-to-machine work queue for volunteers who submit SerpApi results on
their own quota. Its whole design assumes the caller is hostile, and its
`jobs_api` Postgres role is deliberately granted NOTHING on the seven
pipeline-owned tables -- three sections of its README exist to defend that
boundary. Serving logged-in users needs SELECT across all of them, so putting
these routes there would mean relaxing the one property that README is about.
So: a second process with a second database identity, sharing ../schema.py and
../lib/ and importing nothing from api/.

RUN LOCALLY:
    python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
    cp .env.example .env && chmod 600 .env
    .venv/bin/python manage_app_users.py init-schema   # once, admin credential
    .venv/bin/uvicorn app:app --port 8421

Deployment (TLS, reverse proxy, the redirect URI in the Google console) is a
separate manual step -- see README.md. Do NOT serve this over plaintext HTTP
off localhost: the session cookie is a bearer credential, and
SESSION_COOKIE_SECURE exists to stop the browser sending it in the clear.
"""

import logging
from contextlib import asynccontextmanager

import config  # noqa: F401  (must come first -- performs the sys.path insert)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import auth
import jobs
import label
import onboarding
import schema_web
import search
from db import db

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("webapp")


@asynccontextmanager
async def lifespan(app):
    """Refuse to serve against a database this service cannot actually use.

    verify_schema checks privileges, not just table existence -- see its
    docstring. A missing GRANT is a deployment error to report at startup, not
    a 500 on a real user's first click.
    """
    with db() as conn:
        schema_web.verify_schema(conn)
    if not config.oauth_configured():
        # Not fatal: /v1/health and the admin CLI work without it, and a
        # deployment that has not been given its client id yet should say so
        # rather than fail to boot.
        log.warning("GOOGLE_CLIENT_ID/SECRET unset -- /v1/auth/login will 503")
    log.info("serving profiles from %s; origins=%s; secure_cookie=%s",
             "jobs_app", config.ALLOWED_ORIGINS, config.SESSION_COOKIE_SECURE)
    yield


app = FastAPI(title="jobs-webapp", docs_url=None, redoc_url=None, lifespan=lifespan)

# Explicit origins, never "*". A wildcard is incompatible with credentialed
# requests per the CORS spec, and the browser's failure mode is to drop the
# session cookie silently rather than tell anyone why. allow_methods and
# allow_headers are the actual sets used, for the same reason: a "*" here is a
# thing nobody revisits.
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

app.include_router(auth.router)
app.include_router(jobs.router)
# Searches (task 25). AFTER jobs.router and before the exception handler below,
# because search.py raises jobs.ContractError -- the same type, so the same
# handler produces the same error envelope for both routers. A second error
# shape for the search screen would be a client-visible inconsistency in the
# one thing API-CONTRACT-v1.md specifies exactly.
app.include_router(search.router)
# API-CONTRACT-v1.md specifies one error shape -- {"error": {code, message,
# request_id}} -- and FastAPI's default handler produces {"detail": ...}.
# Registered for jobs.ContractError alone rather than for HTTPException, so
# auth.py's and label.py's existing 4xx bodies keep the shape their own tests
# and the browser redirect flow already depend on.
app.add_exception_handler(jobs.ContractError, jobs.contract_error_handler)
# Profile creation (tranche_five/26). Registered AFTER the handler above and
# deliberately raising jobs.ContractError rather than a type of its own, so a
# 400 from onboarding comes back in the same envelope as a 400 from /v1/events
# -- one error shape per API, which is what API-CONTRACT-v1.md specifies.
app.include_router(onboarding.router)
# The golden-set labelling surface. Server-rendered HTML rather than JSON,
# because the people it exists for are ~10 Builder volunteers -- see label.py.
# The premise here USED to be that frontend/ held one .gitkeep. It no longer
# does (task 32, 2026-08-02), and the decision is unchanged: that client has no
# labelling screen and is not in scope for one. A <form> and a 303 needs no
# client at all, which is still the right trade for ten volunteers.
app.include_router(label.router)


@app.get("/v1/health")
def health():
    """Liveness only, and deliberately no database call: this answers "is the
    process up". Whether the database is usable is the startup check's
    question, and it already refuses to serve without an answer."""
    return {"ok": True}
