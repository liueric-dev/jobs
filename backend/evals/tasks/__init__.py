"""Adapters onto the pipeline's real LLM stages.

Each task is a thin object exposing build_prompt(), parse(), and the field
vocabulary. The prompt text and the coercion rules stay in extract.py and
score.py -- a copy here would drift, and an eval that measures a copy of the
prompt measures nothing.
"""

from . import extract as extract_task
from . import score as score_task


def get(name):
    tasks = {"extract": extract_task.TASK, "score": score_task.TASK}
    try:
        return tasks[name]
    except KeyError:
        raise ValueError(
            f"unknown task {name!r}; available: {', '.join(sorted(tasks))}")
