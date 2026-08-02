"""Defect D73: a 400 on a malformed body must not quote the body back.

WHAT WAS WRONG. `submit` returned `detail=f"malformed body: {e}"` where `e` is a
pydantic ValidationError, and that exception's string form embeds
`input_value=`. For a field-level error that is the offending field; for
`json_invalid` -- which is every syntactically broken body -- it is the WHOLE
REQUEST BODY. A submit body is a SerpApi response the contributor fetched with
their own key, so whatever a worker sent came back out in the response.

WHY IT IS A DEFECT AND NOT A CRISIS. The only recipient is the sender, who
already has the bytes. `docs/tasks/refactor/tranche_six/33-deployment.md`
recorded it and declined to fix it because another stream owned this file. It
becomes an exposure the moment anything in front of the service logs response
bodies -- a reverse proxy, an error tracker, a tunnel access log -- and that is
a deployment decision made later by someone who will not have read the note.
The RUNBOOK's answer was a rule ("no payload is logged"); this is a property.

WHY THE ASSERTIONS ARE ON THE RENDERED RESPONSE, NOT ON `exc.detail`. What a
proxy logs is the serialized body, so that is what must be clean. These tests
render the exception through the handler `app.app` is actually configured with
(`app.app.exception_handlers`) rather than one imported by name, so a future
custom handler that reformatted the detail would be exercised here too. That is
also why this file exists at all rather than an assertion inside
tests/fakedb.py's world: the 400 is raised before `db()` is ever entered, so a
fake connection has nothing to observe -- there is no SQL on this path, which
is the whole point of rejecting a hostile body before parsing it.

`fastapi.testclient.TestClient` would be the obvious tool and is unavailable:
it needs `httpx`, which this venv does not have and which the service does not
need at runtime. Adding a test-only dependency to a deployed service's venv to
assert one response body is the wrong trade -- calling the endpoint coroutine
and rendering its exception exercises the same two objects.
"""

import ast
import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fakedb import FakeConn, FakeRequest, patch_db     # noqa: E402

import app                                            # noqa: E402
from fastapi import HTTPException                     # noqa: E402
from starlette.exceptions import HTTPException as StarletteHTTPException  # noqa: E402
from starlette.requests import Request                # noqa: E402

#: A marker with no other reason to appear in a response. Every hostile body
#: below carries it, so "did the input reach the output" is one substring test
#: rather than a judgement about which fragment counts as a leak.
SECRET = "SERPAPI-KEY-d41d8cd98f00b204e9800998ecf8427e"

#: Bodies that reach the `except` in submit(), one per shape pydantic reports
#: differently. The first is the one that echoed the ENTIRE body.
HOSTILE_BODIES = {
    "invalid json": b'{"jobs": [{"key": "' + SECRET.encode() + b'"}',
    "wrong type for jobs": b'{"jobs": "' + SECRET.encode() + b'"}',
    "wrong type inside jobs": b'{"jobs": ["' + SECRET.encode() + b'"]}',
    "not an object at all": b'"' + SECRET.encode() + b'"',
    "a number where a body should be": SECRET.encode(),
}


def submit_and_catch(body, conn=None):
    """Call the real endpoint with `body` and return the HTTPException it raised.

    A FakeConn is patched in even though this path never reaches the database:
    if a future edit moved the parse below `with db()`, the connection would be
    opened for real and the test would fail on a socket rather than silently
    exercising something else. `conn` is returned to the caller so it can assert
    that nothing was written.
    """
    conn = conn if conn is not None else FakeConn()
    restore = patch_db(app, conn)
    try:
        asyncio.run(app.submit("google_jobs:query:s0", FakeRequest(body),
                               authorization="Bearer key"))
    except HTTPException as e:
        return e, conn
    finally:
        restore()
    raise AssertionError("submit() accepted a malformed body")


def render(exc):
    """The response bytes a client -- or a logging proxy -- would actually see.

    Rendered through the handler registered on `app.app`, not through one
    imported directly, so this asserts about the app that is served.
    """
    handler = app.app.exception_handlers[StarletteHTTPException]
    scope = {"type": "http", "method": "POST", "http_version": "1.1",
             "path": "/v1/queries/google_jobs:query:s0/submit",
             "raw_path": b"/v1/queries/google_jobs:query:s0/submit",
             "query_string": b"", "headers": [], "app": app.app}
    response = asyncio.run(handler(Request(scope), exc))
    return response.status_code, response.body.decode()


