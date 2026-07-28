"""Tests for the evaluation harness.

Self-contained like the rest of the suite: no network, no database. The
endpoint is stubbed at urllib.request.urlopen, which is the same seam
test_llm.py uses.

The properties worth pinning here are mostly about honesty rather than
arithmetic -- that a replayed latency is never reported as measured, that a
credential never reaches the cache key or a results file, and that a record
the pipeline would never send is not counted against the model.
"""

import json
import os
import shutil
import tempfile
import unittest
import urllib.request

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evals import (cache, corpus, metrics, models, report,  # noqa: E402
                   runner, tasks)

_GOOD = json.dumps({
    "seniority_level": "Mid-Level",           # deliberately off-vocabulary
    "years_experience_min": 3, "years_experience_max": 6,
    "role_archetype": "backend", "tech_stack": ["Python", "  postgres  "],
    "ai_involvement": "uses_ai_tools", "ml_research_required": False,
    "advanced_degree_required": False, "customer_facing": False,
    "remote_policy": "remote_anywhere", "employment_type": "full_time",
    "comp_min": 150000, "comp_max": 190000, "comp_currency": "USD",
    "gap_friendly_language": False, "visa_sponsorship": "unknown",
    "summary": "A backend role. It uses Python.",
})


def _records():
    return [
        {"id": "a1", "title": "Backend Engineer", "company_name": "Acme",
         "location_raw": "NYC", "platform": "ats",
         "description_text": "Build services.", "facts": None},
        {"id": "a2", "title": "T" * 200, "company_name": "HN",
         "location_raw": "", "platform": "hn",
         "description_text": "FENCED role at a startup.", "facts": None},
        {"id": "a3", "title": "No desc", "company_name": "X",
         "location_raw": "", "platform": "wwr",
         "description_text": "   ", "facts": None},
        {"id": "a4", "title": "Garbage", "company_name": "Y",
         "location_raw": "", "platform": "google",
         "description_text": "GARBAGE posting.",
         "facts": {"facts_version": 2, "extraction_model": "FAILED:glm"}},
    ]


class _FakeResp:
    def __init__(self, body):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _StubEndpoint:
    """Counts calls and varies the response by prompt content."""

    def __init__(self):
        self.calls = 0

    def __call__(self, req, timeout=None):
        self.calls += 1
        prompt = json.loads(req.data.decode())["messages"][0]["content"]
        if "GARBAGE" in prompt:
            content = "I cannot help with that."
        elif "FENCED" in prompt:
            content = f"Sure!\n```json\n{_GOOD}\n```\nHope that helps."
        else:
            content = _GOOD
        return _FakeResp(json.dumps({
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": 1060, "completion_tokens": 240},
        }).encode())


class TestModelSpec(unittest.TestCase):
    def test_api_key_may_contain_at_sign(self):
        """split('@', 2), not a rejoin of the middle.

        tools/compare-models.py:213 splits on every '@' and treats the last
        field as the key, which truncates any key containing one. Base URLs
        do not contain a bare '@'; keys routinely can.
        """
        spec = models.parse("m@https://x.example/v1@sk-a@b")
        self.assertEqual(spec.base_url, "https://x.example/v1")
        self.assertEqual(spec.api_key, "sk-a@b")

    def test_bare_model_defers_to_environment(self):
        spec = models.parse("glm-4.5-flash")
        self.assertIsNone(spec.base_url)
        self.assertIsNone(spec.api_key)
        self.assertEqual(spec.backend, "http")

    def test_claude_backend(self):
        spec = models.parse("claude:haiku")
        self.assertEqual(spec.backend, "claude")
        self.assertEqual(spec.call_kwargs(), {"model": "haiku",
                                              "backend": "claude"})

    def test_env_indirection_keeps_secret_out_of_the_spec(self):
        os.environ["_EVALS_TEST_KEY"] = "sk-from-env"
        try:
            spec = models.parse("m@https://x/v1@env:_EVALS_TEST_KEY")
            self.assertEqual(spec.api_key, "env:_EVALS_TEST_KEY")
            self.assertEqual(spec.call_kwargs()["api_key"], "sk-from-env")
        finally:
            del os.environ["_EVALS_TEST_KEY"]

    def test_unset_env_key_is_an_error(self):
        spec = models.parse("m@https://x/v1@env:_EVALS_DEFINITELY_UNSET")
        with self.assertRaises(models.SpecError):
            spec.call_kwargs()

    def test_bad_specs_rejected(self):
        for bad in ("", "   ", "m@", "m@url@", "claude:", "@url@key"):
            with self.assertRaises(models.SpecError, msg=repr(bad)):
                models.parse(bad)

    def test_cache_identity_excludes_credentials(self):
        spec = models.parse("m@https://x/v1@sk-secret")
        self.assertNotIn("sk-secret", json.dumps(spec.cache_identity()))


