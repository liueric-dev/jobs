// Run the client's own modules against the frozen fixtures.
//
//     node frontend/check_client.mjs        # exit 0 if the client agrees with
//                                           # the fixtures and with the source
//
// WHY THIS EXISTS. API-CONTRACT-v1.md § Mocking asks for frozen responses that
// "become contract tests both sides run" once the backend lands.
// `verify_fixtures.py` is the server half -- it re-derives every shape claim in
// fixtures/shipped/ from backend/webapp/*.py. This is the client half: it feeds
// those same fixtures to the code that will parse them in a browser, and it
// re-derives three vocabularies from the Python that owns them. Between them,
// the fixture directory is checked from both ends rather than from neither.
//
// WHAT IT COVERS THAT verify_fixtures.py CANNOT. Shape is not behaviour. The
// four JSON-string columns are correctly shaped strings in the fixture and are
// still a client bug if nobody parses them; a track vocabulary can be correct
// in Python and absent from the client's copy; `apply` is a perfectly
// well-shaped string that is a 400.
//
// IT IS PLAIN NODE, NO TEST FRAMEWORK, NO package.json. The client modules are
// .mjs so node reads them as ES modules with no manifest at all -- which is
// also why the browser can load them unchanged: what a browser reads is the
// text/javascript MIME type, which is what .mjs already resolves to.
//
// IT IS WIRED IN. backend/tests/test_frontend_fixtures.py runs it and skips
// when node is absent, on the same principle as the scratch-database modules:
// a checker nobody runs is a suggestion, and a skip is not a failure.

import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.dirname(HERE);
const SHIPPED = path.join(HERE, "fixtures", "shipped");

// -- a DOM small enough to import against -----------------------------------
// events.mjs registers pagehide/visibilitychange listeners at module scope and
// ui.mjs reaches for document inside its functions. Nothing here pretends to
// be a browser; it is the minimum that lets the pure logic be imported.

const listeners = [];
globalThis.addEventListener = (type, fn) => listeners.push([type, fn]);
globalThis.removeEventListener = () => {};
globalThis.document = { visibilityState: "visible", getElementById: () => null };
globalThis.CSS = { escape: (s) => s };

/** Every request the client makes, in order. Set per-case. */
let sent = [];
globalThis.fetch = async (url, options = {}) => {
  sent.push({ url, ...options, parsed: options.body ? JSON.parse(options.body) : null });
  return {
    ok: true,
    status: 200,
    json: async () => ({ recorded: 0, deduped: 0, skipped: 0, derived_skips: 0 }),
  };
};

const { parseJobRow, ApiError } = await import("./js/api.mjs");
const tracks = await import("./js/tracks.mjs");
const format = await import("./js/format.mjs");
const ui = await import("./js/ui.mjs");
const events = await import("./js/events.mjs");
const detailView = await import("./js/detail.mjs");

// -- helpers ----------------------------------------------------------------

const fixture = (name) =>
  JSON.parse(fs.readFileSync(path.join(SHIPPED, name), "utf8"));

/** Every module-level NAME = ("a", "b", ...) tuple-of-strings in a .py file.
 *  The same trick verify_fixtures.py plays with `ast`, done with a regex
 *  because there is no Python here -- and deliberately narrow: it resolves one
 *  form and nothing more general, so a tuple written another way fails loudly
 *  as a missing name rather than silently as an empty list. */
function pyTuple(relPath, name) {
  const source = fs.readFileSync(path.join(REPO, relPath), "utf8");
  const match = source.match(new RegExp(`^${name} = \\(([\\s\\S]*?)\\)`, "m"));
  assert.ok(match, `${name} is no longer a module-level tuple in ${relPath}`);
  return [...match[1].matchAll(/"([^"]*)"/g)].map((m) => m[1]);
}

const cases = [];
const it = (name, fn) => cases.push([name, fn]);

/**
 * Render the detail page for one job object and return its HTML.
 *
 * paint() is module-private, so this drives the real show() with a stubbed
 * root and a fetch that answers the detail call with `job` and the list call
 * (renders.resolve's cold-start crawl) with an empty render. Going through
 * show() rather than exporting paint() means the assertions run against the
 * code path the browser actually takes.
 */
async function renderDetail(job) {
  const before = globalThis.fetch;
  let html = "";
  globalThis.fetch = async (url) => ({
    ok: true,
    status: 200,
    json: async () => (String(url).includes(`/v1/jobs/`)
      ? job
      : { request_id: "req_stub", jobs: [], next_cursor: null, profile: "pursuit" }),
  });
  const root = {
    set innerHTML(v) { html = v; }, get innerHTML() { return html; },
    addEventListener() {}, removeEventListener() {}, querySelector: () => null,
  };
  try {
    const teardown = await detailView.show(root, job.id);
    teardown();
    return html;
  } finally {
    globalThis.fetch = before;
  }
}

