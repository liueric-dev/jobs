#!/usr/bin/env python3
"""
Report over `submission_log` -- contribution counts, and which workers are
submitting nothing.

WHY THIS EXISTS. Task 24's Definition of done asks for "contribution counts
tracked; empty-submission workers detectable", and until this file the answer
was *detectable, not surfaced*: defect D08's fix made an empty submit write a
`submission_log` row saying so instead of one indistinguishable from a
successful submit, and defect D41's fix put `action` on every row -- so the
query existed and nothing ran it. A signal nobody reads is the same as no
signal, one step later, and this service's named failure mode is silence.

WHY IT LIVES HERE AND NOT IN backend/tools/. `submission_log` is granted to
`jobs_api` and to nothing else (see qc.REQUIRED_TABLES, and README's privilege
table). A script under `backend/tools/` runs as `jobs_pipeline`, which holds
nothing on this table, so putting the report there would mean a new GRANT --
widening a role's reach to produce a report, which is the opposite of what the
role separation buys. It reads two tables this service already holds SELECT on
and needs no new privilege at all. `manage_users.py` is the CLI precedent in
this package and this follows its shape: argparse subcommands, the restricted
DATABASE_URL, run by hand on the box.

    cd backend/api
    .venv/bin/python contribution_report.py                  # per contributor
    .venv/bin/python contribution_report.py --empty-workers  # only the findings
    .venv/bin/python contribution_report.py --by-dataset     # per query slug
    .venv/bin/python contribution_report.py --since 2026-08-01 --json

THE VOCABULARY HAS FOUR VALUES, NOT THREE, AND NULL IS THE FOURTH.
`qc.SUBMISSION_ACTIONS` is ('claim', 'submit', 'release'). The column is
nullable with no default, and query_claims.py says what a NULL means: "written
before this column existed". That is an unknown, not a zero and not a submit,
and this report never collapses it -- it gets its own column, it is excluded
from every rate, and a contributor whose rows are all NULL is reported as
having no evidence rather than as a broken worker. Same rule the pipeline
applies to an unversioned `job_scores` row and to `job_events.rank`: a guessed
value is worse than a missing one.

There is a FIFTH bucket, `other`, for an action that is neither NULL nor in the
vocabulary. `action` is free TEXT -- the closed set lives in code because a
CHECK constraint would need DDL rights this service deliberately does not hold
-- so "outside the vocabulary" is a state the database can represent and the
code cannot prevent. The five buckets partition the rows exactly, and
`summarize()` asserts they add up to COUNT(*). That is the "reconcile the
collected counts against the total" rule from `.claude/CLAUDE.md`, applied to a
log instead of a paginated API: a row in no bucket would otherwise be a row
this report silently drops, which is the shape of defect it exists to find.

WHAT MAKES AN "EMPTY-SUBMISSION WORKER" ANSWERABLE.

  * An empty submit is `action = 'submit' AND fetched_count = 0`. That is the
    row app.submit writes on the D08 short-circuit, and `fetched_count` is
    `len(payload.jobs)` computed server-side. Deliberately NOT keyed on
    `reason`, which is free text the caller partially controls on the release
    path -- a quota or a diagnosis that parses caller-supplied text is one an
    input can influence, the argument DEC-83 used to reject a `reason` prefix
    in favour of a column.

  * A worker that claims and never submits at all is the other half of the same
    failure and does not show up as an empty submit, because it writes no
    submit row of any kind. It gets its own finding.

  * `--by-dataset` is the control. If every contributor's submits on one slug
    come back empty, the query is dead and the workers are fine; if one
    contributor's submits come back empty across many slugs, the worker is
    broken. Neither question is answerable from the other view alone, and
    reporting a broken worker for a dead query is the failure this second view
    exists to prevent.

THE TWO THRESHOLDS ARE A READING LENS, NOT A POLICY. `--min-submits` and
`--empty-rate` decide what gets a label printed beside it; nothing acts on
them, no request is refused because of them, and no row is written. That is why
they are flags with defaults rather than constants: the service has never been
deployed, so there is no distribution of real worker behaviour to derive a
ceiling from, and picking an enforced number before one is observable would be
inventing a constant (the reason defect D71's concurrency cap was left open).
Changing a flag here changes what a person is shown; it changes nothing the
service does.
"""

import argparse
import json
import sys

import psycopg

import query_claims as qc

