"""Record/replay for the six non-LLM fetchers: real upstream bytes, on disk.

WHY THIS EXISTS
    `evals/cache.py` made LLM answers replayable. Six of the nine pipeline
    scripts have no LLM in them at all -- they are fetch -> normalize ->
    upsert -- and every P0 in `docs/ingest/` lives in that half. What they
    need is the same trick one layer down: a saved upstream response per
    source, so a normalizer can be exercised against the real bytes an API
    returned instead of against a hand-written approximation of them.

    That is not a nicety. The defect register (deleted 2026-08-02:
    `git show refactor-freeze-2026-08-02:docs/ingest/DEFECTS.md`) disposes ten
    defects as "fix with harness -- task 09" precisely because the failing
    input is a
    shape nobody would invent: a Built In card whose company anchor is
    missing so the title/company zip slips by one (D02), a WWR item with no
    counters (D05), an Apify run that is already SUCCEEDED when the start
    call returns (D17). You cannot write those fixtures from the docs. You
    can only record them.

WHERE THE SEAM IS, AND WHY IT IS NOT lib/http.py
    `docs/ingestion_tests/05-fetcher-harness.md:63` describes this module as
    "record/replay for lib/http.py". That would cover two of the six sources.
    When this was written, four sites built their own request and called
    urllib directly, and this paragraph said they did it "to send a
    browser-ish User-Agent that lib/http.py does not take a parameter for".
    That reason was never true -- `get_text(headers=...)` merges over the
    default -- and D31's disposition (2026-08-02) moved three of the four to
    lib.http, User-Agent and all. One raw urlopen is left, and it is
    deliberate:

        ingest/builtin-nyc.py:281      urllib.request.urlopen(req, ...)

    It stays because lib.http would retry the 429 that `RateLimited` exists
    to stop on. Read that docstring before touching it; the split is now
    recorded rather than accidental.

    None of that changes where the seam is, which is the point of this
    section. `urllib.request.urlopen` is BELOW lib/http.py, which resolves it
    at call time (`open_fn = opener.open if opener else
    urllib.request.urlopen`, lib/http.py:79), so hooking it catches both
    shapes and would have caught them however D31 had been decided. One seam,
    six sources, and no test hook in lib/ -- which is this repo's own code
    now (`lib/__init__.py`) and used to be described here as vendored.

ADAPTERS, NEVER COPIES
    Nothing here parses anything. A cassette test imports the real ingest
    module and replays bytes into its real fetch/parse functions. A test that
    exercises a copy of the parser measures the copy.

THE KEY IS SCRUBBED, AND SO IS THE FILE
    An API key is never part of a cassette's key and never reaches disk.
    Rotating SERPAPI_API_KEY must not invalidate a recorded corpus, and a
    credential in git history is not something to do by accident. Secret
    query parameters are replaced with REDACTED in the stored URL *and* in
    the lookup key, secret request headers are dropped, and any value of a
    secret-shaped environment variable found anywhere in the recorded bytes
    is replaced before the file is written. Same rule as cache.py's THE KEY.

TIMING IS NEVER RECORDED
    A replayed response carries the latency of a call made months ago
    against a possibly different endpoint revision, so no cassette stores a
    duration and `Player.wall_clock` raises rather than returning one. The
    rule is enforced where the number would be read, not by asking each
    caller to remember -- the same choice `evals/report.py` made for cost.

RECORDING DATE IS PART OF THE FIXTURE
    A cassette recorded against a live source embeds that source's state on
    that day. `recorded_at` is stored, `provenance_line()` renders it with an
    age in days, and the cassette tests print it -- otherwise a fixture
    recorded in July silently becomes the specification in December.
"""

import base64
import datetime
import email.message
import hashlib
import io
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager

#: Where committed cassettes live. Unlike evals/.cache/ these ARE tracked:
#: they are small, they are the specification, and a fixture nobody can see
#: is a fixture nobody can correct.
CASSETTE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "fixtures", "cassettes")

#: On-disk format version. Bump only for a change a reader cannot ignore.
FORMAT_VERSION = 1

