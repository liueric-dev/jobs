---
kind: index
generator: tools/index.py
---

# backend/tools/

**Operational tools and one-off investigation.** `run-daily.py` invokes
`ats-discover.py --nightly --known-only`; the other tools are operator-run. Each entry below is the
first line of that file's own docstring; open the file for the full one, which is
where the caveats live (what it costs, what it writes, what it must not be trusted
for).

**This file is generated.** `python3 tools/index.py --write` rebuilds it and
`tests/test_tools_index.py` fails when it is out of date. To change a line here,
change the docstring in the tool.

Everything resolves relative to `backend/`, so `cd backend` first. Every tool here
takes command-line options; run one with `--help` for its own.

| tool | what it answers |
|---|---|
| [`ats-discover.py`](ats-discover.py) | Discover and validate employer ATS boards. |
| [`provision-database.py`](provision-database.py) | Create or verify the ingestion database schema. |
| [`volume-check.py`](volume-check.py) | The soft-failure alarm: has any source gone quiet, and did the run happen? |

`provision-database.py` changes schema. Check its target URL before running it.
