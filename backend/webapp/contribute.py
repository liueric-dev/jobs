"""Opting in to contribute: the mint endpoint that IS the installer.

docs/adr/0007 decision 1. A Builder who opts in gets back the exact
`config.json` they drop beside the worker -- one paste, and one secret they
type themselves. Their SerpApi key never reaches this server, which is 0006
decision 3 (retained unchanged by 0007) made mechanical: the field is in the
payload, and it is empty.

HOW A ROW GETS INTO `api_keys` FROM HERE, WHICH IS THE DESIGN QUESTION IN T-27.
It does not. This service holds `jobs_web`, which is granted nothing on
../api/'s tables, and docs/adr/0006's consequences reject DEC-84 option 1 --
granting it INSERT there -- "outright, same blast-radius argument". The three
candidates were that grant, a request queue for `manage_users.py create` to
drain (rejected by 0006 decision 1, "auto-mint, not a request queue"), and a
server-to-server call. The third is the only survivor, and 0006's own
consequences list already assumed it by naming "the server-to-server shared
secret" as the unscoped follow-up.

So: this service authenticates the person, ../api/ issues the credential, and
they talk over exactly one route in one direction on a shared secret. The
property worth stating plainly, because it is what makes this cheaper than the
alternative rather than merely different: NO GRANT CROSSES THE TWO ROLES.
`jobs_api` already holds INSERT on `contributors` and `api_keys`
(../api/query_claims.py:127-128); `jobs_web` gains nothing it did not have.
The only new privilege anywhere is on this service's OWN app_users, which it
already writes.

WHAT THIS COSTS. ../README.md's "Why this is not part of `../api/`" used to end
"The two do not talk", and that sentence is now false in one specific way --
amended there rather than left to be discovered here. The coupling is a URL and
a secret, not an import: this module imports nothing from ../api/ and the call
is one httpx POST -- the same client auth.py already uses for Google's token
endpoint, so requirements.txt is unchanged -- and the two processes still share
no code and no database role.

THE RAW KEY IS IN ONE RESPONSE AND IS NEVER READABLE AGAIN. ../api/ stores only
sha256 and has no read-back route; this service stores the contributor id and
the timestamp and NOTHING ELSE -- see schema_web._ensure_contributor_link. A
Builder who loses the file opts in again, which re-keys: the lost credential is
revoked in the same statement that issues its replacement.
"""

import config  # noqa: F401  (must come first -- performs the sys.path insert)

import httpx
from fastapi import APIRouter, Depends, HTTPException
from auth import User, require_user
from db import db
from lib.timeparse import utc_now_str

router = APIRouter()

#: THE CONTRACT WITH T-28, AND THE REASON IT IS A CONSTANT RATHER THAN A DICT
#: LITERAL IN THE FUNCTION BELOW. These are the worker's own environment
#: variable names, verbatim -- ../api/contributor-worker/google-serpapi-worker.py
#: reads JOBS_API_BASE_URL, JOBS_API_KEY and SERPAPI_API_KEY and exits 1 naming
#: exactly these three when they are unset. T-28 makes that script read this
#: file when the environment is bare, so a rename on either side is a broken
#: install on a stranger's laptop, discovered by them.
#:
#: tests/test_contribute.py pins this against the worker's SOURCE, not against
#: a copy of this tuple, so the test fails when T-28 renames a field rather
#: than when someone forgets to update a fixture.
#:
#: FLAT, AND EVERY VALUE A STRING. The worker reads its settings from
#: os.environ, where everything is a string; a config file whose loader has to
#: coerce types is a second place for the two rows to disagree. MAX_QUERIES,
#: HTTP_TIMEOUT and DEBUG are deliberately absent: they have defaults in the
#: worker, and 0007 decision 3 puts the per-run policy in the POLL RESPONSE
#: (T-31), not in a file written once at install time.
CONFIG_FIELDS = ("JOBS_API_BASE_URL", "JOBS_API_KEY", "SERPAPI_API_KEY")

#: What the Builder types over. Not a placeholder like "<your key here>": the
#: worker's own unset-check is `if not SERPAPI_API_KEY`, so an empty string
#: fails it and a plausible-looking placeholder would sail past and produce a
#: SerpApi 401 instead of the legible message T-28's main() prints.
SERPAPI_KEY_PLACEHOLDER = ""


