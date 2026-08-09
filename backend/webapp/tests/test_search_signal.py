"""Searches through the endpoints: registration, the badge, and what it hides.

WHY THESE ARE IN webapp/tests/ WHEN searchqueries.py IS PIPELINE CODE
    test_cohort_signal.py's two reasons, and both apply here unchanged.

    Every claim is about a WHERE clause or a GRANT, so it needs a real
    Postgres; test_event_replay.py already built the scratch-schema machinery
    for both sides' tables and this file reuses it rather than carrying a
    second copy that can drift.

    And this is the only interpreter that can import BOTH searchqueries.py and
    webapp/search.py -- the pipeline must not import fastapi, so the pipeline
    suite can exercise searchnorm's SQL constants against a schema but can
    never see the endpoint that executes them. The tests that matter most here
    are exactly the ones that need both halves: that the ROUTE returns null for
    a two-watcher search, and that the route and the fold agree on the floor.

WHAT IS BEING PINNED, IN ONE SENTENCE EACH
    * Two Builders watching a search produce NO badge. Not a small one.
    * Two Builders submitting the same words produce ONE row, TWO watchers and
      ONE due query -- the entire cost argument in tranche_four/25.
    * The endpoint reads the materialised table and gets null when that table
      is empty, even with three watchers sitting in search_query_watchers.
    * No identity, no exact count and no recency reaches any response.
    * Results come through jobs_app, so a posting the gate rejected is
      invisible however it got into the results table.
"""

import contextlib
import os
import sys
import unittest
import unittest.mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
#: This directory too, so `test_event_replay` below imports under BOTH
#: invocations -- see test_cohort_signal.py, which needs the same two entries
#: for the same reason.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config  # noqa: F401,E402  (must come first -- performs the sys.path insert)

import schema                                           # noqa: E402
import schema_web                                       # noqa: E402
import search                                           # noqa: E402
import searchnorm                                       # noqa: E402
import searchqueries                                    # noqa: E402
from auth import User                                   # noqa: E402

from test_event_replay import (                          # noqa: E402
    PROFILE, USER, USER_B, requires_db, seed_users, web_scratch_schema)

#: A third and a fourth Builder. Four is the floor, so the smallest cohort that
#: can produce a badge at all has four people in it, and proving that the fold
#: SUBTRACTS requires being able to take one away and still have three.
USER_C = User(id="u_search_c", email="search-c@example.test",
              display_name="Search C", profile=PROFILE, is_admin=False)
USER_D = User(id="u_search_d", email="search-d@example.test",
              display_name="Search D", profile=PROFILE, is_admin=False)
ALL_FOUR = (USER, USER_B, USER_C, USER_D)


@contextlib.contextmanager
def redirect_db(conn):
    """Point search.db at the scratch connection for the duration.

    A separate helper from test_event_replay.redirect_db because that one
    rebinds `jobs.db`, and these routes live in another module with its own
    import of the same name. Rebinding one does not rebind the other, which is
    a silent no-op rather than an error -- the route would open a real
    connection to the `jobs_web` role and find none of the scratch tables.
    """
    @contextlib.contextmanager
    def fake_db():
        yield conn

    original = search.db
    search.db = fake_db
    try:
        yield
    finally:
        search.db = original


def watch(conn, query_id, user, now="2026-08-02T00:00:00"):
    conn.execute(searchnorm.REGISTER_WATCHER_SQL,
                 (query_id, user.id, user.profile, now))
    conn.commit()


