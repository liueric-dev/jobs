# Handoff — events pipeline data quality

**Date:** 2026-07-25 · **Status:** All five approved changes applied and verified against live
data. Two follow-ups identified and deliberately **not** started (see [Open work](#open-work)).
**Nothing is committed.** `git status` in `~/.hermes/scripts` also shows unrelated in-flight
work from the `jobs/` pipeline — only the files in [What changed](#what-changed) are mine.

---

## The ask

Read `~/.hermes/scripts/events/`, verify the ingestion and the data, and confirm the events are
high quality — that people would actually want to go to them and that necessary fields are
populated.

## What turned out to be true

**The ingestion machinery was in good shape. The data it produced was not.** Checkpointing,
scoped prunes, content hashing, watermarks and geocoding all worked as documented. What the
pipeline had never been asked was whether the rows arriving at the other end were events.

Five quality problems and one silent correctness bug, all measured against the live database:

### 1. 44% of the table was un-clickable, and its `description` column was fake

All 6,457 `nyc_permitted_events` rows had `source_url`, `registration_url`, `venue_name` and
`is_free` NULL — and `description` was a **verbatim copy of `categories` in 6,457 of 6,457
rows** (`"Special Event"`, `"Block Party"`). A populated column that says nothing reads as
data and hides the gap. It is now NULL, which is honest. The missing URL is upstream's gap:
`tvpp-9vvx` carries no per-event link of any kind, so even a real event from this source
cannot be clicked through to.

### 2. ~2,400 rows were private permits, not public events

`DROPPED_CATEGORIES` caught `Sport - Youth`/`Sport - Adult`, but 88% of the survivors landed
in one bucket — `Special Event` — and that is where the private permits live. Top titles:
`Miscellaneous` (818), `Celebration` (605), `Picnic` (417), `Barbecue` (346), `Party` (234),
plus `Wedding ceremony`, `Saiges 8th World Birthday`, `Jacks 30th Birthday Stage`.

In a random 30-row sample of one weekend, **roughly 13 of 30 were somebody's private party
permit.** Nobody outside the permit holder's family can attend one.

### 3. 152 rows were park *closures* — the negation of an event

`Lawn Closures & maintenance` (29), `Construction` (28), `closed` (28),
`CROCHERON PARK GAZEBO CONSTRUCTION` (27), `Pilgrim Hill - Maintenance Days - Closed All Day`.
All 152 live matches were reviewed individually; there were no false positives.

### 4. Every parks row had `borough` = NULL

All 1,047 of them — the best free public programming in the table (free concerts, Kids in
Motion, NYRR open runs, Learn to Swim) — invisible to any borough filter. The feed has no
borough field, but `parkids` is borough-prefixed (`X045` = Bronx) and covers 943 of 1,047 for
free; the remaining 104 are non-park venues (libraries, community gardens, health centers)
that have coordinates but no park ID.

### 5. Parks descriptions leaked their markup

151 rows carried literal `&amp;`/`&nbsp;`, and block tags had been stripped without
substituting whitespace, running sentences together:
`"bike rental locations.For the summer-long celebration"`.

### 6. THE BUG — `fetch_socrata` paged without `$order`, and 6.5% of rows were invisible

Found while verifying the fix for #1, because 227 rows kept their fake description.

`$limit`/`$offset` with no ORDER BY has **no defined row order**, so Socrata is free to return a
different arrangement per page request — serving one row twice and another never. Measured
directly against `tvpp-9vvx` for the live 90-day window:

| paging | rows fetched | distinct rows |
|---|---|---|
| no `$order` (as written) | 33,471 | 31,306 |
| `$order=:id` | 33,471 | **33,471** |

**2,165 rows — 6.5% — had been invisible to the pipeline on every run since it was written.**

It was undetectable from inside the script: full pages, no error, a plausible total, and
`complete=True`, so the watermark advanced as if nothing were missing. My first read of those
227 stale rows was that the permits had been withdrawn upstream. They had not —
`Beulah Church Annual Block Party` was in the feed the whole time and had simply never been
served to us. **Do not trust a row count as evidence that offset paging is complete.**

Fixed with `$order=:id` — a Socrata *system* field, guaranteed present and unique on every
dataset and stable across content updates, unlike a data column. Both Socrata datasets share
`fetch_socrata`, so parks is covered too.

---

## What changed

| file | change |
|---|---|
| `events/boroughs.py` | **new.** Borough by point-in-polygon (PostGIS + NYC Open Data `gthc-hcne`), plus the `parkids` prefix decoder. |
| `pipelib/__init__.py` | added `boroughs` to `__all__`. |
| `events/schema.py` | **new home of the drop policy:** `DROPPED_CATEGORIES`, `DROPPED_TITLES`, `CLOSURE_PATTERN`, `is_public_event()`. |
| `events/nyc-events-ingest.py` | `$order=:id`; filters via `is_public_event`; parks borough; parks description via `strip_html`; permitted `description=None`. |
| `events/migrate.py` | `drop_non_events` now uses the shared predicate; new step 7 `reset_opendata_watermarks`. |
| `events/nyc-library-events-ingest.py` | QPL WAF block no longer claims "will resume next run" when there is nothing to resume. |
| `pipelib/tests/test_event_quality.py` | **new.** 11 tests over the filter and borough derivation. |

### Why the drop policy lives in `schema.py` and not in the ingest script

`migrate.py` needs the same predicate to delete rows admitted under an older rule, and it
**already kept its own copy of the category list that had drifted from the ingest script's.**
If the two disagree, the pipeline re-admits on every run exactly what the migration just
deleted. One definition, two callers.

### Why the migration resets the watermarks

Fixing the normalizer does not reach stored rows. The Socrata jobs filter on
`:updated_at > <last success>`, so a row unchanged upstream is never refetched and therefore
never re-normalized. Deleting the watermark makes the next run refetch the window once and
re-normalize everything — using the pipeline itself instead of a second copy of each
normalizer inside the migration, which is what put borough out of sync in the first place.
It is the **last** step, so it cannot run before the fixes it is meant to propagate.

---

## Verified results

Backup taken before any writes: `~/.hermes/backups/nyc_events-pre-quality-20260725-060229.sql.gz`

| | before | after |
|---|---|---|
| rows | 14,797 | 12,534 |
| private permits + closures | 2,590 | **0** |
| rows with no borough | 1,047 | **0** |
| descriptions with raw HTML entities/tags | 151 | **0** |
| fake descriptions (category copies) | 6,457 | **3** — see below |
| parks rows with borough | 0 | 1,047 (943 `parkids`, 104 polygon) |
| duplicate groups, permitted | 442 | 51 |

Per source, after:

| source | rows | borough | link | real description | coords |
|---|---|---|---|---|---|
| `nypl_events` | 7,293 | 7,293 | 7,293 | 7,227 | 6,129 |
| `nyc_permitted_events` | 4,194 | 4,194 | 0 | 0 | 3,245 |
| `nyc_parks_events` | 1,047 | 1,047 | 1,047 | 1,047 | 1,036 |

Borough now populated on **12,534 of 12,534 rows**: Manhattan 5,037 · Bronx 4,084 ·
Staten Island 1,208 · Brooklyn 1,184 · Queens 1,021.

**The 3 remaining fake descriptions are not a missed case — they are the reaping gap in
[Open work #1](#1-nothing-reaps-rows-that-vanish-or-change-upstream--recommended-next).**
Those rows no longer exist upstream at that `start_datetime`, so no fetch can refresh them and
no normalizer change can reach them. They are the same three rows listed in that section
(`MUTS-Baruch Playground`, `NYRR Open Run at Marine Park`, `Summer Block Party`), and they are
a useful canary: **when reaping lands, this count should go to 0.** It is the cheapest test
that the reap works.

Point-in-polygon spot checks, including the negative case:
Bayside→Queens, Macon→Brooklyn, Tompkins Sq→Manhattan, Bronx River Garden→Bronx,
Snug Harbor→Staten Island, **Newark→`None`** (not a wrong guess).

Tests: **103 pass**, standalone and under `unittest discover`.

---

## How to verify this yourself

```sh
set -a; . ~/.hermes/.env; set +a
cd ~/.hermes/scripts

python3 -m unittest discover -s pipelib/tests -t . -q     # 103 tests
python3 events/migrate.py                                  # dry run, never writes
DEBUG_PRINT_KEYS=1 python3 events/nyc-events-ingest.py     # ~15-25 min, Nominatim-bound
```

In the migrate dry run the line that matters is **`non-events dropped: 0`** — that is the
idempotency check, and anything above 0 means the ingest filter and the migration have drifted
apart again. The other lines are *not* expected to be zero: geocode failures expire on a TTL
and park-coded addresses are resolved incrementally, so both show ongoing churn, and the
watermark step always reports 2 because a watermark is always resettable.

```sql
-- must be 0
SELECT count(*) FROM events WHERE borough IS NULL;
SELECT count(*) FROM events WHERE description ~ '&[a-zA-Z]+;|<[a-zA-Z/][^>]*>';

-- must be 0 for each of the three filters
SELECT count(*) FROM events
 WHERE source = 'nyc_permitted_events'
   AND (lower(btrim(title)) IN ('miscellaneous','celebration','picnic','barbecue','party')
        OR title ~* 'construction|closure|closed|maintenance'
        OR categories IN ('Sport - Youth','Sport - Adult','Theater Load in and Load Outs'));

-- currently 3, NOT 0 -- these are the un-reapable ghosts, see Open work #1.
-- Goes to 0 when reaping lands; treat any OTHER number as a regression.
SELECT count(*) FROM events WHERE source='nyc_permitted_events' AND description IS NOT NULL;
```

**A run takes ~15-25 minutes**, almost entirely Nominatim at its published 1 req/sec. The
geocode cache is warm now, so steady-state runs are much shorter. The `events-ingest` cron job
(`0 8 * * *` → `events/run-daily.py`) previously died on a 3600s timeout; watch whether the
first scheduled run after this clears it.

---

## Open work

### 1. Nothing reaps rows that vanish or change upstream — RECOMMENDED NEXT

`prune_expired` only deletes rows outside the *date window*. A permit that is cancelled or
amended upstream keeps its old row until its date passes.

Amendment is the case that actually misinforms, because the primary key includes
`start_datetime`, so an amended permit is stored **twice**. Both confirmed against upstream:

| event | stored | upstream now |
|---|---|---|
| `MUTS-Baruch Playground` | Aug 12 **16:00** and Aug 12 20:00 | Aug 12 20:00 only |
| `NYRR Open Run at Marine Park` | Jul 25 **08:00** and Jul 26 08:00 | Jul 26 08:00 only |

So the event is served at the right time *and* the wrong one. `Summer Block Party` is the
simpler cancellation case: 0 occurrences upstream, still in our table.

The mechanism already exists — `last_seen` is maintained, and `fetch_socrata` returns a
`complete` flag that says whether the sweep can be trusted. A reap of "rows in-window not seen
by the last *complete* fetch" is the obvious shape. **I did not implement it: it is a new
delete path, and getting `complete` wrong deletes live data.** Rehearse against a restored
snapshot per `DATABASE.md`.

I could not size it cleanly. 398 permitted `source_id`s have more than one `start_datetime`,
but legitimately recurring permits (a weekly farmers market under one permit) are in that
number too — treat 398 as an upper bound, not a ghost count.

### 2. QPL needs a real browser session — Queens and Brooklyn are thin

Queens Public Library has **never ingested a single row.** There is no `qpl_events` entry in
`ingest_state` *or* `ingest_progress`. Reproduced live: the WAF rejects the very first request,
to the `/calendar` landing page that establishes the session, 4/4 retries. The
checkpoint-and-resume design cannot help — the block lands before page 1.

I only made it stop lying (it claimed "will resume next run"). With QPL blocked and Brooklyn
Public Library excluded by design — `bklynlibrary.org` bans scrapers in robots.txt and its
BiblioCommons platform issues API keys only to institutional partners — **neither Brooklyn nor
Queens has any library events at all**: Brooklyn 1,184 events for 2.7M people against the
Bronx's 4,084 for 1.4M. The borough fix makes that gap measurable, not smaller.

### 3. Smaller, unaddressed

- **4 permitted rows geocode to Syracuse** (43.06, −76.13) — "St. James Park" matched the wrong
  state. `boroughs.borough_for_point` now returns `None` outside NYC, so it is available as a
  cheap sanity check on any geocode result; not wired up.
- **`is_free` is unconditionally TRUE for parks**; ~5 rows are actually paid (Wheel Fun Rentals
  surrey rentals, $29/$39).
- **39 NYPL duplicate pairs** from upstream slug collisions (`…/adult-gaming` and
  `…/adult-gaming-0`) — identical title, time and venue.
- **1,164 NYPL rows (16%) have no coordinates**; ~18 start at 2–5 AM local; 2 parks rows have
  `end_ts < start_ts`.
- **Ticketmaster and SeatGeek contribute nothing** — no API keys — so 2 of 6 sources are dark.
  That script has therefore never completed a run; its fixes are unexercised.

---

## Gotchas for whoever picks this up

**The title filter is whole-title, case-folded, never substring.** This is load-bearing.
`Picnic` is a private reservation; `Picnic in the Park with the Philharmonic` is a real event.
Pinned by `test_generic_match_is_whole_title_not_substring`.

**`CLOSURE_PATTERN` is scoped to `nyc_permitted_events` only, on purpose.** Applied table-wide
it would delete NYPL's `Creative Construction Corner` (a kids' building program) and
`Advanced Python Functions Part 2: Closures and Decorators`. Seven such rows exist today.

**The known residue:** whole-title matching catches generic names, not distinctive private
ones — `"Ragnars first birthday"` survives. That is the deliberate tradeoff against dropping
real events, and it is small next to the 2,438 caught.

**These changes touch three hash fields** (`description`, `borough`, `categories`), so the
first run after them reports every in-window permitted and parks row as `updated`. That is the
intended one-time rewrite, not hash-scheme breakage; subsequent runs settle to `unchanged`.
`HASH_FIELDS` order and membership are still frozen — only values changed.

**Two files are named `schema.py`** (`events/` and `jobs/`), and both pipelines import theirs as
bare `schema` after putting their own directory on `sys.path`. That is unambiguous when a
script runs alone but **not** under `unittest discover`, where one interpreter is shared and
whichever imports first wins `sys.modules`. `test_event_quality.py` loads
`events/schema.py` by path to sidestep the name; do the same in any new test.

**Borough boundaries are shoreline boundaries.** A point in the harbor belongs to no borough
and returns `None`. That is the honest answer — every venue we care about is on land — but do
not read `None` as "lookup failed".
