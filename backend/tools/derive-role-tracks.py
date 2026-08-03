#!/usr/bin/env python3
"""
Derive the `role_track` vocabulary and validate archetype candidates from the corpus.

READ-ONLY. Task 11 asks for two vocabularies and forbids authoring either from
imagination: the archetype superset must be "grounded in what the corpus actually
contains", and the tracks must be clustered out of the postings rather than
decided in a workshop. This script is how that grounding is produced, and it is
built to be RE-RUN after Phase 3 adds sources -- the first vocabulary is
explicitly provisional (11-archetype-superset-role-track.md:56-64), so the tool
that produced it has to outlive it.

    python3 tools/derive-role-tracks.py                  # everything
    python3 tools/derive-role-tracks.py --tracks         # clustering only
    python3 tools/derive-role-tracks.py --archetypes     # candidate probe only
    python3 tools/derive-role-tracks.py --profile pursuit --max-tier 2

TWO POPULATIONS, BECAUSE THE SUPERSET SERVES BOTH
    cohort  the open postings passing `--profile`'s relevance gate at or below
            --max-tier. This is the cohort's opportunity space. Extraction is
            gated on ACTIVE profiles and `pursuit` is inactive, so most of these
            rows have NO job_facts and the analysis must run off title and
            description_text rather than off extracted values.
    other   every job_facts row at the CURRENT facts_version whose
            role_archetype is already 'other'. These are the postings today's
            vocabulary cannot name, and any new value's worth is partly how
            many of them it reclaims. The version filter was missing until
            2026-07-31 and its absence made every reclaim figure this tool
            printed an overstatement -- see load_other().

WHY THE CLUSTERING READS TITLES AND NOT DESCRIPTIONS
    Measured, not assumed. Clustering title+description at any description
    weight recovers EMPLOYERS, not roles: the top terms of the largest clusters
    come out as 'interpretable, steerable, beneficial' (one employer's mission
    page), 'gdp, economy, staggering' (another's), 'harmony, work-life' (a
    third). A job description is mostly employer copy with a little role in it,
    and TF-IDF finds the majority signal. Scored by the fraction of clusters
    spanning >=4 distinct employers -- an employer-specific cluster is an
    artifact, a role family is not:

        title only        36 clusters n>=5, 34 span >=4 employers, 614 postings
        title x4 + desc   56 clusters n>=5, 17 span >=4 employers, 160 postings
        description-heavy 45 clusters n>=5, 16 span >=4 employers, 188 postings

    Those three were swept with the vocabulary floor at 3 employers and the
    cluster-spread criterion held at 4. This tool couples the two into
    --min-employers, so they are NOT what a default run prints: at the
    shipped default of 4 the title-only arm reports 41 clusters, 25 at n>=5,
    24 spanning >=4 employers, 620 representatives. `--min-employers 3`
    reproduces the sweep's 46 / 36. The comparison is recorded because it is
    why descriptions are excluded at all; the default is tighter on purpose.

    So descriptions are dropped from the vector entirely. `employers=` is
    printed on every cluster and every candidate for the same reason: it is the
    statistic that distinguishes a role family from one company's hiring spree,
    and it is the one this analysis was wrong about twice before it was right.

THE NEAR-DUPLICATE TRAP, AND WHY THE OBVIOUS FIX IS WRONG
    One employer posting one role many times is not a cluster. The corpus
    contains a 54-posting block from a single employer -- one telehealth
    clinician role, duplicated per US state -- which is large enough to
    manufacture a whole track on its own.

    The fix is (company, normalized title) with geography and seniority stripped,
    NOT a description fingerprint. Fingerprinting the head of the description
    collapses every posting from the same employer regardless of role, because
    that is exactly where the boilerplate lives: it merged one employer's 40
    postings spanning 25 distinct titles -- Applied Legal Researcher, IT
    Operations Analyst, Strategy Associate -- into a single "duplicate" block.
    Nor does hashing the FULL description work: that employer's 54 postings are
    all byte-distinct, because the state name appears in the body too.

READING THE OUTPUT
    clusters      the tail is not trustworthy. Titles are ~5 tokens, so below
                  roughly n=8 clusters form on incidental shared words -- a
                  Site Reliability Engineer and a Pharmacy Technician sharing
                  'technician, site'. Name the head, ignore the tail.
    candidates    counts are UPPER BOUNDS. The patterns overlap by design and
                  role_archetype is single-valued, so a posting matching three
                  candidates is counted by all three. Read `dedup` and
                  `employers`, not `raw`.
"""