class TestTheFloorAgreesAcrossTheProcessBoundary(unittest.TestCase):
    """The vocabulary is not duplicated here -- both sides import schema.py --
    and these assertions exist to keep it that way."""

    def test_the_route_and_the_fold_read_one_constant(self):
        # If either side ever grows its own copy of the floor, this is what
        # fails. cohort.py duplicates the EVENT vocabulary across the boundary
        # because the pipeline must not import fastapi; the threshold has no
        # such excuse and is imported, so there is nothing to drift.
        self.assertIs(search.schema, schema)
        self.assertIs(searchqueries.schema, schema)

    def test_the_floor_is_four_and_the_neighbour_is_three(self):
        self.assertEqual(schema.SEARCH_MIN_WATCHERS, 4)
        self.assertEqual(schema.COHORT_MIN_SAVERS, 3)

    def test_the_signal_table_is_declared_select_only(self):
        # The design decision this whole task rests on, asserted at the layer
        # that enforces it. cohort_signal's entry in REQUIRED_TABLES states the
        # rule; this is the same rule for the same reason.
        self.assertEqual(schema_web.REQUIRED_TABLES["search_query_signal"],
                         ("SELECT",))
        self.assertEqual(schema_web.REQUIRED_TABLES["search_query_results"],
                         ("SELECT",))

    def test_the_service_may_register_but_not_schedule(self):
        self.assertEqual(schema_web.REQUIRED_TABLES["search_queries"],
                         ("SELECT", "INSERT"))
        self.assertNotIn("UPDATE", schema_web.REQUIRED_TABLES["search_queries"])

    def test_the_bigserial_sequence_is_granted(self):
        # search_queries.id is BIGSERIAL and this service INSERTs into it, so
        # INSERT on the table alone is a permission error at nextval() -- the
        # exact failure REQUIRED_SEQUENCES was added for.
        self.assertIn("search_queries_id_seq", schema_web.REQUIRED_SEQUENCES)


