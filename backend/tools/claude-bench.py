#!/usr/bin/env python3
"""
Benchmark the Claude Code CLI as a scoring backend before committing to it.

This exists because the existing tools (compare-models.py, cost-test.py) are
hardwired to the OpenAI HTTP wire format and cannot reach the `claude -p`
path -- which shells out to a subscription-authenticated CLI, not an API
endpoint. Before swapping the nightly scorer onto it, we need real numbers
on the four variables that decide whether it's viable at scale:

    1. MODEL        -- haiku vs sonnet (haiku is ~10x cheaper per token and
                       should be plenty for structured extraction, but does
                       it actually hold up on scoring judgment?)
    2. BATCH SIZE   -- how many jobs to score in one CLI call. Startup +
                       system-prompt cache creation dominate a 1-job call;
                       batching amortizes that. But too large risks context
                       bloat and degrades output. Find the sweet spot.
    3. TOKEN USAGE  -- what does it actually cost per job at each batch size?
                       Claude Code reports usage in its JSON envelope; this
                       reads it directly rather than estimating.
    4. SCORING QUALITY -- does haiku agree with sonnet? Does a batch of 10
                       produce the same fit_scores as 10 single calls?
                       Score spread and JSON parse rate matter too -- a model
                       that rates everything 70-75 isn't discriminating.

READ-ONLY. Never writes to `jobs` or `job_scores`. Pulls real unscored
postings (or, with --only-scored, samples from evals/'s frozen fixture and
looks up each one's current score), scores them in memory, prints a
comparison table.

USAGE
    # quick haiku-vs-sonnet check on 20 jobs, single calls
    python3 tools/claude-bench.py --n 20

    # sweep batch sizes to find the throughput sweet spot
    python3 tools/claude-bench.py --n 40 --batch 1 5 10 20

    # just haiku, just throughput -- skip the quality comparison
    python3 tools/claude-bench.py --n 100 --batch 10 25 50 --model haiku

    # compare against existing GLM scores (read-only)
    python3 tools/claude-bench.py --n 30 --model haiku --batch 10 --vs-production

WHAT TO LOOK FOR
    json_ok      -- hard gate. Under ~90% means the model/prompt/batch
                    combination can't be trusted in the nightly run.
    median_lat   -- per-batch wall clock. Multiply by (n/batch) for nightly
                    runtime. Sonnet single-job calls at 8s each * 30 jobs =
                    4 minutes just in latency.
    tok_per_job  -- input + output tokens per job. Cache hit ratio shows
                    whether batching is actually amortizing the prompt.
    fit_score    -- spread (stdev) and range. A flat distribution means the
                    model isn't discriminating between postings.
    agree        -- how often batched haiku agrees with single-call sonnet
                    (treated as reference). Below ~75% track agreement or a
                    large score delta means the cheaper model's judgment
                    diverges enough to change the shortlist.
    cost_per_job -- Claude Code reports real cost in the envelope. This is
                    reconcilable against subscription usage, not a guess.

COST NOTE
    These calls bill against your Claude Pro/Max subscription. A full
    --n 40 --batch sweep across both models costs roughly $0.50-1.50 in
    subscription tokens. Keep --n modest for iteration; raise it for the
    final confirmation run.
"""

import os
import sys
import json
import time
import random
import argparse
import statistics
import subprocess

# ingest/ and tools/ sit one level below the pipeline modules they import
# (schema, relevance, llm, ...). Python puts THIS file's directory on sys.path,
# not its parent, so the parent is added by hand. That same insert is what
# reaches lib/ -- there is nothing to install.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import schema      # noqa: E402
import score       # noqa: E402
from lib import dbconn  # noqa: E402
from evals import corpus  # noqa: E402  (frozen, per-platform-stratified fixtures)

#: T-14: --only-scored used to sample with `ORDER BY first_seen DESC` against
#: production, which silently excludes whole sources (greenhouse/ashby ingest
#: continuously; wwr, hn and lever do not) and makes two runs a week apart
#: incomparable -- see evals/corpus.py's own docstring. This is the fixture
#: that replaces it. The default (unscored) path already used
#: score.select_shortlist(), which is match_score-ordered, not recency --
#: that path is unaffected.
DEFAULT_CORPUS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "evals", "fixtures", "corpus-v1.jsonl")

