# Frontend

The browser client is plain HTML, CSS, and JavaScript modules. It has no npm
dependencies or build step. It uses the webapp's session cookie and relative
API paths, so serve it from the webapp's origin.

## Running it

After setting up the webapp and local database, run `./dev.sh` from the
repository root and open `http://localhost:8421/`. Or launch the combined
server directly:

```bash
cd backend/webapp
.venv/bin/python ../../frontend/serve.py
```

`frontend/preview.html` shows fixture-based UI states without the API. Serve
`frontend/` with a local static server to use it; the main `index.html` still
needs the webapp API for sign-in and data.

## Where the search contract and the shipped API differ

`fixtures/contract/` includes proposed response shapes. The client uses
`fixtures/shipped/`, which records what the server currently returns. The
fixture checks below cover the shipped contract.

## What building against these fixtures turned up

Job `role_track` is stored on `job_facts` and exposed through `jobs_app`. Both
the Today grouping and onboarding's seed draw use that field. Search queries
also have a `role_track`, but it describes the query rather than a posting.

## Check the client contract

From the repository root:

```bash
backend/.venv/bin/python frontend/verify_fixtures.py
node frontend/check_client.mjs
```

`fixtures/shipped/` captures current server responses and
`fixtures/contract/` contains contract examples. The checks compare those
fixtures with the Python API and JavaScript client.
