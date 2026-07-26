#!/bin/bash
set -a
source ~/.hermes/.env
set +a
cd ~/.hermes/scripts
python3 jobs/backfill-scores.py --workers 3 2>&1 | tee backfill.log
