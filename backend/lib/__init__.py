"""Mechanism layer for ingestion: fetch, retry, identity, state, and upsert.

Row schemas and source-specific parsing live outside this package. Stored ID
and content-hash behavior is pinned by tests/test_row_identity.py and must
not change as a side effect of cleanup.
"""

__all__ = [
    "dbconn",
    "envfile",
    "http",
    "ids",
    "state",
    "text",
    "timeparse",
    "upsert",
]
