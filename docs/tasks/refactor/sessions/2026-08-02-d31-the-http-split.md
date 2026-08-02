---
kind: record
written: 2026-08-02
generator: none
---

# Session record — 2026-08-02, D31 and the `lib.http` split

**Frozen on write.** A `record` says what happened on a date and is corrected by a later
record rather than rewritten ([`../../../DOCS-POLICY.md`](../../../DOCS-POLICY.md) rule 4).
Nothing here is a figure: [`AUDIT.md`](../AUDIT.md) owns the run-level numbers.

## What was taken, and why this one

The first of the two items [`../HANDOFF.md`](../HANDOFF.md) § *What is next* still listed.
The other (`OQ-2`/`D75`, the impression dedup key) is the owner's, so this was the whole of
the session-doable surface.

`HANDOFF.md` warned that the answer would be *"a mixed disposition, not a migration"*. That
turned out to be exactly right, and the pointer it gave — read
`ingest/builtin-nyc.py`'s `fetch_description` before starting — was the load-bearing part.

## What was decided

`DEC-96`. Three of **four** call sites moved to `lib.http`; `builtin-nyc.fetch_description`
stayed on `urllib.request.urlopen` because `lib.http` retries the 429 that `RateLimited`
exists to stop on. The register said three sites; there were four, both of them in
`builtin-nyc.py`, taking opposite dispositions in the same file.

`lib/` gained `get_bytes` — the retry loop, undecoded — and `get_text` became that decoded.
`weworkremotely.fetch_feed` must return bytes: the feeds carry an XML encoding declaration
and `ET.fromstring` refuses a `str` that has one.

## What was wrong before this session, and what it cost

**The recorded reason for the bypass was false.** `evals/cassettes.py` said the four sites
built their own requests "to send a browser-ish User-Agent that lib/http.py does not take a
parameter for." `lib/http.py:56-58` has merged `headers=` over its default since it was
written. All four User-Agents survived the migration untouched, in one keyword argument.

That sentence was the reason D31 read as a hard call. `weworkremotely.md`'s open question,
D31's own body and the harness docstring all reasoned from it, and none of them checked it.
`DEFECTS.md` already carries *read the code, not the cite* as a standing lesson, learned
from line numbers that had drifted. This is the same lesson about a **rationale**, which is
worse, because a stale line number announces itself the moment you follow it.

Three other things in `evals/cassettes.py`'s header were wrong on arrival and were fixed in
passing: all four line cites had drifted (by 1, 47, 14 and 14 lines), and it described
`lib/` as "vendored byte-identical to another repo", which `lib/__init__.py` and
`.claude/CLAUDE.md` have both contradicted since `lib/` became this repo's own code.

## What is pinned, and the one test that matters

`backend/tests/test_ingest_retry.py`, ten cases, no network. Four of them fail against the
pre-session tree. The one that does **not** is the point of the file:
`fetch_description` issues exactly one request per posting on a 429. It passes today and it
passed a month ago, and it is there so the next person who notices the inconsistency and
tidies it up gets a red test and a reason instead of a rude scraper.

`tests/test_lib_contract.py` grew four cases so that `get_text` is pinned as `get_bytes`
decoded rather than as something merely similar to what it used to be.

## Suite

Read from the `Ran N tests` line before and after, in the same tree. **The count itself is
[`AUDIT.md`](../AUDIT.md)'s figure** and is not restated here — that row's whole point is
that it is whatever the runner prints. What this session is entitled to say is the delta:
**+14, and green at both readings**, ten cases in `test_ingest_retry.py` and four in
`test_lib_contract.py`.

The webapp and `api/` suites were both run, by their own interpreters, and both came back
OK unchanged. This change touches neither, but "it should not have" is not a reading.

(C4 caught the first draft of this paragraph restating the before-count, which is why the
paragraph reads the way it does. Worth noting where it fired: not in a contract or a
register, but in a `sessions/` record written by someone who had read rule 2 that morning.)

## What this leaves for the next session

**`OQ-2`/`D75` is now the only thing on `HANDOFF.md` § *What is next*, and it is the
owner's.** The session-doable surface of this run is empty until an owner decision opens
something. `D33` and `D34` remain deliberately open, unchanged, for the reasons their
entries give — `D33` belongs to task 25 and `D34` wants a person at a psql prompt.

One thing was found and not fixed, on purpose: `lib/http.py` prints its `[retry] … waiting
Ns` line before deciding whether another attempt exists, so `max_retries=1` announces a
wait it never takes. No caller in this repo passes `max_retries=1` — it was considered as a
way to route `fetch_description` through `lib.http` and rejected — so fixing it now would be
changing shared code to serve a hypothetical. It is written down here instead.
