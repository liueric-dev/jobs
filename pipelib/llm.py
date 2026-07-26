"""Minimal OpenAI-compatible chat client and tolerant JSON extraction.

Extracted from jobs/score.py. Nothing here is jobs-specific -- the prompt,
the persona and the result schema all stay with the caller; this module only
knows how to make the call and get structured output back out of it.

Deliberately stdlib urllib rather than an SDK, matching the rest of the
codebase. Works against anything speaking the OpenAI wire format: Z.ai (the
current default), Groq, OpenRouter, a local Ollama/LM Studio server.

    LLM_BASE_URL   default https://api.z.ai/api/paas/v4
    LLM_MODEL      default glm-4.5-flash
    LLM_API_KEY    falls back to GLM_API_KEY

Free-tier budgets are enforced client-side by pipelib.ratelimit (LLM_MAX_RPM
/ LLM_MAX_RPD, both per-model). Unset means unlimited, so this stays a no-op
for local and paid endpoints.
"""

import json
import os
import re
import subprocess
import urllib.error
import urllib.request

from . import ratelimit

DEFAULT_BASE_URL = "https://api.z.ai/api/paas/v4"
DEFAULT_MODEL = "glm-4.5-flash"
#: Socket timeout per call. 120s, not 60, because 60 was cutting off work
#: that was about to succeed: glm-4.5-flash runs a 39s median but a 85s max,
#: so the slow tail was timing out, raising TransientError, and deferring
#: jobs that the model would have answered given a few more seconds. In a
#: backfill smoke test that cost 3 rounds out of 7 -- every call in them
#: deferred, none of them actually failing.
#:
#: A longer timeout costs nothing when the endpoint is healthy (fast calls
#: still return fast) and only delays the verdict when it is genuinely
#: hung. Set LLM_TIMEOUT_SECS to override.
DEFAULT_TIMEOUT_SECS = int(os.environ.get("LLM_TIMEOUT_SECS", "120"))

#: Sampling temperature. 0 because everything this module is used for is
#: structured extraction against a fixed schema -- there is no upside to
#: sampling, and a large downside.
#:
#: Measured on 40 real postings, scored twice with identical prompts:
#:
#:     qwen2.5:14b, provider default   Spearman 0.666, top-15 overlap 11/15
#:     qwen2.5:14b, temperature 0      Spearman 1.000, top-15 overlap 15/15
#:
#: At the default, a third of the shortlist reshuffled between two runs of
#: the same model over the same jobs. Scores are ranked and read top-down, so
#: that is the difference between a ranking and a lottery. It also made model
#: comparison nearly meaningless: run-to-run variance for one model was the
#: same size as the gap between two different models.
#:
#: Set LLM_TEMPERATURE if a caller genuinely wants sampling.
DEFAULT_TEMPERATURE = float(os.environ.get("LLM_TEMPERATURE", "0"))

#: Backend selection. "http" (default) is the original OpenAI-compatible
#: HTTP path. "claude" shells out to `claude -p` and bills against a Claude
#: Pro/Max subscription (OAuth), not an API key -- the only way to reach a
#: Claude subscription from a script. See _call_claude() for the why.
DEFAULT_BACKEND = os.environ.get("LLM_BACKEND", "http").strip().lower()

#: Overridable because `claude` is not always on PATH for a cron-spawned
#: process, whose environment is far smaller than an interactive shell's.
CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "claude")


def backend():
    return DEFAULT_BACKEND


#: Prefix written into the model column when an attempt fails permanently.
FAILED_PREFIX = "FAILED:"


def base_url():
    return os.environ.get("JOB_SCORING_BASE_URL",
                          os.environ.get("LLM_BASE_URL", DEFAULT_BASE_URL))


def model():
    #: The "claude" backend has no per-request model id -- the Claude CLI
    #: picks it from its own config / subscription. We report a stable label
    #: for the scores table so the provenance column stays meaningful and
    #: scores stay comparable within one backend.
    if backend() == "claude":
        return os.environ.get("JOB_SCORING_MODEL",
                              os.environ.get("LLM_MODEL", "claude-sonnet"))
    return os.environ.get("JOB_SCORING_MODEL",
                          os.environ.get("LLM_MODEL", DEFAULT_MODEL))


def api_key():
    #: "claude" authenticates via the CLI's OAuth store, not a bearer token,
    #: so no env key is needed. The sentinel is returned purely so that
    #: callers guarding on `if not llm.api_key()` (score.py, extract.py) let
    #: the run proceed. It is never sent anywhere -- _call_claude() does not
    #: build an Authorization header.
    if backend() == "claude":
        return "claude-cli-oauth"
    return (os.environ.get("JOB_SCORING_API_KEY")
            or os.environ.get("LLM_API_KEY")
            or os.environ.get("GLM_API_KEY"))


class TransientError(RuntimeError):
    """The call failed for a reason that says nothing about this prompt.

    Rate limits, timeouts, connection resets, 5xx. Retrying later is expected
    to work, so a caller must NOT record a permanent outcome for the item it
    was working on -- see failed_label() and the tombstone discussion there.
    """


