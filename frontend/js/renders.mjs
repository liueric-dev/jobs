// Which render a posting was last seen in, and at what rank.
//
// WHY THIS IS A MODULE AND NOT A LOCAL IN today.js. An `open` is raised from
// the DETAIL page, and `open` is one of the two events the server refuses
// without a rank (RANK_REQUIRED_EVENTS, backend/webapp/jobs.py:91). The rank
// belongs to the list the Builder tapped from, which by then has been torn
// down. So the list records it on the way past and the detail page reads it.
//
// LAST WRITE WINS, and that is the right answer rather than a convenience:
// Today and a Saved crawl are two different renders, and the position the
// Builder acted from is the one they most recently saw.
//
// A COLD DEEP LINK HAS NO CONTEXT. Reloading on #/job/<id>, or pasting the
// URL, finds nothing here -- and POST /v1/events refuses a batch with no
// request_id at all (`missing_request_id`, backend/webapp/jobs.py:682-685), so
// without one the detail page could record nothing, not even a save. resolve()
// below renders a real list to obtain a real render id rather than fabricating
// a string. If that render also contains the posting, its real rank comes with
// it; if it does not -- a dismissed posting, which the list hides and the
// detail endpoint still serves -- the rank stays null and only the events that
// legitimately have no position are sent. Inventing a rank is precisely the
// sentinel task 27 refused in the schema.

import { crawlAll } from "./crawl.mjs";

/** job_id -> {requestId, rank} */
const seen = new Map();

export function remember(requestId, jobs) {
  for (const job of jobs) {
    if (job.rank == null) continue;
    seen.set(job.id, { requestId, rank: job.rank });
  }
}

export function contextFor(jobId) {
  return seen.get(jobId) || null;
}

/**
 * The render context for a posting, fetching one if this session has none.
 *
 * Returns {requestId, rank} with a real rank when the crawl found the row,
 * {requestId, rank: null} when it did not, and null when even the crawl
 * failed -- in which case the caller records nothing, which is the correct
 * outcome rather than a degraded one.
 */
export async function resolve(jobId) {
  const known = contextFor(jobId);
  if (known) return known;
  try {
    const { requestId } = await crawlAll();
    return contextFor(jobId) || { requestId, rank: null };
  } catch (e) {
    console.warn("could not obtain a render id; events will not be sent", e);
    return null;
  }
}

export function forgetAll() {
  seen.clear();
}
