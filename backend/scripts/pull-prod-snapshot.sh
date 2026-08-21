#!/usr/bin/env bash
# Restore a production snapshot into the local development database.
#
#     scripts/pull-prod-snapshot.sh --list              # what restore points exist
#     scripts/pull-prod-snapshot.sh                     # newest, from B2
#     scripts/pull-prod-snapshot.sh --dump jobs-20260818-043012.dump
#     scripts/pull-prod-snapshot.sh --from ssh          # copy the file off fedora
#     scripts/pull-prod-snapshot.sh --from live         # fresh pg_dump, fedora up
#     scripts/pull-prod-snapshot.sh --slice-days 30     # keep only recent postings
#
# THIS CONSUMES AN ARTEFACT THAT ALREADY EXISTS; IT DOES NOT CREATE ONE.
# `jobs-backup.timer` runs `backup-jobs.sh` nightly at 04:30 ET, which writes
# `jobs-<stamp>.dump` (pg_dump -Fc, whole database), `roles-<stamp>.sql` and a
# `.sha256` sidecar, then copies all three off-machine to B2. A second timer
# restores the newest one into a scratch database and compares all 29 tables'
# row counts against live. So the file this script pulls is one a nightly job
# already proves restorable -- which is the reason not to add a second dump
# path here. `--from live` is the exception and it is not the default.
#
# WHY B2 IS THE DEFAULT RATHER THAN THE FALLBACK. The bucket does not depend on
# the server being up, and the server is not always up: on 2026-08-21 fedora had
# been off the tailnet for three days and `--from ssh` could not have run at all.
# B2 also keeps every dump ever copied -- backup-jobs.sh prunes its LOCAL
# directory on a 14-day glob and deliberately never prunes the remote ("a bug in
# this script must not be able to delete the only off-machine copy") -- so the
# remote is the only place with a long history of restore points to choose from.
#
# GIVE THIS MACHINE A READ-ONLY B2 KEY. The corpus is the asset: `job_facts`
# holds one LLM extraction per posting, written once per posting ever, and a
# posting whose source has delisted it is not re-extractable at all because the
# description text is gone from the internet. That is what makes the unpruned
# remote worth protecting. A laptop holding a key that can delete from the
# bucket quietly undoes the protection the no-prune rule buys. Backblaze can
# scope an application key to one bucket with listFiles/readFiles only; use one.
#
# WHAT THIS DOES NOT RESTORE: roles, and therefore grants. `roles-<stamp>.sql`
# is left in the bucket on purpose. Production separates jobs_pipeline, jobs_api
# and jobs_web as a security boundary; a laptop reproducing that would gain
# nothing and `provision-database.py` issues no GRANTs anyway (docs/adr/0004).
# The consequence, stated rather than discovered: THIS DATABASE CANNOT VERIFY A
# PRIVILEGE. Grants are checked against the deployed database, by hand.
set -euo pipefail

# --- where snapshots come from ----------------------------------------------
# An rclone remote AND path, e.g. `b2jobs:my-bucket` or `b2jobs:my-bucket/jobs`.
# Deliberately unset by default: the bucket name lives in ~/.config/jobs-backup.env
# ON THE SERVER, which is exactly the file you cannot read when the server is
# down. Read it off the Backblaze console's Buckets page and export it here.
#
# NOT `rclone lsd b2jobs:`, which is the obvious move and does not reliably
# work: the key this machine should hold is scoped to one bucket and read-only
# (see the header above), and B2 can refuse a bucket-LIST to a bucket-scoped
# key. The failure reads as a credential problem rather than a permissions
# scope, so it is worth not walking into.
REMOTE=${JOBS_SNAPSHOT_REMOTE:-}
SSH_HOST=${JOBS_SNAPSHOT_SSH:-eric@fedora}
SRC_DIR=${JOBS_SNAPSHOT_DIR:-\$HOME/backups/jobs}

# Downloaded dumps are kept OUTSIDE the repo. .gitignore already covers *.dump,
# but a cache under ~/.cache cannot be committed even by a `git add -f`, and it
# is what makes re-restoring an earlier restore point free rather than another
# download.
CACHE=${JOBS_SNAPSHOT_CACHE:-$HOME/.cache/jobs-snapshots}

