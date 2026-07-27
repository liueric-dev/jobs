"""Run one task over one corpus with one model, and record what happened.

CACHE POLICY IS SET HERE, ENFORCED IN report.py
    A run carries `use_cache`. Every Result records whether it came from the
    cache, and report.py refuses to print cost or latency for a run that
    contains a replayed result. Putting the decision in one place and the
    enforcement at the point of printing means no caller has to remember the
    rule, and a cached latency can never be reported as measured.

TRANSIENT FAILURES ARE NOT CACHED AND NOT COUNTED
    llm.TransientError means the prompt was never evaluated -- a 429, a
    socket timeout. Storing that as a response would poison the cache with a
    non-answer, and counting it against the model would blame it for the
    endpoint being busy. It is recorded as `deferred`, which is exactly what
    extract.py does with the same signal (extract.py:365).

CONCURRENCY MATCHES THE PIPELINE
    Same ThreadPoolExecutor shape and the same default worker count as
    extract.py, because latency measured at a concurrency the pipeline never
    uses is not the pipeline's latency.
"""

import concurrent.futures
import dataclasses

import llm

from . import cache as cache_mod

#: Mirrors EXTRACT_MAX_WORKERS (extract.py:67). Not imported from it: the
#: sweep tools legitimately want to vary this, and coupling them would make
#: a sweep silently change the pipeline's default too.
DEFAULT_WORKERS = 3

OK, TOMBSTONE, DEFERRED, SKIPPED = "ok", "tombstone", "deferred", "skipped"


@dataclasses.dataclass
class Result:
    job_id: str
    status: str
    normalized: dict = None
    raw_text: str = None
    reason: str = None
    replayed: bool = False
    usage: dict = dataclasses.field(default_factory=dict)
    latency_s: float = 0.0
    cost_usd: float = None
    prompt_sha: str = None


@dataclasses.dataclass
class Run:
    """One task x model x corpus. `replayed_any` gates cost/latency reporting."""

    task: str
    model_label: str
    model_identity: dict
    results: list
    use_cache: bool

    @property
    def replayed_any(self):
        return any(r.replayed for r in self.results)

    @property
    def ok(self):
        return [r for r in self.results if r.status == OK]

    def counts(self):
        out = {}
        for r in self.results:
            out[r.status] = out.get(r.status, 0) + 1
        return out


def _one(task, spec, record, *, use_cache, refresh, json_object, call_kwargs):
    """Execute a single record. Never raises for a per-record failure."""
    job_id = record.get("id")
    if not task.eligible(record):
        return Result(job_id=job_id, status=SKIPPED, reason="ineligible")

    prompt = task.build_prompt(record)
    digest = cache_mod.key_for(spec, prompt, json_object=json_object)

    entry = None
    if use_cache and not refresh:
        entry = cache_mod.get(digest)

    if entry is None:
        try:
            completion = llm.call_detailed(prompt, json_object=json_object,
                                           **call_kwargs)
        except llm.TransientError as e:
            # Never cached: the prompt was not evaluated, so there is no
            # answer to store and nothing to hold against the model.
            return Result(job_id=job_id, status=DEFERRED,
                          reason=f"transient: {str(e)[:160]}",
                          prompt_sha=digest)
        except RuntimeError as e:
            return Result(job_id=job_id, status=TOMBSTONE,
                          reason=f"call_failed: {str(e)[:160]}",
                          prompt_sha=digest)
        entry = (cache_mod.put(digest, completion) if use_cache
                 else cache_mod.Entry(text=completion.text,
                                      model=completion.model,
                                      usage=completion.usage,
                                      latency_s=completion.latency_s,
                                      cost_usd=completion.cost_usd))

    normalized, reason = task.parse(entry.text)
    return Result(job_id=job_id,
                  status=OK if normalized is not None else TOMBSTONE,
                  normalized=normalized,
                  raw_text=entry.text,
                  reason=reason,
                  replayed=entry.replayed,
                  usage=entry.usage,
                  latency_s=entry.latency_s,
                  cost_usd=entry.cost_usd,
                  prompt_sha=digest)


def run(task, spec, records, *, use_cache=True, refresh=False,
        workers=DEFAULT_WORKERS, json_object=True, progress=None):
    """Execute `task` over `records` with `spec`. Returns a Run.

    Results come back in corpus order regardless of completion order, so two
    runs over the same fixture produce byte-identical reports.
    """
    if use_cache:
        cache_mod.ensure_gitignored()

    # Resolve credentials ONCE, here, before any work starts. Two reasons:
    # an `env:VARNAME` that is unset is a configuration error, and it should
    # surface as one actionable line before the first call rather than as a
    # traceback out of a worker thread after some records have already been
    # billed; and this is otherwise an environment lookup per record.
    call_kwargs = spec.call_kwargs()

    results = [None] * len(records)
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_one, task, spec, rec, use_cache=use_cache,
                        refresh=refresh, json_object=json_object,
                        call_kwargs=call_kwargs): i
            for i, rec in enumerate(records)
        }
        done = 0
        for fut in concurrent.futures.as_completed(futures):
            i = futures[fut]
            results[i] = fut.result()
            done += 1
            if progress:
                progress(done, len(records), results[i])

    return Run(task=task.name, model_label=spec.label,
               model_identity=spec.cache_identity(), results=results,
               use_cache=use_cache)
