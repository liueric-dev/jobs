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
#:
#: `role_track` IS ON THIS LIST FOR A DIFFERENT REASON FROM THE OTHER FOUR, and
#: the difference matters enough to state. The other four are here because task
#: 06 measured them and found the model unstable; a human label buys a ceiling
#: to read that instability against. `role_track` HAS NO TASK 06 FIGURE AT ALL
#: -- it postdates that measurement (task 11 added it) and its nine-value
#: vocabulary is explicitly provisional, derived pre-Phase-3 from a tech-heavy
#: corpus. See `git show refactor-freeze-2026-08-02:docs/role-track-derivation.md`.
#:
#: It is here because task 30 groups its precision figures BY this vocabulary,
#: so an unvalidated vocabulary would silently condition every per-track number
#: that task produces. And the validation is only available now: nobody can
#: label a set after the labelling session is over.
#:
#: THE ROWS WHERE IT BUYS THE MOST ARE THE ROWS WHERE model_vs_human IS
#: SILENT, which inverts the usual argument. Measured 2026-07-29 over
#: job_facts at facts_version 3: `role_track` is NULL on 244 of 881 rows
#: (27.7%), and within the pursuit-v1 label set it is NULL on 16 of 100
#: `surfaced`, 17 of 50 `below_floor` and 50 of 50 `gate_rejected` -- 83 of
#: 200. On those 83 there is no model answer to agree or disagree with. That is
#: the interesting half: if a human confidently assigns a track where the
#: extractor abstained, the NULL rate is an EXTRACTION problem; if the human
#: cannot either, the VOCABULARY is wrong. Those are different fixes and no
#: other instrument distinguishes them.
#:
#: Rejected: swapping it in for `role_archetype` to keep the form at five
#: questions. `role_archetype` is the field task 12 measured at 31.1% `other`
#: (44.0% on first-time extractions), so it is the one with a known quality
#: problem and dropping it would forfeit the label that diagnoses it.
AXIS_A_FIELDS = ("ai_involvement", "seniority_level", "role_archetype",
                 "remote_policy", "role_track")

#: Fields in tasks/extract.py PRIORITY_FIELDS that are NOT on the form, with
#: the measurement that took them off it. The instruction is
#: `git show refactor-freeze-2026-08-02:docs/ingestion_tests/03-metrics-and-golden-set.md:116`:
#: let the selfcheck narrow the set, and record the rest as known-unstable
#: rather than dropping them silently.
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

