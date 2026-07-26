"""The `jobs.jobs` table -- DDL, column specs, and lifecycle helpers.

Owned by the jobs pipeline, deliberately not by pipelib: pipelib provides
mechanism (upsert, retry, hashing, checkpoints, claims) and knows nothing
about what a job listing is. This module is the single definition the six
ingest scripts and score.py share, replacing six separately-drifting copies
of ensure_schema() -- one of which (ingest/google-serpapi.py) described
itself in a comment as a "Defensive duplicate of ingest/ats.py's".

SCHEMA, NOT DATABASE
    These tables live in a Postgres schema called `jobs`, inside the same
    database as `public.events`. search_path is per-connection, so every
    connection must set it -- pipelib.dbconn.connect(schema="jobs") does,
    including the per-thread connections score.py opens. Getting this wrong
    does not error; it silently reads and writes `public`.

HASH FIELDS ARE PER SOURCE, DELIBERATELY
    The six scripts did NOT hash the same fields, and that is correct rather
    than drift: ats and weworkremotely include `department`; builtin-nyc
    includes `seniority_guess` and `salary_text` but no description; the
    Google and HN sources hash a shorter set. Each tuple below is the one
    its source has always used. These are stored digests -- unifying them
    would mark every row in the table as changed on the next run.

    `blank_if_falsy` preserves the other half of that compatibility: the
    originals hashed `rec.get("description_text") or ""` while hashing every
    other field bare, so a missing description contributed "" and not the
    string "None". Verified against 3,000 live rows.

    Note `salary_text` is a record-only field. It feeds builtin-nyc's hash
    but is not a column on the table, which is why it appears in
    HASH_FIELDS_BUILTIN and not in COLUMNS.

SCORES ARE PER PROFILE, NOT PER JOB
    fit_score, primary_track, gap_bridging_angle and the rest used to be
    columns on `jobs`. They are not properties of a job -- they are one
    persona's opinion of it, and `jobs` is shared. One column per job means
    a second persona overwrites the first, and re-scoring after editing
    config/persona.json destroys the answers the old persona gave.

    `job_scores` is keyed (job_id, profile) instead, so profiles coexist and
    a persona revision is a new profile rather than a destructive UPDATE.
    "Is this job scored?" becomes "scored FOR THIS PROFILE", which is the
    question select_unscored_jobs actually needs to ask.

    Done at 44 scored rows, deliberately: the same change after a few
    thousand is a real migration rather than an afternoon.

SCORING IS TWO TIERS, AND ONLY ONE OF THEM COSTS PER USER
    job_scores solved "one persona overwrites another". It did not solve
    "every persona pays for every job": one LLM call per (job, profile) means
    cost, latency and rate-limit consumption all scale as jobs x profiles. At
    one profile that is invisible. At a hundred it is 11,500 calls a day, and
    a new profile cannot see anything until its whole eligible corpus has been
    scored -- measured at ~4 hours.

    So the single call is split by what the answer actually depends on:

      job_facts    properties of the POSTING -- seniority, years required,
                   archetype, stack, remote policy, comp. True regardless of
                   who is looking, so extracted once, by one LLM call, and
                   shared by every profile that will ever exist. Flat in the
                   number of users.

      job_matches  properties of the PAIRING -- computed by arithmetic over
                   job_facts and the profile's criteria_json. No LLM, no
                   network, no marginal cost. This is what ranks, and it is
                   why a brand-new profile gets a full ranked list in seconds
                   instead of four hours.

      job_scores   the narrative -- gap_bridging_angle, risk_factors, the
                   things that genuinely require a model to have read both the
                   posting and the persona. Bounded by what a user is actually
                   shown, not by corpus size.

    The ordering rule that keeps this honest: job_matches.match_score ranks,
    job_scores.fit_score only annotates. Sorting by fit_score would put an
    LLM call back on the critical path for every job a user might see, which
    is exactly the property being removed.

TIMESTAMPS STAY TEXT HERE
    Unlike events, this pipeline keeps bookkeeping timestamps as TEXT in
    'YYYY-MM-DDTHH:MM:SS' form. String comparison is load-bearing --
    `WHERE last_seen < %s`, `watermark > cutoff` -- and "" is the "never
    run" sentinel that must sort before every real timestamp. Converting
    these to timestamptz would silently break the self-healing gap logic in
    google-serpapi's choose_date_chip(). pipelib.timeparse.utc_now_str()
    produces exactly this format and is the only thing that should.
"""

