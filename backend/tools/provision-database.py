#!/usr/bin/env python3
"""Create every database object this project's three processes require.

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

  !! ONE HAZARD, AND IT IS NOT HYPOTHETICAL. Step 3 calls
  !! schema.ensure_app_view(), whose fallback DROPs the view when a column
  !! reorder raises InvalidTableDefinition -- and DROP VIEW takes every GRANT
  !! with it, with no re-grant anywhere in this repo (schema.py:1215-1223, and
  !! T-13). On an empty database that path is unreachable. Against a populated
  !! deployment it is the one step here that can cost you something, and the
  !! symptom arrives later, as the webapp refusing to start. Run --verify-only
  !! first anywhere that matters.
"""

import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)
sys.path.insert(0, _BACKEND)

import psycopg  # noqa: E402

import schema  # noqa: E402
from evals import labels  # noqa: E402
from lib import envfile  # noqa: E402

# webapp/ is imported last and its `config` must come first within it -- that
# module performs the sys.path insert the rest of the package relies on. It is
# a plain module import rather than `manage_app_users.py init-schema` because
# that command resolves its own admin credential out of webapp/.env, which does
# not exist on a fresh checkout and is exactly the thing being provisioned.
# One block so isort leaves it alone, and `config` sorts ahead of `schema_web`
# anyway -- but the ordering here is a REQUIREMENT, not alphabetical luck. If a
# module is ever added that would sort between them, it goes in its own block
# below with this comment repeated.
sys.path.insert(0, os.path.join(_BACKEND, "webapp"))
import config as _webapp_config  # noqa: E402,F401
import schema_web  # noqa: E402

#: In order, and the order is forced: schema_web's tables reference nothing, but
#: verify_schema() checks the pipeline's alongside its own, and ensure_app_view
#: reads columns the first step creates.
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

        # The same check the webapp runs in its lifespan, so a green run here
        # means that process would start. It raises listing everything wrong
        # rather than the first thing, which is why it is printed whole.
        try:
            schema_web.verify_schema(conn)
        except RuntimeError as exc:
            print(f"\nNOT READY: {exc}", file=sys.stderr)
            return 1

    print("\nverify_schema: ready")
    return 0


if __name__ == "__main__":
    sys.exit(main())