def build_config(api_key):
    """The payload, and the only place its shape is decided."""
    return {
        "JOBS_API_BASE_URL": config.CONTRIBUTOR_API_PUBLIC_URL,
        "JOBS_API_KEY": api_key,
        "SERPAPI_API_KEY": SERPAPI_KEY_PLACEHOLDER,
    }


def mint_credential(name, contributor_id=None):
    """Ask ../api/ for a credential. Returns (contributor_id, raw_key).

    httpx, matching auth.py's POST to Google's token endpoint -- the only other
    outbound call this service makes. It is already the pinned dependency this
    venv installs for that call, so this adds nothing to requirements.txt, and
    a second HTTP idiom in one service would be two failure vocabularies to
    keep in agreement for no gain. The SYNC client, though: this route is a
    plain def, so FastAPI runs it in a threadpool and an AsyncClient here would
    be an event loop that has to be created to be awaited.

    EVERY FAILURE IS A 502 AND NONE OF THEM SAYS WHY. A refused connection and
    a 401 against the shared secret are both "the operator's two processes
    disagree" -- ours to fix, not the Builder's to act on, and the shape of an
    auth failure on a mint route is not something to describe to a browser.
    Nothing is logged here either: see the module docstring on read-back paths.
    """
    try:
        with httpx.Client(timeout=config.CONTRIBUTOR_MINT_TIMEOUT_SECONDS) as client:
            response = client.post(
                f"{config.CONTRIBUTOR_API_INTERNAL_URL}/v1/internal/contributors",
                json={"name": name, "contributor_id": contributor_id},
                headers={
                    "Authorization": f"Bearer {config.JOBS_MINT_SHARED_SECRET}",
                    "User-Agent": "jobs-webapp-mint/1.0",
                },
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail="the contributor service is unavailable") from exc

    if response.status_code != 201:
        raise HTTPException(status_code=502,
                            detail="the contributor service is unavailable")
    try:
        payload = response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail="the contributor service is unavailable") from exc

    minted_id = payload.get("contributor_id")
    api_key = payload.get("api_key")
    if not minted_id or not api_key:
        raise HTTPException(status_code=502,
                            detail="the contributor service is unavailable")
    return minted_id, api_key


@router.post("/v1/contribute/opt-in")
def opt_in(user: User = Depends(require_user)):
    """Mint this Builder a credential and return their config.json.

    RE-ENTRANT, AND EVERY CALL RE-KEYS. There is no "am I already opted in?"
    branch that returns the old credential, because the old credential is not
    recoverable -- that is the property this row exists to have. A second call
    revokes the first key and returns a new file, which is also the recovery
    path for a Builder who lost theirs.

    THE STORED ID IS WRITTEN AFTER THE MINT, NEVER BEFORE. If ../api/ fails,
    nothing here changed; if this UPDATE fails, the Builder holds a working
    credential this service has forgotten, and their next opt-in mints a second
    contributor rather than re-keying. That asymmetry is deliberate: an orphaned
    contributor row costs the operator one line in `manage_users.py list`, and
    the other ordering costs a Builder a credential that was revoked before its
    replacement existed.
    """
    if not config.contribute_configured():
        # Same shape as auth.py's oauth_configured() check and for the same
        # reason: a named 503 rather than a confusing failure further in.
        raise HTTPException(status_code=503,
                            detail="contributing is not configured on this server")

    with db() as conn:
        row = conn.execute(
            "SELECT contributor_id FROM app_users WHERE id = %s", (user.id,)
        ).fetchone()
        existing = row[0] if row else None

    contributor_id, api_key = mint_credential(
        user.display_name or user.email or user.id, contributor_id=existing)

    with db() as conn:
        conn.execute(
            "UPDATE app_users SET contributor_id = %s, contributor_opted_in_at = %s "
            "WHERE id = %s",
            (contributor_id, utc_now_str(), user.id),
        )
        conn.commit()

    return {
        "filename": "config.json",
        # The file itself, as an object rather than a pre-serialised string, so
        # the client decides the indentation it writes and there is no second
        # opinion about it here.
        "config": build_config(api_key),
    }
