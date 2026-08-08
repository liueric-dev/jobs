"""The `jobs` table -- DDL, column specs, and lifecycle helpers.

Owned by the jobs pipeline, deliberately not by lib/: lib provides
mechanism (upsert, retry, hashing, checkpoints, claims) and knows nothing
about what a job listing is. This module is the single definition the six
ingest scripts and score.py share, replacing six separately-drifting copies
of ensure_schema() -- one of which (ingest/google-serpapi.py) described
itself in a comment as a "Defensive duplicate of ingest/ats.py's".

DATABASE, NOT SCHEMA
    These tables own the `jobs` database and live in its `public` schema.
    They used to be a `jobs` schema inside the events database, told apart
    from `public.events` by a per-connection search_path -- which did not
    error when you forgot it, it silently read and wrote `public`. The
    boundary is now one Postgres enforces: no role granted on this database
    can reach events data at all.

    What that trades away is a mistake that used to be harmless. The two
    applications are now distinguished ONLY by the database named in
    DATABASE_URL, and both put unqualified tables in `public`. Point this
    pipeline at the events database and nothing would stop it creating all 13
    tables next to `public.events` -- so ensure_schema() refuses to run when
    `public.events` exists. That guard, and the fact that no non-superuser
    role can connect to nyc_events, are what make a half-finished rollback
    (repointing .env without reverting SCHEMA, or the reverse) fail loudly.

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
    google-serpapi's choose_date_chip(). lib.timeparse.utc_now_str()
    produces exactly this format and is the only thing that should.
"""

import os
from collections.abc import Iterable
from typing import Any

import psycopg
from psycopg import sql

from lib import dbconn, ids, state
from lib.upsert import TableSpec

#: The schema these tables live in, inside the `jobs` database. Every
#: connect(schema=...) call site reaches it through this one constant, which is
#: what let the database split be a one-line change here rather than 22.
SCHEMA = "public"
TABLE = "jobs"
WATERMARK_TABLE = "job_ingest_state"

STATUS_OPEN = "open"
STATUS_CLOSED = "closed"