import os

from pipelib import dbconn, ids, state
from pipelib.upsert import TableSpec

SCHEMA = "jobs"
TABLE = "jobs"
WATERMARK_TABLE = "job_ingest_state"

STATUS_OPEN = "open"
STATUS_CLOSED = "closed"

#: Columns written from a normalized record.
COLUMNS = (
    "platform", "company_token", "company_name", "source_id",
    "title", "location_raw", "department", "job_url", "posted_at",
    "seniority_guess", "location_is_nyc", "location_is_remote",
    "company_is_nyc_hq", "company_is_ai_focused",
    "description_text", "raw_json",
)

#: Per-source hash field tuples. FROZEN -- see the module docstring.
HASH_FIELDS_ATS = ("title", "location_raw", "department", "job_url",
                   "posted_at", "description_text")
HASH_FIELDS_WWR = HASH_FIELDS_ATS
HASH_FIELDS_SHORT = ("title", "location_raw", "job_url", "posted_at",
                     "description_text")
HASH_FIELDS_BUILTIN = ("title", "location_raw", "job_url", "posted_at",
                       "seniority_guess", "salary_text")

SCORES_TABLE = "job_scores"
FACTS_TABLE = "job_facts"
MATCHES_TABLE = "job_matches"
PROFILES_TABLE = "profiles"
EVENTS_TABLE = "job_events"

#: Bump to invalidate every extracted row. job_facts.facts_version records
#: which generation of the extraction schema produced a row, so "which rows
#: predate the new field" is a query rather than a guess, and a re-extraction
#: can be a resumable backlog burn-down instead of a TRUNCATE.
FACTS_VERSION = 1

#: match_score below this is not written to job_matches at all. Most jobs are
#: irrelevant to most profiles, and at N profiles the full cross product is
#: N x 11k rows of mostly noise. Storing only what could plausibly be shown
#: keeps the table ~8% of that. Lowering it costs storage, not correctness --
#: match.py recomputes from job_facts, which is never discarded.
MATCH_FLOOR = int(os.environ.get("JOBS_MATCH_FLOOR", "40"))

#: Default profile name when nothing says otherwise. A "profile" is one
#: persona's answer to "is this job a good fit" -- see the SCORES ARE PER
#: PROFILE note in the module docstring.
DEFAULT_PROFILE = "default"

#: The eight legacy per-job scoring columns. Superseded by job_scores and
#: removed by migrate_scores.py; kept here only so that script knows what to
#: read and drop. Nothing creates them any more.
LEGACY_SCORING_COLUMNS = (
    "fit_score", "primary_track", "gap_friendly_signal", "key_technologies",
    "gap_bridging_angle", "risk_factors", "scored_at", "scoring_model",
)


def resolve_profile(persona=None):
    """Which profile's scores we are reading or writing.

    JOBS_PROFILE wins so a one-off run can score against an alternate persona
    without editing config; otherwise the persona file names itself. Both are
    optional -- an unlabelled persona is DEFAULT_PROFILE, which is what every
    existing deployment was implicitly using when scores lived on `jobs`.
    """
    return (os.environ.get("JOBS_PROFILE")
            or (persona or {}).get("profile")
            or DEFAULT_PROFILE)


def spec(hash_fields, blank_if_falsy=("description_text",)):
    """A TableSpec for one source's hash field set.

    `computed` reopens a listing that reappears upstream: status back to
    'open' and closed_at cleared, on INSERT and UPDATE alike. Paired with
    revive_column, a row previously marked closed counts as an update rather
    than as unchanged, so a reappearance is never silently ignored.
    """
    return TableSpec(
        table=TABLE,
        columns=COLUMNS,
        hash_fields=hash_fields,
        blank_if_falsy=blank_if_falsy,
        computed={"status": f"'{STATUS_OPEN}'", "closed_at": "NULL"},
        revive_column="status",
        revive_value=STATUS_OPEN,
    )


