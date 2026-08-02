"""
How a Builder comes to exist as a scored entity, and how their overrides
resolve against the cohort's.

THE GAP THIS CLOSES (tranche_five/26). Authentication has been done since
2026-07-26: a Builder signs in with Google, gets a session, and every query in
jobs.py is scoped to the `profile` on their app_users row. What they could not
do was EXIST as anything the ranking is aware of. `profiles` rows -- carrying
persona_json, criteria_json, relevance_json and criteria_version -- could only
be created by migrations/migrate_profiles.py, a CLI reading a hand-written
file. Fine for two profiles and impossible for thirty.

INHERITANCE, NOT AUTHORING, and this is the design decision everything else
here follows from. A Builder does NOT get a `profiles` row. There is ONE cohort
profile; nobody is hand-authoring thirty weight files, and eight unvalidatable
configs are worse than one validated one. The cohort row carries the persona,
the criteria and the relevance gate for all thirty, and builder_profiles
carries only what genuinely varies -- where they will work, what they will
accept, what they earned before, what they are subscribed to.

    cohort profile  --  criteria_json, relevance_json, persona_json  (task 13)
          |
          +-- builder --  location, remote preference, comp floor, tracks

That is the same fixed-effect/random-effect decomposition as the ranker's
eventual global-plus-residual shape and as builder_job_state one level down,
kept deliberately consistent so the per-Builder residual has somewhere obvious
to live later.

WHAT IS NOT HERE, AND IT IS HALF THE DEFINITION OF DONE. Two of task 26's done
bullets need a screen -- "a Builder signs in with Google and reaches a ranked
list" and "onboarding is <= 3 screens" -- and a screen is tranche_six/32. This
module is the endpoint those screens post to. An endpoint can be built against
no screen and a screen cannot be built against no endpoint, which is the
direction the 26/32 cycle had to be cut in.

NO FILE UPLOAD, ANYWHERE, and it is a privacy decision rather than an
unfinished feature. A resume upload would mean storing personal documents for
thirty low-income adults on a residential home connection. A structured form
yields the same matching-relevant fields without ever holding the document. If
resume parsing is added later it must extract fields and discard the source,
and it should wait until there is somewhere better to put it than a home
server.
"""

import logging

import config  # noqa: F401  (must come first -- performs the sys.path insert)

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

import jobs
import profiles
import schema_web
from auth import User, require_user
from db import db
from jobs import ContractError
from lib.timeparse import utc_now_str

log = logging.getLogger("webapp.onboarding")

router = APIRouter()

#: The four resolvable preferences and what they mean when nobody has said.
#:
#: THIS IS relevance.DISABLED's JOB, IN relevance.DISABLED's SPIRIT. That
#: constant (relevance.py) is the config used when config/relevance.json is
#: absent, and every value in it is the PERMISSIVE one: everything is tier 1 and
#: eligible, i.e. exactly the unfiltered behaviour that predates the module. Its
#: comment says why -- "a missing config must not silently start skipping jobs".
#: The same rule decides every value below. A Builder who has not onboarded, or
#: who skipped a field, must see MORE than one who answered, never less.
#: Silence is this system's failure mode (../.claude/CLAUDE.md) and a default
#: that filters is silence with an opinion.
#:
#:   location_pref   "either" -- both of jobs_app's location booleans pass.
#:   remote_pref     "onsite_ok" -- the flexible end of the threshold, so no
#:                   remote_policy value is excluded. Reads oddly and is
#:                   correct: it is "onsite is acceptable too", not "onsite".
#:   comp_floor      0 -- no floor. NOT None: the merge below treats None as
#:                   "fall through to the next layer", so the bottom layer has
#:                   to be a real value or resolution has no fixed point.
#:   tracks          None -- and this is the one deliberate exception to the
#:                   sentence above, because there is no finite value meaning
#:                   "all tracks". See resolve().
DEFAULTS = {
    "location_pref": "either",
    "remote_pref": "onsite_ok",
    "comp_floor": 0,
    "tracks": None,
}