class TestCorpus(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="evals-corpus-")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_jsonl_round_trip_is_lossless(self):
        path = os.path.join(self.dir, "c.jsonl")
        recs = _records()
        corpus.save(path, recs)
        self.assertEqual(corpus.load(path), recs)

    def test_pathology_tagging(self):
        recs = _records()
        self.assertEqual(corpus.classify(recs[0]), [])
        self.assertEqual(corpus.classify(recs[1]), ["long_title"])
        self.assertEqual(corpus.classify(recs[2]), ["no_description"])
        self.assertEqual(corpus.classify(recs[3]), ["tombstoned"])

    def test_stratify_is_deterministic_for_a_seed(self):
        pool = [dict(_records()[0], id=f"x{i}") for i in range(50)]
        a = [r["id"] for r in corpus.stratify(pool, 10, seed=7)]
        b = [r["id"] for r in corpus.stratify(pool, 10, seed=7)]
        self.assertEqual(a, b)
        self.assertEqual(len(a), 10)

    def test_never_extracted_is_distinct_from_empty_extraction(self):
        # A row job_facts has never seen stores facts=None. A row extracted
        # into all-empty fields is a real and different outcome.
        self.assertIsNone(_records()[0]["facts"])
        self.assertIsNotNone(_records()[3]["facts"])


class _RunnerCase(unittest.TestCase):
    """Shared stub-endpoint plumbing with an isolated cache directory."""

    def setUp(self):
        self.cache_dir = tempfile.mkdtemp(prefix="evals-cache-")
        self._prev = os.environ.get("EVAL_CACHE_DIR")
        os.environ["EVAL_CACHE_DIR"] = self.cache_dir
        self.stub = _StubEndpoint()
        self._real = urllib.request.urlopen
        urllib.request.urlopen = self.stub
        self.task = tasks.get("extract")
        self.spec = models.parse("m@https://x/v1@k")
        self.records = _records()

    def tearDown(self):
        urllib.request.urlopen = self._real
        if self._prev is None:
            os.environ.pop("EVAL_CACHE_DIR", None)
        else:
            os.environ["EVAL_CACHE_DIR"] = self._prev
        shutil.rmtree(self.cache_dir, ignore_errors=True)

    def _run(self, **kw):
        kw.setdefault("workers", 2)
        return runner.run(self.task, self.spec, self.records, **kw)


