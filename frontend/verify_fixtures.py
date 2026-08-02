#!/usr/bin/env python3
"""Check that every fixture under fixtures/shipped/ still matches the code.

WHY THIS EXISTS. API-CONTRACT-v1.md § Mocking asks for frozen responses that
"become contract tests both sides run" once the backend lands. Half of that is
free -- the frontend builds against the JSON. The other half is this: a fixture
nobody re-checks becomes a description of an API that used to exist, which is
worse than no fixture, because it is confidently wrong.

WHAT IT CHECKS, AND WHAT IT DELIBERATELY DOES NOT. It checks SHAPE -- the exact
key set of every job object, the top-level keys of every response, the event
vocabulary and the dismiss vocabulary. It does not check values: nothing here
can know that Mount Sinai is hiring. A shape check is what actually breaks when
someone adds a column to LIST_COLUMNS, which is the failure this is for.

IT READS THE SOURCE, IT DOES NOT IMPORT IT. backend/webapp/jobs.py imports
fastapi and pydantic, which live only in webapp/.venv (both venvs set
include-system-site-packages = false, see .claude/CLAUDE.md). Parsing the
constants out with `ast` means this runs under the top level's bare system
python3 with no venv and no dependency, which is the only way it gets run
often enough to be worth having.

    python3 frontend/verify_fixtures.py

Exit status 0 if every fixture matches, 1 otherwise, listing everything wrong
rather than the first thing -- the same reason webapp/schema_web.py's
verify_schema() collects problems instead of raising on the first.
"""

import ast
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
JOBS_PY = REPO / "backend" / "webapp" / "jobs.py"
SCHEMA_WEB_PY = REPO / "backend" / "webapp" / "schema_web.py"
AUTH_PY = REPO / "backend" / "webapp" / "auth.py"
SHIPPED = HERE / "fixtures" / "shipped"


# --------------------------------------------------------------------------
# Reading constants out of the source
# --------------------------------------------------------------------------

def _tuples(path):
    """Every module-level NAME = (...) tuple-of-literals in one file.

    Resolves the one composition the file actually uses --
    DETAIL_COLUMNS = LIST_COLUMNS + ("description_text",) -- and nothing more
    general than that. A second form appearing in jobs.py should fail loudly
    here rather than be silently skipped, so anything unrecognised is dropped
    and the caller's KeyError names it.
    """
    tree = ast.parse(path.read_text())
    out = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        value = node.value
        if isinstance(value, ast.BinOp) and isinstance(value.op, ast.Add):
            left, right = value.left, value.right
            if isinstance(left, ast.Name) and left.id in out:
                try:
                    out[target.id] = out[left.id] + tuple(ast.literal_eval(right))
                except (ValueError, TypeError):
                    pass
                continue
        try:
            literal = ast.literal_eval(value)
        except (ValueError, TypeError, SyntaxError):
            continue
        if isinstance(literal, tuple) and all(isinstance(v, str) for v in literal):
            out[target.id] = literal
    return out


def _me_keys():
    """The keys GET /v1/me returns, read from the dict literal it returns.

    auth.py's me() is the only function in that file whose body is a single
    Return of a dict of `user.<attr>` values, so it is found by name rather
    than by shape.
    """
    tree = ast.parse(AUTH_PY.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "me":
            for stmt in ast.walk(node):
                if isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Dict):
                    return tuple(k.value for k in stmt.value.keys)
    raise LookupError("auth.me() no longer returns a dict literal")


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------

def _load(name):
    return json.loads((SHIPPED / name).read_text())


#: Every module-level tuple-of-strings jobs.py declares, and what this file
#: does with it. Anything NOT here fails the run rather than being ignored --
#: which is the whole of defect D70.
#:
#: D70: cohort_signal (task 28) landed as a THIRD response-key group,
#: COHORT_FIELDS, between STATE_FIELDS and rank. The row composition below read
#: two groups and hardcoded the tail, so the new key was invisible to it: the
#: fixtures omitted cohort_signal, this file's expectation omitted it too, the
#: two agreed with each other, and BOTH disagreed with the source. A verifier
#: stops being a derivation exactly where its hardcoding starts, and that is
#: where the next field always lands. Adding COHORT_FIELDS to the composition
#: fixes the instance; this map is what fixes the class, because a fourth group
#: cannot arrive without a name that is not in it.
_KNOWN_JOBS_TUPLES = {
    "LIST_COLUMNS":          "row keys, list",
    "DETAIL_COLUMNS":        "row keys, detail",
    "STATE_FIELDS":          "row keys, both",
    "COHORT_FIELDS":         "row keys, both -- task 28",
    "CLIENT_EVENT_NAMES":    "event vocabulary",
    "SERVER_EVENT_NAMES":    "event vocabulary",
    "RANK_REQUIRED_EVENTS":  "event vocabulary",
    "COHORT_VISIBLE_EVENTS": "not a response shape; visibility, checked nowhere here",
}


