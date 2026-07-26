#!/usr/bin/env python3
"""
Score the whole relevant backlog with one model, in one configuration.

WHY A DRIVER INSTEAD OF A BIGGER SCORE_BATCH_SIZE
    score.py is built for a nightly batch: pick N unscored jobs, score them,
    exit. Raising N to 5,000 would work in principle and be a bad idea in
    practice -- one process holding one connection for two days, where a
    dropped connection, an OOM, or a laptop lid loses the whole run.

    This calls score.py in a loop instead. Each invocation is a short,
    independent transaction that commits as it goes, so the backfill is
    resumable by construction: nothing tracks progress, because "what is
    still unscored" IS the progress, and select_unscored_jobs asks the
    database that question fresh every round. Interrupt it whenever; rerun
    it whenever; it picks up where it stopped.

CONSISTENCY IS THE POINT
    A fit_score is only comparable to another fit_score produced the same
    way. Ranking 5,000 jobs scored by a mix of models and temperatures
    produces an ordering that partly reflects which model happened to see
    which posting, which is worse than useless -- it looks like a ranking.

    So this pins the configuration and refuses to drift:

      * The model label is captured before the first round and re-checked
        every round. If it changes mid-run, the backfill stops rather than
        silently producing a two-model corpus.
      * --rescore-stale deletes scores that came from a different model so
        they are re-done in the current one. Off by default: it deletes
        rows, and that should be a decision, not a side effect.

    Temperature is pinned in llm.py (DEFAULT_TEMPERATURE = 0), which
    matters here more than anywhere else -- at the provider default, the
    same model rescored the same jobs into a materially different order.

RUNTIME
    glm-4.5-flash runs about 39s per job. At --workers 3 that is roughly
    19 hours for 5,000 jobs; at --workers 1, about 56. Slow is fine -- it
    is one pass over a backlog, it survives interruption, and the daily
    cron keeps working while it runs.

USAGE
    # see the plan, touch nothing
    python3 backfill-scores.py --dry-run

    # the actual run (nohup so it survives the terminal closing)
    nohup python3 backfill-scores.py --workers 3 > backfill.log 2>&1 &

    # rescore the handful from older models too, for one uniform corpus
    python3 backfill-scores.py --rescore-stale

STOPPING
    Ctrl-C once: finishes the round in flight, prints a summary, exits.
    Everything already scored stays scored.
"""

import os
import sys
import time
import signal
import argparse
import subprocess
import urllib.parse
from datetime import timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

import schema      # noqa: E402
import relevance   # noqa: E402
import score       # noqa: E402
import llm         # noqa: E402
from pipelib import dbconn  # noqa: E402

#: Progress is the whole point of this script, and it will normally be run
#: as `nohup ... > backfill.log &`. Python block-buffers stdout when it is
#: not a terminal, so without this the log stays empty for hours and a run
#: that is working looks indistinguishable from one that is hung.
try:
    sys.stdout.reconfigure(line_buffering=True)
except AttributeError:      # pragma: no cover -- pre-3.7
    pass

_stop = False


def _on_sigint(signum, frame):
    """Finish the current round rather than dying mid-batch.

    score.py commits per job, so a hard kill would not corrupt anything --
    but letting the round finish keeps the final summary truthful.
    """
    global _stop
    if _stop:
        print("\nbackfill: second interrupt -- exiting now.")
        sys.exit(130)
    _stop = True
    print("\nbackfill: interrupt received, finishing this round then stopping...")


def model_label():
    """Same label score.py writes into scoring_model, so they can be compared."""
    host = urllib.parse.urlparse(llm.base_url()).hostname or llm.base_url()
    return f"{llm.model()}@{host}"


