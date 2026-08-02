---
kind: task
written: 2026-07-30
generator: none
---

# Labelling night — pre-flight

Hand-written. Not generated, no `script:` frontmatter, do not regenerate.

**Written 2026-07-30.** Everything an agent could do for task 29 is done: the schema
exists in the live database, `pursuit-v1` is drawn and pinned, and `/v1/label` is
server-rendered and wired. What is left is this list, and it is ~15 minutes plus
however long it takes to collect ten email addresses.

**Read `tranche_five/29-labelling-session.md` for what the night is FOR.** This file is
only the sequence of operations, in the order they have to happen.

**Added 2026-07-30: there are two cases and this file was written entirely for the second
one.** Everything below the divider assumes **Case B** — ten Builders on their own devices,
reaching the service through a tunnel — and it is all still correct for that. **The repo
owner is going to label ALONE on localhost first**, which is a shorter list and, more
importantly, **produces a different and incomplete result**. That is Case A, immediately
below. Case A is a strict subset of Case B's setup except for the two values that invert
(`SESSION_COOKIE_SECURE`, and the origin).

---

## Case A — solo, localhost

**One person, at the machine running the service, over plain HTTP.** ~10 minutes of setup,
and read § *What a solo run can and cannot produce* **before** doing it, because the
report at the end will refuse to print and that is the designed behaviour, not a fault.

### A1. `backend/webapp/.env` — verified 2026-07-30, and it is already right

```
FRONTEND_ORIGIN=http://localhost:8421
ALLOWED_ORIGINS=http://localhost:8421
SESSION_COOKIE_SECURE=false
GOOGLE_REDIRECT_URI=http://localhost:8421/v1/auth/callback
```

> **Correction, 2026-07-30.** This file and `HANDOFF.md` both say `FRONTEND_ORIGIN` and
> `ALLOWED_ORIGINS` are `http://localhost:5173` today — see § *2. `FRONTEND_ORIGIN`* below,
> which still reads that way and is **left standing as the record of what was found**.
> **They are not `:5173` any more.** Checked directly today: `backend/webapp/.env:57` reads
> `FRONTEND_ORIGIN=http://localhost:8421` and `:67` reads
> `ALLOWED_ORIGINS=http://localhost:8421`, each under a comment block explaining the
> `:5173` failure. `grep -n 5173 backend/webapp/.env` returns **nothing**. The file is
> gitignored (`.gitignore:18`), so there is no commit to point at and no way to date the
> change from history — **verify it yourself before the sitting rather than trusting either
> value written here.** The diagnosis in § *2* was right; only its "today" has expired.

**`SESSION_COOKIE_SECURE=false` is correct for Case A and must NOT be flipped to `true`.**
It defaults to `true` on purpose so that the insecure setting has to be typed out, and the
instinct on reading it is to "fix" it. Over plain-HTTP `localhost` a `true` here makes the
**browser silently discard the session cookie**: sign-in appears to succeed and every page
after it is signed out again. It flips to `true` only when the origin becomes `https://`,
which is Case B.

### A2. Google console — one redirect URI and one test user

- **Authorized redirect URI:** `http://localhost:8421/v1/auth/callback`, **byte-for-byte**,
  trailing slash included, matching `GOOGLE_REDIRECT_URI` in `.env` exactly. This is the
  one value in the whole setup that fails **loudly** — Google refuses with
  `redirect_uri_mismatch` before the request reaches this service.
- **Test users:** the owner's own Google address. While the consent screen is unverified,
  an address absent from that list is refused **by Google**, with no log line here. Solo
  does not exempt you from the two-allowlist trap (§ *4* below); it just makes it a list
  of one on each side.
- `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` still have to be filled in. That is § *1*
  below and it is the only hard blocker in either case.

### A3. Move the owner's `app_users` row from `tech` to `pursuit`

The one existing row is `ericliu93@gmail.com` on profile **`tech`**, which task 12 made
**inactive**. Labelling from it means labelling as a user of a dead profile.

