#!/usr/bin/env python3
"""Pull the durable core out of the banked orientation data.

1.06MB of JSON is ~265k tokens; reading it whole is the mistake that made this
expensive in the first place. This writes small, targeted files instead.
"""
import json
import pathlib
import sys

S = pathlib.Path(sys.argv[1])
OUT = S / 'core'
OUT.mkdir(exist_ok=True)

p1 = json.loads((S / 'phase1.json').read_text())
p2 = json.loads((S / 'phase2-partial.json').read_text())


def w(name, text):
    f = OUT / name
    f.write_text(text)
    print(f'{name:<28} {len(text):>8,} chars  (~{len(text)//4:>6,} tok)')


# ---------------------------------------------------------------- landmines
lines = []
for a in p1:
    for d in a.get('dead_or_suspect', []):
        lines.append(f"[{a['_key']}] {d['what']}\n    why: {d['why']}\n    cite: {d['citation']}")
w('landmines.txt', f'# {len(lines)} suspect/dead/landmine findings\n\n' + '\n\n'.join(lines))

# ------------------------------------------------- open questions, by blocker
byneed = {}
for a in p1:
    for q in a.get('open_questions', []):
        byneed.setdefault(q.get('needs', 'unspecified'), []).append(f"[{a['_key']}] {q['question']}")
lines = []
for need in sorted(byneed):
    lines.append(f'## needs: {need}  ({len(byneed[need])})')
    lines += [f'- {x}' for x in byneed[need]]
w('open-questions.txt', '\n'.join(lines))

# ---------------------------------------------------- brief contradictions
lines = [f"[{a['_key']}] {c}" for a in p1 for c in a.get('contradictions', [])]
w('contradictions.txt', f'# {len(lines)} facts a brief asserted that the code refuted\n\n'
  + '\n\n'.join(lines))

# ------------------------------------------------------------- LLM cost sites
lines = []
for a in p1:
    for l in a.get('llm_calls', []):
        lines.append(f"[{a['_key']}] {l['site']}\n    cite: {l['citation']}\n"
                     f"    model: {l.get('model_selection', '?')}\n    on_failure: {l.get('on_failure', '?')}")
w('llm-calls.txt', f'# {len(lines)} sites that cost a model call\n\n' + '\n\n'.join(lines))

# ----------------------------------------------------------------- suites
suites = next(a for a in p1 if a['_key'] == 'suites')
lines = [f"{s['name']}\n    cmd: {s['command']}\n    Ran {s['ran']}, ok={s['ok']}, "
         f"fail={s.get('failures')}, err={s.get('errors')}, skip={s.get('skipped')}, "
         f"{s.get('duration', '?')}" for s in suites['suites']]
lines += [f"NOTE {n['observation']}  [{n.get('citation', '')}]" for n in (suites.get('notable') or [])]
w('suites.txt', '\n\n'.join(lines))

# -------------------------------------------------- task verdicts that matter
rows = [t for r in p2 for t in r.get('tasks', [])]
interesting = [t for t in rows
               if t.get('mismatch') or t.get('evidence_status') not in ('DONE', 'NOT-AN-IMPLEMENTATION')
               or (t.get('blocked_on') and t['blocked_on'] != 'nothing')]
lines = []
for t in sorted(interesting, key=lambda x: x['id']):
    lines.append(
        f"{t['id']}  {t.get('title', '')}\n"
        f"    claimed:  {(t.get('claimed_status') or '')[:90]}\n"
        f"    evidence: {t['evidence_status']}   mismatch={t.get('mismatch')}   "
        f"blocked_on={t.get('blocked_on', '?')}\n"
        f"    residual: {t.get('residual_work', '-')}\n"
        f"    note:     {(t.get('note') or '-')[:400]}")
w('tasks-open.txt', f'# {len(interesting)} of {len(rows)} task verdicts are a mismatch, '
  f'not-DONE, or blocked\n\n' + '\n\n'.join(lines))

done = [t for t in rows if t not in interesting]
w('tasks-done.txt', f'# {len(done)} clean DONE verdicts\n\n'
  + '\n'.join(f"{t['id']}  {t.get('title', '')[:70]}  [{t['evidence_status']}]" for t in sorted(done, key=lambda x: x['id'])))

# --------------------------- disagreements that survive deleting docs/: CLAUDE.md
dis = [d for r in p2 for d in r.get('disagreements', [])]
survives = [d for d in dis if 'CLAUDE.md' in (d.get('doc') or '') or 'README.md' == (d.get('doc') or '').split('/')[-1].split(':')[0]]
lines = []
for d in sorted(survives, key=lambda x: {'high': 0, 'medium': 1, 'low': 2}.get(x.get('severity'), 3)):
    lines.append(f"[{d.get('severity')}] {d.get('doc')}  ({d.get('kind', '?')})\n"
                 f"    doc:  {d.get('doc_claim', '')[:300]}\n"
                 f"    code: {d.get('code_says', '')[:300]}\n"
                 f"    cite: {d.get('code_citation', '')}")
w('claudemd-disagreements.txt',
  f'# {len(survives)} of {len(dis)} disagreements are against files that SURVIVE deleting docs/\n'
  f'# (.claude/CLAUDE.md and the root READMEs). UNVERIFIED - no skeptic checked these.\n\n'
  + '\n\n'.join(lines))

# a one-line index of the rest, so nothing is silently dropped
rest = [d for d in dis if d not in survives]
w('disagreements-index.txt',
  f'# {len(rest)} disagreements against files under docs/ (being deleted). UNVERIFIED.\n'
  f'# One line each, as a record that they were found.\n\n'
  + '\n'.join(f"[{d.get('severity')}] {d.get('doc')} :: {(d.get('doc_claim') or '')[:110]}" for d in rest))

# ---------------------------------------------------------------- entrypoints
lines = []
for a in p1:
    for e in a.get('entrypoints', []):
        lines.append(f"[{a['_key']}] {e['name']}  [{e['citation']}]\n"
                     f"    invoked_by: {e.get('invoked_by', '?')}\n    {e.get('description', '')[:200]}")
w('entrypoints.txt', '\n\n'.join(lines))

print()
print('area fact counts (read these selectively):')
for a in p1:
    if a.get('facts'):
        print(f"  {a['_key']:<10} {len(a['facts']):>3} facts  {len(json.dumps(a['facts']))//4:>6,} tok")
