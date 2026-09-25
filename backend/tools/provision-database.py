#!/usr/bin/env python3
"""Create or verify the ingestion database schema.

This is for a fresh database. Use --verify-only before pointing it at an
existing one; no stored rows or legacy product tables are removed.
"""

import argparse
import os
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)
sys.path.insert(0, os.path.join(_BACKEND, "migrations"))

import psycopg  # noqa: E402

import schema  # noqa: E402
from lib import envfile  # noqa: E402
from migrate_company_ats import ensure_ats_schema  # noqa: E402

REQUIRED_TABLES = ("jobs", "job_ingest_state", "hn_seen_comments",
                   "ats_seed", "company_ats")


def verify_schema(conn):
    missing = [table for table in REQUIRED_TABLES
               if conn.execute("SELECT to_regclass(%s)",
                               (f"public.{table}",)).fetchone()[0] is None]
    if missing:
        raise RuntimeError("missing ingestion tables: " + ", ".join(missing))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", help="database URL; DATABASE_URL otherwise")
    parser.add_argument("--verify-only", action="store_true",
                        help="check tables without issuing DDL")
    args = parser.parse_args(argv)

    envfile.load(os.path.join(_BACKEND, ".env"))
    url = args.url or os.environ.get("DATABASE_URL")
    if not url:
        print("no database: pass --url or set DATABASE_URL", file=sys.stderr)
        return 2

    with psycopg.connect(url) as conn:
        if not args.verify_only:
            schema.ensure_schema(conn)
            ensure_ats_schema(conn)
            conn.commit()
        try:
            verify_schema(conn)
        except RuntimeError as exc:
            print(f"NOT READY: {exc}", file=sys.stderr)
            return 1
    print("ingestion schema: ready")
    return 0


if __name__ == "__main__":
    sys.exit(main())
