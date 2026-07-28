"""Content-addressed store of raw model responses, so a run can be replayed.

WHAT REPLAY IS FOR
    Once a response has been paid for, the questions that remain are mostly
    not about the model at all:

      * Does the new score.normalize() coerce this output correctly? That is
        a question about OUR code, asked against real malformed answers.
      * Is fit_score agreement better measured at +/-5 or +/-10? A metric
        change, re-analysed over stored answers.
      * Did editing build_prompt() change the facts, or only the wording?
        Needs the old answers as a baseline.

    None of those should cost money or require a network, and all of them
    should give the same result twice.

WHAT IS STORED IS THE RAW TEXT, PRE-parse_json
    Storing the parsed dict would throw away exactly the cases worth keeping:
    fenced JSON, a model that prefixed "Sure!", a truncated object. Those are
    the inputs llm.parse_json() and normalize() have to survive, and they
    cannot be reconstructed from a successful parse.

WHAT IS NOT CACHED
    Nothing here decides that. The cache records `replayed` on every hit and
    report.py refuses to print cost or latency for a run containing one --
    the rule is enforced where the number would be printed, not by asking
    every caller to remember. tools/cost-test.py and the batch sweeps measure
    wall-clock and real token usage, so they pass use_cache=False and get a
    live call every time.

THE KEY
    sha256 over backend, model id, base URL, temperature, the json_object
    flag, and the full prompt. Temperature is in there because it is the one
    sampling knob llm.py exposes and a cache hit across two values would be
    silently wrong. The API key is NOT in there: rotating a credential must
    not throw away a corpus of answers, and a key must never reach disk.
"""

import dataclasses
import hashlib
import json
import os
import time

#: Default location. Outside the package directory would be tidier, but
#: keeping it here means one `rm -rf` clears it and no stray path needs
#: documenting. `.cache/` is not tracked -- see ensure_gitignored().
DEFAULT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")


def cache_dir():
    return os.environ.get("EVAL_CACHE_DIR") or DEFAULT_DIR


@dataclasses.dataclass(frozen=True)
class Entry:
    """One stored response. `replayed` is False on the call that created it."""

    text: str
    model: str
    usage: dict
    latency_s: float
    cost_usd: float = None
    created_at: str = None
    replayed: bool = False

    def as_replay(self):
        return dataclasses.replace(self, replayed=True)


def key_for(spec, prompt, *, json_object=True, temperature=None,
            repeat_index=0):
    """Stable digest for one (model, prompt) pair.

    `spec` is an evals.models.ModelSpec; only its cache_identity() is used,
    which excludes the API key.

    REPEAT INDEX, AND WHY OMITTING IT WOULD BE A SILENT FALSE PASS
        This store is content-addressed: same model, same prompt, same
        digest. A self-consistency measurement asks the same model the same
        prompt N times on purpose, so without disambiguation repeat 2 reads
        back repeat 1's stored answer and the run reports 100% agreement --
        on the exact quantity it was built to measure, with no error and
        nothing in the output to suggest anything went wrong. It is the most
        convincing possible wrong number.

        Index 0 adds nothing to the material, so an ordinary single run and
        the first pass of a repeat run share entries and no existing cache
        is invalidated. Every later pass gets its own key.

        Belt and braces: runner.run_repeated() also turns caching OFF by
        default when repeat > 1, because the measurement is about live
        variance. This keying is what makes --repeat with caching forced on
        (for testing the harness itself) mean something rather than lie.
    """
    if temperature is None:
        import llm
        temperature = llm.DEFAULT_TEMPERATURE
    material = {**spec.cache_identity(),
                "temperature": temperature,
                "json_object": bool(json_object),
                "prompt": prompt}
    if repeat_index:
        material["repeat_index"] = int(repeat_index)
    # sort_keys so a dict reordering never silently re-keys the whole cache.
    blob = json.dumps(material, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _path(digest):
    # One level of fan-out: a flat directory of tens of thousands of files is
    # slow to list and unpleasant to inspect by hand.
    return os.path.join(cache_dir(), digest[:2], f"{digest}.json")


def get(digest):
    """The stored Entry, marked replayed, or None."""
    path = _path(digest)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, json.JSONDecodeError):
        # A truncated file from an interrupted write reads as a miss. The
        # alternative -- raising -- would make one bad file poison a run.
        return None
    return Entry(text=raw.get("text", ""),
                 model=raw.get("model", ""),
                 usage=raw.get("usage") or {},
                 latency_s=raw.get("latency_s", 0.0),
                 cost_usd=raw.get("cost_usd"),
                 created_at=raw.get("created_at"),
                 replayed=True)


def put(digest, completion, *, meta=None):
    """Store one llm.Completion. Returns the Entry as written (replayed=False).

    Written to a temporary file and renamed, because a run interrupted
    mid-write would otherwise leave a half-written JSON file that every
    subsequent run reads as a miss and re-buys.
    """
    entry = Entry(text=completion.text,
                  model=completion.model,
                  usage=completion.usage,
                  latency_s=completion.latency_s,
                  cost_usd=completion.cost_usd,
                  created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                  replayed=False)
    path = _path(digest)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = dataclasses.asdict(entry)
    payload.pop("replayed")          # a property of the read, not of the row
    if meta:
        payload["meta"] = meta
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False)
    os.replace(tmp, path)
    return entry


def stats():
    """(entries, bytes) currently stored. For `evals cache stats`."""
    root = cache_dir()
    count = total = 0
    for dirpath, _, names in os.walk(root):
        for name in names:
            if name.endswith(".json"):
                count += 1
                try:
                    total += os.path.getsize(os.path.join(dirpath, name))
                except OSError:
                    pass
    return count, total


def ensure_gitignored():
    """Write .cache/.gitignore so stored responses can never be committed.

    They are large, they are worthless to anyone else, and a posting's full
    text sitting in git history is not something to do by accident.
    """
    root = cache_dir()
    os.makedirs(root, exist_ok=True)
    marker = os.path.join(root, ".gitignore")
    if not os.path.exists(marker):
        with open(marker, "w", encoding="utf-8") as fh:
            fh.write("*\n")