#: Query parameters whose value is a credential. Matched case-insensitively.
#: `token` is here for Apify, whose REST API takes ?token=; `api_key` for
#: SerpApi, whose URL is built at ingest/google-serpapi.py:277.
SECRET_PARAMS = frozenset({
    "api_key", "apikey", "key", "token", "access_token", "auth",
    "app_key", "app_id", "appid", "subscription-key", "signature",
})

#: Request headers never written to disk.
SECRET_HEADERS = frozenset({
    "authorization", "x-api-key", "x-auth-token", "cookie", "proxy-authorization",
})

REDACTED = "REDACTED"

#: Environment variables whose value is scrubbed out of recorded bytes
#: wholesale, wherever it appears. A response body echoing the token that
#: fetched it is not hypothetical -- Apify's run object carries the actor's
#: input, and the input is whatever the caller sent.
SECRET_ENV_SUFFIXES = ("_API_KEY", "_API_TOKEN", "_TOKEN", "_SECRET",
                       "_PASSWORD", "DATABASE_URL")

#: Keys a cassette may never contain, asserted by tests/test_cassettes.py.
#: See TIMING IS NEVER RECORDED above.
FORBIDDEN_KEYS = ("latency_s", "elapsed_s", "duration_s", "cost_usd")


class CassetteMiss(LookupError):
    """A request was made that the cassette does not hold.

    Deliberately fatal. Falling through to the network on a miss is how a
    "replayed" test quietly becomes a live test again -- and then starts
    failing on the day the upstream changes, weeks after the change that
    actually caused it.
    """


class CassetteError(RuntimeError):
    """The cassette file itself is unusable."""


# ---------------------------------------------------------------------------
# scrubbing
# ---------------------------------------------------------------------------

def scrub_url(url):
    """`url` with every secret query parameter's value replaced.

    Returns the scrubbed URL. Parameter ORDER and every non-secret value are
    preserved, because the scrubbed URL is both what is stored and what is
    matched on, and a normalisation that reordered parameters would make a
    cassette recorded by one caller unfindable by another.
    """
    parts = urllib.parse.urlsplit(url)
    if not parts.query:
        return url
    pairs = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    scrubbed = [(k, REDACTED if k.lower() in SECRET_PARAMS else v)
                for k, v in pairs]
    return urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, parts.path,
         urllib.parse.urlencode(scrubbed), parts.fragment))


def secret_values(environ=None):
    """Values of secret-shaped environment variables, longest first.

    Longest first so that a substring of one secret is not replaced before
    the whole one is, which would leave a recognisable tail on disk.
    """
    environ = os.environ if environ is None else environ
    out = []
    for name, value in environ.items():
        if not value or len(value) < 8:
            continue
        if any(name.upper().endswith(sfx) for sfx in SECRET_ENV_SUFFIXES):
            out.append(value)
    return sorted(set(out), key=len, reverse=True)


def scrub_text(blob, secrets=None):
    """Every known secret value in `blob`, replaced."""
    for secret in (secret_values() if secrets is None else secrets):
        blob = blob.replace(secret, REDACTED)
    return blob


def _scrub_headers(headers):
    return {k: v for k, v in (headers or {}).items()
            if k.lower() not in SECRET_HEADERS}


# ---------------------------------------------------------------------------
# the on-disk shape
# ---------------------------------------------------------------------------

def _body_fields(raw):
    """(body, body_b64) -- text when the bytes round-trip through utf-8.

    Round-TRIP, not merely decode: `errors="replace"` would decode anything
    and silently change the bytes, and a fixture whose bytes are not the
    bytes the server sent is worse than no fixture. Anything that does not
    survive intact is stored base64 and stays exact.
    """
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    try:
        text = raw.decode("utf-8")
        if text.encode("utf-8") == raw:
            return text, None
    except UnicodeDecodeError:
        pass
    return None, base64.b64encode(raw).decode("ascii")