#: How long to let one claude -p invocation run. Batches of 20 can take
#: 60-90s on haiku; sonnet is slower. 180s gives headroom without hanging
#: forever on a stuck call.
CLI_TIMEOUT = int(os.environ.get("CLAUDE_CLI_TIMEOUT", "240"))

#: Claude Code binary. Found on PATH normally; override for non-standard installs.
CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "claude")

#: Output schema we expect per job, mirroring score.py's REQUIRED_FIELDS.
JOB_RESULT_KEYS = (
    "fit_score", "primary_track", "gap_friendly_signal",
    "key_technologies", "gap_bridging_angle", "risk_factors",
)


def fetch_jobs(n, only_scored=False, corpus_path=DEFAULT_CORPUS):
    """Pull real postings for the benchmark. Unscored by default (the actual
    backlog, via score.select_shortlist -- already match_score-ordered, not
    recency-biased). --only-scored samples from evals/'s frozen, per-platform
    fixture instead of querying production by recency, then looks up each
    sampled job's CURRENT production score so quality is still measured
    against what GLM already produced -- that lookup is inherently live,
    since "what you already trust" means today's score, not a frozen one.
    """
    conn = dbconn.connect_or_exit("claude-bench", schema=schema.SCHEMA)
    persona = score.load_persona()
    profile = schema.resolve_profile(persona)
    if only_scored:
        records = [r for r in corpus.load(corpus_path)
                  if r.get("status") == schema.STATUS_OPEN
                  and (r.get("description_text") or "").strip()]
        picked = random.Random(0).sample(records, min(n, len(records)))  # noqa: S311 (reproducible sampling, not a security use)
        ids = [r["id"] for r in picked]
        rows = conn.execute(
            f"""SELECT job_id, fit_score, primary_track
                FROM {schema.SCORES_TABLE}
                WHERE profile = %s AND job_id = ANY(%s) AND fit_score IS NOT NULL""",
            (profile, ids)).fetchall()
        conn.close()
        scored = {jid: (fit, track) for jid, fit, track in rows}
        jobs = []
        for r in picked:
            if r["id"] not in scored:
                continue
            job = corpus.job_fields(r)
            job.update(corpus.facts_fields(r) or {})
            job["fit_score"], job["primary_track"] = scored[r["id"]]
            jobs.append(job)
        return jobs
    # select_shortlist, not a relevance-tier query: narrative candidates
    # are chosen by match_score now, so the benchmark runs against the
    # same postings the pipeline would have spent a call on.
    jobs = score.select_shortlist(conn, n, profile)
    conn.close()
    return jobs


def build_batch_prompt(persona, jobs):
    """One prompt that asks for a JSON array of results, one per job.

    Keeping the persona/instructions identical to score.build_prompt() means
    quality comparisons are apples-to-apples with the single-job path -- the
    only variable is whether the model handles N-at-once, not whether it was
    asked differently.
    """
    buckets = "\n".join(
        f"- {name}: {b['description']} ({b['fit_signal']})"
        for name, b in persona["buckets"].items())
    strengths = "\n".join(f"- {s}" for s in persona["strengths"])
    gaps = "\n".join(f"- {g}" for g in persona["honest_gaps"])

    job_blocks = []
    for i, j in enumerate(jobs):
        desc = (j.get("description_text") or "")[:3000]
        job_blocks.append(
            f'JOB {i+1}:\n'
            f'Title: {j.get("title")}\n'
            f'Company: {j.get("company_name")}\n'
            f'Location: {j.get("location_raw")}\n'
            f'Source: {j.get("platform")}\n'
            f'Description: {desc}')
    job_list = "\n\n".join(job_blocks)

    return f"""You are evaluating {len(jobs)} job postings for fit against a specific candidate's background. Respond with ONLY a single JSON object containing a "results" array -- no markdown code fences, no explanation before or after. The array must have exactly {len(jobs)} elements, one per job, in the order given.

CANDIDATE BACKGROUND:
{persona['background_summary']}

STRENGTHS:
{strengths}

HONEST GAPS:
{gaps}

POSITIONING BUCKETS:
{buckets}

SCORING INSTRUCTIONS:
{persona['scoring_instructions']}

JOB POSTINGS TO EVALUATE:

{job_list}

Respond with exactly this JSON shape (no other text):
{{
  "results": [
    {{
      "fit_score": <integer 0-100>,
      "primary_track": "<one of: Core SWE, AI Integration, Bridge & Solutions, Re-Entry & Growth, Poor Fit>",
      "gap_friendly_signal": <true or false>,
      "key_technologies": ["...", "..."],
      "gap_bridging_angle": "<1-2 concrete sentences specific to this posting>",
      "risk_factors": ["...", "..."]
    }},
    ... ({len(jobs)} total, one per job in order)
  ]
}}"""


