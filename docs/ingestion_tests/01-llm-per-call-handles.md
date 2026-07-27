# 01 — Per-call model handles in `llm.py`

**Status:** done, 2026-07-27, `fb733df`.
**Depends on:** nothing. **Blocks:** 02.

Let a caller point one call at one model without mutating `os.environ`.

## The problem

`llm.model()`, `base_url()` and `api_key()` read process-global environment.
There was no way to say "this call goes to DeepSeek" in a process already
configured for GLM. So four tools under `tools/` rebuilt the HTTP request by
hand: `compare-models.py`, `compare-extract.py`, `cost-test.py` and
`verify-date-filter.py` each `import llm` for the prompt and then call
`urllib.request.urlopen` themselves.

That is not merely duplication. The hand-built path skips
`ratelimit.acquire()` (`llm.py:127`), which is the client-side enforcement of
`LLM_MAX_RPM` / `LLM_MAX_RPD` **per model**. An exploratory sweep on the free
GLM tier could therefore spend the quota `score.py` needs at 03:00, and
nothing would report it.

## What landed

```python
def call(prompt, **kwargs):                    # unchanged return: a string
    return call_detailed(prompt, **kwargs).text

def call_detailed(prompt, *, model=None, base_url=None, api_key=None,
                  backend=None, timeout=DEFAULT_TIMEOUT_SECS,
                  json_object=True) -> Completion
```

`Completion` is a frozen dataclass: `text`, `model`, `usage`, `latency_s`,
`cost_usd`.

Every override defaults to `None` and falls back to the existing environment
lookup, so no pipeline caller changes behaviour. `extract.py:374` and
`score.py:423` both call `llm.call(prompt)` with the prompt positional and
nothing else; that still works and still returns a bare string.

### Two decisions worth not undoing

**A separate function, not a `return_usage=` flag.** A flag that changes the
return type makes `content = llm.call(...)` something you have to read the
arguments to understand. The plan originally specified the flag; the split is
better and costs nothing.

**`usage` is passed through unchanged.** The OpenAI wire format reports
`prompt_tokens`/`completion_tokens`; the Claude CLI envelope reports
`input_tokens` plus separate `cache_read_input_tokens` and
`cache_creation_input_tokens`. Normalising them is a reporting concern —
`llm.py` deliberately knows nothing jobs-specific and nothing about prices.
`cost_usd` is non-`None` only on the `claude` backend, which is the only one
that tells us.

**Private aliases for the shadowed lookups.** The keyword arguments share
names with the module functions (`model=` reads better than `model_id=` at
every call site), so `call_detailed` reaches them through `_env_model`,
`_env_base_url`, `_env_api_key`, `_env_backend`. Those are bound to the
functions, not their results, so a test that patches `os.environ` between
calls still works.

## Verification

`tests/test_llm.py` gained `TestPerCallOverrides` — 5 tests pinning that
defaults read the environment, that overrides reach the wire *without*
mutating it, that a trailing slash on `base_url` does not double up, that
`Completion` carries usage, and that temperature stays at
`DEFAULT_TEMPERATURE`.

The existing `TestTransientClassification` cases still pass unchanged, which
is the thing that mattered most: a 429 must stay a `TransientError` through
the new path, or a job that was never evaluated gets tombstoned.