#: `role_track`'s answer for "none of these tracks describes this role".
#:
#: IT IS A VALUE, NOT AN ABSTENTION, AND THAT DISTINCTION IS THE WHOLE POINT.
#: extract.py's own prompt (`extract.py:338`) tells the model: "Use null if none
#: of the listed tracks clearly describes the role. Do not force a value -- null
#: is the correct answer for a role that belongs to no listed track, and is more
#: useful than a wrong one." So the model's NULL on this field is a SUBSTANTIVE
#: ANSWER. ROLE_TRACK has nine values and no `other`, unlike ARCHETYPE, whose
#: prompt says "'other' is a real answer and is not the same as omitting the
#: field".
#:
#: validate() below turns '' and 'unsure' into None -- an abstention, "I can't
#: tell from this posting". Without this constant a human meaning "no track
#: fits" would store the same None, and model_vs_human would then be comparing
#: a considered verdict against a shrug and scoring them as agreement. That is
#: the same conflation the AXIS_B_FIELD note below refuses for "no" versus "I
#: cannot tell", one field over.
#:
#: Compared against a model NULL this value means AGREEMENT: both say no listed
#: track fits. See model_vs_human().
NO_TRACK_FITS = "no_track_fits"

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
        # ROLE_TRACK plus one. The pipeline expresses "no track fits" as null,
        # which a form cannot offer as a radio button distinguishable from the
        # abstention every question already carries -- see NO_TRACK_FITS.
        "role_track": tuple(extract_stage.ROLE_TRACK) + (NO_TRACK_FITS,),
    }
    prompts = {
        "ai_involvement": "How much AI is in this job, as the posting "
                          "describes it?",
        "seniority_level": "What seniority does the posting actually ask "
                           "for?",
        "role_archetype": "What kind of role is this?",
        "remote_policy": "Where does the posting say the work happens?",
        "role_track": "Which broad role family does this posting belong to?",
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

#: Pipeline-owned tables the labelling surface READS, kept apart from the
#: label tables it owns. record() resolves facts_version from job_facts at
#: write time (PROVENANCE_COLUMNS below), so a missing SELECT here is a 500 on
#: a volunteer's submit rather than a refusal to start -- which is what
#: verify_schema() exists to convert.
#:
#: NOT MERGED INTO WEB_PRIVILEGES, for two reasons that are easy to miss.
#: `set(WEB_PRIVILEGES) == set(TABLES)` is an invariant with a test on it
#: (tests/test_labels.py) and it is a true statement about this module's own
#: tables. And webapp/schema_web.py does `REQUIRED_TABLES.update(
#: WEB_PRIVILEGES)` over a dict that ALREADY declares job_facts at line 45 --
#: identical today, so the merge would be invisible, and silently authoritative
#: the day the two disagree. jobs_web already holds this grant; nothing new is
#: issued.
WEB_READS = {
    "job_facts": ("SELECT",),
}

#: The two columns that record which extraction a label was formed against,
#: in the shape lib.dbconn.add_missing_columns takes. Also spelled out in the
#: CREATE TABLE in ensure_schema(); the test that they agree is in
#: tests/test_labels.py and is deliberately not a shared constant feeding both.
#:
#: WHY TWO COLUMNS AND NOT ONE NULLABLE INTEGER. A single `facts_version`
#: would collapse two states that mean opposite things:
#:
#:   facts_version IS NULL, known   the posting had NO job_facts row when the
#:                                  judgement was made. Permanent and normal --
#:                                  it is most of the `gate_rejected` and
#:                                  `below_floor` strata, and those labels can
#:                                  never be compared against model output at
#:                                  any version, which is a fact worth having.
#:   NOT known                      nobody was recording. Every row written
#:                                  before 2026-08-02.
#:
#: A sentinel 0 for the first would put back exactly what task 11 took out
#: when normalize() stopped laundering absence into sentinels. NOT NULL
#: DEFAULT FALSE gives every pre-existing row the right answer without a
#: backfill, and a backfill is not available anyway: today's
#: job_facts.facts_version is today's value, not the one that was current when
#: someone answered the form. The rule is job_events.rank's -- a guessed value
#: is worse than a missing one. DEC-95.
#:
#: WHY IT IS ON THE LABEL AND NOT ON eval_label_items, where `platform` lives
#: and where _FETCH_COLUMNS below is emphatic that a second copy does not
#: belong. `platform` is a property of the POSTING and cannot change; this is
#: a property of the LABELLING EVENT and is supposed to be able to disagree
#: with the live table -- that disagreement is the entire signal. The
#: precedent is `stratum` on eval_label_items, carried on the row because it
#: is a property of the pipeline AT SAMPLING TIME. Round 2 is seven days after
#: round 1 by design, so a re-extraction can land between one labeller's two
#: answers, and per-item would average that away.
PROVENANCE_COLUMNS = (
    ("facts_version", "INTEGER"),
    ("facts_version_known", "BOOLEAN NOT NULL DEFAULT FALSE"),
)

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
    api/app.py:99: the long-running browser-facing process holds no CREATE
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
            facts_version       INTEGER,
            facts_version_known BOOLEAN NOT NULL DEFAULT FALSE,
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

    # WHICH EXTRACTION THE LABEL WAS FORMED AGAINST. Added 2026-08-02; every
    # row written before that carries the defaults, which is the honest answer
    # and not a gap to be filled. See PROVENANCE_COLUMNS for why there are two
    # of them and DEC-95 for why nothing is backfilled.
    #
    # In the DDL above as well as here, and the pairing is not redundant: the
    # CREATE TABLE serves a database that does not exist yet and this serves
    # the one that does. tests/test_labels.py asserts the two agree, because
    # task 41a was a live production bug of exactly this shape -- a column
    # added on one side of a pair, the other side not following, and the
    # Workday gate dying on UndefinedColumn in the nightly run.
    from lib import dbconn

    dbconn.add_missing_columns(conn, "eval_labels", PROVENANCE_COLUMNS)
    conn.commit()


def verify_schema(conn, privileges=None, sequences=None):
    """Names everything missing, not just the first thing.

    Ported from webapp/schema_web.py:143 including its reasoning: a table can
    exist and still be unusable if a GRANT was missed, and that failure mode
    surfaces as a 500 on a real user's first click rather than as a refusal to
    start. Returns a list of problems; the caller decides whether to raise.
    """
    privileges = ({**WEB_PRIVILEGES, **WEB_READS} if privileges is None
                  else privileges)
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
    """  # noqa: S608 -- splices tier_expr from relevance.tier_sql(), the one relevance SQL compiler, and TABLE/FACTS_TABLE/MATCHES_TABLE constants
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

    # THE OVERLAP BLOCK IS STRATIFIED, NOT THE FIRST n BY job_id. It carries
    # the ENTIRE inter-annotator ceiling -- it is the only part of the set
    # more than one person sees -- so its composition decides what that
    # ceiling is a ceiling ON. Taking the head of a job_id sort is a draw
    # with no stratification guarantee, and the first draw of pursuit-v1
    # returned 6 gate_rejected / 3 surfaced / 1 below_floor against a set
    # that is 25/50/25 (~2% likely). Six of ten rows would then have been
    # postings the pipeline threw away -- "Senior Mechanical Engineer",
    # "Branch Operations Coordinator" -- on which every labeller answers
    # Axis B "no" and agreement is near-unanimous for free. THAT INFLATES
    # THE CEILING BY MEASURING IT ON THE EASY CASES, which is the same
    # failure mode as evaluating on the population the pipeline already
    # chose, one level in.
    #
    # Proportional allocation by largest remainder, so the block mirrors the
    # set it is drawn from and the arithmetic is exact rather than rounded
    # into a short block.
    by_stratum = {}
    for row in picked:
        by_stratum.setdefault(row["stratum"], []).append(row)

    overlap = min(overlap, len(picked))
    exact = {s: overlap * len(rs) / len(picked) for s, rs in by_stratum.items()}
    want = {s: int(v) for s, v in exact.items()}
    for s in sorted(by_stratum, key=lambda s: (-(exact[s] - want[s]), s)):
        if sum(want.values()) >= overlap:
            break
        want[s] += 1

    shared = set()
    for stratum, rows_in in by_stratum.items():
        shared.update(r["job_id"] for r in rows_in[:want[stratum]])

    # Shared rows first, then the rest, each half still in job_id order so
    # the set stays canonically ordered and next_item()'s tail rotation has
    # a contiguous block to rotate.
    picked.sort(key=lambda r: (r["job_id"] not in shared, r["job_id"]))
    for i, row in enumerate(picked):
        row["position"] = i
        row["overlap"] = row["job_id"] in shared
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


class SetAlreadyDrawn(ValueError):
    """A second draw under a name that is already pinned to a first one.

    Raised, never warned, and never downgraded by a flag -- the same stance
    `Uninterpretable` takes one section down and for the same reason: a warning
    is a thing people read once, and this one has to survive being re-read at
    11pm by whoever is re-running the sampler because a stratum came out short.

    THE DAMAGE IS SILENT, WHICH IS WHY IT NEEDS AN EXCEPTION. register_set()
    inserts `ON CONFLICT DO NOTHING` on both tables, so a re-draw with a
    different --seed or --n does not fail: the existing items keep their old
    `position` and `overlap`, newly drawn job_ids are APPENDED, and
    `eval_label_sets.n` and `job_id_sha256` go on describing the first draw. The
    database, the committed fixture and the published figures then disagree
    three ways, and nothing anywhere is red.
    """


def redraw_refusal(conn, label_set, rows):
    """Why this draw may not be registered under this name, or None if it may.

    A string rather than a raise, so a caller that has not written anything yet
    -- `evals label sample --dry-run` -- can ASK the question read-only and
    report the answer, instead of finding out by being refused. register_set()
    below turns the same string into SetAlreadyDrawn, so there is one rule and
    two renderings of it, not two rules.

    THREE OUTCOMES, AND THE MIDDLE ONE IS THE POINT.

    No stored row -- a first draw. Allowed, unchanged.

    Stored digest EQUALS this draw's -- allowed, and it must stay allowed. A
    re-run of the same command with the same seed is how an operator recovers
    from a crash between register_set() and save_set(), and how `pursuit-v1`'s
    own defect-4 redraw was verified. Refusing every re-registration would make
    the sampler unusable for the one safe case it is used for most.

    Stored digest DIFFERS -- refused. CLAUDE.md pins eval sets by sorted
    `job_id`; a set regenerated in place changes what every published figure was
    measured on while the figures sit unchanged in the docs, now wrong. The
    message names both digests so the reader can tell "I changed the seed" from
    "the corpus moved under me", which are different mistakes with different
    fixes.

    AND `eval_labels` OVERRIDES ALL THREE. Any label at all for the set refuses
    any re-registration, INCLUDING one at the same digest. Same digest does not
    mean same set: the job ids are the digest's whole input, so a re-draw that
    keeps them and moves the `overlap` flags -- exactly what the defect-4 redraw
    did -- hashes identically. Those flags decide which postings every labeller
    sees and which rows the inter-annotator ceiling is computed over, so moving
    them under someone who has already answered silently changes what their
    answers were answers to. The set tables would not even record the move
    (ON CONFLICT DO NOTHING), but save_set() rewrites the committed fixture,
    which is what report time reads.
    `git show refactor-freeze-2026-08-02:docs/tasks/refactor/HANDOFF.md:275`
    calls this window closed as prose; this is the prose in code.
    """
    stored = conn.execute(
        "SELECT n, job_id_sha256 FROM eval_label_sets WHERE label_set = %s",
        (label_set,)).fetchone()
    if stored is None:
        return None
    stored_n, stored_sha = stored
    fresh_sha = digest(rows)
    labelled = conn.execute(
        "SELECT COUNT(*) FROM eval_labels WHERE label_set = %s",
        (label_set,)).fetchone()[0]

    # Both digests, both counts, on every refusal -- including the one where
    # the digests match, where seeing them match is what tells the reader the
    # refusal is about the labels and not about the draw.
    facts = (f"stored sha256(sorted job_id)={stored_sha} over n={stored_n}; "
             f"this draw is {fresh_sha} over n={len(rows)}; "
             f"eval_labels holds {labelled} row(s) for {label_set!r}")

    if labelled:
        return (
            f"{label_set} has been labelled and cannot be re-registered "
            f"({facts}). This holds even at an identical digest: the job ids "
            f"are the digest's only input, so a draw that keeps them and moves "
            f"the `overlap` flags hashes the same, and those flags decide what "
            f"every labeller was shown. Draw the new set under a NEW "
            f"--label-set and a new --out; the existing labels stay attached "
            f"to the set they were answers to.")
    if fresh_sha != stored_sha:
        return (
            f"{label_set} is already drawn from a different set of job ids "  # noqa: S608 -- not executed SQL -- a human-readable error message quoting the DELETE an operator would type by hand
            f"({facts}). An eval set is pinned by its sorted job_id and is "
            f"never regenerated in place -- the figures measured on the first "
            f"draw would stay in the docs, unchanged and now wrong. Draw under "
            f"a NEW --label-set and a new --out, or, while eval_labels is "
            f"still empty for it, DELETE FROM eval_label_sets WHERE label_set "
            f"= '{label_set}' first (the items cascade) and say in --note why.")
    return None


def register_set(conn, label_set, rows, *, seed, profile, note=None):
    """Record the set and its items. Writes nothing to eval_labels.

    THE REDRAW GUARD IS HERE, NOT IN THE CLI, so every caller inherits it --
    the same argument webapp/schema_web.py:97 makes for putting init-schema's
    work in one function two entry points call. A check in cmd_label_sample
    protects the one path that exists today and none of the ones added later,
    and the failure it is protecting against is invisible from every side.
    See redraw_refusal() for what is refused and why.
    """
    from lib.timeparse import utc_now_str

    refusal = redraw_refusal(conn, label_set, rows)
    if refusal:
        raise SetAlreadyDrawn(refusal)

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
                  "labeller_id", "round_no", "labelled_at", "note",
                  "facts_version", "facts_version_known")

#: What fetch() returns: the label, plus the platform of the posting it is
#: about. `platform` is NOT a column of `eval_labels` and must not become one
#: -- it is a property of the posting, already recorded once on
#: eval_label_items (ensure_schema above), and a second copy on every label
#: row is a copy that can disagree with the first.
#:
#: `facts_version` IS a column of eval_labels and the distinction is exact,
#: not a relaxation of the rule above: what is stored is the version that was
#: current WHEN THE JUDGEMENT WAS MADE, and it is supposed to be able to
#: disagree with today's job_facts. A copy that can never disagree is
#: duplication; one that must be able to is a snapshot. PROVENANCE_COLUMNS
#: gives the argument in full.
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

    facts_version IS RESOLVED HERE AND NOT PASSED IN, for the same reason
    validate() is called here: one place, and a route cannot forget. It is a
    scalar subquery inside the INSERT rather than a SELECT before it, so there
    is no window in which a re-extraction lands between the read and the write
    and no second round trip on a form submit. job_facts.job_id is the primary
    key (../schema.py), so it returns at most one row, and SQL NULL when the
    posting has no extraction at all -- which is a real state, not a failure,
    and is why facts_version_known is a separate column. See
    PROVENANCE_COLUMNS.

    THE COLUMNS MUST EXIST BEFORE THIS RUNS. That is ensure_schema()'s job and
    webapp/schema_web.py's REQUIRED_COLUMNS is what makes a deploy that shipped
    this INSERT ahead of the migration refuse to start rather than 500 on a
    volunteer's first submit.
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
                                 note,
                                 facts_version, facts_version_known)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                (SELECT facts_version FROM job_facts WHERE job_id = %s), TRUE)
        ON CONFLICT DO NOTHING
        RETURNING id
        """,
        (axis, label_set, job_id, field, value, profile, labeller_id,
         int(round_no), now or utc_now_str(), note, job_id),
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
        f"SELECT {cols}, i.platform FROM eval_labels l "  # noqa: S608 -- splices _LABEL_COLUMNS (module constant) and a where clause built from fixed literals, values always bound via params
        f"LEFT JOIN eval_label_items i "
        f"  ON i.label_set = l.label_set AND i.job_id = l.job_id "
        f"{clause} ORDER BY l.job_id, l.field, l.labeller_id, l.round_no",
        params).fetchall()
    return [dict(zip(_FETCH_COLUMNS, r)) for r in rows]


