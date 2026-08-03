"""The 55 synthetic postings and their answer key, loaded and validated.

THIS IS A SPECIFICATION FIXTURE, NOT A LABEL. Nothing in this module may ever
reach `eval_labels`: an answer key written from a specification tests the
specification, and recording it as a label would let a fixture's assumptions be
read back later as evidence about a model. `git show refactor-freeze-2026-08-02:docs/tasks/refactor/HANDOFF.md:805-808` states the rule
this module is bound by -- "Fixtures written from a specification test the
specification. All three failure modes task 18 found live were invisible to the
four constructed fixtures, because those encode the shapes the task file
*describes*." The same caveat applies here in full: these postings were written
to exercise five named failure modes, so a model that scores well on them has
demonstrated that it handles the five modes somebody thought of. That is worth
measuring and is not the same claim as "it handles real postings", and the two
must not be conflated in anything this module feeds.

    from evals import mock_corpus as mc
    postings = mc.load_postings()          # 55, order preserved
    key      = mc.load_key()               # {job_id: entry}, cross-validated
    rows     = mc.records()                # jobs-table records, ready to upsert

WHAT IS HERE AND WHAT IS NOT
    Everything in this module is pure: it reads two files off disk, validates
    them against the real vocabularies in extract.py and the real column tuple
    in schema.py, and maps postings to `jobs` records. It spends no LLM calls,
    opens no socket and writes to no database -- tests/test_labels.py:423 greps
    every module in this package for exactly that and this one lives here.
    Driving the pipeline over these records, which does cost calls, belongs to
    the caller.

    Precedent for synthesised fixtures living in `evals/`:
    evals/workday_fixtures.py, which is equally explicit about being
    constructed rather than recorded.

WHY THE MOCK ROWS CANNOT REACH THE WEBAPP
    `job_url` is the empty string on every mapped record, deliberately. The
    jobs_app view's WHERE requires `coalesce(j.job_url,'') <> ''`
    (schema.py:711), so a mock row that somehow leaked into a real schema still
    cannot surface to a user. That is a containment property, not an oversight
    -- see to_job_record().

TWO KINDS OF EXPECTED ANSWER, AND THEY MUST NOT BE ADDED TOGETHER
    An entry's `fields` block holds extraction targets -- things a model
    produces and can therefore be right or wrong about. Its `loader_fields`
    block holds `jobs` columns that THIS MODULE produces: `location_is_nyc`
    and `location_is_remote`. They look alike downstream because
    match.py:275-288 selects both kinds into one flat row, twelve columns from
    `job_facts` and two from `jobs`.

    Folding them into one accuracy figure would credit a model with 110
    agreements it was never asked for. So extraction_fields() and
    loader_fields() return disjoint sets, expected() REFUSES a loader field
    rather than answering None, and the loader block is consumed by
    loader_disagreements(), which runs the check backwards: the key as a second
    reader, this module's mapping as the thing under test.

WHY THE MOCK'S OWN FACTS ARE STRIPPED FROM THE RECORD
    The postings file carries `remote_policy` and four `comp_*` keys. Those are
    job_facts columns (schema.py:420-424) -- they are things extract.py is
    supposed to PRODUCE. `upsert()` ignores keys that are not columns (pinned
    by tests/test_nyc_open_data.py:490-505), so passing them through would be
    harmless to the write and corrosive to the measurement: any later code that
    read them off the input row would be reading the answer out of the input.
    They are stripped here and belong to the answer key instead.
"""

import hashlib
import json
import os

import extract
import schema
from lib import text

#: Not one of the seven real platforms. No whitelist exists to violate:
#: `jobs.platform` is a bare `TEXT NOT NULL` (schema.py:335) and the only
#: platform tuple in the codebase is ats_sources.HANDLED_PLATFORMS
#: (ingest/ats_sources.py:76), which gates which ATS feeds get fetched and is
#: never consulted on a write. Verified by grep, and pinned by
#: tests/test_mock_corpus.py.
PLATFORM = "mock"

