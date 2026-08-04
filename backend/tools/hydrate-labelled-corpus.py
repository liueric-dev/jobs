#!/usr/bin/env python3
"""
Hydrate the labelled postings of a label set into a corpus fixture.

READ-ONLY. No LLM call, no API key, no write to the database.

WHY THIS EXISTS AT ALL
    It is the non-obvious link in the chain that produces a three-quantity
    report, and it spent the 2026-08-02 sitting as a one-off script in a
    session scratchpad -- which is to say, one `/tmp` sweep away from the
    measurement not being reproducible at all.

    `evals label sample` pins WHICH postings are to be labelled and writes
    evals/fixtures/labelset-pursuit-v1.jsonl: ids, strata, queue positions.
    It carries NO `description_text`, so it cannot be fed to `evals run`.
    A corpus has to be built by reading those pinned ids back out of the
    database, and that is this script.

    The full chain, since none of it is discoverable from --help:

        python3 -m evals label export --out evals/fixtures/golden-v1.jsonl
        python3 tools/hydrate-labelled-corpus.py evals/fixtures/corpus-labelled36-<date>.jsonl
        python3 -m evals run --task extract --corpus <that corpus> \\
            --model "$SPEC" --out evals/fixtures/run-labelled36-<date>.jsonl
        python3 -m evals selfcheck --model "$SPEC" --corpus <that corpus> \\
            --repeat 3 --out evals/fixtures/selfcheck-labelled36-<date>.json
        python3 -m evals label report --golden ... --run ... --selfcheck ...

    `git show refactor-freeze-2026-08-02:docs/labelling-report-2026-08-02.md` is what that chain produced, with
    the caveats that belong beside the numbers.

WHAT IT SELECTS, AND WHY THAT IS THE POINT
    Every id comes from the golden file -- the postings that actually have
    labels, which is a subset of the pinned set. There is no sampling here
    and no `ORDER BY first_seen DESC`, the trap
    `git show refactor-freeze-2026-08-02:docs/MEASUREMENT-TRAPS.md`
    names: that ordering is ~85% greenhouse/ashby and so measures the easy
    sources. The set was stratified when it was drawn and this script must
    not re-select it.

    The record shape comes from evals/corpus.py's own column tuples and
    `_row_to_record`, so it cannot drift from what `evals run` expects.
"""

import argparse
import json
import os
import sys

# ingest/ and tools/ sit one level below the pipeline modules they import
# (schema, evals, ...). Python puts THIS file's directory on sys.path, not
# its parent, so the parent is added by hand.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import schema                    # noqa: E402
from evals import corpus         # noqa: E402
from lib import dbconn, envfile  # noqa: E402

# Read-only tool, so it loads the pipeline's own .env rather than requiring
# the caller to export DATABASE_URL first. Same contract as
# label-findings.py:74 and relevance-report.py:69.
_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
envfile.load(os.path.join(_BACKEND, ".env"))

DEFAULT_GOLDEN = os.path.join(_BACKEND, "evals", "fixtures", "golden-v1.jsonl")


def labelled_ids(golden_path):
    """The distinct job_ids that carry at least one label, sorted.

    Sorted because `git show refactor-freeze-2026-08-02:docs/MEASUREMENT-TRAPS.md` asks for eval sets pinned by
    sorted job_id: a set whose ORDER depends on the order rows came back is
    a set that cannot be shown to be the same set twice.
    """
    with open(golden_path, "r", encoding="utf-8") as fh:
        return sorted({json.loads(line)["job_id"]
                       for line in fh if line.strip()})


def hydrate(conn, ids, profile):
    cols = list(corpus.JOB_COLUMNS) + list(corpus.FACT_COLUMNS) + [
        "match_score", "match_reasons"]
    job_cols = ", ".join(f"j.{c}" for c in corpus.JOB_COLUMNS)
    fact_cols = ", ".join(f"f.{c}" for c in corpus.FACT_COLUMNS)

    # LEFT JOIN on both: a gate_rejected posting legitimately has no
    # job_facts row and no job_matches row, and dropping it here would
    # quietly remove the stratum the recall question is bought for.
    rows = conn.execute(
        f"""
        SELECT {job_cols}, {fact_cols}, m.match_score, m.match_reasons
        FROM {schema.TABLE} j
        LEFT JOIN {schema.FACTS_TABLE} f ON f.job_id = j.id
        LEFT JOIN {schema.MATCHES_TABLE} m
               ON m.job_id = j.id AND m.profile = %(profile)s
        WHERE j.id = ANY(%(ids)s)
        ORDER BY j.id
        """,  # noqa: S608 -- splices schema.TABLE/schema.FACTS_TABLE/schema.MATCHES_TABLE and fixed column-name lists -- all module-level constants
        {"profile": profile, "ids": ids},
    ).fetchall()
    return [corpus._row_to_record(r, cols) for r in rows]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("out", help="corpus JSONL to write")
    ap.add_argument("--golden", default=DEFAULT_GOLDEN,
                    help="label export to take the ids from "
                         "(default: evals/fixtures/golden-v1.jsonl)")
    ap.add_argument("--profile", default="pursuit",
                    help="which profile's job_matches row to attach")
    args = ap.parse_args()

    ids = labelled_ids(args.golden)
    print(f"{len(ids)} labelled posting(s) to hydrate")

    conn = dbconn.connect_or_exit("hydrate-labelled", schema=schema.SCHEMA)
    records = hydrate(conn, ids, args.profile)

    # Both of these are printed rather than raised. A pinned id that has left
    # `jobs`, or a posting whose description was never filled, is a fact about
    # the corpus the next reader needs -- not a reason to refuse to write it.
    found = {r["id"] for r in records}
    missing = [i for i in ids if i not in found]
    if missing:
        print(f"WARNING: {len(missing)} pinned id(s) not in jobs: {missing}")

    no_desc = [r["id"] for r in records
               if not (r.get("description_text") or "").strip()]
    if no_desc:
        print(f"NOTE: {len(no_desc)} record(s) have no description_text: "
              f"{no_desc}")

    corpus.save(args.out, records)
    print(f"wrote {args.out}: {len(records)} record(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