# --from live only. Matches backup-jobs.sh's own defaults, and for the same
# reasons: there is no pg_dump on the fedora host, everything goes through the
# `pg-main` container, and the dump must be taken as the cluster owner. A dump
# taken as jobs_api would silently omit every object that role cannot read and
# produce a file that looks like a backup and restores a subset.
CONTAINER=${JOBS_BACKUP_CONTAINER:-pg-main}
PGUSER=${JOBS_BACKUP_USER:-nyc_events}
SRC_DB=${JOBS_BACKUP_DB:-jobs}

HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
BACKEND=$(dirname "$HERE")

# The interpreter that has psycopg, which is the only thing the verify step
# needs. CLAUDE.md's model is `python3` with a --user install, and that is still
# the fallback -- but it is wrong on a Mac, where `python3` is the 3.9 the OS
# ships and this codebase needs 3.11+ (lib/timeparse.py imports UTC from
# datetime; the tree is full of `str | None`). Homebrew's python is also
# PEP 668 externally-managed, so `pip install --user` into it is refused and a
# venv is the supported route. Prefer one if it is there, and say which was
# used rather than failing three steps later with a ModuleNotFoundError.
PY=${JOBS_DEV_PYTHON:-}
if [ -z "$PY" ]; then
  if [ -x "$BACKEND/.venv/bin/python" ]; then
    PY="$BACKEND/.venv/bin/python"
  else
    PY=python3
  fi
fi

source_kind=b2
want_dump=
slice_days=
do_list=0
target_url=

while [ $# -gt 0 ]; do
  case "$1" in
    --from)        source_kind=${2:?--from needs b2|ssh|live}; shift 2 ;;
    --dump)        want_dump=${2:?--dump needs a filename}; shift 2 ;;
    --slice-days)  slice_days=${2:?--slice-days needs a number}; shift 2 ;;
    --url)         target_url=${2:?--url needs a connection string}; shift 2 ;;
    --list)        do_list=1; shift ;;
    -h|--help)     sed -n '2,40p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *)             echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

case "$source_kind" in
  b2|ssh|live) ;;
  *) echo "--from must be b2, ssh or live (got: $source_kind)" >&2; exit 2 ;;
esac

if [ -n "$slice_days" ] && ! [[ "$slice_days" =~ ^[0-9]+$ ]]; then
  echo "--slice-days must be a whole number of days (got: $slice_days)" >&2
  exit 2
fi

# --- the target, and the guard that makes dropping it safe -------------------
#
# THIS SCRIPT ISSUES `DROP DATABASE`. That is the entire reason for the check
# below. This repo's guards exist because pointing the wrong process at the
# wrong database is its known failure mode -- lib/dbconn.py has no DATABASE_URL
# default at all rather than risk a fallback creating tables in another
# application's database, and schema.py:458-468 refuses outright to run where
# the events database's table is present. A restore tool that drops whatever
# DATABASE_URL happens to name would be a bigger version of the same mistake,
# and the .env it reads is one careless copy-paste away from production.
#
# So: loopback only, no exceptions and no override flag. A tunnel forwarding
# 5432 to a remote server would defeat this, which is one more reason the plan
# for local development does not use one.
if [ -z "$target_url" ]; then
  target_url=${DATABASE_URL:-}
fi
if [ -z "$target_url" ] && [ -f "$BACKEND/.env" ]; then
  target_url=$(sed -n 's/^DATABASE_URL=//p' "$BACKEND/.env" | head -1)
fi
if [ -z "$target_url" ]; then
  echo "no target database: pass --url, export DATABASE_URL, or write backend/.env" >&2
  exit 2
fi

