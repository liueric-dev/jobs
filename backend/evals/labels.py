"""L0: what a human said, kept apart from what a model said.

WHAT THIS IS FOR
    Every existing tool substitutes an LLM for a human. tools/claude-bench.py
    treats `sonnet-batch-1` as ground truth (claude-bench.py:417) and
    tools/calibrate-match.py reads existing `job_scores` (calibrate-match.py:47).
    Both measure AGREEMENT, not correctness, and both are blind to any error
    two models share. This module is the other side of that: a place for
    judgements a person made, with no model anywhere in the causal chain.

    It ships EMPTY. Filling it is task 29's job and it needs people, not code.
    Nothing here generates, guesses, seeds or defaults a label, and there is
    no code path from a model's output into `eval_labels`.

TWO AXES, KEYED INDEPENDENTLY, BECAUSE THEY HAVE DIFFERENT LIFETIMES
    axis A  "is the extraction correct?"   objective   outlives the cohort
    axis B  "would you apply to this?"     subjective  dies with the cohort

    Axis A validates `job_facts`, which is extracted ONCE and shared by every
    profile that will ever exist (extract.py:16). It has never been measured
    against a human: tools/compare-extract.py measures the model against
    ITSELF, which catches instability and is structurally blind to systematic
    error -- a model can be perfectly self-consistent and consistently wrong.

    So the two axes get separate partial unique indexes rather than one
    composite key with a nullable column:

        axis A   UNIQUE (job_id, field, labeller_id, round_no)
        axis B   UNIQUE (job_id, field, profile, labeller_id, round_no)

    Axis A's key deliberately carries NO profile and NO label_set. "Does this
    posting say `mid`" is a fact about the posting; it is not owned by a
    persona and not owned by whichever eval set happened to sample the row.
    `DELETE FROM eval_labels WHERE axis = 'B'` when the Pursuit cohort ends
    leaves every axis-A row intact and fully interpretable, and a CHECK
    constraint makes the two shapes impossible to mix up.

THREE QUANTITIES, AND THE THIRD CANNOT BE PRINTED ALONE
    model-vs-human is uninterpretable without a floor and a ceiling beside it.
    A model that agrees with itself 85% of the time cannot be scored at 80%
    against labels and called 80% accurate, and humans who agree with each
    other 88% of the time set a bar no model can pass.

        floor    model self-consistency   metrics.selfcheck (task 06, exists)
        ceiling  inter-annotator          inter_annotator() below
        measured model vs human           model_vs_human() below

    Following the precedent task 16 set -- a tool that refuses to print one
    denominator alone -- the API makes the bad report UNREPRESENTABLE rather
    than discouraged. `interpretable()` is the only thing report.py will
    render, and it raises `Uninterpretable` for any field that has a measured
    cell without a floor cell and a ceiling cell. There is no flag to pass.

AND ALL THREE ARE BROKEN OUT BY SOURCE PLATFORM
    29:106 requires it and 29:87-89 gives the reason: task 06's
    reconciliation predicts extraction degrades on messy sources and Phase 3
    just added several, so a blended number would hide exactly that effect.

    The breakout is a DIAGNOSTIC BESIDE the blended figure, never a
    replacement for it. At the label counts this session can realistically
    collect -- 100 postings across six platforms -- a per-platform cell is
    single digits, and a bare percentage over n=3 reads exactly like one over
    n=300. So every cell carries its n and its interval, and is_thin() marks
    the ones whose interval is too wide to separate a good platform from a
    bad one. Same axis as the self-consistency table: metrics.CLEAN_PLATFORMS,
    reused rather than redefined.

ABSTAIN IS A VALUE AND IS NEVER FOLDED AWAY
    A labeller who cannot tell from the posting records NULL. Recording a
    guess instead is precisely the poison this module exists to avoid.
    Abstentions are excluded from every agreement rate and counted beside it,
    the same treatment metrics.selfcheck gives records that are not usable in
    every repeat (metrics.py:42).

THE SAMPLE MUST CONTAIN ROWS THE PIPELINE REJECTED
    Everything measured up to now was something the pipeline already chose to
    surface, so only PRECISION is estimable and recall is not. sample() below
    draws from three strata, two of which have no `job_scores` row at all and
    one of which has no `job_facts` row either. See STRATA.

READ-ONLY AGAINST THE CORPUS
    sample() only ever SELECTs from `jobs`, `job_facts` and `job_matches`.
    The only tables this module writes are the three it creates itself.
"""

import dataclasses
import hashlib
import json
import os

from . import metrics

# --------------------------------------------------------------------------
# The questions
# --------------------------------------------------------------------------

#: Axis A fields, in labelling order. `ai_involvement` and `seniority_level`
#: come first and that ordering is a finding, not a preference: task 06
#: measured `ai_involvement` at 77.8% pairwise self-agreement on
#: hn_whoishiring against 92.2% on greenhouse/ashby, and it is the entire
#: mechanism by which the Pursuit cohort's opportunity space is identified.
#: A field that cannot agree with itself is where a human label buys the most.
#:
#: The tail is the rest of tasks/extract.py PRIORITY_FIELDS -- the fields
#: match.py actually scores on. An error in `seniority_level` changes what a
#: person is shown; an error in `comp_currency` does not. metrics scores only
#: what is labelled, so this list can grow later without rework.
AXIS_A_FIELDS = ("ai_involvement", "seniority_level", "role_archetype",
                 "remote_policy")

#: Fields in tasks/extract.py PRIORITY_FIELDS that are NOT on the form, with
#: the measurement that took them off it. `03-metrics-and-golden-set.md:116`
#: is the instruction: let the selfcheck narrow the set, and record the rest as
#: known-unstable rather than dropping them silently.
#:
#: `tech_stack` self-agrees 70.4% exact across three identical runs (task 06,
#: n=115). A field that cannot agree with ITSELF will not be rescued by a human
#: label: the number a label produces there describes variance, and the fix it
#: points at is a prompt or a model, not a golden set. Spending scarce
#: volunteer hours on it buys a figure nobody can act on.
#:
#: `remote_policy` is 81.7% and is KEPT, which is the judgement call in this
#: list. The two are unstable in different ways: remote_policy is a five-value
#: enum where a disagreement is a disagreement, and a human can settle it from
#: the posting. tech_stack is a set scored by Jaccard, where most of the
#: instability is granularity ("Postgres" vs "PostgreSQL", whether the
#: nice-to-haves count) rather than a claim about the job -- so a label would
#: be settling a question about the field's DEFINITION, and that is a spec
#: change, not evidence.
KNOWN_UNSTABLE = {
    "tech_stack": "70.4% exact self-agreement (task 06, n=115) -- set-valued, "
                  "and the disagreement is mostly granularity",
}

#: Axis B is one question with two answers. Not a 1-5 scale: "would you apply"
#: is the decision the product actually asks a Builder to make, and a scale
#: invites a middle that means nothing. "I cannot tell" is an abstention
#: (value NULL), which is a different statement from "no".
AXIS_B_FIELD = "would_apply"
AXIS_B_VALUES = ("yes", "no")

AXIS_A, AXIS_B = "A", "B"


@dataclasses.dataclass(frozen=True)
class Question:
    """One thing a labeller is asked, and the closed set of answers."""

    axis: str
    field: str
    prompt: str
    choices: tuple