#: Columns written from a normalized record. Every normalize_* function must
#: supply every key here: upsert binds them as named parameters, so a missing
#: one fails that record (isolated by its SAVEPOINT) rather than the batch.
COLUMNS = (
    "platform", "company_token", "company_name", "source_id",
    "title", "location_raw", "department", "job_url", "posted_at",
    "posted_at_ts", "salary_text",
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
COHORT_SIGNAL_TABLE = "cohort_signal"

#: How many DISTINCT Builders must have a posting currently saved before the
#: cohort badge says anything at all. THIS IS A PRIVACY CONTROL AND NOT A
#: DISPLAY PREFERENCE, which is why it is a constant here rather than a literal
#: in the query or a config knob.
#:
#: The argument is in `git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_five/28-cohort-aggregation.md`
#: § The small-N problem and it is arithmetic, not caution. Thirty Builders who see each other
#: in a classroom: "1 Builder saved this", plus knowing who was on their laptop,
#: plus a posting for a role someone mentioned out loud, is an identification.
#: An aggregate is not automatically anonymous at this scale.
#:
#: LOWERING IT TO SEE OUTPUT IS THE ONE THING NOT TO DO. The live cohort is two
#: labellers today (`git show refactor-freeze-2026-08-02:docs/labelling-report-2026-08-02.md`), so at 3 this table is
#: empty by construction -- and an empty badge is the CORRECT rendering of a
#: two-person cohort, not a bug to tune away. webapp/tests/test_cohort_signal.py
#: TestSuppression pins that 2 savers produce no row.
COHORT_MIN_SAVERS = 3

#: (inclusive upper bound or None for "no ceiling", label), in order. Bucketed
#: rather than exact because an exact count that increments visibly lets an
#: observer infer WHEN somebody saved something, and timing is the strongest
#: deanonymiser available in a room where people can see each other.
#:
#: NOTE ON THE BOUNDARY, because the labels are ambiguous and the code is not:
#: 10 savers is '6-10' -- the first matching bound wins -- so '10+' means ELEVEN
#: or more despite reading as "ten or more". The labels are the task file's,
#: verbatim, and the fixtures in frontend/fixtures/contract/ already show those
#: exact strings, so they are not ours to tidy.
COHORT_BUCKETS = ((5, "3-5"), (10, "6-10"), (None, "10+"))

#: Just the labels, for the CHECK constraint and for anything asserting on the
#: vocabulary. One tuple, so the constraint and the writer cannot disagree.
COHORT_BUCKET_LABELS = tuple(label for _, label in COHORT_BUCKETS)


def cohort_bucket(savers: int) -> str | None:
    """Bucket a distinct-Builder count, or None if it must be suppressed.

    Pure arithmetic, no I/O, so the suppression rule is unit-testable without a
    database -- the same property score_job() is kept for. It is the ONLY place
    the threshold and the boundaries are applied; cohort.py's SQL selects which
    rows exist and this decides what they are allowed to say.
    """
    if savers < COHORT_MIN_SAVERS:
        return None
    for bound, label in COHORT_BUCKETS:
        if bound is None or savers <= bound:
            return label
    raise AssertionError("COHORT_BUCKETS has no open-ended final bucket")


SEARCH_QUERIES_TABLE = "search_queries"
SEARCH_WATCHERS_TABLE = "search_query_watchers"
SEARCH_SIGNAL_TABLE = "search_query_signal"
SEARCH_RESULTS_TABLE = "search_query_results"

#: How many DISTINCT Builders must currently watch a search before its badge
#: says anything at all. SAME KIND OF CONTROL AS COHORT_MIN_SAVERS ABOVE, SAME
#: RULE ABOUT LOWERING IT, AND DELIBERATELY A DIFFERENT NUMBER.
#:
#: The copy-the-neighbour answer is 3, and it is wrong here for one reason:
#: WHAT IS BEING COUNTED IS ATTACKER-CHOSEN. The set of postings a save count
#: can be observed on is fixed by the pipeline -- an observer can watch a badge
#: but cannot conjure the posting it sits on. A search query is created by
#: submitting it, which is free and unlimited to anyone with an account. An
#: observer who suspects a specific Builder is looking for "bilingual healthcare
#: operations Brooklyn" can type exactly that, create the row, and then watch
#: its bucket. That is a chosen-plaintext capability the save path does not
#: have, and it makes 3 weaker here than the same 3 is there.
#:
#: It compounds with a second asymmetry: THE PLANTER IS ALWAYS A WATCHER.
#: POST /v1/searches registers its caller, so at a floor of 3 the badge appears
#: when 2 OTHER people arrive -- an anonymity set of two, in a thirty-person
#: cohort who sit in a room together. 4 restores the set of three that
#: COHORT_MIN_SAVERS was chosen to give.
#:
#: WHY NOT HIGHER. At N=30 a floor of 5 or 6 means most real searches never show
#: a badge, and a signal nobody ever sees is not a privacy win -- it is the
#: feature removed, on a guess rather than on a measurement. 4 is the smallest
#: number that survives both asymmetries.
#:
#: WHAT IT DOES NOT DEFEND AGAINST, so it is not read as more than it is: a
#: planter who gets no badge still learns "fewer than four". The mitigation is
#: the same one COHORT_MIN_SAVERS relies on -- every count below the floor is
#: rendered identically, because search_watcher_bucket() returns None for all of
#: them and search_query_signal holds no row at all. tests/test_search_queries.py
#: TestSuppression pins that two watchers and zero watchers are indistinguishable.
#:
#: LOWERING IT TO SEE OUTPUT IS THE ONE THING NOT TO DO -- the live cohort is
#: two labellers today (`git show refactor-freeze-2026-08-02:docs/labelling-report-2026-08-02.md`), so this table is
#: empty by construction, and an empty badge is the CORRECT rendering of a
#: two-person cohort rather than a bug to tune away.
SEARCH_MIN_WATCHERS = 4

#: (inclusive upper bound or None for "no ceiling", label), in order -- the same
#: shape as COHORT_BUCKETS and applied by the same first-match-wins rule.
#:
#: THE LABELS DO NOT OVERLAP, WHICH IS THE ONE PLACE THIS DEVIATES FROM ITS
#: NEIGHBOUR. COHORT_BUCKETS reads '3-5' | '6-10' | '10+', where 10 satisfies
#: two of the three and '10+' actually means eleven or more; that comment says
#: those labels are the task file's verbatim and already shipped in
#: frontend/fixtures/contract/, so they are not that constant's to tidy. This
#: vocabulary is new, tranche_four/25 specifies no labels at all, and nothing
#: has shipped against it -- so the boundaries are written to say what they mean
#: the first time. A label a value can satisfy twice is a boundary that leaks
#: which side of it the value was on.
SEARCH_WATCHER_BUCKETS = ((6, "4-6"), (10, "7-10"), (None, "11+"))

#: Just the labels, for the CHECK constraint and for anything asserting on the
#: vocabulary. One tuple, so the constraint and the writer cannot disagree.
SEARCH_WATCHER_BUCKET_LABELS = tuple(label for _, label in SEARCH_WATCHER_BUCKETS)

#: The closed set of search_queries.source. 'track' means the row exists because
#: role_track has this value, which is what makes "one seeded query per track"
#: checkable; 'seeded' is reserved for a hand-added query that is not a track --
#: there are none today, and the value exists so that adding one later is not a
#: CHECK-constraint migration under load.
SEARCH_SOURCES = ("builder", "seeded", "track")


def search_watcher_bucket(watchers: int) -> str | None:
    """Bucket a distinct-Builder watcher count, or None if it must be suppressed.

    Pure arithmetic, no I/O, deliberately identical in shape to cohort_bucket()
    above: the ONLY place the threshold and the boundaries are applied.
    searchqueries.py's SQL selects which rows exist and this decides what they
    are allowed to say.
    """
    if watchers < SEARCH_MIN_WATCHERS:
        return None
    for bound, label in SEARCH_WATCHER_BUCKETS:
        if bound is None or watchers <= bound:
            return label
    raise AssertionError("SEARCH_WATCHER_BUCKETS has no open-ended final bucket")


#: Bump to invalidate every extracted row. job_facts.facts_version records
#: which generation of the extraction schema produced a row, so "which rows
#: predate the new field" is a query rather than a guess, and a re-extraction
#: can be a resumable backlog burn-down instead of a TRUNCATE.
#:
#: 2 (2026-07-26): the INPUT changed, not the schema. Version 1 rows were
#: extracted from Greenhouse descriptions that stored escaped markup as
#: literal text and were truncated at 5,000 chars, so roughly a quarter of the
#: 3,000-char prompt budget was spent on `&lt;div class=&quot;` instead of
#: prose. Measured against a self-consistency control on 50 postings, the
#: clean text moves tech_stack (-13.1 jaccard), employment_type (-18.0) and
#: years_experience_min (-10.0) beyond run-to-run noise; role_archetype and
#: ai_involvement were unaffected. See migrate_ats_descriptions.py.
#:
#: 3 (2026-07-28, task 12): the SEMANTICS changed, and four separate changes
#: are settled by this one number. Each independently invalidated every row;
#: bumping once means one burn-down instead of four. What moved:
#:   * Vote semantics. config/extraction-policy.json and extract.vote_facts()
#:     made extraction per-platform: a posting from a source below the 0.90
#:     self-agreement threshold is now a field-wise majority over three passes,
#:     where every version-2 row is a single draw. job_facts.extraction_passes
#:     and .vote_unanimity record which a row got.
#:   * role_archetype's vocabulary went from 12 values to 26
#:     (extract.ARCHETYPE), so a posting that answered "other" under version 2
#:     may answer "support_ops" under version 3 with no change to the posting.
#:   * role_track is a new extracted field, NULL on every version-2 row
#:     because nothing had been extracted for it.
#:   * normalize() stopped defaulting role_archetype, ai_involvement,
#:     remote_policy and the four booleans (extract.py:520-573), so an absent
#:     answer is now NULL rather than "other" / "none" / "unknown" / false.
#:     That changes what a stored value MEANS, not merely which values occur.
#: The middle three all edit _INSTRUCTIONS, extract.py's cache-keyed fixed
#: prefix, whose own comment asks for a bump on exactly this kind of change.
#:
#: WHAT THIS BUMP DID NOT VALIDATE, stated so the version number is not read as
#: evidence it does not carry: the majority-of-3 vote DID NOT FIRE during the
#: version-3 re-extraction. hn_whoishiring is the only platform below the 0.90
#: threshold and it contributed 0 of the 863 rows re-extracted. 208 of its
#: postings are open and described, so they were not filtered out by status --
#: the active profile set moved to `pursuit` alone in the same operation, and
#: the relevance union rejects every one of them. So the vote-semantics item
#: is paid on paper -- version 3 now means "extracted under the per-platform
#: policy" -- while the mechanism itself remains unexercised in production.
#: The first hn_whoishiring row to become eligible is the first real test of
#: vote_facts(); do not treat 3 as a passing grade for it. See
#: `git show refactor-freeze-2026-08-02:docs/facts-v3-diff.md`.
#:
#: STRANDED ROWS ARE EXPECTED AND ARE NOT A BUG. _eligible_sql requires
#: j.status = open (extract.py:405), so a bump never reaches facts rows whose
#: job has since closed -- 85 rows at the time of this bump, 15 of them still
#: at version 1. The invariant this bump can actually hold is "no OPEN,
#: relevant row sits below the current version", not "no row anywhere does".
#: Do not delete those rows to make a count come out; they are the last facts
#: anyone has about a posting that no longer exists.
FACTS_VERSION = 3

#: The narrative prompt's version, recorded on every job_scores row so a
#: stored narrative knows which template produced it. score.build_prompt owns
#: the template; this constant lives here for the same reason FACTS_VERSION
#: does -- it is a column value, the migration and the staleness report both
#: need it, and importing score.py drags in llm, relevance and a persona file.
#:
#: THE BUMP RULE IS ABSOLUTE: any change to the digest of build_prompt()'s
#: output bumps this, whitespace included. tests/test_score_versions.py pins
#: that digest, so editing the template fails the suite and the only fix is to
#: bump here in the same diff. No carve-outs for "cosmetic" edits -- arguing
#: about which changes really matter is how bumps get skipped.
#:
#: That absolutism is affordable ONLY because invalidation is inert: a stale
#: row is never re-scored until an operator passes score.py --rescore-stale
#: with an explicit --limit. Over-sensitivity costs nothing here. If re-scoring
#: ever becomes automatic, this rule has to be renegotiated first.
#:
#: Starts at 1, not 2. Every row written before this column existed is NULL,
#: and NULL is not "version 0" -- see the unversioned-is-not-stale note in
#: score.py.
SCORE_PROMPT_VERSION = 1

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


def resolve_profile(persona: dict[str, Any] | None = None) -> str:
    """Which profile's scores we are reading or writing.

    JOBS_PROFILE wins so a one-off run can score against an alternate persona
    without editing config; otherwise the persona file names itself. Both are
    optional -- an unlabelled persona is DEFAULT_PROFILE, which is what every
    existing deployment was implicitly using when scores lived on `jobs`.
    """
    return (os.environ.get("JOBS_PROFILE")
            or (persona or {}).get("profile")
            or DEFAULT_PROFILE)


def spec(hash_fields: tuple[str, ...], blank_if_falsy: tuple[str, ...] = ("description_text",),
         sticky: tuple[str, ...] = ()) -> TableSpec:
    """A TableSpec for one source's hash field set.

    `computed` reopens a listing that reappears upstream: status back to
    'open' and closed_at cleared, on INSERT and UPDATE alike. Paired with
    revive_column, a row previously marked closed counts as an update rather
    than as unchanged, so a reappearance is never silently ignored.

    `sticky` is empty for every source that reports an absolute publication
    date, which is all of them except Google -- see google_spec().
    """
    return TableSpec(
        table=TABLE,
        columns=COLUMNS,
        hash_fields=hash_fields,
        blank_if_falsy=blank_if_falsy,
        computed={"status": f"'{STATUS_OPEN}'", "closed_at": "NULL"},
        revive_column="status",
        revive_value=STATUS_OPEN,
        sticky=sticky,
    )


#: Derived from a relative string ("23 days ago") rather than an absolute date,
#: so the value depends on WHEN it was computed. First observation wins.
GOOGLE_STICKY = ("posted_at", "posted_at_ts")


def google_spec() -> TableSpec:
    """The spec for every Google Jobs writer -- both ingest scripts and api/.

    A function rather than three call sites passing the same arguments,
    because the three have to agree and there is nothing else making them.
    That is the same lesson google_jobs.py exists to record: the SerpApi
    script, the Apify script and the contributor API are three routes into one
    table, and every property they must share belongs in one place.

    ONLY the Google sources are sticky. ATS, WeWorkRemotely, Built In and HN
    all report an absolute publication date, which re-derives identically
    forever, so pinning it there would buy nothing and would additionally
    ignore a genuine upstream correction.
    """
    return spec(HASH_FIELDS_SHORT, sticky=GOOGLE_STICKY)


def make_job_id(rec: dict[str, Any]) -> str:
    """Primary key: sha256("platform:token:source_id")[:24].

    Identical to the expression all six scripts used, so existing keys are
    preserved -- verified against 3,000 live rows. Deduplicates within a
    source only: the same posting arriving via both Greenhouse and Google
    Jobs is two rows, which ingest/builtin-nyc.py already acknowledged.
    Cross-source dedup is a separate problem and not solved here.
    """
    return ids.make_id(rec["platform"], rec["company_token"], rec["source_id"])


def ensure_schema(conn: psycopg.Connection) -> None:
    """Create the jobs tables. Idempotent.

    Refuses to run against the events database. See DATABASE, NOT SCHEMA
    above: since the split, a wrong DATABASE_URL is no longer a harmless
    mistake -- it would create these 14 tables in `public` alongside
    `public.events`, and nothing downstream would report it. `public.events`
    exists in exactly one database and never in this one, so it is the cheapest
    honest way to ask "am I where I think I am".
    """
    events_check = conn.execute("SELECT to_regclass('public.events')").fetchone()
    if events_check is not None and events_check[0] is not None:
        raise RuntimeError(
            "refusing to run: DATABASE_URL points at the events database "
            "(public.events exists here). The jobs tables live in the `jobs` "
            "database -- check this application's .env."
        )
    conn.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    conn.execute(f"SET search_path TO {SCHEMA}")
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
    # The cohort badge's materialised answer (tranche_five/28), beside the table
    # it is folded from. One row per posting the cohort is ALLOWED to be told
    # about, refreshed nightly by cohort.py, joined by webapp/jobs.py and read
    # by nothing else.
    #
    # MATERIALISED RATHER THAN COMPUTED LIVE, which is the task file's
    # instruction and has two reasons. Live computation invites a timing side
    # channel -- a badge that flips mid-session tells an observer that somebody
    # in the room just saved something, which is the recency leak the whole
    # design exists to avoid -- and it puts a fold over an append-only log on
    # every list render.
    #
    # THE PIPELINE OWNS IT, NOT webapp/. builder_job_state (webapp/schema_web.py)
    # carries saved_at per Builder and is the obvious source; it is also on the
    # far side of the ownership line this file's processes keep -- they share
    # only this file and lib/, and none imports another -- and the compute runs
    # on the nightly cycle. A pipeline table must not require the surfacing
    # service's schema, the same argument app_user_id is annotated with below.
    # So the fold reads job_events, which lives here. See cohort.py.
    #
    #   save_bucket -- '3-5' | '6-10' | '10+'. NOT NULL, AND THAT IS A
    #     DELIBERATE DEVIATION from the task file's sketch, which lists null as
    #     a fourth value. A row with a NULL bucket would mean "somebody saved
    #     this and it is below three", and the webapp role holds SELECT on this
    #     table -- so the row's mere EXISTENCE would publish the fact the
    #     threshold exists to withhold. That is the suppression failing open,
    #     one indirection later than the obvious way. Absence is the answer for
    #     everything below the threshold: a posting with two savers and a
    #     posting with none are the same query result and are indistinguishable,
    #     which is what "absence of a badge must not be readable as exactly one
    #     or two" asks for. The endpoint LEFT JOINs and renders the miss as
    #     null, so the API shape the task file describes is unchanged.
    #   computed_at -- when the nightly fold last ran. Provenance for an
    #     operator, and DELIBERATELY NOT SERVED: it is a per-posting timestamp
    #     that moves when the underlying set moves, so a client that could read
    #     it would have the recency channel back. webapp/jobs.py selects
    #     save_bucket and nothing else.
    #
    # No index beyond the primary key. Every read is a lookup by
    # (job_id, cohort_profile) from a LEFT JOIN, which the PK already serves;
    # nothing orders or ranges over this table, and nothing may -- ordering by
    # a save count is the ranking feedback loop the task file rules out.
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {COHORT_SIGNAL_TABLE} (
            job_id TEXT NOT NULL REFERENCES jobs(id)
                ON DELETE CASCADE ON UPDATE CASCADE,
            cohort_profile TEXT NOT NULL,
            save_bucket TEXT NOT NULL,
            computed_at TEXT NOT NULL,
            PRIMARY KEY (job_id, cohort_profile),
            CONSTRAINT cohort_signal_bucket CHECK (save_bucket IN (
                {', '.join("'" + b + "'" for b in COHORT_BUCKET_LABELS)}))
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
    # The surfacing layer's hot path, which is a different question from the
    # one above: "has this profile already saved or dismissed THIS job", asked
    # once per row on every list render. (profile, occurred_at DESC) answers
    # "recent activity" and cannot answer this one, so webapp/ would sequential-
    # scan a growing table on every page.
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_job_events_profile_job "
                 f"ON {EVENTS_TABLE}(profile, job_id)")
    conn.commit()

    _ensure_fk_update_cascade(conn)

    # Columns added after the table already existed in the wild. Routed through
    # add_missing_columns (which checks the catalog first) rather than a bare
    # ADD COLUMN IF NOT EXISTS, because the latter still takes an ACCESS
    # EXCLUSIVE lock on every run even when it changes nothing -- see
    # lib/dbconn.py and the idle-transaction incident in DATABASE.md.
    #
    #   posted_at_ts -- sortable absolute time. posted_at is TEXT, is in every
    #     HASH_FIELDS_* tuple (so its format is frozen), and holds three
    #     incompatible formats including Built In's relative English
    #     ("Reposted 8 Hours Ago"), which no database can order. See
    #     text.posted_at_timestamp.
    #   salary_text  -- ingest/builtin-nyc.py has always parsed this and it has
    #     always been in HASH_FIELDS_BUILTIN, but it was never in COLUMNS, so
    #     every run hashed it and threw it away.
    dbconn.add_missing_columns(conn, "jobs", [
        ("posted_at_ts", "TIMESTAMPTZ"),
        ("salary_text", "TEXT"),
    ])

    # The extraction stability signal, added when extract.py started spending
    # more than one call on the platforms measured least self-consistent (see
    # config/extraction-policy.json and extract.vote_facts).
    #
    #   extraction_passes -- how many usable passes this row was voted from,
    #     as it happened rather than as the policy asks: a three-pass platform
    #     whose extra calls were rate-limited records 1. Without it, "was this
    #     row voted on" is unanswerable after the fact, and the answer changes
    #     what the row is worth.
    #   vote_unanimity    -- the fraction of voted fields on which every pass
    #     agreed, or NULL for a single pass. NULL rather than 1.0 deliberately:
    #     one pass agrees with itself trivially, and 1.0 would make an
    #     unmeasured row indistinguishable from a genuinely unanimous one in
    #     exactly the query this column exists to answer.
    #
    # Both are NULL for every row extracted before this, which is honest --
    # nothing recorded it. migrations/migrate_extraction_passes.py can fill
    # extraction_passes=1 for them, which is a fact about how the pipeline ran,
    # not a guess. It deliberately does not invent a unanimity.
    #
    #   role_track -- the browsable role family a posting belongs to
    #     (extract.ROLE_TRACK), a coarser grain than role_archetype and a
    #     separate axis rather than a rollup of it. NULLABLE BY DESIGN: the
    #     clustering it was derived from covers 83.2% of the corpus and
    #     `git show refactor-freeze-2026-08-02:docs/role-track-derivation.md` is explicit that the tail below n=5 is
    #     not trustworthy, so "no track fits this" has to be representable
    #     rather than rounded to the nearest one. The vocabulary itself is
    #     PROVISIONAL -- derived pre-Phase-3 from a tech-heavy corpus, and
    #     tools/derive-role-tracks.py exists to re-run it once Phase 3 lands.
    #
    # ~~role_track is NULL on every existing row and stays NULL until task 12
    # re-extracts.~~ TASK 12 IS DONE and this sentence stopped being true with
    # it; the rule below still holds and is why it is struck rather than
    # deleted. Nothing has ever been backfilled for this column and nothing
    # should be -- the same rule as job_events.rank, where a guessed value is
    # worse than a missing one. What is NULL now is the genuine "no track fits
    # this", plus rows stranded below FACTS_VERSION.
    #
    # A corpus statistic here has a shelf life of one night
    # (`git show refactor-freeze-2026-08-02:docs/facts-v3-diff.md`). Measure it through jobs_app, not this table --
    # the view inner-joins job_matches and applies four completeness
    # predicates, so what reaches a Builder is a strict subset.
    dbconn.add_missing_columns(conn, FACTS_TABLE, [
        ("extraction_passes", "INTEGER"),
        ("vote_unanimity", "REAL"),
        ("role_track", "TEXT"),
    ])

    # The narrative's cache keys. job_scores shipped with none, so re-scoring
    # triggered only on an anti-join for "no row exists" (score.py) -- a
    # violation of CLAUDE.md's "every derived row records the version of
    # everything upstream" that nothing noticed because pursuit has no scores
    # and tech/frontend are inactive.
    #
    # The narrative's inputs are exactly four: the persona, the facts block,
    # the prompt template and the model. Three become columns here; the fourth
    # already exists as scoring_model.
    #
    #   facts_version    -- the job_facts version the facts block was built
    #     from. Compared against the JOINED row's version, never against
    #     FACTS_VERSION: a score is stale when the facts IT READ have since
    #     changed, not because extraction is behind. The latter is extract.py's
    #     job and would mark all 5,029 v2 rows permanently stale for nothing.
    #   persona_sha      -- score.persona_sha(), a digest of exactly the five
    #     persona keys build_prompt reads. A digest rather than an integer
    #     version because it cannot be forgotten, and a FIVE-KEY digest rather
    #     than a whole-blob one because persona_json carries _comment
    #     documentation that never reaches a prompt.
    #   prompt_version   -- SCORE_PROMPT_VERSION above.
    #   criteria_version -- RECORDED FOR PROVENANCE, DELIBERATELY NOT A CACHE
    #     KEY. build_prompt and _facts_block never read match_score or
    #     match_reasons, so criteria changes which jobs are asked about, never
    #     what is asked. It is stored because L2 analysis of job_events must
    #     know which weight generation ordered the list a user saw. The
    #     exclusion is enforced by test, not by this comment.
    #
    # NULLABLE WITH NO DEFAULT, and nothing backfills them. A DEFAULT would
    # fabricate a value for all 1,293 pre-existing rows. Nothing about them is
    # recoverable as a fact: build_prompt changed mid-history (e1cdf7b) and the
    # rows straddle it, persona_json is overwritten wholesale with no history,
    # and copying today's f.facts_version onto a v2-era narrative would stamp
    # it v3-current and permanently HIDE a genuinely stale row. An unversioned
    # row is a third state -- reported separately, never automatically stale.
    # See migrations/migrate_score_versions.py.
    #
    # jobs_app (below) is deliberately NOT extended with these. It is the app's
    # read contract and these are pipeline provenance; ensure_app_view's DROP
    # fallback makes adding a view column a one-way door.
    dbconn.add_missing_columns(conn, SCORES_TABLE, [
        ("facts_version", "INTEGER"),
        ("persona_sha", "TEXT"),
        ("prompt_version", "INTEGER"),
        ("criteria_version", "INTEGER"),
    ])

    # The position-bias instrumentation (tranche_five/27). job_events shipped
    # able to say WHAT a user did and not WHERE in the list they did it, and
    # that half cannot be recovered afterwards: rank and request_id describe the
    # state of the list at the moment it was rendered, and the render is over.
    # Position bias is the best-documented failure mode in implicit-feedback
    # ranking -- a model trained on uncorrected logs learns the previous
    # ranker's ordering back -- so an impression without a rank is not weak
    # training data, it is unusable training data.
    #
    #   request_id -- groups one rendered list. Minted by webapp/jobs.py's
    #     list endpoint, echoed by the client on every event from that render.
    #   rank       -- 1-based position within that render, global across pages
    #     rather than per-track: the ordering the user actually saw.
    #   dwell_ms   -- 'open' only, and LOGGED RATHER THAN BELIEVED. A short
    #     dwell can mean disinterest or prior familiarity; a long one can mean
    #     an abandoned tab. It is a weak positive gate, never a label.
    #   reason     -- the dismiss enum (jobs.DISMISS_REASONS). A closed set,
    #     not free text, because 'wrong_level' is evidence about the seniority
    #     weight rather than about one posting -- which is what task 31 reads.
    #   visibility -- 'private' | 'cohort_anon', set server-side by event type.
    #     Only a save is ever cohort-visible; an application is private, because
    #     in a cohort competing for the same entry-level roles, seeing who else
    #     applied is discouraging at best.
    #   criteria_version -- which weight generation ordered the list. See the
    #     SCORES_TABLE block above, which added the same column for the same
    #     reason and states it directly: L2 analysis of job_events must know
    #     which generation ordered the list a user saw. Task 27 sketched a
    #     `model_version` here; that name is one of three .claude/CLAUDE.md
    #     records as "planned and never built", and criteria_version is the
    #     provenance that actually exists and is already read server-side from
    #     job_matches beside match_score.
    #
    # NULLABLE, AND NOTHING BACKFILLS THEM -- the same treatment as the block
    # above, for a sharper reason. CLAUDE.md's "do not backfill rank on existing
    # job_events rows: a guessed rank is worse than a missing one" makes NOT
    # NULL unsatisfiable here without a sentinel, and a sentinel is a guessed
    # value wearing a different name. NULL means "written before instrumentation
    # existed", which is true, legible, and already covered by the analysis
    # exclusion task 27 requires for rank. The writer enforces what the schema
    # cannot: webapp/jobs.py rejects a batch missing request_id or an impression
    # missing rank with a 400.
    #
    # visibility is the one exception and takes a DEFAULT, because it is the one
    # column whose value for an old row is knowable rather than guessed: every
    # pre-instrumentation row was written under a system that shared nothing.
    #
    # app_user_id is a LATER and DIFFERENT concern that lands in this same block
    # because it needs this block's nullability argument verbatim.
    #
    #   app_user_id -- WHICH BUILDER. Not position bias: identity. This table
    #     was keyed (profile, job_id) and thirty Builders share the `pursuit`
    #     profile, so "did this Builder see it" was not a question the table
    #     could answer at all. webapp/jobs.py resolved `seen` and `applied` from
    #     it anyway, by profile, which made one Builder's impression everyone's
    #     -- defects D66 and D67 in the defect register (deleted 2026-08-02;
    #     `git show refactor-freeze-2026-08-02:docs/ingest/DEFECTS.md`), both
    #     recorded as BLOCKED-BY this column. `applied` was the sharper half:
    #     visibility above correctly stores an application as 'private' and
    #     the response
    #     body then reported it cohort-wide, so the control was enforced in the
    #     column and defeated in the join. Task 31 had already moved `dismissed`
    #     and `saved` onto builder_job_state (webapp/schema_web.py), which
    #     carries app_user_id; `seen` and `applied` could not follow, because
    #     they derive from events and events live only here.
    #
    #     It is TEXT and not a foreign key on purpose. app_users belongs to
    #     webapp/schema_web.py, on the other side of the ownership line this
    #     file's processes keep -- the same reason builder_job_state declares a
    #     real FK to app_users and declines one to jobs. A pipeline table must
    #     not require the surfacing service's schema to exist.
    #
    # NULLABLE AND UNBACKFILLED, for exactly the reason the paragraph above
    # gives for rank. There is no recoverable fact here: the pre-existing rows
    # were written by a single labeller under a system with no per-Builder
    # identity, and stamping today's only active account onto them would assert
    # something nobody recorded -- the same guess `rank` is forbidden to make.
    # A sentinel ('unknown', '') is that guess wearing a different name, and it
    # is worse than NULL because a sentinel JOINs. NULL means "written before
    # this column existed", which is true, and it makes the read side fail in
    # the safe direction: an old impression resolves `seen` to FALSE for
    # everyone rather than TRUE for everyone.
    dbconn.add_missing_columns(conn, EVENTS_TABLE, [
        ("request_id", "TEXT"),
        ("rank", "INTEGER"),
        ("dwell_ms", "INTEGER"),
        ("reason", "TEXT"),
        ("visibility", "TEXT DEFAULT 'private'"),
        ("criteria_version", "INTEGER"),
        ("app_user_id", "TEXT"),
    ])
    # The skip derivation's only query: "un-actioned impressions before rank k
    # in this render". Without it, deriving skips on an open is a sequential
    # scan over a table whose whole purpose is to grow forever. Partial, because
    # every row this index exists to find has a request_id and the rows that do
    # not are precisely the pre-instrumentation ones no derivation may touch.
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_job_events_request "
                 f"ON {EVENTS_TABLE}(profile, request_id, rank) "
                 f"WHERE request_id IS NOT NULL")
    # The per-Builder analogue of idx_job_events_profile_job above, and needed
    # for the same reason that one is: webapp/jobs.py's _EVENT_STATE_JOIN asks
    # "has THIS Builder seen or applied to THIS job" once per row on every list
    # render, and it now asks it by app_user_id. Re-keying that join without
    # this index would move a per-row lookup off an index and onto a sequential
    # scan of a table whose whole purpose is to grow forever -- which is the
    # exact regression idx_job_events_profile_job was added to prevent, one key
    # earlier. (profile, job_id) cannot answer the new question: thirty
    # Builders share a profile, so it matches thirty times as many rows as the
    # answer needs.
    #
    # Partial, on the same argument as idx_job_events_request: the join's
    # predicate is a strict equality against a real user id, so a NULL
    # app_user_id can never satisfy it, and the NULL rows are precisely the
    # pre-existing ones that must not be attributed to anybody.
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_job_events_user_job "
                 f"ON {EVENTS_TABLE}(app_user_id, job_id) "
                 f"WHERE app_user_id IS NOT NULL")
    conn.commit()

    for name, col in (("idx_jobs_company", "company_token"),
                      ("idx_jobs_status", "status"),
                      ("idx_jobs_seniority", "seniority_guess"),
                      ("idx_jobs_nyc", "location_is_nyc")):
        conn.execute(f"CREATE INDEX IF NOT EXISTS {name} ON jobs({col})")
    # DESC NULLS LAST matches how an app reads a job board: newest first, and
    # the 126 postings whose source gave no date sort last rather than first.
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_posted_at_ts "
                 "ON jobs(posted_at_ts DESC NULLS LAST)")
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
    # correctness: it, not the jobs table, is the source of truth for "this HN
    # comment was already parsed."  google_jobs_query_stats is append-only
    # history for the not-yet-built adaptive-cadence feature (described in
    # `git show 5046f98:backend/docs/DEVELOPER.md`, deleted 2026-08-03; it is
    # not on any current roadmap
    # -- see docs/STATE-OF-THE-SYSTEM.md § 4 for what is actually open);
    # nothing reads it yet, but both Google scripts write it
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

    ensure_search_query_schema(conn)

    ensure_app_view(conn)


