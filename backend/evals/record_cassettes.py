#!/usr/bin/env python3
"""Record a cassette against the live upstream. The only thing here that does.

    python3 evals/record_cassettes.py --list
    python3 evals/record_cassettes.py ats-greenhouse
    python3 evals/record_cassettes.py --all-free

WHY THE RECIPES LIVE IN A FILE INSTEAD OF IN SOMEONE'S SHELL HISTORY
    A cassette is a claim about what an endpoint returned. Six months from
    now the only way to check that claim, or to refresh it, is to make the
    same request again -- so what was requested has to be written down next
    to what came back. Each recipe below calls the REAL fetch function from
    the REAL ingest script, so the recorded request is by construction the
    request the pipeline makes; if ats.py changes its URL, re-recording
    follows it for free.

COST, EXPLICITLY
    free   ats-greenhouse, ats-greenhouse-no-content, ats-lever, ats-ashby,
           hn-hiring, wwr-feeds, builtin-nyc -- public unauthenticated
           endpoints
    quota  google-serpapi   -- ONE SerpApi search off a metered key
    quota  google-apify     -- reads a HISTORICAL actor run. It starts no
           new run, so it bills nothing; see the recipe for why that is both
           cheaper and more honest than paying $0.15 to record a start.

    `--all-free` is the safe bulk button and deliberately excludes both.

POLITENESS
    One pass, no sweeps, the real User-Agent each script sends, and the same
    inter-request delays the scripts use. builtin-nyc.py is the only scraped
    HTML source here and it gets one listing page and one detail page.
"""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evals import cassettes                                   # noqa: E402
from evals.ingest_modules import load as load_ingest          # noqa: E402
from lib import envfile                                       # noqa: E402

RECORDED_BY = "evals/record_cassettes.py (task 09)"

#: Which HN comments to keep. The first N kids of the current thread: enough
#: shapes to exercise pick_title_segment (ingest/hn-hiring.py:236) without
#: pulling three hundred comments off a free API to prove a parser works.
HN_COMMENTS = 10

#: An id HN has never issued. Returns the four bytes `null`, which is the
#: exact response ingest/hn-hiring.py:409 guards with `if not comment`, and
#: the input for the "null items are re-fetched forever" defect
#: (05-fetcher-harness.md item 5): the guard returns BEFORE the ledger
#: insert, so the id is never marked seen and comes back every run.
HN_NULL_ITEM = 99999999999


def record_ats_greenhouse():
    ats = load_ingest("ats")
    # kickstarter: 5 open reqs, the smallest of the 44 greenhouse tokens in
    # config/companies.json (measured 2026-07-28). Small board, real
    # double-escaped `content` field -- which is the whole reason a
    # greenhouse cassette is worth having, see ats.py:169-194.
    with cassettes.recording(
            "ats-greenhouse", source="api.greenhouse.io", recorded_by=RECORDED_BY,
            note="ingest/ats.py fetch_greenhouse('kickstarter'); ?content=true, "
                 "so `content` carries the once-escaped HTML that "
                 "greenhouse_description() exists to unescape twice."):
        jobs = ats.fetch_greenhouse("kickstarter")
    return f"{len(jobs)} greenhouse postings"


def record_ats_greenhouse_no_content():
    """The same board WITHOUT ?content=true -- the missing-`content` payload.

    `05-fetcher-harness.md:73-76` wants "a Greenhouse payload with a missing
    `content` field" among the awkward responses, and no live board offers
    one: every posting on every board carries the field when it is asked
    for. Dropping the query parameter produces the identical shape from the
    identical endpoint, and it is not a hypothetical -- it is exactly what
    ats.py:152 would receive if that parameter were ever lost, and the
    failure would be every description on every greenhouse board silently
    becoming NULL while the run reported success.
    """
    from lib import http
    with cassettes.recording(
            "ats-greenhouse-no-content", source="api.greenhouse.io",
            recorded_by=RECORDED_BY,
            note="kickstarter WITHOUT ?content=true: real bytes, no `content` "
                 "key. The shape ats.py:152 gets if the query parameter is "
                 "lost -- descriptions silently NULL, run reports success."):
        data = http.get_json(
            "https://api.greenhouse.io/v1/boards/kickstarter/jobs")
    return f"{len(data.get('jobs', []))} postings, no content field"


