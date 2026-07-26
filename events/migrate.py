#!/usr/bin/env python3
"""One-off, idempotent migration of `public.events` onto the pipelib schema.

Checked in rather than run ad hoc so it is reviewable, repeatable, and
reports what it changed. Every step is a no-op the second time.

    python3 events/migrate.py              # dry run -- counts only, no writes
    python3 events/migrate.py --apply      # perform the migration

DRY RUN IS THE DEFAULT deliberately: this rewrites tens of thousands of
rows and deletes a majority of one source. Run it against a restored
pg_dump snapshot before touching the live database.

STEPS
  1. Schema        add start_ts/end_ts + indexes (events/schema.py).
  2. Timestamps    parse the TEXT columns into real instants. Socrata's
                   naive strings are America/New_York local; NYPL/QPL are
                   already UTC. Storing both in one TEXT column meant they
                   string-compared as if on the same clock -- a 4-hour error.
  3. Parks times   all 1,175 nyc_parks_events rows sit at midnight because
                   the normalizer took date-only `startdate` and discarded
                   `starttime` as unreliable. Measured across every row:
                   `starttime`'s DATE is indeed always stale, but its
                   TIME-OF-DAY is sound (10am peak, zero midnights). So the
                   fix is date-from-startdate + time-from-starttime, which
                   recovers all 1,175 without refetching.
  4. Non-events    drop permitted rows that are not public events, using
                   schema.is_public_event -- the same predicate the ingest
                   filters with. Originally the `Sport - Youth`/`Sport -
                   Adult` purge (24,237 rows, 79% of the source); now also
                   the generic private-permit titles ("Miscellaneous",
                   "Celebration", "Picnic", "Barbecue", "Party" -- 2,438
                   rows) and 152 park closures. prune_expired will not
                   remove these on its own: it only drops rows outside the
                   date window, so rows the pipeline has stopped writing
                   would linger for up to 90 days.
  5. Geocode reset truncate `geocode_failed`. It had become a permanent
                   blocklist (2,720 rows, consulted with no expiry), so the
                   addresses that failed under the old facility-code parser
                   could never recover. events/geocode.py now expires failures.
  6. Park lookup   populate `park_locations` from NYC Parks Properties and
                   resolve the park-coded addresses locally -- no
                   rate-limited calls. Measured coverage: 91.8% of the
                   park-coded rows worth keeping.
  7. Watermarks    delete the two Socrata watermarks so the next scheduled
                   run refetches the full window once and re-normalizes
                   every stored row. Without this the parks borough and the
                   description fixes never reach rows that have not changed
                   upstream, because `:updated_at` filters them out.

Any step that touches a hash field (start_datetime, latitude, longitude)
recomputes content_hash with the same function the ingest scripts use, so
the next scheduled run sees "unchanged" rather than re-updating every row.
"""

import argparse
import json
import os
import sys

_d = os.path.dirname(os.path.abspath(__file__))
while _d != os.path.dirname(_d) and not os.path.isdir(os.path.join(_d, "pipelib")):
    _d = os.path.dirname(_d)
sys.path.insert(0, _d)

import geocode  # noqa: E402  (events/geocode.py, same directory)
import schema  # noqa: E402  (events/schema.py, same directory)
from pipelib import dbconn, ids  # noqa: E402
from pipelib.timeparse import to_utc, utc_now_str  # noqa: E402

#: Was a local copy of the category list, which had already drifted from the
#: ingest script's. Both now read schema.is_public_event, so a row deleted
#: here is a row the next run will not re-admit.
DROP_CATEGORIES = tuple(sorted(schema.DROPPED_CATEGORIES))


def step(label, n, apply_):
    verb = "would" if not apply_ else ""
    print(f"  {label:<34} {n:>7} rows {verb}".rstrip())
    return n


# -- 2. timestamps -----------------------------------------------------------

