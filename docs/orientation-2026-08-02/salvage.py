#!/usr/bin/env python3
"""Salvage phase 1 of wf_8a96dc0c-0bd and generate the phase-2 workflow script.

Rebuilds the GROUND digest with exactly the logic at
.claude/workflows/orientation-from-code.js:586-616 so the downstream briefs are
byte-identical to what the dead run would have sent.
"""
import json
import pathlib
import re
import sys

RUN = pathlib.Path.home() / '.claude/projects/-home-eric-apps-jobs' \
    / '913da432-6b47-4f4b-89bb-f0184157c49d/subagents/workflows/wf_8a96dc0c-0bd'
ORIG = pathlib.Path('/home/eric/apps/jobs/.claude/workflows/orientation-from-code.js')
OUT = pathlib.Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------- 1. salvage
results = []
for line in (RUN / 'journal.jsonl').open():
    d = json.loads(line)
    if d.get('type') == 'result':
        results.append(d['result'])

# Re-attach the _key each agent's .then() added, by matching on shape/content.
KEYMAP = {
    'stages': 'stages', 'ingest': 'ingest', 'schema': 'schema', 'webapp': 'webapp',
    'api': 'api', 'frontend': 'frontend', 'evals': 'evals', 'deploy': 'deploy',
}
gt = []
git_seen = 0
for r in results:
    if 'suites' in r:
        r['_key'] = 'suites'
    elif 'landed' in r:
        # the 01-29 pass reported task '01'; the 30-54 pass reported '30' or higher
        nums = [t.get('task', '') for t in r['landed']]
        low = sum(1 for n in nums if n and n[0] in '012' and n[:2] < '30')
        r['_key'] = 'git-a' if low > len(nums) / 2 else 'git-b'
        git_seen += 1
    else:
        area = (r.get('area') or '').split('—')[0].strip().lower()
        r['_key'] = KEYMAP.get(area, area or 'unknown')
    gt.append(r)

keys = sorted(g['_key'] for g in gt)
assert len(gt) == 11, f'expected 11 results, got {len(gt)}'
assert 'git-a' in keys and 'git-b' in keys, f'git passes not distinguished: {keys}'
assert 'unknown' not in keys, f'unmapped area: {keys}'

(OUT / 'phase1.json').write_text(json.dumps(gt, indent=1))

# --------------------------------------------- 2. rebuild GROUND (js:586-616)
stopped = [f"[{g['_key']}] {c}" for g in gt for c in (g.get('contradictions') or [])]

code_areas = [g for g in gt if g.get('facts')]


def digest_area(a):
    s = f"### AREA: {a['area']} ({a['_key']})\n{a['summary']}\n\nFACTS:\n"
    s += '\n'.join(f"- {f['claim']}  [{f['citation']}]" for f in (a.get('facts') or []))
    if a.get('data_flow'):
        s += '\n\nDATA FLOW:\n' + '\n'.join(
            f"- {d['operation']} {d['store']}  [{d['citation']}]" for d in a['data_flow'])
    if a.get('llm_calls'):
        s += '\n\nLLM CALLS:\n' + '\n'.join(
            f"- {l['site']}  [{l['citation']}] model:{l.get('model_selection') or '?'}"
            for l in a['llm_calls'])
    if a.get('dead_or_suspect'):
        s += '\n\nSUSPECT:\n' + '\n'.join(
            f"- {d['what']}: {d['why']}  [{d['citation']}]" for d in a['dead_or_suspect'])
    return s


digest = '\n\n'.join(digest_area(a) for a in code_areas)

suites = next((g for g in gt if g['_key'] == 'suites'), None)
suite_line = '\n'.join(
    f"{s['name']}: Ran {s['ran']}, ok={s['ok']}, fail={s.get('failures', '?')}, "
    f"err={s.get('errors', '?')}, skip={s.get('skipped', '?')} [{s['command']}]"
    for s in suites['suites'])

git_digest = '\n'.join(
    f"- task {l['task']}: {l['verdict']} {','.join(l.get('commits') or [])}"
    + (' — ' + l['note'] if l.get('note') else '')
    for g in gt if g.get('landed') for l in g['landed'])

