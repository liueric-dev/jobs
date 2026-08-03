---
paths:
  - "frontend/**"
---

# Frontend conventions

**A shipping client, not a prototype.** Plain HTML, one stylesheet, ES modules — **no build step,
no framework, no npm, no `package.json`**, and that is a constraint to keep. Five screens exist and
all five are routed: Today, Job detail, Saved, Search and Onboarding. Not built: Contribute, and
the phone test.

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
