"""Profiles: who the pipeline is scoring for.

WHY THIS REPLACED config/persona.json AS THE SOURCE OF TRUTH
    A persona in a file works for exactly one user. It cannot be created
    without a deploy, cannot be edited by the person it describes, and gives
    the pipeline no way to ask "who is active right now" -- which is the
    question extract.py needs answered before it can decide that a posting is
    worth an LLM call for ANYONE.

    config/persona.json is still the seed. migrate_profiles.py imports it once
    and thereafter the table is authoritative. The file is kept because it is
    a readable, reviewable starting point for a new profile, not because
    anything reads it at runtime.

THREE JSON BLOBS, THREE DIFFERENT JOBS
    persona_json    prose about the candidate. Goes into the narrative prompt
                    verbatim. Only an LLM ever reads it.
    relevance_json  which postings are worth extracting at all, as Postgres
                    title regexes. NULL means "use the shared default" --
                    most profiles will never need their own.
    criteria_json   numeric weights over job_facts. This is what actually
                    ranks, and it is the only one of the three that must be
                    machine-readable, so it is the only one this module
                    validates in any depth.

    They are stored as TEXT rather than JSONB deliberately: nothing queries
    inside them in SQL, they are read whole or not at all, and TEXT keeps
    them diffable against the config files they came from.

criteria_version IS A CACHE KEY, NOT A CHANGELOG
    job_matches rows record the criteria_version they were computed under, so
    match.py can recompute exactly the profiles whose rules moved instead of
    rebuilding the whole table. bump_criteria() exists so that editing weights
    without bumping is not something a caller can do by accident -- that
    combination leaves stale scores that look current, which is worse than
    either a rebuild or no change at all.
"""

import json
import os
from dataclasses import dataclass

import relevance
import schema
from lib.timeparse import utc_now_str

#: The seed persona, imported once by migrate_profiles.py. Not read at runtime.
PERSONA_FILE = os.environ.get(
    "JOB_SCORING_PERSONA_FILE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "config/persona.json"),
)

_COLUMNS = ("profile", "display_name", "persona_json", "relevance_json",
            "criteria_json", "criteria_version", "daily_narrative_budget",
            "active", "created_at", "updated_at")


@dataclass(frozen=True)
class Profile:
    """One user's view of the corpus.

    persona/relevance/criteria are the parsed forms; the raw TEXT stays in the
    database. relevance is None when the profile uses the shared default,
    which the caller resolves rather than this module -- extract.py wants the
    union across profiles and score.py wants one, and neither is a property
    of the profile itself.
    """

    profile: str
    display_name: str
    persona: dict
    relevance: dict
    criteria: dict
    criteria_version: int
    daily_narrative_budget: int
    active: bool


def _row_to_profile(row):
    (profile, display_name, persona_json, relevance_json, criteria_json,
     criteria_version, budget, active, _created, _updated) = row
    return Profile(
        profile=profile,
        display_name=display_name or profile,
        persona=json.loads(persona_json),
        relevance=json.loads(relevance_json) if relevance_json else None,
        criteria=json.loads(criteria_json),
        criteria_version=criteria_version,
        daily_narrative_budget=budget,
        active=active,
    )


def load_active(conn):
    """Every profile the pipeline should currently be working for.

    Ordered by profile name so that anything iterating profiles -- match.py's
    rebuild, the narrative warm pass -- does so in a stable order. That makes
    a partial run's progress predictable and keeps one profile from being
    starved by whatever order Postgres felt like returning.
    """
    rows = conn.execute(
        f"SELECT {', '.join(_COLUMNS)} FROM {schema.PROFILES_TABLE} "  # noqa: S608 -- splices _COLUMNS and schema.PROFILES_TABLE -- both module-level constants
        f"WHERE active ORDER BY profile"
    ).fetchall()
    return [_row_to_profile(r) for r in rows]


def load_one(conn, profile):
    """One profile by name, active or not, or None.

    Deliberately does not filter on `active`: the login path needs to serve a
    profile that an operator has paused, and "paused" should mean "not in the
    nightly sweep", not "404".
    """
    row = conn.execute(
        f"SELECT {', '.join(_COLUMNS)} FROM {schema.PROFILES_TABLE} "  # noqa: S608 -- splices _COLUMNS and schema.PROFILES_TABLE -- both module-level constants
        f"WHERE profile = %s", (profile,)
    ).fetchone()
    return _row_to_profile(row) if row else None


