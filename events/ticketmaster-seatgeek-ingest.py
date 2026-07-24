#!/usr/bin/env python3
"""Ticketmaster + SeatGeek ingestion -- sliced, resumable, degrades gracefully.

Pulls NYC-area events from the Ticketmaster Discovery API and the SeatGeek
API into the shared `events` table (source = 'ticketmaster' / 'seatgeek').

    python3 events/ticketmaster-seatgeek-ingest.py
    DEBUG_PRINT_KEYS=1 python3 events/ticketmaster-seatgeek-ingest.py

CONFIG -- set whichever you have; either alone is fine
    DATABASE_URL           postgres connection string (see ~/.hermes/.env)
    TICKETMASTER_API_KEY   free at developer.ticketmaster.com
    SEATGEEK_CLIENT_ID     free at seatgeek.com/build

STATUS: neither key is currently configured, so this script has never
completed a run. Its cron job is paused deliberately rather than left to
fail every morning. With no key set it now reports the fact and exits 0 --
"not configured" is a different condition from "failed", the same
distinction the library script draws for a WAF block. Add a key and
re-enable the job with `hermes cron resume`.

WHY THIS IS STRUCTURED DIFFERENTLY FROM nyc-events-ingest.py

1. DATE SLICING, not one big query. Ticketmaster enforces deep-paging: you
   can only reach the 1000th result of any single query, and it does not
   error -- it just silently stops. A single "NYC, next 90 days, everything"
   query would plausibly exceed that and be truncated with no warning.
   Splitting into ~7-day slices keeps each query well under the ceiling.
   SeatGeek has no documented equivalent cap, but slicing costs nothing and
   keeps both sources structurally identical.

2. PER-PAGE CHECKPOINTING. The unit of retry is "the next page of the next
   incomplete slice", not "the whole dataset" -- ~13 slices x 2 sources, so
   a mid-run failure without checkpointing would redo a lot of work.

3. FRESHNESS-GATED SKIPPING. A slice completed within SLICE_FRESHNESS_HOURS
   is skipped *before* any API call, not deduped after one. Once today's
   data for a date range is in hand, tomorrow's run doesn't re-ask for it.

4. GRACEFUL DEGRADATION. One slice exhausting its retries is marked failed
   and the run moves on; the next run picks it back up (neither 'failed' nor
   'in_progress' counts as fresh). The script only exits non-zero if it
   could do nothing at all -- database unreachable.

FIXED IN THIS REVISION -- all four of these had never been exercised,
because the script could not connect to a database and so never ran:
  * set_progress() was called with `source` and `run_key` transposed on the
    deep-paging path, corrupting checkpoint state for every slice.
  * The DATABASE_URL default pointed at `nycevents:nycevents@…/nycevents`,
    a database that has never existed here.
  * upsert() had no per-record error isolation, unlike its two siblings, and
    the caller only guarded the HTTP call -- one malformed record would have
    aborted the entire run.
  * The prune was unscoped and compared TEXT, so it deleted other scripts'
    rows and removed date-only events on the morning they occurred.
"""

import json
import os
import sys
from datetime import timedelta

_d = os.path.dirname(os.path.abspath(__file__))
while _d != os.path.dirname(_d) and not os.path.isdir(os.path.join(_d, "pipelib")):
    _d = os.path.dirname(_d)
sys.path.insert(0, _d)

import schema  # noqa: E402
from pipelib import dbconn, http, state  # noqa: E402
from pipelib.timeparse import UTC, day_bounds_utc, to_utc  # noqa: E402
from pipelib.upsert import prune_expired, upsert  # noqa: E402

TICKETMASTER_API_KEY = os.environ.get("TICKETMASTER_API_KEY", "")
SEATGEEK_CLIENT_ID = os.environ.get("SEATGEEK_CLIENT_ID", "")
DEBUG = os.environ.get("DEBUG_PRINT_KEYS", "") == "1"

WINDOW_DAYS_AHEAD = 90
SLICE_DAYS = 7
SLICE_FRESHNESS_HOURS = 20

#: Ticketmaster refuses to page past the 1000th result of a query.
TM_RESULT_CEILING = 1000
TM_PAGE_SIZE = 199  # the API rejects size >= 200

NYC_LAT, NYC_LON = 40.7128, -74.0060
RADIUS_MILES = 25


def weekly_slices(start, end, days=SLICE_DAYS):
    slices, cursor = [], start
    while cursor < end:
        stop = min(cursor + timedelta(days=days), end)
        slices.append((cursor, stop))
        cursor = stop
    return slices


