"""T-56: the body ceiling is the service's, not `submit`'s.

WHAT WAS WRONG. `MAX_BODY_BYTES` was enforced in exactly one place -- `submit`
reads `await request.body()` by hand and measures it before parsing. `claim`,
`release` and the mint route take a Pydantic body parameter instead, so
Starlette read the whole body into memory before any code in app.py ran, and
uvicorn sets no ceiling below that. The exposure is authenticated and it is not
new: `ReleaseRequest.reason` has been an unbounded caller-supplied string since
the endpoint existed. What T-35 changed is that `claim` became an inviting
shape, because a worker now posts a version, a count and an error string to it
every hour.

WHY THESE TESTS DRIVE RAW ASGI. `fastapi.testclient.TestClient` needs `httpx`,
which this venv does not have and which the service does not need at runtime --
the same trade test_malformed_body.py records and declines. A middleware IS an
ASGI callable, so calling it with a scope, a receive and a send is not a
reduction of the thing under test; it is the interface the server uses. The
integration class below goes further and drives `app.app` itself, so the
assertions are about the stack that is served rather than about a middleware
instance a test built.

THE ROUTE LIST IS DERIVED, NOT SPELLED OUT. TestEveryRouteWithABody walks
`app.app.routes` and refuses every POST route in it. The defect was that the
ceiling was per-function, so the case that matters most is the route nobody has
written yet -- a test naming today's four would go green on a fifth.
"""

import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fakedb import FakeConn, patch_db                   # noqa: E402

import app                                              # noqa: E402
from fastapi import HTTPException                       # noqa: E402
from starlette.exceptions import HTTPException as StarletteHTTPException  # noqa: E402
from starlette.requests import Request                  # noqa: E402

#: A body big enough to be refused under any cap these tests set, and small
#: enough that building it costs nothing.
CAP = 64


def scope_for(path="/v1/queries/claim", headers=(), method="POST"):
    """A minimal HTTP scope. Headers are (bytes, bytes), lowercased, as a real
    ASGI server delivers them -- the spec requires the server to lowercase, and
    a middleware that matched case-insensitively would be defending against
    something that cannot arrive."""
    return {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": method, "scheme": "http", "path": path,
        "raw_path": path.encode(), "query_string": b"", "root_path": "",
        "headers": list(headers), "client": ("127.0.0.1", 1234),
        "server": ("127.0.0.1", 8420),
    }


def content_length(n):
    return [(b"content-length", str(n).encode())]


class Recorder:
    """An inner ASGI app that records what it was handed and answers 200.

    It reads the body to exhaustion, because that is what the routes this
    middleware protects do -- a fake that never called receive() could not
    observe the counting branch at all.
    """

    def __init__(self, *, read_body=True):
        self.read_body = read_body
        self.calls = 0
        self.body = b""

    async def __call__(self, scope, receive, send):
        self.calls += 1
        if self.read_body:
            while True:
                message = await receive()
                if message["type"] != "http.request":
                    break
                self.body += message.get("body") or b""
                if not message.get("more_body"):
                    break
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": b'{"ok":true}'})


def chunked_receive(chunks):
    """A receive() that hands over `chunks` and then reports disconnect.

    Counts its own calls, so "the body was never read" is assertable rather
    than inferred from the absence of something else.
    """
    remaining = list(chunks)
    state = {"calls": 0}

    async def receive():
        state["calls"] += 1
        if not remaining:
            return {"type": "http.disconnect"}
        body = remaining.pop(0)
        return {"type": "http.request", "body": body,
                "more_body": bool(remaining)}

    receive.state = state
    return receive


def drive(asgi, scope, chunks=(b"",)):
    """Run an ASGI callable to completion and return (sent messages, receive)."""
    sent = []

    async def send(message):
        sent.append(message)

    receive = chunked_receive(chunks)
    asyncio.run(asgi(scope, receive, send))
    return sent, receive


def status_of(sent):
    for message in sent:
        if message["type"] == "http.response.start":
            return message["status"]
    raise AssertionError(f"no response was started: {sent}")


def body_of(sent):
    return b"".join(m.get("body") or b"" for m in sent
                    if m["type"] == "http.response.body")