def progress(conn, label_set, labeller_id, *, round_no=1):
    """(done, total) for one labeller on one set, for the form's footer.

    ROUND 2's DENOMINATOR IS THE OVERLAP BLOCK, NOT THE SET. Counting round-2
    progress against all 200 items would show a volunteer "3 / 200" on a queue
    that is ten rows long, which reads as an eight-hour evening and is the
    single most likely reason someone closes the tab. The queue and the
    denominator have to be the same population -- see next_item().
    """
    if round_no != 1:
        total = conn.execute(
            "SELECT COUNT(*) FROM eval_label_items "
            "WHERE label_set = %s AND overlap",
            (label_set,)).fetchone()[0]
    else:
        total = conn.execute(
            "SELECT COUNT(*) FROM eval_label_items WHERE label_set = %s",
            (label_set,)).fetchone()[0]
    done = conn.execute(
        "SELECT COUNT(DISTINCT job_id) FROM eval_labels "
        "WHERE label_set = %s AND labeller_id = %s AND round_no = %s",
        (label_set, labeller_id, int(round_no))).fetchone()[0]
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


#: How long a labeller must wait before the same posting is served again for
#: round 2. Days.
#:
#: THIS CONSTANT IS THE MEASUREMENT, NOT A POLITENESS SETTING. Round 2 exists
#: to measure intra-annotator agreement -- whether one person gives the same
#: answer twice. Served an hour later, that measures whether they REMEMBER
#: their first answer, which is a fact about human memory and not about the
#: field's difficulty, and it would come back near 100% and be quoted as a
#: ceiling. The quantity is specified at
#: `git show refactor-freeze-2026-08-02:docs/ingestion_tests/03-metrics-and-golden-set.md:25`
#: as "5-10 jobs labelled twice, A WEEK APART" and the delay is that phrase,
#: in code.
#:
#: Seven days, from that line, not tuned. Shortening it does not buy a faster
#: measurement, it buys a different and weaker one.
ROUND_TWO_DELAY_DAYS = 7


def round_two_ready(conn, label_set, labeller_id, *, now=None,
                    delay_days=ROUND_TWO_DELAY_DAYS):
    """(ready, n_waiting, earliest) -- may this labeller start round 2 yet?

    Separate from next_item() so a caller can explain a refusal rather than
    show an empty page. "Come back on Tuesday" and "you have finished" are
    different states and the form has to be able to tell them apart.

    `n_waiting` counts postings that will EVENTUALLY be re-askable, so it
    deliberately carries no maturity bound -- that is what lets a caller
    distinguish "not yet" from "finished". It must, however, carry the same
    `value IS NOT NULL` filter as next_item() and round_one_answers(): a
    posting that can never be served must not be counted as outstanding, or the
    caller's "come back later" page never retires. See the SQL comment.
    """
    from lib.timeparse import utc_now_str

    row = conn.execute(
        """
        SELECT COUNT(DISTINCT l.job_id), MIN(l.labelled_at)
        FROM eval_labels l
        JOIN eval_label_items i
          ON i.label_set = l.label_set AND i.job_id = l.job_id
        WHERE l.label_set = %s AND l.labeller_id = %s
          AND l.round_no = 1 AND i.overlap
          -- value IS NOT NULL, matching next_item() and round_one_answers().
          -- Without it a posting a labeller ABSTAINED on across every question
          -- counts toward n_waiting while being permanently unservable (the
          -- queue needs a non-NULL round-1 row), so the caller's
          -- `done < n_waiting` test never comes true and the "come back later"
          -- page becomes PERMANENT -- the original round-2 exhaustion defect
          -- inverted. Plausible on a thin gate_rejected posting, and 2 of the
          -- 10 overlap rows in pursuit-v1 are gate_rejected.
          AND l.value IS NOT NULL
        """,
        (label_set, labeller_id)).fetchone()
    n, earliest = (row or (0, None))
    if not n or earliest is None:
        return False, 0, None

    # MIN, matching the per-row gate in next_item(): the date this reports is
    # when the FIRST row becomes re-askable, which is when the queue stops
    # being empty. Reporting the last row's date would tell a volunteer to come
    # back later than they need to.
    import datetime as _dt
    when = (_dt.datetime.fromisoformat(str(earliest)[:19])
            + _dt.timedelta(days=delay_days)).strftime("%Y-%m-%dT%H:%M:%S")
    ready = str(now or utc_now_str())[:19] >= when
    return ready, n, when


