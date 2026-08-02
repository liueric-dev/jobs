#!/usr/bin/env python3
"""Check the six mechanically-checkable rules of `docs/DOCS-POLICY.md` and exit non-zero.

WHY THIS EXISTS

Two documentation rules were written in this repo by careful people, in the same
task (34). One had a script -- `backend/tools/audit-doc-links.py` -- and holds.
The other, "dispositions go by document type", had only prose, and four documents
drifted out from under it inside a day. That is the whole argument: a correct rule
with no check decays at the speed of the surrounding work.

The argument is weaker than it first looks, and the deliverable is shaped by the
weakness. `audit-doc-links.py` is wired into nothing -- no test, no git hook, no CI
(verified 2026-08-01). It has held for one day, and only because a person typed the
command. A script nobody runs automatically is exactly one step better than prose.
So this file is not "another tool in tools/": it is a checker that fails a suite
someone is already running, and `backend/tests/test_docs_policy.py` wires in both
this script and `audit-doc-links.py`.

WHAT IS SCANNED

Every `.md` under `docs/`, PLUS the declared reachability roots that live outside
it -- `README.md` and `.claude/CLAUDE.md`. Task 36 scoped this to `docs/` and said
widening was a later call; `AUDIT.md` s "What is open" and `DOCS-POLICY.md` rule 7
then named the hole precisely: those two files were roots for C2 and were read by
NO other check, C4 included, while both carry figures. They are also the two most-
read documents in the repo -- `.claude/CLAUDE.md` is the first thing every session
opens. A figure there was on the honour system, checked by a `grep` in one task's
Definition of done that a person has to remember to run, which is the exact thing
rule 7 says is one step better than prose. See `scanned_files()`.

THE SIX CHECKS

  C1  kind declared      every scanned `.md` has frontmatter with a `kind:` in
                         {contract, rationale, record, rolling, task}   (rule 1)
  C2  no orphans         every `.md` under docs/ is reachable by relative link,
                         transitively, from a declared root                (rule 1)
  C3  rolling is fresh   a `kind: rolling` document has not sat still while the
                         tree it describes moved                           (rule 4)
  C4  one figure, owner  a figure declared in config/doc-figures.json appears
                         outside its owning document                  (rules 2, 3)
  C5  register prefixes  `D<n>` is defined only in docs/ingest/DEFECTS.md, `DEC-<n>`
                         only in DECISIONS.md, and no identifier is defined twice
                         inside one register                              (rule 6)
  C6  archive provenance every file under docs/archive/ opens with a header giving
                         a date and what superseded it                    (rule 4)

Rule 5 -- "promote durable content out of bound contexts" -- is NOT checked and
cannot be. It turns on whether a sentence would still be true for a different
cohort, model or product, which is a judgement about meaning. `DOCS-POLICY.md`
rule 7 requires such a rule to be documented as unenforced; this paragraph is that
documentation.

WHAT IS DELIBERATELY NOT CHECKED

Whether a `rationale` entry is any good. Whether a `record` is interesting.
Whether any sentence in any document is true. No script can check those, and a
green tick here is a claim about frontmatter, links and identifiers -- nothing
more. `AUDIT.md` s "How to audit this run in an hour" exists precisely because
passing a mechanical check is not the same as being right.

CONTRACT, COPIED FROM audit-doc-links.py BECAUSE THAT IS THE ONE THAT WORKED

  - prints `file:line`, the problem, and the correct fix where exactly one is
    unambiguous
  - REFUSES TO GUESS when the fix is ambiguous. Guessing at a missing target is
    what produced a duplicate task 34
  - exits non-zero when anything fires
  - offline: no network, no database, no LLM, stdlib only. C3 shells out to `git`,
    which is local; if `git` is unavailable C3 reports nothing rather than failing

    python3 backend/tools/audit-docs.py                  # everything, exit 1 if any
    python3 backend/tools/audit-docs.py --check C5       # one check
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

#: The five kinds of `DOCS-POLICY.md` rule 1. Each has exactly one lifecycle; the
#: list is closed, because "some other kind" is how a taxonomy stops being one.
VALID_KINDS = ("contract", "rationale", "record", "rolling", "task")

#: Where reachability starts, for C2. Declared, never inferred -- an inferred root
#: is just "the file with the most inbound links", which would let a whole
#: disconnected island of documents vouch for itself. `docs/README.md` does not
#: exist yet; task 37 creates it, and until then C2 reports the missing root.
ROOTS = ("README.md", "docs/README.md", ".claude/CLAUDE.md")

#: Documents that nothing links to ON PURPOSE. An explicit list, not a pattern:
#: "we decided this orphan is fine" is exactly the kind of decision that has to be
#: written down where the next reader sees it.
DELIBERATE_ORPHANS = {
    "docs/tasks/refactor/tranche_six/34-documentation-cleanup.md":
        "the pointer stub task 34 left behind when its content moved to "
        "../34-documentation-cleanup.md. Being unlinked is the point of the file: "
        "it exists so an old citation to this path still lands somewhere.",
}

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

#: C5's two registers and the ID prefix each one owns, per `DOCS-POLICY.md` rule 6.
#: A definition is a HEADING IN ONE OF THESE FILES and nothing else. Everything
#: everywhere else -- `### D16: the buckets KeyError` in `docs/score-validation.md`,
#: the headings in the task files that FIX defects, a heading quoted inside a fenced
#: block -- is discussion, and discussion is not checked. A prototype without this
#: restriction flagged four such lines on 2026-08-01, three of them in the files
#: written to satisfy this very check. A check that fires on the documents written
#: to satisfy it is a check that gets switched off in week one.
REGISTERS = {
    "docs/ingest/DEFECTS.md": "D",
    "docs/tasks/refactor/DECISIONS.md": "DEC",
}

#: A register identifier at the very start of a heading: `## D45 - ...`,
#: `### DEC-66 - ...`. Anchored at the start deliberately, so that
#: `### Defect D45 - ...` -- the disambiguating form task 39 proposes -- is prose
#: naming a defect, not a second definition of it.
HEADING_ID = re.compile(r"^#{1,6}\s+\*{0,2}(DEC-\d+|D\d+)\b")

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

#: A struck figure is not a restatement (task 46, and `DOCS-POLICY.md` rule 4).
#:
#: Rule 4 mandates struck-and-kept -- "tidying by deletion removes the only evidence a
#: number was ever wrong" -- and 235 struck spans across 48 documents under docs/ are
#: doing exactly that (measured 2026-08-02 with this regex; `grep -o '~~'` counts 470,
#: which is the same 235 spans seen as opening and closing markers -- a marker count is
#: not a span count and the two get quoted interchangeably).
#: `.claude/CLAUDE.md:190` reads `~~**1182** as of
#: 2026-07-31~~` and the sentence around it exists to say the number was wrong. A check
#: that reports a figure whose own sentence disowns it is penalising the behaviour the
#: policy requires, which is the one way to make people stop doing it.
#:
#: IMPLEMENTED BY MASKING, not by a second exemption list: the span is blanked to
#: spaces of the same length before the compliance test, so offsets are untouched and
#: a struck figure simply has nothing left to match. See `figure_hits()`.
STRIKETHROUGH = re.compile(r"~~(?!~).+?~~", re.S)

#: C6: a provenance header is a blockquote in the opening lines of the file that
#: carries a date and says what superseded it. The prose inside it is not checked --
#: only that all three components are present.
ARCHIVE_HEADER_LINES = 12
ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
SUPERSEDE_WORDS = re.compile(
    r"\b(archived|superseded|supersedes|replaced|moved|split)\b", re.I)

#: Which task in tranche seven clears each check's current findings. Written into
#: the generated baseline so that a non-empty baseline names an owner rather than
#: being an anonymous list of things somebody tolerated.
CLEARED_BY = {
    "C1": "task 37 -- classify every document with a kind: in frontmatter",
    "C2": "task 37 -- docs/README.md, the index that reaches the unreached files",
    "C3": "no task; C3 finds nothing today because nothing declares kind: rolling",
    "C4": "task 38 -- one figure, one owner",
    "C5": "task 39 -- split the D namespace, D46-D65 become DEC-46-DEC-65",
    "C6": "no task; C6 finds nothing today",
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


def external_roots(root):
    """The declared roots that live outside `docs/`, and that exist.

    DERIVED FROM `ROOTS`, NEVER A SECOND LIST. A second list would be a figure
    copied to two places, which is the rule this script checks. The set is exactly
    "declared root, not under docs/": today `README.md` and `.claude/CLAUDE.md`.

    A root that does not exist is skipped here and reported by C2 as
    `missing-root`, which is where that finding already lives. Reporting it twice
    would make one missing file two findings and two fixes.
    """
    return sorted(rel for rel in ROOTS
                  if not rel.startswith("docs/")
                  and os.path.isfile(os.path.join(root, rel)))


def scanned_files(root):
    """Everything the checks read: `docs/` plus the external declared roots.

    WHY THE ROOTS ARE IN, AND WHAT IT COSTS. `AUDIT.md` s "What is open" states the
    gap this closes and states it as a rule 7 gap rather than an oversight. The two
    files are read more than anything under `docs/` and are edited by every session,
    which is the combination that makes an unchecked figure spread.

    NOT EVERY CHECK USES THIS SET, and the exceptions are properties of the checks
    rather than exemptions for the files:

      C1  yes. Rule 1 says EVERY document declares its kind, and these two are
          documents -- `.claude/CLAUDE.md` is a `contract` by every line of rule 1's
          table (edited in place, a stale line in it is a defect, and it already
          carries struck-and-kept corrections).
      C2  no -- a root cannot be an orphan. Reachability is defined FROM these
          files; asking whether they are reached is a category error, and
          `check_orphans()` reads `ROOTS` directly for that reason.
      C3  yes, and it finds nothing: neither root declares `kind: rolling`. It is in
          so that marking one `rolling` later is checked without a code change.
      C4  yes, and this is the whole point of the widening.
      C5  unaffected. It reads the two register files named in `REGISTERS`.
      C6  unaffected. It reads `docs/archive/` only.
    """
    return docs_files(root) + external_roots(root)


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
    time. `29-labelling-session.md:792` is the webapp suite count with `backend/webapp/`
    ending the line above it, and `LABELLING-NIGHT.md:508-509` is the labelling rate
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


def link_grammar():
    """`targets()` and `SKIP` from audit-doc-links.py, loaded rather than copied.

    One definition of the link grammar, two callers. Duplicating the regexes here
    would mean a fix to one checker silently not reaching the other, which is the
    same failure mode as a figure copied into two documents.
    """
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "audit-doc-links.py")
    spec = importlib.util.spec_from_file_location("audit_doc_links", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# the checks


def check_kind(root, files):
    """C1 -- every document declares a valid `kind:` (rule 1)."""
    declared = {}
    for rel in files:
        fm, _ = frontmatter(read(root, rel))
        if fm.get("kind") in VALID_KINDS:
            declared[rel] = fm["kind"]

    #: A directory whose declaring files all agree gives an unambiguous suggestion.
    #: Where they disagree, or where none declares, there is no suggestion and the
    #: check says so -- task 37 makes that call, not this script.
    by_dir = {}
    for rel, kind in declared.items():
        by_dir.setdefault(os.path.dirname(rel), set()).add(kind)

    for rel in files:
        if rel in declared:
            continue
        lines = read(root, rel)
        fm, present = frontmatter(lines)
        if not present:
            problem = "no frontmatter block"
        elif "kind" not in fm:
            problem = "frontmatter has no `kind:` key"
        else:
            problem = (f"kind: {fm['kind']!r} is not one of "
                       f"{', '.join(VALID_KINDS)}")
        siblings = by_dir.get(os.path.dirname(rel), set())
        fix = None
        if len(siblings) == 1:
            fix = (f"siblings in {os.path.dirname(rel)}/ all declare "
                   f"kind: {next(iter(siblings))}")
        yield Finding("C1", rel, 1, problem, fix)


def outbound(root, rel, links):
    """Repo-relative `.md` targets of every relative link in one document."""
    base = os.path.dirname(rel)
    out = []
    for _, text in outside_fences(read(root, rel)):
        for target in links.targets(text):
            if links.SKIP.match(target):
                continue
            bare = target.split("#")[0]
            if not bare.endswith(".md"):
                continue
            nxt = os.path.normpath(os.path.join(base, bare)).replace(os.sep, "/")
            if nxt != rel and os.path.isfile(os.path.join(root, nxt)):
                out.append(nxt)
    return out


def check_orphans(root, files):
    """C2 -- every document is reached from a declared root (rule 1).

    `audit-doc-links.py` proves every link RESOLVES. Nothing proved every file was
    REACHED, and a file nothing links to has no broken link for a resolver to find.
    This is the check that would have caught the duplicate task 34 on the day it was
    written: it was tracked, invisible, and asserting a claim its visible twin
    existed to retire.

    TWO TIERS, AND THE DIFFERENCE MATTERS.

      `orphan`    in-degree zero. NOTHING links to it. This is the defect above,
                  exactly, and it is what a reader can never stumble into.
      `unreached` something links to it, but no path of relative links runs to it
                  from a declared root. A cluster of documents citing each other
                  is not reachability -- an island can vouch for itself all day.

    Both are C2 and both exit non-zero, because rule 1 asks for reachability and
    reachability is transitive from the roots. They are separate tokens because
    they have separate fixes and separate sizes: 11 orphans against 95 unreached
    today, and the 95 is almost entirely ONE missing file. `docs/README.md`, the
    declared root task 37 creates, does not exist, so the only live entry into the
    tree is the root `README.md` -- which links to `docs/ingest/` and `docs/tasks/`
    as DIRECTORIES. A link to a directory reaches no file in it, and that is not a
    quibble: it is why the root README can call docs/ingest/ "the per-script
    reference for all eleven entry points" while seven of those eleven have no
    inbound link at all.

    Returns (findings, allowed), where `allowed` names the deliberate orphans that
    were found and skipped -- reported rather than silently dropped, because an
    allowance nobody can see is indistinguishable from a check that stopped working.
    """
    links = link_grammar()
    findings, allowed = [], []

    roots = []
    for rel in ROOTS:
        if os.path.exists(os.path.join(root, rel)):
            roots.append(rel)
        else:
            findings.append(Finding(
                "C2", rel, None, "declared reachability root does not exist",
                "create it, or drop it from ROOTS in this script",
                token="missing-root"))

    inbound = {rel: [] for rel in files}
    for rel in files + roots:
        for nxt in outbound(root, rel, links):
            if nxt in inbound:
                inbound[nxt].append(rel)

    reached, queue = set(roots), list(roots)
    while queue:
        for nxt in outbound(root, queue.pop(), links):
            if nxt not in reached:
                reached.add(nxt)
                queue.append(nxt)

    for rel in files:
        if rel in reached:
            continue
        if rel in DELIBERATE_ORPHANS:
            allowed.append(rel)
            continue
        sources = sorted(set(inbound[rel]))
        if not sources:
            findings.append(Finding(
                "C2", rel, 1,
                "orphan: no document anywhere links to it", None, token="orphan"))
            continue
        #: Where exactly one document links here, that document is the whole chain
        #: and naming it is unambiguous -- the fix is to reach IT. Where several do,
        #: this refuses to pick one, per the contract inherited from
        #: audit-doc-links.py.
        fix = (f"linked only from {sources[0]}, which is itself unreached; "
               "connect that document to a root" if len(sources) == 1 else None)
        findings.append(Finding(
            "C2", rel, 1,
            f"unreached: {len(sources)} inbound link(s), but no path from "
            f"{' / '.join(ROOTS)}", fix, token="unreached"))
    return findings, allowed


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


def check_registers(root, files):
    """C5 -- register prefixes do not collide (rule 6).

    A DEFINITION IS A HEADING IN A REGISTER FILE. See REGISTERS above for why that
    restriction is the whole difficulty of this check.
    """
    for register, prefix in REGISTERS.items():
        if not os.path.isfile(os.path.join(root, register)):
            yield Finding("C5", register, None, "declared register file is missing",
                          None, token="missing-register")
            continue
        seen = {}
        for lineno, text in outside_fences(read(root, register)):
            m = HEADING_ID.match(text)
            if not m:
                continue
            ident = m.group(1)
            got, number = ident.split("-") if "-" in ident else (ident[0], ident[1:])
            #: Wrong-register and defined-twice are reported INDEPENDENTLY, not as
            #: an if/elif. `DECISIONS.md` currently holds two `### D45` headings:
            #: each is in the wrong register AND together they are a collision, and
            #: an elif would report the second as merely foreign and lose the fact
            #: that D45 resolves to two different entries -- which is the ambiguity
            #: rule 6 exists to prevent, and it has already propagated into
            #: backend/tools/ats-discover.py.
            if got != prefix:
                other = [f for f, p in REGISTERS.items() if p == got]
                #: NO SUGGESTED FIX HERE, DELIBERATELY. An earlier version emitted
                #: "re-prefix this heading to DEC-45", which is an identifier the
                #: allocator forbids: DECISIONS.md's own allocator header starts at
                #: DEC-46 because DEFECTS.md burns 46-65, so DEC-45 can never exist.
                #: A checker that suggests an ID the allocator refuses to issue is
                #: worse than one that refuses to guess -- the reader either follows
                #: it and creates a collision, or learns to distrust every other
                #: suggestion the tool makes. The fix is genuinely ambiguous: the
                #: heading is either a decision needing a FRESH id from the allocator
                #: (never the same number) or a section ABOUT the other register's
                #: entry, which is retitled `### Defect D45 - ...` and stays. Naming
                #: both readings and picking neither is what rule 7 asks for.
                yield Finding(
                    "C5", register, lineno,
                    f"{ident} is defined here, but the {got!r} prefix belongs to "
                    f"{other[0] if other else 'another register'}. Either allocate a "
                    f"FRESH {prefix} id from this file's allocator header -- not "
                    f"{prefix}-{number}, which the allocator does not issue -- or "
                    f"retitle it as a cross-reference, which is not a definition",
                    None, token=f"foreign:{ident}")
            if ident in seen:
                yield Finding(
                    "C5", register, lineno,
                    f"{ident} is defined twice in this register "
                    f"(first at line {seen[ident]})",
                    None, token=f"duplicate:{ident}")
            else:
                seen[ident] = lineno


def check_archive(root, files):
    """C6 -- archived files carry provenance (rule 4).

    `docs/archive/README.md` requires this in prose and it has never been checked:
    a file in an archive with no provenance is worse than one left in place, because
    the reader cannot tell whether they are holding the current answer.

    `docs/archive/README.md` itself is exempt -- it is the directory's index, not an
    archived document, and it is what states the rule.

    Checks the SHAPE of the header, never the prose: a blockquote in the opening
    lines carrying a date and a word that says what happened to it. Whether the
    sentence is accurate is one of the things named as unchecked at the top of
    this file.
    """
    for rel in files:
        if not rel.startswith("docs/archive/") or rel == "docs/archive/README.md":
            continue
        head = "\n".join(read(root, rel)[:ARCHIVE_HEADER_LINES])
        quoted = "\n".join(l for l in head.splitlines() if l.lstrip().startswith(">"))
        missing = []
        if not quoted:
            missing.append("a provenance blockquote")
        if not ISO_DATE.search(quoted):
            missing.append("a date")
        if not SUPERSEDE_WORDS.search(quoted):
            missing.append("what superseded it")
        if missing:
            yield Finding(
                "C6", rel, 1,
                "no provenance header: missing " + ", ".join(missing),
                "add the header docs/archive/README.md requires: what it measured, "
                "when, and what superseded it", token="provenance")


CHECKS = ("C1", "C2", "C3", "C4", "C5", "C6")


def run_checks(root=REPO_ROOT, only=None):
    """(findings, allowed). The entry point the suite calls."""
    #: Two sets, and the difference is one line of meaning: C2 asks whether a
    #: document is REACHED, and the roots are what it is reached from. Everything
    #: else asks a question about the document itself, which the roots are not
    #: exempt from. See `scanned_files()`.
    files = scanned_files(root)
    reachable = docs_files(root)
    wanted = set(only or CHECKS)
    findings, allowed = [], []
    if "C1" in wanted:
        findings += list(check_kind(root, files))
    if "C2" in wanted:
        got, allowed = check_orphans(root, reachable)
        findings += got
    if "C3" in wanted:
        findings += list(check_rolling(root, files))
    if "C4" in wanted:
        findings += list(check_figures(root, files))
    if "C5" in wanted:
        findings += list(check_registers(root, files))
    if "C6" in wanted:
        findings += list(check_archive(root, files))
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


EPILOG = """scanned: every .md under docs/, PLUS the declared roots outside it --
README.md and .claude/CLAUDE.md. C2 exempts them because a root cannot be an orphan;
C5 and C6 read their own fixed file sets. See scanned_files() for the rest.