class TestTheDeclaredLength(unittest.TestCase):
    """Content-Length over the cap: refused without the app being entered."""

    def test_an_oversized_declaration_is_refused(self):
        inner = Recorder()
        sent, _ = drive(app.BodySizeLimit(inner, max_bytes=CAP),
                        scope_for(headers=content_length(CAP + 1)))
        self.assertEqual(status_of(sent), 413)
        self.assertIn(b"payload too large", body_of(sent))

    def test_the_app_is_never_entered_and_the_body_never_read(self):
        # THE POINT OF THE ROW. Not "a large body is rejected" -- `submit`
        # already did that after buffering it -- but that nothing downstream
        # runs and no chunk is pulled into this process.
        inner = Recorder()
        sent, receive = drive(app.BodySizeLimit(inner, max_bytes=CAP),
                              scope_for(headers=content_length(CAP + 1)),
                              chunks=[b"x" * (CAP + 1)])
        self.assertEqual(status_of(sent), 413)
        self.assertEqual(inner.calls, 0)
        self.assertEqual(receive.state["calls"], 0)
        self.assertEqual(inner.body, b"")

    def test_exactly_the_cap_is_allowed_through(self):
        # The boundary is `>`, not `>=`: MAX_BODY_BYTES is a ceiling that is
        # itself permitted, which is the reading submit() has always used
        # (`len(raw) > MAX_BODY_BYTES`). The two must not disagree by one.
        inner = Recorder()
        sent, _ = drive(app.BodySizeLimit(inner, max_bytes=CAP),
                        scope_for(headers=content_length(CAP)),
                        chunks=[b"x" * CAP])
        self.assertEqual(status_of(sent), 200)
        self.assertEqual(inner.calls, 1)
        self.assertEqual(inner.body, b"x" * CAP)

    def test_the_largest_of_several_declarations_decides(self):
        # A duplicated Content-Length is malformed and a real server will
        # usually refuse it upstream. If one arrives, believing the smaller
        # value is what lets a caller under-declare.
        inner = Recorder()
        headers = content_length(1) + content_length(CAP + 1)
        sent, _ = drive(app.BodySizeLimit(inner, max_bytes=CAP),
                        scope_for(headers=headers))
        self.assertEqual(status_of(sent), 413)
        self.assertEqual(inner.calls, 0)


class TestTheUndeclaredBody(unittest.TestCase):
    """No Content-Length, or a lying one -- the half a header check cannot do."""

    def test_a_chunked_body_over_the_cap_is_refused(self):
        # HTTP/1.1 chunked transfer sends no Content-Length at all, so with
        # only the header check above this is a one-header bypass of the whole
        # ceiling.
        inner = Recorder()
        limited = app.BodySizeLimit(inner, max_bytes=CAP)
        with self.assertRaises(HTTPException) as caught:
            drive(limited, scope_for(), chunks=[b"x" * 32, b"y" * 40])
        self.assertEqual(caught.exception.status_code, 413)
        self.assertEqual(caught.exception.detail, app.TOO_LARGE_DETAIL)

    def test_a_chunked_body_under_the_cap_arrives_intact(self):
        inner = Recorder()
        sent, _ = drive(app.BodySizeLimit(inner, max_bytes=CAP),
                        scope_for(), chunks=[b"ab", b"cd", b"ef"])
        self.assertEqual(status_of(sent), 200)
        self.assertEqual(inner.body, b"abcdef")

    def test_a_declaration_smaller_than_the_body_does_not_buy_a_pass(self):
        # The lying-Content-Length case. The header check waves it through and
        # the counter is the thing that stops it, which is why both exist.
        inner = Recorder()
        limited = app.BodySizeLimit(inner, max_bytes=CAP)
        with self.assertRaises(HTTPException) as caught:
            drive(limited, scope_for(headers=content_length(4)),
                  chunks=[b"x" * (CAP + 1)])
        self.assertEqual(caught.exception.status_code, 413)

    def test_the_refusal_fires_before_the_whole_body_is_accumulated(self):
        # Counting only matters if it stops early. Six chunks of 32 bytes
        # against a cap of 64: the third is the one that crosses it, and the
        # remaining three must never be requested.
        inner = Recorder()
        limited = app.BodySizeLimit(inner, max_bytes=CAP)
        receive = chunked_receive([b"x" * 32] * 6)

        async def send(message):
            raise AssertionError(f"a response was sent: {message}")

        with self.assertRaises(HTTPException):
            asyncio.run(limited(scope_for(), receive, send))
        self.assertEqual(receive.state["calls"], 3)

    def test_an_unparseable_declaration_is_treated_as_absent(self):
        # Not as zero, and not as a reason to refuse: a garbled header must
        # neither switch the ceiling off nor become a way to 413 an honest
        # client. The counter is what answers for it.
        inner = Recorder()
        limited = app.BodySizeLimit(inner, max_bytes=CAP)
        for value in (b"", b"abc", b"-1", b"12 34"):
            with self.subTest(value):
                self.assertIsNone(
                    app._declared_length(scope_for(headers=[(b"content-length", value)])))
        with self.assertRaises(HTTPException):
            drive(limited, scope_for(headers=[(b"content-length", b"abc")]),
                  chunks=[b"x" * (CAP + 1)])

    def test_a_request_with_no_body_at_all_is_fine(self):
        inner = Recorder()
        sent, _ = drive(app.BodySizeLimit(inner, max_bytes=CAP),
                        scope_for(method="GET", path="/v1/health"), chunks=[b""])
        self.assertEqual(status_of(sent), 200)


