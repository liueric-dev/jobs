---
status: draft — not reviewed, not decided, not started
written: 2026-08-04
owner decision needed: yes (see "Open questions" — this is what OQ-numbering in DEV_TASKS.md is for once this is triaged)
---

# Draft: a personal layer on top of cohort scoring — resume-tailoring via a client-side, bring-your-own-key LLM call

**This is a design exploration from a chat session, not an adopted plan.** Nothing described here has been built. Review it, cut what doesn't hold up, and if any of it survives, give the surviving piece(s) a `T-` or `OQ-` row in `TASKS.md`/`DEV_TASKS.md` the normal way — this file is not itself a task and should not be treated as one.

---

## 1. Where this came from

The existing pipeline has exactly one scoring layer: the **cohort layer**. `match_score` (free arithmetic, `match.py`) ranks every posting for the `pursuit` profile, and `job_scores` (`gap_bridging_angle`, `risk_factors`, an LLM call via `score.py`) writes one narrative per `(job_id, profile)` — shared by all ~30 Builders in the cohort. That sharing is deliberate and load-bearing: `schema.py`'s "SCORING IS TWO TIERS" comment states it explicitly, and `CLAUDE.md` names it an architecture invariant — `job_matches`/`job_scores` are keyed `(job_id, profile)`, "the property that makes cost flat in users."

The idea explored in this session: a **second, personal layer**, per-Builder rather than per-cohort, that speaks to an individual's own work history — starting with the narrowest, most concrete version of that idea: **tailoring a resume to a specific job posting** by selecting relevant bullets from a master document the Builder maintains themselves.

Two other options were discussed and explicitly set aside before landing here — recorded so a future session doesn't re-litigate them from scratch:

- **Running the existing cohort narrative client-side with a Builder's own key** — rejected. The cohort narrative is identical for every Builder (no per-Builder input feeds it today), so client-side execution would mean 30 Builders redundantly regenerating the *same* output on 30 separate keys — pure waste, and the opposite of what the `(job_id, profile)` cost-flat-in-users design already achieves. Client-side execution only makes sense where the output is genuinely different per person.
- **A structured, LLM-free personal layer using already-collected onboarding fields** (`location_pref`, `remote_pref`, `comp_floor`, `tracks`, `prior_years`, `situation` — `webapp/schema_web.py:599-631`) — **not rejected, just out of scope for this document.** These fields are captured at onboarding (`webapp/onboarding.py:427-449`) and currently read by nothing (`match.py`/`score.py`/`webapp/jobs.py` have zero references to `builder_profiles` — confirmed by grep). A free arithmetic per-Builder adjustment to `match_score` using these fields is a smaller, no-new-cost, no-privacy-change piece of "the personal layer" that could ship independently of anything in this document. Worth its own design pass.

This document is about the third option: **resume tailoring**, which does need an LLM and does need to think hard about privacy and cost, because the output is genuinely personal and genuinely expensive to fake without one.

---

## 2. The constraint that shapes everything: no resumes on the server, on purpose

`webapp/onboarding.py:37-43`, verbatim:

> "NO FILE UPLOAD, ANYWHERE, and it is a privacy decision rather than an unfinished feature. A resume upload would mean storing personal documents for thirty low-income adults on a residential home connection. A structured form yields the same matching-relevant fields without ever holding the document. If resume parsing is added later it must extract fields and discard the source, and it should wait until there is somewhere better to put it than a home server."

This is real and current: the pipeline runs on the operator's home machine — confirmed directly this session via `systemctl --user` and `docker ps` (postgres, the webapp, the contributor API, and cloudflared all run as user services / containers on the same box that also runs unrelated personal media services). A resume-tailoring feature that stores Builders' work histories server-side would be exactly the thing that docstring refuses to do, for a stated and still-valid reason.

**The proposal in this document is designed to never need that decision reversed.** If the master document lives entirely in the Builder's own browser (e.g. `localStorage`) and is sent directly from their browser to their own LLM provider using their own API key, it never reaches the pipeline's database or its host. The `NO FILE UPLOAD` constraint stays intact — nothing here uploads a file to this server. That's a different privacy posture than a resume upload (the Builder's exposure is to their chosen LLM provider, not to the operator), and it's worth being explicit that it's *still a posture with real tradeoffs* — see Open Questions — not a free pass.

---

## 3. Why this is a good fit for client-side + bring-your-own-key (unlike the cohort narrative)

The objection that killed "run the cohort narrative client-side" doesn't apply here: a tailored resume is, by construction, unique per `(Builder, job)`. There is no shared output to cache and no redundant compute to avoid — every Builder doing this client-side is doing genuinely necessary, non-duplicated work. Cost and infrastructure ownership both land on the person the output is for, which is the right place for them to land.

---

## 4. Why "tailoring" is a tractable LLM task, and how to make "no hallucination" a real guarantee rather than a prompt hope

The request was: the Builder has one large master document — every job, every bullet, every skill they've ever had — and for a given posting, the model should pick which bullets and which jobs are relevant, **never inventing content that isn't already in the master document.**

This is a *selection* task, not a *generation* task, and that distinction is what makes the no-hallucination goal achievable rather than aspirational:

