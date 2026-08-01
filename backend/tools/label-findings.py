#!/usr/bin/env python3
"""
Re-derive the findings a labelling sitting produces, from `eval_labels`.

READ-ONLY. No LLM call, no API key, no write of any kind.

WHY THIS EXISTS AT ALL
    HANDOFF.md has asked three separate sessions to "re-derive it, do not
    re-quote it" and has then been re-quoted three times. The per-posting
    timing number is the worst case: measured once at 154 s from FOUR
    intervals, written into two documents, and used to size every
    Builder-session estimate in the run. Re-derived at n=29 it is 93 s, and
    the caveat printed beside it -- "the fastest interval is the first, which
    is the opposite of a warm-up curve" -- turned out to be backwards.

    An instruction to re-derive that requires someone to write four lines of
    SQL first is an instruction that decays into a quotation. This is those
    four lines, kept, so that the next session runs a command instead.

    python3 tools/label-findings.py                     # every section
    python3 tools/label-findings.py --timing            # the stopwatch reading
    python3 tools/label-findings.py --break-secs 900    # a longer break

WHAT IT DELIBERATELY DOES NOT PRINT
    Model-vs-human agreement. `evals label report` exits 2 for as long as
    there is one labeller, because a model score has no meaning without the
    inter-annotator ceiling to denominate it -- if humans agree with each
    other 98% a model at 80% is bad, and if they agree 79% it has saturated
    the task. There is deliberately no `--force` on that command, and this
    tool is not a way around it: a number computed here and pasted into a
    document would have no exit code to protect the next reader.

    Every quantity below is either the humans' own answers (a marginal rate)
    or a human answer against a PIPELINE decision (a recall bound). Neither
    is a per-item agreement rate and neither needs a ceiling.

WHY IT IS NOT PART OF `evals label`
    `evals label status` answers "who has labelled what" and `evals label
    report` is the guarded three-quantity report. This is analysis of a
    sitting in progress, and folding it into either one would put unguarded
    numbers next to guarded ones in the same command's output. They are
    better apart.

READING THE TIMING SECTION
    Intervals are printed RAW, in order, before any statistic. That is the
    point: a sitting contains breaks, and a median taken over an interval
    list containing a 96-minute gap is a statistic about dinner. --break-secs
    is the threshold above which an interval is called a break and excluded,
    and both figures are printed so the exclusion can be argued with.

    The quartile split exists because "is there a warm-up curve" is the
    question a growing label count is supposed to answer, and a single
    median cannot show it.
"""

import os
import sys
import argparse
import statistics
from datetime import datetime

# ingest/ and tools/ sit one level below the pipeline modules they import
# (schema, evals, ...). Python puts THIS file's directory on sys.path, not
# its parent, so the parent is added by hand.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import schema                    # noqa: E402
from evals import metrics        # noqa: E402
from lib import dbconn, envfile  # noqa: E402