class TestTheNonHttpScopes(unittest.TestCase):

    def test_lifespan_passes_straight_through(self):
        # verify_schema() runs in the lifespan, and a middleware that touched
        # that scope would put a body check in the startup path.
        seen = []

        async def inner(scope, receive, send):
            seen.append(scope["type"])

        asyncio.run(app.BodySizeLimit(inner, max_bytes=CAP)(
            {"type": "lifespan"}, None, None))
        self.assertEqual(seen, ["lifespan"])


class TestTheCapIsTheServiceSetting(unittest.TestCase):

    def test_the_registered_middleware_follows_the_module_constant(self):
        # A cap copied at construction is a second ceiling that nothing can
        # reach -- an operator raising MAX_BODY_BYTES would move submit()'s
        # check and not this one, and the two would refuse different requests.
        limited = app.BodySizeLimit(Recorder())
        original = app.MAX_BODY_BYTES
        try:
            app.MAX_BODY_BYTES = 7
            self.assertEqual(limited.max_bytes, 7)
        finally:
            app.MAX_BODY_BYTES = original
        self.assertEqual(limited.max_bytes, original)


class TestTheRefusalMatchesTheFramework(unittest.TestCase):
    """The 413 is hand-built ASGI, so pin it against what FastAPI renders."""

    def test_the_bytes_are_the_ones_the_handler_would_have_produced(self):
        # app.py builds this response by hand rather than importing
        # JSONResponse, because that import would have to sit at the top of the
        # file and move ~45 external `app.py:NNN` citations. That is only a safe
        # trade while the hand-built copy provably matches the framework's.
        handler = app.app.exception_handlers[StarletteHTTPException]
        rendered = asyncio.run(handler(
            Request(scope_for()),
            HTTPException(status_code=413, detail=app.TOO_LARGE_DETAIL)))

        sent, _ = drive(app.BodySizeLimit(Recorder(), max_bytes=CAP),
                        scope_for(headers=content_length(CAP + 1)))
        self.assertEqual(status_of(sent), rendered.status_code)
        self.assertEqual(body_of(sent), rendered.body)

    def test_submit_and_the_middleware_refuse_in_the_same_words(self):
        # A caller must not be able to tell which of the two refused it, and
        # after this row submit()'s literal is the shared constant rather than
        # a copy that can drift.
        with open(app.__file__, encoding="utf-8") as handle:
            source = handle.read()
        self.assertNotIn('detail="payload too large"', source)
        self.assertIn("detail=TOO_LARGE_DETAIL", source)


class TestItIsRegisteredOnTheServedApp(unittest.TestCase):
    """Everything above is a test of the service only if the service uses it."""

    def test_the_middleware_is_on_app_app(self):
        classes = [m.cls for m in app.app.user_middleware]
        self.assertIn(app.BodySizeLimit, classes)

    def test_it_is_the_outermost_user_middleware(self):
        # A body ceiling that runs after something else has already read the
        # body is not a ceiling. Nothing else is registered today; this is what
        # notices when something is.
        self.assertIs(app.app.user_middleware[0].cls, app.BodySizeLimit)


def concrete_path(route_path):
    """A routable URL for a path template, so the router matches it.

    Path parameters are filled with a value the endpoint would accept; what is
    behind them does not matter, because every assertion below is that the
    request is refused before any endpoint runs.
    """
    if "{dataset:path}" in route_path:
        return route_path.replace("{dataset:path}", "google_jobs:query:s0")
    return route_path


