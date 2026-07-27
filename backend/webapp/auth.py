"""
Google SSO, and the sessions it mints. The only way into this application.

THE DIVISION OF LABOUR: Google authenticates, the app_users allowlist
authorises. A valid Google login for an address with no row is refused with 403
and creates nothing. See manage_app_users.py for why that is deliberate.

THE FLOW is OAuth 2.0 Authorization Code with PKCE, driven entirely
server-side. The browser never receives a token -- only an opaque cookie whose
sha256 is what the database stores -- which means no token is reachable from
JavaScript, revocation is one UPDATE, and the frontend needs no Google SDK.
That last part is why this shape was chosen while frontend/ is still empty: it
does not commit the other half of the repo to a framework.

WHY THERE IS NO JWT LIBRARY. The id_token is consumed ONLY from the direct,
TLS-authenticated response to our own POST to Google's token endpoint -- never
from a request body, a header or a query parameter. That is precisely the case
Google's documentation exempts from signature verification: the channel already
authenticates the issuer, so checking aud/iss/exp/nonce on the decoded payload
is sufficient. See _claims_from_id_token() for the guardrail. THIS STOPS BEING
TRUE the moment anything accepts an id_token over HTTP, which is what the
frontend-GIS variant of this flow does; that design needs full JWKS signature
verification and this decode must not be reused for it.
"""

import base64
import hashlib
import json
import logging
import secrets
import time
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import config  # noqa: F401  (must come first -- performs the sys.path insert)

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

import schema_web
from db import db
from lib.timeparse import utc_now_str

log = logging.getLogger("webapp.auth")

router = APIRouter()

#: Tolerance when checking `exp`. Small on purpose: an id_token is used within
#: seconds of being issued, so this covers clock skew between us and Google and
#: nothing else.
CLOCK_SKEW_SECONDS = 60


# --------------------------------------------------------------------------
# The authenticated caller
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class User:
    """What every authenticated route gets. `profile` is the tenancy key, and
    it comes from here -- from the session -- never from a request parameter."""

    id: str
    email: str
    display_name: str
    profile: str
    is_admin: bool


def _hash(token):
    """What the database stores. The cookie value itself is never written
    anywhere, so a database dump yields no working session."""
    return hashlib.sha256(token.encode()).hexdigest()


def require_user(request: Request) -> User:
    """FastAPI dependency: cookie -> session -> user, or 401.

    One query joining app_sessions to app_users, so a disabled account is
    refused on its NEXT request rather than at its next login -- `active` is
    re-read every time on purpose.

    SLIDING EXPIRY, written at most once per half-TTL. Pushing expires_at
    forward on every request would turn every read into a write and make
    last_seen_at a hot row for no benefit; refreshing only past the halfway
    point keeps sessions alive for active users at a bounded write cost.
    """
    token = request.cookies.get(config.SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="not signed in")

    now = utc_now_str()
    with db() as conn:
        row = conn.execute(
            """
            SELECT u.id, u.email, u.display_name, u.profile, u.is_admin, u.active,
                   s.expires_at, s.revoked_at
            FROM app_sessions s JOIN app_users u ON u.id = s.user_id
            WHERE s.token_hash = %s
            """,
            (_hash(token),),
        ).fetchone()

        if row is None:
            raise HTTPException(status_code=401, detail="not signed in")
        uid, email, name, profile, is_admin, active, expires_at, revoked_at = row
        if revoked_at:
            raise HTTPException(status_code=401, detail="session revoked")
        if expires_at <= now:
            raise HTTPException(status_code=401, detail="session expired")
        if not active:
            # 403, not 401: they are who they say they are, and signing in
            # again would not help. A 401 would send the frontend round the
            # login loop forever.
            raise HTTPException(status_code=403, detail="account disabled")

        full_ttl = timedelta(days=config.SESSION_TTL_DAYS)
        if _parse(expires_at) - datetime.now(timezone.utc) < full_ttl / 2:
            conn.execute(
                "UPDATE app_sessions SET expires_at = %s, last_seen_at = %s "
                "WHERE token_hash = %s",
                (_stamp(datetime.now(timezone.utc) + full_ttl), now, _hash(token)),
            )
            conn.commit()

    return User(id=uid, email=email, display_name=name or email,
                profile=profile, is_admin=bool(is_admin))