class Interaction:
    """One request and the response it got."""

    def __init__(self, *, method, url, status, headers=None, body=None,
                 body_b64=None, request_body_sha256=None, reason=""):
        self.method = (method or "GET").upper()
        self.url = url
        self.status = int(status)
        self.headers = headers or {}
        self.body = body
        self.body_b64 = body_b64
        self.request_body_sha256 = request_body_sha256
        self.reason = reason

    @property
    def raw(self):
        if self.body_b64 is not None:
            return base64.b64decode(self.body_b64)
        return (self.body or "").encode("utf-8")

    def key(self):
        return (self.method, self.url, self.request_body_sha256)

    def loose_key(self):
        return (self.method, self.url)

    def to_json(self):
        out = {"method": self.method, "url": self.url, "status": self.status,
               "headers": self.headers}
        if self.reason:
            out["reason"] = self.reason
        if self.request_body_sha256:
            out["request_body_sha256"] = self.request_body_sha256
        if self.body_b64 is not None:
            out["body_b64"] = self.body_b64
        else:
            out["body"] = self.body or ""
        return out

    @classmethod
    def from_json(cls, raw):
        return cls(method=raw.get("method", "GET"), url=raw["url"],
                   status=raw.get("status", 200),
                   headers=raw.get("headers") or {},
                   body=raw.get("body"), body_b64=raw.get("body_b64"),
                   request_body_sha256=raw.get("request_body_sha256"),
                   reason=raw.get("reason", ""))


class Cassette:
    """A recorded conversation with one upstream, plus its provenance."""

    def __init__(self, name, *, source="", note="", recorded_at=None,
                 recorded_by="", interactions=None):
        self.name = name
        self.source = source
        self.note = note
        self.recorded_at = recorded_at
        self.recorded_by = recorded_by
        self.interactions = list(interactions or [])

    # -- disk ---------------------------------------------------------------

    @classmethod
    def path_for(cls, name, directory=None):
        return os.path.join(directory or CASSETTE_DIR, f"{name}.json")

    @classmethod
    def load(cls, name, directory=None):
        path = cls.path_for(name, directory)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except FileNotFoundError:
            raise CassetteError(
                f"no cassette {name!r} at {path}. Record it with "
                f"`python3 evals/record_cassettes.py {name}` -- see that "
                f"script for what it hits and what it costs.") from None
        except json.JSONDecodeError as e:
            raise CassetteError(f"{path} is not readable JSON: {e}") from None
        if raw.get("format_version") != FORMAT_VERSION:
            raise CassetteError(
                f"{path} is format_version {raw.get('format_version')!r}, "
                f"this reader speaks {FORMAT_VERSION}")
        return cls(name=raw.get("name", name),
                   source=raw.get("source", ""),
                   note=raw.get("note", ""),
                   recorded_at=raw.get("recorded_at"),
                   recorded_by=raw.get("recorded_by", ""),
                   interactions=[Interaction.from_json(i)
                                 for i in raw.get("interactions", [])])

    def save(self, directory=None):
        path = self.path_for(self.name, directory)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        payload = {
            "format_version": FORMAT_VERSION,
            "name": self.name,
            "source": self.source,
            "recorded_at": self.recorded_at,
            "recorded_by": self.recorded_by,
            "note": self.note,
            "interactions": [i.to_json() for i in self.interactions],
        }
        blob = scrub_text(json.dumps(payload, indent=1, ensure_ascii=False,
                                     sort_keys=False))
        tmp = f"{path}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(blob + "\n")
        os.replace(tmp, path)
        return path

    # -- provenance ---------------------------------------------------------

    def age_days(self):
        """Days since recording, or None if the cassette does not say."""
        if not self.recorded_at:
            return None
        try:
            when = datetime.datetime.strptime(
                self.recorded_at[:10], "%Y-%m-%d").replace(
                    tzinfo=datetime.timezone.utc)
        except ValueError:
            return None
        return (datetime.datetime.now(datetime.timezone.utc) - when).days

    def provenance_line(self):
        """The line a cassette test prints. See RECORDING DATE above."""
        age = self.age_days()
        aged = f", {age}d old" if age is not None else ""
        return (f"cassette {self.name}: {len(self.interactions)} interaction(s) "
                f"from {self.source or 'unknown source'}, "
                f"recorded {self.recorded_at or 'at an unrecorded date'}{aged}")

    # -- lookup -------------------------------------------------------------

    def player(self):
        return Player(self)


