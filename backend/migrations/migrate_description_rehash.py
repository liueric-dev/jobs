#!/usr/bin/env python3
"""
Rewrite ATS description_text from raw_json after lib/text._TAG was fixed.

WHAT WAS WRONG
    lib/text.strip_html() stripped tags with `<[^>]+>`. That character class
    cannot cross a ">", so a tag ended at the FIRST one in the source --
    including a ">" inside a quoted attribute value. Tailwind arbitrary
    variants contain them:

        <div class="[&:has([data-writing-block])>*]:pointer-events-auto"
             data-testid="conversation-turn-136">

    Everything after `>*]` was emitted as prose and stored in
    description_text. lib/text.py's note above `_TAG` has the full account.

WHY A MIGRATION IS NEEDED AT ALL -- THE PART THAT IS EASY TO MISS
    Fixing the stripper does not heal the rows it already wrote.
    `description_text` is in schema.HASH_FIELDS_ATS (schema.py:131-132), and
    lib/upsert.py compares the STORED content_hash against one recomputed
    from the INCOMING record. The incoming record is built by the fixed
    stripper, so its hash no longer matches -- which means the next ordinary
    run WOULD rewrite these rows by itself.

    That is not a reason to skip this. It is a reason to do it deliberately:
      * the poisoned rows only heal when their board is re-fetched AND the
        posting is still open. Five of the six are already stale enough that
        a Greenhouse board may well have dropped them, in which case the
        poisoned bytes stay in the table forever.
      * `raw_json` holds the untouched API response for every ATS row, so the
        corrected text is derivable locally: no network, no API quota, no
        risk of the posting having changed since ingest.

WHY IT RECOMPUTES content_hash TOO
    Same reason migrate_ats_descriptions.py did (that file's own section says
    it, and it is still the precedent this follows). Rewriting the text
    without the hash leaves every touched row's stored hash describing text
    that is no longer there, so the next ingest reports those rows as changed
    upstream on a day when nothing changed upstream -- which is the exact
    signal the run report exists to give. lib/text.py's docstring records the
    last time that happened: 217 of 242 weworkremotely rows.

    The hash is rebuilt from the row's OWN stored columns with only
    description_text replaced, not from a re-normalized record, because this
    migration must change one field and nothing else. The report prints how
    many UNCHANGED rows reproduce their stored hash by that method; if that
    is not 100% the recomputation is not trustworthy and --apply refuses.

WHY IT REUSES THE INGEST NORMALIZERS
    The description is produced by calling ingest/ats.py's own normalize_*
    functions, not a copy of their logic. A migration that reimplements the
    transformation it is migrating to will drift from it; this one cannot.
    Same rule evals/cassettes.py states as ADAPTERS, NEVER COPIES.

WHY ONLY THE ATS PLATFORMS, AND WHY THAT IS NOT AN OVERSIGHT
    Measured 2026-07-29 over every markup string in every stored raw_json --
    21,350 strings from 13,066 rows, each tested at every level of escaping.
    Exactly 6 rows change, all greenhouse. The other platforms are excluded
    for reasons, one each, not by omission:

      weworkremotely, builtin, hn_whoishiring (939 described rows)
          store NO raw_json at all. There is nothing to rebuild from. A
          re-ingest is the only repair available and none of them changed.
      workday (330 rows)
          raw_json is the LIST payload; description_text comes from a second
          detail fetch (ingest/workday.py:708) that is not stored. Rebuilding
          from raw_json would blank the description, not fix it.
      google_jobs (970 rows)
          raw_json is written through text.bounded_json(), which SHRINKS the
          description field to keep the envelope under RAW_JSON_LIMIT
          (lib/text.py:65-94). Rebuilding from it can silently shorten a real
          posting, so a rebuild is not a safe no-op for the ~0 rows it would
          fix here.
      nyc_open_data (1,353 rows)
          rebuildable in principle, zero affected in practice, and its
          normalizer lives in a hyphenated module that is not importable
          without importlib gymnastics. Not worth the reach for a measured
          zero -- re-measure with tools/audit-description-markup.py before
          assuming that stays true.

WHAT THIS DOES NOT DO: THE DERIVED ROWS
    Five of the six rows have a job_facts row extracted FROM the soup, and
    two of those have a job_matches / job_scores row under it. This migration
    does not touch them -- tools/audit-description-markup.py already owns that
    disposition and documents why it is all three writes or none.

    ORDER MATTERS, and the report below prints it:

        1. tools/audit-description-markup.py --remediate --commit
             deletes the derived rows and NULLs the poisoned description.
        2. this migration, with --apply
             puts the CLEAN description back and writes a matching hash, so
             the posting is extractable again on the next run.

    Run in that order the posting is repaired. Run this one alone and the
    text is clean while the facts under it are still soup.

USAGE
    python3 migrations/migrate_description_rehash.py                # report
    python3 migrations/migrate_description_rehash.py --limit 500    # sample it
    python3 migrations/migrate_description_rehash.py --apply        # rewrite
    python3 migrations/migrate_description_rehash.py --apply --platform greenhouse

IDEMPOTENT: a second run finds nothing to change, because the recomputed
description and hash both already match what is stored.
"""

