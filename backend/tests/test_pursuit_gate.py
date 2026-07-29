"""Unit tests for the `pursuit` cohort relevance gate.

Run:  python3 tests/test_pursuit_gate.py

WHY THIS FILE EXISTS, AND WHY IT DID NOT UNTIL 2026-07-29
    The suite was at 1030 tests and NOT ONE of them asserted anything about
    this gate's vocabulary. Nothing read AI_VOCAB, nothing read the entry-level
    group, nothing read the pursuit title_exclude. That is precisely how a
    defect costing 51.7% of gate recall sat green for a month: the gate is
    data, the tests were about code, and the two never met.

    The defect: the gate is CONJUNCTIVE, needing one AI term and one
    entry-level term in the SAME field (relevance.py:216-226). Task 10 built a
    description-first gate and handed it a TITLE vocabulary -- associate,
    coordinator, assistant, specialist, analyst. Descriptions do not restate
    their own title's seniority noun, so on the description path the AI half
    matched and the entry half did not. Measured on the 55-posting mock
    corpus: 15 of 29 intended-good postings rejected, 14 of them here.

    TestTheDescriptionGateAdmitsTheRolesItWasBuiltFor is the test that would
    have caught it, and it fails against the pre-2026-07-29 gate.

DIALECT, AND THE ONE THING THESE TESTS CANNOT DO IN PYTHON
    The patterns are POSTGRES regexes. Postgres spells the word boundary \\y;
    Python spells it \\b, and in Postgres \\b means BACKSPACE -- which is the
    landmine CLAUDE.md leads with, because a \\b pattern matches nothing and
    silently demotes everything it was meant to catch.

    So the pure-Python classes here translate \\y -> \\b to test the SEMANTICS,
    and TestGateAgainstRealPostgres puts rows through the actual tier_sql to
    test the DIALECT. Neither substitutes for the other: the translation would
    happily pass a pattern Postgres rejects, and the DB class is skipped on a
    machine with no Postgres.
"""

import json
import importlib.util
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import profiles  # noqa: E402
import relevance  # noqa: E402
from evals import mock_corpus, scratchdb  # noqa: E402
from lib import dbconn, envfile  # noqa: E402

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GATE_FILE = os.path.join(_BACKEND, "config", "pursuit-relevance.json")

#: The pipeline's own .env, as tests/test_extract.py:48-52 does it. Tests must
#: not depend on the caller having exported anything.
envfile.load(os.path.join(_BACKEND, ".env"))

requires_db = unittest.skipUnless(
    scratchdb.available(),
    "no scratch database: set DATABASE_URL (or JOBS_SCRATCH_DATABASE_URL)")


def gate():
    with open(GATE_FILE) as f:
        return json.load(f)


def as_python(pattern):
    """A Postgres pattern as the equivalent Python one.

    Only \\y differs among the constructs these lists use. Asserting that is
    the point of TestRegexDialect: if a pattern ever needs more translation
    than this, that test fails first and this helper does not silently lie.
    """
    return pattern.replace("\\y", "\\b")


def matches_group(group, text):
    """True when any pattern in one include group matches, as Postgres ~* would."""
    return any(re.search(as_python(p), text, re.I) for p in group)


