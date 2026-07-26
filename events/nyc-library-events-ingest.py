#!/usr/bin/env python3
"""NYC library events ingestion -- NYPL + Queens Public Library.

Pulls upcoming programs, normalizes into the shared `events` schema, and
upserts into Postgres. Runs as a Hermes no-agent cron job alongside
nyc-events-ingest.py.

    python3 events/nyc-library-events-ingest.py
    DEBUG_PRINT_KEYS=1 python3 events/nyc-library-events-ingest.py

Brooklyn Public Library is deliberately NOT included -- bklynlibrary.org
blocks bots outright (robots.txt bans scrapers/GPTBot, direct fetches return
403), and its BiblioCommons/BiblioEvents platform only issues API keys to
institutional partners. There is no unauthenticated path in, unlike NYPL/QPL.

SOURCES -- both unofficial, found by reading each site's own frontend JS.
Neither library publishes a documented public events API.

    NYPL: POST https://scout.nypl.org/api/graphql (CalendarEventList).
    nypl.org itself sits behind an Incapsula WAF that blocks plain HTTP
    clients, but the underlying scout.nypl.org endpoint is open -- no auth,
    no rate limiting observed, CORS-open. Its robots.txt disallows
    everything, which reads as generic Drupal boilerplate rather than a
    deliberate signal about this endpoint, but it is still unsanctioned;
    treat it as liable to change without notice. Paginated via a
    `userQueryString` of "locality=<borough>&page=<n>", fetched once per
    borough so each event's locality filter doubles as its borough label
    (confirmed: the three per-borough totals sum exactly to the unfiltered
    total, so the partition is clean).

    QPL: GET https://www.queenslibrary.org/search/call?...&pageParam=<n>
    -- the same endpoint the site's own "Load More" button calls
    (reverse-engineered from qbpl_solr/js/searchBlock.js). Each result card
    embeds a full JSON payload in an inline `arrJsonData_cal['<id>'] = '{…}'`
    script tag, so no HTML-field scraping is needed.

    IMPORTANT: queenslibrary.org sits behind a WAF that returns HTTP 200
    with a "Request Rejected" body when it decides a client is abusive --
    observed firsthand after ~30 rapid requests. It also requires session
    cookies from an initial GET to /calendar before /search/call serves real
    data. QPL fetching is therefore deliberately slow (SLEEP_QPL between
    every request) and treats a rejection body as retryable, distinct from a
    legitimately empty results page.

    NOTE: queens.libnet.info (a Communico/Evanced calendar QPL also has
    live) was investigated first and looked more promising on paper
    (unauthenticated JSON/RSS, real branch data) but its events endpoints
    consistently returned zero results -- it appears to be an inactive
    parallel instance. The Drupal search endpoint above is the one that
    actually returns current events, verified end to end.

FREE-NESS: NYPL and QPL programs are free to the public by policy. Neither
source exposes a per-event fee field and none is needed; is_free is True
unconditionally for both.

WHY A BLOCKED QPL NO LONGER FAILS THE JOB
    Previously a WAF block after the retry budget raised, so the whole job
    exited 1 -- and because QPL runs second, a block meant the run was
    reported as a failure even though NYPL had already ingested thousands of
    events successfully. That is exactly what the last scheduled run did.
    Since progress is checkpointed per page and resumed next run, a block is
    a *partial success*, not an error: it is reported on stderr and the job
    exits 0. A genuine failure (NYPL down, database unreachable) still
    exits 1.

RESUMABILITY
    Neither source offers a cheap "only what changed" filter, so a full run
    walks every page of every source. pipelib.state records the next page per
    job (NYPL is 3 jobs, one per borough; QPL is 1). Each page's upserts are
    committed and the cursor advanced immediately, so a run killed on page 40
    resumes at 40 rather than re-walking 1..39. On clean completion the
    cursor rewinds to the start page.
"""

import html
import json
import os
import re
import sys
import time
import http.cookiejar
import urllib.request

_d = os.path.dirname(os.path.abspath(__file__))
while _d != os.path.dirname(_d) and not os.path.isdir(os.path.join(_d, "pipelib")):
    _d = os.path.dirname(_d)
sys.path.insert(0, _d)

import schema  # noqa: E402
from pipelib import dbconn, geocode, http as phttp, state  # noqa: E402
from pipelib.timeparse import day_bounds_utc, to_utc, utc_now_str  # noqa: E402
from pipelib.upsert import prune_expired, upsert  # noqa: E402