class TestRunner(_RunnerCase):
    def test_statuses(self):
        by_id = {r.job_id: r for r in self._run().results}
        self.assertEqual(by_id["a1"].status, runner.OK)
        self.assertEqual(by_id["a2"].status, runner.OK)   # fenced JSON parses
        self.assertEqual(by_id["a3"].status, runner.SKIPPED)
        self.assertEqual(by_id["a4"].status, runner.TOMBSTONE)
        self.assertEqual(by_id["a4"].reason, "unparseable_json")

    def test_ineligible_record_is_never_sent(self):
        # An empty description is excluded by extract.py's own selector, so
        # billing a call for it -- or counting it as a model failure -- would
        # both be wrong.
        self._run()
        self.assertEqual(self.stub.calls, 3)

    def test_results_are_in_corpus_order(self):
        ids = [r.job_id for r in self._run().results]
        self.assertEqual(ids, ["a1", "a2", "a3", "a4"])

    def test_normalize_is_applied(self):
        # The comparison that matters is against what job_facts would store,
        # not against the model's raw formatting.
        by_id = {r.job_id: r for r in self._run().results}
        facts = by_id["a1"].normalized
        self.assertEqual(facts["seniority_level"], "mid")
        self.assertEqual(json.loads(facts["tech_stack"]),
                         ["postgres", "python"])

    def test_unresolvable_credential_fails_before_any_call(self):
        """A config error must surface before the first record is billed.

        Resolving `env:VARNAME` lazily inside the worker meant an unset key
        raised out of a thread after some records had already been paid for,
        and reached the user as a traceback rather than one actionable line.
        """
        spec = models.parse("m@https://x/v1@env:_EVALS_DEFINITELY_UNSET")
        with self.assertRaises(models.SpecError):
            runner.run(self.task, spec, self.records, workers=2)
        self.assertEqual(self.stub.calls, 0)

    def test_transient_error_is_deferred_not_tombstoned(self):
        import llm

        def transient(*a, **k):
            raise urllib.error.HTTPError("http://x", 429, "busy", {},
                                         __import__("io").BytesIO(b"b"))

        urllib.request.urlopen = transient
        run = self._run()
        statuses = {r.status for r in run.results if r.job_id != "a3"}
        self.assertEqual(statuses, {runner.DEFERRED})
        # A deferred record must leave nothing behind: the prompt was never
        # evaluated, so there is no answer to cache.
        self.assertEqual(cache.stats()[0], 0)


class TestCachePolicy(_RunnerCase):
    def test_replay_is_free_and_identical(self):
        first = self._run()
        calls_after_first = self.stub.calls
        second = self._run()
        self.assertEqual(self.stub.calls, calls_after_first,
                         "a replayed run must make no live calls")
        self.assertTrue(second.replayed_any)
        self.assertEqual([r.normalized for r in first.results],
                         [r.normalized for r in second.results])

    def test_refresh_rebuys(self):
        self._run()
        before = self.stub.calls
        run = self._run(refresh=True)
        self.assertEqual(self.stub.calls, before + 3)
        self.assertFalse(run.replayed_any)

    def test_cache_is_keyed_on_model(self):
        self._run()
        before = self.stub.calls
        runner.run(self.task, models.parse("other@https://x/v1@k"),
                   self.records, workers=2)
        self.assertEqual(self.stub.calls, before + 3)

    def test_rotating_a_credential_does_not_invalidate_the_cache(self):
        self._run()
        before = self.stub.calls
        run = runner.run(self.task, models.parse("m@https://x/v1@new-key"),
                         self.records, workers=2)
        self.assertEqual(self.stub.calls, before)
        self.assertTrue(run.replayed_any)

    def test_no_cache_writes_nothing(self):
        self._run(use_cache=False)
        self.assertEqual(cache.stats()[0], 0)


class TestReport(_RunnerCase):
    def test_replayed_run_refuses_to_report_cost_or_latency(self):
        self._run()
        out = report.render(self._run())
        self.assertIn("not reported", out)
        self.assertIn("--no-cache", out)
        self.assertNotIn("latency       median", out)
        self.assertNotIn("tokens", out)

    def test_live_run_reports_cost_and_latency(self):
        out = report.render(self._run(use_cache=False))
        self.assertIn("latency       median", out)
        self.assertIn("tokens", out)

    def test_usable_is_over_attempted_not_over_n(self):
        # a3 is ineligible; counting it would understate the model.
        out = report.render(self._run(use_cache=False))
        self.assertIn("usable        2/3", out)
        self.assertIn("skipped       1", out)

    def test_jsonl_rows_carry_prompt_digest_and_no_secrets(self):
        # A distinctive credential, so "did the key leak" is an honest
        # substring test rather than a search for a letter that also occurs
        # in the word "backend".
        secret = "sk-must-never-be-written-to-disk"
        run = runner.run(self.task, models.parse(f"m@https://x/v1@{secret}"),
                         self.records, use_cache=False, workers=2)
        path = os.path.join(self.cache_dir, "results.jsonl")
        report.write_jsonl(path, run)
        with open(path, encoding="utf-8") as fh:
            body = fh.read()
        rows = [json.loads(line) for line in body.splitlines()]

        self.assertEqual(len(rows), 4)
        self.assertNotIn(secret, body)
        for row in rows:
            if row["status"] != runner.SKIPPED:
                self.assertTrue(row["prompt_sha"])
            self.assertNotIn("api_key", json.dumps(row))