#: How a NULL action prints. A word, not an empty cell -- an empty cell in a
#: column of integers reads as zero, which is the collapse this report refuses
#: to make.
NULL_LABEL = "null"

#: Below this many known submits, no empty-rate finding is reported. One empty
#: submit out of one is 100% and means nothing; the flag exists so the number
#: is visible and arguable rather than buried.
DEFAULT_MIN_SUBMITS = 3

#: Fraction of a contributor's submits that came back empty, above which the
#: row is worth a human look.
DEFAULT_EMPTY_RATE = 0.5

#: Findings. Strings rather than booleans because they are printed and because
#: a third one will be added before a fourth column would be.
FINDING_NO_SUBMITS = "no-submits"
FINDING_EMPTY_SUBMITS = "empty-submits"

#: The five buckets, in the order they print. `claim`/`submit`/`release` come
#: from qc.SUBMISSION_ACTIONS; the other two are the states the column can hold
#: that the vocabulary does not name.
BUCKETS = ("claims", "submits", "releases", "unknown_action", "other_action")


def connect():
    """The service's own restricted role -- read-only work, no admin credential.

    manage_users.py's `init-schema` is the only thing in this package that
    needs JOBS_ADMIN_DATABASE_URL. This reads two tables `jobs_api` already
    holds SELECT on, so it deliberately cannot be the command that runs as
    something stronger.
    """
    conn = psycopg.connect(qc.DATABASE_URL)
    conn.execute("SET search_path TO public")
    return conn


def _since_clause(since):
    """(sql_fragment, params) for an optional lower bound on submitted_at.

    `submitted_at` is TEXT in ISO-8601, so a lexicographic >= is a
    chronological >= and a bare date is a valid prefix of the timestamps it
    should include. Validated rather than trusted: a mistyped bound that
    silently matches nothing would report every contributor as having done no
    work, which is exactly the wrong direction for a report about workers doing
    no work.
    """
    if not since:
        return "", []
    if not _looks_like_a_timestamp(since):
        raise ValueError(
            f"--since {since!r}: expected YYYY-MM-DD or "
            f"YYYY-MM-DDTHH:MM:SS")
    return " WHERE submitted_at >= %s", [since]


def _looks_like_a_timestamp(value):
    if len(value) not in (10, 19):
        return False
    shape = "####-##-##" if len(value) == 10 else "####-##-##T##:##:##"
    for got, want in zip(value, shape):
        if want == "#" and not got.isdigit():
            return False
        if want != "#" and got != want:
            return False
    return True


#: The bucket arithmetic, written once and used by both views.
#:
#: COUNT(*) FILTER rather than five queries or a GROUP BY on `action`: a GROUP
#: BY returns one row per action actually present, so an action nobody wrote
#: comes back as a missing row rather than a zero, and the caller has to invent
#: the zero. These five expressions are total over the table -- every row lands
#: in exactly one -- which is what makes the reconciliation below meaningful.
_BUCKET_SQL = """
        COUNT(*) AS rows_total,
        COUNT(*) FILTER (WHERE action = 'claim') AS claims,
        COUNT(*) FILTER (WHERE action = 'submit') AS submits,
        COUNT(*) FILTER (WHERE action = 'submit' AND fetched_count = 0)
            AS empty_submits,
        COUNT(*) FILTER (WHERE action = 'release') AS releases,
        COUNT(*) FILTER (WHERE action IS NULL) AS unknown_action,
        COUNT(*) FILTER (WHERE action IS NOT NULL AND NOT (action = ANY(%s)))
            AS other_action,
        COALESCE(SUM(fetched_count) FILTER (WHERE action = 'submit'), 0)
            AS fetched,
        COALESCE(SUM(accepted_count) FILTER (WHERE action = 'submit'), 0)
            AS accepted,
        MIN(submitted_at) AS first_at,
        MAX(submitted_at) AS last_at
"""

_ROW_KEYS = ("rows_total", "claims", "submits", "empty_submits", "releases",
             "unknown_action", "other_action", "fetched", "accepted",
             "first_at", "last_at")


