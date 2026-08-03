#!/usr/bin/env python3
"""Cut the Verify phase and tell the synthesizer the truth about it.

With the skeptic fan-out at zero, `disagreements_confirmed` and
`disagreements_refuted` are both empty and everything lands in
`disagreements_unverified`. The synthesis prompt as written asserts that
skeptics vetted the findings, which would be false and would get unverified
claims written up as confirmed ones. Both are patched here.
"""
import pathlib
import sys

p = pathlib.Path('/home/eric/apps/jobs/.claude/workflows/orientation-phase2.js')
s = p.read_text()
orig_len = len(s)


def sub(old, new, label):
    global s
    assert s.count(old) == 1, f'{label}: expected 1 occurrence, found {s.count(old)}'
    s = s.replace(old, new)
    print(f'  patched: {label}')


# 1. The cap itself.
sub('.slice(0, 12)', '.slice(0, 0)   // Verify phase CUT for cost — see the synthesis brief',
    'verify cap 12 -> 0')

# 2. The overflow note, which now covers everything rather than a tail.
sub(
    "  log(`NOTE: ${allDisagreements.length - toVerify.length} low-severity or overflow disagreements are reported UNVERIFIED and labelled as such. Nothing was silently dropped.`)",
    "  log(`NOTE: the adversarial Verify phase was CUT for cost. All ${allDisagreements.length - toVerify.length} disagreements are reported UNVERIFIED and labelled as such. Nothing was silently dropped.`)",
    'overflow log message')

# 3. The synthesis brief's claim that skeptics filtered the findings.
sub(
    """adversarially against what the code says. Disagreements were then handed to skeptics instructed
to refute them; only survivors are in \\`disagreements_confirmed\\`.""",
    """adversarially against what the code says.

**The adversarial Verify phase was CUT for cost and did not run.** No skeptic examined any of
these disagreements. \\`disagreements_confirmed\\` and \\`disagreements_refuted\\` are therefore both
EMPTY, and every candidate is in \\`disagreements_unverified\\`. This is a fact about the method and
it must be visible in the report, not buried: a reader who treats these as vetted will act on a
finding no second reader ever checked. Section 0 must state it and section 5 must be built
entirely out of the unverified list.""",
    'synthesis brief: skeptic claim')

# 4. Section 5's structure, which assumed a confirmed/refuted split.
sub(
    """**5. What the documents claim that the code does not support** — the confirmed disagreement
   list, ordered by severity, each with the doc quote, the code citation, and the verifier's
   note. Then a short subsection of the UNVERIFIED candidates, clearly labelled as unverified so
   nobody acts on them as if they were checked. Then the refuted candidates in one line each, so
   the next session does not re-raise them. Give the counts.""",
    """**5. What the documents claim that the code does not support** — every disagreement from
   \\`disagreements_unverified\\`, ordered by severity, each with the doc quote, the code citation
   and the reporting agent. **Head this section with a one-line banner stating that none of it
   was adversarially verified**, and give the count. Where a single agent's claim rests on a
   citation you cannot corroborate from the ground-truth data, say so per row — the rows differ
   in how well-evidenced they are and flattening that would be its own error. Task 51
   dispositions this list and must re-check each row before acting; say that once, here.""",
    'synthesis brief: section 5 structure')

# 5. Do not let the agent count imply verification depth.
sub('Below is the complete output of ~20 agents that read the code, ran the three test suites, read',
    'Below is the complete output of 20 agents (11 whose results were salvaged from an earlier,\ninterrupted run of this same workflow) that read the code, ran the three test suites, read',
    'agent-count provenance')

p.write_text(s)
print(f'\n{orig_len:,} -> {len(s):,} bytes')
