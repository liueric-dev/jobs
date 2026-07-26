#!/usr/bin/env python3
"""
One-time migration: the `jobs` table's scoring columns -> the job_scores table.

Scores used to be eight columns on `jobs`. They are one persona's opinion of
a posting, not a property of it, so they now live in job_scores keyed
(job_id, profile). See SCORES ARE PER PROFILE in schema.py.

WHY THIS IS A SCRIPT AND NOT PART OF ensure_schema()
    Creating job_scores is additive and safe to repeat, so ensure_schema()
    does it on every run. Dropping the old columns is neither. A DROP COLUMN
    that runs automatically on every invocation is one bad ordering away from
    deleting data a half-migrated deployment still needs -- so the destructive
    half is opt-in, explicit, and separate.

USAGE
    python3 migrate_scores.py                    # dry run: report, change nothing
    python3 migrate_scores.py --apply            # copy rows into job_scores
    python3 migrate_scores.py --apply --drop-columns   # ...and drop the old columns

    --profile NAME   which profile the existing scores belong to
                     (default: whatever config/persona.json names, since that
                     is the persona that produced them)

Copying is idempotent -- ON CONFLICT DO NOTHING, so re-running never
double-writes and never overwrites a score written since. --drop-columns
refuses to run unless every scored row has already been copied.
"""

import os
import sys
import json
import argparse

import schema  # schema.py
from pipelib import dbconn


def default_profile():
    """The profile the legacy scores belong to.

    They were produced by whatever persona config/persona.json currently
    describes, so that is where they go -- migrating them anywhere else would
    leave score.py unable to see them and re-score every row from scratch.
    Falls back to schema.resolve_profile() if the file is unreadable.
    """
    persona_file = os.environ.get(
        "JOB_SCORING_PERSONA_FILE",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "config/persona.json"),
    )
    try:
        with open(persona_file) as f:
            return schema.resolve_profile(json.load(f))
    except (OSError, json.JSONDecodeError):
        return schema.resolve_profile()


def legacy_columns_present(conn):
    """Which of the eight old columns still exist. Empty once dropped."""
    present = dbconn.existing_columns(conn, schema.TABLE)
    return [c for c in schema.LEGACY_SCORING_COLUMNS if c in present]


def count_legacy_scored(conn):
    return conn.execute(
        f"SELECT count(*) FROM {schema.TABLE} WHERE scored_at IS NOT NULL"
    ).fetchone()[0]


def copy_scores(conn, profile):
    """Copy every legacy-scored row into job_scores for `profile`.

    ON CONFLICT DO NOTHING rather than DO UPDATE: if a row already has a
    score for this profile it was written by the new code path, which is
    necessarily newer than the column data being migrated. Clobbering it with
    the old value would be a regression, not a migration.
    """
    cur = conn.execute(
        f"""
        INSERT INTO {schema.SCORES_TABLE}
            (job_id, profile, fit_score, primary_track, gap_friendly_signal,
             key_technologies, gap_bridging_angle, risk_factors,
             scored_at, scoring_model)
        SELECT id, %s, fit_score, primary_track, gap_friendly_signal,
               key_technologies, gap_bridging_angle, risk_factors,
               scored_at, scoring_model
        FROM {schema.TABLE}
        WHERE scored_at IS NOT NULL
        ON CONFLICT (job_id, profile) DO NOTHING
        """,
        (profile,),
    )
    conn.commit()
    return cur.rowcount


def unmigrated_count(conn, profile):
    """Legacy-scored rows with no job_scores row for this profile."""
    return conn.execute(
        f"""
        SELECT count(*) FROM {schema.TABLE} j
        WHERE j.scored_at IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM {schema.SCORES_TABLE} s
                          WHERE s.job_id = j.id AND s.profile = %s)
        """,
        (profile,),
    ).fetchone()[0]


def drop_legacy_columns(conn, columns):
    """One ALTER, not eight -- a single ACCESS EXCLUSIVE lock rather than a
    queue of them, each of which would block every reader behind it."""
    drops = ", ".join(f"DROP COLUMN IF EXISTS {c}" for c in columns)
    conn.execute(f"ALTER TABLE {schema.TABLE} {drops}")
    conn.commit()


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--apply", action="store_true",
                   help="actually copy rows (default is a dry run)")
    p.add_argument("--drop-columns", action="store_true",
                   help="after copying, drop the eight legacy columns")
    p.add_argument("--profile", default=None,
                   help="profile name for the existing scores")
    args = p.parse_args()

    conn = dbconn.connect_or_exit("migrate-scores", schema=schema.SCHEMA)
    schema.ensure_schema(conn)

    profile = args.profile or default_profile()
    legacy = legacy_columns_present(conn)

    if not legacy:
        already = conn.execute(
            f"SELECT count(*) FROM {schema.SCORES_TABLE} WHERE profile = %s",
            (profile,),
        ).fetchone()[0]
        print(f"migrate-scores: nothing to do -- the legacy columns are already "
              f"gone; job_scores holds {already} row(s) for profile {profile!r}.")
        conn.close()
        return

    scored = count_legacy_scored(conn)
    print(f"migrate-scores: profile={profile!r}")
    print(f"  legacy columns present : {len(legacy)}/8 ({', '.join(legacy)})")
    print(f"  rows with scored_at set: {scored}")

    if not args.apply:
        pending = unmigrated_count(conn, profile)
        print(f"  would copy              : {pending}")
        print("\ndry run -- nothing changed. Re-run with --apply.")
        conn.close()
        return

    copied = copy_scores(conn, profile)
    remaining = unmigrated_count(conn, profile)
    total = conn.execute(
        f"SELECT count(*) FROM {schema.SCORES_TABLE} WHERE profile = %s",
        (profile,),
    ).fetchone()[0]
    print(f"  copied                  : {copied}")
    print(f"  job_scores total        : {total} for profile {profile!r}")

    if args.drop_columns:
        # Refuse rather than warn. The columns are the only remaining copy of
        # this data; dropping them with rows still unmigrated is unrecoverable.
        if remaining:
            print(f"\nREFUSING to drop columns: {remaining} scored row(s) are not "
                  f"in job_scores for profile {profile!r}.")
            conn.close()
            sys.exit(1)
        drop_legacy_columns(conn, legacy)
        print(f"  dropped columns         : {', '.join(legacy)}")

    conn.close()


if __name__ == "__main__":
    main()