DEBUG = os.environ.get("DEBUG_PRINT_KEYS", "") == "1"
WINDOW_DAYS_AHEAD = 90

USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

NYPL_GRAPHQL_URL = "https://scout.nypl.org/api/graphql"
NYPL_QUERY = """
query CalendarEventList($adminFilters: AdminFilters, $userQueryString: String) {
  calendarEventList(adminFilters: $adminFilters, userQueryString: $userQueryString) {
    items {
      title slug date { timeStart timeEnd } summary
      audienceInterest series locations { name externalLocation }
      registration { method }
    }
    pageInfo { pageCount }
  }
}
"""
# GraphQL `locality` filter value -> the borough label we store.
NYPL_BOROUGHS = {"Bronx": "Bronx", "New York": "Manhattan",
                 "Staten Island": "Staten Island"}
NYPL_MAX_PAGES = 500  # safety valve; the true bound is pageInfo.pageCount
NYPL_FRESHNESS_HOURS = 20  # skip a borough that completed recently
SLEEP_NYPL = 0.1      # polite pacing; no rate limiting observed

# Static fallback for NYPL venues that Nominatim can't resolve by name.
# Last verified 2026-07-25 against nypl.org/locations.
NYPL_ADDRESS_MAP = {
    "Stavros Niarchos Foundation Library (SNFL)": "476 5th Ave, New York, NY 10018",
    "Thomas Yoseloff Business Center": "20 W 53rd St, New York, NY 10019",
    "Inwood Library–Joseph and Sheila Rosenblatt Building": "4790 Broadway, New York, NY 10034",
    "Van Cortlandt Library, Arline Schwarzman Building": "601 W 231st St, Bronx, NY 10463",
    "Harry Belafonte 115th Street Library": "203 W 115th St, New York, NY 10026",
    "Hunts Point Library": "877 Southern Blvd, Bronx, NY 10459",
    "Pelham Bay Library": "3060 Middletown Rd, Bronx, NY 10461",
    "The New York Public Library for the Performing Arts": "40 Lincoln Center Plaza, New York, NY 10023",
}

QPL_CALENDAR_URL = ("https://www.queenslibrary.org/calendar"
                    "?searchField=*&category=calendar&fromlink=calendar")
QPL_SEARCH_CALL_URL = ("https://www.queenslibrary.org/search/call"
                       "?searchField=*&category=calendar&pageParam={page}&searchFilter=")
QPL_MAX_PAGES = 500
SLEEP_QPL = 2.0       # deliberately slow -- the WAF blocks bursty clients
QPL_MAX_RETRIES = 4

ARR_JSON_RE = re.compile(r"arrJsonData_cal\['[^']+'\]\s*=\s*'(.*?)';", re.DOTALL)


class WafBlocked(Exception):
    """QPL's WAF rejected us. Retryable next run, not a job failure."""


# ---------------------------------------------------------------- NYPL

def nypl_fetch_page(locality, page):
    payload = {"operationName": "CalendarEventList", "query": NYPL_QUERY,
               "variables": {"adminFilters": {},
                             "userQueryString": f"locality={locality}&page={page}"}}
    data = phttp.post_json(NYPL_GRAPHQL_URL, payload, label=f"nypl/{locality}")
    if "errors" in data:
        raise RuntimeError(f"NYPL GraphQL error: {data['errors']}")
    return data["data"]["calendarEventList"]


def normalize_nypl_event(item, borough_label, geo_conn):
    locations = item.get("locations") or []
    loc = locations[0] if locations else {}
    venue_name = loc.get("name") or loc.get("externalLocation") or None

    date_block = item.get("date") or {}
    start_ts = to_utc(date_block.get("timeStart"))
    end_ts = to_utc(date_block.get("timeEnd"))

    lat = lon = address_str = None
    if geo_conn and venue_name and loc.get("externalLocation") != "Virtual":
        lat, lon, address_str = geocode.geocode_with_address(
            geo_conn, f"{venue_name}, New York, NY", debug=DEBUG)
    # Static fallback for venues Nominatim can't resolve
    if not address_str and venue_name:
        address_str = NYPL_ADDRESS_MAP.get(venue_name)

    tags = list(item.get("audienceInterest") or []) + list(item.get("series") or [])
    categories = ", ".join(dict.fromkeys(tags)) or None  # dedupe, keep order

    source_url = "https://www.nypl.org" + item["slug"] if item.get("slug") else None
    reg_method = (item.get("registration") or {}).get("method")

    return schema.blank_record(
        source=schema.SOURCE_NYPL,
        source_id=item.get("slug"),
        title=item.get("title"),
        description=item.get("summary"),
        # The TEXT columns keep the ISO form this source has always stored;
        # content_hash is computed over them, so they must stay stable.
        start_datetime=start_ts.isoformat() if start_ts else None,
        end_datetime=end_ts.isoformat() if end_ts else None,
        start_ts=start_ts,
        end_ts=end_ts,
        venue_name=venue_name,
        address=address_str,  # resolved from geocode display_name
        borough=borough_label,
        latitude=lat,
        longitude=lon,
        categories=categories,
        is_free=True,
        registration_url=source_url if reg_method and reg_method != "none" else None,
        source_url=source_url,
        raw_json=json.dumps(item),
    )