def record_ats_lever():
    ats = load_ingest("ats")
    with cassettes.recording(
            "ats-lever", source="api.lever.co", recorded_by=RECORDED_BY,
            note="ingest/ats.py fetch_lever('finix'); the only lever token in "
                 "config/companies.json. Lever serves real HTML in "
                 "`description`, unlike greenhouse -- ats.py:261."):
        jobs = ats.fetch_lever("finix")
    return f"{len(jobs)} lever postings"


def record_ats_ashby():
    ats = load_ingest("ats")
    with cassettes.recording(
            "ats-ashby", source="api.ashbyhq.com", recorded_by=RECORDED_BY,
            note="ingest/ats.py fetch_ashby('runway'); smallest ashby board in "
                 "config/companies.json. Carries isRemote, which normalize_ashby "
                 "ORs over the location regex (ats.py:271)."):
        jobs = ats.fetch_ashby("runway")
    return f"{len(jobs)} ashby postings"


def record_hn_hiring():
    hn = load_ingest("hn-hiring")
    with cassettes.recording(
            "hn-hiring", source="hacker-news.firebaseio.com",
            recorded_by=RECORDED_BY,
            note=f"find_latest_hiring_thread() plus the first {HN_COMMENTS} "
                 f"kids of the current thread, plus item {HN_NULL_ITEM} which "
                 f"returns literal `null` -- the deleted/nonexistent item that "
                 f"hn-hiring.py:409 skips before the ledger insert."):
        thread = hn.find_latest_hiring_thread()
        if not thread:
            raise RuntimeError("no hiring thread found; refusing to record")
        for kid in (thread.get("kids") or [])[:HN_COMMENTS]:
            hn.http.get_json(f"{hn.HN_API_BASE}/item/{kid}.json")
            time.sleep(0.2)
        hn.http.get_json(f"{hn.HN_API_BASE}/item/{HN_NULL_ITEM}.json")
    return f"thread {thread['id']}, {HN_COMMENTS} comments, 1 null item"


def record_wwr_feeds():
    wwr = load_ingest("weworkremotely")
    # Two categories, not four: enough to exercise the cross-listing dedup at
    # weworkremotely.py:207 (a posting appearing in both back-end and
    # full-stack) without pulling the whole site.
    cats = ["remote-back-end-programming-jobs", "remote-full-stack-programming-jobs"]
    with cassettes.recording(
            "wwr-feeds", source="weworkremotely.com", recorded_by=RECORDED_BY,
            note="fetch_feed() for two of the four categories in CATEGORIES. "
                 "Two, so the cross-listing dedup at weworkremotely.py:207 has "
                 "something to dedup."):
        total = 0
        for i, cat in enumerate(cats):
            total += len(wwr.fetch_feed(cat))
            if i < len(cats) - 1:
                time.sleep(wwr.REQUEST_DELAY_SECONDS)
    return f"{len(cats)} feeds, {total} bytes"


def record_builtin_nyc():
    builtin = load_ingest("builtin-nyc")
    with cassettes.recording(
            "builtin-nyc", source="builtinnyc.com", recorded_by=RECORDED_BY,
            note="One listing page and one detail page. The listing bytes are "
                 "what D02 (title/company zip misattribution) and D03 (unscoped "
                 "salary regex) live in; the detail page is what "
                 "extract_description() reads the ld+json out of, including the "
                 "&#x2B; escaping noted at builtin-nyc.py:156."):
        page = builtin.fetch_page(1)
        records = builtin.parse_page(page)
        if not records:
            raise RuntimeError("listing page parsed to zero records; "
                               "refusing to record a cassette that proves nothing")
        time.sleep(builtin.DETAIL_DELAY_SECONDS)
        builtin.fetch_description(records[0]["job_url"])
    return f"1 listing page ({len(records)} cards), 1 detail page"


