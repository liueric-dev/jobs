"""The score stage, as an evaluatable task.

Delegates to score.py for everything that decides an answer: the prompt, the
track vocabulary, and normalize()'s coercion. What this file adds is the seam
-- turning a fixture record into the (persona, job) pair build_prompt() wants,
and a raw response into the exact dict job_scores would have stored.

WHAT THIS CAN MEASURE, AND WHAT IT CANNOT
    Shape, not accuracy. Extraction's fields are closed vocabularies over
    facts a posting either states or does not, so a human label settles a
    disagreement. There is no fact of the matter about whether 72 is the right
    fit_score, and a labeller asked to produce one is inventing a number
    rather than recording an observation
    (docs/ingestion_tests/04-score-validation.md:8-37).

    Under the Pursuit scope it is weaker still: ~30 Builders at different
    stages with no single target role means fit_score accuracy is not merely
    hard to establish, it is not well defined. So the metric here is
    SELF-CONSISTENCY -- two runs of the same persona over the same corpus
    should rank the same postings the same way. A model that cannot reproduce
    its own ordering is disqualified without anyone having to agree on what
    the right ordering was.

THE PERSONA IS THE FIXTURE CONTRACT
    build_prompt() reads exactly five persona keys -- background_summary,
    strengths[], honest_gaps[], buckets{} and scoring_instructions
    (score.py:310-372) -- and nothing else about the user reaches any prompt
    in this pipeline. Pin those five and the input is fully determined.

    persona_sha() is that pin. A persona edit changes the prompt for every
    record, so it invalidates a comparison exactly the way a model swap does,
    and job_scores has no persona_version column to notice
    (schema.py:328-343 -- no version column at all; see
    docs/score-validation.md). Recording the digest beside a run is the only
    thing standing between "the numbers moved" and an unanswerable question.
"""

import hashlib
import json

import llm
import score as score_stage

from .. import corpus


#: Which comparison rule each field gets. metrics.py reads this.
#:
#: fit_score is "score", not "int". They compare identically in the three
#: headline agreement columns -- deliberately, so every column in the table
#: means the same thing -- but "score" additionally carries tolerance bands,
#: a tie histogram and rank correlation, which are the quantities that
#: actually matter for a number whose only job is to annotate an ordering
#: match.py already produced.
FIELD_KINDS = {
    "fit_score": "score",
    "primary_track": "enum",
    "gap_friendly_signal": "bool",
    "key_technologies": "set",
    "gap_bridging_angle": "prose",
    "risk_factors": "prose",
}

#: The two a person would actually notice. primary_track is what task 30
#: proposes to display INSTEAD of a number, which makes its stability the
#: measurement that decides that design; fit_score is the number itself.
PRIORITY_FIELDS = ("primary_track", "fit_score")


def persona_sha(persona):
    """Digest of the five keys build_prompt() reads. Nothing else.

    Deliberately not a digest of the whole persona blob: `_comment`,
    `display_name` and `profile` do not reach a prompt, and a digest that
    changed when someone fixed a typo in a comment would train people to
    ignore it.
    """
    material = {k: persona.get(k) for k in
                ("background_summary", "strengths", "honest_gaps", "buckets",
                 "scoring_instructions")}
    blob = json.dumps(material, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _job_from_record(record):
    """A fixture record as select_shortlist() would have returned it.

    The facts block is what build_prompt() sends -- not the description --
    so the job columns and the job_facts columns both have to be present and
    flat. corpus.py captures both in one record for exactly this reason
    (corpus.py:17-22).
    """
    job = corpus.job_fields(record)
    job.pop("description_text", None)   # facts, not prose: score.py:29-35
    job.update(corpus.facts_fields(record) or {})
    return job


class ScoreTask:
    name = "score"
    required_fields = score_stage.REQUIRED_FIELDS
    field_kinds = FIELD_KINDS
    priority_fields = PRIORITY_FIELDS
    #: metrics.selfcheck() reports ranking stability for this field. Declared
    #: here rather than detected from the name so a task without an ordering
    #: quantity simply omits it.
    rank_field = "fit_score"

    def __init__(self, persona=None):
        # Loaded from disk, not from the database: the harness runs with no
        # DATABASE_URL after a corpus snapshot (corpus.py:20-22), and
        # score.load_persona() exists precisely so a prompt can be measured
        # without a profile row (score.py:222-232).
        self._persona = persona

    @property
    def persona(self):
        if self._persona is None:
            self._persona = score_stage.load_persona()
        return self._persona

    @property
    def persona_sha(self):
        return persona_sha(self.persona)

    def build_prompt(self, record):
        return score_stage.build_prompt(self.persona, _job_from_record(record))

    def parse(self, raw_text):
        """Raw response -> (normalized dict or None, reason).

        Mirrors _score_one_job()'s decision tree (score.py:657) without its
        database writes, so a fixture run classifies a response exactly as the
        pipeline would: unparseable JSON and a response with nothing usable in
        it both become a tombstone, and the reason distinguishes them.
        """
        parsed = llm.parse_json(raw_text)
        if parsed is None:
            return None, "unparseable_json"
        normalized = score_stage.normalize(parsed)
        if normalized is None:
            return None, "no_usable_fields"
        return normalized, None

    def eligible(self, record):
        """Whether the pipeline would ever send this record.

        select_shortlist() inner-joins job_facts (score.py:259), so a posting
        that has never been extracted is one the score stage cannot see. It is
        reported as skipped rather than counted against the model, the same
        rule tasks/extract.py applies to a row with no description.

        The pipeline additionally requires a job_matches row above the floor.
        That is NOT checked here: it is a property of a profile's criteria at
        one moment, not of the posting, and applying it would make the corpus
        change under a criteria edit -- which is the exact instability frozen
        fixtures exist to remove.
        """
        return bool(corpus.facts_fields(record))


TASK = ScoreTask()
