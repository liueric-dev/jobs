#!/usr/bin/env python3
"""
Find which NYC employers run which ATS, and confirm every token against the
live feed before believing it.

Task 16. Blocks 17 (retargeted ats.py), 18 (Workday CXS) and 20 (iCIMS).

WHAT IT DOES
    1. Reads employers from `ats_seed` (created and populated by
       migrations/migrate_company_ats.py).
    2. Fetches each careers page and regexes it for the ATS URL signatures in
       ats_discovery.SIGNATURES.
    3. VALIDATES every signature by calling the ATS's own endpoint and
       checking for a 200 with a non-empty job list. A signature found in a
       stale footer link is common, and an unvalidated token contributes zero
       rows forever -- which looks exactly like a quiet employer.
    4. Upserts the results into `company_ats` through upsert_checked.

THE FAILURE MODE THIS IS BUILT AGAINST
    Not "the probe crashes". A probe that is blocked at the front door by
    every host finds zero tokens, exits 0, and writes an empty table that the
    next run reads as settled fact. CLAUDE.md: "Silence is this system's
    failure mode ... Alert on volume, not errors."

    Three mechanisms, in increasing order of how loud they are:

      * Every employer carries an OUTCOME, not a boolean. `not_found` (page
        read, no ATS) and `blocked` (403/429/WAF) are different rows in
        ats_seed.last_probe_outcome and different lines in the summary. Only
        `not_found` may write status='never_found'.

      * A token that was found but could not be checked is
        status='unvalidated', never 'valid' and never 'dead'. Task 16's
        three-value status enum has no such value; see ats_discovery.py.

      * A CIRCUIT BREAKER. If the blocked fraction of the probes attempted so
        far exceeds --max-blocked-frac once at least --breaker-after probes
        have run, the run aborts with a non-zero exit rather than finishing
        and reporting a clean, empty result.

POLITENESS
    This is outward-facing traffic against several hundred hosts that never
    asked for it, so:
      * one global request every --delay seconds (default 1.5) AND at most
        one request per host every --host-delay seconds (default 5),
      * an honest User-Agent that names the project, not a browser string,
      * NO retries, ever. lib/http.py retries 429 with backoff, which is
        right for a known API and wrong here -- retrying into a rate limit is
        how a probe turns into an incident. It is deliberately not used.
      * a host that answers 403 or 429 is added to a blocklist and receives
        no further request this run, including the validation request,
      * at most --max-url-candidates URLs per employer (default 3),
      * --max-requests as a hard ceiling on the whole run.

WHAT IS NOT WIRED UP
    Adzuna `top_companies` (16-ats-token-discovery.md:32) is a named discovery
    source and is STUBBED -- see adzuna_top_companies() below. Task 15 is
    blocked on an Adzuna app_id/app_key that requires registering an account.
    The function is the seam: fill it in, and its employers flow into ats_seed
    with no other change.

USAGE
    python3 tools/ats-discover.py                        # dry run, 20 employers
    python3 tools/ats-discover.py --apply --limit 50
    python3 tools/ats-discover.py --apply --all
    python3 tools/ats-discover.py --apply --due-only     # monthly re-probe
    python3 tools/ats-discover.py --apply --all --revalidate   # tokens only
    python3 tools/ats-discover.py --report               # no network at all
    python3 tools/ats-discover.py --add-employer "Foo Inc" \\
        --careers-url https://foo.com/careers --sector health

SCHEDULE
    run-daily.py runs `--apply --due-only`, which exits immediately on 29 days
    out of 30. See the ats-discovery watermark in job_ingest_state.
"""

import argparse
import datetime
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request

# tools/ sits one level below the pipeline modules it imports (schema,
# ats_discovery, ...). Python puts THIS file's directory on sys.path, not its
# parent, so the parent is added by hand. That same insert is what reaches
# lib/ -- there is nothing to install.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ats_discovery as ad  # noqa: E402
import schema  # noqa: E402
from lib import dbconn, envfile, state  # noqa: E402
from lib.timeparse import utc_now, utc_now_str  # noqa: E402
from lib.upsert import (TableSpec, UpsertErrorRate,  # noqa: E402
                        UpsertResult, upsert_checked)

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "migrations"))
from migrate_company_ats import (ATS_TABLE, SEED_TABLE,  # noqa: E402
                                 ensure_ats_schema)

#: Named honestly. A browser User-Agent would get past more WAFs, and that is
#: exactly the reason not to use one: a host that does not want automated
#: traffic is entitled to recognise this as automated traffic and say no. A
#: 403 here is a datum (outcome=blocked), not an obstacle to route around.
USER_AGENT = ("jobs-pipeline-ats-discovery/1.0 "
              "(+https://github.com/hermes/jobs; NYC employer ATS discovery; "
              "one request per host per run)")

#: Per-request timeout. 10s, not 20: a careers page that has not answered in
#: ten seconds is not going to, and the cost is paid three times per employer
#: on a dead host. Measured on the first full pass -- freshdirect.com and
#: globalindemnity.com each burned 60 seconds of a 40-minute budget returning
#: nothing. Overridable with --timeout.
TIMEOUT = 10

#: Read cap for a CAREERS PAGE. It is only ever regexed, so a truncated one
#: costs at most a missed signature on a pathologically large page.
MAX_BYTES = 2_000_000

#: Read cap for a VALIDATION response, which must parse as complete JSON.
#:
#: WHY IT IS NOT THE SAME NUMBER. These feeds carry every posting's full
#: description: api.lever.co/v0/postings/leverdemo is 2.43 MB for 388 jobs,
#: and a large hospital system's board is larger. At the 2 MB page cap that
#: body arrives truncated, json.loads fails, and classify_validation reports
#: "200 but the response was not a recognisable job feed" -- so the BIGGEST
#: and healthiest boards, the ones most worth ingesting, are exactly the ones
#: that read as unverifiable. Measured, not hypothesised; see the note in
#: docs/ats-token-discovery.md.
VALIDATION_MAX_BYTES = 40_000_000

#: Bodies that mean "refused" behind a 200. lib/http.py documents the same
#: class of response (queenslibrary.org's WAF answers 200 with "Request
#: Rejected"); a probe that counted those as "page read, no ATS found" would
#: write never_found rows on the strength of a block.
_WAF_BODY = re.compile(
    r"request rejected|access denied|attention required!\s*\|\s*cloudflare"
    r"|are you a robot|captcha-delivery|please enable (?:js|javascript) and "
    r"cookies|akamai reference (?:number|error)|incapsula incident",
    re.I)

#: Re-probe cadence. Companies migrate ATS constantly AND the old feed keeps
#: serving stale jobs after they do, so this is not optional maintenance.
DEFAULT_INTERVAL_DAYS = 30
#: A token whose open_jobs_at_validation has not moved in this long is flagged
#: for manual review -- the stale-feed signature.
STALE_COUNT_DAYS = 60