@requires_db
class TestTwoBuildersOneRow(unittest.TestCase):
    """The cost argument, through the actual route."""

    def submit(self, text, user, location=None):
        return search.create_search(
            search.SearchRequest(text=text, location=location), user=user)

    def test_two_builders_one_row_two_watchers_one_due_query(self):
        with web_scratch_schema() as (conn, _name):
            seed_users(conn, USER, USER_B)
            with redirect_db(conn):
                first = self.submit("AI Operations", USER)
                second = self.submit("  ai   operations!  ", USER_B)

            self.assertEqual(first["id"], second["id"])
            self.assertEqual(
                conn.execute("SELECT count(*) FROM search_queries").fetchone()[0], 1)
            self.assertEqual(
                conn.execute("SELECT count(*) FROM search_query_watchers "
                             "WHERE removed_at IS NULL").fetchone()[0], 2)
            # ONE provider call is what the row count buys: the runner
            # dispatches per due QUERY, not per watcher and not per submission.
            due = searchqueries.due_queries(conn, now="2026-08-02T01:00:00")
            self.assertEqual(len(due), 1)

    def test_the_second_builder_sees_the_firsts_spelling(self):
        with web_scratch_schema() as (conn, _name):
            seed_users(conn, USER, USER_B)
            with redirect_db(conn):
                self.submit("AI Operations", USER)
                second = self.submit("ai operations", USER_B)
            self.assertEqual(second["text"], "AI Operations")

    def test_a_different_location_is_a_different_search(self):
        with web_scratch_schema() as (conn, _name):
            seed_users(conn, USER)
            with redirect_db(conn):
                a = self.submit("data analyst", USER, location="Brooklyn, NY")
                b = self.submit("data analyst", USER, location="New York, NY")
            self.assertNotEqual(a["id"], b["id"])

    def test_an_empty_query_is_a_contract_error(self):
        with web_scratch_schema() as (conn, _name):
            seed_users(conn, USER)
            with redirect_db(conn):
                with self.assertRaises(search.ContractError) as caught:
                    self.submit("!!! ???", USER)
        self.assertEqual(caught.exception.code, "empty_query")

    def test_the_per_builder_cap_warns_and_does_not_refuse(self):
        # T-33, and the assertion that used to be here was the opposite one:
        # this raised ContractError("too_many_searches") at a constant 20.
        # docs/adr/0007 decision 5 makes a watch row a saved keyword and a
        # discovery surface, so the plan advises and never refuses -- if this
        # ever goes back to raising, the block has returned under a new name.
        cap = search.plan_cap()
        self.assertIsNotNone(cap, "config/serp-quota.json must yield a cap")
        with web_scratch_schema() as (conn, _name):
            seed_users(conn, USER)
            with redirect_db(conn):
                for i in range(cap):
                    row = self.submit(f"search number {i}", USER)
                    # Not one warning on the way UP to the cap.
                    self.assertIsNone(row["warning"], f"warned at {i}")
                past = self.submit("one past the cap", USER)
        # It SUCCEEDED -- there is a row, the Builder watches it -- and the
        # warning rides along beside it rather than replacing it.
        self.assertTrue(past["watching"])
        self.assertIsNotNone(past["id"])
        self.assertEqual(past["warning"]["code"], "watching_past_plan")
        self.assertIn(str(cap), past["warning"]["message"])

    def test_the_cap_is_read_from_the_plan_rather_than_written_down(self):
        # The whole of T-33 in one assertion: change the plan, the cap moves.
        # A constant restored anywhere on this path passes every test above
        # this one and fails this one.
        small = self._with_plan({"serpapi": {"allowance": 31, "reserve": 0}})
        large = self._with_plan({"serpapi": {"allowance": 3100, "reserve": 0}})
        self.assertLess(small, large)
        # And an account the pipeline cannot see paces nothing rather than
        # capping at zero -- searchnorm.run_allowance()'s direction, inherited.
        self.assertIsNone(self._with_plan({"serpapi": {"allowance": None}}))
        self.assertIsNone(self._with_plan({}))

    def _with_plan(self, providers):
        # `providers` and not `config` -- this module imports a module by that
        # name at the top and shadowing it is an F811 ruff can see.
        with unittest.mock.patch.object(search.quota, "load_config",
                                        return_value=providers):
            return search.plan_cap()

    def test_an_unknown_plan_warns_about_nothing(self):
        # No cap is not a cap of zero. A vendor config this process cannot read
        # must not turn every save into a warning a Builder cannot act on.
        with web_scratch_schema() as (conn, _name):
            seed_users(conn, USER)
            with redirect_db(conn), unittest.mock.patch.object(
                    search.quota, "load_config", return_value={}):
                rows = [self.submit(f"unpaced {i}", USER) for i in range(3)]
        self.assertEqual([r["warning"] for r in rows], [None, None, None])

    def test_resubmitting_a_watched_search_is_not_warned(self):
        # The cap must not make a Builder's own existing search unreachable --
        # and must not nag about it either. Re-submitting something already
        # watched adds nothing to the night, so there is nothing to warn about.
        cap = search.plan_cap()
        with web_scratch_schema() as (conn, _name):
            seed_users(conn, USER)
            with redirect_db(conn):
                for i in range(cap):
                    self.submit(f"search number {i}", USER)
                again = self.submit("search number 0", USER)
        self.assertTrue(again["watching"])
        self.assertIsNone(again["warning"])

    def test_the_watch_route_warns_on_the_same_footing(self):
        # Counted over WATCHES, so the catalogue is not a way around the
        # advice: watching a query somebody else typed puts the same query
        # into the night as typing it.
        cap = search.plan_cap()
        with web_scratch_schema() as (conn, _name):
            seed_users(conn, USER, USER_B)
            with redirect_db(conn):
                theirs = self.submit("somebody else's search", USER_B)
                for i in range(cap):
                    self.submit(f"search number {i}", USER)
                taken = search.watch_search(theirs["id"], user=USER)
        self.assertTrue(taken["watching"])
        self.assertEqual(taken["warning"]["code"], "watching_past_plan")


