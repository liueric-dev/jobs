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
import json
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
#: "3 days ago", "30+ days ago", and -- added 2026-07-26 -- "An Hour Ago",
#: "51 Minutes Ago". The bare a/an and minute alternatives only ADD matches for
#: inputs that previously returned None; every string that matched before still
#: parses to the same instant, which matters because posted_at feeds
#: content_hash for the Google Jobs sources.
RELATIVE_TIME_PATTERN = re.compile(
    r"(?:(\d+)\+?|\b(an?)\b)\s*(minute|hour|day|week|month)s?\s*ago",
    re.IGNORECASE,
)

#: Whole-day words Built In uses instead of a count. Kept separate from the
#: pattern above because they carry no number to multiply.
DAY_WORD_PATTERN = re.compile(r"\b(yesterday|today)\b", re.IGNORECASE)

#: An ISO-8601-ish leading date, which is what every source except Built In
#: already stores. Cheap discriminator for posted_at_timestamp().
ISO_DATE_PREFIX = re.compile(r"^\s*\d{4}-\d{2}-\d{2}")

#: Storage cap for description_text. Raised from 5000 on 2026-07-26: measured
#: over 400 Greenhouse postings, real text averages 6,269 chars (median 6,056,
#: p90 8,970, max 12,816), so 5000 captured only 75.6% of the text and cut off
#: 72% of rows mid-sentence. This is a DISPLAY cap, not a prompt budget --
#: extract.py and score.py each truncate to 3,000 independently before building
#: a prompt, so raising it costs disk (~70 MB across 11k rows) and no LLM spend.
MAX_DESCRIPTION_CHARS = 20000


def bounded_json(obj, limit, long_field="description"):
    """json.dumps(obj) kept under `limit` chars and still VALID JSON.

    `json.dumps(obj)[:limit]` is not this. Slicing serialized JSON cuts
    mid-string and produces a value json.loads cannot read at all -- the Google
    ingests did exactly that and 10 rows in the live table are unparseable
    stumps ending at character 20000. raw_json is meant to be the untouched
    original that anything needing precision falls back to (see this module's
    docstring), and jobs/migrate_ats_descriptions.py rebuilds descriptions from
    it, so "valid" is the whole point of storing it.

    Shrinking the single biggest field instead keeps the envelope -- ids,
    urls, company, dates, apply_options -- intact, which is the part worth
    keeping when a posting's prose is what blew the budget.
    """
    dumped = json.dumps(obj)
    if len(dumped) <= limit:
        return dumped
    if isinstance(obj.get(long_field), str):
        trimmed = dict(obj)
        overflow = len(dumped) - limit
        keep = max(0, len(trimmed[long_field]) - overflow - 20)
        trimmed[long_field] = trimmed[long_field][:keep]
        dumped = json.dumps(trimmed)
        if len(dumped) <= limit:
            return dumped
    # Nothing left to shrink without corrupting the structure. A valid
    # placeholder beats an invalid stump: the row still upserts, and the
    # marker says why the payload is not here.
    return json.dumps({"_truncated": True, "_original_chars": len(json.dumps(obj))})


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
    now = now or datetime.now(timezone.utc)

    m = RELATIVE_TIME_PATTERN.search(text)
    if m:
        # Either a count ("51 Minutes Ago") or a bare article ("An Hour Ago").
        n = int(m.group(1)) if m.group(1) else 1
        unit = m.group(3).lower()
        delta = {
            "minute": timedelta(minutes=n), "hour": timedelta(hours=n),
            "day": timedelta(days=n), "week": timedelta(weeks=n),
            "month": timedelta(days=n * 30),
        }[unit]
        return (now - delta).isoformat()

    # Built In writes "Yesterday" and "Today" (and "Reposted Yesterday")
    # instead of a count. Anchored to midnight rather than now-24h so two runs
    # on the same day agree: the point is a sortable day, and pretending to
    # know the hour would be a guess that also drifts between runs.
    word = DAY_WORD_PATTERN.search(text)
    if word:
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if word.group(1).lower() == "yesterday":
            midnight -= timedelta(days=1)
        return midnight.isoformat()

    return None


def posted_at_timestamp(value, now=None):
    """A sortable absolute timestamp for whatever a source put in posted_at.

    WHY THIS IS SEPARATE FROM THE posted_at COLUMN
        `posted_at` is TEXT and appears in every HASH_FIELDS_* tuple, so its
        stored format is frozen -- rewriting it re-hashes rows. It also holds
        three mutually incompatible formats: ISO from the ATS/RSS/HN sources,
        NULL from Google when the posting gave no date, and relative English
        from Built In ("Reposted 8 Hours Ago", "Yesterday"), which no database
        can sort.

        So this feeds a SECOND, unhashed column instead. Sorting "newest
        first" becomes possible without touching a hashed value, and Built In's
        relative strings are converted at write time rather than at read time
        by every consumer.

        Converting a relative phrase is stable in real terms even though it is
        recomputed each run: a posting that reads "10 Hours Ago" today reads
        "34 Hours Ago" tomorrow, and both resolve to the same instant. That is
        why this is safe to recompute and why it must NOT go in the hash --
        there it would churn on rounding alone.
    """
    if not value:
        return None
    if ISO_DATE_PREFIX.match(value):
        return value
    return parse_relative_posted_at(value, now=now)


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