# Strip scheme and credentials, then take the host between @ and the port or
# path. Deliberately crude: anything this does not recognise falls through to
# the refusal below rather than being assumed local.
url_body=${target_url#*://}
url_hostport=${url_body##*@}
target_host=${url_hostport%%[:/]*}
target_db=${target_url##*/}
target_db=${target_db%%\?*}

case "$target_host" in
  localhost|127.0.0.1|::1|"") ;;
  *)
    echo "refusing to run: this script drops and recreates the target database," >&2
    echo "and the target is not local (host: $target_host)." >&2
    echo "Local development uses the container in docker-compose.dev.yml." >&2
    exit 1 ;;
esac

if [ -z "$target_db" ]; then
  echo "could not read a database name out of the target URL" >&2
  exit 1
fi

# The maintenance connection, for the DROP/CREATE that cannot run from inside
# the database being dropped. Same server, same credentials, `postgres` instead.
maint_url="${target_url%/*}/postgres"

mkdir -p "$CACHE"

# --- listing restore points --------------------------------------------------

list_remote() {
  case "$source_kind" in
    b2)
      [ -n "$REMOTE" ] || { echo "JOBS_SNAPSHOT_REMOTE is unset -- see the header" >&2; return 1; }
      rclone lsl "$REMOTE" --include "$SRC_DB-*.dump" 2>/dev/null \
        | awk '{printf "%12d  %s %s  %s\n", $1, $2, $3, $4}' | sort -k4 ;;
    ssh)
      # shellcheck disable=SC2029  # $SRC_DIR is meant to expand on the server
      ssh "$SSH_HOST" "ls -lt $SRC_DIR/$SRC_DB-*.dump" 2>/dev/null \
        | awk '{printf "%12d  %s\n", $5, $9}' ;;
    live)
      echo "(--from live takes a new dump; there is nothing to list)" ;;
  esac
}

if [ "$do_list" = 1 ]; then
  echo "cached locally in $CACHE:"
  if ls -1t "$CACHE/$SRC_DB-"*.dump >/dev/null 2>&1; then
    ( cd "$CACHE" && ls -lt "$SRC_DB-"*.dump | awk '{printf "  %12d  %s\n", $5, $9}' )
  else
    echo "  (none)"
  fi
  echo
  echo "available from $source_kind:"
  list_remote | sed 's/^/  /' || echo "  (unavailable)"
  exit 0
fi

# --- acquiring the dump ------------------------------------------------------

fetch_b2() {
  [ -n "$REMOTE" ] || {
    echo "JOBS_SNAPSHOT_REMOTE is unset. Take the bucket name from the" >&2
    echo "Backblaze console's Buckets page, then:" >&2
    echo "    export JOBS_SNAPSHOT_REMOTE=b2jobs:<bucket>" >&2
    echo "(a bucket-scoped read-only key may not be allowed to list buckets," >&2
    echo " so 'rclone lsd b2jobs:' is not a reliable way to find the name)" >&2
    exit 2; }
  command -v rclone >/dev/null || { echo "rclone not installed: brew install rclone" >&2; exit 2; }

  local name=$want_dump
  if [ -z "$name" ]; then
    # Newest by NAME, not by mtime: the stamp is YYYYmmdd-HHMMSS, so it sorts
    # correctly as a string, and an object's mtime in a bucket is the upload
    # time -- which for a backfilled copy is not when the dump was taken.
    name=$(rclone lsf "$REMOTE" --include "$SRC_DB-*.dump" | sort | tail -1)
    [ -n "$name" ] || { echo "no $SRC_DB-*.dump found in $REMOTE" >&2; exit 1; }
  fi

  if [ -f "$CACHE/$name" ]; then
    echo "using cached $name"
  else
    echo "downloading $name from $REMOTE"
    rclone copy "$REMOTE/$name" "$CACHE/" --progress
  fi
  # The sidecar is copied to the bucket by backup-jobs.sh alongside the dump, so
  # a truncated or bit-rotted transfer is detectable rather than assumed absent.
  rclone copy "$REMOTE/$name.sha256" "$CACHE/" 2>/dev/null || true
  printf '%s' "$name"
}

fetch_ssh() {
  local name=$want_dump
  if [ -z "$name" ]; then
    # shellcheck disable=SC2029
    name=$(ssh "$SSH_HOST" "ls -1 $SRC_DIR/$SRC_DB-*.dump" | xargs -n1 basename | sort | tail -1)
    [ -n "$name" ] || { echo "no $SRC_DB-*.dump found on $SSH_HOST" >&2; exit 1; }
  fi
  if [ -f "$CACHE/$name" ]; then
    echo "using cached $name"
  else
    echo "copying $name from $SSH_HOST"
    scp "$SSH_HOST:$SRC_DIR/$name" "$CACHE/$name"
  fi
  scp "$SSH_HOST:$SRC_DIR/$name.sha256" "$CACHE/$name.sha256" 2>/dev/null || true
  printf '%s' "$name"
}

