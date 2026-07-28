"""Which NYC employer runs which ATS -- signatures, validators, outcomes.

The endpoints in ingest/ats.py are trivial. Knowing that Mount Sinai's
Greenhouse token is `mountsinai` and not `mount-sinai` is the actual work, and
there is no public directory of board tokens. This module is the half of that
work with no I/O in it: the regexes that read a token out of a careers page,
the URL builders that ask the ATS to confirm it, and the vocabulary the probe
uses to say *why* it found nothing.

WHY PROBING WORKS AT ALL
    A company with no Greenhouse board returns 404 for one HTTP request, so
    precision comes from validation rather than from curating the seed list.
    A big, dumb list of employers is therefore fine as an input -- which is
    what makes `data/nyc-employer-seed.json` a flat data file that anyone can
    append to, and what makes `ats_seed` a table rather than a config.

THE DISTINCTION THIS MODULE EXISTS TO PRESERVE
    "Found no token" and "was not allowed to look" are the same observation to
    a naive probe: zero rows either way. CLAUDE.md names that this pipeline's
    failure mode, and a discovery pass is the worst possible place for it --
    a run blocked at the front door writes an empty table, and the next run
    reads that table as settled fact.

    So every probe records an OUTCOME from the closed set below, and the two
    are never conflated:

      FOUND         page fetched, at least one ATS signature matched
      NOT_FOUND     page fetched, parsed, no signature -- a real negative
      BLOCKED       403/429/WAF body -- we were refused; says NOTHING about
                    the employer, and never writes a company_ats row
      UNREACHABLE   DNS failure, timeout, connection reset, 5xx
      MISSING_PAGE  404/410 on every candidate careers URL we know
      NO_URL        the seed row has no careers_url to probe
      SKIPPED       budget exhausted or host already blocked this run

    Only NOT_FOUND may become `status='never_found'`. BLOCKED and UNREACHABLE
    leave the employer un-probed as far as company_ats is concerned, stay
    counted in ats_seed.last_probe_status, and get retried next month.

STATUS VALUES, AND THE ONE THE TASK DID NOT HAVE
    16-ats-token-discovery.md lists `valid | dead | never_found`. There is no
    value there for "a token was found but we could not reach the ATS to check
    it", which collapses back into the same silence problem one level down: an
    unvalidated token that gets written as `valid` contributes zero rows
    forever and looks healthy, and one written as `dead` is deleted evidence.
    STATUS_UNVALIDATED is that fourth value. It is also what platforms with no
    public JSON feed (Taleo, Oracle, SuccessFactors ...) carry, since detecting
    them is real information for tasks 18 and 20 even though this module cannot
    confirm them.
"""

import json
import re
import urllib.parse

# -- probe outcomes ----------------------------------------------------------

FOUND = "found"
NOT_FOUND = "not_found"
BLOCKED = "blocked"
UNREACHABLE = "unreachable"
MISSING_PAGE = "missing_page"
NO_URL = "no_url"
SKIPPED = "skipped"

#: Outcomes that mean we genuinely observed the employer's careers page. Only
#: these two may write a company_ats row; everything else is an observation
#: about the network, not about the employer.
CONCLUSIVE = (FOUND, NOT_FOUND)

#: Outcomes that mean the probe was refused or failed. Counted separately in
#: every report, because a run where these dominate has measured nothing.
INCONCLUSIVE = (BLOCKED, UNREACHABLE, MISSING_PAGE, NO_URL, SKIPPED)

# -- row status --------------------------------------------------------------

STATUS_VALID = "valid"
STATUS_DEAD = "dead"
STATUS_NEVER_FOUND = "never_found"
STATUS_UNVALIDATED = "unvalidated"


# -- ATS signatures ----------------------------------------------------------
#
# Ordered: the first pattern that matches a URL wins for that URL, but every
# pattern is run against the whole page, so one careers page may yield several
# platforms (a footer link to an old board plus the live one). Validation is
# what sorts those out -- see the module docstring.
#
# Every token group is bounded to 2+ characters. A one-character capture is
# almost always a path fragment (`boards.greenhouse.io/e...`) and validating it
# spends a request to learn nothing.

