// The HTTP edge. Everything that knows what the server actually sends lives
// here; the rest of the client sees parsed objects and one error type.
//
// THE TWO THINGS THIS FILE EXISTS FOR are both in frontend/README.md
// § "Things a client author will get wrong if nobody says them":
//
//   1. FOUR FIELDS ARRIVE AS JSON STRINGS, NOT ARRAYS. match_reasons,
//      tech_stack, risk_factors and key_technologies are TEXT columns holding
//      json.dumps(...) output and backend/webapp/jobs.py parses none of them
//      (LIST_COLUMNS, jobs.py:102-111 -- the handler does dict(zip(names, row))
//      at jobs.py:417 and returns it). Every one is JSON.parse'd on the way in,
//      once, here, so no view ever sees the string form.
//
//   2. THERE ARE TWO ERROR SHAPES, NOT ONE. app.py:93 registers the contract's
//      {"error": {code, message, request_id}} envelope for jobs.ContractError
//      ALONE. A 401 (auth.py:92), a 403 (auth.py:117), a 404 (jobs.py:468) and
//      a malformed cursor (jobs.py:235) are bare HTTPExceptions and come back
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
 * POST /v1/events. One request_id per batch, which is why events.js groups.
 *
 * EVERY VALIDATION FAILURE FAILS THE WHOLE BATCH (jobs.py:503-512), so a
 * caller must not mix a speculative event into a batch of real ones.
 */
export function postEvents(requestId, events) {
  return request("/v1/events", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ request_id: requestId, events }),
  });
}
