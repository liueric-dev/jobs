#!/usr/bin/env bash
# Start the local stack: dev Postgres, the webapp API, and the client, one origin.
#
#     ./dev.sh                  # then http://localhost:8421/
#     ./dev.sh --host 0.0.0.0   # reachable from a phone -- read frontend/serve.py first
#     ./dev.sh --no-db          # a database is already running; do not touch docker
#
# THIS DEFINES NOTHING. Postgres comes from docker-compose.dev.yml, the process
# is frontend/serve.py, the environment is backend/webapp/.env, and the schema
# comes from provision-database.py or a restored snapshot. All this file does is
# put them in an order and refuse EARLY where the failure would otherwise be
# silent or arrive as something that reads like a different bug. Every check
# below is one somebody has already spent time on:
#
#   * .env missing -> config.py raises on DATABASE_URL, which is correct and
#     says nothing about the four values that are not the DATABASE_URL.
#   * FRONTEND_ORIGIN still http://localhost:5173 (the .env.example default,
#     written before the client was served from this service's own origin) ->
#     the page loads, sign-in completes, and Google returns the browser to a
#     port with nothing listening. serve.py warns; that warning scrolls past
#     under uvicorn's banner, so it is also checked here, before the banner.
#   * schema absent -> app.py refuses to start naming a missing GRANT, which
#     reads as a permissions problem rather than an empty database.
#
# WHY IT DOES NOT CREATE THE SCHEMA FOR YOU. `manage_app_users.py init-schema`
# and `tools/provision-database.py` issue DDL, and this repo keeps DDL a typed
# command in both other services for the same reason. It tells you which one to
# run and stops.
#
# NOT FOR DEPLOYMENT, for every reason in frontend/serve.py's docstring: no TLS,
# static files served from the application process, SESSION_COOKIE_SECURE=false.
set -euo pipefail

cd "$(dirname "$(readlink -f "$0" 2>/dev/null || echo "$0")")"

COMPOSE_FILE=docker-compose.dev.yml
WEBAPP=backend/webapp
PORT=8421
# The role dev-initdb/01-dev-role.sh creates, on the port docker-compose.dev.yml
# publishes. Not a secret and not shared with anything: the container binds
# 127.0.0.1 only.
DEV_URL=postgresql://jobs_dev:jobs_dev@127.0.0.1:5433/jobs

start_db=1
serve_args=()
for arg in "$@"; do
    case "$arg" in
        --no-db) start_db=0 ;;
        *) serve_args+=("$arg") ;;
    esac
done

die() { printf '%s\n' "$@" >&2; exit 1; }

# --- the environment file ----------------------------------------------------
# Checked before docker, because this is the one that needs a human and a
# browser tab open on the Google Cloud Console.
if [ ! -f "$WEBAPP/.env" ]; then
    die "$WEBAPP/.env does not exist." \
        "" \
        "    cp $WEBAPP/.env.example $WEBAPP/.env && chmod 600 $WEBAPP/.env" \
        "" \
        "Local values -- note these differ from the example's defaults:" \
        "" \
        "    DATABASE_URL=$DEV_URL" \
        "    FRONTEND_ORIGIN=http://localhost:$PORT" \
        "    ALLOWED_ORIGINS=http://localhost:$PORT" \
        "    SESSION_COOKIE_SECURE=false" \
        "" \
        "GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET come from the Google Cloud" \
        "Console -- see '## Google Cloud Console' in $WEBAPP/README.md. Leave" \
        "GOOGLE_REDIRECT_URI at http://localhost:$PORT/v1/auth/callback and" \
        "register that string in the console byte-for-byte."
fi

# The format is a contract (see .env.example): a trailing comment after a value
# is read as part of the value, and the resulting origin mismatch is invisible.
env_value() { sed -n "s/^$1=//p" "$WEBAPP/.env" | tail -1; }

for required in DATABASE_URL GOOGLE_CLIENT_ID GOOGLE_CLIENT_SECRET; do
    [ -n "$(env_value "$required")" ] || die "$WEBAPP/.env: $required is empty."
done

for origin_var in FRONTEND_ORIGIN ALLOWED_ORIGINS; do
    value=$(env_value "$origin_var")
    case "$value" in
        *"localhost:$PORT"*) ;;
        *) die "$WEBAPP/.env: $origin_var is '$value', which does not name" \
               "http://localhost:$PORT. The client is served from this" \
               "service's own origin, so both must be that origin -- the" \
               ":5173 in .env.example predates that and breaks sign-in with" \
               "no error text in the browser." ;;
    esac