#: Moved out of `docs/tasks/refactor/mock/` on 2026-08-02 when `docs/` was
#: deleted. These three files are fixtures, not documentation -- the corpus, its
#: independently-written answer key and the addendum this module parses -- so
#: they now live beside the code that reads them. History: `git log --follow`.
_MOCK_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "fixtures", "mock")

POSTINGS_PATH = os.path.join(_MOCK_DIR, "mock-postings-v3.json")
KEY_PATH = os.path.join(_MOCK_DIR, "mock-postings-v3-answer-key.json")
ADDENDUM_PATH = os.path.join(
    _MOCK_DIR, "mock-postings-v3-answer-key-addendum.md")

#: The corpus is frozen at this size. Checked only when loading POSTINGS_PATH
#: itself -- a caller passing an explicit path is building a smaller fixture
#: and is not asserting anything about the frozen corpus.
EXPECTED_N = 55

#: Keys every posting must carry. `source` and `generated_by` are provenance
#: (which model wrote the posting) and are validated but not mapped.
POSTING_KEYS = ("job_id", "title", "company_name", "location", "remote_policy",
                "source", "generated_by", "posted_at", "description_text",
                "comp_min", "comp_max", "comp_currency", "comp_period",
                "comp_is_estimated")

#: The three that must be non-empty for the posting to be worth running: an
#: empty description is not a hard case, it is a missing case.
POSTING_REQUIRED_NONEMPTY = ("job_id", "title", "company_name",
                             "description_text")

VERDICTS = ("good", "bad", "undecided")

#: The closed failure-mode vocabulary. `mock_048` and `mock_053` each carry
#: two, which is the point of the list being a list -- the addendum
#: (mock-postings-v3-answer-key-addendum.md:43) calls out the compound case
#: explicitly, since real postings do not usually fail for one tidy reason.
FAILURE_MODES = ("clean_reject", "seniority", "branding_trap",
                 "not_a_real_employer", "technical_bar",
                 "out_of_scope_location")

#: Answer-key `fields` entries are checked against extract.py's own tuples, by
#: reference rather than by copy: a vocabulary that grows there (ARCHETYPE went
#: from 12 values to 26 in FACTS_VERSION 3) must not leave a stale duplicate
#: here quietly rejecting valid answers.
CLOSED_VOCABULARIES = {
    "seniority_level": extract.SENIORITY,
    "role_archetype": extract.ARCHETYPE,
    "role_track": extract.ROLE_TRACK,
    "ai_involvement": extract.AI_INVOLVEMENT,
    "remote_policy": extract.REMOTE_POLICY,
    "employment_type": extract.EMPLOYMENT_TYPE,
    "visa_sponsorship": extract.VISA,
}

#: Every job_facts column an answer-key entry may name in `fields`, from the
#: DDL at schema.py:407-430. `facts_version`, `extracted_at` and
#: `extraction_model` are bookkeeping the pipeline writes and no key can have
#: an opinion about.
#:
#: THESE ARE THE ONLY THINGS A MODEL IS SCORED ON. See LOADER_FIELDS below for
#: the other half of the story, and why the two halves must never merge.
FACT_FIELDS = (
    "seniority_level", "years_experience_min", "years_experience_max",
    "role_archetype", "role_track", "tech_stack", "ai_involvement",
    "ml_research_required", "advanced_degree_required", "customer_facing",
    "remote_policy", "employment_type", "comp_min", "comp_max",
    "comp_currency", "gap_friendly_language", "visa_sponsorship", "summary",
)

