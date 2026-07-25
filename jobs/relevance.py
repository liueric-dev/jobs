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
    "location_columns": [],
    "max_tier_to_score": 3,
}


def load(path=None):
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


def tier_sql(cfg, table_alias="j"):
    """(sql_expression, params) computing the tier for a row.

    Built as SQL rather than evaluated in Python because the caller needs
    ORDER BY tier ... LIMIT n. Ranking in Python would mean fetching all
    11k candidate rows to choose 30 of them.
    """
    a = table_alias
    include = _alternation(cfg["title_include"])
    exclude = _alternation(cfg["title_exclude"])
    loc_cols = cfg["location_columns"]

    params = {}
    if include:
        title_ok = f"{a}.title ~* %(rel_include)s"
        params["rel_include"] = include
        if exclude:
            title_ok += f" AND {a}.title !~* %(rel_exclude)s"
            params["rel_exclude"] = exclude
    else:
        title_ok = "TRUE"

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

    sql = (f"CASE WHEN ({title_ok}) AND ({loc_ok}) THEN 1 "
           f"     WHEN ({title_ok}) THEN 2 "
           f"     ELSE 3 END")
    return sql, params


def max_tier(cfg):
    return int(cfg.get("max_tier_to_score", 3))