def make_job_id(rec):
    """Primary key: sha256("platform:token:source_id")[:24].

    Identical to the expression all six scripts used, so existing keys are
    preserved -- verified against 3,000 live rows. Deduplicates within a
    source only: the same posting arriving via both Greenhouse and Google
    Jobs is two rows, which ingest/builtin-nyc.py already acknowledged.
    Cross-source dedup is a separate problem and not solved here.
    """
    return ids.make_id(rec["platform"], rec["company_token"], rec["source_id"])


def ensure_schema(conn):
    """Create the jobs schema and tables. Idempotent."""
    conn.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    conn.execute(f"SET search_path TO {SCHEMA}, public")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            platform TEXT NOT NULL,
            company_token TEXT NOT NULL,
            company_name TEXT NOT NULL,
            source_id TEXT NOT NULL,
            title TEXT,
            location_raw TEXT,
            department TEXT,
            job_url TEXT,
            posted_at TEXT,
            seniority_guess TEXT,
            location_is_nyc BOOLEAN,
            location_is_remote BOOLEAN,
            company_is_nyc_hq BOOLEAN,
            company_is_ai_focused BOOLEAN,
            status TEXT NOT NULL DEFAULT 'open',
            description_text TEXT,
            raw_json TEXT,
            content_hash TEXT,
            first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL,
            closed_at TEXT
        )
    """)
    conn.commit()
    # One row per (job, profile) -- see SCORES ARE PER PROFILE above.
    # ON DELETE CASCADE because a score for a job that no longer exists is
    # meaningless; nothing deletes from jobs today (closing is a status
    # change) but leaving orphans possible would be a slow leak if that ever
    # changes.
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCORES_TABLE} (
            job_id TEXT NOT NULL REFERENCES jobs(id)
                ON DELETE CASCADE ON UPDATE CASCADE,
            profile TEXT NOT NULL,
            fit_score INTEGER,
            primary_track TEXT,
            gap_friendly_signal BOOLEAN,
            key_technologies TEXT,
            gap_bridging_angle TEXT,
            risk_factors TEXT,
            scored_at TEXT NOT NULL,
            scoring_model TEXT,
            PRIMARY KEY (job_id, profile)
        )
    """)
    # select_unscored_jobs anti-joins on (profile, job_id) and the ranking
    # query sorts by fit_score within a profile; both are profile-first.
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_job_scores_profile "
                 f"ON {SCORES_TABLE}(profile, fit_score DESC)")
    conn.commit()

    # -- the multi-user scoring tables ---------------------------------------
    # See the SCORING IS TWO TIERS note in the module docstring for why these
    # exist and which of them costs money to fill.
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {PROFILES_TABLE} (
            profile TEXT PRIMARY KEY,
            display_name TEXT,
            persona_json TEXT NOT NULL,
            relevance_json TEXT,
            criteria_json TEXT NOT NULL,
            criteria_version INTEGER NOT NULL DEFAULT 1,
            daily_narrative_budget INTEGER NOT NULL DEFAULT 20,
            active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    # One row per posting, never per profile: these are properties of the job
    # itself, so the LLM call that produces them is paid once and shared by
    # every profile that will ever exist. That is the whole cost argument.
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {FACTS_TABLE} (
            job_id TEXT PRIMARY KEY REFERENCES jobs(id)
                ON DELETE CASCADE ON UPDATE CASCADE,
            facts_version INTEGER NOT NULL,
            seniority_level TEXT,
            years_experience_min INTEGER,
            years_experience_max INTEGER,
            role_archetype TEXT,
            tech_stack TEXT,
            ai_involvement TEXT,
            ml_research_required BOOLEAN,
            advanced_degree_required BOOLEAN,
            customer_facing BOOLEAN,
            remote_policy TEXT,
            employment_type TEXT,
            comp_min INTEGER,
            comp_max INTEGER,
            comp_currency TEXT,
            gap_friendly_language BOOLEAN,
            visa_sponsorship TEXT,
            summary TEXT,
            extracted_at TEXT NOT NULL,
            extraction_model TEXT
        )
    """)
    # Cheap and disposable: recomputed from job_facts whenever facts or
    # criteria move, so nothing here is precious. The version columns are what
    # make that incremental instead of a full rebuild.
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {MATCHES_TABLE} (
            job_id TEXT NOT NULL REFERENCES jobs(id)
                ON DELETE CASCADE ON UPDATE CASCADE,
            profile TEXT NOT NULL,
            match_score INTEGER NOT NULL,
            match_reasons TEXT NOT NULL,
            facts_version INTEGER NOT NULL,
            criteria_version INTEGER NOT NULL,
            matched_at TEXT NOT NULL,
            PRIMARY KEY (job_id, profile)
        )
    """)
    # Nothing in the pipeline reads this yet. It exists because engagement
    # cannot be collected retroactively -- every day without it is training
    # data for the learned ranker that can never be recovered. Recording the
    # scores AS OF the impression is the load-bearing part: without them you
    # cannot reconstruct what the user was reacting to once weights change.
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {EVENTS_TABLE} (
            id BIGSERIAL PRIMARY KEY,
            profile TEXT NOT NULL,
            job_id TEXT NOT NULL REFERENCES jobs(id)
                ON DELETE CASCADE ON UPDATE CASCADE,
            event TEXT NOT NULL,
            match_score INTEGER,
            fit_score INTEGER,
            occurred_at TEXT NOT NULL
        )
    """)
    conn.commit()
    # match.py's hot path is "top N for this profile"; extract.py's is "which
    # jobs still lack facts at the current version".
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_job_matches_profile "
                 f"ON {MATCHES_TABLE}(profile, match_score DESC)")
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_job_facts_version "
                 f"ON {FACTS_TABLE}(facts_version)")
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_job_events_profile "
                 f"ON {EVENTS_TABLE}(profile, occurred_at DESC)")
    conn.commit()

    _ensure_fk_update_cascade(conn)
    for name, col in (("idx_jobs_company", "company_token"),
                      ("idx_jobs_status", "status"),
                      ("idx_jobs_seniority", "seniority_guess"),
                      ("idx_jobs_nyc", "location_is_nyc")):
        conn.execute(f"CREATE INDEX IF NOT EXISTS {name} ON jobs({col})")
    conn.commit()
    # The watermark table lives in this schema too, and every ingest script
    # writes it before writing a single row. Each of the six used to create
    # it inline; centralising ensure_schema() moved that responsibility here.
    # with_claims because this pipeline leases datasets -- see state.try_claim.
    state.ensure_state_schema(conn, watermark_table=WATERMARK_TABLE,
                              with_claims=True)

    # Two source-specific side tables. They are not part of the jobs row, but
    # they are part of this schema, and the scripts that write them do so
    # before their first upsert -- so they have to exist by the time
    # ensure_schema() returns, exactly like the watermark table.
    #
    # hn_seen_comments is hn-hiring.py's dedup ledger and is load-bearing for
    # correctness: it, not jobs.jobs, is the source of truth for "this HN
    # comment was already parsed."  google_jobs_query_stats is append-only
    # history for the not-yet-built adaptive-cadence feature (see
    # DEVELOPER.md); nothing reads it yet, but both Google scripts write it
    # on every run and previously carried identical copies of this DDL.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS hn_seen_comments (
            comment_id TEXT PRIMARY KEY,
            fetched_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS google_jobs_query_stats (
            slug TEXT NOT NULL,
            run_at TEXT NOT NULL,
            new_count INTEGER NOT NULL,
            total_fetched INTEGER NOT NULL,
            days_since_last_run REAL,
            PRIMARY KEY (slug, run_at)
        )
    """)
    conn.commit()