#: The CHECKs are GENERATED from the tuples above, never typed out beside them,
#: so the vocabulary cannot be widened in Python while the database keeps
#: refusing the new value -- a failure that surfaces as a 500 on one Builder's
#: click and nowhere else. Same construction as cohort_signal's own CHECK below
#: and as webapp/schema_web.py's _PRIOR_DOMAIN_CHECK.
_SEARCH_SOURCE_CHECK = (
    "source IN (" + ", ".join(f"'{v}'" for v in SEARCH_SOURCES) + ")")
_SEARCH_BUCKET_CHECK = (
    "watcher_bucket IN ("
    + ", ".join(f"'{v}'" for v in SEARCH_WATCHER_BUCKET_LABELS) + ")")


def ensure_search_query_schema(conn: psycopg.Connection) -> None:
    """The four tables behind tranche_four/25. Idempotent.

    WHY THEY ARE DECLARED HERE AND NOT IN webapp/schema_web.py. The webapp is
    the process a Builder talks to, so the naive home for a table a Builder
    writes is that service's own schema module. It is the wrong home, for the
    reason schema_web.py gives about tranche_five/28's cohort_signal: the
    suppression rule lives in the pipeline's nightly fold and the service must
    not be able to write a bucket it did not compute. The PIPELINE runs these
    queries, updates their run statistics, decays them and folds their watcher
    counts; the service registers a watcher and reads. Ownership follows who
    computes, not who is nearest the user.

    That split is enforced by GRANT, not by comment. The service role holds:
      search_queries        SELECT, INSERT   -- register a query. NO UPDATE:
                            run_count, last_run_at and retired_at are the
                            pipeline's, and INSERT alone cannot forge them
                            because searchnorm.REGISTER_QUERY_SQL's conflict
                            branch assigns a column to itself.
      search_query_watchers SELECT, INSERT, UPDATE  -- watch and unwatch.
      search_query_signal   SELECT ONLY. This is the exposed watcher count and
                            the service cannot write one at all.
      search_query_results  SELECT ONLY. Attaching a posting to a search is a
                            pipeline act; a service that could do it could put
                            an ungated posting in front of a Builder.

    THE EXPOSED COUNT IS A SEPARATE TABLE, NOT A COLUMN ON search_queries, and
    that is forced rather than tidy. The task file sketches
    `watcher_count INTEGER NOT NULL DEFAULT 0` on the query row. The service
    needs INSERT on that row to register a new query, and an INSERT names
    whatever columns it likes -- so a `watcher_count` column on a table the
    service can INSERT into is a count the service can write. Splitting it out
    is what makes "a value the webapp cannot write" true of the grant rather
    than of the caller's good manners.

    NO SUB-THRESHOLD ROW EXISTS. watcher_bucket is NOT NULL, so a query with
    three watchers has no row here rather than a row saying NULL. A NULL-bucket
    row would still be a row -- present for a query with 1, 2 or 3 watchers and
    absent for one with none -- and that presence is the count leaking back out
    through the side door the bucketing closed.
    """
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {SEARCH_QUERIES_TABLE} (
            id BIGSERIAL PRIMARY KEY,
            normalized_text TEXT NOT NULL,
            normalized_location TEXT NOT NULL,
            display_text TEXT NOT NULL,
            display_location TEXT NOT NULL,
            chips TEXT,
            source TEXT NOT NULL,
            role_track TEXT,
            first_requested_at TEXT NOT NULL,
            last_run_at TEXT,
            last_result_at TEXT,
            run_count INTEGER NOT NULL DEFAULT 0,
            provider_last_used TEXT,
            result_count_last_run INTEGER,
            retired_at TEXT,
            CONSTRAINT search_queries_source CHECK ({_SEARCH_SOURCE_CHECK}),
            UNIQUE (normalized_text, normalized_location)
        )
    """)
    # -- what is NOT on that table, and why --------------------------------
    #
    # watcher_count -- see the docstring. It is search_query_signal.
    #
    # created_by / requested_by -- deliberately absent. `search_queries`
    #   carries NO per-Builder identity at all, which is what lets the read
    #   endpoint select from it without a privacy argument. Identity lives in
    #   search_query_watchers and reaches nothing that is rendered.
    #
    # chips is TEXT holding JSON, not JSONB. Every other JSON in this database
    #   is TEXT (jobs.raw_json, job_matches.match_reasons, job_facts.tech_stack)
    #   and nothing queries inside it. One JSONB column would be the same kind
    #   of special case ../webapp/schema_web.py refuses for TIMESTAMPTZ.
    #
    # display_text is FIRST-WRITER-WINS and is never re-attributed. The second
    #   Builder to type "ai ops" sees the first one's spelling. That is a
    #   deliberate trade: re-attributing on every request would make the
    #   displayed spelling change the moment someone new arrived, which is a
    #   recency channel of exactly the kind tranche_five/28 forbids.

    # -- the claim columns, ADDED rather than declared ----------------------
    #
    # search_queries.claimed_at, .claimed_by and .claim_granted_at, in that
    # order of dependence.
    #
    # Per-query dispatch (docs/adr/0007) leases a search_queries row the way
    # api/query_claims.py already leases a job_ingest_state one: claimed_at is
    # the lease, claimed_by is who holds it, and claim_granted_at is what
    # claimed_at was at the moment this service granted it. The third column
    # is not redundant -- any writer that knows only claimed_at can rewrite it
    # under a live claimant, and an owner check reading claimed_by alone would
    # then hand a stale claimant a write. `holds_search_query_claim` in
    # ../api/query_claims.py carries that sequence in full.
    #
    # WHY add_missing_columns AND NOT THREE MORE LINES IN THE CREATE ABOVE.
    # Every already-provisioned database has this table, so a column that
    # exists only inside `CREATE TABLE IF NOT EXISTS` would never reach one --
    # the statement is a no-op the moment the table is there. lib/state.py:59
    # adds claimed_at to the watermark table for exactly this reason, and
    # `ALTER ... ADD COLUMN IF NOT EXISTS` is avoided for the lock argument
    # dbconn.add_missing_columns states.
    #
    # THIS IS NOT THE created_by THE BLOCK ABOVE REFUSES, and the difference is
    # the whole reason it is allowed here. created_by would be permanent
    # attribution of who asked for a query. claimed_by is a transient lease
    # holder -- cleared on release, on success and on expiry -- and it holds a
    # CONTRIBUTOR id (`c_<hex>`, minted in api/), not the app_user_id that
    # identifies a Builder to the webapp. It is also absent from
    # backend/webapp/search.py:73's QUERY_COLUMNS allowlist, so nothing renders
    # it; that allowlist exists precisely so a column added here cannot ship to
    # a client by default, and this is the case it was written for.
    dbconn.add_missing_columns(conn, SEARCH_QUERIES_TABLE, [
        ("claimed_at", "TEXT"),
        ("claimed_by", "TEXT"),
        ("claim_granted_at", "TEXT"),
    ])

    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {SEARCH_WATCHERS_TABLE} (
            query_id BIGINT NOT NULL REFERENCES {SEARCH_QUERIES_TABLE}(id)
                ON DELETE CASCADE,
            app_user_id TEXT NOT NULL,
            profile TEXT NOT NULL,
            created_at TEXT NOT NULL,
            removed_at TEXT,
            PRIMARY KEY (query_id, app_user_id)
        )
    """)
    # app_user_id is BARE TEXT WITH NO FOREIGN KEY to app_users(id), and the
    # reason is the ownership rule pointing the other way for once:
    # webapp/schema_web.py owns app_users, so a real FK here would make the
    # PIPELINE's DDL depend on a table it must not own. That module makes the
    # identical call for builder_job_state.job_id against jobs(id)
    # (schema_web.py:303-309) and the exposure is the same and equally small: a
    # stranded watcher row is invisible, because every read of this table is
    # either scoped to one app_user_id or folded into a count.
    #
    # KEYED (query_id, app_user_id) AND NOT (query_id, profile). Thirty
    # Builders share one profile, so a profile-keyed watcher table can hold at
    # most one row per query per COHORT -- see searchnorm.REGISTER_WATCHER_SQL.
    #
    # cohort_signal (above) is keyed (job_id, cohort_profile) and has no such
    # problem, because job_events carries app_user_id and cohort.py counts
    # DISTINCT on it. This table has no log to fold, so the identity has to be
    # the key.
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {SEARCH_SIGNAL_TABLE} (
            query_id BIGINT NOT NULL REFERENCES {SEARCH_QUERIES_TABLE}(id)
                ON DELETE CASCADE,
            cohort_profile TEXT NOT NULL,
            watcher_bucket TEXT NOT NULL,
            computed_at TEXT NOT NULL,
            CONSTRAINT search_query_signal_bucket CHECK ({_SEARCH_BUCKET_CHECK}),
            PRIMARY KEY (query_id, cohort_profile)
        )
    """)
    # The link between a search and what it surfaced. It exists so the read
    # endpoint can JOIN jobs_app rather than re-run a text search, which is
    # what makes "results route through the full gate" a structural property:
    # jobs_app requires a job_matches row, match.py writes one only for
    # postings that pass relevance.union_sql, so a relister posting a provider
    # returned has no match row and cannot be selected however it got here.
    #
    # ON DELETE CASCADE on BOTH sides. A closed posting is deleted from nothing
    # (closing is a status change) but a re-keyed one is real -- see
    # _ensure_fk_update_cascade -- so ON UPDATE CASCADE is on the jobs side for
    # the reason every other child table has it.
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {SEARCH_RESULTS_TABLE} (
            query_id BIGINT NOT NULL REFERENCES {SEARCH_QUERIES_TABLE}(id)
                ON DELETE CASCADE,
            job_id TEXT NOT NULL REFERENCES jobs(id)
                ON DELETE CASCADE ON UPDATE CASCADE,
            first_seen_at TEXT NOT NULL,
            provider TEXT,
            PRIMARY KEY (query_id, job_id)
        )
    """)
    conn.commit()
    # The scheduler's only question: "which queries are due". Partial on
    # retired_at, because every row it exists to find has retired_at NULL and
    # the retired ones are precisely the rows the scan must never reach.
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_search_queries_due "
                 f"ON {SEARCH_QUERIES_TABLE}(last_run_at NULLS FIRST) "
                 f"WHERE retired_at IS NULL")
    # "What does this Builder watch", asked on every render of the search
    # screen, and "who watches this query", asked once per query by the fold.
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_search_watchers_user "
                 f"ON {SEARCH_WATCHERS_TABLE}(app_user_id) "
                 f"WHERE removed_at IS NULL")
    conn.commit()