def _stamp(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def _parse(stamp):
    return datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# Redirect-target validation
# --------------------------------------------------------------------------

def safe_next_path(raw):
    """Reduce a caller-supplied `next` to a local path, or '/'.

    THIS IS THE ONLY PLACE IN THE SERVICE WHERE AN OPEN REDIRECT CAN HAPPEN, so
    the rule is an allowlist, not a blocklist: one leading slash, no second
    slash, no scheme, no backslash, no control characters.

    '//evil.com' is the case worth naming -- it is a protocol-relative URL, so
    a browser follows it off-site while it reads like a path. A backslash is
    the same trap, because several browsers normalise '\\' to '/' in URLs.

    A rejected value becomes '/' silently rather than raising: a bad redirect
    target is not worth a 400 in the middle of somebody's login, and there is
    no attacker for whom the error message is useful.
    """
    if not raw or not isinstance(raw, str):
        return "/"
    if not raw.startswith("/") or raw.startswith("//"):
        return "/"
    if "\\" in raw or ":" in raw.split("?", 1)[0]:
        return "/"
    if any(ord(c) < 0x20 or ord(c) == 0x7F for c in raw):
        return "/"
    return raw


# --------------------------------------------------------------------------
# id_token claims
# --------------------------------------------------------------------------

def _b64url_decode(segment):
    """Base64url with the padding Google omits."""
    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


def _claims_from_id_token(id_token, expected_nonce, now=None):
    """Decode and validate an id_token's claims. Raises ValueError on any
    failure, naming which one -- for the log, never for the response.

    THE SIGNATURE IS NOT VERIFIED, AND THAT IS ONLY SAFE HERE. This function
    must be called with a token that came straight out of the TLS-authenticated
    response to our own client-secret-authenticated POST to Google's token
    endpoint. In that channel Google is already authenticated, which is the
    exemption its own documentation grants. Passing this a token from a request
    body would make every check below bypassable by anyone who can base64-encode
    a JSON object -- that variant needs JWKS signature verification, and this
    function is not it.
    """
    now = now if now is not None else time.time()
    parts = id_token.split(".")
    if len(parts) != 3:
        raise ValueError("id_token is not a JWT")
    try:
        claims = json.loads(_b64url_decode(parts[1]))
    except Exception as e:
        raise ValueError(f"id_token payload is not JSON: {e}")

    if claims.get("aud") != config.GOOGLE_CLIENT_ID:
        raise ValueError("aud does not match this client")
    if claims.get("iss") not in config.GOOGLE_ISSUERS:
        raise ValueError(f"unexpected iss {claims.get('iss')!r}")
    try:
        exp = float(claims["exp"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("missing or malformed exp")
    if exp + CLOCK_SKEW_SECONDS < now:
        raise ValueError("id_token has expired")
    # The nonce is what ties this token to the login WE started: it was minted
    # into oauth_logins before the redirect and is single-use. Without this
    # check, a token legitimately issued for our client id in some other
    # context would be replayable here.
    if claims.get("nonce") != expected_nonce:
        raise ValueError("nonce does not match this login")
    if not claims.get("sub"):
        raise ValueError("missing sub")
    if not claims.get("email"):
        raise ValueError("missing email")
    # Unverified addresses are self-asserted. Accepting one would let anyone
    # who can create a Google account claiming an allowlisted address in.
    if not claims.get("email_verified"):
        raise ValueError("email is not verified")
    return claims


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------

@router.get("/v1/auth/login")
def login(request: Request, next: str = "/"):
    """Start a login. 302s to Google."""
    if not config.oauth_configured():
        raise HTTPException(
            status_code=503,
            detail="Google OAuth is not configured (GOOGLE_CLIENT_ID / "
                   "GOOGLE_CLIENT_SECRET). See README 'Google Cloud Console'.")

    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(32)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")

    expires = datetime.now(timezone.utc) + timedelta(
        minutes=config.OAUTH_STATE_TTL_MINUTES)
    with db() as conn:
        conn.execute(
            """
            INSERT INTO oauth_logins (state, code_verifier, nonce, next_path,
                                      created_at, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (state, verifier, nonce, safe_next_path(next),
             utc_now_str(), _stamp(expires)),
        )
        conn.commit()

    params = {
        "client_id": config.GOOGLE_CLIENT_ID,
        "redirect_uri": config.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        # Without this, a browser already signed into one Google account skips
        # the chooser entirely -- which on a shared machine silently signs in
        # the wrong person, and there is no UI here to notice with.
        "prompt": "select_account",
    }
    return RedirectResponse(
        f"{config.GOOGLE_AUTH_ENDPOINT}?{urllib.parse.urlencode(params)}",
        status_code=302)


@router.get("/v1/auth/callback")
async def callback(request: Request, code: str = "", state: str = ""):
    """Google's redirect target. Ends with a session cookie and a 302 home."""
    if not config.oauth_configured():
        raise HTTPException(status_code=503, detail="Google OAuth is not configured")
    if not code or not state:
        raise HTTPException(status_code=400, detail="missing code or state")

    with db() as conn:
        # Single-use redemption. A replayed or forged state finds no row, so
        # replay protection is a property of the primary key rather than of
        # code anyone has to keep correct.
        row = conn.execute(
            "DELETE FROM oauth_logins WHERE state = %s "
            "RETURNING code_verifier, nonce, next_path, expires_at",
            (state,),
        ).fetchone()
        schema_web.prune_expired_logins(conn)
        conn.commit()

    if row is None:
        raise HTTPException(status_code=400, detail="unknown or already-used login")
    verifier, nonce, next_path, expires_at = row
    if expires_at <= utc_now_str():
        raise HTTPException(status_code=400, detail="login expired, please try again")

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(config.GOOGLE_TOKEN_ENDPOINT, data={
                "code": code,
                "client_id": config.GOOGLE_CLIENT_ID,
                "client_secret": config.GOOGLE_CLIENT_SECRET,
                "redirect_uri": config.GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
                "code_verifier": verifier,
            })
    except httpx.HTTPError as e:
        log.warning("token endpoint unreachable: %s", e)
        raise HTTPException(status_code=502, detail="could not reach Google")

    if resp.status_code != 200:
        # Google's body can contain the client_secret context; log the status
        # and keep the body out of both the response and the log.
        log.warning("token exchange failed: HTTP %s", resp.status_code)
        raise HTTPException(status_code=401, detail="sign-in failed")

    id_token = resp.json().get("id_token")
    if not id_token:
        raise HTTPException(status_code=401, detail="sign-in failed")

    try:
        # Safe without signature verification ONLY because id_token came from
        # the response above -- see this module's docstring.
        claims = _claims_from_id_token(id_token, nonce)
    except ValueError as e:
        # The reason goes to the log, never to the caller: it describes our
        # validation rules to someone probing them.
        log.warning("id_token rejected: %s", e)
        raise HTTPException(status_code=401, detail="sign-in failed")

    user_id = _resolve_user(claims)

    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=config.SESSION_TTL_DAYS)
    with db() as conn:
        conn.execute(
            """
            INSERT INTO app_sessions (token_hash, user_id, created_at, expires_at,
                                      last_seen_at, revoked_at, user_agent, ip)
            VALUES (%s, %s, %s, %s, %s, NULL, %s, %s)
            """,
            (_hash(token), user_id, utc_now_str(), _stamp(expires), utc_now_str(),
             (request.headers.get("user-agent") or "")[:500],
             request.client.host if request.client else None),
        )
        conn.execute("UPDATE app_users SET last_login_at = %s WHERE id = %s",
                     (utc_now_str(), user_id))
        conn.commit()

    response = RedirectResponse(
        config.FRONTEND_ORIGIN + safe_next_path(next_path), status_code=302)
    _set_session_cookie(response, token)
    return response


def _resolve_user(claims):
    """Map Google's claims to an app_users row, or refuse.

    SUB BEFORE EMAIL. Google's `sub` is the stable identifier for an account;
    an email address is not -- inside a Workspace domain it can be reassigned
    to a different person. Matching on email alone would hand the new holder of
    a recycled address the previous holder's sessions and job profile. So: look
    up sub first, fall back to email only to bind the sub on a first login, and
    after that the address is free to change.
    """
    sub = claims["sub"]
    email = claims["email"].strip().lower()

    with db() as conn:
        row = conn.execute(
            "SELECT id, active FROM app_users WHERE google_sub = %s", (sub,)
        ).fetchone()
        if row is None:
            row = conn.execute(
                "SELECT id, active FROM app_users WHERE email = %s AND google_sub IS NULL",
                (email,),
            ).fetchone()
            if row is not None:
                conn.execute("UPDATE app_users SET google_sub = %s WHERE id = %s",
                             (sub, row[0]))

        if row is None:
            # No row is created. The allowlist IS the access control -- see
            # manage_app_users.py. 403 rather than 401: they authenticated
            # fine, they are simply not allowed in, and retrying will not help.
            log.info("refused sign-in for un-allowlisted address %s", email)
            raise HTTPException(
                status_code=403,
                detail="this account is not authorised for this application")

        user_id, active = row
        if not active:
            raise HTTPException(status_code=403, detail="account disabled")

        # Keep the display name fresh; it is Google's to change, not ours.
        if claims.get("name"):
            conn.execute(
                "UPDATE app_users SET display_name = %s WHERE id = %s AND "
                "(display_name IS NULL OR display_name <> %s)",
                (claims["name"], user_id, claims["name"]))
        conn.commit()
    return user_id


def _set_session_cookie(response, token):
    response.set_cookie(
        key=config.SESSION_COOKIE_NAME,
        value=token,
        max_age=config.SESSION_TTL_DAYS * 24 * 3600,
        httponly=True,
        secure=config.SESSION_COOKIE_SECURE,
        # Lax, not Strict: the OAuth callback is a top-level cross-site
        # navigation, and Strict would drop the cookie on the one request that
        # sets it. Lax still blocks it on cross-site subrequests, which is what
        # CSRF needs.
        samesite="lax",
        path="/",
    )


@router.post("/v1/auth/logout")
def logout(request: Request, response: Response):
    """Revoke this session and clear the cookie. Idempotent."""
    token = request.cookies.get(config.SESSION_COOKIE_NAME)
    if token:
        with db() as conn:
            conn.execute(
                "UPDATE app_sessions SET revoked_at = %s "
                "WHERE token_hash = %s AND revoked_at IS NULL",
                (utc_now_str(), _hash(token)))
            conn.commit()
    # The delete must repeat the attributes the cookie was set with -- a
    # browser ignores a deletion whose path or secure flag doesn't match.
    response.delete_cookie(
        key=config.SESSION_COOKIE_NAME, path="/",
        httponly=True, secure=config.SESSION_COOKIE_SECURE, samesite="lax")
    # 200 even with no session: a logout that 401s is a confusing dead end.
    return {"ok": True}


@router.get("/v1/me")
def me(user: User = Depends(require_user)):
    """What the frontend calls on load to choose between the app and the
    sign-in button. Deliberately touches no jobs table."""
    return {
        "email": user.email,
        "display_name": user.display_name,
        "profile": user.profile,
        "is_admin": user.is_admin,
    }