#: Path segments that appear where a board token would and are never one.
#: `embed` is the big one: boards.greenhouse.io/embed/job_board?for=TOKEN puts
#: the real token in the query string, which the second Greenhouse pattern
#: reads. Without this exclusion every employer using the embed form is
#: recorded with the token `embed`, which 404s and lands as `dead` -- a false
#: negative that looks exactly like a migrated company.
_NOT_A_TOKEN = {
    "embed", "www", "api", "job", "jobs", "job-boards", "boards", "careers",
    "search", "static", "assets", "images", "css", "js", "index", "en-us",
    "en", "us", "login", "apply", "widget", "v1", "v2", "v3", "support",
    "help", "about", "privacy", "terms", "sitemap", "home",
    # Build-output paths that sit where a tenant slug would. Observed live:
    # jobvite.com/__assets__/... produced the token `__assets__` for the NYC
    # Housing Development Corporation.
    "__assets__", "assets_", "_next", "__next", "dist", "build",
}

#: (platform, compiled pattern, group names in capture order).
#:
#: WORKDAY IS THE ONE THAT NEEDS CARE. Its URLs are
#:     https://{tenant}.wd{N}.myworkdayjobs.com/{locale}/{site}
#: where {locale} ("en-US", "fr-CA", ...) is OPTIONAL. A pattern that captures
#: the first path segment as the site records `en-US` for every employer that
#: includes it, and task 18 then POSTs to /wday/cxs/{tenant}/en-US/jobs and
#: gets a 404. The locale group below is non-capturing and optional, which is
#: the whole reason it is written out rather than `([\w-]+)`.
#:
#: Getting wd1 vs wd5 wrong is likewise a 404, so the data centre is captured
#: as its own group and stored in its own column -- task 18 reads it from
#: there and is forbidden to guess.
SIGNATURES = (
    ("greenhouse",
     re.compile(r"(?:boards|job-boards|boards-api)\.greenhouse\.io/"
                r"(?!embed\b)([A-Za-z0-9_.-]{2,})", re.I),
     ("token",)),
    # The embed form comes in several spellings -- .../job_board?for=X,
    # .../job_board/js?for=X, and either of those with other query parameters
    # ahead of `for`, HTML-escaped (`&amp;`) as often as not. Anchoring on
    # `for=` rather than on the path is what covers all of them.
    ("greenhouse",
     re.compile(r"greenhouse\.io/embed/job_board[^\s\"']*?[?&](?:amp;)?"
                r"for=([A-Za-z0-9_.-]{2,})", re.I),
     ("token",)),
    ("lever",
     re.compile(r"jobs\.(?:eu\.)?lever\.co/([A-Za-z0-9_.-]{2,})", re.I),
     ("token",)),
    ("ashby",
     re.compile(r"jobs\.ashbyhq\.com/([A-Za-z0-9_.-]{2,})", re.I),
     ("token",)),
    ("workable",
     re.compile(r"apply\.workable\.com/([A-Za-z0-9_-]{2,})", re.I),
     ("token",)),
    ("recruitee",
     re.compile(r"([A-Za-z0-9_-]{2,})\.recruitee\.com", re.I),
     ("token",)),
    ("smartrecruiters",
     re.compile(r"(?:careers|jobs)\.smartrecruiters\.com/([A-Za-z0-9_-]{2,})",
                re.I),
     ("token",)),
    ("workday",
     re.compile(r"([A-Za-z0-9_-]{2,})\.(wd\d+)\.myworkdayjobs\.com/"
                r"(?:[a-z]{2}-[A-Z]{2}/)?([A-Za-z0-9_-]{2,})", re.I),
     ("token", "workday_dc", "workday_site")),
    ("icims",
     re.compile(r"(?:careers|jobs)-([A-Za-z0-9_-]{2,})\.icims\.com", re.I),
     ("token",)),
    # The bare form, for tenants that do not use the careers- prefix. The
    # lookahead is load-bearing: without it `careers-montefiore.icims.com`
    # matches BOTH patterns -- once correctly as `montefiore` and once as
    # `careers-montefiore`, because `-` is in the character class. The second
    # is validated as careers-careers-montefiore.icims.com, 404s, and is
    # stored as a `dead` row sitting next to the valid one, which reads like
    # an employer mid-migration rather than like a regex bug.
    ("icims",
     re.compile(r"(?<![\w.-])(?!careers-|jobs-)([A-Za-z0-9_-]{2,})"
                r"\.icims\.com", re.I),
     ("token",)),
    # -- detected but not validatable ------------------------------------
    # No public JSON feed, so nothing below can be confirmed by this module
    # and every row lands as STATUS_UNVALIDATED. They are recorded anyway:
    # "which large NYC employers are on Taleo/Oracle" is exactly the skew the
    # task asks to be reported, and it is the input that decides how much of
    # the plan's weight tasks 18 and 20 carry.
    ("taleo",
     re.compile(r"([A-Za-z0-9_-]{2,})\.taleo\.net", re.I),
     ("token",)),
    ("oracle_cloud",
     re.compile(r"([A-Za-z0-9_-]{2,})\.oraclecloud\.com/hcmUI/CandidateExperience",
                re.I),
     ("token",)),
    ("successfactors",
     re.compile(r"career\d*\.successfactors\.com/career\?company="
                r"([A-Za-z0-9_-]{2,})", re.I),
     ("token",)),
    ("jobvite",
     re.compile(r"jobs\.jobvite\.com/([A-Za-z0-9_-]{2,})", re.I),
     ("token",)),
    ("bamboohr",
     re.compile(r"([A-Za-z0-9_-]{2,})\.bamboohr\.com/(?:careers|jobs)", re.I),
     ("token",)),
    ("adp",
     re.compile(r"workforcenow\.adp\.com/mascsr/default/mdf/recruitment/"
                r"recruitment\.html\?cid=([A-Za-z0-9-]{8,})", re.I),
     ("token",)),
    ("paylocity",
     re.compile(r"recruiting\.paylocity\.com/recruiting/jobs/All/"
                r"([A-Za-z0-9-]{8,})", re.I),
     ("token",)),
)

