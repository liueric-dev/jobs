---
kind: contract
written: 2026-08-02
generator: none
---

# Runbook

**How to keep this running, written for whoever has it next.**

You are probably not the person who built this. The Builder who did was in a programme
that ends, and the whole reason this file exists is that the system should outlive the
cohort. So it assumes you know Postgres and systemd and assumes nothing else — every
command below is copy-pasteable, and every one of them says what it is for and what a
bad answer looks like.

`kind: contract`, so a stale line here is a defect rather than history. If you change
how something is operated, change it here in the same commit.

**Where things are.** Code in `~/apps/jobs`. Machine configuration in
[`deploy/`](../deploy/README.md), symlinked into `~/.config/systemd/user/`. Secrets in
three separate `.env` files, mode 600, never in git. Backups in `~/backups/jobs` plus
wherever `JOBS_BACKUP_REMOTE` points.

---

## The one thing to understand before anything else

**Silence is this system's failure mode.** Not crashes — silence.

An exhausted API key returns zero rows. A revoked key returns zero rows. A blocked
scraper returns zero rows. A Workday tenant that changed its site path returns zero
rows. None of them raise, none of them exits non-zero, and a green
`jobs-ingest.service` says all four are fine.

So: **alert on volume, not on errors.** Two units implement that and they are the ones
worth understanding.

- `jobs-failure@.service` fires when a unit exits non-zero. Loud failures.
- `jobs-volume-check.service` fires when a source has written less than its floor over
  its window — or when the nightly run did not happen at all. **Quiet failures, which
  is nearly all of them.** It runs at 09:00 on its own timer, deliberately outside the
  pipeline, because a check inside the run cannot report the run's absence.

Both notify the same Telegram channel through `hermes send`. If you stop getting the
Monday digest, that is itself the signal.

---

## Failure domains — what is separate and what is not

| | inbound? | uptime matters? | if it stops |
|---|---|---|---|
| **nightly pipeline** (`jobs-ingest`) | no | no | one night of ingest lost |
| **webapp + contributor API** | yes | yes | the whole cohort locked out |

They are separate **units** — each restarts alone, each fails alone, and killing the
pipeline does not touch the app. They are **not** separate machines, and the honest
statement of what they share is:

1. **One Postgres instance**, in the `nyc-events-postgres` container. The pipeline
   writes it nightly; the webapp reads it constantly. A dead container takes out
   everything, and it is the single point of failure in this design.
2. **One host.** A power cut costs a night of ingest *and* locks thirty people out.
   The task that specified this deployment says a power cut should cost the first and
   not the second — **that is not true today**, and the reason it is not is written up
   in the task file's *What the work turned up* rather than papered over here.
3. **One `job_ingest_state` claim row**, shared between the pipeline and the
   contributor API. This is the tightest coupling in the system and the least obvious:
   a contributor holding a claim blocks the nightly pipeline from that query for
   `CLAIM_TTL_MINUTES`, and `backend/api/README.md`'s *Before opening this up* notes
   that claiming is currently unmetered, so a claim-loop could starve the pipeline
   outright. Mint contributor keys only for people you know until that is closed.

They do **not** share a venv, a Postgres role, or an import. `backend/`'s three
processes import nothing from each other; they share only `schema.py` and `lib/`. Do
not "simplify" that — `jobs_api` can touch six tables and nothing else, and that is a
security boundary rather than tidiness.

**If uptime ever has to improve, move the app and leave the pipeline here.** The app is
stateless apart from Postgres; the pipeline is the half that wants to be near the
database and does not care about being reachable.

---

## Restarting a service

```bash
systemctl --user restart jobs-webapp.service       # the Builders' app
systemctl --user restart jobs-api.service          # the contributor work queue
systemctl --user restart cloudflared.service       # the tunnel
systemctl --user start   jobs-ingest.service       # the nightly pipeline, now
```

The three long-running services carry `Restart=always` with the systemd start-limit
removed, so they come back on their own; restarting by hand is for after a config or
`.env` change. `jobs-ingest` is `Type=oneshot` — it is started, not restarted, and it
takes a `flock`, so starting it while the nightly run is going is a silent no-op rather
than a double run.

**Check it worked, and check the right thing.** A unit being `active` means the process
is up, not that it is serving:

```bash
systemctl --user status jobs-webapp.service
journalctl --user -u jobs-webapp.service -n 50 --no-pager
curl -fsS localhost:8421/v1/health          # origin, bypassing the tunnel
curl -fsS https://<webapp-hostname>/v1/health   # through the tunnel
```