// -- the four JSON-string columns -------------------------------------------

it("the four TEXT columns are parsed out of their JSON strings", () => {
  const row = fixture("GET_v1_jobs.json").jobs[0];
  for (const field of ["match_reasons", "tech_stack", "risk_factors",
                       "key_technologies"]) {
    assert.equal(typeof row[field], "string",
                 `${field} is no longer a string in the fixture`);
  }
  const parsed = parseJobRow({ ...row });
  assert.ok(Array.isArray(parsed.match_reasons));
  assert.ok(Array.isArray(parsed.tech_stack));
  assert.ok(Array.isArray(parsed.risk_factors));
  assert.ok(Array.isArray(parsed.key_technologies));
  assert.deepEqual(parsed.match_reasons[0], { rule: "base", delta: 50 });
});

it("an unscored posting parses to nulls rather than throwing", () => {
  // Rent the Runway: jobs_app LEFT JOINs job_scores, so five fields are null
  // together on a posting the nightly run has not reached.
  const row = fixture("GET_v1_jobs.json").jobs[3];
  assert.equal(row.fit_score, null);
  const parsed = parseJobRow({ ...row });
  assert.equal(parsed.risk_factors, null);
  assert.equal(parsed.key_technologies, null);
  assert.ok(Array.isArray(parsed.match_reasons));   // matching is free; scoring is not
});

it("a malformed JSON column becomes null, not an exception", () => {
  const parsed = parseJobRow({ id: "x", risk_factors: "[not json" });
  assert.equal(parsed.risk_factors, null);
});

// -- both error shapes -------------------------------------------------------

it("the contract envelope and FastAPI's detail both become an ApiError", () => {
  // Rebuilt through the same branch readError() takes, without a live socket.
  const enveloped = fixture("errors/400_unknown_event.json");
  const bare = fixture("errors/NOT-ENVELOPED-404_no_such_job.json");
  assert.equal(enveloped.error.code, "unknown_event");
  assert.equal(typeof bare.detail, "string");
  assert.ok(!("code" in bare), "a NOT-ENVELOPED- fixture must carry no code");

  const withCode = new ApiError(400, enveloped.error.code,
                                enveloped.error.message,
                                enveloped.error.request_id);
  const without = new ApiError(404, null, bare.detail, null);
  assert.equal(withCode.code, "unknown_event");
  assert.equal(without.code, null,
               "a {detail: ...} response has no code and must not be given one");
  assert.ok(without.isMissing);
});

it("every enveloped error fixture carries all three envelope keys", () => {
  for (const name of fs.readdirSync(path.join(SHIPPED, "errors"))) {
    const body = fixture(path.join("errors", name));
    if (name.startsWith("NOT-ENVELOPED-")) {
      assert.deepEqual(Object.keys(body), ["detail"], name);
    } else {
      assert.deepEqual(Object.keys(body.error),
                       ["code", "message", "request_id"], name);
    }
  }
});

// -- the track axis ----------------------------------------------------------

it("the client's ROLE_TRACK is backend/extract.py's, verbatim", () => {
  assert.deepEqual(tracks.ROLE_TRACK, pyTuple("backend/extract.py", "ROLE_TRACK"),
                   "DEC-77 groups by extract.ROLE_TRACK; the two have drifted");
});

it("every track in the vocabulary has plain-language copy", () => {
  // A blurb is the part that cannot be produced by humanising a slug, so it is
  // what actually proves somebody wrote copy for this track. A label that
  // happens to equal the humanised slug is fine -- "Technical support" is what
  // a person would say -- but a missing blurb means a track was added to
  // ROLE_TRACK and never given words.
  for (const track of [...tracks.ROLE_TRACK, tracks.UNTRACKED]) {
    const { label, blurb } = tracks.labelFor(track);
    assert.ok(label, `${track} has no label`);
    assert.ok(blurb, `${track} has no blurb; it was added without copy`);
    assert.ok(!label.includes("_"), `${track}'s label is still a slug`);
  }
});

