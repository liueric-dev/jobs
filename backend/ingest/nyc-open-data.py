#!/usr/bin/env python3
"""Ingest external NYC Jobs postings from Socrata dataset kpav-sd4t.

The source is a bounded public open-data feed. It normalizes current external
postings into jobs and uses staleness, not an exact list diff, for closures.
An optional SOCRATA_APP_TOKEN raises the request limit; anonymous access works.
"""

import os
import sys
import json
import time
import urllib.error
from dataclasses import dataclass
from datetime import date, datetime, timezone

# ingest/ and tools/ sit one level below the pipeline modules they import
# (schema, relevance, llm, ...). Python puts THIS file's directory on
# sys.path, not its parent, so the parent is added by hand -- the same
# insert every ingest script opens with (ingest/ats.py:224).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import schema  # noqa: E402  (schema.py)
from lib import dbconn, http, state, text  # noqa: E402
from lib.timeparse import utc_now_str  # noqa: E402
from lib.upsert import UpsertErrorRate, upsert_checked  # noqa: E402

#: The `jobs.platform` value for every row this script writes.
#:
#: This identifier is stored in jobs.platform and used by source reports.
#:
#: `nyc_open_data` rather than `nyc_jobs` or `kpav-sd4t`: underscores to
#: match other sampled sources: the PUBLISHER rather than the
#: dataset id because a dataset id is unreadable in a report, and not
#: `nyc_jobs` because that reads like "jobs in NYC" -- which describes half
#: this table -- rather than "the City's own posting feed". A future NY
#: State mirror (data.ny.gov/resource/vntw-tq6b) is a different publisher
#: and would be a different platform string, not more rows under this one.
PLATFORM = "nyc_open_data"

DATASET_ID = "kpav-sd4t"
SODA_ENDPOINT = f"https://data.cityofnewyork.us/resource/{DATASET_ID}.json"

#: cityjobs.nyc.gov 301-redirects /job/<job_id> to the canonical slug URL
#: (verified 2026-07-28: /job/786162 -> /job/lead-researcher-behavioral-
#: health-in-manhattan-jid-45370). The numeric form is the one that is
#: stable and derivable from the record, so it is what is stored; the slug
#: contains the title and would change when the title is edited.
JOB_URL_BASE = "https://cityjobs.nyc.gov/job/"

#: Kept only to be counted. See the Internal drop in main().
EXTERNAL, INTERNAL = "External", "Internal"

#: SODA's own maximum page size is 50,000; 1,000 is the documented default
#: and keeps a single response near 3-4 MB on this dataset. At 2,376 rows
#: that is three pages a night.
PAGE_SIZE = 1000

#: Hard stop on the pagination loop, so a `$order` that stops being honoured
#: (or an endpoint that ignores `$offset`) costs 25 requests rather than an
#: unbounded crawl. 25 x 1,000 is ten times the dataset's current size;
#: hitting it is reported, not silently accepted -- see FetchResult.
MAX_PAGES = 25

#: Stable pagination key. See "A SHORT PAGE IS NOT THE END OF THE LIST".
PAGE_ORDER = "job_id"

APP_TOKEN = os.environ.get("SOCRATA_APP_TOKEN", "")

#: Anonymous requests share a throttling pool, so they get a full second
#: between pages; a token moves the caller to its own bucket and 0.25s is
#: ample. Three pages either way -- this costs three seconds a night.
DEFAULT_DELAY = 0.25 if APP_TOKEN else 1.0
REQUEST_DELAY_SECONDS = float(
    os.environ.get("NYC_OPEN_DATA_DELAY", str(DEFAULT_DELAY)))

DEBUG_PRINT_KEYS = os.environ.get("DEBUG_PRINT_KEYS", "") == "1"

#: How long a row may be absent from the dataset before it is closed.
#:
#: The disappearance half of the closure story, and deliberately looser than
#: the daily cadence: DCAS republishes in batches (on 2026-07-28 every one
#: of max(process_date), max(posting_updated) and max(posting_date) read
#: 2026-07-20, an eight-day-old snapshot), and a row briefly missing from
#: one batch must not be closed and then reopened. Seven days tolerates that
#: and still closes a genuinely withdrawn posting inside a week. It does not
#: have to be tight, because `post_until` -- the precise signal -- does the
#: work for the 98% of postings that carry one.
STALE_AFTER_DAYS = 7

