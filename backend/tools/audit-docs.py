#!/usr/bin/env python3
"""Check this repo's mechanically-checkable documentation rules and exit non-zero.

THIS FILE IS THE AUTHORITY FOR THE RULES IT CHECKS. It used to cite
`git show refactor-freeze-2026-08-02:docs/DOCS-POLICY.md`, deleted 2026-08-02 with the 137 documents it governed.
`.claude/CLAUDE.md`'s ceiling forbids a replacement document, and code that
enforces a rule is the right owner of the rule's text -- see
`docs/adr/0010-the-doc-layer-checks-citations-not-documents.md`, which also
decides which of the checks below survive.

WHY THIS EXISTS

A correct rule with no check decays at the speed of the surrounding work. That was
shown here twice: a rule with a script (`backend/tools/audit-doc-links.py`) held,
while a rule with only prose lost four documents to drift inside a day -- and then
on 2026-08-02 the 137 documents this file guarded were deleted for contradicting
the code in 168 places, and this file went with them.

WHAT THAT SECOND DELETION CHANGED, because it is the reason five checks are gone.
The layer was sized for 137 documents and twelve is what came back. Worse, none of
C1-C7 catches the drift the tree actually suffers, which is a citation that still
resolves and no longer says what the citing text claims. `docs/adr/0010` records
the measurement and the decision: keep the two checks that catch drift this repo
has really had, retire the rest, and spend the difference on
`backend/tools/audit-citations.py`, which now snapshots what each cited line said
when it was confirmed. Read that ADR before adding a check back here.

WHAT IS SCANNED

Every `.md` under `docs/`, plus the tracked documents outside it -- `README.md`,
`.claude/CLAUDE.md`, `TASKS.md` and `DEV_TASKS.md`. See `TRACKED_OUTSIDE_DOCS`,
which explains why the last two matter: they are the only `kind: rolling` files in
the repo, so before they were scanned C3 could not see a single one of the
documents it exists to check, and reported zero because it had not looked.

THE TWO CHECKS, AND THIS FILE IS THE AUTHORITY FOR BOTH

  C3  rolling is fresh   a `kind: rolling` document has not sat still while the
                         tree it describes moved. Threshold and its derivation are
                         at `ROLLING_STALE_COMMITS`.
  C4  one figure, owner  a figure declared in `config/doc-figures.json` appears
                         outside its owning document. A number a script can produce
                         is never typed into prose; the owner carries the command,
                         and every other mention cites rather than restates. A
                         ~~struck~~ figure is exempt, because struck-and-kept is the
                         correction form.

The identifiers C1, C2, C5, C6 and C7 are retired and not reused. The gaps keep
every citation written while they existed resolving, which is the rule `TASKS.md`
applies to `T-` numbers.

WHAT IS DELIBERATELY NOT CHECKED

Whether any sentence in any document is true. No script can check that, and a green
run here is a claim about freshness and figure ownership -- nothing more. The same
limit is stated, at more length and for the case that matters most, in
`backend/tools/audit-citations.py`: a snapshot proves a cited line has not changed
since someone confirmed it, never that the claim was right when they did.

CONTRACT, COPIED FROM audit-doc-links.py BECAUSE THAT IS THE ONE THAT WORKED

  - prints `file:line`, the problem, and the correct fix where exactly one is
    unambiguous
  - REFUSES TO GUESS when the fix is ambiguous. Guessing at a missing target is
    what produced a duplicate task 34
  - exits non-zero when anything fires
  - offline: no network, no database, no LLM, stdlib only. C3 shells out to `git`,
    which is local; if `git` is unavailable C3 reports nothing rather than failing

    python3 backend/tools/audit-docs.py                  # everything, exit 1 if any
    python3 backend/tools/audit-docs.py --check C4       # one check
    python3 backend/tools/audit-docs.py --emit-baseline  # the JSON in config/
"""

import argparse
import fnmatch
import importlib.util
import json
import os
import re
import subprocess
import sys

#: Repo root, from this file's own location rather than the working directory:
#: the suite runs this from `backend/`, a person runs it from the repo root, and
#: a pre-commit hook runs it from wherever the commit happened.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