it("the shipped payload carries no role_track, so every row is UNTRACKED", () => {
  // THE FINDING THIS PINS. `role_track` is on jobs (backend/schema.py:542) and
  // is NOT in the jobs_app view, so it is in no response body. If this ever
  // starts failing, the field has landed and grouping begins working on its
  // own -- which is the point of writing it this way round.
  const body = fixture("GET_v1_jobs.json");
  for (const job of body.jobs) {
    assert.ok(!("role_track" in job), `${job.id} now has role_track; update README`);
    assert.equal(tracks.trackOf(job), tracks.UNTRACKED);
  }
  const groups = tracks.groupByTrack(body.jobs.map((j) => ({ ...j })));
  assert.equal(groups.length, 1);
  assert.equal(groups[0].track, tracks.UNTRACKED);
  assert.deepEqual(groups[0].jobs.map((j) => j.rank), [1, 2, 3, 4],
                   "grouping must not reorder rows");
});

it("grouping keys off role_track the moment it appears", () => {
  const rows = [
    { id: "a", rank: 1, role_track: "data_and_analytics" },
    { id: "b", rank: 2, role_track: null },
    { id: "c", rank: 3, role_track: "data_and_analytics" },
    { id: "d", rank: 4, role_track: "software_engineering" },
    { id: "e", rank: 5, role_track: "a_track_that_does_not_exist" },
  ];
  const groups = tracks.groupByTrack(rows);
  assert.deepEqual(groups.map((g) => g.track),
                   ["data_and_analytics", tracks.UNTRACKED, "software_engineering"],
                   "groups order by their best rank, and by nothing else");
  assert.deepEqual(groups[0].jobs.map((j) => j.id), ["a", "c"]);
  // A null track and a track outside the closed vocabulary land in the same
  // place. Neither is dropped -- schema.py:534 says role_track is NULL on
  // every pre-task-11 row, which is most of the table.
  assert.deepEqual(groups[1].jobs.map((j) => j.id), ["b", "e"]);
});

it("the caveat under every heading is present and says what it must", () => {
  assert.match(tracks.CAVEAT, /different group/,
               "the heading must not read as a fact about a posting: "
               + "11.3% of postings change whether they belong to ANY track "
               + "between runs (docs/ingestion_tests/selfcheck-n120-2026-08-02.md)");
});

// -- cohort_signal -------------------------------------------------------------

it("cohort_signal sits between dismiss_reason and rank, and last on detail", () => {
  // The position is load-bearing: jobs.py pops the raw save_bucket and
  // re-assigns the nested value, which APPENDS -- so on a list row it lands
  // ahead of rank, and on a detail row it lands last.
  for (const job of fixture("GET_v1_jobs.json").jobs) {
    const keys = Object.keys(job);
    assert.equal(keys[keys.indexOf("cohort_signal") - 1], "dismiss_reason");
    assert.equal(keys[keys.indexOf("cohort_signal") + 1], "rank");
  }
  const detail = Object.keys(fixture("GET_v1_jobs_by_id.json"));
  assert.equal(detail[detail.length - 1], "cohort_signal");
});

it("one posting cannot have two answers", () => {
  // Mount Sinai is in both the list and the detail fixture. A badge is a fact
  // about a posting, not about which endpoint you asked.
  const listed = fixture("GET_v1_jobs.json").jobs[0];
  const detail = fixture("GET_v1_jobs_by_id.json");
  assert.equal(listed.id, detail.id);
  assert.deepEqual(listed.cohort_signal, detail.cohort_signal);
  assert.deepEqual(listed.cohort_signal, { save_bucket: "3-5" });
});

it("a null cohort_signal renders NOTHING -- never a zero, never a count", async () => {
  // THE FAILURE THIS PREVENTS. null is a privacy suppression, not "no data":
  // the count is withheld below three Builders, so null covers both "nobody
  // saved this" and "one or two did" (jobs.py:370). Rendering "0 saves", a
  // greyed zero, or any "fewer than three" copy would make absence readable as
  // *exactly* one or two, in a thirty-person cohort who see each other in a
  // classroom. At today's size EVERY value is null, so this is the main path.
  for (const raw of fixture("GET_v1_jobs.json").jobs) {
    const html = ui.jobCard(parseJobRow({ ...raw }));
    assert.ok(!/cohort|Builders saved/i.test(html),
              "the card renders a cohort badge; the surfaces table puts it on detail only");
  }
  const nulled = { ...fixture("GET_v1_jobs_by_id.json"), cohort_signal: null };
  const rendered = await renderDetail(nulled);
  assert.ok(!/Builders saved|saved this posting|no one|nobody|fewer than/i.test(rendered),
            "a suppressed count leaked into the detail page");
});