@requires_db
class TestSuppression(unittest.TestCase):
    """Below the floor, nothing is said -- through the route, not just the fold."""

    def make(self, conn, users):
        seed_users(conn, *ALL_FOUR)
        with redirect_db(conn):
            row = search.create_search(
                search.SearchRequest(text="ai operations"), user=users[0])
        for user in users[1:]:
            watch(conn, row["id"], user)
        return row["id"]

    def test_two_builders_produce_no_badge_rather_than_a_small_one(self):
        with web_scratch_schema() as (conn, _name):
            query_id = self.make(conn, (USER, USER_B))
            searchqueries.refresh(conn, PROFILE, now="2026-08-02T02:00:00")
            with redirect_db(conn):
                row = search.get_search(query_id, user=USER)
        self.assertIsNone(row["watcher_bucket"])

    def test_three_builders_still_produce_no_badge(self):
        # Three is COHORT_MIN_SAVERS and is deliberately NOT this floor.
        with web_scratch_schema() as (conn, _name):
            query_id = self.make(conn, (USER, USER_B, USER_C))
            searchqueries.refresh(conn, PROFILE, now="2026-08-02T02:00:00")
            with redirect_db(conn):
                row = search.get_search(query_id, user=USER)
        self.assertIsNone(row["watcher_bucket"])

    def test_four_builders_produce_the_first_bucket(self):
        with web_scratch_schema() as (conn, _name):
            query_id = self.make(conn, ALL_FOUR)
            searchqueries.refresh(conn, PROFILE, now="2026-08-02T02:00:00")
            with redirect_db(conn):
                row = search.get_search(query_id, user=USER)
        self.assertEqual(row["watcher_bucket"], "4-6")

    def test_a_search_nobody_watches_and_one_two_watch_are_indistinguishable(self):
        # THE test. In a thirty-person cohort who see each other in a room, a
        # count of one or two is close to an identifier, so "no badge" must not
        # be readable as "exactly one or two" -- it has to be the same answer an
        # unwatched search gives.
        with web_scratch_schema() as (conn, _name):
            seed_users(conn, *ALL_FOUR)
            with redirect_db(conn):
                quiet = search.create_search(
                    search.SearchRequest(text="quiet search"), user=USER)
                busy = search.create_search(
                    search.SearchRequest(text="two watcher search"), user=USER)
            watch(conn, busy["id"], USER_B)
            conn.execute(searchnorm.UNWATCH_SQL,
                         ("2026-08-02T01:00:00", quiet["id"], USER.id))
            conn.commit()
            searchqueries.refresh(conn, PROFILE, now="2026-08-02T02:00:00")
            with redirect_db(conn):
                a = search.get_search(quiet["id"], user=USER_C)
                b = search.get_search(busy["id"], user=USER_C)
        self.assertEqual(a["watcher_bucket"], b["watcher_bucket"])
        self.assertIsNone(a["watcher_bucket"])

    def test_the_badge_disappears_when_a_builder_unwatches(self):
        # The fold replaces rather than upserts precisely so this works. A
        # stale badge is a watch the Builder retracted, still being published.
        with web_scratch_schema() as (conn, _name):
            query_id = self.make(conn, ALL_FOUR)
            searchqueries.refresh(conn, PROFILE, now="2026-08-02T02:00:00")
            with redirect_db(conn):
                search.unwatch_search(query_id, user=USER_D)
            searchqueries.refresh(conn, PROFILE, now="2026-08-03T02:00:00")
            with redirect_db(conn):
                row = search.get_search(query_id, user=USER)
        self.assertIsNone(row["watcher_bucket"])

    def test_watchers_in_the_table_do_not_reach_the_route_without_the_fold(self):
        # The route reads the MATERIALISED table and never counts. Four
        # watchers exist and no fold has run, so the answer is null: the
        # suppression rule lives in one place and the endpoint has no opinion.
        with web_scratch_schema() as (conn, _name):
            query_id = self.make(conn, ALL_FOUR)
            with redirect_db(conn):
                row = search.get_search(query_id, user=USER)
            self.assertIsNone(row["watcher_bucket"])
            self.assertEqual(
                conn.execute("SELECT count(*) FROM search_query_watchers "
                             "WHERE removed_at IS NULL").fetchone()[0], 4)

    def test_another_cohorts_watchers_do_not_top_up_this_one(self):
        # Cross-cohort aggregation would raise the counts and is a different
        # privacy promise than the one made (tranche_five/28).
        with web_scratch_schema() as (conn, _name):
            seed_users(conn, *ALL_FOUR)
            with redirect_db(conn):
                row = search.create_search(
                    search.SearchRequest(text="ai operations"), user=USER)
            watch(conn, row["id"], USER_B)
            for i in range(4):
                conn.execute(
                    "INSERT INTO search_query_watchers (query_id, app_user_id, "
                    "profile, created_at) VALUES (%s, %s, 'other-cohort', %s)",
                    (row["id"], f"other-{i}", "2026-08-02T00:00:00"))
            conn.commit()
            searchqueries.refresh(conn, PROFILE, now="2026-08-02T02:00:00")
            with redirect_db(conn):
                seen = search.get_search(row["id"], user=USER)
        self.assertIsNone(seen["watcher_bucket"])