#: What may appear in an entry's `loader_fields` block: any writable `jobs`
#: column (schema.COLUMNS, schema.py:121-128).
#:
#: WHY THIS BLOCK IS SEPARATE FROM `fields`, AND MUST STAY SEPARATE
#:     match.py:275-288 (`_SELECT_FACTS`) selects twelve columns from
#:     `job_facts` and TWO from `jobs`: `j.location_is_nyc` and
#:     `j.location_is_remote`. Those two reach score_job the same way every
#:     extracted fact does, so they look interchangeable at the point of use
#:     and are not: no model ever produces them. `_location_flags()` in this
#:     module produces them, from the posting's location string.
#:
#:     So an answer-key entry for `location_is_nyc` is not an expected model
#:     answer -- it is a second reading of the same string this module already
#:     read. Scoring a model against it would compare this module's mapping to
#:     whoever wrote the key, and every agreement would land in the numerator
#:     of a figure captioned "extraction accuracy". On this corpus that is 110
#:     free agreements across 55 postings, which is enough to move any headline
#:     it was folded into.
#:
#:     Kept rather than deleted because it is a genuinely useful check running
#:     the other way -- see loader_disagreements(). If `_location_flags()` is
#:     wrong, score_job's location penalties are wrong for every row and
#:     nothing else in this repo would notice.
LOADER_FIELDS = tuple(schema.COLUMNS)

#: Top-level answer-key keys. `_not_a_label` is the one that carries this
#: module's docstring as data, so a reader of the JSON alone still gets the
#: warning. `_field_provenance` is accepted when present and is documentation
#: of the FACT_FIELDS/LOADER_FIELDS split for a reader of the JSON alone; it is
#: not required, because this module enforces the split structurally and a
#: prose block cannot be the thing that enforces it.
KEY_TOP_LEVEL = ("_comment", "_method", "_not_a_label", "_generated",
                 "postings_file", "postings_sha256", "n", "entries")
KEY_TOP_LEVEL_OPTIONAL = ("_field_provenance",)

#: Where a quote may be looked up. Both the posting's own key and the mapped
#: record's name for it resolve, because the key is written against the
#: postings file while everything downstream sees `location_raw`.
_QUOTE_FIELD_ALIASES = {"location_raw": "location"}

DEFAULT_QUOTE_FIELD = "description_text"


class MockCorpusError(ValueError):
    """Raised for any structural defect in either file.

    A single exception type, and never a warning: an answer key that silently
    skipped its unparseable entries would report a precision computed over
    whatever happened to parse, which is the flattering denominator this whole
    fixture exists to avoid.
    """


# ---------------------------------------------------------------------------
# Postings
# ---------------------------------------------------------------------------

def load_postings(path=None):
    """The synthetic postings, validated, in file order.

    Order is preserved rather than sorted by job_id because the file's order
    is its narrative order -- 001-040 from the first batch, 041-055 from the
    second, which is how the addendum reads. Nothing downstream may depend on
    it; anything that needs a stable key uses job_id.
    """
    resolved = path or POSTINGS_PATH
    postings = _read_json(resolved)
    if not isinstance(postings, list):
        raise MockCorpusError(
            f"{resolved}: expected a JSON array of postings, got "
            f"{type(postings).__name__}")

    seen = set()
    for i, posting in enumerate(postings):
        where = f"{resolved}[{i}]"
        if not isinstance(posting, dict):
            raise MockCorpusError(f"{where}: expected an object, got "
                                  f"{type(posting).__name__}")
        missing = [k for k in POSTING_KEYS if k not in posting]
        if missing:
            raise MockCorpusError(f"{where}: missing key(s) {missing}")
        for k in POSTING_REQUIRED_NONEMPTY:
            if not str(posting[k] or "").strip():
                raise MockCorpusError(f"{where}: {k} is empty")
        if posting["source"] != PLATFORM:
            raise MockCorpusError(
                f"{where}: source is {posting['source']!r}, expected "
                f"{PLATFORM!r} -- a posting from a real source does not "
                f"belong in a fixture that claims to be synthetic")
        if posting["job_id"] in seen:
            raise MockCorpusError(
                f"{where}: duplicate job_id {posting['job_id']!r}. Two "
                f"postings sharing a source_id collapse to one row under "
                f"schema.make_job_id and the corpus silently shrinks")
        seen.add(posting["job_id"])

    if path is None and len(postings) != EXPECTED_N:
        raise MockCorpusError(
            f"{resolved}: {len(postings)} postings, expected {EXPECTED_N}. "
            f"The corpus is frozen; a new size is a new corpus and needs a "
            f"new answer key, not an edited constant")
    return postings


