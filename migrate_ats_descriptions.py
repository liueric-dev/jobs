#!/usr/bin/env python3
"""
Rewrite ATS description_text from raw_json, using the fixed extraction.

WHAT WAS WRONG
    ingest/ats.py passed `unescape=False` to text.strip_html for all three ATS
    platforms. Greenhouse's `content` field arrives HTML-*escaped*, so the
    markup survived as literal text in every one of its 7,182 rows:

        &lt;div class=&quot;content-intro&quot;&gt;&lt;h2&gt;About Us:&amp;nbsp;

    Ashby and Lever serve real HTML, so their rows were merely left holding
    `&amp;` where `&` belonged (1,521 of 2,561 Ashby rows). Separately, the
    5,000-char cap truncated 92% of Greenhouse rows, and roughly a quarter of
    that budget was being spent on the escaped markup rather than on prose.

WHY NO REFETCH
    `raw_json` stores the untouched API response for every ATS row, so the
    corrected text can be derived locally. 9,752 rows, no network, no API
    quota, and no risk of a company's board having changed since ingest. Rows
    whose upstream posting has since been edited will pick that up on the next
    ordinary run.

WHY THIS RECOMPUTES content_hash TOO -- THE PART THAT IS EASY TO MISS
    `description_text` is in schema.HASH_FIELDS_ATS. Rewriting the text
    without rewriting the hash leaves every row's stored hash describing text
    that is no longer there, so the next ingest sees 9,752 "changes" and
    rewrites all of them. Harmless but a lie: the run report would claim
    thousands of postings changed upstream on a day when none did, which is
    exactly the signal that report exists to give. lib/text.py's docstring
    records the last time this happened (217 of 242 weworkremotely rows).

    The hash is rebuilt from the row's OWN stored columns with only
    description_text replaced -- not from a re-normalized record -- because
    this migration must change one field and nothing else. Verified against
    3,000 live rows: reconstructing the hash this way reproduces the existing
    stored hash exactly (3000/3000) before any edit, which is what makes the
    recomputed value trustworthy.

WHY IT REUSES THE INGEST NORMALIZERS
    The description is produced by calling ingest/ats.py's own normalize_*
    functions, not by a copy of their logic. A migration that reimplements the
    transformation it is migrating to will drift from it; this one cannot.

USAGE
    python3 migrate_ats_descriptions.py                  # report only
    python3 migrate_ats_descriptions.py --limit 200      # sample the report
    python3 migrate_ats_descriptions.py --apply          # rewrite
    python3 migrate_ats_descriptions.py --apply --platform greenhouse

IDEMPOTENT: a second run finds nothing to change, because the recomputed
description and hash both already match what is stored.
"""

import argparse
import json
import os
import re
import statistics
import sys

# `import ats` reaches into ingest/, which is not a package -- four of its
# siblings have hyphenated filenames -- so it is not importable without this.
# Everything else this file imports is a sibling or an installed package.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "ingest"))

import ats  # noqa: E402  (ingest/ats.py -- the normalizers themselves)
import schema  # noqa: E402
from lib import dbconn, ids  # noqa: E402

ATS_PLATFORMS = ("greenhouse", "ashby", "lever")

#: The normalizers read company flags, but none of them feed HASH_FIELDS_ATS
#: and none of them feed description_text, so a stub is sufficient here. Only
#: description_text is read back out.
STUB_COMPANY = {"token": "", "name": "", "is_nyc_hq": False,
                "is_ai_focused": False}

#: Literal entities that should never appear in extracted plain text. Used for
#: reporting only -- the fix is upstream, this just measures it.
#:
#: This does not reach zero, and should not be chased to zero: 3 of 9,752 rows
#: are TRIPLE-escaped at the employer's end (`&amp;amp;` in Greenhouse's own
#: payload, from someone typing "&" into a WYSIWYG that escaped it before
#: Greenhouse escaped the document), leaving a cosmetic "R&amp;D". Unescaping
#: in a loop until nothing changes would fix those three and start corrupting
#: any posting that legitimately quotes an HTML entity, which is a worse trade.
ENTITY = re.compile(r"&(nbsp|amp|lt|gt|quot|#\d+|#x[0-9a-fA-F]+);")