def backfill_timestamps(conn, apply_):
    rows = conn.execute("""
        SELECT id, start_datetime, end_datetime FROM events
        WHERE start_ts IS NULL AND start_datetime IS NOT NULL
    """).fetchall()
    if not apply_:
        return step("timestamps to backfill", len(rows), apply_)

    done = unparseable = 0
    for rec_id, raw_start, raw_end in rows:
        start_ts = to_utc(raw_start)
        if start_ts is None:
            unparseable += 1
            continue
        conn.execute("UPDATE events SET start_ts = %s, end_ts = %s WHERE id = %s",
                     (start_ts, to_utc(raw_end), rec_id))
        done += 1
    conn.commit()
    step("timestamps backfilled", done, apply_)
    if unparseable:
        print(f"    ! {unparseable} rows had unparseable start_datetime "
              f"(left NULL, will not be pruned)")
    return done


# -- 3. parks time recovery --------------------------------------------------

def recover_parks_times(conn, apply_):
    """Combine the authoritative date with the usable time-of-day."""
    if not apply_:
        # start_ts is still NULL during a dry run (step 2 hasn't written), so
        # count off the TEXT column instead -- otherwise this always reports 0.
        n = conn.execute("""
            SELECT count(*) FROM events
            WHERE source = %s AND start_datetime LIKE '%%T00:00:00%%'
        """, (schema.SOURCE_PARKS,)).fetchone()[0]
        return step("parks rows at midnight", n, apply_)

    rows = conn.execute("""
        SELECT id, source_id, title, raw_json FROM events
        WHERE source = %s AND start_ts IS NOT NULL
          AND (start_ts AT TIME ZONE 'America/New_York')::time = '00:00'
    """, (schema.SOURCE_PARKS,)).fetchall()

    fixed = 0
    for rec_id, source_id, title, raw in rows:
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            continue
        start = _combine(data.get("startdate"), data.get("starttime"))
        if not start:
            continue
        end = _combine(data.get("enddate"), data.get("endtime"))

        current = conn.execute(
            "SELECT " + ", ".join(schema.HASH_FIELDS) + " FROM events WHERE id = %s",
            (rec_id,)).fetchone()
        rec = dict(zip(schema.HASH_FIELDS, current))
        rec["start_datetime"], rec["end_datetime"] = start, end

        # start_datetime is part of the primary key, so recovering the time
        # changes the id. Without re-keying here, the next ingest run mints
        # the new id and the migrated row survives under the old one --
        # every parks event stored twice. (Found exactly that way: a first
        # pass produced 1,175 duplicated guids.)
        new_id = schema.make_event_id({
            "source": schema.SOURCE_PARKS, "source_id": source_id,
            "title": title, "start_datetime": start})
        if new_id != rec_id:
            conn.execute("DELETE FROM events WHERE id = %s", (new_id,))

        conn.execute("""
            UPDATE events SET id = %s, start_datetime = %s, end_datetime = %s,
                              start_ts = %s, end_ts = %s, content_hash = %s
            WHERE id = %s
        """, (new_id, start, end, to_utc(start), to_utc(end),
              ids.content_hash(rec, schema.HASH_FIELDS), rec_id))
        fixed += 1
    conn.commit()
    return step("parks times recovered", fixed, apply_)


def _combine(date_part, time_part):
    """'2026-07-24T00:00:00.000' + '2026-07-20 11:00:00' -> '2026-07-24T11:00:00.000'.

    The date comes from `startdate`, which is authoritative. The clock time
    comes from `starttime`, whose own date is stale in every row measured
    but whose time-of-day is correct.
    """
    if not date_part:
        return None
    day = str(date_part)[:10]
    clock = str(time_part)[11:19] if time_part and len(str(time_part)) >= 19 else None
    return f"{day}T{clock}.000" if clock else str(date_part)


# -- 4. non-event purge ------------------------------------------------------