#: Where the COHORT's answers to those same four keys live: an optional section
#: of the cohort profile's criteria_json, read and never written here.
#:
#: WHY criteria_json AND NOT A NEW COLUMN. Adding one to `profiles` would be
#: this service issuing DDL against a pipeline-owned table, which is the line
#: schema_web.py's docstring draws. criteria_json is already TEXT holding a
#: whole document that only its owner interprets, so a section nothing else
#: reads costs the pipeline nothing: profiles.validate() checks `base`,
#: `archetypes`, `flags` and `tech.boost` by name and ignores everything else,
#: and match.score_job() reads the sections it knows about.
#:
#: IT IS ABSENT TODAY AND THAT IS THE EXPECTED STATE. `pursuit` has no
#: builder_defaults section, so every unanswered key currently resolves to
#: DEFAULTS. The layer exists so that "the cohort is NYC" can stop being a
#: sentence in CLAUDE.md and become a value, WITHOUT that having to be decided
#: now and without thirty Builders each having to type it.
COHORT_DEFAULTS_KEY = "builder_defaults"

#: The keys resolve() will merge. Anything else in a builder_defaults section is
#: ignored rather than merged, so a typo in a hand-edited criteria_json cannot
#: introduce a preference nothing knows how to apply.
RESOLVABLE = tuple(DEFAULTS)

#: What a seed judgement means, as an event this service already knows how to
#: write. The contract fixture's two verdicts, and nothing else.
#:
#: THE MAPPING WAS THE OPEN QUESTION. frontend/fixtures/contract/MANIFEST.json
#: records it as such -- "'interested' has to map onto a CLIENT_EVENT_NAMES
#: value, and no mapping has been decided" -- so here it is, with the reasoning.
#:
#: `interested` -> save. A save is the strongest positive a client can send, it
#: is the only cohort-visible event (jobs.COHORT_VISIBLE_EVENTS), and it leaves
#: the posting in the list where the Builder can act on it. `applied` would be a
#: lie and `open` would claim they read it.
#:
#: `not_interested` -> dismiss, WITH ITS FULL CONSEQUENCE ACCEPTED. A dismissal
#: is permanent for that Builder and hides the posting from GET /v1/jobs by
#: default (jobs.py, `include_dismissed`). That is the right reading: they were
#: shown a real posting and said no. It is also reversible from the detail page,
#: which is why get_job() deliberately does not filter dismissals, and the undo
#: is itself a row (`undismiss`) rather than a deletion.
#:
#: NO REASON IS ATTACHED. jobs.DISMISS_REASONS is a closed vocabulary about WHY,
#: and an onboarding thumbs-down carries no why. A reason invented here would be
#: unfalsifiable evidence in the table task 31's aggregation reads.
VERDICT_EVENTS = {"interested": "save", "not_interested": "dismiss"}

#: 15-20 deliberately diverse postings is what task 26 asks a screen to show.
#: The cap is above it with room, and it exists for the reason
#: jobs.EventBatch's does: an unbounded list is a way to make one request cost
#: an arbitrary number of inserts.
MAX_SEED_JUDGEMENTS = 40


# --------------------------------------------------------------------------
# Resolution
# --------------------------------------------------------------------------

def _strip_comments(cfg):
    """Drop the _-prefixed documentation keys.

    The convention `_comment` fields are load-bearing documentation
    (../.claude/CLAUDE.md), and the reason every reader has to strip them:
    relevance.load() does it at relevance.py:88-97, and
    migrations/migrate_profiles.py's strip_comments() does it with a comment
    saying it is the same convention. A builder_defaults section is
    hand-edited into a config file, so it will have them.
    """
    return {k: v for k, v in cfg.items() if not k.startswith("_")}


