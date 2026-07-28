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


#: Flip patterns printed per field before the table is truncated. 8 rather
#: than 6 because ai_involvement has exactly 7 and it is the field the gate
#: decision turns on.
_FLIP_ROWS = 8


def _pct(x):
    return "  n/a" if x is None else f"{100.0 * x:4.0f}%"


def _ci(lo, hi):
    return f"[{100.0*lo:3.0f}-{100.0*hi:3.0f}]"


def render_selfcheck(stats, runs, *, platform_order=None):
    """The self-consistency table: per field, per platform, with intervals.

    WHY THREE COLUMNS AND NOT ONE
        `agree2` is repeat 1 vs repeat 2 -- the same two-run protocol that
        produced the provisional n=17 figures, so it is the column those
        numbers and the thresholds in backend/config/criteria.json are
        comparable to. `unan` is all N repeats identical, which is strictly
        harder and answers a different question. `pair` uses every pair and
        is the better point estimate of the agree2 quantity, but carries no
        interval because the pairs from one record are not independent.

    COST AND LATENCY ARE NOT PRINTED HERE AT ALL
        Each pass is rendered by render(), which already refuses them for a
        replayed run. Summing them across passes here would route around
        that check, so this table reports agreement only and defers.
    """
    n_repeat = stats["repeat"]
    lines = [
        "",
        f"self-consistency  model={runs[0].model_label}  "
        f"repeat={n_repeat}  n={stats['n_records']} "
        f"({stats['n_comparable']} usable in every repeat)",
        "  agree2 = repeat 1 vs 2 (comparable to the n=17 figures); "
        "unan = all "
        f"{n_repeat} identical; pair = mean over all pairs",
        "  [lo-hi] is a 95% Wilson interval on the column to its left.",
        "",
    ]

    if stats["not_ok"]:
        lines.append(f"  {len(stats['not_ok'])} record(s) not usable in every "
                     "repeat -- excluded from the field table, listed because "
                     "an answer that parses only sometimes is itself unstable:")
        for job_id, statuses in stats["not_ok"][:10]:
            lines.append(f"    {job_id}: {'/'.join(statuses)}")
        lines.append("")

    order = platform_order or sorted(stats["platform_counts"])
    header = f"  {'field':<26}{'agree2':>7} {'ci':>10}{'unan':>7} {'ci':>10}{'pair':>7}"
    lines += [header, "  " + "-" * (len(header) - 2)]
    for field, blob in stats["fields"].items():
        c = blob["overall"]
        row = (f"  {field:<26}{_pct(c['agree2']):>7} "
               f"{_ci(*c['agree2_ci']):>10}{_pct(c['unanimous']):>7} "
               f"{_ci(*c['unanimous_ci']):>10}{_pct(c['pairwise']):>7}")
        if c["jaccard"] is not None:
            row += f"   jaccard {100.0*c['jaccard']:.0f}%"
        lines.append(row)
    wr = stats["whole_record"]
    lines.append(f"  {'WHOLE RECORD (all fields)':<26}"
                 f"{'':>7} {'':>10}{_pct(wr['rate']):>7} "
                 f"{_ci(*_wilson(wr['k'], wr['n'])):>10}")

    lines += ["", "  per platform -- agree2 with its 95% Wilson interval", ""]
    width = max([26] + [len(p) for p in order])
    head = "  " + "field".ljust(26) + "".join(
        f"{p:>{max(len(p), 16) + 1}}" for p in order)
    lines += [head, "  " + "-" * (len(head) - 2)]
    for field, blob in stats["fields"].items():
        cells = []
        for p in order:
            c = blob["by_platform"].get(p)
            if not c or not c["n"]:
                cells.append(f"{'-':>{max(len(p), 16) + 1}}")
                continue
            txt = f"{100.0*c['agree2']:.0f}% {_ci(*c['agree2_ci'])}"
            cells.append(f"{txt:>{max(len(p), 16) + 1}}")
        lines.append("  " + field.ljust(26) + "".join(cells))
    lines.append("  " + "n".ljust(26) + "".join(
        f"{stats['platform_counts'].get(p, 0):>{max(len(p), 16) + 1}}"
        for p in order))

    flippers = [(f, b) for f, b in stats["fields"].items()
                if b["overall"]["flips"]]
    if flippers:
        lines += ["", "  what the disagreements ARE (non-unanimous records)",
                  ""]
        for field, blob in flippers:
            flips = blob["overall"]["flips"]
            lines.append(f"  {field}")
            for pair, k in flips[:_FLIP_ROWS]:
                lines.append(f"      {k:>3}x  {pair}")
            # Never truncate silently. The first draft of this capped at 6
            # rows with no marker, which hid ai_involvement's seventh group
            # -- and that group crossed the `none` boundary, so the number
            # that was actually being decided on came out one record short.
            if len(flips) > _FLIP_ROWS:
                hidden = sum(k for _, k in flips[_FLIP_ROWS:])
                lines.append(f"      ... {len(flips) - _FLIP_ROWS} more "
                             f"pattern(s), {hidden} record(s); see --out JSON")

    lines += render_ranking(stats)

    lines += ["", "  clean (greenhouse+ashby) vs messy (everything else)", ""]
    for field, blob in stats["fields"].items():
        cl, ms = blob["clean"], blob["messy"]
        if not cl["n"] or not ms["n"]:
            continue
        gap = 100.0 * (cl["agree2"] - ms["agree2"])
        row = (f"  {field:<26}clean {_pct(cl['agree2'])} "
               f"{_ci(*cl['agree2_ci'])} (n={cl['n']})   "
               f"messy {_pct(ms['agree2'])} {_ci(*ms['agree2_ci'])} "
               f"(n={ms['n']})   gap {gap:+.0f}pt")
        if cl["jaccard"] is not None:
            row += (f"   jaccard clean {100.0*cl['jaccard']:.0f}% "
                    f"messy {100.0*ms['jaccard']:.0f}%")
        lines.append(row)
    return "\n".join(lines) + "\n"


