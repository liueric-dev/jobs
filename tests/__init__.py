"""Unit tests for the jobs pipeline. Run with:

    cd ~/apps/jobs && python3 -m unittest discover -s tests -t .

`-t .` sets the top-level directory to the repo root, which is what puts the
pipeline modules (schema, llm, relevance, ...) on sys.path for discovery.
pipelib needs nothing -- it is an installed package.
"""
