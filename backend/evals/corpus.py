"""Frozen fixtures: the same postings, every run, forever.

WHY FREEZE
    Every tool under tools/ selects its corpus with

        ORDER BY j.first_seen DESC LIMIT n

    against production. That means the corpus is different every night, so
    two runs a week apart cannot be compared: a drop in agreement is equally
    well explained by a worse model or by a batch of scrappier postings
    arriving. Freezing the corpus is what turns "the numbers moved" into
    evidence about the thing that changed.

    It also removes the database from the inner loop entirely. After one
    snapshot, the harness runs with no DATABASE_URL and no network.

ONE RECORD CARRIES BOTH STAGES' INPUTS
    extract.build_prompt() wants the posting; score.build_prompt() wants the
    posting AND its job_facts row, because the prompt embeds a facts block
    (score.py:249 _facts_block). Capturing facts alongside the posting means
    the score task can run against a fixture without first running extract --
    the two stages stay independently testable, which is the whole point.

WHAT GETS SAMPLED
    Stratified by platform, because the sources do not look alike: an ATS
    posting is clean HTML with a real title, an HN comment is free text whose
    "title" the parser guesses at. A corpus that is 80% ATS measures ATS.

    And deliberately seeded with the awkward rows -- see PATHOLOGY. A corpus
    of well-formed postings tests the easy path and reports it as the score.

READ-ONLY
    snapshot() is the only thing here that opens a database connection, and
    it only ever SELECTs.
"""

import json
import os
import random

#: The awkward shapes worth guaranteeing in every corpus, with the quota each
#: gets. These are not hypotheticals: they come out of the ingestion audit in
#: docs/ingest/, and each one has broken something.
#:
#:   long_title   HN rows holding a comment body where a title belongs -- the
#:                longest is 415 characters (audit item 15).
#:   no_description  extract.py's own selector excludes these, so nothing has
#:                ever run a prompt against one. Worth knowing what happens.
#:   tombstoned   rows whose extraction_model is 'FAILED:%'. A model that
#:                failed on these once is the sharpest available test of a
#:                candidate replacement.
PATHOLOGY = {"long_title": 6, "no_description": 3, "tombstoned": 6}

#: Columns lifted verbatim from job_facts. Kept as an explicit tuple rather
#: than SELECT * so a schema addition cannot silently change a fixture's shape
#: and re-key every cached response through a changed prompt.
FACT_COLUMNS = ("facts_version", "seniority_level", "years_experience_min",
                "years_experience_max", "role_archetype", "tech_stack",
                "ai_involvement", "ml_research_required",
                "advanced_degree_required", "customer_facing",
                "remote_policy", "employment_type", "comp_min", "comp_max",
                "comp_currency", "gap_friendly_language", "visa_sponsorship",
                "summary", "extraction_model")

JOB_COLUMNS = ("id", "title", "company_name", "location_raw", "platform",
               "description_text", "status", "first_seen")


def load(path):
    """Read a JSONL fixture. Blank lines tolerated, comments are not."""
    records = []
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}:{lineno}: {e}") from e
    return records


def save(path, records):
    """Write a JSONL fixture, one record per line, keys sorted.

    Sorted keys and one-record-per-line so that a re-snapshot produces a
    reviewable diff rather than a reformatted blob.
    """
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, sort_keys=True, ensure_ascii=False) + "\n")
    os.replace(tmp, path)
    return len(records)


def job_fields(record):
    """The subset extract.build_prompt() reads."""
    return {k: record.get(k) for k in
            ("id", "title", "company_name", "location_raw", "platform",
             "description_text")}


def facts_fields(record):
    """The job_facts subset score.build_prompt() reads, or None if unextracted."""
    facts = record.get("facts")
    return facts if facts else None


