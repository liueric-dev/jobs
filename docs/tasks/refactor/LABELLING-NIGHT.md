# Labelling night — pre-flight

Hand-written. Not generated, no `script:` frontmatter, do not regenerate.

**Written 2026-07-30.** Everything an agent could do for task 29 is done: the schema
exists in the live database, `pursuit-v1` is drawn and pinned, and `/v1/label` is
server-rendered and wired. What is left is this list, and it is ~15 minutes plus
however long it takes to collect ten email addresses.

**Read `tranche_five/29-labelling-session.md` for what the night is FOR.** This file is
only the sequence of operations, in the order they have to happen.

---

## The four things that are wrong today, in order

### 1. Google OAuth credentials — the only hard blocker

`GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are **empty strings** in
`backend/webapp/.env` (checked 2026-07-30). While they are, `/v1/auth/login` returns
**503** with a legible message and nobody can sign in at all
(`backend/webapp/auth.py:235-239`).

From the Google Cloud Console → Credentials → OAuth client ID → **Web application**.
`GOOGLE_REDIRECT_URI` is already set to `http://localhost:8421/v1/auth/callback` and
must match the console's *Authorized redirect URI* **byte-for-byte, trailing slash
included** — `.env`'s own comment says so, and it is the failure that looks like a
Google bug.

### 2. `FRONTEND_ORIGIN` — sign-in will SUCCEED and land on a dead origin

**This is the one that will waste the night if it is missed, because nothing errors.**

```
FRONTEND_ORIGIN=http://localhost:5173
```

That is what `backend/webapp/.env` says today. The post-login redirect is built from
it — `RedirectResponse(config.FRONTEND_ORIGIN + safe_next_path(next_path))`
(`backend/webapp/auth.py:359-360`) — so a volunteer completes Google sign-in, gets a
valid session cookie, and is then sent to `:5173`.

**Nothing is served on `:5173`.** `/v1/label` is served by **this** service, on
**`:8421`** (`GOOGLE_REDIRECT_URI`, and `PORT` defaults to 8421), and `frontend/` in
this repo contains exactly one file: `.gitkeep`. There is no dev server to start —
the port is a leftover from a frontend that does not exist yet.

**The fix is one line, made at the same time as the secrets:**

```
FRONTEND_ORIGIN=http://localhost:8421
```

Set it to whatever origin volunteers actually reach the service on — if the night runs
through a tunnel or a tailnet name, that name, not `localhost`. Set `ALLOWED_ORIGINS`
the same way while you are in the file.

**Which case are you in?** `localhost` only works for someone sitting at the machine
running the service. Ten Builders on their own phones and laptops cannot reach it, so a
real night needs a public origin — the tunnel half of task 33. **All four values change
together, and one of them is a trap in the opposite direction:**

| | testing alone, same machine | ten Builders, own devices |
|---|---|---|
| `FRONTEND_ORIGIN` | `http://localhost:8421` | `https://<tunnel-host>` |
| `ALLOWED_ORIGINS` | `http://localhost:8421` | `https://<tunnel-host>` |
| `GOOGLE_REDIRECT_URI` | `http://localhost:8421/v1/auth/callback` | `https://<tunnel-host>/v1/auth/callback` |
| `SESSION_COOKIE_SECURE` | **`false`** | **`true`** |

**`SESSION_COOKIE_SECURE` fails the other way round.** It defaults to `true` on purpose
("the insecure setting has to be typed out"), and `.env` currently sets it `false`, which
is correct for `http://localhost`. Leave it `true` while serving plain HTTP and the
**browser silently discards the session cookie** — sign-in looks successful and every
page after it is signed out again. Over HTTPS, set it back to `true`.

**`GOOGLE_REDIRECT_URI` must also be registered verbatim in the Google console.** This is
the only one of the four that gives you a real error (`redirect_uri_mismatch`, from Google,
before the request ever reaches this service) — which makes it the easiest of the four to
debug and the only one you will not have to guess at.

### 3. One `app_users` row per Builder

```bash
cd backend/webapp
.venv/bin/python manage_app_users.py add --email them@gmail.com --profile pursuit
.venv/bin/python manage_app_users.py list        # confirm before sending links
```

**`--profile pursuit`, on every one of them.** The only row that exists today is
`ericliu93@gmail.com` on profile **`tech`**, which task 12 made **inactive** — so it is
not a working example to copy from, and a Builder added on `tech` is added to the wrong
cohort.

The allowlist is the access control. A valid Google login for an address with no row is
403 and creates nothing.

**You do not need to know the schema to add people — but if you are inspecting rows,**
it is nine columns at `backend/webapp/schema_web.py:107-117`: `id`, `email`, `google_sub`,
`display_name`, `profile`, `is_admin`, `active`, `created_at`, `last_login_at`. Three
things the CLI does for you and are worth knowing before you reach for SQL:

- **`id` is generated** as `u_` plus 12 hex characters. Do not invent one.
- **`google_sub` is NULL until that person's first successful login**, then bound
  permanently. The row is matched by email before that and **by `sub` after** — so someone
  changing their Gmail address later is harmless, and a recycled address cannot inherit an
  old account.
- **`profile` has no foreign key**, deliberately, so nothing stops you seeding a user
  against a profile that is paused. That is exactly how the one existing row ended up on
  the inactive `tech`. `add` validates the name exists; it does not check it is active.

`manage_app_users.py list` is the pre-flight check: it shows profile, whether `google_sub`
is bound yet, and `last_login_at`, which together answer "did all ten rows land, and has
anyone actually got in".

### 4. The two-allowlist trap

