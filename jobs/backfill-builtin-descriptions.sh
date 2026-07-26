#!/usr/bin/env bash
# Drain the Built In NYC description backlog by calling ingest/builtin-nyc.py
# until no open row is missing one. Same shape as backfill-facts.sh: progress IS
# the remaining count, so this is interruptible and resumable with no
# bookkeeping of its own.
#
# WHY A BACKLOG EXISTS AT ALL
#   The listing pages carry no description, so each one costs a detail-page
#   fetch. ingest/builtin-nyc.py budgets those at BUILTIN_DETAIL_LIMIT (60) per
#   run to stay a polite scraper, and fill_descriptions() works oldest-gap-first
#   against the table rather than against the current listing -- so rows pushed
#   past page 3 still get reached. With the daily run stalled, 187 of 192 rows
#   accumulated with description_text IS NULL, which is the one field an app
#   cannot render around.
#
# THIS WILL NOT DRAIN THE BACKLOG IN ONE SITTING -- MEASURED
#   Built In starts returning HTTP 429 after roughly 50-60 detail fetches in
#   quick succession, and then 429s even a single request for a while. Observed
#   2026-07-26: a run at the 2.0s default filled 52 descriptions and was
#   throttled for the rest of the pass. So expect this to fill a slice, back
#   off, and finish across several invocations or several daily runs -- that is
#   the host's budget, not a bug here, and pushing through it is what turns a
#   polite scraper into a rude one.
#
# RATE LIMITING IS RESPECTED, NOT WORKED AROUND
#   builtin-nyc.py raises RateLimited on HTTP 429 and abandons the pass, which
#   is the entire point of that class -- each row is committed as it lands, so
#   stopping loses nothing. This script then waits far longer than the
#   per-request delay before asking again.
#
#   ./jobs/backfill-builtin-descriptions.sh
#   BUILTIN_DETAIL_DELAY=10 BUILTIN_BACKOFF=1800 ./jobs/backfill-builtin-descriptions.sh
set -uo pipefail

cd "$(dirname "$0")/.."
set -a; . ~/.hermes/.env; set +a

# Gentler than ingest/builtin-nyc.py's own defaults (60 fetches, 2.0s apart),
# which is what tripped the 429 above. A backfill has no deadline; the daily
# ingest does, which is why only this wrapper slows things down.
export BUILTIN_DETAIL_LIMIT="${BUILTIN_DETAIL_LIMIT:-40}"
export BUILTIN_DETAIL_DELAY="${BUILTIN_DETAIL_DELAY:-6}"

#: Seconds to wait after a 429 before trying the next pass. Long, because the
#: observed throttle outlasts a short nap.
BACKOFF="${BUILTIN_BACKOFF:-1800}"

#: Give up after this many consecutive throttled passes rather than looping all
#: night. The remaining rows keep draining via the daily run.
MAX_THROTTLES="${BUILTIN_MAX_THROTTLES:-3}"

remaining() {
    python3 - <<'PY'
import os, sys
sys.path.insert(0, ".")
sys.path.insert(0, "jobs")
import schema
from pipelib import dbconn
conn = dbconn.connect_or_exit("builtin-remaining", schema=schema.SCHEMA)
print(conn.execute(
    f"""SELECT count(*) FROM {schema.TABLE}
        WHERE platform = 'builtin' AND status = %s
          AND coalesce(description_text, '') = ''
          AND coalesce(job_url, '') <> ''""",
    (schema.STATUS_OPEN,)).fetchone()[0])
conn.close()
PY
}

start=$(date +%s)
round=0
throttles=0
left=$(remaining) || { echo "backfill-builtin: cannot reach the database."; exit 1; }
echo "backfill-builtin: $left open rows missing a description."

while [ "${left:-0}" -gt 0 ]; do
    round=$((round + 1))
    out=$(python3 jobs/ingest/builtin-nyc.py 2>&1)
    echo "  [$(printf '%3d' "$round")] $out"

    left=$(remaining)
    el=$(( $(date +%s) - start ))
    printf '        %s remaining  elapsed %dm%02ds\n' "$left" $((el / 60)) $((el % 60))

    if grep -q "rate limited" <<<"$out"; then
        throttles=$((throttles + 1))
        if [ "$throttles" -ge "$MAX_THROTTLES" ]; then
            echo "backfill-builtin: throttled $throttles times in a row -- stopping."
            echo "  $left row(s) still empty; the daily run will keep chipping at"
            echo "  them. Re-run later, or raise BUILTIN_DETAIL_DELAY."
            exit 0
        fi
        echo "        (rate limited $throttles/$MAX_THROTTLES -- backing off ${BACKOFF}s)"
        sleep "$BACKOFF"
        continue
    fi
    throttles=0

    # Progress is "descriptions fetched", NOT the change in `remaining`. Each
    # pass also ingests the current listing pages, so a run that successfully
    # filled 23 descriptions while discovering 55 new postings leaves the
    # backlog LARGER -- which is real progress, not a stall. Comparing
    # remaining counts read that as failure and quit on the first pass.
    fetched=$(sed -n 's/.*[^0-9]\([0-9]\+\) descriptions fetched.*/\1/p' <<<"$out")
    if [ "${fetched:-0}" -eq 0 ]; then
        echo "backfill-builtin: no descriptions fetched this pass -- the oldest"
        echo "  $left gap(s) have no usable description on their detail page"
        echo "  (404, or no schema.org JobPosting block). Stopping."
        exit 0
    fi
done

echo "backfill-builtin: done -- every open builtin row has a description."
