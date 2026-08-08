"""
Every environment variable this service reads, in one module.

WHY ONE MODULE: the README's configuration table has to stay true, and the only
way to keep it true is for there to be exactly one place a knob can be added.
A route that reaches for os.environ directly is a knob that exists in the code
and nowhere in the docs.

IMPORT ORDER: this module performs the sys.path insert that reaches ../schema.py
and ../lib/, so it must be imported BEFORE either of those anywhere in this
package. Every other module here imports `config` first for that reason -- the
same constraint api/app.py has with query_claims, and it is worth keeping
explicit rather than relying on import side-effects landing in a lucky order.

CREDENTIALS ARE NOT VALIDATED AT IMPORT TIME. GOOGLE_CLIENT_ID and its secret
default to empty and are checked by the routes that use them, so that
/v1/health, the unit tests and `manage_app_users.py list` all work on a machine
that has no OAuth client at all. Only DATABASE_URL is required, and only when
something actually connects.
"""

import os
import sys

# webapp/ sits one level below the pipeline modules it shares code with. Python
# puts THIS file's directory on sys.path, not its parent, so the parent is added
# by hand. That one insert reaches BOTH ../schema.py and ../lib/, which is why
# there is nothing to pip-install for them: this venv sets
# include-system-site-packages = false, so anything not vendored or in
# requirements.txt is missing at runtime and nowhere else.
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from lib import envfile  # noqa: E402  (../lib/ -- reached by the insert above)

#: Read ./.env if it exists. override=False, so an exported value beats the
#: file -- same precedence lib.envfile uses for the pipeline, and what makes a
#: one-off `DATABASE_URL=... uvicorn app:app` behave the way you'd expect.
envfile.load(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))


def _flag(name, default):
    """Parse a boolean env var. Anything unrecognised is the default, not False
    -- a typo in SESSION_COOKIE_SECURE must not silently disable it."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    lowered = raw.strip().lower()
    if lowered in ("1", "true", "yes", "on"):
        return True
    if lowered in ("0", "false", "no", "off"):
        return False
    return default


def _int(name, default):
    try:
        return int(os.environ.get(name, "").strip())
    except ValueError:
        return default


# -- database ---------------------------------------------------------------

#: Resolved lazily, not at import, because `manage_app_users.py init-schema`
#: needs the admin URL and the unit tests need neither. lib.dbconn.database_url()
#: raises a named error when unset; there is deliberately no default anywhere in
#: this repo, because the only one that ever existed pointed at a different
#: application's database and every table here is unqualified in `public`.
def database_url():
    from lib import dbconn
    return dbconn.database_url()


def admin_database_url():
    """DDL credential, used by manage_app_users.py init-schema and nothing else.

    Falls back to the restricted URL so a single-role setup still works: it will
    fail on CREATE with a legible "permission denied", which is the correct
    error for that case rather than something surprising.
    """
    return os.environ.get("JOBS_ADMIN_DATABASE_URL") or database_url()


# -- Google OAuth -----------------------------------------------------------

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.environ.get(
    "GOOGLE_REDIRECT_URI", "http://localhost:8421/v1/auth/callback")

#: Google's endpoints. Constants rather than a discovery-document fetch: the
#: discovery URL is one more network dependency on the login path, and these
#: three have not moved in a decade.
GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
#: Both spellings are legitimate in Google's id_tokens and which one you get is
#: not something to depend on.
GOOGLE_ISSUERS = ("accounts.google.com", "https://accounts.google.com")


# -- browser-facing ---------------------------------------------------------

#: Where the OAuth callback sends the browser once a session exists.
FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173").rstrip("/")

#: CORS allowlist. Explicit origins only -- a wildcard is incompatible with
#: credentialed requests per the CORS spec, and the browser's failure mode is to
#: silently drop the session cookie rather than say so.
ALLOWED_ORIGINS = [
    o.strip().rstrip("/")
    for o in os.environ.get("ALLOWED_ORIGINS", "http://localhost:5173").split(",")
    if o.strip()
]

SESSION_COOKIE_NAME = os.environ.get("SESSION_COOKIE_NAME", "jobs_session")
#: Defaults to True so that the insecure setting has to be typed out on purpose.
SESSION_COOKIE_SECURE = _flag("SESSION_COOKIE_SECURE", True)
SESSION_TTL_DAYS = _int("SESSION_TTL_DAYS", 30)
OAUTH_STATE_TTL_MINUTES = _int("OAUTH_STATE_TTL_MINUTES", 10)

#: Documentation only -- uvicorn takes --port. api/ holds 8420.
PORT = _int("PORT", 8421)


def oauth_configured():
    """Whether a login can even be attempted. Routes check this and return a
    named 503 rather than redirecting the user to a Google error page."""
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)


# -- the contributor mint (docs/adr/0007 decision 1) ------------------------
#
# THE ONE PLACE THIS SERVICE TALKS TO ../api/. README's "Why this is not part
# of `../api/`" used to end "The two do not talk"; they now talk over exactly
# one route, in one direction, and this is every knob that makes that happen.
# The alternative -- granting `jobs_web` INSERT on `api_keys` -- is rejected by
# docs/adr/0006's consequences, so the credential is minted by the role that
# owns the table and this service only asks.

#: Where THIS PROCESS reaches ../api/. A loopback or tailnet address: the call
#: is server-to-server and never leaves the host in a normal deployment.
CONTRIBUTOR_API_INTERNAL_URL = os.environ.get(
    "CONTRIBUTOR_API_INTERNAL_URL", "http://127.0.0.1:8420").rstrip("/")

#: What goes into the Builder's config.json as JOBS_API_BASE_URL -- the address
#: THEIR MACHINE will call, which is the public one and is emphatically not the
#: internal URL above. No default: a wrong value here produces a config.json
#: that fails on a stranger's laptop with a connection error, and 127.0.0.1 is
#: the wrong value that would look most plausible in a log.
CONTRIBUTOR_API_PUBLIC_URL = os.environ.get(
    "CONTRIBUTOR_API_PUBLIC_URL", "").rstrip("/")

#: The server-to-server secret. THE SAME ENV VAR NAME ../api/ READS
#: (query_claims.MINT_SHARED_SECRET), so the operator sets one value under one
#: name in two .env files rather than keeping two names in agreement.
JOBS_MINT_SHARED_SECRET = os.environ.get("JOBS_MINT_SHARED_SECRET", "")

#: Short on purpose. A Builder is waiting on this request, and ../api/ is a
#: loopback hop away; a long timeout here only converts "api/ is down" into a
#: page that hangs before it fails.
CONTRIBUTOR_MINT_TIMEOUT_SECONDS = _int("CONTRIBUTOR_MINT_TIMEOUT_SECONDS", 10)


def contribute_configured():
    """Whether opting in can be attempted at all.

    Same shape as oauth_configured() above and for the same reason: the unit
    tests, /v1/health and every other route must work on a machine that has no
    contributor API at all, so this is checked by the one route that needs it
    rather than at import.
    """
    return bool(JOBS_MINT_SHARED_SECRET and CONTRIBUTOR_API_PUBLIC_URL
                and CONTRIBUTOR_API_INTERNAL_URL)