def questions():
    """The label form, with vocabularies read from extract.py, never copied.

    THE VOCABULARY MUST BE THE PIPELINE'S OWN. A human label recorded as
    "Mid-Level" cannot be compared against a `job_facts` row holding "mid" --
    it would score formatting, which is the exact mistake
    evals/tasks/extract.py's docstring exists to prevent. Reading SENIORITY,
    ARCHETYPE and friends from extract.py means the form cannot drift from
    what normalize() produces; a copy here would, silently, and the resulting
    disagreement would be read as a model error.

    Imported lazily: this module is imported by the browser-facing webapp,
    and `import extract` drags in llm.py and the pipeline's argument parsing
    for no benefit until somebody actually renders the form.
    """
    import extract as extract_stage

    vocab = {
        "ai_involvement": extract_stage.AI_INVOLVEMENT,
        "seniority_level": extract_stage.SENIORITY,
        "role_archetype": extract_stage.ARCHETYPE,
        "remote_policy": extract_stage.REMOTE_POLICY,
    }
    prompts = {
        "ai_involvement": "How much AI is in this job, as the posting "
                          "describes it?",
        "seniority_level": "What seniority does the posting actually ask "
                           "for?",
        "role_archetype": "What kind of role is this?",
        "remote_policy": "Where does the posting say the work happens?",
    }
    out = [Question(axis=AXIS_A, field=f, prompt=prompts[f],
                    choices=tuple(vocab[f]))
           for f in AXIS_A_FIELDS]
    out.append(Question(
        axis=AXIS_B, field=AXIS_B_FIELD,
        prompt="Would you apply to this job?",
        choices=AXIS_B_VALUES))
    return out


def validate(axis, field, value):
    """Coerce one submitted answer, or raise ValueError naming the problem.

    Returns the value to store; '' and 'unsure' both become None, which is an
    abstention. The caller must not turn an abstention into a guess.
    """
    if axis not in (AXIS_A, AXIS_B):
        raise ValueError(f"unknown axis {axis!r}")
    for q in questions():
        if q.axis == axis and q.field == field:
            break
    else:
        raise ValueError(f"{field!r} is not a labelled field on axis {axis}")
    if value in (None, "", "unsure"):
        return None
    if value not in q.choices:
        raise ValueError(
            f"{value!r} is not one of {list(q.choices)} for {field}")
    return value


# --------------------------------------------------------------------------
# Schema
# --------------------------------------------------------------------------

#: This module owns exactly these three tables and restates nothing else.
#: Same ownership rule webapp/schema_web.py:5 states and for the same reason
#: recorded there: nine functions and three tables' DDL were once duplicated
#: across api/query_claims.py and had drifted six ways by the time anyone
#: measured, two of the drifts changing row identity. One definition per
#: table, in the module that owns it -- and this is the module that owns
#: these, NOT backend/schema.py, which owns the pipeline's corpus. A label is
#: evaluation ground truth: never read by the pipeline, never trained on
#: (CLAUDE.md's L0 rule), and deleted per-axis when a cohort ends.
TABLES = ("eval_label_sets", "eval_label_items", "eval_labels")

#: Privileges the browser-facing labelling surface needs. Exported so
#: webapp/schema_web.py has one place to read them from rather than a second
#: copy that can drift out of agreement with the DDL below.
#:
#: No DELETE and no UPDATE on `eval_labels`: a label is evidence and a
#: correction is a second round, exactly as job_events treats a dismiss as a
#: row rather than a deletion. The set tables are read-only to the service --
#: only the CLI, running as an operator, draws a sample.
WEB_PRIVILEGES = {
    "eval_label_sets": ("SELECT",),
    "eval_label_items": ("SELECT",),
    "eval_labels": ("SELECT", "INSERT"),
}

WEB_SEQUENCES = {
    # eval_labels.id is BIGSERIAL, so INSERT on the table is not sufficient on
    # its own -- nextval() is a separate privilege. api/ and webapp/ have each
    # already paid for forgetting this once: it surfaces as a 500 on a real
    # user's first submit rather than as a refusal to start.
    "eval_labels_id_seq": ("USAGE", "SELECT"),
}


