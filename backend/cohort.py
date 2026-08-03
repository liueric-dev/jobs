#!/usr/bin/env python3
"""
"Four Builders saved this", without ever revealing which four.

WHAT THIS COMPUTES
    One row in cohort_signal per posting that at least COHORT_MIN_SAVERS
    distinct Builders CURRENTLY have saved, carrying a bucket ('3-5', '6-10',
    '10+') and nothing else. Postings below the threshold get no row at all --
    see schema.py's DDL comment for why absence rather than a NULL bucket is
    the privacy-correct representation.

    It runs on the nightly cycle (run-daily.py) rather than at read time.
    tranche_five/28-cohort-aggregation.md: live computation invites a timing
    side channel, and timing is the strongest deanonymiser available in a room
    where thirty people can see each other.

WHY job_events AND NOT builder_job_state
    builder_job_state carries saved_at per Builder and is the obvious source.
    It is declared in webapp/schema_web.py, on the surfacing service's side of
    the ownership line -- the three processes share only schema.py and lib/,
    and none imports another. This compute belongs to the pipeline, so it reads
    the pipeline's table. The two agree by construction anyway: webapp/jobs.py
    writes the event and the state row in one transaction.

THE CURRENT ANSWER IS A FOLD OVER THE LOG, NOT A FILTER ON IT
    This is the part that is easy to get wrong and silently wrong when it is.
    `save` and `unsave` are BOTH events (webapp/jobs.py _STATE_WRITES) and
    job_events is append-only, so somebody who saved a posting in July and
    unsaved it in August still has a `save` row today, forever. A
    COUNT(DISTINCT app_user_id) over event='save' therefore counts retracted
    saves, which pushes postings OVER the threshold -- the suppression failing
    open. What is wanted is the LATEST of {save, unsave} per (Builder, job),
    and only then a count of the ones that landed on `save`.

    The tie-break is `id DESC` after `occurred_at DESC` and it is load-bearing:
    occurred_at is TEXT to the second and record_events stamps one `now` across
    a whole batch, so a save and an unsave of the same posting in one batch
    share a timestamp exactly. id is BIGSERIAL and monotonic in insertion
    order, which is the real order.

app_user_id IS NULL IS EXCLUDED, NOT COUNTED
    Rows written before the column landed carry NULL and are deliberately
    unbackfilled (schema.py). SQL would fold every one of them into a single
    group -- one phantom Builder standing for every pre-2026-08-01 saver -- and
    a phantom Builder is a whole unit of evidence toward a threshold, on the
    strength of a row that names nobody. Excluded at the source, and the
    partial index idx_job_events_user_job is on exactly this predicate.

WHAT NEVER LEAVES THIS MODULE
    No exact count, no recency, no ordering, no identity. The bucket is the
    entire output. Nothing reads cohort_signal for ranking and nothing may:
    boosting saved postings at N=30 with no position-bias correction is an
    unmitigated feedback loop, which the task file rules out explicitly.

USAGE
    python3 cohort.py                    # every active profile
    python3 cohort.py --profile pursuit  # one
    python3 cohort.py --dry-run          # report, write nothing
"""

import argparse
import sys

import schema
from lib import dbconn
from lib.timeparse import utc_now_str

#: The event vocabulary this fold reads, MIRRORED FROM webapp/jobs.py RATHER
#: THAN IMPORTED, because that module lives in the other process and imports
#: fastapi and pydantic besides. The names are duplicated on purpose and the
#: duplication is checked rather than trusted: webapp/tests/test_cohort_signal.py
#: TestVocabularyDoesNotDrift asserts these three constants equal
#: jobs.COHORT_VISIBLE_EVENTS, the `unsave` key of jobs._STATE_WRITES, and
#: jobs.VISIBILITY_COHORT. That test is on the webapp side because it is the
#: only interpreter that can import both files.
SAVE_EVENT = "save"
UNSAVE_EVENT = "unsave"
VISIBILITY_COHORT = "cohort_anon"

