#!/usr/bin/env python3
"""Track which of this directory's ten migrations have been applied.

WHY THIS EXISTS
    `backend/migrations/` holds ten scripts and nothing records which have
    been run. On any box but the one an operator remembers running them on,
    the only way to know is to inspect the schema and infer -- read the
    columns a script would add, guess from row counts whether a backfill
    happened, and hope nothing was half-applied. This is a `schema_migrations`
    table plus a thin CLI over it, stdlib only. No Alembic: a table and a
    loop solve a problem this small, and CLAUDE.md's runtime-dependency bound
    applies to `migrations/` the same as everywhere else.

WHAT "APPLIED" MEANS HERE, AND WHAT IT DOES NOT
    This table records what THIS RUNNER has done, not what is independently
    true of the database. The two are not the same thing on this box: nine of
    the ten scripts predate this runner and several were run by hand months
    apart, so the table starts empty regardless of what has actually
    happened. `--mark-applied NAME --note "..."` exists to bootstrap that
    history deliberately -- one recorded, checkable claim at a time -- rather
    than have the runner guess by parsing each script's own report text,
    which would be a second, drifting copy of logic ten scripts already have
    (the same reasoning CLAUDE.md gives for not reimplementing relevance
    matching in Python: one implementation, many callers).

WHY `--apply NAME` NAMES EXACTLY ONE MIGRATION, AND THERE IS NO `--apply-all`
    Half of these scripts document a real, non-destructive-but-not-nothing
    effect on a second run: `migrate_profiles.py --apply` refreshes a live
    profile's criteria/persona from whatever the config files currently say,
    `migrate_pursuit_profile.py --apply` without `--active` deactivates an
    active profile, `migrate_company_ats.py --apply` inserts from whatever
    `--seed-file` currently points at. None of that is a bug in those
    scripts -- it is the operator decision each one's own docstring calls
    out. A blanket `--apply-all` would make that decision on an operator's
    behalf the moment a session ran this file with a shrug. Naming one
    migration keeps the decision exactly as explicit as running the
    underlying script directly always was.

WHAT RUNNING THE SAME `--apply NAME` TWICE DOES
    The first call invokes `python3 migrations/<NAME>.py --apply` as a
    subprocess and, only on exit 0, records a row here. The second call
    finds that row and returns without invoking the script at all -- not
    "invokes it again and trusts it to be idempotent", which is a second,
    independent contract the ten scripts already document but that this
    runner does not need to lean on twice.

USAGE
    python3 migrations/runner.py                          # --status, the default
    python3 migrations/runner.py --status
    python3 migrations/runner.py --apply migrate_extraction_passes
    python3 migrations/runner.py --mark-applied migrate_google_ids \\
        --note "T-20, 2026-08-03: verified count(*) = count(DISTINCT source_id) = 1320"
"""

import argparse
import os
import subprocess
import sys

# migrations/ sits one level below the pipeline modules it imports (schema,
# lib/...). Python puts THIS file's directory on sys.path, not its parent, so
# the parent is added by hand -- same as every other script in this directory.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)

import schema  # noqa: E402
from lib import dbconn, envfile  # noqa: E402

envfile.load(os.path.join(_REPO_ROOT, ".env"))

MIGRATIONS_TABLE = "schema_migrations"

#: The ten scripts in this directory, registered by name so this file can be
#: read as the list. Order is `ls migrations/*.py` order -- there is no
#: dependency between them to encode; each connects and checks its own
#: preconditions independently.
REGISTRY = [
    ("migrate_ats_descriptions",
     "Rewrite ATS description_text from raw_json, using the fixed extraction."),
    ("migrate_company_ats",
     "Create ats_seed and company_ats, and load the NYC employer seed list."),
    ("migrate_description_rehash",
     "Rewrite ATS description_text from raw_json after lib/text._TAG was fixed."),
    ("migrate_extraction_passes",
     "Add job_facts.extraction_passes / .vote_unanimity, and label the rows "
     "that predate them."),
    ("migrate_google_ids",
     "One-time migration: re-key google_jobs rows onto a stable posting identity."),
    ("migrate_posted_at_ts",
     "Populate jobs.posted_at_ts for rows that predate the column."),
    ("migrate_profiles",
     "Seed jobs.profiles from the config files that used to be the source of truth."),
    ("migrate_pursuit_profile",
     "Create the pursuit profile: the Pursuit AI-Native cohort's relevance "
     "gate, INACTIVE."),
    ("migrate_scores",
     "One-time migration: the jobs table's scoring columns -> the job_scores table."),
    ("migrate_score_versions",
     "Add job_scores' four version columns, and count -- without touching -- "
     "the rows that predate them."),
]
NAMES = {name for name, _ in REGISTRY}