#: How far the collected row count may fall short of the dataset's own count
#: before the crawl is treated as truncated. Relative, plus an absolute
#: floor for small slices.
#:
#: NOT A MEASUREMENT. The dataset moves between the count query and the last
#: page, so some slack is required or every run would refuse to close
#: anything; 2% of 2,376 is 47 rows, which is far more slack than a batch
#: republish needs and far less than the failure this guards against (the
#: A published account reports 1,960 of 2,000 lost -- a 98%
#: shortfall). Tighten it once there is a distribution of observed
#: run-to-run drift to pick from. Rejected: zero tolerance, which turns a
#: normal one-row edit into a nightly alert and trains everyone to ignore
#: the alert.
RECONCILE_TOLERANCE = 0.02
RECONCILE_FLOOR = 5

#: Volume tripwire. 1,230 External postings on 2026-07-28; the dataset has
#: not been below four figures in any published snapshot. A run that returns
#: fewer than this has not necessarily failed, but nobody should find out
#: about it by noticing the table stopped growing -- "Silence is this
#: system's failure mode", .
MIN_EXTERNAL_ROWS = 400

#: raw_json cap. Same reasoning as the Google sources: keep the envelope,
#: shrink the one field that blows the budget -- see text.bounded_json.
RAW_JSON_LIMIT = 20000

#: Hash fields for this source. NOT one of schema.py's frozen tuples, and it
#: does not need to be: those are frozen because they are stored digests
#: over existing rows, and this platform has none yet.
#:
#: It is HASH_FIELDS_ATS plus `salary_text`. Salary here is STATED by the
#: employer rather than parsed out of prose, so a change to it is a real
#: upstream edit worth recording; without it in the hash, a posting whose
#: salary band was corrected and whose description was not would be counted
#: `unchanged`, the UPDATE would be skipped, and the stored band would stay
#: wrong forever. `department` is in the tuple because this source fills it
#: (from `job_category`), which is the same reason ats and wwr hash it.
HASH_FIELDS = ("title", "location_raw", "department", "job_url",
               "posted_at", "description_text", "salary_text")

#: Which SODA fields become `description_text`, IN THIS ORDER, and the
#: heading each is written under.
#:
#: Put the short, useful skills and qualifications before the long narrative
#: so they survive the storage cap. The complete source row remains in raw_json.
DESCRIPTION_PARTS = (
    ("PREFERRED SKILLS", "preferred_skills"),
    ("MINIMUM QUALIFICATION REQUIREMENTS", "minimum_qual_requirements"),
    ("JOB DESCRIPTION", "job_description"),
)

#: `residency_requirement` is deliberately NOT concatenated. It is the same
#: two paragraphs of civil-service boilerplate on essentially every row
#: ("New York City residency is generally required within 90 days of
#: appointment..."), it says nothing about the job, and at ~500 chars it
#: would take a sixth of the prompt budget on every posting. It stays
#: available in raw_json.

#: `post_until` arrives as `12-SEP-2026` -- a text field, not one of the
#: floating timestamps the rest of the record uses (`posting_date`,
#: `posting_updated` and `process_date` are all ISO). 1,206 of 1,206
#: non-null External values matched this one shape on 2026-07-28. Anything
#: else parses to None and falls through to disappearance-based closure,
#: which is the safe direction: a deadline we cannot read must never close a
#: posting early.
_MONTHS = {m: i for i, m in enumerate(
    ("JAN", "FEB", "MAR", "APR", "MAY", "JUN",
     "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"), start=1)}


# ---------------------------------------------------------------------------
# fetching
# ---------------------------------------------------------------------------

def _headers():
    """Request headers. The app token, if there is one, and nothing else."""
    if APP_TOKEN:
        return {"X-APP-TOKEN": APP_TOKEN}
    return None


def soda_url(params):
    """`params` (an ordered list of pairs) appended to the dataset endpoint.

    Order is fixed by the caller and never sorted, because the URL is the
    cassette lookup key (testsupport/cassettes.py:222) and two spellings of the
    same request would not match each other.
    """
    return f"{SODA_ENDPOINT}?{http.urlencode(params)}"