def drop_non_events(conn, apply_):
    """Delete stored permitted rows that are not public events.

    Category-only deletion is not enough. The ingest filter now also rejects
    generic private-permit titles and park closures, and prune_expired only
    removes rows outside the date window -- so without this, 2,590 rows the
    pipeline will never write again would sit in the table until they aged
    out, up to 90 days of serving somebody's wedding permit as an event.

    Evaluated in Python against the same predicate the ingest uses rather
    than as SQL, so there is exactly one definition of the rule.
    """
    rows = conn.execute(
        "SELECT id, title, categories FROM events WHERE source = %s",
        (schema.SOURCE_PERMITTED,)).fetchall()
    doomed = [r[0] for r in rows if not schema.is_public_event(r[1], r[2])]
    if apply_ and doomed:
        conn.execute("DELETE FROM events WHERE id = ANY(%s)", (doomed,))
        conn.commit()
    return step("non-events dropped", len(doomed), apply_)


# -- 5/6. geocoding ----------------------------------------------------------

def retire_legacy_progress_tables(conn, apply_):
    """Fold `library_ingest_progress` and `fetch_progress` into `ingest_progress`.

    pipelib.state unified the two -- they were the same mechanism with an
    off-by-one between them (one stored the next page, the other the last
    completed page). Only rows still mid-walk are worth carrying over; a
    completed cursor is just its start page, which is the default anyway.
    """
    legacy = [t for t in ("library_ingest_progress", "fetch_progress")
              if conn.execute("SELECT to_regclass(%s)", (f"public.{t}",)).fetchone()[0]]
    if not legacy:
        return step("legacy progress tables", 0, apply_)
    if not apply_:
        return step("legacy progress tables to retire", len(legacy), apply_)

    carried = 0
    if "library_ingest_progress" in legacy:
        rows = conn.execute(
            "SELECT job_key, next_page FROM library_ingest_progress "
            "WHERE next_page > 1").fetchall()
        for job_key, next_page in rows:
            conn.execute("""
                INSERT INTO ingest_progress (run_key, source, next_page, status, updated_at)
                VALUES (%s, %s, %s, 'in_progress', %s)
                ON CONFLICT (run_key) DO NOTHING
            """, (job_key, job_key.split(":")[0], next_page, utc_now_str()))
            carried += 1
    for table in legacy:
        conn.execute(f"DROP TABLE IF EXISTS {table}")
    conn.commit()
    print(f"    dropped {', '.join(legacy)}; carried {carried} in-progress cursor(s)")
    return step("legacy progress tables retired", len(legacy), apply_)


def reset_failed_geocodes(conn, apply_):
    n = conn.execute("SELECT count(*) FROM geocode_failed").fetchone()[0]
    if apply_:
        conn.execute("TRUNCATE geocode_failed")
        conn.commit()
    return step("stale geocode failures cleared", n, apply_)


def reset_opendata_watermarks(conn, apply_):
    """Force the next run to re-normalize every in-window Socrata row.

    The Socrata jobs filter on `:updated_at > <last success>`, so a row that
    has not changed upstream is never refetched -- and therefore never
    re-normalized. Three normalizer fixes (parks borough, parks description
    unescaping, permitted description no longer duplicating the category)
    only reach stored rows if the rows come back through the pipeline.

    Deleting the watermark is the whole fix: the next run refetches the full
    90-day window once, content hashing reports the genuinely-changed rows as
    updated, and the watermark re-establishes itself. Rewriting the columns
    here instead would mean a second copy of each normalizer, which is what
    put the borough logic out of sync in the first place.

    Costs one unfiltered fetch of each dataset -- ~7k rows, well inside the
    max_pages valve.
    """
    datasets = ("permitted_events", "parks_events")
    n = conn.execute("SELECT count(*) FROM ingest_state WHERE dataset = ANY(%s)",
                     (list(datasets),)).fetchone()[0]
    if apply_ and n:
        conn.execute("DELETE FROM ingest_state WHERE dataset = ANY(%s)",
                     (list(datasets),))
        conn.commit()
    return step("Socrata watermarks reset (forces one full refetch)", n, apply_)


