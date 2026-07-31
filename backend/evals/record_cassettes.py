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
           ats-workable, ats-recruitee, ats-smartrecruiters, ats-validation,
           workday-cxs, hn-hiring, wwr-feeds, builtin-nyc, nyc-open-data --
           public unauthenticated endpoints
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

import extract                                                # noqa: E402
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


def record_ats_greenhouse_domsoup():
    """A LIVE greenhouse posting whose `content` is a pasted browser DOM.

    THE FIXTURE FOR TASK 35, and it is a recording rather than a constructed
    string for the reason HANDOFF.md:571-574 states: fixtures written from a
    specification test the specification. Nobody would invent
    `[&:has([data-writing-block])>*]:pointer-events-auto` -- and that exact
    token is the defect, because the ">" inside the class attribute is what
    ends lib/text.strip_html()'s `<[^>]+>` early and spills the rest of the
    tag into description_text as prose.

    Two postings from the same board on the same day:

        8035268  Product Analyst (Maternity-Leave Replacement)  -- the poisoned
                 one. Its `content` is a rendered ChatGPT conversation someone
                 pasted into Greenhouse's job-description editor. That it is
                 Greenhouse, a structured ATS API, is the whole point: the
                 markup is in the EMPLOYER's field, so no scraper is at fault
                 and no per-source fix would have caught it.
        8087797  Senior Data Scientist -- an ordinary posting, so the same test
                 can show the gate leaves a real job description alone without
                 a synthetic control.

    THE SINGLE-JOB ENDPOINT, not fetch_greenhouse(). The whole taboola board is
    95 postings and 875 KB, of which one posting is the evidence;
    `ats-greenhouse.json` already pins that fetch_greenhouse() pages and
    unescapes correctly. This recipe pins what greenhouse_description() does to
    one pathological `content`, at 1/80th of the disk. Same precedent as
    record_ats_greenhouse_no_content() above, which also builds its own request.
    """
    from lib import http
    ats = load_ingest("ats")
    urls = {
        "poisoned": "https://boards-api.greenhouse.io/v1/boards/taboola/jobs/"
                    "8035268?content=true",
        "clean": "https://boards-api.greenhouse.io/v1/boards/taboola/jobs/"
                 "8087797?content=true",
    }
    bodies = {}
    with cassettes.recording(
            "ats-greenhouse-domsoup", source="boards-api.greenhouse.io",
            recorded_by=RECORDED_BY,
            note="Two taboola postings. 8035268's `content` is a pasted "
                 "ChatGPT web UI -- the input extract.py's markup gate exists "
                 "to reject; 8087797 is an ordinary posting from the same "
                 "board as the control. Recorded for task 35."):
        for label, url in urls.items():
            bodies[label] = http.get_json(url)
            time.sleep(1.0)

    # REFUSE TO RECORD BYTES THAT NO LONGER CARRY THE DEFECT. A cassette that
    # has quietly stopped reproducing its own failure reads like coverage and
    # is worse than none -- the lesson task 18 wrote down (HANDOFF.md:565-570).
    # If Taboola fixes this job description, this recipe must fail loudly so
    # the fixture is re-sourced rather than silently downgraded to two clean
    # postings that assert nothing.
    ratios = {}
    for label, body in bodies.items():
        description = ats.greenhouse_description(body.get("content")) or ""
        ratios[label] = extract.markup_ratio(
            extract.prompt_description({"description_text": description}))
    if ratios["poisoned"] < extract.MARKUP_REJECT_RATIO:
        raise RuntimeError(
            f"taboola 8035268 now scores {ratios['poisoned']:.4f}, below the "
            f"{extract.MARKUP_REJECT_RATIO} gate -- the employer has fixed the "
            f"posting and these bytes are no longer evidence for task 35. Find "
            f"another contaminated posting before re-recording.")
    if ratios["clean"] >= extract.MARKUP_REJECT_RATIO:
        raise RuntimeError(
            f"the control posting 8087797 now scores {ratios['clean']:.4f} and "
            f"would itself be rejected; it is no longer a control.")
    return (f"2 postings: 8035268 markup_ratio={ratios['poisoned']:.4f} "
            f"(rejected), 8087797 markup_ratio={ratios['clean']:.4f} (kept)")


