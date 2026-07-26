#!/usr/bin/env python3
"""NYC Open Data events ingestion -- permitted events + parks events.

Pulls from Socrata, normalizes into the shared `events` schema, and upserts
into Postgres. Runs as a Hermes no-agent cron job.

    python3 events/nyc-events-ingest.py
    DEBUG_PRINT_KEYS=1 python3 events/nyc-events-ingest.py
    hermes cron run nyc-events-ingest

CONFIG
    DATABASE_URL             postgres connection string (pipelib.dbconn)
    NYC_OPENDATA_APP_TOKEN   optional; raises Socrata's rate limit
    NOMINATIM_EMAIL          contact address, required to geocode remotely

Mechanism (upsert, retry, hashing, watermarks) lives in pipelib; geocoding
and borough derivation are events-only, so they live alongside this script
in events/geocode.py and events/boroughs.py; the events table definition
lives in events/schema.py. What remains here is only what is specific to
these two Socrata datasets.

SOURCES
    permitted_events  tvpp-9vvx
    parks_events      w3wp-dpdi -- the live "Upcoming 14 Days" feed.
        fudw-fgrp ("Parks Events Listing") was checked and confirmed
        stale/archival -- confirmed-dated rows going back to 2015, nothing
        current -- so it is not a source.

WHAT WE KEEP FROM permitted_events -- three filters, all at normalize time
    This is a permit register, not an events listing. Most of what it
    contains is somebody reserving a space, and the distinction does not
    show up in any single field, so it takes three passes:

    1. DROPPED_CATEGORIES. `Sport - Youth` (15,538 rows) and `Sport - Adult`
       (8,699) were 79% of the feed -- youth-league field and court bookings
       with no URL, no description, and a location that is a court number
       rather than a place.

    2. DROPPED_TITLES. Category filtering alone left 88% of the survivors in
       one bucket, `Special Event`, and that bucket is where the private
       permits live: 2,438 rows titled exactly "Miscellaneous",
       "Celebration", "Picnic", "Barbecue" or "Party" -- 38% of the source.
       Whole-title match only, so "Picnic in the Park with the Philharmonic"
       survives while "Picnic" does not.

    3. CLOSURE_PATTERN. 152 rows are park *closures* ("Lawn Closures &
       maintenance", "Construction", "closed") -- the negation of an event.

    What survives is the genuinely public material: block parties, farmers
    markets, parades, street festivals, health fairs, concerts in the park.

    KNOWN LIMIT, not fixed here: this feed has no per-event URL and no free
    text, so even a real event from it cannot be clicked through to. That is
    upstream's gap, not a normalization bug -- see `description` below.

GEOCODING
    permitted_events carries no coordinates -- only free-text
    `event_location`, which is a facility code like "Chelsea Park:
    Soccer-01". The old approach fed that whole string to Nominatim and
    failed 95.5% of the time. events/geocode.py instead splits on the colon
    and resolves the park name against NYC Parks Properties, which covers
    91.8% of park-coded rows with no rate-limited call. See that module.

    KNOWN GAP, unchanged: `community_board` on this dataset does NOT match
    NYC's official community-district numbering (verified: values like
    "64"/"55" fall outside every borough's valid range). Don't join it
    against the community-district boundary file -- it will silently
    mislocate events. `borough` remains a valid coarse filter.

INCREMENTAL FETCHING -- three layers, so nothing is pulled twice
    0. Date window: every query is bounded to today <= date <= today +
       WINDOW_DAYS_AHEAD, expressed in NYC local time because that is what
       Socrata's own timestamps are. CONFIRMED NECESSARY: tvpp-9vvx without
       a lower bound returns its entire history back to 2013, and without an
       upper bound returns permits many months out.
    1. Server-side watermark: `:updated_at > '<last success>'`, a Socrata
       system field present on every dataset.
       CAVEAT: a dataset published by full nightly replace marks every row
       changed on every run, so this may not reduce the payload -- check
       with DEBUG_PRINT_KEYS=1 that counts drop after the first run.
    2. Client-side content hashing: a row is only written if its content
       actually changed, whatever :updated_at claims. Unchanged rows just
       get last_seen bumped.

    The watermark is only advanced on a COMPLETE fetch. Previously it was
    advanced even when paging hit the max_pages safety cap, so the rows past
    the cap were skipped and then permanently excluded by the next run's
    watermark filter.
"""

