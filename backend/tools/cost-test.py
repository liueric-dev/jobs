#!/usr/bin/env python3
"""
Measure what a scoring run actually SPENDS -- in requests, seconds and
concurrency. Dollars are reported last, because they stopped being the
constraint.

WHY THIS TOOL WAS REWRITTEN (task 04)
    The old version answered "what does a call cost in dollars", and
    docs/SCORING.md's own conclusion says that is the wrong question:
    "token cost has stopped being the interesting constraint. What binds is
    request rate limits, wall-clock, and ranking quality." Everything under
    that sentence was denominated in dollars anyway.

    Three things changed with it:

      * THE CORPUS IS FROZEN. The old version selected live, with
        `select_unextracted_jobs`/`select_shortlist` against production, so
        the corpus changed every night and no two runs were comparable --
        a slower p95 was equally well explained by a busier endpoint or by a
        batch of longer postings. It now reads a fixture and pins the sample
        by sorted job_id. See evals/corpus.py's WHY FREEZE.
      * IT CALLS THROUGH llm.call_detailed(). The old version rebuilt the
        HTTP request by hand, which silently dropped ratelimit.acquire() --
        so a measurement run could spend the budget the nightly run depends
        on. llm.py:214 names this tool as one of the four that did it.
      * IT MEASURES AT THE PIPELINE'S CONCURRENCY. Latency measured at
        workers=1, which was the old default, is not the latency the
        pipeline sees. Default workers now mirror EXTRACT_MAX_WORKERS (3)
        and SCORE_MAX_WORKERS (5).

WHAT IT REPORTS, AND WHY EACH ONE
    quota            what the provider will actually refuse to serve. On
                     DeepSeek that is a concurrency ceiling, not a daily
                     request budget -- see PROVIDER_LIMITS.
    wall clock p50   the number that decides whether the nightly extraction
    /p95             pass fits inside the systemd window. p95, not max: one
                     slow call is weather, the 95th percentile is the tail
                     a 40-call batch will actually hit.
    cache hit rate   on the CURRENT prompt. The 94% in docs/SCORING.md was
                     measured months ago against a prompt that has since
                     changed, and the provider's caching behaviour is not a
                     contract.
    tokens in/out    retained. Still the input to any future paid tier.
    failure/deferral a call that 429s is DEFERRED, not failed: extract.py
                     writes nothing and retries it tomorrow. A permanent
                     failure is tombstoned and never retried. Those two need
                     opposite responses, so they are counted separately.

READ-ONLY. Writes nothing to `jobs`, `job_facts` or `job_scores`, and does
not touch the database at all -- the fixture is the corpus. The API calls are
billable; that is the point.

USAGE
    cd backend
    python3 tools/cost-test.py --stage extract --n 60
    python3 tools/cost-test.py --stage score --n 24
    python3 tools/cost-test.py --stage extract --n 60 \\
        --model "deepseek-v4-flash@$DEEPSEEK_BASE_URL@env:DEEPSEEK_API_KEY"

Prefer `env:VARNAME` in --model. A spec string reaches stdout and any log
that captures it; a literal key there is a key on disk.

--no-thinking IS GONE, DELIBERATELY
    The old version sent `thinking={"type": "disabled"}` by building the HTTP
    request itself. Keeping it here means either a provider-specific switch
    in llm.py -- which that module refuses on purpose, it knows nothing about
    any one backend -- or a second HTTP path that bypasses
    ratelimit.acquire(), which is the defect this rewrite exists to remove.

    Nothing is lost. The reasoning-on/off question was already decided and
    the decision is recorded in docs/SCORING.md "Reasoning tokens: measured,
    and deliberately left ON": 4.9x cheaper, and rejected, because it moved
    the four highest-weight matching fields by 10-19 points against their
    self-consistency floor. That comparison belongs to tools/compare-extract.py,
    which measures the agreement half as well as the cost half. A cost number
    on its own could only re-argue a settled decision from the weaker side.

PRICES are dollars per million tokens and change without notice -- PRICES
below is a convenience, not an authority. Pass --price-* to override, and
check the provider's page before trusting any total.
"""

import os
import sys
import math
import time
import argparse
import datetime
import statistics
import concurrent.futures

