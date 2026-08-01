---
kind: record
written: 2026-08-01
generator: none
---

# The tree state at handoff, and how it was attributed

> **Archived from `docs/tasks/refactor/HANDOFF.md` on 2026-08-01**, by task 44, for the same
> reason as [`handoff-state-2026-07-31.md`](handoff-state-2026-07-31.md): the file carried a
> frozen session narrative underneath a `rolling` entry point.
>
> **What it is:** § *Nothing is in flight — but the tree is NOT clean*, recorded 2026-07-29
> through 2026-07-31 — what was committed and what was only a database write, the content
> digests that proved nothing was overwritten, and two superseded live-state snapshots.
>
> **Two parts of that section did not come here.** Its FAQ, *The next session's likely first
> question, answered*, is standing guidance and stays in `HANDOFF.md`. Its four cross-stream
> lessons were promoted to [`../MEASUREMENT-TRAPS.md`](../MEASUREMENT-TRAPS.md) under rule 5,
> because they would survive this cohort, model and product changing.

## Nothing is in flight — but the tree is NOT clean


**Nothing is half-written and nothing is waiting on a reply.** Step 0 is implemented,
committed and written to the database, and so are task 29's four sampler fixes and its
drawn set; the docs were rolled forward in the same session each time. ~~The working tree
is clean apart from untracked `scripts/`, which predates this run and is not ours.~~

~~**AMENDED 2026-07-30: the working tree carries the whole solo-labelling change and NONE of
it is committed.** It is finished, not half-done — both suites are green at **1166** and
**75** — but a fresh session will find modifications, not a clean checkout:~~

```
 M backend/evals/__main__.py            M backend/webapp/manage_app_users.py
 M backend/evals/labels.py             ?? backend/webapp/tests/test_set_profile.py
 M backend/tests/test_labels.py         M docs/tasks/refactor/  (8 files)
```

~~plus `backend/webapp/.env`, which is **gitignored and will never appear in `git status`** —
and which now holds the OAuth secrets.~~ Untracked `scripts/` still predates this run and is
still not ours.

> **RE-AMENDED 2026-07-31: all of the above is COMMITTED, at `4374ede` — "Unblock task 29,
> and guard the pin before the first label closes it" — plus the four commits before it.**
> The file list above is now the *contents* of that commit rather than a description of a
> dirty tree. `git status` is clean apart from untracked `scripts/`, which still predates
> this run and is still not ours. `backend/webapp/.env` remains gitignored and still holds
> the OAuth secrets, so that half stands. Suite counts re-run 2026-07-31 and unchanged at
> the time of the commit: **1166** and **75**.

**Two database writes have no commit and cannot be inferred from the tree**, the same way
the gate write and the label tables could not: the owner's `app_users` row moved from
`tech` to `pursuit`, and ~~`eval_labels` is **still empty** — so the redraw window is open
until the first label is submitted, and~~ `redraw_refusal()` is what now closes it on
purpose rather than by memory.

> **THE REDRAW WINDOW IS CLOSED. Measured 2026-07-31: `eval_labels` holds 30 rows** — 5
> postings × 6 questions, one labeller (`u_090b0ad12e99`), round 1, `labelled_at`
> `2026-07-31T02:56:05`–`03:06:19` UTC, which is the evening of 2026-07-30 in New York and
> is **one sitting, not two**. So `pursuit-v1` is now permanently pinned: `redraw_refusal()`
> refuses every redraw, identical digest included, exactly as designed. **Nothing can be
> added to or removed from the drawn set from here on.** A third database write to add to
> the list above: the labels themselves.
>
> This also makes two things live that this file records as risks rather than facts.
> `consensus()` promoting a majority of size one is happening now, not hypothetically. And
> the per-posting timing is no longer unmeasured — see the pending follow-up below and
> `tranche_five/29-labelling-session.md` § *Findings, 2026-07-31*, E.

**The next session starts from a finished state**, and for task 29 it starts from one that
is waiting on nobody.

**What the task-29 session wrote to the database**, all of it new and none of it touching
anything that existed: the three label tables created by `evals label init-schema` as
`jobs_pipeline`, the `jobs_web` grants from `labels.WEB_PRIVILEGES`, and one registered
set — `pursuit-v1`, 200 rows in `eval_label_items`, **re-registered once when defect 4
forced a redraw**. **`eval_labels` is empty and must stay that way until people put labels
in it** — and it being empty is what made that redraw safe.