def record_ats_lever():
    ats = load_ingest("ats")
    with cassettes.recording(
            "ats-lever", source="api.lever.co", recorded_by=RECORDED_BY,
            note="ingest/ats.py fetch_lever('finix'); the only lever token in "
                 "the companies.json seed. Lever serves real HTML in "
                 "`description`, unlike greenhouse. RE-RECORDED for task 17: "
                 "fetch_lever now pages with &limit=100&skip=N, so the URL "
                 "differs from the pre-task-17 recording. Finix returns a "
                 "short first page, which is what ends the loop."):
        jobs = ats.fetch_lever("finix")
    return f"{len(jobs)} lever postings"


def record_ats_ashby():
    ats = load_ingest("ats")
    with cassettes.recording(
            "ats-ashby", source="api.ashbyhq.com", recorded_by=RECORDED_BY,
            note="ingest/ats.py fetch_ashby('runway'); smallest ashby board in "
                 "the companies.json seed. Carries isRemote, which "
                 "normalize_ashby ORs over the location regex. RE-RECORDED for "
                 "task 17: the URL now carries ?includeCompensation=true. "
                 "Runway does not publish compensation, so every posting here "
                 "holds the KEY with empty tiers and null summaries -- the "
                 "shape ashby_salary() must answer None to, and the common "
                 "case. The populated shape is pinned by unit test instead; "
                 "the smallest ashby board that publishes compensation is "
                 "`writer` at 859 KB, too large to commit for one string."):
        jobs = ats.fetch_ashby("runway")
    return f"{len(jobs)} ashby postings"


def record_ats_workable():
    """Both halves of a Workable pull, including the duplicate-expansion trap.

    braven, a national nonprofit hiring in NYC among other cities -- picked
    because it EXHIBITS THE TRAP: the v1 widget returns 66 entries for 20
    distinct shortcodes (measured 2026-07-28), one per posting per location.
    A cassette from an account without multi-location postings would let a
    future edit drop the dedupe in fetch_workable() with nothing failing.
    """
    ats = load_ingest("ats")
    with cassettes.recording(
            "ats-workable", source="apply.workable.com", recorded_by=RECORDED_BY,
            note="ingest/ats.py fetch_workable('braven'): the v3 POST that "
                 "reports `total`, then the v1 widget with ?details=true that "
                 "carries the descriptions. TWO endpoints on purpose -- v3 has "
                 "no descriptions and pages ten at a time, the widget has "
                 "descriptions and no total. The widget's 66 entries collapse "
                 "to 20 unique shortcodes and v3 says total=20, which is the "
                 "reconciliation this cassette exists to pin."):
        jobs = ats.fetch_workable("braven")
    return (f"{len(jobs)} unique workable postings, "
            f"total reported {jobs.reported_total}")


def record_ats_recruitee():
    """One request, whole board, descriptions and structured salary.

    Tellent's own board (`jobs.recruitee.com`) -- eight offers, each with a
    `salary` object, which is the only structured salary in this script
    besides Ashby's and the thing recruitee_salary() renders.
    """
    ats = load_ingest("ats")
    with cassettes.recording(
            "ats-recruitee", source="recruitee.com", recorded_by=RECORDED_BY,
            note="ingest/ats.py fetch_recruitee('jobs'). One GET, the whole "
                 "board: no pagination and no total, so a short answer IS the "
                 "answer here. Offers carry `updated_at` and the endpoint "
                 "accepts no filter for it -- the delta-sync claim in "
                 "17-retarget-ats-ingest.md does not hold for this platform "
                 "either."):
        jobs = ats.fetch_recruitee("jobs")
    return f"{len(jobs)} recruitee offers"


