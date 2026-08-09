// The HTTP edge. Everything that knows what the server actually sends lives
// here; the rest of the client sees parsed objects and one error type.
//
// THE TWO THINGS THIS FILE EXISTS FOR are both in frontend/README.md
// § "Things a client author will get wrong if nobody says them":
//
//   1. FOUR FIELDS ARRIVE AS JSON STRINGS, NOT ARRAYS. match_reasons,
//      tech_stack, risk_factors and key_technologies are TEXT columns holding
//      json.dumps(...) output and backend/webapp/jobs.py parses none of them
//      (LIST_COLUMNS, jobs.py:119-128 -- the handler does dict(zip(names, r))
//      at jobs.py:552 and returns it). Every one is JSON.parse'd on the way in,
//      once, here, so no view ever sees the string form.
//
//   2. THERE ARE TWO ERROR SHAPES, NOT ONE. app.py:101 registers the contract's
//      {"error": {code, message, request_id}} envelope for jobs.ContractError
//      ALONE. A 401 (auth.py:92), a 403 (auth.py:117), a 404 (jobs.py:619) and
//      a malformed cursor (jobs.py:252) are bare HTTPExceptions and come back
//      as FastAPI's {"detail": "..."}. Both are normalised into ApiError below.
//
// SAME ORIGIN, SO NO CORS. backend/webapp/.env sets FRONTEND_ORIGIN and
// ALLOWED_ORIGINS to http://localhost:8421 and this page is served from there
// (frontend/serve.py). credentials: "same-origin" is still stated explicitly
// rather than left to the default, because the session cookie is the only
// credential this client has and a silent drop is indistinguishable from a
// logged-out user.

export const BASE = "";

/** The four TEXT columns holding JSON. See the note above. */
export const JSON_STRING_FIELDS = [
  "match_reasons", "tech_stack", "risk_factors", "key_technologies",
];

export class ApiError extends Error {
  constructor(status, code, message, requestId) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    /** snake_case machine code from the envelope, or null when the response
     *  used FastAPI's {"detail": ...} shape, which carries no code at all. */
    this.code = code;
    this.requestId = requestId ?? null;
  }

  get isAuth() { return this.status === 401; }
  get isForbidden() { return this.status === 403; }
  get isMissing() { return this.status === 404; }
}

async function readError(response) {
  let body = null;
  try {
    body = await response.json();
  } catch {
    // A proxy or a 502 can return HTML. Nothing below should throw on it.
  }
  if (body && typeof body === "object" && body.error && typeof body.error === "object") {
    // The contract envelope. jobs.ContractError only.
    return new ApiError(response.status, body.error.code ?? null,
                        body.error.message ?? "Request failed",
                        body.error.request_id ?? null);
  }
  if (body && typeof body === "object" && typeof body.detail === "string") {
    // FastAPI's default. No code, and there is no way to synthesise one --
    // guessing here is how a client ends up branching on a message string.
    return new ApiError(response.status, null, body.detail, null);
  }
  return new ApiError(response.status, null,
                      `HTTP ${response.status}`, null);
}

async function request(path, options = {}) {
  const response = await fetch(BASE + path, {
    credentials: "same-origin",
    ...options,
    headers: { Accept: "application/json", ...(options.headers || {}) },
  });
  if (!response.ok) throw await readError(response);
  if (response.status === 204) return null;
  return response.json();
}

/** Parse the four JSON-string columns in place and return the row.
 *
 *  A malformed value becomes null rather than throwing: one unparseable
 *  risk_factors must not blank the whole list. It is logged, because silence
 *  is this system's documented failure mode and a client should not add to it.
 */
export function parseJobRow(job) {
  for (const field of JSON_STRING_FIELDS) {
    const raw = job[field];
    if (raw === null || raw === undefined) {
      job[field] = null;
      continue;
    }
    if (typeof raw !== "string") continue;   // already an array: leave it
    try {
      job[field] = JSON.parse(raw);
    } catch (e) {
      console.warn(`job ${job.id}: ${field} is not JSON`, raw, e);
      job[field] = null;
    }
  }
  return job;
}

// -- endpoints -------------------------------------------------------------

export function me() {
  return request("/v1/me");
}

export function logout() {
  return request("/v1/auth/logout", { method: "POST" });
}

/** Where to send the browser to sign in. Server-driven OAuth: the client never
 *  touches a Google SDK and never sees a token (backend/webapp/auth.py). */
export function loginUrl(nextPath = "/") {
  return `/v1/auth/login?next=${encodeURIComponent(nextPath)}`;
}