#: Child tables whose job_id must follow jobs.id when a row is re-keyed.
#: The newer three are created with ON UPDATE CASCADE already; they are listed
#: so that adding a table is never silently the thing that reintroduces the
#: migrate_google_ids.py failure described below.
_JOB_CHILD_FKS = (
    (SCORES_TABLE, "job_id"),
    (FACTS_TABLE, "job_id"),
    (MATCHES_TABLE, "job_id"),
    (EVENTS_TABLE, "job_id"),
)


def _ensure_fk_update_cascade(conn):
    """Upgrade pre-existing job_id foreign keys to ON UPDATE CASCADE.

    WHY THIS EXISTS
        The original job_scores FK was ON DELETE CASCADE only. Deleting a job
        took its scores with it, which was the case anyone thought about --
        but CHANGING a job's id was not, and the primary key is a content
        hash, so re-keying is a thing that genuinely happens.

        migrate_google_ids.py hit exactly this: it correctly repointed the
        losers' scores before deleting them, then failed on
        `UPDATE jobs SET id = ...` for every survivor that had a score of its
        own, because changing the parent key would orphan the child. 496 of
        632 groups aborted. The migration is not wrong; the constraint was.

        ON UPDATE CASCADE is also the honest semantics: a score belongs to a
        posting, not to a particular spelling of its primary key.

    Idempotent -- checks pg_constraint.confupdtype and only rebuilds a
    constraint that is not already 'c' (CASCADE), so ordinary runs do no DDL
    and take no locks.
    """
    for table, col in _JOB_CHILD_FKS:
        row = conn.execute(
            """
            SELECT conname FROM pg_constraint
            WHERE conrelid = %s::regclass AND contype = 'f'
              AND confupdtype <> 'c'
              AND conkey = ARRAY[(SELECT attnum FROM pg_attribute
                                  WHERE attrelid = %s::regclass AND attname = %s)]
            """,
            (f"{SCHEMA}.{table}", f"{SCHEMA}.{table}", col),
        ).fetchone()
        if not row:
            continue
        conn.execute(f"ALTER TABLE {table} DROP CONSTRAINT {row[0]}")
        conn.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT {row[0]} "
            f"FOREIGN KEY ({col}) REFERENCES jobs(id) "
            f"ON DELETE CASCADE ON UPDATE CASCADE"
        )
        conn.commit()


