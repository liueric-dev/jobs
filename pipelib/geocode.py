"""Address -> coordinates, with a cache that can actually recover.

THE PROBLEM THIS REPLACES
    The old geocoder had failed 2,720 times against 127 successes -- a 95.5%
    failure rate that left 200 of 30,650 permitted events with coordinates.
    It was not an API problem. NYC's permitted-events feed does not carry
    street addresses; `event_location` is a *facility code*:

        "Chelsea Park: Soccer-01"
        "Riverside Park: Lawn-145th Street West-RSP"

    Nominatim cannot resolve those and never will, so every call was spent
    to learn nothing. Worse, each failure was written to `geocode_failed` and
    that table was consulted with no expiry -- `retry_count` was written but
    never read -- so it had become a permanent blocklist. Those 2,720
    addresses could not have recovered even after the parsing was fixed.

THE FIX -- resolve the park, not the facility
    Of the permitted-event rows worth keeping, 5,829 are "<Park>: <Facility>"
    and 712 are "X AVE between Y ST and Z ST". Splitting on the first colon
    and matching the park name against NYC Parks Properties (Socrata
    enfh-gkve, which carries a MultiPolygon per property) resolves 91.8% of
    the park-coded rows -- measured, not estimated -- with no rate-limited
    call at all. Nominatim is left to handle only the intersection-style
    minority.

    Name matching needs a little tolerance because the two datasets disagree
    on formatting: "Thomas Paine Park (Foley Square)" carries a parenthetical
    alias, "Park Of The Americas / Linden Park" is slash-joined, and
    "MontefioreSquarePark" is missing a space. candidates() generates those
    variants in order, with a tight-cutoff fuzzy match as a last resort.

NEGATIVE CACHING WITH A TTL
    Failures are still cached -- re-asking Nominatim about an unresolvable
    string every night is pointless -- but they now expire (FAILURE_TTL_DAYS)
    so a fixed parser or an upstream data correction can take effect.
"""

import json
import re
import sys
import time
import urllib.request
from datetime import timedelta

from . import dbconn, http
from .timeparse import utc_now, utc_now_str

PARKS_DATASET = "enfh-gkve"  # NYC Parks Properties -- verified to carry geometry
NOMINATIM_BASE = "https://nominatim.openstreetmap.org/search"
NOMINATIM_MIN_INTERVAL = 1.1  # their published policy is 1 req/sec
FAILURE_TTL_DAYS = 30
PARKS_REFRESH_DAYS = 30
FUZZY_CUTOFF = 0.92

_last_nominatim_call = 0.0


def nominatim_email():
    """Contact address, required by Nominatim's usage policy.

    The previous value was a fake example.com address. A real, monitored
    contact is the difference between being throttled and being blocked.
    """
    import os
    return os.environ.get("NOMINATIM_EMAIL", "")


# -- schema ------------------------------------------------------------------