def call_claude(prompt, model, timeout=CLI_TIMEOUT):
    """Run one `claude -p` call. Returns (content_str, usage_dict, cost_usd, elapsed_s, error).

    --output-format json gives an envelope whose "result" field is the model's
    text answer and whose "usage" / "total_cost_usd" fields carry the real
    accounting. We read those directly rather than estimating tokens.

    --model haiku / sonnet selects within the subscription. haiku is the
    right default for structured extraction -- this function exists partly
    to confirm that.
    """
    cmd = [CLAUDE_BIN, "-p", prompt,
           "--output-format", "json",
           "--max-turns", "1",
           "--model", model]
    t0 = time.time()
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, {}, 0.0, time.time() - t0, f"timeout after {timeout}s"
    elapsed = time.time() - t0

    if proc.returncode != 0:
        return None, {}, 0.0, elapsed, f"exit {proc.returncode}: {proc.stderr[:200]}"

    try:
        env = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        return None, {}, 0.0, elapsed, f"envelope not JSON: {e}; stdout[0:200]={proc.stdout[:200]}"

    if env.get("is_error"):
        return None, {}, 0.0, elapsed, f"claude error: {env.get('result','')[:200]}"

    content = env.get("result", "")
    usage = env.get("usage") or {}
    # Per-model breakdown lives in modelUsage; flatten for convenience.
    cost = env.get("total_cost_usd", 0.0) or 0.0
    return content, usage, cost, elapsed, None


def extract_results(content, n_expected):
    """Parse the batch JSON. Tolerant: strip fences, find the outer object,
    pull results[]. Returns (list_of_dicts_or_None, parse_error)."""
    if not content:
        return None, "empty content"
    t = content.strip()
    # Strip markdown fences the way score.py / llm.parse_json do.
    if t.startswith("```"):
        t = t.split("```")
        # ["", "json\n{...}\n", ""] -- take the middle
        t = t[1] if len(t) > 1 else t[0]
        if t.startswith("json"):
            t = t[4:]
        t = t.strip()
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end == -1:
        return None, "no JSON object found"
    try:
        obj = json.loads(t[start:end + 1])
    except json.JSONDecodeError as e:
        return None, f"JSON decode: {e}"
    results = obj.get("results") if isinstance(obj, dict) else None
    if not isinstance(results, list):
        return None, "no 'results' array in response"
    if len(results) != n_expected:
        return None, f"expected {n_expected} results, got {len(results)}"
    return results, None


def run_batch(jobs, persona, model, batch_size):
    """Score `jobs` in chunks of `batch_size`. Returns a list of per-job
    result dicts plus aggregate usage. Each result dict carries the parsed
    scoring fields, the token usage attributed to that job (pro-rated from
    the batch), and the batch latency."""
    all_results = []
    for i in range(0, len(jobs), batch_size):
        batch = jobs[i:i + batch_size]
        prompt = build_batch_prompt(persona, batch)
        content, usage, cost, elapsed, err = call_claude(prompt, model)
        if err:
            for j in batch:
                all_results.append({
                    "job": j, "result": None, "error": err,
                    "tokens": {}, "cost": 0.0, "latency_s": elapsed})
            continue
        parsed, perr = extract_results(content, len(batch))
        if perr or parsed is None:
            for j in batch:
                all_results.append({
                    "job": j, "result": None, "error": perr or "no results",
                    "tokens": {}, "cost": 0.0, "latency_s": elapsed})
            continue
        # Pro-rate usage across the batch. Cache tokens belong to the shared
        # prefix, so dividing them across jobs shows the amortization.
        per_job_tokens = {k: v / len(batch) for k, v in usage.items()
                          if isinstance(v, (int, float))}
        per_job_cost = cost / len(batch)
        for j, r in zip(batch, parsed):
            ok = (isinstance(r, dict)
                  and all(k in r for k in JOB_RESULT_KEYS)
                  and isinstance(r.get("fit_score"), (int, float)))
            all_results.append({
                "job": j, "result": r if ok else None,
                "error": None if ok else "missing/invalid fields",
                "tokens": per_job_tokens, "cost": per_job_cost,
                "latency_s": elapsed / len(batch)})
    return all_results