def ensure_schema(conn):
    """Create the label tables. Idempotent, DDL, admin credential only.

    Deliberately a separate explicitly-invoked step rather than something a
    service does at startup, matching webapp/schema_web.py:69 and
    api/app.py:82: the long-running browser-facing process holds no CREATE
    rights, so a missing table is a deployment error to report rather than
    damage to silently repair.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS eval_label_sets (
            label_set     TEXT PRIMARY KEY,
            created_at    TEXT NOT NULL,
            seed          INTEGER NOT NULL,
            n             INTEGER NOT NULL,
            profile       TEXT NOT NULL,
            job_id_sha256 TEXT NOT NULL,
            note          TEXT
        )
    """)
    # job_id_sha256 pins the set by its sorted job ids -- CLAUDE.md's rule,
    # and the same device tests/test_evals.py:454 uses on the frozen corpora.
    # A set regenerated in place would silently change what every published
    # figure was measured on, and the figures would still be in the docs,
    # unchanged and now wrong.

    conn.execute("""
        CREATE TABLE IF NOT EXISTS eval_label_items (
            label_set  TEXT NOT NULL REFERENCES eval_label_sets(label_set)
                            ON DELETE CASCADE,
            job_id     TEXT NOT NULL,
            stratum    TEXT NOT NULL,
            platform   TEXT,
            overlap    BOOLEAN NOT NULL DEFAULT FALSE,
            position   INTEGER NOT NULL,
            PRIMARY KEY (label_set, job_id)
        )
    """)
    # `overlap` is what makes the ceiling measurable. An overlap row is shown
    # to EVERY labeller; the rest are divided between them. Without a
    # deliberate overlap, ten people labelling disjoint sets produce no
    # inter-annotator number at all, and the ceiling is the quantity that
    # gives every other figure here a scale.
    #
    # `stratum` is carried on the item rather than recomputed at report time
    # because a row's stratum is a property of the pipeline AT SAMPLING TIME
    # -- match.py re-ranks nightly, so a row that was below the floor when it
    # was sampled may be above it when the report runs, and reclassifying it
    # then would silently move it between populations.

    conn.execute("""
        CREATE TABLE IF NOT EXISTS eval_labels (
            id          BIGSERIAL PRIMARY KEY,
            axis        TEXT NOT NULL,
            label_set   TEXT,
            job_id      TEXT NOT NULL,
            field       TEXT NOT NULL,
            value       TEXT,
            profile     TEXT,
            labeller_id TEXT NOT NULL,
            round_no    INTEGER NOT NULL DEFAULT 1,
            labelled_at TEXT NOT NULL,
            note        TEXT,
            CONSTRAINT eval_labels_axis
                CHECK (axis IN ('A', 'B')),
            CONSTRAINT eval_labels_axis_shape
                CHECK ((axis = 'A' AND profile IS NULL)
                    OR (axis = 'B' AND profile IS NOT NULL))
        )
    """)
    # THE TWO AXES ARE KEYED INDEPENDENTLY, and this is the whole design.
    #
    # Not one composite key over a nullable `profile`: Postgres treats NULLs
    # as distinct in a unique index, so `UNIQUE (job_id, field, profile,
    # labeller_id, round_no)` would enforce nothing at all on axis A and the
    # same person could answer the same question ten times with no complaint.
    #
    # Axis A's key carries no profile AND no label_set. "Does this posting say
    # mid" is a fact about the posting, not about a persona and not about
    # whichever eval set sampled it; a second set drawing the same row must
    # not create a second, competing answer from the same person. A revised
    # judgement is round_no 2, which is also what the intra-annotator
    # measurement reads.
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS eval_labels_axis_a_key
            ON eval_labels (job_id, field, labeller_id, round_no)
            WHERE axis = 'A'
    """)
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS eval_labels_axis_b_key
            ON eval_labels (job_id, field, profile, labeller_id, round_no)
            WHERE axis = 'B'
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_eval_labels_set "
                 "ON eval_labels (label_set, job_id)")
    conn.commit()


def verify_schema(conn, privileges=None, sequences=None):
    """Names everything missing, not just the first thing.

    Ported from webapp/schema_web.py:143 including its reasoning: a table can
    exist and still be unusable if a GRANT was missed, and that failure mode
    surfaces as a 500 on a real user's first click rather than as a refusal to
    start. Returns a list of problems; the caller decides whether to raise.
    """
    privileges = WEB_PRIVILEGES if privileges is None else privileges
    sequences = WEB_SEQUENCES if sequences is None else sequences
    problems = []
    for table, needed in privileges.items():
        qualified = f"public.{table}"
        if conn.execute("SELECT to_regclass(%s)",
                        (qualified,)).fetchone()[0] is None:
            problems.append(f"{qualified}: missing")
            continue
        lacking = [p for p in needed if not conn.execute(
            "SELECT has_table_privilege(current_user, %s, %s)",
            (qualified, p)).fetchone()[0]]
        if lacking:
            problems.append(f"{qualified}: no {', '.join(lacking)}")
    for sequence, needed in sequences.items():
        qualified = f"public.{sequence}"
        if conn.execute("SELECT to_regclass(%s)",
                        (qualified,)).fetchone()[0] is None:
            problems.append(f"{qualified}: missing")
            continue
        lacking = [p for p in needed if not conn.execute(
            "SELECT has_sequence_privilege(current_user, %s, %s)",
            (qualified, p)).fetchone()[0]]
        if lacking:
            problems.append(f"{qualified}: no {', '.join(lacking)}")
    return problems


# --------------------------------------------------------------------------
# The sample
# --------------------------------------------------------------------------

#: The three populations, and what each one makes estimable.
#:
#:   surfaced      a job_matches row exists for the profile, so match.py:291
#:                 scored it at or above schema.MATCH_FLOOR. This is the only
#:                 population anything has ever been measured on, and it is
#:                 why only PRECISION is currently estimable.
#:   below_floor   job_facts exists and job_matches does not. match.py stores
#:                 a row only when `score >= schema.MATCH_FLOOR` (match.py:291)
#:                 and deletes one that stops clearing it (match.py:295), so
#:                 absence means the arithmetic rejected it. score_job() is
#:                 pure (match.py:73), so confirm_scores() recomputes the exact
#:                 number for these rows without an LLM call and without a
#:                 write -- turning "probably below the floor" into the figure.
#:   gate_rejected relevance tier > max_tier_to_score for THIS PROFILE, so the
#:                 profile's users can never see it. A human label on these is
#:                 the only way RECALL is ever estimable.
#:
#:                 THIS USED TO SAY "and there is no job_facts row either".
#:                 That is false and was false when written: 24 of the 50
#:                 gate-rejected rows in `pursuit-v1` carry facts, because
#:                 extraction is SHARED and its queue is the union over ACTIVE
#:                 profiles (extract._eligible_sql), so anything `tech` and
#:                 `frontend` pulled in before task 12 flipped the active set
#:                 still has facts under a gate that now rejects it. The
#:                 stratum is unaffected -- rejection is what defines it -- and
#:                 those 24 are a small bonus, since Axis A on them can be read
#:                 against an extraction the cohort gate never asked for.
#:                 What DOES matter is checked and holds: 0 of the 50 carry a
#:                 `pursuit` job_matches row, and corpus-wide 0 of the 144
#:                 pursuit matches are tier > max_tier. The gate and the
#:                 matcher agree; only the ordering of the two tests in
#:                 classify() could ever make them appear not to.
STRATA = ("surfaced", "below_floor", "gate_rejected")

#: Default shape of a label set. Deliberately not equal thirds: `surfaced` is
#: the population the product actually serves and the one whose precision
#: figure is quoted, while the two rejected strata exist to bound recall, for
#: which a smaller sample still moves the answer from "unknown" to "bounded".
#: Task 29 owns the real numbers; these are what `--strata` defaults to so the
#: sampler is exercisable without one.
DEFAULT_STRATA_QUOTA = {"surfaced": 0.5, "below_floor": 0.25,
                        "gate_rejected": 0.25}

_ITEM_COLUMNS = ("job_id", "platform", "stratum", "title", "company_name",
                 "match_score", "computed_score", "tier", "extracted")


def pool_query(profile, cfg):
    """The one SELECT. Read-only, and per-platform for the reason corpus.py
    gives at corpus.py:115.

    `cfg` IS REQUIRED, AND IT MUST BE THE PROFILE'S OWN GATE. It used to
    default to relevance.load() -- the shared config/relevance.json -- which
    is a different gate from the one a cohort profile is filtered by, and the
    argument names a profile, so the default silently answered for the wrong
    population. Measured on the live corpus 2026-07-29, `pursuit`: the shared
    gate classifies 59 rows as `surfaced` and the profile's own gate 144,
    because classify() tests tier BEFORE match_score and 85 postings the
    pipeline is actively surfacing come back tier 3 under the author's gate.
    Resolve with relevance.for_profile(), the same helper extract.py and
    score.py use.

    LEFT JOIN, NOT INNER, ON BOTH SIDES. That is the entire point of this
    query: an inner join to job_facts or job_matches reproduces exactly the
    selection bias this task exists to break -- it would return only rows the
    pipeline already chose to surface, which is the population every existing
    measurement is trapped in.

    The tier expression comes from relevance.tier_sql(), not from a second
    implementation. CLAUDE.md: do not reimplement relevance matching in
    Python -- one implementation, two callers. A copy here would drift from
    config/relevance.json and misclassify the gate-rejected stratum, which is
    the one stratum whose entire value is being identified correctly.
    """
    import relevance
    from schema import TABLE, FACTS_TABLE, MATCHES_TABLE

    tier_expr, tier_params = relevance.tier_sql(cfg, "j")
    params = dict(tier_params)
    params["profile"] = profile

    sql = f"""
        WITH ranked AS (
            SELECT j.id AS job_id, j.platform, j.title, j.company_name,
                   j.description_text, j.location_is_nyc, j.location_is_remote,
                   {tier_expr} AS tier,
                   f.facts_version, f.seniority_level, f.years_experience_min,
                   f.years_experience_max, f.role_archetype, f.tech_stack,
                   f.ai_involvement, f.ml_research_required,
                   f.advanced_degree_required, f.customer_facing,
                   f.remote_policy, f.employment_type, f.comp_min, f.comp_max,
                   f.comp_currency, f.gap_friendly_language, f.visa_sponsorship,
                   m.match_score,
                   ROW_NUMBER() OVER (PARTITION BY j.platform
                                      ORDER BY j.first_seen DESC) AS rn
            FROM {TABLE} j
            LEFT JOIN {FACTS_TABLE} f ON f.job_id = j.id
            LEFT JOIN {MATCHES_TABLE} m
                   ON m.job_id = j.id AND m.profile = %(profile)s
        )
        SELECT * FROM ranked WHERE rn <= %(per_platform)s
    """
    return sql, params


def pool(conn, profile, *, per_platform=100_000, cfg=None):
    """Read production and return classified candidate rows. Never writes.

    Generous per_platform by default for the same reason corpus.py:230 gives:
    the interesting strata are a small fraction of any slice, and a pool too
    thin to contain them yields a set that quietly measures only the easy
    path. Here the risk is sharper -- `gate_rejected` rows are, by
    construction, the ones the pipeline is least interested in keeping fresh.

    THE PER-PLATFORM DEFAULT IS THE WHOLE TABLE, and that is a correction
    rather than a preference. At 400 the newest-first window held 29 of
    `pursuit`'s 144 surfaced postings (greenhouse 6/65, ashby 13/52,
    google_jobs 9/26) -- measured 2026-07-29 -- so the stratum the precision
    figure is quoted from was being drawn from a fifth of itself, and
    sample() under-fills in silence. PARTITION BY platform answers CLAUDE.md's
    "~85% greenhouse/ashby" composition complaint; it does nothing about the
    recency truncation underneath it. `jobs` is ~14,000 rows and one SELECT
    over all of it is free.

    `cfg` defaults to THE PROFILE'S OWN GATE, not the shared file -- see
    pool_query(). Passing it in explicitly is still preferred when the caller
    already holds the profile row, which saves the second load.
    """
    import relevance
    import profiles

    if cfg is None:
        cfg = relevance.for_profile(profiles.load_one(conn, profile))
    sql, params = pool_query(profile, cfg)
    params["per_platform"] = per_platform
    cur = conn.execute(sql, params)
    names = [d[0] for d in cur.description]
    limit = relevance.max_tier(cfg)

    rows = []
    for raw in cur.fetchall():
        row = dict(zip(names, raw))
        row["stratum"] = classify(row, limit)
        row["computed_score"] = None
        if row["stratum"]:
            rows.append(row)
    return rows


def classify(row, max_tier):
    """Which stratum one pool row belongs to. Exactly one, never several."""
    if (row.get("tier") or 0) > max_tier:
        return "gate_rejected"
    if row.get("match_score") is not None:
        return "surfaced"
    if row.get("facts_version") is not None:
        return "below_floor"
    # Inside the gate, never extracted: an empty description (extract.py:180
    # excludes those) or a backlog the nightly run has not reached. Not a
    # stratum -- it is a row about which the pipeline has not yet had an
    # opinion, and labelling it measures the schedule rather than the model.
    return None


def confirm_scores(rows, criteria):
    """Fill `computed_score` for below_floor rows, using match.score_job().

    WHY THIS IS WORTH DOING. "No job_matches row" has two causes -- the score
    was under the floor, or match.py has not run for this profile since the
    facts landed -- and they are indistinguishable in SQL. Reporting a recall
    figure over a stratum contaminated with the second would be a measurement
    of the scheduler.

    score_job() is pure (match.py:73-84): no database, no clock, no config
    lookup. So the exact number can be recomputed here, for free, with nothing
    written anywhere, and the ambiguity stops being one. A row whose recomputed
    score is at or above the floor is dropped from the stratum and counted.
    """
    from match import score_job
    import schema

    kept, mismatched = [], []
    for row in rows:
        if row["stratum"] != "below_floor":
            kept.append(row)
            continue
        score, _reasons = score_job(row, criteria)
        row["computed_score"] = score
        if score >= schema.MATCH_FLOOR:
            mismatched.append(row)
        else:
            kept.append(row)
    return kept, mismatched


def sample(rows, n, *, seed=0, quota=None, overlap=0):
    """Pick `n` rows across the strata, then mark `overlap` of them shared.

    There used to be a `max_tier` parameter here. It was never referenced in
    the body -- classification happens in pool()/classify(), which is the only
    place that has a tier -- so it read as a second, disagreeing knob for the
    gate boundary. Removed rather than wired up: one implementation.

    UNDER-FILL IS NOT REPORTED HERE. A stratum with fewer rows than its quota
    yields what it has and the loop moves on, because sample() cannot know
    whether that is a starved pool or a deliberately small draw. The caller
    compares taken against want and refuses -- __main__.cmd_label_sample.

    Deterministic given a seed, and stratified within each stratum by platform
    for the reason corpus.py:24 gives: an ATS posting is clean HTML with a real
    title and an HN comment is free text whose title the parser guessed at, so
    a set that is 80% ATS measures ATS.

    `overlap` rows are drawn from the FRONT of the ordered set, which is what
    puts them in every labeller's queue first. The ceiling is the measurement
    most likely to be lost to attrition -- a volunteer who labels ten jobs and
    stops has still contributed to it if the shared rows came first, and has
    contributed nothing to it if they came last.
    """
    import random

    quota = DEFAULT_STRATA_QUOTA if quota is None else quota
    rng = random.Random(seed)

    by_stratum = {s: [] for s in STRATA}
    for row in rows:
        stratum = row.get("stratum")
        if stratum in by_stratum:
            by_stratum[stratum].append(row)

    picked = []
    for stratum in STRATA:
        want = int(round(n * quota.get(stratum, 0.0)))
        pool = list(by_stratum[stratum])
        rng.shuffle(pool)
        # Round-robin across platforms inside the stratum, the same argument
        # corpus.stratify() makes at corpus.py:209: a fixed per-platform quota
        # silently under-fills from a small source and wastes the slots.
        by_platform = {}
        for row in pool:
            by_platform.setdefault(row.get("platform") or "unknown",
                                   []).append(row)
        taken = 0
        while taken < want and any(by_platform.values()):
            for platform in sorted(by_platform):
                if taken >= want:
                    break
                if by_platform[platform]:
                    picked.append(by_platform[platform].pop())
                    taken += 1

    # Pinned by sorted job_id, per CLAUDE.md, so the set has one canonical
    # order and two sessions cannot disagree about what it contains.
    picked.sort(key=lambda r: r["job_id"])
    for i, row in enumerate(picked):
        row["position"] = i
        row["overlap"] = i < overlap
    return picked


def digest(rows):
    """sha256 over the sorted job ids. The set's identity.

    The same pin tests/test_evals.py:454 puts on the frozen corpora, for the
    same reason: a set regenerated in place would change what every published
    figure was measured on while the figures sat unchanged in the docs.
    """
    ids = sorted(str(r["job_id"]) for r in rows)
    return hashlib.sha256("\n".join(ids).encode("utf-8")).hexdigest()


def save_set(path, rows):
    """Write the set as JSONL, keys sorted, one row per line.

    The set is a file and the LABELS are a database table, deliberately. Ten
    volunteers submitting concurrently through a web form need a table with a
    unique index; the question of WHICH postings are in the eval set needs to
    be reviewable as a diff and pinnable by digest, which is a file.
    """
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        for row in rows:
            slim = {k: row.get(k) for k in
                    ("job_id", "platform", "stratum", "position", "overlap",
                     "match_score", "computed_score", "tier")}
            fh.write(json.dumps(slim, sort_keys=True, ensure_ascii=False)
                     + "\n")
    os.replace(tmp, path)
    return len(rows)


def load_set(path):
    from . import corpus
    return corpus.load(path)


def register_set(conn, label_set, rows, *, seed, profile, note=None):
    """Record the set and its items. Writes nothing to eval_labels."""
    from lib.timeparse import utc_now_str

    conn.execute(
        """
        INSERT INTO eval_label_sets (label_set, created_at, seed, n, profile,
                                     job_id_sha256, note)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (label_set) DO NOTHING
        """,
        (label_set, utc_now_str(), seed, len(rows), profile, digest(rows),
         note))
    for row in rows:
        conn.execute(
            """
            INSERT INTO eval_label_items (label_set, job_id, stratum, platform,
                                          overlap, position)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (label_set, job_id) DO NOTHING
            """,
            (label_set, row["job_id"], row["stratum"], row.get("platform"),
             bool(row.get("overlap")), int(row.get("position", 0))))
    conn.commit()
    return len(rows)


# --------------------------------------------------------------------------
# Reading and writing labels
# --------------------------------------------------------------------------

_LABEL_COLUMNS = ("axis", "label_set", "job_id", "field", "value", "profile",
                  "labeller_id", "round_no", "labelled_at", "note")

#: What fetch() returns: the label, plus the platform of the posting it is
#: about. `platform` is NOT a column of `eval_labels` and must not become one
#: -- it is a property of the posting, already recorded once on
#: eval_label_items (ensure_schema above), and a second copy on every label
#: row is a copy that can disagree with the first.
#:
#: It rides along on the read because the per-platform breakout task 29's
#: Definition of done asks for (29:106) has to happen somewhere, and every
#: consumer downstream of here -- the export JSONL, corpus.load(), the three
#: agreement functions -- takes label rows and nothing else. Carrying it on
#: the row means the breakout needs no second query, no second argument
#: threaded through __main__, and no chance of the platform map being built
#: from a different set than the labels.
_FETCH_COLUMNS = _LABEL_COLUMNS + ("platform",)


def record(conn, *, axis, job_id, field, value, labeller_id, label_set=None,
           profile=None, round_no=1, note=None, now=None):
    """Store one human judgement. Returns True if a row was written.

    The value is put through validate() here rather than trusted from the
    caller, so there is exactly one place an off-vocabulary label can be
    refused, and a route cannot forget.

    ON CONFLICT DO NOTHING, not DO UPDATE: the partial unique indexes make a
    repeat submission of the same answer a no-op and a CHANGED answer for the
    same round silently ignored rather than silently overwriting. A revision
    is round_no 2, which is the intra-annotator measurement. Quietly replacing
    round 1 would destroy the ceiling.
    """
    from lib.timeparse import utc_now_str

    value = validate(axis, field, value)
    if axis == AXIS_B and not profile:
        raise ValueError("axis B labels carry a profile; axis A must not")
    if axis == AXIS_A and profile:
        raise ValueError("axis A is profile-independent -- see the CHECK "
                         "constraint in ensure_schema()")

    row = conn.execute(
        """
        INSERT INTO eval_labels (axis, label_set, job_id, field, value,
                                 profile, labeller_id, round_no, labelled_at,
                                 note)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT DO NOTHING
        RETURNING id
        """,
        (axis, label_set, job_id, field, value, profile, labeller_id,
         int(round_no), now or utc_now_str(), note),
    ).fetchone()
    return row is not None


def fetch(conn, *, axis=None, label_set=None):
    """Every label, as dicts. Small by construction -- this is human output.

    LEFT JOIN, NOT INNER, and for the same reason pool_query() gives. A label
    may carry a NULL `label_set` (record() allows one, and the CLI's
    axis-A-is-not-owned-by-a-set rule is why), and an inner join would drop
    those rows silently -- deleting evidence to add a column. A row with no
    matching item simply has `platform` None, which the breakout reports as
    `unknown` rather than as absent.

    At most one item can match: eval_label_items' primary key is
    (label_set, job_id), so this cannot fan a label out into several rows.
    """
    where, params = [], []
    if axis:
        where.append("l.axis = %s")
        params.append(axis)
    if label_set:
        where.append("l.label_set = %s")
        params.append(label_set)
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    cols = ", ".join(f"l.{c}" for c in _LABEL_COLUMNS)
    rows = conn.execute(
        f"SELECT {cols}, i.platform FROM eval_labels l "
        f"LEFT JOIN eval_label_items i "
        f"  ON i.label_set = l.label_set AND i.job_id = l.job_id "
        f"{clause} ORDER BY l.job_id, l.field, l.labeller_id, l.round_no",
        params).fetchall()
    return [dict(zip(_FETCH_COLUMNS, r)) for r in rows]


def progress(conn, label_set, labeller_id):
    """(done, total) for one labeller on one set, for the form's footer."""
    total = conn.execute(
        "SELECT COUNT(*) FROM eval_label_items WHERE label_set = %s",
        (label_set,)).fetchone()[0]
    done = conn.execute(
        "SELECT COUNT(DISTINCT job_id) FROM eval_labels "
        "WHERE label_set = %s AND labeller_id = %s",
        (label_set, labeller_id)).fetchone()[0]
    return done, total