class Player:
    """Serves a cassette's interactions and refuses to serve anything else."""

    def __init__(self, cassette):
        self.cassette = cassette
        self.requests = []
        self._exact = {}
        self._loose = {}
        for i, interaction in enumerate(cassette.interactions):
            self._exact.setdefault(interaction.key(), []).append(i)
            self._loose.setdefault(interaction.loose_key(), []).append(i)
        self._used = set()

    @property
    def wall_clock(self):
        raise RuntimeError(
            "cost and latency are never reported from replay -- a replayed "
            "response carries the timing of a call made on "
            f"{self.cassette.recorded_at}, against a possibly different "
            "endpoint revision. Measure timing against the live source, or "
            "not at all.")

    def _take(self, method, url, body):
        """Index of the interaction answering this request.

        Exact match on (method, scrubbed url, request-body digest) first,
        because a POST-paginated source (Workday) sends the same URL with a
        different offset in the body. Falling back to (method, url) in
        RECORDED ORDER is what makes an ordinary paginated GET replay
        correctly without the caller having to think about it.
        """
        scrubbed = scrub_url(url)
        digest = hashlib.sha256(body).hexdigest() if body else None
        candidates = [(self._exact, (method, scrubbed, digest))]
        # The loose fallback is for a source that varies its url and not its
        # body -- every GET here. It must NOT apply when the recorded
        # interactions for this url are told apart BY their bodies: Workday
        # paginates by POST body against one endpoint, so answering
        # offset=2000 with whatever page happens to be first would turn a
        # miss into a wrong answer, which is the failure mode this whole
        # harness exists to remove.
        if not any(self.cassette.interactions[i].request_body_sha256
                   for i in self._loose.get((method, scrubbed), [])):
            candidates.append((self._loose, (method, scrubbed)))
        for table, key in candidates:
            for idx in table.get(key, []):
                if idx not in self._used:
                    self._used.add(idx)
                    return idx
            # Every copy consumed: replay the last one rather than missing.
            # A retry loop asking twice for the same page is asking a
            # question the cassette has already answered.
            if table.get(key):
                return table[key][-1]
        raise CassetteMiss(
            f"cassette {self.cassette.name!r} has no response for "
            f"{method} {scrubbed}"
            + (f" (body sha256 {digest[:12]})" if digest else "")
            + ".\nIt holds:\n  "
            + "\n  ".join(f"{i.method} {i.url}"
                          for i in self.cassette.interactions))

    def open(self, req, timeout=None, **_):
        """The urlopen replacement. Raises HTTPError for a recorded >=400."""
        method, url, body = _request_parts(req)
        self.requests.append((method, scrub_url(url)))
        interaction = self.cassette.interactions[self._take(method, url, body)]
        return _respond(interaction)


def _request_parts(req):
    """(method, url, body bytes) from whatever urlopen was handed."""
    if isinstance(req, urllib.request.Request):
        return req.get_method().upper(), req.full_url, req.data
    return "GET", str(req), None


def _headers(mapping):
    msg = email.message.Message()
    for k, v in (mapping or {}).items():
        msg[k] = v
    return msg