def _wilson(k, n):
    from . import metrics
    return metrics.wilson(k, n)


def render_ranking(stats):
    """The `score` block: does the model reproduce its own ORDERING?

    Returns a list of lines, empty when no field has kind `score` -- which is
    every extract run, so the existing table is unchanged.

    WHY THIS IS THE HEADLINE FOR fit_score AND agree2 IS NOT
        fit_score has no ground truth (evals/tasks/score.py), and exact
        agreement on a 0-100 scale understates a model that answered 70 and
        then 72 about the same posting. The quantity that matters is whether
        the shortlist comes out in the same order, because ordering is the
        only thing a fit_score is allowed to influence -- and match_score,
        not fit_score, is what actually orders the list.

    WHY THE TIE HISTOGRAM IS PRINTED HERE
        A coarse scale inflates every agreement number above by pure
        arithmetic: if half the corpus scores 15, two independent passes
        agree on those by coincidence a quarter of the time. p_tie is that
        coincidence rate, so it is the floor under the floor, and printing it
        next to rho is what stops a high agree2 being read as stability.
    """
    blocks = stats.get("ranking") or {}
    if not blocks:
        return []
    lines = ["", "  ranking stability (fields whose kind is `score`)", ""]
    for field, r in sorted(blocks.items()):
        k = r["k"]
        lines.append(f"  {field}")
        lines.append(f"      spearman rho   mean {_num(r['spearman_mean'])}  "
                     f"worst pair {_num(r['spearman_min'])}  "
                     f"({r['spearman_pairs']} pair(s))")
        lines.append(f"      top-{k} overlap  mean "
                     f"{_pct(r.get(f'top{k}_overlap_mean'))}  worst pair "
                     f"{_pct(r.get(f'top{k}_overlap_min'))}")
        lines.append(f"      |diff|         mean {_num(r['mean_abs_diff'])}  "
                     f"max {_num(r['max_abs_diff'])}")
        for tol, cell in sorted(r["bands"].items()):
            lines.append(f"      within +/-{tol:<3}    {_pct(cell['rate'])} "
                         f"{_ci(*cell['ci'])}  ({cell['k']}/{cell['n']}, "
                         "repeat 1 vs 2)")
        for i, hist in enumerate(r["ties"]):
            top = ", ".join(f"{v}x{c}" for v, c in hist["top"][:6])
            lines.append(f"      pass {i + 1} ties    "
                         f"{hist['distinct']} distinct over {hist['n']}, "
                         f"largest {hist['largest']}, "
                         f"p_tie {_pct(hist['p_tie'])}"
                         + (f", undefined {hist['undefined']}"
                            if hist["undefined"] else ""))
            if top:
                lines.append(f"                     {top}")
    return lines


def _num(x, places=3):
    return " n/a" if x is None else f"{x:.{places}f}"


