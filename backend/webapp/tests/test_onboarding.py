"""Onboarding's vocabularies, its three-layer merge, and the frozen contract.

NO DATABASE HERE, the line tests/test_events.py and tests/test_prior_domain.py
both draw: this is the file someone runs on a laptop with nothing installed.
Every claim below is about a constant, a pure function, or a JSON file on disk.
What needs a server -- that the CHECK constraints refuse a bad value, that the
composite foreign key holds, that the endpoint writes what it says it writes --
is in tests/test_builder_profiles.py and skips when there is none.

WHY THE FIXTURE IS CHECKED HERE AT ALL. API-CONTRACT-v1.md § Mocking asks that
the frozen fixtures "become contract tests both sides run" once the backend
lands. frontend/verify_fixtures.py is the half of that which runs under the bare
system python3, and it deliberately covers fixtures/shipped/ only -- the
contract directory's own MANIFEST says nothing there is verified, "deliberately:
there is no code to verify it against". POST /v1/onboarding is the first
endpoint for which that stopped being true, so this is where the aspirational
fixture starts being held to the code. It is here rather than in
verify_fixtures.py because the check needs pydantic, which lives only in this
venv.

THE FIXTURES MOVED TO shipped/ ON 2026-08-02, WITH THE ONBOARDING SCREEN, AND
THAT CHANGED WHAT ONE TEST BELOW SHOULD ASSERT. While they sat in contract/ they
were a TARGET, so a difference from the code was a deviation to record --
which is what test_the_one_deviation_is_the_timestamp_format did, correctly.
shipped/ means something stronger: "what the API returns TODAY, derived from the
code". A shipped fixture that differs from the code is not a deviation, it is
the confidently-wrong fixture verify_fixtures.py's docstring exists to prevent.
So the `Z` came off the fixture and that test now pins its absence. The
REASONING did not change and neither did the conclusion about which form wins;
only which file has to agree with which.

Both paths below are still resolved here rather than duplicated, and
verify_fixtures.py now checks the same two files from the other side under the
bare interpreter. Two checkers, one fixture, neither able to be the only one.
"""

import json
import os
import pathlib
import re
import sys
import unittest

WEBAPP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WEBAPP_DIR)

import config  # noqa: E402,F401  (must come first -- performs the sys.path insert)

import onboarding  # noqa: E402
import schema_web  # noqa: E402

REPO = pathlib.Path(WEBAPP_DIR).parents[1]
#: Moved out of fixtures/contract/ on 2026-08-02, when the onboarding screen
#: landed: the ASPIRATIONAL_ prefix said "no route" and the route had shipped
#: since 4c874e7. See the module docstring for what that changed about the last
#: test in this file.
SHIPPED = REPO / "frontend" / "fixtures" / "shipped"
REQUEST_FIXTURE = SHIPPED / "POST_v1_onboarding.request.json"
RESPONSE_FIXTURE = SHIPPED / "POST_v1_onboarding.response.json"
#: GET /v1/onboarding was in neither directory until the same day.
GET_FIXTURE = SHIPPED / "GET_v1_onboarding.json"
GET_FIRST_RUN_FIXTURE = SHIPPED / "GET_v1_onboarding.first_run.json"