def cohort_defaults(profile):
    """The cohort layer: `builder_defaults` out of a profiles row, or {}.

    Takes a profiles.Profile rather than a connection, so the merge below is
    pure and sweepable without a database -- the same property score_job() has
    and for the same reason.

    A profile that is missing, or whose criteria_json has no builder_defaults
    section, contributes NOTHING rather than an error. That is not leniency:
    the section is absent from `pursuit` today, so treating its absence as a
    failure would make the endpoint 500 against the only cohort that exists.
    """
    if profile is None:
        return {}
    section = (profile.criteria or {}).get(COHORT_DEFAULTS_KEY)
    if not isinstance(section, dict):
        return {}
    return {k: v for k, v in _strip_comments(section).items() if k in RESOLVABLE}


def resolve(override=None, cohort=None):
    """Builder override, else cohort, else shared default. One dict.

    THE MERGE IS relevance.load(path=None, cfg=None)'s, WHICH IS WHAT TASK 26
    ASKS FOR -- "reuse that pattern rather than inventing a second one". What
    carries over from relevance.py:88-97 is the shape of it: a dict of
    documented permissive defaults, `_`-prefixed keys dropped on the way in, and
    a key-wise overlay so that a layer specifying one key gets the DEFAULT for
    the keys it omitted rather than some other layer's answer to them.

    WHERE IT DIFFERS, STATED BECAUSE THE DIFFERENCE IS DELIBERATE. relevance
    merges a profile's cfg over DISABLED and pointedly NOT over the shared
    file's contents, "which would make its behaviour depend on a file it never
    mentioned". That is right there because a profile's relevance_json REPLACES
    the shared gate wholesale -- two layers, not three. Here the cohort layer is
    an INHERITED parent, which is the whole design ("everything else resolves
    through the parent"), so it sits between the two and a Builder who answers
    one question does not lose the cohort's answers to the rest. Same
    mechanism, one more layer, and the layer is the reason the table exists.

    None MEANS "NOT EXPRESSED" AT EVERY LAYER, which is what makes a merge the
    right operation at all. Every column on builder_profiles is nullable and
    NULL means nobody asked -- the distinction PRIOR_DOMAINS draws in
    schema_web.py -- so a None arriving from a layer falls through to the next
    one instead of overwriting it with an absence. This is the one place that
    rule is implemented, and it is why `comp_floor` bottoms out at 0 rather
    than at None: the bottom layer cannot itself fall through.

    `tracks` IS THE EXCEPTION AND IT RESOLVES TO None ON PURPOSE. There is no
    finite list meaning "every track", the vocabulary is undecided anyway (task
    30), and the honest encoding of "this Builder has no subscription" is the
    absence of one. A caller reading tracks None must show everything; a caller
    that treats None as an empty filter shows nothing, which is the failure this
    sentence exists to prevent.
    """
    resolved = dict(DEFAULTS)
    for layer in (cohort or {}, override or {}):
        for key in RESOLVABLE:
            value = layer.get(key)
            if value is not None:
                resolved[key] = value
    return resolved


def load_builder(conn, app_user_id):
    """One Builder's override row as a plain dict, or None if they never
    onboarded. Only the resolvable keys -- the rest of the row is onboarding
    provenance, not preference."""
    row = conn.execute(
        "SELECT location_pref, remote_pref, comp_floor, tracks "
        "FROM builder_profiles WHERE app_user_id = %s", (app_user_id,)
    ).fetchone()
    return dict(zip(RESOLVABLE, row)) if row else None


def resolved_for(conn, user):
    """The config one Builder's list should be filtered by. Three layers.

    The analogue of relevance.for_profile(), and kept here rather than on
    builder_profiles' own module for the same reason that function gives:
    "None means fall back" is a fact about resolution, not about storage, and
    every caller has to resolve it the same way.

    NOTHING CALLS THIS ON THE LIST PATH YET. jobs.list_jobs() does not filter on
    any of these four, and wiring it in belongs with the screen that lets a
    Builder set them (tranche_six/32) -- turning on a filter nobody can see or
    change would silently shrink thirty people's lists. It is the read half of
    this table and it is tested, so 32 has something to call.
    """
    return resolve(load_builder(conn, user.id),
                   cohort_defaults(profiles.load_one(conn, user.profile)))


