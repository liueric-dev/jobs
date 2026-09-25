"""Load deduplicated ATS board tokens from company_ats.

The runtime roster is the table, not config/companies.json. Valid and
temporarily unvalidated tokens are attempted; conclusively dead or absent
tokens are skipped. Seed imports are insert-only.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ats_discovery  # noqa: E402
from lib.timeparse import utc_now_str  # noqa: E402
from lib.upsert import TableSpec, upsert_checked  # noqa: E402

ATS_TABLE = "company_ats"

#: The platforms `ingest/ats.py` can fetch. Workday uses its own fetcher;
#: unsupported platforms are excluded here.
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

#: Date the original seed tokens were confirmed by direct HTTP calls. Used as
#: first/last_validated_at on a seeded row rather than "now", because
#: stamping today's date on a check made in July is how a 60-day staleness
#: rule gets quietly disarmed.
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

    Goes through `upsert_checked` rather than `upsert`, so dropped rows are
    counted in run-daily.py's nightly
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
