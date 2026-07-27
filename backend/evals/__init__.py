"""Evaluation harness for the pipeline's LLM stages.

WHY THIS EXISTS
    Nine scripts under tools/ each answer one question about a model, and
    each rebuilds the same plumbing to do it: three parse MODEL@URL@KEY
    differently, four import llm and then reimplement the HTTP call anyway,
    and every one selects its corpus with `ORDER BY first_seen DESC LIMIT n`
    against the PRODUCTION database. That last one is the expensive part --
    the corpus changes every night, so no two runs are comparable and a
    model regression is indistinguishable from a corpus shift.

    This package is the shared substrate those scripts should have had:
    frozen fixtures, one model handle, a replay cache, and per-field
    comparison rules.

NAMED `evals`, NOT `eval`
    `eval` is a builtin. A package by that name means any module doing
    `import eval` silently loses the builtin, which is the kind of breakage
    that surfaces a long way from its cause.

WHAT IT DOES NOT DO
    It never writes to the jobs corpus. `corpus snapshot` reads production
    and writes a fixture file; everything downstream reads the fixture. The
    ingest scripts under ingest/ and scripts/ are the only things that write,
    and nothing here invokes them.
"""
