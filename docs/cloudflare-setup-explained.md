---
kind: record
written: 2026-08-04
subject: deploy/cloudflared, deploy/systemd
---

# What the Cloudflare setup actually did, and why

Written for someone who has never set up Cloudflare before. It walks through every command run
during the `OQ-4b`/`OQ-4a` install, in order, with what each one is *for* — not just what it
printed. The reference sequence lives in [`deploy/README.md`](../deploy/README.md); this is the
narrated version.

## The problem this solves

This project runs on a home machine, behind a residential ISP connection. Two services need to be
reachable from the internet: the webapp (`~30 Builders` use it) and the contributor API
(volunteers run a worker script against it). A home ISP connection usually can't do that cleanly:

- Most residential ISPs don't give you a static IP, so `your-service.com` has nothing stable to
  point at.
- Opening an inbound port on your home router is a real attack surface on your own network.
- Getting a real TLS certificate (the padlock, not a browser warning) normally means running
  something like `certbot`, which needs port 80 reachable from the internet to prove you own the
  domain — the same inbound-port problem again.
- Many residential ISPs block inbound connections on standard ports outright, so even the above
  might not work.

A **Cloudflare Tunnel** sidesteps all four at once. Instead of the internet connecting *in* to
your machine, your machine makes an *outbound* connection out to Cloudflare and holds it open.
Cloudflare receives public traffic for your domain at its own edge (with its own TLS certificate),
and forwards it down that outbound tunnel to your machine. No inbound port, no static IP, no
certbot. This reasoning is recorded in the config file itself —
[`deploy/cloudflared/config.yml:8-13`](../deploy/cloudflared/config.yml).

**What a tunnel does *not* do**, and this surprises people: it is not a login wall. It authenticates
your machine (the "origin") to Cloudflare, not a user to your app. Once the tunnel is up, anyone on
the internet can reach `jobs.etotheric.com` and `jobs-api.etotheric.com` — what keeps strangers out
is the webapp's own Google sign-in and the contributor API's own bearer key, same as if this were
hosted anywhere else. That's spelled out at
[`deploy/cloudflared/config.yml:15-20`](../deploy/cloudflared/config.yml).

## The pieces, and what each one is

| thing | what it is | where it lives |
|---|---|---|
| Cloudflare account | owns the domain, `etotheric.com`, in Cloudflare's DNS | cloudflare.com |
| `cert.pem` | proves *this machine* is allowed to act on your Cloudflare account | `~/.cloudflared/cert.pem` |
| a tunnel | a named, persistent object in your Cloudflare account with its own ID | Cloudflare's side, referenced by UUID |
| tunnel credentials file | the tunnel's own bearer secret — whoever has this file can receive traffic for it | `~/.cloudflared/<UUID>.json` |
| DNS route | a CNAME record pointing a hostname at your tunnel | Cloudflare's DNS, one per hostname |
| `config.yml` | tells `cloudflared` which local port each public hostname maps to | `deploy/cloudflared/config.yml`, symlinked to `~/.cloudflared/config.yml` |
| `cloudflared` | the daemon that holds the outbound connection open and does the forwarding | runs as `cloudflared.service` |

Three of these are secrets that must never enter the repo: `cert.pem`, the tunnel credentials
`.json`, and the tunnel UUID's practical equivalent (the UUID itself is not secret, but the
credentials file that authenticates it is). `.gitignore` covers `deploy/**/*.json` for exactly this
reason — a copy made "just to test" can't accidentally get committed.

## What was run, in order

**1. Account login** (you did this) — `cloudflared tunnel login` opened a browser, you approved
this machine against your Cloudflare account, and it wrote `~/.cloudflared/cert.pem`. Every command
below uses that file to prove it's allowed to act on your account.

**2. Create the tunnel:**
```
cloudflared tunnel create jobs
```
This creates one named tunnel object, `jobs`, in your Cloudflare account, and writes its
credentials file locally. Output was:
```
Tunnel credentials written to /home/eric/.cloudflared/726fa841-8945-4e06-bb06-f241cbbe30dc.json
Created tunnel jobs with id 726fa841-8945-4e06-bb06-f241cbbe30dc
```
That UUID is now this tunnel's permanent identity. It shows up twice in `config.yml` —
[line 30](../deploy/cloudflared/config.yml) (`tunnel:`) says *which* tunnel this config is for,
and [line 36](../deploy/cloudflared/config.yml) (`credentials-file:`) says where to find its secret.

**3. Route DNS to it — twice, one per hostname:**
```
cloudflared tunnel route dns jobs jobs.etotheric.com
cloudflared tunnel route dns jobs jobs-api.etotheric.com
```
Each of these adds a CNAME record in Cloudflare's DNS for `etotheric.com`, pointing that hostname
at the `jobs` tunnel. This is the step that makes `jobs.etotheric.com` resolve to *something* —
before this, that hostname didn't exist anywhere. Two hostnames, not one, because the webapp and
the contributor API are deliberately kept on separate origins (separate processes, separate
Postgres roles) — see [`deploy/cloudflared/config.yml:67-75`](../deploy/cloudflared/config.yml)
for why a shared hostname with a path split was rejected.

