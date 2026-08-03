#!/usr/bin/env python3
"""
Create `ats_seed` and `company_ats`, and load the NYC employer seed list.

WHAT THESE TWO TABLES ARE

    ats_seed     WHO to probe. One row per employer: a display name, a
                 starting careers URL, a sector, and the outcome of the last
                 probe. Grows continuously and is the thing task 16 means by
                 "store as a simple seeded table, not a config file" -- adding
                 an employer is an INSERT, never a deploy.

    company_ats  WHAT was found. One row per (ats, token) -- plus one row per
                 employer conclusively found to run no public-feed ATS. This
                 is what tasks 17, 18 and 20 read instead of
                 config/companies.json.

WHY TWO TABLES AND NOT ONE
    They have opposite lifecycles and opposite cardinalities. An employer is
    seeded once and probed forever; a token is discovered, validated monthly,
    and may go dead or be replaced when the employer migrates ATS. One
    employer can also yield several tokens (a hospital system with a separate
    board for its physician group is normal). Folding them together would mean
    either losing the seed row when a token dies or losing the token history
    when the seed is re-probed.

WHY A MIGRATION AND NOT schema.ensure_schema()
    Same reasoning as migrate_scores.py and migrate_profiles.py: this writes
    ROWS, not just structure, and the rows it writes decide what the probe
    will spend several hundred outward HTTP requests on. The DDL half is
    additive and idempotent; the seed half is opt-in. Dry run is the default.

    The DDL is nonetheless re-run on every invocation of tools/ats-discover.py
    via ensure_ats_schema() below, which is import-safe and does no row writes
    -- so the discovery tool cannot run against a half-created schema, and
    nothing has to remember to run this first.

USAGE
    python3 migrations/migrate_company_ats.py                 # report only
    python3 migrations/migrate_company_ats.py --apply         # create + seed
    python3 migrations/migrate_company_ats.py --apply --seed-file other.json
    python3 migrations/migrate_company_ats.py --apply --refresh-urls

IDEMPOTENT. Re-running inserts only employers absent from the table and
leaves every probe result alone. It deliberately does NOT overwrite
careers_url on an existing row -- the probe corrects that column when it
follows a redirect or a fallback path, and a stale hand-written value in the
seed FILE must not clobber a live one learned from the network. Pass
--refresh-urls when the file is genuinely the better source.
"""

import argparse
import json
import os
import sys

# migrations/ sits one level below the pipeline modules it imports (schema,
# ats_discovery, ...). Python puts THIS file's directory on sys.path, not its
# parent, so the parent is added by hand. That same insert is what reaches
# lib/ -- there is nothing to install.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)

import schema  # noqa: E402
from lib import dbconn, envfile  # noqa: E402
from lib.timeparse import utc_now_str  # noqa: E402

# Unlike the other migrations, this one establishes its own environment. Those
# were run by hand in a shell that had already sourced .env; this one is also
# the documented first step of a task whose second step (tools/ats-discover.py)
# loads .env itself, and having the two disagree about where DATABASE_URL comes
# from is exactly the confusion run-daily.py's docstring records from the
# 2026-07-25 run. Already-exported values still win -- see envfile.load().
envfile.load(os.path.join(_REPO_ROOT, ".env"))

SEED_TABLE = "ats_seed"
ATS_TABLE = "company_ats"

#: Resolved against the repo root. data/ rather than config/: this is an input
#: corpus with provenance, not tuning, and it is read exactly once per
#: environment (by this script) rather than on every pipeline run.
SEED_FILE = os.path.join(_REPO_ROOT, "data", "nyc-employer-seed.json")


