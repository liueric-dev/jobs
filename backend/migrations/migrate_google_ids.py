#!/usr/bin/env python3
"""
One-time migration: re-key google_jobs rows onto a stable posting identity.

THE BUG THIS REPAIRS
    `source_id` for google_jobs rows was Google's `job_id` verbatim. That
    looks like a posting identifier and is not one -- it is a base64 JSON blob
    carrying the search context that produced it, including an `fc` token that
    rotates on every *fresh* fetch from Google and `hl`/`gl` keys that are
    present or absent depending on the call. schema.make_job_id() hashes it,
    so every fetch of an already-stored posting minted a brand-new primary key.

    Measured before the fix: 837 google_jobs rows holding 632 distinct
    postings -- 32% inflation, one 15Five listing stored four times.

    It stayed invisible because SerpApi caches responses for 1h and serves
    them free: repeat runs inside that window replayed a byte-identical
    payload, reported "0 new", and looked correct. The first run past cache
    expiry reported 10 new / 10 fetched for the same query. So
    google_jobs_query_stats.new_count was measuring cache expiry, not job
    novelty -- see the note on truncation below.

    lib/ids.py:google_source_id() is the fix; this script repairs the rows
    written before it existed.

WHY A SCRIPT AND NOT ensure_schema()
    Same reasoning as migrate_scores.py: merging rows and repointing foreign
    keys is destructive and must be explicit, opt-in, and separately reviewed.
    Dry run is the default.

USAGE
    python3 migrations/migrate_google_ids.py            # report only, change nothing
    python3 migrations/migrate_google_ids.py --apply    # merge
    python3 migrations/migrate_google_ids.py --apply --keep-stats   # don't truncate stats

    Back up first -- note this must dump the `jobs` database, NOT nyc_events.
    Since slice E of the reorg the jobs tables live in their own database; a
    dump of nyc_events would back up the events data and none of what this
    script rewrites:
      docker exec pg-main pg_dump -U jobs_pipeline -d jobs \\
        | gzip > ~/backups/pre-googleid-$(date +%Y%m%d).sql.gz

MERGE RULES (per group of rows collapsing to one new id)
    survivor      the most recently seen row -- its content columns are the
                  freshest view of the posting
    first_seen    MIN across the group; the posting really was first observed
                  then, and losing that would reset its apparent age
    last_seen     MAX across the group
    status        'open' if ANY row in the group is open. close_stale() closes
                  on last_seen age, and duplicates made rows look stale that
                  were being re-fetched the whole time under new keys.
    job_scores    repointed to the survivor. PK is (job_id, profile), so two
                  merged rows scored under the same profile collide -- the
                  HIGHEST fit_score wins. Scores are expensive LLM calls and
                  identical for duplicates of one posting, so this is a
                  tie-break, not a judgement.

IDEMPOTENT: re-running finds no group with >1 row and reports nothing to do.
"""

import argparse
import os
import sys
from collections import defaultdict

# migrations/ sits one level below the pipeline modules it imports (schema,
# profiles, ...). Python puts THIS file's directory on sys.path, not its
# parent, so the parent is added by hand. That same insert is what reaches
# lib/ -- there is nothing to install.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import schema  # noqa: E402  (schema.py)
from lib import dbconn, ids  # noqa: E402

PLATFORM = "google_jobs"


def load_rows(conn):
    """Every google_jobs row, with what google_source_id() needs to re-key it.

    raw_json is deliberately NOT read: it is up to 20KB per row and the only
    field needed from it (job_id) is already stored as source_id.
    """
    return conn.execute(
        f"""
        SELECT id, source_id, company_token, title, job_url, first_seen, last_seen, status
        FROM {schema.TABLE} WHERE platform = %s
        ORDER BY last_seen
        """,
        (PLATFORM,),
    ).fetchall()


def plan_merges(rows):
    """new_id -> list of existing rows, for groups that actually change.

    Rows already keyed correctly (a group of one whose id is unchanged) are
    excluded, so an idempotent re-run plans nothing.
    """
    groups = defaultdict(list)
    for row in rows:
        old_id, source_id, token, title, url, first_seen, last_seen, status = row
        job = {
            "job_id": source_id,
            "title": title,
            "apply_options": [{"link": url}] if url else [],
        }
        new_source_id = ids.google_source_id(job, token)
        new_id = ids.make_id(PLATFORM, token, new_source_id)
        groups[(new_id, new_source_id)].append(row)

    return {k: v for k, v in groups.items()
            if len(v) > 1 or v[0][0] != k[0]}


def scores_for(conn, job_ids):
    """(job_id, profile, fit_score) for the given rows."""
    if not job_ids:
        return []
    return conn.execute(
        f"SELECT job_id, profile, fit_score FROM {schema.SCORES_TABLE} "
        f"WHERE job_id = ANY(%s)",
        (list(job_ids),),
    ).fetchall()