BATCH = 500


def redescribe(platform, raw_json):
    """The description ingest/ats.py would store for this row today."""
    normalize = ats.NORMALIZERS[platform]
    return normalize(STUB_COMPANY, json.loads(raw_json))["description_text"]


def main():
    p = argparse.ArgumentParser(
        description="Rewrite ATS description_text from raw_json (read-only by default).")
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

    conn = dbconn.connect_or_exit("migrate-ats-descriptions", schema=schema.SCHEMA)

    sql = (f"SELECT id, platform, raw_json, content_hash, {', '.join(fields)} "
           f"FROM {schema.TABLE} WHERE platform = ANY(%(p)s) "
           f"AND coalesce(raw_json, '') <> '' ORDER BY id")
    params = {"p": platforms}
    if args.limit:
        sql += " LIMIT %(lim)s"
        params["lim"] = args.limit
    rows = conn.execute(sql, params).fetchall()

    pending, unchanged, failed = [], 0, []
    before_lens, after_lens = [], []
    before_dirty = after_dirty = 0

    for row in rows:
        job_id, platform, raw_json, stored_hash = row[0], row[1], row[2], row[3]
        rec = dict(zip(fields, row[4:]))
        old_desc = rec.get("description_text") or ""

        try:
            new_desc = redescribe(platform, raw_json)
        except (ValueError, KeyError, TypeError) as e:
            failed.append((job_id, f"{type(e).__name__}: {e}"))
            continue

        before_lens.append(len(old_desc))
        after_lens.append(len(new_desc or ""))
        before_dirty += bool(ENTITY.search(old_desc))
        after_dirty += bool(ENTITY.search(new_desc or ""))

        if (new_desc or "") == old_desc:
            unchanged += 1
            continue

        new_hash = ids.content_hash({**rec, "description_text": new_desc},
                                    fields, blank_if_falsy=("description_text",))
        pending.append((job_id, platform, new_desc, new_hash, stored_hash, old_desc))

    def avg(xs):
        return statistics.mean(xs) if xs else 0

    print(f"migrate-ats-descriptions: {len(rows)} rows examined "
          f"({', '.join(platforms)})")
    print(f"  to rewrite : {len(pending)}")
    print(f"  unchanged  : {unchanged}")
    if failed:
        print(f"  unparseable raw_json: {len(failed)}  e.g. {failed[:2]}")
    print(f"  description length  avg {avg(before_lens):.0f} -> {avg(after_lens):.0f} chars")
    print(f"  rows with literal HTML entities  {before_dirty} -> {after_dirty}")

    for job_id, platform, new_desc, _, _, old_desc in pending[:args.samples]:
        print(f"\n  --- {platform} {job_id} ---")
        print(f"  before: {old_desc[:150]!r}")
        print(f"  after : {(new_desc or '')[:150]!r}")

    if not args.apply:
        print(f"\nDRY RUN -- nothing written. Re-run with --apply to rewrite "
              f"{len(pending)} rows.")
        conn.close()
        return

    written = 0
    for i in range(0, len(pending), BATCH):
        for job_id, _, new_desc, new_hash, _, _ in pending[i:i + BATCH]:
            conn.execute(
                f"UPDATE {schema.TABLE} SET description_text = %(d)s, "
                f"content_hash = %(h)s WHERE id = %(id)s",
                {"d": new_desc, "h": new_hash, "id": job_id})
            written += 1
        conn.commit()
        print(f"  committed {min(i + BATCH, len(pending))}/{len(pending)}")

    conn.close()
    print(f"migrate-ats-descriptions: rewrote {written} rows. "
          f"The next ingest should report ~0 updated -- if it reports "
          f"thousands, the hash recomputation did not take.")


if __name__ == "__main__":
    main()
