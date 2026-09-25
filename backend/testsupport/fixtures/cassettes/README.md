# Recorded upstream responses

Real upstream responses let ingestion tests run without a network.

**Do not hand-edit.** Each file is a recording; editing one makes it a
recording of nothing. Re-record instead:

    .venv/bin/python testsupport/record_cassettes.py --list
    .venv/bin/python testsupport/record_cassettes.py --all-free
    .venv/bin/python testsupport/record_cassettes.py ats-greenhouse

`testsupport/record_cassettes.py` holds one recipe per cassette and is the only
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
file is written. Tests assert this behavior.

**No timing is here.** A replayed response has the latency of a call made
months ago against a possibly different endpoint revision, so nothing stores
one and `Player.wall_clock` raises rather than answering.

Workday's constructed failure fixtures live in
[`testsupport/workday_fixtures.py`](../../workday_fixtures.py). They are
synthetic; the NVIDIA happy-path sample is recorded here.