def check(problems):
    jobs = _tuples(JOBS_PY)
    web = _tuples(SCHEMA_WEB_PY)

    # THE GUARD THAT CLOSES D70 AS A CLASS. A new tuple in jobs.py is either a
    # new response-key group -- in which case the composition below is now
    # wrong and silently passing -- or it is not, in which case saying so here
    # costs one line. Either way it must not be possible to add one and have
    # this file keep exiting 0 without a person having looked.
    unknown = sorted(set(jobs) - set(_KNOWN_JOBS_TUPLES))
    if unknown:
        problems.append(
            f"jobs.py declares tuple(s) {unknown} that verify_fixtures.py does not "
            f"know about. If any is a response-key group, add it to the row "
            f"composition in check(); if not, add it to _KNOWN_JOBS_TUPLES saying "
            f"so. This guard exists because cohort_signal (D70) arrived exactly "
            f"this way and nothing noticed.")

    # DERIVED, NOT LITERAL, except for `rank` -- SEE THE NEXT COMMENT.
    # The endpoint builds the list row as LIST_COLUMNS + STATE_FIELDS +
    # cohort_signal + rank (jobs.py, list_jobs: the zip names, then the pop and
    # re-assign that moves cohort_signal to the end, then the rank loop). The
    # detail row is the same without rank, because a detail request is not a
    # render and has no position.
    list_row = (tuple(jobs["LIST_COLUMNS"]) + tuple(jobs["STATE_FIELDS"])
                + tuple(jobs["COHORT_FIELDS"]) + ("rank",))
    detail_row = (tuple(jobs["DETAIL_COLUMNS"]) + tuple(jobs["STATE_FIELDS"])
                  + tuple(jobs["COHORT_FIELDS"]))

    # `rank` IS STILL A LITERAL AND THAT SEAM IS STILL OPEN, narrowly. There is
    # no module-level constant naming it: the endpoint assigns
    # `item["rank"] = first_rank + offset` inside the handler, so there is
    # nothing for _tuples() to read. Deriving it would mean pattern-matching a
    # subscript assignment in a function body, which is a worse trade -- it
    # would break on a rename of `item` and pass on a rename of `rank`.
    #
    # WHAT THE RESIDUE ACTUALLY IS, MEASURED RATHER THAN REASONED. Renaming
    # `item["rank"]` to `item["position"]` in jobs.py and running this file
    # against the current fixtures exits 0. Tested 2026-08-02 on a throwaway
    # copy. The fixtures still say "rank", the expectation below still says
    # "rank", the two agree with each other and both disagree with the source
    # -- which is D70's exact sentence with one field substituted.
    #
    # So the guard above does NOT cover `rank`. What it covers is the arrival
    # of a new response-key GROUP, because a group comes with a module-level
    # tuple and an unrecognised name fails the run. Two things remain uncovered
    # and both need a person:
    #
    #   * renaming `rank`, per the measurement above;
    #   * a new response key added as a bare subscript assignment with no
    #     module-level constant at all.
    #
    # Both are narrower than what D70 was, and neither is closed. Written out
    # rather than left to be rediscovered, because the absence of exactly this
    # sentence is what produced D70.
    client_events = set(jobs["CLIENT_EVENT_NAMES"])
    server_events = set(jobs["SERVER_EVENT_NAMES"])
    reasons = set(web["DISMISS_REASONS"])
    rank_required = set(jobs["RANK_REQUIRED_EVENTS"])

    def keyset(where, got, want):
        got, want = list(got), list(want)
        if got == want:
            return
        missing = [k for k in want if k not in got]
        extra = [k for k in got if k not in want]
        if missing or extra:
            problems.append(f"{where}: missing {missing}, unexpected {extra}")
        else:
            problems.append(f"{where}: same keys, wrong order\n"
                            f"    got  {got}\n    want {want}")

    # -- the list endpoint --------------------------------------------------
    for name in ("GET_v1_jobs.json", "GET_v1_jobs.page2.json",
                 "GET_v1_jobs.empty.json"):
        body = _load(name)
        keyset(f"{name} (top level)", body,
               ("request_id", "jobs", "next_cursor", "profile"))
        for i, row in enumerate(body["jobs"]):
            keyset(f"{name} jobs[{i}]", row, list_row)

    # rank is 1-based and continues across pages via the cursor.
    page1, page2 = _load("GET_v1_jobs.json"), _load("GET_v1_jobs.page2.json")
    ranks = [r["rank"] for r in page1["jobs"]] + [r["rank"] for r in page2["jobs"]]
    if ranks != list(range(1, len(ranks) + 1)):
        problems.append(f"rank is not 1..N across the two pages: {ranks}")
    if page1["request_id"] != page2["request_id"]:
        problems.append("page 2 has a different request_id; a render spans pages")

    # The cursor is opaque but it is not arbitrary: decoding it must yield the
    # last row of page 1, the render, and the rank page 2 starts at.
    import base64
    raw = page1["next_cursor"]
    payload = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
    last = page1["jobs"][-1]
    expected = {"v": 2, "s": last["match_score"], "t": last["posted_at_ts"],
                "i": last["id"], "r": page1["request_id"],
                "k": page1["jobs"][-1]["rank"] + 1}
    if payload != expected:
        problems.append(f"next_cursor decodes to {payload}, expected {expected}")

    # -- the detail endpoint ------------------------------------------------
    for name in ("GET_v1_jobs_by_id.json", "GET_v1_jobs_by_id.dismissed.json"):
        keyset(name, _load(name), detail_row)

    # -- events -------------------------------------------------------------
    request = _load("POST_v1_events.request.json")
    keyset("POST_v1_events.request.json", request, ("request_id", "events"))
    for i, e in enumerate(request["events"]):
        if e["event"] not in client_events:
            problems.append(f"events[{i}]: '{e['event']}' is not a client event name")
        if e["event"] in rank_required and "rank" not in e:
            problems.append(f"events[{i}]: '{e['event']}' requires rank")
        if "reason" in e and e["event"] != "dismiss":
            problems.append(f"events[{i}]: reason on '{e['event']}'")
        if "reason" in e and e.get("reason") not in reasons:
            problems.append(f"events[{i}]: unknown reason {e.get('reason')!r}")
        if "dwell_ms" in e and e["event"] != "open":
            problems.append(f"events[{i}]: dwell_ms on '{e['event']}'")

    for name in ("POST_v1_events.response.json",
                 "POST_v1_events.response.empty_batch.json"):
        keyset(name, _load(name),
               ("recorded", "deduped", "skipped", "derived_skips"))

    # -- me -----------------------------------------------------------------
    keyset("GET_v1_me.json", _load("GET_v1_me.json"), _me_keys())

    # -- errors -------------------------------------------------------------
    # Every enveloped fixture's code must be one the validator can actually
    # raise, and the two vocabularies must not overlap.
    raised = set()
    tree = ast.parse(JOBS_PY.read_text())
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "ContractError" and node.args
                and isinstance(node.args[0], ast.Constant)):
            raised.add(node.args[0].value)

    for path in sorted((SHIPPED / "errors").glob("*.json")):
        body = json.loads(path.read_text())
        if path.name.startswith("NOT-ENVELOPED-"):
            keyset(f"errors/{path.name}", body, ("detail",))
            continue
        keyset(f"errors/{path.name}", body, ("error",))
        keyset(f"errors/{path.name} .error", body["error"],
               ("code", "message", "request_id"))
        if body["error"]["code"] not in raised:
            problems.append(f"errors/{path.name}: code "
                            f"{body['error']['code']!r} is raised nowhere in jobs.py")

    if client_events & server_events:
        problems.append("CLIENT_EVENT_NAMES and SERVER_EVENT_NAMES overlap")
    if "applied" not in client_events:
        problems.append("'applied' is no longer a client event name (DEC-73)")
    if "apply" in client_events:
        problems.append("'apply' is a client event name again; DEC-73 says 'applied'")


def main():
    problems = []
    check(problems)
    if problems:
        print(f"{len(problems)} problem(s):\n")
        for p in problems:
            print(f"  - {p}")
        print("\nfixtures/shipped/ no longer describes the code. Either the "
              "fixtures are stale or the change was unintended.")
        return 1
    print("fixtures/shipped/ matches backend/webapp/{jobs,auth,schema_web}.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