class TestTheVocabulariesAreDerivedNotInvented(unittest.TestCase):
    """The standard schema_web.PRIOR_DOMAINS set for itself, applied to the
    four vocabularies task 26 added. Each value is traceable to a file in this
    repo, and the tests name which."""

    def test_the_only_attested_situation_is_in_the_vocabulary(self):
        # The contract fixture's value, which is API-CONTRACT-v1.md's value.
        # If this is ever not in SITUATIONS, the endpoint 400s on the exact body
        # the frontend was built against.
        self.assertIn("employed_seeking", schema_web.SITUATIONS)

    def test_situation_can_say_not_employed(self):
        # The negation the attested value implies. Without it every unemployed
        # Builder answers `other`, which is the `none`-vs-NULL conflation
        # PRIOR_DOMAINS refuses, one field over.
        self.assertIn("unemployed_seeking", schema_web.SITUATIONS)

    def test_situation_prices_other_as_no_information(self):
        self.assertIn("other", schema_web.SITUATIONS)

    def test_location_prefs_are_exactly_what_the_read_path_can_answer(self):
        # jobs_app exposes location_is_nyc and location_is_remote and GET
        # /v1/jobs filters on precisely those two. A richer preference
        # vocabulary would be a promise the list cannot keep.
        self.assertEqual(set(schema_web.LOCATION_PREFS),
                         {"nyc", "remote", "either"})

    def test_remote_prefs_are_a_threshold_over_the_extractors_enum(self):
        # Read out of ../extract.py's source rather than imported: that module
        # is the pipeline's and its dependencies are not in this venv (both
        # venvs set include-system-site-packages = false). This is the same
        # technique, for the same reason, as frontend/verify_fixtures.py.
        source = (REPO / "backend" / "extract.py").read_text()
        match = re.search(r"REMOTE_POLICY = \(([^)]*)\)", source)
        self.assertIsNotNone(match, "extract.REMOTE_POLICY moved or changed shape")
        policies = set(re.findall(r"'([^']+)'|\"([^\"]+)\"", match.group(1)))
        policies = {a or b for a, b in policies}
        self.assertEqual(
            policies,
            {"onsite", "hybrid", "remote_local", "remote_anywhere", "unknown"},
            "extract.REMOTE_POLICY changed; REMOTE_PREFS is a threshold over it "
            "and has to be re-derived rather than left alone")
        # One threshold per real arrangement, and none for `unknown`: that is
        # the extractor's abstention, not a place anybody works.
        self.assertEqual(set(schema_web.REMOTE_PREFS),
                         {"onsite_ok", "hybrid_ok", "remote_only"})

    def test_schedule_constraints_holds_only_what_is_attested(self):
        # One value, and that is the honest size of it. Widening this is a
        # decision taken with a real Builder's answer in hand -- the lesson
        # PRIOR_DOMAINS is still teaching, since HANDOFF.md records that it
        # already fails on the one real user in the table.
        self.assertEqual(schema_web.SCHEDULE_CONSTRAINTS, ("no_overnight",))

    def test_no_vocabulary_has_duplicates(self):
        for name in ("SITUATIONS", "LOCATION_PREFS", "REMOTE_PREFS",
                     "SCHEDULE_CONSTRAINTS"):
            vocabulary = getattr(schema_web, name)
            self.assertEqual(len(set(vocabulary)), len(vocabulary), name)