def to_job_record(posting):
    """One posting as a `jobs` record: every key in schema.COLUMNS, no others.

    Every key is present because upsert binds COLUMNS as named parameters, so
    an omission fails that record inside its SAVEPOINT rather than raising --
    one line of a summary nobody reads (schema.py:118-120).
    """
    location = posting["location"]
    is_nyc, is_remote = _location_flags(location, posting.get("remote_policy"))
    return {
        "platform": PLATFORM,
        "company_token": text.slugify(posting["company_name"]),
        "company_name": posting["company_name"],
        # The mock id, not the row id. schema.make_job_id hashes this into the
        # 24-char primary key; `mock_001` is never itself a key.
        "source_id": posting["job_id"],
        "title": posting["title"],
        "location_raw": location,
        "department": None,
        # DELIBERATELY EMPTY, and load-bearing. jobs_app's WHERE requires
        # `coalesce(j.job_url,'') <> ''` (schema.py:711), so a mock row can
        # never surface in the webapp even if one leaked into a real schema.
        # It is also in HASH_FIELDS_SHORT, where a constant contributes
        # nothing to the digest and therefore costs nothing to pin.
        "job_url": "",
        "posted_at": posting["posted_at"],
        "posted_at_ts": text.posted_at_timestamp(posting["posted_at"]),
        "salary_text": None,
        "seniority_guess": text.guess_seniority(posting["title"]),
        # NEVER None. A NULL location boolean reads as FALSE through
        # relevance.py's COALESCE (relevance.py:292-295), which drops the row
        # to tier 2 -- so the whole corpus would measure the tier-2 path and
        # the tier-1 gate would go unexercised while still reporting a number.
        "location_is_nyc": is_nyc,
        "location_is_remote": is_remote,
        # No company-level enrichment exists for a fictional employer, and
        # inventing one would price these rows on a fact nothing observed.
        "company_is_nyc_hq": None,
        "company_is_ai_focused": None,
        "description_text": posting["description_text"],
        "raw_json": None,
    }


def records(postings=None):
    """to_job_record over the whole corpus."""
    return [to_job_record(p) for p in (postings
                                       if postings is not None
                                       else load_postings())]


def job_id_for(posting):
    """The `jobs.id` this posting will get: sha256("mock:<token>:mock_001")[:24].

    Not `mock_001`. schema.make_job_id (schema.py:302) is the only thing that
    mints a row id, and a caller that assumes the raw mock id is the key will
    join against nothing.
    """
    return schema.make_job_id(to_job_record(posting))


def spec():
    """The TableSpec these rows upsert through.

    HASH_FIELDS_SHORT rather than HASH_FIELDS_ATS: the mock postings carry no
    `department`, so hashing it would hash a constant None for all 55.
    """
    return schema.spec(schema.HASH_FIELDS_SHORT)


def _location_flags(location, remote_policy):
    """(is_nyc, is_remote), from the real heuristic plus the stated policy.

    lib.text.classify_location (lib/text.py:137) is used unmodified and its
    misses are kept. NYC_PATTERN (lib/text.py:25) lists seven names, so
    "Long Island City, NY", "Astoria, NY" and "Yonkers, NY" all classify as
    NOT NYC. That is wrong about the world and right about the pipeline: these
    rows exist to measure the gate that production actually runs, and
    hand-correcting them here would report a gate nobody has.

    `remote_policy` is the posting's own stated policy and only ever ADDS
    is_remote -- a "Remote" location string already sets it, and "hybrid" is
    not remote.
    """
    is_nyc, is_remote = text.classify_location(location)
    return is_nyc, bool(is_remote or str(remote_policy or "").startswith("remote"))


# ---------------------------------------------------------------------------
# Answer key
# ---------------------------------------------------------------------------