WATERMARK = "ats-discovery"


# -- rate-limited, non-retrying fetch ----------------------------------------

class Fetcher:
    """One global pace, one per-host pace, and a hard blocklist.

    Deliberately not lib/http.py: that module retries 429 with exponential
    backoff, which is correct against an API you own a key for and is the
    wrong instinct entirely when probing several hundred strangers. lib/ is
    also vendored byte-identical to another repo (CLAUDE.md), so changing its
    retry policy to suit this caller is not an option and should not be.
    """

    def __init__(self, delay=1.5, host_delay=5.0, max_requests=2000,
                 dry_run=False, verbose=False, timeout=TIMEOUT):
        self.timeout = timeout
        self.delay = delay
        self.host_delay = host_delay
        self.max_requests = max_requests
        self.dry_run = dry_run
        self.verbose = verbose
        self.requests = 0
        self.blocked_hosts = set()
        self._last_global = 0.0
        self._last_host = {}

    def budget_left(self):
        return self.max_requests - self.requests

    def _wait(self, host):
        now = time.monotonic()
        due = max(self._last_global + self.delay,
                  self._last_host.get(host, 0.0) + self.host_delay)
        if due > now:
            time.sleep(due - now)
        # A little jitter so a run never looks like a metronome to a WAF.
        self._last_global = time.monotonic() + random.uniform(0, 0.2)
        self._last_host[host] = self._last_global

    def get(self, url, method="GET", body=None, max_bytes=MAX_BYTES):
        """(outcome, http_status, text, truncated). Never raises, never retries.

        outcome is one of ats_discovery's constants; FOUND is not used here
        (that is the caller's judgement about the body) -- a successful fetch
        comes back as NOT_FOUND, meaning "read it, now go look".

        `truncated` is returned rather than inferred because a body cut off at
        the cap is not merely incomplete, it is INDISTINGUISHABLE from a
        malformed one: both fail json.loads, and the caller would report a
        healthy feed as unparseable. Whoever raises a cap must not have to
        also remember that.
        """
        host = ad.host_of(url)
        if host in self.blocked_hosts:
            return (ad.SKIPPED, None, "", False)
        if self.requests >= self.max_requests:
            return (ad.SKIPPED, None, "", False)

        self._wait(host)
        self.requests += 1

        headers = {"User-Agent": USER_AGENT,
                   "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
                   "Accept-Language": "en-US,en;q=0.9"}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data, headers=headers,
                                     method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                # One byte past the cap, so "exactly at the cap" and "cut
                # off" are distinguishable instead of both looking complete.
                raw = resp.read(max_bytes + 1)
                truncated = len(raw) > max_bytes
                text = raw[:max_bytes].decode("utf-8", errors="replace")
                status = resp.status
        except urllib.error.HTTPError as e:
            try:
                text = e.read(MAX_BYTES).decode("utf-8", errors="replace")
            except Exception:
                text = ""
            # 401/406/451 join the obvious 403/429 as refusals. 406 in
            # particular is what several enterprise WAFs return to a
            # non-browser Accept header, and it is ambiguous -- it could also
            # be genuine content negotiation. Ambiguity resolves toward
            # BLOCKED on purpose: BLOCKED is inconclusive and can never write
            # a never_found row, so guessing wrong here costs one re-probe
            # next month rather than a false "this employer has no ATS".
            if e.code in (401, 403, 406, 429, 451):
                self.blocked_hosts.add(host)
                return (ad.BLOCKED, e.code, text, False)
            if e.code in (404, 410):
                return (ad.MISSING_PAGE, e.code, text, False)
            return (ad.UNREACHABLE, e.code, text, False)
        except Exception as e:  # URLError, ssl, timeout, ConnectionReset, ...
            if self.verbose:
                print(f"[debug] {url}: {type(e).__name__}: {e}",
                      file=sys.stderr)
            return (ad.UNREACHABLE, None, "", False)

        if _WAF_BODY.search(text[:20000]):
            # A 200 that means no. Same host treatment as a 403.
            self.blocked_hosts.add(host)
            return (ad.BLOCKED, status, text, False)
        return (ad.NOT_FOUND, status, text, truncated)


# -- discovery sources -------------------------------------------------------

def adzuna_top_companies(query="artificial intelligence", where="new york",
                         app_id=None, app_key=None):
    """STUB -- Adzuna `top_companies`, task 15's discovery source.

    16-ats-token-discovery.md:32 lists this as a seed source. It is not wired
    up because task 15 is BLOCKED: the endpoint

        GET https://api.adzuna.com/v1/api/jobs/us/top_companies
            ?app_id=...&app_key=...&what=...&where=...

    needs an app_id/app_key pair that requires registering an Adzuna account,
    and nobody has. That is a credentials problem, not a design one, so this
    stays a seam rather than a hole: it returns the same shape
    `insert_discovered_employers()` takes from any other source, so switching
    it on is filling in this function and adding the two keys to .env --
    nothing else in this file changes.

    Returns [] and says so on stderr, rather than raising. A discovery source
    being unavailable must not take the other 376 employers down with it.
    """
    app_id = app_id or os.environ.get("ADZUNA_APP_ID")
    app_key = app_key or os.environ.get("ADZUNA_APP_KEY")
    if not (app_id and app_key):
        print("ats-discover: adzuna top_companies skipped -- ADZUNA_APP_ID/"
              "ADZUNA_APP_KEY not set (task 15 is blocked on registering an "
              "account). Seed list is the hand-assembled roster only.",
              file=sys.stderr)
        return []
    raise NotImplementedError(
        "Adzuna credentials are present but the client is not written -- "
        "finish task 15 and call insert_discovered_employers() with the "
        "`display_name` values from the top_companies response.")


def insert_discovered_employers(conn, employers, source, now=None):
    """Add employers found by any discovery source to ats_seed.

    `employers` is an iterable of dicts with at least employer_name;
    careers_url, sector and is_non_tech are optional. The insertion point for
    adzuna_top_companies(), for the Apify bootstrap actors the task mentions,
    and for --add-employer.
    """
    now = now or utc_now_str()
    added = 0
    for e in employers:
        cur = conn.execute(
            f"""
            INSERT INTO {SEED_TABLE}
                (employer_name, careers_url, sector, is_non_tech,
                 seed_source, added_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (employer_name) DO NOTHING
            """,  # noqa: S608 -- splices SEED_TABLE, a module-level constant
            (e["employer_name"], e.get("careers_url"), e.get("sector"),
             bool(e.get("is_non_tech", True)), source, now))
        added += cur.rowcount
    conn.commit()
    return added