def ensure_geocode_schema(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS geocode_cache (
            address TEXT PRIMARY KEY,
            latitude DOUBLE PRECISION NOT NULL,
            longitude DOUBLE PRECISION NOT NULL,
            geocoded_at TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'nominatim'
        )
    """)
    # display_name added later; backfilled on first Nominatim hit
    dbconn.add_missing_columns(conn, "geocode_cache", [("display_name", "TEXT")])
    conn.execute("""
        CREATE TABLE IF NOT EXISTS geocode_failed (
            address TEXT PRIMARY KEY,
            failed_at TEXT NOT NULL,
            error_msg TEXT,
            retry_count INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS park_locations (
            park_key TEXT PRIMARY KEY,
            signname TEXT,
            latitude DOUBLE PRECISION NOT NULL,
            longitude DOUBLE PRECISION NOT NULL,
            refreshed_at TEXT NOT NULL
        )
    """)
    conn.commit()


# -- park name matching ------------------------------------------------------

def normalize_name(s):
    """Lowercase, strip punctuation, collapse whitespace."""
    s = re.sub(r"[^\w\s]", " ", (s or "").lower())
    return re.sub(r"\s+", " ", s).strip()


def candidates(raw):
    """Normalized lookup keys for a park name, most-literal first.

    Handles the three formatting disagreements observed between the
    permitted-events feed and Parks Properties -- parenthetical aliases,
    slash-joined alternate names, and missing inter-word spaces.
    """
    base = (raw or "").strip()
    if not base:
        return
    seen = set()

    def emit(v):
        v = normalize_name(v)
        if v and v not in seen:
            seen.add(v)
            return v

    for value in (
        base,
        re.sub(r"\([^)]*\)", " ", base),                      # drop "(Foley Square)"
        *re.split(r"\s*/\s*", re.sub(r"\([^)]*\)", " ", base)),  # "A / B"
        re.sub(r"(?<=[a-z])(?=[A-Z])", " ", base),            # "SquarePark"
    ):
        got = emit(value)
        if got:
            yield got


def park_name_of(address):
    """The park portion of a "<Park>: <Facility>" location string."""
    if not address or ":" not in address:
        return None
    return address.split(":", 1)[0].strip()


def refresh_park_locations(conn, force=False, debug=False):
    """Populate `park_locations` from Parks Properties.

    Stores one interior point per property. ST_PointOnSurface, not
    ST_Centroid: the centroid of a concave or multi-part property (a park
    wrapping a lake, or split by a road) can land outside the park itself.
    """
    row = conn.execute("SELECT max(refreshed_at) FROM park_locations").fetchone()
    if row and row[0] and not force:
        age = utc_now() - _parse_bookkeeping(row[0])
        if age < timedelta(days=PARKS_REFRESH_DAYS):
            return 0

    inserted, offset = 0, 0
    while True:
        url = (f"https://data.cityofnewyork.us/resource/{PARKS_DATASET}.json?"
               + http.urlencode({"$limit": 5000, "$offset": offset,
                                 "$select": "signname,name311,multipolygon"}))
        batch = http.get_json(url, timeout=60)
        if not batch:
            break
        for r in batch:
            geom = r.get("multipolygon")
            if not geom:
                continue
            geojson = json.dumps(geom) if isinstance(geom, dict) else geom
            for name in (r.get("signname"), r.get("name311")):
                key = normalize_name(name)
                if not key:
                    continue
                try:
                    conn.execute(
                        """
                        INSERT INTO park_locations
                            (park_key, signname, latitude, longitude, refreshed_at)
                        SELECT %s, %s, ST_Y(p), ST_X(p), %s
                        FROM ST_PointOnSurface(ST_GeomFromGeoJSON(%s)) AS p
                        ON CONFLICT (park_key) DO UPDATE SET
                            latitude = EXCLUDED.latitude,
                            longitude = EXCLUDED.longitude,
                            refreshed_at = EXCLUDED.refreshed_at
                        """,
                        (key, name, utc_now_str(), geojson),
                    )
                    inserted += 1
                except Exception as e:
                    if debug:
                        print(f"[debug] park geometry failed for {name!r}: {e}",
                              file=sys.stderr)
                    conn.rollback()
        conn.commit()
        offset += 5000
        if len(batch) < 5000:
            break

    if debug:
        print(f"[debug] park_locations refreshed: {inserted} rows", file=sys.stderr)
    return inserted


#: Per-process memo of park-name -> (lat, lon) or None. The fuzzy fallback
#: is O(number of parks) per lookup, and a single ingest run resolves ~7,000
#: rows drawn from only ~420 distinct park names -- without this, every row
#: with an unmatchable name re-ran a 1,900-way comparison. Misses are cached
#: too, which is the case that actually mattered.
_park_memo = {}
_park_keys_cache = None


def _all_park_keys(conn):
    global _park_keys_cache
    if _park_keys_cache is None:
        _park_keys_cache = [r[0] for r in conn.execute(
            "SELECT park_key FROM park_locations").fetchall()]
    return _park_keys_cache


def _lookup_park(conn, raw_name):
    if raw_name in _park_memo:
        return _park_memo[raw_name]
    result = _lookup_park_uncached(conn, raw_name)
    _park_memo[raw_name] = result
    return result


def _lookup_park_uncached(conn, raw_name):
    keys = list(candidates(raw_name))
    if not keys:
        return None
    row = conn.execute(
        "SELECT latitude, longitude FROM park_locations "
        "WHERE park_key = ANY(%s) ORDER BY array_position(%s, park_key) LIMIT 1",
        (keys, keys),
    ).fetchone()
    if row:
        return float(row[0]), float(row[1])

    # Fuzzy last resort, tight cutoff -- a wrong park is worse than no park.
    import difflib
    all_keys = _all_park_keys(conn)
    for key in keys:
        match = difflib.get_close_matches(key, all_keys, n=1, cutoff=FUZZY_CUTOFF)
        if match:
            row = conn.execute(
                "SELECT latitude, longitude FROM park_locations WHERE park_key = %s",
                (match[0],)).fetchone()
            if row:
                return float(row[0]), float(row[1])
    return None


# -- the cache chain ---------------------------------------------------------

def _parse_bookkeeping(text):
    from datetime import datetime, timezone
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)


def _remember(conn, address, lat, lon, source, display_name=None):
    conn.execute(
        """
        INSERT INTO geocode_cache (address, latitude, longitude, geocoded_at, source, display_name)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (address) DO UPDATE SET
            latitude = EXCLUDED.latitude, longitude = EXCLUDED.longitude,
            geocoded_at = EXCLUDED.geocoded_at, source = EXCLUDED.source,
            display_name = COALESCE(EXCLUDED.display_name, geocode_cache.display_name)
        """,
        (address, lat, lon, utc_now_str(), source, display_name),
    )
    conn.execute("DELETE FROM geocode_failed WHERE address = %s", (address,))


def _remember_failure(conn, address, message):
    conn.execute(
        """
        INSERT INTO geocode_failed (address, failed_at, error_msg, retry_count)
        VALUES (%s, %s, %s, 1)
        ON CONFLICT (address) DO UPDATE SET
            failed_at = EXCLUDED.failed_at,
            error_msg = EXCLUDED.error_msg,
            retry_count = geocode_failed.retry_count + 1
        """,
        (address, utc_now_str(), (message or "")[:500]),
    )


def _failure_is_current(conn, address):
    row = conn.execute(
        "SELECT failed_at FROM geocode_failed WHERE address = %s", (address,)
    ).fetchone()
    if not row:
        return False
    try:
        return (utc_now() - _parse_bookkeeping(row[0])) < timedelta(days=FAILURE_TTL_DAYS)
    except ValueError:
        return False  # unparseable timestamp -> treat as expired, i.e. retry


def geocode(conn, address, *, allow_remote=True, debug=False):
    """Resolve `address` to (lat, lon), or (None, None).

    Order: positive cache -> park lookup (free, local) -> fresh negative
    cache -> Nominatim. The park lookup deliberately precedes the negative
    cache so the 2,720 addresses that failed under the old parser resolve
    immediately rather than waiting out a TTL.

    `conn` must be in autocommit mode -- cache writes have to survive
    independently of whatever transaction the caller is in. That coupling is
    why the old code needed a bare `conn.rollback()` before pruning: a failed
    geocode INSERT poisoned the caller's transaction.
    """
    if not conn or not address or not address.strip():
        return None, None
    address = address.strip()

    row = conn.execute(
        "SELECT latitude, longitude FROM geocode_cache WHERE address = %s",
        (address,)).fetchone()
    if row:
        return float(row[0]), float(row[1])

    park = park_name_of(address)
    if park:
        found = _lookup_park(conn, park)
        if found:
            _remember(conn, address, found[0], found[1], "nyc_parks_properties")
            if debug:
                print(f"[debug] park match {address!r} -> {found}", file=sys.stderr)
            return found

    if _failure_is_current(conn, address):
        if debug:
            print(f"[debug] geocode skipped (failed recently): {address!r}",
                  file=sys.stderr)
        return None, None

    if not allow_remote:
        return None, None

    lat, lon, _ = _nominatim(conn, address, debug=debug)
    return lat, lon


def geocode_with_address(conn, address, *, allow_remote=True, debug=False):
    """Resolve `address` to (lat, lon, display_name), or (None, None, None).

    Same resolution order as geocode() -- positive cache, park lookup,
    negative cache, Nominatim -- but also captures the formatted display
    name (street address string) when available from Nominatim or an
    earlier cached result.
    """
    if not conn or not address or not address.strip():
        return None, None, None
    address = address.strip()

    # Check cache for cached result including display_name.
    # If the cache entry has no display_name (e.g. from park_locations),
    # fall through to Nominatim rather than returning a partial result.
    row = conn.execute(
        "SELECT latitude, longitude, display_name, source FROM geocode_cache WHERE address = %s",
        (address,)).fetchone()
    if row:
        lat, lon, display_name, source = float(row[0]), float(row[1]), row[2], row[3]
        if display_name:
            return lat, lon, display_name
        # Cached coordinates but no display_name (pre-upgrade or
        # park_locations). Try Nominatim for the formatted address.
        if allow_remote:
            dn = _fetch_display_name(conn, address, debug=debug)
            if dn:
                _remember(conn, address, lat, lon, source, display_name=dn)
                return lat, lon, dn
        return lat, lon, None

    # Park lookup (no display_name available from this path)
    park = park_name_of(address)
    if park:
        found = _lookup_park(conn, park)
        if found:
            _remember(conn, address, found[0], found[1], "nyc_parks_properties")
            if debug:
                print(f"[debug] park match {address!r} -> {found}", file=sys.stderr)
            return found[0], found[1], None

    if _failure_is_current(conn, address):
        if debug:
            print(f"[debug] geocode skipped (failed recently): {address!r}",
                  file=sys.stderr)
        return None, None, None

    if not allow_remote:
        return None, None, None

    return _nominatim(conn, address, debug=debug)


def _fetch_display_name(conn, address, debug=False):
    """Call Nominatim for just the display_name, reusing coordinates cache.

    Nominatim results are still stored in geocode_cache (updating the
    display_name for any existing entry), but the caller discards the
    coordinates — they were already resolved via park_locations.
    """
    _, _, dn = _nominatim(conn, address, debug=debug)
    return dn


def _nominatim(conn, address, debug=False):
    global _last_nominatim_call

    email = nominatim_email()
    if not email:
        # Without a contact address this violates their usage policy, and
        # silently hammering them risks a block on the whole host.
        if debug:
            print("[debug] NOMINATIM_EMAIL unset -- skipping remote geocode",
                  file=sys.stderr)
        return None, None, None

    elapsed = time.monotonic() - _last_nominatim_call
    if elapsed < NOMINATIM_MIN_INTERVAL:
        time.sleep(NOMINATIM_MIN_INTERVAL - elapsed)
    _last_nominatim_call = time.monotonic()

    try:
        url = NOMINATIM_BASE + "?" + http.urlencode({
            "q": f"{address}, New York City, NY", "format": "json",
            "limit": "1", "email": email})
        req = urllib.request.Request(
            url, headers={"User-Agent": "hermes-nyc-events/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        if data:
            lat, lon = float(data[0]["lat"]), float(data[0]["lon"])
            display_name = data[0].get("display_name")
            _remember(conn, address, lat, lon, "nominatim", display_name=display_name)
            if debug:
                print(f"[debug] nominatim {address!r} -> ({lat}, {lon})"
                      f"  ({display_name})", file=sys.stderr)
            return lat, lon, display_name
        _remember_failure(conn, address, "no results")
        return None, None, None
    except Exception as e:
        _remember_failure(conn, address, str(e))
        if debug:
            print(f"[debug] nominatim error for {address!r}: {e}", file=sys.stderr)
        return None, None, None