import os
import re
import sys
import math
import argparse
import collections

# ingest/ and tools/ sit one level below the pipeline modules they import
# (schema, relevance, profiles, ...). Python puts THIS file's directory on
# sys.path, not its parent, so the parent is added by hand.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import schema     # noqa: E402
import relevance  # noqa: E402
import profiles   # noqa: E402
from lib import dbconn, envfile  # noqa: E402

# Read-only tool, so it loads the pipeline's own .env rather than requiring the
# caller to export DATABASE_URL first. Same contract as relevance-report.py:69.
envfile.load(os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))


# --------------------------------------------------------------------------
# text normalisation
# --------------------------------------------------------------------------

#: Stripped from titles before near-duplicate collapsing. The geography terms
#: are what make one role posted in forty states look like forty roles; the
#: seniority terms are what make one role at three levels look like three.
#: Deliberately US-state-shaped because that is the duplication this corpus
#: actually contains -- see the module docstring.
_TITLE_NOISE = set("""
alabama alaska arizona arkansas california colorado connecticut delaware florida
georgia hawaii idaho illinois indiana iowa kansas kentucky louisiana maine
maryland massachusetts michigan minnesota mississippi missouri montana nebraska
nevada hampshire jersey mexico york carolina dakota ohio oklahoma oregon
pennsylvania rhode island tennessee texas utah vermont virginia washington
wisconsin wyoming remote telehealth onsite hybrid
senior sr junior jr lead staff principal i ii iii iv v
""".split())

#: Function words plus job-posting furniture. The employer-specific boilerplate
#: is NOT listed here -- it is removed statistically by the cross-employer
#: document-frequency floor, which does not need to be told any company's name.
_STOP = set("""
a an the and or of to in for with on at by from as is are be was were this that
these those it its we you your our their they he she his her them us will can
may must should would could not no if then than so such other more most any all
each both few some own same very just also about into over under out up down off
again further once here there when where why how what which who whom
job role position work working works team teams company companies employer
employees employee opportunity opportunities candidate candidates applicant
applicants apply application applications hiring hire hired experience
experienced years year required require requires requirements requirement
preferred prefer skills skill ability abilities strong excellent good great new
please including include includes included etc per within across while during
equal employment status veteran disability race color religion sex national
origin gender identity sexual orientation age protected law regardless basis
without regard discrimination harassment benefits benefit health dental vision
insurance paid time off pto salary range compensation base bonus equity stock
offer offers total rewards package annual usd llc inc ltd corp
join mission world people culture passionate looking help make building built
build every one
""".split())

_WORD = re.compile(r"[a-z][a-z0-9+#.\-]{1,}")


def words(text):
    """Content tokens, lowercased, stopwords and one-character terms removed."""
    return [w for w in _WORD.findall((text or "").lower())
            if w not in _STOP and len(w) > 2]


def normalized_title(title):
    """A title reduced to its role, for near-duplicate collapsing.

    Parenthesised asides, punctuation, geography and seniority all go. What is
    left is what two postings must share to be called the same posting.
    """
    t = (title or "").lower().replace("–", " ").replace("—", " ")
    t = re.sub(r"\(.*?\)", " ", t)
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    return " ".join(w for w in t.split() if w not in _TITLE_NOISE)


#: dbconn sets no row factory, so queries come back as plain tuples. Every
#: posting is wrapped in this before anything else touches it -- positional
#: indexing across four report functions is how a column swap becomes a silent
#: wrong answer rather than an error.
Posting = collections.namedtuple(
    "Posting", "id title company_name platform description_text")


def _company(row):
    return (row.company_name or "").lower().strip()


# --------------------------------------------------------------------------
# corpus
# --------------------------------------------------------------------------

def load_cohort(conn, profile, max_tier):
    """Open postings passing `profile`'s own relevance gate at <= max_tier.

    for_profile, not load(): a profile carrying its own relevance_json is gated
    by that and not by the shared file (relevance.py:100), and reporting the
    shared file for it would describe a filter that is not running.
    """
    row = profiles.load_one(conn, profile)
    if row is None:
        sys.exit(f"no such profile: {profile!r}")
    cfg = relevance.for_profile(row)
    expr, params = relevance.tier_sql(cfg)
    params["status"] = schema.STATUS_OPEN
    params["cap"] = max_tier
    rows = conn.execute(
        f"""SELECT j.id, j.title, j.company_name, j.platform, j.description_text
            FROM {schema.TABLE} j
            WHERE j.status = %(status)s AND ({expr}) <= %(cap)s""",  # noqa: S608 -- splices schema.TABLE (constant) and expr from relevance's SQL compiler, not user input
        params,
    ).fetchall()
    return [Posting(*r) for r in rows], row


