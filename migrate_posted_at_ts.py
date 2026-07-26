#!/usr/bin/env python3
"""
Populate jobs.posted_at_ts for rows that predate the column.

WHY A MIGRATION IS NEEDED AT ALL
    A new column does not fill itself on the next ingest. upsert() only writes
    columns when a row's content_hash changes; an unchanged row takes the
    touch_sql path, which bumps last_seen and nothing else. Since posted_at_ts
    is deliberately NOT part of any hash, an untouched posting would keep a
    NULL date indefinitely -- and "sort by newest" would silently order the
    entire back catalogue last.

WHAT IT DERIVES FROM
    Six of the seven sources already store an ISO timestamp in posted_at, so
    those are a straight cast. Two need more:

      builtin      posted_at is relative English ("Reposted 8 Hours Ago",
                   "Yesterday"), handled by text.posted_at_timestamp. Note this
                   resolves the phrase against NOW, so a backfill dates a
                   posting relative to when the migration runs, not when it was
                   scraped -- accurate to within one ingest cycle, which is the
                   best available from a relative string and better than NULL.
      greenhouse   posted_at holds updated_at (an edit timestamp), so this
                   prefers first_published out of raw_json. That is the
                   difference between "posted in February" and "looks posted
                   today because someone fixed a typo".

USAGE
    python3 migrate_posted_at_ts.py            # report, change nothing
    python3 migrate_posted_at_ts.py --apply
    python3 migrate_posted_at_ts.py --apply --all   # also recompute non-NULL

IDEMPOTENT: without --all it only touches rows where posted_at_ts IS NULL, so
re-running finds nothing.
"""

import argparse
import collections
import json
import os
import sys

import schema
from pipelib import dbconn, text

BATCH = 1000


def derive(platform, posted_at, raw_json):
    """The posted_at_ts value for one row, or None if nothing is knowable."""
    if platform == "greenhouse" and raw_json:
        try:
            first = json.loads(raw_json).get("first_published")
        except ValueError:
            first = None
        if first:
            return text.posted_at_timestamp(first)
    return text.posted_at_timestamp(posted_at)


def main():
    p = argparse.ArgumentParser(
        description="Fill jobs.posted_at_ts (read-only by default).")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--all", action="store_true",
                   help="recompute rows that already have a value")
    args = p.parse_args()

    conn = dbconn.connect_or_exit("migrate-posted-at-ts", schema=schema.SCHEMA)
    schema.ensure_schema(conn)

    where = "" if args.all else "WHERE posted_at_ts IS NULL"
    rows = conn.execute(
        f"SELECT id, platform, posted_at, raw_json FROM {schema.TABLE} {where}"
    ).fetchall()

    resolved, unresolved = [], collections.Counter()
    for job_id, platform, posted_at, raw_json in rows:
        ts = derive(platform, posted_at, raw_json)
        if ts:
            resolved.append((job_id, ts))
        else:
            unresolved[platform] += 1

    print(f"migrate-posted-at-ts: {len(rows)} candidate rows")
    print(f"  resolvable   : {len(resolved)}")
    print(f"  unresolvable : {sum(unresolved.values())}"
          + (f"  {dict(unresolved)}" if unresolved else ""))
    if unresolved:
        print("  (unresolvable means the source itself gave no date -- most of "
              "these are Google postings with no posted_at at all.)")

    if not args.apply:
        print(f"\nDRY RUN -- nothing written. Re-run with --apply to set "
              f"{len(resolved)} rows.")
        conn.close()
        return

    for i in range(0, len(resolved), BATCH):
        chunk = resolved[i:i + BATCH]
        conn.execute(
            f"UPDATE {schema.TABLE} AS j SET posted_at_ts = v.ts::timestamptz "
            f"FROM (SELECT unnest(%(ids)s::text[]) AS id, "
            f"             unnest(%(tss)s::text[]) AS ts) AS v "
            f"WHERE j.id = v.id",
            {"ids": [c[0] for c in chunk], "tss": [c[1] for c in chunk]})
        conn.commit()
        print(f"  committed {min(i + BATCH, len(resolved))}/{len(resolved)}")

    conn.close()
    print(f"migrate-posted-at-ts: set {len(resolved)} rows.")


if __name__ == "__main__":
    main()