fetch_live() {
  # A REAL DUMP AGAINST PRODUCTION, and that is why it is not the default.
  # jobs-backup.timer's 04:30 slot was chosen against the other timers on that
  # machine because a dump competes for IO with the ingest run it is dumping.
  # Streamed to stdout rather than written to the server's disk, so this leaves
  # nothing behind and does not disturb the retention window.
  local stamp name
  stamp=$(date -u +%Y%m%d-%H%M%S)
  name="$SRC_DB-$stamp-live.dump"
  echo "streaming a fresh pg_dump from $SSH_HOST ($CONTAINER, as $PGUSER)" >&2
  # .part until it succeeds: a stream killed halfway must never sit in the cache
  # looking exactly like a good dump. Same rule backup-jobs.sh applies with .tmp.
  ssh "$SSH_HOST" "docker exec -i $CONTAINER pg_dump -U $PGUSER -d $SRC_DB -Fc" \
    >"$CACHE/$name.part"
  mv "$CACHE/$name.part" "$CACHE/$name"
  printf '%s' "$name"
}

case "$source_kind" in
  b2)   dump_name=$(fetch_b2   | tail -1) ;;
  ssh)  dump_name=$(fetch_ssh  | tail -1) ;;
  live) dump_name=$(fetch_live | tail -1) ;;
esac

dump="$CACHE/$dump_name"
[ -s "$dump" ] || { echo "dump is missing or empty: $dump" >&2; exit 1; }

# --- verifying it before trusting it -----------------------------------------
#
# Cheapest checks first, so a corrupt file fails in a second rather than after a
# full restore -- and so that a bad download is never mistaken for a bad schema.
if [ -f "$dump.sha256" ]; then
  echo "checksum..."
  # ONE SIDECAR, TWO FILES. backup-jobs.sh writes the checksums of the dump AND
  # the roles-only dump into a single `<dump>.sha256`, so feeding the whole file
  # to `shasum -c` here fails on the roles line -- not because anything is
  # corrupt, but because that file was deliberately not downloaded.
  #
  # AND IT SHOULD NOT BE. `pg_dumpall --roles-only` carries the cluster's role
  # definitions including password hashes. That belongs on the server and in the
  # bucket, not on a laptop, and this script does not restore roles anyway. So
  # the dump's own line is selected out and checked alone; a sidecar that does
  # not mention the dump at all is a real failure and still stops the run.
  line=$(grep -E "[[:space:]]\*?$(basename "$dump_name")\$" "$dump.sha256" || true)
  if [ -z "$line" ]; then
    echo "sidecar $dump_name.sha256 has no line for $dump_name" >&2
    exit 1
  fi
  ( cd "$CACHE" && printf '%s\n' "$line" | shasum -a 256 -c - ) >/dev/null
else
  # --from live produces no sidecar because nothing on the far end wrote one.
  # Say so rather than letting a silently unverified file look like a verified
  # one; the pg_restore -l below is then the only integrity check there is.
  echo "WARNING: no .sha256 beside $dump_name -- integrity is unverified" >&2
fi
echo "catalogue..."
pg_restore -l "$dump" >/dev/null

# --- restoring ----------------------------------------------------------------

echo "waiting for $target_host to accept connections..."
for _ in $(seq 1 30); do
  pg_isready -d "$maint_url" >/dev/null 2>&1 && break
  sleep 1
done
pg_isready -d "$maint_url" >/dev/null 2>&1 || {
  echo "no Postgres at $target_host. Start it with:" >&2
  echo "    docker compose -f docker-compose.dev.yml up -d" >&2
  exit 1; }

echo "recreating database $target_db"
# Terminating first: a psql or a uvicorn left connected makes DROP DATABASE hang
# rather than fail, which reads as the script being stuck.
psql -d "$maint_url" -v ON_ERROR_STOP=1 -q -c \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity
    WHERE datname = '$target_db' AND pid <> pg_backend_pid();" >/dev/null
psql -d "$maint_url" -v ON_ERROR_STOP=1 -q -c "DROP DATABASE IF EXISTS \"$target_db\";"
psql -d "$maint_url" -v ON_ERROR_STOP=1 -q -c "CREATE DATABASE \"$target_db\";"

