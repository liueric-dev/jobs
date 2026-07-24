"""Text heuristics shared by the jobs ingest scripts.

Every one of these was duplicated 4-6 times across jobs/ingest/*.py. The
regexes were verified byte-identical before consolidating (the only
difference found anywhere was a trailing comma in one copy of NYC_PATTERN).

The functions were NOT all identical, and assuming they were caused a real
regression: `strip_html` existed in two versions, one of which unescaped
HTML entities first. Unifying on the wrong one changed description_text and
therefore content_hash, reporting 217 of 242 weworkremotely rows as updated
when nothing upstream had changed. Hence the `unescape` parameter -- and
hence the rule that anything feeding a stored hash gets diffed across all
copies before it is merged, not assumed equivalent because the names match.

These are deliberately crude keyword heuristics, not classifiers. They exist
to make a listing filterable at a glance; `raw_json` always preserves the
untouched original for anything that needs to be precise.
"""

import html as html_module
import re
from datetime import datetime, timedelta, timezone

NYC_PATTERN = re.compile(
    r"\b(new york|nyc|manhattan|brooklyn|queens|bronx|staten island)\b",
    re.IGNORECASE,
)
REMOTE_PATTERN = re.compile(r"\bremote\b", re.IGNORECASE)
SENIOR_PATTERN = re.compile(
    r"\b(senior|sr\.?|staff|principal|director|vp\b|vice president|"
    r"head of|lead\b|chief|executive|manager)\b", re.IGNORECASE,
)
ENTRY_PATTERN = re.compile(
    r"\b(entry.?level|junior|jr\.?|new grad|graduate|intern(ship)?|"
    r"apprentice|associate|coordinator)\b", re.IGNORECASE,
)
RELATIVE_TIME_PATTERN = re.compile(
    r"(\d+)\+?\s*(hour|day|week|month)s?\s*ago", re.IGNORECASE,
)

MAX_DESCRIPTION_CHARS = 5000


def strip_html(markup, unescape=True):
    """Rough tag-stripper -- good enough for keyword heuristics and display,
    not meant to be a correct HTML parser. Truncated because raw_json
    preserves the untouched original for anything that needs it.

    `unescape` decodes HTML entities ("&amp;" -> "&") before stripping tags.
    It is parameterised because the six copies of this function had drifted:
    weworkremotely, google-serpapi and google-apify unescaped, ats did not.
    That difference is not cosmetic -- it changes description_text, which
    feeds content_hash, so unifying on either behaviour silently rewrites
    every row belonging to the sources that used the other one. (Measured:
    unifying on the ats variant reported 217 of 242 weworkremotely rows as
    updated when nothing upstream had changed.)

    True is the default because decoding entities is the correct behaviour
    and three of the four callers already did it. ats.py passes False to
    preserve its stored hashes; switching it costs a one-time rewrite of
    its rows and would be an improvement, just not a silent one.
    """
    if not markup:
        return None
    text = html_module.unescape(markup) if unescape else markup
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:MAX_DESCRIPTION_CHARS] if text else None


def slugify(text):
    text = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return text or "unknown"


def guess_seniority(title):
    if not title:
        return "unknown"
    if SENIOR_PATTERN.search(title):
        return "senior"
    if ENTRY_PATTERN.search(title):
        return "entry"
    return "mid_or_unspecified"


def classify_location(text):
    """(is_nyc, is_remote) for a free-text location string."""
    text = text or ""
    return bool(NYC_PATTERN.search(text)), bool(REMOTE_PATTERN.search(text))


def parse_relative_posted_at(text, now=None):
    """Convert Google's relative phrasing ("3 days ago") to a timestamp.

    SerpApi and Apify both return the relative form rather than an absolute
    date. Anything without an exact anchor ("30+ days ago") returns None
    rather than a guess.

    NOTE: the returned format is datetime.isoformat() -- with microseconds
    and a +00:00 offset -- which differs from the bare utc_now_str() format
    used for first_seen/last_seen. That inconsistency is preserved
    deliberately: `posted_at` is part of the jobs content_hash, so changing
    its formatting would mark every affected row as changed.
    """
    if not text:
        return None
    m = RELATIVE_TIME_PATTERN.search(text)
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2).lower()
    delta = {
        "hour": timedelta(hours=n), "day": timedelta(days=n),
        "week": timedelta(weeks=n), "month": timedelta(days=n * 30),
    }[unit]
    return ((now or datetime.now(timezone.utc)) - delta).isoformat()


def days_since(timestamp_str, now=None):
    """Fractional days since a bookkeeping timestamp, or None if unparseable."""
    if not timestamp_str:
        return None
    try:
        then = datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%S").replace(
            tzinfo=timezone.utc)
    except ValueError:
        return None
    return ((now or datetime.now(timezone.utc)) - then).total_seconds() / 86400