# -- probing -----------------------------------------------------------------

def probe_employer(fetcher, employer, max_candidates=ad.MAX_URL_CANDIDATES):
    """(outcome, careers_url_used, detail, [(platform, fields), ...]).

    Tries the seeded careers URL, then same-origin fallbacks, stopping at the
    first page that comes back. The outcome reported is the BEST one seen --
    a 404 on /careers followed by a 200 on /jobs is a success, and a block on
    any candidate is a block, since it means the host refused us.
    """
    candidates = ad.careers_url_candidates(employer["careers_url"],
                                           limit=max_candidates)
    if not candidates:
        return (ad.NO_URL, None, "no careers_url on the seed row", [])

    fallback = None
    for url in candidates:
        outcome, status, text, _ = fetcher.get(url)
        if outcome == ad.BLOCKED:
            return (ad.BLOCKED, url, f"HTTP {status} or WAF body", [])
        if outcome in (ad.UNREACHABLE, ad.SKIPPED) and status is None:
            # HOST-level failure -- DNS miss, timeout, connection reset. The
            # fallback candidates are same-origin by construction, so trying
            # them asks the identical dead host the identical question two
            # more times and pays the timeout again for each. Only a 404 says
            # anything about the PATH; this says something about the host.
            # (Measured: three 20s timeouts per dead host was the single
            # largest line item in the first full pass.)
            return (outcome, url, f"host unreachable ({outcome})", [])
        if outcome in (ad.MISSING_PAGE, ad.UNREACHABLE, ad.SKIPPED):
            detail = f"HTTP {status}" if status else outcome
            fallback = fallback or (outcome, url, detail, [])
            continue
        hits = ad.find_signatures(text)
        if hits:
            return (ad.FOUND, url, f"{len(hits)} signature(s)", hits)
        # Page read cleanly and holds no ATS URL. That IS the answer, and the
        # probe stops here rather than also asking /careers and /jobs.
        #
        # It used to keep going. Two reasons it no longer does, and the second
        # is the real one:
        #   * cost -- `not_found` is the majority outcome, so two extra
        #     same-origin requests per employer (each waiting out the per-host
        #     delay) was roughly half the wall clock of a full pass and ~40%
        #     of its total request volume.
        #   * politeness -- those extra requests were being spent on the
        #     employers who had already given a complete answer. Guessing two
        #     more URLs at a host that just served us a real page is the least
        #     defensible traffic this tool sends.
        # The fallbacks remain for the case they were written for: a seeded
        # URL that 404s, where the path is wrong and the host is fine.
        return (ad.NOT_FOUND, url, "page fetched; no ATS signature", [])
    return fallback or (ad.UNREACHABLE, candidates[0],
                        "no candidate answered", [])


def validate(fetcher, platform, fields):
    """(status, open_jobs, note) for one discovered token."""
    req = ad.validation_request(platform, fields["token"],
                                workday_site=fields.get("workday_site"),
                                workday_dc=fields.get("workday_dc"))
    if req is None:
        return ad.classify_validation(platform, None, None)
    method, url, body = req
    outcome, status, text, truncated = fetcher.get(
        url, method=method, body=body, max_bytes=VALIDATION_MAX_BYTES)
    if outcome in (ad.BLOCKED, ad.UNREACHABLE, ad.SKIPPED) and status is None:
        return (ad.STATUS_UNVALIDATED, None,
                f"validation request did not complete ({outcome})")
    if truncated:
        # Never fall through to classify_validation with a half-read body: it
        # would fail json.loads and report "not a recognisable job feed",
        # which is a claim about the employer rather than about our own cap.
        return (ad.STATUS_UNVALIDATED, None,
                f"response exceeded the {VALIDATION_MAX_BYTES}-byte read cap; "
                f"not parsed")
    return ad.classify_validation(platform, status, text)


# -- persistence -------------------------------------------------------------

def company_ats_spec():
    return TableSpec(
        table=ATS_TABLE,
        columns=ad.COMPANY_ATS_COLUMNS,
        hash_fields=ad.HASH_FIELDS_COMPANY_ATS,
        sticky=ad.STICKY_COMPANY_ATS,
    )


def existing_counts(conn, ids):
    """id -> (open_jobs_at_validation, open_jobs_changed_at) for rows we are
    about to write.

    Read BEFORE the upsert, because after it the previous count is gone. This
    is what lets open_jobs_changed_at move only when the number actually
    moves, which is the only way "unchanged for 60 days" is answerable.
    """
    if not ids:
        return {}
    rows = conn.execute(
        f"SELECT id, open_jobs_at_validation, open_jobs_changed_at "  # noqa: S608 -- splices ATS_TABLE, a module-level constant
        f"FROM {ATS_TABLE} WHERE id = ANY(%s)", (list(ids),)).fetchall()
    return {r[0]: (r[1], r[2]) for r in rows}


def dedupe_by_id(records):
    """One record per primary key, first occurrence wins.

    Two seeded employers routinely resolve to ONE board -- Staten Island
    University Hospital and Northwell Health share a careers host, and a
    hospital system's subsidiaries share its Workday tenant. Left in, the
    duplicates are written twice in a single batch, and the second write is
    the one that lands. That is not merely wasteful: apply_change_tracking()
    keys on the row id, so only one of the pair gets open_jobs_changed_at
    filled and the other would overwrite it with NULL -- silently disarming
    the 60-day stale-feed check for exactly the largest employers, which are
    the ones most likely to have subsidiaries in the first place.
    """
    seen, out = set(), []
    for rec in records:
        row_id = ad.make_row_id(rec)
        if row_id in seen:
            continue
        seen.add(row_id)
        out.append(rec)
    return out


def apply_change_tracking(conn, records, now):
    """Fill open_jobs_changed_at on each record from what is already stored."""
    by_id = {ad.make_row_id(r): r for r in records}
    stored = existing_counts(conn, by_id)
    for row_id, rec in by_id.items():
        prev = stored.get(row_id)
        if prev is None:
            rec["open_jobs_changed_at"] = now
        elif prev[0] != rec["open_jobs_at_validation"]:
            rec["open_jobs_changed_at"] = now
        else:
            rec["open_jobs_changed_at"] = prev[1] or now
    return records


def touch_validated(conn, records, now):
    """Bump last_validated_at for every row this run looked at.

    Needed because last_validated_at is deliberately NOT a hash field: an
    unchanged row takes upsert's touch branch, which bumps last_seen and
    nothing else. Without this, a token confirmed alive every month for a year
    would still read last_validated_at = the day it was discovered.
    """
    ids = [ad.make_row_id(r) for r in records]
    if not ids:
        return 0
    cur = conn.execute(
        f"UPDATE {ATS_TABLE} SET last_validated_at = %s WHERE id = ANY(%s)",  # noqa: S608 -- splices ATS_TABLE, a module-level constant
        (now, ids))
    conn.commit()
    return cur.rowcount