def load_key(path=None, postings=None):
    """The answer key as {job_id: entry}, cross-validated against the postings.

    Raises rather than warns or skips, on all five of:
      * an entry naming a job_id that no posting has;
      * a posting with no entry -- a partial key computes precision over a
        subset chosen by whoever ran out of time;
      * a value outside the closed vocabulary extract.py would produce;
      * a non-null quote that is not a literal substring of the field it names;
      * a `fields` name that is not a job_facts column.

    `postings` is an escape hatch for tests that pair a temporary key with a
    temporary postings file; production callers pass neither argument.
    """
    resolved = path or KEY_PATH
    key = _read_json(resolved)
    if not isinstance(key, dict):
        raise MockCorpusError(
            f"{resolved}: expected a JSON object, got {type(key).__name__}")
    missing = [k for k in KEY_TOP_LEVEL if k not in key]
    if missing:
        raise MockCorpusError(f"{resolved}: missing top-level key(s) {missing}")
    # Prose or a per-field map, both accepted: it is documentation of the
    # fields/loader_fields split for a reader who has only the JSON. The split
    # itself is enforced structurally below -- a comment block must never be
    # the thing enforcing it.
    provenance = key.get("_field_provenance")
    if provenance is not None and not isinstance(provenance, (str, dict)):
        raise MockCorpusError(
            f"{resolved}: _field_provenance must be a string or an object, "
            f"got {type(provenance).__name__}")

    if postings is None:
        postings = load_postings() if path is None else load_postings(
            os.path.join(os.path.dirname(resolved),
                         os.path.basename(key["postings_file"])))
    by_id = {p["job_id"]: p for p in postings}

    entries = key["entries"]
    if not isinstance(entries, dict):
        raise MockCorpusError(f"{resolved}: `entries` must be an object keyed "
                              f"by job_id, got {type(entries).__name__}")

    unknown = sorted(set(entries) - set(by_id))
    if unknown:
        raise MockCorpusError(
            f"{resolved}: entries for job_id(s) no posting has: {unknown}")
    unanswered = sorted(set(by_id) - set(entries))
    if unanswered:
        raise MockCorpusError(
            f"{resolved}: {len(unanswered)} posting(s) have no entry: "
            f"{unanswered}. A key that covers part of the corpus measures "
            f"whichever part somebody got to")

    if key["n"] != len(entries):
        raise MockCorpusError(
            f"{resolved}: declares n={key['n']} but carries {len(entries)} "
            f"entries")

    for job_id in sorted(entries):
        _validate_entry(resolved, job_id, entries[job_id], by_id[job_id])

    # A `loader_fields` block on some entries and not others is the drift this
    # split exists to prevent: whichever entries kept it would form a
    # denominator chosen by whoever stopped editing, which is the same defect
    # as a half-written key.
    with_block = {j for j, e in entries.items() if "loader_fields" in e}
    if with_block and len(with_block) != len(entries):
        raise MockCorpusError(
            f"{resolved}: {len(with_block)} of {len(entries)} entries carry a "
            f"`loader_fields` block. Either every entry has one or none does; "
            f"missing on: {sorted(set(entries) - with_block)}")
    return dict(entries)


def _validate_entry(where, job_id, entry, posting):
    if not isinstance(entry, dict):
        raise MockCorpusError(f"{where}:{job_id}: expected an object, got "
                              f"{type(entry).__name__}")
    for required in ("verdict", "failure_modes", "key_source", "notes",
                     "fields"):
        if required not in entry:
            raise MockCorpusError(f"{where}:{job_id}: missing {required!r}")

    if entry["verdict"] not in VERDICTS:
        raise MockCorpusError(
            f"{where}:{job_id}: verdict {entry['verdict']!r} is not one of "
            f"{list(VERDICTS)}")
    modes = entry["failure_modes"]
    if not isinstance(modes, list):
        raise MockCorpusError(f"{where}:{job_id}: failure_modes must be a "
                              f"list, got {type(modes).__name__}")
    bad = [m for m in modes if m not in FAILURE_MODES]
    if bad:
        raise MockCorpusError(
            f"{where}:{job_id}: failure_mode(s) {bad} outside "
            f"{list(FAILURE_MODES)}")
    if "addendum_verdict" in entry and entry["addendum_verdict"] not in VERDICTS:
        raise MockCorpusError(
            f"{where}:{job_id}: addendum_verdict "
            f"{entry['addendum_verdict']!r} is not one of {list(VERDICTS)}")

    fields = entry["fields"]
    if not isinstance(fields, dict):
        raise MockCorpusError(f"{where}:{job_id}: fields must be an object, "
                              f"got {type(fields).__name__}")
    for name in sorted(fields):
        _validate_field(where, job_id, name, fields[name], posting)

    loader = entry.get("loader_fields")
    if loader is None:
        return
    if not isinstance(loader, dict):
        raise MockCorpusError(f"{where}:{job_id}: loader_fields must be an "
                              f"object, got {type(loader).__name__}")
    for name in sorted(loader):
        _validate_field(where, job_id, name, loader[name], posting,
                        block="loader_fields")