**Proof that nothing else moved.** Content digests byte-identical either side:

| table | rows | content digest |
|---|---:|---|
| `job_matches` | 3,521 | `383a9266c3b862716ff977e08491dd0e` |
| `job_scores` | 1,293 | `6960a9c3a1f39cdfbd8f8ecb838b645b` |
| `job_facts` | 5,923 | `df46e5ee2a1b63ab93d080fdbf6f5a7e` |

**These digests are computed over a DIFFERENT COLUMN SET from the ones quoted earlier in
this file** (`c98c4bbc…`, `90715a5f…`, `af8a273f…`). They are before-and-after pairs within
this session and prove nothing was overwritten *during it*; they are **not** comparable to
the older values and a difference against those means nothing. Say which columns went into
a digest, or it is a number that can only mislead the next reader.

**Six agents ran in the implementing session** — three read-only verification up front,
three writing documentation on disjoint files at the end. The orchestrator made every code edit, every measurement and
every commit itself, because the four commits were strictly sequential and each gated on
the previous one's numbers.

**One row of `profiles` was written** — `pursuit`'s `relevance_json`, by
`migrate_profiles.py --apply` with all three file flags and no `--bump`. Everything else
was a `SELECT`. Proof that nothing else moved: the `job_matches` content digest is
byte-identical before and after (`c98c4bbceed1b77d82979e83dfad70cc`, 3,521 rows), and
`md5(persona_json)` and `md5(criteria_json)` are unchanged. **Take the digest, not the
count** — a count cannot see an overwrite.

**The tree is clean.** Every agent across all six prior sessions completed, was verified
against the code and the database, and was committed — six in the session that landed
03–18, three in the session that landed 11, three in the session that landed 08/12/19,
three in the session that landed 13/35/D45, two in the session that landed the
`job_scores` version keys, five in the session that landed the mock acceptance run and
the `strip_html` fix. Nothing is half-written and nothing is waiting on a reply.
Untracked `scripts/` predates this run and is not ours.

`run-daily.py`'s `STEPS` is fully wired — `ingest/workday.py` and `ingest/nyc-open-data.py`
were added by the orchestrator, and `ats.py` was already there. **No task since 12 has
touched `STEPS`**, so the nightly run is unchanged in shape — and that is now asserted
by test rather than left to habit (`test_score_versions.py`, two tests: the score entry
verbatim, and no `--rescore-*` flag anywhere in the schedule). Four things changed
underneath it:

- the nightly `extract.py` step serves one profile with a much smaller queue (task 12);
- **it can now REJECT before calling the model** (task 35). A posting whose prompt window
  is ≥1% markup is tombstoned for zero LLM calls and counted in `unusable` on the summary
  line. If that counter starts climbing, an ingest path is capturing the wrong bytes —
  `tools/audit-description-markup.py` is the instrument;
- `match.py` now writes a real ranking instead of 863 identical scores (task 13), and
  `score.py` still writes nothing at all because `pursuit`'s `daily_narrative_budget`
  is 0;
- **`score.py` can now be told a stored narrative is out of date, and still will not
  act on it.** `job_scores` carries version keys, but the nightly step passes no
  `--rescore-*` flag and the default selection is the old existence-only anti-join.
  A persona edit or a prompt bump changes what `--stale-report` says and changes
  nothing about what the pipeline spends;
- **the bytes it stores are no longer contaminated at the source.** `lib/text.strip_html()`
  is fixed, so the `unusable` counter above should now stay at 0 for greenhouse. It is
  still the alarm and still guards the ~13,000 rows the old stripper wrote — its tests
  were re-pointed, not retired, precisely so that a future reader does not find a gate
  with no reachable trigger and remove it as dead code.

**Start here:** `cd backend && python3 -m unittest discover -s tests -t .` should report
**1070, OK**. `backend/.env` is not exported by default — scripts that reach the
database need `cd backend && (set -a; . ./.env; set +a; python3 ...)`. **The webapp is a
second environment**: `cd backend/webapp && .venv/bin/python -m unittest discover -s tests
-t .` reports **55, OK**, reads `backend/webapp/.env`, and is not covered by the 1070.

