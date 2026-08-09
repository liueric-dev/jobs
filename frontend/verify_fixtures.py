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

IT READS TWO TOP-LEVEL MODULES AS WELL AS THE FOUR IN webapp/, and that is not
sprawl. `backend/searchnorm.py` and `backend/schema.py` are where task 25 put
the two things a search response is checked against -- the InvalidQuery codes a
client can receive, and the watcher-bucket vocabulary -- precisely so that one
definition serves both processes. Reading them here rather than restating four
codes and three labels is the same rule the rest of this file follows.

    python3 frontend/verify_fixtures.py

Exit status 0 if every fixture matches, 1 otherwise, listing everything wrong
rather than the first thing -- the same reason webapp/schema_web.py's
verify_schema() collects problems instead of raising on the first.
"""

import ast
import base64
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
JOBS_PY = REPO / "backend" / "webapp" / "jobs.py"
SCHEMA_WEB_PY = REPO / "backend" / "webapp" / "schema_web.py"
AUTH_PY = REPO / "backend" / "webapp" / "auth.py"
ONBOARDING_PY = REPO / "backend" / "webapp" / "onboarding.py"
SEARCH_PY = REPO / "backend" / "webapp" / "search.py"
#: NOT under backend/webapp/. searchnorm.py is a TOP-LEVEL pipeline module that
#: both processes import, for the reason its own docstring gives: a second
#: `normalize()` in webapp/ would not fail loudly, it would quietly halve the
#: cache hit rate. Its InvalidQuery codes reach a client through search.py's
#: `raise ContractError(bad.code, str(bad))`, so the error fixtures below need
#: it -- see _contract_codes().
SEARCHNORM_PY = REPO / "backend" / "searchnorm.py"
#: Also top-level: the suppression threshold and the bucket vocabulary live
#: beside COHORT_MIN_SAVERS in schema.py rather than in searchnorm.py, because
#: schema.py generates the CHECK constraint from the same tuple the writer
#: reads (searchnorm.py's own docstring says so). So the labels a
#: `watcher_bucket` may carry are derived from there and never listed here.
SCHEMA_PY = REPO / "backend" / "schema.py"
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


def _returned_dict_keys(path, function):
    """The keys one function returns, read from the dict literal it returns.

    THE GENERAL FORM OF WHAT _me_keys() WAS. Four response shapes in this repo
    are a single `return {…}` of string keys -- auth.me(), and onboarding's
    _state(), get_onboarding() and post_onboarding() -- so one reader covers
    all four and a fifth costs a call rather than a function.

    IT RAISES RATHER THAN RETURNING EMPTY. A response shape that stops being a
    dict literal is exactly the moment this file stops deriving anything, and
    the D70 lesson is that a check which silently degrades to agreeing with the
    fixture is worse than no check: the two agree with each other and both
    disagree with the source.
    """
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == function:
            for stmt in ast.walk(node):
                if isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Dict):
                    return tuple(k.value for k in stmt.value.keys)
    raise LookupError(f"{path.name}:{function}() no longer returns a dict literal")


def _me_keys():
    """The keys GET /v1/me returns.

    auth.py's me() is the only function in that file whose body is a single
    Return of a dict of `user.<attr>` values, so it is found by name rather
    than by shape.
    """
    return _returned_dict_keys(AUTH_PY, "me")


def _model_fields(path, model):
    """The field names one pydantic model declares, in declaration order.

    WHY THE ORDER AND NOT JUST THE SET. A request fixture is what a client
    author types against, so the key order is documentation; but the reason
    this check exists at all is the SET. Pydantic IGNORES unknown fields by
    default, so a client sending `prior_domains` for `prior_domain` gets a 200
    and stores nothing -- the Builder answered a question that went nowhere and
    was told it worked. That is silence, this system's documented failure mode
    (.claude/CLAUDE.md), reached through a typo, and a shape check on the
    request fixture is the only thing on either side that catches it.

    Reads AnnAssign targets in the class body only -- not nested, not inherited
    -- which is the one form OnboardingRequest uses.
    """
    tree = ast.parse(path.read_text())
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == model:
            return tuple(stmt.target.id for stmt in node.body
                         if isinstance(stmt, ast.AnnAssign)
                         and isinstance(stmt.target, ast.Name))
    raise LookupError(f"{path.name} declares no class {model}")


def _dict_literal(path, name):
    """A module-level NAME = {"a": "b", ...} mapping of string literals.

    onboarding.VERDICT_EVENTS is a dict rather than a tuple because it IS a
    mapping -- verdict to event name -- and flattening it to a tuple here would
    lose the half that matters. Narrow on purpose, like _tuples(): anything
    that is not a plain dict of string constants is skipped, and the caller's
    KeyError names it.
    """
    tree = ast.parse(path.read_text())
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == name):
            try:
                literal = ast.literal_eval(node.value)
            except (ValueError, TypeError, SyntaxError):
                break
            if isinstance(literal, dict) and all(
                    isinstance(k, str) and isinstance(v, str)
                    for k, v in literal.items()):
                return literal
    raise LookupError(f"{path.name}: {name} is no longer a module-level "
                      f"dict of string literals")


def _literal(path, name):
    """A module-level NAME = <any literal>, whatever its shape.

    _tuples() above is deliberately narrow -- tuples of strings only -- and
    schema.SEARCH_WATCHER_BUCKETS is `((6, "4-6"), (10, "7-10"), (None, "11+"))`,
    which is neither. Rather than widen the narrow reader (whose narrowness is
    what makes an unrecognised form fail loudly), this is the general one, used
    only where the shape is known and named.
    """
    tree = ast.parse(path.read_text())
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == name):
            try:
                return ast.literal_eval(node.value)
            except (ValueError, TypeError, SyntaxError):
                break
    raise LookupError(f"{path.name}: {name} is no longer a module-level literal")


def _contract_codes(*paths):
    """Every `code` a ContractError or an InvalidQuery can be raised with.

    TWO CALL SHAPES, ONE VOCABULARY, AND THE SECOND ONE IS WHY THIS IS NOT A
    ONE-LINER. jobs.py and search.py raise `ContractError("some_code", ...)`
    with the code as a literal, which is readable directly. But search.py also
    raises `ContractError(bad.code, str(bad))` where `bad` is a
    searchnorm.InvalidQuery -- so four of the codes a client can receive from
    POST /v1/searches appear NOWHERE in backend/webapp/ as a constant, and a
    reader that only looked there would report them as "raised nowhere" and
    fail on a fixture that is correct. Reading InvalidQuery's own first
    arguments out of searchnorm.py is the derivation; hardcoding the four here
    would be the seam D70 came through, one file to the left.
    """
    codes = set()
    for path in paths:
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id in ("ContractError", "InvalidQuery")
                    and node.args and isinstance(node.args[0], ast.Constant)):
                codes.add(node.args[0].value)
    return codes


def _int_literal(path, name):
    """A module-level NAME = <int>."""
    tree = ast.parse(path.read_text())
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == name
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, int)):
            return node.value.value
    raise LookupError(f"{path.name}: {name} is no longer a module-level int")


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


#: The same treatment for search.py, and it is here BECAUSE D70 WOULD OTHERWISE
#: HAVE HAPPENED TWICE. `_KNOWN_JOBS_TUPLES` above closed the class for one
#: file; task 25 then landed a second router with its own module-level tuples
#: -- QUERY_COLUMNS and RESPONSE_NAMES -- and no guard at all, so a new group
#: there would have arrived exactly the way `cohort_signal` did, into a checker
#: that had already learned the lesson in the next file over. A guard that
#: protects one file is a guard against one instance.
#:
#: THE QUERY ROW HAS NO `rank`-SHAPED RESIDUE, which is worth saying because
#: the list row does. _row_to_query() (search.py) composes the object as
#: `RESPONSE_NAMES + _SIGNAL_FIELDS` and assigns no key inside the handler, so
#: the expectation below is derived end to end. The results row is a different
#: story and inherits jobs.py's residue verbatim: search_results() does its own
#: `item["rank"] = first_rank + offset`, so `rank` is a literal there for the
#: same reason and with the same two uncovered cases.
_KNOWN_SEARCH_TUPLES = {
    "QUERY_COLUMNS":   "the search_queries columns SELECTed; the storage half",
    "RESPONSE_NAMES":  "response keys, query object; the rendered half",
    "_SIGNAL_FIELDS":  "response keys, query object -- appended by _row_to_query",
}


def check(problems):
    jobs = _tuples(JOBS_PY)
    web = _tuples(SCHEMA_WEB_PY)
    search = _tuples(SEARCH_PY)

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

    unknown = sorted(set(search) - set(_KNOWN_SEARCH_TUPLES))
    if unknown:
        problems.append(
            f"search.py declares tuple(s) {unknown} that verify_fixtures.py does "
            f"not know about. Same rule as jobs.py above: if any is a "
            f"response-key group, add it to the query-row composition in "
            f"check(); if not, add it to _KNOWN_SEARCH_TUPLES saying so.")

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

    # -- onboarding ---------------------------------------------------------
    #
    # THESE TWO FIXTURES WERE `contract/ASPIRATIONAL_POST_v1_onboarding.*` AND
    # THE PREFIX HAD GONE FALSE. Task 26 gave the endpoint a route
    # (onboarding.py:540, mounted at app.py:106) while frontend/README.md was
    # being written, so two files describing a live route sat in the directory
    # this script deliberately does not read, and NOTHING checked them against
    # the code they described. They are in shipped/ now and this block is the
    # check they never had.
    #
    # EVERY EXPECTATION HERE IS DERIVED, WITH NO `rank`-SHAPED RESIDUE. All
    # three response shapes are single dict literals and the request shape is a
    # pydantic model, so there is nothing to hardcode -- which is a better
    # position than the list endpoint is in, and is worth saying because the
    # reason is luck rather than virtue: onboarding.py assembles no key inside
    # a handler the way jobs.py assigns item["rank"].
    onboarding_state = _returned_dict_keys(ONBOARDING_PY, "_state")
    request_fields = _model_fields(ONBOARDING_PY, "OnboardingRequest")
    verdicts = _dict_literal(ONBOARDING_PY, "VERDICT_EVENTS")
    max_seed = _int_literal(ONBOARDING_PY, "MAX_SEED_JUDGEMENTS")

    for name in ("GET_v1_onboarding.json", "GET_v1_onboarding.first_run.json"):
        body = _load(name)
        keyset(f"{name} (top level)", body,
               _returned_dict_keys(ONBOARDING_PY, "get_onboarding"))
        keyset(f"{name} .onboarding", body["onboarding"], onboarding_state)

    response = _load("POST_v1_onboarding.response.json")
    keyset("POST_v1_onboarding.response.json", response,
           _returned_dict_keys(ONBOARDING_PY, "post_onboarding"))
    keyset("POST_v1_onboarding.response.json .onboarding",
           response["onboarding"], onboarding_state)

    # `completed_at` HAS NO ZONE AND MUST NOT GROW ONE. builder_profiles.
    # onboarded_at is TEXT (schema_web.py:553) written by
    # lib.timeparse.utc_now_str(), whose docstring says the
    # '%Y-%m-%dT%H:%M:%S' shape is load-bearing and "must not gain an offset or
    # microseconds" because both pipelines compare these as STRINGS. The fixture
    # carried a trailing 'Z' -- inherited from the contract, which invented the
    # response shape -- and a client doing new Date(completed_at) on the real
    # value reads it as local time. Same trap `first_seen` already sets, which
    # is why format.mjs appends the Z itself.
    for name in ("GET_v1_onboarding.json", "POST_v1_onboarding.response.json"):
        stamp = _load(name)["onboarding"]["completed_at"]
        if stamp is not None and not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}",
                                                  stamp):
            problems.append(
                f"{name}: completed_at {stamp!r} is not utc_now_str()'s "
                f"'%Y-%m-%dT%H:%M:%S'. onboarded_at is TEXT written by that "
                f"function (schema_web.py, onboarding.py); an offset here is a "
                f"fixture inventing a timezone the column does not carry.")

    # A first-run Builder is `completed: false` with NULL everywhere, and NULL
    # is not the prior_domain literally named 'none' -- schema_web.py:177-182
    # makes that distinction load-bearing.
    first_run = _load("GET_v1_onboarding.first_run.json")["onboarding"]
    if first_run["completed"] is not False or first_run["completed_at"] is not None:
        problems.append("GET_v1_onboarding.first_run.json: not a first-run state")
    if first_run["prior_domain"] is not None:
        problems.append(
            "GET_v1_onboarding.first_run.json: prior_domain must be null, not "
            "'none'. NULL means nobody asked; 'none' is a real answer.")

    request = _load("POST_v1_onboarding.request.json")
    keyset("POST_v1_onboarding.request.json", request, request_fields)

    # The four closed vocabularies the handler validates against, plus the
    # array one. Read from _VOCABULARIES' own tuples so a widened vocabulary
    # cannot be accepted here and refused by the column.
    for field, tuple_name in (("prior_domain", "PRIOR_DOMAINS"),
                              ("situation", "SITUATIONS"),
                              ("location_pref", "LOCATION_PREFS"),
                              ("remote_pref", "REMOTE_PREFS")):
        value = request.get(field)
        if value is not None and value not in web[tuple_name]:
            problems.append(f"POST_v1_onboarding.request.json: {field} {value!r} "
                            f"is not in schema_web.{tuple_name}")
    for value in request.get("schedule_constraints") or ():
        if value not in web["SCHEDULE_CONSTRAINTS"]:
            problems.append(f"POST_v1_onboarding.request.json: schedule "
                            f"constraint {value!r} is not in "
                            f"schema_web.SCHEDULE_CONSTRAINTS")

    seed = request.get("seed_judgements") or []
    if len(seed) > max_seed:
        problems.append(f"POST_v1_onboarding.request.json: {len(seed)} seed "
                        f"judgements exceeds MAX_SEED_JUDGEMENTS ({max_seed})")
    seen_ids = set()
    for i, judgement in enumerate(seed):
        keyset(f"POST_v1_onboarding.request.json seed_judgements[{i}]",
               judgement, ("job_id", "verdict"))
        if judgement.get("verdict") not in verdicts:
            problems.append(f"seed_judgements[{i}]: verdict "
                            f"{judgement.get('verdict')!r} is not a "
                            f"VERDICT_EVENTS key")
        # Two verdicts on one posting is a 400 with code
        # duplicate_seed_judgement (onboarding.py:356-365), so a fixture
        # carrying one would be a request the endpoint refuses.
        if judgement.get("job_id") in seen_ids:
            problems.append(f"seed_judgements[{i}]: job "
                            f"{judgement.get('job_id')} judged twice; that is a "
                            f"400, code duplicate_seed_judgement")
        seen_ids.add(judgement.get("job_id"))

    # The event names the verdicts map onto have to be ones POST /v1/events
    # accepts, because record_seed_judgements() goes through jobs.record_events()
    # rather than a second INSERT (onboarding.py:454-495).
    for verdict, event in verdicts.items():
        if event not in client_events:
            problems.append(f"VERDICT_EVENTS[{verdict!r}] = {event!r}, which is "
                            f"not in CLIENT_EVENT_NAMES")

    # -- searches -----------------------------------------------------------
    #
    # TASK 25's SIX ROUTES. The query object is fully derived -- see
    # _KNOWN_SEARCH_TUPLES on why there is no `rank`-shaped residue on this
    # half -- and the RESULTS object is jobs.py's list row, imported rather
    # than restated (search.py imports LIST_COLUMNS, STATE_FIELDS,
    # COHORT_FIELDS and the joins), so the same `list_row` above is the
    # expectation here. That is the property worth freezing: a client renders
    # both lists with ONE renderer, and the day the two shapes drift is the day
    # it needs two.
    query_row = tuple(search["RESPONSE_NAMES"]) + tuple(search["_SIGNAL_FIELDS"])

    # THE RENAME IS POSITIONAL, SO THE TWO TUPLES MUST STAY THE SAME LENGTH.
    # _row_to_query() zips RESPONSE_NAMES against a row SELECTed as
    # QUERY_COLUMNS, so adding a column to one and not the other does not raise
    # -- zip() stops at the shorter -- it silently drops a field or shifts
    # every name onto the wrong value. Nothing else in either process notices.
    if len(search["QUERY_COLUMNS"]) != len(search["RESPONSE_NAMES"]):
        problems.append(
            f"search.py: QUERY_COLUMNS has {len(search['QUERY_COLUMNS'])} entries "
            f"and RESPONSE_NAMES has {len(search['RESPONSE_NAMES'])}. _row_to_query() "
            f"zips one against the other, so an unequal pair silently mislabels "
            f"columns rather than raising.")

    sources = _tuples(SCHEMA_PY)["SEARCH_SOURCES"]
    buckets = tuple(label for _, label in _literal(SCHEMA_PY, "SEARCH_WATCHER_BUCKETS"))

    def check_query(where, item):
        keyset(where, item, query_row)
        # THE TWO FIELDS THAT MUST NEVER APPEAR, and their absence is the whole
        # privacy argument rather than an oversight. `first_requested_at` is the
        # moment one identifiable person typed something, and timing is the
        # strongest deanonymiser available in a cohort who sit in a room
        # together (search.py's module docstring, tranche_five/28).
        # `computed_at` moves when the underlying watcher set moves, which hands
        # back the recency channel the bucketing exists to close -- the same
        # column jobs._COHORT_COLUMNS refuses for the same reason.
        for forbidden in ("first_requested_at", "computed_at", "watcher_count",
                          "watchers", "app_user_id"):
            if forbidden in item:
                problems.append(f"{where}: carries {forbidden!r}, which no "
                                f"search response may (search.py's docstring)")
        if item.get("source") not in sources:
            problems.append(f"{where}: source {item.get('source')!r} is not in "
                            f"schema.SEARCH_SOURCES {list(sources)}")
        # NULL OR A LABEL, NEVER A NUMBER. watcher_bucket is NOT NULL on
        # search_query_signal (schema.py) and the row is ABSENT below
        # SEARCH_MIN_WATCHERS, so the LEFT JOIN yields exactly two kinds of
        # value. A fixture carrying an integer, a zero or a "fewer than four"
        # string would be teaching a client author to render the suppression as
        # a count, which is the one thing DEC-85 exists to prevent.
        bucket = item.get("watcher_bucket")
        if bucket is not None and bucket not in buckets:
            problems.append(
                f"{where}: watcher_bucket {bucket!r} is not null and is not one "
                f"of schema.SEARCH_WATCHER_BUCKETS {list(buckets)}. Below "
                f"SEARCH_MIN_WATCHERS there is NO ROW, so null is the only "
                f"other legal value -- never a count, never a floor.")
        if not isinstance(item.get("watching"), bool):
            problems.append(f"{where}: `watching` is the caller's own fact and "
                            f"is a bool, not {item.get('watching')!r}")

    for name in ("GET_v1_searches.suggested.json", "GET_v1_searches.mine.json",
                 "GET_v1_searches.mine.empty.json"):
        body = _load(name)
        keyset(f"{name} (top level)", body,
               _returned_dict_keys(SEARCH_PY, "list_searches"))
        for i, item in enumerate(body["searches"]):
            check_query(f"{name} searches[{i}]", item)
        # `scope` is echoed, and the endpoint's own Query pattern is the closed
        # set: there is deliberately no third scope (search.py, list_searches).
        if body["scope"] not in ("mine", "suggested"):
            problems.append(f"{name}: scope {body['scope']!r} is outside the "
                            f"endpoint's ^(mine|suggested)$ pattern")

    # The suggested catalogue is `source IN ('seeded','track') AND retired_at IS
    # NULL` by the WHERE clause, and every row carries a role_track because the
    # seeder writes one per track. THAT role_track IS THE QUERY'S, NOT A
    # POSTING'S -- see the note in fixtures/shipped/MANIFEST.json. The two never
    # share a JSON object and conflating them is the mistake this feature makes
    # available for the first time.
    for i, item in enumerate(_load("GET_v1_searches.suggested.json")["searches"]):
        if item["source"] not in ("seeded", "track"):
            problems.append(f"GET_v1_searches.suggested.json searches[{i}]: "
                            f"source {item['source']!r}; the suggested scope "
                            f"selects seeded and track rows only")
        if item["role_track"] is None:
            problems.append(f"GET_v1_searches.suggested.json searches[{i}]: "
                            f"role_track is null on a seeded query")
        if item["retired_at"] is not None:
            problems.append(f"GET_v1_searches.suggested.json searches[{i}]: "
                            f"retired_at is set; the scope filters those out")

    for name in ("POST_v1_searches.response.json", "GET_v1_searches_by_id.json",
                 "POST_v1_searches_watch.json", "POST_v1_searches_unwatch.json"):
        check_query(name, _load(name))

    keyset("POST_v1_searches.request.json", _load("POST_v1_searches.request.json"),
           _model_fields(SEARCH_PY, "SearchRequest"))

    # ONE QUERY CANNOT HAVE TWO ANSWERS, the same rule the cohort_signal pair is
    # held to. Query 4 appears in three fixtures and a badge is a fact about the
    # query, not about which route you asked.
    listed = [q for q in _load("GET_v1_searches.suggested.json")["searches"]
              if q["id"] == 4]
    mine = [q for q in _load("GET_v1_searches.mine.json")["searches"]
            if q["id"] == 4]
    by_id = _load("GET_v1_searches_by_id.json")
    if not (listed and mine and listed[0] == mine[0] == by_id):
        problems.append(
            "query 4 differs between GET_v1_searches.suggested.json, "
            "GET_v1_searches.mine.json and GET_v1_searches_by_id.json. All three "
            "are _select_queries() over the same row.")

    # WATCH AND UNWATCH DIFFER IN ONE FIELD AND ONLY ONE. Unwatching is an
    # UPDATE setting removed_at, never a delete (searchnorm.UNWATCH_SQL), and
    # the response is the same row re-read -- so anything else moving between
    # this pair means the fixtures invented a side effect the route has not got.
    watched, unwatched = (_load("POST_v1_searches_watch.json"),
                          _load("POST_v1_searches_unwatch.json"))
    differ = sorted(k for k in query_row if watched.get(k) != unwatched.get(k))
    if differ != ["watching"]:
        problems.append(
            f"watch and unwatch differ in {differ}, expected ['watching'] alone. "
            f"Unwatch is an UPDATE of removed_at and a re-read of the same row; "
            f"it changes nothing else, and in particular does not move a bucket "
            f"the service holds no grant to write.")

    # -- search results -----------------------------------------------------
    #
    # THE SHAPE IS /v1/jobs' SHAPE, FIELD FOR FIELD, and that is the point
    # rather than a coincidence: a search result list is a rendered list,
    # position bias applies identically, and task 27's instrumentation is
    # unusable if half the renders in the product report positions in a
    # different vocabulary. `list_row` here is the SAME variable the /v1/jobs
    # fixtures are checked against, so the two cannot pass while disagreeing.
    for name in ("GET_v1_searches_results.json", "GET_v1_searches_results.page2.json",
                 "GET_v1_searches_results.empty.json"):
        body = _load(name)
        keyset(f"{name} (top level)", body,
               _returned_dict_keys(SEARCH_PY, "search_results"))
        for i, row in enumerate(body["jobs"]):
            keyset(f"{name} jobs[{i}]", row, list_row)

    r1, r2 = (_load("GET_v1_searches_results.json"),
              _load("GET_v1_searches_results.page2.json"))
    ranks = [r["rank"] for r in r1["jobs"]] + [r["rank"] for r in r2["jobs"]]
    if ranks != list(range(1, len(ranks) + 1)):
        problems.append(f"search results: rank is not 1..N across the two "
                        f"pages: {ranks}")
    if r1["request_id"] != r2["request_id"]:
        problems.append("search results page 2 has a different request_id; a "
                        "render spans pages here exactly as it does on /v1/jobs")
    if r1["query_id"] != r2["query_id"]:
        problems.append("search results page 2 belongs to a different query_id")
    raw = r1["next_cursor"]
    payload = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
    last = r1["jobs"][-1]
    expected = {"v": 2, "s": last["match_score"], "t": last["posted_at_ts"],
                "i": last["id"], "r": r1["request_id"], "k": last["rank"] + 1}
    if payload != expected:
        problems.append(f"search results next_cursor decodes to {payload}, "
                        f"expected {expected}")

    # ONE POSTING CANNOT HAVE TWO ANSWERS EITHER. Mount Sinai is in the /v1/jobs
    # fixture and in this one; cohort_signal is a fact about the posting, not
    # about which list surfaced it.
    listed_job = _load("GET_v1_jobs.json")["jobs"][0]
    found = [j for j in r1["jobs"] if j["id"] == listed_job["id"]]
    if found and found[0]["cohort_signal"] != listed_job["cohort_signal"]:
        problems.append(
            f"{listed_job['id']} carries cohort_signal "
            f"{found[0]['cohort_signal']!r} in the search results and "
            f"{listed_job['cohort_signal']!r} in the job list")

    # -- errors -------------------------------------------------------------
    # Every enveloped fixture's code must be one the validator can actually
    # raise, and the two vocabularies must not overlap.
    #
    # THREE FILES, NOT ONE, AND THE THIRD IS NOT UNDER webapp/. search.py
    # re-raises searchnorm.InvalidQuery as a ContractError carrying the
    # exception's own `code`, so `empty_query` and its three neighbours are
    # reachable by a client and appear as a literal only in
    # backend/searchnorm.py. See _contract_codes().
    raised = _contract_codes(JOBS_PY, SEARCH_PY, SEARCHNORM_PY)

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
    print("fixtures/shipped/ matches "
          "backend/webapp/{jobs,auth,schema_web,onboarding,search}.py "
          "and backend/{searchnorm,schema}.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