def _validate_field(where, job_id, name, field, posting, block="fields"):
    """One `{"value", "quote"}` object, in whichever of the two blocks it sits.

    The membership check runs in BOTH directions -- an extraction field is
    refused in `loader_fields` and a loader field is refused in `fields` -- so
    the two sets cannot quietly drift back together. Being merely absent from
    the other block's list is not enough: a name added to `job_facts` later
    would otherwise become silently legal in `loader_fields`.
    """
    if block == "fields":
        if name in LOADER_FIELDS:
            raise MockCorpusError(
                f"{where}:{job_id}.{name}: this is a `jobs` column, not a "
                f"job_facts column. match.py:275-288 feeds it to score_job "
                f"alongside the extracted facts, which is exactly why it "
                f"looks scoreable and is not -- no model produces it, "
                f"mock_corpus._location_flags() does. Move it to the entry's "
                f"`loader_fields` block")
        if name not in FACT_FIELDS:
            raise MockCorpusError(
                f"{where}:{job_id}.{name}: not a job_facts column "
                f"(schema.py:407-430). Nothing extracts it, so nothing can be "
                f"scored against it")
    else:
        if name in FACT_FIELDS:
            raise MockCorpusError(
                f"{where}:{job_id}.{name}: this is a job_facts column, which a "
                f"model DOES produce. It belongs in `fields`, where it counts "
                f"toward extraction accuracy; in `loader_fields` it would be "
                f"quietly removed from that denominator")
        if name not in LOADER_FIELDS:
            raise MockCorpusError(
                f"{where}:{job_id}.{name}: not a writable `jobs` column "
                f"(schema.COLUMNS, schema.py:121-128). Nothing in "
                f"to_job_record() produces it, so there is nothing to check "
                f"it against")
    if not isinstance(field, dict) or "value" not in field or "quote" not in field:
        raise MockCorpusError(
            f"{where}:{job_id}.{name}: expected "
            f'{{"value": ..., "quote": ...}}, got {field!r}')

    value = field["value"]
    vocabulary = CLOSED_VOCABULARIES.get(name)
    # A null value is "not determinable from the posting". It is NOT a wrong
    # answer and is never checked against a vocabulary -- see expected().
    if value is not None and vocabulary is not None and value not in vocabulary:
        raise MockCorpusError(
            f"{where}:{job_id}.{name}: {value!r} is outside the closed "
            f"vocabulary extract.py would produce: {list(vocabulary)}")

    quote = field["quote"]
    if quote is None:
        return
    if not isinstance(quote, str):
        raise MockCorpusError(f"{where}:{job_id}.{name}: quote must be a "
                              f"string or null, got {type(quote).__name__}")
    source_field = field.get("quote_field", DEFAULT_QUOTE_FIELD)
    source = _quote_source(posting, source_field)
    if source is None:
        raise MockCorpusError(
            f"{where}:{job_id}.{name}: quote_field {source_field!r} is not a "
            f"field of the posting")
    if quote not in source:
        raise MockCorpusError(
            f"{where}:{job_id}.{name}: quote is not a literal substring of "
            f"{source_field}. A quote that has been tidied cannot be checked "
            f"against the posting, which is the only thing making this key "
            f"auditable rather than merely assertable. quote={quote!r}")


