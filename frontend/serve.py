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

--host, AND WHY THE DEFAULT DOES NOT MOVE. This bound 127.0.0.1 unconditionally,
which made task 32's "works on a phone, tested on a real one" impossible without
the Cloudflare tunnel of task 33 -- no device on the LAN could load the page at
all. `--host 0.0.0.0` lifts that. The default is unchanged and deliberately so:
opening a listener is the kind of thing that should be typed, not inherited.

    cd backend/webapp && .venv/bin/python ../../frontend/serve.py --host 0.0.0.0

WHAT A LAN BIND DOES NOT GIVE YOU, AND IT IS THE HALF PEOPLE ASSUME. The page
renders and the API answers, so the LAYOUT half of the phone test is exercisable
-- viewport, tap targets, the bottom sheet, safe-area insets, against live
payloads. SIGNING IN IS NOT. Google's OAuth client rejects a redirect URI that is
not registered byte-for-byte, and `http://<lan-ip>:8421/...` is not; adding it is
a Google Cloud Console change, which is the same console step the tunnel needs.
FRONTEND_ORIGIN also holds exactly one value, so pointing it at the LAN address
is what breaks signing in from localhost while it is set. main() warns about
each of these rather than leaving them to be discovered in a browser with no
error message, which is this stack's documented failure mode for all three.
"""

import argparse
import os
import socket
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
from starlette.datastructures import MutableHeaders  # noqa: E402
from app import app                              # noqa: E402


class CacheControlledStaticFiles(StaticFiles):
    """StaticFiles, plus an explicit Cache-Control on every response.

    Starlette's StaticFiles sends no Cache-Control of its own, so Cloudflare
    fills the gap with its own default heuristic caching for known static
    extensions -- observed serving a stale app.css for hours after a deploy
    (T-21). no-cache forces revalidation on every request via the ETag /
    Last-Modified FileResponse already sets, rather than the edge serving a
    cached copy outright for its default TTL.
    """

    async def __call__(self, scope, receive, send):
        async def send_with_cache_control(message):
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)["cache-control"] = "no-cache"
            await send(message)

        await super().__call__(scope, receive, send_with_cache_control)


# html=True serves index.html for "/" and 404s anything else, which is what a
# hash-routed client needs: every client route is "/#/...", so the server only
# ever sees "/". check_dir=True is the default and is wanted -- a typo'd path
# should fail at startup, not on the first request.
app.mount("/", CacheControlledStaticFiles(directory=HERE, html=True), name="frontend")


#: Bind addresses that reach this machine and nothing else. Anything outside
#: this set is treated as a LAN bind, including a specific interface address.
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

DEFAULT_HOST = "127.0.0.1"


def lan_address():
    """The address a phone on the same network would use to reach this box.

    Nothing is sent. `connect()` on a UDP socket only selects a route, which is
    the one portable way to ask the kernel "which interface would you leave by"
    without parsing `ip`/`ifconfig` output per platform. The peer is TEST-NET-1
    (RFC 5737), which is guaranteed never to be routed anywhere real.

    Returns None when there is no route out -- an offline laptop, a container
    with no network. The caller degrades to advice rather than printing a
    confident wrong address, because a wrong address here costs someone the
    ten minutes of typing it into a phone.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("192.0.2.1", 9))
        return sock.getsockname()[0]
    except OSError:
        return None
    finally:
        sock.close()


def warn_about_origins(origin, host, port):
    """Print what will silently not work, before it silently does not work.

    Every case below fails in a browser with no error text -- CORS drops a
    credentialed fetch as a bare network error, an unregistered redirect URI is
    Google's own screen, and a wrong FRONTEND_ORIGIN lands the browser on a port
    where nothing is listening. None of them reach a log on this side.
    """
    if origin and origin not in config.ALLOWED_ORIGINS:
        # Not fatal: the app still boots and the API still answers. But every
        # credentialed fetch from the page will be refused by CORS, and the
        # browser reports that as a network error with no explanation.
        print(f"WARNING: {origin} is not in ALLOWED_ORIGINS "
              f"({config.ALLOWED_ORIGINS}). Add it in backend/webapp/.env.",
              file=sys.stderr)
    if origin and config.FRONTEND_ORIGIN != origin:
        print(f"WARNING: FRONTEND_ORIGIN is {config.FRONTEND_ORIGIN}, not "
              f"{origin}. Signing in will land you on the wrong origin.",
              file=sys.stderr)

    if host in LOOPBACK_HOSTS:
        return

    # ALLOWED_ORIGINS is a list and can name both; FRONTEND_ORIGIN and the
    # Google redirect URI hold one value each, so serving a phone means taking
    # them off localhost for as long as the phone is the thing being tested.
    print(f"NOTE: bound to {host}, so this is reachable by anything on the "
          "LAN. Three things must name the address the PHONE uses, not "
          "localhost: ALLOWED_ORIGINS (can hold both), FRONTEND_ORIGIN (one "
          "value -- setting it here stops localhost sign-in working) and "
          "Google's authorised redirect URI (Cloud Console, not this repo). "
          "Without the third, the page renders and signing in does not.",
          file=sys.stderr)
    print("NOTE: there is no TLS here and SESSION_COOKIE_SECURE is "
          f"{config.SESSION_COOKIE_SECURE}. On a LAN bind the session cookie "
          "crosses the network in the clear. Fine on a home network for a "
          "layout test; not a way to serve anyone.", file=sys.stderr)


def main(argv=None):
    import uvicorn

    parser = argparse.ArgumentParser(
        description="Serve frontend/ and the webapp API from one origin.")
    parser.add_argument(
        "--host", default=DEFAULT_HOST,
        help="bind address (default %(default)s -- this machine only). Use "
             "0.0.0.0 to reach it from a phone on the same network; read the "
             "module docstring first, signing in needs a console change too.")
    args = parser.parse_args(argv)

    port = config.PORT
    if args.host in LOOPBACK_HOSTS:
        origin = f"http://localhost:{port}"
    else:
        address = lan_address()
        origin = f"http://{address}:{port}" if address else None

    warn_about_origins(origin, args.host, port)

    print(f"frontend + API on {origin}/" if origin else
          f"frontend + API on port {port} -- no route out, so the address a "
          f"phone would use could not be determined")
    uvicorn.run(app, host=args.host, port=port)


if __name__ == "__main__":
    main()