#: 2**64 / phi. Fibonacci hashing's constant, used here for its low-discrepancy
#: property rather than as a hash: successive multiples land maximally far
#: apart, so k labellers tile the tail into k near-equal windows for ANY k,
#: without any of them needing to know what k is. Integer arithmetic
#: throughout -- a float version is deterministic in practice but this is a
#: number that decides which postings get labelled, and it costs nothing to
#: put it beyond argument.
_PHI64 = 11400714819323198485


def tail_offset(rank, tail_size):
    """Where in the non-overlap tail the labeller with this rank starts.

    RANK, NOT NAME, AND THAT IS THE WHOLE POINT. The first version of this
    hashed the labeller_id, which is stateless and spreads people at random
    -- and random windows COLLIDE. Measured against the drawn 200-row set
    (190-row tail, ten labellers, twenty postings each):

        hashed offsets      84 distinct postings
        rank-spaced        110 distinct postings   (the ideal)

    84 misses task 29's ">=100 labelled postings" and 110 meets it, at the
    same twenty-minute sitting. The idealised arithmetic in the plan --
    overlap + labellers * (budget - overlap) -- assumes disjoint windows, and
    hashing does not give disjoint windows; it gives the birthday problem.
    """
    if tail_size <= 0:
        return 0
    return (rank * _PHI64 % (1 << 64)) * tail_size >> 64


