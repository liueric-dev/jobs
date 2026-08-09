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
    python3 manage_users.py settings --contributor c_ab12 --paused
    python3 manage_users.py settings --contributor c_ab12 --active \
                                     --daily-cap 8 --reserve-floor 2

KEY HANDLING: the raw key is printed exactly once, at creation, and is never
stored anywhere -- only sha256(key) goes into the database. There is
deliberately no "show me Dave's key again" command: if a key is lost, revoke
it and mint a new one. That way a database dump (or this script's output being
piped somewhere) never yields working credentials.

TWO CREDENTIALS: `init-schema` issues DDL and `settings` writes policy, and
those two are the ones that use JOBS_ADMIN_DATABASE_URL. Everything else runs
on the same restricted DATABASE_URL the API itself uses, because
create/list/revoke need nothing beyond the INSERT/SELECT/UPDATE grants that role
already holds. Keeping schema creation in a separate, explicitly-invoked command
is what lets the long-running service hold no schema-modification rights at all;
keeping `settings` there is what stops the internet-facing role from being able
to rewrite the policy that governs it -- see cmd_settings().
"""

import os
import sys
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
    conn.execute("SET search_path TO public")
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
            if conn.execute("SELECT to_regclass(%s)", (f"public.{t}",)).fetchone()[0]
        ]
    print(f"schema ready: {len(present)}/{len(qc.REQUIRED_TABLES)} tables present")
    for t in qc.REQUIRED_TABLES:
        print(f"  {'ok     ' if t in present else 'MISSING'}  public.{t}")
    if len(present) != len(qc.REQUIRED_TABLES):
        sys.exit(1)


def cmd_create(args):
    """The manual fallback, per docs/adr/0006. Still here, still not the
    primary path -- 0007 decision 1 makes the webapp's opt-in the way a Builder
    normally gets one, and this is what the operator runs when that is not
    available or when the contributor is not a Builder at all.

    THE MINT MOVED, THE BEHAVIOUR DID NOT. qc.mint_credential() is now the one
    implementation, shared with app.py's mint route, so there is a single place
    that decides a key is `token_urlsafe(32)` and that only its sha256 is
    stored. This command passes no contributor_id, so it always creates a new
    contributor rather than re-keying one -- which is exactly what it did
    before.
    """
    with connect() as conn:
        contributor_id, raw_key, key_hash, _ = qc.mint_credential(
            conn, args.name, label=args.label, notes=args.notes)
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


def cmd_settings(args):
    """Set (or clear) one contributor's desired state -- docs/adr/0007 dec. 3.

    ON THE ADMIN CREDENTIAL, WHICH IS THE THIRD COMMAND TO NEED ONE AND THE
    FIRST THAT ISSUES NO DDL. `jobs_api` holds SELECT and INSERT on
    `contributors` and deliberately not UPDATE, and this command is the reason
    to keep it that way rather than the reason to widen it: these three columns
    are the operator's policy over a contributor's machine, and the role that
    faces those machines must not be able to rewrite them. A compromised app.py
    that could un-pause a contributor and raise their own cap would make the
    control layer 0007 decision 3 exists to build enforceable only against a
    process that was not compromised, which is not enforcement.

    So the module docstring's "TWO CREDENTIALS" split now reads: the admin URL
    is DDL AND policy; the restricted URL is everything the running service
    could do anyway.

    UNPASSED IS UNTOUCHED, `--clear` IS BACK TO THE DEFAULT. Three settings on
    one row means the obvious implementation writes all three every time, so
    `settings --paused` would silently reset a cap somebody set last week. Only
    the flags actually given are in the UPDATE. Clearing to NULL is spelled out
    rather than done with a sentinel value, because 0 is a meaningful cap (spend
    nothing) and would otherwise be unreachable.
    """
    updates = {}
    if args.paused is not None:
        updates["paused"] = args.paused
    for name in ("daily_cap", "reserve_floor"):
        value = getattr(args, name)
        if value is not None:
            updates[name] = None if value == "clear" else int(value)
    if not updates:
        print("nothing to set; pass at least one of --paused/--active, "
              "--daily-cap, --reserve-floor", file=sys.stderr)
        sys.exit(1)

    # Every spliced name is a key this function put there itself, from the
    # literal tuple above and args.paused -- never a value off the command line.
    # See .claude/rules/sql.md on why identifier splicing is constants-only.
    assignments = ", ".join(f"{name} = %s" for name in updates)
    with connect(admin=True) as conn:
        changed = conn.execute(
            f"UPDATE contributors SET {assignments} WHERE id = %s",  # noqa: S608
            (*updates.values(), args.contributor),
        ).rowcount
        conn.commit()

    if not changed:
        print(f"no contributor with id {args.contributor!r}", file=sys.stderr)
        sys.exit(1)

    with connect(admin=True) as conn:
        row = conn.execute(
            "SELECT paused, daily_cap, reserve_floor FROM contributors WHERE id = %s",
            (args.contributor,),
        ).fetchone()
    paused, cap, floor = row
    print(f"{args.contributor}  paused={bool(paused)}  "
          f"daily_cap={'default' if cap is None else cap}  "
          f"reserve_floor={0 if floor is None else floor}")


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

    s = sub.add_parser("settings", help="set a contributor's pause/cap/reserve")
    s.add_argument("--contributor", required=True, help="contributor_id")
    # One destination, two flags, so neither "--paused false" nor a bare
    # "--paused" that means the opposite of what it reads is possible.
    s.add_argument("--paused", dest="paused", action="store_const", const=True,
                   default=None, help="stop granting this contributor queries")
    s.add_argument("--active", dest="paused", action="store_const", const=False,
                   help="resume granting queries")
    s.add_argument("--daily-cap", dest="daily_cap", default=None,
                   help="queries per day, or 'clear' for the service default")
    s.add_argument("--reserve-floor", dest="reserve_floor", default=None,
                   help="SerpApi credits to keep unspent -- claiming stops when "
                        "the balance this contributor reports would drop below "
                        "it -- or 'clear' for 0")
    s.set_defaults(func=cmd_settings)

    r = sub.add_parser("revoke", help="revoke an API key by key_hash prefix")
    r.add_argument("--key-hash", required=True, dest="key_hash")
    r.set_defaults(func=cmd_revoke)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
