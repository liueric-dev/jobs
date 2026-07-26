"""The record shape for Google Jobs postings, shared by all three consumers.

WHY THIS MODULE EXISTS
    Google Jobs reaches this pipeline three ways -- ingest/google-serpapi.py,
    ingest/google-apify.py, and contributors posting to api/. Until slice D
    each carried its own copy of normalize_job(), and the API's copy had drifted
    four ways: it truncated descriptions at 5000 instead of 20000, its relative
    time parser did not understand minutes, bare articles ("an hour ago") or
    "yesterday", it sliced serialized JSON mid-string instead of using
    bounded_json, and it omitted posted_at_ts and salary_text entirely.

    Two of those feed content_hash. description_text and posted_at are both in
    HASH_FIELDS_SHORT (schema.py), so the same posting written by the pipeline
    and then by the API produced two different digests -- meaning each write
    counted the row as "updated" and rewrote it, flip-flopping the same row on
    alternating runs. It stayed latent only because the API was never deployed.

    So the rule is not "keep these three in sync". It is that there is one
    copy and the question cannot come up.

WHY NOT IN pipelib
    pipelib's membership rule is mechanism, never schema, and this is schema:
    it names this application's columns. It is shared between the pipeline and
    the API because those are two halves of one application, which is exactly
    what slice D merged them into one repo to express. events must never import
    it.

WHY THE APIFY AND SERPAPI PAYLOADS CAN SHARE ONE FUNCTION
    The Apify actor's output schema matches SerpApi's field-for-field --
    confirmed live, the same job_id for the same posting via both paths. That
    is also why they must derive source_id identically: the two sources
    returning the same posting is supposed to be one row, and it only stays one
    row while both key it the same way.
"""

from pipelib import ids, text

#: Ceiling on the stored raw payload. Deliberately a separate constant from
#: text.MAX_DESCRIPTION_CHARS even though both are currently 20000: that one
#: bounds one field, this one bounds the whole serialized blob. They are equal
#: by coincidence, and collapsing them would tie two unrelated limits together.
RAW_JSON_LIMIT = 20000


def normalize_job(job, mode):
    """Derive every stored field from the RAW posting payload.

    SECURITY-RELEVANT, and the reason api/ calls this rather than accepting
    client-computed fields: platform/company_token/source_id feed make_id(),
    which is the cross-source dedup key. Letting a client set those directly
    would let a hostile contributor overwrite arbitrary existing rows -- e.g.
    claiming a Greenhouse posting's id and replacing its URL. Recomputing here
    means the worst a bad payload can do is insert junk under its own derived
    id, never clobber another source's.

    `source_id` is ids.google_source_id(), NOT the raw `job_id`. The raw blob
    embeds a per-search token that rotates on every fresh fetch, so using it
    minted a new primary key for an already-stored posting on every run -- 32%
    duplicate rows (837 rows holding 632 real postings) on the live table. See
    the Google Jobs section of pipelib/ids.py for the full autopsy.

    Note the fallback branch of google_source_id() depends on the apply URL,
    which a contributor controls. That is still client-derived-but-recomputed,
    never client-supplied.
    """
    title = job.get("title")
    company_name = job.get("company_name") or "Unknown"
    location = job.get("location")
    detected = job.get("detected_extensions") or {}
    apply_options = job.get("apply_options") or []
    company_token = text.slugify(company_name)

    is_nyc = bool(text.NYC_PATTERN.search(location or ""))
    is_remote = bool(text.REMOTE_PATTERN.search(location or "")) or mode == "remote"

    return {
        "platform": "google_jobs",
        "company_token": company_token,
        "company_name": company_name,
        "source_id": ids.google_source_id(job, company_token),
        "title": title,
        "location_raw": location,
        "department": detected.get("schedule_type"),
        "job_url": (apply_options[0].get("link") if apply_options else None) or job.get("share_link"),
        "posted_at": text.parse_relative_posted_at(detected.get("posted_at")),
        "posted_at_ts": text.parse_relative_posted_at(detected.get("posted_at")),
        "salary_text": (detected.get("salary") or None),
        "seniority_guess": text.guess_seniority(title),
        "location_is_nyc": is_nyc,
        "location_is_remote": is_remote,
        "company_is_nyc_hq": None,
        "company_is_ai_focused": None,
        "description_text": text.strip_html(job.get("description")),
        # NOT json.dumps(job)[:limit] -- that slices serialized JSON mid-string
        # and stored 10 unparseable stumps in the live table. bounded_json
        # shrinks the description field instead, so the result still parses.
        "raw_json": text.bounded_json(job, RAW_JSON_LIMIT),
    }
