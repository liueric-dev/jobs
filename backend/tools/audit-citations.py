#!/usr/bin/env python3
"""Do the repo's `file:line` citations still point at anything?

`.claude/CLAUDE.md` requires a claim about the code to carry a `file:line`, on
the grounds that a citation is what makes a claim checkable. It also admits, in
the same paragraph, that a number of existing citations have drifted and that
there is no checker. This is the checker.

    python3 backend/tools/audit-citations.py             # exit 1 on new drift
    python3 backend/tools/audit-citations.py --all       # baseline included
    python3 backend/tools/audit-citations.py --update-baseline
    python3 backend/tools/audit-citations.py --update-snapshots
    python3 backend/tools/audit-citations.py --self-test

WHAT IT CAN AND CANNOT SEE, because overstating this would make it the exact
thing it exists to prevent:

  * A path that does not exist -- CHECKED, and mechanical.
  * A line number past the end of the file it names -- CHECKED, and mechanical,
    **EXCEPT behind the tag form described below, which is skipped whole.**
    `git show <ref>:<path>:99999` resolves exactly as cleanly as a correct one:
    the tag-span test in `scan()` `continue`s before any line-range check can
    run. Found by reading content, not by this tool -- citations to a 144-line
    file at line numbers as high as 1047 passed silently across two sessions
    (`T-18`). RE-RUN `--all` AFTER EVERY BATCH of citation edits: the
    PostToolUse hook fires on the file being edited, so its silence says
    nothing about a citation in a file you touched two commits ago.
  * A citation whose line still exists but no longer says anything like what
    the citing comment claims -- **PARTLY CHECKED SINCE 2026-08-18, and the
    distinction matters.** `config/citation-snapshots.json` records a digest of
    what each cited span said when a person last confirmed it, and a run reports
    every citation whose target line has CHANGED underneath it. What that
    catches is drift. What it cannot catch is a citation that was wrong when it
    was written: that gets snapshotted wrong and stays green forever. So a
    confirmed citation is a human assertion with a date, not a proof, and
    `--update-snapshots` is the act of asserting -- run it after re-reading the
    lines that moved, never to clear a red run. See `docs/adr/0010`.
  * Whether a path is present because the tree contains it or because the
    pipeline has run -- SIDESTEPPED. Git-ignored paths are not judged; see
    `_drop_ignored`.

That third class is real, and the worked example is HISTORICAL rather than
in-tree -- do not go looking for it here and conclude this tool is lying. It is
also the example that motivated the snapshots: the drift below is exactly what a
digest comparison reports and what a line-range check cannot.
`git show 20ee7d0:backend/extract.py` line 404 cited `lib/text.py:119` for a
`re.sub(r"<[^>]+>", " ", text)` that had been folded into `_TAG` rather than
left where it was, while `lib/text.py:184` said outright "Tag stripping is
`_TAG` above, not `<[^>]+>`". The line number resolved. The claim was false, and
this tool was green across it for as long as it stood. A green run means the
citations RESOLVE, never that they are RIGHT.

WHY A BASELINE RATHER THAN A SWEEP. There are dozens of drifted citations in
the tree and fixing them all in one commit would be a large, unreviewable diff
whose correctness nobody could check -- the same move that produced the docs
this repo just deleted. The baseline records what was already broken, with a
reason, so that NEW drift fails and OLD drift is visible without blocking. It
is `config/citation-baseline.json` and it is meant to shrink.

THE TAG FORM IS DELIBERATELY ALLOWED. `git show refactor-freeze-2026-08-02:<p>`
is the correct way to cite the 137 documents deleted on 2026-08-02, and a
checker that flagged those would push people back toward pretending the files
are present. A bare `docs/…` path is a finding; the same path behind `git show
<ref>:` is not.

No third-party imports: this runs under the top level's bare system python3,
like everything else in tools/.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASELINE = os.path.join(REPO, "backend", "config", "citation-baseline.json")
SNAPSHOTS = os.path.join(REPO, "backend", "config", "citation-snapshots.json")

#: Extensions worth reading. Everything else is data or binary.
#: `.jsonl` is here for the same reason the alternation below is length-sorted:
#: without it every `evals/fixtures/corpus-v1.jsonl` citation matched as a file
#: named `corpus-v1.json` and was reported missing. Adding a suffix that the
#: tree uses but this tuple omits is how this checker grows false findings.
SUFFIXES = (".py", ".mjs", ".js", ".md", ".jsonl", ".json", ".sh", ".service",
            ".timer", ".yml", ".yaml", ".css", ".html", ".sql")

#: Directories never scanned. `.venv` holds two vendored FastAPI trees whose
#: own docs cite paths that mean nothing here.
#:
#: `.claude` IS NOT HERE, and was: skipping it exempted `.claude/CLAUDE.md` --
#: the file that imposes the cite-`file:line` rule in the first place, and the
#: densest collection of citations in the repo -- from the checker enforcing it.
#: Nothing else under `.claude/` is tracked, and `_tracked_files()` reads
#: `git ls-files`, so the gitignored working files there are still never read.
#: It was scanning clean when it was added, so this costs nothing today; the
#: point is that the next drifted citation in it fails the suite.
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", ".cache"}

#: docs/orientation-2026-08-02/ is the frozen raw output of the audit that
#: produced STATE-OF-THE-SYSTEM.md. Its citations were correct when written and
#: it is a `kind: record` snapshot -- rewriting it would destroy the evidence.
SKIP_PATHS = {os.path.join("docs", "orientation-2026-08-02")}

#: Corpora and recorded HTTP bodies. These hold JOB POSTING TEXT, not prose
#: about this repo, and a posting that says "Rails/Node.js" or
#: "Ethereum/Ethers.js" is not making a claim about a file. Scanning them
#: produced findings that could never be fixed, because the fix would be
#: editing a frozen fixture. MANIFEST.json files under fixtures/ are NOT
#: skipped -- those are written by us and do cite the code they describe.
#: THE CHECKER CANNOT SCAN ITSELF, and the reason is not special pleading: a
#: file whose SUBJECT is broken citations necessarily contains broken citations.
#: The baseline is a list of findings and every entry quotes the dead path it is
#: about. This module's docstring quotes `docs/RUNBOOK.md` to explain the tag
#: form and `Rails/Node.js` to explain the corpus skip. The test uses `a/b/*`
#: fixtures. None is a claim that a file exists.
#:
#: Found the honest way: by committing them, at which point `git ls-files` began
#: listing them and the checker reported 300-odd findings against itself.
SELF = {
    "backend/config/citation-baseline.json",
    "backend/tools/audit-citations.py",
    "backend/tests/test_citations.py",
}


def _is_corpus(rel):
    if rel in SELF:
        return True
    if os.path.basename(rel).startswith("MANIFEST"):
        return False
    return (rel.endswith(".jsonl")
            or "/cassettes/" in rel
            or "/fixtures/mock/" in rel)

#: A repo-relative path, optionally followed by :line or :line-line.
#: Anchored on a known suffix so that prose like "see match.py" is caught but
#: "3.14" and "a.b" are not.
#:
#: LONGEST SUFFIX FIRST, and this is not cosmetic. Python's `|` takes the first
#: alternative that matches, not the longest, so with "js" ahead of "json" every
#: `GET_v1_searches.suggested.json` in verify_fixtures.py matched as a file
#: named `...suggested.js` and was reported as missing. That single ordering
#: produced ~2,500 false findings on the first run -- more than enough noise to
#: make the checker worth ignoring, which is how a checker dies.
_EXT = "|".join(sorted((s.lstrip(".") for s in SUFFIXES), key=len, reverse=True))
CITATION = re.compile(
    r"(?<![\w./-])"                     # not mid-identifier
    r"((?:[\w.-]+/)*[\w.-]+\.(?:" + _EXT + r"))"   # the path
    r"(?::(\d+)(?:-(\d+))?)?"           # optional :line or :line-line
)

#: `git show <ref>:<path>` -- the supported way to cite a deleted file.
TAG_CITATION = re.compile(r"git\s+show\s+[\w.@/-]+:")

#: Paths that are not repo paths and must not be resolved as such.
IGNORE_PREFIXES = ("http://", "https://", "file://", "~/", "/usr/", "/etc/",
                   "/home/", "/tmp/", "/var/", "./node_modules")

#: Bare filenames with no directory are ambiguous (`app.py` exists three times)
#: and are resolved by basename anywhere in the tree; only a name that matches
#: NOTHING is reported. A path with a slash must resolve exactly.
_ANY_SLASH = re.compile(r"/")


def _tracked_files():
    """Every tracked text file, from git, so untracked scratch is never read."""
    out = subprocess.run(["git", "-C", REPO, "ls-files", "-z"],
                         capture_output=True, text=True, check=True).stdout
    for rel in out.split("\0"):
        if not rel or not rel.endswith(SUFFIXES):
            continue
        parts = rel.split("/")
        if any(p in SKIP_DIRS for p in parts):
            continue
        if any(rel.startswith(p) for p in SKIP_PATHS):
            continue
        yield rel


def _index_basenames(tracked):
    index = {}
    for rel in tracked:
        index.setdefault(os.path.basename(rel), []).append(rel)
    return index


#: Returned when a bare basename matches several tracked files. Neither
#: "resolves" nor "missing" is honest, so nothing is reported.
AMBIGUOUS = object()

#: Where a repo-relative citation is resolved from, in order.
#:
#: `backend/` IS A ROOT AND THAT IS THE HOUSE CONVENTION, not a convenience:
#: .claude/CLAUDE.md opens with "Everything resolves relative to `backend/`,
#: never the repo root". So `ingest/ats.py` cited from backend/tests/test_x.py
#: means backend/ingest/ats.py, and resolving only from the citing file's own
#: directory reports 75 of them missing.
SEARCH_ROOTS = ("", "backend")


def _resolve(path, citing_file, basenames):
    """Return the repo-relative file a citation names, or None.

    Tries, in order: each search root; relative to the citing file's own
    directory (how a Markdown link resolves); the same with leading `../`
    stripped, since a script's docstring cites paths relative to the directory
    it is RUN from rather than the one it lives in (frontend/serve.py runs from
    backend/webapp/); and finally any tracked file with that basename.
    """
    for root in SEARCH_ROOTS:
        cand = os.path.normpath(os.path.join(root, path)) if root else path
        if not cand.startswith("..") and os.path.exists(os.path.join(REPO, cand)):
            return cand

    here = os.path.dirname(citing_file)
    joined = os.path.normpath(os.path.join(here, path))
    if not joined.startswith("..") and os.path.exists(os.path.join(REPO, joined)):
        return joined

    bare = path.lstrip("./")
    while bare.startswith("../"):
        bare = bare[3:]
    if bare != path:
        for root in SEARCH_ROOTS:
            cand = os.path.normpath(os.path.join(root, bare)) if root else bare
            if os.path.exists(os.path.join(REPO, cand)):
                return cand

    # ONLY WHEN THE BASENAME IS UNIQUE. `score.py` is several files here
    # (backend/score.py, evals/tasks/score.py, ...), so picking the first hit
    # resolved lib/dbconn.py's `jobs/score.py:417` against a 156-line
    # evals/tasks/score.py and reported a line overrun that does not exist. An
    # ambiguous basename is not evidence either way -- AMBIGUOUS says so, and
    # the caller skips it rather than guessing in either direction.
    hits = basenames.get(os.path.basename(path))
    if not hits:
        return None
    if len(hits) == 1:
        return hits[0]
    return AMBIGUOUS


def _ignore_candidates(path):
    """The forms `_resolve` would have tried, for an ignore check.

    A citation that did not resolve names no file, so there is nothing to test
    but the shapes it could have meant: the path as written, and the same under
    each search root.
    """
    out = [path]
    for root in SEARCH_ROOTS:
        if root:
            out.append(os.path.normpath(os.path.join(root, path)))
    return [p for p in out if not p.startswith("..")]


def _ignored(paths):
    """Which of these repo-relative paths git ignores. ONE call, not one each.

    `git check-ignore` consults the index by default, so a TRACKED file is never
    reported here even when a pattern would otherwise match it -- tracked files
    stay judgeable, which is the whole population this tool exists to check.
    """
    paths = sorted({p for p in paths if p})
    if not paths:
        return set()
    proc = subprocess.run(["git", "-C", REPO, "check-ignore", "--stdin", "-z"],
                          input="\0".join(paths) + "\0",
                          capture_output=True, text=True)
    # 0 = some ignored, 1 = none ignored, >1 = git itself failed. On a real
    # failure report nothing as ignored: a checker that goes quiet when its
    # helper breaks is worse than one that over-reports.
    if proc.returncode > 1:
        return set()
    return {p for p in proc.stdout.split("\0") if p}


def _drop_ignored(candidates):
    """Findings whose target is a git-ignored path are not findings.

    THE RESULT MUST NOT DEPEND ON WHETHER THE PIPELINE HAS RUN, and without
    this it did. `backend/.run-volumes.jsonl` is written by the nightly ingest
    and is ignored (`.gitignore:95`), so it is absent on a clean checkout and
    present on any machine that has run `run-daily.py`. Two citations to it went
    into the baseline from a tree that had never run, and this tool then told
    the next machine they "now resolve and can be dropped" -- advice that would
    have turned the clean checkout red through `tests/test_citations.py`. That
    is the same cries-wolf failure the (citing file, citation text) key was
    introduced to prevent, arriving by a different road.

    Runtime state is unjudgeable here for the same reason the corpora are: the
    honest answer is neither "resolves" nor "missing".
    """
    ignored = _ignored(p for _, _, cands in candidates for p in cands)
    return [(key, desc) for key, desc, cands in candidates
            if not any(p in ignored for p in cands)]


def _lines_of(rel, cache):
    """The cited file's lines, cached. Empty list if it cannot be read."""
    if rel not in cache:
        try:
            with open(os.path.join(REPO, rel), encoding="utf-8",
                      errors="replace") as fh:
                cache[rel] = fh.read().split("\n")
        except OSError:
            cache[rel] = []
    return cache[rel]