While the OAuth consent screen is unverified, an address must be in **both**:

1. the Google console's **Test users** list, and
2. `app_users`.

**Only one of the two failures produces an error message from this service**
(`backend/webapp/README.md:143-151`, and `.env`'s own comment repeats it). Missing from
`app_users` → this service says 403. Missing from Google's test users → **Google**
refuses, before any request reaches us, and the volunteer sees a Google error page
about an app not being verified. You will hear about that one as *"the link is
broken"*, and no log line here will mention it.

Add all ten addresses to both lists in the same sitting, from the same list of emails.

---

## Serving it

```bash
cd backend/webapp
.venv/bin/uvicorn app:app --port 8421
```

**Use `backend/webapp/.venv`, and note that this is a SECOND environment.**
`fastapi`, `uvicorn`, `starlette`, `pydantic` and `httpx` are installed there and
nowhere else — `backend/webapp/requirements.txt` is a separate file from
`backend/requirements.txt` (which is `psycopg[binary]` alone), and the venv sets
`include-system-site-packages = false`. **System `python3` cannot import these
modules, and that observation has already been mistaken once for "fastapi is not
installed".** If an import fails, check which interpreter made the observation before
concluding anything about the repo.

No install and no code is needed. The route exists and is wired:
`backend/webapp/label.py:241` (the form), `:296` (submit), `:364` (progress), included
at `backend/webapp/app.py:91`.

Sanity-check before sending any link: sign in yourself and confirm you land on a
posting rather than on `:5173`.

## The link volunteers get

One URL, and nothing else:

```
https://<the origin you set as FRONTEND_ORIGIN>/v1/label
```

Signed out, that URL **302s to Google** rather than returning 401 — deliberate, because
it is a URL somebody pastes out of an email (`webapp/label.py:249-255`). They sign in
with Google, answer six questions per posting, and the form walks them to the next one.
Each labeller's queue starts with the shared **overlap block** and then rotates into
their own window of the tail, so ten people at twenty postings each cover ~110 distinct
postings rather than the same twenty.

Tell them the abstention is a real answer. *"I can't tell from this posting"* is on
every question and a guess recorded as a label is the exact poison the table exists to
avoid.

---

## What NOT to do

- **Do not add an auth bypass.** There is none anywhere in `webapp/`, and that is
  deliberate. Not a `--dev-user` flag, not a header, not "just for the night". The
  labeller identity is what the entire inter-annotator ceiling is computed from; a
  shared or spoofable identity does not produce a weaker measurement, it produces a
  number that means nothing.
- **Do not redraw the set.** `pursuit-v1` is pinned at
  `sha256(sorted job_id) = afb2d58f5d369dfd03ad9237a8b16396cea31b838a67343f51aceecf70cd1763`,
  committed at `backend/evals/fixtures/labelset-pursuit-v1.jsonl`. It could be redrawn
  only while `eval_labels` was empty — **the first submitted label closes that window
  permanently**, because redrawing reassigns what somebody's answers were answers to.
  If the set looks wrong, that is a finding to write down, not a thing to fix tonight.
- **Do not seed, import or default a label.** No code path from a model into
  `eval_labels` exists; do not build one to "get started".
- **Do not send the round-2 link on the night.** It measures memory. See below.
- **Do not quote a per-platform cell as a rate.** At these counts most of them are
  single digits and `labels.is_thin()` marks them; a bare percentage over n=3 reads
  exactly like one over n=300.

---

## Optional follow-up — the second sitting, at least 7 days later

**Clearly optional, and it is a decision about volunteers' time rather than a technical
step. Nothing in the pipeline requires it.**

A second pass over the same postings measures **intra-annotator** agreement — whether
one person gives the same answer twice. It is the *weaker* of the two ceilings; the
**inter-annotator** ceiling comes free from the overlap block on the night itself and
is the better one. Round 2 is kept because attrition may leave the weaker one as the
only ceiling with any usable n.

**Cost: ~10 more minutes per labeller who does it**, on the overlap block only — 10
postings, not 200. `progress()` counts round 2 against the overlap block precisely so
the footer does not read "3 / 200" on a ten-row queue.

**It cannot be run sooner than 7 days after their first label, and the delay IS the
measurement.** `labels.ROUND_TWO_DELAY_DAYS = 7` (`backend/evals/labels.py:1007`),
sourced from `docs/ingestion_tests/03-metrics-and-golden-set.md:25`'s *"a week apart"*.
Served an hour later it measures whether they remember their first answer, which comes
back near 100% and would then be quoted as a ceiling. The form enforces this: too soon,
and it names the **date** to come back on rather than showing an empty page
(`labels.round_two_ready()` at `:1010`, rendered by `_TOO_SOON` in `webapp/label.py`).

If you decide to spend it, the link is the same URL with one parameter:

```
https://<origin>/v1/label?round=2
```

Send it to the people who completed round 1 — anyone who answered nothing in the
overlap block gets a page saying there is nothing to re-check.

---

## Afterwards

- `python3 -m evals label status` and `export`, run from `backend/` with the
  **pipeline's** interpreter (system `python3`), not the webapp venv. Two environments,
  two purposes.
- Nothing is interpretable until the floor is beside it. `labels.interpretable()`
  refuses to build a report for any field lacking a floor or a ceiling cell, and task
  06's selfcheck JSON is the floor — `docs/ingestion_tests/selfcheck-n120-2026-07-28.json`.
- **Re-check the budget arithmetic before the night, not during it.** The figures in
  `HANDOFF.md` were computed for a five-question form and the form now asks six. See
  `HANDOFF.md`, § *the labelling night's pre-flight*.