# Read-only tool, so it loads the pipeline's own .env rather than requiring
# the caller to export DATABASE_URL first. Same contract as
# relevance-report.py:69 and derive-role-tracks.py:99.
envfile.load(os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

#: The two answers that mean "your vocabulary has no word for this posting".
#: They are at different grains -- `no_track_fits` is a verdict on the nine
#: role_track values, `other` a verdict on the twenty-six archetypes -- and
#: they are counted separately for that reason. Neither is an abstention;
#: `labels.validate()` stores an abstention as NULL and both of these as
#: themselves, which is the distinction that decision DEC-60 exists to preserve.
NO_TRACK_FITS = "no_track_fits"
ARCHETYPE_OTHER = "other"


def load_postings(conn, label_set):
    """One row per labelled posting: identity, stratum, human and model answers.

    LEFT JOIN on job_facts is load-bearing rather than defensive: 26 of the 50
    `gate_rejected` rows in pursuit-v1 have no job_facts row at all, so an
    inner join would silently drop the stratum whose whole purpose is to
    contain postings the pipeline threw away.
    """
    cur = conn.execute("""
        SELECT j.id, j.company_name, j.title, i.stratum, i.position,
               MIN(l.labelled_at) AS first_answer,
               MAX(CASE WHEN l.field = 'role_track'      THEN l.value END),
               MAX(CASE WHEN l.field = 'role_archetype'  THEN l.value END),
               MAX(CASE WHEN l.field = 'would_apply'     THEN l.value END),
               f.role_track, f.role_archetype, f.ai_involvement
          FROM eval_labels l
          JOIN eval_label_items i
            ON i.job_id = l.job_id AND i.label_set = l.label_set
          JOIN jobs j ON j.id = l.job_id
          LEFT JOIN job_facts f ON f.job_id = l.job_id
         WHERE l.label_set = %s
         GROUP BY j.id, j.company_name, j.title, i.stratum, i.position,
                  f.role_track, f.role_archetype, f.ai_involvement
         ORDER BY first_answer
    """, (label_set,))
    cols = ("job_id", "company", "title", "stratum", "position", "first_answer",
            "human_track", "human_archetype", "would_apply",
            "model_track", "model_archetype", "model_ai")
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def load_field_answers(conn, label_set):
    """Every stored answer, including the NULLs. Abstentions are the point.

    A NULL here is "I can't tell from this posting", stored deliberately and
    counted rather than folded in -- folding them in as a value would score
    two people who both gave up as two people who concurred.
    """
    cur = conn.execute("""
        SELECT field, value, COUNT(*)
          FROM eval_labels
         WHERE label_set = %s
         GROUP BY field, value
         ORDER BY field, COUNT(*) DESC
    """, (label_set,))
    return cur.fetchall()


def report_header(conn, label_set, postings):
    print(f"\n=== {label_set} -- state, as of {datetime.now():%Y-%m-%d %H:%M} ===\n")
    cur = conn.execute("""
        SELECT COUNT(*), COUNT(DISTINCT job_id), COUNT(DISTINCT labeller_id),
               COUNT(DISTINCT round_no)
          FROM eval_labels WHERE label_set = %s
    """, (label_set,))
    rows, jobs, labellers, rounds = cur.fetchone()
    print(f"  {rows} label rows / {jobs} postings / {labellers} labeller(s)"
          f" / {rounds} round(s)")
    by_stratum = {}
    for p in postings:
        by_stratum[p["stratum"]] = by_stratum.get(p["stratum"], 0) + 1
    print("  labelled by stratum: "
          + ", ".join(f"{k} {v}" for k, v in sorted(by_stratum.items())))
    if labellers < 2:
        print("\n  NOTE: one labeller. `evals label report` exits 2 and that is"
              "\n  correct behaviour -- there is no inter-annotator ceiling to"
              "\n  denominate a model score against. Nothing below is a model"
              "\n  score. See the module docstring.")


def interval_stats(intervals, break_secs):
    """Split an interval list into breaks and postings, and describe both.

    PURE, and separated from the printing for one reason: this is the number
    that has already been published wrong once, off a sample of four, and it
    is the number every Builder-session estimate in the run is built from.
    Everything else this tool prints is a count that can be eyeballed against
    the raw rows; this one is a statistic with a judgement call inside it.

    `curve` compares the first and last quartile because "is the labeller
    speeding up" is exactly what a growing label count is supposed to settle,
    and a single median structurally cannot answer it. It is None below the
    n where the comparison would be two points against two points.

    Returns None when nothing survives the break filter -- an entirely
    interrupted sitting is a real outcome and the caller still has to print.
    """
    breaks = [x for x in intervals if x > break_secs]
    kept = [x for x in intervals if x <= break_secs]
    if not kept:
        return None
    q = len(kept) // 4
    curve = None
    if q >= 3:
        curve = (q, statistics.mean(kept[:q]), statistics.mean(kept[-q:]))
    return {
        "breaks": breaks,
        "kept": kept,
        "median_all": statistics.median(intervals),
        "mean_all": statistics.mean(intervals),
        "median": statistics.median(kept),
        "mean": statistics.mean(kept),
        "curve": curve,
    }


def report_timing(postings, break_secs):
    """The stopwatch reading, from labelled_at. No stopwatch required."""
    print("\n=== timing ===")
    print("Instrument: successive MIN(labelled_at) per job_id, in submit order.")
    if len(postings) < 3:
        print(f"  {len(postings)} posting(s) -- too few for an interval.")
        return
    times = [datetime.fromisoformat(p["first_answer"]) for p in postings]
    iv = [(times[i + 1] - times[i]).total_seconds() for i in range(len(times) - 1)]

    print(f"\n  raw intervals (n={len(iv)}), seconds, in order:")
    for i in range(0, len(iv), 10):
        print("    " + " ".join(f"{int(x):>5}" for x in iv[i:i + 10]))

    st = interval_stats(iv, break_secs)
    print(f"\n  {0 if st is None else len(st['breaks'])} interval(s) over"
          f" --break-secs={break_secs} treated as breaks in the sitting")
    if st is None:
        print("  nothing left after exclusions.")
        return
    if st["breaks"]:
        print("    excluded: " + ", ".join(f"{int(x)}s" for x in st["breaks"]))

    print(f"\n  including breaks: median {st['median_all']:.0f}s"
          f"  mean {st['mean_all']:.0f}s  (n={len(iv)})")
    print(f"  EXCLUDING breaks: median {st['median']:.0f}s"
          f"  mean {st['mean']:.0f}s  (n={len(st['kept'])})")

    if st["curve"] is None:
        print("\n  too few intervals to ask whether there is a warm-up curve.")
    else:
        q, first, last = st["curve"]
        print(f"\n  first {q}: mean {first:.0f}s   |   last {q}: mean {last:.0f}s")
        if last < first * 0.8:
            print("    -> the labeller is speeding up. A rate taken from the"
                  "\n       first few postings overstates the cost of the rest.")
        elif last > first * 1.25:
            print("    -> the labeller is slowing down. Fatigue, or the queue"
                  "\n       got harder -- the strata are interleaved, so check"
                  "\n       which.")
        else:
            print("    -> no clear curve either way at this n.")

    rate = st["median"]
    print(f"\n  budgets at the median of {rate:.0f}s/posting:")
    for label, n in (("10 overlap rows (a second labeller)", 10),
                     ("20 minutes", None), ("60 postings", 60),
                     ("100 postings (the DoD)", 100), ("200 postings", 200)):
        if n is None:
            print(f"    {label:38} {20 * 60 / rate:.0f} postings")
        else:
            print(f"    {label:38} {n * rate / 60:.0f} min"
                  f"  ({n * rate / 3600:.1f} h)")
    print("\n  Caveats that belong beside this number wherever it is quoted:"
          "\n    submit-to-submit includes reading; the FIRST posting's own"
          "\n    reading time is not in the figure at all, so the true rate is"
          "\n    higher than this, not lower.")


def report_recall(postings):
    """would_apply against the PIPELINE's decision. A recall bound, not a rate.

    `gate_rejected` cannot enter a precision rate at all -- those rows were
    never surfaced, so there is no ranked list for them to be precise about.
    What they yield is k of n: how many postings the pipeline discarded a
    human would have applied to.
    """
    print("\n=== the recall question ===")
    print("Instrument: eval_labels.would_apply x eval_label_items.stratum.")
    print("This is a human answer against a PIPELINE decision, not against the"
          "\nmodel. It is a recall bound; it is not an agreement rate.\n")
    strata = ("surfaced", "below_floor", "gate_rejected")
    print(f"  {'stratum':<14} {'yes':>4} {'no':>4} {'n':>4}   "
          f"{'rate':>6}  95% CI")
    for s in strata:
        rows = [p for p in postings if p["stratum"] == s]
        yes = sum(1 for p in rows if p["would_apply"] == "yes")
        no = sum(1 for p in rows if p["would_apply"] == "no")
        n = yes + no
        if not n:
            print(f"  {s:<14} {'-':>4} {'-':>4} {0:>4}   none labelled yet")
            continue
        lo, hi = metrics.wilson(yes, n)
        print(f"  {s:<14} {yes:>4} {no:>4} {n:>4}   {yes / n:>5.0%}"
              f"  [{lo:.2f}, {hi:.2f}]")

    missed = [p for p in postings
              if p["stratum"] != "surfaced" and p["would_apply"] == "yes"]
    print(f"\n  {len(missed)} posting(s) the pipeline did NOT surface that the"
          " labeller would apply to:")
    if not missed:
        print("    none. The recall question has not been earned yet.")
        return
    for p in missed:
        facts = ("no job_facts row" if p["model_ai"] is None
                 else f"ai_involvement={p['model_ai']}")
        print(f"    [{p['stratum']:<13}] {(p['company'] or '?')[:22]:22}"
              f" | {p['title'][:40]}")
        print(f"        {facts}")
    print("\n  HANDOFF.md: the back half of the set is bought \"almost entirely"
          "\n  for the recall question\", and is earned \"the moment any"
          "\n  gate_rejected row turns out to be one the owner would genuinely"
          "\n  apply to\". Read the count above against that sentence.")


def report_vocabulary(postings, answers):
    """How often the human had no word for the posting. A marginal rate.

    Quoted bare this number is worthless -- the model's own `other` rate is
    measured on a different population (the cohort-eligible corpus) than this
    one (a stratified 200-row eval set). Both denominators are printed for
    that reason.
    """
    print("\n=== the vocabulary gap ===")
    print("Instrument: the humans' own role_track / role_archetype answers.")
    n = len(postings)
    nt = sum(1 for p in postings if p["human_track"] == NO_TRACK_FITS)
    oa = sum(1 for p in postings if p["human_archetype"] == ARCHETYPE_OTHER)
    for label, k in ((f"role_track = {NO_TRACK_FITS}", nt),
                     (f"role_archetype = {ARCHETYPE_OTHER}", oa)):
        lo, hi = metrics.wilson(k, n)
        print(f"  {label:<32} {k:>3} of {n}  {k / n:>5.0%}  [{lo:.2f}, {hi:.2f}]")
    print(f"\n  Population: {n} labelled postings of a stratified 200-row eval"
          "\n  set. NOT the cohort corpus. Any comparison to task 12's `other`"
          "\n  rate is a comparison across two different populations and must"
          "\n  say so -- it is not an agreement figure.")

    print("\n  per-field answers, abstentions counted separately:")
    fields = {}
    for field, value, count in answers:
        fields.setdefault(field, []).append((value, count))
    for field in sorted(fields):
        vals = fields[field]
        nulls = sum(c for v, c in vals if v is None)
        named = [(v, c) for v, c in vals if v is not None]
        print(f"    {field}  ({nulls} abstention(s))")
        for v, c in named:
            print(f"        {v:<32} {c:>3}")


def report_side_list(postings):
    """The postings the vocabulary could not express, with the model beside them.

    There is no free-text field on the form, by design -- so the labels record
    THAT nothing fit and never WHAT was missing. This list is the only place
    the content can live, and it is the input to re-running
    tools/derive-role-tracks.py.
    """
    print("\n=== side list: postings no value described ===")
    rows = [p for p in postings
            if p["human_track"] == NO_TRACK_FITS
            or p["human_archetype"] == ARCHETYPE_OTHER]
    print(f"{len(rows)} of {len(postings)} labelled postings. The model's own"
          " answers are shown\nbeside each one so the shape of the gap is"
          " legible -- this is a side-by-side\nfor reading, not a scored"
          " comparison.\n")
    for p in sorted(rows, key=lambda r: (r["stratum"], r["company"] or "")):
        print(f"  [{p['stratum']:<13}] {(p['company'] or '?')[:22]:22}"
              f" | {p['title'][:44]}")
        print(f"      human  track={p['human_track']} arch={p['human_archetype']}"
              f" apply={p['would_apply']}")
        print(f"      model  track={p['model_track']} arch={p['model_archetype']}"
              f" ai={p['model_ai']}")


def main():
    p = argparse.ArgumentParser(
        description="Re-derive a labelling sitting's findings from eval_labels "
                    "(read-only). Prints no model-vs-human agreement.")
    p.add_argument("--label-set", default="pursuit-v1",
                   help="label set to report on")
    p.add_argument("--break-secs", type=float, default=600,
                   help="an interval longer than this is a break in the "
                        "sitting, not a posting; excluded from the rate")
    p.add_argument("--timing", action="store_true", help="the stopwatch reading")
    p.add_argument("--recall", action="store_true", help="would_apply x stratum")
    p.add_argument("--vocabulary", action="store_true", help="no_track_fits/other")
    p.add_argument("--side-list", action="store_true", help="the postings themselves")
    args = p.parse_args()

    picked = (args.timing, args.recall, args.vocabulary, args.side_list)
    everything = not any(picked)

    conn = dbconn.connect_or_exit("label-findings", schema=schema.SCHEMA)
    postings = load_postings(conn, args.label_set)
    if not postings:
        print(f"No labels for label set {args.label_set!r}.")
        conn.close()
        return
    answers = load_field_answers(conn, args.label_set)

    report_header(conn, args.label_set, postings)
    if everything or args.timing:
        report_timing(postings, args.break_secs)
    if everything or args.recall:
        report_recall(postings)
    if everything or args.vocabulary:
        report_vocabulary(postings, answers)
    if everything or args.side_list:
        report_side_list(postings)
    print()
    conn.close()


if __name__ == "__main__":
    main()