class TestGateShapeInvariants(unittest.TestCase):
    """The properties that make the 2026-07-29 split safe by construction
    rather than by measurement. Each one is cheap and each one, if it broke,
    would break silently."""

    def setUp(self):
        self.cfg = gate()

    def test_the_two_ai_groups_are_identical(self):
        """Both include lists must select for the same AI vocabulary.

        This assertion could not fail before the gate moved to JSON: it was one
        Python list referenced twice, so the two 'copies' were the same object.
        Serialising to a file is what turned an identity into two literals that
        can drift, so the move is what gives this test teeth -- not the reverse.
        """
        self.assertEqual(self.cfg["title_include"][0],
                         self.cfg["description_include"][0])

    def test_the_description_entry_group_is_a_strict_superset(self):
        """The whole safety argument for the split. The title group is
        unchanged, so the title path cannot lose a row; the description group
        contains it, so the description path cannot lose one either. Every
        added term can only admit."""
        title = self.cfg["title_include"][1]
        description = self.cfg["description_include"][1]
        self.assertEqual(description[:len(title)], title,
                         "the description group must OPEN with the title group, "
                         "byte for byte, so the superset is readable as well as true")
        self.assertTrue(set(title) < set(description))

    def test_the_title_path_is_byte_identical(self):
        """Pinned, not derived. relevance._alternation joins the group with a
        bare | (relevance.py:120), so this string is exactly what Postgres
        compares titles against -- and a change to it is a change to which
        postings the pipeline extracts. That should require someone to look at
        this line and decide, the same argument test_relevance.py:110-115 makes
        for the shared config's SQL."""
        _, params = relevance.tier_sql(relevance.load(cfg=self.cfg))
        self.assertEqual(
            params["rel_include2"],
            "\\yentry.?level\\y|\\yjunior\\y|\\yassociate\\y|\\ycoordinator\\y"
            "|\\yassistant\\y|\\yspecialist\\y|\\yanalyst\\y|\\yno experience\\y"
            "|\\ywill train\\y|\\yapprentice\\y|\\yintern(ship)?s?\\y")

    def test_the_two_paths_no_longer_compile_the_same_entry_alternation(self):
        """The split is real in the compiled SQL, not only in the file."""
        _, params = relevance.tier_sql(relevance.load(cfg=self.cfg))
        self.assertNotEqual(params["rel_include2"], params["rel_dincl2"])
        self.assertTrue(params["rel_dincl2"].startswith(params["rel_include2"]))

    def test_the_gate_is_complete_rather_than_a_patch(self):
        """relevance.load() merges over DISABLED, not over config/relevance.json
        (relevance.py:88-90), so an omitted key is not inherited -- it goes
        permissive. A gate missing one of these does not fail; it opens."""
        for key in ("title_include", "description_include", "title_exclude",
                    "company_exclude", "platform_exclude", "description_exclude",
                    "location_columns", "max_tier_to_score"):
            self.assertIn(key, self.cfg)

    def test_max_tier_is_two(self):
        """3 is an unconditional pass, not a wider gate: it disables
        title_exclude, company_exclude, platform_exclude and
        description_exclude at once (relevance.py:297-299, :331)."""
        self.assertEqual(self.cfg["max_tier_to_score"], 2)


class TestRegexDialect(unittest.TestCase):
    """CLAUDE.md's first landmine, asserted rather than remembered."""

    def setUp(self):
        self.cfg = gate()
        self.patterns = []
        for key in ("title_include", "description_include"):
            for group in self.cfg[key]:
                self.patterns.extend(group)
        for key in ("title_exclude", "company_exclude", "platform_exclude",
                    "description_exclude"):
            self.patterns.extend(self.cfg[key])

    def test_no_pattern_uses_a_python_word_boundary(self):
        """In Postgres \\b is BACKSPACE. A \\b pattern raises nothing, matches
        nothing, and quietly demotes to tier 3 everything it was written to
        catch. Measured positive control, recorded in _regex_dialect:
        \\yllm\\y -> 1,127 rows, \\bllm\\b -> 0 rows and no error."""
        for p in self.patterns:
            self.assertNotIn("\\b", p, f"{p!r} uses \\b; Postgres needs \\y")

    def test_the_make_dot_com_dot_stays_escaped(self):
        """Unescaped, make.com matches 116 rows against 2 -- a 58x inflation,
        because it also catches 'make a common' and 'makes com'."""
        ai = self.cfg["title_include"][0]
        self.assertIn("make\\.com", ai)
        self.assertNotIn("make.com", [p for p in ai if p != "make\\.com"])

    def test_every_pattern_compiles_once_translated(self):
        for p in self.patterns:
            re.compile(as_python(p))

    def test_no_include_term_hides_a_top_level_alternation(self):
        """relevance._alternation joins terms with a bare | and
        tools/relevance-report.py --dead tests each term standalone, so a term
        containing an unparenthesised | is two terms wearing a trenchcoat: it
        would report as live while half of it is dead. The three phrase terms
        wrap their alternations in (?:...) for exactly this reason."""
        for key in ("title_include", "description_include"):
            for group in self.cfg[key]:
                for p in group:
                    depth = 0
                    for i, ch in enumerate(p):
                        if ch == "(" and (i == 0 or p[i - 1] != "\\"):
                            depth += 1
                        elif ch == ")" and (i == 0 or p[i - 1] != "\\"):
                            depth -= 1
                        elif ch == "|" and depth == 0:
                            self.fail(f"{p!r} has a top-level |; wrap it in (?:...)")