#: Distinct Builders whose LATEST save/unsave on a posting is a save, for
#: postings at or above the threshold. Returns (job_id, savers), job_id order.
#:
#: THE VISIBILITY PREDICATE IS ON THE POSITIVE EVENT ONLY, and that asymmetry
#: is the one thing here that the task file does not anticipate. It asks to
#: "aggregate only cohort_anon events -- enforce it in the query", and an
#: `unsave` is NOT stored cohort_anon: visibility_for() maps only `save`
#: (jobs.py COHORT_VISIBLE_EVENTS), so every unsave row is 'private'. Filtering
#: the whole fold on visibility = 'cohort_anon' would therefore delete exactly
#: the rows that make the fold a fold, and silently restore the retracted-save
#: overcount the fold exists to prevent.
#:
#: The resolution keeps the guarantee the instruction is FOR. A save may
#: contribute to a count only if it is cohort_anon; an unsave is not a
#: contribution but a retraction of the Builder's OWN save, and reading it can
#: only ever remove somebody from a count, never add one. The privacy failure
#: mode is a posting appearing that should not have; a retraction cannot cause
#: it. So the enforcement is in the outer WHERE, on the row that is actually
#: counted, where 'applied' (private, and the event the instruction is really
#: aimed at) is refused twice over -- once by the event set, once by
#: visibility. TestPrivateEventsCannotReachTheCount pins both halves,
#: including the case a convention-only implementation would pass: a `save` row
#: whose visibility says 'private' is NOT counted.
_SAVERS_SQL = f"""
    WITH latest AS (
        SELECT DISTINCT ON (e.app_user_id, e.job_id)
               e.job_id, e.app_user_id, e.event, e.visibility
          FROM {schema.EVENTS_TABLE} e
         WHERE e.profile = %s
           AND e.app_user_id IS NOT NULL
           AND e.event IN (%s, %s)
         ORDER BY e.app_user_id, e.job_id, e.occurred_at DESC, e.id DESC
    )
    SELECT job_id, COUNT(DISTINCT app_user_id) AS savers
      FROM latest
     WHERE event = %s
       AND visibility = %s
     GROUP BY job_id
    HAVING COUNT(DISTINCT app_user_id) >= %s
     ORDER BY job_id
"""  # noqa: S608 -- splices schema.EVENTS_TABLE, a module-level constant


def savers_by_job(conn, profile, min_savers=None):
    """[(job_id, distinct Builders with it currently saved)], threshold applied.

    min_savers is a parameter so a test can ask what the query would say at a
    lower floor and prove the difference is the threshold rather than an empty
    table. NOTHING IN THE PIPELINE MAY PASS IT: run() does not, and the default
    is schema.COHORT_MIN_SAVERS.
    """
    if min_savers is None:
        min_savers = schema.COHORT_MIN_SAVERS
    return conn.execute(
        _SAVERS_SQL,
        (profile, SAVE_EVENT, UNSAVE_EVENT, SAVE_EVENT, VISIBILITY_COHORT,
         min_savers),
    ).fetchall()


#: How many Builders this profile has any live save from, at all. The VOLUME
#: instrument, and the reason it is here: .claude/CLAUDE.md says this system's
#: failure mode is silence and to alert on volume rather than errors, and at
#: today's cohort of two this step writes zero rows on a completely healthy
#: run. "0 postings" alone cannot tell a working fold from a broken one; "0
#: postings, 2 builders, floor 3" can.
#:
#: It is a COHORT-LEVEL count and deliberately not a per-posting one -- it says
#: how many people are using the feature, which is not a fact about any
#: posting and cannot narrow anybody. Printing "12 postings are below the
#: threshold" would be a per-posting sub-threshold fact, which is the thing
#: this whole module refuses to emit; it is not printed anywhere.
_ACTIVE_SAVERS_SQL = f"""
    SELECT COUNT(DISTINCT live.app_user_id) FROM (
        SELECT DISTINCT ON (e.app_user_id, e.job_id) e.app_user_id, e.event
          FROM {schema.EVENTS_TABLE} e
         WHERE e.profile = %s
           AND e.app_user_id IS NOT NULL
           AND e.event IN (%s, %s)
         ORDER BY e.app_user_id, e.job_id, e.occurred_at DESC, e.id DESC
    ) live
    WHERE live.event = %s
"""  # noqa: S608 -- splices schema.EVENTS_TABLE, a module-level constant