def _quote_source(posting, source_field):
    """The posting text a quote names, or None if it names nothing."""
    name = _QUOTE_FIELD_ALIASES.get(source_field, source_field)
    value = posting.get(name)
    return value if isinstance(value, str) else None


# ---------------------------------------------------------------------------
# Reading the key
# ---------------------------------------------------------------------------

def expected(key, job_id, field):
    """(value, quote) for one field, or None if the key does not answer it.

    THREE OUTCOMES, AND THE MIDDLE ONE IS THE POINT:

      * None                -- the key has no entry for this field. Out of
                               scope; not part of any denominator.
      * (None, quote)        -- the key says the posting does not determine
                               this field. NOT MEASURABLE. A model's answer
                               here is neither right nor wrong, and counting
                               it as wrong manufactures errors out of the
                               fixture's own silence.
      * (value, quote)       -- a real expected answer.

    Callers must branch on `is_measurable()` rather than on truthiness of the
    value: False and 0 are perfectly good expected answers.

    Asking for a LOADER field here RAISES rather than returning None. Silently
    answering None would let a caller compute `location_is_nyc` accuracy over a
    denominator of zero and print it beside the real ones, which is the exact
    confusion the two blocks exist to prevent. Use loader_expected().
    """
    _refuse_loader_field(field)
    entry = key.get(job_id)
    if not entry:
        return None
    field_entry = entry.get("fields", {}).get(field)
    if field_entry is None:
        return None
    return field_entry["value"], field_entry["quote"]


def _refuse_loader_field(field):
    if field in LOADER_FIELDS:
        raise MockCorpusError(
            f"{field!r} is a loader field, not an extraction target. No model "
            f"produces it -- to_job_record() does -- so it has no extraction "
            f"accuracy. See LOADER_FIELDS, and use loader_expected() / "
            f"loader_disagreements() instead")


def loader_expected(key, job_id, field):
    """(value, quote) from the entry's `loader_fields` block, or None.

    The deliberately separate door. Same shape as expected() and a different
    meaning: this is a second reading of the posting to check THIS MODULE's
    mapping against, never a model's answer to be scored. See
    loader_disagreements(), which is the only thing that should consume it.
    """
    entry = key.get(job_id)
    if not entry:
        return None
    field_entry = entry.get("loader_fields", {}).get(field)
    if field_entry is None:
        return None
    return field_entry["value"], field_entry["quote"]


def is_measurable(key, job_id, field):
    """Whether this (job, field) can be scored at all.

    False both when the key is silent and when it explicitly answers null.
    The two differ in what they say about the posting and not in what they
    permit, which is: nothing.
    """
    answer = expected(key, job_id, field)
    return answer is not None and answer[0] is not None


def measurable(key, field):
    """The job_ids that can form an honest denominator for one field."""
    _refuse_loader_field(field)
    return [job_id for job_id in sorted(key)
            if is_measurable(key, job_id, field)]


def measurable_counts(key):
    """{field: n} -- the honest denominator for every extraction field.

    This must travel with any per-field accuracy figure. `years_experience_min`
    is answered null on 41 of the 55 postings, so its n is 14: a percentage
    printed without that beside it invites the reader to assume 55 and read a
    two-posting difference as four points.
    """
    return {field: len(measurable(key, field))
            for field in sorted(extraction_fields(key))}


def extraction_fields(key):
    """The field names a model can be scored on. Disjoint from loader_fields().

    THE DISTINCTION THIS PAIR EXISTS TO ENFORCE
        match.py:275-288 hands score_job twelve `job_facts` columns and two
        `jobs` columns -- `j.location_is_nyc` and `j.location_is_remote` -- in
        one flat row. Downstream of that SELECT the two kinds are
        indistinguishable, which is why an accuracy figure can fold them
        together without anyone noticing: the loader fields would contribute
        110 near-certain agreements across 55 postings to a numerator captioned
        "the model got this right", when the model was never asked.

        These two functions return DISJOINT sets, and a test asserts it. A
        caller that wants one denominator must take the union deliberately and
        will have written the word `union` where a reviewer can see it.
    """
    names = set()
    for entry in key.values():
        names.update(entry.get("fields", {}))
    return names


