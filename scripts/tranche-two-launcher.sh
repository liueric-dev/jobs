#!/bin/bash
#
# tranche-two-launcher.sh
#
# Runs all 7 tranche_two tasks (07-13) through Claude Code in the
# claude-refactor tmux session, in dependency-respecting order:
#
#   07 (dep: 06✓)   metrics + golden set
#   09 (dep: 02✓)   fetcher harness
#   10 (dep: 05✓)   description-first gate
#   08 (dep: 07)     score validation
#   11 (dep: 06,10)  archetype superset / role_track
#   12 (dep: 04,07,11) facts version bump + re-extract
#   13 (dep: 11,12)  cohort criteria profile
#
# Sends Telegram status report when done. Checks for blockers per task.
#
set -euo pipefail

SESSION="claude-refactor"
REPO="/home/eric/apps/jobs"
TRANCHE="tranche_two"
TG() { hermes send --to telegram "$1" 2>/dev/null || true; }
REPORT="/tmp/tranche_two-report.md"

echo "# Tranche Two Status Report" > "$REPORT"
echo "" >> "$REPORT"
echo "_Started: $(date)_" >> "$REPORT"
echo "" >> "$REPORT"

# --- Verify session exists ---
if ! tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "ERROR: tmux session '$SESSION' not found. Cannot proceed." >> "$REPORT"
    TG "❌ Cannot start Tranche Two: tmux session '$SESSION' not found."
    cat "$REPORT"
    exit 1
fi

# --- Verify tranche_one prerequisites landed ---
# Tasks 04, 05, 06 are measurements — check they have commits or notes
cd "$REPO"
TRANCHE_ONE_COMMITS=$(git log --oneline --all | grep -ciP 'tranche_one' || true)
echo "## Prerequisites" >> "$REPORT"
echo "- Tranche one commits found: ${TRANCHE_ONE_COMMITS}" >> "$REPORT"
echo "- Last commit: $(git log --oneline -1)" >> "$REPORT"
echo "" >> "$REPORT"

# Check if tranche_one report exists and has blockers
if [ -f "/tmp/tranche_one-report.md" ]; then
    BLOCKERS=$(grep -ciP 'BLOCKER' /tmp/tranche_one-report.md || true)
    if [ "$BLOCKERS" -gt 0 ]; then
        echo "- ⚠️ Tranche one had ${BLOCKERS} blocker(s) — some deps may be unmet" >> "$REPORT"
        TG "⚠️ Tranche Two starting, but tranche one had ${BLOCKERS} blocker(s). Dependent tasks may fail."
    fi
fi
echo "" >> "$REPORT"

# --- Helper: wait for Claude idle ---
wait_done() {
    local elapsed=0 idle=0
    while true; do
        sleep 30
        elapsed=$((elapsed + 30))
        local pane
        pane=$(tmux capture-pane -t "$SESSION" -p -S -12 2>/dev/null || echo "")
        [ -z "$pane" ] && { echo "session gone"; return 1; }
        if echo "$pane" | grep -qP '(Wibbling|Thinking|Osmosing|Reading|Searching|Running|Pondering|Musing|Reflecting|✶|✽|●|✢|✸|★|⚡|↓ \d|still thinking|thinking more)'; then
            idle=0
        else
            if echo "$pane" | grep -qP 'Worked for|Elapsed'; then
                echo "done at ${elapsed}s"
                return 0
            fi
            idle=$((idle + 1))
            [ $idle -ge 3 ] && { echo "idle at ${elapsed}s"; return 0; }
        fi
        [ $elapsed -ge 1800 ] && { echo "timeout at ${elapsed}s"; return 1; }
    done
}

# --- Helper: run one task ---
# Args: task_number task_filename dependency_task_numbers(space-separated)
run_task() {
    local num="$1" file="$2" deps="${3:-}"
    local task_path="docs/tasks/refactor/${TRANCHE}/${file}"
    local name="${file%.md}"

    echo ">>> Starting ${name}"

    # Send prompt
    tmux send-keys -t "$SESSION" "Implement the task described in ${task_path} completely. Follow the instructions in .claude/CLAUDE.md first. Read the task file and every file it cites at the lines it cites, then implement everything in the Work section and Definition of Done section. Run the full test suite (python3 -m unittest discover -s backend/tests) when done and ensure all tests pass. After completing all work, commit your changes with a descriptive message starting with the task number." Enter

    # Wait
    local result
    result=$(wait_done || true)
    echo ">>> ${name}: ${result}"

    # Capture
    local pane commit tests
    pane=$(tmux capture-pane -t "$SESSION" -p -S -80 2>/dev/null || echo "")
    commit=$(cd "$REPO" && git log --oneline -1 2>/dev/null || echo "unknown")
    tests=$(echo "$pane" | grep -oP '\d+/\d+ tests pass|\d+ tests? pass|Ran \d+ tests' | tail -1 || echo "unknown")

    # Report entry
    echo "## ${name}" >> "$REPORT"
    echo "- Commit: \`${commit}\`" >> "$REPORT"
    echo "- Tests: ${tests}" >> "$REPORT"

    # Blocker check
    if echo "$pane" | grep -qiP 'cannot|unable to|no such file|permission denied|API key|credential|BLOCKED|needs.*human|requires.*volunteer'; then
        local snippet
        snippet=$(echo "$pane" | grep -iP 'cannot|unable to|no such file|permission denied|API key|credential|BLOCKED|needs.*human|requires.*volunteer' | tail -3)
        echo "- Status: ⚠️ BLOCKER" >> "$REPORT"
        echo "- Blocker: ${snippet}" >> "$REPORT"
        TG "⚠️ BLOCKER in ${name}: ${snippet}"
    else
        echo "- Status: completed" >> "$REPORT"
    fi
    echo "" >> "$REPORT"

    # Clear session
    sleep 2
    tmux send-keys -t "$SESSION" '/clear' Enter
    sleep 3
    tmux send-keys -t "$SESSION" '' Enter
    sleep 2

    echo ">>> ${name} done, cleared"
}

# === Run tasks in dependency order ===
run_task "07" "07-metrics-and-golden-set.md"       "06"
run_task "09" "09-fetcher-harness.md"               "02"
run_task "10" "10-description-first-gate.md"        "05"
run_task "08" "08-score-validation.md"              "07"
run_task "11" "11-archetype-superset-role-track.md" "06 10"
run_task "12" "12-facts-version-bump.md"            "04 07 11"
run_task "13" "13-cohort-criteria-profile.md"       "11 12"

# === Final report ===
echo "" >> "$REPORT"
echo "_Tranche Two complete — $(date)_" >> "$REPORT"

TG "✅ Tranche Two complete. 7 tasks processed."
hermes send --to telegram --file "$REPORT" -s "Tranche Two Report" -q 2>/dev/null || TG "$(cat "$REPORT")"

echo "=== TRANCHE TWO COMPLETE ==="
cat "$REPORT"