import argparse
import json
import os
import sys

# migrations/ sits one level below the pipeline modules it imports (schema,
# extract, ...). Python puts THIS file's directory on sys.path, not its
# parent, so the parent is added by hand. That same insert is what reaches
# lib/ -- there is nothing to install.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)

# `import ats` needs a second one. ingest/ is not a package -- four of its
# members have hyphenated filenames -- so its directory has to be on the path
# in its own right, not merely reachable from the root.
sys.path.insert(0, os.path.join(_REPO_ROOT, "ingest"))

import ats  # noqa: E402  (ingest/ats.py -- the normalizers themselves)
import extract  # noqa: E402  (markup_ratio: the gate's own predicate, not a copy)
import schema  # noqa: E402
from lib import dbconn, envfile, ids  # noqa: E402

# Already-exported values still win -- see envfile.load().
envfile.load(os.path.join(_REPO_ROOT, ".env"))

ATS_PLATFORMS = ("greenhouse", "ashby", "lever")

#: The normalizers read company flags, but none of them feed HASH_FIELDS_ATS
#: and none of them feed description_text, so a stub is sufficient here. Only
#: description_text is read back out. Same stub, same reason, as
#: migrate_ats_descriptions.py:82-84.
STUB_COMPANY = {"token": "", "name": "", "is_nyc_hq": False,
                "is_ai_focused": False}

BATCH = 500


def redescribe(platform, raw_json):
    """The description ingest/ats.py would store for this row today."""
    normalize = ats.NORMALIZERS[platform]
    return normalize(STUB_COMPANY, json.loads(raw_json))["description_text"]


def ratio(description):
    """extract.py's OWN gate predicate over the window a prompt would carry.

    Imported rather than restated so the number this migration reports is the
    number the gate would compute -- the same reason
    tools/audit-description-markup.py imports it.
    """
    return extract.markup_ratio(
        extract.prompt_description({"description_text": description or ""}))