#: C3's threshold, in commits landed on the subject tree since the rolling document
#: itself last moved.
#:
#: WHY 25. This repo's sessions are days, and a day lands 4, 5, 6, 6, 6, 12, 17, 28
#: or 47 commits (`git log --date=short --pretty=%ad | uniq -c`, 131 commits through
#: 2026-08-01) -- median 6, mean ~15. At 25 a rolling document that sat through a
#: median session is NOT flagged, and one that sat through roughly four of them is.
#: That is the intent of rule 4: catch a document that missed an entire session, not
#: nag about one that is a few commits behind.
#:
#: DELIBERATELY PERMISSIVE. This is the check with the highest false-positive risk in
#: the set, and a check that cries wolf is worse than no check because it teaches the
#: reflex that retires all the others. Tighten it only with a measurement.
ROLLING_STALE_COMMITS = 25

#: What C3 compares the document against, when the document does not say. A rolling
#: document may declare `subject:` in its frontmatter (a space- or comma-separated
#: list of paths); absent that, its subject is the whole repo, which is the most
#: permissive reading -- any commit at all counts as the subject moving.
ROLLING_DEFAULT_SUBJECT = "."


#: Fence open/close for skipping code blocks. Both ``` and ~~~, three or more.
FENCE = re.compile(r"^\s*(`{3,}|~{3,})")

#: C4's unit of a CLAIM, which is the sentence and not the physical line (task 46).
#:
#: The rows in doc-figures.json license a figure by a lookahead: a line that names
#: its metric, or cites the owning document, is compliant with rule 2 and rule 3's
#: corollary. That lookahead was scoped to the physical line, and `.claude/CLAUDE.md`
#: is hard-wrapped at ~88 columns, so a compliant sentence can put `94.8%` on one
#: line and the `agree2` that licenses it on the next. The prose satisfied the rule
#: exactly as written and C4 could not see it. Task 38's design was right against the
#: corpus it was measured on -- `docs/`, where no registered figure straddled a wrap;
#: widening the scanned set to the two roots is what moved the population.
#:
#: SENTENCE, NOT PARAGRAPH. Both clear the finding, and the sentence is the smaller
#: window: task 46 says in terms that if a widening clears anything real the answer is
#: a narrower rule and not a bigger one, so the narrowest unit that clears the false
#: positive is the one to take. Measured 2026-08-02 over docs/ plus the two roots, both
#: with the licence test of `figure_hits()`: the sentence licenses 3 lines, the
#: paragraph licenses 7. The extra 4 are licensed by a token in a DIFFERENT SENTENCE of
#: the same paragraph -- `docs/ingestion_tests/README.md:141` and `:172`,
#: `docs/archive/README.md:43` -- which is not a claim citing its metric, it is two
#: claims that happen to be adjacent.
#:
#: A boundary is `.`, `!` or `?` followed by whitespace. Nothing narrower survives
#: this corpus: `AUDIT.md`, `1,960`, `94.8%` and `docs/ingest/*.md` all carry a `.`
#: with a non-space after it, and requiring the space is what keeps them whole.
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")

#: A struck figure is not a restatement: struck-and-kept is the correction form
#: this repo uses, so the old number stays visible beside the new one (task 46).
#:
#: Rule 4 mandates struck-and-kept -- "tidying by deletion removes the only evidence a
#: number was ever wrong" -- and 235 struck spans across 48 documents under docs/ are
#: doing exactly that (measured 2026-08-02 with this regex; `grep -o '~~'` counts 470,
#: which is the same 235 spans seen as opening and closing markers -- a marker count is
#: not a span count and the two get quoted interchangeably).
#: `.claude/CLAUDE.md` then read `~~**1182** as of 2026-07-31~~`, and the sentence
#: around it existed to say the number was wrong. NO LINE NUMBER: that file has been
#: rewritten since and the struck text is gone, so the quoted string identifies the
#: case and a line number would only point somewhere arbitrary. A check
#: that reports a figure whose own sentence disowns it is penalising the behaviour the
#: policy requires, which is the one way to make people stop doing it.
#:
#: IMPLEMENTED BY MASKING, not by a second exemption list: the span is blanked to
#: spaces of the same length before the compliance test, so offsets are untouched and
#: a struck figure simply has nothing left to match. See `figure_hits()`.
STRIKETHROUGH = re.compile(r"~~(?!~).+?~~", re.S)


