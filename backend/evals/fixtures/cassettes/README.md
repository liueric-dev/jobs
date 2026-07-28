# Recorded upstream responses

Real bytes from the real endpoints, so the six non-LLM ingest scripts can be
exercised without a network. Written by task 09
([`docs/ingestion_tests/05-fetcher-harness.md`](../../../../docs/ingestion_tests/05-fetcher-harness.md)).

**Do not hand-edit.** Each file is a recording; editing one makes it a
recording of nothing. Re-record instead:

    python3 evals/record_cassettes.py --list        # what exists, and what it costs
    python3 evals/record_cassettes.py --all-free    # everything that costs no quota
    python3 evals/record_cassettes.py ats-greenhouse

`evals/record_cassettes.py` holds one recipe per cassette and is the only
thing in this repo that makes a live third-party call from a test path. Each
recipe drives the REAL fetch function from the REAL ingest script, so what was
requested is a property of the pipeline rather than of somebody's shell
history.

**Each file says what it is.** `source`, `recorded_at`, `recorded_by` and a
prose `note` are stored in every cassette; `tests/test_cassettes.py` asserts
all four are present and prints the recording date on every run. A fixture
recorded in July becomes December's specification whether anyone meant it to
or not, so the age is always on screen.

**No credential is here, and none is part of the lookup key.** Secret query
parameters are stored as `REDACTED`, secret request headers are dropped, and
any secret-shaped environment value is scrubbed out of the bytes before the
file is written. Rotating `SERPAPI_API_KEY` does not invalidate this
directory. Two tests assert it.

**No timing is here.** A replayed response has the latency of a call made
months ago against a possibly different endpoint revision, so nothing stores
one and `Player.wall_clock` raises rather than answering.

Workday's four failure fixtures are *not* here. They are constructed rather
than recorded — there is no Workday tenant to record against until task 16 —
and live in [`evals/workday_fixtures.py`](../../workday_fixtures.py), which
says so at length.
