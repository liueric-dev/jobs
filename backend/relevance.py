"""Compile shared job-title and location filters for Workday's fetch gate.

Workday list responses are filtered before detail requests to keep that source
within a reasonable request budget. Every posting actually fetched is stored
as a raw normalized job; this module does not rank or score stored rows.
Patterns live in config/relevance.json and use PostgreSQL regex syntax.
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
    """Load the shared config, or normalize a supplied override for tests."""
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
    single-group case keeps stable SQL and parameter names. Tests pin the
    generated contract used by the Workday fetch gate.
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

    Built as SQL because Workday evaluates list-row eligibility in Postgres.
    param_prefix keeps bound names distinct when multiple configs are checked.
    """
    a = table_alias
    exclude = _alternation(cfg["title_exclude"])
    company_exclude = _alternation(cfg.get("company_exclude") or [])
    platform_exclude = _alternation(cfg.get("platform_exclude") or [])
    description_exclude = _alternation(cfg.get("description_exclude") or [])
    loc_cols = cfg["location_columns"]

    params = {}

    # Two ways in, OR'd. A posting is "relevant" if its title says so or its
    # body does. COALESCE on the body for the same reason as
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

    # Provenance exclusions are separate from title exclusions. A relisting
    # site's name or placeholder description does not identify the employer;
    # platform_exclude filters by source when explicitly configured.
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