#: Which task in tranche seven clears each check's current findings. Written into
#: the generated baseline so that a non-empty baseline names an owner rather than
#: being an anonymous list of things somebody tolerated.
CLEARED_BY = {
    "C3": "no task; C3 had never fired, because until docs/adr/0010 widened "
          "scanned_files() it could not see either kind: rolling document",
    "C4": "task 38 -- one figure, one owner",
}

BASELINE_PATH = "backend/config/doc-policy-baseline.json"
FIGURES_PATH = "backend/config/doc-figures.json"


class Finding:
    """One rule violation.

    `key` is the baseline identity and is deliberately LINE-INDEPENDENT: it is the
    path plus a check-specific token, never a line number. A baseline keyed on line
    numbers goes stale the first time anyone edits the file above the finding, which
    is every single commit of tasks 37-40 -- and a baseline that goes stale on
    unrelated edits is a baseline that gets deleted rather than pruned.
    """

    def __init__(self, check, path, lineno, problem, fix=None, token=None):
        self.check = check
        self.path = path
        self.lineno = lineno
        self.problem = problem
        self.fix = fix
        self.key = path if token is None else f"{path}::{token}"

    def line(self):
        where = f"{self.path}:{self.lineno}" if self.lineno else self.path
        fix = f"  -> {self.fix}" if self.fix else "  -> no unambiguous fix"
        return f"{where}\t[{self.check}] {self.problem}{fix}"


# ---------------------------------------------------------------------------
# reading


def docs_files(root):
    """Every `.md` under `docs/`, repo-relative and sorted.

    Deliberately still means exactly what its name says. `scanned_files()` is what
    the checks read; keeping this one narrow is what makes the widening visible in
    the diff instead of hidden inside a walk.
    """
    out = []
    for dirpath, _, filenames in os.walk(os.path.join(root, "docs")):
        for name in filenames:
            if name.endswith(".md"):
                out.append(os.path.relpath(
                    os.path.join(dirpath, name), root).replace(os.sep, "/"))
    return sorted(out)



#: Documents this repo owns that do not live under `docs/`. Both checks read every
#: one of them.
#:
#: THIS REPLACED `ROOTS`, AND THE RENAME IS THE POINT. `ROOTS` meant "where
#: reachability starts", which was C2's question and only C2's; the tuple was then
#: reused as the scan set, so the two ideas were one name. `docs/adr/0010` retired
#: C2, and what is left is the second idea alone: documents this repo owns.
#:
#: `TASKS.md` AND `DEV_TASKS.md` ARE HERE FOR C3, AND THEIR ABSENCE IS WHY C3 WAS
#: DEAD. They are the only two files declaring `kind: rolling`, they hold every open
#: item in the repo, and they sit at the repo root -- outside `docs/`, and never in
#: `ROOTS` because nothing links to them, which is exactly what disqualified them as
#: reachability roots. So the check written to catch a stale rolling document could
#: not see either of the rolling documents, and reported zero findings for that
#: reason rather than because it had looked.
TRACKED_OUTSIDE_DOCS = ("README.md", ".claude/CLAUDE.md", "TASKS.md", "DEV_TASKS.md")


def scanned_files(root):
    """Everything the checks read: `docs/` plus the tracked files outside it.

    A path listed in `TRACKED_OUTSIDE_DOCS` that does not exist is skipped rather
    than reported. Nothing checks for its absence now that C2 is gone: a missing
    entry here is a mistake in this tuple, which is read by anyone editing it, and
    inventing a finding for it would be a check on this file rather than on the
    tree.
    """
    tracked = [rel for rel in TRACKED_OUTSIDE_DOCS
               if os.path.isfile(os.path.join(root, rel))]
    return docs_files(root) + sorted(tracked)


