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
#:   gate_rejected relevance tier > max_tier_to_score, so extract.py never
#:                 sent it and there is no job_facts row either. These are the
#:                 rows nothing downstream can see, and a human label on them
#:                 is the only way RECALL is ever estimable.
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


def pool_query(profile, cfg=None):
    """The one SELECT. Read-only, and per-platform for the reason corpus.py
    gives at corpus.py:115.

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

    cfg = relevance.load() if cfg is None else cfg
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


def pool(conn, profile, *, per_platform=400, cfg=None):
    """Read production and return classified candidate rows. Never writes.

    Generous per_platform by default for the same reason corpus.py:230 gives:
    the interesting strata are a small fraction of any slice, and a pool too
    thin to contain them yields a set that quietly measures only the easy
    path. Here the risk is sharper -- `gate_rejected` rows are, by
    construction, the ones the pipeline is least interested in keeping fresh.
    """
    import relevance

    cfg = relevance.load() if cfg is None else cfg
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


def sample(rows, n, *, seed=0, quota=None, overlap=0, max_tier=2):
    """Pick `n` rows across the strata, then mark `overlap` of them shared.

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
    """Every label, as dicts. Small by construction -- this is human output."""
    where, params = [], []
    if axis:
        where.append("axis = %s")
        params.append(axis)
    if label_set:
        where.append("label_set = %s")
        params.append(label_set)
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    cols = ", ".join(_LABEL_COLUMNS)
    rows = conn.execute(
        f"SELECT {cols} FROM eval_labels {clause} ORDER BY job_id, field, "
        f"labeller_id, round_no", params).fetchall()
    return [dict(zip(_LABEL_COLUMNS, r)) for r in rows]


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


def next_item(conn, label_set, labeller_id):
    """The next job this labeller has not answered anything about, or None.

    OVERLAP ROWS COME FIRST, and that ordering is the ceiling's survival plan
    -- see sample(). After those, `position` order, which is sorted job_id, so
    two labellers walk the set in the same order and their overlap accrues
    even on the non-overlap rows if they both get far enough.
    """
    row = conn.execute(
        """
        SELECT i.job_id, i.stratum, i.overlap, i.position
        FROM eval_label_items i
        WHERE i.label_set = %s
          AND NOT EXISTS (SELECT 1 FROM eval_labels l
                           WHERE l.job_id = i.job_id
                             AND l.label_set = i.label_set
                             AND l.labeller_id = %s)
        ORDER BY i.overlap DESC, i.position ASC
        LIMIT 1
        """,
        (label_set, labeller_id)).fetchone()
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


def inter_annotator(rows, field_kinds, *, axis=AXIS_A, round_no=1):
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
    """
    grouped = _group(rows, axis)
    per_field, abstained, thin = {}, {}, {}
    for (key, group) in sorted(grouped.items()):
        field = key[1]
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

    return {
        "axis": axis,
        "round": round_no,
        "fields": {f: metrics.field_cell(field_kinds.get(f, "enum"), v)
                   for f, v in sorted(per_field.items())},
        "abstained": abstained,
        "single_labeller_items": thin,
        "labellers": sorted({r["labeller_id"] for r in rows
                             if r["axis"] == axis}),
    }


def intra_annotator(rows, field_kinds, *, axis=AXIS_A):
    """The weaker ceiling: how often ONE person repeats their own answer.

    The original design's measurement -- 5-10 jobs labelled twice, a week
    apart. Kept beside inter_annotator() rather than replaced by it because
    the two can disagree in an informative direction: a person who is
    self-consistent but disagrees with everyone else has a different reading
    of the question, which is a problem with the FORM, not with the labellers,
    and only having both numbers distinguishes the two cases.
    """
    grouped = _group(rows, axis)
    per_field, abstained = {}, {}
    for key, group in sorted(grouped.items()):
        field = key[1]
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

    return {
        "axis": axis,
        "fields": {f: metrics.field_cell(field_kinds.get(f, "enum"), v)
                   for f, v in sorted(per_field.items())},
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
                   round_no=1):
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
    """
    if axis != AXIS_A:
        raise ValueError(
            "model_vs_human is axis A only. Axis B is a person's preference; "
            "there is no model output to compare it against, and inventing "
            "one would put an LLM between a user and an ordering.")

    agreed, tied = consensus(rows, axis=axis, round_no=round_no)
    per_field_consensus, per_field_each = {}, {}
    missing = set()
    for (job_id, field), human in sorted(agreed.items()):
        normalized = model_values.get(job_id)
        if normalized is None:
            missing.add(job_id)
            continue
        per_field_consensus.setdefault(field, []).append(
            (normalized.get(field), human))

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
    """
    fields = sorted(measured) if fields is None else list(fields)
    return [Interpretable(field=f,
                          floor=(floor.get(f) or {}).get("overall")
                                or floor.get(f) or {},
                          ceiling=ceiling.get(f) or {},
                          measured=measured.get(f) or {})
            for f in fields]
