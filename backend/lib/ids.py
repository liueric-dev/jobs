"""Stable row identity and change detection.

Both pipelines derive a primary key by hashing a few identifying fields, and
detect "did this row actually change" by hashing the content fields. The
implementations were byte-identical across all nine scripts apart from which
fields went in, so both are parameterised here.

COMPATIBILITY REQUIREMENT -- these MUST produce byte-identical output to the
copies they replace. Both functions feed values that are already stored in
the database: `id` is the primary key of every existing row, and
`content_hash` decides whether a row counts as changed. If either digest
shifts, the first run after the migration re-keys or re-writes every row in
the table -- 40k spurious "new"/"updated" rows and a destroyed audit trail.

The compatibility hinge is str() semantics. The originals interpolated with
f-strings, so a None became the literal "None" and never an empty string:

    events:  f"{source}:{source_id or title}:{start or ''}"
    jobs:    f"{platform}:{token}:{source_id}"

`make_id` therefore does a plain str() on every part rather than normalising
None away. The `or title` / `or ''` fallbacks are caller-side and stay at
the call site, so events calls make_id(source, source_id or title, start or "").
tests/test_ids.py pins this against the original expressions.
"""

import base64
import hashlib
import json
import re
import urllib.parse
from collections.abc import Iterable, Mapping
from typing import Any

ID_LENGTH = 24


def make_id(*parts: Any, length: int = ID_LENGTH) -> str:
    """Stable primary key: sha256 of ":"-joined parts, truncated.

    Equivalent to the f-string interpolation the callers used before -- a
    None part becomes "None", not "". See the module docstring.
    """
    key = ":".join(str(p) for p in parts)
    return hashlib.sha256(key.encode()).hexdigest()[:length]


def content_hash(rec: Mapping[str, Any], fields: Iterable[str],
                  blank_if_falsy: Iterable[str] = ()) -> str:
    """Hash only the fields that represent real content.

    Deliberately excludes bookkeeping (raw_json, first_seen/last_seen,
    status) so unrelated metadata churn upstream doesn't register as a
    change -- a row whose hash is unchanged only gets its last_seen bumped.

    `fields` is an ordered tuple of keys into `rec`. Order and membership
    are part of the digest, so changing either is a breaking change to every
    stored hash. Each pipeline -- and in the jobs pipeline, each *source* --
    keeps its own tuple for exactly that reason; they are not interchangeable
    and were never meant to be unified.

    `blank_if_falsy` names keys that render as "" rather than "None" when
    absent. This is not a stylistic choice: the jobs scripts hashed
    `rec.get("description_text") or ""` while hashing every other field
    bare, so a row with no description hashed a "" there. Without this
    parameter every such row would re-hash and be rewritten on the first run
    after the migration.
    """
    parts = []
    for f in fields:
        if f in blank_if_falsy:
            parts.append(str(rec.get(f) or ""))
        else:
            parts.append(str(rec[f]))
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


# -- Google Jobs posting identity --------------------------------------------
#
# Google's `job_id` LOOKS like a stable posting id and is not one. It is a
# base64-encoded JSON blob carrying the search context that produced it:
#
#   {"job_title": ..., "company_name": ..., "htidocid": "5p69hxMzFmQrlLqiAAAAAA==",
#    "uule": ..., "gl": "us", "hl": "en", "fc": "EswBCowBQUpp...", "fcv": "3",
#    "fc_id": "5p69hxMzFmQrlLqiAAAAAA=="}
#
# `fc` is an opaque token that rotates on every *fresh* fetch from Google, and
# `hl`/`gl` are present or absent depending on the call. So hashing the raw
# blob mints a brand-new primary key for a posting already stored, every time.
#
# Measured on the live table before this was fixed: 837 google_jobs rows held
# only 632 distinct postings -- 32% inflation, one 15Five listing stored four
# times. The reason it wasn't obvious is SerpApi's 1h response cache: repeat
# runs inside the window replay the byte-identical payload and report 0 new,
# so `google_jobs_query_stats.new_count` was tracking cache expiry rather than
# job novelty, and the adaptive-cadence feature it was collected for would
# have been fitting noise.
#
# `htidocid` is the stable part and is strictly better than a
# (company, title, location) tuple: the 37 cases where one htidocid mapped to
# two tuples were all Google reporting a remote posting's location as
# "United States" on one search and "Anywhere" on another. The tuple splits
# those; htidocid correctly unifies them.

#: Tracking params that vary per search and must never reach the fingerprint.
#: Every Google Jobs apply link carries utm_campaign=google_jobs_apply.
_TRACKING_PARAMS = re.compile(r"^(utm_|gclid|fbclid|ref|source$)", re.I)


def decode_google_job_id(job_id: str | None) -> dict[str, Any] | None:
    """Google's base64 job_id blob as a dict, or None if it isn't one.

    Padding is restored explicitly -- Google strips trailing '=' and
    b64decode raises on unpadded input rather than coping with it.
    """
    if not job_id:
        return None
    try:
        padded = job_id + "=" * (-len(job_id) % 4)
        decoded = json.loads(base64.b64decode(padded))
    except ValueError:
        return None
    return decoded if isinstance(decoded, dict) else None


def normalize_apply_url(url: str | None) -> str:
    """Drop tracking params and the fragment, so one posting has one URL."""
    if not url:
        return ""
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return url
    kept = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query)
            if not _TRACKING_PARAMS.match(k)]
    return urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, parts.path.rstrip("/"),
         urllib.parse.urlencode(sorted(kept)), ""))


def google_source_id(job: Mapping[str, Any], company_token: str | None,
                      length: int = 16) -> str:
    """Stable `source_id` for one Google Jobs posting.

    `htidocid` when the blob yields one. Otherwise a content fingerprint over
    (company_token, title, normalized apply URL) -- deliberately NOT including
    location, since that is the field Google itself reports inconsistently for
    the same posting.

    Returns a string in both cases; the fingerprint is prefixed `fp:` so a
    row's identity source is legible in the database without re-deriving it.
    """
    decoded = decode_google_job_id(job.get("job_id"))
    if decoded and decoded.get("htidocid"):
        return decoded["htidocid"]

    apply_options = job.get("apply_options") or []
    url = (apply_options[0].get("link") if apply_options else None) or job.get("share_link")
    key = "|".join((
        str(company_token or ""),
        " ".join(str(job.get("title") or "").lower().split()),
        normalize_apply_url(url),
    ))
    return "fp:" + hashlib.sha256(key.encode()).hexdigest()[:length]
