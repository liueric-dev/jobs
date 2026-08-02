---
kind: task
written: 2026-08-02
generator: none
---

# 48 — stop the refactor at a known-green state

**Status:** TODO. **Depends on:** nothing. **Blocks:** 49, and everything after it.

**This is the cheapest task in the tranche and it is not ceremonial.** Everything after this
reads the tree as ground truth. If the tree is not the tree, 49 measures the wrong thing and
50 extracts from it.

## The premise, and check it before believing it

`HANDOFF.md` § *What is next* states that a session opening this run should expect to find
nothing it can start alone. **That sentence has already been wrong once** — on 2026-08-02 it
said exactly this while `README.md`'s status column listed task 23 as `todo`, needing no
credential, no person and no device. 23 landed the same day.

So: **read the status column, not the prose.** The current tally is 33 done, 6 in progress,
1 todo. Confirm it rather than inheriting it.

```bash
grep -oE "\| (done|todo|in progress) \|?$" docs/tasks/refactor/README.md | sort | uniq -c
```

If a session-doable task is genuinely open, **stop this tranche and do that task first.**
Cutting mid-flight to reorganise documentation is how tranche seven happened.

## The work

1. **Land or stash whatever is in flight.** Nothing uncommitted survives into 49.

2. **Run all three suites and both doc checkers, from the repo root.** Record what the runners
   print. Do not type a count into any document — rule 3.

   ```bash
   cd backend        && python3 -m unittest discover -s tests
   cd backend/webapp && .venv/bin/python -m unittest discover -s tests
   cd backend/api    && .venv/bin/python -m unittest discover -s tests
   cd $REPO_ROOT && python3 backend/tools/audit-docs.py
   cd $REPO_ROOT && python3 backend/tools/audit-doc-links.py docs
   ```

   **`audit-doc-links.py` defaults its root to `docs` relative to CWD and `backend/docs/`
   exists** — run from `backend/` it scans the wrong tree and reports zero while links are
   broken (task 47). Pass the path explicitly, from the root.

3. **Tag it.** `git tag refactor-freeze-2026-08-02` on the commit everything else cuts from.
   This is the "we can always get back" guarantee that makes 51 safe to do quickly.

4. **Write the freeze record.** `docs/tasks/refactor/sessions/YYYY-MM-DD-the-freeze.md`,
   `kind: record`, frozen on write. It holds: the three suite readings, the checker readings,
   the status tally, the tag, and the one-line reason the run is stopping. **It does not hold a
   plan** — the plan is this tranche.

5. **Mark the refactor paused in `HANDOFF.md`**, in its live state section, one line, pointing
   at this tranche. Do not append narrative; that is what `sessions/` is for.

## Definition of done

- [ ] `git status` clean; all three suites green; both checkers report zero
- [ ] The status tally is reproduced from the file, not quoted from this task
- [ ] `refactor-freeze-2026-08-02` tag exists and is pushed
- [ ] A `kind: record` freeze file exists carrying every reading, each with its command
- [ ] `HANDOFF.md` names the pause and links here, and did not grow by more than five lines
- [ ] **No product code changed by this task**

## What this task must not do

Do not "tidy up while we're here." Do not fix a stale doc you notice. Do not close a defect.
The entire value of a freeze is that it is a single known point, and every extra change makes
49's measurement one step less trustworthy.
