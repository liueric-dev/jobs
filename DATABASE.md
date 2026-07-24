# Database setup

One Postgres + PostGIS instance backs both pipelines:

| Schema   | Table              | Owner                |
|----------|--------------------|----------------------|
| `public` | `events`           | `events/` pipeline   |
| `jobs`   | `jobs`             | `jobs/` pipeline     |

They share the instance but not the schema. See `pipelib/__init__.py` for why
the shared library covers mechanism only.

## Credentials

Nothing in this repository contains a password. The connection string lives in
`~/.hermes/.env`, which is gitignored:

```
DATABASE_URL=postgresql://nyc_events:<password>@localhost:5432/nyc_events
POSTGRES_PASSWORD=<the same password>
```

`POSTGRES_PASSWORD` is required separately because `docker-compose.yml` reads
it directly; it must match the password inside `DATABASE_URL`. If it is
missing, compose fails fast with a message rather than silently starting a
database with no password.

> **Action required:** `.env` currently defines `DATABASE_URL` but not
> `POSTGRES_PASSWORD`. Add it (same value as in the URL) before the next
> `docker compose up`.

`docker-compose.yml` previously hardcoded the password in plaintext. It was
removed before this directory was ever committed, so it is not in git history
and no rotation is needed on that account.

## Starting it

```sh
docker compose --env-file ~/.hermes/.env up -d
```

The `--env-file` flag is needed because the secrets live in `~/.hermes/.env`
rather than beside the compose file.

## Multi-device access

The jobs pipeline is meant to run on more than one machine so it can gather
more postings. As configured that does not work yet, for two reasons:

1. **The port is bound to localhost.** `docker-compose.yml` publishes
   `127.0.0.1:5432`, so nothing off this machine can connect. (It used to
   bind every interface, which exposed Postgres to the whole network without
   TLS -- that is worth turning back on deliberately, not by default.)
2. **`DATABASE_URL` says `localhost`,** which on another machine means that
   machine's own Postgres.

Three ways forward, roughly in order of how much they cost:

- **SSH tunnel (simplest, no exposure).** On each remote device:
  `ssh -N -L 5432:localhost:5432 user@this-host`, then leave `DATABASE_URL`
  pointing at `localhost`. Nothing is exposed to the network; the tunnel
  carries the encryption. Good for a handful of trusted machines.
- **Tailscale or equivalent overlay network.** Bind the port to the overlay
  interface and point `DATABASE_URL` at the host's overlay address. Devices
  connect as if on a LAN, with no public exposure and no per-session setup.
- **Managed Postgres.** Move the database to a hosted provider with PostGIS
  (Supabase, Neon, RDS), point every device's `DATABASE_URL` at it, and stop
  running the container entirely. Most robust, and the only option that
  survives this machine being offline; costs money and a migration.

If you do widen the bind address instead, pair it with a firewall rule
restricting source addresses and `sslmode=require` in the connection string.
An open 5432 with password auth is found by scanners within hours.

## Concurrency across devices

Several devices ingesting into one database is safe by construction:

- Writes go through `pipelib.upsert`, which is keyed on a content hash, so a
  row written twice is written identically and the second write is a no-op
  `last_seen` bump.
- Metered APIs are protected by `pipelib.state.try_claim()`, a TTL lease on a
  dataset. Two devices cannot spend the same SerpApi or Apify budget twice,
  and a crashed run's claim expires rather than blocking the dataset forever.

## Operational note: idle transactions

A run that dies while holding an open transaction keeps its locks
indefinitely. This has already happened once here: a suspended
`nyc-events-ingest.py` process held an `ingest_state` transaction open for
thirty hours, and because a *pending* `ACCESS EXCLUSIVE` lock queues ahead of
new readers, one blocked `ALTER TABLE` behind it made the table unreadable
for everything that arrived later.

Two mitigations, both applied:

- `pipelib.dbconn.add_missing_columns()` checks the catalog before issuing
  DDL, so the steady-state path emits no `ALTER TABLE` at all. A bare
  `ADD COLUMN IF NOT EXISTS` takes the exclusive lock even when it changes
  nothing.
- `pipelib.state.ensure_state_schema(with_claims=...)` makes the claims
  column opt-in, so a pipeline that never leases datasets never asks for DDL.

Worth setting on the server as a backstop:

```sql
ALTER SYSTEM SET idle_in_transaction_session_timeout = '15min';
SELECT pg_reload_conf();
```

To find and clear a stuck holder:

```sql
SELECT pid, state, now() - state_change AS idle_for, query
FROM pg_stat_activity
WHERE datname = 'nyc_events' AND state LIKE 'idle%'
ORDER BY state_change;

SELECT pg_terminate_backend(<pid>);
```

## Backups

`events/migrate.py` defaults to a dry run and should be rehearsed against a
restored snapshot before touching live data:

```sh
docker exec nyc-events-postgres pg_dump -U nyc_events -d nyc_events | gzip > backup.sql.gz
docker exec nyc-events-postgres psql -U nyc_events -d postgres -c "CREATE DATABASE migtest;"
zcat backup.sql.gz | docker exec -i nyc-events-postgres psql -q -U nyc_events -d migtest
DATABASE_URL=...//migtest python3 events/migrate.py --apply
```
