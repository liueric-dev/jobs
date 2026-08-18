---
kind: index
generator: tools/index.py
---

# backend/tools/

**Measurement and one-off investigation. Nothing here runs as part of the nightly
pipeline** -- `run-daily.py`'s 14 steps touch none of it. Each entry below is the
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
| [`ats-discover.py`](ats-discover.py) | Find which NYC employers run which ATS, and confirm every token against the live feed before believing it. |
| [`audit-citations.py`](audit-citations.py) | Do the repo's `file:line` citations still point at anything? |
| [`audit-description-markup.py`](audit-description-markup.py) | Sweep extract.py's input-sanity gate over the whole jobs table, and clean up after it. |
| [`audit-doc-links.py`](audit-doc-links.py) | Resolve every relative Markdown link under docs/ and report the broken ones. |
| [`audit-docs.py`](audit-docs.py) | Check this repo's mechanically-checkable documentation rules and exit non-zero. |
| [`calibrate-match.py`](calibrate-match.py) | Is the free rules ranking good enough to gate the paid narrative tier? |
| [`claude-bench.py`](claude-bench.py) | Benchmark the Claude Code CLI as a scoring backend before committing to it. |
| [`claude-ceiling-test.py`](claude-ceiling-test.py) | Batch ceiling + token budget experiment for the Claude scoring backend. |
| [`compare-extract.py`](compare-extract.py) | Does disabling reasoning change the FACTS, or only the bill? |
| [`compare-models.py`](compare-models.py) | Compare scoring models against the same jobs, before switching the default. |
| [`cost-test.py`](cost-test.py) | Measure what a scoring run actually SPENDS -- in requests, seconds and concurrency. Dollars are reported last, because they stopped being the constraint. |
| [`derive-role-tracks.py`](derive-role-tracks.py) | Derive the `role_track` vocabulary and validate archetype candidates from the corpus. |
| [`dismiss-reasons.py`](dismiss-reasons.py) | What the cohort's dismissals say about `config/pursuit-criteria.json`. |
| [`hydrate-labelled-corpus.py`](hydrate-labelled-corpus.py) | Hydrate the labelled postings of a label set into a corpus fixture. |
| [`jsonld-probe.py`](jsonld-probe.py) | Measure whether task 19 (the JSON-LD parser) is worth building. |
| [`label-findings.py`](label-findings.py) | Re-derive the findings a labelling sitting produces, from `eval_labels`. |
| [`learned-ranker-probe.py`](learned-ranker-probe.py) | Is the ranking ceiling the FEATURES or the hand-tuned WEIGHTS? |
| [`mock-acceptance.py`](mock-acceptance.py) | Run the real pipeline over 55 constructed postings and compare it to an answer key. |
| [`provision-database.py`](provision-database.py) | Create every database object this project's three processes require. |
| [`relevance-report.py`](relevance-report.py) | Show what config/relevance.json actually does to the current table. |
| [`score-ledger.py`](score-ledger.py) | What did the weights actually DO to the list a user sees? |
| [`verify-date-filter.py`](verify-date-filter.py) | Does `chips=date_posted:` still filter anything? Costs ~3 SerpApi credits. |
| [`volume-check.py`](volume-check.py) | The soft-failure alarm: has any source gone quiet, and did the run happen? |

Two of these cannot run on a clean checkout or against every machine, and the
reasons are in their docstrings rather than repeated here:
`learned-ranker-probe.py` needs numpy and sklearn, which are deliberately in no
`requirements.txt`, and `provision-database.py` has a banner to read before it is
pointed at a populated database.