#: Batch size for the ONE durability boundary in the probe loop, counted in
#: EMPLOYERS PROBED.
#:
#: WHY THIS IS NOT "once at the end, it is simpler". A full pass is ~380
#: employers at a 1.2s politeness delay -- about forty minutes of outward HTTP
#: against several hundred strangers. Buffering the whole run means a crash,
#: an OOM, a `systemctl stop`, or a laptop lid at minute 39 discards every
#: token discovered AND leaves ats_seed.last_probed_at set, so the next run
#: skips those employers as recently probed and the requests are spent for
#: nothing. Flushing in batches makes an interrupted run a partial success,
#: which is the honest outcome.
#:
#: WHY IT IS COUNTED IN EMPLOYERS AND NOT IN RECORDS -- defect D45. A probe
#: writes to two tables: ats_seed.last_probe_outcome (record_probe) and
#: company_ats (flush). Those used to commit on two different cadences
#: measured on two different AXES -- the seed committed every 20 ITERATIONS,
#: company_ats flushed every 50 RECORDS -- so no choice of constants could
#: line them up, and a run killed between the two boundaries kept the seed
#: outcome durably while silently discarding up to 49 buffered company_ats
#: rows. That is what happened: a 100-employer pass on 2026-07-28T07:40 left
#: exactly 50 rows in company_ats (one flush batch) and 100 outcomes in
#: ats_seed, and the 104-row shortfall D45 reports is the accumulated
#: difference. "Partial success" is only honest if BOTH tables are partial by
#: the same amount, so there is now one boundary, on the iteration axis, and
#: commit_batch() is the only place either table is made durable.
FLUSH_EVERY = 20


def flush(conn, records, now, verbose=False):
    """Write a batch of discovered rows. Returns an UpsertResult.

    upsert_checked, never a bare `upsert()` three-tuple unpack: UpsertResult
    yields (new, updated, unchanged) and NOT .errors, which is the defect
    task 03 existed to remove and CLAUDE.md names a landmine. It also emits
    the `upsert-summary:` line run-daily.py parses, so this step appears in
    the nightly written/dropped record instead of being invisible.
    """
    if not records:
        return UpsertResult()
    records = dedupe_by_id(records)
    apply_change_tracking(conn, records, now)
    try:
        result = upsert_checked(conn, company_ats_spec(), records,
                                ad.make_row_id, debug=verbose)
    except UpsertErrorRate as e:
        # One bad batch is survivable and is recorded, exactly as ingest/ats.py
        # treats one unreachable company. The records that succeeded ARE
        # written -- upsert() commits before the rate check raises.
        #
        # It is survivable, not invisible. The dropped records are carried out
        # on result.errors, main() reports the count in its volume line, and a
        # run that dropped anything exits non-zero: "a run that dropped a
        # hundred records and hit no read errors reported success" is the exact
        # defect lib/upsert.py:246-260 exists to remove, and swallowing it into
        # stderr here would have reinstated it one layer up.
        result = e.result
        print(f"ats-discover ALERT: {len(e.result.errors)} record(s) dropped "
              f"from a batch of {len(records)} -- {e}", file=sys.stderr)
    touch_validated(conn, records, now)
    return result


def commit_batch(conn, records, now, verbose=False, reconcile=True):
    """Make one batch durable in BOTH tables, or in neither. See FLUSH_EVERY.

    flush() -> upsert() commits (lib/upsert.py:235), and that commit also
    lands the record_probe() UPDATEs pending on this same connection, so the
    company_ats rows and the ats_seed outcomes they describe are one
    transaction. The trailing conn.commit() is for the batch that produced no
    records at all -- flush() returns early on an empty list without
    committing, and the seed outcomes still have to land.

    An exception escaping flush() therefore rolls the seed outcomes back too,
    which is the point: the two tables cannot end a run disagreeing.

    The one case that does NOT get rolled back is a per-record upsert failure.
    upsert() isolates those with a SAVEPOINT and commits the survivors before
    check_error_rate raises (lib/upsert.py:198, :235), so the batch partly
    lands and the failed records do not -- D45's shape again, one record wide.
    reconcile_seed_outcomes() closes that too, by measuring what actually
    landed rather than trusting the return value.

    `reconcile=False` for the backfill path, and ONLY for it. Reconciliation
    clears the ats_seed outcome so the employer is re-probed, which is right
    when this batch is the thing that produced the outcome and wrong when
    ats_seed is the SOURCE the batch was derived from -- there, clearing it
    would destroy the only surviving record of a probe that has already been
    paid for, to repair a company_ats row that can be rebuilt from it.
    """
    result = flush(conn, records, now, verbose=verbose)
    if result.errors and reconcile:
        reconcile_seed_outcomes(conn, records, verbose=verbose)
    conn.commit()
    return result


def reconcile_seed_outcomes(conn, records, verbose=False):
    """Un-probe any employer in this batch whose row is NOT in company_ats.

    Called only when a batch reported per-record errors, and it checks the
    TABLE rather than the error list: upsert()'s errors are strings with no
    record identity on them, and inferring identity from a message is how a
    reconciliation quietly stops reconciling.

    Clearing last_probed_at/last_probe_outcome is what makes the next run
    re-probe the employer -- select_employers() orders NULLS FIRST and
    --new-only admits a NULL outcome. probe_attempts is deliberately left
    incremented: the attempt happened, and a counter that only counts
    successes cannot be used to find an employer that fails every time.

    Returns the employer names reset.
    """
    ids = {ad.make_row_id(r): r["employer_name"] for r in records}
    if not ids:
        return []
    landed = {r[0] for r in conn.execute(
        f"SELECT id FROM {ATS_TABLE} WHERE id = ANY(%s)",  # noqa: S608 -- splices ATS_TABLE, a module-level constant
        (list(ids),)).fetchall()}
    lost = sorted({name for row_id, name in ids.items() if row_id not in landed})
    if not lost:
        return []
    conn.execute(
        f"UPDATE {SEED_TABLE} SET last_probed_at = NULL, "  # noqa: S608 -- splices SEED_TABLE, a module-level constant
        f"last_probe_outcome = NULL, last_probe_detail = %s "
        f"WHERE employer_name = ANY(%s)",
        ("write to company_ats failed; outcome cleared for re-probe", lost))
    shown = lost if verbose else lost[:5]
    print(f"ats-discover ALERT: {len(lost)} employer(s) reset for re-probe "
          f"after a failed write -- {', '.join(shown)}"
          f"{'' if len(shown) == len(lost) else ' ... (--verbose for all)'}",
          file=sys.stderr)
    return lost


