"""Provider answers on disk, so the same search is not bought twice in a day.

SHAPED AFTER evals/cache.py AND DELIBERATELY SO: atomic write-then-rename,
one level of fan-out, a `.gitignore` marker written by the store itself, and a
truncated file read as a miss rather than raised on. Those four are that file's
answers to problems this one has identically, and re-deriving them differently
would mean two stores with two sets of bugs.

WHAT DIFFERS, AND IT IS THE ONE THING THAT MATTERS
    evals/cache.py is content-addressed and its entries never expire: the same
    prompt to the same model is the same question forever. A SERP answer is a
    question about TODAY. So this store keys on the date and ALSO carries a
    TTL, which is belt-and-braces on purpose:

      the date in the KEY      makes yesterday's answer unreachable rather
                               than merely stale -- a miss, not a hit on
                               something old
      the TTL on the ENTRY     covers the seam. A run at 23:58 and a run at
                               00:02 are 4 minutes apart and land on two
                               different dates; without the TTL the second
                               buys a fresh copy of an answer 4 minutes old,
                               and with it the entry written yesterday is
                               still servable this side of midnight.

    They disagree in exactly one direction -- the TTL can serve across a date
    boundary, the date key cannot -- and the TTL wins, because the point is not
    to spend a metered credit on a question already answered.

THE KEY EXCLUDES THE API KEY, AND THAT IS A REQUIREMENT NOT AN OVERSIGHT
    23-serp-abstraction.md: "The API key is not part of the cache key ...
    rotating a credential must not discard a corpus of paid-for answers, and a
    key must never reach disk. It matters more here -- eight providers with
    rotating free-tier keys." The material below is the query, the location,
    the date chip, the provider and the date. Nothing else, and nothing secret.

WHAT IS IN THE KEY THAT A READER MIGHT NOT EXPECT
    The date_chip. Two searches for the same words with chips=today and
    chips=month are different questions with different answers, and sharing an
    entry between them would serve a one-day window to a query that asked for a
    month -- a silent under-fetch, which is this repo's failure mode wearing
    the cache's hat.
"""

import hashlib
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import searchnorm  # noqa: E402  (../searchnorm.py)

#: Beside evals/.cache for the same reason it gives: one `rm -rf` clears it and
#: no stray path needs documenting.
DEFAULT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")

#: 23-serp-abstraction.md's router step 1, verbatim: "Cache -- (normalized_query,
#: location, date), 24h TTL".
TTL_SECONDS = 24 * 60 * 60


def cache_dir():
    return os.environ.get("SERP_CACHE_DIR") or DEFAULT_DIR


def _today(now=None):
    return time.strftime("%Y-%m-%d", time.gmtime(now))


def key(text, location, *, date_chip=None, provider=None, now=None):
    """The digest for one search. Normalised, so spelling does not fragment it.

    searchnorm.normalize_query() is the SAME normaliser search_queries is keyed
    on (its UNIQUE is on the normalized pair), so "Software  Engineer" and
    "software engineer" are one cache entry for the same reason they are one
    row. Deriving a second normalisation here would let the table and the cache
    disagree about what one query is.
    """
    normalized_text, normalized_location = searchnorm.normalize_query(
        text, location)
    material = {
        "text": normalized_text,
        "location": normalized_location,
        "date_chip": date_chip or "",
        "provider": provider or "",
        "date": _today(now),
    }
    blob = json.dumps(material, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _path(digest):
    return os.path.join(cache_dir(), digest[:2], f"{digest}.json")


def get(digest, now=None):
    """The stored raw payload, or None for a miss, an expiry or a bad file."""
    try:
        with open(_path(digest), "r", encoding="utf-8") as fh:
            entry = json.load(fh)
    except (OSError, json.JSONDecodeError):
        # A truncated file from an interrupted write reads as a miss, which
        # costs one search. Raising would make one bad file poison every run
        # until someone deleted it by hand.
        return None
    stored_at = entry.get("stored_at")
    if not isinstance(stored_at, (int, float)):
        return None
    # `now if now is None else` rather than `now or time.time()`: an epoch of 0
    # is a legitimate instant and falsy, so the `or` idiom silently substitutes
    # the wall clock for the caller's argument. Found by the TTL test, which
    # passed for the wrong reason -- it stored at "now=0", got time.time(), and
    # therefore never aged.
    at = time.time() if now is None else now
    if at - stored_at > TTL_SECONDS:
        return None
    raw = entry.get("raw")
    return raw if isinstance(raw, list) else None


def put(digest, raw, *, now=None):
    """Store one provider payload. Written-then-renamed, never in place."""
    path = _path(digest)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    ensure_gitignored()
    payload = {"stored_at": time.time() if now is None else now, "raw": raw}
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False)
    os.replace(tmp, path)
    return raw


def ensure_gitignored():
    """`.cache/.gitignore` holding `*`, written by the store itself.

    evals/cache.py's reason applies unchanged and one more besides: these
    payloads are third-party job postings fetched from a metered account, and
    a posting's full text in git history is not a thing to do by accident.
    """
    root = cache_dir()
    os.makedirs(root, exist_ok=True)
    marker = os.path.join(root, ".gitignore")
    if not os.path.exists(marker):
        with open(marker, "w", encoding="utf-8") as fh:
            fh.write("*\n")


def stats():
    """(entries, bytes) currently stored."""
    count = total = 0
    for dirpath, _, names in os.walk(cache_dir()):
        for name in names:
            if name.endswith(".json"):
                count += 1
                try:
                    total += os.path.getsize(os.path.join(dirpath, name))
                except OSError:
                    pass
    return count, total