#: Platforms this module can confirm against a live feed. Everything else is
#: recorded as detected-but-unvalidated, with the reason in validation_note.
VALIDATABLE = ("greenhouse", "lever", "ashby", "workable", "recruitee",
               "smartrecruiters", "workday", "icims")

#: Platforms ingest/ats.py already handles today. Used only for reporting --
#: "how much of what we found can we ingest without writing new code".
INGESTIBLE_TODAY = ("greenhouse", "lever", "ashby")


def find_signatures(page_text):
    """Every (platform, fields) pair whose signature appears in `page_text`.

    Deduplicated on (platform, token, workday_site) and returned in a stable
    order, because a careers page routinely links the same board four times
    and each duplicate would otherwise cost a validation request.

    Pure. `page_text` is the raw response body -- HTML, JS, JSON, whatever the
    employer serves. The patterns match URLs wherever they appear, including
    inside a JS bundle, which is where single-page careers apps keep them.
    """
    seen, out = set(), []
    for platform, pattern, groups in SIGNATURES:
        for m in pattern.finditer(page_text):
            fields = dict(zip(groups, m.groups()))
            token = (fields.get("token") or "").strip(".-")
            if len(token) < 2 or token.lower() in _NOT_A_TOKEN:
                continue
            fields["token"] = token
            if "workday_dc" in fields:
                fields["workday_dc"] = fields["workday_dc"].lower()
            key = (platform, token.lower(),
                   (fields.get("workday_site") or "").lower())
            if key in seen:
                continue
            seen.add(key)
            out.append((platform, fields))
    return out


# -- validation endpoints ----------------------------------------------------
#
# Each entry is (method, url, json body or None). The token was read out of a
# page; these ask the ATS itself whether it is real. A signature sitting in a
# stale footer link is common, and an unvalidated token contributes zero rows
# forever -- which, again, is indistinguishable from a quiet employer.
#
# The Greenhouse URL is deliberately the one ingest/ats.py:152 already calls,
# not the boards-api host 17-retarget-ats-ingest.md:38 names. Validating
# against a different host than the ingest will use means validating something
# other than the thing that has to work.

def validation_request(platform, token, workday_site=None, workday_dc=None):
    """(method, url, body) that confirms this token, or None if unvalidatable."""
    if platform == "greenhouse":
        return ("GET",
                f"https://api.greenhouse.io/v1/boards/{token}/jobs", None)
    if platform == "lever":
        return ("GET",
                f"https://api.lever.co/v0/postings/{token}?mode=json", None)
    if platform == "ashby":
        return ("GET",
                f"https://api.ashbyhq.com/posting-api/job-board/{token}", None)
    if platform == "workable":
        return ("GET",
                f"https://apply.workable.com/api/v1/widget/accounts/{token}"
                f"?details=true", None)
    if platform == "recruitee":
        return ("GET", f"https://{token}.recruitee.com/api/offers/", None)
    if platform == "smartrecruiters":
        return ("GET",
                f"https://api.smartrecruiters.com/v1/companies/{token}"
                f"/postings?limit=10", None)
    if platform == "workday":
        if not (workday_site and workday_dc):
            return None
        # limit=20 and not one more. Workday returns an empty jobPostings
        # array with NO error for limit>20, byte-identical to "no results" --
        # CLAUDE.md's landmine, and asking for 100 here would validate every
        # live Workday tenant as dead.
        return ("POST",
                f"https://{token}.{workday_dc}.myworkdayjobs.com/wday/cxs/"
                f"{token}/{workday_site}/jobs",
                {"appliedFacets": {}, "limit": 20, "offset": 0,
                 "searchText": ""})
    if platform == "icims":
        # iCIMS publishes no JSON feed (which is why task 20 reaches for
        # Firecrawl). The search page is the only public surface, so
        # `open_jobs` stays None for this platform and validity means "the
        # portal exists and lists jobs".
        return ("GET",
                f"https://careers-{token}.icims.com/jobs/search?ss=1", None)
    return None


