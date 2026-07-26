#!/bin/bash
# Burn down the job_scores backlog. See jobs/backfill-facts.sh for the facts
# equivalent, and jobs/backfill-builtin-descriptions.sh for descriptions.
#
# Resolves its own location rather than hardcoding ~/.hermes/scripts: the README
# documents cloning this repo to ~/hermes-scripts on other machines, where an
# absolute cd would silently run the wrong copy or none at all.
set -euo pipefail

cd "$(dirname "$(readlink -f "$0")")"
set -a; . ~/.hermes/.env; set +a

python3 jobs/backfill-scores.py --workers "${BACKFILL_WORKERS:-3}" 2>&1 \
    | tee backfill.log