# --------------------------------------------------------------------------
# Request
# --------------------------------------------------------------------------

class SeedJudgement(BaseModel):
    job_id: str
    verdict: str


class OnboardingRequest(BaseModel):
    """POST /v1/onboarding's body, per API-CONTRACT-v1.md.

    EVERY FIELD IS OPTIONAL AT THE MODEL LAYER AND VALIDATED IN THE HANDLER,
    which is jobs.Event's arrangement and is copied for jobs.Event's reason: a
    contract violation has to come back in the contract's own 400 envelope
    ({"error": {code, message, request_id}}) rather than as FastAPI's 422, and
    pydantic cannot produce that shape. It is also right on the merits here --
    onboarding is a form thirty people fill in on a phone, and "you may skip
    this" is the actual product requirement, so NULL has to be reachable for
    every one of them.

    THERE IS NO `profile` FIELD AND THERE MUST NEVER BE ONE. The cohort comes
    from the session, via app_users.profile, exactly as jobs.py's tenancy does:
    "a `?profile=` parameter would turn one forgotten check into a cross-user
    data leak".

    THERE IS NO `tracks` FIELD EITHER, and its absence is the design. Task 26
    is explicit that seed judgements seed track subscriptions "from behaviour
    rather than a checkbox" -- see derive_tracks(). The contract fixture has no
    tracks key for the same reason.
    """

    prior_domain: str | None = None
    prior_years: int | None = Field(default=None, ge=0)
    situation: str | None = None
    location_pref: str | None = None
    remote_pref: str | None = None
    comp_floor: int | None = Field(default=None, ge=0)
    schedule_constraints: list[str] | None = None
    seed_judgements: list[SeedJudgement] = Field(
        default_factory=list, max_length=MAX_SEED_JUDGEMENTS)


#: Each closed-vocabulary field and the tuple its CHECK constraint is generated
#: from. ONE SOURCE, TWO ENFORCEMENTS: the request validator below and the
#: database both read these tuples, so a value cannot be accepted by the API and
#: refused by the column. That is the failure the generated CHECKs in
#: schema_web.py exist to prevent, extended one layer outward -- without it,
#: widening a vocabulary in Python and forgetting the API surfaces as a 500 on
#: one Builder's submit and nowhere else.
_VOCABULARIES = {
    "prior_domain": schema_web.PRIOR_DOMAINS,
    "situation": schema_web.SITUATIONS,
    "location_pref": schema_web.LOCATION_PREFS,
    "remote_pref": schema_web.REMOTE_PREFS,
}


def validate_request(body):
    """Raise ContractError on anything the columns would refuse.

    THE WHOLE REQUEST FAILS, never part of it. That is validate_batch()'s rule
    and the contract's instruction -- "fail loudly; silence is this system's
    default failure mode and the API should not add to it" -- and it is sharper
    here than there: a half-accepted onboarding leaves a Builder who believes
    they answered six questions and a row that recorded four, with nothing
    anywhere to say which.

    request_id is None on every error. The client did not supply one -- this
    endpoint mints its own for the seed judgements -- and echoing a
    server-minted id back inside the failure that prevented it from being used
    would name a render that does not exist.
    """
    for field, vocabulary in _VOCABULARIES.items():
        value = getattr(body, field)
        if value is not None and value not in vocabulary:
            raise ContractError(
                f"unknown_{field}",
                f"unknown {field} {value!r}; expected one of {list(vocabulary)}",
                None)

    if body.schedule_constraints is not None:
        bad = sorted(set(body.schedule_constraints)
                     - set(schema_web.SCHEDULE_CONSTRAINTS))
        if bad:
            raise ContractError(
                "unknown_schedule_constraint",
                f"unknown schedule constraint(s) {bad}; expected a subset of "
                f"{list(schema_web.SCHEDULE_CONSTRAINTS)}", None)

    bad_verdicts = sorted({j.verdict for j in body.seed_judgements}
                          - set(VERDICT_EVENTS))
    if bad_verdicts:
        raise ContractError(
            "unknown_verdict",
            f"unknown verdict(s) {bad_verdicts}; expected one of "
            f"{list(VERDICT_EVENTS)}", None)

    seen = set()
    for judgement in body.seed_judgements:
        if judgement.job_id in seen:
            # Two verdicts on one posting is a client bug, and the two orders
            # produce different builder_job_state. Refusing is the only answer
            # that does not depend on list order.
            raise ContractError(
                "duplicate_seed_judgement",
                f"job {judgement.job_id} judged twice in one request", None)
        seen.add(judgement.job_id)


