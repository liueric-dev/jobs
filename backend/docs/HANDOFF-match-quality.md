# HANDOFF: extraction fields and match quality — MOVED

> **ARCHIVED 2026-08-01 (task 40) → [`docs/archive/handoff-match-quality.md`](../../docs/archive/handoff-match-quality.md).**
> A stub and a link are left here so an inbound citation still lands somewhere, per
> `docs/archive/README.md`. `git log --follow` on this path reaches the original text.

**Written 2026-07-26**, at the end of the multi-user scoring rework. It measured how well
`match.py` ranked postings for **profile `tech`** — the repo author's own software-engineer
job search. **That is not the Pursuit cohort**, and nothing measured against it transfers.

## Where each part went

| you were looking for | read this instead |
|---|---|
| **§ 4, the seven measurement traps** (4.1–4.7) | **[`docs/MEASUREMENT-TRAPS.md`](../../docs/MEASUREMENT-TRAPS.md)** — promoted 2026-07-31, section numbering preserved so `4.1`–`4.7` still resolve, and it carries later additions from the refactor run. `.claude/CLAUDE.md` points every session there. **Code comments citing `HANDOFF-match-quality.md:147` / `:155` mean traps 4.1 and 4.2 and should cite the promoted file.** |
| **how the pipeline works, and what each stage costs** | [`SCORING.md`](SCORING.md) — the design argument; and [`docs/scoring.md`](../../docs/scoring.md) — the contract |
| **everything else** — §§ 1–3 and 5–9: the inherited state, what is ruled out, the learned-ranker probe, the shelved extraction fields, the cheap-experiment loop, the practical warnings | **[`docs/archive/handoff-match-quality.md`](../../docs/archive/handoff-match-quality.md)**, in full and unedited apart from the header |

## Before you quote a number out of it

**The 12.7/20 is imitation fidelity against a non-target persona, not a quality score.**
The learned-ranker probe was fitted and cross-validated against `job_scores.fit_score` —
the judgement of the LLM-per-pair pipeline this design *replaced*, for a software engineer
who is not a Builder. A perfect 20/20 would mean perfect imitation of an incumbent nobody
claims was right. The archived header states this at length, and
`docs/MEASUREMENT-TRAPS.md` § *Never evaluate on the layer you trained on* is the general
form.

**The recommendation survives; the numbers attached to it do not.** Its conclusion — build
the learned ranker over the features that already exist, rather than extracting more
fields — is still the open next move, tracked in `docs/tasks/refactor/README.md`.
