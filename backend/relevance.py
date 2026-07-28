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
    1  the posting looks right AND location is acceptable  -- score first
    2  the posting looks right, location is not/unknown    -- score next
    3  everything else                                     -- score only if
                                                              the budget
                                                              reaches it

    "Looks right" is title_include OR description_include. The second path
    exists because a whole class of role says nothing in the header and
    everything in the body: "Operations Coordinator" whose description is
    about running ChatGPT workflows is the same job as "AI Operations
    Coordinator", and a title regex cannot tell them apart. Both paths are
    subject to the same exclusions -- a description mentioning ChatGPT does
    not make an Account Executive posting wanted.
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
    "description_include": [],
    "title_exclude": [],
    "company_exclude": [],
    "platform_exclude": [],
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


def _include_groups(patterns):
    """Normalise an include list into a list of groups (AND of ORs).

    A flat list of strings is one group -- the historical shape, and still
    what every include list in config/relevance.json uses:

        ["engineer", "developer"]          ->  title ~* 'engineer|developer'

    A list of lists is several groups, and a row must match at least one term
    from EVERY group:

        [["chatgpt", "claude"], ["junior", "intern"]]
            ->  desc ~* 'chatgpt|claude' AND desc ~* 'junior|intern'

    WHY THE CONJUNCTION IS A LIST SHAPE AND NOT A LOOKAHEAD
        The same predicate can be written as one Postgres regex with
        lookahead constraints -- `^(?=[\\s\\S]*a)(?=[\\s\\S]*b)` -- and that
        was the first version. It was rejected for two reasons that have
        nothing to do with correctness. It defeats tools/relevance-report.py
        --dead, which tests one term at a time and is the only thing standing
        between this config and the \\y-vs-\\b landmine; a lookahead blob is a
        single untestable pattern. And it measured ~1.0s of sequential scan
        against 0.8s for the plain AND, because constraints force Postgres's
        backtracking engine.

    Mixing the two shapes in one list is rejected rather than guessed at: the
    two readings differ (OR vs AND), and picking one silently is how a filter
    ends up matching everything.
    """
    if not patterns:
        return []
    listish = [isinstance(p, (list, tuple)) for p in patterns]
    if all(listish):
        return [list(p) for p in patterns]
    if any(listish):
        raise ValueError(
            "relevance include lists must be all strings (one OR group) or "
            "all lists (AND of OR groups), not a mixture")
    return [list(patterns)]


def _include_sql(patterns, column, param_prefix, key, params):
    """AND-of-ORs predicate over one column, or None if there is nothing to say.

    The first group keeps the un-suffixed parameter name so that the common
    single-group case emits byte-identical SQL to the version of this module
    that had no groups at all. That identity is what makes "the author's
    profiles are unaffected" provable rather than hopeful; tests/test_relevance
    pins it.
    """
    clauses = []
    for group in _include_groups(patterns):
        alt = _alternation(group)
        if not alt:
            continue
        name = (f"{param_prefix}_{key}" if not clauses
                else f"{param_prefix}_{key}{len(clauses) + 1}")
        clauses.append(f"{column} ~* %({name})s")
        params[name] = alt
    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return "(" + " AND ".join(clauses) + ")"


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
    exclude = _alternation(cfg["title_exclude"])
    company_exclude = _alternation(cfg.get("company_exclude") or [])
    platform_exclude = _alternation(cfg.get("platform_exclude") or [])
    description_exclude = _alternation(cfg.get("description_exclude") or [])
    loc_cols = cfg["location_columns"]

    params = {}

    # Two ways in, OR'd. A posting is "relevant" if its title says so or its
    # body does; see the TIERS note at the top of the module for why the
    # second path exists. COALESCE on the body for the same reason as
    # description_exclude below: a NULL description must read as "did not
    # match", not poison the OR into NULL.
    include = _include_sql(cfg["title_include"], f"{a}.title",
                           param_prefix, "include", params)
    description_include = _include_sql(
        cfg.get("description_include") or [],
        f"COALESCE({a}.description_text, '')",
        param_prefix, "dincl", params)

    match_clauses = [c for c in (include, description_include) if c]
    if match_clauses:
        row_ok = (match_clauses[0] if len(match_clauses) == 1
                  else "(" + " OR ".join(match_clauses) + ")")
        # title_exclude gates BOTH paths, deliberately. The exclusion lists
        # encode "this role is not wanted whatever else the posting says", and
        # a body full of AI vocabulary does not make an Account Executive
        # requisition into an entry-level AI job -- it makes it an Account
        # Executive requisition at an AI company.
        if exclude:
            row_ok += f" AND {a}.title !~* %({param_prefix}_exclude)s"
            params[f"{param_prefix}_exclude"] = exclude
    else:
        row_ok = "TRUE"

    # Three exclusions that are about the POSTING's provenance rather than the
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
    #   platform_exclude    -- matched against the `platform` column, i.e. the
    #       SOURCE a row was ingested from rather than anything about the row.
    #       It exists because sources are not interchangeable across profiles:
    #       builtin/weworkremotely/hn_whoishiring are tech-company boards and
    #       carry real signal for a software profile, while a profile aimed at
    #       entry-level roles across all industries gets almost nothing from
    #       them. Per-profile rather than global for exactly that reason --
    #       dropping a source from one profile's gate must not delete it for
    #       another's.
    #
    # NOT USED, DELIBERATELY: "SerpApi's `via` field equals company_name".
    # It catches 160 rows but false-positives on every company that posts to
    # its own careers site -- via='Cisco Careers'/company='Cisco',
    # 'Snowflake Careers'/'Snowflake', Capital One, Deloitte, ServiceNow,
    # Citadel. Those are the BEST rows in the table. Measured before rejecting.
    if company_exclude:
        row_ok += f" AND {a}.company_name !~* %({param_prefix}_coexcl)s"
        params[f"{param_prefix}_coexcl"] = company_exclude
    if platform_exclude:
        row_ok += f" AND {a}.platform !~* %({param_prefix}_pfexcl)s"
        params[f"{param_prefix}_pfexcl"] = platform_exclude
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
