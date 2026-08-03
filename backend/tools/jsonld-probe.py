#!/usr/bin/env python3
"""
Measure whether task 19 (the JSON-LD parser) is worth building.

THIS IS A MEASUREMENT, NOT THE PARSER. Nothing here writes to the database,
nothing here is on the nightly path, and no code in this file is intended to
survive into the eventual ingest module. The deliverable is a number, its
method, and its date -- see docs/jsonld-coverage.md.

WHAT IT MEASURES
    For each employer with a `never_found` row in `company_ats` (the exact
    population task 19 exists to serve, per 19-jsonld-parser.md:15-17):

      1. Does the careers page -- or a job-detail page one hop from it --
         publish schema.org/JobPosting? Via JSON-LD, microdata or RDFa.
      2. Which of the eight fields in 19-jsonld-parser.md:21-33 are actually
         present, per employer. `validThrough` matters most: it is the only
         closure signal that makes re-crawl affordable (19:69).
      3. Is there a sitemap.xml carrying job URLs, and do they have <lastmod>?
      4. How many postings are discoverable, and how fresh are they -- the
         two inputs to a postings/day estimate.

WHY NOT extruct
    19-jsonld-parser.md:53 says to use `extruct`. It is not installed, and
    backend/requirements.txt:1-6 is explicit that psycopg is "the pipeline's
    only third-party dependency ... every added package is another thing that
    can be missing on one of them." A measurement spike that decides whether
    to build a thing must not install that thing's dependency into the user's
    environment as a side effect of deciding. So: stdlib only.

    What that costs, stated plainly so nobody reads a floor as a ceiling:
      * JSON-LD  -- no loss. It is `json.loads` over <script> bodies, which
                    is what extruct does too.
      * microdata -- reduced. See MicrodataProbe below: scopes are counted
                    exactly, but itemprop names are collected document-wide
                    rather than per-scope, so a page with two JobPosting
                    scopes reports the union of their fields.
      * RDFa     -- DETECTION ONLY. `typeof="JobPosting"` is counted, never
                    parsed. Rejected rather than half-implemented: an RDFa
                    extractor needs CURIE prefix resolution against @vocab and
                    xmlns:*, which is a real parser, and the answer this spike
                    needs is "does the long tail publish anything at all",
                    for which a count suffices.
    Every coverage figure below is therefore a FLOOR. Task 16 learned the same
    lesson the expensive way -- its positive control found zero of four
    known-good ATS tokens because those boards render client-side, so
    `never_found` never meant "no ATS". Read every number here the same way.

POLITENESS
    This is outward traffic against ~35 hosts that never asked for it.
      * robots.txt is fetched first and OBEYED, for our own User-Agent. A
        disallowed URL is not fetched and is recorded as an outcome, not
        skipped silently -- `robots_disallowed` and "no JobPosting" must not
        collapse into the same bucket.
      * One global request every --delay seconds AND at most one request per
        host every --host-delay seconds. Per host, not global, so one employer
        with a large sitemap cannot starve the other thirty-four
        (19-jsonld-parser.md:80-82).
      * NO retries, ever. Same reasoning as tools/ats-discover.py:47-49:
        retrying into a rate limit is how a probe becomes an incident.
      * A host answering 401/403/406/429/451 is blocklisted for the rest of
        the run and receives no further request.
      * An honest User-Agent naming the project, with a contact address. Not a
        browser string: a host that does not want automated traffic is
        entitled to recognise this as automated traffic and refuse it.
      * --max-requests is a hard ceiling on the entire run and the number is
        reported. Default 400.
      * NO Firecrawl. Task 20 needs that credit pool (19-jsonld-parser.md:89-92)
        and a JS-rendered page is a finding here, not an obstacle to route
        around.

USAGE
    python3 tools/jsonld-probe.py --report
        Population only. No network at all.

    python3 tools/jsonld-probe.py --run --out /path/results.json
        The probe. Writes one JSON document with every observation.

    python3 tools/jsonld-probe.py --summarize /path/results.json
        Every headline number in docs/jsonld-coverage.md, printed. If a figure
        in that document is not in this output, that figure is not measured.

    python3 tools/jsonld-probe.py --estimate /path/results.json
        The postings/day derivation, each step printed with its input.

DATABASE
    Read-only. --run and --report SELECT from company_ats and ats_seed.
    --estimate additionally creates a TEMP table to apply relevance.tier_sql()
    to harvested titles -- CLAUDE.md forbids reimplementing relevance matching
    in Python, so the harvested rows are pushed to Postgres and gated by the
    production expression instead. TEMP, so it dies with the connection.
"""

import argparse
import collections
import datetime
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

# tools/ sits one level below the pipeline modules it imports. Python puts
# THIS file's directory on sys.path, not its parent, so the parent is added by
# hand -- same three lines as tools/ats-discover.py:88-91.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import relevance  # noqa: E402
from lib import dbconn, envfile  # noqa: E402

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
envfile.load(os.path.join(_REPO_ROOT, ".env"))

#: Honest, and deliberately not a browser string. The contact is the project
#: URL rather than the maintainer's personal email: the address has to survive
#: being read by ~35 unknown hosts and end up in their logs, and a repository
#: URL is contactable without publishing a private individual's mailbox to
#: everyone who runs `grep User-Agent` on an access log. Same posture as
#: tools/ats-discover.py:106-110, same string shape.
USER_AGENT = ("jobs-pipeline-jsonld-probe/1.0 "
              "(+https://github.com/hermes/jobs; structured-data coverage "
              "measurement for a nonprofit job-search project; "
              "obeys robots.txt; no retries)")

#: 10s. A careers page that has not answered in ten seconds is not going to,
#: and on a run capped at 400 requests the timeout budget is the wall clock.
TIMEOUT = 10

#: Read cap for an HTML page. JSON-LD lives in the head or the tail; 3 MB
#: covers both on every page that is not pathological, and a truncated body is
#: reported as truncated rather than silently read as "no JobPosting".
MAX_BYTES = 3_000_000

#: The eight fields of 19-jsonld-parser.md:23-32, in that order. `validThrough`
#: is bolded there and is the one that decides whether re-crawl is affordable.
FIELDS = ["title", "description", "datePosted", "validThrough",
          "employmentType", "hiringOrganization.name", "jobLocation.address",
          "baseSalary"]

#: How many job-detail links to follow per employer when the careers page
#: itself carries no JobPosting. THREE, not thirty. The question is binary --
#: "do detail pages carry structured data" -- and one page answers it while
#: three survive two dead links. An unbounded crawl is the failure mode
#: 19-jsonld-parser.md:46-50 warns about, and this file has no business
#: exercising it.
DETAIL_LINKS_PER_EMPLOYER = 3

#: Href shapes that plausibly lead to a job detail page. Ordered by how
#: specific they are; the first match wins so /job/12345 outranks /careers.
_JOB_LINK_PATTERNS = [
    re.compile(r"/job[s]?[/-][^/]*\d", re.I),
    re.compile(r"/(job|jobs|position|positions|opening|openings|vacancy|"
               r"vacancies|requisition|req)[/-]", re.I),
    re.compile(r"[?&](job|jobid|job_id|reqid|req_id|posting|positionid)=", re.I),
    re.compile(r"/(career|careers)/[^/]+/[^/]+", re.I),
]

#: Sitemap URLs whose path suggests jobs. Used to pick which child sitemap of
#: a <sitemapindex> to open -- opening all of them is how one employer spends
#: the whole request budget.
_JOB_SITEMAP_HINT = re.compile(r"job|career|position|opening|vacan", re.I)

#: Paths that contain a jobs word but are LISTINGS, not postings.
#:
#: MEASURED, NOT ANTICIPATED. The first version of this tool had no such list
#: and reported 963 "job-shaped" sitemap URLs across 12 employers. Opening
#: them showed what they were: Moody's 432 are all
#: `/en/category/engineering-and-technology-jobs/...` and BCG's 815 are all
#: `/ca/fr/c/conseil-jobs` -- category indexes, one per taxonomy node, in
#: every language the site publishes. Counting those as job URLs inflates the
#: only denominator this spike has, and an ingest built on that count would
#: spend its whole nightly budget re-crawling category pages that never
#: contain a JobPosting.
_LISTING_PATH = re.compile(
    r"/(category|categories|c|search|browse|all-jobs|job-search|"
    r"job-categories|locations?|departments?|teams?)/", re.I)

#: A 200 that means no. Lifted verbatim in spirit from ats-discover.py's
#: _WAF_BODY: a probe that counted these as "page read, no JobPosting" would
#: report a block as an absence, which is the exact error task 16 made.
_WAF_BODY = re.compile(
    r"request rejected|access denied|are you a robot|captcha|"
    r"unusual traffic|cf-browser-verification|just a moment\.\.\.|"
    r"enable javascript and cookies to continue|incapsula|"
    r"pardon our interruption", re.I)

#: Page bodies that carry no server-rendered content. A single-page app shell
#: is the DOMINANT expected finding for this population and it is a distinct
#: outcome from "fetched, nothing there" -- 19-jsonld-parser.md:90-91 routes it
#: to Firecrawl, which this run must not spend.
_SPA_HINT = re.compile(
    r"<div[^>]+id=[\"'](root|app|__next|__nuxt)[\"']|"
    r"window\.__NUXT__|window\.__INITIAL_STATE__|_next/static", re.I)

