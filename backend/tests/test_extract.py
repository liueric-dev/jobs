"""Unit tests for the extraction policy, the vote, and the drain loop.

Run:  python3 tests/test_extract.py

stdlib unittest -- pytest is not installed and is not worth a dependency here.

WHY THESE TESTS AND NOT OTHERS
    Three properties decide whether extract.py is doing what
    config/extraction-policy.json says it does, and all three fail SILENTLY:

      * one platform gets three calls and every other gets exactly one. A
        renamed platform string, or a policy file that failed to load, would
        quietly drop everything back to one pass -- and a one-pass row looks
        exactly like a three-pass unanimous one unless something counts the
        calls. So the calls are counted, with a fake `call` that spends
        nothing.
      * the vote is pure and its ties are pinned. A tie rule that drifts
        changes stored facts without changing any test that only checks the
        easy case, and the fallback ("the first pass's value") is precisely
        the behaviour this change must never be worse than.
      * a zero-progress batch stops the drain loop. DEFERRED rows stay
        eligible, so a down endpoint re-selects the same batch forever; a
        loop that did not break here would spin until its deadline against
        an endpoint already returning 429, which is strictly worse than the
        single batch it replaces. Nothing about that failure is visible in
        production until it has already happened.

Nothing here touches a database or an endpoint.
"""

import json
import os
import sys
import tempfile
import unittest
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import extract  # noqa: E402
import llm  # noqa: E402
import schema  # noqa: E402
from evals import scratchdb  # noqa: E402
from lib import dbconn, envfile  # noqa: E402

#: The pipeline's own .env, the way run-daily.py loads it -- see
#: tests/test_scratchdb.py, which does the same. Tests must not depend on the
#: caller having exported anything.
envfile.load(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), ".env"))

requires_db = unittest.skipUnless(
    scratchdb.available(),
    "no scratch database: set DATABASE_URL (or JOBS_SCRATCH_DATABASE_URL)")


#: One complete normalize()-shaped result. Tests mutate copies of this, so
#: every field job_facts stores is present in every vote and a new column
#: cannot be forgotten by a test that only builds the fields it cares about.
BASE = {
    "seniority_level": "junior",
    "years_experience_min": 2,
    "years_experience_max": 4,
    "role_archetype": "backend",
    "tech_stack": '["python"]',
    "ai_involvement": "uses_ai_tools",
    "ml_research_required": False,
    "advanced_degree_required": False,
    "customer_facing": True,
    "remote_policy": "hybrid",
    "employment_type": "full_time",
    "comp_min": 100000,
    "comp_max": 140000,
    "comp_currency": "USD",
    "gap_friendly_language": False,
    "visa_sponsorship": "unknown",
    "summary": "A backend role. It uses Python.",
}


def result(**overrides):
    return {**BASE, **overrides}


def job(platform, job_id="j1"):
    return {"id": job_id, "title": "Engineer", "company_name": "Acme",
            "location_raw": "NYC", "platform": platform,
            "description_text": "We are hiring an engineer."}


def response(**overrides):
    """A raw model response that normalize() will accept."""
    payload = {
        "seniority_level": "junior", "role_archetype": "backend",
        "remote_policy": "hybrid", "tech_stack": ["python"],
        "summary": "A backend role. It uses Python.",
    }
    payload.update(overrides)
    return json.dumps(payload)


