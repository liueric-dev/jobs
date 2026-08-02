"""Provider payload -> the stored record shape. THE ONLY ROUTE, AND IT ADDS NOTHING.

WHY THIS FILE IS FOUR LINES OF LOGIC AND FIFTY OF COMMENT
    23-serp-abstraction.md: "Normalisation is an adapter, never a copy. The
    Google Jobs record shape is already frozen in lib/ -- commit 0c3ae51 ... A
    second definition appearing here would undo work that was deliberately done
    once." ".claude/CLAUDE.md" states the same as a prohibition: "Do not add a
    second definition of the Google Jobs record shape."

    google_jobs.py's own docstring records what the second, third and fourth
    copies cost when they existed: the API's copy truncated descriptions at
    5000 instead of 20000, could not parse "an hour ago" or "yesterday", sliced
    serialized JSON mid-string, and omitted posted_at_ts and salary_text. Two of
    those feed content_hash, so the same posting written by two paths produced
    two digests and each write counted the row as updated -- the row flip-
    flopped on alternating runs. So this module calls normalize_job and defines
    nothing.

THE ONE THING IT DOES DECIDE, AND WHY IT IS HERE RATHER THAN IN AN ADAPTER
    normalize_job(job, mode) takes a `mode` that config/google-queries.json
    carries per query ("nyc" or "remote") and search_queries does not have a
    column for. Its only effect is `location_is_remote`:

        is_remote = REMOTE_PATTERN.search(location or "") or mode == "remote"

    -- so mode is a statement about the SEARCH, standing in for a posting whose
    own location string does not say "remote" although the search asked for it.
    A search query's location is the only thing here that knows, so the mode is
    derived from it with text.REMOTE_PATTERN, the same predicate normalize_job
    applies to the posting. Deriving it with a second pattern would be the
    duplication this file exists to refuse, one level down.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google_jobs import normalize_job  # noqa: E402  (../google_jobs.py)
from lib import text  # noqa: E402

#: The two values normalize_job() distinguishes. Not an enum anywhere in the
#: repo -- config/google-queries.json spells them as bare strings and this
#: names them rather than adding a third spelling.
MODE_NYC = "nyc"
MODE_REMOTE = "remote"


def mode_for(location):
    """Which `mode` a search over `location` implies. See the module docstring."""
    if location and text.REMOTE_PATTERN.search(location):
        return MODE_REMOTE
    return MODE_NYC


def records(raw, location):
    """Every result normalised, in order. Raises on a result it cannot read.

    Deliberately NOT per-record tolerant. ingest/google-serpapi.py:395-405 (D19)
    already decided this shape once: a payload that does not normalise is a
    provider whose response SHAPE changed, not one bad row, and dropping the
    unreadable ones would report a thin night rather than a broken adapter.
    The caller releases the claim and counts the query as failed; the credit is
    spent either way.
    """
    mode = mode_for(location)
    return [normalize_job(job, mode) for job in raw]