@requires_db
class TestIdentitiesNeverLeave(unittest.TestCase):

    def test_no_response_field_names_a_builder_or_a_count(self):
        with web_scratch_schema() as (conn, _name):
            seed_users(conn, *ALL_FOUR)
            with redirect_db(conn):
                row = search.create_search(
                    search.SearchRequest(text="ai operations"), user=USER)
            for user in (USER_B, USER_C, USER_D):
                watch(conn, row["id"], user)
            searchqueries.refresh(conn, PROFILE, now="2026-08-02T02:00:00")
            with redirect_db(conn):
                seen = search.get_search(row["id"], user=USER)
                listed = search.list_searches(user=USER, scope="mine", limit=50)

        for item in [seen] + listed["searches"]:
            for forbidden in ("app_user_id", "watchers", "watcher_count",
                              "watcher_ids", "profile", "email",
                              "first_requested_at", "computed_at"):
                self.assertNotIn(forbidden, item, f"{forbidden} must not be served")
            # `watching` is the caller's OWN fact and is the one per-person
            # field allowed out.
            self.assertIn("watching", item)
            self.assertIn("watcher_bucket", item)

    def test_the_bucket_is_the_same_for_every_builder_in_the_cohort(self):
        # A per-Builder badge would let two people compare answers and
        # difference out who the fourth watcher was.
        with web_scratch_schema() as (conn, _name):
            seed_users(conn, *ALL_FOUR)
            with redirect_db(conn):
                row = search.create_search(
                    search.SearchRequest(text="ai operations"), user=USER)
            for user in (USER_B, USER_C, USER_D):
                watch(conn, row["id"], user)
            searchqueries.refresh(conn, PROFILE, now="2026-08-02T02:00:00")
            with redirect_db(conn):
                buckets = {search.get_search(row["id"], user=u)["watcher_bucket"]
                           for u in ALL_FOUR}
        self.assertEqual(buckets, {"4-6"})

    def test_no_recency_reaches_the_response(self):
        # first_requested_at is the moment one identifiable person typed
        # something, and computed_at moves when the underlying set moves. Both
        # are timing channels, and timing is the strongest deanonymiser
        # available in a room where people can see each other.
        self.assertNotIn("first_requested_at", search.QUERY_COLUMNS)
        self.assertNotIn("computed_at", search._SIGNAL_COLUMNS)
        self.assertIn("watcher_bucket", search._SIGNAL_COLUMNS)

    def test_there_is_no_browse_all_searches_scope(self):
        # A listing of every search anyone ever typed would hand an observer
        # the whole population to plant against -- the text of a builder query
        # is often self-identifying even though the row carries no identity.
        with web_scratch_schema() as (conn, _name):
            seed_users(conn, USER, USER_B)
            with redirect_db(conn):
                search.create_search(
                    search.SearchRequest(text="somebody elses search"), user=USER_B)
                mine = search.list_searches(user=USER, scope="mine", limit=50)
        self.assertEqual(mine["searches"], [])

    def test_the_suggested_scope_carries_only_seeded_rows(self):
        with web_scratch_schema() as (conn, _name):
            seed_users(conn, USER, USER_B)
            searchqueries.seed(conn, now="2026-08-02T00:00:00")
            with redirect_db(conn):
                search.create_search(
                    search.SearchRequest(text="somebody elses search"), user=USER_B)
                suggested = search.list_searches(user=USER, scope="suggested", limit=50)
        self.assertTrue(suggested["searches"])
        for item in suggested["searches"]:
            self.assertIn(item["source"], ("seeded", "track"))
            self.assertIsNotNone(item["role_track"],
                                 "a seeded row exists BECAUSE a track does")