# ingest/ and tools/ sit one level below the pipeline modules they import
# (schema, relevance, llm, ...). Python puts THIS file's directory on sys.path,
# not its parent, so the parent is added by hand. That same insert is what
# reaches lib/ -- there is nothing to install.
BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

import extract      # noqa: E402
import llm          # noqa: E402
import score        # noqa: E402
from evals import corpus, models  # noqa: E402
from lib import envfile           # noqa: E402

#: The frozen fixture. Never a live `ORDER BY first_seen DESC` selection:
#: that is ~85% clean ATS postings, so it measures the easy sources, and it
#: changes nightly so two runs are not comparable. docs/ingestion_tests/README.md
#: records the measurement this argument came from.
DEFAULT_CORPUS = os.path.join(BACKEND, "evals", "fixtures", "corpus-v1.jsonl")

#: The systemd window, from ~/.config/systemd/user/jobs-ingest.service's
#: TimeoutStartSec=10800. Not a soft target -- systemd kills the unit at it,
#: mid-run, and the steps are sequential so extraction shares it with every
#: ingest fetch and score.py. Timer is OnCalendar=*-*-* 00:00:00
#: America/New_York.
RUN_DAILY_WINDOW_SECS = 10800

#: WHAT THE PROVIDER WILL ACTUALLY REFUSE TO SERVE, and where each figure
#: came from. This block exists because task 04 found the number lived in
#: nobody's repo and one person's memory.
#:
#: `concurrent` is the binding limit on DeepSeek and there is no published
#: daily request ceiling, which is why the derived sentence below talks about
#: concurrency rather than inventing a "% of daily quota".
#:
#: PROVENANCE MATTERS MORE THAN THE NUMBER. `source` distinguishes a figure
#: somebody measured from a figure somebody stated. The 2,500 below is
#: OPERATOR-STATED, NOT MEASURED: the throttle probe the task originally
#: asked for (push until 429) was dropped deliberately, because discovering a
#: limit already in hand risks the nightly run-daily window for nothing.
#: Anyone re-deriving it should treat it as a claim to check, not a
#: measurement to reuse.
PROVIDER_LIMITS = {
    "api.deepseek.com": {
        "concurrent": 2500,
        "requests_per_day": None,
        "requests_per_minute": None,
        "source": "repo owner, 2026-07-28 -- operator-stated, NOT measured",
        "note": "No daily or per-minute ceiling is published. DeepSeek's "
                "documented posture is that it does not hard-limit request "
                "rate; it degrades under load instead, which is why "
                "llm.DEFAULT_TIMEOUT_SECS is 120 and not 60.",
    },
}

#: Client-side caps, which are a different thing from the provider's and can
#: bind first. Unset means unlimited -- see ratelimit.py.
CLIENT_LIMIT_VARS = ("LLM_MAX_RPM", "LLM_MAX_RPD")

#: $ per million tokens: (input_miss, input_cache_hit, output).
#: Output covers reasoning tokens too -- they are billed as output.
PRICES = {
    "deepseek-v4-flash": (0.14, 0.0028, 0.28),
    "deepseek-v4-pro": (0.435, 0.003625, 0.87),
    "glm-4.5-flash": (0.0, 0.0, 0.0),          # free tier
    "gemini-3.6-flash": (0.0, 0.0, 0.0),       # free tier (20 req/day)
    "gemini-3.5-flash-lite": (0.0, 0.0, 0.0),  # free tier
}

STAGE_WORKERS = {"extract": extract.EXTRACT_MAX_WORKERS,
                 "score": score.SCORE_MAX_WORKERS}

#: THE TWO STAGES ARE BOUNDED BY DIFFERENT THINGS, and reporting one figure
#: for both is how a projection gets quoted at the wrong stage.
#:
#:   extract  is driven by N eligible postings/day and hard-capped by
#:            EXTRACT_BATCH_SIZE (extract.py:70, default 40), because
#:            run-daily.py invokes extract.py exactly once per night
#:            (run-daily.py:120). More postings than that per day is not a
#:            slow night, it is a backlog that never closes.
#:
#:   score    is not a function of N at all. run_for_profile() takes
#:            `profile_obj.daily_narrative_budget` (score.py:479, 20 in the
#:            database today) for each ACTIVE profile, so the nightly call
#:            count is budget x profiles regardless of how many postings
#:            arrived. NOTE: SCORE_BATCH_SIZE (score.py:195) is NOT the cap --
#:            it is defined, documented in two docstrings, and read by
#:            nothing on the nightly path.
EXTRACT_BATCH = extract.EXTRACT_BATCH_SIZE

