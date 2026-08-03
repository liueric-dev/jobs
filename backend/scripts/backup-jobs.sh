#!/usr/bin/env bash
# Dump the `jobs` database, verifiably.
#
# THE CORPUS IS THE ASSET. Every row carries an LLM extraction that cost a real
# call to produce, and job_facts is written ONCE PER POSTING, EVER -- that is the
# property that makes cost flat in users, and it is also what makes the table
# expensive to lose. Re-extraction is possible and slow; a posting whose source
# has since delisted it is not re-extractable at all, because the description
# text is gone from the internet. Task 12's snapshot discipline is worthless if
# the whole database sits on one disk.
#
# Shell rather than a Python entry point, deliberately, and the reason is the
# same one backup-garmin.sh gives: this runs `docker exec` and touches no
# application code, so it keeps working while the Python side is broken
# mid-edit -- which is exactly when a restore is most likely to be needed.
# Making the backup depend on the thing it exists to recover from is a circular
# dependency with a very bad failure mode. It also means the backup does not
# need psycopg, a venv, or DATABASE_URL to be parseable.
#
# There is no pg_dump on this host; everything goes through the container, which
# is `nyc-events-postgres` and holds several unrelated databases. See
# ~/apps/infra/DATABASE.md.
set -euo pipefail

DB=${JOBS_BACKUP_DB:-jobs}
CONTAINER=${JOBS_BACKUP_CONTAINER:-nyc-events-postgres}
DEST=${JOBS_BACKUP_DIR:-$HOME/backups/jobs}
KEEP_DAYS=${JOBS_BACKUP_KEEP_DAYS:-14}

# -U nyc_events, the cluster owner, not jobs_pipeline and emphatically not
# jobs_api. Two reasons. The restore rehearsal needs CREATEDB, which the
# application roles deliberately do not have; and a dump taken as a restricted
# role silently omits every object that role cannot read, producing a file that
# looks like a backup and restores a subset. jobs_api can see six tables out of
# the fifteen-ish in this database -- a dump taken as jobs_api would be a
# catastrophe that reported success.
PGUSER=${JOBS_BACKUP_USER:-nyc_events}

stamp=$(date +%Y%m%d-%H%M%S)
mkdir -p "$DEST"

dump="$DEST/$DB-$stamp.dump"
roles="$DEST/roles-$stamp.sql"

# The redirection creates .tmp before pg_dump runs, so a failed dump exits under
# `set -e` leaving a zero-byte orphan. Found in the neighbouring project by a
# deliberate failure test rather than by reading the code. The atomic-rename
# design still holds -- no partial file is ever visible as a real dump -- but
# orphans accumulate, and one named for a database the prune globs do not match
# is invisible forever.
trap 'rm -f "$dump.tmp" "$roles.tmp"' EXIT

# Custom format (-Fc): already compressed, and it is what lets
# verify-jobs-backup.sh run `pg_restore -l` to read the catalogue without
# restoring the whole thing first -- a cheap check that the file is a dump
# rather than a truncated blob.
#
# Written to .tmp and moved into place only on success. A dump killed halfway --
# OOM, a reboot, a full disk -- must never sit in the directory looking exactly
# like a good one. `mv` within one filesystem is atomic, so the visible file is
# always complete.
echo "backing up $DB -> $dump"
docker exec "$CONTAINER" pg_dump -U "$PGUSER" -d "$DB" -Fc >"$dump.tmp"
mv "$dump.tmp" "$dump"

# Roles live in the CLUSTER, not in a per-database dump, so a restore onto a
# fresh cluster fails on missing jobs_pipeline and jobs_api without this. It
# matters more here than in most projects: backend/api/README.md's privilege
# table is a security boundary, not a convenience, and restoring the data
# without the roles would mean recreating those grants from memory under
# pressure -- which is how a service comes back as a superuser.
docker exec "$CONTAINER" pg_dumpall -U "$PGUSER" --roles-only >"$roles.tmp"
mv "$roles.tmp" "$roles"

# Checksums, so bitrot and truncation are detectable rather than assumed absent.
# /home is btrfs and checksums data blocks itself, so this is belt-and-braces
# for the integrity half -- what it really buys is a way to verify a copy made
# somewhere that is not btrfs, which is the whole point of the off-machine step
# below.
( cd "$DEST" && sha256sum "$(basename "$dump")" "$(basename "$roles")" \
    >"$(basename "$dump").sha256" )

# -- OFF THE MACHINE ---------------------------------------------------------
#
# THIS IS THE HALF THAT MAKES IT A BACKUP RATHER THAN A COPY. A dump sitting on
# the same disk as the database survives `DROP TABLE` and survives nothing else
# -- not a failed disk, not a stolen laptop, not a house fire. The task is
# explicit: "pg_dump nightly, OFF THE MACHINE".
#
# UNCONFIGURED BY DEFAULT, AND THAT IS DELIBERATE. There is no destination this
# repo can pick for you: it needs an account, a bucket or a host key, and
# credentials that must not live in git. Set JOBS_BACKUP_REMOTE to an
# rclone/rsync destination and this block runs; leave it unset and the script
# says loudly, on every run, that the backup is still on one disk. It does NOT
# fail -- a local dump is better than no dump -- but it must never be silent,
# because "backups are running" is exactly the belief this project cannot
# afford to hold without evidence.
if [ -n "${JOBS_BACKUP_REMOTE:-}" ]; then
  echo "copying to $JOBS_BACKUP_REMOTE"
  case "$JOBS_BACKUP_REMOTE" in
    *:*/*|*:*)
      # rclone remote (`remote:path`) -- covers Backblaze B2, S3, Drive and the
      # rest without this script knowing which.
      rclone copy "$dump" "$JOBS_BACKUP_REMOTE" --checksum
      rclone copy "$dump.sha256" "$JOBS_BACKUP_REMOTE" --checksum
      rclone copy "$roles" "$JOBS_BACKUP_REMOTE" --checksum
      ;;
    *)
      # A local path: another disk, or an already-mounted share.
      mkdir -p "$JOBS_BACKUP_REMOTE"
      cp -f "$dump" "$dump.sha256" "$roles" "$JOBS_BACKUP_REMOTE/"
      ;;
  esac
  echo "off-machine copy ok"
else
  echo "WARNING: JOBS_BACKUP_REMOTE is unset -- this dump is on the same disk" \
       "as the database it came from, and protects against DROP TABLE and" \
       "nothing else. See 'Where the backups are' in:" \
       "git show refactor-freeze-2026-08-02:docs/RUNBOOK.md" >&2
fi

# Prune. -mtime is applied to the dumps and their sidecars by globs that move
# together, so a pruned dump never leaves an orphaned .sha256 behind claiming to
# describe a file that is gone. The remote copy is NOT pruned from here:
# retention on the far end is the remote's policy, and a bug in this script must
# not be able to delete the only off-machine copy.
find "$DEST" -maxdepth 1 -name "$DB-*.dump*" -mtime "+$KEEP_DAYS" -delete
find "$DEST" -maxdepth 1 -name 'roles-*.sql' -mtime "+$KEEP_DAYS" -delete

echo "ok: $(du -h "$dump" | cut -f1) $dump"