# ---------------------------------------------------------------- normalize

def normalize_ticketmaster(e):
    start_block = e.get("dates", {}).get("start", {})
    # dateTime is a real instant; localDate is a bare date. The old code
    # stored either as TEXT and compared them lexicographically, so a
    # localDate row sorted before local midnight of its own day and the
    # prune deleted it on the morning it happened.
    start = start_block.get("dateTime") or start_block.get("localDate")

    venues = e.get("_embedded", {}).get("venues", [])
    venue = venues[0] if venues else {}
    loc = venue.get("location") or {}
    try:
        lat = float(loc["latitude"]) if loc.get("latitude") else None
        lon = float(loc["longitude"]) if loc.get("longitude") else None
    except (TypeError, ValueError, KeyError):
        lat = lon = None

    categories = None
    classifications = e.get("classifications") or []
    if classifications:
        seg = (classifications[0].get("segment") or {}).get("name")
        genre = (classifications[0].get("genre") or {}).get("name")
        categories = " | ".join(x for x in (seg, genre) if x) or None

    url = e.get("url")
    return schema.blank_record(
        source=schema.SOURCE_TICKETMASTER,
        source_id=e.get("id"),
        title=e.get("name"),
        description=None,      # Discovery API has no reliable free-text field
        start_datetime=start,
        end_datetime=None,     # not reliably provided either
        start_ts=to_utc(start),
        end_ts=None,
        venue_name=venue.get("name"),
        address=(venue.get("address") or {}).get("line1"),
        borough=None,          # not reported -- only city/state
        latitude=lat,
        longitude=lon,
        categories=categories,
        registration_url=url,
        source_url=url,
        raw_json=json.dumps(e),
    )


def normalize_seatgeek(e):
    start = e.get("datetime_utc") or e.get("datetime_local")
    venue = e.get("venue") or {}
    loc = venue.get("location") or {}
    taxonomies = e.get("taxonomies") or []
    url = e.get("url")
    event_id = e.get("id")

    return schema.blank_record(
        source=schema.SOURCE_SEATGEEK,
        source_id=str(event_id) if event_id is not None else None,
        title=e.get("title"),
        description=None,
        start_datetime=start,
        end_datetime=None,
        # datetime_utc is already UTC; datetime_local is naive NYC.
        start_ts=to_utc(start, assume_tz=UTC) if e.get("datetime_utc") else to_utc(start),
        end_ts=None,
        venue_name=venue.get("name"),
        address=venue.get("address"),
        borough=None,
        latitude=loc.get("lat"),
        longitude=loc.get("lon"),
        categories=" | ".join(t.get("name") for t in taxonomies if t.get("name"))
                   or e.get("type"),
        registration_url=url,
        source_url=url,
        raw_json=json.dumps(e),
    )


# ---------------------------------------------------------------- fetching

def fetch_slice(conn, source, slice_start, slice_end):
    """Walk one date slice, resuming from its checkpoint.

    Returns (UpsertResult-ish totals, status).
    """
    run_key = f"{source}:{slice_start.date()}_{slice_end.date()}"
    if state.is_fresh(conn, run_key, SLICE_FRESHNESS_HOURS):
        return [0, 0, 0], "skipped_fresh"

    page = state.resume_page(conn, run_key,
                             start_page=0 if source == schema.SOURCE_TICKETMASTER else 1)
    totals = [0, 0, 0]

    while True:
        if source == schema.SOURCE_TICKETMASTER:
            if (page + 1) * TM_PAGE_SIZE > TM_RESULT_CEILING:
                print(f"[warn] {run_key}: reached Ticketmaster's {TM_RESULT_CEILING}-"
                      f"result ceiling; some events in this window are unreachable. "
                      f"Reduce SLICE_DAYS to narrow each query.", file=sys.stderr)
                state.complete_progress(conn, run_key, source, start_page=0)
                return totals, "ok"
            url, parser = _ticketmaster_request(slice_start, slice_end, page)
        else:
            url, parser = _seatgeek_request(slice_start, slice_end, page)

        try:
            data = http.get_json(url, label=run_key)
        except Exception as e:
            # Keep the cursor where it is so the next run resumes here.
            state.save_progress(conn, run_key, source, page, state.STATUS_FAILED,
                                slice_start.isoformat(), slice_end.isoformat())
            print(f"[error] {run_key} page {page} failed, will retry next run: {e}",
                  file=sys.stderr)
            return totals, "failed"

        events, is_last = parser(data, page)
        records = [normalize_ticketmaster(x) if source == schema.SOURCE_TICKETMASTER
                   else normalize_seatgeek(x) for x in events]
        res = upsert(conn, schema.SPEC, records, schema.make_event_id, debug=DEBUG)
        totals = [t + v for t, v in zip(totals, (res.new, res.updated, res.unchanged))]

        if DEBUG:
            print(f"[debug] {run_key} page {page}: {len(events)} events -> "
                  f"{res.new} new, {res.updated} upd, {res.unchanged} unch",
                  file=sys.stderr)

        if is_last:
            state.complete_progress(
                conn, run_key, source,
                start_page=0 if source == schema.SOURCE_TICKETMASTER else 1)
            return totals, "ok"

        page += 1
        state.save_progress(conn, run_key, source, page, state.STATUS_IN_PROGRESS,
                            slice_start.isoformat(), slice_end.isoformat())