def exit_on_dropped(conn, errors, repaired=""):
    """Close the connection and exit non-zero if any record was dropped.

    A dropped record is a probe that was paid for -- an outward request against
    a stranger's site -- and then thrown away. Every write path in this script
    ends here rather than each deciding for itself, because "a run that dropped
    a hundred records and hit no read errors reported success" is the defect
    lib/upsert.py:246-260 exists to remove, and one path quietly exiting 0
    reinstates it. run-daily.py:257 already counts the volume from the
    upsert-summary line; this is the run saying so itself.
    """
    conn.close()
    if not errors:
        return
    print(f"ats-discover FAILED: {errors} record(s) dropped and NOT written "
          f"to {ATS_TABLE}.{' ' + repaired if repaired else ''} Read the "
          f"upsert-summary line for what failed.", file=sys.stderr)
    sys.exit(1)


def record_probe(conn, employer_name, outcome, detail, careers_url, now):
    conn.execute(
        f"""
        UPDATE {SEED_TABLE}
           SET last_probed_at = %s, last_probe_outcome = %s,
               last_probe_detail = %s, probe_attempts = probe_attempts + 1,
               careers_url = COALESCE(%s, careers_url)
         WHERE employer_name = %s
        """,  # noqa: S608 -- splices SEED_TABLE, a module-level constant
        (now, outcome, (detail or "")[:300], careers_url, employer_name))


def select_seed_not_found(conn):
    """Every employer whose careers page was READ and held no ATS signature.

    `last_probe_outcome = 'not_found'` is the same judgement never_found_row()
    records; ats_seed is simply the table that kept all of them, because its
    write committed on a cadence company_ats' did not. See FLUSH_EVERY.
    """
    return [{"employer_name": r[0], "careers_url": r[1]}
            for r in conn.execute(
                f"SELECT employer_name, careers_url FROM {SEED_TABLE} "  # noqa: S608 -- splices SEED_TABLE, a module-level constant
                f"WHERE last_probe_outcome = %s ORDER BY employer_name",
                (ad.NOT_FOUND,)).fetchall()]


def backfill_never_found(conn, now, apply=False, verbose=False):
    """Write a never_found row for every ats_seed `not_found` outcome.

    NO NETWORK, and none is needed: the probe already happened and its result
    is in ats_seed. This re-derives the company_ats row that the probe should
    have written, from the outcome it did write.

    Idempotent by construction rather than by a NOT EXISTS guard. A tokenless
    row keys on lower(employer_name) (ats_discovery.make_row_id), the rows
    are byte-identical in shape to the ones already present, and
    careers_url -- the only hash field with any freedom in it -- is copied
    from the same seed column the probe read it from. Verified before writing:
    all 35 pre-existing rows carry exactly the seed's careers_url. So a
    re-run reports every row `unchanged`, which is a stronger statement than
    "selected nothing the second time".

    Returns (rows_considered, UpsertResult).
    """
    seeds = select_seed_not_found(conn)
    records = [ad.never_found_row(s["employer_name"], s["careers_url"], now,
                                  discovered_via="backfill-from-ats_seed")
               for s in seeds]
    if not apply:
        return len(records), UpsertResult()
    return len(records), commit_batch(conn, records, now, verbose=verbose,
                                      reconcile=False)


def probe_pass(conn, fetcher, employers, now, *, apply=False,
               max_url_candidates=ad.MAX_URL_CANDIDATES, breaker_after=25,
               max_blocked_frac=0.35, verbose=False):
    """Probe each employer, writing both tables on one cadence.

    Returns (totals, counts, aborted). Lifted out of main() so the durability
    cadence can be tested by killing a pass at every index and comparing what
    survived in each table -- see tests/test_ats_discovery.py. That is the
    only property of this loop that D45 showed cannot be verified by reading
    it.
    """
    records, counts, aborted = [], {}, None
    totals = UpsertResult()

    for i, employer in enumerate(employers, 1):
        outcome, url, detail, hits = probe_employer(
            fetcher, employer, max_candidates=max_url_candidates)
        counts[outcome] = counts.get(outcome, 0) + 1

        if outcome == ad.FOUND:
            for platform, fields in hits:
                status, open_jobs, note = validate(fetcher, platform, fields)
                records.append({
                    "employer_name": employer["employer_name"],
                    "careers_url": url,
                    "ats": platform,
                    "token": fields["token"],
                    "workday_site": fields.get("workday_site"),
                    "workday_dc": fields.get("workday_dc"),
                    "open_jobs_at_validation": open_jobs,
                    "first_validated_at": now,
                    "last_validated_at": now,
                    "open_jobs_changed_at": None,
                    "status": status,
                    "validation_note": note,
                    "discovered_via": "careers-page-regex",
                })
                counts[f"token:{status}"] = counts.get(f"token:{status}", 0) + 1
        elif outcome == ad.NOT_FOUND:
            # The ONLY path that may write never_found. See ats_discovery.py.
            records.append(ad.never_found_row(employer["employer_name"], url, now))

        if apply:
            record_probe(conn, employer["employer_name"], outcome, detail,
                         url, now)
            # ONE boundary, on the iteration axis, for both tables. See
            # FLUSH_EVERY -- the two-axis version of these four lines is D45.
            if i % FLUSH_EVERY == 0:
                totals += commit_batch(conn, records, now, verbose=verbose)
                records = []

        if verbose or not apply:
            print(f"  [{i}/{len(employers)}] {employer['employer_name'][:38]:40s}"
                  f" {outcome:13s} {detail or ''}"
                  + ("  " + ", ".join(f"{p}:{f['token']}" for p, f in hits)
                     if hits else ""))

        # CIRCUIT BREAKER. A run that is mostly being refused has measured
        # nothing, and finishing it would write a confident, empty answer.
        blocked = counts.get(ad.BLOCKED, 0)
        if i >= breaker_after and blocked / i > max_blocked_frac:
            aborted = (f"{blocked}/{i} probes blocked "
                       f"({blocked / i:.0%} > {max_blocked_frac:.0%})")
            break

    if apply:
        # The tail batch. It runs on the circuit-breaker path too: those
        # probes were performed and their outcomes are already pending on the
        # connection, so dropping their company_ats rows here would recreate
        # the D45 divergence at the one moment the run is least trusted.
        totals += commit_batch(conn, records, now, verbose=verbose)
    return totals, counts, aborted


# -- reporting ---------------------------------------------------------------

