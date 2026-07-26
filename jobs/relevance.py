"""Which jobs are worth spending a scoring call on.

THE PROBLEM THIS SOLVES
    ingest/ats.py pulls every open requisition at all 68 configured
    companies -- entire boards, not a filtered listing. 87% of the table
    arrives that way, and it includes "Chief Compliance Officer (APAC)",
    "Sales Development Representative, Korea" and "Remote Therapist -- Older
    Adults | LCSW". score.py had no filter beyond `status='open' AND not yet
    scored`, so those were all scoring candidates, and at SCORE_BATCH_SIZE=30
    a day against 200-400 new rows a day the queue only ever grew.

    Scoring was doing double duty as both the filter and the ranker. An LLM
    call is the most expensive way to decide that a compliance role is not a
    software job. A regex is the cheapest.

NOTHING IS DROPPED
    Rows are never deleted and never permanently excluded -- the pipeline
    keeps everything at ingest on purpose, so filtering stays a query-time
    decision you can revise. This module only assigns a TIER, and
    max_tier_to_score decides how deep the current budget reaches. Raise it
    and yesterday's tier-3 rows become eligible with no re-ingest.

    That matters because the boundary is genuinely fuzzy. "Forward Deployed
    Product Manager" is a real fit for the bridge_solutions bucket and a
    title regex will not reliably say so. Deprioritising it is recoverable;
    deleting it is not.

DOMAIN-NEUTRAL BY CONSTRUCTION
    Every pattern lives in config/relevance.json. There is not one
    engineering term in this file, which is the whole point: pointing the
    pipeline at nursing or trades jobs is a config swap, not a code change.
    The tier RULES are general ("does the title look like the work",
    "is the location acceptable"); only the ANSWERS are domain-specific.

TIERS
    1  title looks right AND location is acceptable   -- score first
    2  title looks right, location is not/unknown     -- score next
    3  everything else                                -- score only if the
                                                         budget reaches it
"""

import os
import json
import re

_IDENTIFIER = re.compile(r"[a-z_][a-z0-9_]*", re.IGNORECASE)

CONFIG_FILE = os.environ.get(
    "JOBS_RELEVANCE_FILE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "relevance.json"),
)

#: Used when config/relevance.json is absent: everything is tier 1 and
#: eligible, i.e. exactly the unfiltered behaviour that predates this module.
#: A missing config must not silently start skipping jobs.
DISABLED = {
    "title_include": [],
    "title_exclude": [],
    "company_exclude": [],
    "description_exclude": [],
    "location_columns": [],
    "max_tier_to_score": 3,
}


def load(path=None, cfg=None):
    """The shared config from disk, or a profile's own overrides.

    `cfg` is the per-profile case: profiles.relevance is either None ("use the
    shared default") or a dict from jobs.profiles.relevance_json. Merging it
    over DISABLED rather than over the file's contents is deliberate -- a
    profile that specifies title_include and nothing else should get the
    permissive default for the keys it omitted, not the shared config's
    answers for them, which would make its behaviour depend on a file it never
    mentioned.
    """
    if cfg is not None:
        return {**DISABLED, **{k: v for k, v in cfg.items()
                               if not k.startswith("_")}}
    path = path or CONFIG_FILE
    try:
        with open(path) as f:
            cfg = json.load(f)
    except FileNotFoundError:
        return dict(DISABLED)
    return {**DISABLED, **{k: v for k, v in cfg.items() if not k.startswith("_")}}


def for_profile(profile, default_cfg=None):
    """The relevance config one profile should be filtered by.

    Kept here rather than in profiles.py because "None means fall back to the
    shared config" is a fact about relevance, not about profiles -- and both
    extract.py and score.py need to resolve it the same way.
    """
    if profile.relevance is not None:
        return load(cfg=profile.relevance)
    return default_cfg if default_cfg is not None else load()


def _alternation(patterns):
    """Config holds a list of terms; Postgres wants one regex.

    Terms are joined raw rather than escaped -- they are author-written
    patterns, not user input, and being able to write "ml |machine learning"
    or a word boundary is the point. The file is trusted config, the same as
    companies.json.
    """
    return "|".join(p for p in patterns if p) or None