class PolicyTests(unittest.TestCase):
    """The shipped config, read as extract.py reads it."""

    def setUp(self):
        self.policy = extract.load_policy()

    def test_only_hn_is_below_the_threshold(self):
        # The measured figures are task 06's, n=115, 2026-07-28. If a
        # re-measurement moves one, this is the test that says which
        # platforms changed cost.
        multi = {p for p in self.policy["measured_agreement"]
                 if extract.passes_for(p, self.policy) > 1}
        self.assertEqual(multi, {"hn_whoishiring"})

    def test_hn_gets_three_passes_and_everything_else_one(self):
        self.assertEqual(extract.passes_for("hn_whoishiring", self.policy), 3)
        for platform in ("greenhouse", "ashby", "google_jobs", "builtin",
                         "weworkremotely", "lever"):
            self.assertEqual(extract.passes_for(platform, self.policy), 1,
                             platform)

    def test_unmeasured_platform_gets_one_pass(self):
        # An unmeasured source is not a bad source. Tripling it would be
        # paying for a number nobody has -- and this is also what protects
        # the bill when a platform string is renamed.
        self.assertEqual(extract.passes_for("a_new_board", self.policy), 1)
        self.assertEqual(extract.passes_for(None, self.policy), 1)
        # "builtin", not "builtin-nyc" -- several task files write the latter.
        self.assertIn("builtin", self.policy["measured_agreement"])

    def test_missing_config_falls_back_to_one_pass_everywhere(self):
        with tempfile.TemporaryDirectory() as d:
            policy = extract.load_policy(os.path.join(d, "absent.json"))
        self.assertEqual(extract.passes_for("hn_whoishiring", policy), 1)

    def test_threshold_is_not_sitting_on_a_measured_value(self):
        # Documented in the config's _threshold_note: 0.90 has clear air
        # under it (0.778) and above it (0.911), so the decision does not
        # turn on a rounding difference.
        threshold = self.policy["agreement_threshold"]
        for platform, agreement in self.policy["measured_agreement"].items():
            self.assertNotAlmostEqual(agreement, threshold, places=3,
                                      msg=platform)


class CallCountTests(unittest.TestCase):
    """Decision A1's actual claim: how many calls each platform costs."""

    def _count_calls(self, platform):
        calls = []

        def fake_call(prompt):
            calls.append(prompt)
            return response()

        outcome, facts, passes, unanimity = extract.extract_facts(
            job(platform), call=fake_call)
        return calls, outcome, facts, passes, unanimity

    def test_hn_whoishiring_makes_three_calls_and_votes(self):
        calls, outcome, facts, passes, unanimity = self._count_calls(
            "hn_whoishiring")
        self.assertEqual(len(calls), 3)
        self.assertEqual(outcome, extract.EXTRACTED)
        self.assertEqual(passes, 3)
        # Three identical answers: unanimous on every voted field.
        self.assertEqual(unanimity, 1.0)
        # Same prompt every pass -- the cache prefix argument in the module
        # docstring depends on the instruction block being byte-identical.
        self.assertEqual(len(set(calls)), 1)

    def test_every_other_platform_makes_exactly_one_call(self):
        for platform in ("greenhouse", "ashby", "google_jobs", "builtin",
                         "weworkremotely", "lever", "some_future_source"):
            calls, outcome, facts, passes, unanimity = self._count_calls(platform)
            self.assertEqual(len(calls), 1, platform)
            self.assertEqual(passes, 1, platform)
            # NULL, not 1.0: one pass has no agreement to report.
            self.assertIsNone(unanimity, platform)

    def test_three_passes_actually_disagreeing_produce_the_majority(self):
        answers = iter([response(seniority_level="junior"),
                        response(seniority_level="mid"),
                        response(seniority_level="junior")])
        outcome, facts, passes, unanimity = extract.extract_facts(
            job("hn_whoishiring"), call=lambda p: next(answers))
        self.assertEqual(facts["seniority_level"], "junior")
        self.assertEqual(passes, 3)
        self.assertLess(unanimity, 1.0)

    def test_a_transient_pass_does_not_discard_the_usable_ones(self):
        answers = [response(), llm.TransientError("429"), llm.TransientError("429")]

        def flaky(prompt):
            item = answers.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

        outcome, facts, passes, unanimity = extract.extract_facts(
            job("hn_whoishiring"), call=flaky)
        self.assertEqual(outcome, extract.EXTRACTED)
        # Records what the row GOT, not what the policy asked for.
        self.assertEqual(passes, 1)
        self.assertIsNone(unanimity)

    def test_all_passes_transient_defers_and_writes_nothing(self):
        def always_429(prompt):
            raise llm.TransientError("429")

        outcome, facts, passes, unanimity = extract.extract_facts(
            job("hn_whoishiring"), call=always_429)
        self.assertEqual(outcome, extract.DEFERRED)
        self.assertIsNone(facts)

    def test_all_passes_unusable_is_a_tombstone_not_a_defer(self):
        # Every pass answered; none of the answers were usable. That is
        # evidence about the posting, so it earns a tombstone -- the
        # distinction score.py's three-way split exists to preserve.
        outcome, facts, passes, unanimity = extract.extract_facts(
            job("hn_whoishiring"), call=lambda p: "not json at all")
        self.assertEqual(outcome, extract.REJECTED)
        self.assertIsNone(facts)