# Outcome vocabulary. Deliberately the same five words tools/ats-discover.py
# uses (ats_discovery.py), because the distinction they encode is the same
# one: "we looked and there was nothing" must never be stored in the same
# bucket as "we were never allowed to look".
FETCHED = "fetched"
BLOCKED = "blocked"
MISSING_PAGE = "missing_page"
UNREACHABLE = "unreachable"
ROBOTS_DISALLOWED = "robots_disallowed"
SKIPPED = "skipped"


def host_of(url):
    """Lowercased host. Same helper as ats_discovery.host_of:420."""
    if not url:
        return ""
    if "://" not in url:
        url = "https://" + url
    return urllib.parse.urlsplit(url).netloc.lower()


# --------------------------------------------------------------------------
# Fetching
# --------------------------------------------------------------------------

class Fetcher:
    """One global pace, one per-host pace, robots.txt, a blocklist, a ceiling.

    Never raises and never retries. Every call returns
    (outcome, status, text, truncated) so that a caller cannot accidentally
    treat a refusal as an empty result -- the shape is copied from
    ats-discover.py:195 for exactly that reason.
    """

    def __init__(self, delay=1.5, host_delay=5.0, max_requests=400,
                 timeout=TIMEOUT, verbose=False, obey_robots=True):
        self.delay = delay
        self.host_delay = host_delay
        self.max_requests = max_requests
        self.timeout = timeout
        self.verbose = verbose
        self.obey_robots = obey_robots
        self.requests = 0
        self.robots_requests = 0
        self.blocked_hosts = set()
        self._last_global = 0.0
        self._last_host = {}
        self._robots = {}          # host -> RobotFileParser or None
        self._sitemaps = {}        # host -> [urls declared in robots.txt]

    # -- pacing ------------------------------------------------------------

    def _wait(self, host):
        now = time.monotonic()
        due = max(self._last_global + self.delay,
                  self._last_host.get(host, 0.0) + self.host_delay)
        if due > now:
            time.sleep(due - now)
        # Jitter, so a run never looks like a metronome to a WAF.
        self._last_global = time.monotonic() + random.uniform(0, 0.2)
        self._last_host[host] = self._last_global

    # -- robots ------------------------------------------------------------

    def robots(self, url):
        """RobotFileParser for this URL's host, fetched at most once.

        Fetched by hand rather than via RobotFileParser.read(): read() opens
        the URL itself, which would send urllib's default User-Agent, bypass
        the rate limiter, and bypass the request ceiling. Three ways to be
        impolite while implementing politeness.
        """
        host = host_of(url)
        if host in self._robots:
            return self._robots[host]
        parts = urllib.parse.urlsplit(url)
        robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
        outcome, status, text, _ = self._raw(robots_url, max_bytes=500_000,
                                             count_as_robots=True)
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(robots_url)
        if outcome == FETCHED and status == 200:
            try:
                rp.parse(text.splitlines())
            except Exception:
                rp.allow_all = True
            self._sitemaps[host] = [
                line.split(":", 1)[1].strip()
                for line in text.splitlines()
                if line.lower().startswith("sitemap:")]
        elif outcome == MISSING_PAGE:
            # No robots.txt means no restrictions. RFC 9309 §2.3.1.
            rp.allow_all = True
            self._sitemaps[host] = []
        else:
            # Unreachable or blocked robots.txt. Treated as DISALLOW, not as
            # allow: RFC 9309 §2.3.1.4 says a 5xx should be read as full
            # disallow, and a host that refuses to serve its own robots.txt to
            # this User-Agent has answered the question.
            rp.disallow_all = True
            self._sitemaps[host] = []
        self._robots[host] = rp
        return rp

    def allowed(self, url):
        if not self.obey_robots:
            return True
        try:
            return self.robots(url).can_fetch(USER_AGENT, url)
        except Exception as e:
            if self.verbose:
                print(f"[debug] {url}: {type(e).__name__}: {e}",
                      file=sys.stderr)
            return False

    def sitemaps_from_robots(self, url):
        self.robots(url)
        return self._sitemaps.get(host_of(url), [])

    # -- the request -------------------------------------------------------

    def _raw(self, url, max_bytes=MAX_BYTES, count_as_robots=False):
        host = host_of(url)
        if host in self.blocked_hosts:
            return (SKIPPED, None, "", False)
        if self.requests + self.robots_requests >= self.max_requests:
            return (SKIPPED, None, "", False)

        self._wait(host)
        if count_as_robots:
            self.robots_requests += 1
        else:
            self.requests += 1

        headers = {"User-Agent": USER_AGENT,
                   "Accept": "text/html,application/xhtml+xml,"
                             "application/xml;q=0.9,*/*;q=0.8",
                   "Accept-Language": "en-US,en;q=0.9"}
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read(max_bytes + 1)
                truncated = len(raw) > max_bytes
                text = raw[:max_bytes].decode("utf-8", errors="replace")
                status = resp.status
        except urllib.error.HTTPError as e:
            try:
                text = e.read(200_000).decode("utf-8", errors="replace")
            except Exception:
                text = ""
            if e.code in (401, 403, 406, 429, 451):
                self.blocked_hosts.add(host)
                return (BLOCKED, e.code, text, False)
            if e.code in (404, 410):
                return (MISSING_PAGE, e.code, text, False)
            return (UNREACHABLE, e.code, text, False)
        except Exception as e:
            if self.verbose:
                print(f"[debug] {url}: {type(e).__name__}: {e}",
                      file=sys.stderr)
            return (UNREACHABLE, None, "", False)

        if _WAF_BODY.search(text[:20000]):
            self.blocked_hosts.add(host)
            return (BLOCKED, status, text, False)
        return (FETCHED, status, text, truncated)

    def get(self, url, max_bytes=MAX_BYTES):
        """Robots-checked fetch. The only entry point callers should use."""
        if not self.allowed(url):
            return (ROBOTS_DISALLOWED, None, "", False)
        return self._raw(url, max_bytes=max_bytes)

    @property
    def total_requests(self):
        return self.requests + self.robots_requests


# --------------------------------------------------------------------------
# Structured-data extraction
# --------------------------------------------------------------------------