#: The one supported read surface for a consumer (an app, a digest, a report).
#:
#: WHY A VIEW AND NOT "JUST QUERY THE JOBS TABLE"
#:     The jobs table is deliberately unfiltered. ingest/ats.py pulls entire company
#:     boards, so roughly two thirds of it is roles this pipeline exists to
#:     ignore -- enterprise sales, tax directors, clinical staff. Querying the
#:     table directly means every consumer re-derives the same four or five
#:     joins and the same status/completeness predicates, and gets them subtly
#:     different. This is that query, written once.
#:
#: WHY NOT NOT NULL CONSTRAINTS INSTEAD
#:     The required-field guarantee cannot be a column constraint, because
#:     ingest/builtin-nyc.py legitimately writes a listing row first and fills
#:     description_text on a later pass (its detail pages are rate-limited, so
#:     the backlog drains over days). A NOT NULL would break that two-phase
#:     write. Enforcing completeness at the read edge keeps both properties:
#:     partial rows may exist, but nothing downstream can see one.
#:
#: ORDERING: match_score first (the whole point of the ranking), posted_at_ts
#: as the tie-break so equal scores read newest-first.
APP_VIEW = "jobs_app"

_APP_VIEW_SQL = f"""
CREATE OR REPLACE VIEW {APP_VIEW} AS
SELECT j.id,
       j.platform,
       j.company_name,
       j.title,
       j.job_url,
       j.description_text,
       j.location_raw,
       j.location_is_nyc,
       j.location_is_remote,
       j.department,
       j.seniority_guess,
       j.posted_at_ts,
       j.first_seen,
       j.last_seen,
       coalesce(j.salary_text, f.comp_currency || ' ' ||
                nullif(concat_ws('-', f.comp_min, f.comp_max), '')) AS salary,
       f.comp_min,
       f.comp_max,
       f.comp_currency,
       f.seniority_level,
       f.years_experience_min,
       f.role_archetype,
       f.tech_stack,
       f.ai_involvement,
       f.remote_policy,
       f.employment_type,
       f.visa_sponsorship,
       f.gap_friendly_language,
       f.summary,
       m.profile,
       m.match_score,
       m.match_reasons,
       s.fit_score,
       s.primary_track,
       s.gap_bridging_angle,
       s.risk_factors,
       s.key_technologies,
       -- LAST, and it must stay last. CREATE OR REPLACE VIEW can only APPEND
       -- columns; inserting this next to f.role_archetype where it reads
       -- naturally is a reorder, which raises InvalidTableDefinition and sends
       -- ensure_app_view down its DROP fallback (below) -- and DROP VIEW takes
       -- every GRANT on jobs_app with it. Nothing in this repo re-grants; the
       -- statement is hand-typed in webapp/README.md. The failure surfaces as
       -- verify_schema() refusing to start the webapp with "no SELECT", on the
       -- next nightly run, pointing nowhere near the commit that caused it.
       f.role_track
FROM {TABLE} j
JOIN {MATCHES_TABLE} m ON m.job_id = j.id
LEFT JOIN {FACTS_TABLE} f ON f.job_id = j.id
LEFT JOIN {SCORES_TABLE} s ON s.job_id = j.id AND s.profile = m.profile
WHERE j.status = '{STATUS_OPEN}'
  AND coalesce(j.company_name, '') <> ''
  AND coalesce(j.title, '') <> ''
  AND coalesce(j.job_url, '') <> ''
  AND coalesce(j.description_text, '') <> ''
"""  # noqa: S608 -- splices TABLE/MATCHES_TABLE/FACTS_TABLE/SCORES_TABLE and the STATUS_OPEN literal -- all module-level constants; a view definition cannot bind %s parameters


