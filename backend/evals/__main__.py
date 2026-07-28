"""Command line for the evaluation harness.

    python3 -m evals corpus snapshot --n 200 --out evals/fixtures/corpus-v1.jsonl
    python3 -m evals corpus info evals/fixtures/corpus-v1.jsonl
    python3 -m evals run --task extract --model "$SPEC" --corpus <path> --n 20
    python3 -m evals selfcheck --model "$SPEC" --n 120 --repeat 3
    python3 -m evals cache stats

Run from backend/, which is what puts the pipeline modules (extract, llm,
schema, ...) on sys.path -- the same arrangement tools/ uses.
"""

import argparse
import os
import sys

# Running as `python3 -m evals` from backend/ already puts backend/ on
# sys.path. Adding the package's parent explicitly makes `python3
# backend/evals/__main__.py` work too, which is what an editor's run button
# does.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evals import cache as cache_mod          # noqa: E402
from evals import corpus as corpus_mod        # noqa: E402
from evals import models as models_mod        # noqa: E402
from evals import runner as runner_mod        # noqa: E402
from evals import tasks as tasks_mod          # noqa: E402
from lib import envfile                       # noqa: E402

#: Same file and same precedence as run-daily.py:92 -- an exported value wins,
#: the file is the fallback. Loaded here rather than in each subcommand so
#: `corpus snapshot` finds DATABASE_URL and `run` finds a model key without
#: the caller having to source anything.
ENV_FILE = os.environ.get(
    "JOBS_ENV_FILE",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 ".env"))


def cmd_corpus_snapshot(args):
    import schema
    import score
    from lib import dbconn

    persona = score.load_persona()
    profile = args.profile or schema.resolve_profile(persona)
    conn = dbconn.connect_or_exit("evals corpus snapshot", schema=schema.SCHEMA)
    try:
        records = corpus_mod.snapshot(conn, args.n, profile=profile,
                                      seed=args.seed)
    finally:
        conn.close()

    corpus_mod.save(args.out, records)
    _print_summary(records, f"wrote {args.out}")
    return 0


def cmd_corpus_info(args):
    records = corpus_mod.load(args.path)
    _print_summary(records, args.path)
    return 0


def _print_summary(records, header):
    s = corpus_mod.summarize(records)
    print(f"{header}: {s['total']} records, {s['with_facts']} with facts")
    print("  platforms: " + ", ".join(
        f"{k}={v}" for k, v in sorted(s["platforms"].items())))
    print("  pathology: " + (", ".join(
        f"{k}={v}" for k, v in sorted(s["pathology"].items())) or "none"))


def cmd_run(args):
    try:
        spec = models_mod.parse(args.model)
    except models_mod.SpecError as e:
        print(f"evals run FAILED: {e}", file=sys.stderr)
        return 2

    task = tasks_mod.get(args.task)
    records = corpus_mod.load(args.corpus)
    if args.n:
        records = records[:args.n]
    if not records:
        print("evals run FAILED: corpus is empty", file=sys.stderr)
        return 1

    use_cache = not args.no_cache
    # flush: the banner goes to stdout and failures go to stderr, and stdout
    # is block-buffered when piped -- without this the two arrive out of order
    # and the error looks like it preceded the run it came from.
    print(f"evals run: task={task.name} model={spec.label} "
          f"n={len(records)} cache={'on' if use_cache else 'off'}"
          f"{' (refresh)' if args.refresh else ''}", flush=True)

    def progress(done, total, result):
        if args.verbose:
            print(f"  [{done}/{total}] {result.job_id} {result.status}"
                  + (f" ({result.reason})" if result.reason else ""),
                  file=sys.stderr)

    try:
        run = runner_mod.run(task, spec, records, use_cache=use_cache,
                             refresh=args.refresh, workers=args.workers,
                             progress=progress)
    except models_mod.SpecError as e:
        # Raised by the one-time credential resolve in runner.run(), before
        # anything is billed. A config error deserves one line, not a
        # traceback -- the same argument run-daily.py:145 makes for its
        # REQUIRED_ENV check.
        print(f"evals run FAILED: {e}", file=sys.stderr)
        return 2

    from evals import report
    print(report.render(run))
    if args.out:
        n = report.write_jsonl(args.out, run)
        print(f"wrote {n} result rows to {args.out}")
    return 0


