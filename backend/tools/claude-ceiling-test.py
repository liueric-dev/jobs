#!/usr/bin/env python3
"""
Batch ceiling + token budget experiment for the Claude scoring backend.

Runs claude-bench.py at increasing batch sizes on the same set of jobs,
measures the weekly Claude Pro usage delta before/after each config, and
reports quality + cost-per-percentage-point in one combined table.

USAGE
    python3 tools/claude-ceiling-test.py --n 60 --batch 20 30 40 60
    python3 tools/claude-ceiling-test.py --n 100 --batch 100   # push the limit
"""
import subprocess
import sys
import os
import re
import json
import time

# ingest/ and tools/ sit one level below the pipeline modules they import
# (schema, relevance, llm, ...). Python puts THIS file's directory on sys.path,
# not its parent, so the parent is added by hand. That same insert is what
# reaches lib/ -- there is nothing to install.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse

BENCH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "claude-bench.py")


def run_bench(n, batch_size, model="haiku", extra_args=None):
    """Run claude-bench.py for one config and capture its stdout."""
    cmd = [sys.executable, BENCH,
           "--n", str(n),
           "--model", model,
           "--batch", str(batch_size),
           "--vs-production"]
    if extra_args:
        cmd.extend(extra_args)
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    elapsed = time.time() - t0
    return r.stdout, r.stderr, elapsed, r.returncode


def parse_summary(output):
    """Extract key metrics from claude-bench.py's summary block."""
    metrics = {}
    # json_ok
    m = re.search(r'json_ok\s+(\d+)/(\d+)\s+\((\d+)%\)', output)
    if m:
        metrics["json_ok"] = int(m.group(1))
        metrics["json_total"] = int(m.group(2))
        metrics["json_pct"] = int(m.group(3))
    # latency
    m = re.search(r'latency/batch\s+median\s+([\d.]+)s\s+max\s+([\d.]+)s', output)
    if m:
        metrics["latency_median"] = float(m.group(1))
        metrics["latency_max"] = float(m.group(2))
    # fit_score
    m = re.search(r'fit_score\s+median\s+(\d+)\s+range\s+(\d+)-(\d+)\s+stdev\s+([\d.]+)', output)
    if m:
        metrics["score_median"] = int(m.group(1))
        metrics["score_min"] = int(m.group(2))
        metrics["score_max"] = int(m.group(3))
        metrics["score_stdev"] = float(m.group(4))
    # cost
    m = re.search(r'cost\s+\$([\d.]+)\s+total\s+\(\$([\d.]+)/job\)', output)
    if m:
        metrics["cost_total"] = float(m.group(1))
        metrics["cost_per_job"] = float(m.group(2))
    # tokens per job -- values may have decimal points (e.g. "1,800.0")
    m = re.search(r'per job\s+in\s+([\d,]+(?:\.\d+)?)\s+out\s+([\d,]+(?:\.\d+)?)', output)
    if m:
        metrics["tokens_in_per_job"] = int(float(m.group(1).replace(",", "")))
        metrics["tokens_out_per_job"] = int(float(m.group(2).replace(",", "")))
    # track agreement vs production
    m = re.search(r'vs production\s+track_agree\s+(\d+)/(\d+)\s+score_delta mean\s+([\d.]+)\s+max\s+(\d+)', output)
    if m:
        metrics["track_agree"] = int(m.group(1))
        metrics["track_total"] = int(m.group(2))
        metrics["score_delta_mean"] = float(m.group(3))
        metrics["score_delta_max"] = int(m.group(4))
    return metrics


