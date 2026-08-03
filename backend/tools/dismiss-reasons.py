#!/usr/bin/env python3
"""
What the cohort's dismissals say about `config/pursuit-criteria.json`.

READ-ONLY. No LLM call, no API key, no write of any kind.

WHY THIS IS A REPORT AND NOT A LOOP
    `docs/tasks/refactor/tranche_six/31-dismiss-demotion.md` is explicit, and
    the reasoning is worth keeping in front of whoever runs this:

        "do not implement feature-level demotion as a learned adjustment yet.
        At ~600 impressions per Builder per month and no position-bias
        correction in use, a per-Builder weight adjustment would be fitting
        noise, and it would do so invisibly. Instead: aggregate reasons and
        report them."

    So the output of this tool is EVIDENCE FOR A PERSON EDITING A CONFIG. It
    never writes a weight, and nothing in the pipeline reads it. A `wrong_level`
    dismiss is evidence about the seniority weight rather than about the one
    posting it landed on, and that is the whole reason `DISMISS_REASONS` is a
    closed enum mapping onto existing features instead of free text.

WHY IT READS builder_job_state AND NOT job_events
    Because `builder_job_state` is the CURRENT ANSWER and `job_events` is the
    evidence, and a dismissal that was undone is not a complaint any more.
    Counting the log would count reversed dismissals as live ones.

    ~~`job_events` has no `app_user_id` column~~ -- IT DOES, since 2026-08-01
    (`../schema.py`, `add_missing_columns` on `EVENTS_TABLE`; defects D66/D67 in
    the defect register, deleted 2026-08-02:
    `git show refactor-freeze-2026-08-02:docs/ingest/DEFECTS.md`). That was the
    original reason this tool read the other table and it is no longer true, so
    it is corrected rather than left to
    mislead the next reader into thinking the log cannot be grouped by Builder.
    It can. Note the column is NULLABLE AND UNBACKFILLED: rows written before
    that date carry NULL, so any per-Builder count over `job_events` must say
    what it does with them rather than silently dropping them into a bucket.

    The reason it still matters that a Builder can be counted at all: this tool
    can count DISMISSALS or it can count BUILDERS, and "twelve Builders
    dismissed postings as wrong_level this week" and "one Builder dismissed
    twelve" are the same row count and opposite conclusions -- only the first is
    a reason to touch a weight. `builder_job_state` carries `app_user_id`, so
    the distinct count is available; that is why every headline figure below is
    a Builder count and the posting count is printed beside it rather than
    instead of it.

    The cost of that choice is stated rather than hidden: this table holds the
    CURRENT state, so an undone dismissal is gone from it. An undo is still a
    row in `job_events` (event `undismiss`), and § UNDONE below reads it there.

WHAT IT DELIBERATELY DOES NOT PRINT
    A per-Builder breakdown. In a thirty-person cohort who see each other in a
    classroom, "who dismissed what" is an identity, and task 28's suppression
    argument applies to this tool as much as to the API: a count of one is
    close to an identifier. Counts here are cohort-level, and § *Interaction
    with cohort signal* in task 31 forbids surfacing any of it to Builders --
    "18 Builders dismissed this" is discouraging, deanonymising at small N, and
    reflects a cohort-wide config problem more often than a bad posting.

    A verdict. There is no threshold in here above which something is "wrong".
    At the volumes this will see for its first several months, the honest
    output is a distribution and the reader's own judgement.

    python3 tools/dismiss-reasons.py                # the last 7 days
    python3 tools/dismiss-reasons.py --days 30
    python3 tools/dismiss-reasons.py --days 0       # everything ever recorded
"""

import argparse
import os
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

# ingest/ and tools/ sit one level below the pipeline modules they import
# (schema, evals, ...). Python puts THIS file's directory on sys.path, not
# its parent, so the parent is added by hand.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg                   # noqa: E402

import schema                    # noqa: E402
from lib import dbconn, envfile  # noqa: E402