def read(root, rel):
    with open(os.path.join(root, rel), encoding="utf-8") as fh:
        return fh.read().splitlines()


def frontmatter(lines):
    """(dict, present). A leading `---` block of `key: value` pairs.

    Not a YAML parser and does not pretend to be one: stdlib only, and the only
    frontmatter this repo writes is flat scalars.
    """
    if not lines or lines[0].strip() != "---":
        return {}, False
    out = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return out, True
        if ":" in line and not line.startswith(" "):
            key, _, value = line.partition(":")
            out[key.strip()] = value.strip()
    return out, False  # unterminated block: not frontmatter


def outside_fences(lines):
    """Yield (lineno, text) for lines that are not inside a fenced code block."""
    fence = None
    for lineno, text in enumerate(lines, 1):
        m = FENCE.match(text)
        if m:
            marker = m.group(1)[0]
            if fence is None:
                fence = marker
                continue
            if fence == marker:
                fence = None
                continue
        if fence is None:
            yield lineno, text


def paragraphs(lines):
    """Yield [(lineno, text), ...] -- runs of consecutive non-blank unfenced lines.

    Built on `outside_fences()` rather than beside it, so C4's fence-skipping is the
    same fence-skipping every other check uses. A gap in the line numbers means a
    fenced block was skipped, and that ENDS the run: joining across a fence would let
    a shell transcript license the prose under it.
    """
    run, prev = [], None
    for lineno, text in outside_fences(lines):
        if not text.strip() or (prev is not None and lineno != prev + 1):
            if run:
                yield run
            run = []
        if text.strip():
            run.append((lineno, text))
        prev = lineno
    if run:
        yield run


def _joined(run):
    """(block, [(offset, lineno, text), ...]) for one paragraph.

    JOINED WITH A SPACE, NEVER WITH A NEWLINE, and this is the trap in the whole
    change. Every pattern in doc-figures.json uses `^` WITHOUT `re.MULTILINE` and
    `[^\\n]*`. Join on `\\n` and `^` still anchors only at the block's start while
    `[^\\n]*` confines BOTH the lookahead and the match to the block's first line --
    the check would report fewer findings and look fixed, while having gone blind to
    every figure that is not on a paragraph's first line. A space is what actually
    widens these regexes.
    """
    parts, placed, pos = [], [], 0
    for lineno, text in run:
        placed.append((pos, lineno, text))
        parts.append(text)
        pos += len(text) + 1
    return " ".join(parts), placed


def _mask(block):
    """`block` with every `~~struck~~` span blanked to spaces of the same length."""
    out = list(block)
    for m in STRIKETHROUGH.finditer(block):
        for i in range(m.start(), m.end()):
            out[i] = " "
    return "".join(out)


def _sentences(block, masked):
    """Yield (offset, masked_text) for each sentence of one paragraph.

    Split on the RAW block and slice the masked one at the same offsets: masking is
    length-preserving, and a `.` inside a struck span must still end a sentence.
    """
    start = 0
    for m in SENTENCE_END.finditer(block):
        yield start, masked[start:m.start()]
        start = m.end()
    yield start, masked[start:]