def remaining(conn, profile, cfg):
    """Unscored, open, relevant, and actually describable.

    Mirrors select_unscored_jobs' WHERE clause. Kept as a count query rather
    than len(select_unscored_jobs(...)) so progress does not depend on the
    batch limit.
    """
    tier_expr, tier_params = relevance.tier_sql(cfg)
    params = {"status": schema.STATUS_OPEN, "profile": profile,
              "max_tier": relevance.max_tier(cfg), **tier_params}
    return conn.execute(
        f"""SELECT count(*) FROM {schema.TABLE} j
            WHERE j.status = %(status)s
              AND coalesce(j.description_text, '') <> ''
              AND NOT EXISTS (SELECT 1 FROM {schema.SCORES_TABLE} s
                              WHERE s.job_id = j.id AND s.profile = %(profile)s)
              AND {tier_expr} <= %(max_tier)s""",
        params).fetchone()[0]


def score_census(conn, profile):
    """scoring_model -> count, for the profile. Includes FAILED: tombstones."""
    return conn.execute(
        f"""SELECT scoring_model, count(*) FROM {schema.SCORES_TABLE}
            WHERE profile = %(profile)s GROUP BY scoring_model
            ORDER BY count(*) DESC""",
        {"profile": profile}).fetchall()


def delete_stale(conn, profile, keep_label):
    """Drop scores from any other model so they get redone in this one."""
    n = conn.execute(
        f"""DELETE FROM {schema.SCORES_TABLE}
            WHERE profile = %(profile)s AND scoring_model IS DISTINCT FROM %(keep)s""",
        {"profile": profile, "keep": keep_label}).rowcount
    conn.commit()
    return n


