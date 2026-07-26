#!/usr/bin/env python3
"""
Admin CLI for contributor accounts and API keys.

RUN LOCALLY ONLY -- this is never exposed over HTTP. It talks straight to
Postgres, so it must only ever run on the server itself (or over a trusted
tunnel), unlike app.py which is the untrusted-facing surface.

    python3 manage_users.py init-schema          # once, with an admin credential
    python3 manage_users.py create --name "Dave" --label "dave-laptop"
    python3 manage_users.py list
    python3 manage_users.py revoke --key-hash <prefix>

KEY HANDLING: the raw key is printed exactly once, at creation, and is never
stored anywhere -- only sha256(key) goes into the database. There is
deliberately no "show me Dave's key again" command: if a key is lost, revoke
it and mint a new one. That way a database dump (or this script's output being
piped somewhere) never yields working credentials.

TWO CREDENTIALS: `init-schema` is the only command that issues DDL, and it is
the only one that uses JOBS_ADMIN_DATABASE_URL. Everything else runs on the
same restricted DATABASE_URL the API itself uses, because create/list/revoke
need nothing beyond the INSERT/SELECT/UPDATE grants that role already holds.
Keeping schema creation in a separate, explicitly-invoked command is what lets
the long-running service hold no schema-modification rights at all.
"""

import os
import sys
import secrets
import hashlib
import argparse
from datetime import datetime, timezone

import psycopg

import query_claims as qc

#: DDL credential. Falls back to the restricted URL so a single-role setup
#: still works -- it will simply fail with "permission denied" on CREATE,
#: which is the correct and legible error for that case.
ADMIN_DATABASE_URL = os.environ.get("JOBS_ADMIN_DATABASE_URL", qc.DATABASE_URL)


def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def connect(admin=False):
    conn = psycopg.connect(ADMIN_DATABASE_URL if admin else qc.DATABASE_URL)
    conn.execute("SET search_path TO jobs, public")
    return conn


def cmd_init_schema(args):
    """Create the schema. Run once at deploy time, and after any DDL change.

    Separated from the service so that the service can run without CREATE
    rights -- see this module's docstring.
    """
    with connect(admin=True) as conn:
        qc.ensure_schema(conn)
        present = [
            t for t in qc.REQUIRED_TABLES
            if conn.execute("SELECT to_regclass(%s)", (f"jobs.{t}",)).fetchone()[0]
        ]
    print(f"schema ready: {len(present)}/{len(qc.REQUIRED_TABLES)} tables present")
    for t in qc.REQUIRED_TABLES:
        print(f"  {'ok     ' if t in present else 'MISSING'}  jobs.{t}")
    if len(present) != len(qc.REQUIRED_TABLES):
        sys.exit(1)


def cmd_create(args):
    with connect() as conn:
        contributor_id = f"c_{secrets.token_hex(6)}"
        # token_urlsafe(32) -> ~43 chars, 256 bits of entropy. Long enough that
        # online guessing is hopeless, and the server only ever compares hashes.
        raw_key = secrets.token_urlsafe(32)
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

        conn.execute(
            "INSERT INTO contributors (id, name, created_at, notes) VALUES (%s, %s, %s, %s)",
            (contributor_id, args.name, utc_now(), args.notes),
        )
        conn.execute(
            """
            INSERT INTO api_keys (key_hash, contributor_id, label, created_at, revoked_at)
            VALUES (%s, %s, %s, %s, NULL)
            """,
            (key_hash, contributor_id, args.label, utc_now()),
        )
        conn.commit()

    print(f"contributor_id : {contributor_id}")
    print(f"name           : {args.name}")
    print(f"key_hash       : {key_hash}")
    print()
    print("API KEY (shown once, not recoverable -- send this to the contributor):")
    print(f"  {raw_key}")


def cmd_list(args):
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT c.id, c.name, k.key_hash, k.label, k.created_at, k.revoked_at
            FROM contributors c
            LEFT JOIN api_keys k ON k.contributor_id = c.id
            ORDER BY c.created_at, k.created_at
            """
        ).fetchall()

    if not rows:
        print("no contributors yet")
        return
    for cid, name, key_hash, label, created, revoked in rows:
        status = f"REVOKED {revoked}" if revoked else "active"
        kh = (key_hash or "")[:12]
        print(f"{cid}  {name:<20}  {kh:<12}  {label or '-':<16}  {created}  [{status}]")


def cmd_revoke(args):
    with connect() as conn:
        rows = conn.execute(
            "SELECT key_hash, contributor_id, revoked_at FROM api_keys WHERE key_hash LIKE %s",
            (args.key_hash + "%",),
        ).fetchall()

        if not rows:
            print(f"no key matching prefix {args.key_hash!r}", file=sys.stderr)
            sys.exit(1)
        if len(rows) > 1:
            # Refuse rather than guess -- revoking the wrong contributor's key
            # silently breaks their worker with no obvious cause.
            print(f"prefix {args.key_hash!r} matches {len(rows)} keys; be more specific",
                  file=sys.stderr)
            sys.exit(1)

        key_hash, contributor_id, already = rows[0]
        if already:
            print(f"already revoked at {already}")
            return
        conn.execute(
            "UPDATE api_keys SET revoked_at = %s WHERE key_hash = %s", (utc_now(), key_hash)
        )
        conn.commit()
    print(f"revoked {key_hash[:12]} (contributor {contributor_id})")


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    sub = p.add_subparsers(dest="cmd", required=True)

    i = sub.add_parser("init-schema",
                       help="create/extend the schema (needs JOBS_ADMIN_DATABASE_URL)")
    i.set_defaults(func=cmd_init_schema)

    c = sub.add_parser("create", help="create a contributor + API key")
    c.add_argument("--name", required=True)
    c.add_argument("--label", default=None, help="which machine this key is for")
    c.add_argument("--notes", default=None)
    c.set_defaults(func=cmd_create)

    l = sub.add_parser("list", help="list contributors and keys")
    l.set_defaults(func=cmd_list)

    r = sub.add_parser("revoke", help="revoke an API key by key_hash prefix")
    r.add_argument("--key-hash", required=True, dest="key_hash")
    r.set_defaults(func=cmd_revoke)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