def summarize(label, results, reference=None, production=None):
    """Print a summary block for one (model, batch_size) combination.
    `reference` is single-call sonnet results for quality comparison;
    `production` is existing GLM scores from the DB."""
    ok = [r for r in results if r["result"]]
    errs = [r for r in results if r["error"]]
    scores = [r["result"]["fit_score"] for r in ok]
    lats = [r["latency_s"] * _batch_of(r) for r in results]

    print(f"\n{'='*70}\n{label}\n{'='*70}")
    print(f"  jobs           {len(results)}")
    print(f"  json_ok        {len(ok)}/{len(results)}"
          f"   ({100*len(ok)/max(len(results),1):.0f}%)")
    if lats:
        print(f"  latency/batch  median {statistics.median(lats):.1f}s"
              f"   max {max(lats):.1f}s")
    if scores:
        print(f"  fit_score      median {statistics.median(scores):.0f}"
              f"   range {min(scores):.0f}-{max(scores):.0f}"
              f"   stdev {statistics.pstdev(scores):.1f}")

    # Token usage -- sum then per-job. Note: Claude Code's envelope reports
    # input_tokens as ONLY the new uncached input; cache_read and cache_creation
    # are separate. Total input is all three combined.
    if ok:
        tot_in_new = sum(r["tokens"].get("input_tokens", 0) for r in ok)
        tot_out = sum(r["tokens"].get("output_tokens", 0) for r in ok)
        cache_read = sum((r["tokens"].get("cache_read_input_tokens", 0)
                          or 0) for r in ok)
        cache_create = sum((r["tokens"].get("cache_creation_input_tokens", 0)
                            or 0) for r in ok)
        tot_input_real = tot_in_new + cache_read + cache_create
        cost = sum(r["cost"] for r in ok)
        print(f"  tokens         in {tot_in_new:,} (new) + {cache_read:,} (cached) "
              f"+ {cache_create:,} (cache write) = {tot_input_real:,} total")
        print(f"                 out {tot_out:,}")
        print(f"  per job        in {tot_input_real//len(ok):,}  out {tot_out//len(ok):,}")
        if tot_input_real:
            print(f"  cache hit      {100*cache_read/tot_input_real:.0f}% of total input")
        print(f"  cost           ${cost:.4f} total  (${cost/len(ok):.5f}/job)")

    # Quality vs reference (single-call sonnet).
    if reference:
        ref_map = {id(r["job"]): r["result"] for r in reference if r["result"]}
        pairs = [(r["result"], ref_map[id(r["job"])])
                 for r in ok if id(r["job"]) in ref_map]
        if pairs:
            track_agree = sum(1 for a, b in pairs
                              if a.get("primary_track") == b.get("primary_track"))
            deltas = [abs(a["fit_score"] - b["fit_score"]) for a, b in pairs]
            print(f"  vs sonnet-1x   track_agree {track_agree}/{len(pairs)}"
                  f"   score_delta mean {statistics.mean(deltas):.1f}"
                  f"  max {max(deltas):.0f}")

    # Quality vs production GLM scores.
    if production:
        prod_map = {r["job"]["id"]: r["job"] for r in results
                    if r["job"].get("fit_score") is not None}
        pairs = [(r["result"], r["job"])
                 for r in ok if r["job"].get("fit_score") is not None]
        if pairs:
            track_agree = sum(1 for a, j in pairs
                              if a.get("primary_track") == j.get("primary_track"))
            deltas = [abs(a["fit_score"] - j["fit_score"]) for a, j in pairs]
            print(f"  vs production  track_agree {track_agree}/{len(pairs)}"
                  f"   score_delta mean {statistics.mean(deltas):.1f}"
                  f"  max {max(deltas):.0f}")

    if errs:
        uniq = list(dict.fromkeys(e["error"] for e in errs))
        print(f"  errors         {len(errs)}")
        for e in uniq[:3]:
            print(f"    - {e}")


