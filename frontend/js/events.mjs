// The event loop: what the client tells the server about what the Builder did.
//
// THE ONE REQUIREMENT THAT CANNOT BE ADDED LATER (32-frontend.md § Non-
// negotiable): every event echoes the `request_id` of the render it came from
// and the `rank` the row actually had. Impressions logged without position are
// permanently unusable, and there is no backfill -- .claude/CLAUDE.md's "do not
// backfill rank on existing job_events rows" is the same rule seen from the
// other side.
//
// A RENDER SPANS PAGES. GET /v1/jobs mints a request_id on an un-cursored call
// and carries it inside the cursor thereafter (backend/webapp/jobs.py:210-232,
// :464-468), so page two of the same render continues both the id and the rank
// sequence. This module therefore keys everything on request_id and never
// assumes there is only one live render: Today and a Saved crawl are two, and
// a queued event from the first must not be posted under the second's id.
// POST /v1/events takes exactly one request_id per body, so drain() groups.
//
// IMPRESSIONS FIRE ON VISIBILITY, NOT ON PAYLOAD RECEIPT. observe() below is
// an IntersectionObserver with a dwell timer; a row that scrolled past in 80ms
// was not examined. Recording it would poison the skip derivation, which reads
// impressions and treats everything above an `open` as passed over
// (jobs.py:772-781).
//
// ORDER MATTERS AT THE SERVER. derive_skips runs inside the `open`'s own
// transaction and looks for impressions ALREADY IN THE TABLE for that render.
// An impression queued but not yet posted, followed by an open, derives
// nothing. Everything therefore goes through one serialised chain, in the
// order it happened.

import { postEvents, ApiError } from "./api.mjs";

/** Batched impressions go out at least this often. */
const FLUSH_INTERVAL_MS = 3000;
/** ...or as soon as this many are waiting. The server caps a batch at 200
 *  (EventBatch.events, jobs.py:646); staying well under it keeps a page of
 *  impressions plus the actions raised from it inside one request. */
const FLUSH_AT = 40;
/** How long a row must stay visible before it counts as examined. */
export const IMPRESSION_DWELL_MS = 500;
/** How much of a row must be on screen. */
export const IMPRESSION_RATIO = 0.5;

/** Queued events, in the order they happened, each tagged with its render. */
const queue = [];
/** (requestId, jobId) pairs already reported, so a re-scroll is not a second
 *  impression. The server also dedups, by (app_user_id, job_id) for 24 hours
 *  (jobs.py:104, :1000-1003) -- this is about not sending, not correctness. */
const impressed = new Set();

let timer = null;
/** One serialised chain, so two flushes can never interleave two renders. */
let chain = Promise.resolve(null);

/** Called with an ApiError when a batch is refused. Set by app.js. */
let onError = () => {};
export function setErrorHandler(fn) { onError = fn; }

/**
 * Drop the sent-impression memory. Called on sign-out, with renders.forgetAll().
 *
 * `impressed` is keyed (requestId, jobId) and requestId is per render, so a new
 * Builder's renders could not collide with an old one's -- but the Set is the
 * only thing in this module that outlives a session, and leaving one user's
 * state in memory while another is signed in is the shape of the bug, not the
 * collision itself. It costs nothing to clear and it means "signed out" is
 * true of this module too.
 */
export function forgetImpressions() { impressed.clear(); }

function schedule() {
  if (timer !== null) return;
  timer = setTimeout(() => { timer = null; flush(); }, FLUSH_INTERVAL_MS);
}

function enqueue(requestId, event) {
  if (!requestId) {
    // Not recoverable by inventing one: request_id is minted server-side
    // precisely so two clients cannot collide (jobs.py:181-196).
    console.warn("dropping event with no request_id", event);
    return;
  }
  queue.push({ requestId, event });
}

/** Strip undefined/null so the body carries only fields that mean something.
 *  An explicit null rank reads as a claim; omitting it is what the contract's
 *  rank-less `save` and `applied` actually are (jobs.py:83-91). */
function clean(event) {
  const out = {};
  for (const [k, v] of Object.entries(event)) {
    if (v !== undefined && v !== null) out[k] = v;
  }
  return out;
}

function groupByRender(batch) {
  const byRender = new Map();
  for (const { requestId, event } of batch) {
    if (!byRender.has(requestId)) byRender.set(requestId, []);
    byRender.get(requestId).push(clean(event));
  }
  return byRender;
}

/**
 * Record that a row was actually looked at.
 *
 * `rank` is the server's, from the payload. Never a DOM index: the list is
 * grouped by track for display, so the position on screen and the position in
 * the render are different numbers, and only one of them is the ordering the
 * ranker produced.
 */