# -- lifecycle ---------------------------------------------------------------

def close_missing(conn, platform, token, seen_ids, now=None):
    """Close listings that were open but absent from this run's fetch.

    Only valid for sources returning a company's COMPLETE listing set -- the
    ATS boards. SAFETY VALVE: an empty seen_ids would close every open job
    for the company, which is correct only if the fetch is trustworthy, so
    it raises instead. The original relied on the caller remembering.
    """
    from pipelib.timeparse import utc_now_str
    if not seen_ids:
        raise ValueError(
            "close_missing requires a non-empty seen_ids -- an empty fetch "
            "would close every open job for this company")
    now = now or utc_now_str()
    cur = conn.execute(
        """
        UPDATE jobs SET status = 'closed', closed_at = %s, last_seen = %s
        WHERE platform = %s AND company_token = %s AND status = 'open'
          AND NOT (source_id = ANY(%s))
        """,
        (now, now, platform, token, list(seen_ids)),
    )
    conn.commit()
    return cur.rowcount


def close_stale(conn, platform, stale_days, now=None):
    """Close listings not seen for `stale_days`.

    For sources returning a sampled slice rather than a full listing set,
    where absence from any single fetch means nothing.
    """
    from datetime import timedelta
    from pipelib.timeparse import utc_now, utc_now_str
    now = now or utc_now_str()
    cutoff = (utc_now() - timedelta(days=stale_days)).strftime("%Y-%m-%dT%H:%M:%S")
    cur = conn.execute(
        """
        UPDATE jobs SET status = 'closed', closed_at = %s
        WHERE platform = %s AND status = 'open' AND last_seen < %s
        """,
        (now, platform, cutoff),
    )
    conn.commit()
    return cur.rowcount


def prune_old_closed(conn, days):
    from datetime import timedelta
    from pipelib.timeparse import utc_now
    cutoff = (utc_now() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
    cur = conn.execute(
        "DELETE FROM jobs WHERE status = 'closed' AND closed_at IS NOT NULL "
        "AND closed_at < %s", (cutoff,))
    conn.commit()
    return cur.rowcount
