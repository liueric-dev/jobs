"""Stable row identity and change detection.

Both pipelines derive a primary key by hashing a few identifying fields, and
detect "did this row actually change" by hashing the content fields. The
implementations were byte-identical across all nine scripts apart from which
fields went in, so both are parameterised here.

COMPATIBILITY REQUIREMENT -- these MUST produce byte-identical output to the
copies they replace. Both functions feed values that are already stored in
the database: `id` is the primary key of every existing row, and
`content_hash` decides whether a row counts as changed. If either digest
shifts, the first run after the migration re-keys or re-writes every row in
the table -- 40k spurious "new"/"updated" rows and a destroyed audit trail.

The compatibility hinge is str() semantics. The originals interpolated with
f-strings, so a None became the literal "None" and never an empty string:

    events:  f"{source}:{source_id or title}:{start or ''}"
    jobs:    f"{platform}:{token}:{source_id}"

`make_id` therefore does a plain str() on every part rather than normalising
None away. The `or title` / `or ''` fallbacks are caller-side and stay at
the call site, so events calls make_id(source, source_id or title, start or "").
tests/test_ids.py pins this against the original expressions.
"""

import hashlib

ID_LENGTH = 24


def make_id(*parts, length=ID_LENGTH):
    """Stable primary key: sha256 of ":"-joined parts, truncated.

    Equivalent to the f-string interpolation the callers used before -- a
    None part becomes "None", not "". See the module docstring.
    """
    key = ":".join(str(p) for p in parts)
    return hashlib.sha256(key.encode()).hexdigest()[:length]


def content_hash(rec, fields, blank_if_falsy=()):
    """Hash only the fields that represent real content.

    Deliberately excludes bookkeeping (raw_json, first_seen/last_seen,
    status) so unrelated metadata churn upstream doesn't register as a
    change -- a row whose hash is unchanged only gets its last_seen bumped.

    `fields` is an ordered tuple of keys into `rec`. Order and membership
    are part of the digest, so changing either is a breaking change to every
    stored hash. Each pipeline -- and in the jobs pipeline, each *source* --
    keeps its own tuple for exactly that reason; they are not interchangeable
    and were never meant to be unified.

    `blank_if_falsy` names keys that render as "" rather than "None" when
    absent. This is not a stylistic choice: the jobs scripts hashed
    `rec.get("description_text") or ""` while hashing every other field
    bare, so a row with no description hashed a "" there. Without this
    parameter every such row would re-hash and be rewritten on the first run
    after the migration.
    """
    parts = []
    for f in fields:
        if f in blank_if_falsy:
            parts.append(str(rec.get(f) or ""))
        else:
            parts.append(str(rec[f]))
    return hashlib.sha256("|".join(parts).encode()).hexdigest()