class TestTheDescriptionGateAdmitsTheRolesItWasBuiltFor(unittest.TestCase):
    """THE DEFECT ITSELF. Every posting below is an intended-good row from the
    mock corpus that the pre-2026-07-29 gate rejected, and every one is the
    kind of role the whole retarget exists to find: an ordinary NYC employer,
    AI tooling described in the body, no AI vocabulary in the title.

    This class fails against the old gate. That is what it is for -- a test
    that cannot fail on the code it was written for is documentation, not a
    test. Run it against `git show HEAD~1:backend/config/pursuit-relevance.json`
    if you want to watch it go red.
    """

    #: The eight that the description phrases recover. mock_016/017/018 are
    #: NOT here: they are reachable only through the four rejected phrase
    #: families below, at roughly +136 live junk rows, and that trade was refused.
    RECOVERED = ("mock_012", "mock_019", "mock_022", "mock_023",
                 "mock_025", "mock_029", "mock_044", "mock_045")

    @classmethod
    def setUpClass(cls):
        cls.cfg = gate()
        cls.postings = {p["job_id"]: p for p in mock_corpus.load_postings()}

    def test_each_recovered_posting_clears_both_description_groups(self):
        ai, entry = self.cfg["description_include"]
        for job_id in self.RECOVERED:
            text = self.postings[job_id]["description_text"]
            with self.subTest(job_id=job_id):
                self.assertTrue(
                    matches_group(ai, text),
                    f"{job_id} carries no AI vocabulary in its description")
                self.assertTrue(
                    matches_group(entry, text),
                    f"{job_id} carries no entry-level signal in its description "
                    "-- this is the defect: the group was title vocabulary")

    def test_the_titles_really_do_lack_the_entry_level_nouns(self):
        """The premise of the fix, stated as an assertion so it cannot rot: if
        these titles DID carry the nouns, the title path would already have
        admitted them and the description group would not be the problem."""
        entry_title = self.cfg["title_include"][1]
        ai_title = self.cfg["title_include"][0]
        for job_id in self.RECOVERED:
            title = self.postings[job_id]["title"]
            with self.subTest(job_id=job_id):
                self.assertFalse(
                    matches_group(ai_title, title) and matches_group(entry_title, title),
                    f"{job_id} title {title!r} clears the title path on its own")

    def test_mock_022_is_the_canonical_case(self):
        """'No retail or e-commerce experience required; training provided' --
        matching neither \\yno experience\\y nor \\ywill train\\y, and now
        matching two of the three added phrases."""
        text = self.postings["mock_022"]["description_text"]
        self.assertIn("no retail or e-commerce experience required", text.lower())
        self.assertFalse(matches_group(["\\yno experience\\y", "\\ywill train\\y"], text))
        self.assertTrue(matches_group(self.cfg["description_include"][1], text))


