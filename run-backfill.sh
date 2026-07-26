#!/bin/bash
# Burn down the job_scores backlog. See backfill-facts.sh for the facts
# equivalent, and backfill-builtin-descriptions.sh for descriptions.
#
# Resolves its own location rather than hardcoding a path: the README documents
# cloning this repo elsewhere on other machines, where an absolute cd would
# silently run the wrong copy or none at all. The same reasoning applies to the
# env file, which is why it is sourced relative to this script rather than from
# ~/.hermes/.env as it was before slice D.
set -euo pipefail

cd "$(dirname "$(readlink -f "$0")")"
set -a; . ./.env; set +a

python3 backfill-scores.py --workers "${BACKFILL_WORKERS:-3}" 2>&1 \
    | tee backfill.log