If the first `curl` works and the second does not, the problem is the tunnel, not the
app. Start with `journalctl --user -u cloudflared -n 50`.

---

## Rotating a key

**Rotation never requires a redeploy, and that property is tested** — see
`backend/tests/test_secrets_rotation.py`. No credential is a literal in tracked code;
every one is read from the process environment. What differs is what has to be
restarted afterwards, and it differs by process:

| what you rotated | where it lives | what to do after |
|---|---|---|
| `SERPAPI_API_KEY`, `APIFY_API_TOKEN`, `SOCRATA_APP_TOKEN`, any LLM key | `backend/.env` | **nothing.** The next nightly run picks it up |
| `DATABASE_URL` (pipeline) | `backend/.env` | nothing |
| `DATABASE_URL` (webapp), `GOOGLE_CLIENT_SECRET` | `backend/webapp/.env` | `systemctl --user restart jobs-webapp.service` |
| `DATABASE_URL` (contributor API) | `backend/api/.env` | `systemctl --user restart jobs-api.service` |

The pipeline needs nothing because `run-daily.py` loads `backend/.env` at the top of
every run and every step is a fresh subprocess inheriting that environment. The two
services are long-lived uvicorn processes that read config at import, so they need a
restart — which is still not a redeploy. Nothing is rebuilt and no tracked file changes.

```bash
chmod 600 backend/.env            # after any edit; it is easy to lose this
cd backend && DEBUG_PRINT_KEYS=1 python3 ingest/google-serpapi.py   # prove the new key works
```

**Do not skip that last step.** A wrong key does not raise — it returns zero rows, and
you will find out from `jobs-volume-check` three days later, or from nothing at all if
the source is one whose window is thirty days.

### Contributor keys

Different mechanism, and deliberately so. Contributors' SerpApi keys stay on
contributors' machines; the API only ever receives results. Its own bearer keys are
stored as `sha256(key)` and the raw key prints once:

```bash
cd backend/api
python3 manage_users.py list
python3 manage_users.py revoke --key-hash <prefix>
python3 manage_users.py create --name "Dana" --label "dana-laptop"
```

There is no recovery command by design. A lost key is revoked and re-minted.

---

## A source has gone quiet

This is the alert you will actually get. It looks like:

```
volume-check: FINDINGS
  below_floor google-serpapi: wrote 0 over 3 run(s) in 3d, floor 40
```

**Work it in this order.** The first three are cheap and are the answer most of the
time.

1. **Did the run happen at all?** A `stale` finding beside the source findings means
   the pipeline did not run, and every source is "quiet" for one reason.
   `systemctl --user list-timers jobs-ingest.timer`.
2. **Read the last run's own volume line.** It is printed on every run, clean or not:
   ```bash
   journalctl --user -u jobs-ingest.service -n 200 --no-pager | grep -F 'written/dropped'
   ```
   One source at zero and the rest healthy is a source problem. Everything at zero is a
   database, network or `.env` problem.
3. **Run just that step by hand.** Every script runs standalone and this is the fastest
   way to see the real error, which the nightly run captures but does not surface:
   ```bash
   cd backend && DEBUG_PRINT_KEYS=1 python3 ingest/google-serpapi.py
   ```
4. **Then the source-specific causes**, in the order they actually happen here:
   - **an exhausted or revoked key** — the free tiers reset monthly and expire without
     warning. Returns an empty result set, never an error.
   - **a blocked scraper** — `builtin-nyc` is an HTML scrape. A WAF serves a challenge
     page that parses to zero cards.
   - **a moved endpoint** — `workday` is the fragile one. `docs/ingest/workday.md` has
     its gate. Remember `limit` cannot exceed 20: ask for 100 and Workday returns an
     empty array with no error, identical to "no more results".
   - **a throttled page mistaken for the end of a list** — reconcile collected counts
     against the `total` the API returned. One published account lost most of a
     2,000-posting pull to exactly this.
5. **If the source is legitimately quieter now**, change the floor rather than muting
   the alert — and record why in `backend/config/volume-floors.json`'s `_comment` for
   that source, which is the only place that reasoning will survive. Then:
   ```bash
   python3 backend/tools/volume-check.py --self-test    # must still exit 0
   cd backend && python3 -m unittest tests.test_volume_floors
   ```

**What is not a finding.** `hn-hiring` writes zero most nights — it is one monthly
thread, and its window is set accordingly. `nyc-open-data` and `weworkremotely`
legitimately write nothing for days. `skipped (insufficient history)` means the history
is shorter than that source's window, which is honest rather than reassuring: it is not
being checked yet.

