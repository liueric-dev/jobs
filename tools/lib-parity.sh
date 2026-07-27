#!/usr/bin/env bash
# Report drift between the two vendored copies of the mechanism layer.
#
# ~/apps/events/lib and ~/apps/jobs/lib were one shared package until
# 2026-07-26 (~/apps/REORG.md slice G). Vendoring made each application
# standalone and bought back the risk the shared package existed to remove:
# two copies that drift without anyone noticing. This project has already
# paid that bill once -- api/ carried its own implementations and four of
# them diverged, two in ways that silently changed row identity.
#
# This is NOT a gate and it does not fail on divergence. Divergence is
# allowed and some of it is deliberate; see ALLOWED below. What was missing
# last time was any way to ask the question at all, so this answers it in
# five seconds.
#
# The hard guarantee lives elsewhere: {events,jobs}/tests/test_row_identity.py
# pin the digests of every function that feeds a stored hash, as literals, in
# both repos. That is what actually fails when row identity moves. This
# script catches the wider class of "these two drifted and nobody meant them
# to", including in functions no test covers.
#
# WHERE THIS LIVES, AND WHY THERE ARE TWO OF IT
#   ~/apps is not a git repo -- events, jobs, pipelib and infra each are. A
#   script that only existed at ~/apps/tools/ would be the one part of this
#   guard that nothing versions and nothing backs up. So the canonical copy is
#   committed to BOTH repos as tools/lib-parity.sh, and ~/apps/tools/ holds a
#   symlink for convenience. The script checks its own two copies for drift
#   along with everything else -- a guard that can rot silently is the exact
#   failure it exists to catch.
#
# Usage:  ~/apps/tools/lib-parity.sh [-v]
#         -v  show the actual diff for every diverged file

set -uo pipefail

EVENTS="${HOME}/apps/events/lib"
JOBS="${HOME}/apps/jobs/lib"
SELF_EV="${HOME}/apps/events/tools/lib-parity.sh"
SELF_JB="${HOME}/apps/jobs/tools/lib-parity.sh"
VERBOSE=0
[[ "${1:-}" == "-v" ]] && VERBOSE=1

for d in "$EVENTS" "$JOBS"; do
    if [[ ! -d "$d" ]]; then
        echo "lib-parity: $d does not exist" >&2
        exit 2
    fi
done

# Files that are SUPPOSED to differ, with the reason. Add a line here in the
# same commit that creates the divergence -- an entry without a reason is
# worse than no entry, because it launders drift as intent.
declare -A ALLOWED=(
  [__init__.py]="per-repo docstring: each names its own pipeline and row counts"
  [dbconn.py]="jobs has no DEFAULT_DATABASE_URL -- the events-shaped default is destructive there (FOOTGUN 2)"
  [state.py]="events keeps the pager half, jobs keeps the claim half; zero overlap"
  [text.py]="events keeps strip_html alone; jobs uses all nine functions"
  [upsert.py]="GEOG_EXPR and prune_expired are events-only"
)

printf '%-14s %-12s %s\n' FILE STATUS NOTE
printf '%.0s-' {1..78}; echo

status=0
unexpected=0
mapfile -t files < <(
    { find "$EVENTS" -maxdepth 1 -name '*.py' -printf '%f\n'
      find "$JOBS"   -maxdepth 1 -name '*.py' -printf '%f\n'; } | sort -u)

for f in "${files[@]}"; do
    a="$EVENTS/$f"; b="$JOBS/$f"
    if [[ ! -f "$a" ]]; then
        printf '%-14s %-12s %s\n' "$f" "JOBS-ONLY" "absent from events/lib"
        unexpected=$((unexpected+1)); continue
    fi
    if [[ ! -f "$b" ]]; then
        printf '%-14s %-12s %s\n' "$f" "EVENTS-ONLY" "absent from jobs/lib"
        unexpected=$((unexpected+1)); continue
    fi
    if cmp -s "$a" "$b"; then
        printf '%-14s %-12s\n' "$f" "identical"
    elif [[ -v ALLOWED[$f] ]]; then
        printf '%-14s %-12s %s\n' "$f" "diverged" "expected: ${ALLOWED[$f]}"
        [[ $VERBOSE -eq 1 ]] && diff -u "$a" "$b" | sed 's/^/    /'
    else
        printf '%-14s %-12s %s\n' "$f" "DIVERGED" "NOT in the allowlist -- was this meant?"
        unexpected=$((unexpected+1))
        [[ $VERBOSE -eq 1 ]] && diff -u "$a" "$b" | sed 's/^/    /'
    fi
done