def run_round(batch_size, workers, timeout):
    """One score.py invocation. Returns (ok, output)."""
    env = os.environ.copy()
    env["SCORE_BATCH_SIZE"] = str(batch_size)
    env["SCORE_MAX_WORKERS"] = str(workers)
    # A deferred job costs a full round-trip and scores nothing, so the
    # backfill leans generous on the timeout -- see llm.DEFAULT_TIMEOUT_SECS.
    env.setdefault("LLM_TIMEOUT_SECS", "150")
    try:
        r = subprocess.run(
            [sys.executable, os.path.join(SCRIPT_DIR, "score.py")],
            cwd=SCRIPT_DIR, env=env, capture_output=True, text=True,
            timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, f"score.py exceeded {timeout}s and was killed"
    out = (r.stdout or "").strip()
    if r.returncode != 0:
        return False, f"exit {r.returncode}: {out} {(r.stderr or '').strip()[:300]}"
    return True, out


def human(seconds):
    return str(timedelta(seconds=int(seconds)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch-size", type=int, default=40,
                    help="jobs per score.py round (default 40)")
    ap.add_argument("--workers", type=int, default=3,
                    help="concurrent scoring requests (default 3)")
    ap.add_argument("--pause", type=float, default=2.0,
                    help="seconds between rounds (default 2)")
    ap.add_argument("--max-hours", type=float,
                    help="stop cleanly after this long")
    ap.add_argument("--stall-rounds", type=int, default=3,
                    help="give up after this many rounds with no progress")
    ap.add_argument("--round-timeout", type=int, default=3600,
                    help="kill a single round after this many seconds")
    ap.add_argument("--rescore-stale", action="store_true",
                    help="DELETE scores from other models so they are redone")
    ap.add_argument("--dry-run", action="store_true",
                    help="report the plan and exit without scoring")
    args = ap.parse_args()

    label = model_label()
    conn = dbconn.connect_or_exit("backfill-scores", schema=schema.SCHEMA)
    persona = score.load_persona()
    profile = schema.resolve_profile(persona)
    cfg = relevance.load()

    left = remaining(conn, profile, cfg)
    census = score_census(conn, profile)

    print(f"backfill-scores")
    print(f"  model        {label}  (temperature {llm.DEFAULT_TEMPERATURE})")
    print(f"  profile      {profile}")
    print(f"  max tier     {relevance.max_tier(cfg)}")
    print(f"  unscored     {left:,}")
    if census:
        print(f"  existing scores:")
        for m, n in census:
            flag = "" if m == label else "   <- different configuration"
            print(f"     {str(m):<44} {n:>6,}{flag}")

    stale = [(m, n) for m, n in census if m != label]
    if stale and not args.rescore_stale:
        total_stale = sum(n for _, n in stale)
        print(f"\n  NOTE: {total_stale} score(s) came from a different model. They are"
              f"\n  left alone, so the corpus will mix configurations. Re-run with"
              f"\n  --rescore-stale to delete and redo them in {label}.")

    if args.dry_run:
        est = left * 39.0 / max(1, args.workers)
        print(f"\n  dry run -- nothing scored. Rough estimate at 39s/job, "
              f"{args.workers} workers: {human(est)}")
        conn.close()
        return

    if args.rescore_stale and stale:
        n = delete_stale(conn, profile, label)
        print(f"\n  deleted {n} score(s) from other models -- they will be redone")
        left = remaining(conn, profile, cfg)
        print(f"  unscored is now {left:,}")

    if not left:
        print("\n  nothing to do.")
        conn.close()
        return

    signal.signal(signal.SIGINT, _on_sigint)
    started = time.time()
    start_left = left
    rounds = stalled = failed_rounds = 0
    print(f"\n  starting: {left:,} to score, batch {args.batch_size}, "
          f"{args.workers} workers. Ctrl-C to stop cleanly.\n")

    while left > 0 and not _stop:
        if args.max_hours and (time.time() - started) / 3600 >= args.max_hours:
            print(f"  reached --max-hours {args.max_hours}, stopping.")
            break

        rounds += 1
        ok, out = run_round(args.batch_size, args.workers, args.round_timeout)
        if out:
            print(f"  [{rounds:>4}] {out}")
        if not ok:
            failed_rounds += 1
            print(f"  [{rounds:>4}] ROUND FAILED: {out}")
            if failed_rounds >= args.stall_rounds:
                print(f"  {failed_rounds} consecutive failures -- stopping.")
                break
            time.sleep(min(60, 5 * failed_rounds))
            continue
        failed_rounds = 0

        now_left = remaining(conn, profile, cfg)
        done = left - now_left
        left = now_left

        if done <= 0:
            stalled += 1
            # Every job in the batch deferred (rate limit, endpoint down) or
            # tombstoned without reducing the count. Retrying immediately just
            # burns the same wall on the same rows.
            if stalled >= args.stall_rounds:
                print(f"  no progress for {stalled} rounds -- the endpoint is "
                      f"probably rate-limiting or down. Nothing was lost; "
                      f"rerun later to resume.")
                break
            time.sleep(min(120, 15 * stalled))
            continue
        stalled = 0

        scored = start_left - left
        elapsed = time.time() - started
        rate = scored / elapsed if elapsed else 0
        eta = (left / rate) if rate > 0 else 0
        pct = 100.0 * scored / start_left if start_left else 100.0
        print(f"         {scored:,}/{start_left:,} ({pct:.1f}%)  "
              f"{rate*3600:.0f}/hr  elapsed {human(elapsed)}  eta {human(eta)}")

        if args.pause:
            time.sleep(args.pause)

    elapsed = time.time() - started
    scored = start_left - left
    print(f"\nbackfill-scores: {scored:,} scored in {human(elapsed)} "
          f"({rounds} rounds), {left:,} still unscored.")

    final = score_census(conn, profile)
    tombstones = sum(n for m, n in final
                     if m and str(m).startswith(llm.FAILED_PREFIX))
    if tombstones:
        print(f"  {tombstones} job(s) tombstoned as permanently unparseable "
              f"-- they will not be retried.")
    models = [m for m, _ in final if m and not str(m).startswith(llm.FAILED_PREFIX)]
    if len(set(models)) > 1:
        print(f"  WARNING: scores now come from {len(set(models))} configurations: "
              f"{sorted(set(models))}")
    conn.close()


if __name__ == "__main__":
    main()