- **Structure the master document into addressable units.** Each work-history entry gets a stable ID; each bullet under it gets a stable ID and (optionally) tags. Not a blob of prose — a small structured list, the same shape `score.build_prompt()` already uses for job facts (`score.py:555-585`).
- **The model's output is a selection, not prose.** It returns a list of bullet IDs to include, an ordering, and maybe a one-line "why this is relevant" per selection — modeled on the same normalize/parse-JSON pattern this codebase already uses for the cohort narrative (`score.py:774` `normalize()`, `llm.parse_json()`). It does **not** return resume text.
- **The client assembles the final document from the master doc's own strings**, keyed by the IDs the model returned. There is no path for the model to introduce content that wasn't already in the source, because the rendered output never passes through the model's own generated prose for the substantive claims. The one deliberately-allowed exception is a short tailored summary/objective line, which is free text — flag it in the UI as "written for you, worth a glance" rather than presenting it with the same trust level as the selected (verifiably sourced) bullets.
- **This is checkable, not just designed-to-be-checkable.** Because bullets are ID-referenced, a lightweight client-side verification pass (does every ID the model returned actually exist in the source doc?) is a few lines of code, not a matter of trusting the prompt.

---

## 5. Is free-tier Groq actually capable enough? (checked live this session, 2026-08-04)

| Free-tier model | RPM | RPD | TPM | TPD |
|---|---|---|---|---|
| `llama-3.3-70b-versatile` | 30 | 1,000 | 12,000 | 100,000 |
| `openai/gpt-oss-120b` | 30 | 1,000 | 8,000 | 200,000 |
| `openai/gpt-oss-20b` | 30 | 1,000 | 8,000 | 200,000 |
| `llama-3.1-8b-instant` | 30 | 14,400 | 6,000 | 500,000 |

(Source: `console.groq.com/docs/rate-limits`, fetched live this session — re-verify before building against it; provider free-tier terms change without notice, see §6.)

A realistic single tailoring call — master doc + one job posting + instructions in, a bullet-ID selection out — lands in the low thousands of tokens. That fits inside a single request on any model in this table, and the daily budgets support many such calls per Builder per day. This is comfortably feasible **for the on-demand, one-job-at-a-time shape** ("Builder clicks tailor for this posting"). It is **not** sized for a batch job across an entire feed for every Builder every night — don't build it that way; that would recreate the exact "every persona pays for every job" cost shape the cohort layer's redesign already moved away from (`match.py:5-9`).

`llama-3.3-70b-versatile` and `openai/gpt-oss-120b` are both strong instruction-followers at a task difficulty roughly comparable to what `score.py` already does successfully against `deepseek-v4-flash` in production (structured extraction/classification against a schema) — this is not a task that needs frontier-model reasoning.

---

## 6. A risk this codebase has already been burned by once: don't hardcode Groq

`llm.py:31-45`'s own comment records that `deepseek-v4-flash` was chosen "as the cheapest paid option found once glm-4.7 turned out unreachable on this account" — a provider changed something and a model this pipeline was relying on stopped being usable. Free tiers are reshuffled by providers more often and with less notice than paid ones. Whatever gets built here should treat the model/provider as a swappable parameter (`llm.py`'s existing `base_url`/`model`/`api_key` triple already models this correctly for the server-side pipeline — the client-side code for this feature should follow the same shape: don't bake "Groq" into the UI copy or the request-building code as if it's permanent) rather than a foundational assumption.

---

## 7. Explicit non-goals for this document

- **Not** a nightly/batch job over the whole feed for every Builder. On-demand, one job at a time, Builder-initiated only.
- **Not** a change to the existing cohort `match_score`/`job_scores` pipeline. This is additive, at the job-detail level, and should not touch ranking — consistent with the standing invariant that "LLMs explain, never rank" (`CLAUDE.md`).
- **Not** a resume upload or any new server-side storage of Builder work history. If server-side storage (e.g. for cross-device access to the master doc) is ever wanted, that is a re-opening of the `NO FILE UPLOAD` decision and needs to be argued on its own, explicitly — not a default anyone should slide into while building this.

---

## 8. Open questions (owner decisions — none of these have been decided)

1. **Where does a Builder create/edit their master document?** A structured form (safer, more like the existing onboarding pattern, more work to build) vs. a freeform text box the Builder self-structures (faster to ship, weaker guarantees on the ID-addressable-unit design in §4).
2. **Where does the Builder's own LLM API key live?** `localStorage` is the obvious answer for "never touches the server," but it's also readable by any XSS on the page, and this is a population the `NO FILE UPLOAD` reasoning already flagged as needing extra care (low-income adults, home-server-hosted app). Worth asking whether the same caution that blocked resume upload should also shape how casually a third-party API key gets stored in the browser.
3. **Cross-device access.** A Builder who edits their master doc on a laptop won't see it on their phone if it's `localStorage`-only. Is that an acceptable limitation, or does it push toward some form of server-side storage (which reopens §7's non-goal)?
4. **Which provider/model to point the UI at by default**, and how to keep that swappable per §6 — does the Builder pick their own provider, or does the product pick one default with an escape hatch?
5. **Verification UX** — once the ID-existence check in §4 passes programmatically, does the Builder still get a visible "these came from your own document" affirmation, or is the guarantee purely structural and invisible?
6. **Does this fit the frontend's "no build step" constraint?** (`.claude/rules/frontend.md`) Plausibly yes — it's one more `fetch()` call from plain JS, no new tooling — but worth a second look once there's an actual UI sketch, since the master-doc editor is more UI surface than anything the frontend currently has.

---

## 9. Suggested next steps, if this survives review

Not committed to, just the natural order if the answer is "yes, build it":

1. Settle Open Question 1 (master-doc structure) first — everything else depends on it.
2. Prototype the selection prompt and the ID-existence verification pass against a fake master doc and 2-3 real postings from the live corpus, using `llama-3.3-70b-versatile` or `openai/gpt-oss-120b`, before writing any UI.
3. Only then design the editor UI and the key-storage UX (Open Questions 1-2 answered by then should make this concrete rather than speculative).