def record_ats_smartrecruiters():
    """The list page plus one detail call per posting.

    Visa: totalFound=2, so the whole pull is three requests and the cassette
    stays small while still holding a REAL `totalFound` to reconcile against.

    Its two job ads are thin -- one has text only in `additionalInformation`
    and the other's four sections are all empty strings -- and that is worth
    keeping rather than recording around. "The detail call was spent and the
    ad is empty" and "the detail call has not been spent yet" are different
    states that both end as a NULL description if the parser conflates them,
    and both are in these bytes. The rich shape (all four sections full of
    HTML) was measured the same day against `BoschGroup`, whose board is
    4,755 postings -- not something to commit to prove one join.

    Multi-page reconciliation arithmetic is pinned by a synthetic cassette in
    tests/test_ats_new_platforms.py -- recording a board large enough to page
    would mean committing hundreds of kilobytes to prove one comparison.
    """
    ats = load_ingest("ats")
    with cassettes.recording(
            "ats-smartrecruiters", source="api.smartrecruiters.com",
            recorded_by=RECORDED_BY,
            note="ingest/ats.py fetch_smartrecruiters('Visa') at the "
                 "production limit=100, then fetch_smartrecruiters_detail() "
                 "for each posting. The list endpoint carries NO description "
                 "-- the job ad is one GET per posting and there is no bulk "
                 "form (?expand=jobAd is ignored), which is why the detail "
                 "fetch is budgeted rather than unconditional."):
        postings = ats.fetch_smartrecruiters("Visa")
        details = []
        for posting in postings:
            details.append(ats.fetch_smartrecruiters_detail("Visa", posting["id"]))
            time.sleep(ats.REQUEST_DELAY_SECONDS)
    return (f"{len(postings)} postings (totalFound "
            f"{postings.reported_total}), {len(details)} job ads")


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


#: The slice of NYC Open Data that gets recorded, and the page size it is
#: crawled at. NOT the production request: that is the whole 2,376-row
#: dataset at $limit=1000 and would commit an ~8 MB fixture to prove three
#: pages of pagination. `post_until IS NULL` is 49 rows (24 External, 25
#: Internal on 2026-07-28) and is chosen because it IS the edge case -- task
#: 14 asks for a fixture with a null `post_until` and one with an Internal
#: `posting_type`, and this one `$where` guarantees both without any
#: hardcoded job_id that would rot the moment DCAS closes that posting.
#:
#: At page size 20 the crawl is three pages ending in a short one, so the
#: recorded interactions are the real pagination shape: count, page, page,
#: short page, count. Everything about the request except the `$where` and
#: the `$limit` is what production sends, because it goes through the ingest
#: script's own fetch_all().
NYC_OPEN_DATA_WHERE = "post_until IS NULL"
NYC_OPEN_DATA_PAGE_SIZE = 20


def record_nyc_open_data():
    """The count/crawl/count shape, over the dataset's own edge cases.

    Free: data.cityofnewyork.us is a public Socrata endpoint and no app
    token is used or needed. Five requests, paced by the script's own
    inter-page delay.
    """
    nyc = load_ingest("nyc-open-data")
    with cassettes.recording(
            "nyc-open-data", source="data.cityofnewyork.us",
            recorded_by=RECORDED_BY,
            note=f"ingest/nyc-open-data.py fetch_count/fetch_all/fetch_count "
                 f"over `{NYC_OPEN_DATA_WHERE}` at $limit="
                 f"{NYC_OPEN_DATA_PAGE_SIZE}. That slice is 49 rows holding "
                 f"BOTH edge cases task 14 asks for -- every null post_until "
                 f"in the dataset, and Internal postings for the "
                 f"posting_type filter to drop. The two count queries "
                 f"bracket the crawl: reconcile() compares what was "
                 f"collected against them, because a throttled page and the "
                 f"last page are the same bytes."):
        before = nyc.fetch_count(where=NYC_OPEN_DATA_WHERE)
        fetched = nyc.fetch_all(where=NYC_OPEN_DATA_WHERE,
                                page_size=NYC_OPEN_DATA_PAGE_SIZE)
        after = nyc.fetch_count(where=NYC_OPEN_DATA_WHERE)
    kinds = {r.get("posting_type") for r in fetched.rows}
    if not {"External", "Internal"} <= kinds:
        raise RuntimeError(
            f"recorded slice holds only {sorted(kinds)} -- the Internal "
            f"filter would be untested by these bytes; refusing to record")
    return (f"{len(fetched.rows)} rows over {fetched.pages} page(s), "
            f"count {before} -> {after}")


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