#: Active profiles and their narrative budget, from jobs.profiles on
#: 2026-07-28: `frontend` and `tech`, both at 20. Constants rather than a
#: query, because this tool no longer opens a database connection -- and a
#: figure that silently changes with production is not a baseline.
SCORE_ACTIVE_PROFILES = 2
SCORE_BUDGET_PER_PROFILE = 20


def price_for(model, args):
    if args.price_in is not None:
        return (args.price_in, args.price_cached or 0.0, args.price_out or 0.0)
    for name, p in PRICES.items():
        if model.startswith(name):
            return p
    return None


def limits_for(base_url):
    """Documented provider limits for an endpoint, or None if unrecorded.

    Returning None rather than a default is deliberate: an invented ceiling
    is worse than an absent one, because it gets quoted.
    """
    host = (base_url or "").split("://", 1)[-1].split("/", 1)[0]
    return PROVIDER_LIMITS.get(host)


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


def percentile(sorted_values, q):
    """Nearest-rank percentile. No interpolation, so every printed number is
    a latency something actually took."""
    if not sorted_values:
        return 0.0
    k = max(1, math.ceil(q * len(sorted_values)))
    return sorted_values[min(k, len(sorted_values)) - 1]


def hours(seconds):
    return seconds / 3600.0


def select_records(path, stage, n):
    """`n` fixture records the pipeline would actually send, pinned by job_id.

    Sorted by job_id, not sampled: two runs of this tool over the same
    fixture must measure the same postings, or the p95 moves for reasons
    that have nothing to do with the endpoint. CLAUDE.md's "pin eval sets by
    sorted job_id".
    """
    records = corpus.load(path)
    if stage == "extract":
        # extract.select_unextracted_jobs requires a non-empty description
        # (extract.py:185). A fixture deliberately contains rows that fail
        # this; sending them would measure a prompt the pipeline never sends.
        eligible = [r for r in records
                    if (r.get("description_text") or "").strip()]
    else:
        # score.select_shortlist joins job_facts, so a record without a facts
        # block is one the narrative stage could never reach.
        eligible = [r for r in records if r.get("facts")]
    eligible.sort(key=lambda r: r.get("id") or "")
    return records, eligible, eligible[:n]


def build_prompts(stage, records):
    if stage == "extract":
        return [extract.build_prompt(corpus.job_fields(r)) for r in records]
    persona = score.load_persona()
    # score.build_prompt takes either shape; a fixture facts block is the
    # shortlist shape once it carries `summary` (score.py:307).
    return [score.build_prompt(persona, dict(r.get("facts") or {}, **{
        "title": r.get("title"), "company_name": r.get("company_name"),
        "location_raw": r.get("location_raw"), "platform": r.get("platform"),
    })) for r in records]