# An allowlist entry covers a WHOLE FILE, which is too coarse for the files
# that carry row identity. text.py is allowlisted because events keeps one
# function of nine -- but that same entry would have laundered the exact
# historical bug this project is guarding against, a strip_html truncating at
# 5000 instead of 20000. (Verified by planting it: the file-level check called
# it "expected".) So the hash-critical functions are compared BY BODY,
# regardless of what the allowlist says about the file they live in.
echo
python3 - "$EVENTS" "$JOBS" <<'PY'
import ast, sys

# Every function whose output reaches a stored digest. Anything added to a
# HASH_FIELDS tuple, or feeding one, belongs on this list.
CRITICAL = {
    "ids.py":  ["make_id", "content_hash", "normalize_apply_url",
                "google_source_id", "decode_google_job_id"],
    "text.py": ["strip_html", "parse_relative_posted_at",
                "posted_at_timestamp", "bounded_json"],
}
CONSTANTS = {"text.py": ["MAX_DESCRIPTION_CHARS"]}

def defs(path):
    try:
        tree = ast.parse(open(path).read())
    except FileNotFoundError:
        return {}, {}
    fns = {n.name: ast.dump(n) for n in tree.body
           if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    consts = {}
    for n in tree.body:
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    consts[t.id] = ast.dump(n.value)
    return fns, consts

checked = bad = absent = 0
for fname, names in CRITICAL.items():
    ef, ec = defs(f"{sys.argv[1]}/{fname}")
    jf, jc = defs(f"{sys.argv[2]}/{fname}")
    for n in names:
        if n not in ef or n not in jf:
            # Legitimately trimmed out of one side -- not drift.
            absent += 1
            continue
        checked += 1
        if ef[n] != jf[n]:
            bad += 1
            print(f"    DIVERGED: {fname}:{n}() -- this function feeds a "
                  f"stored content_hash")
    for n in CONSTANTS.get(fname, []):
        if n in ec and n in jc:
            checked += 1
            if ec[n] != jc[n]:
                bad += 1
                print(f"    DIVERGED: {fname}:{n} -- this constant feeds a "
                      f"stored content_hash")

print(f"hash-critical functions: {checked} compared, {bad} diverged, "
      f"{absent} present in only one copy (trimmed, not drift)")
sys.exit(1 if bad else 0)
PY
[[ $? -ne 0 ]] && unexpected=$((unexpected+1))

# The row-identity vectors must agree class for class, since they are the
# thing both repos rely on to prove their copy still writes the same digests.
echo
EV_T="${HOME}/apps/events/tests/test_row_identity.py"
JB_T="${HOME}/apps/jobs/tests/test_row_identity.py"
if [[ -f "$EV_T" && -f "$JB_T" ]]; then
    python3 - "$EV_T" "$JB_T" <<'PY'
import re, sys
def classes(p):
    s = open(p).read()
    out = {}
    for m in re.finditer(r"^class (\w+)\(", s, re.M):
        nxt = s.find("\n\nclass ", m.start() + 1)
        end = nxt if nxt > 0 else s.find("\n\nif __name__")
        out[m.group(1)] = s[m.start():end if end > 0 else len(s)]
    return out
e, j = classes(sys.argv[1]), classes(sys.argv[2])
shared = sorted(set(e) & set(j))
bad = [k for k in shared if e[k] != j[k]]
print(f"row-identity vectors: {len(shared)} shared classes, "
      f"{len(bad)} diverged")
for k in bad:
    print(f"    DIVERGED: {k} -- the two repos disagree about a stored digest")
print(f"    jobs-only (expected): {', '.join(sorted(set(j) - set(e))) or 'none'}")
sys.exit(1 if bad else 0)
PY
    [[ $? -ne 0 ]] && unexpected=$((unexpected+1))
else
    echo "row-identity vectors: MISSING in one or both repos"
    unexpected=$((unexpected+1))
fi

# This script is itself duplicated across the two repos, so it is subject to
# exactly the drift it reports on.
echo
if [[ -f "$SELF_EV" && -f "$SELF_JB" ]]; then
    if cmp -s "$SELF_EV" "$SELF_JB"; then
        echo "this script: both repo copies identical"
    else
        echo "this script: DIVERGED between the two repos -- the guard itself drifted"
        unexpected=$((unexpected+1))
    fi
else
    echo "this script: MISSING from one or both repos (expected tools/lib-parity.sh)"
    unexpected=$((unexpected+1))
fi

echo
if [[ $unexpected -eq 0 ]]; then
    echo "OK -- every difference is on the allowlist."
else
    echo "$unexpected unexpected difference(s). Either fix the drift, or add an"
    echo "allowlist entry WITH A REASON in the commit that introduces it."
    status=1
fi
exit $status