class _ReplayHTTPError(urllib.error.HTTPError):
    """HTTPError over an in-memory body.

    HTTPError inherits `tempfile._TemporaryFileWrapper` (via
    urllib.response.addbase), whose closer emits a ResourceWarning for any
    instance garbage-collected unclosed. A caught-and-dropped error is the
    normal case here -- lib/http.py:81 keeps one as `last_exc` and never
    closes it -- so every replayed retry would print a warning about a
    BytesIO that owns no resource. Marking the closer satisfied is the
    truthful statement: there is nothing to release.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        closer = getattr(self, "_closer", None)
        if closer is not None:
            closer.close_called = True


def _respond(interaction):
    raw = interaction.raw
    hdrs = _headers(interaction.headers)
    if interaction.status >= 400:
        # The shape lib/http.py:75-81 inspects: .code, .headers (for
        # Retry-After), and a readable fp so a caller that catches it can
        # still read the error body.
        raise _ReplayHTTPError(
            interaction.url, interaction.status,
            interaction.reason or "recorded error", hdrs, io.BytesIO(raw))
    return _ReplayResponse(interaction.url, interaction.status, hdrs, raw)


class _ReplayResponse(io.BytesIO):
    """Enough of http.client.HTTPResponse for every caller in this pipeline.

    BytesIO gives read()/close()/context-manager for free; the rest is the
    handful of attributes the six scripts and lib/http.py actually touch.
    """

    def __init__(self, url, status, headers, raw):
        super().__init__(raw)
        self.url = url
        self.status = status
        self.code = status
        self.headers = headers
        self.msg = "OK"

    def getcode(self):
        return self.status

    def geturl(self):
        return self.url

    def info(self):
        return self.headers


# ---------------------------------------------------------------------------
# replay / record
# ---------------------------------------------------------------------------

@contextmanager
def replay(name=None, directory=None, cassette=None):
    """Serve `name`'s recorded responses to every urllib caller in-process.

    Yields the Player, whose `.requests` is the ordered list of requests the
    code under test actually made -- which is itself an assertion target
    (Workday's "limit is hardcoded to 20" is a claim about the request, not
    about the response).
    """
    cas = cassette or Cassette.load(name, directory)
    player = cas.player()
    real = urllib.request.urlopen
    urllib.request.urlopen = player.open
    try:
        yield player
    finally:
        urllib.request.urlopen = real


@contextmanager
def recording(name, *, source="", note="", recorded_by="", directory=None,
              recorded_at=None):
    """Pass every urllib call through to the network and keep what came back.

    THIS HITS LIVE THIRD-PARTY ENDPOINTS. It is the only thing here that
    does, it is never invoked by a test, and it is driven exclusively by
    evals/record_cassettes.py so that what was recorded and what it cost is
    written down in one place.
    """
    cas = Cassette(name, source=source, note=note, recorded_by=recorded_by,
                   recorded_at=recorded_at or _today())
    real = urllib.request.urlopen

    def capture(req, *args, **kwargs):
        method, url, body = _request_parts(req)
        digest = hashlib.sha256(body).hexdigest() if body else None
        req_headers = _scrub_headers(
            dict(req.header_items()) if isinstance(req, urllib.request.Request)
            else {})
        try:
            resp = real(req, *args, **kwargs)
        except urllib.error.HTTPError as e:
            raw = e.read()
            cas.interactions.append(_captured(
                method, url, e.code, dict(e.headers or {}), raw, digest,
                reason=str(e.reason)))
            raise urllib.error.HTTPError(e.url, e.code, e.reason, e.headers,
                                         io.BytesIO(raw))
        with resp:
            raw = resp.read()
        cas.interactions.append(_captured(
            method, url, getattr(resp, "status", 200),
            _keep_headers(dict(resp.headers or {})), raw, digest))
        del req_headers          # recorded nowhere; see THE KEY IS SCRUBBED
        return _ReplayResponse(url, getattr(resp, "status", 200),
                               _headers(dict(resp.headers or {})), raw)

    urllib.request.urlopen = capture
    try:
        yield cas
    finally:
        urllib.request.urlopen = real
        cas.save(directory)


#: Response headers worth keeping. Everything else is per-connection noise
#: (Set-Cookie, CF-Ray, Date) that would make a diff of two recordings of the
#: same endpoint unreadable -- and Set-Cookie is a credential.
KEPT_HEADERS = ("content-type", "content-encoding", "retry-after",
                "x-ratelimit-remaining", "x-ratelimit-limit", "link")


def _keep_headers(headers):
    return {k: v for k, v in headers.items() if k.lower() in KEPT_HEADERS}


def _captured(method, url, status, headers, raw, digest, reason=""):
    body, body_b64 = _body_fields(raw)
    return Interaction(method=method, url=scrub_url(url), status=status,
                       headers=_keep_headers(headers), body=body,
                       body_b64=body_b64, request_body_sha256=digest,
                       reason=reason)


def _today():
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


@contextmanager
def no_sleep():
    """Neutralise lib/http.py's backoff for a replayed retry.

    A cassette holding a 429 followed by a 200 exercises the retry path in
    milliseconds; without this it exercises it in eight seconds, and a suite
    that takes eight seconds per retry test is a suite people stop running.
    """
    import time as _time
    real = _time.sleep
    _time.sleep = lambda _s: None
    try:
        yield
    finally:
        _time.sleep = real


def available(name, directory=None):
    """Whether `name` is on disk. For skipUnless in a test that needs it."""
    return os.path.exists(Cassette.path_for(name, directory))


def names(directory=None):
    """Every committed cassette name, sorted."""
    root = directory or CASSETTE_DIR
    if not os.path.isdir(root):
        return []
    return sorted(f[:-5] for f in os.listdir(root) if f.endswith(".json"))