def validate(persona, criteria, relevance_cfg=None):
    """Raise ValueError if these blobs would break the pipeline downstream.

    Called before every write. The point is that a bad profile fails at the
    moment someone saves it, naming the field, rather than at 3am inside a
    thread pool where the only evidence is a deferred batch.

    relevance is the security-relevant one: relevance.tier_sql interpolates
    location_columns into SQL because column names cannot be bound as
    parameters. That interpolation is safe only while the config is trusted,
    and "trusted" stops being true the moment a profile is user-supplied.
    Checking here means the identifier check in tier_sql is a second line of
    defence rather than the only one.
    """
    if not isinstance(persona, dict):
        raise ValueError("persona must be a JSON object")
    # `buckets` is deliberately NOT in this list, and D16 is why it looks like
    # an oversight. score.build_prompt() used to hard-index persona["buckets"]
    # and take down a whole batch without it; the fix went there (the section
    # is omitted when the key is absent) rather than here, because a persona
    # with no positioning buckets is legitimate under the Pursuit scope -- the
    # active `pursuit` profile has none -- so requiring it would reject a
    # profile that already exists. Adding it here would resurrect the defect
    # as a save-time failure. See score.py's build_prompt docstring.
    for key in ("background_summary", "strengths", "honest_gaps",
                "scoring_instructions"):
        if key not in persona:
            raise ValueError(f"persona is missing required key {key!r}")

    if not isinstance(criteria, dict):
        raise ValueError("criteria must be a JSON object")
    base = criteria.get("base", 0)
    if not isinstance(base, (int, float)):
        raise ValueError("criteria.base must be a number")
    for section in ("archetypes", "flags"):
        for name, delta in (criteria.get(section) or {}).items():
            if not isinstance(delta, (int, float)):
                raise ValueError(
                    f"criteria.{section}.{name} must be a number, got {delta!r}")
    for name, delta in ((criteria.get("tech") or {}).get("boost") or {}).items():
        if not isinstance(delta, (int, float)):
            raise ValueError(
                f"criteria.tech.boost.{name} must be a number, got {delta!r}")

    if relevance_cfg is not None:
        if not isinstance(relevance_cfg, dict):
            raise ValueError("relevance must be a JSON object or null")
        # Compiling it is the check: tier_sql validates every location column
        # against a plain-identifier pattern and raises on anything else.
        relevance.tier_sql({**relevance.DISABLED, **relevance_cfg})


def upsert(conn, profile, persona, criteria, *, relevance_cfg=None,
           display_name=None, daily_narrative_budget=20, active=True,
           bump_criteria=False):
    """Create or update one profile.

    bump_criteria is explicit rather than automatic-on-change: match.py keys
    its incremental rebuild on criteria_version, so a silent bump on every
    write would rebuild every profile's matches whenever anyone edited a
    display name. Changing weights without bumping is the genuinely dangerous
    combination, so callers that touch criteria_json must say so.
    """
    validate(persona, criteria, relevance_cfg)
    now = utc_now_str()
    conn.execute(
        f"""
        INSERT INTO {schema.PROFILES_TABLE}
            (profile, display_name, persona_json, relevance_json, criteria_json,
             criteria_version, daily_narrative_budget, active,
             created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, 1, %s, %s, %s, %s)
        ON CONFLICT (profile) DO UPDATE SET
            display_name = EXCLUDED.display_name,
            persona_json = EXCLUDED.persona_json,
            relevance_json = EXCLUDED.relevance_json,
            criteria_json = EXCLUDED.criteria_json,
            criteria_version = {schema.PROFILES_TABLE}.criteria_version
                               + CASE WHEN %s THEN 1 ELSE 0 END,
            daily_narrative_budget = EXCLUDED.daily_narrative_budget,
            active = EXCLUDED.active,
            updated_at = EXCLUDED.updated_at
        """,  # noqa: S608 -- splices schema.PROFILES_TABLE, a module-level constant
        (profile, display_name or profile, json.dumps(persona),
         json.dumps(relevance_cfg) if relevance_cfg else None,
         json.dumps(criteria), daily_narrative_budget, active, now, now,
         bump_criteria),
    )
    conn.commit()


def set_active(conn, profile, active):
    conn.execute(
        f"UPDATE {schema.PROFILES_TABLE} SET active = %s, updated_at = %s "  # noqa: S608 -- splices schema.PROFILES_TABLE, a module-level constant
        f"WHERE profile = %s", (active, utc_now_str(), profile))
    conn.commit()


def load_persona_file(path=None):
    """The seed persona from disk. Used by migrate_profiles.py, not at runtime."""
    with open(path or PERSONA_FILE) as f:
        return json.load(f)