def _line_count(rel, cache):
    return len(_lines_of(rel, cache))


def digest_of(rel, start, end, cache):
    """A digest of the cited span's CONTENT, or None if it cannot be read.

    Leading and trailing whitespace goes before hashing, so re-indenting a block
    does not read as drift; anything else about the line does. Twelve hex
    characters is not a security boundary -- it is a change detector, and the
    thing it is detecting is someone editing the line, not someone forging it.
    """
    lines = _lines_of(rel, cache)
    if not lines:
        return None
    lo = int(start) - 1
    hi = int(end) if end else int(start)
    if lo < 0 or hi > len(lines):
        return None
    body = "\n".join(line.strip() for line in lines[lo:hi])
    return hashlib.sha1(body.encode("utf-8")).hexdigest()[:12]


def _spans(text):
    """Character ranges covered by a `git show <ref>:` citation."""
    return [(m.start(), m.end()) for m in TAG_CITATION.finditer(text)]


def scan(digests=None):
    """Every unresolvable citation in the tree, as (key, description) pairs.

    Pass a dict as `digests` and it is filled with `key -> digest_of(...)` for
    every citation that RESOLVES and names a line. That is the snapshot set; see
    `check_snapshots()`.
    """
    tracked = list(_tracked_files())
    # The index spans EVERY tracked file, including the corpora that are not
    # themselves scanned -- a citation TO evals/fixtures/corpus-v1.jsonl must
    # still resolve. Only the reading loop below skips them.
    basenames = _index_basenames(tracked)
    lines_cache = {}
    findings = []

    for rel in tracked:
        if _is_corpus(rel):
            continue
        try:
            with open(os.path.join(REPO, rel), encoding="utf-8") as fh:
                text = fh.read()
        except (OSError, UnicodeDecodeError):
            continue

        tag_spans = _spans(text)
        for m in CITATION.finditer(text):
            path, start, end = m.group(1), m.group(2), m.group(3)
            if path.startswith(IGNORE_PREFIXES):
                continue
            # A `git show <ref>:<path>` citation names a file at a REF, not in
            # the working tree. Correct by construction; never a finding.
            if any(s <= m.start() <= e + len(path) for s, e in tag_spans):
                continue

            # A BARE FILENAME WITH NO LINE NUMBER IS PROSE, NOT A CITATION.
            # "Node.js", "Vue.js" and "hashlib.sh" all match the path shape,
            # and so does every mention of "CLAUDE.md" in running text. None is
            # a claim about a location, which is what this tool checks. A bare
            # name WITH a line number -- `extract.py:404` -- is a citation and
            # is kept: that is the most common and most drift-prone form here.
            if not start and not _ANY_SLASH.search(path):
                continue

            lineno = int(text.count("\n", 0, m.start())) + 1

            # THE KEY DELIBERATELY OMITS THE CITING LINE NUMBER. Keying on
            # `file:line -> citation` meant that inserting a paragraph anywhere
            # above a baselined citation renumbered it, so the checker reported
            # an untouched citation as NEW and failed the suite on an unrelated
            # edit. A checker that cries wolf when you add a sentence is one
            # people learn to skip. The pair (citing file, citation text) is
            # stable under edits elsewhere in the file; the cost is that two
            # identical citations in one file share an entry, which is fine --
            # they are the same claim and get fixed together.
            key = f"{rel} -> {m.group(0)}"

            target = _resolve(path, rel, basenames)
            if target is AMBIGUOUS:
                continue
            if target is None:
                findings.append((key, f"{rel}:{lineno} cites {path!r}, which "
                                      f"does not exist", _ignore_candidates(path)))
                continue

            if start:
                total = _line_count(target, lines_cache)
                worst = int(end or start)
                if total and worst > total:
                    findings.append(
                        (key, f"{rel}:{lineno} cites {path}:{m.group(0).split(':', 1)[1]}, "
                              f"but {target} has only {total} lines", [target]))
                    continue
                if digests is not None:
                    d = digest_of(target, start, end, lines_cache)
                    if d:
                        digests[key] = d
    return _drop_ignored(findings)