def loader_fields(key):
    """The field names this module produces and no model does.

    The other half of extraction_fields(); see its docstring for match.py:281
    and why the two must not be summed. Consume these through
    loader_disagreements(), not as accuracy.
    """
    names = set()
    for entry in key.values():
        names.update(entry.get("loader_fields", {}))
    return names


def loader_disagreements(key, postings=None):
    """Where to_job_record() and the key read the same posting differently.

    THE CHECK RUNS BACKWARDS, AND THAT IS THE POINT. Everywhere else in this
    module the key is the expected answer and something else is under test.
    Here the key is a second reader and THIS MODULE is under test: if
    `_location_flags()` is wrong, score_job's location penalties are wrong for
    every row in the corpus and nothing else in this repo would report it --
    the flags are computed once at ingest, stored, and never re-derived.

    One row per disagreement, shaped like reconcile()'s and for the same
    reason: it carries `derived` and `key` side by side and never one merged
    value.
    """
    by_id = {p["job_id"]: p for p in (postings if postings is not None
                                      else load_postings())}
    rows = []
    for job_id in sorted(key):
        block = key[job_id].get("loader_fields") or {}
        posting = by_id.get(job_id)
        if posting is None:
            continue
        record = to_job_record(posting)
        for name in sorted(block):
            derived = record[name]
            stated = block[name]["value"]
            if stated is None or derived == stated:
                continue
            rows.append({"job_id": job_id, "field": name,
                         "derived": derived, "key": stated,
                         "quote": block[name]["quote"],
                         "note": block[name].get("notes")})
    return rows


def verdicts(key):
    """{job_id: "good"|"bad"|"undecided"}."""
    return {job_id: entry["verdict"] for job_id, entry in key.items()}


def failure_modes(key):
    """{job_id: [mode, ...]}. Empty list for a `good` posting, never None."""
    return {job_id: list(entry["failure_modes"])
            for job_id, entry in key.items()}


def reconcile(key):
    """Every entry whose addendum verdict is recorded, with BOTH verdicts.

    One row per entry carrying `addendum_verdict`:

        {"job_id", "derived", "addendum", "agrees", "note"}

    `derived` is the entry's own `verdict`; `addendum` is what
    mock-postings-v3-answer-key-addendum.md said. Where they differ this
    returns both and sets agrees=False. It NEVER returns a single merged
    value: HANDOFF's rule is to make the tool print both rather than pick one,
    because a disagreement quietly resolved in a loader is a real distinction
    buried where nobody will look for it. mock_042 is the live example -- the
    addendum (line 37) flags it "good - flag for your judgment" precisely
    because "bachelor's degree or equivalent experience" sits against a cohort
    floor of no degree required, and that is a decision, not a lookup.
    """
    rows = []
    for job_id in sorted(key):
        entry = key[job_id]
        if "addendum_verdict" not in entry:
            continue
        derived = entry["verdict"]
        addendum = entry["addendum_verdict"]
        rows.append({
            "job_id": job_id,
            "derived": derived,
            "addendum": addendum,
            "agrees": derived == addendum,
            "note": entry.get("disagreement") or entry.get("addendum_note"),
        })
    return rows


# ---------------------------------------------------------------------------

def postings_sha256(path=None):
    """sha256 of the postings file's bytes.

    The answer key records this so a key can say which corpus it answers. Not
    checked automatically by load_key: agent A generates the key against a
    file that may be reformatted later, and a hash mismatch should be a
    reported difference rather than an unloadable key.
    """
    with open(path or POSTINGS_PATH, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError as e:
        raise MockCorpusError(f"{path}: not found") from e
    except json.JSONDecodeError as e:
        raise MockCorpusError(f"{path}: {e}") from e