def fetch_count(where=None):
    """How many rows the dataset says it has. The reconciliation anchor.

    Returns an int, or raises -- a count that cannot be fetched is not
    reported as zero, because zero is a number this script would act on.
    """
    params = [("$select", "count(*) AS n")]
    if where:
        params.append(("$where", where))
    rows = http.get_json(soda_url(params), headers=_headers(),
                         label=f"{DATASET_ID} count")
    if not rows:
        raise ValueError(f"{DATASET_ID}: count query returned no rows")
    row = rows[0]
    raw = row.get("n", next(iter(row.values()), None))
    return int(raw)


def fetch_page(offset, limit=PAGE_SIZE, where=None, order=PAGE_ORDER):
    """One page of the dataset."""
    params = [("$limit", limit), ("$offset", offset), ("$order", order)]
    if where:
        params.append(("$where", where))
    rows = http.get_json(soda_url(params), headers=_headers(),
                         label=f"{DATASET_ID} offset={offset}")
    return rows if isinstance(rows, list) else []


@dataclass(frozen=True)
class FetchResult:
    rows: tuple
    pages: int
    #: True when the loop stopped because it ran out of allowed pages rather
    #: than because a page came back short. Never treated as a complete
    #: crawl -- reconcile() will see the shortfall, but this says WHY.
    hit_page_cap: bool


def fetch_all(where=None, page_size=PAGE_SIZE, max_pages=MAX_PAGES,
              order=PAGE_ORDER, delay=REQUEST_DELAY_SECONDS):
    """Every row, by `$limit`/`$offset`, in a stable `$order`.

    Stops on a short page, which is the ordinary end-of-list signal AND the
    shape a throttled response takes. That ambiguity is not resolved here on
    purpose: this function reports what it collected and reconcile() decides
    whether to believe it.
    """
    rows = []
    pages = 0
    hit_cap = True
    for page in range(max_pages):
        batch = fetch_page(page * page_size, limit=page_size, where=where,
                           order=order)
        pages += 1
        rows.extend(batch)
        if DEBUG_PRINT_KEYS:
            print(f"[debug] page {page} (offset {page * page_size}): "
                  f"{len(batch)} rows, {len(rows)} so far", file=sys.stderr)
        if len(batch) < page_size:
            hit_cap = False
            break
        if delay:
            time.sleep(delay)
    return FetchResult(rows=tuple(rows), pages=pages, hit_page_cap=hit_cap)


@dataclass(frozen=True)
class Reconciliation:
    """Did the crawl collect what the dataset says exists?"""
    collected: int
    count_before: int
    count_after: int
    allowance: int
    ok: bool
    note: str

    @property
    def shortfall(self):
        return max(0, min(self.count_before, self.count_after) - self.collected)


def reconcile(collected, count_before, count_after,
              tolerance=RECONCILE_TOLERANCE, floor=RECONCILE_FLOOR):
    """Compare a crawl against the dataset's own count. Pure -- no I/O.

    Pure so it is unit-testable and so the rule can be exercised against the
    shapes that matter (a throttled first page, a dataset that grew mid-
    crawl, a count of zero) without a network or a database.

    The two counts bracket the crawl: `low` is the smallest number of rows
    the dataset claimed at any point, and falling short of THAT by more than
    the allowance is a truncation. Collecting more than `high` is not an
    error -- the dataset grew while we were reading it.
    """
    low, high = min(count_before, count_after), max(count_before, count_after)
    allowance = max(floor, int(high * tolerance))

    if high == 0:
        ok = collected == 0
        note = ("dataset reports zero rows" if ok else
                f"count says 0 but {collected} rows were collected")
    elif collected >= low - allowance:
        ok = True
        note = "reconciled"
        if count_before != count_after:
            note += (f" (dataset moved during the crawl: "
                     f"{count_before} -> {count_after})")
        if collected > high:
            note += f" ({collected - high} rows over the higher count)"
    else:
        ok = False
        note = (f"TRUNCATED: collected {collected} of {low} rows "
                f"({low - collected} missing, allowance {allowance}). A short "
                f"page is not the end of a list -- refusing to close anything "
                f"on this run.")
    return Reconciliation(collected=collected, count_before=count_before,
                          count_after=count_after, allowance=allowance,
                          ok=ok, note=note)


# ---------------------------------------------------------------------------
# normalizing
# ---------------------------------------------------------------------------