def load_other(conn, facts_version):
    """Every job_facts row the CURRENT vocabulary could only call 'other'.

    THE facts_version FILTER IS THE WHOLE CORRECTNESS OF THIS FUNCTION, and it
    was missing until 2026-07-31. Without it the query returns rows extracted
    under EVERY vocabulary this project has ever had, and the reclaim counts
    below are then answers to a question nobody asked.

    Measured on the live table the day the filter was added:

        facts_version 2   402 'other' of 5,024   (the TWELVE-value vocabulary)
        facts_version 3   294 'other' of   940   (the twenty-six)

    So 58% of the unfiltered population never had access to the fourteen
    values this tool exists to evaluate. `hardware_embedded` is the clearest
    case: 54 raw 'other' rows match its title probe unfiltered and only THREE
    of them are v3. The other ~50 are not evidence that a value is missing --
    they are rows that predate the value and would be reclaimed by
    re-extraction alone. Reading them as reclaim credits a new value with work
    a re-run already does.

    Pass an explicit version to ask a historical question on purpose; the
    default is schema.FACTS_VERSION, so the honest question is the cheap one.
    """
    sql = """SELECT j.id, j.title, j.company_name, j.platform, j.description_text
               FROM job_facts f JOIN jobs j ON j.id = f.job_id
              WHERE f.role_archetype = 'other'"""
    params = ()
    if facts_version is not None:
        sql += " AND f.facts_version = %s"
        params = (facts_version,)
    return [Posting(*r) for r in conn.execute(sql, params).fetchall()]


def collapse_duplicates(rows):
    """Group by (company, normalized title); return representatives and blocks.

    See the module docstring for why this key and not a description
    fingerprint. Returns (representatives, blocks) where blocks are the
    multi-posting groups, largest first.
    """
    groups = collections.defaultdict(list)
    for r in rows:
        groups[(_company(r), normalized_title(r.title))].append(r)
    reps = [g[0] for g in groups.values()]
    blocks = sorted((g for g in groups.values() if len(g) > 1),
                    key=len, reverse=True)
    return reps, blocks


# --------------------------------------------------------------------------
# tf-idf over titles
# --------------------------------------------------------------------------

def build_vectors(reps, min_df, min_employers, max_df_frac):
    """L2-normalised TF-IDF vectors over titles, boilerplate removed.

    `min_employers` is the load-bearing parameter. A term confined to fewer
    than this many distinct employers is that employer's vocabulary rather than
    the language of a role, and keeping it is what makes the clustering rebuild
    the company list. It is applied even though this vectorises titles only,
    because titles carry product names too ('Lakebase', 'Zo') and those cluster
    just as hard as mission statements do.
    """
    docs = [collections.Counter(words(r.title)) for r in reps]
    n = len(docs)
    df = collections.Counter()
    employers = collections.defaultdict(set)
    for doc, rep in zip(docs, reps):
        for w in doc:
            df[w] += 1
            employers[w].add(_company(rep))

    vocab, dropped = {}, []
    for w, d in df.items():
        if d < min_df or d > max_df_frac * n:
            continue
        if len(employers[w]) < min_employers:
            if d >= min_df * 2:
                dropped.append(w)
            continue
        vocab[w] = math.log(n / d)

    vectors = []
    for doc in docs:
        v = {w: (1 + math.log(c)) * vocab[w] for w, c in doc.items() if w in vocab}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        vectors.append({w: x / norm for w, x in v.items()})
    return docs, vectors, vocab, sorted(dropped, key=lambda w: -df[w])


def cosine_pairs(vectors, max_postings_per_term=250):
    """Sparse all-pairs cosine, via an inverted index.

    Only pairs sharing a term can be non-zero, so the inverted index does the
    work an O(n^2) dense pass would. Terms carried by more postings than
    `max_postings_per_term` are skipped: they contribute a near-uniform smear
    to every pair while costing a quadratic number of updates.
    """
    inverted = collections.defaultdict(list)
    for i, v in enumerate(vectors):
        for w, x in v.items():
            inverted[w].append((i, x))
    sim = [collections.defaultdict(float) for _ in vectors]
    for postings in inverted.values():
        if len(postings) > max_postings_per_term:
            continue
        for a in range(len(postings)):
            ia, xa = postings[a]
            for b in range(a + 1, len(postings)):
                ib, xb = postings[b]
                sim[ia][ib] += xa * xb
                sim[ib][ia] += xa * xb
    return sim