def active_savers(conn, profile):
    """Distinct Builders with at least one posting currently saved."""
    return conn.execute(
        _ACTIVE_SAVERS_SQL,
        (profile, SAVE_EVENT, UNSAVE_EVENT, SAVE_EVENT),
    ).fetchone()[0]


def refresh(conn, profile, now=None, dry_run=False):
    """Rebuild this profile's cohort_signal rows. Returns (rows, removed).

    A FULL REPLACE INSIDE ONE TRANSACTION, not an upsert. The set can shrink --
    a Builder unsaves and a posting drops below the threshold -- and a posting
    that falls out must LOSE its row, not keep a stale bucket. An upsert-only
    refresh would leave the badge up forever, which is a save the Builder
    retracted still being published. The DELETE and the INSERTs commit
    together, so no reader ever observes the table mid-rebuild; MVCC makes the
    empty window invisible rather than merely short.
    """
    now = now or utc_now_str()
    counted = savers_by_job(conn, profile)

    rows = []
    for job_id, savers in counted:
        bucket = schema.cohort_bucket(savers)
        # Unreachable: the query's HAVING already applied the same threshold.
        # Asserted rather than assumed because the two are the only places the
        # rule lives and a silent disagreement between them writes a row the
        # suppression was supposed to withhold.
        assert bucket is not None, f"{job_id}: {savers} savers passed HAVING"
        rows.append((job_id, profile, bucket, now))

    if dry_run:
        return rows, 0

    removed = conn.execute(
        f"DELETE FROM {schema.COHORT_SIGNAL_TABLE} WHERE cohort_profile = %s",  # noqa: S608 -- splices schema.COHORT_SIGNAL_TABLE, a module-level constant
        (profile,)).rowcount
    for row in rows:
        conn.execute(
            f"INSERT INTO {schema.COHORT_SIGNAL_TABLE} "  # noqa: S608 -- splices schema.COHORT_SIGNAL_TABLE, a module-level constant
            f"(job_id, cohort_profile, save_bucket, computed_at) "
            f"VALUES (%s, %s, %s, %s)", row)
    conn.commit()
    # Rows that were there last night and are not now: a Builder unsaved and
    # the posting fell back under the floor. Reported because a badge
    # DISAPPEARING is the operator-visible half of the feature working.
    return rows, max(removed - len(rows), 0)


def summarise(profile, builders, rows):
    """One line per profile. Buckets, never counts -- including in the log.

    The per-bucket breakdown is a count of POSTINGS in each bucket, which says
    nothing about any individual and is what an operator needs to see the
    feature working. Nothing here reports how many savers a posting has.
    """
    by_bucket = {label: 0 for label in schema.COHORT_BUCKET_LABELS}
    for _, _, bucket, _ in rows:
        by_bucket[bucket] += 1
    spread = ", ".join(f"{label}={by_bucket[label]}"
                       for label in schema.COHORT_BUCKET_LABELS)
    return (f"{profile}: {len(rows)} posting(s) [{spread}], "
            f"{builders} builder(s) saving, floor={schema.COHORT_MIN_SAVERS}")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--profile", help="only this profile (default: all active)")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    # Imported here rather than at module scope: profiles.py pulls in
    # relevance.py and the pipeline's config, and this module is also imported
    # by webapp/tests/test_cohort_signal.py from the other venv, which needs
    # the SQL and the constants and nothing else.
    import profiles

    conn = dbconn.connect_or_exit("cohort-signal", schema=schema.SCHEMA)
    schema.ensure_schema(conn)

    if args.profile:
        one = profiles.load_one(conn, args.profile)
        if not one:
            print(f"cohort-signal FAILED: no profile named {args.profile!r}")
            sys.exit(1)
        active = [one]
    else:
        active = profiles.load_active(conn)
    if not active:
        print("cohort-signal: no active profiles.")
        conn.close()
        return

    now = utc_now_str()
    parts = []
    for prof in active:
        rows, removed = refresh(conn, prof.profile, now=now,
                                dry_run=args.dry_run)
        line = summarise(prof.profile, active_savers(conn, prof.profile), rows)
        parts.append(line + (f", {removed} withdrawn" if removed else ""))

    print(f"cohort-signal{' [dry run]' if args.dry_run else ''}: "
          + "; ".join(parts))
    conn.close()


if __name__ == "__main__":
    main()
