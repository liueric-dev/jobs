---
kind: decision
written: 2026-08-03
generator: none
---

# 0004 — `provision-database.py` creates objects and issues no privileges

**Status:** accepted, 2026-08-03. Landed as `T-19`.

## Context

Until 2026-08-03 nothing in this repo could stand a database up from nothing, and nobody had
noticed, because the one machine that mattered had a `public` schema built by hand over several
months. The DDL was spread across five functions in four modules — `ensure_schema`,
`ensure_search_query_schema` and `ensure_app_view` in `backend/schema.py`, `ensure_schema` in
`backend/evals/labels.py`, and `ensure_schema` in `backend/webapp/schema_web.py` — and nothing
invoked all five. `manage_app_users.py init-schema` calls one, which is why an empty database
reports 23 objects missing and the command its own error message suggests fixes five of them.

CI's first run found it. `backend/tools/provision-database.py` now calls all five in the one order
that works, and CI runs it before the suites.

That raised a second question with a real answer: should it also issue GRANTs? A deployment has
three Postgres roles — `jobs`, `jobs_web`, `jobs_api` — each deliberately narrow, and the webapp's
`verify_schema()` fails at startup when a privilege is missing. `OQ-7` is the recorded instance of
that class costing a day of the whole webapp being down while the row read as a nicety.

## Decision

**Create every object. Issue no privileges.**

`verify_schema()` checks `has_table_privilege(current_user, ...)`, so on a database whose owner is
the connecting role — CI, or a laptop — the privileges are satisfied by ownership and there is
nothing to issue. That is why CI is green without them. A real deployment's three roles stay a
by-hand step, documented under "Database privileges" in `backend/webapp/README.md`, issued once, as
owner.

The reasoning is at `backend/tools/provision-database.py:21-30`: **a tool that hands out privileges
is a different kind of tool, and getting it subtly wrong is worse than not having it.** A
provisioning script that over-grants is a security defect that no test will catch, because every
test passes when the roles can do too much.

## Consequences

- Standing up a *deployment* is two steps, not one, and only the first is automated. That is
  intentional and `backend/webapp/README.md` is the second step.
- **The script carries one hazard, in a banner at the top of the file.** Step 3 is
  `schema.ensure_app_view()`, whose fallback DROPs the view on a column reorder and takes every
  GRANT with it, with no re-grant anywhere in this repo (`backend/schema.py:1215-1223`). Unreachable
  on an empty database; real against a populated deployment. `--verify-only` exists for that and
  changes nothing. `T-13` in [`../../TASKS.md`](../../TASKS.md) is the fix.
- If a privilege-granting tool is ever wanted, it is a separate script with its own review, not a
  flag on this one.
- The finding is worth more than the fix and `T-19` keeps it above the fix in `../../TASKS.md`:
  every green webapp suite before 2026-08-03 rested on a schema no other machine could reproduce.