class TestEveryRouteWithABody(unittest.TestCase):
    """Driven through `app.app`, so this is the real stack: the middleware, the
    router, the endpoint and the exception handler that renders the refusal."""

    def refuse(self, path, headers=()):
        conn = FakeConn()
        restore = patch_db(app, conn)
        try:
            sent, receive = drive(app.app,
                                  scope_for(path=path,
                                            headers=list(headers)
                                            + content_length(app.MAX_BODY_BYTES + 1)))
        finally:
            restore()
        return sent, conn, receive

    def post_routes(self):
        found = []
        for route in app.app.routes:
            methods = getattr(route, "methods", None) or set()
            if "POST" in methods:
                found.append(concrete_path(route.path))
        return found

    def test_there_are_post_routes_to_check(self):
        # The loops below are vacuously green if this list is ever empty.
        self.assertGreaterEqual(len(self.post_routes()), 4)

    def test_every_post_route_refuses_an_oversized_body(self):
        # DERIVED FROM THE ROUTER, so a fifth POST route added without a body
        # ceiling arrives here as a failure. That is the defect this row is
        # about: the cap was a property of one function, so every new endpoint
        # started without one.
        for path in self.post_routes():
            with self.subTest(path):
                sent, _, _ = self.refuse(path)
                self.assertEqual(status_of(sent), 413)
                self.assertIn(b"payload too large", body_of(sent))

    def test_the_refusal_precedes_authentication(self):
        # No Authorization header at all, and the answer is 413 rather than
        # 401. An unauthenticated caller must not be able to make this service
        # buffer an arbitrary body -- if auth ran first, the body would already
        # have been read to get there.
        for path in self.post_routes():
            with self.subTest(path):
                sent, _, _ = self.refuse(path)
                self.assertEqual(status_of(sent), 413)

    def test_the_refusal_touches_no_database(self):
        # FakeConn raises on unrecognised SQL, so a request that reached an
        # endpoint would error rather than pass; these assert the stronger
        # thing, that nothing was recorded at all.
        for path in self.post_routes():
            with self.subTest(path):
                _, conn, _ = self.refuse(path, headers=[(b"authorization", b"Bearer key")])
                self.assertEqual(conn.log, [])
                self.assertEqual(conn.check_ins, [])
                self.assertEqual(conn.commits, 0)

    def test_the_body_is_never_pulled_off_the_wire(self):
        for path in self.post_routes():
            with self.subTest(path):
                _, _, receive = self.refuse(path)
                self.assertEqual(receive.state["calls"], 0)

    def test_an_undeclared_oversized_body_reaches_the_client_as_413(self):
        # THE CLAIM IN BodySizeLimit's DOCSTRING, THROUGH THE REAL STACK. The
        # counter raises from inside `receive`, and everything between it and
        # the client is framework: FastAPI's request handler re-raises an
        # HTTPException from the body read untouched but converts ANY other
        # exception into a 400 "There was an error parsing the body". So the
        # choice of exception class is the difference between a 413 and a
        # misleading 400, and only an end-to-end request can tell them apart --
        # the unit tests above see the exception before the framework has had
        # its say. No Content-Length here, so the header branch cannot answer.
        oversized = b"x" * (app.MAX_BODY_BYTES + 1)
        for path in self.post_routes():
            with self.subTest(path):
                conn = FakeConn()
                restore = patch_db(app, conn)
                try:
                    sent, _ = drive(
                        app.app,
                        scope_for(path=path,
                                  headers=[(b"authorization", b"Bearer key"),
                                           (b"content-type", b"application/json")]),
                        chunks=[oversized[:1024], oversized[1024:]])
                finally:
                    restore()
                self.assertEqual(status_of(sent), 413)
                self.assertIn(b"payload too large", body_of(sent))
                self.assertNotIn(b"parsing the body", body_of(sent))
                self.assertEqual(conn.log, [])


class TestTheHappyPathStillWorks(unittest.TestCase):
    """A ceiling that refuses everything would pass every test above."""

    def test_an_ordinary_claim_is_not_refused(self):
        conn = FakeConn(watermarks={})
        restore = patch_db(app, conn)
        body = b'{"max": 1}'
        headers = [(b"authorization", b"Bearer key"),
                   (b"content-type", b"application/json"),
                   (b"content-length", str(len(body)).encode())]
        try:
            sent, _ = drive(app.app, scope_for(headers=headers), chunks=[body])
        finally:
            restore()
        self.assertEqual(status_of(sent), 200)
        # And the poll did what it does: T-35's check-in was recorded, which
        # only happens if the request reached the endpoint with its body.
        self.assertEqual(len(conn.check_ins), 1)

    def test_submits_own_413_still_fires_with_its_existing_message(self):
        # The middleware makes submit()'s hand-rolled check unreachable over
        # HTTP, and it stays: it is the one that does not depend on middleware
        # registration, and test_malformed_body.py's oversize case calls
        # submit() directly. Pinned here too because the row requires it.
        from test_malformed_body import submit_and_catch
        exc, conn = submit_and_catch(b"[" + b"x" * (app.MAX_BODY_BYTES + 1))
        self.assertEqual(exc.status_code, 413)
        self.assertEqual(exc.detail, "payload too large")
        self.assertEqual(conn.log, [])


if __name__ == "__main__":
    unittest.main()