def breakdown(conn):
    """(by_ats, seed_outcomes, coverage) -- the numbers the task asks for."""
    by_ats = conn.execute(
        f"""
        SELECT ats, status, count(*), sum(coalesce(open_jobs_at_validation,0))
          FROM {ATS_TABLE} GROUP BY ats, status ORDER BY ats, status
        """).fetchall()  # noqa: S608 -- splices ATS_TABLE, a module-level constant
    outcomes = conn.execute(
        f"""
        SELECT coalesce(last_probe_outcome,'(never probed)'), count(*)
          FROM {SEED_TABLE} GROUP BY 1 ORDER BY 2 DESC
        """).fetchall()  # noqa: S608 -- splices SEED_TABLE, a module-level constant
    # The headline the task asks to be stated explicitly: of the NON-TECH
    # employers we conclusively probed, what fraction resolved to a validated
    # public-feed board. Denominator is conclusively-probed, NOT seeded --
    # dividing by the seed list would silently credit blocked employers as
    # "no ATS" and make the coverage look worse than it was measured to be.
    coverage = conn.execute(
        f"""
        SELECT
          count(*) FILTER (WHERE s.is_non_tech) AS non_tech_probed,
          count(*) FILTER (WHERE s.is_non_tech AND v.valid_any) AS non_tech_valid,
          count(*) FILTER (WHERE s.is_non_tech AND v.valid_public) AS non_tech_public_feed,
          count(*) FILTER (WHERE NOT s.is_non_tech) AS tech_probed,
          count(*) FILTER (WHERE NOT s.is_non_tech AND v.valid_any) AS tech_valid
        FROM {SEED_TABLE} s
        LEFT JOIN LATERAL (
            SELECT bool_or(c.status = 'valid') AS valid_any,
                   bool_or(c.status = 'valid'
                           AND c.ats IN ('greenhouse','lever','ashby')) AS valid_public
              FROM {ATS_TABLE} c WHERE c.employer_name = s.employer_name
        ) v ON TRUE
        WHERE s.last_probe_outcome IN ('found','not_found')
        """).fetchone()  # noqa: S608 -- splices SEED_TABLE/ATS_TABLE, both module-level constants
    return by_ats, outcomes, coverage


def stale_tokens(conn, days=STALE_COUNT_DAYS):
    """Valid tokens whose open-job count has not moved in `days`.

    The failure this task is designed against is NOT a 404. It is a feed that
    keeps returning plausible postings after the employer has migrated away --
    a count frozen at 47 for four months is what that looks like from here.
    """
    cutoff = (utc_now() - datetime.timedelta(days=days)
              ).strftime("%Y-%m-%dT%H:%M:%S")
    return conn.execute(
        f"""
        SELECT employer_name, ats, token, open_jobs_at_validation,
               open_jobs_changed_at
          FROM {ATS_TABLE}
         WHERE status = 'valid' AND open_jobs_changed_at IS NOT NULL
           AND open_jobs_changed_at < %s
         ORDER BY open_jobs_changed_at
        """, (cutoff,)).fetchall()  # noqa: S608 -- splices ATS_TABLE, a module-level constant


def print_report(conn):
    by_ats, outcomes, cov = breakdown(conn)
    print("\n-- company_ats by platform ------------------------------------")
    for ats, status, n, jobs in by_ats:
        print(f"  {ats or '(none)':18s} {status:12s} {n:5d}"
              f"{f'   {int(jobs)} open jobs' if jobs else ''}")
    print("\n-- ats_seed probe outcomes ------------------------------------")
    for outcome, n in outcomes:
        print(f"  {outcome:18s} {n:5d}")
    if cov and cov[0]:
        nt_probed, nt_valid, nt_public, t_probed, t_valid = cov
        # BOTH denominators, always, side by side.
        #
        # The conclusively-probed denominator is the honest measurement -- an
        # employer we were refused by tells us nothing, and counting it as
        # "no ATS" would understate coverage. But quoting only that number
        # overstates coverage of the ROSTER whenever the pass is incomplete or
        # heavily blocked, because it silently drops every employer we never
        # got an answer for. Neither number is sufficient alone, so neither is
        # ever printed alone.
        nt_seeded = conn.execute(
            f"SELECT count(*) FROM {SEED_TABLE} WHERE is_non_tech").fetchone()[0]  # noqa: S608 -- splices SEED_TABLE, a module-level constant
        print("\n-- coverage ---------------------------------------------------")
        print(f"  non-tech employers seeded          : {nt_seeded}")
        print(f"  ...conclusively probed             : {nt_probed} "
              f"({nt_probed / nt_seeded:.1%} of seeded)")
        print(f"  ...with any validated ATS          : {nt_valid} "
              f"= {nt_valid / nt_probed:.1%} of probed, "
              f"{nt_valid / nt_seeded:.1%} of seeded")
        print(f"  ...on greenhouse/lever/ashby       : {nt_public} "
              f"= {nt_public / nt_probed:.1%} of probed, "
              f"{nt_public / nt_seeded:.1%} of seeded")
        if t_probed:
            print(f"  tech control (probed)              : {t_valid}/{t_probed} "
                  f"({t_valid / t_probed:.1%})")
        if nt_probed < nt_seeded:
            print(f"  NOTE: {nt_seeded - nt_probed} non-tech employer(s) have "
                  f"no conclusive result. Any fraction quoted over the probed "
                  f"subset alone overstates roster coverage by "
                  f"{nt_seeded / nt_probed:.1f}x.")
        if nt_public / nt_probed < 0.20:
            print("\n  SIGNAL (16-ats-token-discovery.md:98-100): public-feed "
                  "coverage of the non-tech seed list is under 20%. Task 18 "
                  "(Workday) carries most of the plan's weight and should be "
                  "resourced accordingly.")
    stale = stale_tokens(conn)
    if stale:
        print(f"\n-- {len(stale)} token(s) with an unchanged job count for "
              f"{STALE_COUNT_DAYS}+ days (review) --")
        for name, ats, token, n, since in stale[:15]:
            print(f"  {name[:40]:42s} {ats:10s} {token:24s} {n} since {since}")


# -- main --------------------------------------------------------------------

def revalidation_due(conn, interval_days):
    """Has it been `interval_days` since the last completed full re-validation?

    True when the watermark is absent, so a fresh deployment validates on its
    first scheduled run rather than waiting a month to discover that nothing
    was ever checked.
    """
    last = state.get_watermark(conn, WATERMARK, table=schema.WATERMARK_TABLE)
    if not last:
        return True
    due = (utc_now() - datetime.timedelta(days=interval_days)
           ).strftime("%Y-%m-%dT%H:%M:%S")
    return last <= due