# --no-owner --no-privileges because the dump was taken as the cluster owner and
# names jobs_pipeline, jobs_api and jobs_web -- roles that do not exist here and
# deliberately are not created. Without both flags every GRANT and every ALTER
# ... OWNER TO in the archive fails.
#
# NOT --exit-on-error, and the reason is worth stating: a custom-format archive
# from a differently-provisioned cluster can carry objects whose restore is
# noisy but harmless, and aborting on the first would turn a usable restore into
# no restore. The honest check is the one below -- provision-database.py's
# --verify-only asks whether all the objects the three processes require are
# actually present, which is a stronger claim than pg_restore's exit code and
# the same check CI runs. Errors are counted and printed rather than swallowed.
echo "restoring $dump_name"
restore_log=$(mktemp)
trap 'rm -f "$restore_log"' EXIT
set +e
pg_restore --no-owner --no-privileges -j 4 -d "$target_url" "$dump" 2>"$restore_log"
set -e
if [ -s "$restore_log" ]; then
  echo "pg_restore reported $(wc -l <"$restore_log" | tr -d ' ') diagnostic line(s):" >&2
  sed 's/^/    /' "$restore_log" >&2
fi

# --- the slice ----------------------------------------------------------------
#
# ONE STATEMENT, because every derived table cascades from jobs(id):
# job_scores, job_facts, job_matches, job_events, cohort_signal and
# search_query_results all declare ON DELETE CASCADE (schema.py:508, 550, 579,
# 599, 651, 1152). Deleting from `jobs` is enough; nothing else is listed here
# by name, so a seventh dependent table added later is covered for free.
#
# `first_seen` is TEXT holding 'YYYY-MM-DDTHH:MM:SS' in UTC with no offset
# (lib/timeparse.py:113-122), and that format is load-bearing precisely BECAUSE
# the pipeline compares these as strings. The comparison below is the idiom the
# codebase already uses, not a cast invented here.
#
# WHAT A RECENCY SLICE COSTS: it is biased toward whichever sources ingested
# most recently, which is fine for looking at a UI and is NOT a valid eval
# corpus. `docs/STATE-OF-THE-SYSTEM.md` names selecting a corpus with
# ORDER BY first_seen DESC as a rule not to break; this is the same bias.
if [ -n "$slice_days" ]; then
  before=$(psql -d "$target_url" -At -c "SELECT count(*) FROM jobs;")
  psql -d "$target_url" -v ON_ERROR_STOP=1 -q -c \
    "DELETE FROM jobs
      WHERE first_seen < to_char((now() AT TIME ZONE 'utc')
                                 - make_interval(days => $slice_days),
                                 'YYYY-MM-DD\"T\"HH24:MI:SS');"
  # Scoped to this schema's own tables rather than a bare `VACUUM ANALYZE`.
  # jobs_dev is deliberately not a superuser, so a cluster-wide vacuum tries the
  # shared catalogues (pg_authid, pg_database, ...), cannot read them, and prints
  # eleven "permission denied to vacuum" warnings that look like a broken
  # restore and are not. The list is queried, not hardcoded, so a dependent
  # table added later is covered without editing this.
  vac=$(psql -d "$target_url" -At -c \
    "SELECT string_agg(format('public.%I', relname), ', ')
       FROM pg_stat_user_tables WHERE schemaname = 'public';")
  [ -n "$vac" ] && psql -d "$target_url" -v ON_ERROR_STOP=1 -q -c "VACUUM (ANALYZE) $vac;"
  after=$(psql -d "$target_url" -At -c "SELECT count(*) FROM jobs;")
  echo "sliced to the last $slice_days days: jobs $before -> $after"
fi

# --- proving it landed --------------------------------------------------------
echo
echo "verifying the restored database has everything all three processes need..."
echo "  (interpreter: $PY)"
"$PY" "$BACKEND/tools/provision-database.py" --verify-only --url "$target_url"

echo
echo "row counts:"
psql -d "$target_url" -At -F'  ' -c "
SELECT relname, (xpath('/row/c/text()',
         query_to_xml(format('SELECT count(*) AS c FROM public.%I', relname),
                      false, true, '')))[1]::text
FROM pg_stat_user_tables WHERE schemaname = 'public' ORDER BY relname;" | sed 's/^/  /'

echo
echo "ok: $target_db restored from $dump_name"