class TestNoInputEcho(unittest.TestCase):

    def test_no_hostile_body_reaches_the_response(self):
        # THE DEFECT. Restore `detail=f"malformed body: {e}"` and every one of
        # these goes red -- the first two on the whole body, the rest on the
        # field value.
        for label, body in HOSTILE_BODIES.items():
            with self.subTest(label):
                exc, _ = submit_and_catch(body)
                status, rendered = render(exc)
                self.assertEqual(status, 400)
                self.assertNotIn(SECRET, rendered,
                                 f"{label}: the request body reached the "
                                 f"response: {rendered}")

    def test_the_whole_body_was_the_leak_not_one_field(self):
        # Worth its own test because it is the case that makes this more than
        # cosmetic: pydantic's `json_invalid` sets input_value to the entire
        # body, so a broken JSON submit echoed every posting in the batch.
        # Asserted on a distinctive fragment far from the syntax error, so a
        # fix that merely truncated would not pass.
        body = (b'{"jobs": [{"title": "Engineer", "company": "'
                + SECRET.encode() + b'", "x": 1}')
        exc, _ = submit_and_catch(body)
        _, rendered = render(exc)
        self.assertNotIn(SECRET, rendered)
        self.assertNotIn("Engineer", rendered)

    def test_no_fragment_of_the_body_survives_either(self):
        # A leak is not only the whole secret. Every run of >=6 characters from
        # the body must be absent, which catches a "fix" that truncated the
        # echoed value rather than removing it.
        body = b'{"jobs": "' + SECRET.encode() + b'"}'
        exc, _ = submit_and_catch(body)
        _, rendered = render(exc)
        window = 6
        text = body.decode()
        for i in range(len(text) - window):
            fragment = text[i:i + window]
            if fragment.strip('{}" :,'):
                self.assertNotIn(fragment, rendered,
                                 f"fragment {fragment!r} of the request body "
                                 f"reached the response")


class TestTheDiagnosticSurvives(unittest.TestCase):
    """A redaction that says nothing is a different bug, so pin what is kept."""

    def test_the_field_and_the_error_kind_are_still_named(self):
        exc, _ = submit_and_catch(b'{"jobs": "not-a-list"}')
        _, rendered = render(exc)
        self.assertIn("jobs", rendered)
        self.assertIn("list_type", rendered)

    def test_a_list_position_is_named(self):
        # `loc` carries integers for list indices, and an index is not input --
        # it is a position the server counted. Keeping it is what makes "the
        # third posting in your batch" answerable.
        exc, _ = submit_and_catch(b'{"jobs": [{}, {}, 3]}')
        _, rendered = render(exc)
        self.assertIn("jobs.2", rendered)

    def test_broken_json_says_so(self):
        exc, _ = submit_and_catch(b'{"jobs": [')
        _, rendered = render(exc)
        self.assertIn("json_invalid", rendered)

    def test_the_status_is_still_400(self):
        # 400 and not 500: the caller sent something wrong, and a 5xx here would
        # also be a deferral rather than a failure to every retrying worker.
        for body in HOSTILE_BODIES.values():
            exc, _ = submit_and_catch(body)
            self.assertEqual(exc.status_code, 400)


class TestNothingIsWrittenOnThePath(unittest.TestCase):

    def test_a_malformed_body_touches_no_table(self):
        # The size cap and the parse both run before `with db()`, deliberately:
        # a hostile payload should be refused without spending a connection or
        # a submission_log row. This is also what makes the tests above
        # meaningful without a database.
        exc, conn = submit_and_catch(b'{"jobs": [')
        self.assertEqual(exc.status_code, 400)
        self.assertEqual(conn.log, [])
        self.assertEqual(conn.commits, 0)
        self.assertEqual(conn.marked, [])
        self.assertEqual(conn.released, [])

    def test_an_oversized_body_is_refused_before_parsing(self):
        # Same path, one branch earlier, and the reason the parse cannot be the
        # first thing that runs.
        body = b"[" + b"x" * (app.MAX_BODY_BYTES + 1)
        exc, conn = submit_and_catch(body)
        self.assertEqual(exc.status_code, 413)
        _, rendered = render(exc)
        self.assertNotIn("x" * 20, rendered)
        self.assertEqual(conn.log, [])


