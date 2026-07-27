"""Tests for lib/ids.py, lib/timeparse.py and lib/upsert.py.

Split out of the shared library's suite on 2026-07-26 when lib/ was vendored
into this repo (~/apps/REORG.md slice G).

TestHashCompatibility is the important one: it pins make_id and
content_hash against the exact expressions the original scripts used.
Those digests are stored -- `id` is the primary key of every row and
`content_hash` decides what counts as changed -- so a drift here re-keys
or rewrites all ~11,400 rows on the next run.

stdlib unittest rather than pytest, which isn't installed here and isn't
worth adding as a dependency to a stdlib-plus-psycopg codebase.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import hashlib  # noqa: E402
import unittest  # noqa: E402
from datetime import date, datetime, timezone  # noqa: E402

from lib import ids, timeparse, upsert  # noqa: E402

class _FakeConn:
    """Just enough psycopg surface for upsert(): execute/fetchone, a
    transaction() context manager (the real one issues a SAVEPOINT), commit.

    `existing` is the row select_sql() should return, or None for a fresh row.
    Executed statements are recorded so a test can assert what was written.
    """

    def __init__(self, existing=None):
        self.existing = existing
        self.statements = []

    def execute(self, sql, params=None):
        self.statements.append((sql, params))
        conn = self

        class _Cur:
            def fetchone(self_inner):
                return conn.existing if sql.startswith("SELECT") else None
        return _Cur()

    def transaction(self):
        class _Tx:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *exc):
                return False
        return _Tx()

    def commit(self):
        pass


class TestHashCompatibility(unittest.TestCase):
    """Byte-identical to the implementations pipelib replaces."""

    def _legacy_events_id(self, source, source_id, title, start):
        key = f"{source}:{source_id or title}:{start or ''}"
        return hashlib.sha256(key.encode()).hexdigest()[:24]

    def _legacy_jobs_id(self, platform, token, source_id):
        return hashlib.sha256(
            f"{platform}:{token}:{source_id}".encode()).hexdigest()[:24]

    def test_events_id_matches_legacy(self):
        for args in [
            ("nyc_parks_events", "guid-1", "Yoga", "2026-07-24T19:00:00.000"),
            ("nypl_events", None, "Story Time", "2026-07-24T19:00:00+00:00"),
            ("seatgeek", 12345, "Concert", None),          # non-str source_id
            ("nyc_permitted_events", "", "Fair", ""),      # empty falls back to title
        ]:
            source, source_id, title, start = args
            self.assertEqual(
                ids.make_id(source, source_id or title, start or ""),
                self._legacy_events_id(*args),
                f"id drift for {args!r}")

    def test_jobs_id_matches_legacy(self):
        for args in [("greenhouse", "flatironhealth", "4567"),
                     ("lever", "sailorhealth", "abc-def"),
                     ("ashby", "formationbio", 99)]:
            self.assertEqual(ids.make_id(*args), self._legacy_jobs_id(*args))

    def test_none_stringifies_not_empties(self):
        """A None part must render as 'None', matching f-string semantics.

        Normalising None to "" here would silently re-key every row whose
        source_id was absent.
        """
        self.assertEqual(ids.make_id("a", None), ids.make_id("a", "None"))
        self.assertNotEqual(ids.make_id("a", None), ids.make_id("a", ""))

    def test_content_hash_matches_legacy(self):
        rec = {"title": "Yoga", "description": None, "start_datetime": "2026-07-24",
               "end_datetime": None, "venue_name": "Chelsea Park", "address": "x",
               "borough": "Manhattan", "categories": "Fitness", "is_free": True,
               "registration_url": None, "source_url": "http://e", "latitude": 40.7,
               "longitude": -74.0}
        fields = ("title", "description", "start_datetime", "end_datetime",
                  "venue_name", "address", "borough", "categories", "is_free",
                  "registration_url", "source_url", "latitude", "longitude")
        legacy = hashlib.sha256(
            "|".join(str(rec[f]) for f in fields).encode()).hexdigest()
        self.assertEqual(ids.content_hash(rec, fields), legacy)

    def test_content_hash_is_order_sensitive(self):
        rec = {"a": 1, "b": 2}
        self.assertNotEqual(ids.content_hash(rec, ("a", "b")),
                            ids.content_hash(rec, ("b", "a")))

    def test_jobs_content_hash_matches_legacy(self):
        """The jobs scripts hashed `rec.get("description_text") or ""` while
        hashing everything else bare. Without blank_if_falsy, a row with no
        description hashes "None" instead of "" and gets rewritten."""
        rec = {"title": "SWE", "location_raw": "NYC", "department": None,
               "job_url": "http://x", "posted_at": None,
               "description_text": None}
        legacy = hashlib.sha256("|".join(str(f) for f in (
            rec["title"], rec["location_raw"], rec["department"],
            rec["job_url"], rec["posted_at"],
            rec.get("description_text") or "",
        )).encode()).hexdigest()
        got = ids.content_hash(
            rec,
            ("title", "location_raw", "department", "job_url", "posted_at",
             "description_text"),
            blank_if_falsy=("description_text",))
        self.assertEqual(got, legacy)

    def test_blank_if_falsy_actually_differs(self):
        rec = {"a": None}
        self.assertNotEqual(ids.content_hash(rec, ("a",)),
                            ids.content_hash(rec, ("a",), blank_if_falsy=("a",)))


class TestGoogleJobIdentity(unittest.TestCase):
    """The 32%-duplicate-rows bug -- see the Google Jobs section of ids.py.

    The two blobs below are REAL `job_id` values taken from the live jobs
    table (rows first_seen 2026-07-24T18:17:53 and T19:47:41). Both describe
    the same 15Five posting; they differ in the volatile `fc` token and in
    whether `hl` is present, which is exactly what made the old raw-blob key
    mint two rows for one job. Keeping the real values here means the test
    fails if the decoder ever stops coping with what Google actually sends.
    """

    # first_seen 2026-07-24T18:17:53 -- carries "hl":"en"
    BLOB_A = (
        "eyJqb2JfdGl0bGUiOiJbUmVtb3RlXSBTZW5pb3IgQWkgU29sdXRpb25zIEVuZ2luZWVyIiwiY29t"
        "cGFueV9uYW1lIjoiMTVGaXZlIiwiaHRpZG9jaWQiOiI1cDY5aHhNekZtUXJsTHFpQUFBQUFBPT0i"
        "LCJ1dWxlIjoidytDQUlRSUNJTlZXNXBkR1ZrSUZOMFlYUmxjdyIsImdsIjoidXMiLCJobCI6ImVu"
        "IiwiZmMiOiJFc3dCQ293QlFVcHBWRFIwVEZaQ05USnVPRWQwWWtoUlVVWkhUMFpsZFVKVWVsZEpi"
        "bUZzUVhOZk1GODVVSGh5Tm1SVWMxVkZXVlpSUjIxaFdVcEZWMVU0Ym05UFYzaGlha2xTVUdsR2Ez"
        "bGxNMVJ2WDI4emMyWm5TV2xWVVRSTlJFaEtPRXRhWWtwWGFGRnJOSEZ6UmtWM1ZuUjFXR2RoYVRS"
        "dWFWRllVekJzY1RKaWNteFNjR3A2YTBGT2IxbDFURElTRjFWTGVHcGhkRU5GU1UxcGNqRnpVVkJm"
        "WW5aMGQxRnpHaUpCUkhOeU9XWlVVMmhSTTE5WVpsbENhM1JoUzBKeWNtOXVOWGhJVFRkbldVRjMi"
        "LCJmY3YiOiIzIiwiZmNfaWQiOiI1cDY5aHhNekZtUXJsTHFpQUFBQUFBPT0ifQ=="
    )
    # first_seen 2026-07-24T19:47:41 -- 90 minutes later, NO "hl", different fc
    BLOB_B = (
        "eyJqb2JfdGl0bGUiOiJbUmVtb3RlXSBTZW5pb3IgQWkgU29sdXRpb25zIEVuZ2luZWVyIiwiY29t"
        "cGFueV9uYW1lIjoiMTVGaXZlIiwiaHRpZG9jaWQiOiI1cDY5aHhNekZtUXJsTHFpQUFBQUFBPT0i"
        "LCJ1dWxlIjoidytDQUlRSUNJTlZXNXBkR1ZrSUZOMFlYUmxjdyIsImdsIjoidXMiLCJmYyI6IkVz"
        "d0JDb3dCUVVwcFZEUjBURWRhYzJ4NGVVMU1VMGx0Um1oWWFYVkRSMEprTUVob1gxZFJTMHg1WVda"
        "Q1pWQmxlVFJoZEhadE9VeDBTSGR3TFZoVlIxTTRZakV3VEhZd2JtMVRWRTVNVW5SVWNHZDFTbll3"
        "U2xCdU1WbEhVRmhmVTE5RlVrOUtlRjlKYTBOUlIydG5TMVJzYTFZdE5FTTFabGs0UWs1WFRIaHNl"
        "R040WTNZeVZFOWljRnBrWTJkRWVtSVNGMVZ6Um1waGRqWnZSMk0yZW0xMGExQnVZbVZIYlVGVkdp"
        "SkJSSE55T1daVFUyTlpTbkZ2ZG1ZNVZrUklSMmR5YXpVelRFRlphVE10UTBobiIsImZjdiI6IjMi"
        "LCJmY19pZCI6IjVwNjloeE16Rm1RcmxMcWlBQUFBQUE9PSJ9"
    )
    HTIDOCID = "5p69hxMzFmQrlLqiAAAAAA=="

    def test_decodes_real_blob(self):
        d = ids.decode_google_job_id(self.BLOB_A)
        self.assertEqual(d["htidocid"], self.HTIDOCID)
        self.assertEqual(d["company_name"], "15Five")

    def test_same_posting_two_fetches_one_id(self):
        """The whole point: the volatile fc token must not reach the key."""
        a = ids.google_source_id({"job_id": self.BLOB_A}, "15five")
        b = ids.google_source_id({"job_id": self.BLOB_B}, "15five")
        self.assertEqual(a, b)
        self.assertEqual(a, self.HTIDOCID)

    def test_raw_blob_would_have_differed(self):
        """Pins WHY the fix was needed, so nobody 'simplifies' it back."""
        self.assertNotEqual(self.BLOB_A, self.BLOB_B)

    def test_unpadded_blob_still_decodes(self):
        self.assertIsNotNone(
            ids.decode_google_job_id(self.BLOB_A.rstrip("=")))

    def test_garbage_decodes_to_none(self):
        for bad in (None, "", "not-base64!!", "aGVsbG8="):  # last is valid b64, not JSON
            self.assertIsNone(ids.decode_google_job_id(bad))

    def test_fingerprint_fallback_when_no_htidocid(self):
        job = {"job_id": None, "title": "Backend Engineer",
               "apply_options": [{"link": "https://x.com/j/1?utm_campaign=google_jobs_apply"}]}
        got = ids.google_source_id(job, "acme")
        self.assertTrue(got.startswith("fp:"))
        # tracking params and title whitespace/case must not change identity
        same = ids.google_source_id(
            {"job_id": None, "title": "  backend   engineer ",
             "apply_options": [{"link": "https://x.com/j/1"}]}, "acme")
        self.assertEqual(got, same)

    def test_fingerprint_excludes_location(self):
        """Google reports one remote posting as 'United States' and 'Anywhere'
        on different searches -- 37 such cases on the live table. Location
        must not participate in identity."""
        base = {"job_id": None, "title": "SRE",
                "apply_options": [{"link": "https://x.com/j/2"}]}
        self.assertEqual(
            ids.google_source_id({**base, "location": "United States"}, "acme"),
            ids.google_source_id({**base, "location": "Anywhere"}, "acme"))

    def test_different_postings_differ(self):
        a = ids.google_source_id(
            {"job_id": None, "title": "A", "apply_options": [{"link": "https://x/1"}]}, "acme")
        b = ids.google_source_id(
            {"job_id": None, "title": "B", "apply_options": [{"link": "https://x/2"}]}, "acme")
        self.assertNotEqual(a, b)

    def test_normalize_apply_url(self):
        self.assertEqual(
            ids.normalize_apply_url("https://x.com/j/1/?utm_source=g&b=2&a=1#frag"),
            "https://x.com/j/1?a=1&b=2")
        self.assertEqual(ids.normalize_apply_url(None), "")


class TestToUtc(unittest.TestCase):
    """The 4-hour bug: naive Socrata values are NYC local, not UTC."""

    def test_naive_socrata_is_nyc_local(self):
        got = timeparse.to_utc("2026-07-24T19:00:00.000")
        self.assertEqual(got, datetime(2026, 7, 24, 23, 0, tzinfo=timezone.utc),
                         "7pm EDT must become 23:00Z, not 19:00Z")

    def test_aware_value_is_trusted(self):
        got = timeparse.to_utc("2026-07-24T19:00:00+00:00")
        self.assertEqual(got, datetime(2026, 7, 24, 19, 0, tzinfo=timezone.utc))

    def test_winter_uses_est_not_edt(self):
        # Offset must come from the date, not a hard-coded -4.
        self.assertEqual(timeparse.to_utc("2026-01-15T19:00:00.000"),
                         datetime(2026, 1, 16, 0, 0, tzinfo=timezone.utc))

    def test_date_only_is_local_midnight(self):
        self.assertEqual(timeparse.to_utc("2026-07-25"),
                         datetime(2026, 7, 25, 4, 0, tzinfo=timezone.utc))

    def test_date_only_sorts_after_previous_day(self):
        """The prune bug: '2026-07-25' used to sort before
        '2026-07-25T00:00:00.000' as text, deleting same-day events."""
        self.assertGreater(timeparse.to_utc("2026-07-25"),
                           timeparse.to_utc("2026-07-24T23:00:00.000"))

    def test_epoch_seconds(self):
        self.assertEqual(timeparse.to_utc(1_800_000_000),
                         datetime.fromtimestamp(1_800_000_000, tz=timezone.utc))
        self.assertEqual(timeparse.to_utc("1800000000"),
                         datetime.fromtimestamp(1_800_000_000, tz=timezone.utc))

    def test_implausible_epoch_rejected(self):
        self.assertIsNone(timeparse.to_utc(0))

    def test_unparseable_returns_none(self):
        for bad in (None, "", "   ", "not a date", "TBD"):
            self.assertIsNone(timeparse.to_utc(bad), repr(bad))

    def test_datetime_and_date_objects(self):
        self.assertEqual(timeparse.to_utc(date(2026, 7, 25)),
                         datetime(2026, 7, 25, 4, 0, tzinfo=timezone.utc))
        aware = datetime(2026, 7, 24, 19, 0, tzinfo=timezone.utc)
        self.assertEqual(timeparse.to_utc(aware), aware)

    def test_bookkeeping_format_is_stable(self):
        """jobs/ compares these as strings and uses '' as a sentinel that
        must sort first, so the format must not gain an offset."""
        now = timeparse.utc_now_str()
        self.assertRegex(now, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")
        self.assertLess("", now)


class TestTableSpec(unittest.TestCase):
    """`computed` is exercised with this pipeline's own expressions.

    The shared version of this class used GEOG_EXPR, which is events-only and
    is not in this repo's upsert.py -- see lib/state.py's note on what each
    copy carries. jobs' real `computed` is the status/closed_at reopen pair
    from schema.spec(), so that is what is tested here.
    """

    def _spec(self, **kw):
        return upsert.TableSpec(
            table="jobs", columns=("title", "location_raw", "job_url"),
            hash_fields=("title",), **kw)

    def test_insert_includes_computed_and_bookkeeping(self):
        sql = self._spec(
            computed={"status": "'open'", "closed_at": "NULL"}).insert_sql()
        self.assertIn("INSERT INTO jobs", sql)
        self.assertIn("status", sql)
        self.assertIn("%(job_url)s", sql)   # bound, never interpolated
        for col in ("content_hash", "first_seen", "last_seen"):
            self.assertIn(col, sql)

    def test_computed_applies_on_update_too(self):
        """A row reappearing upstream must be reopened, not left closed."""
        sql = self._spec(
            computed={"status": "'open'", "closed_at": "NULL"}).update_sql()
        self.assertIn("status='open'", sql)
        self.assertIn("closed_at=NULL", sql)

    def test_update_never_touches_first_seen(self):
        sql = self._spec().update_sql()
        self.assertNotIn("first_seen", sql)
        self.assertIn("last_seen=%(last_seen)s", sql)

    def test_revive_column_selected(self):
        spec = self._spec(revive_column="status", revive_value="open")
        self.assertIn("status", spec.select_sql())

    def test_rejects_unsafe_identifier(self):
        with self.assertRaises(ValueError):
            upsert.TableSpec(table="events; DROP TABLE events",
                             columns=(), hash_fields=())

    def test_computed_expressions_are_not_interpolated_per_row(self):
        """The SQL text must stop varying per row, so the plan is cacheable
        and a value can never be spliced into the statement."""
        sql = self._spec(
            computed={"status": "'open'", "closed_at": "NULL"}).insert_sql()
        self.assertNotIn("{", sql)


class TestStickyColumns(unittest.TestCase):
    """The sliding posted_at, found in slice D.

    Google reports publication as "23 days ago", which resolves to a different
    absolute time on every ingest. Without sticky, the stored date drifts later
    on every re-see AND the row hashes as changed every time, so it can never
    be counted unchanged.
    """

    def _spec(self, sticky=("posted_at",), revive=False):
        kw = dict(revive_column="status", revive_value="open") if revive else {}
        return upsert.TableSpec(
            table="jobs", columns=("title", "posted_at"),
            hash_fields=("title", "posted_at"), sticky=sticky, **kw)

    def test_sticky_columns_are_selected_back(self):
        self.assertIn("posted_at", self._spec().select_sql())

    def test_sticky_offset_accounts_for_revive_column(self):
        self.assertEqual(self._spec().sticky_offset(), 1)
        self.assertEqual(self._spec(revive=True).sticky_offset(), 2)

    def test_sticky_must_be_a_written_column(self):
        with self.assertRaises(ValueError):
            upsert.TableSpec(table="jobs", columns=("title",),
                             hash_fields=("title",), sticky=("posted_at",))

    def test_existing_row_keeps_its_first_posted_at(self):
        spec = self._spec()
        stored_hash = ids.content_hash(
            {"title": "Engineer", "posted_at": "2026-07-01T00:00:00+00:00"},
            spec.hash_fields)
        conn = _FakeConn(existing=(stored_hash, "2026-07-01T00:00:00+00:00"))

        # Same posting, re-derived a fortnight later from "23 days ago".
        result = upsert.upsert(
            conn, spec,
            [{"title": "Engineer", "posted_at": "2026-07-15T00:00:00+00:00"}],
            lambda rec: "id1", now="2026-07-15T00:00:00")

        self.assertEqual((result.new, result.updated, result.unchanged), (0, 0, 1),
                         "a re-seen posting whose only change is the sliding "
                         "timestamp must count as unchanged")
        self.assertEqual(result.errors, [])
        # Nothing but the last_seen touch should have been written.
        written = [s for s, _ in conn.statements if s.startswith("UPDATE")]
        self.assertTrue(all("last_seen" in s and "posted_at" not in s
                            for s in written), written)

    def test_without_sticky_the_same_row_churns(self):
        """Pins the bug itself, so a regression is visible as a behaviour flip."""
        spec = self._spec(sticky=())
        stored_hash = ids.content_hash(
            {"title": "Engineer", "posted_at": "2026-07-01T00:00:00+00:00"},
            spec.hash_fields)
        conn = _FakeConn(existing=(stored_hash,))
        result = upsert.upsert(
            conn, spec,
            [{"title": "Engineer", "posted_at": "2026-07-15T00:00:00+00:00"}],
            lambda rec: "id1", now="2026-07-15T00:00:00")
        self.assertEqual((result.new, result.updated, result.unchanged), (0, 1, 0))

    def test_new_row_still_takes_the_incoming_value(self):
        spec = self._spec()
        conn = _FakeConn(existing=None)
        result = upsert.upsert(
            conn, spec,
            [{"title": "Engineer", "posted_at": "2026-07-15T00:00:00+00:00"}],
            lambda rec: "id1", now="2026-07-15T00:00:00")
        self.assertEqual((result.new, result.updated, result.unchanged), (1, 0, 0))
        insert = next(p for s, p in conn.statements if s.startswith("INSERT"))
        self.assertEqual(insert["posted_at"], "2026-07-15T00:00:00+00:00")

    def test_a_real_change_still_updates(self):
        """Sticky must not mask a genuine edit to a non-sticky field."""
        spec = self._spec()
        stored_hash = ids.content_hash(
            {"title": "Engineer", "posted_at": "2026-07-01T00:00:00+00:00"},
            spec.hash_fields)
        conn = _FakeConn(existing=(stored_hash, "2026-07-01T00:00:00+00:00"))
        result = upsert.upsert(
            conn, spec,
            [{"title": "Senior Engineer", "posted_at": "2026-07-15T00:00:00+00:00"}],
            lambda rec: "id1", now="2026-07-15T00:00:00")
        self.assertEqual((result.new, result.updated, result.unchanged), (0, 1, 0))
        update = next(p for s, p in conn.statements if s.startswith("UPDATE")
                      and "title" in s)
        self.assertEqual(update["title"], "Senior Engineer")
        self.assertEqual(update["posted_at"], "2026-07-01T00:00:00+00:00",
                         "the update must carry the PINNED date, not the new one")
