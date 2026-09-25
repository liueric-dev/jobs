# Deployment templates

`systemd/` contains user units for the ingestion pipeline, backups, and
source-volume alerts. These templates are
not installed by cloning this repository.

`cloudflared/config.yml` still contains the unrelated Bankan route because
the tunnel is shared; the jobs route was removed. Do not deploy that template
without checking the existing tunnel owner and configuration.

Use the project `backend/.venv/bin/python` for the ingest service. Configure
`backend/.env` and the dedicated database role before enabling the timer.
The backup units may still capture legacy tables in an existing database.

```bash
systemctl --user daemon-reload
systemctl --user list-timers 'jobs-*'
journalctl --user -u jobs-ingest.service -n 50
```
