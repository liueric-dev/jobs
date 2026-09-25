#!/usr/bin/env python3
"""Create every database object the pipeline and webapp require.

    python3 tools/provision-database.py                 # uses DATABASE_URL
    python3 tools/provision-database.py --url ...       # or an explicit one
    python3 tools/provision-database.py --verify-only   # report, change nothing

WHY THIS EXISTS. Until 2026-08-03 nothing in this repo could stand a database
up from nothing. The DDL was spread across five functions in four modules, each
invoked from somewhere different -- `manage_app_users.py init-schema` for the
webapp's five tables, the nightly run for the pipeline's, and nothing at all for
the eval label tables outside `evals` itself. The gap was invisible because the
one machine that runs this had a `public` schema built by hand over several
months, so every suite was green against a database no other machine could
reproduce.

CI found it (T-19 in ../TASKS.md). Two webapp tests read `public.*` by hardcoded
name and pass locally only because that hand-built schema is there; on a clean
database `verify_schema()` reports all 23 objects missing.

WHAT IT DOES NOT DO: GRANTS. `verify_schema()` checks privileges with
`has_table_privilege(current_user, ...)`, so on a database whose owner is the
connecting role -- CI, or a laptop -- they are satisfied by ownership and there
is nothing to issue. A real deployment has three roles and the grants are in
`webapp/README.md` 'Database privileges', issued once, by hand, as owner. This
script deliberately does not reproduce them: a tool that hands out privileges is
a different kind of tool, and getting it subtly wrong is worse than not having
it.

  Every privilege and column this reports is therefore relative to WHICHEVER
  ROLE CONNECTED, and until T-44 that was not the one you think: a webapp/.env
  on the machine silently made it `jobs_web`, whose missing grants read back as
  missing columns (information_schema is privilege-filtered). Fixed at the
  import below. Anything a session recorded from this tool before 2026-08-08 on
  a machine with a webapp/.env is about the wrong role -- re-run it.

  !! ONE HAZARD, AND IT IS NOT HYPOTHETICAL. Step 3 calls
  !! schema.ensure_app_view(), whose fallback DROPs the view when a column
  !! reorder raises InvalidTableDefinition -- and DROP VIEW takes every GRANT
  !! with it, with no re-grant anywhere in this repo (schema.py:1215-1223, and
  !! T-13). On an empty database that path is unreachable. Against a populated
  !! deployment it is the one step here that can cost you something, and the
  !! symptom arrives later, as the webapp refusing to start. Run --verify-only
  !! first anywhere that matters.
  !!
"""

import argparse
import contextlib
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)
sys.path.insert(0, _BACKEND)

import psycopg  # noqa: E402

import schema  # noqa: E402
from evals import labels  # noqa: E402
from lib import envfile  # noqa: E402


@contextlib.contextmanager
def _database_url_unchanged():
    """Let a module be imported without letting it choose this tool's database.

    T-44. `webapp/config.py` calls envfile.load(webapp/.env) in its module body
    (webapp/config.py:40) and that file sets DATABASE_URL to `jobs_web`, a role
    holding no DDL rights. Both loads are override=False (lib/envfile.py:85),
    so whichever runs FIRST wins -- and an import at module scope always beats
    main()'s envfile.load(backend/.env) below. On every machine that has a
    webapp/.env, this tool therefore connected as `jobs_web`: a real run fails
    partway or is refused, and --verify-only reports the WRONG ROLE'S
    privileges while looking like it worked. It is the second that did damage;
    the banner tells an operator to run --verify-only first anywhere that
    matters, and on the deployed database that instruction returned an answer
    about a role that would not be doing the work. It produced at least one
    false finding that way while T-39 was being closed: information_schema is
    privilege-filtered, so a column `jobs_web` may not read reads as a column
    that is not there.

    A fresh checkout and CI have no webapp/.env, which is why the only path
    anything tested was the one that already worked.

    WHY THE FIX IS SCOPED TO THE VARIABLE rather than to the precedence, since
    two wider shapes were considered and rejected:

      * Loading backend/.env at module scope, ahead of the import, would win
        the race -- but by making backend/.env authoritative over webapp/.env
        for EVERY key the two files come to share, not just the one that is
        wrong. Today they share exactly one, DATABASE_URL (measured, not
        assumed), so the two are equivalent now and silently stop being
        equivalent the first time someone adds a second. It also fixes a side
        effect by outrunning it, which stays fixed only as long as nobody
        reorders the imports -- and the ordering here is already load-bearing
        for a different reason, three lines below.

      * Passing override=True for backend/.env would invert lib.envfile's
        documented precedence (lib/envfile.py:90-94) for this one caller and
        stop an exported DATABASE_URL from winning -- the case a one-off run
        against a second database depends on, and something this tool needs
        more than most, since pointing it somewhere other than the configured
        database is exactly how you provision a new one.

    Restoring the variable states the actual invariant -- an import does not
    get to pick the database -- leaves lib.envfile's semantics untouched for
    every other caller, and keeps the precedence `--url` > exported
    DATABASE_URL > backend/.env, with webapp/.env contributing nothing. It
    """
    before = os.environ.get("DATABASE_URL")
    try:
        yield
    finally:
        # Unset must be restored as unset, not as "" -- lib/dbconn.database_url()
        # raises a named error on an unset value and would accept an empty one.
        if before is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = before