def labeller_rank(conn, label_set, labeller_id):
    """This labeller's position in the order people started on this set.

    Derived, not stored, and stable once assigned: labelled_at is written at
    insert time, so a labeller arriving later cannot acquire an earlier first
    label, and nobody's rank can move once they have one. That is what lets
    tail_offset() be both evenly spaced AND resumable -- a volunteer who
    closes the tab is re-seated exactly where they were.

    Ties broken by labeller_id so two people whose first label lands in the
    same instant still get a total order rather than an arbitrary one.

    A labeller with no labels yet has no rank and gets 0. That costs nothing:
    they are still in the overlap block, which every labeller walks in the
    same order anyway, and by the time they reach the tail they have labels.
    """
    row = conn.execute(
        """
        WITH firsts AS (
            SELECT labeller_id, MIN(labelled_at) AS started
            FROM eval_labels WHERE label_set = %(label_set)s
            GROUP BY labeller_id
        )
        SELECT rank FROM (
            SELECT labeller_id,
                   DENSE_RANK() OVER (ORDER BY started, labeller_id) - 1 AS rank
            FROM firsts
        ) ranked
        WHERE labeller_id = %(labeller)s
        """,
        {"label_set": label_set, "labeller": labeller_id}).fetchone()
    return row[0] if row else 0