# --------------------------------------------------------------------------
# Writes
# --------------------------------------------------------------------------

def derive_tracks(conn, profile, job_ids):
    """The tracks a Builder liked, from what they liked. Never a checkbox.

    Task 26's second onboarding step does three things at once, and this is the
    second: showing 15-20 deliberately diverse postings and collecting
    like/dislike "seeds their track subscriptions from behaviour rather than a
    checkbox". A Builder who does not yet know what they want learns more from
    reacting to twenty real postings than from a dropdown, and the dropdown
    would need a vocabulary nobody has agreed (task 30).

    'Poor Fit' is excluded. It is a real score.TRACKS value and it is the
    model's way of saying the posting is wrong for the cohort; subscribing
    somebody to it because they liked one posting the scorer misjudged would
    turn one disagreement into a standing preference.

    THIS RETURNS NOTHING TODAY AND THE CODE IS STILL RIGHT. primary_track is
    written by score.py, and `pursuit` has daily_narrative_budget = 0 -- so
    score.py writes no rows for the cohort profile at all, and job_scores holds
    zero pursuit rows as of 2026-08-02. Every seed judgement therefore derives
    an empty set and the caller leaves `tracks` NULL. config/
    pursuit-persona.json's `_no_buckets_comment` records why the budget is 0 and
    that score.TRACKS' names "do not describe this population" anyway. The
    derivation is written now because the alternative is a checkbox shipped now.
    """
    if not job_ids:
        return []
    rows = conn.execute(
        """
        SELECT DISTINCT s.primary_track FROM job_scores s
        WHERE s.profile = %s AND s.job_id = ANY(%s)
          AND s.primary_track IS NOT NULL AND s.primary_track <> 'Poor Fit'
        ORDER BY s.primary_track
        """,
        (profile, list(job_ids)),
    ).fetchall()
    return [r[0] for r in rows]


def upsert_builder_profile(conn, user, body, now, tracks=None):
    """Create or refresh one Builder's override row. Does not commit.

    ABSENT MEANS PRESERVE, on the four columns a re-submission may legitimately
    not mention. This is migrations/migrate_profiles.py's resolve_preserved()
    rule and it is here for the same reason that file gives at length: a caller
    that did not mention a field has no opinion about it and must not express
    one. `tracks` is the sharpest case -- it is derived from THIS request's
    judgements, so a re-onboarding with no judgements would otherwise erase a
    subscription set built from twenty real answers.

    parent_profile is written from user.profile -- the session's, never a
    parameter's -- and the composite foreign key then guarantees the two agree
    for as long as the row exists. See schema_web.py.
    """
    conn.execute(
        """
        INSERT INTO builder_profiles
            (app_user_id, parent_profile, location_pref, remote_pref,
             comp_floor, tracks, prior_years, situation, schedule_constraints,
             onboarded_at, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (app_user_id) DO UPDATE SET
            location_pref = coalesce(EXCLUDED.location_pref,
                                     builder_profiles.location_pref),
            remote_pref = coalesce(EXCLUDED.remote_pref,
                                   builder_profiles.remote_pref),
            comp_floor = coalesce(EXCLUDED.comp_floor,
                                  builder_profiles.comp_floor),
            tracks = coalesce(EXCLUDED.tracks, builder_profiles.tracks),
            prior_years = coalesce(EXCLUDED.prior_years,
                                   builder_profiles.prior_years),
            situation = coalesce(EXCLUDED.situation, builder_profiles.situation),
            schedule_constraints = coalesce(EXCLUDED.schedule_constraints,
                                            builder_profiles.schedule_constraints),
            onboarded_at = EXCLUDED.onboarded_at,
            updated_at = EXCLUDED.updated_at
        """,
        (user.id, user.profile, body.location_pref, body.remote_pref,
         body.comp_floor, tracks or None, body.prior_years, body.situation,
         body.schedule_constraints, now, now, now),
    )