class TestTheChecksCannotDriftFromThePythonLists(unittest.TestCase):
    """Generated, never typed out beside the tuple. The failure this prevents is
    quiet and one-sided, exactly as it is for PRIOR_DOMAINS: widening the
    vocabulary in Python while the database keeps refusing the new value
    surfaces as a 500 on one Builder's submit and nowhere else."""

    CASES = (
        ("_SITUATION_CHECK", "situation", "SITUATIONS"),
        ("_LOCATION_PREF_CHECK", "location_pref", "LOCATION_PREFS"),
        ("_REMOTE_PREF_CHECK", "remote_pref", "REMOTE_PREFS"),
    )

    def test_every_value_appears_in_its_generated_check(self):
        for check_name, _column, vocab_name in self.CASES:
            check = getattr(schema_web, check_name)
            for value in getattr(schema_web, vocab_name):
                self.assertIn(f"'{value}'", check, check_name)

    def test_no_check_names_anything_its_vocabulary_does_not(self):
        for check_name, _column, vocab_name in self.CASES:
            quoted = set(re.findall(r"'([^']+)'",
                                    getattr(schema_web, check_name)))
            self.assertEqual(quoted, set(getattr(schema_web, vocab_name)),
                             check_name)

    def test_every_check_admits_null(self):
        # NULL means NOBODY ASKED, which is the honest value for every Builder
        # who existed before onboarding did -- all three of them.
        for check_name, column, _vocab_name in self.CASES:
            self.assertIn(f"{column} IS NULL", getattr(schema_web, check_name))

    def test_the_array_check_uses_containment_and_admits_null(self):
        check = schema_web._SCHEDULE_CONSTRAINTS_CHECK
        self.assertIn("schedule_constraints IS NULL", check)
        self.assertIn("<@", check)
        self.assertIn("'no_overnight'", check)

    def test_the_table_ddl_uses_the_generated_checks(self):
        # Rather than a second literal list inside the CREATE TABLE, which is
        # exactly the drift api/query_claims.py's docstring records.
        import inspect
        source = inspect.getsource(schema_web.ensure_schema)
        for check_name, _column, _vocab in self.CASES:
            self.assertIn(f"CHECK ({{{check_name}}})", source, check_name)
        self.assertIn("CHECK ({_SCHEDULE_CONSTRAINTS_CHECK})", source)

    def test_tracks_has_no_check_and_that_is_deliberate(self):
        # It is derived server-side from job_scores.primary_track, not sent by a
        # client, so the argument that closes the other vocabularies does not
        # apply -- and the track vocabulary is task 30's undecided question, so
        # a CHECK would constrain the decision rather than the data.
        import inspect
        source = inspect.getsource(schema_web.ensure_schema)
        self.assertNotIn("builder_profiles_tracks", source)


class TestTheApiAndTheColumnsReadOneVocabulary(unittest.TestCase):

    def test_every_checked_column_is_validated_by_the_request(self):
        # The drift this guards: widening a tuple and forgetting the API, or
        # adding an API field whose column has a CHECK nobody validates against.
        # Both surface as a 500 rather than a 400.
        self.assertEqual(
            set(onboarding._VOCABULARIES),
            {"prior_domain", "situation", "location_pref", "remote_pref"})

    def test_the_validator_reads_the_schema_tuples_themselves(self):
        for field, vocabulary in onboarding._VOCABULARIES.items():
            self.assertIs(vocabulary, getattr(schema_web, {
                "prior_domain": "PRIOR_DOMAINS",
                "situation": "SITUATIONS",
                "location_pref": "LOCATION_PREFS",
                "remote_pref": "REMOTE_PREFS",
            }[field]))


