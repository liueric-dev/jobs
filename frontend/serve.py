#!/usr/bin/env python3
"""Serve this directory and the API from ONE origin, for local development.

    cd backend/webapp && .venv/bin/python ../../frontend/serve.py
    # then open http://localhost:8421/

WHY THIS FILE EXISTS RATHER THAN A LINE IN app.py. `backend/webapp/app.py` is
the deployed service and is owned elsewhere; this is a development launcher
that wraps it without editing it. It adds exactly one thing -- a StaticFiles
mount at "/" -- and it adds it AFTER every router, so `/v1/*` still resolves to
the API and only unmatched paths fall through to a file. Nothing about the
application changes; run `uvicorn app:app` directly and you get the API alone,
exactly as before.

WHY ONE ORIGIN AND NOT TWO. The session cookie is the client's only credential.
`backend/webapp/.env` sets both FRONTEND_ORIGIN and ALLOWED_ORIGINS to
http://localhost:8421 -- the first is where the OAuth callback sends the
browser (auth.py:359-360), the second is the CORS allowlist (app.py:78-84) --
so serving the page from that same origin means there is no cross-origin
request to get wrong. A separate static server on :5173 or :8000 would be a
third origin that neither variable names, and the browser's failure mode for
that is to drop the cookie silently rather than say why.

NO BUILD STEP AND NO NEW DEPENDENCY. StaticFiles is Starlette's, which arrives
with fastapi; uvicorn is already in requirements.txt. The client is plain
HTML/CSS/ES-modules, so there is nothing to compile and nothing to install.

NOT FOR DEPLOYMENT. Serving static files from the application process is fine
for one developer and wrong behind a real deployment, where the reverse proxy
in `backend/webapp/README.md` should serve them. There is also no TLS here:
SESSION_COOKIE_SECURE=false is what makes the cookie work over plaintext
localhost, and app.py's docstring is explicit that this must not be how it is
served anywhere else.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WEBAPP = os.path.join(os.path.dirname(HERE), "backend", "webapp")

# The webapp package resolves its siblings (`config`, `auth`, `jobs`) by
# directory, and config.py's own sys.path insert reaches ../schema.py and
# ../lib/ from there. Python puts THIS file's directory on sys.path, not that
# one, so it goes on by hand and first.
if WEBAPP not in sys.path:
    sys.path.insert(0, WEBAPP)

import config                                    # noqa: E402  (path insert first)
from fastapi.staticfiles import StaticFiles      # noqa: E402
from app import app                              # noqa: E402

# html=True serves index.html for "/" and 404s anything else, which is what a
# hash-routed client needs: every client route is "/#/...", so the server only
# ever sees "/". check_dir=True is the default and is wanted -- a typo'd path
# should fail at startup, not on the first request.
app.mount("/", StaticFiles(directory=HERE, html=True), name="frontend")


def main():
    import uvicorn

    port = config.PORT
    origin = f"http://localhost:{port}"
    if origin not in config.ALLOWED_ORIGINS:
        # Not fatal: the app still boots and the API still answers. But every
        # credentialed fetch from the page will be refused by CORS, and the
        # browser reports that as a network error with no explanation.
        print(f"WARNING: {origin} is not in ALLOWED_ORIGINS "
              f"({config.ALLOWED_ORIGINS}). Set ALLOWED_ORIGINS and "
              f"FRONTEND_ORIGIN to {origin} in backend/webapp/.env.",
              file=sys.stderr)
    if config.FRONTEND_ORIGIN != origin:
        print(f"WARNING: FRONTEND_ORIGIN is {config.FRONTEND_ORIGIN}, not "
              f"{origin}. Signing in will land you on the wrong port.",
              file=sys.stderr)

    print(f"frontend + API on {origin}/")
    uvicorn.run(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
