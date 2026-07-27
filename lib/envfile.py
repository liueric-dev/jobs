"""Load a .env file into os.environ from Python.

The caller passes its own path -- ~/apps/jobs/.env.
There is deliberately no default; see the note on DEFAULT_ENV_FILE below. (This
module was originally written to load ~/.hermes/.env, which is the file the
history below refers to.)

WHY THIS EXISTS
    Every shell entry point into these pipelines sources the env file itself
    -- `scripts/backfill-facts.sh`, `scripts/run-backfill.sh`,
    `tools/learned-ranker-probe.py`'s
    documented invocation. The two `run-daily.py` cron entry points did not:
    they called `os.environ.copy()` and trusted the caller to have exported
    everything.

    That trust was misplaced. The 2026-07-25 00:00 scheduled run of
    daily-jobs-ingest failed all seven steps at once -- "fe_sendauth: no
    password supplied" from the four database steps, "SERPAPI_API_KEY not
    set", "APIFY_API_TOKEN not set", "JOB_SCORING_API_KEY not set" -- because
    nothing had put ~/.hermes/.env into the environment. The job was paused
    after that and stopped running entirely.

    A cron entry point that depends on an ambient environment it does not
    establish is a cron entry point that works when tested by hand and fails
    when scheduled, which is the worst arrangement available.

WHY NOT python-dotenv
    Both pipelines are stdlib-only apart from psycopg (see lib's module
    docstring). One 30-line parser is cheaper than a dependency, and the file
    it parses is 29 plain KEY=VALUE lines.

SHELL-COMPATIBLE, DELIBERATELY
    `set -a; . file; set +a` is what the shell callers do, so this must agree
    with it or two entry points will disagree about one key's value. Verified
    against the real file: an inline comment is stripped only when preceded by
    whitespace, which is what the shell does, and which matters because one
    line in the live file relies on it (a 81-char line whose value is 53
    chars). Surrounding quotes are stripped for the same reason.

    Not supported, because the file does not use them and guessing wrong is
    worse than not trying: variable expansion ($OTHER), command substitution,
    and multi-line values.
"""

import os
import re

#: There is deliberately no DEFAULT_ENV_FILE. It used to be
#: ~/.hermes/.env, which was jobs-specific: events already passed its own path
#: explicitly, and slice D gave jobs its own .env at ~/apps/jobs/.env. A module
#: shared by two applications has no business knowing either one's config path,
#: and a default that is right for exactly one caller is a trap for the other.
#: `load()` therefore requires a path.

_LINE = re.compile(r"""
    ^\s*
    (?:export\s+)?                      # `export FOO=bar` is still FOO=bar
    (?P<key>[A-Za-z_][A-Za-z0-9_]*)
    \s*=\s*
    (?P<value>.*?)
    \s*$
""", re.VERBOSE)


def parse(text):
    """{key: value} from env-file text. Later lines win, as in the shell."""
    out = {}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = _LINE.match(line)
        if not m:
            continue
        value = m.group("value")
        # An inline comment needs leading whitespace to be a comment -- a '#'
        # flush against the value is part of the value. This is the shell's
        # rule, and a password may legitimately contain '#'.
        value = re.split(r"\s+#", value, maxsplit=1)[0].strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out[m.group("key")] = value
    return out


def load(path, override=False):
    """Merge an env file into os.environ. Returns the keys actually set.

    `path` is required -- see the note above where the default used to be.

    `override=False` means a value already in the environment wins, so a
    caller that exported SERPAPI_API_KEY for a one-off run against a second
    machine's quota still gets that key -- the file is the fallback, not the
    authority. That is the same precedence the env-var-only configuration
    convention in README.md already implies everywhere else.

    A missing file is not an error. Not every machine running these scripts
    has one (the README's "On other devices" path exports variables directly),
    and failing here would break the case the file is meant to support.
    """
    try:
        with open(path) as f:
            text = f.read()
    except OSError:
        return []

    applied = []
    for key, value in parse(text).items():
        if override or key not in os.environ:
            os.environ[key] = value
            applied.append(key)
    return applied