GROUND = f"""
=== GROUND TRUTH ESTABLISHED FROM CODE (by other agents, all citations verified against the tree) ===
This is the reference you check documents against. It came from the code, not from any document.
If YOU find the code disagrees with anything below, that is itself a finding — report it in
`contradictions`.

{digest}

=== TEST SUITES, AS THE RUNNER PRINTED THEM ===
{suite_line}

=== WHAT GIT SAYS LANDED ===
{git_digest}
=== END GROUND TRUTH ===
"""

(OUT / 'ground.txt').write_text(GROUND)

# ------------------------------------------------- 3. generate the phase-2 js
src = ORIG.read_text()

# Everything from the MANDATE through the end of the schema block, minus the
# phase-A/B execution, is reused verbatim.
mandate_start = src.index('const MANDATE =')
schemas_end = src.index('// ================================================================== execution')
preamble = src[mandate_start:schemas_end]

# Drop CODE_AREAS / CODE_SCHEMA / SUITE_SCHEMA / GIT_SCHEMA — phase 1 is not re-run.
# They are large and unreferenced downstream; strip them by their declarations.
for name in ('CODE_SCHEMA', 'CODE_AREAS', 'SUITE_SCHEMA', 'GIT_SCHEMA'):
    m = re.search(r'^const %s = ' % name, preamble, re.M)
    assert m, name
    # find the matching close at column 0 (`}` or `]` followed by newline)
    end = re.compile(r'^[}\]]\n', re.M).search(preamble, m.end())
    preamble = preamble[:m.start()] + preamble[end.end():]

body_start = src.index("phase('Tasks')")
body = src[body_start:]

# The one behavioural change: cap the adversarial verify fan-out at 12.
assert '.slice(0, 24)' in body
body = body.replace('.slice(0, 24)', '.slice(0, 12)')

header = """export const meta = {
  name: 'orientation-phase2',
  description: 'Task 49 phase 2 — task verification, adversarial doc audit, figures census, skeptic verify and synthesis, over salvaged phase-1 ground truth',
  phases: [
    { title: 'Tasks' },
    { title: 'Docs' },
    { title: 'Figures' },
    { title: 'Verify' },
    { title: 'Synthesize' },
  ],
}

const ROOT = '/home/eric/apps/jobs'
"""

# The digest-building block from the original, lifted verbatim so the briefs are
# identical to what the dead run would have sent. Embedding both `gt` and a
# pre-rendered GROUND would duplicate ~250KB and blow the 512KB script ceiling.
d_start = src.index("const stopped = gt.flatMap(")
d_end = src.index("log(`Ground-truth digest built:")
digest_code = src[d_start:d_end]
assert 'const GROUND = `' in digest_code and 'const codeAreas' in digest_code

salvaged = f"""
// ============================================================ SALVAGED PHASE 1
// The code/evidence phase of run wf_8a96dc0c-0bd (2026-08-02) completed and is
// reused verbatim rather than re-measured. Eleven structured results: eight code
// areas, the three-suite run, and two git passes. Source of truth:
//   ~/.claude/projects/-home-eric-apps-jobs/913da432-.../subagents/workflows/
//     wf_8a96dc0c-0bd/journal.jsonl
// Everything below this line down to END GROUND TRUTH is orientation-from-code.js
// :581-616 unchanged, so the downstream briefs are byte-identical to the ones the
// interrupted run would have sent.

const gt = {json.dumps(gt)}

log(`Phase 1 salvaged from wf_8a96dc0c-0bd: ${{gt.map(g => g._key).join(', ')}}`)

{digest_code}
log(`Ground-truth digest rebuilt: ~${{Math.round(GROUND.length / 4)}} tokens. Fanning out to tasks, docs and figures.`)
"""

OUT.parent  # noqa
script = header + preamble + salvaged + '\n' + body
dest = pathlib.Path('/home/eric/apps/jobs/.claude/workflows/orientation-phase2.js')
dest.write_text(script)

print(f'phase1.json   {len((OUT / "phase1.json").read_text()):>9,} bytes, {len(gt)} results')
print(f'ground.txt    {len(GROUND):>9,} bytes  (~{len(GROUND)//4:,} tokens)')
print(f'phase2.js     {len(script):>9,} bytes -> {dest}')
print(f'keys          {keys}')
print(f'contradictions {len(stopped)}')
print(f'suites        ' + ' | '.join(f"{s['name']}={s['ran']}/{s['ok']}" for s in suites['suites']))
print(f'git verdicts  {sum(len(g["landed"]) for g in gt if g.get("landed"))}')