def round_one_answers(conn, label_set, job_id, labeller_id, *, now=None,
                      delay_days=ROUND_TWO_DELAY_DAYS):
    """Fields this labeller answered about this posting in round 1, and MAY be
    re-asked in round 2. A set of field names.

    ROUND 2 RE-ASKS WHAT WAS ANSWERED, NOTHING ELSE, AND THAT IS WHAT KEEPS THE
    DELAY HONEST. Three exclusions, each of which was a defect before it was a
    filter:

    NEVER ANSWERED. next_item()'s round-2 branch matches on the POSTING, not
    the field, so round 2 would otherwise re-render every question including
    ones left blank the first time. An answer to one of those is a first
    answer, not a revision, and it has nowhere correct to go: filed as round 2
    it is an orphan no agreement function reads (intra_annotator needs two
    rounds to compare; consensus, inter_annotator and model_vs_human are all
    round-1-scoped), and filed as round 1 it becomes a fresh round-1 row that
    a round-2 row can then partner MINUTES LATER -- bypassing
    ROUND_TWO_DELAY_DAYS entirely, because the posting's eligibility is judged
    on its OTHER fields' timestamps and intra_annotator() never reads
    `labelled_at` at all. Both were live; this is why neither is.

    ABSTAINED. An abstention writes a row with a NULL value, so it is
    "answered" to SQL. But intra_annotator drops a NULL side and then drops the
    pair for having one round, which is the same silent loss. It is also the
    module's stated position one function down: an abstention "is not one that
    can agree or disagree with anything". "I could not tell, then I could" is a
    real thing a person may experience and it is NOT self-agreement; if it is
    ever wanted, it is a different measurement and needs its own name.

    TOO FRESH. Per field, not per posting. The delay is the measurement (see
    ROUND_TWO_DELAY_DAYS) and it has to be enforced where the pair is made,
    not only where the queue is served -- any route that writes a close pair
    lands it in the ceiling unmarked, because nothing downstream checks.
    """
    cutoff = _round_two_cutoff(now, delay_days)
    return {r[0] for r in conn.execute(
        "SELECT field FROM eval_labels WHERE label_set = %s AND job_id = %s "
        "AND labeller_id = %s AND round_no = 1 AND value IS NOT NULL "
        "AND labelled_at <= %s",
        (label_set, job_id, labeller_id, cutoff)).fetchall()}


def _round_two_cutoff(now=None, delay_days=ROUND_TWO_DELAY_DAYS):
    """The latest round-1 timestamp still too fresh to re-ask. A string.

    String comparison throughout, because `labelled_at` is TEXT holding
    lib.timeparse.utc_now_str()'s "%Y-%m-%dT%H:%M:%S" -- a fixed-width ISO
    form, so lexical and chronological order are the same thing. The same
    property webapp/jobs.py's impression-dedup cutoff relies on. Do not
    "improve" this into a timestamptz cast: the column is not one, and the cast
    would run per row.
    """
    import datetime as _dt

    from lib.timeparse import utc_now_str

    base = str(now or utc_now_str())[:19]
    return (_dt.datetime.fromisoformat(base)
            - _dt.timedelta(days=delay_days)).strftime("%Y-%m-%dT%H:%M:%S")


