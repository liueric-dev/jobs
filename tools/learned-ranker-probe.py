#!/usr/bin/env python3
"""
Is the ranking ceiling the FEATURES or the hand-tuned WEIGHTS?

THE QUESTION
    match.py reaches 8/20 precision@20 against the LLM's labels, and a sweep
    across the entire plausible weight space moves recall only 0.468-0.484.
    Two very different explanations fit that:

      the weights   -- 17 fields carry the signal, but hand-tuned points
                       arranged from persona.json do not extract it.
      the features  -- 17 coarse fields cannot express a judgement made from
                       reading 3,500 characters of prose, whatever the weights.

    They imply opposite next moves. If it is the weights, new extraction fields
    are money spent on a non-problem and the answer is a learned ranker. If it
    is the features, the learned ranker has nothing extra to learn from and the
    answer is richer extraction.

    This script decides between them for zero marginal cost: fit a model on the
    features the rules already see, against labels that were paid for months
    ago, and see whether learning the weights beats hand-setting them.

THE THREE ARMS
    A  exactly what score_job() reads. The question above, asked precisely --
       same inputs, learned weights instead of written ones.
    B  A plus the job_facts columns nothing currently scores on
       (employment_type, visa_sponsorship, comp_*, years_experience_max).
       Free to test and free to adopt: they are already extracted.
    C  B plus tf-idf over the posting's title and full description_text.
       NOT A SHIPPABLE RANKER -- 917 rows against tens of thousands of text
       columns overfits anything, which is why it is only ever read
       out-of-fold and only as an UPPER BOUND. Its job is to estimate how much
       of the LLM's judgement is recoverable from the prose the LLM actually
       read, and its top-weighted terms are evidence about WHICH new
       extraction fields would pay -- where HANDOFF section 5 currently lists
       five untested hypotheses.

OUT-OF-FOLD OR NOTHING
    An in-sample precision@20 on this data is near 20/20 for every arm and
    means nothing whatsoever. It is the single most likely way this experiment
    returns a confident wrong answer, so no in-sample number is computed
    anywhere in this file, not even as a diagnostic. Every reported figure is
    out-of-fold, averaged over repeated stratified 5-fold CV, and reported with
    the spread across repeats.

    precision@20 alone is too noisy to decide on: a random draw of 20 from this
    corpus has a standard deviation of ~1.5 hits, so 8 -> 11 is barely one
    standard deviation of nothing. Average precision over the full ranking and
    the precision@k curve are reported alongside, and the comparison against
    the rules is a bootstrap of the DIFFERENCE on shared resamples rather than
    two point estimates eyeballed side by side.

GUARDS, BECAUSE THIS IS THE FIFTH MEASUREMENT TRAP AND THERE WERE FOUR BEFORE
    * the sample and the rules scores come from calibrate-match.load_pairs and
      match.load_facts, not from a reimplementation, so "same postings, same
      ranking function" is structural rather than asserted. Nothing is read
      from job_matches -- that table is floor-filtered and using it moves
      quality metrics for reasons that are pure storage policy (HANDOFF 4.1).
    * a label-shuffle control runs the identical pipeline on permuted labels.
      It must land at the random baseline. Anything higher is leakage and the
      run reports VOID instead of a verdict.
    * every seed is pinned and printed.

READ-ONLY. Zero LLM calls, zero writes, no network.

SETUP -- scikit-learn is deliberately not a dependency of this repo
    python3 -m venv /tmp/mlvenv
    /tmp/mlvenv/bin/pip install scikit-learn 'psycopg[binary]'
    set -a && . ~/.hermes/.env && set +a
    /tmp/mlvenv/bin/python tools/learned-ranker-probe.py --profile tech

    psycopg too, because a venv does not see the system site-packages the rest
    of the repo runs against. Takes about 20 minutes for all three arms.

USAGE
    learned-ranker-probe.py                      # all arms, 10 repeats
    learned-ranker-probe.py --arms A B           # skip the expensive text arm
    learned-ranker-probe.py --repeats 3          # quick pass while iterating
    learned-ranker-probe.py --terms 40           # more arm-C evidence
"""

import argparse
import importlib.util
import os
import random
import re
import sys
import warnings

