"""One database connection per request, committed and closed."""

from contextlib import contextmanager

import psycopg

import config


@contextmanager
def db():
    """A connection that commits on success AND closes afterwards.

    Lifted from api/app.py, docstring included, because the subtlety here has
    already been paid for once:

    psycopg's own `with conn:` commits or rolls back but deliberately does NOT
    close -- it is designed for reusing a long-lived connection. This service
    opens one per request, so every request was leaking a socket until GC got
    round to it. Nesting `with conn:` inside a finally-close keeps psycopg's
    transaction semantics exactly (several callers rely on the implicit commit)
    and adds the close. contextlib.closing alone would NOT do: it closes
    without committing.
    """
    conn = psycopg.connect(config.database_url())
    conn.execute("SET search_path TO public")
    try:
        with conn:
            yield conn
    finally:
        conn.close()