export function impression(requestId, jobId, rank) {
  const key = `${requestId} ${jobId}`;
  if (impressed.has(key)) return;
  impressed.add(key);
  enqueue(requestId, { event: "impression", job_id: jobId, rank });
  if (queue.length >= FLUSH_AT) flush(); else schedule();
}

/**
 * An action. Sent immediately, per the contract's "batch impressions; send
 * actions immediately", and behind anything already queued.
 *
 * Resolves to the server's {recorded, deduped, skipped, derived_skips} for the
 * last batch posted, or null if there was nothing to send. It does NOT reject:
 * a refused batch is reported through setErrorHandler, because the caller is a
 * view that has already updated optimistically and has an undo to offer.
 */
export function sendAction(requestId, event) {
  enqueue(requestId, event);
  return flush();
}

/**
 * Post everything queued, one request per render id, oldest first.
 *
 * A 4xx with a contract `code` is NOT retried. The batch is malformed and
 * re-sending it verbatim would fail identically forever, which is how a client
 * ends up in a loop writing nothing and reporting nothing. A network failure
 * or a 5xx puts the events back, because the endpoint never answering is a
 * deferral rather than a rejection -- the same distinction .claude/CLAUDE.md
 * draws for the scoring stage.
 */
export function flush() {
  chain = chain.then(drain, drain);
  return chain;
}

async function drain() {
  if (queue.length === 0) return null;
  const byRender = groupByRender(queue.splice(0, queue.length));
  let last = null;
  for (const [requestId, events] of byRender) {
    try {
      last = await postEvents(requestId, events);
    } catch (e) {
      if (e instanceof ApiError && e.status >= 400 && e.status < 500) {
        console.error(`event batch refused (${e.code || e.status}): ${e.message}`,
                      events);
        onError(e);
      } else {
        for (const event of events) queue.push({ requestId, event });
        console.warn("event batch deferred, will retry", e);
        schedule();
      }
    }
  }
  return last;
}

/**
 * Last-ditch flush when the page is going away. keepalive rather than
 * navigator.sendBeacon: a beacon with a string body is sent as text/plain,
 * which FastAPI answers with a 422 rather than reading as JSON.
 *
 * GOES THROUGH api.postEvents LIKE EVERY OTHER CALLER. It used to re-spell the
 * POST inline, which meant this path -- the one nobody watches -- quietly had
 * its own copy of credentials, no BASE and no Accept header.
 *
 * The catch is still swallowing, and now deliberately rather than by accident:
 * `postEvents` returns a promise, so the old synchronous try/catch could never
 * have seen an HTTP error or a rejection anyway. `.catch()` is where a refused
 * unload batch actually arrives. There is nothing to do with it -- the queue
 * is already spliced and the page is going -- but a console line means the
 * loss is observable in a devtools session rather than invisible.
 */
function flushOnUnload() {
  if (queue.length === 0) return;
  for (const [requestId, events] of groupByRender(queue.splice(0, queue.length))) {
    postEvents(requestId, events, { keepalive: true }).catch((e) => {
      console.warn("unload event batch lost", e, events);
    });
  }
}

addEventListener("pagehide", flushOnUnload);
addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden") flushOnUnload();
});

// -- visibility ------------------------------------------------------------

let observer = null;
/** element -> {requestId, jobId, rank, timer}. A Map, not a WeakMap, so that
 *  stopObserving() can cancel every pending dwell timer -- a timer surviving a
 *  view teardown would report an impression for a list the Builder has left. */
let watched = new Map();

function ensureObserver() {
  if (observer) return observer;
  const io = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      const row = watched.get(entry.target);
      if (!row) continue;
      if (entry.isIntersecting) {
        if (row.timer === null) {
          row.timer = setTimeout(() => {
            row.timer = null;
            impression(row.requestId, row.jobId, row.rank);
            io.unobserve(entry.target);
            watched.delete(entry.target);
          }, IMPRESSION_DWELL_MS);
        }
      } else if (row.timer !== null) {
        clearTimeout(row.timer);
        row.timer = null;
      }
    }
  }, { threshold: IMPRESSION_RATIO });
  observer = io;
  return io;
}

/** Watch one rendered card. Fires exactly one impression, then stops watching. */
export function observe(element, requestId, jobId, rank) {
  watched.set(element, { requestId, jobId, rank, timer: null });
  ensureObserver().observe(element);
}

/** Drop every pending observation and its dwell timer. Called on view teardown. */
export function stopObserving() {
  for (const row of watched.values()) {
    if (row.timer !== null) clearTimeout(row.timer);
  }
  watched = new Map();
  if (observer) observer.disconnect();
  observer = null;
}

/** Diagnostic hook: what is waiting to go out. Used by the console and by
 *  anyone checking the round trip by hand (frontend/README.md § Running it). */
export function pending() {
  return queue.map(({ requestId, event }) => ({ requestId, ...event }));
}