**Use `manage_app_users.py set-profile`** — which changes an existing user's `profile` in
place, keeping their `id`, their bound `google_sub` and their session. It exists precisely
so that this row does not have to be deleted and re-added, which would unbind `google_sub`.

**And it is not optional tidying. Axis B answers are stamped with the SESSION's profile** —
`label.py:440` passes `profile=user.profile if q.axis == labels_mod.AXIS_B else None`, under
a comment reading *"profile comes from the SESSION, never from the form … what keeps axis B
rows attributable to a cohort"*. `eval_labels` carries **no UPDATE and no DELETE grant**
(`schema_web.py:63`: *"A label is evidence"*). So labelling while still on `tech` records
every `would_apply` answer as a `tech` preference **permanently, with no correction path**.
Run this before the first label, not after.

```bash
cd backend/webapp
.venv/bin/python manage_app_users.py set-profile --email ericliu93@gmail.com --profile pursuit
.venv/bin/python manage_app_users.py list     # confirm the row now reads pursuit
```

**Hand-writing an `UPDATE app_users SET profile = 'pursuit'` is not the path**, and the
reason is the one `backend/webapp/README.md:76-78` already gives for `add`: *"`--profile`
is which pipeline profile they see; it is validated against the `profiles` table at insert
time."* SQL typed at a prompt skips that validation, so a typo — `persuit`, `Pursuit` — is
accepted by the database and shows up as an empty job list with no error. It is the same
class of silent failure as everything else on this page.

> ~~Written 2026-07-30 **without reading `set-profile`'s implementation**, which was being
> added in parallel. Named and described here from its specification; run
> `manage_app_users.py --help` and confirm the subcommand exists before relying on this
> paragraph.~~
>
> **RESOLVED the same day: it landed, and it was then RUN.** `ericliu93@gmail.com` reads
> `pursuit` — verified with `manage_app_users.py list`, `sessions=0`, `google_sub` still
> unbound because nobody has ever logged in. The description above survived contact with
> the implementation. Two details it did not have: no inactive-profile warning fired,
> because task 12 left `pursuit` **active** and only `tech` paused; and the command prints
> *"Takes effect on their NEXT request"* rather than revoking sessions, because
> `require_user` re-joins `app_users` on every request (`auth.py:96-104`) and
> `app_sessions` stores no copy of the profile. **This step is DONE and should not be
> re-run.**

### A4. Serve it

```bash
cd backend/webapp
.venv/bin/uvicorn app:app --port 8421
```

**`backend/webapp/.venv` is the only interpreter that can import `fastapi`** — see
§ *Serving it* below for why, and do not conclude anything about the repo from an import
error made with system `python3`. Then open `http://localhost:8421/v1/label`, sign in, and
confirm you land on a **posting** rather than on `:5173`.

### A5. What a solo run can and cannot produce

**This is the part worth reading twice, because the run ends in a refusal.**

`python3 -m evals label report` **exits 2 and prints `evals label report REFUSED:`** when
there has been only one labeller — `cmd_label_report()` in `backend/evals/__main__.py`,
*"except labels.Uninterpretable as e: … print(f"evals label report REFUSED: {e}") … return
2"*. **That is correct behaviour and not a bug to route around.**

> **Cite these by symbol, not by digit.** `backend/evals/labels.py` and
> `backend/evals/__main__.py` were **being edited by another agent while this section was
> written** — `labels.py` grew by ~107 lines between two reads twenty minutes apart, moving
> `inter_annotator()` from `:1404` to `:1511` inside that window. Numbers below are what
> `grep -n` returned at the moment of writing on 2026-07-30 and are **expected to be wrong
> by the time you read them**. `HANDOFF.md` has recorded this same failure four times; the
> symbol name is the pointer and `grep -n` is the instrument.

The mechanism, so it is not mistaken for a configuration problem:

- The report's ceiling column is bound to the **inter**-annotator quantity and nothing
  else. In `_three_quantity_report()`: `inter = labels.inter_annotator(golden_rows, kinds)`
  (`evals/__main__.py:482`) feeding `ceiling=inter["fields"]` (`:486`). `intra_annotator()`
  is computed on the line between them and passed to the renderer — **but never as the
  ceiling.**