class VoteTests(unittest.TestCase):
    """vote_facts is pure: no database, no clock, no endpoint."""

    def test_every_stored_column_has_a_voting_rule(self):
        covered = (extract.VOTE_ENUM_FIELDS + extract.VOTE_BOOL_FIELDS
                   + extract.VOTE_INT_FIELDS + extract.VOTE_CARRIED_FIELDS)
        self.assertEqual(sorted(covered), sorted(extract._FACT_COLUMNS))
        self.assertEqual(len(covered), len(set(covered)))

    def test_single_pass_is_returned_unchanged_with_no_unanimity(self):
        facts, unanimity = extract.vote_facts([result()])
        self.assertEqual(facts, BASE)
        self.assertIsNone(unanimity)

    def test_single_pass_result_is_a_copy(self):
        original = result()
        facts, _ = extract.vote_facts([original])
        facts["seniority_level"] = "staff"
        self.assertEqual(original["seniority_level"], "junior")

    def test_enum_majority(self):
        facts, _ = extract.vote_facts([
            result(seniority_level="mid"),
            result(seniority_level="junior"),
            result(seniority_level="junior"),
        ])
        self.assertEqual(facts["seniority_level"], "junior")

    def test_enum_three_way_tie_falls_back_to_the_first_pass(self):
        # Pinned deliberately: with three different answers the vote has no
        # information, and the first pass's value is exactly what this script
        # stored before voting existed. The fallback is never worse than the
        # behaviour it replaces.
        facts, unanimity = extract.vote_facts([
            result(ai_involvement="none"),
            result(ai_involvement="uses_ai_tools"),
            result(ai_involvement="builds_llm_features"),
        ])
        self.assertEqual(facts["ai_involvement"], "none")
        self.assertLess(unanimity, 1.0)

    def test_enum_none_votes(self):
        # None means "the posting does not say", which is an answer.
        facts, _ = extract.vote_facts([
            result(seniority_level=None),
            result(seniority_level=None),
            result(seniority_level="senior"),
        ])
        self.assertIsNone(facts["seniority_level"])

    def test_bool_majority(self):
        facts, _ = extract.vote_facts([
            result(customer_facing=True),
            result(customer_facing=False),
            result(customer_facing=False),
        ])
        self.assertFalse(facts["customer_facing"])

    def test_bool_two_of_three_true(self):
        facts, _ = extract.vote_facts([
            result(gap_friendly_language=True),
            result(gap_friendly_language=True),
            result(gap_friendly_language=False),
        ])
        self.assertTrue(facts["gap_friendly_language"])

    def test_int_median_not_mode(self):
        # 3, 3, 4 has a mode; 3, 4, 5 does not, and a majority vote would
        # fall back to an arbitrary pass. The median is defined for both.
        facts, _ = extract.vote_facts([
            result(years_experience_min=3),
            result(years_experience_min=4),
            result(years_experience_min=5),
        ])
        self.assertEqual(facts["years_experience_min"], 4)

    def test_int_median_ignores_a_lone_none(self):
        facts, _ = extract.vote_facts([
            result(comp_min=None),
            result(comp_min=100000),
            result(comp_min=120000),
        ])
        self.assertEqual(facts["comp_min"], 100000)   # lower middle of two

    def test_int_majority_none_wins(self):
        facts, _ = extract.vote_facts([
            result(comp_max=None),
            result(comp_max=None),
            result(comp_max=200000),
        ])
        self.assertIsNone(facts["comp_max"])

    def test_int_all_none_stays_none(self):
        facts, _ = extract.vote_facts([
            result(years_experience_max=None),
            result(years_experience_max=None),
            result(years_experience_max=None),
        ])
        self.assertIsNone(facts["years_experience_max"])

    def test_int_median_never_invents_a_value(self):
        # The lower of the two middle values, not their mean: 3 and 5 must
        # not become a 4 that no pass produced and no posting contains.
        facts, _ = extract.vote_facts([
            result(years_experience_min=3),
            result(years_experience_min=5),
        ])
        self.assertIn(facts["years_experience_min"], (3, 5))
        self.assertEqual(facts["years_experience_min"], 3)

    def test_prose_is_carried_whole_from_the_pass_the_vote_endorsed(self):
        # Pass 2 and 3 agree on the enums, so the summary and tech_stack come
        # from pass 2 -- not merged, not from the outvoted pass 1.
        facts, _ = extract.vote_facts([
            result(seniority_level="staff", summary="Outvoted.",
                   tech_stack='["cobol"]'),
            result(seniority_level="junior", summary="Endorsed.",
                   tech_stack='["python"]'),
            result(seniority_level="junior", summary="Also endorsed.",
                   tech_stack='["python", "sql"]'),
        ])
        self.assertEqual(facts["seniority_level"], "junior")
        self.assertEqual(facts["summary"], "Endorsed.")
        self.assertEqual(facts["tech_stack"], '["python"]')

    def test_prose_tie_goes_to_the_earliest_matching_pass(self):
        facts, _ = extract.vote_facts([
            result(summary="First."),
            result(summary="Second."),
            result(summary="Third."),
        ])
        self.assertEqual(facts["summary"], "First.")

    def test_prose_is_never_merged(self):
        facts, _ = extract.vote_facts([
            result(tech_stack='["python"]'),
            result(tech_stack='["python", "go"]'),
            result(tech_stack='["rust"]'),
        ])
        # Whatever it picks, it is one pass's answer verbatim -- never a
        # union (which accumulates hallucinations) or an intersection (which
        # deletes what two passes named).
        self.assertIn(facts["tech_stack"],
                      ('["python"]', '["python", "go"]', '["rust"]'))

    def test_unanimity_is_the_fraction_of_voted_fields_agreeing(self):
        n_voted = (len(extract.VOTE_ENUM_FIELDS) + len(extract.VOTE_BOOL_FIELDS)
                   + len(extract.VOTE_INT_FIELDS))
        facts, unanimity = extract.vote_facts([
            result(seniority_level="mid"), result(), result()])
        self.assertAlmostEqual(unanimity, (n_voted - 1) / n_voted)

        # Prose is excluded from the count -- three different summaries of
        # the same posting are not a disagreement about the posting.
        facts, unanimity = extract.vote_facts([
            result(summary="One."), result(summary="Two."),
            result(summary="Three.")])
        self.assertEqual(unanimity, 1.0)

    def test_vote_needs_at_least_one_result(self):
        with self.assertRaises(ValueError):
            extract.vote_facts([])

    def test_vote_does_not_mutate_its_inputs(self):
        results = [result(seniority_level="mid"), result(), result()]
        snapshot = json.dumps(results, sort_keys=True)
        extract.vote_facts(results)
        self.assertEqual(json.dumps(results, sort_keys=True), snapshot)