it("a populated cohort_signal renders the bucket, and says Builders not others", async () => {
  const html = await renderDetail(fixture("GET_v1_jobs_by_id.json"));
  assert.match(html, /<strong>3-5 Builders<\/strong> saved this posting/,
               "the bucket string is rendered as the bucket string");
  // "other Builders" would be wrong by one whenever the reader is one of them:
  // the fold counts every distinct app_user_id in the profile, this one
  // included (backend/cohort.py:113).
  assert.ok(!/other Builders/.test(html),
            "the count includes the reader, so 'other' overstates it");
  assert.ok(!/\bexactly\b|\bago\b|computed/.test(html),
            "never an exact count, never a recency, never an identity");
});

// -- rank ---------------------------------------------------------------------

it("rank is 1..N across the two pages of one render", () => {
  const p1 = fixture("GET_v1_jobs.json");
  const p2 = fixture("GET_v1_jobs.page2.json");
  assert.equal(p1.request_id, p2.request_id, "a render spans pages");
  const ranks = [...p1.jobs, ...p2.jobs].map((j) => j.rank);
  assert.deepEqual(ranks, [1, 2, 3, 4, 5],
                   "page two starts at 5, not 1 -- the rank rides in the cursor");
});

it("the detail response has no rank, so a detail page cannot invent one", () => {
  assert.ok(!("rank" in fixture("GET_v1_jobs_by_id.json")),
            "rank is a property of a render and a detail request is not one");
});

// -- no 0-100 score anywhere ---------------------------------------------------

it("the reason chips carry no digits, because the deltas are the score", () => {
  for (const raw of fixture("GET_v1_jobs.json").jobs) {
    const job = parseJobRow({ ...raw });
    for (const chip of format.reasonsFor(job)) {
      assert.ok(!/\d/.test(chip),
                `"${chip}" carries a number; match_reasons deltas sum to match_score`);
    }
    assert.ok(!format.reasonsFor(job).some((c) => /^Base/i.test(c)),
              "'base' is not a reason a person would give");
  }
});

it("a rendered card names no score field and shows no negative rule", () => {
  for (const raw of fixture("GET_v1_jobs.json").jobs) {
    const html = ui.jobCard(parseJobRow({ ...raw }));
    for (const forbidden of ["match_score", "fit_score", "primary_track"]) {
      assert.ok(!html.includes(forbidden), `card names ${forbidden}`);
    }
    // ai:none and years:missing are the negatives in these fixtures. A card is
    // not the place to argue with the ranker; risk_factors on the detail page
    // are the honest negatives and are written for a person.
    assert.ok(!html.includes("Ai none") && !html.includes("Years missing"),
              "a negative rule reached the card");
  }
});

it("third-party strings are escaped on the way into the card", () => {
  const html = ui.jobCard(parseJobRow({
    id: "x", rank: 1, title: '<img src=x onerror="alert(1)">',
    company_name: "A & B", summary: null, match_reasons: null,
  }));
  assert.ok(!html.includes("<img"), "a job title reached innerHTML unescaped");
  assert.ok(html.includes("A &amp; B"));
});

// -- compensation and age ------------------------------------------------------

it("comp is rendered from the band, and absent when the posting states none", () => {
  const [sinai, oscar] = fixture("GET_v1_jobs.json").jobs;
  assert.deepEqual(format.compLabel(sinai), {
    text: "$62,000 – $78,000", estimated: false,
  });
  assert.equal(format.compLabel(oscar), null, "Oscar Health states no pay");
});

it("is_estimated is honoured under either name when it is present", () => {
  const job = { comp_min: 50000, comp_max: 60000, comp_currency: "USD",
                comp_is_estimated: true };
  assert.equal(format.compLabel(job).estimated, true);
  assert.equal(format.compLabel({ ...job, comp_is_estimated: undefined,
                                  is_estimated: true }).estimated, true);
  // And absent means absent. NOTHING in backend/schema.py sets either name --
  // see format.mjs. This asserts the client is ready, not that the API is.
  assert.equal(format.compLabel({ ...job, comp_is_estimated: undefined }).estimated,
               false);
});

it("a posting with no posted_at_ts is labelled 'first seen', never 'posted'", () => {
  const coned = fixture("GET_v1_jobs.json").jobs[2];
  assert.equal(coned.posted_at_ts, null);
  const now = new Date("2026-08-02T00:00:00Z");
  assert.match(format.ageLabel(coned, now).text, /^First seen/,
               "first_seen is when this pipeline saw it, not the employer's claim");
  const sinai = fixture("GET_v1_jobs.json").jobs[0];
  assert.match(format.ageLabel(sinai, now).text, /^Posted/);
});

