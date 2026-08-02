---
kind: rolling
written: 2026-08-02
generator: none
subject: .
budget: 120
---

# Open questions — the `docs/tasks/refactor/` run

**This register owns the prefix `OQ-`.** One allocator, declared here, per
[`../../DOCS-POLICY.md`](../../DOCS-POLICY.md) rule 6 — the same discipline
[`../../ingest/DEFECTS.md`](../../ingest/DEFECTS.md) applies to `D` and
[`DECISIONS.md`](DECISIONS.md) to `DEC`. **The next free number is `OQ-9`.**

**Split out of `HANDOFF.md` on 2026-08-02 by [task 47](tranche_eight/47-split-the-entry-point.md).**
It had been a table inside a document rewritten every session, so the questions were cited by
*row position* — `tranche_six/32-frontend.md:13` says *"open question 1"* and `:280` says
*"open question 7"* — while the rows themselves already read 1, 2, 3, ~~7~~, 8, 4, 5, 6.
**The numbers below are the ones those citations mean and are deliberately not renumbered**;
read `OQ-<n>` and the table's `#` column as the same identifier.

**Every row here is the owner's. None is a session's.** Each names the document that owns the
full argument; this file is an index and deliberately does not restate the reasoning (rule 2).
The recommendations a session wrote against five of them are in
[`sessions/2026-08-02-four-streams-and-the-five-decisions.md`](sessions/2026-08-02-four-streams-and-the-five-decisions.md)
— **recommendations, not decisions taken**, and moving a question is not answering it.

*Assembled 2026-08-02 because they were scattered across this file and three others, and the
next session is going to work through them first. Each row names the document that owns the
full argument; this table is an index and deliberately does not restate the reasoning.*

| # | question | owns it | if you do nothing |
|---|---|---|---|
| 1 | **Who issues a contributor credential?** Grant `jobs_web` INSERT on `jobs_api`'s tables / a server-to-server mint / a request queue the owner services by hand | `DEC-84`, [`24`](tranche_four/24-revive-contributor-api.md) | 24's *"a Builder onboards without the author"* cannot be met, and the page stays unbuilt. **This is a product call about how long `backend/api/` is expected to live** |
| 2 | ~~**Is the impression dedup key `(profile, job_id)` or `(profile, job_id, request_id)`?** One line of code; it changes the documented meaning of *"a list re-render is not new information"*~~ **THIS ROW ASKED THE WRONG QUESTION — see § *A session's read on the five decisions* below. The binding axis is `app_user_id`, not `request_id`, and a third option neither this row nor the source documents offer is almost certainly the answer** | [`27`](tranche_five/27-event-schema.md), [`API-CONTRACT-v1.md`](API-CONTRACT-v1.md), [`engagement-events.md`](../../ingest/engagement-events.md), and `webapp/jobs.py:934-937` which is the code | ~~skips stay a first-render-per-day signal~~ **understated by a wide margin: the key holds no `app_user_id`, thirty Builders share `pursuit`, so the FIRST Builder to load the list suppresses every other Builder's impression of those postings for the window. Skips are derived from impressions, so they inherit it** |
| 3 | **More labellers on the SAME ten overlap rows**, and round 2 (~2026-08-09) | [`AUDIT.md`](AUDIT.md) § *What is open*, [`labelling-report-2026-08-02.md`](../../labelling-report-2026-08-02.md) | tasks **30**, 13's weights and 12's next bump stay gated. More *postings* do nothing — 25 of 36 carry one labeller and add zero to the ceiling. **Task 30's data half is now unblocked and its label half is not**, so this row is the whole remaining blocker there |
| ~~7~~ | ~~**The live database is missing task 25's five search objects and `cohort_signal`'s GRANT.**~~ **CLOSED 2026-08-02.** `init-schema` created the five search objects and `builder_profiles`; the seven GRANTs were issued by hand from README § *Database privileges*, as that command's own output says it does not issue them. `verify_schema()` returns clean and the service boots | [`33`](tranche_six/33-deployment.md), `backend/webapp/schema_web.py` | ~~the search screen cannot be exercised end to end~~ **— and the row understated it. Measured by starting the service: `verify_schema()` raised in `app.py`'s lifespan and the process EXITED, so nothing on the webapp ran at all, not the search screen alone.** Now serving: `/v1/health` answers and the page renders. **The lesson worth keeping is that this row read as a nicety for a day while the whole app was down**, because nobody had started it — the same silence-is-the-failure-mode shape the runbook opens with, one layer up |
| 8 | **Name the tracks, or decide the grouping ships with the vocabulary it has** | `config/pursuit-persona.json`'s `_no_buckets_comment`, [`30`](tranche_six/30-within-track-ordering.md) | grouping works and its headings use `extract.ROLE_TRACK`'s nine slugs with hand-written plain-language copy. The persona config records that `score.TRACKS`' five names "do not describe this population" and makes naming task 30's — **building the mechanism was ungated; choosing the names is not** |
| 4 | **The machine half of 33** — Cloudflare account and `cloudflared login`, the OAuth redirect URI, `systemctl --user enable`, an off-machine backup destination, and **the one verified restore** | [`33`](tranche_six/33-deployment.md) § the command list, [`RUNBOOK.md`](../../RUNBOOK.md) | nothing is reachable by a Builder, and **there is no proven backup** — the script and its verify timer are written and have never run |
| 5 | **Apply the `revenue_commercial` archetype?** Proposed and deliberately unapplied. **Cheaper to answer than it was on 2026-08-02**: labels written from that date carry the `facts_version` they were formed against (`DEC-95`), so a bump no longer silently re-denominates the agreement figures — it becomes visible as a version split in `evals label status`. Rows labelled *before* it are still unrecorded and always will be, so the bump is a one-way door for those and only those | `DEC-64`/`DEC-65`, [`11`](tranche_two/11-archetype-superset-role-track.md) | `role_archetype = other` stays where it is. It is a `FACTS_VERSION` bump and `pursuit-v1` is mid-labelling, which is why it waits |
| 6 | **`D31`** needs a decision, not a fix | [`DEFECTS.md`](../../ingest/DEFECTS.md) | stays open, correctly |


**Two of these have moved since they were written and the movement is easy to miss.** (3) is
no longer *"get a second labeller"* — that happened, the report printed, and **the ceiling
came back below the model's floor on all five fields**, so what is needed now is *overlap*,
not volume. And (4) is no longer blocked on a decision — `DEC-91` took the Cloudflare-vs-
Tailscale call and `DEC-92` took the stays-on-the-home-box call; what is left is purely
account access and a person at a terminal.