def main():
    ap = argparse.ArgumentParser(
        description="Find the batch size ceiling and measure token budget impact.")
    ap.add_argument("--n", type=int, required=True,
                    help="number of jobs to score per config")
    ap.add_argument("--batch", type=int, nargs="+", required=True,
                    help="batch sizes to test")
    ap.add_argument("--model", default="haiku")
    args = ap.parse_args()

    print(f"EXPERIMENT: n={args.n}, model={args.model}, batches={args.batch}")
    print(f"Token budget tracked via total_cost_usd from Claude's JSON envelope.\n")

    print(f"{'='*80}\n")

    results = []

    for bs in args.batch:
        print(f"\n[batch={bs}] running {args.n} jobs...")
        t0 = time.time()

        stdout, stderr, wall, rc = run_bench(args.n, bs, args.model)

        metrics = parse_summary(stdout)
        metrics["batch_size"] = bs
        metrics["wall_clock"] = time.time() - t0
        metrics["stderr_snippet"] = stderr[:200] if stderr else ""

        results.append(metrics)

        # Print the full bench output for this config (so we keep the detail)
        print(stdout)

        print(f"  WALL: {metrics['wall_clock']:.0f}s")

        # Early stop if quality degraded badly
        if metrics.get("json_pct", 100) < 80:
            print(f"\n*** STOPPING: json_ok dropped to {metrics['json_pct']}% "
                  f"at batch={bs} — quality ceiling found ***")
            break

    # Final combined table
    print(f"\n{'='*80}")
    print("COMBINED RESULTS")
    print(f"{'='*80}\n")
    print(f"{'batch':>5} | {'json%':>5} | {'lat_med':>7} | {'stdev':>5} | "
          f"{'$ / job':>8} | {'tok_in':>6} | {'tok_out':>6} | "
          f"{'agree%':>6} | {'delta':>5}")
    print("-" * 80)
    for r in results:
        agree_pct = (100 * r.get("track_agree", 0)
                     / max(r.get("track_total", 1), 1))
        tok_in = r.get("tokens_in_per_job")
        tok_out = r.get("tokens_out_per_job")
        print(f"{r['batch_size']:>5} | "
              f"{r.get('json_pct','?'):>5} | "
              f"{r.get('latency_median','?'):>6.1f}s | "
              f"{r.get('score_stdev','?'):>5.1f} | "
              f"${r.get('cost_per_job','?'):>7.5f} | "
              f"{tok_in or 0:>5,} | "
              f"{tok_out or 0:>5,} | "
              f"{agree_pct:>5.0f}% | "
              f"{r.get('score_delta_mean','?'):>5.1f}")

    print(f"\n{'='*80}")
    print("TOKEN BUDGET EXTRAPOLATION")
    print(f"{'='*80}\n")

    # Claude Pro subscription: $20/mo. The total_cost_usd from Claude's
    # envelope is the API-equivalent cost (what the same tokens would cost
    # on pay-per-token pricing). This lets us estimate how much of the
    # subscription's effective value each run consumes.
    #
    # Claude Pro currently allows ~45 messages per 5 hours on Sonnet
    # (the most limited model). Haiku has a higher cap. Since print-mode
    # calls are billed as API-equivalent, we use cost as the budget unit.
    PRO_MONTHLY_VALUE = 20.0  # $20/mo subscription
    PRO_DAILY_VALUE = PRO_MONTHLY_VALUE / 30

    for r in results:
        bs = r["batch_size"]
        cost_per_job = r.get("cost_per_job", 0)
        if not cost_per_job:
            continue
        print(f"batch={bs} (haiku):")
        print(f"  ${cost_per_job:.5f}/job (API-equivalent cost)")
        nightly = 30 * cost_per_job
        print(f"  Nightly run (30 jobs):    ${nightly:.4f}   "
              f"({nightly/PRO_DAILY_VALUE*100:.1f}% of daily sub value)")
        backfill = 10000 * cost_per_job
        print(f"  Full backfill (10K jobs): ${backfill:.2f}   "
              f"({backfill/PRO_MONTHLY_VALUE*100:.0f}% of monthly sub value)")
        monthly = 30 * cost_per_job * 30
        print(f"  Monthly ongoing (30/day): ${monthly:.2f}   "
              f"({monthly/PRO_MONTHLY_VALUE*100:.0f}% of monthly sub value)")
        print()


if __name__ == "__main__":
    main()