def record_seed_judgements(user, judgements):
    """Write the seed judgements as real job_events. Returns (recorded, id).

    IT CALLS jobs.record_events() RATHER THAN INSERTING. Task 26's definition of
    done says seed judgements "write real job_events rows with the correct
    visibility", and `visibility` is set server-side by event type
    (jobs.visibility_for) precisely because a privacy control a client can set
    is not one. A second INSERT here would be a second answer to that question
    and would drift from the first -- which is the failure api/query_claims.py's
    docstring records, where nine functions and three tables' DDL were
    duplicated and had drifted six ways by the time anyone measured, two of the
    drifts changing row identity.

    Going through that function gets, for free and correctly: visibility by
    event type, match_score and fit_score looked up server-side as of the
    judgement, criteria_version, app_user_id, the builder_job_state write in the
    same transaction, and the refusal to record an event for a job outside this
    profile's match set.

    THE REQUEST ID IS MINTED HERE AND IT IS HONEST. A seed set IS a render -- a
    Builder was shown these postings and reacted to them -- so the rows carry
    one request_id naming it, exactly as a list page's do. No rank is sent:
    jobs.RANK_REQUIRED_EVENTS is impression and open, and a seed set has no
    ranking to speak of. That is the same reading the contract already applies
    to a save raised from a detail page.

    IT IS A SEPARATE TRANSACTION FROM THE PROFILE ROW, and that is the cost of
    not duplicating the write path: record_events() opens its own connection and
    commits it. The order below is chosen so the survivable failure is the one
    that happens -- the profile row lands first, so a crash between them leaves
    a Builder who onboarded with no judgements, which a client can retry, rather
    than judgements belonging to a Builder with no profile row.
    """
    if not judgements:
        return 0, None
    request_id = jobs.new_request_id()
    batch = jobs.EventBatch(
        events=[jobs.Event(job_id=j.job_id, event=VERDICT_EVENTS[j.verdict])
                for j in judgements],
        request_id=request_id)
    result = jobs.record_events(batch, user)
    return result["recorded"], request_id


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------

def _state(conn, user):
    """The onboarding block, for either route. Shape per
    frontend/fixtures/contract/ASPIRATIONAL_POST_v1_onboarding.response.json."""
    row = conn.execute(
        "SELECT b.onboarded_at, u.prior_domain, b.prior_years "
        "FROM app_users u LEFT JOIN builder_profiles b ON b.app_user_id = u.id "
        "WHERE u.id = %s", (user.id,)
    ).fetchone()
    onboarded_at, prior_domain, prior_years = row if row else (None, None, None)
    return {"completed": onboarded_at is not None,
            "completed_at": onboarded_at,
            "prior_domain": prior_domain,
            "prior_years": prior_years}


@router.get("/v1/onboarding")
def get_onboarding(user: User = Depends(require_user)):
    """Has this Builder onboarded? The read a first-run client needs.

    NOT IN API-CONTRACT-v1.md, and frontend/fixtures/contract/MANIFEST.json is
    where the gap is recorded: the contract has POST /v1/onboarding and "no way
    to READ onboarding state, and a first-run client needs one". It invents an
    `onboarding` block on GET /v1/me to cover it. That block is not added here,
    because /v1/me is auth.py's and its "deliberately touches no jobs table"
    property is worth more than saving a request; this route returns the same
    block from the module that owns it. Whichever tranche_six/32 prefers, the
    two must not both exist with different shapes.
    """
    with db() as conn:
        return {"onboarding": _state(conn, user), "profile": user.profile}