class _VaryingEndpoint:
    """Returns a different `seniority_level` on each call for one job.

    This is what a temperature-0 model that does not agree with itself
    actually looks like from the harness's side, and it is the only way to
    tell a real disagreement apart from a cache hit in a test.
    """

    def __init__(self, flip_on="Build services."):
        self.calls = 0
        self.flip_on = flip_on
        self._seen = {}

    def __call__(self, req, timeout=None):
        self.calls += 1
        prompt = json.loads(req.data.decode())["messages"][0]["content"]
        body = json.loads(_GOOD)
        if self.flip_on in prompt:
            n = self._seen.get(self.flip_on, 0)
            self._seen[self.flip_on] = n + 1
            body["seniority_level"] = ["junior", "mid", "senior"][n % 3]
        return _FakeResp(json.dumps({
            "choices": [{"message": {"content": json.dumps(body)}}],
            "usage": {"prompt_tokens": 1060, "completion_tokens": 240},
        }).encode())


class TestRepeatCacheKey(unittest.TestCase):
    """The disambiguation whose absence is a silent, total false pass.

    The store is content-addressed. Without a repeat index in the key,
    repeat 2 of a self-consistency run reads back repeat 1's stored answer
    and every field reports 100% agreement -- on the exact quantity being
    measured, with no error raised and nothing in the output to suggest it.
    Measured with the disambiguation removed, the run below reports 100%;
    with it, 33%. These tests exist so that difference cannot regress
    unnoticed.
    """

    def test_repeat_index_changes_the_digest(self):
        spec = models.parse("m@https://x/v1@k")
        digests = [cache.key_for(spec, "same prompt", repeat_index=i)
                   for i in range(4)]
        self.assertEqual(len(set(digests)), 4,
                         "each repeat must get its own cache entry, or a "
                         "self-consistency run measures the cache")

    def test_index_zero_is_the_plain_key(self):
        # So an ordinary run and the first pass of a repeat run share
        # entries, and adding --repeat does not invalidate a paid-for cache.
        spec = models.parse("m@https://x/v1@k")
        self.assertEqual(cache.key_for(spec, "p"),
                         cache.key_for(spec, "p", repeat_index=0))