done

[ -x "$WEBAPP/.venv/bin/python" ] || die \
    "$WEBAPP/.venv is missing. This service has its own venv and sets" \
    "include-system-site-packages = false, so no other interpreter can import" \
    "its app.py:" \
    "" \
    "    cd $WEBAPP && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"

# --- the port ----------------------------------------------------------------
# uvicorn's own "address already in use" is legible; what it does not tell you
# is that the thing holding the port is usually a previous ./dev.sh.
if holder=$(lsof -ti "tcp:$PORT" 2>/dev/null) && [ -n "$holder" ]; then
    die "Port $PORT is already in use by pid(s): $holder" \
        "$(ps -o pid=,command= -p "$holder" 2>/dev/null || true)" \
        "" \
        "    kill $holder"
fi

# --- the database ------------------------------------------------------------
if [ "$start_db" -eq 1 ]; then
    command -v docker >/dev/null || die \
        "docker not found. Start Postgres yourself and re-run with --no-db," \
        "or install Docker Desktop -- docker-compose.dev.yml is the only" \
        "supported local database."

    docker compose -f "$COMPOSE_FILE" up -d

    # Same command as the compose healthcheck, for the same reason
    # pull-prod-snapshot.sh waits: a restore or a connection racing initdb
    # fails halfway. 60s covers first boot, where initdb runs dev-initdb/.
    printf 'waiting for postgres'
    for _ in $(seq 60); do
        if docker compose -f "$COMPOSE_FILE" exec -T postgres \
                pg_isready -U postgres -d jobs >/dev/null 2>&1; then
            printf ' ok\n'
            break
        fi
        printf '.'
        sleep 1
    done
    docker compose -f "$COMPOSE_FILE" exec -T postgres \
        pg_isready -U postgres -d jobs >/dev/null 2>&1 || die \
        "" "postgres did not become ready. Logs:" \
        "    docker compose -f $COMPOSE_FILE logs postgres"

    # dev-initdb/01-dev-role.sh runs ONLY on an empty data directory, so a
    # volume that predates it has no jobs_dev at all. Checked separately from
    # the schema below, because "role does not exist" and "table does not
    # exist" have completely different fixes and the next query cannot tell
    # them apart -- it would report an empty database either way.
    docker compose -f "$COMPOSE_FILE" exec -T postgres \
        psql -U jobs_dev -d jobs -tAc "SELECT 1" >/dev/null 2>&1 || die \
        "Cannot connect to the dev database as jobs_dev. If this volume was" \
        "created before dev-initdb/, that script never ran -- it only runs on" \
        "an empty data directory:" \
        "" \
        "    docker compose -f $COMPOSE_FILE down -v   # DISCARDS the data" \
        "    docker compose -f $COMPOSE_FILE up -d"

    # An empty database starts the service and then refuses at its own grant
    # check, naming a privilege -- which reads as a permissions problem. Ask
    # the database directly instead. jobs_app is the view the client reads
    # through; app_users is this service's own table, created separately.
    missing=$(docker compose -f "$COMPOSE_FILE" exec -T postgres \
        psql -U jobs_dev -d jobs -tAc \
        "SELECT string_agg(t, ' ') FROM (VALUES ('jobs_app'), ('app_users')) v(t)
          WHERE to_regclass('public.' || t) IS NULL")
    missing=$(printf '%s' "$missing" | tr -d '[:space:]')

    case "$missing" in
        *jobs_app*)
            die "The database has no pipeline schema yet. Either:" \
                "" \
                "    cd backend && scripts/pull-prod-snapshot.sh   # the real corpus, from B2" \
                "    cd backend && python3 tools/provision-database.py   # empty schema" \
                "" \
                "Read the banner at the top of either file first." ;;
        *app_users*)
            die "The pipeline schema is there; this service's own tables are not." \
                "One command, the only one here that issues DDL:" \
                "" \
                "    cd $WEBAPP && JOBS_ADMIN_DATABASE_URL='$DEV_URL' \\" \
                "        .venv/bin/python manage_app_users.py init-schema" \
                "" \
                "Then allow yourself in:" \
                "" \
                "    .venv/bin/python manage_app_users.py add --email you@gmail.com --profile tech --admin" ;;
    esac
fi

# --- run ---------------------------------------------------------------------
# cd for parity with the documented invocation; serve.py resolves the webapp by
# its own path, so this is not what makes the imports work.
cd "$WEBAPP"
exec .venv/bin/python ../../frontend/serve.py "${serve_args[@]}"