def run_nypl(conn, geo_conn, window_end):
    totals = [0, 0, 0]
    for locality, borough in NYPL_BOROUGHS.items():
        run_key = f"nypl_events:{locality}"
        if state.is_fresh(conn, run_key, NYPL_FRESHNESS_HOURS):
            if DEBUG:
                print(f"[debug] nypl/{borough}: skipped (completed "
                      f"{NYPL_FRESHNESS_HOURS}h freshness window)",
                      file=sys.stderr)
            continue
        page = state.resume_page(conn, run_key, start_page=1)
        while page <= NYPL_MAX_PAGES:
            result_page = nypl_fetch_page(locality, page)
            items = result_page["items"]
            page_count = result_page["pageInfo"]["pageCount"]

            records = [normalize_nypl_event(i, borough, geo_conn) for i in items]
            # NYPL has no server-side date filter, so the 90-day window is
            # applied here. Without it this source reached ~10 months out
            # while every other source stopped at 90 days.
            records = [r for r in records
                       if r["start_ts"] and r["start_ts"] <= window_end]

            res = upsert(conn, schema.SPEC, records, schema.make_event_id, debug=DEBUG)
            totals = [t + v for t, v in zip(totals, (res.new, res.updated, res.unchanged))]

            page += 1
            state.save_progress(conn, run_key, schema.SOURCE_NYPL, page)
            if DEBUG:
                print(f"[debug] nypl/{borough}: page {page - 1}/{page_count} -> "
                      f"{res.new} new, {res.updated} upd, {res.unchanged} unch",
                      file=sys.stderr)
            if page > page_count:
                break
            time.sleep(SLEEP_NYPL)
        state.complete_progress(conn, run_key, schema.SOURCE_NYPL, start_page=1)
    return totals


# ---------------------------------------------------------------- QPL

def qpl_opener():
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def _waf_rejected(body):
    return "Request Rejected" in body and len(body) < 1000


def qpl_request(opener, url):
    """GET with retry. A WAF rejection is a 200 with an error body, so it
    cannot be detected from the status code -- see body_is_transient."""
    try:
        return phttp.get_text(
            url, opener=opener, max_retries=QPL_MAX_RETRIES, label="qpl",
            headers={"User-Agent": USER_AGENT, "Referer": QPL_CALENDAR_URL},
            body_is_transient=_waf_rejected)
    except phttp.TransientBody as e:
        raise WafBlocked(str(e)) from e


def normalize_qpl_event(data, geo_conn):
    raw_start = data.get("date_show_timestamp")
    start_ts = to_utc(raw_start)

    end_ts = None
    for sess in (data.get("other_sessions") or {}).values():
        if sess.get("timestamp_GMT") == raw_start and sess.get("duration"):
            try:
                end_ts = to_utc(int(raw_start) + int(sess["duration"]))
            except (TypeError, ValueError):
                end_ts = None
            break

    venue_name = data.get("branch_name")
    lat = lon = None
    if geo_conn and venue_name:
        lat, lon = geocode.geocode(geo_conn, f"{venue_name} Library, Queens, NY",
                                   debug=DEBUG)

    call_url = data.get("callUrl")
    source_url = "https://www.queenslibrary.org" + call_url if call_url else None

    return schema.blank_record(
        source=schema.SOURCE_QPL,
        source_id=data.get("jobID"),
        title=data.get("title"),
        description=data.get("descr"),
        start_datetime=start_ts.isoformat() if start_ts else None,
        end_datetime=end_ts.isoformat() if end_ts else None,
        start_ts=start_ts,
        end_ts=end_ts,
        venue_name=venue_name,
        address=None,  # only on each event's own detail page, not the search payload
        borough="Queens",
        latitude=lat,
        longitude=lon,
        categories=data.get("prgm_type"),
        is_free=True,
        registration_url=source_url,  # registration happens in-page
        source_url=source_url,
        raw_json=json.dumps(data),
    )