// -- the dismiss vocabulary ----------------------------------------------------

it("the client's dismiss reasons are schema_web.DISMISS_REASONS, in order", () => {
  assert.deepEqual(format.DISMISS_REASONS.map(([slug]) => slug),
                   pyTuple("backend/webapp/schema_web.py", "DISMISS_REASONS"));
  for (const [slug, text] of format.DISMISS_REASONS) {
    assert.ok(text && text !== slug, `${slug} has no plain-language wording`);
  }
});

// -- the event vocabulary ------------------------------------------------------

it("every event name the client can emit is one jobs.py accepts", () => {
  const allowed = new Set(pyTuple("backend/webapp/jobs.py", "CLIENT_EVENT_NAMES"));
  const server = new Set(pyTuple("backend/webapp/jobs.py", "SERVER_EVENT_NAMES"));
  const emitted = new Set();
  for (const file of fs.readdirSync(path.join(HERE, "js"))) {
    const source = fs.readFileSync(path.join(HERE, "js", file), "utf8");
    for (const m of source.matchAll(/event:\s*"([a-z_]+)"/g)) emitted.add(m[1]);
    for (const m of source.matchAll(/event:\s*\w+ \? "([a-z_]+)" : "([a-z_]+)"/g)) {
      emitted.add(m[1]); emitted.add(m[2]);
    }
  }
  assert.ok(emitted.size >= 6, `only found ${emitted.size} event names in js/`);
  for (const name of emitted) {
    assert.ok(allowed.has(name), `client emits '${name}', which jobs.py rejects`);
    assert.ok(!server.has(name),
              `client emits '${name}', which the server derives (400 server_derived_event)`);
  }
  assert.ok(emitted.has("applied") && !emitted.has("apply"),
            "DEC-73: the event for an application is 'applied'; 'apply' is a 400");
});

// -- the event queue -----------------------------------------------------------

it("impressions batch, dedupe, and go out under their own render id", async () => {
  sent = [];
  events.impression("req_A", "job1", 1);
  events.impression("req_A", "job1", 1);       // same render, same row: once
  events.impression("req_A", "job2", 2);
  events.impression("req_B", "job1", 7);       // a different render: separately
  await events.flush();

  assert.equal(sent.length, 2, "one request per render id, never a merged batch");
  const [a, b] = sent;
  assert.equal(a.parsed.request_id, "req_A");
  assert.deepEqual(a.parsed.events, [
    { event: "impression", job_id: "job1", rank: 1 },
    { event: "impression", job_id: "job2", rank: 2 },
  ]);
  assert.equal(b.parsed.request_id, "req_B");
  assert.equal(b.parsed.events[0].rank, 7);
});

it("an action carries no null fields, and undismiss carries no reason", async () => {
  sent = [];
  await events.sendAction("req_C", { event: "dismiss", job_id: "j", rank: 3,
                                     reason: "wrong_level" });
  await events.sendAction("req_C", { event: "undismiss", job_id: "j" });
  await events.sendAction("req_C", { event: "applied", job_id: "j",
                                     rank: undefined });
  const bodies = sent.map((s) => s.parsed.events[0]);
  assert.deepEqual(bodies[0], { event: "dismiss", job_id: "j", rank: 3,
                                reason: "wrong_level" });
  assert.deepEqual(bodies[1], { event: "undismiss", job_id: "j" },
                   "a reason on undismiss is a 400 with code reason_not_allowed");
  assert.deepEqual(bodies[2], { event: "applied", job_id: "j" },
                   "an applied raised from a detail page has no position");
});

it("a skipped reason sends a dismiss with no reason at all", async () => {
  sent = [];
  await events.sendAction("req_D", { event: "dismiss", job_id: "j", rank: 1,
                                     reason: undefined });
  assert.deepEqual(sent[0].parsed.events[0],
                   { event: "dismiss", job_id: "j", rank: 1 },
                   "skipping the question must not substitute 'other'");
});

it("an event with no request_id is dropped rather than guessed at", async () => {
  sent = [];
  await events.sendAction(null, { event: "save", job_id: "j" });
  assert.equal(sent.length, 0);
});

// -- run -----------------------------------------------------------------------

let failed = 0;
for (const [name, fn] of cases) {
  try {
    await fn();
    console.log(`  ok   ${name}`);
  } catch (e) {
    failed++;
    console.log(`  FAIL ${name}\n       ${e.message.split("\n").join("\n       ")}`);
  }
}
console.log(`\n${cases.length} checks, ${failed} failed`);
process.exit(failed ? 1 : 0);