- `labels.inter_annotator()` (`backend/evals/labels.py:1511`, whose first docstring line is
  *"THE CEILING: how often two different people give the same answer"*) builds an `answers`
  dict keyed by `labeller_id` and then **skips the item**: `if len(answers) < 2:` … `continue`
  (`:1563`), counting it under `single_labeller_items`. **Two distinct `labeller_id`s on the
  same item is the requirement.** One labeller means every item is skipped and the ceiling
  block comes back empty.
- `labels.interpretable()` (`:1950`) refuses per field for whichever of floor / ceiling /
  measured is absent, and `Interpretable` is the only thing `report.render_labels()`
  accepts. **A report without a ceiling is unrepresentable, not merely discouraged.**
- **There is deliberately no `--force`.** `labels.py:1891` says so in as many words: *"a
  `--force` flag would undo it and there deliberately is not one."* The `report`
  subparser (`evals/__main__.py:629-639`) takes `--golden`, `--run`, `--selfcheck` and
  `--label-set`, and no override.

**So a solo sitting produces labels, not a report.** The labels are real, they are stored,
and nothing about them is provisional — what is missing is the scale to read a model score
against.

**What unblocks it is small and specific: one second person answering the ten `overlap`
rows.** Not the set — the block. ~~Roughly **10 minutes**~~ — **~16 minutes, measured; see
the correction below** — they never see the other 190 postings, and the queue serves the
overlap block first to everyone by construction. That is the whole of what stands between a
solo sitting and a printable report.

> **Corrected 2026-07-31, and the ask is now READY TO SEND.** Three figures have stood on
> this line and all three are kept:
>
> | figure | where it came from | status |
> |---|---|---|
> | ~~**10 minutes**~~ | a guess, written before anything was labelled | superseded |
> | ~~**~26 minutes**~~ | measured 2026-07-31 at **n=4 intervals** | superseded — it was taken inside the warm-up curve |
> | **~16 minutes** | measured at **n=29 intervals**, median 93 s/posting | **current** |
>
> Instrument: `python3 tools/label-findings.py --timing`, from `backend/`. Re-run it before
> quoting any of this; the figure has moved once per sitting so far.
>
> **And the owner's half is already done.** All ten `overlap` rows — queue positions 0–9 —
> **are answered**, so the second labeller's ten rows complete the inter-annotator ceiling
> **immediately**, with no further work from the owner and no coordination beyond sending
> the link. The ask is ten postings and about a quarter of an hour, and it is the only thing
> standing between the labels already collected and a printable report.
>
> **It is not a ten-minute favour, and asking for it as one will fail on contact.**
>
> > **HAPPENED, 2026-08-02.** `u_919ad2c305c2` answered the overlap block — 11 postings, 66
> > rows, `00:52`–`01:09` UTC — and `evals label report` printed at exit 0. The prediction in
> > this block was right about the mechanics and wrong about the consequence: the ceiling
> > completed *immediately*, and it came back **below the model's own floor on all five
> > fields** at 6–10 items each, so the report it unblocked still cannot be tuned on.
> > [`../../labelling-report-2026-08-02.md`](../../labelling-report-2026-08-02.md) owns the
> > table. **A second labeller was the last input needed for a report, not for an answer** —
> > what the answer needs is a third, a fourth, and round 2.

The other route is the **intra**-annotator ceiling — the owner re-answering those same ten
rows seven days later — and it is deliberately *not* wired to the report's ceiling column.
See `tranche_five/29-labelling-session.md`, § *Deviation* and § *Optional follow-up* below.

### A6. How many to do, and the one thing to bring back

**Do the first ten and time them.** They are the `overlap` block, the queue serves them
first automatically, and they are the exact ten a second person has to answer. Everything
after that is a trade you can make with a real number instead of a guess.