def select_tokens(conn, limit=None, statuses=None):
    """Existing company_ats rows that have a token, for re-validation.

    The cheaper half of the monthly re-probe, and a different question from
    probing: "is this board still alive and how many jobs does it have" costs
    ONE request against an API that expects programmatic traffic, where
    re-reading the careers page costs up to three against a host that does
    not. Re-validation is also the only thing that catches the failure this
    task is actually designed against -- a feed still serving postings filled
    six months ago -- since that board's careers page looks fine.
    """
    sql = (f"SELECT employer_name, careers_url, ats, token, workday_site, "  # noqa: S608 -- splices ATS_TABLE, a module-level constant
           f"workday_dc, discovered_via FROM {ATS_TABLE} WHERE token <> ''")
    params = {}
    if statuses:
        sql += " AND status = ANY(%(st)s)"
        params["st"] = list(statuses)
    sql += " ORDER BY last_validated_at NULLS FIRST, employer_name"
    if limit:
        sql += " LIMIT %(lim)s"
        params["lim"] = limit
    return conn.execute(sql, params).fetchall()


def revalidate(conn, fetcher, rows, now, apply=True, verbose=False):
    """Re-check known tokens against their live feed. Returns (UpsertResult,
    per-status counts)."""
    records, counts = [], {}
    totals = UpsertResult()
    for i, (name, careers_url, ats, token, site, dc, via) in enumerate(rows, 1):
        status, open_jobs, note = validate(
            fetcher, ats, {"token": token, "workday_site": site,
                           "workday_dc": dc})
        counts[status] = counts.get(status, 0) + 1
        records.append({
            "employer_name": name, "careers_url": careers_url, "ats": ats,
            "token": token, "workday_site": site, "workday_dc": dc,
            "open_jobs_at_validation": open_jobs,
            "first_validated_at": now, "last_validated_at": now,
            "open_jobs_changed_at": None, "status": status,
            "validation_note": note, "discovered_via": via or "revalidate",
        })
        if verbose:
            print(f"  [{i}/{len(rows)}] {name[:34]:36s} {ats:10s} "
                  f"{token[:22]:24s} {status:12s} "
                  f"{open_jobs if open_jobs is not None else '-'}")
        if apply and len(records) >= FLUSH_EVERY:
            totals += flush(conn, records, now, verbose=verbose)
            records = []
    if apply:
        totals += flush(conn, records, now, verbose=verbose)
    return totals, counts


def select_employers(conn, limit=None, all_rows=False, only=None,
                     only_unresolved=False):
    """Least-recently-probed first, so a --limit run walks the whole list over
    successive runs instead of re-probing the same head every time.

    `only_unresolved` restricts to employers with no conclusive result yet --
    never probed, or last seen blocked/unreachable/missing_page. That is the
    nightly backfill's selection: it picks up newly added employers and
    retries the ones a WAF refused, without re-fetching the careers page of
    every employer already settled, which would be several hundred requests a
    night to learn nothing.
    """
    where, params = [], {}
    if only:
        where.append("employer_name ILIKE %(only)s")
        params["only"] = f"%{only}%"
    if only_unresolved:
        where.append("(last_probe_outcome IS NULL "
                     "OR last_probe_outcome NOT IN ('found','not_found'))")
    sql = (f"SELECT employer_name, careers_url, sector, is_non_tech "  # noqa: S608 -- splices SEED_TABLE, a module-level constant
           f"FROM {SEED_TABLE}")
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY last_probed_at NULLS FIRST, employer_name"
    if not all_rows and limit:
        sql += " LIMIT %(lim)s"
        params["lim"] = limit
    return [{"employer_name": r[0], "careers_url": r[1], "sector": r[2],
             "is_non_tech": r[3]}
            for r in conn.execute(sql, params).fetchall()]