def agglomerate(sim, threshold):
    """Average-link agglomerative clustering, stopping at `threshold`.

    Average link rather than single link because single link chains: one
    posting sharing a word with two unrelated groups welds them together, and
    at n~650 that produces one giant cluster and a lot of singletons. Naive
    "rescan for the best pair" is O(n^2) per merge, which is fine here and
    obviously correct; at this corpus size the whole loop is seconds. If a
    later corpus makes it slow, the fix is nearest-neighbour chains, not a
    dependency -- backend/requirements.txt keeps psycopg as the only one.
    """
    members = {i: [i] for i in range(len(sim))}
    live = {i: dict(row) for i, row in enumerate(sim)}
    while True:
        best, bi, bj = threshold, None, None
        for i, row in live.items():
            for j, s in row.items():
                if s > best:
                    best, bi, bj = s, i, j
        if bi is None:
            return sorted(members.values(), key=len, reverse=True)
        ni, nj = len(members[bi]), len(members[bj])
        members[bi] += members[bj]
        del members[bj]
        merged = {}
        for k in set(live[bi]) | set(live[bj]):
            if k in (bi, bj) or k not in members:
                continue
            s = (live[bi].get(k, 0.0) * ni + live[bj].get(k, 0.0) * nj) / (ni + nj)
            merged[k] = s
            live[k].pop(bj, None)
            live[k][bi] = s
        live[bi] = merged
        del live[bj]
        for row in live.values():
            row.pop(bj, None)


def discriminating_terms(cluster, docs, vocab, global_df, n_docs, limit=10):
    """Terms over-represented in a cluster relative to the whole corpus.

    Frequency alone returns 'engineer' for every cluster. The lift condition
    (in-cluster rate at least twice the corpus rate) is what makes the printed
    terms usable as a name for the group.
    """
    in_df = collections.Counter()
    for i in cluster:
        for w in set(docs[i]) & set(vocab):
            in_df[w] += 1
    scored = {}
    for w, c in in_df.items():
        if c < 2:
            continue
        p_in, p_all = c / len(cluster), global_df[w] / n_docs
        if p_in > 2 * p_all:
            scored[w] = (p_in - p_all) * math.log(1 + c)
    return sorted(scored, key=scored.get, reverse=True)[:limit]


# --------------------------------------------------------------------------
# archetype candidates
# --------------------------------------------------------------------------