@requires_db
class TestTheSignalJoinBindsInOrder(unittest.TestCase):
    """_SIGNAL_JOIN is spliced ahead of the WHERE, so its two parameters must
    lead. Getting that backwards does not raise -- it compares a user id
    against a profile name, finds nothing, and silently reports every Builder
    as watching nothing, which is the failure jobs._BUILDER_STATE_JOIN is
    emphatic about."""

    def test_the_callers_own_watch_is_reported(self):
        with web_scratch_schema() as (conn, _name):
            seed_users(conn, USER, USER_B)
            with redirect_db(conn):
                row = search.create_search(
                    search.SearchRequest(text="ai operations"), user=USER)
                mine = search.get_search(row["id"], user=USER)
                theirs = search.get_search(row["id"], user=USER_B)
        self.assertTrue(mine["watching"])
        self.assertFalse(theirs["watching"])

    def test_unwatching_flips_it_and_leaves_the_row(self):
        with web_scratch_schema() as (conn, _name):
            seed_users(conn, USER)
            with redirect_db(conn):
                row = search.create_search(
                    search.SearchRequest(text="ai operations"), user=USER)
                after = search.unwatch_search(row["id"], user=USER)
            self.assertFalse(after["watching"])
            self.assertEqual(
                conn.execute("SELECT count(*) FROM search_query_watchers")
                .fetchone()[0], 1)


@requires_db
class TestResultsRouteThroughTheGate(unittest.TestCase):
    """A posting reaches a Builder only through jobs_app, whatever a provider
    returned. The gate is the JOIN, not a filter anyone has to remember."""

    def _seed_posting(self, conn, job_id="relister-1", matched=True,
                      description="Confidential posting from a reputed company."):
        conn.execute(
            """
            INSERT INTO jobs (id, platform, company_token, company_name,
                              source_id, title, job_url, description_text,
                              status, first_seen, last_seen)
            VALUES (%s, 'google_jobs', 'reputed', 'Reputed Company', %s,
                    'AI Operations Coordinator', 'https://example.invalid/1',
                    %s, 'open', '2026-08-02T00:00:00', '2026-08-02T00:00:00')
            """,
            (job_id, job_id, description))
        if matched:
            conn.execute(
                "INSERT INTO job_matches (job_id, profile, match_score, "
                "match_reasons, facts_version, criteria_version, matched_at) "
                "VALUES (%s, %s, 40, '[]', 3, 1, '2026-08-02T00:00:00')",
                (job_id, PROFILE))
        conn.commit()
        return job_id

    def _search_with(self, conn, job_id):
        with redirect_db(conn):
            row = search.create_search(
                search.SearchRequest(text="ai operations"), user=USER)
        searchqueries.attach_results(conn, row["id"], [job_id], provider="test",
                                     now="2026-08-02T00:00:00")
        return row["id"]

    def test_a_posting_with_no_match_row_is_invisible(self):
        # match.py writes a job_matches row only for postings that pass
        # relevance.union_sql. No match row means the gate said no.
        with web_scratch_schema() as (conn, _name):
            seed_users(conn, USER)
            job_id = self._seed_posting(conn, matched=False)
            query_id = self._search_with(conn, job_id)
            with redirect_db(conn):
                results = search.search_results(query_id, user=USER, limit=50,
                                                cursor=None,
                                                include_dismissed=False)
            self.assertEqual(results["jobs"], [])

    def test_the_link_row_exists_regardless(self):
        # attach_results takes NO gate decision, deliberately: raising max_tier
        # or fixing a `\y` pattern must retroactively surface postings this
        # pipeline already paid to fetch.
        with web_scratch_schema() as (conn, _name):
            seed_users(conn, USER)
            job_id = self._seed_posting(conn, matched=False)
            query_id = self._search_with(conn, job_id)
            self.assertEqual(
                conn.execute("SELECT count(*) FROM search_query_results "
                             "WHERE query_id = %s", (query_id,)).fetchone()[0], 1)

    def test_a_matched_posting_is_returned(self):
        with web_scratch_schema() as (conn, _name):
            seed_users(conn, USER)
            job_id = self._seed_posting(conn)
            query_id = self._search_with(conn, job_id)
            with redirect_db(conn):
                results = search.search_results(query_id, user=USER, limit=50,
                                                cursor=None,
                                                include_dismissed=False)
            self.assertEqual([j["id"] for j in results["jobs"]], [job_id])
            # The list vocabulary is /v1/jobs' vocabulary, field for field: a
            # search result list is a rendered list and position bias applies
            # to it identically, so tranche_five/27's instrumentation fits.
            self.assertIn("request_id", results)
            self.assertEqual(results["jobs"][0]["rank"], 1)

    def test_an_incomplete_posting_stays_invisible_even_when_matched(self):
        # jobs_app's four completeness predicates apply here too -- the search
        # route inherits them by joining the view rather than the table.
        with web_scratch_schema() as (conn, _name):
            seed_users(conn, USER)
            job_id = self._seed_posting(conn, job_id="no-desc", description=None)
            query_id = self._search_with(conn, job_id)
            with redirect_db(conn):
                results = search.search_results(query_id, user=USER, limit=50,
                                                cursor=None,
                                                include_dismissed=False)
            self.assertEqual(results["jobs"], [])

    def test_a_closed_posting_leaves_the_results(self):
        with web_scratch_schema() as (conn, _name):
            seed_users(conn, USER)
            job_id = self._seed_posting(conn)
            query_id = self._search_with(conn, job_id)
            conn.execute("UPDATE jobs SET status = 'closed' WHERE id = %s",
                         (job_id,))
            conn.commit()
            with redirect_db(conn):
                results = search.search_results(query_id, user=USER, limit=50,
                                                cursor=None,
                                                include_dismissed=False)
            self.assertEqual(results["jobs"], [])

    def test_the_route_never_names_the_jobs_table(self):
        # Static, and the point of it is that it cannot be satisfied by luck:
        # a future edit that swapped the view for the table to "fix" a missing
        # row would surface exactly the relister postings the curated pipeline
        # was built to suppress.
        import inspect
        source = inspect.getsource(search.search_results)
        self.assertIn("FROM jobs_app v", source)
        self.assertNotIn("FROM jobs ", source)