def render_labels(triples, *, inter, intra, measured, label_set=None):
    """The three-quantity table. The ONLY renderer for a model-vs-human figure.

    IT TAKES `Interpretable`, NOT NUMBERS, AND THAT IS THE ENFORCEMENT
        There is deliberately no function in this module that prints a
        model-vs-human rate on its own. labels.Interpretable refuses to be
        constructed without a floor and a ceiling, so the uninterpretable
        report is unrepresentable rather than merely discouraged -- the same
        move task 16 made when its coverage tool refused to print one
        denominator alone, and the same argument the cache policy above makes
        about enforcing at the point of printing.

    THE THREE COLUMNS ARE THE SAME QUANTITY MEASURED THREE WAYS
        floor and ceiling are both metrics.field_cell() outputs, so `agree2`
        means the same thing in each: one pair, one Bernoulli trial per item.
        That is why they can sit in one row and be read against each other.
        `measured` is the model against the majority human answer, also one
        trial per item.

        A model at or below its own floor has not been shown to be wrong about
        the world -- it has been shown to be unstable, and a golden set cannot
        fix that. A model at or above the ceiling has saturated what the label
        can resolve; the remaining disagreement is between people.
    """
    lines = [
        "",
        "model vs human, with the floor and the ceiling it has to be read "
        "between" + (f"  (set={label_set})" if label_set else ""),
        "  floor   = model self-consistency, agree2  (evals selfcheck)",
        "  ceiling = two different people, agree2    (inter-annotator)",
        "  model   = model vs the majority human answer",
        "",
    ]
    header = (f"  {'field':<22}{'floor':>7}{'ceiling':>9}{'model':>7} "
              f"{'ci':>10}{'n':>5}  reading")
    lines += [header, "  " + "-" * (len(header) - 2)]
    for t in triples:
        floor = t.floor.get("agree2")
        ceiling = t.ceiling.get("agree2")
        rate = t.measured.get("rate")
        # The reading is spelled out rather than left to the reader, because
        # the whole failure this table exists to prevent is someone quoting
        # the middle column on its own a month later.
        if rate is not None and floor is not None and rate <= floor:
            reading = "at/below its own floor -- unstable, not wrong"
        elif rate is not None and ceiling is not None and rate >= ceiling:
            reading = "at/above the human ceiling -- label cannot resolve more"
        else:
            reading = "between floor and ceiling"
        lines.append(
            f"  {t.field:<22}{_pct(floor):>7}{_pct(ceiling):>9}"
            f"{_pct(rate):>7} {_ci(*t.measured['ci']):>10}"
            f"{t.measured['n']:>5}  {reading}")

    lines += ["", f"  ceiling from {len(inter['labellers'])} labeller(s): "
                  + (", ".join(inter["labellers"]) or "none")]
    if inter["single_labeller_items"]:
        lines.append("  items with only one labeller (no ceiling): " + ", ".join(
            f"{k}={v}" for k, v in sorted(
                inter["single_labeller_items"].items())))
    if inter["abstained"]:
        # Never folded away, for the reason metrics.py:42 gives about records
        # not usable in every repeat: hiding the answers a labeller could not
        # give flatters every rate above.
        lines.append("  abstentions (excluded from every rate): " + ", ".join(
            f"{k}={v}" for k, v in sorted(inter["abstained"].items())))
    if measured["no_consensus"]:
        lines.append(f"  {measured['no_consensus']} item(s) had no majority "
                     "human answer and are excluded -- a tie is not broken")
    if measured["no_model_output"]:
        lines.append(f"  {len(measured['no_model_output'])} labelled job(s) "
                     "had no model output to compare against")

    if intra["fields"]:
        lines += ["", "  intra-annotator (same person, two rounds) -- the "
                      "weaker ceiling", ""]
        for field, cell in intra["fields"].items():
            lines.append(f"  {field:<22}{_pct(cell['agree2']):>7} "
                         f"{_ci(*cell['agree2_ci'])}  n={cell['n']}")
    else:
        lines += ["", "  intra-annotator: no field has a second round yet."]

    lines += ["", "  vs_each (model against every individual labeller, no "
                  "consensus rule)", ""]
    for field, cell in measured["vs_each"].items():
        # No interval: the pairs from one item are not independent trials, the
        # same argument metrics.py:30 makes about `pairwise`.
        lines.append(f"  {field:<22}{_pct(cell['rate']):>7}  n={cell['n']}  "
                     "(point estimate; no interval -- pairs are dependent)")
    return "\n".join(lines) + "\n"


def write_selfcheck_json(path, stats, runs):
    """The full table as JSON, so a later run can diff against this one."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    payload = dict(stats)
    payload["model"] = runs[0].model_identity
    payload["model_label"] = runs[0].model_label
    payload["task"] = runs[0].task
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, sort_keys=True, indent=2, ensure_ascii=False)
    os.replace(tmp, path)
    return path


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