def cmd_selfcheck(args):
    """Same corpus, same prompt, N times -- what does the model owe itself?

    Separate from `run` rather than a flag on it because the output is a
    different thing: `run` reports whether a model is usable at all, this
    reports whether it is stable, and the second is only meaningful as a
    floor beside anything measured against labels.
    """
    try:
        spec = models_mod.parse(args.model)
    except models_mod.SpecError as e:
        print(f"evals selfcheck FAILED: {e}", file=sys.stderr)
        return 2

    if args.repeat < 2:
        print("evals selfcheck FAILED: --repeat must be at least 2",
              file=sys.stderr)
        return 2

    task = tasks_mod.get(args.task)
    records = corpus_mod.load(args.corpus)
    if args.n:
        records = records[:args.n]
    if not records:
        print("evals selfcheck FAILED: corpus is empty", file=sys.stderr)
        return 1

    # `--cache` is deliberately opt-IN and named for what it does to the
    # measurement. Caching a repeat run makes every later pass replay the
    # first and reports 100% agreement; the per-repeat cache key stops the
    # collision, but a replayed answer still has no live variance in it.
    use_cache = bool(args.cache)
    print(f"evals selfcheck: task={task.name} model={spec.label} "
          f"n={len(records)} repeat={args.repeat} "
          f"cache={'on (per-repeat keys)' if use_cache else 'off'}",
          flush=True)

    def progress(pass_i, done, total, result):
        if args.verbose:
            print(f"  [pass {pass_i + 1}] [{done}/{total}] {result.job_id} "
                  f"{result.status}"
                  + (f" ({result.reason})" if result.reason else ""),
                  file=sys.stderr)

    try:
        runs = runner_mod.run_repeated(task, spec, records,
                                       repeat=args.repeat,
                                       use_cache=use_cache,
                                       workers=args.workers,
                                       progress=progress)
    except models_mod.SpecError as e:
        print(f"evals selfcheck FAILED: {e}", file=sys.stderr)
        return 2

    from evals import metrics, report
    for i, run in enumerate(runs):
        print(f"--- pass {i + 1} ---")
        print(report.render(run))

    stats = metrics.selfcheck(runs, records, task.field_kinds)
    print(report.render_selfcheck(stats, runs))
    if args.out:
        report.write_selfcheck_json(args.out, stats, runs)
        print(f"wrote {args.out}")
    return 0


def cmd_cache_stats(args):
    count, total = cache_mod.stats()
    print(f"{cache_mod.cache_dir()}: {count} entries, {total/1e6:.1f} MB")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="evals", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    corpus_p = sub.add_parser("corpus", help="build and inspect fixtures")
    corpus_sub = corpus_p.add_subparsers(dest="corpus_cmd", required=True)

    snap = corpus_sub.add_parser("snapshot",
                                 help="read production, write a fixture (read-only)")
    snap.add_argument("--n", type=int, default=200)
    snap.add_argument("--out", required=True)
    snap.add_argument("--profile", default=None)
    snap.add_argument("--seed", type=int, default=0)
    snap.set_defaults(func=cmd_corpus_snapshot)

    info = corpus_sub.add_parser("info", help="summarize a fixture")
    info.add_argument("path")
    info.set_defaults(func=cmd_corpus_info)

    run_p = sub.add_parser("run", help="run a task over a corpus")
    run_p.add_argument("--task", default="extract")
    run_p.add_argument("--model", required=True,
                       help="MODEL@BASE_URL@KEY, MODEL, or claude:MODEL")
    run_p.add_argument("--corpus", required=True)
    run_p.add_argument("--n", type=int, default=None)
    run_p.add_argument("--workers", type=int, default=runner_mod.DEFAULT_WORKERS)
    run_p.add_argument("--no-cache", action="store_true",
                       help="always call live; required for honest latency")
    run_p.add_argument("--refresh", action="store_true",
                       help="re-buy every response and overwrite the cache")
    run_p.add_argument("--out", default=None, help="write results as JSONL")
    run_p.add_argument("--verbose", action="store_true")
    run_p.set_defaults(func=cmd_run)

    sc = sub.add_parser("selfcheck",
                        help="same corpus N times: model self-consistency")
    sc.add_argument("--task", default="extract")
    sc.add_argument("--model", required=True,
                    help="MODEL@BASE_URL@KEY, MODEL, or claude:MODEL")
    sc.add_argument("--corpus", default="evals/fixtures/corpus-v2.jsonl")
    sc.add_argument("--n", type=int, default=None)
    sc.add_argument("--repeat", type=int, default=3,
                    help="passes over the corpus; 3 gives a majority")
    sc.add_argument("--workers", type=int, default=runner_mod.DEFAULT_WORKERS)
    sc.add_argument("--cache", action="store_true",
                    help="replay from cache (per-repeat keys). Off by "
                         "default: this measures live variance")
    sc.add_argument("--out", default=None, help="write the table as JSON")
    sc.add_argument("--verbose", action="store_true")
    sc.set_defaults(func=cmd_selfcheck)

    cache_p = sub.add_parser("cache", help="inspect the replay cache")
    cache_sub = cache_p.add_subparsers(dest="cache_cmd", required=True)
    st = cache_sub.add_parser("stats")
    st.set_defaults(func=cmd_cache_stats)

    args = p.parse_args(argv)
    envfile.load(ENV_FILE)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