class ScriptAndLinkParser(HTMLParser):
    """Pulls ld+json script bodies, <a href>s, and microdata/RDFa markers.

    One pass over the document for all four, because each pass is a full
    re-parse of up to 3 MB and there are up to four pages per employer.

    convert_charrefs is left at its default (True) so that entity-escaped
    JSON bodies decode; script content is exempt from charref conversion in
    html.parser, which is the behaviour wanted here -- a JSON body containing
    &amp; must stay as written.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ld_blocks = []
        self.links = []
        self.microdata_jobposting_scopes = 0
        self.rdfa_jobposting_scopes = 0
        self.itemprops = set()
        self._in_ld = False
        self._buf = []

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "script":
            typ = a.get("type", "").lower().strip()
            # application/ld+json is the spec spelling; the wild also carries
            # text/ld+json and, on a few sites, no type at all next to an
            # @context. Only the two ld+json spellings are accepted -- a
            # typeless <script> is JavaScript far more often than it is
            # JSON-LD, and parsing it costs false positives.
            if typ in ("application/ld+json", "text/ld+json"):
                self._in_ld = True
                self._buf = []
        elif tag == "a":
            href = a.get("href", "").strip()
            if href:
                self.links.append(href)
        if "itemprop" in a:
            self.itemprops.add(a["itemprop"].strip())
        itemtype = a.get("itemtype", "")
        if itemtype and "jobposting" in itemtype.lower():
            self.microdata_jobposting_scopes += 1
        typeof = a.get("typeof", "")
        if typeof and "jobposting" in typeof.lower():
            self.rdfa_jobposting_scopes += 1

    def handle_endtag(self, tag):
        if tag == "script" and self._in_ld:
            self.ld_blocks.append("".join(self._buf))
            self._in_ld = False
            self._buf = []

    def handle_data(self, data):
        if self._in_ld:
            self._buf.append(data)


# Kept as a name the docstring can point at; see the extruct note at the top.
MicrodataProbe = ScriptAndLinkParser


def parse_page(html):
    """(parser, [json objects]) -- every ld+json block that parses.

    A block that does not parse is counted, not raised on: a page with one
    broken JSON-LD island and one good one must still yield the good one, and
    "how many islands are malformed" is itself a finding about how much a real
    parser would have to tolerate.
    """
    p = ScriptAndLinkParser()
    try:
        p.feed(html)
    except Exception:
        pass  # html.parser can raise on sufficiently broken markup
    objects, bad = [], 0
    for block in p.ld_blocks:
        block = block.strip()
        if not block:
            continue
        try:
            objects.append(json.loads(block))
        except Exception:
            bad += 1
    return p, objects, bad


def _types_of(node):
    t = node.get("@type", node.get("type"))
    if isinstance(t, str):
        return [t]
    if isinstance(t, list):
        return [x for x in t if isinstance(x, str)]
    return []


def walk_jobpostings(node, out, depth=0):
    """Every JobPosting anywhere in a JSON-LD document.

    A GENERIC RECURSIVE WALK, and that is the design decision worth recording.
    19-jsonld-parser.md:58-59 names three shapes to handle -- `@graph`
    wrappers, bare arrays, and JobPosting nested inside `ItemList` -- and
    warns that missing them "silently ingests one posting from a page carrying
    twenty".

    REJECTED: special-casing those three keys. It handles the three shapes
    that were thought of and silently drops the fourth. Two real shapes are
    already outside that list -- `ItemList.itemListElement[].item` (the
    ListItem indirection, which is what Google's own examples use) and
    `mainEntity`/`about` on a WebPage. Recursing over every value catches all
    of them and cannot be wrong by omission; the cost is a depth cap and no
    recursion INTO a JobPosting, since a JobPosting inside a JobPosting is not
    a thing and recursing would double-count it.
    """
    if depth > 12:
        return
    if isinstance(node, list):
        for x in node:
            walk_jobpostings(x, out, depth + 1)
        return
    if not isinstance(node, dict):
        return
    types = [t.rsplit("/", 1)[-1].lower() for t in _types_of(node)]
    if "jobposting" in types:
        out.append(node)
        return
    for k, v in node.items():
        if k == "@context":
            continue
        walk_jobpostings(v, out, depth + 1)


def _present(posting, field):
    """Is this dotted field present and non-empty on this posting?

    schema.org permits a value to be a scalar, an object, or an array of
    either, at every level. `jobLocation` is routinely a list of Place; a
    checker that only understood the object case would report the multi-site
    employers -- the ones with the most postings -- as missing their location.
    """
    def nonempty(v):
        if v is None:
            return False
        if isinstance(v, str):
            return bool(v.strip())
        if isinstance(v, (list, dict)):
            return len(v) > 0
        return True

    parts = field.split(".")
    cur = [posting]
    for part in parts:
        nxt = []
        for node in cur:
            if isinstance(node, list):
                cur_nodes = node
            else:
                cur_nodes = [node]
            for n in cur_nodes:
                if isinstance(n, dict) and part in n:
                    nxt.append(n[part])
        cur = nxt
        if not cur:
            return False
    return any(nonempty(v) for v in cur)


def _scalar(posting, field):
    """First scalar value at a dotted path, for reporting. '' if absent."""
    parts = field.split(".")
    cur = posting
    for part in parts:
        if isinstance(cur, list):
            cur = cur[0] if cur else None
        if not isinstance(cur, dict) or part not in cur:
            return ""
        cur = cur[part]
    if isinstance(cur, list):
        cur = cur[0] if cur else ""
    if isinstance(cur, dict):
        for k in ("name", "@value", "value", "addressLocality"):
            if isinstance(cur.get(k), str):
                return cur[k]
        return json.dumps(cur)[:200]
    return str(cur)[:400] if cur is not None else ""


def _location_text(posting):
    """Everything location-ish on a posting, flattened, for NYC/remote calls.

    Includes applicantLocationRequirements and jobLocationType because a
    remote posting frequently has NO jobLocation at all -- reading only
    jobLocation.address would classify every fully-remote req as unknown.
    """
    bits = []
    for key in ("jobLocation", "applicantLocationRequirements",
                "jobLocationType"):
        v = posting.get(key)
        if v is not None:
            bits.append(json.dumps(v))
    return " ".join(bits)[:2000]


def summarize_posting(posting):
    """The subset of a JobPosting this measurement keeps.

    Descriptions are NOT kept. They are the bulk of the bytes, they are not
    needed to answer "does this field exist", and a results file carrying the
    full text of several hundred employer postings is a thing to have to think
    about before committing. Length is kept instead -- enough to tell a real
    description from a one-line stub.
    """
    desc = _scalar(posting, "description")
    return {
        "title": _scalar(posting, "title")[:300],
        "datePosted": _scalar(posting, "datePosted")[:64],
        "validThrough": _scalar(posting, "validThrough")[:64],
        "employmentType": _scalar(posting, "employmentType")[:120],
        "hiringOrganization": _scalar(posting, "hiringOrganization.name")[:200],
        "description_len": len(desc),
        "location_text": _location_text(posting),
        "identifier": _scalar(posting, "identifier")[:120],
        "url": _scalar(posting, "url")[:400],
        "fields": {f: _present(posting, f) for f in FIELDS},
    }


def dedupe(postings):
    """By (title, identifier-or-url). Both halves are load-bearing.

    An index page that lists a posting and links to it yields the same job
    twice once detail pages are followed; counting it twice inflates the one
    number this whole spike is for.

    WHY THE TITLE IS IN THE KEY, which it was not in the first version. Etsy's
    three sampled job pages each carry a distinct JobPosting, and all three
    give `identifier` as the literal string "Etsy" with no `url` at all. Keyed
    on identifier-then-url -- the obvious key, and the one schema.org invites
    -- those three postings collapsed to one and the tool reported 1 where the
    truth was 3. `identifier` inside a JobPosting is whatever the employer's
    templating put there; it is not an identity and must not be trusted as
    one. Caught only because the collapsed count disagreed with the number of
    PAGES that had each reported carrying a posting -- two numbers from the
    same tool contradicting each other.
    """
    seen, out = set(), []
    for p in postings:
        ident = (p.get("identifier") or p.get("url") or "").strip().lower()
        key = (f"{p.get('title', '')}".strip().lower(), ident)
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


# --------------------------------------------------------------------------
# Sitemaps
# --------------------------------------------------------------------------

def _localname(tag):
    return tag.rsplit("}", 1)[-1]


def parse_sitemap(xml_text):
    """(kind, entries) where kind is 'sitemapindex' | 'urlset' | 'unknown'.

    entries are (loc, lastmod). Namespace-insensitive: sitemaps in the wild
    use the 0.84, 0.90 and no-namespace forms, and an ET query with a
    hardcoded namespace silently returns zero entries for two of the three --
    which reads exactly like an empty sitemap.
    """
    try:
        root = ET.fromstring(xml_text.strip())
    except Exception:
        return ("unknown", [])
    kind = _localname(root.tag).lower()
    entries = []
    for child in root:
        loc = lastmod = ""
        for g in child:
            name = _localname(g.tag).lower()
            if name == "loc":
                loc = (g.text or "").strip()
            elif name == "lastmod":
                lastmod = (g.text or "").strip()
        if loc:
            entries.append((loc, lastmod))
    if kind not in ("sitemapindex", "urlset"):
        kind = "unknown"
    return (kind, entries)


def probe_sitemap(fetcher, careers_url, budget=3):
    """Find a sitemap and report whether it carries job URLs with lastmod.

    Candidates in order: whatever robots.txt declares (authoritative), then
    /sitemap.xml. `budget` caps how many sitemap documents are opened for one
    employer -- a <sitemapindex> with 200 children is common and opening them
    all would spend the whole run on one host.
    """
    result = {"sitemap_url": "", "outcome": "", "kind": "",
              "total_urls": 0, "job_urls": 0, "job_urls_with_lastmod": 0,
              "followed_children": 0, "sample_job_urls": []}
    parts = urllib.parse.urlsplit(careers_url)
    if not parts.netloc:
        result["outcome"] = "no_url"
        return result

    declared = fetcher.sitemaps_from_robots(careers_url)
    candidates = list(declared) + [f"{parts.scheme}://{parts.netloc}/sitemap.xml"]
    # Prefer a declared sitemap whose path mentions jobs.
    candidates.sort(key=lambda u: (0 if _JOB_SITEMAP_HINT.search(u) else 1))

    seen = set()
    opened = 0
    for cand in candidates:
        if cand in seen or opened >= budget:
            continue
        seen.add(cand)
        outcome, status, text, _ = fetcher.get(cand, max_bytes=MAX_BYTES)
        opened += 1
        result["sitemap_url"] = cand
        result["outcome"] = outcome
        if outcome != FETCHED:
            continue
        kind, entries = parse_sitemap(text)
        result["kind"] = kind
        if kind == "sitemapindex":
            children = [loc for loc, _ in entries if _JOB_SITEMAP_HINT.search(loc)]
            for child in children[:max(0, budget - opened)]:
                o2, _s2, t2, _ = fetcher.get(child, max_bytes=MAX_BYTES)
                opened += 1
                result["followed_children"] += 1
                if o2 != FETCHED:
                    continue
                k2, e2 = parse_sitemap(t2)
                if k2 == "urlset":
                    result["sitemap_url"] = child
                    result["kind"] = "urlset"
                    _tally_urlset(result, e2)
            if result["total_urls"]:
                return result
            continue
        if kind == "urlset":
            _tally_urlset(result, entries)
            if result["job_urls"]:
                return result
    return result


#: How many sitemap job URLs to keep per employer for the second pass. The
#: FIRST N in document order, not a random sample: a sitemap is generated, its
#: order is stable, and a reproducible sample is worth more here than an
#: unbiased one when the question is binary ("does a job page carry JSON-LD").
#: Recorded so the number can be re-fetched and checked.
SITEMAP_SAMPLE = 3


def _is_job_url(loc):
    path = urllib.parse.urlsplit(loc).path
    if _LISTING_PATH.search(path):
        return False
    return bool(any(p.search(loc) for p in _JOB_LINK_PATTERNS)
                or _JOB_SITEMAP_HINT.search(path))


def _tally_urlset(result, entries):
    result["total_urls"] += len(entries)
    for loc, lastmod in entries:
        if _is_job_url(loc):
            result["job_urls"] += 1
            if lastmod:
                result["job_urls_with_lastmod"] += 1
            if len(result["sample_job_urls"]) < SITEMAP_SAMPLE:
                result["sample_job_urls"].append(loc)


# --------------------------------------------------------------------------
# Per-employer probe
# --------------------------------------------------------------------------

def pick_detail_links(base_url, links, limit=DETAIL_LINKS_PER_EMPLOYER):
    """Job-detail-looking links, same host only, most specific first."""
    base_host = host_of(base_url)
    scored = []
    seen = set()
    for href in links:
        try:
            absolute = urllib.parse.urljoin(base_url, href)
        except Exception:
            continue
        if not absolute.startswith(("http://", "https://")):
            continue
        absolute = absolute.split("#")[0]
        if absolute in seen:
            continue
        # Same host only. Following off-host links is how a careers page that
        # links to greenhouse turns this measurement into a measurement of
        # greenhouse -- which is precisely the population task 19 is NOT for.
        if host_of(absolute) != base_host:
            continue
        for rank, pat in enumerate(_JOB_LINK_PATTERNS):
            if pat.search(absolute):
                seen.add(absolute)
                scored.append((rank, absolute))
                break
    scored.sort()
    return [u for _, u in scored[:limit]]


def probe_employer(fetcher, row, follow_details=True):
    """One employer: careers page, up to three detail pages, one sitemap."""
    out = {
        "employer_name": row["employer_name"],
        "careers_url": row["careers_url"],
        "sector": row.get("sector"),
        "careers_outcome": "",
        "careers_status": None,
        "careers_truncated": False,
        "looks_like_spa": False,
        "ld_blocks": 0,
        "ld_blocks_unparseable": 0,
        "microdata_scopes": 0,
        "rdfa_scopes": 0,
        "postings_on_careers_page": 0,
        "detail_pages_tried": 0,
        "detail_pages_with_jobposting": 0,
        "detail_outcomes": [],
        "postings": [],
        "sitemap": {},
        "requests_used": 0,
    }
    url = row["careers_url"]
    before = fetcher.total_requests
    if not url:
        out["careers_outcome"] = "no_url"
        return out

    outcome, status, text, truncated = fetcher.get(url)
    out["careers_outcome"] = outcome
    out["careers_status"] = status
    out["careers_truncated"] = truncated

    postings = []
    parser = None
    if outcome == FETCHED:
        out["looks_like_spa"] = bool(_SPA_HINT.search(text))
        parser, objects, bad = parse_page(text)
        out["ld_blocks"] = len(parser.ld_blocks)
        out["ld_blocks_unparseable"] = bad
        out["microdata_scopes"] = parser.microdata_jobposting_scopes
        out["rdfa_scopes"] = parser.rdfa_jobposting_scopes
        found = []
        for obj in objects:
            walk_jobpostings(obj, found)
        out["postings_on_careers_page"] = len(found)
        postings.extend(summarize_posting(p) for p in found)

    # Follow detail links only when the careers page itself yielded nothing.
    # If the index page already carries JobPosting the question is answered
    # and three more requests buy nothing.
    if follow_details and parser is not None and not postings:
        for link in pick_detail_links(url, parser.links):
            o, _s, t, _tr = fetcher.get(link)
            out["detail_pages_tried"] += 1
            out["detail_outcomes"].append({"url": link, "outcome": o})
            if o != FETCHED:
                continue
            _p, objs, _bad = parse_page(t)
            found = []
            for obj in objs:
                walk_jobpostings(obj, found)
            if found:
                out["detail_pages_with_jobposting"] += 1
                postings.extend(summarize_posting(x) for x in found)
            if not out["microdata_scopes"]:
                out["microdata_scopes"] = _p.microdata_jobposting_scopes
            if not out["rdfa_scopes"]:
                out["rdfa_scopes"] = _p.rdfa_jobposting_scopes

    out["postings"] = dedupe(postings)
    out["sitemap"] = probe_sitemap(fetcher, url)
    out["requests_used"] = fetcher.total_requests - before
    return out


def sitemap_pass(fetcher, doc, per_employer=SITEMAP_SAMPLE):
    """Second pass: open ACTUAL job URLs, taken from each employer's sitemap.

    WHY THIS PASS EXISTS, AND WHY THE FIRST PASS WITHOUT IT WOULD HAVE BEEN
    A WRONG ANSWER.

    Pass one followed job-detail links scraped out of the careers page's HTML.
    It found links for 7 of the 29 employers it reached: the other 22 render
    their listing client-side, so there were no <a href>s to follow and NO JOB
    DETAIL PAGE WAS EVER OPENED FOR THEM. Reporting "1 of 35 publish
    JobPosting" off that would be measuring careers-page INDEX markup and
    calling it employer coverage -- structurally the same error task 16 made
    when its positive control found zero of four known-good ATS tokens.

    The sitemap does not care whether the listing renders client-side. It is
    also the discovery path 19-jsonld-parser.md:42-45 puts first. So: take the
    job URLs the sitemap already declared, open a few, and look at the pages a
    real ingest would actually parse.

    Only employers whose sitemap declared job-shaped URLs can be re-probed
    here; for the rest the question stays open, and that is reported rather
    than rounded to zero.
    """
    out = []
    for row in doc["employers"]:
        urls = (row.get("sitemap") or {}).get("sample_job_urls") or []
        if not urls:
            continue
        rec = {"employer_name": row["employer_name"],
               "population": row.get("population"),
               "sitemap_url": row["sitemap"].get("sitemap_url"),
               "job_urls_declared": row["sitemap"].get("job_urls", 0),
               "pages": [], "postings": []}
        for url in urls[:per_employer]:
            outcome, status, text, _t = fetcher.get(url)
            page = {"url": url, "outcome": outcome, "status": status,
                    "ld_blocks": 0, "postings": 0, "microdata_scopes": 0,
                    "rdfa_scopes": 0, "looks_like_spa": False}
            if outcome == FETCHED:
                p, objects, bad = parse_page(text)
                page["ld_blocks"] = len(p.ld_blocks)
                page["ld_blocks_unparseable"] = bad
                page["microdata_scopes"] = p.microdata_jobposting_scopes
                page["rdfa_scopes"] = p.rdfa_jobposting_scopes
                page["looks_like_spa"] = bool(_SPA_HINT.search(text))
                found = []
                for obj in objects:
                    walk_jobpostings(obj, found)
                page["postings"] = len(found)
                for f in found:
                    s = summarize_posting(f)
                    s["found_at"] = url
                    rec["postings"].append(s)
            rec["pages"].append(page)
        rec["postings"] = dedupe(rec["postings"])
        out.append(rec)
        print(f"  {rec['employer_name'][:44]:<44} "
              f"{len(rec['pages'])} page(s), "
              f"{len(rec['postings'])} JobPosting", file=sys.stderr, flush=True)
    return out


def summarize_sitemap_pass(doc):
    """Every figure the sitemap pass produces, printed."""
    rows = doc.get("sitemap_pass") or []
    print("=" * 72)
    print("SITEMAP PASS -- job pages opened from each employer's own sitemap")
    print("=" * 72)
    if not rows:
        print("  no sitemap pass in this results file")
        return
    print(f"  run                                       {doc.get('sitemap_pass_at','')}")
    print(f"  requests spent on this pass               "
          f"{doc.get('sitemap_pass_requests', 0)}")
    print(f"  employers with sitemap job URLs to try    {len(rows)}")
    pages = [p for r in rows for p in r["pages"]]
    fetched = [p for p in pages if p["outcome"] == FETCHED]
    print(f"  job pages opened                          {len(pages)}")
    print(f"  ... fetched                               {len(fetched)}")
    outc = collections.Counter(p["outcome"] for p in pages)
    for k, v in outc.most_common():
        print(f"      {k:<22} {v:>4}")
    withjp = [r for r in rows if r["postings"]]
    print(f"  employers with >=1 JobPosting on a job    {len(withjp)} "
          f"of {len(rows)}")
    print(f"  distinct postings harvested               "
          f"{sum(len(r['postings']) for r in rows)}")
    print(f"  job pages carrying JobPosting             "
          f"{sum(1 for p in pages if p['postings'])}")
    print(f"  job pages fetched but carrying none       "
          f"{sum(1 for p in fetched if not p['postings'])}")
    print(f"  ... of those, look client-side rendered   "
          f"{sum(1 for p in fetched if not p['postings'] and p['looks_like_spa'])}")
    print(f"  microdata JobPosting scopes               "
          f"{sum(p['microdata_scopes'] for p in pages)}")
    print(f"  RDFa typeof=JobPosting scopes             "
          f"{sum(p['rdfa_scopes'] for p in pages)}")
    print("\n  PER EMPLOYER")
    print(f"  {'employer':<44} {'declared':>9} {'opened':>7} {'found':>6}")
    for r in sorted(rows, key=lambda x: -len(x["postings"])):
        print(f"  {r['employer_name'][:44]:<44} {r['job_urls_declared']:>9} "
              f"{len(r['pages']):>7} {len(r['postings']):>6}")

    allp = [p for r in rows for p in r["postings"]]
    if allp:
        print("\n  FIELD COMPLETENESS, sitemap-pass postings")
        print(f"  {'field':<26} {'present':>8} {'of':>5} {'pct':>7}")
        for f in FIELDS:
            got = sum(1 for p in allp if p["fields"][f])
            print(f"  {f:<26} {got:>8} {len(allp):>5} "
                  f"{100.0*got/len(allp):>6.1f}%")


# --------------------------------------------------------------------------
# Population
# --------------------------------------------------------------------------

NEVER_FOUND_SQL = """
    SELECT c.employer_name,
           COALESCE(NULLIF(c.careers_url, ''), s.careers_url) AS careers_url,
           s.sector
    FROM company_ats c
    LEFT JOIN ats_seed s ON s.employer_name = c.employer_name
    WHERE c.status = 'never_found'
    ORDER BY c.employer_name
"""

#: The wider population, for the representativeness check. company_ats holds
#: 35 never_found rows; ats_seed holds every employer the probe has ever
#: reached a conclusion about, and its `not_found` outcome is the same
#: judgement. The two counts differ, and the difference is a finding -- see
#: --report.
SEED_NOT_FOUND_SQL = """
    SELECT s.employer_name, s.careers_url, s.sector
    FROM ats_seed s
    WHERE s.last_probe_outcome = 'not_found'
      AND s.employer_name NOT IN (
          SELECT employer_name FROM company_ats WHERE status = 'never_found')
    ORDER BY s.employer_name
"""


def load_population(conn, extra_sample=0, seed=19):
    rows = [dict(employer_name=r[0], careers_url=r[1], sector=r[2])
            for r in conn.execute(NEVER_FOUND_SQL).fetchall()]
    for r in rows:
        r["population"] = "company_ats.never_found"
    if extra_sample:
        wider = [dict(employer_name=r[0], careers_url=r[1], sector=r[2])
                 for r in conn.execute(SEED_NOT_FOUND_SQL).fetchall()]
        # Seeded, so the sample is reproducible and re-runnable. A sample
        # nobody can reproduce is not a control.
        rnd = random.Random(seed)
        rnd.shuffle(wider)
        for r in wider[:extra_sample]:
            r["population"] = "ats_seed.not_found"
            rows.append(r)
    return rows


def report_population(conn):
    print("POPULATION")
    print("-" * 72)
    for label, sql in (
            ("company_ats by status",
             "SELECT status, count(*) FROM company_ats GROUP BY 1 ORDER BY 2 DESC"),
            ("ats_seed by last_probe_outcome",
             "SELECT COALESCE(last_probe_outcome,'(never probed)'), count(*) "
             "FROM ats_seed GROUP BY 1 ORDER BY 2 DESC")):
        print(f"\n{label}:")
        for k, v in conn.execute(sql).fetchall():
            print(f"  {k:<22} {v:>5}")
    total_seed = conn.execute("SELECT count(*) FROM ats_seed").fetchone()[0]
    total_ats = conn.execute("SELECT count(*) FROM company_ats").fetchone()[0]
    print(f"\nats_seed rows: {total_seed}   company_ats rows: {total_ats}")

    nf = conn.execute(
        "SELECT count(*) FROM company_ats WHERE status='never_found'").fetchone()[0]
    orphan = conn.execute(
        "SELECT count(*) FROM ats_seed WHERE last_probe_outcome='not_found' "
        "AND employer_name NOT IN (SELECT employer_name FROM company_ats "
        "WHERE status='never_found')").fetchone()[0]
    print(f"\ncompany_ats never_found:                     {nf}")
    print(f"ats_seed not_found with NO never_found row:  {orphan}")
    print(f"true 'probed, no ATS' population:            {nf + orphan}")
    print("\nfirst letter of employer_name, never_found rows:")
    hist = conn.execute(
        "SELECT left(employer_name,1), count(*) FROM company_ats "
        "WHERE status='never_found' GROUP BY 1 ORDER BY 1").fetchall()
    print("  " + "  ".join(f"{k}={v}" for k, v in hist))
    print("\nsector, never_found rows:")
    for k, v in conn.execute(
            "SELECT COALESCE(s.sector,'(none)'), count(*) FROM company_ats c "
            "LEFT JOIN ats_seed s ON s.employer_name=c.employer_name "
            "WHERE c.status='never_found' GROUP BY 1 ORDER BY 2 DESC").fetchall():
        print(f"  {k:<24} {v:>4}")
    print("\nsector, all ats_seed not_found:")
    for k, v in conn.execute(
            "SELECT COALESCE(sector,'(none)'), count(*) FROM ats_seed "
            "WHERE last_probe_outcome='not_found' GROUP BY 1 ORDER BY 2 DESC"
    ).fetchall():
        print(f"  {k:<24} {v:>4}")


# --------------------------------------------------------------------------
# Summary
# --------------------------------------------------------------------------

def _employers(doc, population=None, merge_sitemap_pass=False):
    """Employer rows, optionally with the sitemap pass folded in.

    The two passes looked at different pages for different reasons, and every
    headline count must be over their UNION -- an employer whose careers HTML
    had no crawlable links but whose sitemap-sampled job page carried a
    JobPosting publishes JobPosting, and counting the passes separately would
    report it in neither.
    """
    rows = doc["employers"]
    if population and population != "all":
        rows = [r for r in rows if r.get("population") == population]
    if not merge_sitemap_pass:
        return rows
    extra = collections.defaultdict(list)
    for r in doc.get("sitemap_pass") or []:
        extra[r["employer_name"]].extend(r["postings"])
    merged = []
    for r in rows:
        if r["employer_name"] in extra:
            r = dict(r)
            r["postings"] = dedupe(list(r["postings"])
                                   + extra[r["employer_name"]])
            r["sitemap_pass_postings"] = len(extra[r["employer_name"]])
        merged.append(r)
    return merged


def summarize(doc, population="company_ats.never_found"):
    rows = _employers(doc, population, merge_sitemap_pass=True)
    n = len(rows)
    print("=" * 72)
    print(f"JSON-LD COVERAGE  --  population: {population}")
    print("=" * 72)
    print(f"run started         {doc['started_at']}")
    print(f"run finished        {doc['finished_at']}")
    print(f"employers probed    {n}")
    print(f"requests, total     {doc['requests_total']}  "
          f"= pass 1 {doc['requests_page'] + doc['requests_robots']} "
          f"(page {doc['requests_page']} + robots {doc['requests_robots']}) "
          f"+ sitemap pass {doc.get('sitemap_pass_requests', 0)}")
    print(f"request ceiling     {doc['max_requests']}")
    print(f"delay/host-delay    {doc['delay']}s / {doc['host_delay']}s")
    print(f"user agent          {doc['user_agent']}")
    print(f"blocklisted hosts   {doc['blocked_hosts']}")

    print("\nCAREERS-PAGE OUTCOME")
    print("-" * 72)
    outcomes = collections.Counter(r["careers_outcome"] for r in rows)
    for k, v in outcomes.most_common():
        print(f"  {k:<22} {v:>4}   {100.0*v/n:>5.1f}%")
    reached = [r for r in rows if r["careers_outcome"] == FETCHED]
    print(f"  {'REACHED (denominator)':<22} {len(reached):>4}")

    print("\nJobPosting FOUND")
    print("-" * 72)
    with_posting = [r for r in rows if r["postings"]]
    ld_only = [r for r in with_posting if r["postings_on_careers_page"]]
    via_detail = [r for r in with_posting if r["detail_pages_with_jobposting"]]
    micro = [r for r in rows if r["microdata_scopes"]]
    rdfa = [r for r in rows if r["rdfa_scopes"]]
    spa = [r for r in reached if r["looks_like_spa"] and not r["postings"]]
    print(f"  employers with >=1 parseable JobPosting   {len(with_posting):>4}"
          f"  of {n}   ({100.0*len(with_posting)/n:.1f}%)")
    if reached:
        print(f"  ... as a fraction of employers REACHED    "
              f"{len(with_posting):>4}  of {len(reached)}   "
              f"({100.0*len(with_posting)/len(reached):.1f}%)")
    # THE THREE DISCOVERY PATHS, AND WHY THEY MUST SUM TO THE HEADLINE.
    #
    # The first two lines here describe pass 1 only. The sitemap pass had no
    # line at all, so with a headline of 2 the sub-counts summed to 1 and the
    # difference could only be resolved by opening the raw JSON. A breakdown
    # that does not reconcile against the number above it is worse than no
    # breakdown: it reads as an arithmetic error in the headline.
    #
    # Assigned by PRECEDENCE, not by membership, so no employer is counted
    # twice: careers page beats detail page beats sitemap. An employer found
    # by two paths appears under the earliest one.
    detail_only = [r for r in via_detail if not r["postings_on_careers_page"]]
    sitemap_only = [r for r in with_posting
                    if not r["postings_on_careers_page"]
                    and not r["detail_pages_with_jobposting"]
                    and r.get("sitemap_pass_postings", 0)]
    print(f"  found on the careers page itself          {len(ld_only):>4}")
    print(f"  found only on a job-detail page           {len(detail_only):>4}")
    print(f"  found only via the sitemap pass           {len(sitemap_only):>4}")
    accounted = len(ld_only) + len(detail_only) + len(sitemap_only)
    print(f"  ... those three sum to                    {accounted:>4}"
          f"   (must equal {len(with_posting)})")
    if accounted != len(with_posting):
        # Loud rather than silent. If a fourth path is ever added and this
        # breakdown is not updated, the discrepancy prints itself instead of
        # waiting to be found in the JSON.
        print(f"  *** UNRECONCILED: {len(with_posting) - accounted} employer(s) "
              f"publish JobPosting via no counted path ***")
    # n is small enough that naming them is the whole point: a reader cannot
    # judge whether two employers generalise without knowing which two.
    for label, group in (("careers page", ld_only), ("job-detail page",
                         detail_only), ("sitemap pass", sitemap_only)):
        for r in group:
            print(f"      via {label:<16} {r['employer_name']} "
                  f"({len(r['postings'])} posting(s))")
    print(f"  microdata JobPosting scopes seen          {len(micro):>4}")
    print(f"  RDFa typeof=JobPosting seen (count only)  {len(rdfa):>4}")
    print(f"  reached, no JobPosting, looks like an SPA {len(spa):>4}")
    print(f"  unparseable ld+json blocks (all pages)    "
          f"{sum(r['ld_blocks_unparseable'] for r in rows):>4}")
    total_postings = sum(len(r["postings"]) for r in rows)
    print(f"  distinct postings harvested               {total_postings:>4}")

    print("\nFIELD COMPLETENESS")
    print("-" * 72)
    if total_postings:
        print(f"  {'field':<26} {'postings':>9} {'% postings':>11} "
              f"{'employers':>10} {'% employers':>12}")
        for f in FIELDS:
            got = sum(1 for r in rows for p in r["postings"] if p["fields"][f])
            emp = sum(1 for r in rows
                      if r["postings"] and all(p["fields"][f] for p in r["postings"]))
            print(f"  {f:<26} {got:>9} {100.0*got/total_postings:>10.1f}% "
                  f"{emp:>10} "
                  f"{(100.0*emp/len(with_posting) if with_posting else 0):>11.1f}%")
        print("  (% employers = employers where EVERY harvested posting has "
              "the field)")
    else:
        print("  no postings harvested -- no completeness table to print")

    print("\nPER-EMPLOYER")
    print("-" * 72)
    print(f"  {'employer':<44} {'outcome':<18} {'post':>4} {'flds':>4} "
          f"{'sitemap job urls':>17}")
    for r in sorted(rows, key=lambda x: (-len(x["postings"]),
                                         x["employer_name"])):
        nfields = 0
        if r["postings"]:
            nfields = max(sum(1 for f in FIELDS if p["fields"][f])
                          for p in r["postings"])
        sm = r["sitemap"]
        smtxt = f"{sm.get('job_urls', 0)}/{sm.get('total_urls', 0)}"
        if sm.get("job_urls_with_lastmod"):
            smtxt += f" lm={sm['job_urls_with_lastmod']}"
        print(f"  {r['employer_name'][:44]:<44} {r['careers_outcome']:<18} "
              f"{len(r['postings']):>4} {nfields:>4} {smtxt:>17}")

    print("\nSITEMAPS")
    print("-" * 72)
    with_sm = [r for r in rows if r["sitemap"].get("outcome") == FETCHED]
    with_jobs = [r for r in rows if r["sitemap"].get("job_urls", 0) > 0]
    with_lm = [r for r in rows if r["sitemap"].get("job_urls_with_lastmod", 0) > 0]
    print(f"  employers with a fetchable sitemap        {len(with_sm):>4} of {n}")
    print(f"  ... carrying job-shaped URLs              {len(with_jobs):>4} of {n}")
    print(f"  ... with <lastmod> on those URLs          {len(with_lm):>4} of {n}")
    print(f"  total job-shaped sitemap URLs seen        "
          f"{sum(r['sitemap'].get('job_urls', 0) for r in rows):>4}")

    print("\nFRESHNESS (datePosted on harvested postings)")
    print("-" * 72)
    _freshness(rows, doc)

    # The sitemap pass is not an appendix -- it is where the second of the two
    # publishers was found, and every count above already includes it. Printing
    # it only under a separate flag is how a figure ends up in a document with
    # no way to reproduce it.
    if doc.get("sitemap_pass"):
        print()
        summarize_sitemap_pass(doc)


#: Y-M-D with the month and day NOT zero-padded. `datetime.date.fromisoformat`
#: rejects these, and every `datePosted` this run harvested is in this shape:
#: Moody's publishes "2026-6-10", not "2026-06-10". A first cut of this
#: function used fromisoformat alone and reported "0 of 3 postings have a
#: parseable datePosted" -- next to a completeness table saying datePosted was
#: present on 100% of them. Both numbers were produced by this tool and they
#: contradicted each other, which is the only reason it was caught. Anything
#: task 19 builds needs this tolerance on day one; schema.org says the field
#: is an ISO 8601 Date and the wild disagrees.
_LOOSE_DATE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})")


def evidence(doc, population="all"):
    """Every observation the prose in docs/jsonld-coverage.md cites.

    WHY THIS MODE EXISTS. A previous agent on this project shipped a document
    claiming "every number below is printed by the tool" where four headline
    figures were printed nowhere and no flag produced them. The summary
    aggregates; a document also cites shapes ("what were those sitemap URLs
    actually?") and raw values ("what does datePosted literally say?"), and
    if the tool does not print those, the document is asserting from a
    scratch buffer. So it prints them.
    """
    rows = _employers(doc, population, merge_sitemap_pass=True)
    print("=" * 72)
    print(f"EVIDENCE  --  population: {population}")
    print("=" * 72)

    print("\nWHY PASS 2 EXISTS: job-detail links found in careers-page HTML")
    print("-" * 72)
    reached = [r for r in rows if r["careers_outcome"] == FETCHED]
    dist = collections.Counter(r["detail_pages_tried"] for r in rows)
    print(f"  detail_pages_tried distribution           "
          f"{dict(sorted(dist.items()))}")
    print(f"  employers reached                         {len(reached)}")
    zero = [r for r in reached if r["detail_pages_tried"] == 0]
    print(f"  reached with ZERO crawlable job links     {len(zero)}")
    print(f"  detail pages opened, all employers        "
          f"{sum(r['detail_pages_tried'] for r in rows)}")
    print(f"  detail page outcomes                      "
          f"{dict(collections.Counter(o['outcome'] for r in rows for o in r['detail_outcomes']))}")

    print("\nld+json ISLANDS SEEN (careers pages, pass 1)")
    print("-" * 72)
    print(f"  ld+json <script> blocks found             "
          f"{sum(r['ld_blocks'] for r in rows)}")
    print(f"  ... that did not parse as JSON            "
          f"{sum(r['ld_blocks_unparseable'] for r in rows)}")
    print(f"  employers whose careers page had >=1      "
          f"{sum(1 for r in rows if r['ld_blocks'])}")
    print(f"  employers whose careers page had a        "
          f"{sum(1 for r in rows if r['postings_on_careers_page'])}")
    print("      JobPosting in one of them")

    print("\nEVERY HARVESTED POSTING, RAW")
    print("-" * 72)
    for r in rows:
        for p in r["postings"]:
            print(f"  {r['employer_name']}")
            print(f"    title        {p['title'][:90]}")
            print(f"    datePosted   {p['datePosted']!r}"
                  f"   -> parsed {_parse_date(p['datePosted'])}")
            print(f"    validThrough {p['validThrough']!r}")
            print(f"    identifier   {p['identifier']!r}   url {p['url'][:80]!r}")
            print(f"    found_at     {p.get('found_at', '(careers-page crawl)')[:100]}")
            print(f"    fields       "
                  f"{sorted(f for f, v in p['fields'].items() if v)}")

    print("\nEVERY JOB PAGE OPENED IN THE SITEMAP PASS")
    print("-" * 72)
    print("  (the URL shapes -- this is how 'job-shaped sitemap URL' counts")
    print("   were shown to be mostly category and content pages)")
    for r in doc.get("sitemap_pass") or []:
        print(f"\n  {r['employer_name']}  "
              f"declared={r['job_urls_declared']}  sitemap={r['sitemap_url'][:70]}")
        for p in r["pages"]:
            print(f"    {p['outcome']:<14} ld={p['ld_blocks']} "
                  f"jobposting={p['postings']}  {p['url'][:100]}")

    print("\nEVERY DETAIL PAGE OPENED IN PASS 1")
    print("-" * 72)
    for r in rows:
        if not r["detail_outcomes"]:
            continue
        print(f"\n  {r['employer_name']}  (postings found: {len(r['postings'])})")
        for o in r["detail_outcomes"]:
            print(f"    {o['outcome']:<14} {o['url'][:100]}")


def _parse_date(s):
    if not s:
        return None
    s = s.strip()
    try:
        return datetime.date.fromisoformat(s[:10])
    except ValueError:
        pass
    m = _LOOSE_DATE.match(s)
    if m:
        try:
            return datetime.date(int(m.group(1)), int(m.group(2)),
                                 int(m.group(3)))
        except ValueError:
            return None
    try:
        return datetime.datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _freshness(rows, doc):
    asof = _parse_date(doc.get("started_at", "")) or datetime.date.today()
    dated = []
    for r in rows:
        for p in r["postings"]:
            d = _parse_date(p["datePosted"])
            if d:
                dated.append((r["employer_name"], d))
    total = sum(len(r["postings"]) for r in rows)
    print(f"  postings with a parseable datePosted      {len(dated):>4} of {total}")
    if not dated:
        print("  no dated postings -- no posting-rate estimate is possible")
        return
    for window in (7, 30, 90):
        k = sum(1 for _, d in dated if (asof - d).days <= window)
        print(f"  posted within {window:>2}d of the run           {k:>4}"
              f"   -> {k/window:.2f}/day across this population")
    ages = sorted((asof - d).days for _, d in dated)
    mid = ages[len(ages) // 2]
    print(f"  median age of a dated posting             {mid:>4} days")
    print(f"  oldest / newest                           "
          f"{max(ages)} / {min(ages)} days")


# --------------------------------------------------------------------------
# The estimate
# --------------------------------------------------------------------------

GATE_DOC = "docs/pursuit-gate-volume.md"


def estimate(doc, conn, population="company_ats.never_found"):
    """postings/day, then relevant postings/day, every step printed.

    The gate is applied by pushing harvested titles into a TEMP table and
    evaluating relevance.tier_sql() against it. CLAUDE.md: "Do not reimplement
    relevance matching in Python. One implementation, two callers." This is
    that implementation, called from a third place, not a fourth copy.
    """
    rows = _employers(doc, population, merge_sitemap_pass=True)
    n = len(rows)
    reached = [r for r in rows if r["careers_outcome"] == FETCHED]
    with_posting = [r for r in rows if r["postings"]]
    postings = [(r["employer_name"], p) for r in rows for p in r["postings"]]

    print("=" * 72)
    print("POSTINGS/DAY DERIVATION")
    print("=" * 72)
    print(f"  step 0  employers in population           {n}")
    print(f"  step 1  reached (careers page fetched)    {len(reached)}")
    print(f"  step 2  publishing parseable JobPosting   {len(with_posting)}")
    print(f"  step 3  distinct postings harvested       {len(postings)}")

    if not postings:
        print("\n  NO POSTINGS HARVESTED.")
        print("  There is no defensible postings/day estimate from this run.")
        print("  CLAUDE.md: 'Do not re-tune on a provisional number.'")
        return

    asof = _parse_date(doc.get("started_at", "")) or datetime.date.today()
    dated = [(e, _parse_date(p["datePosted"])) for e, p in postings]
    dated = [(e, d) for e, d in dated if d]
    print(f"  step 4  postings with a datePosted        {len(dated)}"
          f"  ({100.0*len(dated)/len(postings):.1f}%)")

    if not dated:
        print("\n  NO POSTING CARRIES A PARSEABLE datePosted.")
        print("  A per-day rate cannot be derived from a stock with no dates.")
        return

    fresh30 = sum(1 for _, d in dated if (asof - d).days <= 30)
    rate = fresh30 / 30.0
    print(f"  step 5  posted in the 30d before the run  {fresh30}")
    print(f"  step 6  => raw postings/day, this sample  {rate:.2f}/day")
    print(f"          (that is {fresh30} / 30, over {len(with_posting)} "
          f"employers)")

    # Coverage correction. What was harvested is a sample of what these
    # employers publish, not a census: at most DETAIL_LINKS_PER_EMPLOYER detail
    # pages were opened. Sitemap job-URL counts are the honest denominator
    # where they exist.
    sitemap_jobs = sum(r["sitemap"].get("job_urls", 0) for r in with_posting)
    print(f"  step 7  sitemap job URLs at those same    {sitemap_jobs}")
    print(f"          employers (an upper bound on their live stock)")

    print("\n  RELEVANCE GATE (relevance.tier_sql, production config)")
    print("  " + "-" * 68)
    tier1, tier2, tier3 = _gate_titles(conn, postings)
    tot = tier1 + tier2 + tier3
    print(f"  step 8  harvested titles gated            {tot}")
    print(f"          tier 1 (relevant AND NYC/remote)   {tier1}")
    print(f"          tier 2 (relevant, location no)     {tier2}")
    print(f"          tier 3 (not relevant)              {tier3}")
    print("          NOTE: title-only. description_text is NULL for every")
    print("          row here, so the description path of the gate cannot")
    print("          fire and tier 1+2 is a FLOOR on what the real gate")
    print("          would pass.")
    frac = (tier1 + tier2) / tot if tot else 0.0
    print(f"  step 9  relevant fraction of harvested    {frac:.3f}")
    print(f"  step 10 => relevant postings/day          "
          f"{rate * frac:.2f}/day")
    print("\n  STEPS 5-10 ARE NOT A YIELD, AND MUST NOT BE QUOTED AS ONE.")
    print("  At most three job pages were opened per employer, so what was")
    print("  harvested is a SAMPLE of two employers' boards, not a census of")
    print("  them. n=6 postings. CLAUDE.md: 'n=17 is not a result.' The")
    print("  coverage fraction at step 2 is the measured quantity here; the")
    print("  per-employer posting rate is not measured at all.")
    upper_bound(doc, conn, population, tier1_frac=frac)


#: Inputs to the upper bound, each one chosen to FAVOUR task 19. The point of
#: the bound is that it fails even when every uncertain quantity is resolved
#: generously, so a reader who disputes one of these numbers has to dispute it
#: upward, and there is not room upward.
#:
#: open_postings_per_employer: 100. The two employers that publish JobPosting
#:   declared 36 (Etsy) and an uncountable number (Moody's -- its sitemap's
#:   "job" URLs are faceted category pages, see _LISTING_PATH, so its live
#:   stock was never established). 100 is above both and above the median
#:   board size of the ATS tokens already ingested.
#: posting_lifetime_days: 30. Shorter means more churn means more new postings
#:   per day, so 30 is generous; the ATS feeds in this pipeline show longer.
#: relevant_fraction: the range docs/pursuit-gate-volume.md measured on the
#:   corpus that already exists -- 13.7% clear the AI-vocab + entry-level +
#:   NYC/remote gate, and 6.7% survived hand-checking (n=30). Using the
#:   pipeline's own funnel rather than the n=6 gate result above, which cannot
#:   resolve anything.
UPPER_BOUND_OPEN_POSTINGS = 100
UPPER_BOUND_LIFETIME_DAYS = 30
GATE_FRACTIONS = (("hand-checked precision, n=30", 0.067),
                  ("AI-vocab + entry-level + NYC/remote", 0.137))


def upper_bound(doc, conn, population, tier1_frac=None):
    """The generous bound. Every input printed, every step shown."""
    rows = _employers(doc, population, merge_sitemap_pass=True)
    n = len(rows)
    with_posting = sum(1 for r in rows if r["postings"])
    true_pop = conn.execute("""
        SELECT (SELECT count(*) FROM company_ats WHERE status='never_found')
             + (SELECT count(*) FROM ats_seed WHERE last_probe_outcome='not_found'
                AND employer_name NOT IN (SELECT employer_name FROM company_ats
                                          WHERE status='never_found'))""").fetchone()[0]

    print("\n" + "=" * 72)
    print("UPPER BOUND ON TASK 19's YIELD")
    print("=" * 72)
    print("  Every input below is chosen to favour task 19. This is a ceiling,")
    print("  not an estimate.\n")
    cov = with_posting / n if n else 0.0
    print(f"  a  employers probed                        {n}")
    print(f"  b  publishing parseable JobPosting         {with_posting}")
    print(f"  c  coverage = b/a                          {cov:.3f}"
          f"  ({100*cov:.1f}%)")
    print(f"  d  true 'probed, no ATS' population        {true_pop}"
          f"   (company_ats.never_found + ats_seed.not_found)")
    employers = cov * true_pop
    print(f"  e  employers in d expected to publish      {employers:.1f}"
          f"   = c x d")
    print(f"  f  ASSUMED open postings per employer      "
          f"{UPPER_BOUND_OPEN_POSTINGS}   (generous; see GATE note)")
    print(f"  g  ASSUMED posting lifetime, days          "
          f"{UPPER_BOUND_LIFETIME_DAYS}   (generous)")
    gross = employers * UPPER_BOUND_OPEN_POSTINGS / UPPER_BOUND_LIFETIME_DAYS
    print(f"  h  gross new postings/day                  {gross:.1f}"
          f"   = e x f / g")
    print()
    for label, frac in GATE_FRACTIONS:
        print(f"  i  relevant fraction ({label}): {frac}")
        print(f"  j  => RELEVANT POSTINGS/DAY                {gross*frac:.2f}/day")
    lo = gross * GATE_FRACTIONS[0][1]
    hi = gross * GATE_FRACTIONS[1][1]
    print(f"\n  UPPER BOUND: {lo:.1f} - {hi:.1f} relevant postings/day.")
    print(f"  TASK 19 CLAIMS 30-60/day (19-jsonld-parser.md:4).")
    if hi > 0:
        print(f"  The claim is {30.0/hi:.0f}x - {60.0/lo:.0f}x the CEILING "
              f"measured here.")
    # The single assumption most likely to be wrong is "no JavaScript was
    # executed". Bound it rather than argue about it: credit task 19 with
    # EVERY employer that looks like an SPA shell also publishing perfect
    # JSON-LD behind JavaScript, and re-run the same arithmetic.
    spa = sum(1 for r in rows
              if r["careers_outcome"] == FETCHED and r["looks_like_spa"]
              and not r["postings"])
    cov_spa = (with_posting + spa) / n if n else 0.0
    gross_spa = cov_spa * true_pop * UPPER_BOUND_OPEN_POSTINGS / \
        UPPER_BOUND_LIFETIME_DAYS
    print("\n  SENSITIVITY: if every SPA shell hides perfect JSON-LD")
    print(f"    reached, no JobPosting, looks like an SPA  {spa}")
    print(f"    coverage would be                          "
          f"{with_posting + spa} of {n}  ({100*cov_spa:.1f}%)")
    print(f"    gross new postings/day                     {gross_spa:.1f}")
    print(f"    => relevant postings/day                   "
          f"{gross_spa*GATE_FRACTIONS[0][1]:.1f} - "
          f"{gross_spa*GATE_FRACTIONS[1][1]:.1f}/day")
    print(f"    still short of 30-60/day, and it would cost a Firecrawl")
    print(f"    fetch per page forever -- task 20's budget.")

    print("\n  And the ceiling is not reachable: it credits task 19 with every")
    print("  posting at every publishing employer, while the only two found")
    print("  publish 3 pages' worth between them and one of them (Etsy) is")
    print("  not in the never_found population task 19 exists to serve.")


def _gate_titles(conn, postings):
    """(tier1, tier2, tier3) for harvested titles, via relevance.tier_sql().

    A TEMP table shaped like the columns tier_sql touches: title,
    description_text, company_name, platform, location_is_nyc,
    location_is_remote. NULL description_text is faithful -- the JSON-LD
    descriptions were deliberately not kept (see summarize_posting) and, more
    to the point, an ingest built on this data would not have run the LLM
    extraction that fills the location booleans either.
    """
    cfg = relevance.load()
    sql, params = relevance.tier_sql(cfg, table_alias="t")
    conn.execute("""
        CREATE TEMP TABLE IF NOT EXISTS jsonld_probe_titles (
            title TEXT, description_text TEXT, company_name TEXT,
            platform TEXT, location_is_nyc BOOLEAN, location_is_remote BOOLEAN
        ) ON COMMIT DROP""")
    conn.execute("DELETE FROM jsonld_probe_titles")
    for employer, p in postings:
        loc = (p.get("location_text") or "").lower()
        is_nyc = bool(re.search(
            r"new york|nyc|manhattan|brooklyn|queens|bronx|staten island|"
            r"\bny\b", loc))
        is_remote = "remote" in loc or "telecommute" in loc
        conn.execute(
            "INSERT INTO jsonld_probe_titles VALUES (%s,%s,%s,%s,%s,%s)",
            (p["title"], None, employer, "jsonld_probe", is_nyc, is_remote))
    counts = dict(conn.execute(
        f"SELECT {sql} AS tier, count(*) FROM jsonld_probe_titles t "
        f"GROUP BY 1", params).fetchall())
    conn.rollback()
    return counts.get(1, 0), counts.get(2, 0), counts.get(3, 0)


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--report", action="store_true",
                   help="population only, no network")
    p.add_argument("--run", action="store_true", help="probe the population")
    p.add_argument("--summarize", metavar="RESULTS.json")
    p.add_argument("--estimate", metavar="RESULTS.json")
    p.add_argument("--evidence", metavar="RESULTS.json",
                   help="every raw observation the coverage document cites")
    p.add_argument("--sitemap-pass", metavar="RESULTS.json",
                   help="second pass: open real job URLs from each employer's "
                        "sitemap. Updates the results file in place.")
    p.add_argument("--population", default="company_ats.never_found",
                   help="which population to summarize/estimate over")
    p.add_argument("--out", default=None, help="results file for --run")
    p.add_argument("--limit", type=int, default=0,
                   help="probe only the first N employers (0 = all)")
    p.add_argument("--extra-sample", type=int, default=0,
                   help="additionally probe N random ats_seed not_found "
                        "employers, as a representativeness control")
    p.add_argument("--delay", type=float, default=1.5)
    p.add_argument("--host-delay", type=float, default=5.0)
    p.add_argument("--max-requests", type=int, default=400)
    p.add_argument("--timeout", type=float, default=TIMEOUT)
    p.add_argument("--no-details", action="store_true",
                   help="do not follow job-detail links")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    if args.summarize:
        with open(args.summarize) as f:
            summarize(json.load(f), args.population)
        return 0

    if args.evidence:
        with open(args.evidence) as f:
            evidence(json.load(f), args.population)
        return 0

    if args.sitemap_pass:
        with open(args.sitemap_pass) as f:
            doc = json.load(f)
        fetcher = Fetcher(delay=args.delay, host_delay=args.host_delay,
                          max_requests=args.max_requests, timeout=args.timeout,
                          verbose=args.verbose)
        # Results recorded before sample_job_urls existed carry counts but no
        # URLs. Re-derive the sitemap for exactly those employers rather than
        # re-running the whole first pass.
        for row in doc["employers"]:
            sm = row.get("sitemap") or {}
            if sm.get("job_urls", 0) > 0 and not sm.get("sample_job_urls"):
                print(f"  re-deriving sitemap: {row['employer_name']}",
                      file=sys.stderr, flush=True)
                row["sitemap"] = probe_sitemap(fetcher, row["careers_url"])
        before = fetcher.total_requests
        doc["sitemap_pass"] = sitemap_pass(fetcher, doc)
        doc["sitemap_pass_at"] = datetime.datetime.now(
            datetime.timezone.utc).isoformat(timespec="seconds")
        doc["sitemap_pass_requests"] = fetcher.total_requests
        doc["sitemap_pass_page_requests"] = fetcher.total_requests - before
        doc["sitemap_pass_blocked_hosts"] = sorted(fetcher.blocked_hosts)
        doc["requests_total"] = doc.get("requests_total", 0) + \
            fetcher.total_requests
        with open(args.sitemap_pass, "w") as f:
            json.dump(doc, f, indent=1, sort_keys=True)
        print(f"\nupdated {args.sitemap_pass}", file=sys.stderr)
        summarize_sitemap_pass(doc)
        return 0

    if args.estimate:
        with open(args.estimate) as f:
            doc = json.load(f)
        conn = dbconn.connect()
        try:
            estimate(doc, conn, args.population)
        finally:
            conn.close()
        return 0

    conn = dbconn.connect()
    try:
        if args.report or not args.run:
            report_population(conn)
            if not args.run:
                return 0
        rows = load_population(conn, extra_sample=args.extra_sample)
    finally:
        conn.close()

    if args.limit:
        rows = rows[:args.limit]

    fetcher = Fetcher(delay=args.delay, host_delay=args.host_delay,
                      max_requests=args.max_requests, timeout=args.timeout,
                      verbose=args.verbose)
    started = datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds")
    results = []
    for i, row in enumerate(rows, 1):
        print(f"[{i}/{len(rows)}] {row['employer_name']} "
              f"({row['careers_url']})", file=sys.stderr, flush=True)
        r = probe_employer(fetcher, row, follow_details=not args.no_details)
        r["population"] = row["population"]
        results.append(r)
        print(f"    {r['careers_outcome']}  postings={len(r['postings'])}  "
              f"req={r['requests_used']}  "
              f"(total {fetcher.total_requests}/{args.max_requests})",
              file=sys.stderr, flush=True)
        if fetcher.total_requests >= args.max_requests:
            print("    request ceiling reached; stopping", file=sys.stderr)
            break

    doc = {
        "started_at": started,
        "finished_at": datetime.datetime.now(datetime.timezone.utc).isoformat(
            timespec="seconds"),
        "user_agent": USER_AGENT,
        "delay": args.delay,
        "host_delay": args.host_delay,
        "max_requests": args.max_requests,
        "timeout": args.timeout,
        "detail_links_per_employer": (0 if args.no_details
                                      else DETAIL_LINKS_PER_EMPLOYER),
        "requests_total": fetcher.total_requests,
        "requests_page": fetcher.requests,
        "requests_robots": fetcher.robots_requests,
        "blocked_hosts": sorted(fetcher.blocked_hosts),
        "employers_planned": len(rows),
        "employers": results,
    }
    out = args.out or os.path.join(
        _REPO_ROOT, "data", f"jsonld-probe-{started[:10]}.json")
    with open(out, "w") as f:
        json.dump(doc, f, indent=1, sort_keys=True)
    print(f"\nwrote {out}", file=sys.stderr)
    summarize(doc, args.population)
    return 0


if __name__ == "__main__":
    sys.exit(main())