def next_item(conn, label_set, labeller_id, *, round_no=1, now=None,
              delay_days=ROUND_TWO_DELAY_DAYS):
    """The next job this labeller has not answered anything about, or None.

    ROUND 2 IS A DIFFERENT QUEUE AND IT IS THE OVERLAP BLOCK, NOTHING ELSE.
    Round 1's predicate is "not answered yet"; round 2's is its inverse,
    "answered in round 1 and not yet in round 2", restricted to `overlap` rows.

    Why the overlap block specifically, rather than a fresh 5-10:

      It is the only part of the set more than one person sees, so it is
      already where the INTER-annotator ceiling is measured (see sample(), and
      the stratification note there). Re-serving those same rows means both
      ceilings are computed over IDENTICAL POSTINGS and can therefore be read
      against each other. Measured on two different subsets they would differ
      for two reasons at once -- the quantity and the postings -- and
      test_the_two_ceilings_are_different_quantities exists precisely because
      that distinction is the point.

      It is also 10 rows, which is what
      `git show refactor-freeze-2026-08-02:docs/ingestion_tests/03-metrics-and-golden-set.md:25`
      asks for ("5-10 jobs labelled twice"), at ~10 minutes of a volunteer's time.

    THE DELAY IS PART OF THE QUEUE, see ROUND_TWO_DELAY_DAYS. This function
    does not enforce it -- round_two_ready() does, so that a caller can say
    WHEN rather than showing an empty page -- but a round-2 queue served
    immediately measures memory and not agreement, and any caller that skips
    that check is producing a number it should not print.

    Round 1's behaviour is unchanged, deliberately down to the SQL: the
    rank-spacing below is what buys 110 distinct postings instead of 84 and
    must not be perturbed by adding a second mode. See tail_offset().

    THE DEFECT THIS FIXES (round 1). This used to order every labeller's queue
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
    if round_no != 1:
        # The inverse predicate, over the overlap block only. Ordered by
        # `position` and NOT rotated: round 2 is ten rows and every labeller
        # answers all of them, so there is no coverage to spread and rotating
        # would only make two people's queues differ for no gain.
        #
        # THE DELAY IS ENFORCED PER ROW, NOT PER LABELLER, and that is a real
        # distinction rather than a refinement. Gating on the labeller's
        # earliest round-1 answer would serve a row answered yesterday as soon
        # as their oldest row matured -- measuring memory on that row, which is
        # the one thing ROUND_TWO_DELAY_DAYS exists to prevent. Gating on their
        # LATEST would be sound but blocks nine mature rows behind one fresh
        # one, for up to a month. Per row is the only version that is both
        # correct and not self-defeating; in practice the overlap block is
        # answered in one sitting and all ten mature together anyway.
        row = conn.execute(
            """
            SELECT i.job_id, i.stratum, i.overlap, i.position
            FROM eval_label_items i
            WHERE i.label_set = %(label_set)s AND i.overlap
              AND EXISTS (SELECT 1 FROM eval_labels l
                           WHERE l.job_id = i.job_id
                             AND l.label_set = %(label_set)s
                             AND l.labeller_id = %(labeller)s
                             AND l.round_no = 1
                             AND l.value IS NOT NULL
                             AND l.labelled_at <= %(cutoff)s)
              AND NOT EXISTS (SELECT 1 FROM eval_labels l
                               WHERE l.job_id = i.job_id
                                 AND l.label_set = %(label_set)s
                                 AND l.labeller_id = %(labeller)s
                                 AND l.round_no = %(round)s)
            ORDER BY i.position ASC
            LIMIT 1
            """,
            {"label_set": label_set, "labeller": labeller_id,
             "round": int(round_no),
             "cutoff": _round_two_cutoff(now, delay_days)}).fetchone()
        if row is None:
            return None
        return {"job_id": row[0], "stratum": row[1], "overlap": row[2],
                "position": row[3]}

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
    (`git show refactor-freeze-2026-08-02:docs/ingestion_tests/03-metrics-and-golden-set.md:25`),
    so a per-platform cell here is n=1 or n=2 -- thin by any reading of
    is_thin(), and a table of `~` cells is
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


def as_model_domain(field, human_value):
    """A human answer projected onto the vocabulary the model answers in.

    ONE FIELD NEEDS THIS AND THE REASON IS NO_TRACK_FITS. `role_track` has no
    `other` member; extract.py:338 tells the model to answer null when no
    listed track fits, so the model's null on that field is a verdict. A form
    cannot offer null as a radio button distinguishable from the abstention
    every question already carries, so the human says NO_TRACK_FITS instead.

    THE TWO REPRESENTATIONS MUST STAY SEPARATE IN STORAGE AND FOLD TOGETHER AT
    COMPARISON, WHICH IS WHY THIS IS A FUNCTION AND NOT A validate() RULE.
    Folding in validate() would write None to eval_labels, making "no track
    fits" indistinguishable from "I can't tell from this posting" forever --
    and those are the two statements this module works hardest to keep apart
    (see NO_TRACK_FITS, and AXIS_B_VALUES' note on "no" versus abstention).
    Folding here loses nothing: a human abstention never reaches a comparison,
    because consensus() drops None values and vs_each skips them, so the only
    thing NO_TRACK_FITS can match is a model null -- which is agreement, and is
    the intended reading.

    Every other field passes through untouched. Do not grow this into a general
    normalisation layer: questions() reads its vocabularies from extract.py
    precisely so that no such layer is needed, and a second place where values
    get rewritten is a second place they can drift.
    """
    if field == "role_track" and human_value == NO_TRACK_FITS:
        return None
    return human_value


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

    AN ABSENT FIELD IS NOT A NULL ANSWER, AND `.get()` CANNOT TELL THEM APART.
    This used to build every pair with `normalized.get(field)`, which collapses
    two different situations into the same `None`:

      the key is MISSING       the model produced no answer for this field.
                               Nothing to agree or disagree with.
      the key is PRESENT, null  on `role_track` that is a VERDICT. extract.py's
                               own prompt (extract.py:338) says: "Use null if
                               none of the listed tracks clearly describes the
                               role. Do not force a value -- null is the
                               correct answer for a role that belongs to no
                               listed track, and is more useful than a wrong
                               one."

    So the first was scored as though the model had answered "no track fits",
    and as_model_domain() makes the collision exact rather than approximate: it
    folds a human NO_TRACK_FITS to None for comparison, so silence and a
    considered verdict scored as AGREEMENT. That is the same conflation
    NO_TRACK_FITS exists to prevent, reintroduced one layer down -- comparing a
    verdict against a shrug, except here the shrug is the model's.

    Membership is tested instead. A present null is compared, because on
    `role_track` it is an answer; a missing key is excluded and COUNTED, in
    `no_model_field`. Silence is this system's failure mode (CLAUDE.md) and a
    field driven to 0% by a corpus's shape is exactly the kind of number that
    gets quoted as a model finding.

    THE CORPUS THIS IS NOT MEASURABLE AGAINST, AND WHY IT STAYS THAT WAY.
    Measured 2026-07-30: `evals/fixtures/pursuit-criteria-corpus.jsonl` holds
    859 frozen rows, each a flat dict with no nested `facts` block, and NONE of
    them carries a `role_track` key -- 0 of 859, against 859 of 859 for the
    other four AXIS_A_FIELDS. `role_track` was added to the form after that
    corpus was frozen (task 11 added the column; see AXIS_A_FIELDS' note). So
    every human `role_track` answer except `no_track_fits` would have scored as
    a disagreement with a model that never spoke, driving that field's
    `vs_consensus` toward 0% for a reason with nothing to do with the model.

    THE FIXTURE IS NOT THE THING TO FIX. Writing `role_track` values into it
    would be inventing model answers in an eval corpus -- a fabricated ground
    truth, which is the one thing this whole module exists to keep out of the
    measurement -- and it would do so in a file with no generator script:
    `git show refactor-freeze-2026-08-02:docs/tasks/refactor/HANDOFF.md:1043-1047`
    records that it and pursuit-criteria-goldens.json "were produced ad hoc and
    re-pinned by hand once already". That goldens file pins scores and ranks for 30 of these
    job_ids and tests/test_match.py asserts them (its PURSUIT_CORPUS_FILE,
    test_match.py:414), so the rows are load-bearing for a second measurement
    as well. Note it is NOT covered by tests/test_evals.py:454's sha256 pin,
    which lists corpus-v1 and corpus-v2 only -- so an edit here would be
    QUIETER than an edit to those, not louder, which makes the temptation worse
    rather than better.

    The honest report is that the field is not measurable against this corpus,
    which is what the counter says. Re-extracting it at a facts_version that
    carries `role_track` is separate, deliberate follow-up work, and whoever
    does it writes the generator that does not exist yet.

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
    no_field, no_field_each = {}, {}
    for (job_id, field), human in sorted(agreed.items()):
        normalized = model_values.get(job_id)
        if normalized is None:
            missing.add(job_id)
            continue
        # MEMBERSHIP, NOT .get(). See the docstring: on `role_track` a present
        # null is a verdict and an absent key is silence, and .get() returns
        # None for both.
        if field not in normalized:
            no_field[field] = no_field.get(field, 0) + 1
            continue
        pair = (normalized[field], as_model_domain(field, human))
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
            # The abstention test comes FIRST and this one second, so a
            # labeller who could not tell is booked once, to the human, and
            # does not also count as a model gap. Inside the row loop rather
            # than hoisted out of it because `vs_each`'s denominator is
            # comparisons, not items -- five labellers on an unanswered field
            # are five lost comparisons.
            if field not in normalized:
                no_field_each[field] = no_field_each.get(field, 0) + 1
                continue
            per_field_each.setdefault(field, []).append(
                (normalized[field],
                 as_model_domain(field, row["value"])))

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
        # THREE EXCLUSIONS, THREE KEYS. `no_consensus` is a human
        # disagreement, `no_model_output` is a whole record the model never
        # produced, and these two are one FIELD it never produced. Different
        # faults with different fixes; see the docstring.
        #
        # Counts keyed by field, not ids, following this module's own
        # `abstained` and `single_labeller_items` blocks (inter_annotator()).
        # `no_model_output` keeps ids because a wholly absent record is a
        # specific row to go and look up; a field absent from a corpus is
        # absent from all of it, and the useful quantity is the n it cost.
        #
        # TWO OF THEM, BECAUSE THE TWO COLUMNS HAVE DIFFERENT DENOMINATORS.
        # `vs_consensus` counts items and `vs_each` counts comparisons, so one
        # shared counter would be a number belonging to neither -- the same
        # rule _stratum_block() states as "two denominators, two keys, never
        # one". `no_model_field` is the one that conditions the column in the
        # three-quantity table.
        "no_model_field": no_field,
        "no_model_field_each": no_field_each,
    }


# --------------------------------------------------------------------------
# The gate: three quantities or nothing
# --------------------------------------------------------------------------

class Uninterpretable(ValueError):
    """A model-vs-human figure with no floor or no ceiling beside it.

    Raised, never warned. CLAUDE.md: "Any measurement without that floor
    beside it is uninterpretable" -- and a warning is a thing people read
    once. Task 16 set the precedent that the tool refuses to print one
    denominator alone
    (`git show refactor-freeze-2026-08-02:docs/tasks/refactor/DECISIONS.md:174`);
    this is that rule for this table.
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
        # TWO CAUSES, AND THEY POINT AT OPPOSITE ENDS. A field can have no
        # measured cell because nobody has labelled it, or because the model
        # output being compared against does not carry the field at all --
        # `role_track` against pursuit-criteria-corpus.jsonl, where it is
        # absent from 859 of 859 rows. Naming only the first sends a reader to
        # look for volunteers when the labels are already in the table; the
        # count that distinguishes them is model_vs_human()'s
        # `no_model_field`.
        "measured": "Either no human labels for this field yet -- the tables "
                    "ship empty on purpose and task 29 fills them -- or the "
                    "model output carries no such field, in which case "
                    "model_vs_human()'s `no_model_field` counts how many "
                    "comparisons that cost.",
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


# --------------------------------------------------------------------------
# Axis B against the ordering the product actually ships
#
# WHAT THIS SECTION IS. Nothing above joins a human "would you apply" to the
# number that decides what a Builder sees. Every function up to here measures
# labels against labels, or a model against labels; `match_score` does not
# appear. That join is the entire evidence base for two decisions:
#
#   task 30's experiment, recorded at
# git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_six/30-within-track-ordering.md:32
#   -- "bucket the labelled postings by `match_score`" and ask whether a posting at 88 beats
#   one at 81 in Builder judgement more often than chance. Its whole claim
#   ladder rests on the answer.
#
#   any re-tuning of task 13's criteria weights, which currently have no
#   human evidence under them at all.
#
# IT IS PURE, FOR THE REASON confirm_scores() IS. score_job() is pure
# (match.py:73-84) so a below_floor score can be recomputed with no database
# and no LLM call; these functions take rows and return dicts for the same
# reason -- the figures that decide an ordering must be reproducible from a
# fixture on a laptop with no credentials, and unit-testable against synthetic
# labels before a single real one exists.
#
# AND IT MUST NOT BECOME A SWEEP. A `--json` dump of `ordering()`'s figures is
# exactly what a weight sweep would read, and pointing a sweep at this set
# would be fitting weights to L0 -- CLAUDE.md: "Never evaluate on the layer you
# trained on", and L0 is the layer with no other copy. The set is 200 postings
# and one labelling night; spent as a training signal it is gone, and every
# later precision figure quoted from it is a training-set figure. Read the
# figures, decide, and re-measure on a set drawn afterwards.
# --------------------------------------------------------------------------

#: Which column of a label-set row carries the score, per stratum. ONE PLACE
#: KNOWS THIS, and it is here rather than at each call site because the two
#: columns are the same quantity under two names and a caller that reached for
#: the wrong one would still produce a number.
#:
#: THEY ARE ON THE SAME SCALE, and that is an argument rather than an
#: assumption. `match_score` is what match.py stored (match.py:386, `if score
#: >= schema.MATCH_FLOOR`); `computed_score` is what confirm_scores() got back
#: from `match.score_job()` for the rows match.py stored nothing for. Same
#: function, same criteria, no I/O in between -- so `surfaced` 40-92 and
#: `below_floor` 0-34 are two windows on one 0-100 construction, which is what
#: makes ranking across the pair meaningful at all.
#:
#: NEVER `fit_score`, on either stratum. CLAUDE.md: "`match_score` orders the
#: list. `fit_score` only annotates it", and "LLMs explain, never rank".
#: `fit_score` is an LLM's output, so ranking by it would put an LLM call
#: between a user and an ordering -- and worse for a measurement, it is
#: CLAUDE.md's L1, the layer tools/learned-ranker-probe.py already fits
#: against. Scoring an L0 label against an L1 ordering would be evaluating on
#: the layer that was trained, one indirection out.
SCORE_COLUMN = {"surfaced": "match_score", "below_floor": "computed_score"}

#: The strata that can be ranked at all, in reporting order.
#:
#: `gate_rejected` IS DELIBERATELY ABSENT AND ITS ABSENCE IS ENFORCED, not
#: documented -- see _scored_strata(). Those 50 postings have neither column
#: (checked: 0 of 50 carry `match_score` and 0 of 50 carry `computed_score` in
#: labelset-pursuit-v1.jsonl), because the profile's gate rejected them before
#: match.py ever saw them. They have no position in any ordering, on any scale.
SCORED_STRATA = ("surfaced", "below_floor")


def _scored_strata(strata, caller):
    """Validate a `strata` argument, refusing `gate_rejected` by name.

    REFUSED, NOT FILTERED, and that is the whole point of this function
    existing instead of a set intersection. Silently dropping the stratum would
    let a caller ask for a precision figure "over the whole set" and get one
    computed over three quarters of it, labelled as if it were the whole -- a
    stratum measured against the wrong population, which is the defect
    trap 4.1
    (`git show refactor-freeze-2026-08-02:docs/MEASUREMENT-TRAPS.md`) is about
    and the one that has already cost this project a rewritten conclusion.

    The module's own precedent is model_vs_human(), which raises for axis B
    (labels.py:1554) rather than returning an empty block: when the question
    cannot be asked, say so at the call, not in a footnote.
    """
    out = tuple(strata)
    for stratum in out:
        if stratum == "gate_rejected":
            raise ValueError(
                f"{caller}: `gate_rejected` has no score to rank by. Neither "
                "match_score nor computed_score exists on those rows, because "
                "the profile's relevance gate rejected them before match.py "
                "ran, so they hold no position on any scale. They are also "
                "unreachable by that profile's users, so a `yes` on one is "
                "not a precision miss: nothing was ranked wrongly. Use "
                "recall_bound(), which reports them as k of N with an "
                "interval and never as a rate.")
        if stratum not in SCORE_COLUMN:
            raise ValueError(
                f"{caller}: {stratum!r} is not a stratum with a score column; "
                f"known: {sorted(SCORE_COLUMN)}")
    return out


def score_index(set_rows, scores=None, *, strata=SCORED_STRATA):
    """job_id -> the score that orders it, from the label-set rows themselves.

    The same shape and the same convention as platform_index()
    (labels.py:1269), including "an explicit map wins": save_set() writes both
    score columns into the set file (labels.py:770-772), so the normal case
    needs no second argument and no database read at all, and `scores` is for
    a caller holding fresher numbers -- a re-run of match.py, or a swept weight
    table -- who is being specific on purpose.

    NO DATABASE READ IS NEEDED AND THAT IS NOT AN OPTIMISATION. A score read
    live would be the score as of report time, and match.py re-ranks nightly.
    The stratum a row was sampled into is a property of the pipeline AT
    SAMPLING TIME -- the reason `stratum` is stored on eval_label_items rather
    than recomputed (see ensure_schema()) -- and a figure that pairs a
    sampling-time stratum with a report-time score is measuring two different
    days at once.

    Which column to read comes from SCORE_COLUMN, never from the caller. Rows
    in a stratum outside `strata` are skipped, which is how a caller reports
    the two strata separately; `gate_rejected` is refused rather than skipped,
    see _scored_strata().
    """
    strata = _scored_strata(strata, "score_index")
    index = {}
    for row in set_rows:
        stratum = row.get("stratum")
        if stratum not in strata:
            continue
        value = row.get(SCORE_COLUMN[stratum])
        if value is not None:
            index.setdefault(str(row["job_id"]), value)
    for job_id, value in (scores or {}).items():
        if value is not None:
            index[str(job_id)] = value
    return index


def _positive(value):
    """Axis B's answer as the positive class. `yes` is 1, `no` is 0.

    Raises on anything else rather than treating it as a negative. validate()
    already confines the column to AXIS_B_VALUES and None, and consensus()
    drops the Nones, so an unexpected value here means a row reached
    `eval_labels` without going through record() -- and quietly scoring it 0
    would move it into the negative class, making the ranker look worse or
    better with no trace of why.
    """
    if value not in AXIS_B_VALUES:
        raise ValueError(
            f"{value!r} is not one of {list(AXIS_B_VALUES)} for "
            f"{AXIS_B_FIELD}; every label must come through validate()")
    return 1 if value == "yes" else 0


def _axis_b_by_job(rows, profile, round_no):
    """job_id -> the axis-B values recorded for THIS profile at THIS round.

    Including the Nones, deliberately: this is the recount that tells an item
    every labeller abstained on apart from an item nobody opened, and
    consensus() cannot answer that -- see ordering().
    """
    per_job = {}
    for row in rows:
        if row.get("axis") != AXIS_B or row.get("field") != AXIS_B_FIELD:
            continue
        if row.get("profile") != profile or row.get("round_no") != round_no:
            continue
        per_job.setdefault(str(row["job_id"]), []).append(row["value"])
    return per_job


def _consensus_by_job(rows, profile, round_no):
    """(agreed, tied) from consensus(), narrowed to one profile, keyed by job.

    THE NARROWING IS DONE ON THE KEY, NOT BY PRE-FILTERING THE ROWS, and the
    difference is the point. _item_key() (labels.py:1329) puts the profile in
    every axis-B key, so another profile's answer about the same posting is
    already a DIFFERENT ITEM to consensus() -- it cannot be pooled in, and it
    cannot silently become a disagreement either. Pre-filtering would get the
    same `agreed` and lose that: a tie among `tech` labellers would vanish
    instead of being attributed to `tech`, and `match_score` is keyed
    (job_id, profile), so there is a separate figure for it to belong to.
    """
    agreed, tied = consensus(rows, axis=AXIS_B, round_no=round_no)
    mine = {str(k[0]): v for k, v in agreed.items()
            if len(k) == 3 and k[1] == AXIS_B_FIELD and k[2] == profile}
    mine_tied = {str(k[0]) for k in tied
                 if len(k) == 3 and k[1] == AXIS_B_FIELD and k[2] == profile}
    return mine, mine_tied


def _split_members(members, agreed, tied, per_job):
    """(pairs of (job_id, y), counts) for one stratum's set members.

    THREE EXCLUSIONS, NOT ONE, AND consensus() CONFLATES TWO OF THEM. That is a
    real defect in the function above rather than a subtlety of this one: an
    item every labeller abstained on reaches `if not counts: continue`
    (labels.py:1481) and disappears from BOTH of consensus()'s return values,
    landing in exactly the same silence as an item nobody ever opened. The
    module's stated rule is that an abstention is a value and is never folded
    away, and those two are different findings -- "five Builders read this
    posting and none could tell" is evidence about the POSTING, "nobody reached
    it" is evidence about the NIGHT.

    So this recounts from the rows and reports them apart:

        no_consensus    labellers disagreed with no majority -- consensus()
                        does surface these, in `tied`
        all_abstained   axis-B rows exist for the item at this round and every
                        one of them is NULL
        unlabelled      no axis-B row for this item, this profile, this round

    consensus()'s RETURN SHAPE IS NOT CHANGED. model_vs_human() and
    interpretable() are built on the two-value tuple and __main__ passes it
    around; widening it to carry a third bucket would be a change to every
    caller for the benefit of one. The recount is three lines here.

    THE ASYMMETRY WITH AXIS A IS DELIBERATE AND WORTH KNOWING.
    inter_annotator() DOES count abstentions (its `abstained` block,
    labels.py:1394) because axis A asks five questions per posting and a NULL
    on one of them is a fact about that FIELD -- "the posting does not say"
    about one of five things. Axis B asks one question, so an
    abstention there is a fact about the whole item, which is why it has to be
    counted per item here rather than per field there. Same rule, two shapes,
    because the two axes have different arity.
    """
    pairs, counts = [], {"no_consensus": 0, "all_abstained": 0,
                         "unlabelled": 0}
    for job_id in members:
        if job_id in agreed:
            pairs.append((job_id, _positive(agreed[job_id])))
        elif job_id in tied:
            counts["no_consensus"] += 1
        elif per_job.get(job_id):
            counts["all_abstained"] += 1
        else:
            counts["unlabelled"] += 1
    return pairs, counts


def _members(set_rows, stratum):
    """This stratum's job ids, deduplicated, in sorted order.

    Sorted because CLAUDE.md pins an eval set by sorted `job_id` and this is
    the same set; dict.fromkeys because a set file should not contain a job
    twice (eval_label_items' primary key forbids it) and if one does, counting
    it twice would move a denominator.
    """
    return sorted(dict.fromkeys(
        str(r["job_id"]) for r in set_rows if r.get("stratum") == stratum))


def _stratum_block(stratum, members, pairs, counts, index, k):
    """One stratum's figures. Never merged with another stratum's.

    THE COMPOSITION TRAVELS WITH THE FIGURE, in the same dict, because average
    precision's chance level IS the positive rate (metrics.py:396-399) and this
    set is stratified 100/50/50 BY DESIGN -- its prevalence is not the corpus's
    and cannot be read as one. A bare AP of 0.55 here is either strong or
    nothing at all depending on `positive_rate`, and the two must not be
    printable apart. `positive_rate` is what tools/mock-acceptance.py:686 calls
    `baseline`, in ranking_quality() (mock-acceptance.py:628), whose block this
    mirrors so the two are diffable.

    TWO DENOMINATORS, TWO KEYS, NEVER ONE.

        label_coverage   labelled / set members. How much of the night landed.
        coverage         Ranked.coverage(), scored / labelled. How often the
                         RANKER produced a number.

    Collapsing them would book a labelling shortfall as a pipeline failure,
    which is wrong in the flattering direction -- see ordering().

    TIES ARE NOT BROKEN. `average_precision` is metrics' default
    ties="expected", the mean over every tie-break and the only one of the
    three that is a property of the ranker rather than of the sort
    (metrics.TIE_MODES, metrics.py:282-300). `ap_optimistic` and
    `ap_pessimistic` bound what a real sort could have produced and `ties`
    carries metrics.tie_histogram() so a reader can see whether the point
    estimate is describing the ranking or the tie structure. `precision_at_k`
    averages ties the same way, which is why a fractional numerator and a
    value like 0.75 over 2 slots are correct rather than rounding errors
    (metrics.py:450-454). Nothing here breaks a tie by `job_id` or `position`:
    top_k_overlap() does, and its docstring (metrics.py:221-225) says why that
    is tolerable only there -- it needs a deterministic answer to compare TWO
    ORDERINGS of the same rows, and it is reported beside Spearman's rho rather
    than instead of it precisely because the break is arbitrary. Against a
    LABEL there is no second ordering and no rho beside it: the break would
    silently decide which postings the figure was computed over, and the figure
    would be the only number on the page.
    """
    scores = [index.get(job_id) for job_id, _y in pairs]
    ys = [y for _job_id, y in pairs]
    ap = metrics.average_precision(scores, ys)
    at_k = metrics.precision_at_k(scores, ys, k=k)
    return {
        "stratum": stratum,
        "score_column": SCORE_COLUMN[stratum],
        # Composition of the population, before any figure.
        "members": len(members),
        "labelled": len(pairs),
        "label_coverage": f"{len(pairs)}/{len(members)}",
        "no_consensus": counts["no_consensus"],
        "all_abstained": counts["all_abstained"],
        "unlabelled": counts["unlabelled"],
        # The ranker's own coverage, a separate denominator.
        "n": ap.n,
        "coverage": ap.coverage(),
        "complete": ap.complete,
        "n_unscored": ap.n_dropped,
        "n_unscored_positive": ap.n_dropped_positive,
        # The figures.
        "n_positive": ap.n_positive,
        "positive_rate": (ap.n_positive / ap.n) if ap.n else None,
        "average_precision": ap.value,
        "ap_optimistic": metrics.average_precision(
            scores, ys, ties="optimistic").value,
        "ap_pessimistic": metrics.average_precision(
            scores, ys, ties="pessimistic").value,
        # `k` and `k_requested` both, and the key name embeds neither, for the
        # reason mock-acceptance.py:695-697 gives: min(k, n) makes the two
        # differ on a small stratum and a key that renamed itself with k would
        # make two artifacts un-diffable.
        "k": at_k.k,
        "k_requested": k,
        "precision_at_k": at_k.value,
        "ties": metrics.tie_histogram(scores),
    }


def recall_bound(rows, set_rows, *, profile, round_no=1):
    """k of N gate-rejected postings a Builder said yes to. NOT A RATE.

    THE ONE STATEMENT THIS STRATUM CAN MAKE. `gate_rejected` rows were rejected
    by the profile's relevance gate before match.py ran, so they carry no
    `match_score` and no `computed_score` (0 of 50 in labelset-pursuit-v1) and
    hold no position in any ordering. Nothing about them can enter a precision
    figure, because precision asks "of what was shown, how much was good" and
    these were never shown -- the profile's users cannot reach them. A `yes`
    here is not a posting ranked too high; it is a posting the gate threw away,
    which is a RECALL fact and the only reason this stratum was sampled (see
    STRATA).

    Mixing them into a precision denominator would be a fresh instance of the
    defect this project has already paid for -- a stratum measured against the
    wrong population, trap 4.1. CLAUDE.md cited these traps as
    `git show refactor-freeze-2026-08-02:docs/MEASUREMENT-TRAPS.md`; that file
    existed but was deleted 2026-08-02 with the rest of docs/, and it is where
    the 4.1-4.7 numbering every citation in this package uses comes from.

    RETURNED AS A COUNT AND AN INTERVAL, WITH NO `rate` KEY. metrics.wilson()
    over k of n bounds the proportion, so 2 of 50 reads "[0.6%, 8.5%] of what
    the gate discards, a Builder would have applied to" -- a bound on what is
    being missed. There is deliberately no `rate` and no `average_precision`
    key for a report to reach for by mistake, and `statement` renders the
    sentence once so no caller has to decide how to phrase it (the same reason
    Ranked.coverage() is a string, metrics.py:349-355).

    `n` IS THE NUMBER WITH A CONSENSUS ANSWER, NOT THE STRATUM SIZE. Those are
    the same 50 when the night finishes the stratum, and when it does not, the
    interval has to be over the postings someone actually answered about --
    `members` and `label_coverage` carry the shortfall beside it rather than
    hiding it in the denominator. The three exclusions are broken out here for
    the same reason as in the ranked strata, see _split_members().
    """
    members = _members(set_rows, "gate_rejected")
    agreed, tied = _consensus_by_job(rows, profile, round_no)
    per_job = _axis_b_by_job(rows, profile, round_no)
    pairs, counts = _split_members(members, agreed, tied, per_job)

    n = len(pairs)
    k = sum(y for _job_id, y in pairs)
    lo, hi = metrics.wilson(k, n)
    return {
        "stratum": "gate_rejected",
        "quantity": "recall_bound",
        "k": k,
        "n": n,
        "members": len(members),
        "label_coverage": f"{n}/{len(members)}",
        "ci": (lo, hi),
        "no_consensus": counts["no_consensus"],
        "all_abstained": counts["all_abstained"],
        "unlabelled": counts["unlabelled"],
        "statement": (
            f"{k} of {n} gate-rejected postings a Builder said yes to "
            f"[{lo:.1%}-{hi:.1%}] -- a bound on what the gate discards, "
            f"never a precision rate"),
    }


def ordering(rows, set_rows, *, profile, strata=SCORED_STRATA, scores=None,
             round_no=1, k=metrics.TOP_K):
    """Does `match_score` put the postings a Builder would apply to first?

    THE ADAPTER between axis B and the number that orders the product. `rows`
    are label rows in fetch()'s shape; `set_rows` are the label set's own rows
    in save_set()'s shape, which already carry `stratum` and both score columns
    -- so this needs no database, no LLM and no credentials, and is testable
    against synthetic labels before a real one exists. Same discipline as
    score_job() being pure (match.py:73-84).

    `profile` IS REQUIRED AND HAS NO DEFAULT. `match_score` is keyed
    (job_id, profile) -- CLAUDE.md's flat-cost property -- and _item_key()
    (labels.py:1329) puts the profile in every axis-B key for the same reason.
    A default would silently pool two personas' answers about one posting
    against one score, which is not a disagreement and not a second trial; it
    is two different questions. inter_annotator() already refuses to pool them
    (see test_axis_b_agreement_is_keyed_by_profile_not_pooled_across_them) and
    so does this.

    EVERY FIGURE IS PER STRATUM AND THE TWO ARE NEVER AVERAGED. `surfaced` is
    a 100-row draw from what the pipeline shows and `below_floor` a 50-row draw
    from what it hides; the set is stratified 100/50/50 by design, so neither
    prevalence is the corpus's and their mean is a figure about no population
    at all. `strata` chooses which are reported and `gate_rejected` is REFUSED
    rather than filtered (_scored_strata()); it appears instead under
    `recall_bound`, as a count with an interval, always computed and never
    folded into a precision denominator.

    UNLABELLED ITEMS ARE NOT FED IN AS score=None. `Ranked.n_dropped` means the
    RANKER produced no number (metrics.py:331, and the argument at
    metrics.py:306-321), and every drop there is read as a pipeline failure
    that flatters the ranker. Booking a labelling shortfall into it would
    inherit that reading while being false: the score exists, the label does
    not. So `pairs` contains only items with a consensus answer, and label
    coverage is its own number beside `Ranked.coverage()` -- two denominators,
    two keys, never one. A None reaching `n_unscored` therefore means what it
    says: a set member somebody labelled that the ranker could not score.

    HUMAN TIES ARE NOT BROKEN EITHER. consensus() refuses to invent a majority
    out of a disagreement (labels.py:1466-1471) and the count is surfaced under
    `no_consensus`, the same key name model_vs_human() uses (labels.py:1608),
    so the two tables' columns line up. Score ties are not broken either; see
    _stratum_block().

    `labelled_not_in_set` IS NOT A DIAGNOSTIC. It counts axis-B answers for
    this profile about postings the set does not contain -- a label from an
    older set, or a set file that is not the one the labels were collected
    against. Silence is this system's failure mode (CLAUDE.md), and a digest
    mismatch is exactly the case where every figure above is computed over the
    wrong 200 rows; compare digest(set_rows) against eval_label_sets.

    WHAT NOT TO DO WITH THE RESULT: see this section's header comment. A
    `--json` dump of these figures is what a weight sweep would read, and
    sweeping on this set is training on L0.
    """
    strata = _scored_strata(strata, "ordering")
    index = score_index(set_rows, scores, strata=strata)
    agreed, tied = _consensus_by_job(rows, profile, round_no)
    per_job = _axis_b_by_job(rows, profile, round_no)

    blocks, totals = {}, {"no_consensus": 0, "all_abstained": 0,
                          "unlabelled": 0}
    reported = set()
    for stratum in strata:
        members = _members(set_rows, stratum)
        pairs, counts = _split_members(members, agreed, tied, per_job)
        reported.update(members)
        for name in totals:
            totals[name] += counts[name]
        blocks[stratum] = _stratum_block(stratum, members, pairs, counts,
                                         index, k)

    in_set = {str(r["job_id"]) for r in set_rows}
    return {
        "axis": AXIS_B,
        "field": AXIS_B_FIELD,
        "profile": profile,
        "round": round_no,
        "strata": blocks,
        # Always computed, never merged into `strata`.
        "recall_bound": recall_bound(rows, set_rows, profile=profile,
                                     round_no=round_no),
        # Summed over the REPORTED strata only -- `recall_bound` carries its
        # own three, over a population these figures say nothing about.
        "no_consensus": totals["no_consensus"],
        "all_abstained": totals["all_abstained"],
        "unlabelled": totals["unlabelled"],
        "labelled_not_in_set": len(set(agreed) - in_set),
    }
