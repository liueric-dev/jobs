# The labelling rate, measured at n=4 and re-derived at n=29

> **Archived from `docs/tasks/refactor/HANDOFF.md` on 2026-07-31**, when that file was split.
>
> **What it is:** Measured the per-posting labelling rate, 2026-07-31. The n=4 reading (154 s) and its same-day correction at n=29 (93 s median). Superseded as a *narrative* by the single entry in HANDOFF.md's § Pending follow-ups, which carries the live number.
>
> Moved, not deleted. `git log --follow` on this path reaches the original text, and a stub
> and link remain where this section was.

---

## READ THIS FIRST: ~~the stopwatch reading, and the budget is out by 2.5x~~ the stopwatch reading was RE-DERIVED, and the correction goes the other way

**Corrected 2026-07-31, later the same day, at n=29 intervals instead of n=4.** The
section below it is kept in full, because it is what the run planned against for a day and
because the way it was wrong is the reusable part.

**The re-derived number: median 93 s, mean 110 s per posting** (n=29). Instrument:
`python3 backend/tools/label-findings.py --timing` — successive `min(labelled_at)` per
`job_id` in submit order, over all 31 labelled postings, one labeller (`u_090b0ad12e99`),
`2026-07-31T02:56:05`–`05:25:27` UTC.

Raw intervals, printed before any statistic because a sitting contains breaks:

```
 87  170  247  110  5765   81  178   83  133   93
125   74  113  131   119  171  116   80   69  251
 43  101   38   78    50   67   91   76   73  149
```

**One interval of 5,765 s is excluded as a break** at the tool's default `--break-secs
600`. Both figures are printed so the exclusion can be argued with: **including** the
break, median 97 s / mean 299 s (n=30); **excluding** it, **median 93 s / mean 110 s**
(n=29). A mean over a list containing a 96-minute gap is a statistic about dinner.

**There IS a warm-up curve, and it runs the direction the note below said it did not.**
First 7 intervals mean **137 s**; last 7 mean **83 s**. The labeller speeds up. **The
original n=4 sample — 87, 170, 247, 110, mean 153.5 s — is the first four intervals of
this list and sits entirely inside the warm-up.** It was not a rate; it was the price of
learning the form.

| what this file says | ~~at 154 s~~ | at the median 93 s |
|---|---|---|
| *"Twenty minutes, in person, in one sitting"* → ~20 postings (`29` § *Logistics*) | ~~~8 postings~~ | **13 postings** |
| *"one second person and ten minutes"*, the ten `overlap` rows | ~~~26 minutes~~ | **16 minutes** |
| 60 postings | ~~~2.6 hours~~ | **1.6 h** |
| ≥100 postings, one person (the DoD) | ~~~4.3 hours~~ | **2.6 h** |
| 200 postings, one person | — | **5.2 h** |

**THE IRONY IS THE FINDING, and it is worth one sentence.** The superseded section's own
closing caveat reads *"the fastest interval is the first, which is the opposite of a
warm-up curve and is the thing to re-check as the count grows."* It named the re-check,
the re-check was run, and **the re-check overturned the section that asked for it.** A
caveat that specifies its own instrument is worth more than a caveat that hedges.

**What this changes about asking people, and it changes it twice.** ~~Ask for half an
hour.~~ Ask for **about twenty minutes** — ten `overlap` rows at 93 s is 16 min, and those
ten rows are now the *only* thing standing between this run and a printable
`evals label report`, because the overlap block is already complete on the owner's side.
The ask got smaller and what it buys got larger in the same measurement.

**Caveats that belong beside the number wherever it is quoted**: one labeller; six-question
form, not a factor applied to a five-question one; submit-to-submit includes reading, and
**the first posting's own reading time is not in the figure at all**, so the true rate is
*higher* than 93 s rather than lower. And the curve means **a rate taken from a fresh
labeller's first few postings overstates the cost of the rest** — which is now measured
rather than asserted, at 137 s against 83 s.

**Re-derive it, do not re-quote it — and that instruction now has a command.** It was
issued three times and re-quoted three times, because re-deriving needed four lines of SQL
first. `backend/tools/label-findings.py` is those four lines, kept. An instruction to
re-derive that requires someone to write SQL is an instruction that decays into a
quotation.

Full working: `tranche_five/29-labelling-session.md` § *Findings, 2026-07-31*, E.

---

> **SUPERSEDED 2026-07-31. Everything from here to the end of this section is the n=4
> reading, kept verbatim.** It is what §§ *How many to label*, *recommended next steps* and
> *Pending follow-ups* were written against, and a reader who was working from "154 s" or
> "~8 postings" needs to see it to recognise what they had.

**Added 2026-07-31.** This file has asked three times for the one number nobody had
measured, and warned each time against inventing a correction factor for it. **It is now
measured, and it is worse than every estimate built on it.**

Instrument: `eval_labels.labelled_at`, successive `min(labelled_at)` per `job_id`, over the
first five labelled postings. **No stopwatch was needed — the rows carry it.** Intervals:
**87 s, 170 s, 247 s, 110 s. Median 170 s, mean 154 s.**

| what this file says | at 154 s/posting |
|---|---|
| *"Twenty minutes, in person, in one sitting"* → ~20 postings (`29` § *Logistics*) | **~8 postings** |
| *"one second person and ten minutes"*, the ten `overlap` rows | **~26 minutes** |
| *"~28 items each"* at five labellers, to reach ≥100 | **~72 minutes each** |
| ≥100 postings, one person (the DoD) | **~4.3 hours** |

**The recommendation in § *How many to label* survives and gets cheaper to state.** That
section already says ~60 in the first sitting and 110 as the target across two or three,
and that 200 is bought almost entirely for the recall question. At this rate **60 postings
is ~2.6 hours**, which is not one sitting — so *"across two or three"* was right and the
per-sitting figure inside it was not.

**What this changes about asking people.** The second labeller's ten rows are the cheapest
unblock in task 29 and that is unchanged — they still turn every refused field into a
printable one, they still never see the other 190, and they should still be arranged
**before** a long solo sitting. **But it is not a ten-minute favour.** Asking for it as one
and then keeping somebody for half an hour is how the second labeller does not become a
third. Ask for half an hour.

**Caveats, because this is n=4 intervals and the file's own rule is to state them beside
the number**: one labeller; submit-to-submit includes reading; **the first posting's own
reading time is not in the figure at all**, so the true rate is *higher* than 154 s rather
than lower; and the fastest interval is the first, which is the opposite of a warm-up curve
and is the thing to re-check as the count grows. **Re-derive it, do not re-quote it** — the
query is four lines and this file has now gone stale on eight numbers it quoted.

This is a measurement of the **six**-question form, not a factor applied to a five-question
one. Full working: `tranche_five/29-labelling-session.md` § *Findings, 2026-07-31*, E.