#: Retrying these is worthwhile; anything else is the server's final answer.
TRANSIENT_STATUSES = frozenset({408, 409, 425, 429, 500, 502, 503, 504})


def call(prompt, *, timeout=DEFAULT_TIMEOUT_SECS, json_object=True):
    """One chat completion. Returns the message content as a string.

    Raises TransientError when the failure is retryable and plain
    RuntimeError when it is not. That distinction is the caller's only way to
    tell "this model cannot handle this prompt" from "this endpoint was busy",
    and getting it wrong permanently discards work: a 429 recorded as a
    failure means that item is never attempted again.

    Both backends honour that contract; only the transport differs.
    """
    active_model = model()

    # Before the request, not after: the point is to not send the call that
    # would 429. QuotaExhausted becomes a TransientError because the prompt
    # was never evaluated -- see ratelimit's module docstring.
    try:
        ratelimit.acquire(active_model)
    except ratelimit.QuotaExhausted as e:
        raise TransientError(str(e))

    if backend() == "claude":
        return _call_claude(prompt, active_model, timeout)
    return _call_http(prompt, active_model, timeout, json_object)


#: CLI output that means "try again later" rather than "this prompt is bad".
#: Without this every rate limit would raise RuntimeError and the caller would
#: tombstone a job that was never evaluated -- the exact failure mode
#: TRANSIENT_STATUSES exists to prevent on the HTTP path.
_CLAUDE_TRANSIENT = re.compile(
    r"rate.?limit|overloaded|usage limit|quota|too many requests"
    r"|\b(429|500|502|503|504)\b|timed? out",
    re.IGNORECASE)


def _call_claude(prompt, active_model, timeout):
    """One `claude -p` call, billed against a Claude Pro/Max subscription via
    the CLI's OAuth store rather than an API key.

    --output-format json wraps the answer in an envelope whose "result" field
    holds the model's text; --max-turns 1 keeps it a single completion rather
    than an agent loop. Proven shape, lifted from tools/claude-bench.py.

    There is no response_format equivalent here, so `json_object` cannot be
    honoured -- callers depend on parse_json()'s fence-stripping tolerance
    instead, which is precisely why that function is written the way it is.
    """
    cmd = [CLAUDE_BIN, "-p", prompt,
           "--output-format", "json",
           "--max-turns", "1",
           "--model", active_model]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout)
    except subprocess.TimeoutExpired:
        raise TransientError(f"claude CLI timed out after {timeout}s")
    except OSError as e:
        # Binary missing or not executable: a config error, not a busy
        # endpoint. Permanent, so the caller stops rather than retrying 11k
        # times against a path that will never exist.
        raise RuntimeError(f"claude CLI not runnable ({CLAUDE_BIN}): {e}")

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "")[:300]
        if _CLAUDE_TRANSIENT.search(err):
            raise TransientError(f"claude CLI exit {proc.returncode}: {err}")
        raise RuntimeError(f"claude CLI exit {proc.returncode}: {err}")

    try:
        env = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"claude CLI envelope not JSON: {e}; "
                           f"stdout[:200]={proc.stdout[:200]}")

    if env.get("is_error"):
        detail = str(env.get("result", ""))[:300]
        if _CLAUDE_TRANSIENT.search(detail):
            raise TransientError(f"claude CLI error: {detail}")
        raise RuntimeError(f"claude CLI error: {detail}")

    content = (env.get("result") or "").strip()
    if not content:
        raise RuntimeError("claude CLI returned an empty result")
    return content


def _call_http(prompt, active_model, timeout, json_object):
    """The original OpenAI-compatible path: POST /chat/completions."""
    payload = {"model": active_model,
               "temperature": DEFAULT_TEMPERATURE,
               "messages": [{"role": "user", "content": prompt}]}
    if json_object:
        payload["response_format"] = {"type": "json_object"}

    req = urllib.request.Request(
        f"{base_url().rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {api_key()}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:300]
        if e.code in TRANSIENT_STATUSES:
            raise TransientError(f"LLM API HTTP {e.code}: {body}")
        raise RuntimeError(f"LLM API HTTP {e.code}: {body}")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        # No response at all -- a socket timeout or a refused/reset
        # connection. Never evidence about the prompt.
        raise TransientError(f"LLM API unreachable: {type(e).__name__}: {e}")

    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"LLM API returned no choices: {json.dumps(data)[:300]}")
    return choices[0]["message"]["content"].strip()


def parse_json(raw_text):
    """Tolerant JSON extraction, or None.

    Strips markdown fences and pulls out the outermost {...} rather than
    requiring the whole response to be valid JSON -- smaller and free models
    are chattier about wrapping output in explanation despite instructions
    not to.
    """
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_text.strip(),
                  flags=re.MULTILINE).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None


def has_fields(result, required_fields):
    return isinstance(result, dict) and all(k in result for k in required_fields)


def failed_label(model_label=None):
    """Tombstone value for a permanently failed attempt.

    Writing a terminal marker rather than leaving the row unscored is what
    stops a job that fails once from being retried on every future run
    forever -- the same lesson as hn-hiring.py's hn_seen_comments table.
    """
    return f"{FAILED_PREFIX}{model_label or model()}"