import json
import os
import sys
from datetime import timedelta

_d = os.path.dirname(os.path.abspath(__file__))
while _d != os.path.dirname(_d) and not os.path.isdir(os.path.join(_d, "pipelib")):
    _d = os.path.dirname(_d)
sys.path.insert(0, _d)

import boroughs  # noqa: E402  (events/boroughs.py)
import geocode  # noqa: E402  (events/geocode.py)
import schema  # noqa: E402
from pipelib import dbconn, http, state, text  # noqa: E402
from pipelib.timeparse import NYC, to_utc, utc_now_str  # noqa: E402
from pipelib.upsert import prune_expired, upsert  # noqa: E402

from datetime import datetime  # noqa: E402

APP_TOKEN = os.environ.get("NYC_OPENDATA_APP_TOKEN", "")
DEBUG = os.environ.get("DEBUG_PRINT_KEYS", "") == "1"
WINDOW_DAYS_AHEAD = 90

DATASETS = {"permitted_events": "tvpp-9vvx", "parks_events": "w3wp-dpdi"}

# The drop policy (DROPPED_CATEGORIES / DROPPED_TITLES / CLOSURE_PATTERN,
# behind schema.is_public_event) lives in schema.py because migrate.py needs
# the same predicate to delete rows admitted under an older rule. Keeping a
# second copy here is how the category list drifted last time.


def fetch_socrata(dataset_id, where_clauses=None, page_size=5000, max_pages=40):
    """Page through a Socrata dataset.

    Returns (rows, complete). `complete` is False when the max_pages safety
    valve tripped -- the caller must not advance its watermark in that case,
    or the unfetched remainder is excluded forever.

    $ORDER IS LOAD-BEARING, NOT COSMETIC. `$limit`/`$offset` without an
    ORDER BY has no defined row order, so Socrata is free to return a
    different arrangement for each page request -- which means a row can be
    served twice while another is never served at all. Paging this window
    unordered returned the right *count* (33,471) and the wrong *rows*:
    31,306 distinct keys, silently missing 2,165 of them, 6.5%. It looks
    healthy from every angle the script checks -- full pages, no error, a
    plausible total -- which is why it went unnoticed. Measured directly
    against tvpp-9vvx: with `$order=:id`, all 33,471 rows come back distinct.

    `:id` rather than a data column because it is a Socrata system field,
    guaranteed present and unique on every dataset, and stable across
    updates to the row's contents.
    """
    base = f"https://data.cityofnewyork.us/resource/{dataset_id}.json"
    headers = {"X-App-Token": APP_TOKEN} if APP_TOKEN else None
    rows, offset, pages = [], 0, 0

    while True:
        params = {"$limit": page_size, "$offset": offset, "$order": ":id"}
        if where_clauses:
            params["$where"] = " AND ".join(where_clauses)
        batch = http.get_json(f"{base}?{http.urlencode(params)}",
                              headers=headers, label=dataset_id)
        if not batch:
            return rows, True
        rows.extend(batch)
        pages += 1
        if DEBUG:
            print(f"[debug] {dataset_id} page {pages}: +{len(batch)} "
                  f"({len(rows)} total)", file=sys.stderr)
            if pages == 1:
                print(f"[debug] {dataset_id} keys: {sorted(batch[0].keys())}",
                      file=sys.stderr)
        if len(batch) < page_size:
            return rows, True
        if pages >= max_pages:
            print(f"[warn] {dataset_id}: hit max_pages={max_pages} "
                  f"({len(rows)} rows) -- stopping early and NOT advancing the "
                  f"watermark. The $where filter is probably not narrowing as "
                  f"expected.", file=sys.stderr)
            return rows, False
        offset += page_size