#: Title patterns for the values task 11 proposes, plus the ones the `other`
#: population turns out to demand. These are PROBES, not the extractor's
#: definition of the value -- the extractor reads the whole posting and picks
#: one value; this asks the cheaper question "is there a mass of postings here
#: at all". A candidate that cannot find its own postings by title is not
#: thereby refuted, but a candidate with no title mass AND no reclaim from
#: 'other' has nothing to recommend it.
#:
#: Grouped so the report can total the two families separately: the superset
#: serves the cohort (ops-shaped work) and the existing software profile
#: (the tech roles today's twelve values happen to miss) at once.
#:
#: The third element is the RECOMMENDATION, so that "which 14 values" is an
#: output of this tool rather than a claim in a document that has drifted from
#: it. "drop" is not a deletion -- the candidate is still probed and still
#: printed, because the evidence AGAINST a value is the part a reader cannot
#: reconstruct later. Rationale for each: docs/role-track-derivation.md.
CANDIDATES = {
    # -- the seven named in 11-archetype-superset-role-track.md:28-30 --
    "ai_operations": (
        "ops", "recommend",
        r"\b(ai|genai|generative ai|llm|agentic|automation)\b.{0,24}"
        r"\b(operations|ops|enablement|deployment|adoption|program)\b"
        r"|\b(operations|ops|enablement)\b.{0,20}\b(ai|genai|llm)\b"),
    "automation_specialist": (
        "ops", "drop",
        r"\b(automation|rpa|workflow|zapier|no.?code|low.?code|"
        r"process improvement)\b"),
    "implementation_analyst": (
        "ops", "recommend",
        r"\b(implementation|onboarding|deployment|solutions consultant|"
        r"professional services|technical account)\b"),
    "support_ops": (
        "ops", "recommend",
        r"\b(support|helpdesk|help desk|service desk|technical services|"
        r"customer success|concierge)\b"),
    "marketing_ops": (
        "ops", "recommend",
        r"\b(marketing|brand|social media|content|seo|campaign|growth|"
        r"communications|creative)\b"),
    "data_coordination": (
        "ops", "drop",
        r"\b(data (entry|coordinat|annotat|steward|quality|govern|manage)|"
        r"annotation|labeling|labelling|curation)\b"),
    "admin_ops": (
        "ops", "recommend",
        r"\b(administrative|admin|executive assistant|coordinator|office|"
        r"receptionist|clerk|secretar|scheduling)\b"),
    # -- tech values the 'other' population demands; see the doc --
    "hardware_embedded": (
        "tech", "recommend",
        r"\b(hardware|firmware|embedded|mechanical|electrical|silicon|asic|"
        r"fpga|thermal|mechatronic|vehicle|robot)\b"),
    "infrastructure_compute": (
        "tech", "recommend",
        r"\b(infrastructure|compute|data cent|capacity|network engineer|"
        r"site reliability|platform engineer)\b"),
    "qa_test": (
        "tech", "recommend",
        r"\b(qa|quality assurance|test engineer|sdet|quality engineer|"
        r"test automation|validation engineer)\b"),
    "engineering_management": (
        "tech", "recommend",
        r"\b(engineering manager|manager,? engineering|director,? engineering|"
        r"engineering director|head of engineering|manager i+,? engineering|"
        r"vp engineering)\b"),
    "mobile": (
        "tech", "recommend",
        r"\b(android|ios|mobile|react native|flutter|swift|kotlin)\b"),
    "program_management": (
        "tech", "recommend",
        r"\b(program manager|technical program|tpm|project manager|"
        r"delivery manager|program management)\b"),
    "business_systems": (
        "tech", "recommend",
        r"\b(salesforce|netsuite|workday|business systems|erp|crm|cpq|"
        r"systems analyst|revenue systems)\b"),
    "it_internal": (
        "tech", "recommend",
        r"\b(it |it$|helpdesk|information technology|endpoint|sysadmin|"
        r"system administrator|corporate engineering|workplace technology)\b"),
    "developer_relations": (
        "tech", "recommend",
        r"\b(developer advocate|developer relations|devrel|developer experience|"
        r"technical evangelist|community engineer|technical writer|"
        r"documentation)\b"),
    # -- COMMERCIAL. Added 2026-07-31, probed and NOT adopted; the evidence is
    #    in docs/role-track-derivation.md, "What the first labels showed".
    #
    #    These exist because ARCHETYPE has no commercial value at all -- its own
    #    first line admits it, "The original twelve. All software engineering."
    #    -- while ROLE_TRACK already has `revenue_operations`. The two
    #    vocabularies are supposed to be the same space at two grains, and on
    #    commercial work they are not: a Deal Desk Analyst gets a coherent
    #    track and can only be `other` at the finer grain. That asymmetry is a
    #    structural argument, not a count, and it is why revenue_commercial is
    #    the one recommendation rather than one of five.
    #
    #    clinical_care is kept as a DROP because it is this file's own
    #    employer-spread rule doing its job: 56 raw 'other' matches collapse to
    #    9 dedup at ONE employer, a telehealth hiring spree posted per US
    #    state. Read `emp` first, exactly as the header says. --
    "revenue_commercial": (
        "commercial", "recommend",
        r"\b(sales|deal desk|renewals?|account executive|account manager|"
        r"business development|sales development|partner|partnerships|"
        r"revenue|gtm|go.to.market|quota|enablement|commercial|"
        r"development representative|sdr|bdr)\b"),
    "finance_accounting": (
        "commercial", "drop",
        r"\b(fp&a|financial analyst|finance|accounting|accountant|controller|"
        r"treasury|order operations|billing|equity analyst|audit)\b"),
    "people_recruiting": (
        "commercial", "drop",
        r"\b(recruit|talent|candidate experience|people operations|people ops|"
        r"human resources|hris|compensation|onboarding specialist)\b"),
    "strategy_bizops": (
        "commercial", "drop",
        r"\b(strategy|strategic|chief of staff|competitive intelligence|"
        r"business operations|bizops|corporate development)\b"),
    "clinical_care": (
        "commercial", "drop",
        r"\b(clinical|psychologist|psychiatr|telehealth|therapist|clinician|"
        r"nurse|registered nurse|\brn\b|physician|patient care|social worker)\b"),
}