@requires_db
class TestTheVolumeInstrument(unittest.TestCase):
    """At today's cohort of two this fold writes zero rows on a healthy run, so
    "0 searches" alone cannot tell a working fold from a broken one."""

    def test_it_counts_builders_who_currently_watch_something(self):
        with web_scratch_schema() as (conn, _name):
            seed_users(conn, *ALL_FOUR)
            with redirect_db(conn):
                row = search.create_search(
                    search.SearchRequest(text="ai operations"), user=USER)
            watch(conn, row["id"], USER_B)
            self.assertEqual(searchqueries.active_watchers(conn, PROFILE), 2)

    def test_a_builder_who_unwatched_everything_stops_being_counted(self):
        with web_scratch_schema() as (conn, _name):
            seed_users(conn, USER, USER_B)
            with redirect_db(conn):
                row = search.create_search(
                    search.SearchRequest(text="ai operations"), user=USER)
                search.unwatch_search(row["id"], user=USER)
            self.assertEqual(searchqueries.active_watchers(conn, PROFILE), 0)

    def test_the_summary_line_carries_no_per_query_count(self):
        # "12 searches are below the threshold" would be a per-query
        # sub-threshold fact, which is the thing the module refuses to emit.
        line = searchqueries.summarise(PROFILE, 2, [])
        self.assertIn("floor=4", line)
        self.assertIn("2 builder(s) watching", line)
        self.assertIn("0 search(es)", line)
        for label in schema.SEARCH_WATCHER_BUCKET_LABELS:
            self.assertIn(f"{label}=0", line)


class TestItIsWiredIntoTheNightlyRun(unittest.TestCase):

    def _steps(self):
        import importlib.util
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__)))), "run-daily.py")
        spec = importlib.util.spec_from_file_location("run_daily_search", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return [s if isinstance(s, str) else s[0] for s in module.STEPS]

    def test_searchqueries_is_a_nightly_step(self):
        self.assertIn("searchqueries.py", self._steps())

    def test_it_runs_before_extract(self):
        # It is ingest-shaped: what it dispatches produces `jobs` rows, so it
        # must run before extract turns new postings into facts.
        names = self._steps()
        self.assertLess(names.index("searchqueries.py"), names.index("extract.py"))

    def test_it_runs_with_no_flags(self):
        import importlib.util
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__)))), "run-daily.py")
        spec = importlib.util.spec_from_file_location("run_daily_search2", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        entry = [s for s in module.STEPS
                 if (s if isinstance(s, str) else s[0]) == "searchqueries.py"]
        self.assertEqual(entry, ["searchqueries.py"],
                         "the nightly run folds every active cohort; a "
                         "--profile flag here would silently badge one")


if __name__ == "__main__":
    unittest.main()