def backfill_park_coords(conn, geo_conn, apply_, debug=False):
    """Resolve park-coded addresses locally. No network per row."""
    if not apply_:
        # Exclude the categories step 4 removes -- otherwise this counts
        # 24k sport rows that will no longer exist by the time this runs.
        n = conn.execute("""
            SELECT count(*) FROM events
            WHERE latitude IS NULL AND address IS NOT NULL AND address LIKE '%%:%%'
              AND NOT (source = %s AND categories = ANY(%s))
        """, (schema.SOURCE_PERMITTED, list(DROP_CATEGORIES))).fetchone()[0]
        return step("park-coded addresses to resolve", n, apply_)

    geocode.refresh_park_locations(geo_conn, debug=debug)
    total = geo_conn.execute("SELECT count(*) FROM park_locations").fetchone()[0]
    print(f"    park_locations: {total} entries")

    rows = conn.execute("""
        SELECT id, address FROM events
        WHERE latitude IS NULL AND address IS NOT NULL AND address LIKE '%:%'
    """).fetchall()

    fixed = 0
    for rec_id, address in rows:
        lat, lon = geocode.geocode(geo_conn, address, allow_remote=False, debug=debug)
        if lat is None:
            continue
        current = conn.execute(
            "SELECT " + ", ".join(schema.HASH_FIELDS) + " FROM events WHERE id = %s",
            (rec_id,)).fetchone()
        rec = dict(zip(schema.HASH_FIELDS, current))
        rec["latitude"], rec["longitude"] = lat, lon
        conn.execute("""
            UPDATE events SET latitude = %s, longitude = %s, content_hash = %s,
                geog = ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
            WHERE id = %s
        """, (lat, lon, ids.content_hash(rec, schema.HASH_FIELDS), lon, lat, rec_id))
        fixed += 1
        if fixed % 500 == 0:
            conn.commit()
    conn.commit()
    return step("coordinates recovered", fixed, apply_)


# -- reporting ---------------------------------------------------------------

def snapshot(conn):
    return {
        "rows": conn.execute("SELECT count(*) FROM events").fetchone()[0],
        "with_ts": conn.execute(
            "SELECT count(*) FROM events WHERE start_ts IS NOT NULL").fetchone()[0],
        "with_geog": conn.execute(
            "SELECT count(*) FROM events WHERE geog IS NOT NULL").fetchone()[0],
        "parks_midnight": conn.execute(
            "SELECT count(*) FROM events WHERE source = %s AND start_ts IS NOT NULL "
            "AND (start_ts AT TIME ZONE 'America/New_York')::time = '00:00'",
            (schema.SOURCE_PARKS,)).fetchone()[0],
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--apply", action="store_true",
                    help="perform the migration (default: dry run)")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    conn = dbconn.connect_or_exit("events migrate")
    geo_conn = dbconn.connect(autocommit=True)

    schema.ensure_schema(conn)
    geocode.ensure_geocode_schema(geo_conn)

    before = snapshot(conn)
    print(f"{'DRY RUN -- no writes' if not args.apply else 'APPLYING'}")
    print(f"before: {before}\n")

    backfill_timestamps(conn, args.apply)
    recover_parks_times(conn, args.apply)
    drop_non_events(conn, args.apply)
    retire_legacy_progress_tables(conn, args.apply)
    reset_failed_geocodes(geo_conn, args.apply)
    backfill_park_coords(conn, geo_conn, args.apply, debug=args.debug)
    # Last: it makes the next scheduled run re-normalize everything the
    # steps above just corrected, so it must not run before them.
    reset_opendata_watermarks(conn, args.apply)

    after = snapshot(conn)
    print(f"\nafter:  {after}")
    if args.apply:
        for key in before:
            delta = after[key] - before[key]
            if delta:
                print(f"  {key:<16} {before[key]:>7} -> {after[key]:>7} ({delta:+})")
    else:
        print("\nRe-run with --apply to perform the migration.")

    conn.close()
    geo_conn.close()


if __name__ == "__main__":
    main()