def ensure_ats_schema(conn):
    """Create both tables and their indexes. Idempotent, no row writes.

    Called by this migration and by tools/ats-discover.py on every run, for
    the same reason schema.ensure_schema() is called by every ingest script:
    a tool that cannot run until someone remembers to run a migration is a
    tool that will be run against a missing table at 03:00.
    """
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {SEED_TABLE} (
            employer_name TEXT PRIMARY KEY,
            careers_url TEXT,
            sector TEXT,
            is_non_tech BOOLEAN NOT NULL DEFAULT TRUE,
            seed_source TEXT,
            notes TEXT,
            added_at TEXT NOT NULL,
            last_probed_at TEXT,
            -- The probe outcome vocabulary from ats_discovery.py. This column
            -- is the whole reason a blocked run is distinguishable from an
            -- empty one: "we found no tokens" decomposes into 'not_found'
            -- (a real negative) versus 'blocked'/'unreachable'/'missing_page'
            -- (we were never allowed to look), and the two are counted apart
            -- in every report.
            last_probe_outcome TEXT,
            last_probe_detail TEXT,
            probe_attempts INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {ATS_TABLE} (
            id TEXT PRIMARY KEY,
            employer_name TEXT NOT NULL,
            careers_url TEXT,
            ats TEXT NOT NULL,
            token TEXT NOT NULL,
            -- Workday needs all three of tenant/dc/site and they are stored
            -- separately on purpose: `git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_three/18-ingest-workday-cxs.md:54` forbids
            -- guessing the data centre, because wd1 vs wd5 is a 404 and a 404
            -- there looks exactly like a tenant with no open roles.
            workday_site TEXT,
            workday_dc TEXT,
            open_jobs_at_validation INTEGER,
            -- Moves only when the count actually changes, which is what makes
            -- "unchanged for 60 days" answerable. last_validated_at moves on
            -- every probe and cannot answer it.
            open_jobs_changed_at TEXT,
            first_validated_at TEXT,
            last_validated_at TEXT,
            status TEXT NOT NULL,
            validation_note TEXT,
            discovered_via TEXT,
            content_hash TEXT,
            first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL
        )
    """)
    conn.commit()
    # Task 17's query is "every valid row for the platforms I handle"; task
    # 18's is the same restricted to workday. Both are (status, ats)-first.
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_company_ats_status "
                 f"ON {ATS_TABLE}(status, ats)")
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_company_ats_employer "
                 f"ON {ATS_TABLE}(employer_name)")
    # The monthly re-probe's selection query: least-recently-probed first.
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_ats_seed_probed "
                 f"ON {SEED_TABLE}(last_probed_at NULLS FIRST)")
    conn.commit()


def load_seed_file(path):
    with open(path) as f:
        doc = json.load(f)
    rows = doc["employers"]
    for r in rows:
        if not r.get("employer_name"):
            raise ValueError(f"seed row with no employer_name: {r!r}")
    return rows


def insert_seed(conn, rows, now, refresh_urls=False):
    """Insert absent employers. Returns (inserted, refreshed, skipped).

    ON CONFLICT DO NOTHING by default -- see IDEMPOTENT in the docstring. The
    probe writes back a corrected careers_url when the seeded one redirected
    or 404'd, and re-running this script must not undo that.
    """
    inserted = refreshed = skipped = 0
    for r in rows:
        cur = conn.execute(
            f"""
            INSERT INTO {SEED_TABLE}
                (employer_name, careers_url, sector, is_non_tech,
                 seed_source, notes, added_at)
            VALUES (%(employer_name)s, %(careers_url)s, %(sector)s,
                    %(is_non_tech)s, %(seed_source)s, %(notes)s, %(added_at)s)
            ON CONFLICT (employer_name) DO NOTHING
            """,
            {"notes": None, **r, "added_at": now},
        )
        if cur.rowcount:
            inserted += 1
            continue
        skipped += 1
        if refresh_urls:
            conn.execute(
                f"UPDATE {SEED_TABLE} SET careers_url = %s, sector = %s, "
                f"is_non_tech = %s WHERE employer_name = %s",
                (r.get("careers_url"), r.get("sector"),
                 bool(r.get("is_non_tech", True)), r["employer_name"]))
            refreshed += 1
    conn.commit()
    return inserted, refreshed, skipped


def report(conn):
    seeded = conn.execute(f"SELECT count(*) FROM {SEED_TABLE}").fetchone()[0]
    non_tech = conn.execute(
        f"SELECT count(*) FROM {SEED_TABLE} WHERE is_non_tech").fetchone()[0]
    tokens = conn.execute(f"SELECT count(*) FROM {ATS_TABLE}").fetchone()[0]
    return seeded, non_tech, tokens


def main():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--apply", action="store_true",
                   help="create the tables and load the seed (default: report)")
    p.add_argument("--seed-file", default=SEED_FILE)
    p.add_argument("--refresh-urls", action="store_true",
                   help="overwrite careers_url/sector on employers already "
                        "present -- normally the probe's value wins")
    args = p.parse_args()

    try:
        rows = load_seed_file(args.seed_file)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as e:
        print(f"migrate-company-ats FAILED: could not read "
              f"{args.seed_file}: {e}")
        sys.exit(1)

    non_tech = sum(1 for r in rows if r.get("is_non_tech", True))
    sectors = {}
    for r in rows:
        sectors[r.get("sector") or "?"] = sectors.get(r.get("sector") or "?", 0) + 1

    print("migrate-company-ats:")
    print(f"  seed file        : {args.seed_file}")
    print(f"  employers in file: {len(rows)} ({non_tech} non-tech, "
          f"{len(rows) - non_tech} tech)")
    print(f"  sectors          : "
          f"{', '.join(f'{k} {v}' for k, v in sorted(sectors.items()))}")

    conn = dbconn.connect_or_exit("migrate-company-ats", schema=schema.SCHEMA)

    if not args.apply:
        exists = conn.execute(
            "SELECT to_regclass(%s)", (f"{schema.SCHEMA}.{SEED_TABLE}",)
        ).fetchone()[0]
        if exists:
            seeded, nt, tokens = report(conn)
            print(f"  {SEED_TABLE} today : {seeded} employers ({nt} non-tech)")
            print(f"  {ATS_TABLE} today: {tokens} rows")
        else:
            print(f"  {SEED_TABLE}/{ATS_TABLE}: do not exist yet")
        print("\ndry run -- nothing changed. Re-run with --apply.")
        conn.close()
        return

    ensure_ats_schema(conn)
    inserted, refreshed, skipped = insert_seed(
        conn, rows, utc_now_str(), refresh_urls=args.refresh_urls)
    seeded, nt, tokens = report(conn)

    print(f"\n  inserted  : {inserted}")
    print(f"  already there: {skipped}"
          f"{f' ({refreshed} refreshed)' if refreshed else ''}")
    print(f"  {SEED_TABLE} now: {seeded} employers ({nt} non-tech)")
    print(f"  {ATS_TABLE} now: {tokens} rows")
    print("\n  next: python3 tools/ats-discover.py --apply")
    conn.close()


if __name__ == "__main__":
    main()