@router.post("/v1/onboarding")
def post_onboarding(body: OnboardingRequest, user: User = Depends(require_user)):
    """A structured form and a set of seed judgements. Three steps, no upload.

    Step 1 is the form -- prior domain, years, situation, location, schedule,
    comp floor. Step 2 is the seed judgements, which produce the Builder's first
    job_events rows on day one and seed their track subscriptions from
    behaviour. Step 3 is nothing: "resist adding steps. The population includes
    people for whom this is a first technical product; every additional screen
    loses someone."

    IDEMPOTENT ON THE FORM, APPEND-ONLY ON THE JUDGEMENTS, and the asymmetry is
    correct rather than an oversight. Re-submitting the form updates the same
    row -- a Builder correcting their comp floor is not a second Builder. Re-
    submitting judgements writes more events, because job_events is the
    append-only evidence and a second opinion about a posting is a second real
    thing that happened. builder_job_state, which holds the CURRENT answer,
    converges either way.

    prior_domain GOES TO app_users AND THE REST COME HERE, which looks like a
    split for no reason and is not. That column already exists and exists for a
    different purpose -- decomposing Axis B inter-annotator disagreement by
    background, via eval_labels.labeller_id = app_users.id (schema_web.py, and
    tests/test_prior_domain.py). It is a fact about the labeller, not an input
    to matching, so it belongs on the account row. Everything else here is a
    matching input and belongs on the override row.

    KNOWN, RECORDED, NOT FIXED HERE: schema_web.PRIOR_DOMAINS already fails on a
    real user. The repo owner is a working software engineer changing career, so
    `none` is false and `other` says nothing. Widening the vocabulary moves a
    CHECK constraint generated from it and is a decision, not a tidy-up --
    HANDOFF.md holds it. The field is optional here, so that Builder can leave
    it NULL, which is the honest answer and is what the column already means.
    """
    validate_request(body)
    now = utc_now_str()

    with db() as conn:
        # The absent foreign key, checked at the one moment it can be: a
        # builder_profiles row inherits from a `profiles` row, so a caller whose
        # session names a profile that does not exist gets a 400 naming it
        # rather than a row that resolves to DEFAULTS forever. verify_schema()
        # makes the same check across the whole table at startup.
        if profiles.load_one(conn, user.profile) is None:
            raise ContractError(
                "unknown_profile",
                f"profile {user.profile!r} has no row in `profiles`; a Builder "
                f"inherits from a cohort profile and this one does not exist",
                None)

        judged = [j.job_id for j in body.seed_judgements
                  if j.verdict == "interested"]
        tracks = derive_tracks(conn, user.profile, judged)

        if body.prior_domain is not None:
            conn.execute("UPDATE app_users SET prior_domain = %s WHERE id = %s",
                         (body.prior_domain, user.id))
        upsert_builder_profile(conn, user, body, now, tracks)
        conn.commit()

    recorded, request_id = record_seed_judgements(user, body.seed_judgements)
    if recorded < len(body.seed_judgements):
        # record_events() silently drops events for jobs outside this profile's
        # match set, which for onboarding means the client showed a posting the
        # Builder cannot be scored against. Worth a log line and NOT worth a
        # 400: the form half already landed, and failing the request would
        # invite a retry that re-writes the judgements that did work.
        log.info("seed judgements: %d of %d recorded for %s (request_id=%s)",
                 recorded, len(body.seed_judgements), user.id, request_id)

    with db() as conn:
        return {"onboarding": _state(conn, user),
                "seed_judgements_recorded": recorded,
                "profile": user.profile}