def next_item(conn, label_set, labeller_id):
    """The next job this labeller has not answered anything about, or None.

    THE DEFECT THIS FIXES. This used to order every labeller's queue
    `overlap DESC, position ASC` -- identically for everyone. Ten volunteers
    labelling twenty postings each therefore answered THE SAME twenty, so

        distinct = overlap + n_labellers * (budget - overlap)

    had a structurally zero second term: distinct coverage could never exceed
    what one person completed, and task 29's ">=100 labelled postings from
    >=5 labellers" was unreachable regardless of turnout. Nothing was red,
    because nothing asserted coverage.

    OVERLAP ROWS STILL COME FIRST, and that ordering is the ceiling's survival
    plan -- see sample(). After those the tail is rotated by the labeller's
    rank, evenly spaced; see tail_offset() for why rank and not name.
    """
    tail_size = conn.execute(
        "SELECT COUNT(*) FROM eval_label_items "
        "WHERE label_set = %s AND NOT overlap",
        (label_set,)).fetchone()[0]
    offset = tail_offset(labeller_rank(conn, label_set, labeller_id),
                         tail_size)

    # Rotation is over the tail's RANK, not over `position` arithmetic. The
    # ranks are contiguous by construction; positions are only contiguous
    # when the overlap rows happen to occupy the low ones, which is true of
    # any set sample() drew and not true of one assembled by hand. Modular
    # arithmetic on a sparse column silently collides two rows onto the same
    # slot and the spread quietly degrades.
    row = conn.execute(
        """
        WITH ordered AS (
            SELECT i.job_id, i.stratum, i.overlap, i.position,
                   ROW_NUMBER() OVER (ORDER BY i.position) - 1 AS tail_rank
            FROM eval_label_items i
            WHERE i.label_set = %(label_set)s AND NOT i.overlap
        ),
        queue AS (
            SELECT job_id, stratum, overlap, position,
                   0 AS band, position AS ord
            FROM eval_label_items
            WHERE label_set = %(label_set)s AND overlap
            UNION ALL
            SELECT job_id, stratum, overlap, position,
                   1 AS band,
                   (tail_rank - %(offset)s + %(tail)s) %% %(tail)s AS ord
            FROM ordered
        )
        SELECT q.job_id, q.stratum, q.overlap, q.position
        FROM queue q
        WHERE NOT EXISTS (SELECT 1 FROM eval_labels l
                           WHERE l.job_id = q.job_id
                             AND l.label_set = %(label_set)s
                             AND l.labeller_id = %(labeller)s)
        ORDER BY q.band ASC, q.ord ASC
        LIMIT 1
        """,
        {"label_set": label_set, "labeller": labeller_id,
         "offset": offset, "tail": max(tail_size, 1)}).fetchone()
    if row is None:
        return None
    return {"job_id": row[0], "stratum": row[1], "overlap": row[2],
            "position": row[3]}


def active_set(conn):
    """The most recently created label set, or None. What the form serves."""
    row = conn.execute(
        "SELECT label_set FROM eval_label_sets "
        "ORDER BY created_at DESC, label_set DESC LIMIT 1").fetchone()
    return row[0] if row else None


# --------------------------------------------------------------------------
# Agreement
# --------------------------------------------------------------------------

#: What a platform is called when the label set recorded none. The same
#: string metrics.selfcheck() uses (metrics.py:406), so a row in the breakout
#: below lines up with the row of the same name in the self-consistency
#: table instead of reading as a different population.
UNKNOWN_PLATFORM = "unknown"

#: A cell whose 95% interval is wider than this is marked `~` and must never
#: be quoted as a rate.
#:
#: THE TEST IS ON THE INTERVAL, NOT ON n, AND THAT IS THE POINT. A stratified
#: set of 100 postings across six platforms leaves single-digit cells, and a
#: bare percentage over n=3 reads exactly like one over n=300 -- CLAUDE.md:
#: "n=17 is not a result". But n alone is the wrong predicate: 10/10 spans
#: [72-100] and does say something, while 5/10 spans [24-76] at the same n and
#: says nothing at all. Width is the quantity that decides whether a cell can
#: separate a good platform from a bad one, and field_cell() already computes
#: it -- so this introduces no new estimate, only a threshold on an existing
#: one.
#:
#: 30 points, calibrated against the numbers this table exists to be compared
#: with rather than picked round. Task 06's clean/messy figures on
#: `ai_involvement` are 92.2% [85-96] and 77.8% [55-91] -- intervals of 11 and
#: 23 points, differing by 14. A cell wider than 30 points is wider than the
#: entire spread of the quantities it would be read against, so it cannot
#: participate in that comparison whatever its point estimate says. In
#: practice that is every cell under about ten items, which is the honest
#: description of a 100-posting set spread over six platforms.
THIN_CI_POINTS = 0.30


def cell_ci(cell):
    """(lo, hi) for either cell shape, because there are two.

    metrics.field_cell() names its interval `agree2_ci` -- floor and ceiling
    are both field_cell() outputs. model_vs_human()'s cells are a different
    quantity (the model against the majority human answer, one trial per
    item) and name theirs `ci`. Reading both here rather than unifying them
    is deliberate: the two columns must keep meaning what they mean, and a
    shared key would be the first step to averaging them.
    """
    if not cell:
        return 0.0, 1.0
    lo, hi = cell.get("ci") or cell.get("agree2_ci") or (0.0, 1.0)
    return lo, hi


def is_thin(cell):
    """Is this cell too wide to be read as a rate? Empty cells are thin."""
    if not cell or not cell.get("n"):
        return True
    lo, hi = cell_ci(cell)
    return (hi - lo) > THIN_CI_POINTS


def platform_index(rows, platforms=None):
    """job_id -> platform, from the label rows themselves.

    fetch() carries `platform` on every row (see _FETCH_COLUMNS), so the
    normal case needs no argument. `platforms` is for a caller holding a set
    file rather than a database -- save_set() writes the same field -- and it
    wins where both are present, because a caller passing an explicit map is
    being specific on purpose.
    """
    index = {}
    for row in rows:
        platform = row.get("platform")
        if platform:
            index.setdefault(str(row["job_id"]), platform)
    for job_id, platform in (platforms or {}).items():
        if platform:
            index[str(job_id)] = platform
    return index


def _platform_blocks(per_field_platform, field_kinds, make=None):
    """The breakout, in metrics.selfcheck()'s shape and no other.

    Returns `fields` (one cell per field per platform), `clean` and `messy`
    (the same cells pooled), and `platform_counts`. That is deliberately the
    same shape metrics.selfcheck() returns at metrics.py:419-429 and that
    report.render_selfcheck() already prints, so the two tables can be read
    against each other rather than each needing its own explanation.

    CLEAN_PLATFORMS IS THE RIGHT AXIS HERE, reused rather than redefined.
    It was drawn for the model's input -- clean ATS HTML against scraped free
    text -- and task 29:87-89 predicts degradation on exactly that boundary.
    It survives the move to a human ceiling for the same reason: a person
    reading an hn_whoishiring comment whose title the parser guessed at also
    has less to go on than one reading a greenhouse posting. A second
    definition here would make the floor's clean/messy columns and this one's
    non-comparable, which is precisely what the reuse of field_cell() exists
    to prevent.

    `unknown` pools into messy, as it does in metrics.selfcheck(): a posting
    whose source was not recorded is not evidence of a clean one.
    """
    make = metrics.field_cell if make is None else make
    fields, clean, messy, counts = {}, {}, {}, {}
    for field, groups in sorted(per_field_platform.items()):
        kind = field_kinds.get(field, "enum")
        fields[field] = {p: make(kind, v) for p, v in sorted(groups.items())}
        clean_values, messy_values = [], []
        for platform, values in sorted(groups.items()):
            counts[platform] = counts.get(platform, 0) + len(values)
            if platform in metrics.CLEAN_PLATFORMS:
                clean_values.extend(values)
            else:
                messy_values.extend(values)
        clean[field] = make(kind, clean_values)
        messy[field] = make(kind, messy_values)
    return {"fields": fields, "clean": clean, "messy": messy,
            "platform_counts": counts}