def parse_post_until(value):
    """`12-SEP-2026` -> `2026-09-12`. None for anything unreadable.

    Returns a DATE string, not a timestamp: the City publishes a day, and
    inventing an hour would be inventing precision. close_expired() appends
    the midnight suffix the `jobs` table's TEXT timestamps use.
    """
    parts = (value or "").strip().upper().split("-")
    if len(parts) != 3:
        return None
    day, month, year = parts
    if month not in _MONTHS or not day.isdigit() or not year.isdigit():
        return None
    try:
        return date(int(year), _MONTHS[month], int(day)).isoformat()
    except ValueError:
        return None


def _money(value):
    """`60000` -> `$60,000`; `16.5` -> `$16.50`. None for anything else."""
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return None
    if amount == int(amount):
        return f"${int(amount):,}"
    return f"${amount:,.2f}"


def salary_text(row):
    """The band as the City states it. Stated, never predicted.

    Kept as the source's stated text; no compensation inference is performed.
    """
    low = _money(row.get("salary_range_from"))
    high = _money(row.get("salary_range_to"))
    frequency = (row.get("salary_frequency") or "").strip()
    if not low and not high:
        return None
    band = f"{low}-{high}" if low and high and low != high else (low or high)
    return f"{band} {frequency}".strip()


def description_of(row):
    """The three description fields, concatenated. See DESCRIPTION_PARTS."""
    chunks = []
    for heading, field in DESCRIPTION_PARTS:
        body = (row.get(field) or "").strip()
        if body:
            chunks.append(f"{heading}\n{body}")
    joined = "\n\n".join(chunks)
    return joined[:text.MAX_DESCRIPTION_CHARS] or None


def normalize(row):
    """One SODA record -> one `jobs` row.

    LOCATION IS TRUE BY SOURCE, NOT BY REGEX. `work_location` is a bare
    street address on most rows -- "100 Gold Street", "City Hall", "Rikers
    Island" -- and text.NYC_PATTERN matched only 340 of 1,230 External rows
    (27.6%, measured 2026-07-28). Deriving `location_is_nyc` from it would
    file 72% of the City of New York's own job postings as not-in-New-York,
    and config/relevance.json's `location_columns` is exactly
    ["location_is_nyc", "location_is_remote"], so those rows would drop from
    tier 1 to tier 2 for no reason but a regex missing a street address.
    Every posting in this dataset is a City agency requisition, so this is
    one of the few places where the honest value is a constant. The handful
    of City facilities just outside the line (Valhalla, Hawthorne) are
    accepted as NYC employers rather than special-cased.
    """
    job_id = str(row.get("job_id") or "").strip()
    agency = (row.get("agency") or "").strip()
    title = (row.get("business_title")
             or row.get("civil_service_title") or "").strip()
    location = ((row.get("work_location") or row.get("work_location_1") or "")
                .strip() or None)
    posted_at = (row.get("posting_date") or "").strip() or None
    _, is_remote = text.classify_location(location or "")

    return {
        "platform": PLATFORM,
        "company_token": text.slugify(agency),
        # The agency string as published, upper case and all. Title-casing
        # it would read better and would also turn NYPD into Nypd and DOHMH
        # into Dohmh; the source's own spelling is the one that can be
        # checked against the source.
        "company_name": agency or None,
        "source_id": job_id,
        # business_title over civil_service_title, per the task file:
        # "Lead Researcher, Behavioral Health" vs "RESEARCH PROJECTS
        # COOR(MA)-MGR". The civil service title survives in raw_json.
        "title": title or None,
        "location_raw": location,
        "department": (row.get("job_category") or "").strip() or None,
        "job_url": f"{JOB_URL_BASE}{job_id}" if job_id else None,
        "posted_at": posted_at,
        "posted_at_ts": text.posted_at_timestamp(posted_at),
        "salary_text": salary_text(row),
        "seniority_guess": text.guess_seniority(title),
        "location_is_nyc": True,
        "location_is_remote": is_remote,
        # A City agency is headquartered in New York by definition, and is
        # not an AI company. Both are known here, so both are booleans
        # rather than the None the sources that cannot tell use.
        "company_is_nyc_hq": True,
        "company_is_ai_focused": False,
        "description_text": description_of(row),
        "raw_json": text.bounded_json(row, RAW_JSON_LIMIT,
                                      long_field="job_description"),
        # NOT a `jobs` column -- carried on the record for close_expired(),
        # the same way hn-hiring.py:326 carries thread_id. upsert() binds
        # columns by name, so an extra key is ignored by the write.
        "post_until": parse_post_until(row.get("post_until")),
        # Also not a jobs column. Preserve the source's career-level label
        # without treating it as an inferred seniority value.
        "career_level": (row.get("career_level") or "").strip() or None,
    }