def ensure_migrations_table(conn):
    """CREATE TABLE IF NOT EXISTS. Unlike lib/dbconn.add_missing_columns's ADD
    COLUMN, a CREATE TABLE IF NOT EXISTS that finds the table already there
    takes no lock worth checking the catalog first to avoid."""
    conn.execute(
        f"CREATE TABLE IF NOT EXISTS {MIGRATIONS_TABLE} ("
        f"    name TEXT PRIMARY KEY,"
        f"    applied_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
        f"    note TEXT NOT NULL"
        f")")
    conn.commit()


def applied(conn):
    """{name: (applied_at, note)} for every row this table has recorded."""
    rows = conn.execute(
        f"SELECT name, applied_at, note FROM {MIGRATIONS_TABLE}").fetchall()
    return {row[0]: (row[1], row[2]) for row in rows}


def record(conn, name, note):
    """Record NAME as applied now, with NOTE as the evidence.

    ON CONFLICT overwrites rather than refuses: --mark-applied is meant to be
    correctable, and apply_one()'s own call only ever reaches a fresh name
    (it checks `applied()` first), so the overwrite path is for a human
    fixing an earlier note, not for silently losing history.
    """
    conn.execute(
        f"INSERT INTO {MIGRATIONS_TABLE} (name, note) VALUES (%s, %s) "
        f"ON CONFLICT (name) DO UPDATE SET applied_at = now(), note = EXCLUDED.note",
        (name, note))
    conn.commit()


def status_lines(conn):
    """One line per registered migration, applied or not, in REGISTRY order."""
    state = applied(conn)
    lines = []
    for name, desc in REGISTRY:
        if name in state:
            applied_at, note = state[name]
            lines.append(f"  [applied {applied_at:%Y-%m-%d %H:%M}] {name} -- {note}")
        else:
            lines.append(f"  [NOT APPLIED       ] {name} -- {desc}")
    return lines


def apply_one(conn, name, note="applied via runner.py"):
    """Invoke `<name>.py --apply` once, then record it -- or, if NAME is
    already recorded, do neither. Returns whether NAME ends this call
    recorded as applied.
    """
    state = applied(conn)
    if name in state:
        applied_at, existing_note = state[name]
        print(f"runner: {name} already recorded applied at "
              f"{applied_at:%Y-%m-%d %H:%M} ({existing_note}) -- "
              f"not re-invoked.")
        return True

    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{name}.py")
    print(f"runner: invoking python3 {os.path.relpath(script, _REPO_ROOT)} --apply")
    result = subprocess.run([sys.executable, script, "--apply"], cwd=_REPO_ROOT)
    if result.returncode != 0:
        print(f"runner: {name} exited {result.returncode} -- NOT recorded as applied.")
        return False

    record(conn, name, note)
    print(f"runner: recorded {name} as applied.")
    return True


def main():
    p = argparse.ArgumentParser(
        description="Report or record which of the ten migrations/ scripts "
                    "have been applied (read-only by default).")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--status", action="store_true",
                   help="report each registered migration as applied or not "
                        "(the default action)")
    g.add_argument("--apply", metavar="NAME",
                   help="invoke NAME's own --apply once and record it. A "
                        "no-op -- NAME's script is not re-invoked -- if NAME "
                        "is already recorded as applied.")
    g.add_argument("--mark-applied", metavar="NAME",
                   help="record NAME as applied without running it, for a "
                        "migration already applied by hand before this "
                        "runner existed. Requires --note.")
    p.add_argument("--note", default=None,
                   help="required with --mark-applied: the evidence that "
                        "NAME is already applied")
    args = p.parse_args()

    conn = dbconn.connect_or_exit("migrations-runner", schema=schema.SCHEMA)
    ensure_migrations_table(conn)

    if args.apply:
        if args.apply not in NAMES:
            print(f"migrations-runner: {args.apply!r} is not one of the "
                  f"{len(REGISTRY)} registered migrations -- see --status "
                  f"for the list.")
            conn.close()
            sys.exit(1)
        ok = apply_one(conn, args.apply)
        conn.close()
        sys.exit(0 if ok else 1)

    if args.mark_applied:
        if args.mark_applied not in NAMES:
            print(f"migrations-runner: {args.mark_applied!r} is not one of "
                  f"the {len(REGISTRY)} registered migrations -- see "
                  f"--status for the list.")
            conn.close()
            sys.exit(1)
        if not args.note:
            print("migrations-runner: --mark-applied requires --note "
                  "(the evidence this was already applied).")
            conn.close()
            sys.exit(1)
        record(conn, args.mark_applied, args.note)
        print(f"migrations-runner: recorded {args.mark_applied} as applied.")
        conn.close()
        return

    print("migrations-runner:")
    for line in status_lines(conn):
        print(line)
    n_applied = len(applied(conn))
    print(f"\n  {n_applied}/{len(REGISTRY)} applied.")
    conn.close()


if __name__ == "__main__":
    main()