def probe(rows, pattern):
    rx = re.compile(pattern, re.I)
    return [r for r in rows if rx.search(" " + (r.title or "") + " ")]


# --------------------------------------------------------------------------
# reports
# --------------------------------------------------------------------------

def report_corpus(cohort, profile_row, blocks, reps, args):
    print("=" * 74)
    print("CORPUS")
    print("=" * 74)
    print(f"  profile {args.profile!r}, relevance tier <= {args.max_tier}, status open")
    if profile_row is not None and not profile_row.active:
        print("  NOTE: this profile is INACTIVE. extract.py and match.py do not "
              "see it\n        (profiles.load_active), so most of these rows have "
              "no job_facts row and\n        the analysis runs off title and "
              "description_text, not off facts.")
    print(f"  postings           {len(cohort)}")
    print(f"  distinct employers {len({_company(r) for r in cohort})}")

    print(f"\n{'-' * 74}\nNEAR-DUPLICATE BLOCKS  (company, normalized title)\n{'-' * 74}")
    print("  One employer posting one role many times is not a cluster. These are")
    print("  collapsed to one representative each BEFORE clustering.\n")
    collapsed = len(cohort) - len(reps)
    for b in blocks[:args.examples]:
        print(f"  {len(b):>4}x  {(b[0].company_name or '')[:24]:<26} "
              f"{(b[0].title or '')[:40]}")
    if len(blocks) > args.examples:
        print(f"  ... and {len(blocks) - args.examples} smaller blocks")
    print(f"\n  {len(blocks)} blocks; {collapsed} postings collapsed away "
          f"({100 * collapsed / max(len(cohort), 1):.1f}% of the corpus)")
    print(f"  {len(reps)} representatives go into the clustering")


def report_clusters(reps, docs, vocab, dropped, clusters, args):
    n = len(docs)
    global_df = collections.Counter()
    for doc in docs:
        for w in doc:
            global_df[w] += 1

    print(f"\n{'=' * 74}\nROLE-TRACK CLUSTERS\n{'=' * 74}")
    print(f"  vocabulary {len(vocab)} terms, titles only "
          f"(see the module docstring for why descriptions are excluded)")
    if dropped:
        print(f"  {len(dropped)} terms dropped as employer-specific "
              f"(< {args.min_employers} employers):")
        print(f"    {', '.join(dropped[:14])}")

    big = [c for c in clusters if len(c) >= args.min_cluster]
    spread = [c for c in big
              if len({_company(reps[i]) for i in c}) >= args.min_employers]
    print(f"\n  {len(clusters)} clusters, {len(big)} with n >= {args.min_cluster},")
    print(f"  {len(spread)} of those span >= {args.min_employers} employers "
          f"and cover {sum(len(c) for c in spread)} representatives.")
    print("\n  employers= is the quality statistic. A cluster confined to one or")
    print("  two employers is that employer's hiring, not a role family; it is")
    print("  flagged rather than dropped so the reader can see it was considered.")

    for ci, cluster in enumerate(big):
        n_emp = len({_company(reps[i]) for i in cluster})
        flag = "" if n_emp >= args.min_employers else "   <-- EMPLOYER ARTIFACT"
        terms = discriminating_terms(cluster, docs, vocab, global_df, n)
        print(f"\n  --- c{ci}  n={len(cluster)}  employers={n_emp}{flag}")
        print(f"      {', '.join(terms)}")
        for i in cluster[:args.examples]:
            print(f"        {(reps[i].title or '')[:56]:<58} "
                  f"{(reps[i].company_name or '')[:18]}")