class TestTheSummariser(unittest.TestCase):
    """`_validation_detail` directly, for the inputs no body can produce."""

    def test_a_non_pydantic_exception_degrades_to_a_constant(self):
        # The `except Exception` is deliberately broad -- model_validate_json
        # can raise before pydantic builds a ValidationError -- so the summary
        # has to answer for an object with no .errors() at all.
        self.assertEqual(app._validation_detail(ValueError("boom")),
                         "malformed body")

    def test_an_errors_call_that_raises_degrades_too(self):
        class Hostile(Exception):
            def errors(self):
                raise RuntimeError("no")

        self.assertEqual(app._validation_detail(Hostile()), "malformed body")

    def test_an_unsafe_loc_component_is_replaced_not_printed(self):
        # loc is field names and indices for THIS module's models. The filter is
        # a whitelist anyway, because "pydantic cannot put caller bytes in loc"
        # is a claim about a third-party library across versions, and the point
        # of the fix is not to depend on one.
        class Fake(Exception):
            def errors(self):
                return [{"loc": ("jobs", SECRET), "type": "dict_type"}]

        detail = app._validation_detail(Fake())
        self.assertNotIn(SECRET, detail)
        self.assertIn("jobs.?", detail)

    def test_an_unsafe_type_is_replaced_too(self):
        class Fake(Exception):
            def errors(self):
                return [{"loc": ("jobs",), "type": SECRET}]

        detail = app._validation_detail(Fake())
        self.assertNotIn(SECRET, detail)
        self.assertIn("invalid", detail)

    def test_many_errors_are_truncated_to_a_bounded_summary(self):
        # A batch of fifty bad postings produces fifty errors, and a response
        # that grows with the request is its own small amplification.
        class Fake(Exception):
            def errors(self):
                return [{"loc": ("jobs", i), "type": "dict_type"}
                        for i in range(50)]

        detail = app._validation_detail(Fake())
        self.assertIn(f"and {50 - app.MAX_REPORTED_ERRORS} more", detail)
        self.assertLess(len(detail), 400)

    def test_an_empty_error_list_still_says_something(self):
        class Fake(Exception):
            def errors(self):
                return []

        self.assertEqual(app._validation_detail(Fake()), "malformed body")


class TestTheHandlerUnderTestIsTheOneServed(unittest.TestCase):

    def test_the_submit_route_dispatches_to_this_function(self):
        # Everything above calls app.submit as a plain coroutine. That is only
        # a test of the service if the router points there.
        routes = {getattr(r, "path", None): getattr(r, "endpoint", None)
                  for r in app.app.routes}
        self.assertIs(routes.get("/v1/queries/{dataset:path}/submit"),
                      app.submit)

    def test_the_parse_handler_calls_the_summariser_and_not_an_f_string(self):
        # The defect was one f-string. A future edit that reintroduced it would
        # pass every assertion above only until pydantic changed its formatting,
        # so the shape is pinned as well as the behaviour.
        #
        # Read out of the AST rather than grepped for the old literal: that
        # literal is quoted in _validation_detail's own docstring, where it
        # belongs, and a substring search cannot tell the history from the code.
        # This also refuses to be satisfied by the OTHER f-string details in
        # submit() -- "too many jobs (max ...)" interpolates a server constant,
        # which is fine, and a blanket ban on f-strings here would be false.
        source = ast.parse(open(app.__file__, encoding="utf-8").read())
        submit = next(n for n in ast.walk(source)
                      if isinstance(n, ast.AsyncFunctionDef) and n.name == "submit")
        handlers = [h for node in ast.walk(submit)
                    if isinstance(node, ast.Try) for h in node.handlers]
        self.assertTrue(handlers, "submit() no longer guards the parse")

        details = []
        for handler in handlers:
            for node in ast.walk(handler):
                if not (isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call)):
                    continue
                for kw in node.exc.keywords:
                    if kw.arg == "detail":
                        details.append(kw.value)

        self.assertEqual(len(details), 1)
        detail = details[0]
        self.assertNotIsInstance(
            detail, ast.JoinedStr,
            "the parse handler interpolates into its detail again -- an "
            "f-string over a ValidationError echoes the request body")
        self.assertIsInstance(detail, ast.Call)
        self.assertEqual(detail.func.id, "_validation_detail")


if __name__ == "__main__":
    unittest.main()
