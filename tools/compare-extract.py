#!/usr/bin/env python3
"""
Does disabling reasoning change the FACTS, or only the bill?

WHY THIS TEST AND NOT A SPEARMAN
    For the narrative stage, "is quality preserved" is a question about
    ranking, so the honest measure is rank correlation. Extraction is not
    like that. Its output is a fixed set of closed-vocabulary fields, so
    agreement is directly checkable: extract the SAME postings twice, once
    with reasoning and once without, and count how often each field matches.

    That is a far stronger test than a correlation, and it is the reason
    extraction is the right place to try this first. A disagreement here is
    unambiguous -- one of the two runs is wrong about a fact the posting
    states -- whereas a shifted fit_score is only a recalibration.

WHAT COUNTS AS AGREEMENT
    Enumerated fields: exact match after extract.normalize(), which is what
    would actually be stored. Booleans: exact. tech_stack: Jaccard overlap,
    because listing "node" vs "node.js" is not a disagreement worth failing
    over and the matcher caps stack contribution anyway. summary is not
    compared -- it is prose, and two correct summaries differ.

READ-ONLY. Writes nothing to job_facts. Both runs are billable; that is the
point, and at n=40 it is about two cents.

USAGE
    python3 tools/compare-extract.py \\
        --model "deepseek-v4-flash@$DEEPSEEK_BASE_URL@$DEEPSEEK_API_KEY" --n 40
"""

import os
import sys
import json
import time
import argparse
import statistics
import urllib.request
import concurrent.futures

# ingest/ and tools/ sit one level below the pipeline modules they import
# (schema, relevance, llm, ...). Python puts THIS file's directory on sys.path,
# not its parent, so the parent is added by hand. pipelib needs nothing -- it is
# an installed package (pip install --user -e ~/apps/pipelib).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import extract     # noqa: E402
import llm         # noqa: E402
import profiles    # noqa: E402
import relevance   # noqa: E402
import schema      # noqa: E402
from pipelib import dbconn  # noqa: E402

#: Compared exactly. summary is excluded (prose), tech_stack handled separately.
SCALAR_FIELDS = ("seniority_level", "role_archetype", "ai_involvement",
                 "remote_policy", "employment_type", "visa_sponsorship",
                 "ml_research_required", "advanced_degree_required",
                 "customer_facing", "gap_friendly_language",
                 "years_experience_min", "years_experience_max",
                 "comp_min", "comp_max")


def call(prompt, model, base_url, api_key, thinking, timeout):
    # Must match what llm.py actually sends. Omitting temperature
    # here measures the provider's default sampling, not production: it
    # inflates run-to-run disagreement and makes any A/B look noisier than
    # the pipeline really is.
    body = {"model": model,
            "temperature": llm.DEFAULT_TEMPERATURE,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": prompt}]}
    if not thinking:
        body["thinking"] = {"type": "disabled"}
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {api_key}"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode())
    content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
    return content, time.time() - t0


def extract_both(job, model, base_url, api_key, timeout, arms):
    prompt = extract.build_prompt(job)
    out = {}
    for label, thinking in arms:
        try:
            content, elapsed = call(prompt, model, base_url, api_key,
                                    thinking, timeout)
        except Exception as e:                            # noqa: BLE001
            return job["id"], None, f"{type(e).__name__}: {str(e)[:100]}"
        out[label] = (extract.normalize(llm.parse_json(content)), elapsed)
    return job["id"], out, None


def jaccard(a, b):
    sa, sb = set(json.loads(a or "[]")), set(json.loads(b or "[]"))
    if not sa and not sb:
        return 1.0
    return len(sa & sb) / len(sa | sb) if (sa | sb) else 1.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="MODEL@BASE_URL@API_KEY")
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--arms", choices=("on-off", "off-off", "on-on"),
                    default="on-off",
                    help="off-off measures the FLOOR: how much a field "
                         "disagrees with itself at fixed settings. A field "
                         "whose on-off gap matches its off-off gap is simply "
                         "ambiguous, and reasoning was never buying accuracy "
                         "there.")
    args = ap.parse_args()

    a, b = args.arms.split("-")
    arms = (("on", a == "on"), ("off", b == "on"))

    model, base_url, api_key = args.model.split("@", 2)

    conn = dbconn.connect_or_exit("compare-extract", schema=schema.SCHEMA)
    cfgs = [relevance.for_profile(p) for p in profiles.load_active(conn)]
    jobs = extract.select_unextracted_jobs(conn, args.n, cfgs)
    conn.close()
    if not jobs:
        print("compare-extract: nothing left to extract -- nothing to compare.")
        return

    print(f"compare-extract: {len(jobs)} postings x 2 runs on {model} [arms={args.arms}]\n")
    pairs, errors = [], []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        for job_id, out, err in pool.map(
                lambda j: extract_both(j, model, base_url, api_key,
                                       args.timeout, arms),
                jobs):
            (errors if err else pairs).append((job_id, out or err))

    usable = [(jid, o) for jid, o in pairs
              if o and o["on"][0] and o["off"][0]]
    print(f"  pairs           {len(usable)} usable, {len(pairs) - len(usable)} "
          f"unparseable on one side, {len(errors)} failed")
    if not usable:
        sys.exit(1)

    lat_on = statistics.median(o["on"][1] for _, o in usable)
    lat_off = statistics.median(o["off"][1] for _, o in usable)
    print(f"  latency median  on {lat_on:.1f}s   off {lat_off:.1f}s "
          f"({lat_on / lat_off:.1f}x faster)\n")

    print(f"  FIELD AGREEMENT (arms: {args.arms})")
    worst = []
    for f in SCALAR_FIELDS:
        agree = sum(1 for _, o in usable if o["on"][0][f] == o["off"][0][f])
        pct = 100 * agree / len(usable)
        worst.append((pct, f))
        flag = "  <-- " if pct < 90 else ""
        print(f"    {f:26} {agree:3}/{len(usable)}  {pct:5.1f}%{flag}")

    stacks = [jaccard(o["on"][0]["tech_stack"], o["off"][0]["tech_stack"])
              for _, o in usable]
    print(f"    {'tech_stack (jaccard)':26} {'':7} {100*statistics.mean(stacks):5.1f}%")

    overall = statistics.mean(pct for pct, _ in worst)
    print(f"\n  mean scalar agreement  {overall:.1f}%")
    disagreeing = sorted(worst)[:3]
    print(f"  weakest fields         "
          f"{', '.join(f'{f} ({p:.0f}%)' for p, f in disagreeing)}")

    # Deliberately not a verdict. An absolute agreement threshold is
    # meaningless on its own: this script's first version called 90.7% "good
    # enough to disable reasoning", when the same fields self-disagreed at
    # 93.9% with reasoning held FIXED -- i.e. it was reading sampling noise as
    # signal. (That noise was itself an artefact of not sending temperature;
    # at the production temperature=0 the floor is ~98.6%.)
    #
    # The only meaningful quantity is the gap between these numbers and the
    # off-off floor measured the same way. Anything inside the floor is noise;
    # anything well below it is the setting genuinely changing the answer.
    if args.arms != "off-off":
        print(f"\n  NOT A VERDICT. Re-run with --arms off-off to get the "
              f"self-consistency floor,\n  and compare per field. A field at "
              f"or above its floor is unaffected;\n  a field 10+ points below "
              f"it is being changed by the setting, not by chance.")


if __name__ == "__main__":
    main()
