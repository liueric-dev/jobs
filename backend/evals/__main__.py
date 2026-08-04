"""Command line for the evaluation harness.

    python3 -m evals corpus snapshot --n 200 --out evals/fixtures/corpus-v1.jsonl
    python3 -m evals corpus info evals/fixtures/corpus-v1.jsonl
    python3 -m evals run --task extract --model "$SPEC" --corpus <path> --n 20
    python3 -m evals selfcheck --model "$SPEC" --n 120 --repeat 3
    python3 -m evals label init-schema
    python3 -m evals label sample --n 60 --overlap 20
    python3 -m evals label export --out evals/fixtures/golden-v1.jsonl
    python3 -m evals label report --run <results.jsonl> --selfcheck <sc.json>
    python3 -m evals cache stats

Nothing under `label` ever writes a label. People do that in a browser at
/v1/label -- see backend/webapp/label.py.

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
    if args.golden and not args.selfcheck:
        # Refused here, before anything is billed, rather than after the run:
        # the answer is not printable without the floor and finding that out
        # at the end would have cost the whole corpus.
        print("evals run FAILED: --golden needs --selfcheck. Model-vs-human "
              "without the model's self-consistency beside it is "
              "uninterpretable -- CLAUDE.md, and the reason task 06 ran "
              "first. Produce one with `evals selfcheck --repeat 3 --out`.",
              file=sys.stderr)
        return 2
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

    if args.golden:
        # The model output is right here, so no intermediate file is needed.
        # --selfcheck is required and there is no flag to skip it: a
        # model-vs-human number without the floor beside it is the thing this
        # whole task exists to make impossible to print.
        # NO `from evals import corpus as corpus_mod` here. It was a
        # redundant re-import of line 31, and because Python decides
        # local-vs-global at compile time it made corpus_mod a local for the
        # WHOLE function -- so line 99, which runs on every invocation, raised
        # UnboundLocalError before any model was called. `evals run` was
        # broken for every task, not only when --golden was passed.
        from evals import labels
        golden = corpus_mod.load(args.golden)
        if not golden:
            print(f"{args.golden} holds no labels yet -- the tables ship "
                  "empty and task 29 is what fills them.", file=sys.stderr)
            return 1
        model_values = {r.job_id: r.normalized for r in run.ok if r.normalized}
        try:
            print(_three_quantity_report(golden, model_values, args.selfcheck))
        except labels.Uninterpretable as e:
            print(f"evals run --golden REFUSED: {e}", file=sys.stderr)
            return 2
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


# --------------------------------------------------------------------------
# Labels -- the golden set
# --------------------------------------------------------------------------

def _labels_conn():
    import schema
    from lib import dbconn
    return dbconn.connect_or_exit("evals label", schema=schema.SCHEMA)


def cmd_label_init_schema(args):
    """Create the three label tables. DDL, so an admin credential.

    Separate and explicitly invoked, the same split webapp/manage_app_users.py
    and api/manage_users.py use: the browser-facing labelling surface holds no
    CREATE rights, so a missing table is a deployment error it reports rather
    than damage it silently repairs.
    """
    from evals import labels
    conn = _labels_conn()
    try:
        labels.ensure_schema(conn)
    finally:
        conn.close()
    print("created/verified: " + ", ".join(labels.TABLES))
    print("The tables are EMPTY and stay that way until people label. "
          "Nothing in this harness writes a label.")
    return 0


def cmd_label_sample(args):
    """Draw an eval set spanning all three strata. Writes no labels.

    The set is a file AND a pair of rows in the database, deliberately: the
    file is what gets committed, diffed and pinned by digest, and the table is
    what ten concurrent volunteers' browsers can query.
    """
    from evals import labels
    import profiles
    import relevance
    import schema
    import score

    persona = score.load_persona()
    profile = args.profile or schema.resolve_profile(persona)

    conn = _labels_conn()
    try:
        # The profile row is loaded FIRST and its gate handed to pool()
        # explicitly. pool() would resolve the same thing itself, but the row
        # is needed for criteria anyway and one load beats two. What must not
        # happen is falling back to the shared config/relevance.json: that is
        # a different gate from the one this profile is filtered by, and it
        # misfiles rows the pipeline surfaces as gate-rejected. labels.py:440.
        prof = profiles.load_one(conn, profile)
        cfg = relevance.for_profile(prof)
        rows = labels.pool(conn, profile, per_platform=args.per_platform,
                           cfg=cfg)
        rows, promoted = labels.confirm_scores(rows, prof.criteria)
        picked = labels.sample(rows, args.n, seed=args.seed,
                               overlap=args.overlap)
        # THE REDRAW GUARD RUNS BEFORE save_set(), WHICH IS BELOW AND OUTSIDE
        # THIS BLOCK. save_set() overwrites the committed fixture -- the file
        # the report reads -- so a refusal discovered after it would already
        # have desynced the fixture from the database it was refused by. The
        # rule itself lives in labels.register_set(); this only decides where
        # in the command it is asked, and how the refusal is rendered.
        #
        # The dry run asks the same question read-only rather than skipping
        # it. It writes nothing, so it is never the run that does the damage --
        # but "would write ..." for a draw that cannot be registered is exactly
        # the wrong answer to give the one command an operator runs to find out
        # whether the real one will work.
        refused = None
        try:
            if args.dry_run:
                refused = labels.redraw_refusal(conn, args.label_set, picked)
            else:
                labels.register_set(conn, args.label_set, picked,
                                    seed=args.seed, profile=profile,
                                    note=args.note)
        except labels.SetAlreadyDrawn as e:
            refused = str(e)
    finally:
        conn.close()

    if refused:
        print(f"evals label sample REFUSED: {refused}", file=sys.stderr)
        print(f"  Nothing was registered and {args.out} was not written.",
              file=sys.stderr)
        return 2

    counts = {}
    platforms = {}
    for row in picked:
        counts[row["stratum"]] = counts.get(row["stratum"], 0) + 1
        key = row.get("platform") or "unknown"
        platforms[key] = platforms.get(key, 0) + 1

    # A starved stratum is the failure this command must not pass silently.
    # sample() takes what a stratum has and moves on, so a pool too thin to
    # fill the quota produces a set that looks fine and measures the easy
    # path -- exactly the trap CLAUDE.md's "never select an eval corpus with
    # ORDER BY first_seen DESC" names. Refuse, name the shortfall, and let
    # the operator widen --per-platform or lower --n on purpose.
    shortfall = []
    for stratum in labels.STRATA:
        want = int(round(args.n * labels.DEFAULT_STRATA_QUOTA.get(stratum, 0.0)))
        got = counts.get(stratum, 0)
        if got < want:
            shortfall.append((stratum, want, got))

    if not args.dry_run:
        labels.save_set(args.out, picked)
        print(f"wrote {args.out}: {len(picked)} rows, "
              f"sha256(sorted job_id)={labels.digest(picked)[:16]}...")
    else:
        print(f"would write {args.out}: {len(picked)} rows, "
              f"sha256(sorted job_id)={labels.digest(picked)[:16]}...")
    print("  strata:    " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    print("  platforms: " + ", ".join(f"{k}={v}" for k, v in sorted(platforms.items())))
    print(f"  overlap:   {sum(1 for r in picked if r['overlap'])} row(s) go to "
          "every labeller -- this is what makes the ceiling measurable")
    if promoted:
        # Named rather than dropped quietly: these are rows SQL called
        # below-floor and score_job() disagreed about, which means match.py
        # had not caught up with their facts. Silently keeping them would have
        # contaminated the recall stratum with a scheduling artifact.
        print(f"  {len(promoted)} row(s) had no job_matches row but recompute "
              f"at or above the floor -- excluded from below_floor")
    if args.dry_run:
        print("  (dry run -- nothing registered in the database, "
              "nothing written to disk)")
    if shortfall:
        print("REFUSED: a stratum could not be filled from the pool.")
        for stratum, want, got in shortfall:
            print(f"  {stratum}: wanted {want}, pool held {got}")
        print("  Raise --per-platform, lower --n, or accept a smaller set "
              "deliberately. A short stratum measures the easy path.")
        return 2
    return 0


def cmd_label_export(args):
    """Write golden-vN.jsonl from whatever people have labelled so far.

    Separate from the corpus file so the two version independently, which is
    what `git show refactor-freeze-2026-08-02:docs/ingestion_tests/03-metrics-and-golden-set.md:107` asks for: a corpus is re-snapshotted
    when the sources change and a golden set is never regenerated at all.
    """
    from evals import labels
    conn = _labels_conn()
    try:
        rows = labels.fetch(conn, label_set=args.label_set)
    finally:
        conn.close()

    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    tmp = f"{args.out}.tmp"
    import json as _json
    with open(tmp, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(_json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
    os.replace(tmp, args.out)

    by_axis = {}
    for row in rows:
        by_axis[row["axis"]] = by_axis.get(row["axis"], 0) + 1
    print(f"wrote {args.out}: {len(rows)} label(s) "
          + (", ".join(f"axis {k}={v}" for k, v in sorted(by_axis.items()))
             or "-- none yet, which is the correct state until task 29 runs"))
    return 0


def cmd_label_status(args):
    from evals import labels
    conn = _labels_conn()
    try:
        rows = labels.fetch(conn)
        sets = conn.execute(
            "SELECT label_set, n, created_at, job_id_sha256 "
            "FROM eval_label_sets ORDER BY created_at").fetchall()
    finally:
        conn.close()
    for name, n, created, sha in sets:
        print(f"{name}: n={n} created={created} sha256={sha[:16]}...")
    if not sets:
        print("no label sets yet -- run `evals label sample`")
    # SCOPE FIRST, THEN COUNT EVERYTHING FROM THE SAME ROWS. Scoping partway
    # down printed a set-spanning label count on the same LINE as a set-scoped
    # posting count, which is the "say which columns went into a digest" rule in
    # a smaller costume: two numbers side by side must come from one population
    # or they can only mislead.
    # DISTINCT POSTINGS IS THE DEFINITION OF DONE'S NUMBER, AND UNTIL NOW
    # NOTHING PRINTED IT. Task 29 asks for ">=100 labelled postings from >=5
    # labellers"; the count above is LABELS, which is six per posting now that
    # `role_track` is on the form, so it runs ~6x ahead of coverage. "120
    # labels from 6 labellers" is twenty postings and reads like progress
    # toward 100. This is the line an operator watches on the night, and the
    # per-labeller distinct counts beside it are what say whether the shortfall
    # is turnout or throughput -- two different remedies, and only one of them
    # can be fixed by sending another email.
    # PINNED TO ONE SET, because the threshold it is printed beside belongs to
    # one. fetch() with no label_set returns every set's labels plus the
    # NULL-label_set rows record() permits, so once a pursuit-v2 exists an
    # unpinned numerator would climb past what ">=100" means and the line would
    # read as met when it is not. Identical today (one set) -- which is exactly
    # when it is cheap to pin.
    counted = ([r for r in rows if r["label_set"] == args.label_set]
               if getattr(args, "label_set", None) else rows)
    if getattr(args, "label_set", None):
        print(f"(counting {args.label_set} only)")
    elif len({r["label_set"] for r in rows}) > 1:
        print("WARNING: labels span several sets -- pass --label-set to pin "
              "the distinct count to the one the threshold belongs to")
    rows = counted
    per_labeller, per_labeller_items = {}, {}
    for row in rows:
        per_labeller[row["labeller_id"]] = per_labeller.get(
            row["labeller_id"], 0) + 1
        per_labeller_items.setdefault(row["labeller_id"], set()).add(
            row["job_id"])
    distinct = {row["job_id"] for row in rows}
    print(f"{len(rows)} label(s) from {len(per_labeller)} labeller(s)")
    print(f"{len(distinct)} DISTINCT posting(s) labelled "
          f"-- task 29's definition of done asks for >=100 from >=5 labellers")
    rounds = sorted({row["round_no"] for row in rows})
    if rounds and rounds != [1]:
        # Round 2 re-answers postings already counted above, so it must never
        # look like coverage. See labels.next_item()'s round-2 branch.
        r2 = {row["job_id"] for row in rows if row["round_no"] != 1}
        print(f"  of which {len(r2)} re-checked in a later round "
              f"(intra-annotator; adds no coverage)")
    for who, k in sorted(per_labeller.items()):
        print(f"  {who}: {k} label(s) on "
              f"{len(per_labeller_items.get(who, ()))} posting(s)")

    # WHICH EXTRACTION EACH LABEL WAS FORMED AGAINST. Printed HERE and not in
    # `label report`, whose figures are owned by
    # `git show refactor-freeze-2026-08-02:docs/labelling-report-2026-08-02.md` -- this command owns nothing and is
    # already the "who has labelled what" surface.
    #
    # The three states are not interchangeable and the middle one is the one a
    # reader will misread. `unrecorded` is every row written before 2026-08-02,
    # when nothing captured this; `no extraction` is a posting that genuinely
    # had no job_facts row, which is normal for the gate_rejected and
    # below_floor strata and permanent. See labels.PROVENANCE_COLUMNS.
    by_version = {}
    for row in rows:
        if not row["facts_version_known"]:
            key = "unrecorded (written before 2026-08-02)"
        elif row["facts_version"] is None:
            key = "no extraction at label time"
        else:
            key = f"facts_version {row['facts_version']}"
        by_version[key] = by_version.get(key, 0) + 1
    if by_version:
        print("labels by extraction provenance:")
        for key, k in sorted(by_version.items()):
            print(f"  {key}: {k}")
    return 0


def _three_quantity_report(golden_rows, model_values, selfcheck_path,
                           label_set=None):
    """Assemble and render. Raises labels.Uninterpretable rather than printing
    a bare model-vs-human number -- see labels.Interpretable."""
    import json as _json
    from evals import labels, report
    from evals.tasks import extract as extract_task

    with open(selfcheck_path, "r", encoding="utf-8") as fh:
        floor = _json.load(fh)["fields"]

    kinds = extract_task.FIELD_KINDS
    inter = labels.inter_annotator(golden_rows, kinds)
    intra = labels.intra_annotator(golden_rows, kinds)
    measured = labels.model_vs_human(golden_rows, model_values, kinds)
    triples = labels.interpretable(floor=floor,
                                   ceiling=inter["fields"],
                                   measured=measured["vs_consensus"])
    return report.render_labels(triples, inter=inter, intra=intra,
                                measured=measured, label_set=label_set)


def cmd_label_report(args):
    from evals import corpus as corpus_mod
    from evals import labels

    golden = corpus_mod.load(args.golden)
    if not golden:
        print(f"{args.golden} holds no labels yet. The tables ship empty on "
              "purpose; task 29 is the session that fills them.",
              file=sys.stderr)
        return 1

    model_values = {}
    for row in corpus_mod.load(args.run):
        if row.get("normalized"):
            model_values[row["job_id"]] = row["normalized"]

    try:
        print(_three_quantity_report(golden, model_values, args.selfcheck,
                                     label_set=args.label_set))
    except labels.Uninterpretable as e:
        print(f"evals label report REFUSED: {e}", file=sys.stderr)
        return 2
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
    run_p.add_argument("--golden", default=None,
                       help="a golden-vN.jsonl from `evals label export`: "
                            "also print model-vs-human. Requires --selfcheck")
    run_p.add_argument("--selfcheck", default=None,
                       help="the JSON from `evals selfcheck --out`. This is "
                            "the floor and it is not optional with --golden")
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

    label_p = sub.add_parser(
        "label",
        help="the golden set: draw it, export it, report against it. "
             "NEVER generates a label -- people do that at /v1/label")
    label_sub = label_p.add_subparsers(dest="label_cmd", required=True)

    li = label_sub.add_parser("init-schema",
                              help="create the label tables (admin credential)")
    li.set_defaults(func=cmd_label_init_schema)

    ls = label_sub.add_parser(
        "sample",
        help="draw an eval set across all three strata, INCLUDING rows the "
             "pipeline rejected")
    ls.add_argument("--n", type=int, default=60)
    ls.add_argument("--out", default="evals/fixtures/labelset-v1.jsonl")
    ls.add_argument("--label-set", default="labelset-v1")
    ls.add_argument("--profile", default=None)
    ls.add_argument("--seed", type=int, default=0)
    ls.add_argument("--overlap", type=int, default=10,
                    help="rows shown to EVERY labeller. This is the only "
                         "thing that makes inter-annotator agreement -- the "
                         "ceiling -- computable at all. It also SPENDS each "
                         "labeller's budget: distinct coverage is "
                         "overlap + labellers * (budget - overlap), so 20 "
                         "shared rows against a 20-posting sitting yields 20 "
                         "distinct postings no matter how many people turn up")
    ls.add_argument("--per-platform", type=int, default=100_000,
                    help="newest-N per platform. The default is effectively "
                         "the whole table on purpose: at 400 the window held "
                         "29 of pursuit's 144 surfaced postings")
    ls.add_argument("--note", default=None)
    ls.add_argument("--dry-run", action="store_true")
    ls.set_defaults(func=cmd_label_sample)

    le = label_sub.add_parser("export", help="write golden-vN.jsonl")
    le.add_argument("--out", default="evals/fixtures/golden-v1.jsonl")
    le.add_argument("--label-set", default=None)
    le.set_defaults(func=cmd_label_export)

    lst = label_sub.add_parser("status", help="who has labelled what")
    lst.add_argument("--label-set",
                     help="pin the distinct-posting count to one set. Task "
                          "29's '>=100 distinct' threshold belongs to a single "
                          "set, so with more than one drawn an unpinned count "
                          "reads as met before it is")
    lst.set_defaults(func=cmd_label_status)

    lr = label_sub.add_parser(
        "report",
        help="model vs human, with the floor and ceiling beside it. Refuses "
             "to print without both")
    lr.add_argument("--golden", default="evals/fixtures/golden-v1.jsonl")
    lr.add_argument("--run", required=True,
                    help="a results JSONL from `evals run --out`")
    lr.add_argument("--selfcheck", required=True,
                    help="the JSON from `evals selfcheck --out`. The floor.")
    lr.add_argument("--label-set", default=None)
    lr.set_defaults(func=cmd_label_report)

    cache_p = sub.add_parser("cache", help="inspect the replay cache")
    cache_sub = cache_p.add_subparsers(dest="cache_cmd", required=True)
    st = cache_sub.add_parser("stats")
    st.set_defaults(func=cmd_cache_stats)

    args = p.parse_args(argv)
    envfile.load(ENV_FILE)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