def load_snapshots():
    try:
        with open(SNAPSHOTS, encoding="utf-8") as fh:
            return json.load(fh).get("confirmed", {})
    except FileNotFoundError:
        return {}


def check_snapshots(current, stored):
    """(drifted, unconfirmed) -- the two ways a citation can fail to be vouched for.

    DRIFTED is the finding this file exists for: a citation whose target line
    resolved, was confirmed by a person, and now hashes differently. The line
    moved under the claim, and nothing else in this repo notices.

    UNCONFIRMED is not a finding and does not fail. A citation written since the
    last `--update-snapshots` has never been read by anyone in this role; calling
    that an error would fail the commit that writes a correct citation, and the
    fix would be to run the refresh, which is the one command that must stay a
    deliberate human act. They are counted and printed so the number cannot sit
    at several hundred unnoticed.
    """
    drifted = [(k, stored[k], v) for k, v in sorted(current.items())
               if k in stored and stored[k] != v]
    unconfirmed = sorted(k for k in current if k not in stored)
    return drifted, unconfirmed


def _write_snapshots(digests):
    payload = {
        "_comment": (
            "What each cited line SAID when a person last confirmed the citation, "
            "as a digest of the span's content with leading and trailing whitespace "
            "removed. backend/tools/audit-citations.py compares against this and "
            "reports a citation whose target line has changed underneath it."),
        "_why": (
            "The checker's older half asks whether a citation RESOLVES -- the path "
            "exists, the line is in range. That is mechanical and it is not the "
            "failure this repo actually has. A review on 2026-08-18 found four "
            "citations that resolved perfectly and named the wrong line, one of them "
            "a blank line; every one passed. See "
            "docs/adr/0010-the-doc-layer-checks-citations-not-documents.md."),
        "_limit": (
            "A MATCH PROVES THE LINE HAS NOT CHANGED SINCE IT WAS CONFIRMED, NEVER "
            "THAT THE CLAIM WAS RIGHT WHEN CONFIRMED. A citation written wrong is "
            "snapshotted wrong and stays green. This file is therefore a record of "
            "human assertions, and `--update-snapshots` is the act of making them: "
            "run it after RE-READING what changed, not to clear a red run."),
        "_generated_by": "python3 backend/tools/audit-citations.py --update-snapshots",
        "confirmed": dict(sorted(digests.items())),
    }
    with open(SNAPSHOTS, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    return len(digests)


def load_baseline():
    try:
        with open(BASELINE, encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return set()
    return set(data.get("accepted", {}))


def main():
    p = argparse.ArgumentParser(
        description="Check that file:line citations resolve (read-only).")
    p.add_argument("--all", action="store_true",
                   help="report baselined findings too")
    p.add_argument("--update-baseline", action="store_true",
                   help="rewrite the baseline from the current tree")
    p.add_argument("--update-snapshots", action="store_true",
                   help="re-confirm every cited line's content (see the file's "
                        "own _limit: do this after re-reading, not to clear red)")
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()

    if args.self_test:
        return _self_test()

    digests = {}
    findings = scan(digests)
    baseline = load_baseline()

    if args.update_baseline:
        _write_baseline(findings)
        print(f"citation-baseline.json rewritten: {len(findings)} accepted")
        return 0

    if args.update_snapshots:
        n = _write_snapshots(digests)
        print(f"citation-snapshots.json rewritten: {n} citation(s) confirmed")
        return 0

    snapshots = load_snapshots()
    drifted, unconfirmed = check_snapshots(digests, snapshots)
    orphaned = sorted(set(snapshots) - set(digests))

    fresh = [(k, d) for k, d in findings if k not in baseline]
    stale = [k for k in baseline if k not in {k for k, _ in findings}]

    if args.all:
        for _, d in findings:
            print(f"  {d}")
        print(f"\n{len(findings)} unresolvable citation(s), "
              f"{len(fresh)} of them new")
    else:
        for _, d in fresh:
            print(f"  {d}", file=sys.stderr)

    if stale:
        print(f"\n{len(stale)} baselined citation(s) now resolve and can be "
              f"dropped from citation-baseline.json:")
        for k in sorted(stale)[:20]:
            print(f"  {k}")

    for key, was, now in drifted:
        print(f"  DRIFTED {key}\n"
              f"          the cited line said {was}, now {now}", file=sys.stderr)

    if fresh:
        print(f"\n{len(fresh)} NEW unresolvable citation(s). Either fix the "
              f"citation, or -- if the target is a file deleted on 2026-08-02 "
              f"-- cite it as `git show refactor-freeze-2026-08-02:<path>`.",
              file=sys.stderr)
    if drifted:
        print(f"\n{len(drifted)} citation(s) whose target line CHANGED since it "
              f"was confirmed. Re-read each one: if it still says what the citing "
              f"text claims, run --update-snapshots; if it does not, fix the "
              f"citation. Do not run --update-snapshots to clear this.",
              file=sys.stderr)
    if unconfirmed:
        print(f"({len(unconfirmed)} citation(s) not yet confirmed -- not a "
              f"failure; --update-snapshots records them.)", file=sys.stderr)
    #: An orphan is a snapshot for a citation somebody DELETED, which is
    #: housekeeping and not drift. It is reported and never fails, for the
    #: reason the baseline key is built the way it is: a checker that goes red
    #: when you delete a paragraph teaches people to run the refresh reflexively,
    #: and the refresh is the one command in this tool that has to stay a
    #: deliberate act. The next --update-snapshots drops them.
    if orphaned:
        print(f"({len(orphaned)} snapshot(s) for citations that no longer "
              f"exist -- dropped by the next --update-snapshots.)",
              file=sys.stderr)
    if fresh or drifted:
        return 1

    if not args.all:
        print(f"citations ok: {len(findings)} known-drifted, 0 new")
    return 0


def _write_baseline(findings):
    payload = {
        "_comment": (
            "Citations that do not resolve and are ACCEPTED, so that new drift "
            "fails and old drift stays visible. Written by "
            "tools/audit-citations.py --update-baseline. This file is meant to "
            "SHRINK: every entry is a claim someone can no longer check. Do not "
            "add to it by hand to silence a finding -- fix the citation, or cite "
            "the deleted file as `git show refactor-freeze-2026-08-02:<path>`, "
            "which the checker allows by design."),
        "_why_these_are_here": (
            "Most name documents deleted on 2026-08-02, when 137 files under "
            "docs/ were removed after an audit found 168 places they "
            "contradicted the code. The prose citing them was left in place "
            "deliberately: rewriting every call site in one commit would be a "
            "large unreviewable diff, which is the move that produced the "
            "deleted documents in the first place. The registers they name -- "
            "DEFECTS.md, DECISIONS.md, API-CONTRACT-v1.md -- are all readable "
            "behind the refactor-freeze-2026-08-02 tag."),
        "_what_this_cannot_catch": (
            "A citation whose line number still resolves but whose target no "
            "longer says what the citing comment claims. The worked example is "
            "historical and is not in the working tree: `git show "
            "20ee7d0:backend/extract.py` line 404 vs lib/text.py, described in "
            "the tool's docstring. A green run means citations RESOLVE, not "
            "that they are RIGHT."),
        "accepted": {k: d for k, d in sorted(findings)},
    }
    with open(BASELINE, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def _self_test():
    """The regex, against the shapes it has to get right and wrong."""
    ok = True

    def check(text, expected, label):
        nonlocal ok
        got = [m.group(0) for m in CITATION.finditer(text)]
        if got != expected:
            print(f"  FAIL {label}: {got!r} != {expected!r}")
            ok = False
        else:
            print(f"  ok   {label}")

    check("see match.py:70 for the floor", ["match.py:70"], "path:line")
    check("see schema.py:774-787", ["schema.py:774-787"], "path:line-line")
    check("backend/lib/state.py", ["backend/lib/state.py"], "bare path")
    check("version 3.14 of python", [], "a version is not a path")
    check("`git show refactor-freeze-2026-08-02:docs/RUNBOOK.md`",
          ["docs/RUNBOOK.md"], "tag form still matches (span filter drops it)")

    text = "`git show refactor-freeze-2026-08-02:docs/RUNBOOK.md`"
    spans = _spans(text)
    m = next(CITATION.finditer(text))
    suppressed = any(s <= m.start() <= e + len(m.group(1)) for s, e in spans)
    print(f"  {'ok  ' if suppressed else 'FAIL'} tag form is suppressed")
    ok = ok and suppressed

    print("\nself-test:", "ok" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