# Read-only tool, so it loads the pipeline's own .env rather than requiring the
# caller to export DATABASE_URL first. Same contract as relevance-report.py and
# label-findings.py.
envfile.load(os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

#: Which fact each reason is evidence about. This mapping IS the argument for a
#: closed vocabulary: free text would be unjoinable to any of these columns, and
#: a reason that pointed at nothing would be a reason nobody could act on.
#:
#: `bad_company` has no column and that is recorded rather than papered over --
#: task 31 calls it "a company-level signal the pipeline does not yet have", so
#: the honest report for it is the company names and their counts.
#:
#: `other` is expected to dominate initially and maps to nothing on purpose.
#: Reading it as a signal about any weight is the mistake this comment exists to
#: prevent; it is a signal about the vocabulary.
REASON_EVIDENCE = {
    "wrong_level": ("seniority_level", "the seniority weights"),
    "wrong_role": ("role_archetype", "the archetype weights, or the role_track "
                                     "assignment"),
    "wrong_location": ("location_raw", "location acceptance"),
    "bad_company": ("company_name", "a company-level signal the pipeline does "
                                    "not yet have"),
    "stale_posting": ("posted_at_ts", "posting_age_days weighting"),
    "other": (None, "nothing -- expect this to dominate initially"),
}


def cutoff_for(days):
    """The ISO string dismissals are counted from, or None for all of time.

    occurred_at and dismissed_at are TEXT in a fixed-width ISO form, so string
    comparison IS chronological comparison -- the same property webapp/jobs.py
    relies on for its impression dedup.
    """
    if not days:
        return None
    return (datetime.now(timezone.utc) - timedelta(days=days)
            ).strftime("%Y-%m-%dT%H:%M:%S")


def load_dismissals(conn, cutoff):
    """One row per live dismissal, with the facts its reason implicates.

    LEFT JOIN on job_facts and jobs: a posting can be dismissed before it has
    been extracted, and dropping those rows would silently shrink the count
    this tool exists to report. A missing fact prints as `-`.
    """
    where = ["s.dismissed_at IS NOT NULL"]
    params = []
    if cutoff:
        where.append("s.dismissed_at >= %s")
        params.append(cutoff)
    return conn.execute(
        f"""
        SELECT s.app_user_id, s.job_id, s.dismiss_reason, s.dismissed_at,
               f.seniority_level, f.role_archetype, f.role_track,
               j.company_name, j.title, j.location_raw, j.posted_at_ts
        FROM builder_job_state s
        LEFT JOIN jobs j ON j.id = s.job_id
        LEFT JOIN job_facts f ON f.job_id = s.job_id
        WHERE {' AND '.join(where)}
        ORDER BY s.dismissed_at
        """,
        params).fetchall()


def load_undo_count(conn, cutoff):
    """How many dismissals were reversed, from the append-only log.

    Not available from builder_job_state -- an undo clears the column, so the
    state table has no memory of it. This is the reason task 31 asked for the
    undo to be an event rather than a deletion: "the fact that someone reversed
    a dismissal is itself signal".
    """
    where = ["event = 'undismiss'"]
    params = []
    if cutoff:
        where.append("occurred_at >= %s")
        params.append(cutoff)
    return conn.execute(
        f"SELECT count(*) FROM job_events WHERE {' AND '.join(where)}",
        params).fetchone()[0]


def rule(title):
    print()
    print(title)
    print("-" * len(title))


def distribution(rows, index, limit=8):
    """`value  count` lines, commonest first, NULL rendered as `-`."""
    counts = Counter("-" if r[index] is None else str(r[index]) for r in rows)
    width = max((len(v) for v, _ in counts.most_common(limit)), default=1)
    for value, count in counts.most_common(limit):
        print(f"    {value:<{width}}  {count}")
    if len(counts) > limit:
        print(f"    ... and {len(counts) - limit} more")


#: Column index in a load_dismissals() row, by the fact name in REASON_EVIDENCE.
_COLUMN_INDEX = {"seniority_level": 4, "role_archetype": 5, "role_track": 6,
                 "company_name": 7, "location_raw": 9, "posted_at_ts": 10}


def report(rows, undone, days):
    window = f"the last {days} days" if days else "all recorded time"
    rule(f"Dismissals over {window}")

    if not rows:
        # The correct output today, and it should not be made to look like
        # data. The reason CHANGED on 2026-08-02 (task 32) and the check below
        # matters more now, not less: it used to be that frontend/ held one
        # .gitkeep and no screen could post a dismiss at all. A screen now can
        # -- today.mjs:175 and saved.mjs:123-129 post `dismiss` with an
        # optional reason -- so zero has stopped meaning "impossible" and
        # started meaning "no Builder has done it yet", which is a reading that
        # can also be produced by a client that is broken or unreachable.
        print("    none.")
        print()
        print("    Zero is a reading, not a failure. Check that anything is")
        print("    posting dismissals at all before concluding the cohort has")
        print("    no complaints: `SELECT count(*) FROM job_events WHERE")
        print("    event = 'dismiss'` answers that in one line.")
        return

    builders = {r[0] for r in rows}
    print(f"    {len(rows)} dismissal(s) over {len({r[1] for r in rows})} "
          f"posting(s), by {len(builders)} Builder(s).")
    if undone:
        print(f"    {undone} dismissal(s) were undone in the same window -- "
              f"those are NOT counted above.")

    rule("By reason")
    print("    Builders is the figure to read. One Builder dismissing twelve")
    print("    postings and twelve Builders dismissing one are the same row")
    print("    count and opposite conclusions.")
    print()
    print(f"    {'reason':<16} {'Builders':>8} {'postings':>9}   evidence about")
    by_reason = {}
    for row in rows:
        by_reason.setdefault(row[2], []).append(row)
    for reason, reason_rows in sorted(
            by_reason.items(), key=lambda kv: -len({r[0] for r in kv[1]})):
        _, about = REASON_EVIDENCE.get(reason, (None, "an unknown reason"))
        print(f"    {str(reason):<16} {len({r[0] for r in reason_rows}):>8} "
              f"{len(reason_rows):>9}   {about}")

    for reason, reason_rows in sorted(by_reason.items()):
        fact, about = REASON_EVIDENCE.get(reason, (None, None))
        if fact is None:
            continue
        rule(f"{reason} -- what was dismissed, by {fact}")
        print(f"    Evidence about {about}.")
        distribution(reason_rows, _COLUMN_INDEX[fact])

    rule("What to do with this")
    print("    Nothing automatically. These counts are evidence for a person")
    print("    editing config/pursuit-criteria.json by hand. At ~600")
    print("    impressions per Builder per month and no position-bias")
    print("    correction in use, a learned per-Builder weight would be")
    print("    fitting noise, and it would do so invisibly (task 31).")
    print()
    print("    Do not surface any of this to Builders. Dismissal counts are")
    print("    discouraging, deanonymising at small N, and usually describe a")
    print("    cohort-wide config problem rather than a bad posting.")


def main():
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("--days", type=int, default=7,
                   help="window in days; 0 for everything ever recorded")
    args = p.parse_args()

    conn = dbconn.connect_or_exit("dismiss-reasons", schema=schema.SCHEMA)
    cutoff = cutoff_for(args.days)
    try:
        report(load_dismissals(conn, cutoff),
               load_undo_count(conn, cutoff), args.days)
    except psycopg.errors.UndefinedTable:
        # The one failure with a specific answer, and it is a deployment state
        # rather than a bug: builder_job_state is created by webapp/'s own DDL
        # step, which runs under an admin credential and on its own schedule.
        # A traceback here would send the reader looking for a missing GRANT.
        conn.rollback()
        sys.exit("builder_job_state does not exist -- run "
                 "`.venv/bin/python manage_app_users.py init-schema` in "
                 "backend/webapp with JOBS_ADMIN_DATABASE_URL set.")
    finally:
        conn.close()
    print()


if __name__ == "__main__":
    main()