def _view_grants(conn, view_name):
    """[(grantee, privilege, is_grantable), ...] currently on view_name.

    Reads pg_class.relacl via aclexplode rather than
    information_schema.role_table_grants: that view is restricted (by the
    SQL standard) to rows where the CONNECTING role is grantor or grantee,
    and in a real deployment the grant to jobs_web may have been issued by
    a separate admin role -- this must see it regardless of who granted it.
    Excludes the connecting role's own privileges: aclexplode reports the
    owner's implicit privileges as explicit rows, and those were never
    taken away by the DROP below, so reissuing them would be a no-op that
    only adds noise.
    """
    return conn.execute(
        """
        SELECT CASE WHEN a.grantee = 0 THEN 'PUBLIC'
                    ELSE a.grantee::regrole::text END,
               a.privilege_type,
               a.is_grantable
        FROM pg_class c
        CROSS JOIN LATERAL aclexplode(c.relacl) AS a
        WHERE c.oid = to_regclass(%s)
          AND a.grantee::regrole::text <> current_user
        """, (view_name,)).fetchall()


def _regrant(conn, view_name, grants):
    """Reissue exactly the grants _view_grants captured -- continuity of an
    existing privilege decision, not a new one. See docs/adr/0004 for why
    this repo never has this function invent one instead."""
    for grantee, privilege, grantable in grants:
        grantee_sql = (sql.SQL("PUBLIC") if grantee == "PUBLIC"
                       else sql.Identifier(grantee))
        stmt = sql.SQL("GRANT {} ON {} TO {}").format(
            sql.SQL(privilege), sql.Identifier(view_name), grantee_sql)
        if grantable:
            stmt = stmt + sql.SQL(" WITH GRANT OPTION")
        conn.execute(stmt)