# webapp/ is imported last and its `config` must come first within it -- that
# module performs the sys.path insert the rest of the package relies on. It is
# a plain module import rather than `manage_app_users.py init-schema` because
# that command resolves its own admin credential out of webapp/.env, which does
# not exist on a fresh checkout and is exactly the thing being provisioned.
# One block so isort leaves it alone, and `config` sorts ahead of `schema_web`
# anyway -- but the ordering here is a REQUIREMENT, not alphabetical luck. If a
# module is ever added that would sort between them, it goes in its own block
# below with this comment repeated.
#
# THE GUARD IS PART OF THE IMPORT, not decoration around it: importing `config`
# is what loads webapp/.env, and T-44 is what happens when that reaches main().
# Moving either import out of the `with` block restores the bug.
#
# These two carry no E402 any more and that is not an oversight: inside a `with`
# they are no longer top-level imports, so the rule stops applying and RUF100
# flags the directive as dead. A useful side effect -- move either back out and
# ruff asks for E402 again, which is a second, cheaper signal pointing at the
# same mistake the tests name.
sys.path.insert(0, os.path.join(_BACKEND, "webapp"))
with _database_url_unchanged():
    import config as _webapp_config  # noqa: F401
    import schema_web

#: In order: the app view reads columns the pipeline schema creates.
STEPS = [
    ("pipeline tables", schema.ensure_schema),
    ("search-query tables", schema.ensure_search_query_schema),
    ("jobs_app view", schema.ensure_app_view),
    ("eval label tables", labels.ensure_schema),
    ("webapp tables", schema_web.ensure_schema),
]


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--url", default=None,
                   help="database to provision; DATABASE_URL otherwise")
    p.add_argument("--verify-only", action="store_true",
                   help="run verify_schema() and report; issue no DDL")
    args = p.parse_args()

    # override=False on purpose, and T-44 is the reason not to "fix" it here:
    # an exported DATABASE_URL must still beat this file, because pointing the
    # tool at a database other than the configured one is how a new one gets
    # provisioned. What used to beat it was webapp/.env, and that is contained
    # at the import above rather than by inverting the rule for this caller.
    envfile.load(os.path.join(_BACKEND, ".env"))
    url = args.url or os.environ.get("DATABASE_URL")
    if not url:
        print("no database: pass --url or set DATABASE_URL", file=sys.stderr)
        return 2

    with psycopg.connect(url) as conn:
        if not args.verify_only:
            for name, fn in STEPS:
                fn(conn)
                print(f"  ok  {name}")
            conn.commit()

        # Check the privileges and columns the webapp needs at startup.
        problems = []
        for label, verify in (("webapp", schema_web.verify_schema),):
            try:
                verify(conn)
            except RuntimeError as exc:
                problems.append(f"{label}: {exc}")
        if problems:
            for problem in problems:
                print(f"\nNOT READY: {problem}", file=sys.stderr)
            return 1

    print("\nverify_schema: ready (webapp)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
