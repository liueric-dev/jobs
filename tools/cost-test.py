#!/usr/bin/env python3
"""
Measure what a scoring run actually costs, using real postings and real usage.

WHY THIS IS NOT AN ESTIMATE
    Cost per job was previously guessed as (prompt_chars / 4) * input_rate.
    Every part of that is wrong in a way that matters:

      * chars/4 overstates the token count -- the real ratio on these prompts
        is closer to 6.8, so the guess was ~1.7x high.
      * It ignored the prompt cache. 1024 of ~1060 input tokens are a
        byte-identical persona prefix, and DeepSeek bills cache hits at 1/50th
        the miss rate. Input is nearly free; the estimate treated it as the
        whole bill.
      * It ignored reasoning tokens entirely, which are billed as output and
        are the single largest line item -- on deepseek-v4-flash they were
        ~70% of all output.

    So this reads `usage` off each response instead of predicting it. The
    numbers it prints are reconcilable against a provider's billing page,
    which is the only real test.

READ-ONLY. Scores nothing, writes nothing to `jobs` or `job_scores`.
It pulls real unscored postings, builds the real prompt, and throws the
answers away. The API calls are billable -- that is the point.

USAGE
    python3 tools/cost-test.py \\
        --model "deepseek-v4-flash@$DEEPSEEK_BASE_URL@$DEEPSEEK_API_KEY" \\
        --n 100

    # what turning off reasoning would cost, and save
    python3 tools/cost-test.py --model "..." --n 100 --no-thinking

    # a model this script has no price for
    python3 tools/cost-test.py --model "..." --n 50 \\
        --price-in 0.14 --price-cached 0.0028 --price-out 0.28

PRICES are dollars per million tokens and change without notice -- PRICES
below is a convenience, not an authority. Pass --price-* to override, and
check the provider's page before trusting any total.
"""

import os
import sys
import json
import time
import argparse
import statistics
import urllib.request
import urllib.error
import concurrent.futures

# ingest/ and tools/ sit one level below the pipeline modules they import
# (schema, relevance, llm, ...). Python puts THIS file's directory on sys.path,
# not its parent, so the parent is added by hand. That same insert is what
# reaches lib/ -- there is nothing to install.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import schema      # noqa: E402
import relevance   # noqa: E402
import score       # noqa: E402
import extract     # noqa: E402
import profiles    # noqa: E402
import llm         # noqa: E402
from lib import dbconn  # noqa: E402

#: $ per million tokens: (input_miss, input_cache_hit, output).
#: Output covers reasoning tokens too -- they are billed as output.
PRICES = {
    "deepseek-v4-flash": (0.14, 0.0028, 0.28),
    "deepseek-v4-pro": (0.435, 0.003625, 0.87),
    "glm-4.5-flash": (0.0, 0.0, 0.0),          # free tier
    "gemini-3.6-flash": (0.0, 0.0, 0.0),       # free tier (20 req/day)
    "gemini-3.5-flash-lite": (0.0, 0.0, 0.0),  # free tier
}


def price_for(model, args):
    if args.price_in is not None:
        return (args.price_in, args.price_cached or 0.0, args.price_out or 0.0)
    for name, p in PRICES.items():
        if model.startswith(name):
            return p
    return None


def call_with_usage(prompt, model, base_url, api_key, thinking, timeout):
    """One completion. Returns (content, usage_dict, elapsed_seconds)."""
    # Must match what llm.py actually sends. Omitting temperature
    # here measures the provider's default sampling, not production: it
    # inflates run-to-run disagreement and makes any A/B look noisier than
    # the pipeline really is.
    body = {"model": model,
            "temperature": llm.DEFAULT_TEMPERATURE,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": prompt}]}
    if not thinking:
        # Verified against deepseek-v4-flash; other backends ignore it.
        body["thinking"] = {"type": "disabled"}

    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {api_key}"})
    start = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode())
    elapsed = time.time() - start
    content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
    return content, data.get("usage") or {}, elapsed