/**
 * GET /v1/jobs. One page of one render.
 *
 * A call WITHOUT a cursor starts a render and mints a request_id; a call WITH
 * one continues the render the cursor names, and `rank` resumes rather than
 * restarting at 1 (jobs.py:370-374, encode_cursor at :193-215). Both facts are
 * the caller's problem, which is why this returns the whole envelope.
 */
export async function listJobs({ limit = 25, cursor = null } = {}) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (cursor) params.set("cursor", cursor);
  const body = await request(`/v1/jobs?${params}`);
  body.jobs.forEach(parseJobRow);
  return body;
}

/** GET /v1/jobs/{id}. Deliberately still serves a posting this Builder has
 *  dismissed (jobs.py:440-448) -- the undo has to be reachable. */
export async function getJob(jobId) {
  return parseJobRow(await request(`/v1/jobs/${encodeURIComponent(jobId)}`));
}

/**
 * GET /v1/onboarding. Has this Builder onboarded?
 *
 * Returns {onboarding: {completed, completed_at, prior_domain, prior_years},
 * profile} -- backend/webapp/onboarding.py:517-531, and the block itself is
 * _state() at :502-514.
 *
 * IT IS THIS ROUTE AND NOT AN `onboarding` BLOCK ON GET /v1/me. The contract
 * invents one on /v1/me (fixtures/contract/ASPIRATIONAL_GET_v1_me.json) and
 * onboarding.py:519-528 says in terms why it did not build it there: /v1/me is
 * auth.py's and "deliberately touches no jobs table", which is worth more than
 * saving a request. The two must never both exist with different shapes, so
 * this client calls exactly one of them and it is this one.
 *
 * `completed_at` CARRIES NO ZONE. onboarded_at is TEXT (schema_web.py:553)
 * written by lib.timeparse.utc_now_str(), whose docstring says the
 * '%Y-%m-%dT%H:%M:%S' shape is load-bearing and "must not gain an offset".
 * Same trap as `first_seen` -- see format.mjs, which appends the Z.
 */
export function getOnboarding() {
  return request("/v1/onboarding");
}

/**
 * POST /v1/onboarding. The structured form and the seed judgements, together.
 *
 * ONE REQUEST, NOT TWO, and that is the endpoint's shape rather than a client
 * convenience: onboarding.py:591-594 writes the profile row and commits it
 * BEFORE recording the judgements, deliberately, so that the survivable half-
 * failure is "onboarded with no judgements" rather than "judgements belonging
 * to a Builder with no profile row". Splitting this into two calls client-side
 * would put that ordering back in the client's hands.
 *
 * THE BODY CARRIES NO `profile` AND NO `tracks`, EVER. The cohort comes from
 * the session (onboarding.py:279-283) and tracks are derived from the
 * judgements rather than picked from a checkbox (:284-287, derive_tracks at
 * :372-407). Sending either is not a 400 -- pydantic ignores unknown fields --
 * it is silently discarded, which is why check_client.mjs re-derives
 * OnboardingRequest's field names out of Python rather than trusting this file.
 */
export function postOnboarding(body) {
  return request("/v1/onboarding", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

// -- searches (task 25's six routes) ---------------------------------------
//
// SIX THIN WRAPPERS AND NOT ONE LINE OF PARSING, and that is the whole point.
// backend/webapp/search.py IMPORTS LIST_COLUMNS, STATE_FIELDS, COHORT_FIELDS,
// the three joins and the cursor codec from jobs.py rather than restating
// them, so /v1/searches/{id}/results returns /v1/jobs' shape field for field --
// same keys, same order, its own request_id and its own 1-based rank. So
// searchResults() below is listJobs() with a different path, parseJobRow does
// the same four JSON columns, and ui.jobCard renders the rows unchanged. If
// this file ever needs a second row parser, the two endpoints have drifted and
// that is the bug.
//
// A QUERY OBJECT IS NOT A JOB OBJECT AND SHARES NOTHING WITH ONE. Its twelve
// keys are RESPONSE_NAMES + _SIGNAL_FIELDS (search.py) and only `chips` is
// JSON -- which the SERVER parses (search.py's _row_to_query), unlike the four
// job columns it does not. So no query route goes through parseJobRow.
//
// `role_track` MEANS TWO DIFFERENT THINGS ACROSS THESE TWO SHAPES. On a job row
// it is job_facts.role_track, the posting's family. On a query object it is
// search_queries.role_track, the track this SUGGESTION was seeded from --
// "why does this search exist", not "what kind of job is this". They never
// share a JSON object, and search.mjs keeps the two readings apart in its copy.

/**
 * POST /v1/searches. Register a search and become a watcher of it.
 *
 * ASYNCHRONOUS, AND THE RESPONSE SAYS SO RATHER THAN PRETENDING. No provider
 * is called on this request (search.py, create_search): the query is
 * registered and results appear when the nightly cycle runs it. So the object
 * that comes back has `last_run_at: null` and `run_count: 0`, and a client that
 * renders it as a result list would be showing an empty list as if it were an
 * answer.
 *
 * IDEMPOTENT ON THE NORMALISED KEY, so submitting a search someone else
 * already created returns THEIR row -- same id, their `display_text` spelling,
 * and whatever run history it already has. That is the cache working
 * (searchnorm.REGISTER_QUERY_SQL, first-writer-wins on the spelling), not a
 * bug, and the copy on the screen has to survive it.
 */
export function createSearch({ text, location = null, chips = null } = {}) {
  return request("/v1/searches", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, location, chips }),
  });
}