class TestRepeatedRuns(_RunnerCase):
    def setUp(self):
        super().setUp()
        self.stub = _VaryingEndpoint()
        urllib.request.urlopen = self.stub

    def test_repeat_defaults_to_no_cache_and_calls_live_every_pass(self):
        runs = runner.run_repeated(self.task, self.spec, self.records,
                                   repeat=3, workers=2)
        self.assertEqual(len(runs), 3)
        self.assertEqual(self.stub.calls, 9)      # 3 eligible x 3 passes
        self.assertEqual(cache.stats()[0], 0)
        for run in runs:
            self.assertFalse(run.replayed_any)

    def test_disagreement_survives_caching_being_forced_on(self):
        """The regression test for the false pass.

        With caching ON and per-repeat keys, every pass still calls live and
        the flipping field still reads as unstable: 3 records comparable,
        one of them flipping, so 2/3.
        """
        runs = runner.run_repeated(self.task, self.spec, self.records,
                                   repeat=3, use_cache=True, workers=2)
        self.assertEqual(self.stub.calls, 9)
        stats = metrics.selfcheck(runs, self.records, self.task.field_kinds)
        cell = stats["fields"]["seniority_level"]["overall"]
        self.assertEqual(cell["n"], 3)
        self.assertEqual(cell["unan_k"], 2)
        self.assertEqual(cell["agree2_k"], 2)

    def test_without_disambiguation_the_run_reports_a_perfect_score(self):
        """The failure this guards against, demonstrated rather than asserted.

        Reverting cache.key_for to ignore repeat_index is simulated here.
        The endpoint is asked 3 times instead of 9, every later pass replays
        the first, and the flipping field reports 100% agreement -- a number
        that looks like excellent news and means nothing. If this test ever
        stops showing 100%, the understanding of the cache encoded in
        cache.key_for's docstring is wrong.
        """
        real = cache.key_for
        cache.key_for = lambda spec, prompt, *, repeat_index=0, **kw: real(
            spec, prompt, **kw)
        try:
            runs = runner.run_repeated(self.task, self.spec, self.records,
                                       repeat=3, use_cache=True, workers=2)
        finally:
            cache.key_for = real
        self.assertEqual(self.stub.calls, 3, "later passes replayed pass 1")
        stats = metrics.selfcheck(runs, self.records, self.task.field_kinds)
        cell = stats["fields"]["seniority_level"]["overall"]
        self.assertEqual(cell["agree2"], 1.0)
        self.assertEqual(cell["unanimous"], 1.0)
        self.assertEqual(stats["whole_record"]["rate"], 1.0)

    def test_repeat_one_still_uses_the_cache(self):
        runs = runner.run_repeated(self.task, self.spec, self.records,
                                   repeat=1, workers=2)
        self.assertTrue(runs[0].use_cache)


class TestFixtureIdentity(unittest.TestCase):
    """The eval sets are pinned by sorted job_id, as a literal.

    CLAUDE.md's measurement discipline: pin eval sets by sorted job_id,
    never recycle them. A fixture regenerated in place would silently
    change what every published figure was measured on -- and the figures
    would still be sitting in the docs, unchanged and now wrong. This is the
    same argument tests/test_row_identity.py makes about content hashes.
    """

    FIXTURES = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "evals", "fixtures")

    #: v1: the 2026-07-27 snapshot. task 04's figures cite it.
    #: v2: the 2026-07-28 snapshot the n=120 self-consistency run used.
    DIGESTS = {
        "corpus-v1.jsonl":
            "e0276c616203dd2eecea575e74a2c4ce45e7eb59d225693a14945883fec09ae9",
        "corpus-v2.jsonl":
            "cbf8cfe73896d1ba35a45f9e4dd476900662c9f809c48191e987ece5f4e7a6e3",
    }

    def test_frozen_corpora_have_not_moved(self):
        import hashlib
        for name, want in self.DIGESTS.items():
            path = os.path.join(self.FIXTURES, name)
            ids = sorted(r["id"] for r in corpus.load(path))
            self.assertEqual(len(ids), 120, name)
            got = hashlib.sha256("\n".join(ids).encode()).hexdigest()
            self.assertEqual(got, want,
                             f"{name} is not the fixture the published "
                             f"figures were measured on")

    def test_v2_reaches_every_platform(self):
        # The property the per-platform pool query exists for: a naive
        # most-recent sample returned zero hn_whoishiring and zero
        # weworkremotely rows (corpus.py:115).
        counts = corpus.summarize(
            corpus.load(os.path.join(self.FIXTURES, "corpus-v2.jsonl")))
        self.assertEqual(len(counts["platforms"]), 7)
        for platform, n in counts["platforms"].items():
            self.assertGreater(n, 0, platform)