the checks, all six by name:

  C1  kind declared       every scanned .md declares kind: in frontmatter, one
                          of contract, rationale, record, rolling, task  (rule 1)
  C2  no orphans          every .md under docs/ is reachable by relative link,
                          transitively, from a declared root; deliberate orphans
                          are an explicit allowance and are reported as allowed
  C3  rolling is fresh    a kind: rolling document whose subject tree has moved
                          more than ROLLING_STALE_COMMITS times since the document
                          itself last did                                (rule 4)
  C4  one figure, one     a figure in backend/config/doc-figures.json matched
      owner               outside its owning document                (rules 2, 3)
                          a row's compliance lookahead is satisfied by the whole
                          SENTENCE, not the physical line, and a ~~struck~~ figure
                          is exempt: rule 4 asks for struck-and-kept  (task 46)
  C5  register prefixes   D<n> defined outside docs/ingest/DEFECTS.md, DEC-<n>
                          outside DECISIONS.md, or an identifier defined twice in
                          one register                                   (rule 6)
  C6  archive provenance  a file under docs/archive/ whose opening lines carry no
                          provenance header                              (rule 4)

not checked: rule 5 (promotion of durable content) needs a judgement about meaning.
Nor is whether a rationale entry is good, a record interesting, or any sentence in
any document true.
"""


def main(argv):
    parser = argparse.ArgumentParser(
        prog="audit-docs.py",
        description="Check the mechanically-checkable rules of docs/DOCS-POLICY.md.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=REPO_ROOT,
                        help="repo root (default: derived from this script's path)")
    parser.add_argument("--check", default=None,
                        help="comma-separated subset, e.g. --check C5,C6")
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
    for rel in allowed:
        print(f"allowed: {rel}\n         {DELIBERATE_ORPHANS[rel]}", file=sys.stderr)
    for check in CHECKS:
        if only and check not in only:
            continue
        n = sum(1 for f in findings if f.check == check)
        print(f"{check}: {n} finding(s)", file=sys.stderr)
    scope = ", ".join(["docs/"] + list(external_roots(args.root)))
    print(f"\n{len(findings)} finding(s) under {args.root} ({scope})",
          file=sys.stderr)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