#: Job-count extraction per platform: (json key holding the list, key holding
#: a server-side total or None).
_COUNT_SHAPE = {
    "greenhouse": ("jobs", None),
    "ashby": ("jobs", None),
    "workable": ("jobs", None),
    "recruitee": ("offers", None),
    "smartrecruiters": ("content", "totalFound"),
    "workday": ("jobPostings", "total"),
}

_ICIMS_JOB_LINK = re.compile(r"/jobs/\d+/[^\"'?]+/job", re.I)


def open_job_count(platform, body):
    """Jobs the feed reports, or None if the body is not a countable feed.

    Returns an int (possibly 0 -- a real, meaningful answer: the board exists
    and is empty) or None (could not tell). The caller must not collapse those
    two, because 0 is `dead` and None is `unvalidated`.
    """
    if platform == "icims":
        return len(set(_ICIMS_JOB_LINK.findall(body or "")))
    if platform == "lever":
        try:
            data = json.loads(body)
        except (ValueError, TypeError):
            return None
        return len(data) if isinstance(data, list) else None

    shape = _COUNT_SHAPE.get(platform)
    if shape is None:
        return None
    try:
        data = json.loads(body)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    list_key, total_key = shape
    # Prefer the server-side total: SmartRecruiters and Workday both page, so
    # len(list) is one page and reconciling against `total` is the habit that
    # keeps a throttled page from reading as the end of a list.
    if total_key and isinstance(data.get(total_key), int):
        return data[total_key]
    items = data.get(list_key)
    if isinstance(items, list):
        return len(items)
    # Workable's widget nests differently across account types.
    if platform == "workable" and isinstance(data.get("jobs"), dict):
        return None
    return None


def classify_validation(platform, http_status, body):
    """(status, open_jobs, note) for one validation attempt.

    Called with http_status=None when the request could not be made at all,
    which is UNVALIDATED and never DEAD -- the distinction the whole module is
    built around.
    """
    if platform not in VALIDATABLE:
        return (STATUS_UNVALIDATED, None,
                f"no public feed for {platform}; detected from careers page only")
    if http_status is None:
        return (STATUS_UNVALIDATED, None, "validation request failed (network)")
    if http_status in (403, 429):
        return (STATUS_UNVALIDATED, None,
                f"validation refused with HTTP {http_status}")
    if http_status == 404:
        return (STATUS_DEAD, None, "endpoint returned 404")
    if http_status >= 500:
        return (STATUS_UNVALIDATED, None, f"endpoint returned HTTP {http_status}")
    if http_status != 200:
        return (STATUS_UNVALIDATED, None, f"endpoint returned HTTP {http_status}")

    count = open_job_count(platform, body)
    if count is None:
        return (STATUS_UNVALIDATED, None,
                "200 but the response was not a recognisable job feed")
    if count == 0:
        # A live board with zero open roles is real, and it is still `dead`
        # for this pipeline's purpose: it contributes nothing and re-probing
        # monthly is exactly how it flips back to valid when it reopens.
        return (STATUS_DEAD, 0, "endpoint returned an empty job list")
    return (STATUS_VALID, count, None)


# -- careers URL candidates --------------------------------------------------

#: Tried in order after the seeded careers_url 404s, and never more than
#: MAX_URL_CANDIDATES requests to one employer in total. Employer careers URLs
#: move constantly and the seed file is hand-assembled, so a 404 on the seeded
#: path is expected background noise rather than evidence about the employer --
#: but three guesses is where the value stops and the impoliteness starts.
_FALLBACK_PATHS = ("/careers", "/careers/", "/jobs", "/about/careers",
                   "/careers/job-opportunities")
MAX_URL_CANDIDATES = 3