def usage_fields(u):
    """Normalise the usage block across providers.

    Only DeepSeek reports the cache split and reasoning tokens by these
    names; everything else falls back to "all input was a miss, no
    reasoning", which is the conservative reading -- it can overstate cost
    but never understates it.
    """
    prompt_tokens = u.get("prompt_tokens", 0)
    hit = u.get("prompt_cache_hit_tokens")
    if hit is None:
        hit = (u.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
    miss = u.get("prompt_cache_miss_tokens")
    if miss is None:
        miss = max(0, prompt_tokens - (hit or 0))
    reasoning = (u.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0
    return {"prompt": prompt_tokens, "hit": hit or 0, "miss": miss,
            "out": u.get("completion_tokens", 0), "reasoning": reasoning}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True,
                    help="MODEL@BASE_URL@API_KEY")
    ap.add_argument("--stage", choices=("score", "extract"), default="score",
                    help="which prompt to measure (default: score)")
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--no-thinking", action="store_true",
                    help="send thinking={'type':'disabled'} (DeepSeek)")
    ap.add_argument("--price-in", type=float, help="$/M input (cache miss)")
    ap.add_argument("--price-cached", type=float, help="$/M input (cache hit)")
    ap.add_argument("--price-out", type=float, help="$/M output")
    ap.add_argument("--backfill", type=int, default=5200,
                    help="rows to extrapolate a one-time backfill over")
    ap.add_argument("--daily", type=int, default=400,
                    help="rows/day to extrapolate a monthly figure over")
    args = ap.parse_args()

    try:
        model, base_url, api_key = args.model.split("@", 2)
    except ValueError:
        print("--model must be MODEL@BASE_URL@API_KEY")
        sys.exit(2)

    conn = dbconn.connect_or_exit("cost-test", schema=schema.SCHEMA)
    # The two stages have different prompts and different economics -- the
    # extraction prompt carries no persona, which is the whole reason its
    # prefix caches across every job AND every profile. Measuring one and
    # assuming the other is how the stale figure in this file's docstring
    # happened.
    if args.stage == "extract":
        cfgs = [relevance.for_profile(p) for p in profiles.load_active(conn)]
        jobs = extract.select_unextracted_jobs(conn, args.n, cfgs)
        required = extract.REQUIRED_FIELDS
        build = extract.build_prompt
    else:
        persona = score.load_persona()
        profile = schema.resolve_profile(persona)
        jobs = score.select_unscored_jobs(conn, args.n, profile, relevance.load())
        required = score.REQUIRED_FIELDS
        build = lambda j: score.build_prompt(persona, j)  # noqa: E731
    conn.close()
    if not jobs:
        print(f"cost-test: no {args.stage} candidates matched -- "
              f"nothing to measure.")
        return

    prompts = [build(j) for j in jobs]
    print(f"cost-test: {len(prompts)} {args.stage} calls to {model} "
          f"(thinking={'off' if args.no_thinking else 'on'}, "
          f"workers={args.workers})\n")

    results, errors = [], []

    def one(prompt):
        try:
            content, usage, elapsed = call_with_usage(
                prompt, model, base_url, api_key,
                not args.no_thinking, args.timeout)
        except Exception as e:                       # noqa: BLE001
            return ("err", f"{type(e).__name__}: {str(e)[:120]}")
        parsed = llm.parse_json(content)
        ok = llm.has_fields(parsed, required)
        return ("ok", (usage_fields(usage), elapsed, ok,
                       (parsed or {}).get("fit_score")))

    started = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        for kind, payload in pool.map(one, prompts):
            (results if kind == "ok" else errors).append(payload)
    wall = time.time() - started

    if not results:
        print(f"cost-test: every call failed. First: {errors[0]}")
        sys.exit(1)

    n = len(results)
    tot = {k: sum(r[0][k] for r in results) for k in
           ("prompt", "hit", "miss", "out", "reasoning")}
    lat = sorted(r[1] for r in results)
    json_ok = sum(1 for r in results if r[2])
    scores = [r[3] for r in results if isinstance(r[3], (int, float))]

    print(f"  calls        {n} ok, {len(errors)} failed")
    print(f"  json_ok      {json_ok}/{n} ({100*json_ok//n}%)")
    print(f"  wall clock   {wall:.1f}s   latency median {statistics.median(lat):.1f}s"
          f"  max {lat[-1]:.1f}s")
    if scores:
        print(f"  fit_score    median {statistics.median(scores):.0f}  "
              f"range {min(scores)}-{max(scores)}  "
              f"stdev {statistics.stdev(scores):.1f}" if len(scores) > 1 else "")
    print()
    print(f"  TOKENS (total over {n} calls)")
    print(f"    input        {tot['prompt']:>9,}   "
          f"({tot['hit']:,} cached, {tot['miss']:,} uncached)")
    print(f"    output       {tot['out']:>9,}   "
          f"(of which reasoning: {tot['reasoning']:,})")
    print(f"    per job      input {tot['prompt']//n:,}  output {tot['out']//n:,}")
    if tot["prompt"]:
        print(f"    cache hit    {100*tot['hit']//tot['prompt']}% of input")

    prices = price_for(model, args)
    if prices is None:
        print(f"\n  No price on file for {model}. Re-run with "
              f"--price-in/--price-cached/--price-out to get a cost.")
        return
    p_miss, p_hit, p_out = prices
    cost = (tot["miss"] * p_miss + tot["hit"] * p_hit + tot["out"] * p_out) / 1e6
    per_job = cost / n

    print(f"\n  COST at ${p_miss}/${p_hit}/${p_out} per M (miss/hit/out)")
    if cost == 0:
        print(f"    free tier -- no charge, but check the request cap")
        return
    print(f"    this run     ${cost:.4f}  ({n} jobs)")
    print(f"    per job      ${per_job:.6f}")
    print(f"    backfill     ${per_job * args.backfill:.2f}  ({args.backfill:,} jobs)")
    print(f"    ongoing      ${per_job * args.daily * 30:.2f}/mo  "
          f"({args.daily}/day)")
    out_share = (tot["out"] * p_out) / 1e6 / cost * 100
    print(f"    output is {out_share:.0f}% of the bill"
          + (f", reasoning alone {(tot['reasoning']*p_out)/1e6/cost*100:.0f}%"
             if tot["reasoning"] else ""))

    if errors:
        print(f"\n  {len(errors)} error(s), first: {errors[0]}")


if __name__ == "__main__":
    main()