def _item_key(row):
    """Axis A ignores profile; axis B does not. The keys are independent."""
    if row["axis"] == AXIS_A:
        return (row["job_id"], row["field"])
    return (row["job_id"], row["field"], row["profile"])


def _group(rows, axis):
    grouped = {}
    for row in rows:
        if row["axis"] != axis:
            continue
        grouped.setdefault(_item_key(row), []).append(row)
    return grouped


def inter_annotator(rows, field_kinds, *, axis=AXIS_A, round_no=1,
                    platforms=None):
    """THE CEILING: how often two different people give the same answer.

    This is the quantity that gives every other number here a scale. Without
    it, "the model agrees with humans 80% of the time" cannot be read: if
    humans agree with each other 98% the model is bad, and if they agree 79%
    the model has already saturated the task and no prompt change will help.

    The original design in 03-metrics-and-golden-set.md measured one person
    labelling 5-10 jobs twice a week apart. With ten Builders the stronger
    measurement is available for free -- overlap ~20 postings across all of
    them and compare BETWEEN people. Both are computed; this is the better
    ceiling and intra_annotator() is the weaker one kept because attrition may
    leave it as the only one with any n.

    Reuses metrics.field_cell() unchanged, which means `agree2`, `unanimous`,
    `pairwise` and the Wilson intervals mean here exactly what they mean in
    the self-consistency table -- the floor and the ceiling are then columns of
    the same quantity rather than two statistics that merely look alike.
    `agree2` is the two lowest-sorted labeller ids, which is arbitrary but
    stable; `pairwise` over all C(N,2) pairs is the better point estimate and
    carries no interval, because pairs drawn from one item are not independent
    trials (metrics.py:30).

    ABSTENTIONS ARE DROPPED AND COUNTED. A NULL is "I cannot tell from this
    posting", which is a real and useful answer but not one that can agree or
    disagree with anything. Folding them in as a value would score two people
    who both gave up as two people who concurred.

    `fields` STAYS THE HEADLINE AND `by_platform` SITS BESIDE IT. Task
    29:106 asks for the breakout and 29:87-89 says why -- task 06's
    reconciliation predicts extraction degrades on messy sources and Phase 3
    added several, so a blended number would hide exactly that. It does not
    ask for the blended number to be replaced, and it must not be: the
    per-platform cells are single-digit at any label count this session can
    realistically collect, which is what is_thin() exists to make visible.
    """
    grouped = _group(rows, axis)
    index = platform_index(rows, platforms)
    per_field, per_platform, abstained, thin = {}, {}, {}, {}
    for (key, group) in sorted(grouped.items()):
        field = key[1]
        platform = index.get(str(key[0])) or UNKNOWN_PLATFORM
        answers = {}
        for row in group:
            if row["round_no"] != round_no:
                continue
            if row["value"] is None:
                abstained[field] = abstained.get(field, 0) + 1
                continue
            answers[row["labeller_id"]] = row["value"]
        if len(answers) < 2:
            thin[field] = thin.get(field, 0) + 1
            continue
        values = tuple(answers[k] for k in sorted(answers))
        per_field.setdefault(field, []).append(values)
        per_platform.setdefault(field, {}).setdefault(
            platform, []).append(values)

    return {
        "axis": axis,
        "round": round_no,
        "fields": {f: metrics.field_cell(field_kinds.get(f, "enum"), v)
                   for f, v in sorted(per_field.items())},
        "by_platform": _platform_blocks(per_platform, field_kinds),
        "abstained": abstained,
        "single_labeller_items": thin,
        "labellers": sorted({r["labeller_id"] for r in rows
                             if r["axis"] == axis}),
    }


def intra_annotator(rows, field_kinds, *, axis=AXIS_A, platforms=None):
    """The weaker ceiling: how often ONE person repeats their own answer.

    The original design's measurement -- 5-10 jobs labelled twice, a week
    apart. Kept beside inter_annotator() rather than replaced by it because
    the two can disagree in an informative direction: a person who is
    self-consistent but disagrees with everyone else has a different reading
    of the question, which is a problem with the FORM, not with the labellers,
    and only having both numbers distinguishes the two cases.

    ITS BREAKOUT IS COMPUTED AND NOT PRINTED, and that is a judgement rather
    than an omission. The original design is 5-10 jobs labelled twice
    (03-metrics-and-golden-set.md:25), so a per-platform cell here is n=1 or
    n=2 -- thin by any reading of is_thin(), and a table of `~` cells is
    noise on the page. It is in the returned dict because the JSON consumer
    can pool it across sessions, where the printed table cannot.
    """
    grouped = _group(rows, axis)
    index = platform_index(rows, platforms)
    per_field, per_platform, abstained = {}, {}, {}
    for key, group in sorted(grouped.items()):
        field = key[1]
        platform = index.get(str(key[0])) or UNKNOWN_PLATFORM
        by_labeller = {}
        for row in group:
            if row["value"] is None:
                abstained[field] = abstained.get(field, 0) + 1
                continue
            by_labeller.setdefault(row["labeller_id"], {})[
                row["round_no"]] = row["value"]
        for _labeller, rounds in sorted(by_labeller.items()):
            if len(rounds) < 2:
                continue
            values = tuple(rounds[r] for r in sorted(rounds))
            per_field.setdefault(field, []).append(values)
            per_platform.setdefault(field, {}).setdefault(
                platform, []).append(values)

    return {
        "axis": axis,
        "fields": {f: metrics.field_cell(field_kinds.get(f, "enum"), v)
                   for f, v in sorted(per_field.items())},
        "by_platform": _platform_blocks(per_platform, field_kinds),
        "abstained": abstained,
    }


def consensus(rows, *, axis=AXIS_A, round_no=1):
    """Per item, the majority human answer -- or None where there is no majority.

    A TIE IS NOT BROKEN. Picking one of two equally-supported answers would
    manufacture ground truth out of a disagreement, which is the same error as
    treating a model's output as ground truth, only quieter. Ties are returned
    separately and every caller reports the count.
    """
    grouped = _group(rows, axis)
    agreed, tied = {}, []
    for key, group in sorted(grouped.items()):
        counts = {}
        for row in group:
            if row["round_no"] != round_no or row["value"] is None:
                continue
            counts[row["value"]] = counts.get(row["value"], 0) + 1
        if not counts:
            continue
        top = max(counts.values())
        winners = [v for v, c in counts.items() if c == top]
        if len(winners) > 1:
            tied.append(key)
            continue
        agreed[key] = winners[0]
    return agreed, tied