def apply_merge(conn, new_id, new_source_id, group):
    """Collapse `group` onto `new_id`. One transaction per group.

    Per-group rather than one big transaction: a failure on a malformed group
    rolls back only that group, and the run reports it instead of losing every
    merge that already succeeded.
    """
    # Rows arrive ordered by last_seen ASC, so the survivor is the last one.
    survivor = group[-1]
    survivor_id = survivor[0]
    losers = [r[0] for r in group if r[0] != survivor_id]

    first_seen = min(r[5] for r in group)
    last_seen = max(r[6] for r in group)
    any_open = any(r[7] == schema.STATUS_OPEN for r in group)

    with conn.transaction():
        # 1. Move scores off the losers BEFORE deleting them -- the FK is
        #    ON DELETE CASCADE, so a delete first would silently destroy them.
        if losers:
            rows = conn.execute(
                f"SELECT job_id, profile, fit_score, primary_track, "
                f"       gap_friendly_signal, key_technologies, "
                f"       gap_bridging_angle, risk_factors, scored_at, scoring_model "
                f"FROM {schema.SCORES_TABLE} WHERE job_id = ANY(%s)",
                (losers,),
            ).fetchall()
            for r in rows:
                conn.execute(
                    f"""
                    INSERT INTO {schema.SCORES_TABLE}
                        (job_id, profile, fit_score, primary_track,
                         gap_friendly_signal, key_technologies,
                         gap_bridging_angle, risk_factors, scored_at, scoring_model)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (job_id, profile) DO UPDATE SET
                        fit_score = GREATEST(
                            {schema.SCORES_TABLE}.fit_score, EXCLUDED.fit_score)
                    """,
                    (survivor_id, r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9]),
                )
            conn.execute(f"DELETE FROM {schema.TABLE} WHERE id = ANY(%s)", (losers,))

        # 2. Re-key the survivor and fold in the group's aggregate facts.
        conn.execute(
            f"""
            UPDATE {schema.TABLE}
               SET id = %s, source_id = %s, first_seen = %s, last_seen = %s,
                   status = %s,
                   closed_at = CASE WHEN %s THEN NULL ELSE closed_at END
             WHERE id = %s
            """,
            (new_id, new_source_id, first_seen, last_seen,
             schema.STATUS_OPEN if any_open else schema.STATUS_CLOSED,
             any_open, survivor_id),
        )
    return len(losers)


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--apply", action="store_true",
                   help="actually merge (default is a dry run)")
    p.add_argument("--keep-stats", action="store_true",
                   help="do not truncate google_jobs_query_stats")
    args = p.parse_args()

    conn = dbconn.connect_or_exit("migrate-google-ids", schema=schema.SCHEMA)
    schema.ensure_schema(conn)

    rows = load_rows(conn)
    if not rows:
        print("migrate-google-ids: no google_jobs rows -- nothing to do.")
        conn.close()
        return

    plan = plan_merges(rows)
    merging = {k: v for k, v in plan.items() if len(v) > 1}
    rekey_only = {k: v for k, v in plan.items() if len(v) == 1}
    dropped = sum(len(v) - 1 for v in merging.values())

    affected = [r[0] for v in plan.values() for r in v]
    scored = scores_for(conn, affected)
    colliding = sum(
        1
        for v in merging.values()
        for prof in {s[1] for s in scored if s[0] in {r[0] for r in v}}
        if sum(1 for s in scored if s[1] == prof and s[0] in {r[0] for r in v}) > 1
    )

    print("migrate-google-ids:")
    print(f"  google_jobs rows        : {len(rows)}")
    print(f"  distinct postings after : {len(rows) - dropped}")
    print(f"  merge groups (>1 row)   : {len(merging)}  (removing {dropped} rows)")
    print(f"  re-key only (1 row)     : {len(rekey_only)}")
    print(f"  scores on affected rows : {len(scored)}"
          f"  ({colliding} profile collision(s) resolved by highest fit_score)")

    if not plan:
        print("\nnothing to do -- every row is already keyed on a stable id.")
        conn.close()
        return

    if not args.apply:
        print("\ndry run -- nothing changed. Re-run with --apply.")
        print("Back up first: docker exec pg-main pg_dump -U jobs_pipeline "
              "-d jobs | gzip > ~/backups/pre-googleid-$(date +%Y%m%d).sql.gz")
        conn.close()
        return

    removed = 0
    failures = []
    for (new_id, new_source_id), group in plan.items():
        try:
            removed += apply_merge(conn, new_id, new_source_id, group)
        except Exception as e:  # noqa: BLE001 -- report and continue, see apply_merge
            failures.append(f"{new_id}: {str(e)[:160]}")
    conn.commit()

    total = conn.execute(
        f"SELECT count(*) FROM {schema.TABLE} WHERE platform = %s", (PLATFORM,)
    ).fetchone()[0]
    distinct = conn.execute(
        f"SELECT count(DISTINCT source_id) FROM {schema.TABLE} WHERE platform = %s",
        (PLATFORM,),
    ).fetchone()[0]

    print(f"\n  rows removed            : {removed}")
    print(f"  google_jobs rows now    : {total}  (distinct source_id: {distinct})")
    if total != distinct:
        print(f"  WARNING: {total - distinct} row(s) still share a source_id.")
    if failures:
        print(f"  FAILED groups           : {len(failures)}")
        for f in failures[:5]:
            print(f"    {f}")

    if not args.keep_stats:
        # Not data loss: every new_count in this table was computed from the
        # broken key, so it recorded "did SerpApi's 1h cache expire between
        # these two runs", not "how many new postings did this query find".
        # The adaptive-cadence feature it was collected for would have been
        # fitting noise. job_sources replaces it with per-posting provenance.
        n = conn.execute("SELECT count(*) FROM google_jobs_query_stats").fetchone()[0]
        conn.execute("TRUNCATE google_jobs_query_stats")
        conn.commit()
        print(f"  query stats truncated   : {n} row(s) "
              f"(measured cache expiry, not novelty -- see docstring)")

    conn.close()
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
