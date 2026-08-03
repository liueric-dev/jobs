"""Where `ingest/ats.py` gets its company list: the `company_ats` table.

WHAT CHANGED, AND WHY IT IS A TABLE NOW
    `ats.py` used to read `config/companies.json` -- 68 hand-verified tech
    tokens -- on every run. Task 16 built `company_ats` (see
    `migrations/migrate_company_ats.py:113-141` for the DDL and
    `git show refactor-freeze-2026-08-02:docs/ats-token-discovery.md` for what is in it), and
    `git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_three/16-ats-token-discovery.md:34`
    states the rule this module implements:
    "store as a simple seeded table, not a config file -- it will grow
    continuously." Adding an employer is an INSERT, never a deploy.

    `config/companies.json` is therefore RETIRED as a runtime input. It is
    now a one-time seed corpus, loaded by `ingest/ats.py --seed-from-json`,
    in exactly the relationship `data/nyc-employer-seed.json` has to
    `ats_seed`. Nothing reads it on a nightly run. There is one roster and it
    lives in Postgres.

WHICH STATUSES ADMIT A TOKEN -- AND WHY IT IS NOT JUST 'valid'
    `company_ats.status` is a four-value vocabulary, not a boolean
    (`ats_discovery.py:77-80`): `valid`, `dead`, `never_found`,
    `unvalidated`.

      valid        the ATS answered and listed jobs. Ingest it.

      unvalidated  a token was found and the ATS did NOT answer -- 403, 429,
                   5xx, a network failure, or a 200 whose body was not a
                   recognisable feed (`ats_discovery.py:353-384`). Task 16
                   added this value precisely so that "we could not check"
                   would stop being recorded as either `valid` or `dead`.
                   INGEST IT ANYWAY, for the platforms below. The cost of
                   trying is one request that either works or lands in the
                   per-company error list this script already keeps; the cost
                   of not trying is that a token blocked once at validation
                   time is never pulled again, which is the same silence
                   `git show refactor-freeze-2026-08-02:docs/ats-token-discovery.md:177-186` is about. Rows
                   admitted this way are counted separately on the summary
                   line so the decision stays visible.

      dead         the endpoint 404'd or returned an empty list
                   (`ats_discovery.py:369,383`). Excluded: that is a
                   conclusive negative from the vendor's own API.

      never_found  an employer with NO token at all -- `ats=''`, `token=''`
                   (`ats_discovery.py:490-491`). Excluded by the platform
                   filter before status is even considered.

    Read `git show refactor-freeze-2026-08-02:docs/ats-token-discovery.md:35-60` before treating any of this as a
    coverage measurement: task 16's positive control found 0 of 4 known-good
    tokens because those boards render client-side, so absence from this
    table is not evidence of absence in the world.

DEDUPLICATION IS NOT OPTIONAL
    Two employers can share one board -- a health system and its physician
    group, a parent and its subsidiary. `company_ats` keys on
    (ats, token, workday_site) (`ats_discovery.py:457-473`), so that is
    already one row there; but a roster assembled from several statuses, or
    later from several sources, can still hand `ats.py` the same board twice.
    Pulling it twice would double every request and make `close_missing`
    run twice over the same rows. Deduplicated here, once.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ats_discovery  # noqa: E402
from lib.timeparse import utc_now_str  # noqa: E402
from lib.upsert import TableSpec, upsert_checked  # noqa: E402

ATS_TABLE = "company_ats"

#: The platforms `ingest/ats.py` can fetch. Workday is task 18's and iCIMS is
#: task 20's; both have rows in this table and neither is pulled here.
HANDLED_PLATFORMS = ("greenhouse", "lever", "ashby", "workable", "recruitee",
                     "smartrecruiters")

#: See WHICH STATUSES ADMIT A TOKEN above. Order matters only for reporting.
STATUS_VALID = ats_discovery.STATUS_VALID
STATUS_UNVALIDATED = ats_discovery.STATUS_UNVALIDATED
ADMITTING_STATUSES = (STATUS_VALID, STATUS_UNVALIDATED)

#: TableSpec for seeding. Identical to the one `tools/ats-discover.py` writes
#: through -- deliberately, because two writers with different hash fields
#: would report each other's rows as changed on every run.
COMPANY_ATS_SPEC = TableSpec(
    table=ATS_TABLE,
    columns=ats_discovery.COMPANY_ATS_COLUMNS,
    hash_fields=ats_discovery.HASH_FIELDS_COMPANY_ATS,
    sticky=ats_discovery.STICKY_COMPANY_ATS,
)


def load_companies(conn, platforms=HANDLED_PLATFORMS,
                   statuses=ADMITTING_STATUSES, table=ATS_TABLE):
    """The roster, as a list of dicts `ats.py` can loop over.

    Each dict carries `platform`, `token`, `name` and `status`. It does NOT
    carry `is_nyc_hq` / `is_ai_focused`: `company_ats` has no column for them
    and adding one is a schema change this task is not allowed to make. See
    `normalize_*` in ats.py for what those two columns now hold.

    Sorted by (platform, token) so a run's request order is stable and two
    runs' logs diff cleanly.
    """
    rows = conn.execute(
        f"""
        SELECT ats, token, employer_name, status
          FROM {table}
         WHERE ats = ANY(%s) AND status = ANY(%s) AND token <> ''
         ORDER BY ats, token
        """,  # noqa: S608 -- splices `table`, always one of this module's own constant table names
        (list(platforms), list(statuses)),
    ).fetchall()

    out, seen = [], set()
    for platform, token, name, status in rows:
        key = (platform.lower(), token.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append({"platform": platform, "token": token,
                    "name": name, "status": status})
    return out


# ---------------------------------------------------------------------------
# the one-time seed
# ---------------------------------------------------------------------------

#: The date `config/companies.json`'s own `_comment` records as when every
#: token in it was confirmed live by a direct HTTP call. Used as
#: first/last_validated_at on a seeded row rather than "now", because
#: stamping today's date on a check made in July is how a 60-day staleness
#: rule gets quietly disarmed
#: (`git show refactor-freeze-2026-08-02:docs/ats-token-discovery.md:344-350`).
COMPANIES_JSON_VERIFIED_AT = "2026-07-23T00:00:00Z"

SEED_DISCOVERED_VIA = "companies-json-seed"

SEED_NOTE = ("seeded from config/companies.json, whose tokens were each "
             "confirmed live by a direct call to the platform's public API "
             "on " + COMPANIES_JSON_VERIFIED_AT[:10] + "; re-checked by the "
             "monthly pass in tools/ats-discover.py --nightly")


def companies_json_rows(path):
    """`config/companies.json`'s `companies` list as company_ats records.

    Only the three platforms that file ever held (greenhouse, lever, ashby)
    can appear; anything else is a typo and is surfaced rather than skipped.
    """
    with open(path) as fh:
        doc = json.load(fh)

    rows = []
    for entry in doc["companies"]:
        platform = entry["platform"]
        if platform not in HANDLED_PLATFORMS:
            raise ValueError(
                f"config/companies.json names platform {platform!r} for "
                f"{entry.get('name')!r}, which ingest/ats.py does not handle")
        rows.append({
            "employer_name": entry["name"],
            "careers_url": None,
            "ats": platform,
            "token": entry["token"],
            "workday_site": None,
            "workday_dc": None,
            "open_jobs_at_validation": entry.get("job_count_at_verification"),
            "first_validated_at": COMPANIES_JSON_VERIFIED_AT,
            "last_validated_at": COMPANIES_JSON_VERIFIED_AT,
            "open_jobs_changed_at": COMPANIES_JSON_VERIFIED_AT,
            "status": ats_discovery.STATUS_VALID,
            "validation_note": SEED_NOTE,
            "discovered_via": SEED_DISCOVERED_VIA,
        })
    return rows


def seed_from_companies_json(conn, path, table=ATS_TABLE, debug=False):
    """Insert absent tokens from `path`. Returns (result, skipped).

    INSERT-ONLY, by pre-filtering on the primary key rather than by relying
    on the upsert's three branches. `tools/ats-discover.py` owns every row it
    wrote; re-running this must never overwrite a probe's `status` or
    `validation_note` with the seed file's stale opinion. Same rule, and the
    same reason, as `migrations/migrate_company_ats.py:165-171`.

    Goes through `upsert_checked` rather than `upsert` -- CLAUDE.md's
    landmine, and it is also what puts this step in run-daily.py's nightly
    written/dropped accounting via the `upsert-summary:` line.
    """
    rows = companies_json_rows(path)
    existing = {r[0] for r in conn.execute(
        f"SELECT id FROM {table}").fetchall()}  # noqa: S608 -- splices `table`, always one of this module's own constant table names
    fresh = [r for r in rows
             if ats_discovery.make_row_id(r) not in existing]
    skipped = len(rows) - len(fresh)
    result = upsert_checked(conn, COMPANY_ATS_SPEC, fresh,
                            ats_discovery.make_row_id, now=utc_now_str(),
                            debug=debug)
    return result, skipped
