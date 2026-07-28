#!/usr/bin/env python3
"""
Add job_facts.extraction_passes / .vote_unanimity, and label the rows that
predate them.

WHY A MIGRATION IS NEEDED AT ALL
    ensure_schema() adds both columns on the next run of any script, so the
    DDL half of this is belt and braces -- runnable on demand, before a
    deploy, without waiting for the nightly pipeline to be the thing that
    alters a table. What ensure_schema cannot do is the backfill, and the
    backfill is the point.

    extract.py only writes these columns when it writes a row. job_facts
    rows are not rewritten unless FACTS_VERSION moves, so the 5,328 rows
    extracted before this change would keep extraction_passes NULL
    indefinitely -- and "NULL" would then mean two different things at once:
    "extracted before the column existed" and "extracted after it existed,
    but nothing filled it", which is a bug. Setting them to 1 removes the
    ambiguity, and it is a FACT rather than a guess: every one of those rows
    was produced by a single LLM call, because until this change the script
    could not make a second one.

WHAT IT DELIBERATELY DOES NOT DO
    vote_unanimity is left NULL for those rows and is never backfilled.
    There was one pass, so there is no agreement to report; writing 1.0
    would claim a unanimous vote that never happened and would make the
    unmeasured rows indistinguishable from genuinely unanimous three-pass
    ones in exactly the query the column exists to answer. NULL is the
    honest value and extract.py writes NULL for a single pass too.

    It also does not re-extract anything. Giving hn_whoishiring's existing
    rows their three passes is task 12's FACTS_VERSION bump, not this.

USAGE
    python3 migrations/migrate_extraction_passes.py            # report only
    python3 migrations/migrate_extraction_passes.py --apply

IDEMPOTENT: the column add checks the catalog first (see
lib/dbconn.add_missing_columns -- a bare ADD COLUMN IF NOT EXISTS still takes
an ACCESS EXCLUSIVE lock every run), and the backfill only touches rows where
extraction_passes IS NULL, so re-running finds nothing.
"""

import argparse
import os
import sys

# migrations/ sits one level below the pipeline modules it imports (schema,
# profiles, ...). Python puts THIS file's directory on sys.path, not its
# parent, so the parent is added by hand. That same insert is what reaches
# lib/ -- there is nothing to install.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)

import schema  # noqa: E402
from lib import dbconn, envfile  # noqa: E402

# Establishes its own environment, following migrate_company_ats.py rather
# than the older migrations that assume a shell which already sourced .env.
# Already-exported values still win -- see envfile.load().
envfile.load(os.path.join(_REPO_ROOT, ".env"))

NEW_COLUMNS = [("extraction_passes", "INTEGER"), ("vote_unanimity", "REAL")]


def main():
    p = argparse.ArgumentParser(
        description="Add and backfill job_facts.extraction_passes "
                    "(read-only by default).")
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()

    conn = dbconn.connect_or_exit("migrate-extraction-passes",
                                  schema=schema.SCHEMA)

    present = dbconn.existing_columns(conn, schema.FACTS_TABLE)
    missing = [c for c, _ in NEW_COLUMNS if c not in present]
    print(f"migrate-extraction-passes: columns missing: "
          f"{missing if missing else 'none'}")

    if not args.apply:
        # Cannot count what does not exist yet, and saying so is better than
        # printing a zero that reads like "nothing to backfill".
        if missing:
            total = conn.execute(
                f"SELECT count(*) FROM {schema.FACTS_TABLE}").fetchone()[0]
            print(f"  {total} existing row(s) would be labelled "
                  f"extraction_passes=1 once the column exists.")
        else:
            pending = conn.execute(
                f"SELECT count(*) FROM {schema.FACTS_TABLE} "
                f"WHERE extraction_passes IS NULL").fetchone()[0]
            print(f"  {pending} row(s) would be labelled extraction_passes=1.")
        print("\nDRY RUN -- nothing written. Re-run with --apply.")
        conn.close()
        return

    added = dbconn.add_missing_columns(conn, schema.FACTS_TABLE, NEW_COLUMNS)
    print(f"  added: {added if added else 'nothing (already present)'}")

    updated = conn.execute(
        f"UPDATE {schema.FACTS_TABLE} SET extraction_passes = 1 "
        f"WHERE extraction_passes IS NULL").rowcount
    conn.commit()
    conn.close()

    print(f"migrate-extraction-passes: labelled {updated} pre-existing row(s) "
          f"extraction_passes=1; vote_unanimity left NULL on purpose (one "
          f"pass has no agreement to report).")


if __name__ == "__main__":
    main()