def run_qpl(conn, geo_conn, window_end):
    run_key = "qpl_events"
    opener = qpl_opener()
    # /search/call returns nothing useful without a session from /calendar.
    qpl_request(opener, QPL_CALENDAR_URL)
    time.sleep(SLEEP_QPL)

    page = state.resume_page(conn, run_key, start_page=0)
    totals = [0, 0, 0]

    while page <= QPL_MAX_PAGES:
        body = qpl_request(opener, QPL_SEARCH_CALL_URL.format(page=page))
        raw_matches = ARR_JSON_RE.findall(body)
        if not raw_matches:
            break  # genuine end of results; a WAF block raised above instead

        records = []
        for raw in raw_matches:
            try:
                records.append(normalize_qpl_event(json.loads(html.unescape(raw)),
                                                   geo_conn))
            except json.JSONDecodeError:
                continue
        records = [r for r in records if r["start_ts"] and r["start_ts"] <= window_end]

        res = upsert(conn, schema.SPEC, records, schema.make_event_id, debug=DEBUG)
        totals = [t + v for t, v in zip(totals, (res.new, res.updated, res.unchanged))]

        page += 1
        state.save_progress(conn, run_key, schema.SOURCE_QPL, page)
        if DEBUG:
            print(f"[debug] qpl: page {page - 1} -> {len(records)} events "
                  f"({res.new} new, {res.updated} upd, {res.unchanged} unch)",
                  file=sys.stderr)
        time.sleep(SLEEP_QPL)

    state.complete_progress(conn, run_key, schema.SOURCE_QPL, start_page=0)
    return totals


# ---------------------------------------------------------------- main

def main():
    conn = dbconn.connect_or_exit("nyc-library-events ingest")
    schema.ensure_schema(conn)
    state.ensure_state_schema(conn)

    geo_conn = None
    try:
        geo_conn = dbconn.connect(autocommit=True)
        geocode.ensure_geocode_schema(geo_conn)
    except Exception as e:
        print(f"nyc-library-events: geocoding disabled ({e})", file=sys.stderr)

    window_start, window_end = day_bounds_utc(WINDOW_DAYS_AHEAD)
    run_started_at = utc_now_str()
    totals = [0, 0, 0]
    errors, partial = [], []

    for name, fn, source in (("nypl", run_nypl, schema.SOURCE_NYPL),
                             ("qpl", run_qpl, schema.SOURCE_QPL)):
        try:
            got = fn(conn, geo_conn, window_end)
            totals = [t + v for t, v in zip(totals, got)]
            state.set_watermark(conn, source, run_started_at)
        except WafBlocked as e:
            # A block is only a *partial* success if there is progress to
            # resume. QPL has never had any: it is rejected on the very
            # first request, to the /calendar landing page that establishes
            # the session, so it never reaches page 1 and never records a
            # watermark. Reporting that as "will resume next run" is how a
            # source that has contributed zero rows since it was written
            # stayed invisible -- the job exits 0 either way.
            if state.get_watermark(conn, source):
                partial.append(f"{name}: blocked by WAF ({e}) -- will resume next run")
            else:
                partial.append(
                    f"{name}: blocked by WAF ({e}) -- and has NEVER completed a "
                    f"run, so this source contributes 0 events. Resuming will not "
                    f"help; the block is at the session-establishing request. "
                    f"Needs a real browser session, not a retry.")
        except Exception as e:
            errors.append(f"{name}: {e}")
            if DEBUG:
                import traceback
                traceback.print_exc(file=sys.stderr)

    pruned = prune_expired(conn, schema.TABLE, schema.LIBRARY_SOURCES,
                           window_start, window_end)
    conn.close()
    if geo_conn:
        geo_conn.close()

    for note in partial:
        print(f"nyc-library-events: {note}", file=sys.stderr)

    if errors:
        print(f"nyc-library-events ingest FAILED: {'; '.join(errors)}")
        print(f"Partial: {totals[0]} new, {totals[1]} updated "
              f"(progress saved -- next run resumes where this left off).")
        sys.exit(1)

    if totals[0] or totals[1] or pruned:
        print(f"nyc-library-events: {totals[0]} new, {totals[1]} updated "
              f"({totals[2]} unchanged), {pruned} past events pruned.")


if __name__ == "__main__":
    main()