#: One (platform, token, extra, why) per ATS the task-16 validator can check,
#: plus the non-resolving cases. Recorded through tools/ats-discover.py's own
#: validate(), so the request is by construction the request the discovery
#: tool makes -- change the endpoint and re-recording follows it for free.
#:
#: WHY A NON-RESOLVING TOKEN IS THE POINT. The validator exists to stop
#: trusting a regex match found in a stale footer link. Exercised only against
#: boards that resolve, it would pass while being unable to tell a live board
#: from a dead one -- so the two 404 cases below are the ones that make the
#: rest of the cassette mean anything.
ATS_VALIDATION_PROBES = (
    ("greenhouse", "kickstarter", {},
     "smallest greenhouse board in config/companies.json"),
    ("greenhouse", "no-such-board-xyzzy", {},
     "DOES NOT RESOLVE -- 404, must classify `dead`, never `never_found`"),
    ("lever", "finix", {},
     "the only lever token in config/companies.json"),
    ("ashby", "runway", {},
     "smallest ashby board in config/companies.json"),
    ("workday", "nvidia", {"workday_dc": "wd5",
                           "workday_site": "NVIDIAExternalCareerSite"},
     "the limit=20 landmine, on the very tenant CLAUDE.md cites: `total` "
     "reports 2,000 and one page returns 20. Ask for 100 and Workday returns "
     "an EMPTY array with no error -- so this cassette is what stops a future "
     "edit to the limit from silently validating every tenant as dead"),
    ("workday", "nvidia", {"workday_dc": "wd1",
                           "workday_site": "NVIDIAExternalCareerSite"},
     "WRONG DATA CENTRE, right tenant -- wd1 instead of wd5. This is the "
     "18-ingest-workday-cxs.md:54 failure: a guessed dc 404s, and a 404 here "
     "is indistinguishable from a tenant with no open roles unless the dc is "
     "stored and used. Hence workday_dc being its own column"),
    ("smartrecruiters", "Ubisoft", {},
     "200 with totalFound=0 -- SmartRecruiters does NOT 404 an unknown "
     "company, it returns an empty page. The shape that would read as a live "
     "board if the validator only checked the status code"),
    ("icims", "no-such-tenant-xyzzy", {},
     "iCIMS publishes no JSON feed (why task 20 reaches for Firecrawl), so "
     "validity is 'the portal exists and lists jobs'. This one does not"),
    ("recruitee", "no-such-tenant-xyzzy", {},
     "404 on a per-tenant subdomain"),
    ("workable", "no-such-account-xyzzy", {},
     "the widget endpoint's refusal shape"),
)