class TestRejectedPhraseFamiliesStayRejected(unittest.TestCase):
    """A SENTINEL. These four families are the single most likely thing for a
    future session to add, because tools/mock-acceptance.py scores all four as
    costing NOTHING -- zero added false positives on the mock corpus.

    They are not free. Measured 2026-07-29 by compiling each through
    relevance.tier_sql against the live table, 13,447 open rows:

        we provide / offer ... training      +17 live rows
        we (will) train                       +5
        preferred but not required            +5
        experience ... preferred / is a plus +123

    What they admit: 'Software Engineer, RL Training Infra | OpenAI',
    'Full-Stack Software Engineer, Reinforcement Learning | Anthropic',
    'Product Manager, Gen AI | Scale AI'. \\ywe train\\y matched OpenAI's
    "we train models" -- a false friend that cannot exist on a corpus somebody
    wrote to a specification.

    They look free on the mock corpus because every intended-bad mock posting
    carrying that phrasing has no AI vocabulary at all, so the conjunction
    rejects it on the other half. That is a property of the fixture, not of the
    world, and it is CLAUDE.md's "fixtures written from a specification test
    the specification" firing on the deliverable that introduced the rule.

    Adding them takes mock recall from 89.7% to 100%. Do not. If you are here
    because the harness told you they are free, compile your candidate through
    relevance.tier_sql against the live table first.
    """

    #: Substrings that would appear in any reasonable spelling of the four.
    FORBIDDEN = ("we provide", "we offer", "we will train", "we train",
                 "preferred but not required", "is a plus", "experience preferred")

    def test_none_of_the_four_families_is_in_the_gate(self):
        cfg = gate()
        terms = [p.lower() for key in ("title_include", "description_include")
                 for group in cfg[key] for p in group]
        for forbidden in self.FORBIDDEN:
            for term in terms:
                self.assertNotIn(
                    forbidden, term,
                    f"{term!r} contains {forbidden!r} -- see this class's "
                    "docstring for what it admits live")

    def test_the_training_provided_term_is_narrow_on_purpose(self):
        """\\ytraining (?:is |will be )?provided\\y is kept and 'we provide
        training' is not, and the difference is not stylistic. The passive form
        is what an employer writes about the ROLE; 'we provide training' is
        what an AI company writes about its PRODUCT."""
        cfg = gate()
        entry = cfg["description_include"][1]
        self.assertIn("\\ytraining (?:is |will be )?provided\\y", entry)
        self.assertFalse(matches_group(entry, "We provide training data services"))
        self.assertTrue(matches_group(entry, "No prior experience needed; training provided."))


class TestTitleExcludeKeepsTheCohortsOwnRoles(unittest.TestCase):
    """title_exclude gates BOTH paths (relevance.py:232-234, pinned by
    test_relevance.py:203-211), so a title term vetoes a posting whose
    description passes both required groups. Six of these terms were inherited
    from the AUTHOR's software-engineer profile, where excluding them was
    right, and several were exclusions on the COHORT's target population.

    These assertions are about the DECISIONS, not the counts -- a count moves
    every night. They exist because the reasoning is worth more than the list
    and lived nowhere executable."""

    def setUp(self):
        self.excludes = gate()["title_exclude"]

    def test_customer_success_is_narrowed_to_manager_and_above(self):
        """The bare term blocked 12 rows: 6 Associate/Specialist the cohort
        wants, 5 Manager/CSM it does not, 1 Applied AI Specialist. Removing it
        outright would have imported the 5 -- the seniority block deliberately
        does not catch \\ymanager\\y. Narrowing admits exactly the 7 and blocks
        exactly the 5. It is also the only thing that recovers mock_045."""
        self.assertNotIn("\\ycustomer success\\y", self.excludes)
        for term in ("\\ycustomer success manager\\y",
                     "\\ymanager, customer success\\y",
                     "\\yhead of customer success\\y",
                     "\\ydirector of customer success\\y"):
            self.assertIn(term, self.excludes)

    def test_a_customer_success_associate_is_no_longer_vetoed(self):
        exclude = [as_python(p) for p in self.excludes]
        def blocked(title):
            return any(re.search(p, title, re.I) for p in exclude)
        self.assertFalse(blocked("Customer Success Associate"))
        self.assertFalse(blocked("Customer Success Specialist | Housing"))
        self.assertFalse(blocked("Applied AI Specialist, Commercial Customer Success"))
        self.assertTrue(blocked("Customer Success Manager"))
        self.assertTrue(blocked("Manager, Customer Success"))
        self.assertTrue(blocked("Director of Customer Success"))

    def test_executive_assistant_is_kept(self):
        """Decided on a census, not a sample: all 12 open EA postings at the
        blocked employers were read and every one asks for 3+ to 10+ years of
        executive support. The persona's honest_gaps says prior seniority does
        not transfer. If this is ever revisited, revisit it with descriptions
        -- see _title_exclude_note for the figures."""
        self.assertIn("\\yexecutive assistant\\y", self.excludes)

    def test_the_seniority_block_survives_the_widened_description_group(self):
        """Load-bearing, and MORE so after the split: it is the only thing
        between the description path and every senior requisition at an AI
        employer. \\ywe train\\y matching OpenAI's "we train models" is what
        that failure looks like when the block is missing."""
        for term in ("\\ysenior\\y", "\\ysr\\.?\\y", "\\ystaff\\y",
                     "\\yprincipal\\y", "\\ydirector\\y", "\\yhead of\\y"):
            self.assertIn(term, self.excludes)