def main():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--apply", action="store_true",
                   help="write company_ats (default: probe and report only)")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--all", action="store_true", help="probe every seeded employer")
    p.add_argument("--only", help="substring match on employer_name")
    p.add_argument("--new-only", action="store_true",
                   help="probe only employers never conclusively probed "
                        "(never probed, or last outcome blocked/unreachable/"
                        "missing_page) -- the nightly backfill")
    p.add_argument("--report", action="store_true",
                   help="print the breakdown from the table; no network")
    p.add_argument("--nightly", action="store_true",
                   help="the scheduled shape: re-validate every known token "
                        "if the monthly cadence is due, then probe up to "
                        "--limit employers that have no conclusive answer yet")
    p.add_argument("--due-only", action="store_true",
                   help="exit 0 immediately unless the monthly re-probe is due")
    p.add_argument("--interval-days", type=int, default=DEFAULT_INTERVAL_DAYS)
    p.add_argument("--delay", type=float, default=1.5)
    p.add_argument("--host-delay", type=float, default=5.0)
    p.add_argument("--max-requests", type=int, default=2000)
    p.add_argument("--timeout", type=int, default=TIMEOUT,
                   help="per-request timeout in seconds")
    p.add_argument("--max-url-candidates", type=int, default=ad.MAX_URL_CANDIDATES)
    p.add_argument("--max-blocked-frac", type=float, default=0.35,
                   help="abort the run above this blocked fraction")
    p.add_argument("--breaker-after", type=int, default=25,
                   help="probes before the blocked-fraction breaker arms")
    p.add_argument("--revalidate", action="store_true",
                   help="skip the careers-page probe; re-check known "
                        "company_ats tokens against their live feed")
    p.add_argument("--revalidate-status", nargs="*",
                   help="restrict --revalidate to these status values")
    p.add_argument("--backfill-never-found", action="store_true",
                   help="write a company_ats never_found row for every "
                        "ats_seed not_found outcome and exit; no network, no "
                        "re-probing (defect D45)")
    p.add_argument("--add-employer", help="add one employer to ats_seed and exit")
    p.add_argument("--careers-url")
    p.add_argument("--sector", default="unknown")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    envfile.load(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

    conn = dbconn.connect_or_exit("ats-discover", schema=schema.SCHEMA)
    ensure_ats_schema(conn)
    state.ensure_state_schema(conn, watermark_table=schema.WATERMARK_TABLE,
                              with_claims=True)

    if args.add_employer:
        n = insert_discovered_employers(
            conn, [{"employer_name": args.add_employer,
                    "careers_url": args.careers_url,
                    "sector": args.sector,
                    "is_non_tech": args.sector != "tech"}],
            source="manual --add-employer")
        print(f"ats-discover: added {n} employer(s).")
        conn.close()
        return

    if args.report:
        print_report(conn)
        conn.close()
        return

    if args.backfill_never_found:
        now = utc_now_str()
        considered, res = backfill_never_found(conn, now, apply=args.apply,
                                               verbose=args.verbose)
        print(f"ats-discover: backfill -- {considered} ats_seed "
              f"'{ad.NOT_FOUND}' outcome(s); {res.new} new, {res.updated} "
              f"updated, {res.unchanged} unchanged, {len(res.errors)} dropped.")
        if args.apply:
            print_report(conn)
        else:
            print("\ndry run -- nothing written. Re-run with --apply.")
        exit_on_dropped(conn, len(res.errors),
                        "ats_seed still holds every outcome, so re-running "
                        "the backfill is safe and repairs it.")
        return

    if args.due_only and not revalidation_due(conn, args.interval_days):
        # Silent on purpose: this is 29 days out of 30, and a line here would
        # train the reader to ignore this step's output.
        conn.close()
        return

    if args.nightly:
        # Phase 1, monthly: re-check every known token. Cheap -- one request
        # per token against an API, versus up to three against an employer's
        # own site -- and it is the half that catches a stale feed.
        args.new_only = True
        if revalidation_due(conn, args.interval_days):
            rows = select_tokens(conn)
            if rows:
                fetcher = Fetcher(delay=args.delay, host_delay=args.host_delay,
                                  max_requests=args.max_requests,
                                  verbose=args.verbose, timeout=args.timeout)
                now = utc_now_str()
                totals, counts = revalidate(conn, fetcher, rows, now,
                                            apply=args.apply,
                                            verbose=args.verbose)
                print(f"ats-discover: monthly re-validation of {len(rows)} "
                      f"token(s) -- "
                      + ", ".join(f"{k} {v}" for k, v in sorted(counts.items()))
                      + f"; {totals.new + totals.updated} written, "
                      f"{len(totals.errors)} dropped.")
                if args.apply:
                    state.set_watermark(conn, WATERMARK, now,
                                        table=schema.WATERMARK_TABLE)
                    for row in stale_tokens(conn):
                        print(f"ats-discover: STALE -- {row[0]} {row[1]}:"
                              f"{row[2]} has reported {row[3]} open jobs "
                              f"unchanged since {row[4]}; review.")
        # Phase 2 falls through into the ordinary probe path below, restricted
        # to employers with no conclusive answer yet.

    if args.revalidate:
        rows = select_tokens(conn, limit=None if args.all else args.limit,
                             statuses=args.revalidate_status)
        if not rows:
            print("ats-discover: no tokens to re-validate.")
            conn.close()
            return
        fetcher = Fetcher(delay=args.delay, host_delay=args.host_delay,
                          max_requests=args.max_requests,
                          verbose=args.verbose, timeout=args.timeout)
        now = utc_now_str()
        totals, counts = revalidate(conn, fetcher, rows, now,
                                    apply=args.apply, verbose=args.verbose)
        print(f"ats-discover: re-validated {len(rows)} token(s) -- "
              + ", ".join(f"{k} {v}" for k, v in sorted(counts.items()))
              + f"; {totals.new + totals.updated} row(s) written, "
              f"{len(totals.errors)} dropped; {fetcher.requests} request(s), "
              f"{len(fetcher.blocked_hosts)} host(s) blocklisted.")
        if args.apply:
            print_report(conn)
        else:
            print("\ndry run -- nothing written. Re-run with --apply.")
        exit_on_dropped(conn, len(totals.errors),
                        "The tokens are unchanged in company_ats; the next "
                        "re-validation retries them.")
        return

    # Discovery sources beyond the seeded roster. Stubbed, and loud about it.
    insert_discovered_employers(conn, adzuna_top_companies(), "adzuna")

    employers = select_employers(conn, limit=args.limit, all_rows=args.all,
                                 only=args.only,
                                 only_unresolved=args.new_only)
    if not employers:
        if args.new_only:
            # Not a failure: every seeded employer has a conclusive result,
            # which is the steady state this mode is supposed to reach.
            return conn.close()
        print("ats-discover: no employers to probe -- run "
              "migrations/migrate_company_ats.py --apply first.")
        conn.close()
        sys.exit(1)

    fetcher = Fetcher(delay=args.delay, host_delay=args.host_delay,
                      max_requests=args.max_requests, verbose=args.verbose,
                      timeout=args.timeout)
    now = utc_now_str()
    totals, counts, aborted = probe_pass(
        conn, fetcher, employers, now, apply=args.apply,
        max_url_candidates=args.max_url_candidates,
        breaker_after=args.breaker_after,
        max_blocked_frac=args.max_blocked_frac,
        verbose=args.verbose)
    written, errors = totals.new + totals.updated, len(totals.errors)

    # Volume, not errors -- the summary prints on every run, including a clean
    # one, and separates conclusive observations from inconclusive ones. A
    # reader who sees `found 0` next to `blocked 0 unreachable 0` knows the
    # market is empty; next to `blocked 180` they know nothing was measured.
    conclusive = sum(counts.get(k, 0) for k in ad.CONCLUSIVE)
    inconclusive = sum(counts.get(k, 0) for k in ad.INCONCLUSIVE)
    tokens = {k[6:]: v for k, v in counts.items() if k.startswith("token:")}
    print(f"ats-discover: probed {conclusive + inconclusive} employer(s) -- "
          f"conclusive {conclusive} (found {counts.get(ad.FOUND, 0)}, "
          f"not_found {counts.get(ad.NOT_FOUND, 0)}), "
          f"inconclusive {inconclusive} ("
          + ", ".join(f"{k} {counts.get(k, 0)}" for k in ad.INCONCLUSIVE)
          + f"); tokens " + (", ".join(f"{k} {v}" for k, v in sorted(tokens.items()))
                             or "0")
          + f"; {written} row(s) written, {errors} dropped; "
          f"{fetcher.requests} request(s), "
          f"{len(fetcher.blocked_hosts)} host(s) blocklisted.")

    if aborted:
        print(f"ats-discover FAILED: circuit breaker tripped -- {aborted}. "
              f"The result of this run is NOT evidence that these employers "
              f"have no ATS; they were refused. Re-run later or lower "
              f"--delay pressure.", file=sys.stderr)
        conn.close()
        sys.exit(1)

    if args.apply:
        # Only on a run that completed. The watermark is what --due-only
        # reads, and advancing it after an aborted run would skip the next
        # month on the strength of a blocked probe -- the same mistake
        # lib/state.py:69-76 documents for nyc-events' max_pages cap.
        if args.all or args.due_only:
            # Only a FULL pass advances the cadence clock. A --limit run walks
            # part of the list and must not make the next month's re-probe
            # think it already happened.
            state.set_watermark(conn, WATERMARK, now,
                                table=schema.WATERMARK_TABLE)
        print_report(conn)
    else:
        print("\ndry run -- nothing written. Re-run with --apply.")

    exit_on_dropped(conn, errors,
                    "Their ats_seed outcomes were cleared by "
                    "reconcile_seed_outcomes(), so the next run re-probes "
                    "those employers; nothing needs repairing by hand.")


if __name__ == "__main__":
    main()