def figure_hits(pattern, lines):
    """Yield (lineno, match) for every occurrence of `pattern` that is a finding.

    THREE FILTERS, AND THE ORDER IS THE DESIGN.

      1. THE LINE MUST MATCH, on the raw text, exactly as before. This is the base
         set and it is unchanged, which is what makes this change incapable of
         inventing a finding -- see below, because task 46 asserts that for the wrong
         reason.
      2. THE FIGURE MUST NOT BE STRUCK. Per occurrence, by span containment on the
         match END: rule 4's struck-and-kept is a property of the number, not of the
         sentence around it, and a sentence may hold a struck figure beside a live one.
      3. THE ENCLOSING SENTENCE MUST STILL MATCH SOMEWHERE, on the masked text. This
         one is DELIBERATELY BINARY rather than per-occurrence. Eight of the nine rows
         license compliance with a `^(?!...)` lookahead; falsify it and the anchored
         pattern matches NOWHERE in that sentence, so "matches nowhere" is exactly
         "the sentence named its metric or cited its owner".

    WHY 3 IS BINARY, which cost a rewrite to learn. Matching the sentence per
    occurrence and intersecting on the end offset looks equivalent and is not:
    `[^\\n]*` is greedy, so where a sentence holds the same figure twice the sentence
    match lands on the LATER one and the earlier occurrence looks licensed. Measured
    2026-08-02, that silently cleared `docs/ingestion_tests/README.md:268` -- a real
    `85.7%` restatement in a gate table, licensed by nothing, shadowed by a second
    `85.7%` two lines down. A check cleared for that reason is the exact failure task
    46 warns about, arriving through the fix rather than through the bug.

    WHY AN INTERSECTION RATHER THAN A RE-SCOPE. Task 46 argues "widening a match can
    only ever CLEAR findings, never add them" and uses it to justify measuring only
    what the change clears. THAT IS FALSE FOR THESE PATTERNS. The webapp, labelling-
    rate and labelled-36 rows are PROXIMITY patterns -- `\\bwebapp\\b` within 60
    characters of `93`, `\\bai_involvement\\b` within 60 of `50%` -- and running one of
    those against a joined paragraph pairs a keyword on one line with a number on the
    next, which is a match that does not exist today. Measured 2026-08-02 over docs/
    plus the two roots: a naive paragraph re-scope of all nine patterns INVENTS 2
    matches while clearing 10.

    AND BOTH INVENTED MATCHES ARE REAL, which is the part worth the next reader's
    time. `git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_five/29-labelling-session.md:792` is the webapp suite count with `backend/webapp/`
    ending the line above it, and `git show refactor-freeze-2026-08-02:docs/tasks/refactor/LABELLING-NIGHT.md:508-509` is the labelling rate
    split as `93` / `s/posting` across the wrap. So the line scope has false NEGATIVES
    of exactly the shape it has false positives, and widening the match body would find
    two of them -- both in files these rows already allow, so neither is a finding
    today. That is a real follow-up with its own measurement and its own decision; it
    is not this change. Keeping the match line-scoped and widening only the LICENCE
    makes the new finding set a strict subset of the old one BY CONSTRUCTION, so the
    property task 46 assumes of the regexes becomes true of the implementation instead.
    """
    for run in paragraphs(lines):
        block, placed = _joined(run)
        masked = _mask(block)
        struck = [(m.start(), m.end()) for m in STRIKETHROUGH.finditer(block)]
        scopes = [(offset, offset + len(sentence), pattern.search(sentence) is not None)
                  for offset, sentence in _sentences(block, masked)]
        for offset, lineno, text in placed:
            for m in pattern.finditer(text):
                end = offset + m.end() - 1
                if any(a <= end < b for a, b in struck):
                    continue
                if any(a <= end <= b and live for a, b, live in scopes):
                    yield lineno, m



# ---------------------------------------------------------------------------
# the checks



def _git(root, args):
    try:
        proc = subprocess.run(["git"] + args, cwd=root, check=False,
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              text=True)
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None