def normalize_permitted_event(row, geo_conn):
    """One permitted-event row, or None to drop it."""
    category = row.get("event_type") or row.get("eventtype")
    title = row.get("event_name") or row.get("eventname") or "Untitled event"
    if not schema.is_public_event(title, category):
        return None

    address = row.get("event_location") or row.get("eventlocation")
    start = row.get("start_date_time") or row.get("startdatetime")
    end = row.get("end_date_time") or row.get("enddatetime")
    lat, lon = geocode.geocode(geo_conn, address, debug=DEBUG) if geo_conn else (None, None)

    return schema.blank_record(
        source=schema.SOURCE_PERMITTED,
        source_id=row.get("event_id") or row.get("eventid"),
        title=title,
        # This feed carries no free text at all. The previous version stored
        # `category` here, which made description non-NULL for all 6,457 rows
        # while duplicating a field the row already has -- a populated column
        # that says nothing reads as data and hides the gap. NULL is honest.
        description=None,
        start_datetime=start,
        end_datetime=end,
        start_ts=to_utc(start),
        end_ts=to_utc(end),
        address=address,
        borough=row.get("event_borough") or row.get("eventborough"),
        latitude=lat,
        longitude=lon,
        categories=category,
        # This dataset has no per-event URL of any kind -- no website, no
        # listing page. The dataset's Open Data page is "where the dataset
        # lives", not "where this event came from", so linking it would be
        # misleading. Left NULL deliberately.
        source_url=None,
        raw_json=json.dumps(row),
    )


def normalize_parks_event(row, geo_conn=None):
    """One parks-event row.

    TIME OF DAY: `startdate` is authoritative for the DAY but is always
    midnight; `starttime` carries the real clock time but its own DATE is
    stale in every row measured (it appears to be the series' first
    occurrence). The previous version discarded `starttime` wholesale and so
    stored all 1,175 rows at midnight, losing time-of-day for the entire
    source. Combining the two -- day from `startdate`, clock from
    `starttime` -- recovers it.

    BOROUGH: this feed has no borough field, and every row here used to
    store NULL -- which quietly excluded the whole source, the best free
    programming in the table, from any borough-scoped query. `parkids` is
    borough-prefixed and covers 943 of 1,047 rows for free; the remainder
    are non-park venues (libraries, community gardens, health centers) with
    coordinates but no park ID, so they fall through to point-in-polygon.
    """
    start = _combine_day_and_clock(row.get("startdate"), row.get("starttime"))
    end = _combine_day_and_clock(row.get("enddate"), row.get("endtime"))

    lat = lon = None
    coords = row.get("coordinates")
    if coords:
        try:
            lat_s, lon_s = coords.split(",")
            lat, lon = float(lat_s.strip()), float(lon_s.strip())
        except (ValueError, AttributeError):
            pass

    borough = boroughs.borough_from_park_ids(row.get("parkids"))
    if not borough and geo_conn:
        borough = boroughs.borough_for_point(geo_conn, lat, lon, debug=DEBUG)

    link = row.get("link") or {}
    reg = row.get("registration_url") or {}
    # These are different things and both are worth keeping: link.url is the
    # event's page on nycgovparks.org, registration_url is where to book it.
    # An earlier version used link.url only as a fallback for registration,
    # so it was silently discarded whenever both existed -- the common case.
    return schema.blank_record(
        source=schema.SOURCE_PARKS,
        source_id=row.get("guid"),
        title=row.get("title"),
        # Stored raw, this field leaked its markup: 151 rows carried literal
        # "&amp;"/"&nbsp;", and stripping block tags without substituting a
        # space ran sentences together ("bike rental locations.For the
        # summer-long celebration"). strip_html unescapes first and replaces
        # each tag with whitespace, which fixes both.
        description=text.strip_html(row.get("description")),
        start_datetime=start,
        end_datetime=end,
        start_ts=to_utc(start),
        end_ts=to_utc(end),
        venue_name=row.get("parknames"),
        address=row.get("location"),
        borough=borough,
        latitude=lat,
        longitude=lon,
        categories=row.get("categories"),
        registration_url=reg.get("url"),
        source_url=link.get("url"),
        is_free=True,
        raw_json=json.dumps(row),
    )


def _combine_day_and_clock(day_field, clock_field):
    if not day_field:
        return None
    day = str(day_field)[:10]
    clock = str(clock_field)[11:19] if clock_field and len(str(clock_field)) >= 19 else None
    return f"{day}T{clock}.000" if clock else str(day_field)


