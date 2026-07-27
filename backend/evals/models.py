"""One way to name a model, for every tool that needs to reach one.

THE SPEC FORMAT
    MODEL@BASE_URL@API_KEY      an OpenAI-compatible endpoint
    MODEL                       ditto, but base URL and key come from the
                                environment exactly as the pipeline reads them
    claude:MODEL                the `claude -p` CLI, billed against a Pro/Max
                                subscription -- no URL, no key

    The key may be written `env:VARNAME` to have it read from the environment
    at use time. That is not cosmetic: a spec string ends up in run metadata
    and in error messages, and a literal key would be written to a results
    file on disk.

SPLIT ON THE FIRST TWO '@', NOT ON ALL OF THEM
    The three existing parsers disagreed, and two of them are wrong.
    tools/compare-models.py:213 splits on every '@' and rejoins the middle,
    treating the LAST field as the key; tools/cost-test.py:156 and
    tools/compare-extract.py:124 use split('@', 2), treating the REST as the
    key. They return different things for the same input:

        m@https://x/v1@sk-a@b
            rejoin-the-middle -> base_url='https://x/v1@sk-a', key='b'
            split('@', 2)     -> base_url='https://x/v1',      key='sk-a@b'

    Keys containing '@' are ordinary. Base URLs containing a bare '@' are
    not -- that position is URL userinfo, which nothing here uses. So
    split('@', 2) is correct and the rejoin is a latent truncation bug.

THE KEY IS NEVER PART OF A CACHE KEY OR A REPORT
    cache_identity() exists so the replay cache and the results file can
    describe a model without ever containing its credential. Rotating a key
    must not invalidate a cache; leaking one through a committed fixture is
    worse.
"""

import dataclasses
import os

_CLAUDE_PREFIX = "claude:"


class SpecError(ValueError):
    """A --model argument that cannot be parsed. Always a user-facing message."""


@dataclasses.dataclass(frozen=True)
class ModelSpec:
    """Everything needed to place one call, and nothing about how to score it."""

    model: str
    base_url: str = None
    api_key: str = None
    backend: str = "http"

    @property
    def label(self):
        """Short display name. Distinguishes providers serving the same id.

        `deepseek-v4-flash` at two different hosts is two different things to
        compare, so the host has to survive into the report or the table has
        two identical rows.
        """
        if self.backend == "claude":
            return f"claude:{self.model}"
        if not self.base_url:
            return self.model
        return f"{self.model} ({_host(self.base_url)})"

    def cache_identity(self):
        """The parts of this spec that change what the model returns.

        Deliberately excludes api_key -- see the module docstring. Includes
        backend because llm.py reaches the same model label through both
        _call_http and _call_claude, and those do not return the same thing.
        """
        return {"backend": self.backend,
                "model": self.model,
                "base_url": self.base_url or ""}

    def call_kwargs(self):
        """Keyword arguments for llm.call_detailed().

        Resolves `env:VARNAME` here rather than at parse time so a spec can be
        built, logged, and passed around without ever holding the credential.
        """
        if self.backend == "claude":
            return {"model": self.model, "backend": "claude"}
        return {"model": self.model,
                "base_url": self.base_url,
                "api_key": _resolve_key(self.api_key),
                "backend": "http"}


def _host(url):
    """Host portion of a URL, for display. Tolerates a malformed URL."""
    rest = url.split("://", 1)[-1]
    return rest.split("/", 1)[0] or url


def _resolve_key(key):
    """`env:NAME` -> the environment's value. Anything else passes through."""
    if key and key.startswith("env:"):
        name = key[4:]
        value = os.environ.get(name)
        if not value:
            raise SpecError(f"--model names env:{name}, which is unset")
        return value
    return key


def parse(spec):
    """Parse one --model argument. Raises SpecError with a usable message."""
    if not spec or not spec.strip():
        raise SpecError("--model must not be empty")
    spec = spec.strip()

    if spec.startswith(_CLAUDE_PREFIX):
        model = spec[len(_CLAUDE_PREFIX):].strip()
        if not model:
            raise SpecError("claude: needs a model, e.g. claude:haiku")
        return ModelSpec(model=model, backend="claude")

    parts = spec.split("@", 2)
    if len(parts) == 1:
        # Bare model id: the pipeline's own environment supplies the rest.
        # llm.call_detailed() treats None as "read the environment", so this
        # stays a single code path rather than a special case.
        return ModelSpec(model=parts[0])
    if len(parts) != 3:
        raise SpecError(
            f"bad --model {spec!r}: want MODEL@BASE_URL@API_KEY, "
            f"MODEL, or claude:MODEL")

    model, base_url, api_key = (p.strip() for p in parts)
    if not model:
        raise SpecError(f"bad --model {spec!r}: empty model id")
    if not base_url:
        raise SpecError(f"bad --model {spec!r}: empty base URL")
    if not api_key:
        raise SpecError(f"bad --model {spec!r}: empty API key")
    return ModelSpec(model=model, base_url=base_url, api_key=api_key)