class DrainLoopTests(unittest.TestCase):
    """The 40/day ceiling, and the ways draining it could go wrong."""

    def _loop(self, batches, deadline=1000, clock=None):
        """Run drain_loop over a scripted list of (jobs, outcomes) batches."""
        script = list(batches)
        seen = []

        def fetch():
            return script[len(seen)][0] if len(seen) < len(script) else []

        def run(jobs):
            seen.append(jobs)
            return Counter(script[len(seen) - 1][1])

        kwargs = {"clock": clock} if clock else {}
        return extract.drain_loop(fetch, run, deadline, **kwargs), seen

    def test_drains_until_the_backlog_is_empty(self):
        (totals, batches, stopped), seen = self._loop([
            (["a"] * 40, {extract.EXTRACTED: 40}),
            (["b"] * 40, {extract.EXTRACTED: 38, extract.REJECTED: 2}),
            (["c"] * 5, {extract.EXTRACTED: 5}),
        ])
        self.assertEqual(stopped, extract.DRAINED)
        self.assertEqual(batches, 3)
        self.assertEqual(totals[extract.EXTRACTED], 83)
        self.assertEqual(totals[extract.REJECTED], 2)

    def test_nothing_to_do_runs_no_batches(self):
        (totals, batches, stopped), seen = self._loop([])
        self.assertEqual(batches, 0)
        self.assertEqual(stopped, extract.DRAINED)
        self.assertEqual(seen, [])

    def test_zero_progress_batch_breaks_the_loop(self):
        # THE ONE THAT MATTERS. Every call deferred, so the same rows stay
        # eligible and the next fetch would return them again. Without this
        # break the loop spins against a rate-limited endpoint until the
        # deadline burns -- strictly worse than the single batch it replaces.
        (totals, batches, stopped), seen = self._loop([
            (["a"] * 40, {extract.EXTRACTED: 40}),
            (["b"] * 40, {extract.DEFERRED: 40}),
            (["b"] * 40, {extract.DEFERRED: 40}),
            (["b"] * 40, {extract.DEFERRED: 40}),
        ])
        self.assertEqual(stopped, extract.NO_PROGRESS)
        self.assertEqual(batches, 2)
        self.assertEqual(len(seen), 2)

    def test_one_rejection_still_counts_as_progress(self):
        # A batch where every call came back unusable is progress: those rows
        # were tombstoned and will not be selected again.
        (totals, batches, stopped), seen = self._loop([
            (["a"] * 40, {extract.REJECTED: 40}),
            (["b"] * 40, {extract.DEFERRED: 40}),
        ])
        self.assertEqual(stopped, extract.NO_PROGRESS)
        self.assertEqual(batches, 2)

    def test_deadline_stops_the_loop_between_batches(self):
        ticks = iter([0, 5, 10, 15, 20, 25])
        (totals, batches, stopped), seen = self._loop(
            [(["a"] * 40, {extract.EXTRACTED: 40})] * 10,
            deadline=10, clock=lambda: next(ticks))
        self.assertEqual(stopped, extract.DEADLINE_HIT)
        # start=0 so deadline=10; batch 1 runs unconditionally, the check
        # before batch 2 reads 5 (<10) and runs it, the check before batch 3
        # reads 10 and stops.
        self.assertEqual(batches, 2)

    def test_the_first_batch_always_runs_however_late_it_is(self):
        # One batch per invocation is the old behaviour and the floor this
        # must never fall below -- a deadline already in the past must not
        # turn the nightly run into a no-op.
        ticks = iter([0, 9999, 9999])
        (totals, batches, stopped), seen = self._loop(
            [(["a"] * 40, {extract.EXTRACTED: 40})] * 3,
            deadline=0, clock=lambda: next(ticks))
        self.assertEqual(batches, 1)
        self.assertEqual(stopped, extract.DEADLINE_HIT)

    def test_deadline_is_never_checked_mid_batch(self):
        # The clock is read once per iteration, not per job: a batch that
        # starts is always finished, so the overshoot is bounded by one batch
        # and no posting is left half-extracted.
        reads = []

        def clock():
            reads.append(len(reads))
            return len(reads) * 100

        self._loop([(["a"] * 40, {extract.EXTRACTED: 40})] * 3,
                   deadline=1000, clock=clock)
        self.assertLessEqual(len(reads), 4)   # one start + one per iteration


