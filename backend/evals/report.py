"""Turn a Run into something readable, and into something diffable.

THE ONE RULE THIS FILE ENFORCES
    A replayed response carries the latency and token usage of the call that
    originally produced it, months ago, possibly against a different endpoint
    revision. Printing those as though they were measured is how a harness
    produces a confident wrong number -- and cost is exactly the kind of
    number people quote later without rechecking how it was obtained.

    So: render() prints cost and latency only when nothing in the run was
    replayed. Otherwise it says why they are absent and names the flag that
    would produce them. This is the enforcement point for the cache policy;
    runner.py only records the fact.
"""

import json
import os

from . import runner as runner_mod


def _usage_totals(run):
    """Sum the provider usage blocks, tolerating both wire shapes.

    OpenAI-compatible reports prompt_tokens/completion_tokens; the Claude CLI
    envelope reports input_tokens plus separate cache_read/cache_creation
    counts. Summing whichever is present keeps this honest about which
    provider it is talking to rather than inventing a common denominator.
    """
    totals = {}
    for r in run.ok:
        for k, v in (r.usage or {}).items():
            if isinstance(v, (int, float)):
                totals[k] = totals.get(k, 0) + v
    return totals


def render(run):
    counts = run.counts()
    n = len(run.results)
    ok = len(run.ok)
    attempted = n - counts.get(runner_mod.SKIPPED, 0)

    lines = [
        "",
        f"task={run.task}  model={run.model_label}  n={n}",
        "-" * 60,
    ]

    # json_ok is the hard gate: a model that cannot reliably return parseable
    # JSON is unusable here whatever else it does. Reported over ATTEMPTED,
    # not over n -- records the pipeline would never send are not the model's
    # fault. tools/compare-models.py makes the same argument.
    if attempted:
        lines.append(f"  usable        {ok}/{attempted} "
                     f"({100.0 * ok / attempted:.0f}% of attempted)")
    for status in (runner_mod.TOMBSTONE, runner_mod.DEFERRED,
                   runner_mod.SKIPPED):
        if counts.get(status):
            lines.append(f"  {status:<13} {counts[status]}")

    reasons = {}
    for r in run.results:
        if r.status in (runner_mod.TOMBSTONE, runner_mod.DEFERRED) and r.reason:
            key = r.reason.split(":")[0]
            reasons[key] = reasons.get(key, 0) + 1
    if reasons:
        lines.append("  failure kinds " + ", ".join(
            f"{k}={v}" for k, v in sorted(reasons.items())))

    if run.replayed_any:
        replayed = sum(1 for r in run.results if r.replayed)
        lines += [
            "",
            f"  cost/latency  not reported -- {replayed}/{n} responses were "
            f"replayed from cache.",
            "                Those figures belong to the original call, not "
            "to this run.",
            "                Use --no-cache to measure, or --refresh to "
            "re-buy and re-cache.",
        ]
    else:
        lat = sorted(r.latency_s for r in run.ok)
        if lat:
            median = lat[len(lat) // 2]
            lines.append(f"  latency       median {median:.1f}s  "
                         f"min {lat[0]:.1f}s  max {lat[-1]:.1f}s")
        totals = _usage_totals(run)
        if totals:
            lines.append("  tokens        " + ", ".join(
                f"{k}={int(v):,}" for k, v in sorted(totals.items())))
        costs = [r.cost_usd for r in run.ok if r.cost_usd is not None]
        if costs:
            lines.append(f"  cost          ${sum(costs):.4f} total, "
                         f"${sum(costs)/len(costs):.5f}/job (provider-reported)")

    return "\n".join(lines) + "\n"


def write_jsonl(path, run):
    """One row per record, for tracking a metric across runs.

    Carries the prompt digest alongside the model identity: editing
    build_prompt() otherwise makes two runs look comparable when they are
    not, and that is a mistake nobody catches by eye.
    """
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        for r in run.results:
            fh.write(json.dumps({
                "task": run.task,
                "model": run.model_identity,
                "job_id": r.job_id,
                "status": r.status,
                "reason": r.reason,
                "replayed": r.replayed,
                "prompt_sha": r.prompt_sha,
                "normalized": r.normalized,
                # Latency and usage are recorded even when replayed, because
                # the row also records `replayed` -- a consumer can filter.
                # render() is where the judgement about printing them lives.
                "latency_s": r.latency_s,
                "usage": r.usage,
                "cost_usd": r.cost_usd,
            }, sort_keys=True, ensure_ascii=False) + "\n")
    os.replace(tmp, path)
    return len(run.results)