# sklearn 1.9 deprecation chatter about attribute layouts changing in 1.10.
# Nothing here reads the attributes in question, and 50 folds x 3 arms of it
# buries the actual output.
warnings.filterwarnings("ignore", category=FutureWarning)

# ingest/ and tools/ sit one level below the pipeline modules they import
# (schema, relevance, llm, ...). Python puts THIS file's directory on sys.path,
# not its parent, so the parent is added by hand. pipelib needs nothing -- it is
# an installed package (pip install --user -e ~/apps/pipelib).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import match      # noqa: E402
import profiles   # noqa: E402
import schema     # noqa: E402
from pipelib import dbconn  # noqa: E402


def _sibling(name):
    """Import a tool next to this one whose filename is hyphenated.

    Used for calibrate-match.py, which is the authority on which postings are
    evaluable and what the rules score them. The alternative is duplicating
    load_pairs here, and a second copy of the sample definition is exactly how
    two tools start disagreeing about the number one of them exists to beat.
    """
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), name)
    spec = importlib.util.spec_from_file_location(
        name.replace("-", "_").removesuffix(".py"), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cal = _sibling("calibrate-match.py")

try:
    import numpy as np
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.feature_extraction import DictVectorizer
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegressionCV
    from sklearn.metrics import average_precision_score
    from sklearn.model_selection import RepeatedStratifiedKFold
    from sklearn.pipeline import FeatureUnion, Pipeline
    from sklearn.preprocessing import FunctionTransformer, MaxAbsScaler
except ImportError:
    sys.exit("learned-ranker-probe needs scikit-learn, which this repo "
             "deliberately does not depend on. Install it somewhere "
             "disposable:\n"
             "  python3 -m venv /tmp/mlvenv\n"
             "  /tmp/mlvenv/bin/pip install scikit-learn 'psycopg[binary]'\n"
             "  /tmp/mlvenv/bin/python tools/learned-ranker-probe.py")

#: One seed for the whole run, printed in the header. Every split, every
#: bootstrap resample and every shuffle derives from it.
SEED = 11

#: fit_score at or above which a posting is a positive. Matches the threshold
#: calibrate-match.py recalls against, so the two tools answer the same
#: question about the same set.
GOOD = 80

#: What the corpus looked like when the decision rule below was written. A
#: different shape does not invalidate the run, but the reference numbers in
#: HANDOFF section 1 no longer line up with it.
REFERENCE_N = 917
REFERENCE_POSITIVES = 134

#: Draws to average the random baseline over. One draw is not a baseline: at a
#: ~15% base rate a single sample of 20 lands anywhere from 1 to 6 hits.
RANDOM_DRAWS = 500
BOOTSTRAP_DRAWS = 2000

#: The columns match.load_facts returns beyond bookkeeping -- i.e. exactly the
#: inputs score_job reads. Derived from the module rather than retyped so arm A
#: cannot silently drift away from the function it is being compared against.
ARM_A_DROP = ("job_id", "facts_version")

#: Already extracted, never scored on. Arm B's whole content.
ARM_B_EXTRA = ("employment_type", "visa_sponsorship", "comp_min", "comp_max",
               "years_experience_max")

#: Fields whose absence is informative rather than imputable. years_experience_min
#: is populated on 42% of postings, comp_* on ~13%, years_experience_max on 5%:
#: imputing a mean into those invents a signal the extractor never found.
NUMERIC = ("years_experience_min", "years_experience_max",
           "comp_min", "comp_max")


def load_sample(conn, profile_obj):
    """The evaluable postings, their rules score, their facts and their prose.

    Deliberately delegates both halves of the sample definition:

      calibrate-match.load_pairs  decides WHICH postings are evaluable and
                                  what the rules score them -- so this script
                                  cannot disagree with the tool whose number
                                  it is trying to beat.
      match.load_facts            supplies arm A's features -- so arm A is
                                  score_job's input set by construction rather
                                  than by a hand-copied column list.

    Only the arm B extras and the text are queried here, because nothing else
    exposes them.
    """
    pairs = cal.load_pairs(conn, profile_obj)
    facts_by_id = {f["job_id"]: f for f in match.load_facts(conn)}

    ids = [p["job_id"] for p in pairs]
    rows = conn.execute(
        f"""
        SELECT f.job_id, f.employment_type, f.visa_sponsorship, f.comp_min,
               f.comp_max, f.years_experience_max, f.summary,
               j.title, j.description_text
        FROM {schema.FACTS_TABLE} f
        JOIN {schema.TABLE} j ON j.id = f.job_id
        WHERE f.job_id = ANY(%s)
        """, (ids,)).fetchall()
    extra = {r[0]: {"employment_type": r[1], "visa_sponsorship": r[2],
                    "comp_min": r[3], "comp_max": r[4],
                    "years_experience_max": r[5], "summary": r[6] or "",
                    "title": r[7] or "", "description_text": r[8] or ""}
             for r in rows}

    sample = []
    for p in pairs:
        f = facts_by_id.get(p["job_id"])
        if f is None or p["job_id"] not in extra:
            continue
        sample.append({**p, "facts": f, **extra[p["job_id"]]})

    # Sorted, because every seeded thing downstream indexes into this list --
    # the CV folds, the random baseline's samples, the bootstrap resamples --
    # and Postgres does not promise row order without an ORDER BY. Two runs of
    # the same code moved the random baseline from 3.1 to 2.9 before this line
    # existed. Both were within noise of the truth, which is exactly why it
    # would have gone unnoticed until a real number moved for the same reason.
    sample.sort(key=lambda r: r["job_id"])
    return sample


def tech_vocabulary(sample, criteria, top_n):
    """Terms to turn tech_stack into features.

    Two sources, because they answer different questions. The boost terms from
    criteria.json are what the rules already react to, so arm A must be able to
    express them or it is not being given score_job's inputs. The frequent
    corpus terms let a learned model react to a technology nobody thought to
    weight.

    Built from X only -- no label is consulted -- so it is not leakage.
    """
    boost = tuple((criteria.get("tech") or {}).get("boost") or {})
    counts = {}
    for row in sample:
        for item in set(row["facts"].get("tech_stack") or []):
            tok = str(item).strip().lower()
            if tok:
                counts[tok] = counts.get(tok, 0) + 1
    frequent = [t for t, _ in sorted(counts.items(), key=lambda kv: -kv[1])][:top_n]
    return boost, tuple(t for t in frequent if t not in boost)


def struct_features(row, vocab, arm):
    """One posting as a feature dict. DictVectorizer one-hots the strings.

    Categoricals carry an explicit "__missing__" level rather than being
    dropped: "the extractor could not tell" is a real state of a posting, and
    on this corpus it correlates with thin descriptions.
    """
    boost, frequent = vocab
    f = row["facts"]
    d = {}

    for col, val in f.items():
        if col in ARM_A_DROP or col == "tech_stack" or col in NUMERIC:
            continue
        d[f"{col}={val if val is not None else '__missing__'}"] = 1.0

    stack = [str(s).lower() for s in (f.get("tech_stack") or [])]
    for term in boost:
        # Substring, matching score_job's own matching rule -- postings write
        # "node.js", "Node" and "nodejs" for one thing.
        d[f"tech~{term}"] = 1.0 if any(term in item for item in stack) else 0.0
    for term in frequent:
        d[f"tech={term}"] = 1.0 if term in stack else 0.0

    numeric = ("years_experience_min",) if arm == "A" else NUMERIC
    for col in numeric:
        val = f.get(col) if col in f else row.get(col)
        if val is None:
            d[f"{col}__missing"] = 1.0
        else:
            d[col] = float(val)
            d[f"{col}__missing"] = 0.0

    if arm != "A":
        for col in ("employment_type", "visa_sponsorship"):
            d[f"{col}={row.get(col) or '__missing__'}"] = 1.0

    return d


#: Scraper footers, stripped before the text arm ever sees a posting.
#:
#: WHY THIS EXISTS. The first arm-C run put "18808" and "18808 ljbffr" among
#: its strongest positive terms. That is the "#J-18808-Ljbffr" tag a
#: republisher appends: it is on 41 google_jobs postings, and those postings
#: are 34% fit>=80 against a 13.9% base rate. So the token is genuinely
#: predictive -- and it predicts WHICH BOARD SCRAPED THE PAGE, not anything
#: about the role. Left in, it inflates the prose ceiling this arm exists to
#: estimate, and it nominates itself as an extraction field.
#:
#: The general trap: with 917 rows and tens of thousands of text columns, any
#: artifact that tracks the source will be found, and a source that happens to
#: carry better postings makes it look like signal. Read arm C's terms before
#: its number -- boilerplate in that list means the number is contaminated.
_BOILERPLATE = re.compile(r"#?J-\d+-Ljbffr", re.I)


def clean_text(row):
    return _BOILERPLATE.sub(" ", f"{row['title']}\n{row['description_text']}")


def build_X(sample, vocab, arm):
    return [{"struct": struct_features(r, vocab, arm), "text": clean_text(r)}
            for r in sample]


def _select(key):
    return FunctionTransformer(lambda X, k=key: [x[k] for x in X])


def make_model(arm, kind, terms_only=False):
    """A fresh, unfitted estimator. Called once per fold -- never reused, so
    nothing learned on a training split can reach a test split."""
    struct = Pipeline([("sel", _select("struct")),
                       ("dv", DictVectorizer(sparse=(kind == "logreg")))])

    if kind == "gbt":
        # No sparse input, so the text arm is logreg-only. Fixed sensible
        # hyperparameters rather than an inner search: this arm exists to
        # catch interactions a linear model cannot represent, and if it lands
        # near the decision boundary that is the moment to tune it, not now.
        return Pipeline([("f", struct),
                         ("clf", HistGradientBoostingClassifier(
                             max_iter=250, learning_rate=0.05,
                             max_leaf_nodes=15, l2_regularization=1.0,
                             early_stopping=True, validation_fraction=0.15,
                             class_weight="balanced", random_state=SEED))])

    if arm == "C":
        text = Pipeline([("sel", _select("text")),
                         ("tfidf", TfidfVectorizer(
                             lowercase=True, stop_words="english",
                             ngram_range=(1, 2), min_df=5, max_features=30000,
                             sublinear_tf=True,
                             # Tokens must start with a letter. Bare numbers
                             # are req-ids, salary digits and footer tags --
                             # all of which identify a source or a posting
                             # rather than describing a role.
                             token_pattern=r"(?u)\b[a-z][a-z0-9+#.\-]+\b"))])
        feats = text if terms_only else FeatureUnion([("s", struct),
                                                      ("t", text)])
    else:
        feats = struct

    # Inner-fold regularisation search, not a hand-picked C. Scored on average
    # precision because that is the shape of the outer objective; scoring on
    # accuracy at a 15% base rate would select the model that predicts "no".
    return Pipeline([("f", feats), ("scale", MaxAbsScaler()),
                     ("clf", LogisticRegressionCV(
                         Cs=8, cv=3, scoring="average_precision",
                         class_weight="balanced", max_iter=4000,
                         solver="liblinear", refit=True, random_state=SEED))])


def prec_at(scores, y, k):
    """Positives inside the top k of `scores`. Stable sort, so ties resolve by
    original order every time rather than by whatever the sort felt like."""
    order = np.argsort(-scores, kind="stable")
    return float(y[order[:k]].sum())


def out_of_fold(arm, kind, X, y, repeats, splits=5, seed=SEED, terms_only=False):
    """One out-of-fold score vector per repeat.

    Per repeat rather than pooled across all 50 folds, because the spread
    ACROSS repeats is the number that says whether a difference is real. A
    single pooled vector gives one point estimate and no way to tell 8 from 11.
    """
    rskf = RepeatedStratifiedKFold(n_splits=splits, n_repeats=repeats,
                                   random_state=seed)
    out, cur = [], np.full(len(y), np.nan)
    for i, (tr, te) in enumerate(rskf.split(np.zeros(len(y)), y)):
        model = make_model(arm, kind, terms_only=terms_only)
        model.fit([X[j] for j in tr], y[tr])
        cur[te] = model.predict_proba([X[j] for j in te])[:, 1]
        if (i + 1) % splits == 0:
            assert not np.isnan(cur).any(), "a posting was never held out"
            out.append(cur)
            cur = np.full(len(y), np.nan)
    return out


def summarise(oof, y, ks):
    """mean and sd across repeats, for each metric."""
    stats = {}
    for k in ks:
        vals = [prec_at(s, y, k) for s in oof]
        stats[f"p@{k}"] = (float(np.mean(vals)), float(np.std(vals)))
    aps = [average_precision_score(y, s) for s in oof]
    stats["ap"] = (float(np.mean(aps)), float(np.std(aps)))
    return stats


def bootstrap_delta(learned, rules, y, metric, seed=SEED):
    """CI for (learned - rules) under `metric`, on SHARED resamples.

    Paired, because the two rankings are being compared on the same postings.
    Two independent confidence intervals that happen to overlap say much less
    than one interval on the difference, and the overlap heuristic is how a
    real gain gets talked out of existence.

    Caveat worth knowing: resampling with replacement lets one posting occupy
    several of the top k, so absolute values drift a little from the point
    estimate. The DIFFERENCE is what this is for.
    """
    rng = np.random.default_rng(seed)
    n = len(y)
    deltas = np.empty(BOOTSTRAP_DRAWS)
    for i in range(BOOTSTRAP_DRAWS):
        idx = rng.integers(0, n, n)
        deltas[i] = metric(learned[idx], y[idx]) - metric(rules[idx], y[idx])
    return (float(np.mean(deltas)),
            float(np.percentile(deltas, 2.5)),
            float(np.percentile(deltas, 97.5)))


def _m_p20(s, yy):
    return prec_at(s, yy, 20)


def _m_ap(s, yy):
    return average_precision_score(yy, s) if 0 < yy.sum() < len(yy) else 0.0


def baselines(sample, y, k):
    """Rules, recency and random on this exact sample.

    Recomputed here rather than read off calibrate-match's output so the
    comparison cannot drift, and sorted NEWEST first -- that sort ran backwards
    until 2026-07-26 and reported the 20 oldest postings as "the old
    behaviour". See HANDOFF section 4.6.
    """
    rules = np.array([r["match"] for r in sample], dtype=float)
    newest = np.array([(r.get("first_seen") or "") for r in sample])
    order = np.argsort(newest, kind="stable")[::-1]
    recency = np.zeros(len(sample))
    recency[order] = np.arange(len(sample), 0, -1)

    idx = list(range(len(sample)))
    total = 0.0
    for s in range(RANDOM_DRAWS):
        random.seed(s)
        total += sum(y[j] for j in random.sample(idx, k))
    return rules, recency, total / RANDOM_DRAWS


def top_terms(X, y, n=25):
    """The prose terms a text-only model leans on hardest.

    Fitted on everything, and that is fine BECAUSE IT IS NOT A SCORE -- no
    quality number is read off this. It is a list of hypotheses about what the
    LLM keys on, to replace HANDOFF section 5's five guesses with evidence.
    """
    model = make_model("C", "logreg", terms_only=True)
    model.fit(X, y)
    names = model.named_steps["f"].named_steps["tfidf"].get_feature_names_out()
    coef = model.named_steps["clf"].coef_[0]
    order = np.argsort(coef)
    return ([(names[i], float(coef[i])) for i in order[::-1][:n]],
            [(names[i], float(coef[i])) for i in order[:n]])


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile", default="tech")
    ap.add_argument("--arms", nargs="+", default=["A", "B", "C"],
                    choices=["A", "B", "C"])
    ap.add_argument("--repeats", type=int, default=10,
                    help="CV repeats; the spread across these is what says "
                         "whether a difference is real (default 10)")
    ap.add_argument("--terms", type=int, default=25,
                    help="prose terms to print from arm C (0 to skip)")
    ap.add_argument("--tech-vocab", type=int, default=40,
                    help="frequent tech_stack terms to featurise")
    args = ap.parse_args()

    conn = dbconn.connect_or_exit("learned-ranker-probe", schema=schema.SCHEMA)
    profile_obj = profiles.load_one(conn, args.profile)
    if not profile_obj:
        sys.exit(f"learned-ranker-probe FAILED: no profile {args.profile!r}")
    sample = load_sample(conn, profile_obj)
    conn.close()

    if len(sample) < 200:
        sys.exit(f"learned-ranker-probe: only {len(sample)} labelled postings "
                 f"-- not enough to cross-validate.")

    y = np.array([1 if r["fit"] >= GOOD else 0 for r in sample])
    n, pos = len(y), int(y.sum())
    k = 20

    print(f"learned-ranker-probe: profile={args.profile}  seed={SEED}  "
          f"repeats={args.repeats}x5-fold")
    print(f"  postings {n}   positives (fit>={GOOD}) {pos}  "
          f"({pos / n:.1%} base rate)")
    if (n, pos) != (REFERENCE_N, REFERENCE_POSITIVES):
        print(f"  NOTE: the corpus has moved since this decision rule was "
              f"written ({REFERENCE_N}/{REFERENCE_POSITIVES}). The comparison "
              f"below is still internally consistent -- every arm and every\n"
              f"        baseline is computed on this sample -- but the "
              f"absolute numbers in HANDOFF section 1 are not this run's.")

    rules, recency, rnd = baselines(sample, y, k)
    rules_p20 = prec_at(rules, y, k)
    print(f"\n  BASELINES on these {n} postings")
    print(f"    rules (match_score)        {rules_p20:5.1f}/{k}   "
          f"ap {average_precision_score(y, rules):.3f}")
    print(f"    recency (newest first)     {prec_at(recency, y, k):5.1f}/{k}")
    print(f"    random (mean of {RANDOM_DRAWS})       {rnd:5.1f}/{k}")

    vocab = tech_vocabulary(sample, profile_obj.criteria, args.tech_vocab)
    ks = (20, 50, 100)
    results = {}

    print(f"\n  OUT-OF-FOLD RESULTS   mean +/- sd over {args.repeats} repeats")
    print(f"    {'arm / model':<28} {'p@20':>12} {'p@50':>12} "
          f"{'p@100':>12} {'avg prec':>12}")
    for arm in args.arms:
        X = build_X(sample, vocab, arm)
        # gbt needs dense input; the text arm is tens of thousands of sparse
        # columns, so it is logreg only.
        for kind in (("logreg",) if arm == "C" else ("logreg", "gbt")):
            oof = out_of_fold(arm, kind, X, y, args.repeats)
            st = summarise(oof, y, ks)
            results[(arm, kind)] = (st, np.mean(oof, axis=0))
            cells = "".join(f"{st[f'p@{j}'][0]:8.1f}+-{st[f'p@{j}'][1]:<3.1f}"
                            for j in ks)
            print(f"    {arm + ' ' + kind:<28}{cells}"
                  f"{st['ap'][0]:8.3f}+-{st['ap'][1]:<3.3f}")

    # -- guard: the same machinery on nonsense labels must learn nothing ------
    print("\n  CONTROL (identical pipeline, labels permuted)")
    rng = np.random.default_rng(SEED)
    y_shuf = y.copy()
    rng.shuffle(y_shuf)
    ctrl_arm = "A" if "A" in args.arms else args.arms[0]
    ctrl = out_of_fold(ctrl_arm, "logreg", build_X(sample, vocab, ctrl_arm),
                       y_shuf, max(2, args.repeats // 3))
    ctrl_p20 = float(np.mean([prec_at(s, y_shuf, k) for s in ctrl]))
    leak = ctrl_p20 > rnd + 3 * 1.5
    print(f"    shuffled-label p@20        {ctrl_p20:5.1f}/{k}   "
          f"(must be ~{rnd:.1f}, the random baseline)  "
          f"{'LEAKAGE' if leak else 'ok'}")

    if leak:
        print("\n  VOID: the pipeline scores above chance on permuted labels, "
              "so something\n  in it sees the label. No verdict -- fix the "
              "leak and re-run.")
        sys.exit(2)

    # -- the comparison that decides ----------------------------------------
    #
    # AVERAGE PRECISION DECIDES, precision@20 IS REPORTED. p@20 is the
    # user-facing objective, but it is a count of at most 20 things and its
    # bootstrap CI is correspondingly coarse -- wide enough to call a 12.5-vs-8
    # gap "not distinguishable" while average precision separates the same two
    # rankings by 0.17 with a hundredth of the spread. Deciding on the coarser
    # of two statistics that measure the same ranking would be trap 4.5 again:
    # letting a number that cannot resolve the question answer it.
    print(f"\n  vs THE RULES, paired bootstrap on shared resamples "
          f"({BOOTSTRAP_DRAWS} draws)")
    deltas = {}
    for (arm, kind), (st, scores) in results.items():
        d_ap = bootstrap_delta(scores, rules, y, _m_ap)
        d_p = bootstrap_delta(scores, rules, y, _m_p20)
        deltas[(arm, kind)] = d_ap
        call = ("better" if d_ap[1] > 0 else
                "worse" if d_ap[2] < 0 else "not distinguishable")
        print(f"    {arm + ' ' + kind:<20} avg prec {d_ap[0]:+.3f} "
              f"[{d_ap[1]:+.3f}, {d_ap[2]:+.3f}]  {call:<20}"
              f"p@20 {d_p[0]:+4.1f} [{d_p[1]:+.0f}, {d_p[2]:+.0f}]")

    best_arm_a = max(((kd, v) for kd, v in results.items() if kd[0] == "A"),
                     key=lambda kv: kv[1][0]["ap"][0], default=None)

    if args.terms and "C" in args.arms:
        X_c = build_X(sample, vocab, "C")
        pos_t, neg_t = top_terms(X_c, y, args.terms)
        print(f"\n  PROSE TERMS the text model leans on (evidence for which "
              f"extraction\n  fields would pay -- HANDOFF section 5 is "
              f"currently five untested guesses):")
        print(f"    toward fit>={GOOD}:  "
              + ", ".join(t for t, _ in pos_t))
        print(f"    away from fit>={GOOD}: "
              + ", ".join(t for t, _ in neg_t))

    # -- verdict -------------------------------------------------------------
    print("\n  READING (HANDOFF section 3's decision rule):")
    if best_arm_a is None:
        print("    Arm A was not run, and it is the arm that answers the "
              "question -- it is the\n    only one that holds the inputs "
              "fixed. Re-run including --arms A.")
        return

    a_kind = best_arm_a[0][1]
    a_ap = best_arm_a[1][0]["ap"][0]
    a_p20 = best_arm_a[1][0]["p@20"][0]
    a_lo = deltas[best_arm_a[0]][1]

    best_c = max(((kd, v) for kd, v in results.items() if kd[0] == "C"),
                 key=lambda kv: kv[1][0]["ap"][0], default=None)
    c_ap = best_c[1][0]["ap"][0] if best_c else None

    if a_lo > 0:
        print(f"    Arm A ({a_kind}) beats the rules on IDENTICAL inputs: "
              f"avg prec {a_ap:.3f} vs\n    {average_precision_score(y, rules):.3f}, "
              f"p@20 {a_p20:.1f} vs {rules_p20:.0f}, and the paired CI "
              f"excludes zero.")
        print("    -> THE WEIGHTS were the bottleneck, not the features. The "
              "17 fields already\n       carry signal the hand-tuned points do "
              "not extract. Skip HANDOFF section 5\n       and build the "
              "learned ranker (SCORING.md roadmap step 3).")
        if c_ap is not None and c_ap > a_ap + 0.05:
            print(f"       Arm C is higher still ({c_ap:.3f}) -- there is "
                  f"prose signal on top of\n       that, so section 5 is worth "
                  f"revisiting AFTER the learned ranker, not instead.")
    elif c_ap is not None and c_ap > a_ap + 0.05:
        print(f"    Arm A cannot beat the rules (avg prec {a_ap:.3f}) but the "
              f"prose can ({c_ap:.3f}).")
        print("    -> THE FEATURES are the bottleneck. New extraction fields "
              "are the right\n       spend, and the prose terms above say "
              "which ones -- use those instead of\n       HANDOFF section 5's "
              "five untested hypotheses.")
    else:
        print(f"    Neither learned weights (avg prec {a_ap:.3f})"
              + (f" nor the full prose ({c_ap:.3f})" if c_ap is not None
                 else "")
              + f" beats the rules\n    "
              f"({average_precision_score(y, rules):.3f}).")
        print("    -> The ceiling is neither the weights nor any available "
              "feature. Stop here;\n       revisit when job_events has real "
              "engagement data to learn from.")
        if c_ap is None:
            print("       (Arm C was skipped -- run it before trusting this "
                  "branch.)")


if __name__ == "__main__":
    main()
