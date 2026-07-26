"""Coordinates -> borough, by point-in-polygon.

WHY THIS EXISTS
    `borough` was populated for three of the six event sources and NULL for
    the rest, which made it useless as a filter: all 1,047 nyc_parks_events
    rows -- the best free public programming in the table -- carried NULL and
    so disappeared from any borough-scoped query. Ticketmaster and SeatGeek
    hardcode None for the same reason (their feeds report city/state, not
    borough), so the gap would have widened the moment those keys are added.

    Every one of those sources has coordinates. Boroughs are exactly five
    polygons. So this is a lookup, not a guess, and it belongs somewhere all
    of them can reach rather than in one normalizer.

    Sources that already know their own borough should keep saying so --
    NYPL partitions its own feed by locality and permitted_events carries an
    `event_borough` column. This is for the ones that don't.

PRECEDENCE
    A source-declared borough always wins. This resolves the residual.

BOUNDARY DATA
    NYC Open Data `gthc-hcne` (Borough Boundaries), five MultiPolygons in
    WGS84, refreshed at most every BOROUGH_REFRESH_DAYS. Borough lines do
    not move; the refresh exists so a bad load can heal rather than to track
    change. Stored as GEOMETRY, not GEOGRAPHY: ST_Contains is a planar
    predicate and the shapes are small enough that the projection error is
    far below the width of a street.

    Note the water caveat -- these are the *shoreline* boundaries, so a
    point in the harbor belongs to no borough and returns None. That is the
    honest answer; every venue we care about is on land.
"""

import json
import sys
from datetime import timedelta

from . import http
from .timeparse import utc_now, utc_now_str

BOROUGH_DATASET = "gthc-hcne"  # NYC Borough Boundaries -- verified to carry the_geom
BOROUGH_REFRESH_DAYS = 180

#: NYC Parks property IDs are borough-prefixed ("X045" = St. Mary's Park,
#: Bronx). Free and exact where present -- no geometry lookup needed.
PARK_ID_PREFIX_TO_BOROUGH = {
    "B": "Brooklyn", "M": "Manhattan", "Q": "Queens",
    "R": "Staten Island", "X": "Bronx",
}

#: Coordinate lookups repeat heavily within a run -- a library branch hosts
#: dozens of events -- and the answer cannot change mid-run.
_point_cache = {}


def ensure_borough_schema(conn):
    """Create the boundary table. Idempotent."""
    conn.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS borough_boundaries (
            borough TEXT PRIMARY KEY,
            geom GEOMETRY(MultiPolygon, 4326) NOT NULL,
            refreshed_at TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_borough_geom "
                 "ON borough_boundaries USING GIST(geom)")
    conn.commit()


def refresh_boroughs(conn, force=False, debug=False):
    """Load the five boundary polygons if they are missing or stale.

    Returns the number of rows written (0 when the cached copy is current).
    """
    row = conn.execute(
        "SELECT count(*), max(refreshed_at) FROM borough_boundaries").fetchone()
    count, refreshed_at = (row or (0, None))
    if count == 5 and refreshed_at and not force:
        if utc_now() - _parse_bookkeeping(refreshed_at) < timedelta(
                days=BOROUGH_REFRESH_DAYS):
            return 0

    url = (f"https://data.cityofnewyork.us/resource/{BOROUGH_DATASET}.json?"
           + http.urlencode({"$limit": 50, "$select": "boroname,the_geom"}))
    rows = http.get_json(url, timeout=120)

    written = 0
    for r in rows or ():
        name, geom = r.get("boroname"), r.get("the_geom")
        if not name or not geom:
            continue
        geojson = json.dumps(geom) if isinstance(geom, dict) else geom
        try:
            conn.execute(
                """
                INSERT INTO borough_boundaries (borough, geom, refreshed_at)
                VALUES (%s, ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)), %s)
                ON CONFLICT (borough) DO UPDATE SET
                    geom = EXCLUDED.geom,
                    refreshed_at = EXCLUDED.refreshed_at
                """,
                (name, geojson, utc_now_str()),
            )
            written += 1
        except Exception as e:
            if debug:
                print(f"[debug] borough geometry failed for {name!r}: {e}",
                      file=sys.stderr)
            conn.rollback()
    conn.commit()
    _point_cache.clear()

    if written and written != 5:
        print(f"[warn] borough_boundaries: loaded {written} of 5 boroughs -- "
              f"point lookups will return None inside the missing one(s).",
              file=sys.stderr)
    if debug:
        print(f"[debug] borough_boundaries: {written} polygons loaded",
              file=sys.stderr)
    return written


def borough_for_point(conn, latitude, longitude, debug=False):
    """The borough containing a coordinate, or None if it is outside NYC.

    None is a real answer, not an error: it means the point is in the water,
    in New Jersey, or mis-geocoded. Callers should store NULL rather than
    substituting a default -- a wrong borough is worse than a missing one.
    """
    if latitude is None or longitude is None:
        return None
    key = (round(float(latitude), 6), round(float(longitude), 6))
    if key in _point_cache:
        return _point_cache[key]

    try:
        row = conn.execute(
            """
            SELECT borough FROM borough_boundaries
            WHERE ST_Contains(geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
            LIMIT 1
            """,
            (key[1], key[0]),
        ).fetchone()
    except Exception as e:
        if debug:
            print(f"[debug] borough lookup failed for {key}: {e}", file=sys.stderr)
        return None

    result = row[0] if row else None
    _point_cache[key] = result
    return result


def borough_from_park_ids(park_ids):
    """Borough from an NYC Parks property ID list ("X045", "Q099, R046").

    Returns None when the field is absent or the prefix is unrecognised.
    A multi-park event takes the first entry: those are citywide series
    listed once per site, and the first is as good a label as any -- better
    than NULL, which drops the row out of every borough filter.
    """
    if not park_ids:
        return None
    first = str(park_ids).split(",")[0].strip()
    return PARK_ID_PREFIX_TO_BOROUGH.get(first[:1].upper()) if first else None


def _parse_bookkeeping(value):
    from datetime import datetime, timezone
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