def model_vs_human(rows, model_values, field_kinds, *, axis=AXIS_A,
                   round_no=1, platforms=None):
    """THE QUESTION -- and on its own it answers nothing. See interpretable().

    `model_values` is {job_id: normalized dict}, which is exactly what
    report.write_jsonl() emits per row and what a corpus fixture's `facts`
    block holds. Comparison happens on normalize()'d values on both sides:
    the human picked from extract.py's own vocabulary (see questions()) and
    the model's dict has been through extract.normalize(), so "Mid-Level" vs
    "mid" cannot be scored as a disagreement.

    Two figures, for the same reason metrics.py reports agree2 and pairwise:

      vs_consensus  model against the majority human answer, one Bernoulli
                    trial per item, so a Wilson interval is valid.
      vs_each       model against every individual labeller. Uses more of the
                    evidence and needs no consensus rule at all, but the pairs
                    from one item are not independent, so it gets no interval.

    Only axis A is meaningful here. There is no model prediction of "would you
    apply" and there must not be one -- CLAUDE.md: LLMs explain, never rank.

    ONLY `vs_consensus` IS BROKEN OUT BY PLATFORM. It is the column that sits
    in the three-quantity table, so it is the one 29:106 is asking about, and
    it is one Bernoulli trial per item so its per-platform cells carry a
    valid interval -- which is the whole basis on which a thin cell is
    identified. `vs_each`'s pairs come from the same item and are not
    independent (metrics.py:30), which is why it carries no interval even
    blended; splitting a number that cannot have an interval into cells too
    small to read would produce the most quotable and least supportable
    figures in the report.
    """
    if axis != AXIS_A:
        raise ValueError(
            "model_vs_human is axis A only. Axis B is a person's preference; "
            "there is no model output to compare it against, and inventing "
            "one would put an LLM between a user and an ordering.")

    agreed, tied = consensus(rows, axis=axis, round_no=round_no)
    index = platform_index(rows, platforms)
    per_field_consensus, per_field_each, per_platform = {}, {}, {}
    missing = set()
    for (job_id, field), human in sorted(agreed.items()):
        normalized = model_values.get(job_id)
        if normalized is None:
            missing.add(job_id)
            continue
        pair = (normalized.get(field), human)
        per_field_consensus.setdefault(field, []).append(pair)
        per_platform.setdefault(field, {}).setdefault(
            index.get(str(job_id)) or UNKNOWN_PLATFORM, []).append(pair)

    grouped = _group(rows, axis)
    for key, group in sorted(grouped.items()):
        job_id, field = key[0], key[1]
        normalized = model_values.get(job_id)
        if normalized is None:
            continue
        for row in group:
            if row["round_no"] != round_no or row["value"] is None:
                continue
            per_field_each.setdefault(field, []).append(
                (normalized.get(field), row["value"]))

    def _cell(pairs, kind):
        n = len(pairs)
        k = sum(1 for a, b in pairs if metrics.exact(kind, a, b))
        return {"kind": kind, "n": n, "k": k,
                "rate": (k / n) if n else None,
                "ci": metrics.wilson(k, n)}

    return {
        "axis": axis,
        "vs_consensus": {f: _cell(p, field_kinds.get(f, "enum"))
                         for f, p in sorted(per_field_consensus.items())},
        "vs_each": {f: _cell(p, field_kinds.get(f, "enum"))
                    for f, p in sorted(per_field_each.items())},
        # The same maker as the blended cell above, NOT metrics.field_cell().
        # A per-platform cell has to mean what the column it sits under
        # means; building it from field_cell() would silently swap `rate`
        # (model vs the majority human answer) for `agree2` (two answers
        # about the same item) and the table would still print.
        "by_platform": _platform_blocks(
            per_platform, field_kinds,
            make=lambda kind, pairs: _cell(pairs, kind)),
        "no_consensus": len(tied),
        "no_model_output": sorted(missing),
    }


# --------------------------------------------------------------------------
# The gate: three quantities or nothing
# --------------------------------------------------------------------------

class Uninterpretable(ValueError):
    """A model-vs-human figure with no floor or no ceiling beside it.

    Raised, never warned. CLAUDE.md: "Any measurement without that floor
    beside it is uninterpretable" -- and a warning is a thing people read
    once. Task 16 set the precedent that the tool refuses to print one
    denominator alone (DECISIONS.md:174); this is that rule for this table.
    """


@dataclasses.dataclass(frozen=True)
class Interpretable:
    """One field's three quantities. Cannot be constructed with fewer.

    This is the ONLY thing report.render_labels() accepts, so there is no code
    path anywhere that prints a model-vs-human number alone. Making the bad
    report unrepresentable rather than discouraged is the whole design; a
    `--force` flag would undo it and there deliberately is not one.
    """

    field: str
    floor: dict        # model self-consistency -- metrics.selfcheck
    ceiling: dict      # inter-annotator      -- inter_annotator()
    measured: dict     # model vs human       -- model_vs_human()

    #: The floor's own breakout, straight out of the selfcheck JSON
    #: (metrics.py:419-429), in the shape _platform_blocks() returns:
    #: {"fields": {platform: cell}, "clean": cell, "messy": cell}. Carried
    #: here because report.render_labels() is handed the triples and not the
    #: selfcheck blob, and the breakout needs all three columns to be a
    #: breakout of the three quantities rather than a second table of one of
    #: them. The clean/messy pair is the row with enough n to read: it is
    #: where task 06's 92.2%-vs-77.8% gap on `ai_involvement` lives.
    #:
    #: IT DOES NOT WEAKEN THE REFUSAL. It has a default and is never checked
    #: below, so it cannot be the thing that makes a triple constructible:
    #: floor, ceiling and measured are still each required and still each
    #: checked for n. A field with a per-platform floor and no blended
    #: measured cell raises exactly as it did before.
    floor_by_platform: dict = dataclasses.field(default_factory=dict)

    def __post_init__(self):
        for name in ("floor", "ceiling", "measured"):
            cell = getattr(self, name)
            if not cell or not cell.get("n"):
                raise Uninterpretable(
                    f"{self.field}: no {name}. Model-vs-human is a ratio "
                    f"between the floor (how often the model agrees with "
                    f"itself) and the ceiling (how often two people agree). "
                    f"Reporting it alone says nothing, so this refuses to "
                    f"build. "
                    + _remedy(name))


def _remedy(name):
    return {
        "floor": "Run `python3 -m evals selfcheck --repeat 3 --out <file>` "
                 "and pass it as --selfcheck.",
        "ceiling": "The eval set needs overlap rows labelled by at least two "
                   "people -- `evals label sample --overlap N`, then task 29.",
        "measured": "No human labels for this field yet. The tables ship "
                    "empty on purpose; task 29 fills them.",
    }[name]


def interpretable(*, floor, ceiling, measured, fields=None):
    """Assemble the three quantities per field, or refuse.

    `floor` is metrics.selfcheck()'s `fields` block, `ceiling` is
    inter_annotator()'s, `measured` is model_vs_human()'s `vs_consensus`.

    Refusal is per field and names which of the three is absent, because the
    common case is not "nothing was measured" but "the floor exists for every
    field and the ceiling exists for two of them" -- and silently dropping the
    other fields would be its own quiet lie about what was measured.

    The floor's per-platform cells come free: `floor` IS metrics.selfcheck()'s
    `fields` block, which already carries `by_platform` beside `overall`
    (metrics.py:419-421). Nothing new is asked of the caller for the floor
    column of the breakout, which is why this signature gained no argument.
    """
    fields = sorted(measured) if fields is None else list(fields)
    out = []
    for f in fields:
        blob = floor.get(f) or {}
        out.append(Interpretable(
            field=f,
            floor=blob.get("overall") or blob or {},
            ceiling=ceiling.get(f) or {},
            measured=measured.get(f) or {},
            floor_by_platform={"fields": blob.get("by_platform") or {},
                               "clean": blob.get("clean") or {},
                               "messy": blob.get("messy") or {}}))
    return out