#: Memorial Sloan Kettering: 79 open postings when recorded, the SMALLEST of the four
#: live Workday tenants in `company_ats` (Moelis 43 is smaller but sits behind
#: an `Experienced-Hires` site that is not the shape task 18 walks; nyp 367 and
#: nordstrom 862 are both several times the bytes for no extra shape).
#: `docs/ingest/workday.md:553-557` names this tenant, this size and this
#: request count.
#:
#: All three coordinates, not just the token: 18-ingest-workday-cxs.md:54
#: forbids guessing the data centre, and `wd108` is not derivable from `msk`.
WORKDAY_CXS = ("msk", "wd108", "MSKCC_Careers_Primary")


def record_workday_cxs():
    """A full multi-page walk plus one detail document. ~6 requests, free.

    WHY THIS TENANT AND NOT NVIDIA. The `ats-validation` cassette already
    holds one nvidia.wd5 list page, and `workday_fixtures.recorded_list_page()`
    lifts it rather than recording a second one. What it cannot hold is a
    WALK: it is a single page, and every multi-page failure in
    `docs/ingest/workday.md:241-249` is about what the second page does.
    NVIDIA's board is 2,000 postings -- 100 pages -- so walking it to get that
    would commit megabytes to prove pagination. msk was 79 postings when this
    was recorded on 2026-07-28: FOUR pages, the last one short (20+20+20+19,
    `total` 79/0/0/0), which is the smallest thing that is still a real walk.

    THE COMMITTED CASSETTE'S OWN `note` STILL SAYS "five pages", AND STAYS
    WRONG ON PURPOSE. That string is baked into
    `fixtures/cassettes/workday-cxs.json` at record time, so the only way to
    correct it is to re-record -- which the two guards below exist to refuse,
    because a re-record against today's board is how failure 5's only recorded
    evidence gets destroyed. A false sentence inside an artifact that must not
    be regenerated is cheaper than the regeneration. Read the JSON's page
    count, not its prose.

    (The board was 88 over five pages at task 16's validation. It moved before
    the recording, which is ordinary -- it is why nothing in the ingest path
    reconciles against a stored count, and why this docstring said five pages
    for three days after the bytes said four.)

    WHAT THESE BYTES PIN THAT A CONSTRUCTED FIXTURE CANNOT. Failure 5 --
    `total` reported on the offset=0 page only, every later page answering
    `total: 0` (workday.py:463-475). It is the one failure in that table that
    is NOT in the task file: it was found live, and until now the only fixture
    for it is `workday_fixtures.total_only_on_first_page()`, which is
    constructed. A constructed fixture for an undocumented upstream behaviour
    proves that the code handles the behaviour someone REMEMBERED; it cannot
    prove the behaviour is still real. These bytes can, and the guard below
    refuses to record if it has stopped being real -- a cassette recorded
    against a tenant that has quietly started reporting `total` on every page
    would silently retire the evidence for the latch at workday.py:476.

    NOT RECORDED, DELIBERATELY: the wrap (offset=100 returning page one
    again), which is the other half of failure 5. Provoking it means one
    request PAST the end of a stranger's board purely to record a
    pathology, and `collect_postings` never issues that request -- the
    `fresh == 0` guard at workday.py:490 exists so the walk stops before it.
    A recipe that reached past the end to record it would be recording a
    request the pipeline does not make, which is the one thing this file's
    docstring says a recipe must not do.

    Free: `*.myworkdayjobs.com` CXS is the same public, unauthenticated
    endpoint the employer's own careers page calls. Paced by the ingest
    script's own REQUEST_DELAY_SECONDS.
    """
    workday = load_ingest("workday")
    tenant, dc, site = WORKDAY_CXS
    with cassettes.recording(
            "workday-cxs", source=f"{tenant}.{dc}.myworkdayjobs.com",
            recorded_by=RECORDED_BY,
            note=f"ingest/workday.py collect_tenant('{tenant}', '{dc}', "
                 f"'{site}') -- the whole board at the production "
                 f"limit={workday.PAGE_LIMIT}, every page to the end of the "
                 f"board, plus fetch_detail() for the first posting. Records "
                 f"failure 5 from real bytes: `total` is on the offset=0 page "
                 f"ONLY and every later page answers 0, so a walk that takes "
                 f"the latest value reconciles a complete board against zero "
                 f"and calls it a shortfall (workday.py:463-475). Also pins "
                 f"the limit<=20 ceiling from the request side -- these are "
                 f"the bodies _check_page_limit lets through."):
        postings, total = workday.collect_tenant(tenant, dc, site)
        time.sleep(workday.REQUEST_DELAY_SECONDS)
        detail = workday.fetch_detail(tenant, dc, site,
                                      postings[0]["externalPath"])

    # Two guards, in the style of record_nyc_open_data(): a cassette that does
    # not hold the thing it was recorded for is worse than no cassette,
    # because it will be cited as evidence. Both check the RECORDING, not the
    # parse, so neither can be satisfied by the code under test being wrong in
    # a matching way.
    # The list endpoint is a POST ending in /jobs; the detail endpoint is a GET
    # on the same prefix (workday.py:320-334), so the method is what separates
    # them and a substring match on the path is not enough.
    pages = [i for i in cassettes.Cassette.load("workday-cxs").interactions
             if i.method == "POST" and i.url.endswith("/jobs")]
    totals = []
    for i in pages:
        try:
            # .raw, not .body: a response stored as base64 leaves .body None,
            # and reading None here would report "no totals" as "failure 5 is
            # gone" and refuse a perfectly good recording.
            totals.append(json.loads(i.raw.decode("utf-8")).get("total"))
        except Exception:
            pass
    if len(pages) < 3:
        raise RuntimeError(
            f"recorded only {len(pages)} list page(s) against {tenant}.{dc} -- "
            f"a one-page walk pins nothing that recorded_list_page() does not "
            f"already pin; refusing to record")
    if not (totals and totals[0] and not any(totals[1:])):
        raise RuntimeError(
            f"{tenant}.{dc} reported totals {totals} -- failure 5 (total on "
            f"the first page only) is NOT in these bytes, so this cassette "
            f"would not be evidence for the latch at workday.py:476. Either "
            f"the tenant changed or the walk did; refusing to record")

    return (f"{len(postings)} postings over {len(pages)} list page(s), "
            f"total {total}, page totals {totals}, "
            f"1 detail document ({len(detail.get('jobPostingInfo') or {})} "
            f"jobPostingInfo keys)")


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
    "ats-greenhouse-domsoup": record_ats_greenhouse_domsoup,
    "ats-lever": record_ats_lever,
    "ats-ashby": record_ats_ashby,
    "ats-workable": record_ats_workable,
    "ats-recruitee": record_ats_recruitee,
    "ats-smartrecruiters": record_ats_smartrecruiters,
    "ats-validation": record_ats_validation,
    "workday-cxs": record_workday_cxs,
    "hn-hiring": record_hn_hiring,
    "wwr-feeds": record_wwr_feeds,
    "builtin-nyc": record_builtin_nyc,
    "nyc-open-data": record_nyc_open_data,
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