def _ticketmaster_request(slice_start, slice_end, page):
    params = {
        "apikey": TICKETMASTER_API_KEY,
        "latlong": f"{NYC_LAT},{NYC_LON}", "radius": str(RADIUS_MILES),
        "unit": "miles",
        "startDateTime": slice_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "endDateTime": slice_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "size": TM_PAGE_SIZE, "page": page,
    }
    url = ("https://app.ticketmaster.com/discovery/v2/events.json?"
           + http.urlencode(params))

    def parse(data, page_no):
        events = data.get("_embedded", {}).get("events", [])
        total_pages = data.get("page", {}).get("totalPages", 1)
        return events, (not events or page_no + 1 >= total_pages)

    return url, parse


def _seatgeek_request(slice_start, slice_end, page):
    per_page = 200
    params = {
        "client_id": SEATGEEK_CLIENT_ID,
        "lat": str(NYC_LAT), "lon": str(NYC_LON), "range": f"{RADIUS_MILES}mi",
        "datetime_utc.gte": slice_start.strftime("%Y-%m-%dT%H:%M:%S"),
        "datetime_utc.lte": slice_end.strftime("%Y-%m-%dT%H:%M:%S"),
        "per_page": per_page, "page": page,
    }
    url = "https://api.seatgeek.com/2/events?" + http.urlencode(params)

    def parse(data, page_no):
        events = data.get("events", [])
        total = data.get("meta", {}).get("total", 0)
        return events, (not events or page_no * per_page >= total)

    return url, parse


# ---------------------------------------------------------------- main

def main():
    if not TICKETMASTER_API_KEY and not SEATGEEK_CLIENT_ID:
        # Not configured is not the same as failed. Exiting non-zero here is
        # what made this job report an error every morning.
        print("ticketmaster-seatgeek: neither TICKETMASTER_API_KEY nor "
              "SEATGEEK_CLIENT_ID is set -- nothing to do.", file=sys.stderr)
        return

    conn = dbconn.connect_or_exit("ticketmaster-seatgeek ingest")
    schema.ensure_schema(conn)
    state.ensure_state_schema(conn)

    window_start, window_end = day_bounds_utc(WINDOW_DAYS_AHEAD)
    slices = weekly_slices(window_start, window_end)

    totals = [0, 0, 0]
    failed, skipped = [], 0

    active = []
    if TICKETMASTER_API_KEY:
        active.append(schema.SOURCE_TICKETMASTER)
    if SEATGEEK_CLIENT_ID:
        active.append(schema.SOURCE_SEATGEEK)

    for source in active:
        for s_start, s_end in slices:
            got, status = fetch_slice(conn, source, s_start, s_end)
            totals = [t + v for t, v in zip(totals, got)]
            if status == "failed":
                failed.append(f"{source}:{s_start.date()}")
            elif status == "skipped_fresh":
                skipped += 1

    pruned = prune_expired(conn, schema.TABLE, schema.TICKETING_SOURCES,
                           window_start, window_end)
    conn.close()

    parts = []
    if totals[0] or totals[1]:
        parts.append(f"{totals[0]} new, {totals[1]} updated ({totals[2]} unchanged)")
    if skipped:
        parts.append(f"{skipped} slice(s) still fresh, skipped")
    if pruned:
        parts.append(f"{pruned} past events pruned")
    if failed:
        parts.append(f"{len(failed)} slice(s) failed, retry next run: "
                     f"{', '.join(failed)}")
    if parts:
        print("ticketmaster-seatgeek: " + "; ".join(parts) + ".")


if __name__ == "__main__":
    main()
