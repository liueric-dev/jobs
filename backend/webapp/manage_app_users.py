#!/usr/bin/env python3
"""
Admin CLI for the application's user allowlist.

RUN LOCALLY ONLY -- never exposed over HTTP. It talks straight to Postgres, so
it must only run on the server itself (or over a trusted tunnel), unlike app.py
which is the browser-facing surface.

    python3 manage_app_users.py init-schema                     # once, admin credential
    python3 manage_app_users.py add --email you@x.com --profile tech --admin
    python3 manage_app_users.py add --email them@x.com --profile pursuit \
        --prior-domain healthcare
    python3 manage_app_users.py set-profile --email you@x.com --profile pursuit
    python3 manage_app_users.py list
    python3 manage_app_users.py disable --email you@x.com
    python3 manage_app_users.py sessions --email you@x.com
    python3 manage_app_users.py revoke-sessions --email you@x.com

THIS FILE IS THE ACCESS CONTROL. Google authenticates; it does not authorise.
A Google login for an address with no row here is refused, and no row is ever
created by the login path -- see auth.py. That is deliberate and it is not an
oversight to "fix" by auto-provisioning: an active profile costs real money.

    CORRECTED 2026-07-31. This paragraph used to read "because extract.py and
    score.py both fan out per active profile." That is true of score.py and
    FALSE of extract.py, and the difference decides whether per-Builder
    profiles are affordable at all.

    score.py loops `for prof in targets` and issues LLM calls inside it, so its
    cost really is per profile. extract.py does not loop over profiles anywhere:
    it builds ONE cfgs list and hands it to _eligible_sql -> relevance.union_sql,
    which is an OR across every active gate ("does this row clear the bar for
    ANY profile?"). Facts are extracted once per POSTING and shared -- extract.py's
    own module docstring calls the stage "flat in the number of users".

    So adding an active profile cannot multiply extraction calls. It can only
    add the postings its gate admits that no other active gate already does. For
    N profiles sharing one gate that delta is exactly zero. The real per-profile
    cost is score.py, and `pursuit` currently has daily_narrative_budget = 0.

--prior-domain IS FOR MEASUREMENT, NOT FOR SCORING. Nothing reads it yet. It
records which industry a Builder is changing career from so that Axis B
labelling disagreement can be decomposed rather than read as noise; see
schema_web.PRIOR_DOMAINS for the whole argument and for why 'none' and an
omitted flag are different answers.

TWO CREDENTIALS: `init-schema` is the only command that issues DDL and the only
one that reads JOBS_ADMIN_DATABASE_URL. Everything else runs on the same
restricted DATABASE_URL the service itself uses, because add/list/disable need
nothing beyond grants that role already holds. Keeping schema creation in a
separate, explicitly-invoked command is what lets the long-running process hold
no schema-modification rights at all.
"""

import argparse
import secrets
import sys

import config  # noqa: F401  (must come first -- performs the sys.path insert)

import psycopg

import profiles
import schema_web
from lib.timeparse import utc_now_str


def connect(admin=False):
    url = config.admin_database_url() if admin else config.database_url()
    conn = psycopg.connect(url)
    conn.execute("SET search_path TO public")
    return conn


def cmd_init_schema(args):
    with connect(admin=True) as conn:
        schema_web.ensure_schema(conn)
        present = [
            t for t in schema_web.REQUIRED_TABLES
            if conn.execute("SELECT to_regclass(%s)", (f"public.{t}",)).fetchone()[0]
        ]
    total = len(schema_web.REQUIRED_TABLES)
    print(f"schema ready: {len(present)}/{total} tables present")
    for t in schema_web.REQUIRED_TABLES:
        print(f"  {'ok     ' if t in present else 'MISSING'}  public.{t}")
    if len(present) != total:
        sys.exit(1)
    print()
    print("Grants for the service role are in README.md 'Database privileges'.")
    print("This command does NOT issue them -- run them once, by hand, as owner.")


def cmd_add(args):
    email = args.email.strip().lower()
    with connect() as conn:
        # The substitute for the foreign key that deliberately isn't there.
        # load_one() returns paused profiles too, which is correct here: an
        # operator may well seed a user against a profile they have not
        # activated yet.
        if profiles.load_one(conn, args.profile) is None:
            known = [p.profile for p in profiles.load_active(conn)]
            print(f"no such profile: {args.profile!r}. active profiles: "
                  f"{', '.join(known) or '(none)'}", file=sys.stderr)
            sys.exit(1)

        existing = conn.execute(
            "SELECT id FROM app_users WHERE email = %s", (email,)).fetchone()
        if existing:
            print(f"{email} already exists ({existing[0]}); use enable/disable "
                  f"to change access", file=sys.stderr)
            sys.exit(1)

        user_id = f"u_{secrets.token_hex(6)}"
        conn.execute(
            """
            INSERT INTO app_users (id, email, google_sub, display_name, profile,
                prior_domain, is_admin, active, created_at, last_login_at)
            VALUES (%s, %s, NULL, %s, %s, %s, %s, TRUE, %s, NULL)
            """,
            (user_id, email, args.name, args.profile, args.prior_domain,
             args.admin, utc_now_str()),
        )
        conn.commit()

    print(f"id       : {user_id}")
    print(f"email    : {email}")
    print(f"profile  : {args.profile}")
    print(f"domain   : {args.prior_domain or '(not asked)'}")
    print(f"admin    : {args.admin}")
    print()
    print("google_sub is bound on their first successful login. Until then the")
    print("row is matched by email; afterwards by sub, so an email change is")
    print("harmless and a recycled address cannot inherit this account.")


