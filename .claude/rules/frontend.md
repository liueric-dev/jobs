---
paths:
  - "frontend/**"
---

# Frontend conventions

**A shipping client, not a prototype.** Plain HTML, one stylesheet, ES modules — **no build step,
no framework, no npm, no `package.json`**, and that is a constraint to keep.

**This binds design advice too, including the `frontend-design` plugin's.** Most of it assumes a
bundler, a component framework or a package to install, and all three are refused here regardless of
how good the suggestion is. Take the typography, spacing and hierarchy reasoning; leave anything
that needs a dependency. A design that cannot ship as `app.css` plus ES modules is not a design for
this client. Five screens exist and
all five are routed: Today, Job detail, Saved, Search and Onboarding. Not built: Contribute. The
phone test ran 2026-08-04 (`DEV_TASKS.md`'s `OQ-14`) and found three real bugs nobody had hit
because the client had never been loaded end to end through the deployed tunnel before — see that
row's closure for what they were.

**Serve it on the webapp's own origin, not a second dev server.** The client uses
`credentials: "same-origin"` with `BASE = ""` — served from any other host, every request loses the
session cookie and returns 401, which renders as the sign-in screen with no error anywhere.
`frontend/serve.py` mounts the page on port 8421, the webapp's own port.

```bash
cd backend/webapp && .venv/bin/python ../../frontend/serve.py   # then http://localhost:8421/
python3 frontend/verify_fixtures.py    # fixtures still describe the server
node frontend/check_client.mjs         # client still agrees with the fixtures
```

Both checkers run both ways — fixtures against the server, client against the fixtures — because
either side can drift and each direction is a different bug.