**4. Tell the tunnel what's behind each hostname — `config.yml`.** This is the only file in this
whole setup that's actually tracked in git, because it contains no secrets, just routing rules.
Three placeholders got filled in with real values:

- `tunnel: 726fa841-8945-4e06-bb06-f241cbbe30dc` — which tunnel
- `- hostname: jobs.etotheric.com` → `service: http://localhost:8421` — public traffic for this
  hostname goes to the webapp, port 8421 confirmed at
  [`backend/webapp/config.py:124`](../backend/webapp/config.py)
- `- hostname: jobs-api.etotheric.com` → `service: http://localhost:8420` — public traffic for
  this one goes to the contributor API, port 8420 per
  [`backend/api/README.md:66`](../backend/api/README.md)

There's also a required catch-all rule, `- service: http_status:404`
([`deploy/cloudflared/config.yml:89`](../deploy/cloudflared/config.yml)) — `cloudflared` refuses to
start without one, and it's a deliberate 404 rather than a default backend: if you ever add a
hostname in the Cloudflare dashboard but forget to add it here, it should fail loudly, not silently
land on whichever service happens to be listed first.

**5. Wire the config where `cloudflared` actually looks for it, and check it parses:**
```
ln -s ~/apps/jobs/deploy/cloudflared/config.yml ~/.cloudflared/config.yml
cloudflared tunnel ingress validate
```
`cloudflared` always reads `~/.cloudflared/config.yml` — it has no idea this project exists. The
symlink is what connects "the tracked file in this repo" to "the file the daemon actually reads,"
and it's a *symlink* rather than a copy on purpose: a copy could silently drift from the repo (edit
one, forget the other) with no way to detect it later. `ingress validate` parses the file and
checks the rules make sense — it does **not** send any traffic or start the tunnel, it's a dry run.
It returned `OK`.

**6. Install the systemd units.** Everything above got the tunnel *defined*. Nothing yet makes it
*run continuously*, or makes the webapp/API processes it forwards to exist in the first place —
that's what the `deploy/systemd/` unit files are for. All 14 were symlinked into
`~/.config/systemd/user/` and `systemctl --user daemon-reload` was run so systemd notices them.
Symlink again, same reasoning as the config file — three of these units had been running for a
week as plain copied files, silently invisible to git, before this project's `deploy/` directory
existed at all (the full story is in
[`deploy/README.md`](../deploy/README.md#why-these-files-are-tracked-at-all)).

Installing a unit and **enabling** it are different things, though — right after this step,
`systemctl` showed all 14 as known, but most as `disabled`:

```
cloudflared.service     linked   disabled
jobs-api.service        linked   disabled
jobs-webapp.service     linked   disabled
jobs-ingest.timer       enabled  disabled   ← was already running, untouched
jobs-volume-check.timer enabled  disabled   ← was already running, untouched
```

`cloudflared.service`, `jobs-webapp.service` and `jobs-api.service` were deliberately **not**
started at that point, because the webapp's `.env` still had `GOOGLE_REDIRECT_URI`,
`FRONTEND_ORIGIN` and `SESSION_COOKIE_SECURE` pointed at `localhost`, and Google's OAuth console
had to be told the new redirect URI in the exact same string, byte for byte, or every sign-in
attempt would fail with a Google error page instead of an error from this app — see
[`deploy/cloudflared/config.yml:55-63`](../deploy/cloudflared/config.yml).

**That step happened later the same day.** As of 2026-08-04, all three settings are flipped in
`backend/webapp/.env`, the Google Console redirect URI matches, and all three units are `enabled`
and `active (running)` — `cloudflared.service` has held a tunnel connection since 01:49 EDT,
`curl https://jobs.etotheric.com/v1/health` returns `{"ok":true}` from off-network, and a real
Google sign-in was completed through the public URL the same day. `DEV_TASKS.md`'s `OQ-11` is
closed as a result.

## What's still open after this

- **Three of the fourteen `deploy/systemd/` units remain uninstalled**: `jobs-backup.timer`,
  `jobs-backup-verify.timer`, `jobs-volume-digest.timer`. Tracked as `DEV_TASKS.md`'s `OQ-4a`.
- **The off-machine backup destination** (`~/.config/jobs-backup.env`) doesn't exist yet, so
  those two backup timers would currently only ever produce a local-disk copy even once
  installed — tolerated (the unit's `EnvironmentFile=` has a `-` prefix so a missing file isn't a
  startup error), but not what you want for a real backup.
- **No restore has ever been verified.** A backup nobody has restored from is a belief, not a
  backup — `deploy/README.md`'s own "Prove it before believing it" section has the self-test
  commands for this, the tunnel, and the failure notifier. Tracked as `DEV_TASKS.md`'s `OQ-4b`.

## How to check on any of this later

```bash
cloudflared tunnel list                       # tunnels on this account
cloudflared tunnel ingress validate            # does config.yml still parse
systemctl --user list-timers 'jobs-*'          # what's scheduled and when
systemctl --user status cloudflared.service    # is the tunnel actually up (once started)
curl -fsS https://jobs.etotheric.com/v1/health # does traffic reach the origin (once started)
```