> **DONE, 2026-07-31 — and the trade can now be made with the real number.** Two sittings
> the same night put **186 label rows over 31 postings** into `eval_labels`, one labeller
> (`u_090b0ad12e99`), round 1 only, window `02:56:05`–`05:25:27` UTC. **Queue positions
> 0–30 are contiguous, so the ten `overlap` rows are complete.** By stratum: surfaced 19,
> gate_rejected 9, below_floor 3. `next_item()` resumes at position 31; this paragraph is
> the record of the first ten, not an instruction to redo them.
>
> **These counts are frozen at 2026-07-31 and are no longer the state of the table** — two
> more sittings followed on 2026-08-02. For the current figures run
> `python3 tools/label-findings.py`, which is what [`AUDIT.md`](AUDIT.md)'s row names.

**Recommended: ~60 in the first sitting, 110 as the target across two or three, all 200
only if the recall question earns it.** The strata are interleaved — every 50-row block is
roughly the set's own 50/25/25 — so **any prefix is a proportional miniature and there is
no wrong place to stop.** `next_item()` resumes exactly where you stopped, indefinitely.
The power table behind those three numbers, read against task 06's 76% and 94%
self-consistency floors, is in `HANDOFF.md` § *How many to label*.

> **Priced 2026-07-31, at a measured 93 s/posting.** The three targets above were chosen
> without a rate; here is what each one costs. **Nothing in the recommendation changes** —
> the numbers are cheaper than this file implied, not different.
>
> | target | cost at 93 s |
> |---|---|
> | twenty minutes | **13 postings** |
> | ~60, the first sitting | **1.6 h** |
> | 110, the target | **~2.8 h** across two or three sittings |
> | ≥100, the DoD's own line | **2.6 h** |
> | all 200 | **5.2 h** |
>
> Figures computed at the earlier **154 s** — *"twenty minutes ≈ 8 postings"*, *"100 ≈ 4.3
> hours"* — are superseded and are left in place in
> `tranche_five/29-labelling-session.md` § *Findings, 2026-07-31*, E, with the n each was
> taken at. **154 s was measured over the first four intervals of the first sitting and the
> labeller was still warming up:** first quartile 137 s, last quartile 83 s at n=29.

**The deliverable that is not labels: the per-posting time.** Every budget figure in this
run — *"~20 items each"*, *"~28 at five labellers"* — was computed against a **five**-question
form. The form asks **six**, and the per-posting time has never been measured, only
assumed. ~~**Write the stopwatch reading into `HANDOFF.md` when you stop.**~~ It is what
turns every future Builder-session estimate from a guess into arithmetic.

> **Discharged 2026-07-31 — it is a command now, not a thing to write down.** Run it from
> `backend/`:
>
> ```bash
> python3 tools/label-findings.py --timing     # the stopwatch reading
> python3 tools/label-findings.py              # every section
> ```
>
> Read-only, no LLM, no API key. It prints the intervals **raw and in order** before any
> statistic, calls anything over `--break-secs` (default 600) a break in the sitting and
> excludes it, and prints both figures so the exclusion can be argued with — a median taken
> across a 96-minute gap is *"a statistic about dinner"*, and this sitting contained exactly
> one such gap. It also splits first quartile against last, because *"is there a warm-up
> curve"* is the question a growing label count is supposed to answer and one median cannot
> show it.
>
> **Re-derive it after each sitting; do not re-quote it from here.** The instruction to
> re-derive has been issued three times in this run and re-quoted three times, which is the
> whole reason the tool exists — the four lines of SQL are kept so the next session runs a
> command instead of writing them. **It deliberately prints no model-vs-human agreement**;
> ~~`evals label report` still exits 2 for as long as there is one labeller~~ **that report
> now prints (2026-08-02, two labellers) and is
> [`../../labelling-report-2026-08-02.md`](../../labelling-report-2026-08-02.md)** — and this
> tool is still not a route around it. The division stands: `label-findings.py` reports what
> the humans said, `evals label report` is the only thing that puts a model number between a
> floor and a ceiling.

**Use the abstention.** *"I can't tell from this posting"* is stored as NULL and dropped
from the agreement rates rather than folded in, because *"folding them in as a value would
score two people who both gave up as two people who concurred."* A forced guess to keep the
count up is worse than a lower count.

