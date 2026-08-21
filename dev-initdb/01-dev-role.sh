#!/usr/bin/env bash
# Create the role the three processes actually connect as. Runs once, on initdb.
#
# WHY NOT JUST USE POSTGRES_USER. The postgres image creates POSTGRES_USER by
# running `initdb --username=...`, which makes it the bootstrap SUPERUSER. A
# superuser bypasses every privilege check, so `has_table_privilege()` and
# `has_column_privilege()` answer TRUE unconditionally -- and two tests in the
# api suite exist precisely to measure the difference between those two
# functions against a real server (`backend/api/tests/test_column_grants.py`).
# Their own docstring says it: "jobs_pipeline is not a superuser ... and
# superuser would answer TRUE regardless", which is what makes the REVOKE in
# their fixture bite. Connect as a superuser and both fail, having measured
# nothing.
#
# That is not a hypothetical -- it is what `OQ-29` cost: three documents agreed
# on a false premise about which privilege function sees a column-level GRANT,
# and the service refused to start naming an UPDATE whose absence was the point.
# The tests that pin the real answer must be able to run here.
#
# So: `postgres` stays the superuser and is used for nothing, and `jobs_dev` is
# an ordinary role that happens to own the database. CREATEDB is what lets
# `scripts/pull-prod-snapshot.sh` drop and recreate the database without
# reaching for the superuser, and ownership is what satisfies the
# `has_table_privilege(current_user, ...)` startup checks in all three processes
# without a single GRANT (docs/adr/0004 -- provisioning issues none).
#
# THIS FILE ONLY RUNS ON AN EMPTY DATA DIRECTORY. That is how the postgres image
# works, and it means editing it does nothing to a volume that already exists:
#
#     docker compose -f docker-compose.dev.yml down -v    # discards the data
#     docker compose -f docker-compose.dev.yml up -d      # re-runs this
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-SQL
	CREATE ROLE jobs_dev LOGIN PASSWORD 'jobs_dev' NOSUPERUSER CREATEDB;

	-- Ownership, not grants. In PG15+ the public schema is owned by
	-- pg_database_owner and CREATE on it is revoked from PUBLIC, so making
	-- jobs_dev the database owner is what gives it the CREATE that
	-- evals/scratchdb.py needs for its scratch_<8 hex> schemas.
	ALTER DATABASE "$POSTGRES_DB" OWNER TO jobs_dev;
	GRANT ALL ON SCHEMA public TO jobs_dev;
SQL
