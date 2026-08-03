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
    (`git show refactor-freeze-2026-08-02:docs/ingestion_tests/04-score-validation.md:8-37`).

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
    (score.PERSONA_PROMPT_KEYS) -- and nothing else about the user reaches
    any prompt in this pipeline. Pin those five and the input is fully
    determined.

    persona_sha() is that pin. A persona edit changes the prompt for every
    record, so it invalidates a comparison exactly the way a model swap does.
    It started here, because the harness needed it first and job_scores had no
    version column at all; it now lives in score.py beside build_prompt, which
    defines its field set, and job_scores records it on every row
    (schema.py's persona_sha column). This module re-exports it -- the
    pipeline must not import from the eval harness, and the name is part of
    this module's surface.
"""

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


#: Re-exported, not redefined. The digest is a cache key on every job_scores
#: row now, so two implementations of it would be two answers to "is this
#: narrative stale" -- and the one the pipeline uses cannot live here, because
#: score.py must not import the eval harness.
persona_sha = score_stage.persona_sha


def _job_from_record(record):
    """A fixture record as select_shortlist() would have returned it.

    The facts block is what build_prompt() sends -- not the description --
    so the job columns and the job_facts columns both have to be present and
    flat. corpus.py captures both in one record for exactly this reason
    (corpus.py:17-22).
    """
    job = corpus.job_fields(record)
    # facts, not prose -- see score.py's THE PROMPT READS FACTS section.
    job.pop("description_text", None)
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
        # without a profile row.
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

        Mirrors _score_one_job()'s decision tree (score.py) without its
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

        select_shortlist() inner-joins job_facts (score._SHORTLIST_FROM),
        so a posting that has never been extracted is one the score stage
        cannot see. It is
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