**Then read this, because it is the one thing a fresh session will get wrong:** task 13
is committed and its Definition of done is *not* met. See the top of this file. A
completed task here is not a validated one.

---

*The FAQ that sat here — § *The next session's likely first question, answered* — stayed in
`HANDOFF.md`. What follows is the remainder of the section, the two superseded live-state
snapshots.*

**Live state after the gate-fix session (2026-07-29T15:42Z, the nightly having run at
04:12).** `jobs` 14,049 (13,447 open / 602 closed), `job_facts` 5,923 (881 @v3 + 5,027
@v2 + 15 @v1), `job_matches` 3,521 (pursuit 144 / tech 3,084 / frontend 293), `job_scores`
1,293 (tech 1,110 / frontend 183, **pursuit 0**). `pursuit` is the only active profile,
`criteria_version` 2, `daily_narrative_budget` 0.

**The one write this session made** is `pursuit.relevance_json`:
`md5` `e4efd209789cbeeac201b2102fd6afb8` → **`73b110df7aea5937caabb553077632fd`**, 23 keys.
`persona_json` (`39dc8bdc…`) and `criteria_json` (`7b58380d…`) md5s are **unchanged**, and
the `job_matches` content digest is **byte-identical** either side
(`c98c4bbceed1b77d82979e83dfad70cc`, 3,521 rows). **Gate now admits 880 of 13,447 open**
— tier 1 456, tier 2 424, tier 3 12,567 — and `extract.remaining` is **13**, up from 2.
That backlog drains on the first nightly run, ~$0.004.

**Live state after the mock-acceptance / strip_html session (2026-07-29T05:40Z),
superseded by the paragraph above but kept for its attribution reasoning.**
Baseline taken before any agent started, digests re-checked after: `jobs` 14,049,
`job_facts` **5,923**, `job_matches` 3,521, `job_scores` 1,293. The only deltas this
session caused are the **−2 `job_facts`** rows remediated as markup-derived; the
`job_matches` and `job_scores` content digests (`90715a5f…`, `af8a273f…`) are
**byte-identical** before and after, which is the proof nothing was overwritten. The
mock run touched `public` not at all: 0 rows at `platform='mock'`, no `mock_all`
profile, no new scratch schemas. `scratch_5ce56323` and `scratch_cafb8b05` are still
the only orphans and still predate this run.

**Numbers below are from the previous session and are superseded by the paragraph
above**, kept because their commentary is still the reasoning:
```
job_facts  5,903 = 859 @v3 (the pursuit corpus) + 5,029 @v2 + 15 @v1
           4 v3 rows deleted by task 35's remediation -- they were markup, not postings
           extraction_passes = 1 and vote_unanimity IS NULL on every row
job_matches 3,521 = pursuit 144 @(3,2) + tech 3,084 @(2,5) + frontend 293 @(2,1)
           pursuit fell 863 -> 144 because the weights are real now, not because
           anything broke. tech lost exactly 1 row to task 35, NOT to task 13.
job_scores  1,293 = tech 1,110 + frontend 183; pursuit still has none and will not
           until daily_narrative_budget is raised above 0 -- read D16 first
           NOW CARRIES facts_version / persona_sha / prompt_version /
           criteria_version, and ALL FOUR ARE NULL ON ALL 1,293 ROWS. That is
           deliberate: unversioned is a third state, never automatically stale.
           `score.py --stale-report` reads 0 stale, 1,018 unversioned, and needs
           no API key. The BILL IS 1,018 CALLS, NOT 1,293 -- 275 rows are closed
           or never cleared MATCH_FLOOR, and no flag can reach them.
company_ats  139 never_found (was 35) + 75 valid + 5 unvalidated + 3 dead
profiles    pursuit active @criteria_version 2; tech and frontend inactive but intact
jobs        13,655 total / 13,082 open as of 2026-07-29T04:10. THE NIGHTLY RAN
           DURING THIS SESSION -- max(first_seen) 2026-07-29T04:08:38, 148 postings
           closed. job_facts and job_matches are UNCHANGED by it, so the newest
           intake is not yet extracted or ranked. Do not read that gap as damage.
```

**`job_facts` and `job_matches` above are exactly the pre-session numbers**, which is
the useful part: two agents and a nightly run moved nothing in the derived tables.
