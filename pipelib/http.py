"""HTTP with retry/backoff.

Lifted from ticketmaster-seatgeek-ingest.py, which had the only real retry
logic anywhere in either pipeline -- jobs/ had none at all, so a single
transient 503 from one ATS board failed that company for the day.

The distinction worth keeping: transient failures (network error, 429, 5xx)
back off and retry; permanent ones (401 bad key, 400 bad request, 404) raise
immediately. Retrying a permanent failure just burns wall-clock and API quota
without any possibility of succeeding, and on a metered key that costs real
requests.

Some upstreams signal rejection with a 200 and an error *body* rather than a
status code -- queenslibrary.org's WAF returns HTTP 200 with a "Request
Rejected" page when it decides a client looks abusive. `body_is_transient`
lets a caller declare that shape retryable; status codes alone cannot see it.
"""

import json
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_USER_AGENT = "hermes-ingest/1.0 (+https://github.com/hermes)"
DEFAULT_TIMEOUT = 30
DEFAULT_MAX_RETRIES = 5
MAX_BACKOFF = 60


class TransientBody(Exception):
    """A 200 response whose body indicates a retryable rejection."""


def _backoff(attempt, retry_after=None):
    wait = min(MAX_BACKOFF, (2 ** attempt) + random.uniform(0, 1))
    if retry_after:
        try:
            wait = max(wait, float(retry_after))
        except (TypeError, ValueError):
            pass
    return wait


def get_text(url, *, headers=None, timeout=DEFAULT_TIMEOUT,
             max_retries=DEFAULT_MAX_RETRIES, opener=None,
             body_is_transient=None, data=None, method=None, label=None):
    """Fetch a URL as text, retrying transient failures.

    `opener` accepts a urllib opener so a caller can carry cookies (QPL needs
    a session established against /calendar before /search/call returns data).
    `body_is_transient` is a predicate over the response body.
    """
    hdrs = {"User-Agent": DEFAULT_USER_AGENT}
    if headers:
        hdrs.update(headers)
    tag = label or url.split("?")[0]
    last_exc = None

    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, data=data, headers=hdrs,
                                         method=method)
            open_fn = opener.open if opener else urllib.request.urlopen
            with open_fn(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8", errors="replace")
            if body_is_transient and body_is_transient(body):
                # No tag here -- callers prefix it, and the retry log below
                # already does, so including it prints "qpl: qpl: ...".
                raise TransientBody("upstream rejected the request")
            return body

        except urllib.error.HTTPError as e:
            if e.code != 429 and not (500 <= e.code < 600):
                raise  # permanent -- surface immediately
            wait = _backoff(attempt, e.headers.get("Retry-After") if e.headers else None)
            print(f"[retry] {tag}: HTTP {e.code}, waiting {wait:.1f}s "
                  f"(attempt {attempt + 1}/{max_retries})", file=sys.stderr)
            last_exc = e

        except (urllib.error.URLError, TransientBody, TimeoutError,
                ConnectionError) as e:
            wait = _backoff(attempt)
            print(f"[retry] {tag}: {e}, waiting {wait:.1f}s "
                  f"(attempt {attempt + 1}/{max_retries})", file=sys.stderr)
            last_exc = e

        if attempt < max_retries - 1:
            time.sleep(wait)

    raise last_exc


def get_json(url, **kwargs):
    """get_text() parsed as JSON."""
    return json.loads(get_text(url, **kwargs))


def post_json(url, payload, *, headers=None, **kwargs):
    """POST a JSON body, parse a JSON response. Used by the NYPL GraphQL API."""
    hdrs = {"Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)
    return json.loads(get_text(
        url, data=json.dumps(payload).encode(), headers=hdrs, method="POST",
        **kwargs))


def urlencode(params):
    """Re-exported so callers don't each import urllib.parse."""
    return urllib.parse.urlencode(params)