def main():
    conn = dbconn.connect_or_exit("nyc-events ingest")
    schema.ensure_schema(conn)
    state.ensure_state_schema(conn)

    # Geocode writes need their own autocommit connection: they must survive
    # independently of the ingest transaction. Sharing one connection is why
    # the old code needed a bare rollback() before pruning -- a failed
    # geocode insert poisoned the caller's transaction.
    geo_conn = None
    try:
        geo_conn = dbconn.connect(autocommit=True)
        geocode.ensure_geocode_schema(geo_conn)
        geocode.refresh_park_locations(geo_conn, debug=DEBUG)
        boroughs.ensure_borough_schema(geo_conn)
        boroughs.refresh_boroughs(geo_conn, debug=DEBUG)
    except Exception as e:
        print(f"nyc-events: geocoding disabled ({e})", file=sys.stderr)
        geo_conn = None

    # Socrata's timestamps are naive NYC local, so the window bounds must be
    # too -- computing them in UTC skews the window by the offset.
    today_local = datetime.now(NYC).replace(hour=0, minute=0, second=0, microsecond=0)
    window = (today_local.strftime("%Y-%m-%dT00:00:00.000"),
              (today_local + timedelta(days=WINDOW_DAYS_AHEAD)).strftime("%Y-%m-%dT00:00:00.000"))

    run_started_at = utc_now_str()
    totals = {"new": 0, "updated": 0, "unchanged": 0}
    errors = []

    # parks_events needs geo_conn too now -- not to geocode (the feed carries
    # its own coordinates) but for the borough point-in-polygon fallback.
    jobs = [
        ("permitted_events", "start_date_time", normalize_permitted_event, geo_conn),
        ("parks_events", "startdate", normalize_parks_event, geo_conn),
    ]

    for key, date_field, normalizer, geo in jobs:
        try:
            where = [f"{date_field} >= '{window[0]}'", f"{date_field} <= '{window[1]}'"]
            since = state.get_watermark(conn, key)
            if since:
                where.append(f":updated_at > '{since}'")

            rows, complete = fetch_socrata(DATASETS[key], where_clauses=where)
            records = [r for r in (normalizer(row, geo) for row in rows) if r]
            dropped = len(rows) - len(records)

            result = upsert(conn, schema.SPEC, records, schema.make_event_id, debug=DEBUG)
            totals["new"] += result.new
            totals["updated"] += result.updated
            totals["unchanged"] += result.unchanged

            # Advance only on a fully successful pass. `complete` covers the
            # max_pages safety valve; result.errors covers rows that were
            # fetched but failed to write. Advancing past either would
            # exclude those rows from every future run's :updated_at filter.
            if complete and not result.errors:
                state.set_watermark(conn, key, run_started_at)
            if result.errors:
                errors.append(f"{key}: {len(result.errors)} row errors "
                              f"(e.g. {result.errors[0]})")
            if DEBUG:
                print(f"[debug] {key}: {len(rows)} fetched, {dropped} dropped, "
                      f"{result.new} new, {result.updated} updated, "
                      f"{result.unchanged} unchanged, complete={complete}",
                      file=sys.stderr)
        except Exception as e:
            errors.append(f"{key}: {e}")

    # Scoped to this script's own sources. Two of the three events scripts
    # used to run an unscoped DELETE and so deleted each other's rows.
    pruned = prune_expired(conn, schema.TABLE, schema.OPENDATA_SOURCES,
                           to_utc(today_local),
                           to_utc(today_local + timedelta(days=WINDOW_DAYS_AHEAD)))
    conn.close()
    if geo_conn:
        geo_conn.close()

    if errors:
        print(f"nyc-events ingest FAILED: {'; '.join(errors)}")
        print(f"Partial: {totals['new']} new, {totals['updated']} updated.")
        sys.exit(1)

    # Silent on quiet days -- the point of no-agent watchdog mode.
    if totals["new"] or totals["updated"] or pruned:
        print(f"nyc-events: {totals['new']} new, {totals['updated']} updated "
              f"({totals['unchanged']} unchanged), {pruned} past events pruned.")


if __name__ == "__main__":
    main()
