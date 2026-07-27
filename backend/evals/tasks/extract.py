"""The extract stage, as an evaluatable task.

Delegates to extract.py for everything that decides an answer: the prompt
prefix, the enum vocabularies, and normalize()'s coercion. What this file
adds is only the seam -- turning a fixture record into a prompt and a raw
response into the exact dict job_facts would have stored.

That last part matters for measurement. Comparing a model's raw JSON against
a label would score it on formatting: "Mid-Level" and "mid" are the same
answer, and extract._enum() already knows it. Comparing AFTER normalize()
scores what would actually be written to the database, which is the only
thing anyone cares about.
"""

import extract as extract_stage
import llm

from .. import corpus


#: Which comparison rule each field gets. metrics.py reads this; keeping it
#: beside the field list is what stops the two drifting apart.
FIELD_KINDS = {
    "seniority_level": "enum",
    "role_archetype": "enum",
    "ai_involvement": "enum",
    "remote_policy": "enum",
    "employment_type": "enum",
    "visa_sponsorship": "enum",
    "comp_currency": "enum",
    "ml_research_required": "bool",
    "advanced_degree_required": "bool",
    "customer_facing": "bool",
    "gap_friendly_language": "bool",
    "years_experience_min": "int",
    "years_experience_max": "int",
    "comp_min": "int",
    "comp_max": "int",
    "tech_stack": "set",
    "summary": "prose",
}

#: The subset worth a human's time to label first. These are the fields
#: match.py actually scores on, so an error in one of them changes what a
#: person is shown; an error in comp_currency does not. See the labelling
#: budget note in the plan -- 30 jobs x 17 fields is a lot of human hours,
#: and metrics.py scores only what is labelled, so this can grow later.
PRIORITY_FIELDS = ("seniority_level", "role_archetype", "remote_policy",
                   "ai_involvement", "tech_stack")


class ExtractTask:
    name = "extract"
    required_fields = extract_stage.REQUIRED_FIELDS
    field_kinds = FIELD_KINDS
    priority_fields = PRIORITY_FIELDS

    def build_prompt(self, record):
        return extract_stage.build_prompt(corpus.job_fields(record))

    def parse(self, raw_text):
        """Raw response -> (normalized dict or None, reason).

        Mirrors extract_one_job()'s decision tree (extract.py:368) without its
        database writes, so a fixture run classifies a response exactly as the
        pipeline would: unparseable JSON and unusable content both become a
        tombstone, and the reason distinguishes them for the report.
        """
        parsed = llm.parse_json(raw_text)
        if parsed is None:
            return None, "unparseable_json"
        normalized = extract_stage.normalize(parsed)
        if normalized is None:
            return None, "no_usable_fields"
        return normalized, None

    def eligible(self, record):
        """Whether the pipeline would ever send this record.

        extract.select_unextracted_jobs() requires a non-empty description
        (extract.py:180). Fixture corpora deliberately include rows that fail
        this so the harness can report on them, but they are not counted as
        model failures -- the model was never asked.
        """
        return bool((record.get("description_text") or "").strip())


TASK = ExtractTask()
