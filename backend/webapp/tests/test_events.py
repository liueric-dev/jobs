"""The event vocabulary and the LIKE escaping.

job_events.event is free TEXT, so the closed set in jobs.EVENT_NAMES is the
only thing keeping the table analysable for the learned ranker described in
../docs/SCORING.md. A typo'd event name is worse than a rejected one: it is
silently unusable training data that nobody notices for a year.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import jobs  # noqa: E402


def batch(events, request_id="req_test"):
    """An EventBatch from terse dicts, defaulting the required request_id."""
    return jobs.EventBatch(events=events, request_id=request_id)


class TestEventNames(unittest.TestCase):

    def test_the_closed_set(self):
        # Pinned literally. Adding a name is a deliberate act that should
        # require editing this line, because every addition is a new column of
        # meaning in a table meant to be read years from now.
        self.assertEqual(
            set(jobs.CLIENT_EVENT_NAMES),
            {"impression", "open", "save", "unsave", "dismiss", "undismiss",
             "applied"})

    def test_every_undo_has_something_to_undo(self):
        # `unsave` and `undismiss` are undos, and an undo whose forward event
        # does not exist is a client contract nobody can satisfy. Cheap to
        # state, and it is the property that would break if a future event were
        # added as an "un" name first.
        for undo in ("unsave", "undismiss"):
            self.assertIn(undo, jobs.CLIENT_EVENT_NAMES)
            self.assertIn(undo.removeprefix("un"), jobs.CLIENT_EVENT_NAMES)

    def test_skip_is_server_only_and_storable(self):
        # The two tuples answer two different questions and the bug this guards
        # against is answering one with the other: `skip` must be REJECTED from
        # a client and ACCEPTED into the table. A single set could not be both.
        self.assertEqual(set(jobs.SERVER_EVENT_NAMES), {"skip"})
        self.assertNotIn("skip", jobs.CLIENT_EVENT_NAMES)
        self.assertIn("skip", jobs.EVENT_NAMES)

    def test_the_two_tuples_do_not_overlap(self):
        self.assertEqual(
            set(jobs.CLIENT_EVENT_NAMES) & set(jobs.SERVER_EVENT_NAMES), set())

    def test_batch_validation_rejects_unknown_names(self):
        with self.assertRaises(jobs.ContractError) as caught:
            jobs.validate_batch(batch([
                {"job_id": "a", "event": "impression", "rank": 1},
                {"job_id": "b", "event": "clicked"},      # not in the set
            ]))
        self.assertEqual(caught.exception.code, "unknown_event")

    def test_a_client_sent_skip_is_rejected_by_its_own_name(self):
        # Not "unknown_event": the client author's mistake is a category error,
        # not a typo, and the message has to say which.
        with self.assertRaises(jobs.ContractError) as caught:
            jobs.validate_batch(batch([{"job_id": "a", "event": "skip", "rank": 3}]))
        self.assertEqual(caught.exception.code, "server_derived_event")

    def test_batch_is_capped(self):
        # A page of impressions is one request; an unbounded list is a way to
        # make one request cost an arbitrary number of inserts.
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            batch([{"job_id": str(i), "event": "impression", "rank": i + 1}
                   for i in range(201)])

    def test_dedup_window(self):
        self.assertEqual(jobs.IMPRESSION_DEDUP_HOURS, 24)


class TestBatchValidation(unittest.TestCase):
    """The 400s. Every one of them fails the WHOLE batch, deliberately.

    A partially-accepted impression batch is the worst outcome available: the
    render's rank sequence acquires holes indistinguishable from items the user
    never scrolled to, and nothing downstream can tell the two apart.
    """

    def test_request_id_is_required(self):
        with self.assertRaises(jobs.ContractError) as caught:
            jobs.validate_batch(
                jobs.EventBatch(events=[{"job_id": "a", "event": "impression",
                                         "rank": 1}]))
        self.assertEqual(caught.exception.code, "missing_request_id")

    def test_an_impression_without_a_rank_is_rejected(self):
        with self.assertRaises(jobs.ContractError) as caught:
            jobs.validate_batch(batch([{"job_id": "a", "event": "impression"}]))
        self.assertEqual(caught.exception.code, "missing_rank")

    def test_an_open_without_a_rank_is_rejected(self):
        # open carries rank for a second reason beyond debiasing: it is the
        # entire input to the skip derivation.
        with self.assertRaises(jobs.ContractError) as caught:
            jobs.validate_batch(batch([{"job_id": "a", "event": "open"}]))
        self.assertEqual(caught.exception.code, "missing_rank")

    def test_a_rankless_save_is_allowed(self):
        # THE ONE DELIBERATE DEVIATION from API-CONTRACT-v1.md's "reject a batch
        # missing request_id or any rank", and the contract's own text is the
        # reason: it says a detail-page request "is not an impression", so a
        # save raised from GET /v1/jobs/{id} has no position in any render.
        # Requiring one there would force the client to invent a value, which
        # is the sentinel the schema refused, wearing different clothes.
        jobs.validate_batch(batch([{"job_id": "a", "event": "save"}]))

    def test_rank_must_be_one_based(self):
        # A 0 would silently halve the value of every debiasing correction
        # computed from these rows.
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            jobs.Event(job_id="a", event="impression", rank=0)

    def test_the_dismiss_vocabulary_is_closed(self):
        # Pinned literally, like the event names and for the same reason: each
        # value maps onto a feature -- a wrong_level dismiss is evidence about
        # the seniority weight -- and free text is un-joinable to any of them.
        self.assertEqual(
            set(jobs.DISMISS_REASONS),
            {"wrong_level", "wrong_role", "wrong_location", "bad_company",
             "stale_posting", "other"})

    def test_an_unknown_reason_is_rejected(self):
        with self.assertRaises(jobs.ContractError) as caught:
            jobs.validate_batch(batch([{"job_id": "a", "event": "dismiss",
                                        "rank": 2, "reason": "meh"}]))
        self.assertEqual(caught.exception.code, "unknown_reason")

    def test_a_reason_on_a_non_dismiss_is_rejected(self):
        with self.assertRaises(jobs.ContractError) as caught:
            jobs.validate_batch(batch([{"job_id": "a", "event": "save",
                                        "reason": "wrong_level"}]))
        self.assertEqual(caught.exception.code, "reason_not_allowed")

    def test_a_reason_on_an_undismiss_is_rejected(self):
        # The near miss the rule above exists for: `undismiss` is the one other
        # event a reason reads as plausible on, and it is exactly where one
        # would be wrong. The reason belongs to the dismissal being reversed
        # and is already on that row; a second one here would be a fact about a
        # decision nobody made.
        with self.assertRaises(jobs.ContractError) as caught:
            jobs.validate_batch(batch([{"job_id": "a", "event": "undismiss",
                                        "reason": "wrong_level"}]))
        self.assertEqual(caught.exception.code, "reason_not_allowed")

    def test_an_undismiss_needs_no_rank(self):
        # It is raised from wherever the Builder happens to be -- a detail
        # page, a saved list -- and has no position in any render. Requiring a
        # rank would force a client to invent one.
        jobs.validate_batch(batch([{"job_id": "a", "event": "undismiss"}]))

    def test_dwell_is_open_only(self):
        with self.assertRaises(jobs.ContractError) as caught:
            jobs.validate_batch(batch([{"job_id": "a", "event": "impression",
                                        "rank": 1, "dwell_ms": 900}]))
        self.assertEqual(caught.exception.code, "dwell_not_allowed")

    def test_a_valid_full_batch_passes(self):
        jobs.validate_batch(batch([
            {"job_id": "a", "event": "impression", "rank": 1},
            {"job_id": "b", "event": "open", "rank": 2, "dwell_ms": 14200},
            {"job_id": "c", "event": "dismiss", "rank": 3, "reason": "wrong_level"},
            {"job_id": "d", "event": "applied", "rank": 4},
        ]))

    def test_the_error_envelope_carries_the_render(self):
        # The contract's error shape includes request_id so a 400 can be tied
        # back to the render that produced it in a log nobody was watching live.
        err = jobs.ContractError("missing_rank", "…", "req_abc")
        self.assertEqual(err.request_id, "req_abc")
        self.assertEqual(err.status_code, 400)


class TestVisibility(unittest.TestCase):
    """A privacy control the client can set is not one."""

    def test_only_a_save_is_cohort_visible(self):
        self.assertEqual(jobs.visibility_for("save"), jobs.VISIBILITY_COHORT)

    def test_an_application_is_private(self):
        # Stated as a product decision, not an oversight: in a cohort competing
        # for the same entry-level roles, seeing who else applied is
        # discouraging at best.
        self.assertEqual(jobs.visibility_for("applied"), jobs.VISIBILITY_PRIVATE)

    def test_everything_else_is_private(self):
        for name in ("impression", "open", "unsave", "dismiss", "undismiss",
                     "skip"):
            self.assertEqual(jobs.visibility_for(name), jobs.VISIBILITY_PRIVATE,
                             f"{name} must not be cohort-visible")

    def test_a_dismissal_is_never_aggregated_for_display(self):
        # tranche_six/31 is explicit: "18 Builders dismissed this" is
        # discouraging, deanonymising at small N, and reflects a cohort-wide
        # config problem more often than a bad posting. Task 28 aggregates
        # saves and only saves, and the mechanism enforcing that is this tuple
        # -- dismissals never carry the visibility the aggregation reads.
        self.assertEqual(set(jobs.COHORT_VISIBLE_EVENTS), {"save"})
        for name in ("dismiss", "undismiss"):
            self.assertNotIn(name, jobs.COHORT_VISIBLE_EVENTS)

    def test_the_client_cannot_name_a_visibility(self):
        # Not in the model at all, so there is no field to ignore. A field the
        # server silently overwrites is one a client author can reasonably
        # believe works.
        self.assertNotIn("visibility", jobs.Event.model_fields)
        self.assertNotIn("visibility", jobs.EventBatch.model_fields)

    def test_the_client_cannot_name_a_score_or_a_version(self):
        for field in ("match_score", "fit_score", "criteria_version"):
            self.assertNotIn(field, jobs.Event.model_fields)


class TestRequestId(unittest.TestCase):

    def test_ids_are_unique_and_prefixed(self):
        ids = {jobs.new_request_id() for _ in range(500)}
        self.assertEqual(len(ids), 500)
        self.assertTrue(all(i.startswith("req_") for i in ids))


class TestLikeEscaping(unittest.TestCase):

    def test_wildcards_in_user_input_are_escaped(self):
        # Without this, a search for '100%' matches every row and a search for
        # '_' matches every single character.
        self.assertEqual(jobs._like("100%"), "%100\\%%")
        self.assertEqual(jobs._like("a_b"), "%a\\_b%")

    def test_backslash_is_escaped_first(self):
        # Escaping backslash after the wildcards would double-escape the
        # escapes this function just added.
        self.assertEqual(jobs._like("a\\b"), "%a\\\\b%")

    def test_ordinary_terms_are_wrapped(self):
        self.assertEqual(jobs._like("engineer"), "%engineer%")


class TestListColumns(unittest.TestCase):

    def test_description_is_not_in_the_list_response(self):
        # The largest column in the database. The list has `summary` from
        # job_facts for this purpose; sending both on every page would be the
        # difference between a fast list and a slow one.
        self.assertNotIn("description_text", jobs.LIST_COLUMNS)
        self.assertIn("summary", jobs.LIST_COLUMNS)

    def test_detail_adds_the_description(self):
        self.assertIn("description_text", jobs.DETAIL_COLUMNS)
        self.assertEqual(set(jobs.LIST_COLUMNS) - set(jobs.DETAIL_COLUMNS), set())

    def test_ordering_sorts_on_the_sortable_timestamp(self):
        # posted_at is TEXT holding three incompatible formats, including Built
        # In's relative English ("Reposted 8 Hours Ago"), which no database can
        # order. Sorting on it would look fine and be wrong.
        self.assertIn("posted_at_ts", jobs.ORDER_BY)
        self.assertIn("match_score DESC", jobs.ORDER_BY)


if __name__ == "__main__":
    unittest.main()