def dedupe(records):
    """One record per primary key, keeping the latest deadline.

    `job_id` IS NOT UNIQUE IN THIS DATASET. Measured 2026-07-28: 1,230
    External rows carry 1,219 distinct `job_id` values -- ten ids appear
    twice and one three times. The twins are the same requisition published
    at more than one `level`, and they DO NOT always agree:

        job_id 781780  Scientist (Water Ecology), I  post_until 25-JUL-2026
        job_id 781780  Scientist (Water Ecology), I  post_until 13-SEP-2026

    schema.make_job_id() is sha256("platform:token:source_id"), so both land
    on one primary key and upsert() writes whichever comes last -- the
    "two records share a primary key, so one silently overwrites the other"
    failure that tests/test_ingest_cassettes.py:84-88 exists to catch. Worse
    than the overwrite: on 2026-07-28 the first run of this script wrote the
    live twin of two such pairs and then CLOSED it, from the expired twin's
    deadline. A posting open until September, closed in July, with nothing
    in the output saying so.

    The most permissive deadline wins: a row with no `post_until` beats one
    with a date (no deadline is later than every date), and among dates the
    latest wins. That is the safe direction -- a stale duplicate must never
    be what closes a live posting.
    """
    best = {}
    for record in records:
        key = schema.make_job_id(record)
        current = best.get(key)
        if current is None or _deadline_rank(record) > _deadline_rank(current):
            best[key] = record
    return list(best.values())


def _deadline_rank(record):
    """Sort key for dedupe(): a missing deadline outranks every date."""
    deadline = record.get("post_until")
    return (deadline is None, deadline or "")


def is_expired(record, today=None):
    """Has this posting's published deadline passed?

    `post_until` is inclusive -- "post until 12-SEP" means applications are
    accepted through the twelfth -- so the comparison is strictly less-than.
    A record with no readable deadline is never expired by this rule; it is
    closed by disappearance like every other source's rows.
    """
    deadline = record.get("post_until")
    if not deadline:
        return False
    return deadline < (today or datetime.now(timezone.utc).date().isoformat())


# ---------------------------------------------------------------------------
# closing
# ---------------------------------------------------------------------------

def close_expired(conn, expired, now=None):
    """Close rows whose published deadline has passed, dated FROM it.

    `closed_at` is the deadline, not the clock. The City said when this
    posting stopped accepting applications; recording the night we noticed
    would throw that away and would make two rows that closed on the same
    day look like they closed on different ones.

    Grouped by deadline so this is one statement per distinct date (a
    handful) rather than one per row.
    """
    now = now or utc_now_str()
    by_deadline = {}
    for record in expired:
        by_deadline.setdefault(record["post_until"], []).append(
            record["source_id"])

    closed = 0
    for deadline, source_ids in sorted(by_deadline.items()):
        cur = conn.execute(
            """
            UPDATE jobs SET status = %s, closed_at = %s, last_seen = %s
            WHERE platform = %s AND status = %s AND source_id = ANY(%s)
            """,
            (schema.STATUS_CLOSED, f"{deadline}T00:00:00", now,
             PLATFORM, schema.STATUS_OPEN, source_ids),
        )
        closed += cur.rowcount
    conn.commit()
    return closed


# ---------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------

