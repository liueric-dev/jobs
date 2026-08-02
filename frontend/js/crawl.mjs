// Read the whole list, once, as one render.
//
// WHY A CRAWL EXISTS AT ALL. Two screens need something GET /v1/jobs does not
// offer. Saved needs "the rows where saved is true" and there is no state
// filter among the eight query parameters (backend/webapp/jobs.py:337-348).
// A detail page reached cold -- a reload on #/job/<id>, a pasted link -- needs
// a `request_id`, and the ONLY way to obtain one is to render a list: it is
// minted server-side per render (jobs.py:164-179, :370) and POST /v1/events
// refuses a batch without one (`missing_request_id`, jobs.py:529-532). Both are
// backend gaps recorded in frontend/README.md, not client preferences.
//
// IT IS ONE RENDER. Following next_cursor continues the render page one
// started -- the id and the next rank ride inside the cursor
// (jobs.py:193-215) -- so ranks run 1..N across the whole crawl and every
// event echoing them is telling the truth about position.
//
// IT EMITS NO IMPRESSIONS, and callers must not add any. Nothing here was put
// in front of a person. Emitting impressions would also arm derive_skips
// (jobs.py:723-750), which turns every impression above an `open` into a
// stored negative -- fabricated negatives for postings nobody was shown.

import { listJobs } from "./api.mjs";
import { remember } from "./renders.mjs";

/** The endpoint's own ceiling (MAX_LIMIT, jobs.py:40). */
export const CRAWL_LIMIT = 100;

/** jobs_app holds 166 rows for `pursuit` (measured 2026-08-02), so two
 *  requests. The cap is what keeps this from becoming thirty silent requests
 *  the day the corpus is ten times larger -- it degrades into a truncated list
 *  with a visible message instead. */
export const MAX_PAGES = 8;

/**
 * Every row this Builder can see, in one render.
 *
 * Returns {requestId, jobs, truncated}. Dismissed postings are absent: the
 * list hides them by default (jobs.py:364-365) and `include_dismissed` is
 * documented as debugging only and explicitly not part of the client contract
 * (jobs.py:346, :362-364), so this does not reach for it.
 */
export async function crawlAll({ limit = CRAWL_LIMIT, maxPages = MAX_PAGES } = {}) {
  const jobs = [];
  let requestId = null;
  let cursor = null;
  for (let page = 0; page < maxPages; page++) {
    const body = await listJobs({ limit, cursor });
    if (requestId === null) requestId = body.request_id;
    remember(body.request_id, body.jobs);
    jobs.push(...body.jobs);
    cursor = body.next_cursor;
    if (!cursor) return { requestId, jobs, truncated: false };
  }
  return { requestId, jobs, truncated: true };
}