def cmd_set_profile(args):
    """Move an existing user to a different profile.

    THE COMMAND THAT MAKES app_users.profile CORRECTABLE. `add` is the only
    other writer of that column and `email` is UNIQUE, so re-running `add`
    against an existing address is refused rather than being an update. Without
    this subcommand the only remaining path is an UPDATE typed by hand, which
    README.md tells operators not to do -- and which skips the profile check
    below, the one thing standing in for the foreign key that is deliberately
    absent (schema_web.py:119-125).

    SESSIONS ARE NOT REVOKED, ON PURPOSE. require_user re-joins app_users on
    every request and reads u.profile out of that join (auth.py:96-104,128-129);
    app_sessions stores no copy of the profile (schema_web.py:127-138). The next
    request therefore already sees the new value, and revoking would log someone
    out to achieve nothing. Same reasoning as `disable` taking effect on the
    next request rather than the next login.
    """
    email = args.email.strip().lower()
    with connect() as conn:
        # The same check `add` makes, and for the same reason: no foreign key.
        # load_one() returns paused profiles too, which is again correct -- an
        # operator may well move a user onto a profile they have not activated
        # yet, so an inactive target warns below instead of failing.
        target = profiles.load_one(conn, args.profile)
        if target is None:
            known = [p.profile for p in profiles.load_active(conn)]
            print(f"no such profile: {args.profile!r}. active profiles: "
                  f"{', '.join(known) or '(none)'}", file=sys.stderr)
            sys.exit(1)

        row = conn.execute(
            "SELECT id, profile, prior_domain FROM app_users WHERE email = %s",
            (email,)).fetchone()
        if row is None:
            print(f"no user with email {email!r}; use add to create them",
                  file=sys.stderr)
            sys.exit(1)
        user_id, before, domain_before = row

        conn.execute("UPDATE app_users SET profile = %s WHERE id = %s",
                     (args.profile, user_id))
        # OMITTING --prior-domain LEAVES IT ALONE; it does not clear it. This
        # subcommand's job is the profile, and a flag that silently nulls an
        # unrelated column when you forget it would destroy the one attribute
        # the Axis B decomposition depends on -- and eval_labels has no UPDATE
        # grant, so the labels already recorded against it could not be re-keyed.
        if args.prior_domain is not None:
            conn.execute("UPDATE app_users SET prior_domain = %s WHERE id = %s",
                         (args.prior_domain, user_id))
        conn.commit()

    print(f"id       : {user_id}")
    print(f"email    : {email}")
    print(f"profile  : {before} -> {args.profile}")
    if args.prior_domain is not None:
        print(f"domain   : {domain_before or '(not asked)'} -> {args.prior_domain}")
    else:
        print(f"domain   : {domain_before or '(not asked)'} (unchanged)")
    if not target.active:
        # The failure this command exists to correct, so it must not be silent:
        # the first row this service ever had landed on an inactive profile and
        # nothing said so. A warning rather than an error -- see the docstring.
        print()
        print(f"WARNING: profile {args.profile!r} has active = False.")
        print("The pipeline works only for active profiles (profiles.load_active),")
        print("so nothing new is extracted, matched or scored for this user until")
        print("someone activates it. They can still log in; the list they see is")
        print("whatever rows already exist.")
    print()
    print("Takes effect on their NEXT request -- require_user re-reads "
          "app_users every time, so no session needs revoking.")