class TestMetrics(unittest.TestCase):
    def test_wilson_is_narrower_at_larger_n(self):
        lo17, hi17 = metrics.wilson(13, 17)      # the provisional figure
        lo120, hi120 = metrics.wilson(92, 120)   # the same rate at n=120
        self.assertLess(hi120 - lo120, hi17 - lo17)
        # The n=17 interval is why nothing was to be re-tuned on it.
        self.assertLess(lo17, 0.60)
        self.assertGreater(hi17, 0.88)

    def test_wilson_never_leaves_the_unit_interval(self):
        for k, n in ((0, 5), (5, 5), (9, 9), (0, 1), (1, 1)):
            lo, hi = metrics.wilson(k, n)
            self.assertGreaterEqual(lo, 0.0)
            self.assertLessEqual(hi, 1.0)

    def test_none_is_distinct_from_zero_for_ints(self):
        # "the posting did not say" and "the posting said zero" are
        # different facts, and an eval that conflates them overstates
        # agreement on exactly the fields most often absent.
        self.assertEqual(metrics.compare("int", None, 0), 0.0)
        self.assertEqual(metrics.compare("int", None, None), 1.0)

    def test_jaccard_reads_the_json_string_normalize_stores(self):
        self.assertEqual(metrics.jaccard('["a","b"]', '["b","a"]'), 1.0)
        self.assertEqual(metrics.jaccard('["a","b"]', '["a"]'), 0.5)
        self.assertEqual(metrics.jaccard(None, "[]"), 1.0)

    def test_agree2_uses_only_the_first_two_repeats(self):
        # It is the column comparable to the two-run n=17 protocol, so a
        # third pass must not move it.
        cell = metrics.field_cell("enum", [("a", "a", "b"), ("a", "b", "b")])
        self.assertEqual(cell["agree2_k"], 1)
        self.assertEqual(cell["unan_k"], 0)

    def test_unanimity_is_never_above_agree2(self):
        cell = metrics.field_cell("enum", [("a", "a", "b"), ("a", "a", "a")])
        self.assertLessEqual(cell["unanimous"], cell["agree2"])

    def test_flips_name_the_values_not_just_the_rate(self):
        # A rate says how often the model disagrees with itself; this says
        # what the disagreement is. For ai_involvement the difference
        # decides whether a job leaves the cohort's opportunity space or
        # merely moves within it.
        cell = metrics.field_cell("enum", [
            ("none", "uses_ai_tools", "none"),
            ("none", "uses_ai_tools", "none"),
            ("builds_llm_features", "uses_ai_tools", "uses_ai_tools"),
            ("none", "none", "none")])
        self.assertEqual(cell["flips"],
                         [("none <-> uses_ai_tools", 2),
                          ("builds_llm_features <-> uses_ai_tools", 1)])

    def test_set_fields_get_no_flip_wall(self):
        cell = metrics.field_cell("set", [('["a"]', '["b"]', '["c"]')])
        self.assertEqual(cell["flips"], [])

    def test_truncated_flip_lists_say_so(self):
        """A silent truncation hid the seventh ai_involvement pattern once.

        That pattern crossed the `none` boundary, so the count the gate
        decision rests on came out one record short. The marker is the fix.
        """
        rows = [(f"v{i}", f"w{i}", f"v{i}") for i in range(20)]
        stats = {
            "repeat": 3, "n_records": 20, "n_comparable": 20, "not_ok": [],
            "platform_counts": {"greenhouse": 20},
            "whole_record": {"k": 0, "n": 20, "rate": 0.0},
            "fields": {"seniority_level": {
                "overall": metrics.field_cell("enum", rows),
                "by_platform": {"greenhouse": metrics.field_cell("enum", rows)},
                "clean": metrics.field_cell("enum", rows),
                "messy": metrics.field_cell("enum", [])}},
        }
        run = runner.Run(task="extract", model_label="m", model_identity={},
                         results=[], use_cache=False)
        out = report.render_selfcheck(stats, [run])
        self.assertIn("more pattern(s)", out)

    def test_selfcheck_rejects_a_single_run(self):
        with self.assertRaises(ValueError):
            metrics.selfcheck([], [], {})


if __name__ == "__main__":
    unittest.main()