See the whole picture any time, without waiting for Monday:

```bash
python3 backend/tools/volume-check.py --digest
```

---

## Adding an employer to `company_ats`

Two paths. **Try discovery first** — it is one command and it is right more often than
hand-entry, because it verifies the token against the live board instead of trusting a
URL someone pasted.

```bash
cd backend
python3 tools/ats-discover.py --seed "Employer Name" --apply   # find and store the token
python3 tools/ats-discover.py --status                        # what it concluded
python3 ingest/ats.py                                         # pull it now
```

The nightly run already probes new employers — `run-daily.py`'s first step is
`ats-discover --apply --nightly --limit 40`, so a token learned this morning is pulled
the same night, and the backlog drains over successive nights. Adding an employer and
waiting is a valid answer.

**Verify before you believe it.** A token that resolves is not a token that returns
this cohort's roles:

```bash
cd backend && python3 tools/relevance-report.py
```

Remember what the base table is: `ingest/ats.py` pulls **entire** company boards, so
roughly two thirds of what arrives is roles this pipeline exists to ignore. That is
expected. Read through the `jobs_app` view, never the `jobs` table.

**If you edit any relevance pattern while you are in there**, run
`python3 tools/relevance-report.py --dead` afterwards. Postgres word boundary is `\y`,
not `\b` — `\b` is BACKSPACE, so a `\b` pattern silently matches nothing and quietly
demotes everything it was meant to catch.

---

## Onboarding a contributor

A contributor runs the worker on their own machine with their own SerpApi account, asks
the server what to search, and posts raw results back. **They never touch Postgres and
they never send you a key.**

```bash
cd backend/api
python3 manage_users.py create --name "Dana" --label "dana-laptop"
```

Send them, over something private:

- the raw key — it prints **once** and is never stored, only `sha256(key)`
- the contributor API hostname
- `backend/api/contributor-worker/google-serpapi-worker.py` and its README

They set `JOBS_API_KEY` and their own `SERPAPI_API_KEY` in their own environment. Then
confirm it arrived:

```bash
cd backend/api && python3 manage_users.py list      # their key, with its status
```

**Before you onboard anyone you do not know**, read
`backend/api/README.md` § *Before opening this up*. Two gaps are open, both harmless
among trusted devices and real once strangers can call it: **claiming is unmetered**, so
a claim-loop can hold the whole query bank locked and starve the nightly pipeline; and
there is **no provenance**, so rows submitted through the API are indistinguishable from
locally-ingested ones and there is no way to purge one contributor's rows if they turn
out to be junk. Neither is closed.

**Never put a contributor on the tailnet.** That grants network-level access to the home
network. They reach the HTTPS hostname and nothing else.

---

## Where the backups are

`~/backups/jobs`, plus wherever `JOBS_BACKUP_REMOTE` points (set in
`~/.config/jobs-backup.env`, outside the repo because it may carry a credential).

Each night at 04:30 `jobs-backup.service` writes three files: a custom-format dump, a
cluster-wide roles-only dump, and a `.sha256` sidecar. **The roles dump matters more
here than in most projects** — `jobs_api`'s six grants are a security boundary, and
restoring the data without the roles means recreating them from memory under pressure,
which is how a service comes back as a superuser.

```bash
ls -lt ~/backups/jobs | head
journalctl --user -u jobs-backup.service -n 20 --no-pager
```

**A dump on the same disk as the database is not a backup.** It survives `DROP TABLE`
and nothing else. If `backup-jobs.sh` is warning on every run that
`JOBS_BACKUP_REMOTE` is unset, that is the state you are in and fixing it is one line.

### The restore rehearsal

`jobs-backup-verify.service` runs Sunday 05:30: it restores the newest dump into a
throwaway database and compares exact per-table row counts against the live one. An
unverified backup is a belief, not a backup.

**After changing either backup script, prove the comparison can fail:**

```bash
backend/scripts/verify-jobs-backup.sh --self-test    # MUST exit 1
```

That flag truncates `job_facts` in the restored copy. An exit of 0 means the comparison
is not comparing, which this project has shipped twice before.

**What the rehearsal does not cover, stated plainly:** it verifies **data, not ACLs**.
The restore runs `--no-owner`, so grants are not exercised. After a real restore,
re-verify privileges by hand against `backend/api/README.md`'s table — or start
`jobs-api.service`, which refuses to start when a grant is missing and names what is
absent.

### Restoring for real