---

## Case B — ten Builders, own devices

**Everything from here down is Case B**, and it is unchanged and still correct. Case A
readers still need § *1* (the OAuth secrets), § *4* (the two-allowlist trap), § *Serving
it* and § *Afterwards*; the `:5173` diagnosis in § *2* is the record of a value that has
since been corrected — see A1.

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
**`:8421`** (`GOOGLE_REDIRECT_URI`, and `PORT` defaults to 8421), and ~~`frontend/` in
this repo contains exactly one file: `.gitkeep`. There is no dev server to start —
the port is a leftover from a frontend that does not exist yet.~~

> **`frontend/` is a client as of 2026-08-02 (task 32), and this section's conclusion
> gets *stronger*, not weaker.** There is still nothing on `:5173`, and there is still
> no separate dev server to start: `frontend/serve.py` mounts the page on **this
> service's own port** — `config.PORT`, 8421 — precisely so that the session cookie is
> never cross-origin (`serve.py:15-22`). A static server on `:5173` would be a third
> origin that neither `FRONTEND_ORIGIN` nor `ALLOWED_ORIGINS` names, and the browser's
> failure mode for that is to drop the cookie silently rather than say why. So `:5173`
> is still a leftover, and the fix below is still the fix — it now has a server behind
> it. `serve.py` warns at startup if either variable disagrees with the port it is on.

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
~~`backend/webapp/label.py:241` (the form), `:296` (submit), `:364` (progress)~~, included
at `backend/webapp/app.py:91`.

> **Re-checked 2026-07-30 with `grep -n '@router' backend/webapp/label.py`, and all three
> had moved again.** Current, with the text quoted because the digits keep expiring:
> **`:266`** `@router.get("/v1/label", response_class=HTMLResponse)`, **`:354`**
> `@router.post("/v1/label")`, **`:466`** `@router.get("/v1/label/progress")`. `app.py:91`
> has not moved. These are the **third** set of numbers for one unchanged set of routes —
> `:218`/`:256`/`:311` in `29-labelling-session.md`, then `:241`/`:296`/`:364` here.
> **The route decorator is the durable pointer; run the grep.**

Sanity-check before sending any link: sign in yourself and confirm you land on a
posting rather than on `:5173`.

## The link volunteers get

One URL, and nothing else:

```
https://<the origin you set as FRONTEND_ORIGIN>/v1/label
```

Signed out, that URL **302s to Google** rather than returning 401 — deliberate, because
it is a URL somebody pastes out of an email (~~`webapp/label.py:249-255`~~ — **stale,
re-checked 2026-07-30: that range is now the abstention radio button. The 302 is at
`:274-280`, inside `label_form()`, reading `except HTTPException as e: if e.status_code ==
401: return RedirectResponse("/v1/auth/login?next=/v1/label", status_code=302)`**). They sign in
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

~~**Cost: ~10 more minutes per labeller who does it**~~ — **~16 minutes at the measured 93
s/posting, and read that as an upper bound**, since a re-read of a posting seen before is
plausibly faster and nobody has measured it. On the overlap block only — 10 postings, not
200. `progress()` counts round 2 against the overlap block precisely so the footer does not
read "3 / 200" on a ten-row queue.

**It cannot be run sooner than 7 days after their first label, and the delay IS the
measurement.** `labels.ROUND_TWO_DELAY_DAYS = 7` (~~`backend/evals/labels.py:1007`~~ —
**`:1114` when re-checked 2026-07-30, and moving; grep the name**), sourced from
`docs/ingestion_tests/03-metrics-and-golden-set.md:25`'s *"a week apart"*.
Served an hour later it measures whether they remember their first answer, which comes
back near 100% and would then be quoted as a ceiling. The form enforces this: too soon,
and it names the **date** to come back on rather than showing an empty page
(`labels.round_two_ready()` ~~at `:1010`~~ — **`:1117` today; `:1010` now resolves to
`def progress(...)`, a different function entirely** — rendered by `_TOO_SOON`,
`webapp/label.py:519`, used at `:300`).

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