def main():
    p = argparse.ArgumentParser(
        description="Rewrite ATS description_text after the strip_html tag fix "
                    "(read-only by default).")
    p.add_argument("--apply", action="store_true",
                   help="write the changes; omit for a report")
    p.add_argument("--platform", choices=ATS_PLATFORMS,
                   help="restrict to one platform")
    p.add_argument("--limit", type=int, help="only examine this many rows")
    p.add_argument("--samples", type=int, default=3,
                   help="before/after excerpts to print")
    args = p.parse_args()

    platforms = [args.platform] if args.platform else list(ATS_PLATFORMS)
    fields = schema.HASH_FIELDS_ATS

    conn = dbconn.connect_or_exit("migrate-description-rehash",
                                  schema=schema.SCHEMA)

    sql = (f"SELECT id, platform, raw_json, content_hash, {', '.join(fields)} "
           f"FROM {schema.TABLE} WHERE platform = ANY(%(p)s) "
           f"AND coalesce(raw_json, '') <> '' ORDER BY id")
    params = {"p": platforms}
    if args.limit:
        sql += " LIMIT %(lim)s"
        params["lim"] = args.limit
    rows = conn.execute(sql, params).fetchall()

    pending, unchanged, failed = [], 0, []
    # The trust check: on rows this migration is NOT touching, does the hash
    # reconstruction reproduce what is stored? If it does not, the value it
    # would write for the touched rows is a guess.
    hash_reproduced = hash_checked = 0
    rejected_before = rejected_after = 0

    for row in rows:
        job_id, platform, raw_json, stored_hash = row[0], row[1], row[2], row[3]
        rec = dict(zip(fields, row[4:]))
        old_desc = rec.get("description_text") or ""

        try:
            new_desc = redescribe(platform, raw_json)
        except (ValueError, KeyError, TypeError) as e:
            failed.append((job_id, f"{type(e).__name__}: {e}"))
            continue

        if (new_desc or "") == old_desc:
            unchanged += 1
            if stored_hash:
                hash_checked += 1
                hash_reproduced += (
                    ids.content_hash(rec, fields,
                                     blank_if_falsy=("description_text",))
                    == stored_hash)
            continue

        before, after = ratio(old_desc), ratio(new_desc)
        rejected_before += before >= extract.MARKUP_REJECT_RATIO
        rejected_after += after >= extract.MARKUP_REJECT_RATIO
        new_hash = ids.content_hash({**rec, "description_text": new_desc},
                                    fields, blank_if_falsy=("description_text",))
        pending.append((job_id, platform, new_desc, new_hash, old_desc,
                        before, after))

    print(f"migrate-description-rehash: {len(rows)} rows examined "
          f"({', '.join(platforms)})")
    print(f"  to rewrite : {len(pending)}")
    print(f"  unchanged  : {unchanged}")
    if failed:
        print(f"  unparseable raw_json: {len(failed)}  e.g. {failed[:2]}")
    pct = 100.0 * hash_reproduced / hash_checked if hash_checked else 0.0
    print(f"  hash reconstruction reproduces the stored hash on untouched "
          f"rows: {hash_reproduced}/{hash_checked} ({pct:.1f}%)")
    print(f"  rows the extraction gate would REJECT (ratio >= "
          f"{extract.MARKUP_REJECT_RATIO}): {rejected_before} -> "
          f"{rejected_after}")

    if pending:
        print(f"\n  {'ratio before':>12}  {'after':>7}  {'chars':>14}  job_id")
        for job_id, platform, new_desc, _, old_desc, before, after in pending:
            print(f"  {before:12.4f}  {after:7.4f}  "
                  f"{len(old_desc):6} -> {len(new_desc or ''):5}  "
                  f"{job_id}  {platform}")

    # Excerpted at the FIRST DIVERGENCE, not at character 0. The leak sits
    # wherever the contaminated tag sat, which on five of the six rows is
    # several thousand characters in -- so a `[:150]` sample prints two
    # identical strings and shows a reviewer nothing.
    for job_id, platform, new_desc, _, old_desc, _, _ in pending[:args.samples]:
        new_desc = new_desc or ""
        i = next((k for k in range(min(len(old_desc), len(new_desc)))
                  if old_desc[k] != new_desc[k]), min(len(old_desc), len(new_desc)))
        start = max(0, i - 40)
        print(f"\n  --- {platform} {job_id}  (first divergence at char {i}) ---")
        print(f"  before: {old_desc[start:i + 150]!r}")
        print(f"  after : {new_desc[start:i + 150]!r}")

    # The rows derived from bytes that were never a job description. Reported,
    # not deleted -- see WHAT THIS DOES NOT DO in the module docstring.
    if pending:
        touched = [r[0] for r in pending]
        print("\n  rows derived from the text this migration is replacing:")
        derived_total = 0
        for table in (schema.FACTS_TABLE, schema.MATCHES_TABLE,
                      schema.SCORES_TABLE):
            n = conn.execute(
                f"SELECT count(*) FROM {table} WHERE job_id = ANY(%s)",
                (touched,)).fetchone()[0]
            derived_total += n
            print(f"    {table:14} {n}")
        if derived_total:
            print("    ^ this migration does NOT delete these. Run\n"
                  "        python3 tools/audit-description-markup.py "
                  "--remediate --commit\n"
                  "      FIRST, then this with --apply. In that order the "
                  "posting is re-extractable;\n"
                  "      in the other order the text is clean and the facts "
                  "under it are still soup.")

    if not args.apply:
        print(f"\nDRY RUN -- nothing written. Re-run with --apply to rewrite "
              f"{len(pending)} rows.")
        conn.close()
        return

    # A recomputation that cannot reproduce a hash it did not change is not a
    # recomputation to trust with one it did. Refuse rather than write.
    if hash_checked and hash_reproduced != hash_checked:
        print(f"\nREFUSING TO APPLY: the hash reconstruction reproduces only "
              f"{hash_reproduced}/{hash_checked} untouched rows. Either "
              f"HASH_FIELDS_ATS changed or a normalizer did; the value this "
              f"would write for the {len(pending)} touched rows is a guess.")
        conn.close()
        sys.exit(1)

    written = 0
    for i in range(0, len(pending), BATCH):
        for job_id, _, new_desc, new_hash, _, _, _ in pending[i:i + BATCH]:
            conn.execute(
                f"UPDATE {schema.TABLE} SET description_text = %(d)s, "
                f"content_hash = %(h)s WHERE id = %(id)s",
                {"d": new_desc, "h": new_hash, "id": job_id})
            written += 1
        conn.commit()
        print(f"  committed {min(i + BATCH, len(pending))}/{len(pending)}")

    conn.close()
    print(f"migrate-description-rehash: rewrote {written} rows. "
          f"Re-run tools/audit-description-markup.py -- it should now report "
          f"0 rows above the threshold.")


if __name__ == "__main__":
    main()
