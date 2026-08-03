#!/usr/bin/env python3
"""
Sweep extract.py's input-sanity gate over the whole jobs table, and clean up
after it.

WHY THIS EXISTS SEPARATELY FROM THE GATE
    extract.py's gate decides one posting at a time, at extraction time, and by
    then the decision is invisible: a rejected row is a +1 on the `unusable`
    counter and a tombstone. The number that actually justifies the threshold is
    a corpus-wide one -- how many REAL postings would this predicate reject --
    and it has to be re-derivable, because the answer changes every time the
    corpus grows or a vendor changes their markup. So the sweep is a tool rather
    than a paragraph in a document that was true once.

    It imports extract.markup_ratio() rather than restating the regex. A tool
    that measured its own copy of the predicate would measure the copy -- the
    same rule evals/cassettes.py states as ADAPTERS, NEVER COPIES.

    python3 tools/audit-description-markup.py                 # the sweep
    python3 tools/audit-description-markup.py --show 3        # + the leaked text
    python3 tools/audit-description-markup.py --remediate     # clean the rows
    python3 tools/audit-description-markup.py --remediate --commit

WHAT --remediate DOES, AND WHY IT IS THE STRONGEST OF THE THREE OPTIONS
    A gate does not clean up what is already stored. Three dispositions were
    available for a row that is already poisoned:

      1. tombstone the job_facts row and leave description_text alone. Cheapest,
         and WRONG: the poisoned bytes stay, so the next FACTS_VERSION bump
         re-extracts them and re-derives exactly the facts this task exists to
         remove. It fixes the symptom at the one version it is run at.
      2. delete the jobs row. Loses the posting -- and five of the eight
         contaminated rows are real jobs at real companies whose descriptions
         merely have soup spliced through them. Deleting Databricks' account
         executive req because of twelve Tailwind class names is a worse
         outcome than the defect.
      3. NULL description_text, clear content_hash, and delete the job_facts
         row. What this does.

    3 is right because the three writes are three halves of one fact: the bytes
    were never a job description, nothing derived from them is evidence, and the
    row must be allowed to heal. NULLing description_text makes the posting
    ineligible (extract.py's `coalesce(j.description_text,'') <> ''`), so it
    costs no further LLM calls; deleting rather than tombstoning the facts row
    means the posting is re-extractable the moment ingest re-fetches a
    description that is NOT markup, instead of waiting out a FACTS_VERSION bump.

    CLEARING content_hash IS NOT OPTIONAL, and getting this wrong strands the
    row forever. `description_text` IS in HASH_FIELDS_ATS and HASH_FIELDS_SHORT
    (schema.py:131-135), and lib/upsert.py:219 compares the STORED content_hash
    against a hash recomputed from the INCOMING record. So a row whose
    description_text is NULL but whose content_hash still matches upstream takes
    the `touch_sql` branch on every subsequent run: last_seen is bumped, the
    description is never rewritten, and the posting is permanently invisible to
    a pipeline that reports the night as a success. Clearing the hash forces the
    UPDATE branch exactly once, which is the retry this whole disposition is for.

    The expected repair is the employer fixing their job description; if they do
    not, the gate rejects it again next time at the cost of one tombstone write
    and zero LLM calls.

    The repo owner's standing stance is that database contents are STAGING DATA
    -- optimise for build speed, not preservation (HANDOFF.md:28-33). This tool
    still defaults to a dry run, because a destructive default that is only ever
    typed once is a destructive default nobody reads twice.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import extract  # noqa: E402
import schema  # noqa: E402
from lib import dbconn  # noqa: E402


def scan(conn):
    """Every described posting, with the ratio the gate would compute for it.

    Returns rows sorted worst-first, as (ratio, job_id, platform, company,
    title, leaked_chars, total_chars). Read-only.
    """
    rows = conn.execute(
        f"""
        SELECT j.id, j.platform, j.company_name, j.title, j.description_text
        FROM {schema.TABLE} j
        WHERE coalesce(j.description_text, '') <> ''
        """  # noqa: S608 -- splices schema.TABLE, a module-level constant
    ).fetchall()

    out = []
    for job_id, platform, company, title, description in rows:
        window = extract.prompt_description({"description_text": description})
        ratio = extract.markup_ratio(window)
        if ratio > 0:
            out.append((ratio, job_id, platform, company, title,
                        int(ratio * len(window)), len(window)))
    out.sort(reverse=True)
    return out, len(rows)


def remediate(conn, job_ids, commit=False):
    """Clear the poisoned description, its hash, and everything derived from it.

    All three statements or none: a posting whose description is gone but whose
    content_hash still matches upstream is never rewritten (see the module
    docstring), and one whose facts row survives keeps serving the facts this
    tool exists to remove.
    """
    if not job_ids:
        return 0, {}
    ids = list(job_ids)
    # job_matches and job_scores CASCADE from `jobs`, not from `job_facts`
    # (schema.py:344,415,435), so deleting the facts row alone would leave a
    # match_score and an LLM narrative derived from markup sitting in the list
    # a user actually reads -- which is how 53cbf3ae21a12bff1ff73476's
    # 'core_ml_research' reached a job_scores row in the first place.
    derived = {}
    for table in (schema.SCORES_TABLE, schema.MATCHES_TABLE,
                  schema.FACTS_TABLE):
        derived[table] = conn.execute(
            f"DELETE FROM {table} WHERE job_id = ANY(%s)", (ids,)).rowcount  # noqa: S608 -- splices `table`, iterated only over this module's own constant table names
    jobs = conn.execute(
        f"UPDATE {schema.TABLE} SET description_text = NULL, content_hash = NULL "  # noqa: S608 -- splices schema.TABLE, a module-level constant
        f"WHERE id = ANY(%s)", (ids,)).rowcount
    if commit:
        conn.commit()
    else:
        conn.rollback()
    return jobs, derived


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--show", type=int, default=0, metavar="N",
                    help="print the first N leaked tokens of each flagged row")
    ap.add_argument("--remediate", action="store_true",
                    help="NULL description_text and delete job_facts for rows "
                         "the gate rejects")
    ap.add_argument("--commit", action="store_true",
                    help="actually write --remediate's changes (default: roll back)")
    args = ap.parse_args()

    conn = dbconn.connect_or_exit("audit-description-markup", schema=schema.SCHEMA)
    flagged, total = scan(conn)
    rejected = [r for r in flagged if r[0] >= extract.MARKUP_REJECT_RATIO]

    print(f"described postings scanned: {total}")
    print(f"any markup residue at all:  {len(flagged)}")
    print(f"REJECTED at ratio >= {extract.MARKUP_REJECT_RATIO}: {len(rejected)}")
    print(f"below the threshold (kept): {len(flagged) - len(rejected)}")
    print()
    print(f"{'ratio':>7}  {'job_id':24}  {'platform':12}  company / title")
    for ratio, job_id, platform, company, title, leaked, size in flagged:
        mark = "REJECT" if ratio >= extract.MARKUP_REJECT_RATIO else "keep  "
        print(f"{ratio:7.4f}  {job_id:24}  {platform:12}  {mark}  "
              f"{company} / {title}  ({leaked}/{size} chars)")
        if args.show:
            window = conn.execute(
                f"SELECT description_text FROM {schema.TABLE} WHERE id = %s",  # noqa: S608 -- splices schema.TABLE, a module-level constant
                (job_id,)).fetchone()[0]
            tokens = [t for t in extract.prompt_description(
                {"description_text": window}).split()
                if extract._MARKUP_RESIDUE.search(t)]
            for t in tokens[:args.show]:
                print(f"           {t[:110]}")

    # The number the threshold is actually justified by. Printed even when it is
    # zero, because "no real posting is rejected" is the claim being made and an
    # unstated zero is indistinguishable from a sweep that never ran.
    print()
    print(f"false-positive candidates to inspect by hand: the {len(rejected)} "
          f"REJECT rows above. Every one that is a real job posting is a false "
          f"positive; the threshold is only defensible while that count is 0.")

    if args.remediate:
        ids = [r[1] for r in rejected]
        jobs, derived = remediate(conn, ids, commit=args.commit)
        verb = "cleared" if args.commit else "would clear"
        print(f"\n--remediate: {verb} description_text + content_hash on "
              f"{jobs} job(s); deleted "
              + ", ".join(f"{n} {t}" for t, n in derived.items())
              + ("" if args.commit
                 else "  (DRY RUN -- pass --commit to write)"))

    conn.close()


if __name__ == "__main__":
    main()