def main():
    conn = dbconn.connect_or_exit("nyc-open-data ingest", schema=schema.SCHEMA)
    schema.ensure_schema(conn)

    job_spec = schema.spec(HASH_FIELDS,
                           blank_if_falsy=("description_text", "salary_text"))
    run_started_at = utc_now_str()
    today = datetime.now(timezone.utc).date().isoformat()

    # The count BEFORE and the count AFTER bracket the crawl. Both are
    # inside the same try: a run that cannot ask how big the dataset is
    # cannot decide whether it read all of it, and must not guess.
    try:
        count_before = fetch_count()
        fetched = fetch_all()
        count_after = fetch_count()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
            json.JSONDecodeError, ValueError, OSError) as e:
        print(f"nyc-open-data ingest FAILED: {DATASET_ID} fetch: {e}")
        conn.close()
        sys.exit(1)

    checked = reconcile(len(fetched.rows), count_before, count_after)

    external = [r for r in fetched.rows
                if (r.get("posting_type") or "").strip() == EXTERNAL]
    internal_dropped = len(fetched.rows) - len(external)

    # Deduplicate BEFORE splitting live from expired: the two halves are
    # keyed on the same primary key, and a duplicate that lands on both
    # sides means the run writes a posting and then closes it. See dedupe().
    records = dedupe([normalize(r) for r in external])
    duplicates_collapsed = len(external) - len(records)
    live = [r for r in records if not is_expired(r, today)]
    expired = [r for r in records if is_expired(r, today)]

    # Expired postings are NOT written. A deadline that has already passed
    # is not a job a Builder can apply to, and inserting one would create a
    # row no consumer can see (schema.py's jobs_app view is scoped to
    # status='open') purely so prune_old_closed could delete it later. The
    # ones that were ingested while live are closed below, from their
    # deadline. Writing them and then closing them in the same run would
    # additionally report every expired posting as `updated` every night
    # forever, because schema.spec() recomputes status='open' on every
    # INSERT and UPDATE.
    result = None
    try:
        result = upsert_checked(conn, job_spec, live, schema.make_job_id,
                                debug=DEBUG_PRINT_KEYS)
        upsert_failed = False
    except UpsertErrorRate as e:
        result, upsert_failed = e.result, True
        print(f"nyc-open-data ingest: upsert error rate exceeded: {e}")

    if expired and DEBUG_PRINT_KEYS:
        print(f"[debug] {len(expired)} postings past their post_until, "
              f"not written", file=sys.stderr)

    # -- closure, gated ------------------------------------------------------
    #
    # Both closers are skipped whenever the crawl did not reconcile or the
    # External filter matched nothing. close_stale() in particular closes
    # every row of this platform not seen for a week, so running it after a
    # truncated fetch is how a throttled night becomes a mass closure. The
    # SAFETY VALVE in ingest/ats.py's docstring is the same idea with a
    # per-company scope; this one has a count to check against, which is
    # better.
    closed_expired = closed_stale = 0
    blocked = None
    if not checked.ok:
        blocked = checked.note
    elif not external:
        blocked = (f"posting_type={EXTERNAL!r} matched 0 of "
                   f"{len(fetched.rows)} rows -- the filter or the column "
                   f"has changed shape")
    if blocked is None:
        closed_expired = close_expired(conn, expired, run_started_at)
        closed_stale = schema.close_stale(conn, PLATFORM, STALE_AFTER_DAYS)
        # Only on a complete fetch. state.set_watermark's own docstring
        # (lib/state.py:71-76) is about exactly this: nyc-events-ingest
        # advanced its watermark past a safety cap and never asked for the
        # skipped rows again.
        state.set_watermark(conn, PLATFORM, run_started_at,
                            table=schema.WATERMARK_TABLE)

    conn.close()

    # -- report --------------------------------------------------------------
    #
    # ALWAYS, unlike the ATS script's quiet-day rule. This source writes
    # every row it has every night, so "wrote nothing" is never normal here
    # and the counts are the only way to see a filter that stopped matching.
    print(f"nyc-open-data: {result.new} new, {result.updated} updated, "
          f"{result.unchanged} unchanged, {len(result.errors)} record(s) "
          f"dropped; {len(external)} External of {len(fetched.rows)} fetched "
          f"({internal_dropped} Internal dropped, {duplicates_collapsed} "
          f"duplicate job_id collapsed), {len(expired)} past "
          f"post_until; {closed_expired} closed by deadline, "
          f"{closed_stale} closed as stale; {fetched.pages} page(s), "
          f"{checked.note}")

    if blocked:
        print(f"nyc-open-data ALERT: closure skipped -- {blocked}")
    if fetched.hit_page_cap:
        print(f"nyc-open-data ALERT: pagination stopped at the {MAX_PAGES}-page "
              f"cap rather than at a short page; the crawl is incomplete")
    if len(external) < MIN_EXTERNAL_ROWS:
        print(f"nyc-open-data ALERT: only {len(external)} External postings "
              f"(expected >= {MIN_EXTERNAL_ROWS}; 1,230 on 2026-07-28)")

    # Non-zero for the two conditions that mean the table is now wrong or
    # incomplete, so jobs-failure@.service says so. A quiet night is not one
    # of them; a truncated crawl is.
    if upsert_failed or not checked.ok or not external:
        sys.exit(1)


if __name__ == "__main__":
    main()