#: Per-call outcomes. Same three-way split extract.py uses, and for the same
#: reason: a deferred call was never evaluated and comes back tomorrow, a
#: tombstoned one is a permanent judgement about the posting.
OK, TOMBSTONE, DEFERRED = "ok", "tombstone", "deferred"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=None,
                    help="MODEL, MODEL@BASE_URL@API_KEY, or "
                         "MODEL@BASE_URL@env:VARNAME. Default: whatever the "
                         "pipeline resolves (JOB_SCORING_MODEL).")
    ap.add_argument("--stage", choices=("score", "extract"), default="extract",
                    help="which prompt to measure (default: extract)")
    ap.add_argument("--corpus", default=DEFAULT_CORPUS,
                    help="frozen fixture (default: evals/fixtures/corpus-v1.jsonl)")
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--workers", type=int, default=None,
                    help="default: the stage's own pipeline setting")
    ap.add_argument("--timeout", type=int, default=llm.DEFAULT_TIMEOUT_SECS)
    ap.add_argument("--daily", type=int, default=43,
                    help="N eligible postings/day for the derived sentence. "
                         "Default 43, measured 2026-06-28..2026-07-27 -- "
                         "`git show refactor-freeze-2026-08-02:docs/pursuit-gate-volume.md`.")
    ap.add_argument("--daily-upper", type=int, default=80,
                    help="second N to project, since 43 is a floor (the last "
                         "seven complete days ran 80/day)")
    ap.add_argument("--backfill", type=int, default=6075,
                    help="rows a one-time backfill would cover. Default 6,075 "
                         "= tier-3 rows with no current-version facts, "
                         "measured 2026-07-28.")
    ap.add_argument("--price-in", type=float, help="$/M input (cache miss)")
    ap.add_argument("--price-cached", type=float, help="$/M input (cache hit)")
    ap.add_argument("--price-out", type=float, help="$/M output")
    args = ap.parse_args()

    # Establish the environment the same way run-daily.py does, so this tool
    # works from a bare shell. Anything already exported wins.
    envfile.load(os.path.join(BACKEND, ".env"))

    try:
        spec = models.parse(args.model) if args.model else models.ModelSpec(
            model=llm.model(), base_url=llm.base_url(),
            api_key=llm.api_key(), backend=llm.backend())
    except models.SpecError as e:
        print(f"cost-test: {e}")
        sys.exit(2)

    workers = args.workers or STAGE_WORKERS[args.stage]
    all_records, eligible, chosen = select_records(
        args.corpus, args.stage, args.n)
    if not chosen:
        print(f"cost-test: no {args.stage} candidates in {args.corpus} -- "
              f"nothing to measure.")
        sys.exit(1)

    prompts = build_prompts(args.stage, chosen)
    n_req = len(prompts)
    today = datetime.date.today().isoformat()

    print(f"cost-test: {args.stage} x {n_req} against {spec.label}")
    print(f"  corpus     {os.path.relpath(args.corpus, BACKEND)} "
          f"(frozen, {len(all_records)} records, {len(eligible)} eligible; "
          f"first {n_req} by sorted job_id)")
    print(f"  workers    {workers} "
          f"({'EXTRACT_MAX_WORKERS' if args.stage == 'extract' else 'SCORE_MAX_WORKERS'}"
          f", the pipeline's own)")
    print(f"  temperature {llm.DEFAULT_TEMPERATURE} (production; omitting it "
          f"measures the provider default, not the pipeline)")
    print(f"  date       {today}")
    print()

    call_kwargs = spec.call_kwargs()

    def one(prompt):
        try:
            c = llm.call_detailed(prompt, timeout=args.timeout, **call_kwargs)
        except llm.TransientError as e:
            # Never counted as a failure of the model: the prompt was not
            # evaluated. extract.py defers these and retries tomorrow.
            return (DEFERRED, f"{type(e).__name__}: {str(e)[:120]}", None)
        except RuntimeError as e:
            return (TOMBSTONE, f"{type(e).__name__}: {str(e)[:120]}", None)
        return (OK, None, c)

    started = time.time()
    outcomes = [None] * n_req
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(one, p): i for i, p in enumerate(prompts)}
        for fut in concurrent.futures.as_completed(futures):
            outcomes[futures[fut]] = fut.result()
    wall = time.time() - started

    ok = [c for kind, _, c in outcomes if kind == OK]
    deferred = [msg for kind, msg, _ in outcomes if kind == DEFERRED]
    tombstoned = [msg for kind, msg, _ in outcomes if kind == TOMBSTONE]
    if not ok:
        first = (deferred + tombstoned)[0]
        print(f"cost-test: every call failed. First: {first}")
        sys.exit(1)

    n = len(ok)
    usages = [usage_fields(c.usage) for c in ok]
    tot = {k: sum(u[k] for u in usages) for k in
           ("prompt", "hit", "miss", "out", "reasoning")}
    lat = sorted(c.latency_s for c in ok)
    per_call = wall / n_req          # throughput, not latency: includes queueing
    p50, p95 = statistics.median(lat), percentile(lat, 0.95)

    # A response that parses and carries every required field is the only
    # kind the pipeline can store. Measured here rather than assumed because
    # a truncated answer is a real failure mode of a throttled call, and it
    # returns HTTP 200.
    required = (extract.REQUIRED_FIELDS if args.stage == "extract"
                else score.REQUIRED_FIELDS)
    usable = sum(1 for c in ok
                 if llm.has_fields(llm.parse_json(c.text), required))

    limits = limits_for(spec.base_url or llm.base_url())

    # ------------------------------------------------------------------ #
    # THE DERIVED SENTENCE. Everything below it is supporting detail.
    # ------------------------------------------------------------------ #
    if limits and limits.get("concurrent"):
        pct = 100.0 * workers / limits["concurrent"]
        binds = (f"consumes {pct:.1f}% of what actually binds -- {workers} of "
                 f"the provider's {limits['concurrent']:,}\n  concurrent "
                 f"requests. There is no daily request ceiling to consume.")
    else:
        binds = ("consumes an unknown share of the provider's limits, which "
                 "are not\n  documented for this endpoint.")

    print("=" * 78)
    print("  THE NUMBER THAT MATTERS")
    if args.stage == "extract":
        for N in (args.daily, args.daily_upper):
            print()
            print(f"  At {N} eligible postings/day, the nightly extraction "
                  f"pass takes {hours(N * per_call):.2f} hours\n  and {binds}")
            if N > EXTRACT_BATCH:
                print(f"    ...except it never processes {N}. "
                      f"EXTRACT_BATCH_SIZE caps one run at {EXTRACT_BATCH} "
                      f"and")
                print(f"    run-daily.py invokes extract.py once, so "
                      f"{EXTRACT_BATCH} are done in "
                      f"{hours(EXTRACT_BATCH * per_call):.2f} h and the "
                      f"backlog grows {N - EXTRACT_BATCH}/day, forever.")
    else:
        # N postings/day does not drive this stage -- see the note beside
        # SCORE_ACTIVE_PROFILES. Projecting it against N would be the same
        # error docs/SCORING.md's "one call per (job, profile)" table exists
        # to avoid.
        calls = SCORE_ACTIVE_PROFILES * SCORE_BUDGET_PER_PROFILE
        print()
        print(f"  The nightly narrative pass is not a function of postings/day."
              f" It is {SCORE_ACTIVE_PROFILES} active")
        print(f"  profiles x {SCORE_BUDGET_PER_PROFILE} "
              f"daily_narrative_budget = {calls} calls, takes "
              f"{hours(calls * per_call):.2f} hours\n  and {binds}")
        print(f"    Per additional active profile: "
              f"+{SCORE_BUDGET_PER_PROFILE} calls, "
              f"+{hours(SCORE_BUDGET_PER_PROFILE * per_call):.2f} h.")
    print("=" * 78)
    print()

    print("  QUOTA -- what the provider will refuse to serve")
    if limits:
        print(f"    concurrent requests   {limits['concurrent']:,}"
              if limits.get("concurrent") else
              "    concurrent requests   not documented")
        print(f"    requests/day          "
              f"{limits['requests_per_day'] or 'no published ceiling'}")
        print(f"    requests/minute       "
              f"{limits['requests_per_minute'] or 'no published ceiling'}")
        print(f"    source                {limits['source']}")
        print(f"    this run peaked at    {workers} concurrent, "
              f"{n_req} requests total")
    else:
        print(f"    not documented for {spec.base_url or llm.base_url()}. "
              f"Add it to PROVIDER_LIMITS rather than guessing.")
    client = {v: os.environ.get(f"{v}__{spec.model.replace('-', '_').replace('.', '_')}")
              or os.environ.get(v) for v in CLIENT_LIMIT_VARS}
    print(f"    client-side caps      " + ", ".join(
        f"{k}={v or 'unset (unlimited)'}" for k, v in client.items())
        + "   -- ratelimit.py")
    print()

    print(f"  WALL CLOCK -- per call, at {workers} workers")
    print(f"    p50                   {p50:.1f}s")
    print(f"    p95                   {p95:.1f}s   (nearest-rank over n={n})")
    print(f"    min / max             {lat[0]:.1f}s / {lat[-1]:.1f}s")
    print(f"    run                   {wall:.0f}s for {n_req} calls "
          f"= {per_call:.2f}s/call effective")
    print(f"    systemd window        {RUN_DAILY_WINDOW_SECS}s "
          f"(TimeoutStartSec, jobs-ingest.service) shared with 8 other steps")
    nightly = (EXTRACT_BATCH if args.stage == "extract"
               else SCORE_ACTIVE_PROFILES * SCORE_BUDGET_PER_PROFILE)
    print(f"    a full nightly pass   {nightly * per_call:.0f}s for "
          f"{nightly} calls "
          f"({100.0 * nightly * per_call / RUN_DAILY_WINDOW_SECS:.1f}% "
          f"of the window)")
    print()

    print("  CACHE -- provider prefix cache, on the CURRENT prompt")
    if tot["prompt"]:
        print(f"    hit rate              "
              f"{100.0 * tot['hit'] / tot['prompt']:.0f}% of input tokens "
              f"({tot['hit']:,} of {tot['prompt']:,})")
        # The first `workers` calls start before any of them has written a
        # prefix, so they cannot hit. Reporting only the whole-run rate makes
        # the measured number depend on n, which is not a property of the
        # prompt.
        warm = usages[workers:] if len(usages) > workers else []
        warm_prompt = sum(u["prompt"] for u in warm)
        if warm_prompt:
            print(f"    steady state          "
                  f"{100.0 * sum(u['hit'] for u in warm) / warm_prompt:.0f}% "
                  f"(excluding the first {workers} calls, which start before "
                  f"any prefix is written)")
        zero_hit = sum(1 for u in usages if u["hit"] == 0)
        print(f"    calls with zero hit   {zero_hit}/{n}")
        print(f"    CAVEAT                this number depends on how recently "
              f"the prefix was last sent.")
        print(f"                          DeepSeek's cache survives BETWEEN "
              f"runs: measured 2026-07-28, the")
        print(f"                          score prompt read 74% on a cold "
              f"prefix and 95% on an immediate")
        print(f"                          re-run of the same 24 calls. Quote "
              f"the range, not one run.")
    print()

    print(f"  TOKENS -- per call, mean over {n}")
    print(f"    input                 {tot['prompt'] // n:,}   "
          f"({tot['hit'] // n:,} cached, {tot['miss'] // n:,} uncached)")
    print(f"    output                {tot['out'] // n:,}   "
          f"(of which reasoning {tot['reasoning'] // n:,})")
    print(f"    totals over the run   in {tot['prompt']:,}, out {tot['out']:,}")
    print()

    print("  FAILURES -- deferred and tombstoned are not the same thing")
    print(f"    ok                    {n}/{n_req}")
    print(f"    usable JSON           {usable}/{n} "
          f"(parses AND carries every required field)")
    print(f"    deferred (transient)  {len(deferred)}  "
          f"-- 429/timeout/5xx; nothing written, retried next run")
    print(f"    tombstoned (perm.)    {len(tombstoned)}  "
          f"-- written as FAILED:, never retried")
    print(f"    retry rate            "
          f"{100.0 * len(deferred) / n_req:.1f}%  "
          f"(= the deferral rate: the pipeline does not retry in-run, it "
          f"defers to the next nightly pass)")
    for label, msgs in (("deferred", deferred), ("tombstoned", tombstoned)):
        if msgs:
            print(f"    first {label}: {msgs[0]}")
    print()

    prices = price_for(spec.model, args)
    print("  DOLLARS -- secondary. See QUOTA above for what actually binds.")
    if prices is None:
        print(f"    no price on file for {spec.model}; pass "
              f"--price-in/--price-cached/--price-out")
        return
    p_miss, p_hit, p_out = prices
    cost = (tot["miss"] * p_miss + tot["hit"] * p_hit + tot["out"] * p_out) / 1e6
    if cost == 0:
        print("    free tier -- no charge. The request cap is the constraint.")
        return
    per_job = cost / n
    print(f"    rates                 ${p_miss}/${p_hit}/${p_out} per Mtok "
          f"(miss/hit/out)")
    print(f"    per call              ${per_job:.6f}")
    print(f"    ongoing               ${per_job * args.daily * 30:.2f}/month "
          f"at {args.daily}/day, "
          f"${per_job * args.daily_upper * 30:.2f}/month at "
          f"{args.daily_upper}/day")
    print(f"    backfill              ${per_job * args.backfill:.2f} "
          f"({args.backfill:,} rows)")
    out_share = (tot["out"] * p_out) / 1e6 / cost * 100
    print(f"    output is {out_share:.0f}% of the bill"
          + (f", reasoning alone "
             f"{(tot['reasoning'] * p_out) / 1e6 / cost * 100:.0f}%"
             if tot["reasoning"] else ""))


if __name__ == "__main__":
    main()
