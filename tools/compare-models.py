#!/usr/bin/env python3
"""
Compare scoring models against the same jobs, before switching the default.

Answers the only question that matters when swapping JOB_SCORING_MODEL: does
the cheaper/faster model produce *usable* output, and does it broadly agree
with what you already trust?

READ-ONLY. This never writes to the `jobs` table -- it pulls real postings, scores
them with each candidate model in memory, and prints a comparison. Run it as
many times as you like without polluting scores.

USAGE
    # compare the current default against a candidate
    python3 tools/compare-models.py \\
        --model "glm-4.5-flash@https://api.z.ai/api/paas/v4@$GLM_API_KEY" \\
        --model "gemini-3.6-flash@https://generativelanguage.googleapis.com/v1beta/openai@$GEMINI_API_KEY" \\
        --n 15

    # a local model costs nothing to try
    python3 tools/compare-models.py \\
        --model "llama3.1@http://localhost:11434/v1@unused" --n 10

Each --model is MODEL_ID@BASE_URL@API_KEY. Repeat it to add candidates.

WHAT TO LOOK FOR
    json_ok      -- the hard gate. A model that can't reliably return parseable
                    JSON is unusable here no matter how smart it is; the
                    pipeline tombstones those jobs as FAILED and moves on.
    latency      -- multiply by SCORE_BATCH_SIZE/SCORE_MAX_WORKERS for real
                    run time. A slow model turns the nightly cron into an
                    hours-long job.
    track_agree  -- how often it picks the same primary_track as the FIRST
                    model listed (treated as the reference). Low agreement
                    isn't automatically wrong, but go read the samples before
                    trusting it.
    score spread -- a model that rates everything 70-75 isn't discriminating,
                    which defeats the point of scoring at all.
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

import schema  # noqa: E402  (schema.py)
import score   # noqa: E402  (score.py -- for build_prompt and load_persona)
import llm     # noqa: E402  (llm.py)
from lib import dbconn  # noqa: E402

HTTP_TIMEOUT = int(os.environ.get("HTTP_TIMEOUT", "90"))


def select_jobs(conn, n, only_scored, profile):
    """only_scored=True pulls jobs that already have a trusted score, so you
    can compare candidates against real prior output as well as each other.

    Scores live in job_scores keyed (job_id, profile), so "already scored"
    means scored under THIS profile -- a LEFT JOIN, since without
    --only-scored we still want unscored jobs and just no production column
    to compare against."""
    join = "LEFT JOIN"
    where = "j.status = 'open' AND j.description_text IS NOT NULL"
    if only_scored:
        join = "JOIN"
        where += " AND s.fit_score IS NOT NULL"
    rows = conn.execute(
        f"""SELECT j.id, j.title, j.company_name, j.location_raw, j.platform,
                   j.description_text, s.fit_score, s.primary_track
            FROM jobs j
            {join} job_scores s ON s.job_id = j.id AND s.profile = %s
            WHERE {where}
            ORDER BY j.first_seen DESC LIMIT %s""",
        (profile, n),
    ).fetchall()
    cols = ["id", "title", "company_name", "location_raw", "platform",
            "description_text", "fit_score", "primary_track"]
    return [dict(zip(cols, r)) for r in rows]


def build_prompt(persona, job):
    """Delegates to score.py's own build_prompt.

    This used to be a paraphrase, and it had drifted: it asked for
    primary_track as "core_swe|ai_integration|bridge_solutions|reentry_growth"
    while production asks for "Core SWE|AI Integration|Bridge & Solutions|
    Re-Entry & Growth|Poor Fit". Two vocabularies for one column meant
    track_agree compared candidates against a reference that had answered a
    different question, and the "[production]" line in SIDE BY SIDE could
    never match a candidate's label no matter how well they agreed.

    Importing the real thing is the only version of "keep these in sync" that
    stays true -- a benchmark measured on a different prompt than production
    runs measures the wrong model."""
    return score.build_prompt(persona, job)


def parse_llm_json(text):
    """Same tolerance as score.py: strip fences, take the outermost {...}."""
    if not text:
        return None
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```")[1] if len(t.split("```")) > 1 else t
        if t.startswith("json"):
            t = t[4:]
    s, e = t.find("{"), t.rfind("}")
    if s == -1 or e == -1:
        return None
    try:
        return json.loads(t[s:e + 1])
    except json.JSONDecodeError:
        return None


def call_model(spec, prompt):
    model, base_url, api_key = spec
    # Must match llm.py's DEFAULT_TEMPERATURE. This harness previously
    # hardcoded 0.2 while production sent no temperature at all, so every
    # comparison measured a configuration that never actually ran -- and did
    # it at a temperature low enough to hide the sampling noise production
    # was really getting.
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": llm.DEFAULT_TEMPERATURE,
        "response_format": {"type": "json_object"},
    }).encode()
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=body, method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {api_key}"},
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
        elapsed = time.time() - t0
        content = data["choices"][0]["message"]["content"]
        return parse_llm_json(content), elapsed, None
    except urllib.error.HTTPError as e:
        return None, time.time() - t0, f"HTTP {e.code}: {e.read().decode()[:120]}"
    except Exception as e:
        return None, time.time() - t0, f"{type(e).__name__}: {str(e)[:120]}"


def evaluate(spec, jobs, persona, workers):
    def one(job):
        result, elapsed, err = call_model(spec, build_prompt(persona, job))
        return {"job": job, "result": result, "elapsed": elapsed, "error": err}
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(one, jobs))


def summarize(name, runs, reference=None):
    ok = [r for r in runs if r["result"] and isinstance(r["result"].get("fit_score"), (int, float))]
    scores = [r["result"]["fit_score"] for r in ok]
    lat = [r["elapsed"] for r in runs]
    errs = [r["error"] for r in runs if r["error"]]

    print(f"\n{'='*68}\n{name}\n{'='*68}")
    print(f"  json_ok      {len(ok)}/{len(runs)}   ({100*len(ok)/max(len(runs),1):.0f}%)")
    if lat:
        print(f"  latency      median {statistics.median(lat):.1f}s   max {max(lat):.1f}s")
    if scores:
        print(f"  fit_score    median {statistics.median(scores):.0f}   "
              f"range {min(scores):.0f}-{max(scores):.0f}   "
              f"stdev {statistics.pstdev(scores):.1f}")
    if reference:
        ref = {r["job"]["id"]: r["result"] for r in reference if r["result"]}
        both = [(r["result"], ref[r["job"]["id"]]) for r in ok if r["job"]["id"] in ref]
        if both:
            agree = sum(1 for a, b in both if a.get("primary_track") == b.get("primary_track"))
            deltas = [abs(a["fit_score"] - b["fit_score"]) for a, b in both
                      if isinstance(b.get("fit_score"), (int, float))]
            print(f"  track_agree  {agree}/{len(both)} vs reference")
            if deltas:
                print(f"  score_delta  mean {statistics.mean(deltas):.1f} pts   max {max(deltas):.0f}")
    if errs:
        print(f"  errors       {len(errs)}")
        for e in list(dict.fromkeys(errs))[:3]:
            print(f"    - {e}")
    return runs


def main():
    p = argparse.ArgumentParser(description="Compare LLM scoring models (read-only).")
    p.add_argument("--model", action="append", required=True,
                   metavar="MODEL@BASE_URL@KEY", help="repeatable; first is the reference")
    p.add_argument("--n", type=int, default=10, help="jobs to test (default 10)")
    p.add_argument("--workers", type=int, default=3, help="concurrent requests")
    p.add_argument("--only-scored", action="store_true",
                   help="use jobs that already have a production score")
    p.add_argument("--samples", type=int, default=2, help="side-by-side examples to print")
    p.add_argument("--profile", default=None,
                   help="score profile to compare against (default: persona.json's)")
    args = p.parse_args()

    specs = []
    for m in args.model:
        parts = m.split("@")
        if len(parts) < 3:
            print(f"bad --model {m!r}; want MODEL@BASE_URL@KEY", file=sys.stderr)
            sys.exit(1)
        # base_url contains '://' so rejoin the middle
        specs.append((parts[0], "@".join(parts[1:-1]), parts[-1]))

    persona = score.load_persona()
    profile = args.profile or schema.resolve_profile(persona)
    conn = dbconn.connect_or_exit("compare-models", schema=schema.SCHEMA)
    jobs = select_jobs(conn, args.n, args.only_scored, profile)
    conn.close()

    if not jobs:
        print("no jobs matched -- try without --only-scored")
        sys.exit(1)
    print(f"testing {len(jobs)} jobs against {len(specs)} model(s), profile={profile}")

    all_runs, reference = [], None
    for i, spec in enumerate(specs):
        runs = evaluate(spec, jobs, persona, args.workers)
        summarize(f"{spec[0]}  ({spec[1]})", runs, reference if i else None)
        if i == 0:
            reference = runs
        all_runs.append((spec[0], runs))

    if args.samples:
        print(f"\n{'='*68}\nSIDE BY SIDE\n{'='*68}")
        for job in jobs[:args.samples]:
            print(f"\n{job['title']} — {job['company_name']}")
            if job.get("fit_score") is not None:
                print(f"  {'[production]':<22} {job['fit_score']}  {job.get('primary_track')}")
            for name, runs in all_runs:
                r = next((x["result"] for x in runs if x["job"]["id"] == job["id"]), None)
                if r:
                    print(f"  {name[:20]:<22} {r.get('fit_score')}  {r.get('primary_track')}"
                          f"  | {str(r.get('gap_bridging_angle'))[:60]}")
                else:
                    print(f"  {name[:20]:<22} FAILED")


if __name__ == "__main__":
    main()
