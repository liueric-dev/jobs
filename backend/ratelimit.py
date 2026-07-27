"""Client-side rate limiting for metered/free-tier LLM endpoints.

WHY THIS EXISTS
    Free tiers are enforced per *model*, not per project. The quota violation
    Google returns names it outright:

        quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier

    which means two limits matter and they fail differently:

      * RPM -- burst. Exceeding it 429s immediately and clears in ~60s.
        Purely a pacing problem; spacing calls out fixes it completely.
      * RPD -- a daily budget. Exceeding it 429s for the rest of the day.
        No amount of retrying helps, and a batch that blows through it wastes
        the budget on the first N jobs then fails the rest.

    Discovering RPD by hitting it is the expensive way to find out. This
    module makes the caller stop *before* the provider does.

WHY A TransientError WHEN THE DAILY CAP IS HIT
    Because the job was never evaluated. score.py defers TransientError --
    nothing is written and the row is retried on the next run -- while a
    permanent failure tombstones the job as FAILED and never revisits it.
    Recording "we ran out of budget" as a judgement about the posting would
    silently discard jobs nobody ever looked at. See llm.TransientError and
    llm.failed_label() for the two halves of that contract.

WHY THE DAILY COUNT IS PERSISTED
    RPD spans runs. An in-memory counter resets every time the process
    starts, so an hourly cron would get a fresh "budget" each hour and blow
    the real one by lunchtime. The count lives in a small JSON file keyed by
    model, alongside the date it belongs to.

    The reset boundary is configurable because providers disagree: Google's
    free tier rolls over at midnight Pacific, others use UTC. Default is UTC
    -- set LLM_QUOTA_TZ to match your provider if it differs. Getting this
    wrong is not dangerous, only wasteful: a boundary that lags the
    provider's leaves budget unspent, one that leads it gets you 429s the
    limiter thought it had room for.

CONFIGURATION
    LLM_MAX_RPM        requests per minute, 0/unset = unlimited
    LLM_MAX_RPD        requests per day, 0/unset = unlimited
    LLM_QUOTA_STATE    path to the counter file
    LLM_QUOTA_TZ       IANA zone for the daily reset (default UTC)

    Per-model overrides win over the bare name, so several models can share
    one process with different budgets:

        LLM_MAX_RPD__gemini_3_6_flash=20

    Non-alphanumerics in the model id become underscores, since env var names
    cannot contain '.' or '-'.
"""

import json
import os
import threading
import time
from datetime import datetime, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover -- stdlib since 3.9
    ZoneInfo = None

DEFAULT_STATE_PATH = os.path.expanduser("~/.cache/hermes/llm-quota.json")

#: Guards both the spacing clock and the on-disk counter. One process-wide
#: lock rather than one per model: the critical sections are microseconds of
#: bookkeeping, and a single lock keeps the file read-modify-write atomic
#: without a second layer of per-model locks to reason about.
_LOCK = threading.Lock()

#: model -> monotonic timestamp of the last call we let through.
_last_call = {}


class QuotaExhausted(RuntimeError):
    """The local daily budget for this model is spent.

    llm.call() translates this into a TransientError so callers defer rather
    than tombstone -- see the module docstring.
    """


def _env_key(name, model):
    """Per-model env override, e.g. LLM_MAX_RPD__gemini_3_6_flash."""
    slug = "".join(c if c.isalnum() else "_" for c in model)
    return f"{name}__{slug}"


def _limit(name, model, default=0):
    raw = os.environ.get(_env_key(name, model)) or os.environ.get(name) or ""
    try:
        return int(raw)
    except ValueError:
        return default


def _today():
    """The date string the daily counter is filed under."""
    tz_name = os.environ.get("LLM_QUOTA_TZ", "UTC")
    tz = timezone.utc
    if tz_name != "UTC" and ZoneInfo is not None:
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = timezone.utc  # unknown zone: UTC beats crashing the run
    return datetime.now(tz).strftime("%Y-%m-%d")


def _state_path():
    return os.environ.get("LLM_QUOTA_STATE", DEFAULT_STATE_PATH)


def _read_state():
    """{"date": "...", "counts": {model: n}} -- absent/corrupt reads as empty.

    A missing or unparseable file must not be fatal: the file is a budget
    optimisation, and refusing to run because it got truncated would turn a
    cosmetic problem into an outage. Worst case we under-count for one day.
    """
    try:
        with open(_state_path()) as f:
            state = json.load(f)
    except (OSError, ValueError):
        return {"date": _today(), "counts": {}}
    if state.get("date") != _today():
        return {"date": _today(), "counts": {}}   # new day, fresh budget
    state.setdefault("counts", {})
    return state


def _write_state(state):
    path = _state_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f"{path}.tmp{os.getpid()}"
        with open(tmp, "w") as f:
            json.dump(state, f)
        os.replace(tmp, path)   # atomic: a crash mid-write can't truncate it
    except OSError:
        pass    # see _read_state: budget tracking is best-effort, never fatal


def remaining_today(model):
    """Calls left under LLM_MAX_RPD, or None when uncapped."""
    cap = _limit("LLM_MAX_RPD", model)
    if cap <= 0:
        return None
    with _LOCK:
        return max(0, cap - _read_state()["counts"].get(model, 0))


def acquire(model):
    """Block until this model may be called again. Counts the call.

    Raises QuotaExhausted when the daily budget is spent -- that one is not
    waitable, so the caller has to stop rather than sleep.
    """
    rpm = _limit("LLM_MAX_RPM", model)
    rpd = _limit("LLM_MAX_RPD", model)
    if rpm <= 0 and rpd <= 0:
        return

    with _LOCK:
        if rpd > 0:
            state = _read_state()
            used = state["counts"].get(model, 0)
            if used >= rpd:
                raise QuotaExhausted(
                    f"local daily cap reached for {model}: {used}/{rpd} "
                    f"(LLM_MAX_RPD). Resets at midnight "
                    f"{os.environ.get('LLM_QUOTA_TZ', 'UTC')}.")
            state["counts"][model] = used + 1
            _write_state(state)

        wait = 0.0
        if rpm > 0:
            # Even spacing rather than a token bucket: a bucket lets N calls
            # fire at once and refill, which is exactly the burst that trips
            # a per-minute limit. Spacing them never does.
            interval = 60.0 / rpm
            last = _last_call.get(model)
            now = time.monotonic()
            if last is not None:
                wait = max(0.0, interval - (now - last))
            _last_call[model] = now + wait

    if wait > 0:
        # Slept outside the lock so concurrent workers for *other* models
        # aren't blocked behind this one's pacing.
        time.sleep(wait)