def _batch_of(result):
    """Latency stored per-job but we want per-batch for the summary -- this
    helper isn't currently used for display but kept for future grouping."""
    return 1


def main():
    ap = argparse.ArgumentParser(
        description="Benchmark Claude Code CLI as a scoring backend.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=20,
                    help="jobs to score per configuration (default 20)")
    ap.add_argument("--model", action="append",
                    help="claude model(s) to test: haiku, sonnet "
                         "(default: both). Repeatable.")
    ap.add_argument("--batch", type=int, nargs="+", default=[1, 5],
                    help="batch sizes to sweep (default: 1 5). "
                         "Each job scored once per size.")
    ap.add_argument("--reference", action="store_true",
                    help="run single-call sonnet as a quality reference "
                         "(expensive: ~$0.05/job, ~8s/job). Off by default.")
    ap.add_argument("--vs-production", action="store_true",
                    help="also compare against existing GLM scores "
                         "(requires --only-scored or pre-scored jobs)")
    ap.add_argument("--only-scored", action="store_true",
                    help="use jobs that already have a production score")
    ap.add_argument("--corpus", default=DEFAULT_CORPUS,
                    help="frozen evals fixture --only-scored samples from "
                         "(default: evals/fixtures/corpus-v1.jsonl)")
    ap.add_argument("--samples", type=int, default=0,
                    help="print this many side-by-side job examples")
    args = ap.parse_args()

    models = args.model or ["haiku", "sonnet"]
    jobs = fetch_jobs(args.n, args.only_scored, args.corpus)
    if not jobs:
        print("claude-bench: no jobs matched.")
        sys.exit(1)
    print(f"claude-bench: {len(jobs)} jobs, models={models}, "
          f"batch sizes={args.batch}")

    persona = score.load_persona()

    # Reference: single-call sonnet, produced once and reused as the quality
    # baseline. Sonnet-1x is treated as ground truth for track agreement.
    # EXPENSIVE: costs ~$0.05/job in subscription tokens and ~8s/job in wall
    # time. Skip it unless explicitly requested with --reference.
    reference = None
    if args.reference:
        print("\n[reference] scoring with sonnet, batch=1 (ground truth)...")
        reference = run_batch(jobs, persona, "sonnet", 1)
        summarize("REFERENCE: sonnet @ batch=1", reference)

    all_runs = []
    for model in models:
        for bs in args.batch:
            # Skip the reference config -- already done.
            if model == "sonnet" and bs == 1 and reference:
                all_runs.append((f"{model} @ batch={bs}", reference))
                continue
            label = f"{model} @ batch={bs}"
            print(f"\n[{label}] running...")
            results = run_batch(jobs, persona, model, bs)
            summarize(label, results,
                      reference=reference if model != "sonnet" or bs != 1 else None,
                      production=args.vs_production)
            all_runs.append((label, results))

    if args.samples:
        print(f"\n{'='*70}\nSIDE BY SIDE\n{'='*70}")
        for job in jobs[:args.samples]:
            print(f"\n{job['title']} — {job['company_name']}")
            if job.get("fit_score") is not None:
                print(f"  {'[production]':<22} {job['fit_score']}  "
                      f"{job.get('primary_track')}")
            for label, results in all_runs:
                r = next((x["result"] for x in results
                          if x["job"].get("id") == job.get("id")), None)
                if r:
                    print(f"  {label[:20]:<22} {r.get('fit_score')}  "
                          f"{r.get('primary_track')}"
                          f"  | {str(r.get('gap_bridging_angle'))[:60]}")
                else:
                    print(f"  {label[:20]:<22} FAILED")

    # Final recommendation hint.
    if len(all_runs) > 1:
        print(f"\n{'='*70}\nQUICK READ\n{'='*70}")
        print("(pick the cheapest config with json_ok >= ~90% and "
              "track_agree >= ~75% vs sonnet-1x)")
        for label, results in all_runs:
            ok = [r for r in results if r["result"]]
            json_rate = 100*len(ok)/max(len(results),1)
            cost = sum(r["cost"] for r in ok) / len(ok) if ok else 0
            med_score = statistics.median(
                [r["result"]["fit_score"] for r in ok]) if ok else 0
            print(f"  {label:<24} json_ok={json_rate:>3.0f}%  "
                  f"${cost:.5f}/job  median_fit={med_score:.0f}")


if __name__ == "__main__":
    main()