class TestResolution(unittest.TestCase):
    """Builder override, else cohort, else shared default."""

    def test_nothing_anywhere_resolves_to_the_shared_defaults(self):
        self.assertEqual(onboarding.resolve(), dict(onboarding.DEFAULTS))

    def test_the_builder_wins_over_the_cohort(self):
        resolved = onboarding.resolve(override={"location_pref": "remote"},
                                      cohort={"location_pref": "nyc"})
        self.assertEqual(resolved["location_pref"], "remote")

    def test_the_cohort_wins_over_the_shared_default(self):
        resolved = onboarding.resolve(cohort={"comp_floor": 50000})
        self.assertEqual(resolved["comp_floor"], 50000)

    def test_a_builder_answering_one_key_keeps_the_cohorts_answers_to_the_rest(self):
        """THE POINT OF THE MIDDLE LAYER, and the one place this merge
        deliberately differs from relevance.load().

        relevance merges a profile's cfg over DISABLED and pointedly not over
        the shared file, because a profile's relevance_json REPLACES the shared
        gate wholesale. Here the cohort is an inherited parent -- "everything
        else resolves through the parent" -- so a Builder who answers one
        question must not silently lose the cohort's answers to the others.
        """
        resolved = onboarding.resolve(
            override={"comp_floor": 60000},
            cohort={"location_pref": "nyc", "remote_pref": "hybrid_ok"})
        self.assertEqual(resolved["comp_floor"], 60000)
        self.assertEqual(resolved["location_pref"], "nyc")
        self.assertEqual(resolved["remote_pref"], "hybrid_ok")

    def test_a_none_falls_through_rather_than_overwriting(self):
        # Every column on builder_profiles is nullable and NULL means nobody
        # asked. A row loaded whole therefore arrives with Nones in it, and they
        # must not erase the layer below -- which is what makes load_builder()
        # able to return the row as-is instead of filtering it first.
        resolved = onboarding.resolve(
            override={"location_pref": None, "comp_floor": None},
            cohort={"location_pref": "nyc", "comp_floor": 50000})
        self.assertEqual(resolved["location_pref"], "nyc")
        self.assertEqual(resolved["comp_floor"], 50000)

    def test_every_default_is_the_permissive_one(self):
        # relevance.DISABLED's rule: "a missing config must not silently start
        # skipping jobs". A Builder who has not onboarded must see MORE than one
        # who has, never less.
        self.assertEqual(onboarding.DEFAULTS["location_pref"], "either")
        self.assertEqual(onboarding.DEFAULTS["comp_floor"], 0)
        # onsite_ok reads oddly and is correct: it is the flexible end of the
        # threshold, so no remote_policy value is excluded by it.
        self.assertEqual(onboarding.DEFAULTS["remote_pref"], "onsite_ok")

    def test_tracks_bottoms_out_at_none_meaning_every_track(self):
        # The one key with no finite "all" value. A caller that reads None as an
        # empty filter shows nothing, which is why this is pinned.
        self.assertIsNone(onboarding.resolve()["tracks"])

    def test_the_defaults_are_themselves_legal_values(self):
        # A default that the CHECK constraint would refuse is a default nobody
        # can ever store, which would only surface the first time somebody
        # persisted a resolved config.
        self.assertIn(onboarding.DEFAULTS["location_pref"],
                      schema_web.LOCATION_PREFS)
        self.assertIn(onboarding.DEFAULTS["remote_pref"], schema_web.REMOTE_PREFS)

    def test_the_resolvable_keys_are_the_columns_the_loader_selects(self):
        import inspect
        source = inspect.getsource(onboarding.load_builder)
        for key in onboarding.RESOLVABLE:
            self.assertIn(key, source)

    def test_an_unknown_key_in_a_layer_is_ignored(self):
        # A hand-edited criteria_json is where the cohort layer comes from, so a
        # typo has to be inert rather than introduce a preference nothing knows
        # how to apply.
        resolved = onboarding.resolve(cohort={"comp_flor": 99999})
        self.assertEqual(resolved["comp_floor"], 0)
        self.assertNotIn("comp_flor", resolved)


class TestTheCohortLayer(unittest.TestCase):

    class _Profile:
        def __init__(self, criteria):
            self.criteria = criteria

    def test_a_profile_without_the_section_contributes_nothing(self):
        # This is `pursuit` today, so it is the case that must not raise.
        self.assertEqual(
            onboarding.cohort_defaults(self._Profile({"base": 50})), {})

    def test_a_missing_profile_contributes_nothing(self):
        self.assertEqual(onboarding.cohort_defaults(None), {})

    def test_comment_keys_are_stripped(self):
        # `_comment` fields in config JSON are load-bearing documentation and
        # every reader strips them -- relevance.load() and
        # migrations/migrate_profiles.py's strip_comments() both do.
        section = {"_comment": "why nyc", "location_pref": "nyc"}
        self.assertEqual(
            onboarding.cohort_defaults(
                self._Profile({onboarding.COHORT_DEFAULTS_KEY: section})),
            {"location_pref": "nyc"})

    def test_a_section_of_the_wrong_type_contributes_nothing(self):
        for bad in ("nyc", [1, 2], 7):
            self.assertEqual(
                onboarding.cohort_defaults(
                    self._Profile({onboarding.COHORT_DEFAULTS_KEY: bad})), {})


