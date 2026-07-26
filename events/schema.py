"""The `public.events` table -- DDL, column spec, and shared constants.

Owned by the events pipeline, deliberately NOT by pipelib: pipelib provides
mechanism (upsert, retry, hashing, checkpoints) and knows nothing about what
an event is. This module is the single definition the three ingest scripts
and migrate.py all share, replacing three separately-drifting copies of
ensure_schema().

TIMESTAMP COLUMNS -- two generations, on purpose
    start_datetime/end_datetime (TEXT) hold the value exactly as the source
    gave it. They are kept, unparsed, because they are what content_hash
    hashes: every stored hash was computed over these strings, so removing
    or rewriting them would mark all ~40,000 rows as changed on the next run.
    They are also the only record of what upstream actually said, which
    matters when a source silently changes format.

    start_ts/end_ts (TIMESTAMPTZ) hold the canonical instant, and are what
    every query, window filter and prune should use. See pipelib.timeparse
    for why the TEXT columns cannot be compared across sources.
"""

import re

from pipelib import dbconn, ids
from pipelib.upsert import GEOG_EXPR, TableSpec

TABLE = "events"

#: Every source this pipeline owns. prune_expired() requires an explicit
#: list -- two scripts previously ran unscoped deletes and wiped each
#: other's rows on every run.
SOURCE_PERMITTED = "nyc_permitted_events"
SOURCE_PARKS = "nyc_parks_events"
SOURCE_NYPL = "nypl_events"
SOURCE_QPL = "qpl_events"
SOURCE_TICKETMASTER = "ticketmaster"
SOURCE_SEATGEEK = "seatgeek"

OPENDATA_SOURCES = (SOURCE_PERMITTED, SOURCE_PARKS)
LIBRARY_SOURCES = (SOURCE_NYPL, SOURCE_QPL)
TICKETING_SOURCES = (SOURCE_TICKETMASTER, SOURCE_SEATGEEK)

# ---------------------------------------------------------------------------
# What counts as a public event, for `nyc_permitted_events`
#
# This lives here, not in the ingest script, because migrate.py needs the
# same predicate to clean up rows admitted under an older rule -- and it
# already kept its own drifting copy of the category list. One definition,
# two callers: the ingest filters at normalize time, the migration deletes
# what is already stored. If they disagree, the pipeline re-admits on every
# run exactly what the migration just deleted.
#
# tvpp-9vvx is a permit register. A permit becomes a public event only by
# accident of what it is for, and no single field says which -- hence three
# tests rather than one. Each was measured against live rows; see the module
# docstring in nyc-events-ingest.py for the counts.
# ---------------------------------------------------------------------------

#: Facility reservations and stagehand logistics. 79% of the raw feed.
DROPPED_CATEGORIES = frozenset({
    "Sport - Youth", "Sport - Adult", "Theater Load in and Load Outs",
})

#: Private permits wearing a public label -- someone's own barbecue, wedding
#: or birthday in a reservable park space, with no description, no URL and
#: no venue. 2,438 of 6,457 surviving rows.
#:
#: Matched on the WHOLE title, case-folded, never as a substring: "Picnic"
#: is a private reservation, "Picnic in the Park with the Philharmonic" is a
#: real event and must survive.
DROPPED_TITLES = frozenset({
    "miscellaneous", "celebration", "picnic", "barbecue", "bbq", "party",
    "wedding", "wedding ceremony", "birthday", "birthday party",
    "family reunion", "reunion", "gathering", "other", "n/a", "tbd",
})

#: Park closures -- the negation of an event. All 152 live matches were
#: reviewed individually; there were no false positives.
CLOSURE_PATTERN = re.compile(
    r"construction|closure|closed|maintenance|repair|renovation", re.IGNORECASE)


def is_public_event(title, category):
    """False for permit records that are not events anyone can attend."""
    if category in DROPPED_CATEGORIES:
        return False
    title = (title or "").strip()
    return not (title.lower() in DROPPED_TITLES or CLOSURE_PATTERN.search(title))


#: Fields hashed for change detection. ORDER AND MEMBERSHIP ARE FROZEN --
#: these digests are stored in events.content_hash. Verified byte-identical
#: against 2,982 live rows during the pipelib migration. Note start_ts is
#: absent: it is derived from start_datetime, so including it would be
#: redundant and would invalidate every stored hash.
HASH_FIELDS = (
    "title", "description", "start_datetime", "end_datetime",
    "venue_name", "address", "borough", "categories",
    "is_free", "registration_url", "source_url",
    "latitude", "longitude",
)

#: Columns written from a normalized record.
COLUMNS = (
    "source", "source_id", "title", "description",
    "start_datetime", "end_datetime", "start_ts", "end_ts",
    "venue_name", "address", "borough", "latitude", "longitude",
    "categories", "is_free", "registration_url", "source_url", "raw_json",
)

SPEC = TableSpec(
    table=TABLE,
    columns=COLUMNS,
    hash_fields=HASH_FIELDS,
    computed={"geog": GEOG_EXPR},
)


def make_event_id(rec):
    """Primary key for an event row.

    Reproduces the original expression exactly --
        f"{source}:{source_id or title}:{start_datetime or ''}"
    -- so existing primary keys are preserved. The `or` fallbacks stay at
    the call site because they are events-specific policy, not hashing.
    """
    return ids.make_id(
        rec["source"],
        rec.get("source_id") or rec.get("title"),
        rec.get("start_datetime") or "",
    )


def blank_record(**overrides):
    """A normalized record with every column present.

    Normalizers build on this so a missing key becomes an explicit NULL
    rather than a KeyError mid-batch -- and so content_hash sees a stable
    field set no matter which source produced the row.
    """
    rec = {col: None for col in COLUMNS}
    rec.update(overrides)
    return rec


def ensure_schema(conn):
    """Create or patch the events schema. Idempotent; safe to run from any
    of the ingest scripts or from migrate.py, in any order.

    CREATE TABLE IF NOT EXISTS is a no-op on an existing table -- it does
    NOT add new columns -- so anything introduced after the first revision
    needs an explicit ALTER, which is what the second block does.
    """
    conn.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            source_id TEXT,
            title TEXT,
            description TEXT,
            start_datetime TEXT,
            end_datetime TEXT,
            start_ts TIMESTAMPTZ,
            end_ts TIMESTAMPTZ,
            venue_name TEXT,
            address TEXT,
            borough TEXT,
            latitude DOUBLE PRECISION,
            longitude DOUBLE PRECISION,
            geog GEOGRAPHY(Point, 4326),
            categories TEXT,
            is_free BOOLEAN,
            registration_url TEXT,
            source_url TEXT,
            raw_json TEXT,
            content_hash TEXT,
            first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL
        )
    """)
    conn.commit()
    # Catalog-checked: a bare ADD COLUMN IF NOT EXISTS still takes an ACCESS
    # EXCLUSIVE lock even when it changes nothing, which made every run
    # contend with ordinary readers. See dbconn.add_missing_columns.
    dbconn.add_missing_columns(conn, TABLE, [
        ("start_ts", "TIMESTAMPTZ"),
        ("end_ts", "TIMESTAMPTZ"),
        ("geog", "GEOGRAPHY(Point, 4326)"),
        ("content_hash", "TEXT"),
        ("source_url", "TEXT"),
    ])

    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_start ON events(start_datetime)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_start_ts ON events(start_ts)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_source ON events(source)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_geog ON events USING GIST(geog)")
    conn.commit()