def careers_url_candidates(careers_url, limit=MAX_URL_CANDIDATES):
    """The seeded URL first, then same-origin fallbacks. Pure."""
    if not careers_url:
        return []
    url = careers_url.strip()
    if not url:
        return []
    if "://" not in url:
        url = "https://" + url
    parsed = urllib.parse.urlsplit(url)
    if not parsed.netloc:
        return []
    origin = f"{parsed.scheme}://{parsed.netloc}"
    out = [url]
    for path in _FALLBACK_PATHS:
        candidate = origin + path
        if candidate.rstrip("/") != url.rstrip("/") and candidate not in out:
            out.append(candidate)
    return out[:limit]


def host_of(url):
    """Lowercased host, for per-host rate limiting and block tracking."""
    if not url:
        return ""
    if "://" not in url:
        url = "https://" + url
    return urllib.parse.urlsplit(url).netloc.lower()


# -- rows --------------------------------------------------------------------

#: Written from a probe result into company_ats. Every key must be present on
#: every record: lib.upsert binds them as named parameters, so a missing one
#: fails that record rather than the batch (schema.py:118-120).
COMPANY_ATS_COLUMNS = (
    "employer_name", "careers_url", "ats", "token",
    "workday_site", "workday_dc", "open_jobs_at_validation",
    "first_validated_at", "last_validated_at", "open_jobs_changed_at",
    "status", "validation_note", "discovered_via",
)

#: What makes a row "changed". last_validated_at is deliberately absent -- it
#: moves on every run by definition, and including it would report every
#: monthly re-probe as hundreds of updated rows, burying the handful that
#: actually moved. open_jobs_at_validation IS included, because a token whose
#: count never moves is the stale-feed signal this task is designed against.
HASH_FIELDS_COMPANY_ATS = ("careers_url", "ats", "token", "workday_site",
                           "workday_dc", "open_jobs_at_validation", "status")

#: first_validated_at records when a token was FIRST confirmed and must survive
#: every later write. lib.upsert.TableSpec.sticky replaces the incoming value
#: with the stored one before hashing, which is the only placement that works:
#: merely omitting it from the UPDATE would leave the hash computed from the
#: drifting value and mark every row changed forever. See lib/upsert.py:83-101.
STICKY_COMPANY_ATS = ("first_validated_at",)


def make_row_id(rec):
    """Primary key: sha256("ats:token:workday_site")[:24].

    Employer name is deliberately NOT in the key for a row that has a token.
    The same board reached from two spellings of an employer ("NYU Langone" /
    "NYU Langone Health") is one board and must be one row; the name is data
    on the row, not identity.

    A never_found row has no token, so keying it the same way would hash
    ("", "", "") for every such employer and collapse all of them onto a
    single row -- silently, since upsert would just report them as
    `unchanged`. Those key on the employer name instead.
    """
    from lib import ids
    if not rec.get("token"):
        return ids.make_id("", "", (rec["employer_name"] or "").strip().lower())
    return ids.make_id(rec["ats"], rec["token"], rec.get("workday_site") or "")


def never_found_row(employer_name, careers_url, now, discovered_via="probe"):
    """The row for an employer whose careers page was read and held no ATS.

    This is a positive result and is stored as one. config/companies.json has
    carried a hand-maintained "checked_but_not_found" list for exactly this
    purpose; putting it in the table means the monthly re-probe knows which
    employers it has already ruled out and when, instead of re-deriving it.

    ONLY valid for outcome NOT_FOUND. Calling it after a BLOCKED probe would
    record "this employer has no ATS" on the strength of a 403.
    """
    return {
        "employer_name": employer_name,
        "careers_url": careers_url,
        "ats": "",
        "token": "",
        "workday_site": None,
        "workday_dc": None,
        "open_jobs_at_validation": None,
        "first_validated_at": now,
        "last_validated_at": now,
        "open_jobs_changed_at": None,
        "status": STATUS_NEVER_FOUND,
        # Deliberately worded as a claim about the BYTES, not about the
        # employer. Measured 2026-07-28: of four control employers with a
        # verified live board in config/companies.json (Datadog, MongoDB,
        # Justworks, Ramp), this method found 0 -- their careers pages are
        # client-rendered and the board URL is not in the served HTML at all.
        # `never_found` therefore means "no ATS URL in the HTML we were
        # served", and tasks 17/18/20 must not read it as "no ATS".
        "validation_note": ("no ATS URL in the served HTML -- NOT evidence "
                            "the employer has no ATS; see the false-negative "
                            "rate in docs/ats-token-discovery.md"),
        "discovered_via": discovered_via,
    }