```bash
# 1. Stop everything that writes, or you will race the restore.
systemctl --user stop jobs-ingest.timer jobs-api.service jobs-webapp.service

# 2. Roles first -- the data dump does not carry them.
docker exec -i nyc-events-postgres psql -U nyc_events -d postgres \
  < ~/backups/jobs/roles-<stamp>.sql

# 3. Then the database.
docker exec -i nyc-events-postgres pg_restore -U nyc_events -d jobs --clean \
  < ~/backups/jobs/jobs-<stamp>.dump

# 4. Prove the grants came back before letting anything connect. This refuses to
#    start when a grant is missing and names it, which is why it is the check.
systemctl --user start jobs-api.service
journalctl --user -u jobs-api.service -n 30 --no-pager

# 5. Everything else back.
systemctl --user start jobs-webapp.service jobs-ingest.timer
```

---

## The audit behind the "no payload is logged" claim

Task 33 asked whether anything under `backend/api/` could capture a contributor's
SerpApi key out of a submitted payload. Reproduce it:

```bash
cd backend/api && grep -rn "print(\|logger\|logging\|log\." --include=*.py . \
  | grep -v "submission_log\|contributor-worker"
```

**Result: every hit is in an admin CLI that never sees a submission** — `manage_users.py`,
and since 2026-08-02 `contribution_report.py`, which prints counts read back out of
`submission_log` and never touches a payload. `app.py` and `query_claims.py` — the entire
request path — emit nothing at all. `submission_log` stores counts and a reason, never a
body (`backend/api/app.py:308-315`). `backend/tests/test_secrets_rotation.py` pins both
facts so a future `print()` on the request path fails the suite; it scans exactly the two
request-path modules, which is why an admin CLI printing to a terminal is not a finding
here and adding one does not need the test relaxed.

~~**One residual, recorded rather than smoothed over.** `backend/api/app.py:292` returns
`detail=f"malformed body: {e}"` on a parse failure, and a pydantic `ValidationError`
string can include the offending input. That is a **response body to the sender**, not a
log — it goes back to the machine that just sent it, and nothing persists it — so it
leaks nothing today. It would become a real exposure the moment anything in front of
this service starts logging response bodies. cloudflared does not.~~

**Closed 2026-08-02 as defect `D73`** ([`DEFECTS.md` § D73](ingest/DEFECTS.md#d73)). Two
things about the struck paragraph were wrong and are worth keeping visible. The line number
was off by 58 — the site was `app.py:350`, and `:292` resolved to a *different*
`HTTPException` in a different handler, which is worse than resolving to nothing. And the
severity was understated: for pydantic's `json_invalid`, which is every syntactically broken
body, `input_value` is the **whole request body**, not the one field that failed.

`app._validation_detail()` now builds the 400 from the error's `loc` and `type` alone, both
passed through a whitelist, so the response is independent of the input by construction.
**"cloudflared does not log response bodies" is no longer load-bearing** — it was a rule
about a component someone will eventually reconfigure, and this is a property of the
service. `backend/api/tests/test_malformed_body.py` asserts it on the serialized response
bytes rather than on the exception's `detail`, which is the thing a proxy would actually
write down.

---

## Routine checks

Nothing here is a schedule anyone has to remember; the units do the remembering. This is
what to look at when you want to know the system is healthy.

```bash
systemctl --user list-timers 'jobs-*'                    # everything still scheduled?
python3 backend/tools/volume-check.py --digest           # every source, alive or not
journalctl --user -u jobs-ingest.service -n 1 --no-pager | grep -F 'written/dropped'

cd backend && python3 -m unittest discover -s tests
cd backend/webapp && .venv/bin/python -m unittest discover -s tests
```

Read the `Ran N tests` line rather than comparing against a number written anywhere —
several modules gate on a scratch database, and a skip is not a failure. No count is
recorded in this file on purpose.

## What is deliberately not automated

- **`cloudflared` updates.** `--no-autoupdate` is set. An unattended binary swap under a
  live tunnel is a restart nobody scheduled at an hour nobody chose. Update by hand and
  watch it come back.
- **Re-scoring after a persona or prompt change.** It costs LLM calls, so it never
  happens on a schedule. Run `python3 score.py --stale-report` first, then re-score with
  an explicit `--limit`.
- **Re-recording ingest cassettes.** Re-recording is not a refresh, it is the
  destruction of evidence — one cassette holds a recorded failure mode that a re-record
  would erase. Owner's call, never a session's.
- **Pruning the off-machine backup copy.** Retention on the far end is the remote's
  policy. A bug in `backup-jobs.sh` must not be able to delete the only copy that is not
  on this disk.
