#!/usr/bin/env bash
# Restore the newest dump into a throwaway database and prove it matches.
#
# THIS IS THE HALF THAT MAKES THE OTHER SCRIPT A BACKUP RATHER THAN A FILE. An
# unverified dump is a belief about a file. The task says it in one line -- "an
# unverified backup is a belief, not a backup" -- and this repo has the receipts
# for what happens when a check cannot fail: two shipped checks that skipped
# silently for their entire lives, one of them for months.
#
# So: exit non-zero on any mismatch, and prove that it does by breaking it once.
# `--self-test` below exists for exactly that, and the runbook tells the
# operator to run it after any change to either script.
set -euo pipefail

DB=${JOBS_BACKUP_DB:-jobs}
CONTAINER=${JOBS_BACKUP_CONTAINER:-pg-main}
DEST=${JOBS_BACKUP_DIR:-$HOME/backups/jobs}
PGUSER=${JOBS_BACKUP_USER:-nyc_events}
SCRATCH=${JOBS_BACKUP_SCRATCH_DB:-jobs_restore_check}

# --self-test truncates a table in the restored copy before comparing, which
# must make this script fail. If it does not, the comparison is not comparing.
self_test=0
[ "${1:-}" = "--self-test" ] && self_test=1

psql_scratch() { docker exec -i "$CONTAINER" psql -U "$PGUSER" -d "$SCRATCH" -At -c "$1"; }

# Exact counts, not pg_stat_user_tables.n_live_tup -- that column is an
# ANALYZE-time estimate and will happily report equal while the data differs.
# query_to_xml runs a real count(*) per table in one round trip.
#
# `public` is named explicitly. This is ops tooling that only ever runs against
# a real database and a scratch copy, and query_to_xml needs a name it can
# resolve unambiguously.
count_sql="
SELECT relname || E'\t' || (xpath('/row/c/text()',
         query_to_xml(format('SELECT count(*) AS c FROM public.%I', relname),
                      false, true, '')))[1]::text
FROM pg_stat_user_tables WHERE schemaname = 'public' ORDER BY relname;"

dump=$(ls -1t "$DEST/$DB-"*.dump 2>/dev/null | head -1)
[ -n "$dump" ] || { echo "no dump found in $DEST" >&2; exit 1; }
echo "verifying $dump"

# Cheapest checks first, so a corrupt file fails in a second rather than after a
# full restore.
( cd "$DEST" && sha256sum -c "$(basename "$dump").sha256" ) >/dev/null
docker exec -i "$CONTAINER" pg_restore -l <"$dump" >/dev/null

cleanup() {
  docker exec "$CONTAINER" dropdb -U "$PGUSER" --if-exists "$SCRATCH" >/dev/null 2>&1 || true
}
# A failed run must not leave a scratch database behind; the next run would then
# fail on createdb for a reason that has nothing to do with backups.
trap cleanup EXIT

cleanup
docker exec "$CONTAINER" createdb -U "$PGUSER" "$SCRATCH"

# --no-owner because the restore runs as the cluster owner into a scratch
# database, and reproducing jobs_pipeline's and jobs_api's ownership is not what
# is being tested here.
#
# STATE THE CONSEQUENCE HONESTLY: this rehearsal verifies DATA, NOT ACLs. That
# gap is larger for this database than for most, because backend/api/README.md's
# privilege table is a security boundary -- jobs_api's six grants are what stop
# a leaked bearer token reaching the pipeline's tables. Those grants ride in the
# separate roles-only dump that backup-jobs.sh takes, and NOTHING REHEARSES IT.
# A real restore must re-verify the grants by hand; `git show refactor-freeze-2026-08-02:docs/RUNBOOK.md` says how.
docker exec -i "$CONTAINER" pg_restore -U "$PGUSER" -d "$SCRATCH" --no-owner <"$dump"

if [ "$self_test" = 1 ]; then
  # job_facts, not an arbitrary table: it is the one holding the LLM extractions
  # that cost real calls, so if the comparison is going to be blind to any table
  # it must not be blind to this one.
  echo "SELF-TEST: truncating job_facts in the restored copy; this run must FAIL"
  psql_scratch "TRUNCATE job_facts CASCADE;" >/dev/null
fi

live=$(docker exec -i "$CONTAINER" psql -U "$PGUSER" -d "$DB" -At -c "$count_sql")
restored=$(psql_scratch "$count_sql")

# A count comparison against a LIVE database has one honest caveat and it is
# worth a sentence rather than a footnote: the pipeline writes nightly, so a
# verify that overlaps an ingest run compares a dump against a table that has
# moved since. jobs-backup-verify.timer is scheduled well clear of
# jobs-ingest.timer for that reason. If this ever reports a mismatch of a
# handful of rows in `jobs` alone, check the clock before believing it.
if [ "$live" != "$restored" ]; then
  echo "MISMATCH between $DB and the restored copy:" >&2
  diff <(echo "$live") <(echo "$restored") >&2 || true
  exit 1
fi

echo "ok: $(echo "$live" | wc -l) tables match"
echo "$live" | sed 's/^/  /'
