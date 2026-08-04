# deploy/

**The machine configuration for running this project on a home server, in version
control.** Everything here is a template or a systemd unit; nothing here is a
credential, and nothing here can be run without an account this repository does not
have.

Day-to-day operations — restarting a service, rotating a key, what to do when a
source goes quiet, where the backups are — are in `git show refactor-freeze-2026-08-02:docs/RUNBOOK.md`.
This file covers the one-time install only.

## Why these files are tracked at all

They were not, and that is the finding. `jobs-ingest.service`, `jobs-ingest.timer`
and `jobs-failure@.service` ran for a week as **regular files** in
`~/.config/systemd/user/` — not symlinks, unlike every unit the neighbouring
`garmin-ingest` project owns. So the only copy of the schedule that runs this
pipeline lived on one machine, outside git, unbacked-up and undiffable. Nothing was
red. It is the same shape as an unverified backup: fine until the disk is not, and
no way to tell it has drifted from what anyone intended because there is nothing to
have drifted from.

`deploy/systemd/jobs-ingest.service` and its two siblings are those files, verbatim.
The rest are new.

**Install by symlink, never by copy.** A copy drifts from the repo silently, which is
the failure this whole directory exists to end.

## What runs where

| unit | what it is | schedule |
|---|---|---|
| `cloudflared.service` | the tunnel — the only inbound path | always on |
| `jobs-webapp.service` | the Builders' app, `127.0.0.1:8421` | always on |
| `jobs-api.service` | the contributor work queue, `127.0.0.1:8420` | always on |
| `jobs-ingest.{service,timer}` | the nightly pipeline | daily 00:00 |
| `jobs-backup.{service,timer}` | `pg_dump`, checksum, off-machine copy | daily 04:30 |
| `jobs-backup-verify.{service,timer}` | restore into a scratch db and compare | Sunday 05:30 |
| `jobs-volume-check.{service,timer}` | the soft-failure alarm | daily 09:00 |
| `jobs-failure@.service` | the notifier every unit above points at | on failure |

Ports are not arbitrary and are not duplicated here as a decision: `8421` is
`backend/webapp/config.py:124`, `8420` is `backend/api/README.md:66`.

## Failure domains

The two halves have opposite requirements, and after this directory they are
genuinely separate units rather than separately-described halves of one thing.

| | inbound? | uptime matters? | if it stops |
|---|---|---|---|
| nightly pipeline | no | no | one night of ingest lost |
| webapp + contributor API | yes | yes | thirty people locked out |

**They still share one machine and one Postgres instance, and that coupling is
documented rather than removed.** the deleted `git show refactor-freeze-2026-08-02:docs/RUNBOOK.md` § *Failure domains* said exactly
what is shared, what a failure in each half does to the other, and what the two
tightest couplings are. Moving the app off this box is a real option and is written
up there as a decision the owner has not yet had to make.

## One-time install

Everything below needs an account, a domain or a device this repository cannot
provide. **Read `git show refactor-freeze-2026-08-02:docs/RUNBOOK.md` first**; this is the sequence, not the explanation.

```bash
# 1. cloudflared, once, interactively. `login` opens a browser and writes
#    ~/.cloudflared/cert.pem; `create` writes ~/.cloudflared/<UUID>.json, which
#    is a bearer credential for the tunnel. Neither goes in this repo.
cloudflared tunnel login
cloudflared tunnel create jobs
cloudflared tunnel route dns jobs <webapp-hostname>
cloudflared tunnel route dns jobs <contributor-api-hostname>

# 2. Fill in the three angle-bracketed values in cloudflared/config.yml, then
#    symlink it where cloudflared looks, and validate before serving traffic.
ln -s ~/apps/jobs/deploy/cloudflared/config.yml ~/.cloudflared/config.yml
cloudflared tunnel ingress validate

# 3. The units. Symlink, do not copy.
for u in ~/apps/jobs/deploy/systemd/*; do ln -sf "$u" ~/.config/systemd/user/; done
systemctl --user daemon-reload

# 4. Off-machine backup destination. Outside the repo because it may carry a
#    credential; the `-` on the unit's EnvironmentFile= means its absence is not
#    an error, and backup-jobs.sh warns loudly on every run until it is set.
printf 'JOBS_BACKUP_REMOTE=%s\n' "<rclone-remote:path or /mnt/other-disk/jobs>" \
  > ~/.config/jobs-backup.env

# 5. Enable. Timers and long-running services separately, because they fail for
#    different reasons and starting them together hides which.
systemctl --user enable --now cloudflared.service jobs-webapp.service jobs-api.service
systemctl --user enable --now jobs-ingest.timer jobs-backup.timer \
    jobs-backup-verify.timer jobs-volume-check.timer
systemctl --user list-timers 'jobs-*'
```

## Prove it before believing it

Each of these has already been a silent failure somewhere in this project's history.

```bash
# The alarm can fire. An all-zero history must breach every declared floor; if
# this exits 0 while reporting nothing, the check is decorative.
python3 backend/tools/volume-check.py --self-test

# The restore comparison can fail. --self-test truncates job_facts in the
# restored copy, so THIS RUN IS EXPECTED TO EXIT 1. A 0 here is the defect.
backend/scripts/verify-jobs-backup.sh --self-test

# The notifier can deliver. Nothing else proves the channel is alive, and an
# alert nobody receives is the same as no alert.
systemctl --user start jobs-failure@jobs-ingest.service

# The tunnel reaches the right origin.
curl -fsS https://<webapp-hostname>/v1/health
curl -fsS https://<contributor-api-hostname>/v1/health
```