def fetch_contributors(conn, since=None):
    """One row per contributor that has ever written to submission_log.

    LEFT JOIN, not JOIN: submission_log.contributor_id is plain TEXT with no
    foreign key to contributors, so a log row whose contributor row is absent
    is representable -- and dropping it would hide exactly the rows most worth
    seeing. A missing name prints as a dash.
    """
    where, params = _since_clause(since)
    # An f-string rather than concatenation, so `FROM submission_log` survives
    # as one literal segment. tests/test_grants.py reassembles an f-string from
    # its literal parts and looks for a table name following FROM/JOIN; split
    # across two separate constants, the FROM and the table name land in
    # different scanned strings and the grant check goes blind to this module.
    # That blind spot is defect D69's exact shape and is not worth recreating.
    rows = conn.execute(
        f"""
        SELECT contributor_id, {_BUCKET_SQL}
        FROM submission_log {where}
        GROUP BY contributor_id ORDER BY contributor_id
        """,
        [list(qc.SUBMISSION_ACTIONS)] + params,
    ).fetchall()

    names = dict(conn.execute(
        "SELECT id, name FROM contributors").fetchall())
    out = []
    for row in rows:
        record = dict(zip(("contributor_id",) + _ROW_KEYS, row))
        record["name"] = names.get(record["contributor_id"])
        out.append(summarize(record))
    return out


def fetch_datasets(conn, since=None):
    """One row per dataset -- the control view.

    Same buckets, different grouping key, so "this slug always comes back
    empty" and "this worker always comes back empty" are two readings of one
    table rather than two reports that can disagree.
    """
    where, params = _since_clause(since)
    rows = conn.execute(
        f"""
        SELECT dataset, COUNT(DISTINCT contributor_id) AS contributors,
               {_BUCKET_SQL}
        FROM submission_log {where}
        GROUP BY dataset ORDER BY dataset
        """,
        [list(qc.SUBMISSION_ACTIONS)] + params,
    ).fetchall()
    return [summarize(dict(zip(("dataset", "contributors") + _ROW_KEYS, row)))
            for row in rows]


def summarize(record):
    """Derive `empty_rate` and `finding`, and reconcile the buckets.

    THE ASSERTION IS THE POINT, not a safety net. The five buckets are a
    partition of the rows by construction, so a mismatch cannot come from data
    -- it can only come from a future edit that adds a vocabulary entry, or a
    filter, and forgets one of these expressions. Discovered that way it is a
    loud failure on the operator's own terminal; discovered the other way it is
    a report that quietly under-counts somebody's work, and nobody would ever
    know which somebody.
    """
    counted = sum(record[bucket] for bucket in BUCKETS)
    if counted != record["rows_total"]:
        raise ValueError(
            f"submission_log rows do not reconcile: {counted} in buckets "
            f"{BUCKETS} against {record['rows_total']} rows. A row is in no "
            f"bucket -- check that every value of `action` this report knows "
            f"about is still one of qc.SUBMISSION_ACTIONS, NULL, or `other`.")

    submits = record["submits"]
    #: None, not 0.0, where there is nothing to take a fraction of. A rate of
    #: zero and no evidence of a rate are different answers and the formatter
    #: prints them differently.
    record["empty_rate"] = (record["empty_submits"] / submits
                            if submits else None)
    record["finding"] = ""
    return record


def apply_findings(records, min_submits=DEFAULT_MIN_SUBMITS,
                   empty_rate=DEFAULT_EMPTY_RATE):
    """Label the rows worth a human look. Returns the same list.

    A contributor with only NULL-action rows reaches neither branch: `claims`
    and `submits` both count a value NULL never satisfies, so an unmeasurable
    worker is labelled nothing rather than labelled fine. That is the whole
    reason NULL is not collapsed into a bucket with a name.
    """
    for record in records:
        if record["submits"] == 0 and record["claims"] >= min_submits:
            record["finding"] = FINDING_NO_SUBMITS
        elif (record["submits"] >= min_submits
                and record["empty_rate"] is not None
                and record["empty_rate"] >= empty_rate):
            record["finding"] = FINDING_EMPTY_SUBMITS
        else:
            record["finding"] = ""
    return records


def _rate(value):
    """A percentage, or a dash where there is no denominator."""
    return "-" if value is None else f"{value * 100:.0f}%"


