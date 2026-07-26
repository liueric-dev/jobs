#!/usr/bin/env bash
# Burn down the job_facts backlog by calling extract.py until it stops finding
# work. Progress IS the remaining count -- extract.py's WHERE clause is the
# only state, so this is interruptible and resumable with no bookkeeping.
#
# Reasoning is left ON deliberately. tools/compare-extract.py measured it
# changing role_archetype by 10 points and ai_involvement/remote_policy by
# 17.5 against a 98.6% self-consistency floor -- real, not sampling noise.
# Disabling it would save ~$2/month and risk systematically mis-typing the one
# artifact every profile reads.
#
#   ./backfill-facts.sh              # defaults below
#   EXTRACT_MAX_WORKERS=8 ./backfill-facts.sh
set -uo pipefail

# Was `$(dirname "$0")/..` when this script lived in jobs/ and the python it
# calls was jobs/extract.py. Slice D flattened both to the repo root.
cd "$(dirname "$0")"
set -a; . ./.env; set +a

export JOB_SCORING_BASE_URL="${JOB_SCORING_BASE_URL:-$DEEPSEEK_BASE_URL}"
export JOB_SCORING_API_KEY="${JOB_SCORING_API_KEY:-$DEEPSEEK_API_KEY}"
export JOB_SCORING_MODEL="${JOB_SCORING_MODEL:-deepseek-v4-flash}"
export EXTRACT_BATCH_SIZE="${EXTRACT_BATCH_SIZE:-50}"
export EXTRACT_MAX_WORKERS="${EXTRACT_MAX_WORKERS:-6}"
export LLM_TIMEOUT_SECS="${LLM_TIMEOUT_SECS:-150}"

start=$(date +%s)
round=0
while :; do
    round=$((round + 1))
    out=$(python3 extract.py 2>&1)
    [ -z "$out" ] && { echo "backfill-facts: nothing left to extract."; break; }
    echo "  [$(printf '%4d' "$round")] $out"

    left=$(sed -n 's/.*unusable, [0-9]* deferred (will retry), \([0-9]*\) remaining.*/\1/p' <<<"$out")
    done_n=$(sed -n 's/job-extract: \([0-9]*\) extracted.*/\1/p' <<<"$out")
    if [ -n "${left:-}" ]; then
        el=$(( $(date +%s) - start ))
        printf '         %s remaining  elapsed %dm%02ds\n' "$left" $((el / 60)) $((el % 60))
        [ "$left" -eq 0 ] && { echo "backfill-facts: done."; break; }
    fi
    # A round that extracted nothing at all means every call deferred --
    # backing off is better than hammering a rate-limited endpoint.
    [ "${done_n:-0}" -eq 0 ] && { echo "  (no progress -- backing off 60s)"; sleep 60; }
done