def check_rolling(root, files):
    """C3 -- rolling documents are rolled forward or retired (rule 4).

    A `rolling` document answers "what do I do next". Rule 4 says it is rolled
    forward each session or archived in the commit that lands its subject. Nothing
    enforced that, and `HANDOFF.md`'s entry point went on sending fresh sessions to
    a task that had already finished -- with nothing red, because a document that
    stops being written looks exactly like a document with nothing to say.

    Needs `git`. If git is unavailable, or the document is untracked, this reports
    NOTHING rather than guessing: an unknown history is not evidence of staleness.
    """
    if _git(root, ["rev-parse", "--git-dir"]) is None:
        return

    for rel in files:
        fm, _ = frontmatter(read(root, rel))
        if fm.get("kind") != "rolling":
            continue
        doc = _git(root, ["log", "-1", "--format=%h %cs", "--", rel])
        if not doc:
            continue
        doc_sha, doc_date = doc.split()[0], doc.split()[1]
        subjects = [s for s in re.split(r"[,\s]+",
                                        fm.get("subject", ROLLING_DEFAULT_SUBJECT))
                    if s]
        for subject in subjects:
            behind = _git(root, ["rev-list", "--count",
                                 f"{doc_sha}..HEAD", "--", subject])
            if behind is None or int(behind) < ROLLING_STALE_COMMITS:
                continue
            head = _git(root, ["log", "-1", "--format=%h %cs", "--", subject])
            head_sha, head_date = head.split()[0], head.split()[1]
            yield Finding(
                "C3", rel, 1,
                f"rolling, last written {doc_date} ({doc_sha}), but its subject "
                f"{subject!r} has moved {behind} times since -- latest {head_date} "
                f"({head_sha}), threshold {ROLLING_STALE_COMMITS}",
                "roll it forward, or archive it per docs/archive/README.md",
                token=f"stale:{subject}")


def load_figures(root):
    with open(os.path.join(root, FIGURES_PATH), encoding="utf-8") as fh:
        return json.load(fh)


def check_figures(root, files):
    """C4 -- an owned figure is not copied (rules 2 and 3).

    SCOPED HONESTLY. A general duplicate-number detector is not possible and is not
    attempted. This checks a DECLARED list in config/doc-figures.json, it will never
    be complete, and the declaration is as much the deliverable as the code is.

    THE UNIT OF THE CLAIM IS THE SENTENCE, and a struck figure is not a restatement.
    Both live in `figure_hits()`, with the reasoning at `SENTENCE_END` and
    `STRIKETHROUGH`.
    """
    figures = load_figures(root).get("figures", [])
    for fig in figures:
        pattern = re.compile(fig["pattern"])
        owner = fig["owner"]
        allowed = fig.get("allowed", [])
        for rel in files:
            if rel == owner:
                continue
            if any(fnmatch.fnmatch(rel, pat) for pat in allowed):
                continue
            for lineno, m in figure_hits(pattern, read(root, rel)):
                yield Finding(
                    "C4", rel, lineno,
                    f"{fig['name']!r} ({m.group(0)!r}) is owned by {owner}",
                    f"cite {owner} instead of restating the number",
                    token=f"figure:{fig['name']}")
                break  # one finding per file per figure; the CLI line names the first



#: THE GAPS ARE DELIBERATE. C1, C2, C5, C6 and C7 were retired by
#: `docs/adr/0010`; their identifiers are not reused and the survivors are not
#: renumbered, so `config/doc-policy-baseline.json`, the ADR and every citation
#: written while they existed keep resolving. This is the same rule `TASKS.md`
#: applies to `T-` numbers, for the same reason.
CHECKS = ("C3", "C4")


def run_checks(root=REPO_ROOT, only=None):
    """(findings, allowed). The entry point the suite calls.

    `allowed` is always empty now and the second element is kept anyway: it was
    C2's declared-orphan list, and C4 can grow an allowance of the same shape --
    `load_figures()` already reads one. Callers unpack two values.
    """
    files = scanned_files(root)
    wanted = set(only or CHECKS)
    findings, allowed = [], []
    if "C3" in wanted:
        findings += list(check_rolling(root, files))
    if "C4" in wanted:
        findings += list(check_figures(root, files))
    findings.sort(key=lambda f: (f.check, f.path, f.lineno or 0))
    return findings, allowed


# ---------------------------------------------------------------------------
# baseline


BASELINE_COMMENT = (
    "The findings audit-docs.py reports on the tree AS IT STOOD when this file was "
    "generated, keyed by check and by a line-independent identity. "
    "backend/tests/test_docs_policy.py asserts the current finding set is a SUBSET of "
    "this one: clearing a finding keeps the suite green, and a NEW finding turns it "
    "red. Generated by `python3 backend/tools/audit-docs.py --emit-baseline`, never "
    "by hand -- a hand-written baseline is a claim about what the checker does; a "
    "generated one is evidence of what it did."
)