def _load_discover_cli():
    """tools/ats-discover.py, by path -- its filename has a hyphen.

    The recipe drives the REAL validate()/validation_request() pair rather
    than a copy of the URLs, for the reason this module's docstring gives:
    a cassette recorded against a reimplementation records the
    reimplementation.
    """
    import importlib.util
    path = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "tools", "ats-discover.py")
    spec = importlib.util.spec_from_file_location("ats_discover_cli", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def record_ats_validation():
    """One validation probe per ATS, including tokens that do not resolve.

    Free: every endpoint here is the same public, unauthenticated feed the
    employer's own careers page calls. Ten requests, paced by the tool's own
    rate limiter, one per host except the two Workday tenants.
    """
    cli = _load_discover_cli()
    fetcher = cli.Fetcher(delay=1.0, host_delay=2.0, timeout=20)
    results = []
    with cassettes.recording(
            "ats-validation", source="8 ATS vendor APIs",
            recorded_by=RECORDED_BY,
            note="tools/ats-discover.py validate() against one token per "
                 "validatable ATS, plus four that do not resolve (a 404 "
                 "greenhouse board, a wrong Workday data centre, an unknown "
                 "iCIMS tenant, an unknown Recruitee tenant) and one that "
                 "answers 200 with an empty list (SmartRecruiters). The "
                 "validator is what stops the pipeline trusting a regex match "
                 "from a stale footer link; recorded only against boards that "
                 "resolve, it could not tell live from dead."):
        for platform, token, extra, _why in ATS_VALIDATION_PROBES:
            status, jobs, note = cli.validate(
                fetcher, platform, {"token": token, **extra})
            results.append(f"{platform}:{token}={status}")
    return f"{len(results)} validation probes -- " + ", ".join(results)


def record_google_serpapi():
    """ONE SerpApi search. Metered."""
    serp = load_ingest("google-serpapi")
    if not serp.SERPAPI_API_KEY:
        raise RuntimeError("SERPAPI_API_KEY not set; load backend/.env first")
    with cassettes.recording(
            "google-serpapi", source="serpapi.com", recorded_by=RECORDED_BY,
            note="ONE metered search. The api_key is scrubbed from the stored "
                 "URL and is not part of the replay key -- rotating the "
                 "credential must not invalidate the recording."):
        results = serp.serpapi_search(
            "AI engineer", "New York, New York, United States", date_chip="week")
    return f"{len(results)} jobs_results"


def record_google_apify():
    """A HISTORICAL actor run: poll + dataset fetch. Bills nothing.

    WHY NOT A REAL START. Starting this actor costs ~$0.15 of a $5/month
    free credit (google-apify.py:33-45), and what a start would buy is one
    JSON object. The poll and dataset endpoints are free reads, and the run
    object they return is the SAME `{"data": {...}}` shape the start POST
    returns -- Apify's API documents them as the same resource. So the
    cassette holds real bytes for the two calls that matter and the recipe
    refuses to run at all if there is no historical run to read, rather than
    quietly paying to make one.
    """
    apify = load_ingest("google-apify")
    if not apify.APIFY_API_TOKEN:
        raise RuntimeError("APIFY_API_TOKEN not set; load backend/.env first")
    listing = apify.http.get_json(
        f"https://api.apify.com/v2/actor-runs"
        f"?token={apify.APIFY_API_TOKEN}&limit=10&desc=1")
    runs = [r for r in listing["data"]["items"] if r.get("status") == "SUCCEEDED"]
    if not runs:
        raise RuntimeError(
            "no SUCCEEDED historical run on this Apify account. Recording "
            "would require starting one, which bills ~$0.15 -- refusing. "
            "Run ingest/google-apify.py once for real, then re-record.")
    run_id = runs[0]["id"]
    with cassettes.recording(
            "google-apify", source="api.apify.com", recorded_by=RECORDED_BY,
            note=f"Historical run {run_id}: GET /v2/actor-runs/{{id}} and GET "
                 f"/v2/datasets/{{id}}/items, the poll and fetch halves of "
                 f"run_actor_query(). No run was started, so this cost "
                 f"nothing. The ?token= is scrubbed."):
        run = apify.http.get_json(
            f"https://api.apify.com/v2/actor-runs/{run_id}"
            f"?token={apify.APIFY_API_TOKEN}")
        items = apify.http.get_json(
            f"https://api.apify.com/v2/datasets/"
            f"{run['data']['defaultDatasetId']}/items"
            f"?token={apify.APIFY_API_TOKEN}")
    return f"run {run_id} ({run['data']['status']}), {len(items)} dataset items"


FREE = {
    "ats-greenhouse": record_ats_greenhouse,
    "ats-greenhouse-no-content": record_ats_greenhouse_no_content,
    "ats-lever": record_ats_lever,
    "ats-ashby": record_ats_ashby,
    "ats-validation": record_ats_validation,
    "hn-hiring": record_hn_hiring,
    "wwr-feeds": record_wwr_feeds,
    "builtin-nyc": record_builtin_nyc,
}

METERED = {
    "google-serpapi": record_google_serpapi,
    "google-apify": record_google_apify,
}

RECIPES = {**FREE, **METERED}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("names", nargs="*", help="cassette names to record")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--all-free", action="store_true",
                    help="every recipe that costs no quota")
    args = ap.parse_args()

    if args.list:
        for name in sorted(RECIPES):
            tier = "free " if name in FREE else "QUOTA"
            have = "have" if cassettes.available(name) else "MISSING"
            print(f"{tier}  {have:8s} {name}")
        return

    envfile.load(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), ".env"))

    targets = list(args.names)
    if args.all_free:
        targets = sorted(FREE) + targets
    if not targets:
        ap.error("name a cassette, or --all-free, or --list")

    for name in targets:
        if name not in RECIPES:
            print(f"unknown cassette {name!r}; --list to see them",
                  file=sys.stderr)
            sys.exit(2)
        print(f"recording {name} ...", flush=True)
        summary = RECIPES[name]()
        path = cassettes.Cassette.path_for(name)
        print(f"  {summary} -> {path} ({os.path.getsize(path):,} bytes)")


if __name__ == "__main__":
    main()