class TestTheVerdictMapping(unittest.TestCase):
    """frontend/fixtures/contract/MANIFEST.json recorded this as undecided:
    "'interested' has to map onto a CLIENT_EVENT_NAMES value, and no mapping has
    been decided". These are the decision."""

    def test_both_verdicts_map_to_real_client_events(self):
        import jobs
        for verdict, event in onboarding.VERDICT_EVENTS.items():
            self.assertIn(event, jobs.CLIENT_EVENT_NAMES,
                          f"{verdict} maps to {event}, which no client may send")

    def test_neither_maps_to_a_server_derived_event(self):
        import jobs
        self.assertEqual(
            set(onboarding.VERDICT_EVENTS.values()) & set(jobs.SERVER_EVENT_NAMES),
            set())

    def test_neither_maps_to_a_rank_requiring_event(self):
        # A seed set has no ranking, and record_seed_judgements sends no rank.
        # An impression or an open here would be a 400 from validate_batch --
        # which would be a self-inflicted contract violation.
        import jobs
        self.assertEqual(
            set(onboarding.VERDICT_EVENTS.values())
            & set(jobs.RANK_REQUIRED_EVENTS), set())

    def test_the_positive_verdict_is_the_cohort_visible_one(self):
        import jobs
        self.assertEqual(jobs.visibility_for(onboarding.VERDICT_EVENTS["interested"]),
                         jobs.VISIBILITY_COHORT)

    def test_the_negative_verdict_is_private(self):
        import jobs
        self.assertEqual(
            jobs.visibility_for(onboarding.VERDICT_EVENTS["not_interested"]),
            jobs.VISIBILITY_PRIVATE)