def tier_sql(cfg, table_alias="j", param_prefix="rel"):
    """(sql_expression, params) computing the tier for a row.

    Built as SQL rather than evaluated in Python because the caller needs
    ORDER BY tier ... LIMIT n. Ranking in Python would mean fetching all
    11k candidate rows to choose 30 of them.

    param_prefix exists so union_sql() can embed one of these per profile in
    a single statement without the bound names colliding. A collision would
    not error -- it would silently apply one profile's regex under another
    profile's name, which is the kind of bug that only shows up as "why is
    this profile seeing compliance roles".
    """
    a = table_alias
    include = _alternation(cfg["title_include"])
    exclude = _alternation(cfg["title_exclude"])
    company_exclude = _alternation(cfg.get("company_exclude") or [])
    description_exclude = _alternation(cfg.get("description_exclude") or [])
    loc_cols = cfg["location_columns"]

    params = {}
    if include:
        row_ok = f"{a}.title ~* %({param_prefix}_include)s"
        params[f"{param_prefix}_include"] = include
        if exclude:
            row_ok += f" AND {a}.title !~* %({param_prefix}_exclude)s"
            params[f"{param_prefix}_exclude"] = exclude
    else:
        row_ok = "TRUE"

    # Two exclusions that are about the POSTING's provenance rather than the
    # role, so they belong here and not in title_exclude.
    #
    #   company_exclude     -- Google Jobs returns relist sites as the employer:
    #       25.5% of those rows name a job board ("remote zest jobs",
    #       "vmysmartpros") in company_name. Their titles are keyword-stuffed,
    #       which is exactly what a title_include regex rewards, so they were
    #       taking the top of the ranking -- 19 sat at match_score >= 90, one at
    #       match 99 against an LLM fit of 15.
    #   description_exclude -- some of those relisters scrub the employer out of
    #       the body and leave the literal phrase "reputed company" behind
    #       ("reputed company is redefining IT operations for the modern
    #       reputed company"). A posting whose employer has been deleted cannot
    #       be applied to, whatever its title says.
    #
    # NOT USED, DELIBERATELY: "SerpApi's `via` field equals company_name".
    # It catches 160 rows but false-positives on every company that posts to
    # its own careers site -- via='Cisco Careers'/company='Cisco',
    # 'Snowflake Careers'/'Snowflake', Capital One, Deloitte, ServiceNow,
    # Citadel. Those are the BEST rows in the table. Measured before rejecting.
    if company_exclude:
        row_ok += f" AND {a}.company_name !~* %({param_prefix}_coexcl)s"
        params[f"{param_prefix}_coexcl"] = company_exclude
    if description_exclude:
        # COALESCE: a NULL description must not turn the whole predicate NULL
        # and silently demote every not-yet-described row to tier 3.
        row_ok += (f" AND COALESCE({a}.description_text, '') "
                     f"!~* %({param_prefix}_dexcl)s")
        params[f"{param_prefix}_dexcl"] = description_exclude

    # Column names cannot be bound as parameters, so they are interpolated --
    # hence the identifier check. This is trusted config, but "trusted" is a
    # property of where the file came from, not of the string, and the cost
    # of being wrong about that is arbitrary SQL.
    for c in loc_cols:
        if not _IDENTIFIER.fullmatch(c):
            raise ValueError(
                f"relevance.location_columns: {c!r} is not a plain column name")

    # COALESCE: these columns are NULL for sources that cannot determine
    # location. NULL must read as "not known to be acceptable" (tier 2), not
    # poison the whole OR into NULL and land in tier 3.
    if loc_cols:
        loc_ok = " OR ".join(f"COALESCE({a}.{c}, FALSE)" for c in loc_cols)
    else:
        loc_ok = "TRUE"

    sql = (f"CASE WHEN ({row_ok}) AND ({loc_ok}) THEN 1 "
           f"     WHEN ({row_ok}) THEN 2 "
           f"     ELSE 3 END")
    return sql, params


def max_tier(cfg):
    return int(cfg.get("max_tier_to_score", 3))


def union_sql(cfgs, table_alias="j"):
    """(sql_boolean, params): does this row clear the bar for ANY profile?

    THE QUESTION THIS ANSWERS IS NOT THE ONE tier_sql ANSWERS
        tier_sql ranks a posting for one persona. This asks whether a posting
        is worth extracting facts from at all, and extraction is shared -- it
        happens once and every profile reads the result. So the gate has to be
        the union: a posting one profile would never look at still deserves
        the call if a second profile would.

        Using one profile's filter here, or intersecting them, would mean the
        shared asset is quietly shaped by whoever happens to be profile #1.

    An empty profile list returns FALSE rather than TRUE. "No active profiles"
    means nobody is waiting for this work, and spending an LLM call per
    posting on their behalf is the more expensive way to be wrong.
    """
    if not cfgs:
        return "FALSE", {}

    clauses, params = [], {}
    for i, cfg in enumerate(cfgs):
        expr, p = tier_sql(cfg, table_alias, param_prefix=f"rel{i}")
        key = f"rel{i}_max_tier"
        clauses.append(f"({expr}) <= %({key})s")
        params[key] = max_tier(cfg)
        params.update(p)
    return "(" + " OR ".join(clauses) + ")", params