def report_archetypes(cohort, other, args):
    print(f"\n{'=' * 74}\nARCHETYPE CANDIDATES\n{'=' * 74}")
    print(f"  cohort n={len(cohort)}   other n={len(other)}")
    print("  Counts are UPPER BOUNDS: the patterns overlap and role_archetype is")
    print("  single-valued. `dedup` collapses near-duplicate blocks; `emp` counts")
    print("  distinct employers. A candidate whose mass sits at one employer is")
    print("  that employer's hiring spree, not a role family -- read emp first.\n")
    header = (f"  {'candidate':<24} | {'cohort':^22} | {'other':^22}")
    print(header)
    print(f"  {'':<24} | {'raw':>6}{'dedup':>8}{'emp':>7} | "
          f"{'raw':>6}{'dedup':>8}{'emp':>7}")
    print("  " + "-" * (len(header) - 2))

    for family in _families():
        print(f"  -- {family} --")
        for name, (fam, status, pattern) in CANDIDATES.items():
            if fam != family:
                continue
            c, o = probe(cohort, pattern), probe(other, pattern)
            c_reps, _ = collapse_duplicates(c)
            o_reps, _ = collapse_duplicates(o)
            print(f"  {name:<24} | {len(c):>6}{len(c_reps):>8}"
                  f"{len({_company(r) for r in c}):>7} | "
                  f"{len(o):>6}{len(o_reps):>8}"
                  f"{len({_company(r) for r in o}):>7}")

    for name, (_fam, status, pattern) in CANDIDATES.items():
        c, o = probe(cohort, pattern), probe(other, pattern)
        print(f"\n  === {name}")
        for label, rows in (("cohort", c), ("other ", o)):
            reps_, _ = collapse_duplicates(rows)
            counts = collections.Counter(
                (r.company_name or "?") for r in rows).most_common(3)
            print(f"    {label} n={len(rows):<4} top employers: "
                  f"{', '.join(f'{k} x{v}' for k, v in counts) or '-'}")
            for r in reps_[:args.examples]:
                print(f"       {(r.title or '')[:60]:<62} "
                      f"{(r.company_name or '')[:16]}")


def _union(rows, names):
    """Distinct postings matched by ANY of `names`.

    A union, not a sum. The probe patterns overlap heavily -- a Data Center
    Electrical Engineer matches hardware_embedded and infrastructure_compute
    both -- and role_archetype is single-valued, so adding the per-candidate
    column would double-count exactly the postings that are hardest to
    classify. This is the number that answers "how much of `other` does the
    superset actually reclaim".
    """
    hit = set()
    for name in names:
        rx = re.compile(CANDIDATES[name][2], re.I)
        hit |= {r.id for r in rows if rx.search(" " + (r.title or "") + " ")}
    return hit


def _families():
    """Family order, taken from CANDIDATES rather than written out again.

    It was written out again -- `("ops", "tech")`, in two places -- and a
    third family added in 2026-07-31 was probed, counted, and then silently
    not printed, because neither loop knew about it. A hardcoded list of the
    things a dict contains is a second definition of the dict.
    """
    seen = []
    for fam, _st, _p in CANDIDATES.values():
        if fam not in seen:
            seen.append(fam)
    return seen


def _names(family=None, status=None):
    return [n for n, (fam, st, _p) in CANDIDATES.items()
            if (family is None or fam == family)
            and (status is None or st == status)]


def report_total_effect(cohort, other, args):
    """The figures docs/role-track-derivation.md quotes as its headline.

    Printed here because a number that lives only in a document cannot be
    checked after the corpus moves, and this tool exists to be re-run after
    Phase 3. Task 16 in this run reported success over a literal placeholder;
    the counter to that is making the document's claims be this program's
    output.
    """
    print(f"\n{'=' * 74}\nTOTAL EFFECT\n{'=' * 74}")

    rec, dropped = _names(status="recommend"), _names(status="drop")
    print(f"  RECOMMENDED ({len(rec)}):")
    for family in _families():
        names = _names(family=family, status="recommend")
        print(f"    {family:<5} {', '.join(names)}")
    print(f"  DROPPED ({len(dropped)}): {', '.join(dropped)}")
    print("    Still probed and still printed above -- the evidence AGAINST a")
    print("    value is the part a later reader cannot reconstruct.")

    print(f"\n  {'-' * 70}")
    print("  DISTINCT-ROW UNION RECLAIM.  These are unions, NOT column sums:")
    print("  the patterns overlap and role_archetype is single-valued, so the")
    print("  per-candidate table above double-counts. Expect these to be")
    print("  SMALLER than that table's columns added up.\n")
    print(f"  {'set':<34} {'other/' + str(len(other)):>14} "
          f"{'cohort/' + str(len(cohort)):>15}")
    print("  " + "-" * 66)
    # Per-family rows are derived rather than listed, for the same reason
    # _families() exists: a family added to CANDIDATES and left out of a
    # hardcoded list here is a candidate that is probed and never totalled.
    rows = [(f"{family}, recommended", _names(family, "recommend"))
            for family in _families()]
    rows.insert(1, ("ops, all proposed by task 11", _names("ops")))
    rows += [
        ("ALL RECOMMENDED", rec),
        ("dropped candidates only", dropped),
    ]
    for label, names in rows:
        o, c = _union(other, names), _union(cohort, names)
        print(f"  {label:<34} {len(o):>6} ({100 * len(o) / max(len(other), 1):>4.1f}%) "
              f"{len(c):>6} ({100 * len(c) / max(len(cohort), 1):>4.1f}%)")
    residual = len(other) - len(_union(other, rec))
    added = len(_union(other, rec + dropped)) - len(_union(other, rec))
    print(f"\n  residual `other` after all recommended values: {residual}")
    print(f"  rows the {len(dropped)} dropped candidates would additionally "
          f"reclaim: {added}")

    print(f"\n  {'-' * 70}")
    print("  `other` TITLE TOKEN FREQUENCY")
    print("  Tokenizer: words() -- _WORD at derive-role-tracks.py:139, lowercased,")
    print("  _STOP words and tokens of 2 characters or fewer removed. Occurrences,")
    print("  not postings: a title naming a token twice counts twice.")
    freq = collections.Counter()
    for r in other:
        for w in words(r.title):
            freq[w] += 1
    for chunk in range(0, 24, 8):
        print("    " + ", ".join(
            f"{w} {n}" for w, n in freq.most_common(24)[chunk:chunk + 8]))

    # The length rule costs this corpus its most important token. Reported
    # rather than quietly fixed: raising the floor would change the clustering
    # vocabulary too, and that is a separate decision from reporting a count.
    short = collections.Counter()
    for r in other:
        for w in _WORD.findall((r.title or "").lower()):
            if len(w) <= 2 and w not in _STOP:
                short[w] += 1
    print("  Excluded by the >2-character rule in words(), counted separately"
          " because\n  'ai' is this project's whole subject:")
    print("    " + ", ".join(f"{w} {n}" for w, n in short.most_common(6)))