def cmd_list(args):
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT u.id, u.email, u.profile, u.is_admin, u.active,
                   u.google_sub IS NOT NULL, u.created_at, u.last_login_at,
                   (SELECT count(*) FROM app_sessions s
                     WHERE s.user_id = u.id AND s.revoked_at IS NULL
                       AND s.expires_at > %s),
                   u.prior_domain
            FROM app_users u ORDER BY u.created_at
            """,
            (utc_now_str(),),
        ).fetchall()

    if not rows:
        print("no users yet -- nobody can log in")
        return
    for uid, email, profile, is_admin, active, linked, created, last, live, domain in rows:
        flags = ",".join(f for f, on in (
            ("admin", is_admin), ("linked", linked), ("DISABLED", not active)) if on)
        print(f"{uid}  {email:<32}  {profile:<12}  {flags or '-':<20}  "
              f"domain={domain or '-':<15}  "
              f"sessions={live}  created={created}  last_login={last or '-'}")


def _set_active(email, active):
    email = email.strip().lower()
    with connect() as conn:
        row = conn.execute(
            "UPDATE app_users SET active = %s WHERE email = %s RETURNING id",
            (active, email)).fetchone()
        if row is None:
            print(f"no user with email {email!r}", file=sys.stderr)
            sys.exit(1)
        conn.commit()
    print(f"{email}: active={active}")
    if not active:
        print("Existing sessions are refused on their NEXT request -- "
              "require_user re-reads app_users every time.")


def cmd_disable(args):
    _set_active(args.email, False)


def cmd_enable(args):
    _set_active(args.email, True)


def cmd_sessions(args):
    with connect() as conn:
        sql = """
            SELECT u.email, s.token_hash, s.created_at, s.expires_at,
                   s.last_seen_at, s.revoked_at, s.ip, s.user_agent
            FROM app_sessions s JOIN app_users u ON u.id = s.user_id
        """
        params = ()
        if args.email:
            sql += " WHERE u.email = %s"
            params = (args.email.strip().lower(),)
        rows = conn.execute(sql + " ORDER BY s.created_at DESC", params).fetchall()

    if not rows:
        print("no sessions")
        return
    for email, th, created, expires, seen, revoked, ip, ua in rows:
        state = "revoked" if revoked else "active"
        print(f"{email:<32}  {th[:12]}  {state:<8}  created={created}  "
              f"expires={expires}  seen={seen or '-'}  ip={ip or '-'}")
        if args.verbose:
            print(f"    ua: {ua or '-'}")


def cmd_revoke_sessions(args):
    """The break-glass path for a stolen cookie, and the reason sessions are
    opaque database rows rather than signed tokens: revocation is one UPDATE,
    not a key rotation that logs everyone out."""
    email = args.email.strip().lower()
    with connect() as conn:
        rows = conn.execute(
            """
            UPDATE app_sessions SET revoked_at = %s
            WHERE revoked_at IS NULL
              AND user_id = (SELECT id FROM app_users WHERE email = %s)
            RETURNING token_hash
            """,
            (utc_now_str(), email),
        ).fetchall()
        conn.commit()
    print(f"revoked {len(rows)} session(s) for {email}")


def build_parser():
    """The argument parser, separated from main() so a test can read it.

    Split out when --prior-domain landed: its `choices` come from
    schema_web.PRIOR_DOMAINS, and "the CLI and the CHECK constraint offer the
    same vocabulary" is a property worth asserting rather than assuming. There
    is no way to assert it while the parser only exists inside main().
    """
    p = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    sub = p.add_subparsers(dest="cmd", required=True)

    i = sub.add_parser("init-schema",
                       help="create this service's tables (needs JOBS_ADMIN_DATABASE_URL)")
    i.set_defaults(func=cmd_init_schema)

    # choices= comes from schema_web.PRIOR_DOMAINS, which also generates the
    # CHECK constraint, so argparse and the database cannot disagree about the
    # vocabulary. Not required: NULL means "nobody asked", which is a different
    # answer from 'none' and must stay reachable by simply not passing the flag.
    domain_help = ("industry they are changing career FROM; omit if not asked. "
                   "'none' means genuinely early-career, which is NOT the same "
                   "as omitting it")

    a = sub.add_parser("add", help="allow an email to log in")
    a.add_argument("--email", required=True)
    a.add_argument("--profile", required=True, help="which pipeline profile they see")
    a.add_argument("--name", default=None, dest="name")
    a.add_argument("--prior-domain", default=None, dest="prior_domain",
                   choices=schema_web.PRIOR_DOMAINS, help=domain_help)
    a.add_argument("--admin", action="store_true")
    a.set_defaults(func=cmd_add)

    sp = sub.add_parser("set-profile",
                        help="move an existing user to a different profile")
    sp.add_argument("--email", required=True)
    sp.add_argument("--profile", required=True, help="which pipeline profile they see")
    sp.add_argument("--prior-domain", default=None, dest="prior_domain",
                    choices=schema_web.PRIOR_DOMAINS,
                    help=domain_help + ". Omitting it leaves the stored value alone")
    sp.set_defaults(func=cmd_set_profile)

    l = sub.add_parser("list", help="list users")
    l.set_defaults(func=cmd_list)

    d = sub.add_parser("disable", help="refuse this user from the next request on")
    d.add_argument("--email", required=True)
    d.set_defaults(func=cmd_disable)

    e = sub.add_parser("enable", help="undo disable")
    e.add_argument("--email", required=True)
    e.set_defaults(func=cmd_enable)

    s = sub.add_parser("sessions", help="list sessions")
    s.add_argument("--email", default=None)
    s.add_argument("-v", "--verbose", action="store_true")
    s.set_defaults(func=cmd_sessions)

    r = sub.add_parser("revoke-sessions", help="log a user out everywhere")
    r.add_argument("--email", required=True)
    r.set_defaults(func=cmd_revoke_sessions)

    return p


def main():
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