@requires_db
class SchemaAndSelectionTests(unittest.TestCase):
    """The parts a fake connection structurally cannot check.

    Two claims here are about Postgres rather than about Python: that
    ensure_schema() creates the stability columns on a FRESH database (the
    migration only covers databases that already exist, and a schema whose
    two paths disagree is the drift schema.py:5-8 exists to prevent), and
    that select_unextracted_jobs' ORDER BY does what its docstring says when
    stale and never-extracted rows are mixed. The second cannot be asserted
    against production because production currently has no stale rows.
    """

    def _insert_job(self, conn, job_id, first_seen):
        conn.execute(
            "INSERT INTO jobs (id, platform, company_token, company_name, "
            "source_id, title, description_text, status, first_seen, "
            "last_seen) VALUES (%s, 'greenhouse', 'acme', 'Acme', %s, "
            "'Engineer', 'We are hiring an engineer.', %s, %s, %s)",
            (job_id, job_id, schema.STATUS_OPEN, first_seen, first_seen))

    def test_ensure_schema_creates_the_stability_columns(self):
        with scratchdb.scratch_schema() as (conn, _name):
            cols = dbconn.existing_columns(conn, schema.FACTS_TABLE)
            self.assertIn("extraction_passes", cols)
            self.assertIn("vote_unanimity", cols)

    def test_update_job_facts_writes_the_stability_columns(self):
        with scratchdb.scratch_schema() as (conn, _name):
            self._insert_job(conn, "j1", "2026-07-01T00:00:00")
            conn.commit()
            facts, unanimity = extract.vote_facts(
                [result(), result(), result(seniority_level="mid")])
            extract.update_job_facts(conn, "j1", facts, "test-model",
                                     passes=3, unanimity=unanimity)
            row = conn.execute(
                "SELECT extraction_passes, vote_unanimity, seniority_level "
                "FROM job_facts WHERE job_id = 'j1'").fetchone()
            self.assertEqual(row[0], 3)
            self.assertAlmostEqual(row[1], unanimity, places=5)
            self.assertEqual(row[2], "junior")

    def test_selection_is_never_extracted_first_then_fifo(self):
        with scratchdb.scratch_schema() as (conn, _name):
            # Two never extracted (one old, one new) and two carrying a
            # STALE facts row -- the state a FACTS_VERSION bump produces.
            self._insert_job(conn, "new-never", "2026-07-20T00:00:00")
            self._insert_job(conn, "old-never", "2026-07-01T00:00:00")
            self._insert_job(conn, "new-stale", "2026-07-21T00:00:00")
            self._insert_job(conn, "old-stale", "2026-07-02T00:00:00")
            for job_id in ("new-stale", "old-stale"):
                conn.execute(
                    "INSERT INTO job_facts (job_id, facts_version, "
                    "extracted_at) VALUES (%s, %s, '2026-07-01T00:00:00')",
                    (job_id, schema.FACTS_VERSION - 1))
            # And one already current, which must not be selected at all.
            self._insert_job(conn, "current", "2026-07-22T00:00:00")
            conn.execute(
                "INSERT INTO job_facts (job_id, facts_version, extracted_at) "
                "VALUES ('current', %s, '2026-07-01T00:00:00')",
                (schema.FACTS_VERSION,))
            conn.commit()

            cfgs = [dict(extract.relevance.DISABLED)]
            picked = [j["id"] for j in
                      extract.select_unextracted_jobs(conn, 10, cfgs)]
            self.assertEqual(picked,
                             ["old-never", "new-never", "old-stale", "new-stale"])
            # remaining() must agree with what selection can see, or the
            # summary line reports a backlog no batch will ever burn down.
            self.assertEqual(extract.remaining(conn, cfgs), len(picked))

    def test_a_tombstone_is_not_reselected(self):
        with scratchdb.scratch_schema() as (conn, _name):
            self._insert_job(conn, "dead", "2026-07-01T00:00:00")
            conn.commit()
            extract.mark_extract_failed(conn, "dead", "test-model")
            cfgs = [dict(extract.relevance.DISABLED)]
            self.assertEqual(extract.select_unextracted_jobs(conn, 10, cfgs), [])
            self.assertEqual(extract.remaining(conn, cfgs), 0)


if __name__ == "__main__":
    unittest.main()