BASELINE_WHY = (
    "Task 36 requires two things that conflict: the checker LANDS RED, because a "
    "checker whose first run is green has been tested against nothing, and both "
    "suites stay green, because that is every later wave's gate. Wiring a red checker "
    "into `unittest discover` makes a red suite. This file resolves it without "
    "weakening either: the CLI still exits non-zero today, which is what task 36's "
    "Definition of done checks, while the suite gates on regression rather than on "
    "the absolute count. "
    "A NON-EMPTY BASELINE IS A TEMPORARY STATE WITH AN OWNER -- every check below "
    "names the task that clears it, tasks 37-40 prune it as they land, and phase 9 "
    "exits when `findings` is empty everywhere. Rejected: exempting docs/ from the "
    "checks until they pass, which is the same tolerance with no list, no owner and "
    "no way to notice it growing."
)


def emit_baseline(findings):
    checks = {}
    for check in CHECKS:
        keys = sorted({f.key for f in findings if f.check == check})
        checks[check] = {
            "_cleared_by": CLEARED_BY[check],
            "count": len(keys),
            "findings": keys,
        }
    return {
        "_comment": BASELINE_COMMENT,
        "_why": BASELINE_WHY,
        "_generated": "2026-08-01",
        "_generated_by": "python3 backend/tools/audit-docs.py --emit-baseline",
        "_identity": (
            "A key is `path` or `path::token`, never a line number. Line numbers "
            "move on every edit above the finding, which is every commit of tasks "
            "37-40; a baseline that goes stale on unrelated edits gets deleted "
            "rather than pruned."
        ),
        "checks": checks,
    }


def load_baseline(root=REPO_ROOT):
    with open(os.path.join(root, BASELINE_PATH), encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------


EPILOG = """scanned: every .md under docs/, PLUS the tracked files outside it --
README.md, .claude/CLAUDE.md, TASKS.md and DEV_TASKS.md. See TRACKED_OUTSIDE_DOCS.

the checks, both of them by name:

  C3  rolling is fresh    a kind: rolling document whose subject tree has moved
                          more than ROLLING_STALE_COMMITS times since the document
                          itself last did
  C4  one figure, one     a figure in backend/config/doc-figures.json matched
      owner               outside its owning document
                          a row's compliance lookahead is satisfied by the whole
                          SENTENCE, not the physical line, and a ~~struck~~ figure
                          is exempt, because struck-and-kept is the correction form

C1, C2, C5, C6 and C7 were retired by docs/adr/0010 -- read it before adding a
check back. The identifiers are not reused, so the numbering has gaps on purpose.
"""


def main(argv):
    parser = argparse.ArgumentParser(
        prog="audit-docs.py",
        description="Check this repo's mechanically-checkable documentation rules.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=REPO_ROOT,
                        help="repo root (default: derived from this script's path)")
    parser.add_argument("--check", default=None,
                        help="comma-separated subset, e.g. --check C4")
    parser.add_argument("--emit-baseline", action="store_true",
                        help=f"print {BASELINE_PATH} for the tree as it stands")
    args = parser.parse_args(argv[1:])

    only = None
    if args.check:
        only = [c.strip().upper() for c in args.check.split(",") if c.strip()]
        unknown = [c for c in only if c not in CHECKS]
        if unknown:
            parser.error(f"unknown check(s): {', '.join(unknown)}")

    if not os.path.isdir(os.path.join(args.root, "docs")):
        print(f"no docs/ under {args.root}", file=sys.stderr)
        return 2

    findings, allowed = run_checks(args.root, only)

    if args.emit_baseline:
        print(json.dumps(emit_baseline(findings), indent=2))
        return 0

    for finding in findings:
        print(finding.line())

    print("", file=sys.stderr)
    for check in CHECKS:
        if only and check not in only:
            continue
        n = sum(1 for f in findings if f.check == check)
        print(f"{check}: {n} finding(s)", file=sys.stderr)
    scope = ", ".join(["docs/"] + list(TRACKED_OUTSIDE_DOCS))
    print(f"\n{len(findings)} finding(s) under {args.root} ({scope})",
          file=sys.stderr)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