def format_table(records, key, key_header, extra=()):
    """A fixed-width table, the shape `manage_users.py list` prints.

    Column widths are computed from the data rather than hardcoded: contributor
    ids are `c_` plus twelve hex characters today, and dataset names are as long
    as the longest slug in the bank, which is not a number to freeze here.
    """
    columns = [(key_header, key)]
    columns += [(header, field) for header, field in extra]
    columns += [
        ("claims", "claims"), ("submits", "submits"), ("empty", "empty_submits"),
        ("empty%", None), (NULL_LABEL, "unknown_action"),
        ("other", "other_action"), ("fetched", "fetched"),
        ("accepted", "accepted"), ("finding", "finding"),
    ]

    def cell(record, header, field):
        if header == "empty%":
            return _rate(record["empty_rate"])
        value = record.get(field)
        return "-" if value is None else str(value)

    body = [[cell(record, header, field) for header, field in columns]
            for record in records]
    widths = [max(len(header), *(len(row[i]) for row in body)) if body
              else len(header)
              for i, (header, _) in enumerate(columns)]

    lines = ["  ".join(h.ljust(w) for (h, _), w in zip(columns, widths)).rstrip()]
    lines.append("  ".join("-" * w for w in widths))
    for row in body:
        lines.append("  ".join(c.ljust(w) for c, w in zip(row, widths)).rstrip())
    return "\n".join(lines)


def totals_line(records):
    """One line under the table, and the NULL caveat when there is one.

    The caveat is printed only when it applies, because a warning that is
    always there is a warning nobody reads -- and it is printed unconditionally
    when it does apply, because a reader comparing two contributors needs to
    know one of them has rows this report cannot classify.
    """
    if not records:
        return "no submission_log rows in range"
    total = {bucket: sum(r[bucket] for r in records) for bucket in BUCKETS}
    empty = sum(r["empty_submits"] for r in records)
    parts = [
        # The log-row count first, and the group count named as a group count:
        # a bare "4 row(s)" above a line reading "7 log row(s) carry a NULL
        # action" invites the reader to wonder how 7 of 4 rows are anything.
        f"{sum(r['rows_total'] for r in records)} log row(s) "
        f"over {len(records)} group(s)",
        f"{total['claims']} claim(s)",
        f"{total['submits']} submit(s) of which {empty} empty",
        f"{total['releases']} release(s)",
    ]
    line = "  ".join(parts)
    if total["unknown_action"]:
        line += (f"\n{total['unknown_action']} log row(s) carry a NULL action "
                 f"-- written before the column existed. They are counted as "
                 f"neither claims nor submits nor releases, and are excluded "
                 f"from every rate above.")
    if total["other_action"]:
        line += (f"\n{total['other_action']} log row(s) carry an action "
                 f"outside {sorted(qc.SUBMISSION_ACTIONS)}. The column is free "
                 f"TEXT, so this is possible; something wrote a value the "
                 f"vocabulary does not name.")
    return line


def cmd_report(args):
    with connect() as conn:
        if args.by_dataset:
            records = fetch_datasets(conn, args.since)
            key, header = "dataset", "dataset"
            extra = (("workers", "contributors"),)
        else:
            records = fetch_contributors(conn, args.since)
            key, header = "contributor_id", "contributor"
            extra = (("name", "name"),)

    apply_findings(records, args.min_submits, args.empty_rate)
    shown = ([r for r in records if r["finding"]] if args.empty_workers
             else records)

    if args.json:
        print(json.dumps(shown, indent=2, sort_keys=True))
        return
    if not shown:
        print("no submission_log rows in range" if not records
              else "no contributor met the finding thresholds")
        return
    print(format_table(shown, key, header, extra))
    print()
    print(totals_line(shown))


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Contribution counts over submission_log, and which "
                    "workers are submitting nothing.")
    p.add_argument("--since", default=None,
                   help="lower bound on submitted_at (YYYY-MM-DD or "
                        "YYYY-MM-DDTHH:MM:SS)")
    p.add_argument("--by-dataset", action="store_true",
                   help="group by query dataset instead of by contributor -- "
                        "the control for 'is the worker broken or the query "
                        "dead?'")
    p.add_argument("--empty-workers", action="store_true",
                   help="show only rows carrying a finding")
    p.add_argument("--min-submits", type=int, default=DEFAULT_MIN_SUBMITS,
                   help=f"submits (or claims) below which no finding is "
                        f"reported (default {DEFAULT_MIN_SUBMITS})")
    p.add_argument("--empty-rate", type=float, default=DEFAULT_EMPTY_RATE,
                   help=f"fraction of submits that must be empty to report a "
                        f"finding (default {DEFAULT_EMPTY_RATE})")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    args = p.parse_args(argv)
    try:
        cmd_report(args)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