/**
 * GET /v1/searches?scope=… Returns {searches, scope}.
 *
 * TWO SCOPES AND NO THIRD, AND THE ABSENCE IS A PRIVACY CONTROL RATHER THAN A
 * missing feature (search.py, list_searches): the TEXT of a builder-created
 * query is often self-identifying in a thirty-person cohort, so there is no
 * "everything anyone searched for" listing to browse. A client must not
 * simulate one by concatenating anything.
 */
export function listSearches({ scope = "mine", limit = 25 } = {}) {
  const params = new URLSearchParams({ scope, limit: String(limit) });
  return request(`/v1/searches?${params}`);
}

/** GET /v1/searches/{id}. A 404 for "not yours" and for "does not exist"
 *  alike -- the id space is a small integer sequence, so enumeration is
 *  trivial and the two must be indistinguishable (search.py, get_search). */
export function getSearch(queryId) {
  return request(`/v1/searches/${encodeURIComponent(queryId)}`);
}

/** POST /v1/searches/{id}/watch. Returns the query, re-read after the write. */
export function watchSearch(queryId) {
  return request(`/v1/searches/${encodeURIComponent(queryId)}/watch`,
                 { method: "POST" });
}

/** POST /v1/searches/{id}/unwatch.
 *
 *  A POST AND NOT A DELETE, AND IT IS NOT A STYLE CHOICE: app.py's CORS
 *  middleware allows GET, POST and OPTIONS only, so a DELETE from the browser
 *  would be refused at the preflight with no error anyone would see
 *  (search.py, unwatch_search). That is the silent-failure mode this repo
 *  alerts on, arriving through a verb. */
export function unwatchSearch(queryId) {
  return request(`/v1/searches/${encodeURIComponent(queryId)}/unwatch`,
                 { method: "POST" });
}

/**
 * GET /v1/searches/{id}/results. One page of one render, exactly like listJobs.
 *
 * THE JOIN IS THE GATE. The route reads `jobs_app JOIN search_query_results`,
 * never `jobs` and never the results table alone (search.py, search_results),
 * so a posting only appears if match.py wrote it a job_matches row. Google Jobs
 * is where the relister junk originates and config/relevance.json already
 * carries six excluded relist sites BECAUSE this source fed them in. Nothing on
 * the client re-filters, and nothing on the client may.
 */
export async function searchResults(queryId, { limit = 25, cursor = null } = {}) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (cursor) params.set("cursor", cursor);
  const body = await request(
    `/v1/searches/${encodeURIComponent(queryId)}/results?${params}`);
  body.jobs.forEach(parseJobRow);
  return body;
}

/**
 * POST /v1/events. One request_id per batch, which is why events.js groups.
 *
 * EVERY VALIDATION FAILURE FAILS THE WHOLE BATCH (jobs.py:503-512), so a
 * caller must not mix a speculative event into a batch of real ones.
 *
 * `keepalive` is for the unload path in events.mjs and is the ONLY thing that
 * differs there. It used to be a second hand-written fetch() with its own copy
 * of credentials, its own headers and no BASE -- which meant the endpoint was
 * spelled twice and the copy nobody watches was the one that skipped
 * `Accept: application/json` and would have broken silently the day BASE
 * stopped being "". One spelling, one option.
 */
export function postEvents(requestId, events, { keepalive = false } = {}) {
  return request("/v1/events", {
    method: "POST",
    keepalive,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ request_id: requestId, events }),
  });
}