def main():
    p = argparse.ArgumentParser(
        description="Derive role_track clusters and validate archetype "
                    "candidates against the corpus (read-only).")
    p.add_argument("--profile", default="pursuit",
                   help="profile whose relevance gate selects the cohort corpus")
    p.add_argument("--max-tier", type=int, default=2,
                   help="highest relevance tier admitted to the cohort corpus")
    p.add_argument("--threshold", type=float, default=0.10,
                   help="average-link cosine floor; merging stops below it")
    p.add_argument("--min-cluster", type=int, default=5,
                   help="smallest cluster reported")
    p.add_argument("--min-employers", type=int, default=4,
                   help="distinct employers a term must span to enter the "
                        "vocabulary, and a cluster to be trusted")
    p.add_argument("--min-df", type=int, default=3,
                   help="postings a term must appear in to enter the vocabulary")
    p.add_argument("--max-df-frac", type=float, default=0.40,
                   help="drop terms appearing in more than this fraction")
    p.add_argument("--examples", type=int, default=6,
                   help="example titles printed per cluster and per candidate")
    p.add_argument("--tracks", action="store_true", help="clustering only")
    p.add_argument("--archetypes", action="store_true", help="candidate probe only")
    p.add_argument("--facts-version", type=int, default=schema.FACTS_VERSION,
                   help="facts_version of the 'other' population probed. "
                        "Defaults to the current one, because a row extracted "
                        "under an older vocabulary is not evidence that a "
                        "value is missing. Pass 0 for every version.")
    args = p.parse_args()
    facts_version = args.facts_version or None

    do_tracks = args.tracks or not args.archetypes
    do_arch = args.archetypes or not args.tracks

    conn = dbconn.connect_or_exit("derive-role-tracks", schema=schema.SCHEMA)
    cohort, profile_row = load_cohort(conn, args.profile, args.max_tier)
    other = load_other(conn, facts_version)
    reps, blocks = collapse_duplicates(cohort)
    print(f"\n  'other' population: facts_version"
          f" {facts_version if facts_version else 'ALL (historical)'},"
          f" {len(other)} rows")

    report_corpus(cohort, profile_row, blocks, reps, args)
    if do_tracks:
        docs, vectors, vocab, dropped = build_vectors(
            reps, args.min_df, args.min_employers, args.max_df_frac)
        clusters = agglomerate(cosine_pairs(vectors), args.threshold)
        report_clusters(reps, docs, vocab, dropped, clusters, args)
    if do_arch:
        report_archetypes(cohort, other, args)
        report_total_effect(cohort, other, args)
    conn.close()


if __name__ == "__main__":
    main()
