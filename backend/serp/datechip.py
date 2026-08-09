"""How far back a search asks, given when that query last ran.

MOVED HERE FROM ingest/google-serpapi.py:289 (choose_date_chip), which now
imports it. This is a MOVE, not a copy: the pipeline had one definition and
still has one. What it did not have was a way for anything other than that
script to reach it, which is why task 25's run_due() had no date policy at all
and would have re-fetched the same relevance-ranked page every night.

THE SECOND COPY IN THE REPO IS DELIBERATE AND STAYS. api/query_claims.py:576
holds its own, because ".claude/CLAUDE.md" says the three processes share only
schema.py and lib/ -- backend/api/ importing a pipeline module would break the
property that lets it run under its own venv with
include-system-site-packages = false. So there are two definitions on purpose,
in two processes, and this docstring is where that is written down.

WHY A CHIP AT ALL, AND WHY NOT ALWAYS "today"
    Google's default ranking is relevance-based, not chronological, so re-running
    the same query daily without a filter mostly re-fetches the same top results.
    The chip narrows each run to the window that actually elapsed for THAT
    query. A query that has never run gets no chip at all -- the deliberate
    backfill: take whatever Google currently shows, once.

VERIFIED, AND WORTH RE-VERIFYING BEFORE TRUSTING IT
    SerpApi's API reference marks both `chips` and `ltype` "deprecated by
    Google" with `uds` as the successor, while its Google Jobs guide still
    documents these values as current. Measured 2026-07-25 by
    tools/verify-date-filter.py: chips WORKS -- date_posted:today returned 10/10
    postings inside the window. That script costs ~3 SerpApi credits and is the
    instrument if the yield ever looks wrong.
"""

from datetime import datetime, timedelta, timezone

#: (window, chip). Ordered, and read in order -- the first window the elapsed
#: time fits inside wins. Data rather than an if-chain so that the boundaries
#: are visible as a set; Google accepts exactly these four values.
BUCKETS = (
    (timedelta(days=1), "today"),
    (timedelta(days=3), "3days"),
    (timedelta(days=7), "week"),
)
FALLBACK = "month"

TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S"


def choose(last_run_str, now=None):
    """The chip for a query last run at `last_run_str`, or None for never.

    None means NO FILTER, not "today" -- the backfill case above. An
    unparseable timestamp also returns None, which is the safe direction: the
    run costs the same credit either way and asking too broadly returns a
    superset, where asking too narrowly silently loses postings.
    """
    if not last_run_str:
        return None
    try:
        last_run = datetime.strptime(
            last_run_str, TIMESTAMP_FORMAT).replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None
    elapsed = (now or datetime.now(timezone.utc)) - last_run
    for window, chip in BUCKETS:
        if elapsed <= window:
            return chip
    return FALLBACK
