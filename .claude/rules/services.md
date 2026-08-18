---
paths:
  - "backend/webapp/**"
  - "backend/api/**"
---

# The two HTTP services

Both landmines here are shaped so that a `grep` finds the wrong thing first. Neither is reachable
from the pipeline, which is why they are not in `sql.md` or `ingest.md`.

**CORS `allow_methods` is a literal list: `["GET", "POST", "OPTIONS"]`** (`backend/webapp/app.py:84`).
It is not `["*"]`. Add a `DELETE` route later and it fails at preflight, in the browser, with no
message on the server and nothing in any test that calls the route directly — the route works
perfectly from `curl` and is unreachable from the client. Add the method here in the same change
that adds the route.

**`api/query_claims.py:1415` defines a function named `upsert` that returns an `UpsertResult`, and
it is safe.** Its docstring says "It still unpacks to (new, updated, unchanged)"
(`backend/api/query_claims.py:1431`). The historical defect — a bare three-tuple unpack silently
discarding `.errors` — is closed in the ingest tree (`.claude/rules/ingest.md`), but a `grep -rn
'upsert('` audit hits this definition first and it looks exactly like the thing that was wrong.
**It is a different function in a different process**, it has one caller, and that caller keeps the
whole result rather than unpacking it (`backend/api/app.py:658`). Confirm what a hit is before
"fixing" it.