class TestTheHarnessMeasuresTheGateThePipelineRuns(unittest.TestCase):
    """tools/mock-acceptance.py used to importlib the gate out of
    migrations/migrate_pursuit_profile.py. When the gate moved to a config file
    on 2026-07-29 that function had to move with it -- otherwise the harness
    keeps compiling the old literal, reports the gate unchanged, and the fix
    reads as having done nothing rather than as the instrument pointing at the
    wrong object.

    Nothing in the suite guarded that before this test. install_profiles()'s
    own docstring stated the invariant in prose and prose does not run."""

    @staticmethod
    def _harness():
        path = os.path.join(_BACKEND, "tools", "mock-acceptance.py")
        spec = importlib.util.spec_from_file_location("mock_acceptance_tool", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_the_harness_reads_the_same_gate_file(self):
        self.assertEqual(self._harness().cohort_relevance(), gate())

    def test_the_migration_reads_the_same_gate_file(self):
        path = os.path.join(_BACKEND, "migrations", "migrate_pursuit_profile.py")
        spec = importlib.util.spec_from_file_location("migrate_pursuit_profile", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertEqual(mod.COHORT_RELEVANCE, gate())

    def test_the_gate_validates_as_a_profile_would_store_it(self):
        with open(os.path.join(_BACKEND, "config", "pursuit-persona.json")) as f:
            persona = json.load(f)
        profiles.validate(persona, {"base": 50}, gate())


@requires_db
class TestGateAgainstRealPostgres(unittest.TestCase):
    """The only test here that exercises the actual dialect.

    Everything above translates \\y to \\b and runs Python's engine, which
    would cheerfully accept a pattern Postgres rejects -- and \\y vs \\b is
    exactly the failure this repo has already been bitten by. These rows go
    through the real relevance.tier_sql, in a scratch schema, against real
    Postgres."""

    ROWS = [
        # (title, description, expected admitted)
        ("Permit Intake Assistant",
         "You will use ChatGPT daily. No permitting experience required.", True),
        ("Claims Intake Associate",
         "AI-powered triage tools. No insurance license or prior claims "
         "experience required.", True),
        ("Customer Support Associate",
         "Our automation stack is Zapier. Training provided.", True),
        ("Operations Coordinator",
         "We use Claude to summarise tickets. Training will be provided.", True),
        # The AI half alone is not enough -- the conjunction is the design.
        ("Senior Staff Engineer",
         "We train large language models. No prior experience required.", False),
        ("Warehouse Operative",
         "Lift boxes. Training provided.", False),
        # A description-path row vetoed on its title, deliberately.
        ("Account Executive",
         "You will use ChatGPT daily. No sales experience required.", False),
        # Entry-level signal but no AI vocabulary anywhere.
        ("Filing Assistant",
         "Sort documents. No experience necessary.", False),
    ]

    #: company_name and platform are '' rather than NULL, and that is not
    #: cosmetic. The exclusion arms are `j.company_name !~* %(rel_coexcl)s`,
    #: and in SQL `NULL !~* 'x'` is NULL, not TRUE -- so a NULL there makes the
    #: whole row_ok conjunction NULL and the CASE falls through to tier 3. A
    #: fixture built with NULLs would report every row rejected and every
    #: "expected rejected" assertion would pass for the wrong reason. Verified
    #: against production: 0 of 14,049 rows have a NULL company_name, platform
    #: or title, so this is a property of the fixture and not a live defect --
    #: but see test_a_null_provenance_column_would_send_a_row_to_tier_3.
    EMPTY = "''::text"

    def test_the_rows_tier_as_expected_through_real_tier_sql(self):
        cfg = relevance.load(cfg=gate())
        sql, params = relevance.tier_sql(cfg, table_alias="v")
        conn = dbconn.connect()
        try:
            for title, description, expected in self.ROWS:
                q = (f"SELECT ({sql}) FROM (SELECT %(t)s::text AS title, "
                     f"%(d)s::text AS description_text, "
                     f"{self.EMPTY} AS company_name, {self.EMPTY} AS platform, "
                     f"TRUE AS location_is_nyc, FALSE AS location_is_remote) v")
                tier = conn.execute(q, {**params, "t": title, "d": description}
                                    ).fetchone()[0]
                with self.subTest(title=title):
                    self.assertEqual(
                        tier <= cfg["max_tier_to_score"], expected,
                        f"{title!r} tiered {tier}, expected "
                        f"{'admitted' if expected else 'rejected'}")
        finally:
            conn.rollback()
            conn.close()

    def test_a_null_provenance_column_would_send_a_row_to_tier_3(self):
        """Found while writing the fixture above, and pinned rather than just
        worked around. `NULL !~* 'x'` is NULL, so a NULL company_name or
        platform makes row_ok NULL and the row is silently skipped -- no error,
        no log line, exactly this repo's stated failure mode.

        It is not live: all 14,049 rows have both columns populated, and both
        are NOT NULL where it matters. But an ingest path that started writing
        NULL company_name would lose those postings invisibly, and nothing
        else in the suite would notice. If this test ever fails because the
        columns became COALESCE'd, that is an improvement -- delete it and say
        so."""
        cfg = relevance.load(cfg=gate())
        sql, params = relevance.tier_sql(cfg, table_alias="v")
        conn = dbconn.connect()
        try:
            q = (f"SELECT ({sql}) FROM (SELECT %(t)s::text AS title, "
                 f"%(d)s::text AS description_text, NULL::text AS company_name, "
                 f"''::text AS platform, TRUE AS location_is_nyc, "
                 f"FALSE AS location_is_remote) v")
            tier = conn.execute(q, {**params,
                                    "t": "Permit Intake Assistant",
                                    "d": "You will use ChatGPT daily. "
                                         "No permitting experience required."}
                                ).fetchone()[0]
            self.assertEqual(tier, 3,
                             "a NULL company_name no longer silently rejects; "
                             "see this test's docstring")
        finally:
            conn.rollback()
            conn.close()

    def test_a_backspace_pattern_would_match_nothing(self):
        """The landmine itself, demonstrated rather than described. If this
        ever starts passing with \\b, Postgres has changed and every dialect
        assumption in this file needs re-reading."""
        conn = dbconn.connect()
        try:
            hit_y = conn.execute(
                "SELECT %s ~* %s", ("we use an llm", "\\yllm\\y")).fetchone()[0]
            hit_b = conn.execute(
                "SELECT %s ~* %s", ("we use an llm", "\\bllm\\b")).fetchone()[0]
            self.assertTrue(hit_y)
            self.assertFalse(hit_b)
        finally:
            conn.rollback()
            conn.close()


if __name__ == "__main__":
    unittest.main()
