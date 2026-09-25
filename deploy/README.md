# Deployment templates

`systemd/` contains user services and timers for the pipeline, webapp,
backups, and alerts. `cloudflared/config.yml` is a tunnel
template. These files are not installed by cloning the repository.

| Unit | Purpose |
| --- | --- |
| `jobs-ingest.timer` | Run the nightly pipeline |
| `jobs-webapp.service` | Serve the user app on port 8421 |
| `jobs-backup.timer` | Create backups |
| `jobs-backup-verify.timer` | Test restore and compare data |
| `jobs-volume-check.timer` | Detect quiet ingest sources |
| `cloudflared.service` | Route public traffic to local services |

Configure the pipeline and webapp `.env` files, database roles and grants, Google
OAuth, and the tunnel before enabling services. Install the unit files as
symlinks under `~/.config/systemd/user/` so updates in this repository remain
visible. Keep Cloudflare credentials and the off-machine backup destination
outside the repository.

After installation, reload systemd and inspect the timers and service logs:

```bash
systemctl --user daemon-reload
systemctl --user list-timers 'jobs-*'
journalctl --user -u jobs-ingest.service -n 50
```

The application can be developed locally with `./dev.sh`; no deployment files
are required for that workflow.