def ensure_app_view(conn: psycopg.Connection) -> None:
    """Create or refresh jobs_app. Idempotent, and safe to call every run.

    CREATE OR REPLACE VIEW cannot drop or reorder existing columns, so a change
    that removes one needs an explicit DROP first -- deliberately noisy, since
    anything reading the view would break. DROP VIEW takes every GRANT on the
    view with it, so the grants are captured before the DROP and reissued
    after -- not decided, only carried across the DROP that would otherwise
    lose them silently until the next nightly run refuses to serve the webapp.
    """
    try:
        conn.execute(_APP_VIEW_SQL)
        conn.commit()
    except psycopg.errors.InvalidTableDefinition:
        # Column set changed incompatibly; replace it outright.
        conn.rollback()
        grants = _view_grants(conn, APP_VIEW)
        conn.execute(f"DROP VIEW IF EXISTS {APP_VIEW}")
        conn.execute(_APP_VIEW_SQL)
        _regrant(conn, APP_VIEW, grants)
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
    (COHORT_SIGNAL_TABLE, "job_id"),
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

def close_missing(conn: psycopg.Connection, platform: str, token: str,
                   seen_ids: Iterable[str], now: str | None = None) -> int:
    """Close listings that were open but absent from this run's fetch.

    Only valid for sources returning a company's COMPLETE listing set -- the
    ATS boards. SAFETY VALVE: an empty seen_ids would close every open job
    for the company, which is correct only if the fetch is trustworthy, so
    it raises instead. The original relied on the caller remembering.
    """
    from lib.timeparse import utc_now_str
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


def close_stale(conn: psycopg.Connection, platform: str, stale_days: int,
                 now: str | None = None) -> int:
    """Close listings not seen for `stale_days`.

    For sources returning a sampled slice rather than a full listing set,
    where absence from any single fetch means nothing.
    """
    from datetime import timedelta
    from lib.timeparse import utc_now, utc_now_str
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


def prune_old_closed(conn: psycopg.Connection, days: int) -> int:
    from datetime import timedelta
    from lib.timeparse import utc_now
    cutoff = (utc_now() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
    cur = conn.execute(
        "DELETE FROM jobs WHERE status = 'closed' AND closed_at IS NOT NULL "
        "AND closed_at < %s", (cutoff,))
    conn.commit()
    return cur.rowcount