class TestRequestValidation(unittest.TestCase):

    def _body(self, **kwargs):
        return onboarding.OnboardingRequest(**kwargs)

    def test_an_empty_body_is_valid(self):
        # Every field is skippable. That is the product requirement -- thirty
        # people filling a form on a phone -- not leniency.
        onboarding.validate_request(self._body())

    def test_each_vocabulary_field_is_rejected_by_its_own_code(self):
        for field, value in (("prior_domain", "aerospace"),
                             ("situation", "retired"),
                             ("location_pref", "boston"),
                             ("remote_pref", "maybe")):
            with self.assertRaises(onboarding.ContractError) as caught:
                onboarding.validate_request(self._body(**{field: value}))
            self.assertEqual(caught.exception.code, f"unknown_{field}")
            # The message names the vocabulary, because a client author needs to
            # know what IS allowed, not only that this was not.
            self.assertIn(value, caught.exception.message)

    def test_an_unknown_schedule_constraint_is_rejected(self):
        with self.assertRaises(onboarding.ContractError) as caught:
            onboarding.validate_request(
                self._body(schedule_constraints=["no_overnight", "no_mondays"]))
        self.assertEqual(caught.exception.code, "unknown_schedule_constraint")

    def test_an_empty_constraint_list_is_accepted(self):
        # {} is "asked, and there are none" -- a real Builder. NULL is "nobody
        # asked". Collapsing them is the conflation PRIOR_DOMAINS refuses.
        onboarding.validate_request(self._body(schedule_constraints=[]))

    def test_an_unknown_verdict_is_rejected(self):
        with self.assertRaises(onboarding.ContractError) as caught:
            onboarding.validate_request(self._body(seed_judgements=[
                {"job_id": "a", "verdict": "interested"},
                {"job_id": "b", "verdict": "maybe"}]))
        self.assertEqual(caught.exception.code, "unknown_verdict")

    def test_two_verdicts_on_one_posting_are_rejected(self):
        # The two orders produce different builder_job_state, so refusing is the
        # only answer that does not depend on list order.
        with self.assertRaises(onboarding.ContractError) as caught:
            onboarding.validate_request(self._body(seed_judgements=[
                {"job_id": "a", "verdict": "interested"},
                {"job_id": "a", "verdict": "not_interested"}]))
        self.assertEqual(caught.exception.code, "duplicate_seed_judgement")

    def test_a_contract_error_is_a_400_in_the_contracts_envelope(self):
        # Registered for jobs.ContractError alone in app.py, which is why
        # onboarding raises that type rather than one of its own.
        import jobs
        self.assertIs(onboarding.ContractError, jobs.ContractError)
        error = onboarding.ContractError("unknown_verdict", "…", None)
        self.assertEqual(error.status_code, 400)

    def test_negative_numbers_are_refused_at_the_model_layer(self):
        from pydantic import ValidationError
        for field in ("comp_floor", "prior_years"):
            with self.assertRaises(ValidationError):
                self._body(**{field: -1})

    def test_the_seed_batch_is_capped(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            self._body(seed_judgements=[
                {"job_id": str(i), "verdict": "interested"}
                for i in range(onboarding.MAX_SEED_JUDGEMENTS + 1)])

    def test_the_cap_leaves_room_above_what_a_screen_shows(self):
        # Task 26 asks a screen for 15-20 postings.
        self.assertGreater(onboarding.MAX_SEED_JUDGEMENTS, 20)

    def test_the_request_names_no_profile(self):
        # Tenancy comes from the session, never from a parameter -- jobs.py's
        # rule, and "a `?profile=` parameter would turn one forgotten check into
        # a cross-user data leak".
        self.assertNotIn("profile", onboarding.OnboardingRequest.model_fields)

    def test_the_request_names_no_tracks(self):
        # Seeded from behaviour, not a checkbox. See derive_tracks().
        self.assertNotIn("tracks", onboarding.OnboardingRequest.model_fields)


class TestTheFrozenContractFixture(unittest.TestCase):
    """The frozen fixtures the client is built against, held to the code.

    ~~The aspirational fixture~~ -- they are in fixtures/shipped/ as of
    2026-08-02, because the endpoint ships and a fixture in contract/ is one
    nothing checks. The pydantic-dependent half of the checking is still here,
    because pydantic lives only in this venv; the shape half is in
    frontend/verify_fixtures.py, which runs under the bare system python3.

    IT ASSERTS THAT THE FILES EXIST RATHER THAN SKIPPING PAST THEM. The setUp
    used to skipTest on a missing request fixture, and on the day the files were
    renamed that turned seven tests green-by-absence: the suite still said OK
    and nothing in it was checking the fixture any more. A missing shipped
    fixture is a failure, not an unavailable dependency -- unlike a scratch
    database, these files are in the repo.
    """

    def setUp(self):
        for path in (REQUEST_FIXTURE, RESPONSE_FIXTURE,
                     GET_FIXTURE, GET_FIRST_RUN_FIXTURE):
            self.assertTrue(
                path.exists(),
                f"{path} is missing. It is a committed fixture, so this is a "
                f"rename or a deletion, not an absent dependency -- skipping "
                f"here is how seven of these tests silently stopped running "
                f"when the files moved out of fixtures/contract/.")
        self.request = json.loads(REQUEST_FIXTURE.read_text())
        self.response = json.loads(RESPONSE_FIXTURE.read_text())
        self.get = json.loads(GET_FIXTURE.read_text())
        self.first_run = json.loads(GET_FIRST_RUN_FIXTURE.read_text())

    def test_the_frozen_request_body_parses(self):
        onboarding.OnboardingRequest(**self.request)

    def test_the_frozen_request_body_validates(self):
        # Not merely well-typed: every vocabulary value in it is one the
        # database would accept. This is the assertion that would have caught a
        # contract written against `"prior_domain": "food service"`, which is
        # what API-CONTRACT-v1.md itself says and which PRIOR_DOMAINS refuses --
        # the fixture corrected it to `hospitality` and this pins that.
        onboarding.validate_request(
            onboarding.OnboardingRequest(**self.request))

    def test_the_endpoint_accepts_every_key_the_fixture_sends(self):
        # A key the model silently ignores is worse than one it rejects: the
        # frontend sends it, the API 200s, and nothing is stored.
        self.assertEqual(
            set(self.request) - set(onboarding.OnboardingRequest.model_fields),
            set())

    def test_the_response_top_level_keys_match(self):
        self.assertEqual(set(self.response),
                         {"onboarding", "seed_judgements_recorded", "profile"})

    def test_the_onboarding_block_keys_match(self):
        self.assertEqual(set(self.response["onboarding"]),
                         {"completed", "completed_at", "prior_domain",
                          "prior_years"})

    def test_the_recorded_count_is_the_number_of_judgements_sent(self):
        # The fixture's own internal consistency, and the property the handler
        # implements: every judgement for a job in this profile's match set is
        # recorded, so the two agree whenever the client sent a live list.
        self.assertEqual(self.response["seed_judgements_recorded"],
                         len(self.request["seed_judgements"]))

    def test_the_one_deviation_is_gone_because_the_fixture_moved(self):
        """~~DEVIATION, RECORDED RATHER THAN MATCHED.~~ MATCHED, 2026-08-02.

        THE REASONING IS UNCHANGED AND THE CONCLUSION WAS ALWAYS THE SAME: the
        repo form wins and the fixture was the outlier. This service emits
        '%Y-%m-%dT%H:%M:%S' with no Z, from lib.timeparse.utc_now_str(), whose
        docstring says that shape is load-bearing and "must not gain an offset
        or microseconds" because both pipelines compare these as STRINGS.
        schema_web.py gives the reason for the storage format -- "every other
        table in this database does it, and one table with TIMESTAMPTZ would
        make every join and every hand-written diagnostic query a special case"
        -- and the shipped first_seen is the same bare stamp.

        WHAT CHANGED IS WHICH FILE HAS TO AGREE WITH WHICH. In
        fixtures/contract/ the fixture was a TARGET, so a difference from the
        code was a deviation to write down. In fixtures/shipped/ it is a claim
        about what the API returns today, and a wrong one is exactly the
        confidently-wrong fixture verify_fixtures.py exists to prevent -- a
        client doing new Date(completed_at) on the real value reads it as LOCAL
        time. So the Z came off, and this pins its absence from both ends:
        against utc_now_str() and against the file.
        """
        from lib.timeparse import utc_now_str
        bare = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$"
        self.assertRegex(utc_now_str(), bare)
        for name, body in (("POST response", self.response), ("GET", self.get)):
            self.assertRegex(
                body["onboarding"]["completed_at"], bare,
                f"the {name} fixture's completed_at is not utc_now_str()'s "
                f"format; onboarded_at is TEXT written by that function")

    def test_the_get_fixtures_are_the_same_read_as_the_post_response(self):
        # get_onboarding() and post_onboarding() both return _state(), so the
        # block is the same block. One Builder cannot have two answers.
        self.assertEqual(set(self.get), {"onboarding", "profile"})
        self.assertEqual(self.get["onboarding"], self.response["onboarding"])
        self.assertEqual(set(self.first_run["onboarding"]),
                         set(self.response["onboarding"]))

    def test_a_first_run_builder_is_null_and_not_the_domain_named_none(self):
        # schema_web.py spends a paragraph on this and it is load-bearing:
        # `none` is a real answer about a real person, NULL means NOBODY ASKED.
        # A first-run client that collapsed the two would record every Builder
        # who has not onboarded as one with no prior domain.
        self.assertFalse(self.first_run["onboarding"]["completed"])
        self.assertIsNone(self.first_run["onboarding"]["completed_at"])
        self.assertIsNone(self.first_run["onboarding"]["prior_domain"])
        self.assertIn("none", schema_web.PRIOR_DOMAINS,
                      "the value NULL is being distinguished FROM still exists")


if __name__ == "__main__":
    unittest.main()