def _pool_query(profile):
    """The one SELECT. LEFT JOINs so unextracted rows stay eligible.

    THE POOL IS PER-PLATFORM, NOT GLOBALLY RECENT
        A plain `ORDER BY first_seen DESC LIMIT n` -- what every tool under
        tools/ does -- silently excludes whole sources. Measured against
        production: greenhouse and ashby account for ~9,800 of 11,517 rows and
        are ingested continuously, while weworkremotely, hn_whoishiring and
        lever last wrote on 2026-07-24. A recency-ordered pool of 720 rows
        contained none of the latter three.

        That is not a small sampling wrinkle. The HN parser is the one whose
        "titles" are guessed out of free text, and the audit's item 15 is
        specifically about HN rows holding a comment body where a title
        belongs. A corpus that cannot contain them cannot test them.

        ROW_NUMBER() per platform takes the most recent `per_platform` from
        EACH source, so every source reaches stratify() and the deliberate
        over-sampling of small sources is a choice rather than an accident.
    """
    from schema import TABLE, FACTS_TABLE, MATCHES_TABLE
    fact_cols = ", ".join(f"f.{c}" for c in FACT_COLUMNS)
    job_cols = ", ".join(f"j.{c}" for c in JOB_COLUMNS)
    return f"""
        WITH ranked AS (
            SELECT {job_cols}, {fact_cols}, m.match_score, m.match_reasons,
                   ROW_NUMBER() OVER (PARTITION BY j.platform
                                      ORDER BY j.first_seen DESC) AS rn
            FROM {TABLE} j
            LEFT JOIN {FACTS_TABLE} f ON f.job_id = j.id
            LEFT JOIN {MATCHES_TABLE} m
                   ON m.job_id = j.id AND m.profile = %(profile)s
        )
        SELECT {", ".join(JOB_COLUMNS)}, {", ".join(FACT_COLUMNS)},
               match_score, match_reasons
        FROM ranked
        WHERE rn <= %(per_platform)s
    """


def _row_to_record(row, cols):
    raw = dict(zip(cols, row))
    facts = {c: raw.pop(c) for c in FACT_COLUMNS}
    record = raw
    # facts_version is NULL for a row job_facts has never seen. Storing an
    # empty facts block rather than a dict of Nones keeps "never extracted"
    # distinguishable from "extracted, and every field came back empty" --
    # which is a real outcome extract.normalize() can produce.
    record["facts"] = facts if facts.get("facts_version") is not None else None
    return record


def classify(record):
    """Which pathology buckets a record belongs to. May be several, or none."""
    tags = []
    if len(record.get("title") or "") > 100:
        tags.append("long_title")
    if not (record.get("description_text") or "").strip():
        tags.append("no_description")
    model = ((record.get("facts") or {}).get("extraction_model")) or ""
    if model.startswith("FAILED:"):
        tags.append("tombstoned")
    return tags


def stratify(records, n, *, seed=0, pathology=None):
    """Pick `n` records: pathology quotas first, then even across platforms.

    Deterministic given a seed, so a fixture can be regenerated and reviewed
    as a diff instead of an unexplained new set.
    """
    pathology = PATHOLOGY if pathology is None else pathology
    rng = random.Random(seed)
    remaining = list(records)
    rng.shuffle(remaining)

    picked, taken = [], set()

    # Pathology first: these are rare, so filling them after the even split
    # would usually find nothing left to take.
    for bucket, quota in pathology.items():
        for rec in remaining:
            if len(picked) >= n:
                break
            if rec["id"] in taken or bucket not in classify(rec):
                continue
            picked.append(rec)
            taken.add(rec["id"])
            quota -= 1
            if quota <= 0:
                break

    by_platform = {}
    for rec in remaining:
        if rec["id"] not in taken:
            by_platform.setdefault(rec.get("platform") or "unknown", []).append(rec)

    # Round-robin rather than an equal quota per platform: the sources are not
    # equally represented, and a fixed quota would silently under-fill from a
    # small source and waste the slots.
    while len(picked) < n and any(by_platform.values()):
        for platform in sorted(by_platform):
            if len(picked) >= n:
                break
            if by_platform[platform]:
                rec = by_platform[platform].pop()
                picked.append(rec)
                taken.add(rec["id"])
    return picked


def snapshot(conn, n, *, profile, seed=0, per_platform=None):
    """Read production and return `n` stratified records. Never writes.

    `per_platform` caps how many of each source's most recent rows enter the
    pool. Generous by default: the pathology buckets are a small fraction of
    any slice, and a pool too thin to contain them produces a corpus that
    quietly tests only the easy path.
    """
    per_platform = per_platform or max(n * 2, 250)
    cols = list(JOB_COLUMNS) + list(FACT_COLUMNS) + ["match_score",
                                                     "match_reasons"]
    rows = conn.execute(_pool_query(profile),
                        {"profile": profile,
                         "per_platform": per_platform}).fetchall()
    records = [_row_to_record(r, cols) for r in rows]
    return stratify(records, n, seed=seed)


def summarize(records):
    """Counts by platform and pathology, for the snapshot's stdout line."""
    platforms, tags = {}, {}
    extracted = 0
    for rec in records:
        platforms[rec.get("platform") or "unknown"] = platforms.get(
            rec.get("platform") or "unknown", 0) + 1
        if rec.get("facts"):
            extracted += 1
        for tag in classify(rec):
            tags[tag] = tags.get(tag, 0) + 1
    return {"total": len(records), "platforms": platforms,
            "pathology": tags, "with_facts": extracted}
