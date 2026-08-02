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
// re-derives nine names from the Python that owns them -- ROLE_TRACK, the six
// closed vocabularies, the event names, and OnboardingRequest's field list.
// Between them, the fixture directory is checked from both ends rather than
// from neither.
//
// WHAT IT COVERS THAT verify_fixtures.py CANNOT. Shape is not behaviour. The
// four JSON-string columns are correctly shaped strings in the fixture and are
// still a client bug if nobody parses them; a track vocabulary can be correct
// in Python and absent from the client's copy; `apply` is a perfectly
// well-shaped string that is a 400; and a form field misspelt by one letter is
// a 200 that stores nothing, because pydantic ignores keys it does not declare.
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
// search.mjs routes on the hash rather than on a second ROUTES row, so it needs
// one. Assigning to it is also how the client navigates after a submit.
globalThis.location = { hash: "" };

/** Every element handed to an IntersectionObserver, with the arguments
 *  events.observe() recorded against it. The impression path is 32's one
 *  non-negotiable requirement, so a screen claiming to be a render has to be
 *  shown wiring one up rather than merely rendering `data-rank` attributes. */
let observedCards = [];
globalThis.IntersectionObserver = class {
  constructor(callback, options) { this.callback = callback; this.options = options; }
  observe(element) { observedCards.push(element); }
  unobserve() {}
  disconnect() {}
};

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

const api = await import("./js/api.mjs");
const { parseJobRow, ApiError } = api;
const tracks = await import("./js/tracks.mjs");
const format = await import("./js/format.mjs");
const ui = await import("./js/ui.mjs");
const events = await import("./js/events.mjs");
const detailView = await import("./js/detail.mjs");
const onboardingView = await import("./js/onboarding.mjs");
const searchView = await import("./js/search.mjs");

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

/** Every module-level NAME = {"a": "b", ...} mapping of string literals.
 *  onboarding.VERDICT_EVENTS is a dict rather than a tuple because it IS a
 *  mapping -- verdict to event name -- and both halves are checked below. */
function pyDict(relPath, name) {
  const source = fs.readFileSync(path.join(REPO, relPath), "utf8");
  const match = source.match(new RegExp(`^${name} = \\{([\\s\\S]*?)\\}`, "m"));
  assert.ok(match, `${name} is no longer a module-level dict in ${relPath}`);
  return Object.fromEntries(
    [...match[1].matchAll(/"([^"]*)"\s*:\s*"([^"]*)"/g)].map((m) => [m[1], m[2]]));
}

/** A module-level NAME = <int>. */
function pyInt(relPath, name) {
  const source = fs.readFileSync(path.join(REPO, relPath), "utf8");
  const match = source.match(new RegExp(`^${name} = (-?\\d+)\\s*$`, "m"));
  assert.ok(match, `${name} is no longer a module-level int in ${relPath}`);
  return Number(match[1]);
}

/** The field names one pydantic model declares, in declaration order.
 *
 *  THE REASON THIS IS WORTH A PARSER. Pydantic ignores unknown fields, so a
 *  client sending a key OnboardingRequest does not declare gets a 200 and
 *  stores nothing -- the Builder answered a question that went nowhere and was
 *  told it worked. Neither a 400 nor a log line marks it. Deriving the field
 *  set here is the only place on the client side that can catch it. */
function pyModelFields(relPath, className) {
  const source = fs.readFileSync(path.join(REPO, relPath), "utf8");
  const match = source.match(
    new RegExp(`^class ${className}\\(BaseModel\\):([\\s\\S]*?)\\n\\n\\n`, "m"));
  assert.ok(match, `${className} is no longer a BaseModel in ${relPath}`);
  return [...match[1].matchAll(/^ {4}(\w+): /gm)].map((m) => m[1]);
}

/** One file's text, for the checks that are about source rather than about
 *  behaviour -- the routing table and the shell markup, neither of which can
 *  be imported here (app.mjs reaches for document at module scope and boots). */
function fileText(...parts) {
  return fs.readFileSync(path.join(HERE, ...parts), "utf8");
}

/** The same text with `//` and block comments removed.
 *
 *  WHY THIS EXISTS, since it is exactly the sort of helper that gets added for
 *  no reason: the file-upload check below scans source for `type="file"`, and
 *  the first thing it found was onboarding.mjs's own comment saying there is no
 *  such input and there must not be one. A prohibition that fails on being
 *  written down is a bad prohibition. Every source scan that is about what the
 *  code DOES rather than what it SAYS goes through this. */
function codeOnly(text) {
  return text
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/<!--[\s\S]*?-->/g, "")
    .replace(/^\s*\/\/.*$/gm, "");
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

/**
 * Render the onboarding form for one GET /v1/onboarding body and return its HTML.
 *
 * Same arrangement as renderDetail: the real show() with a stubbed root and a
 * fetch that answers the onboarding read. Screen one is the one that can be
 * reached without a form submit, and it is the one carrying every control.
 */
async function renderOnboarding(body) {
  const before = globalThis.fetch;
  let html = "";
  globalThis.fetch = async () => ({ ok: true, status: 200, json: async () => body });
  const root = {
    set innerHTML(v) { html = v; }, get innerHTML() { return html; },
    addEventListener() {}, removeEventListener() {}, querySelector: () => null,
  };
  try {
    const teardown = await onboardingView.show(root);
    teardown();
    return html;
  } finally {
    globalThis.fetch = before;
  }
}

/**
 * Render one of the search screen's two views and return its HTML.
 *
 * SAME ARRANGEMENT AS renderDetail AND renderOnboarding: the real show() with a
 * stubbed root and a fetch that answers from the frozen fixtures, so the
 * assertions run against the code path the browser takes rather than against an
 * exported fragment. `hash` selects the view, because search.mjs reads the query
 * id out of the hash rather than taking a second ROUTES row.
 *
 * The root grows `querySelectorAll` here, which the other two harnesses do not
 * need: the results list is a REAL render and paints impressions onto its
 * cards, and a stub returning nothing would let that wiring rot unnoticed.
 */
async function renderSearch(hash, { cards = [], respond = searchFixtureFetch } = {}) {
  const beforeFetch = globalThis.fetch;
  const beforeHash = globalThis.location.hash;
  let html = "";
  observedCards = [];
  globalThis.location = { hash };
  globalThis.fetch = async (url, options = {}) => ({
    ok: true, status: 200, json: async () => respond(String(url), options),
  });
  const root = {
    set innerHTML(v) { html = v; }, get innerHTML() { return html; },
    addEventListener() {}, removeEventListener() {},
    querySelector: () => null, querySelectorAll: () => cards,
  };
  try {
    const teardown = await searchView.show(root);
    teardown();
    return html;
  } finally {
    globalThis.fetch = beforeFetch;
    globalThis.location = { hash: beforeHash };
  }
}

/** The six routes, answered from fixtures/shipped/. ORDER MATTERS TWICE:
 *  `/unwatch` contains `/watch`, and both are longer than the bare id. */
function searchFixtureFetch(url) {
  if (url.includes("scope=suggested")) return fixture("GET_v1_searches.suggested.json");
  if (url.includes("scope=mine")) return fixture("GET_v1_searches.mine.json");
  if (url.includes("/unwatch")) return fixture("POST_v1_searches_unwatch.json");
  if (url.includes("/watch")) return fixture("POST_v1_searches_watch.json");
  if (url.includes("/results")) return fixture("GET_v1_searches_results.json");
  if (/\/v1\/searches\/[^/?]+/.test(url)) return fixture("GET_v1_searches_by_id.json");
  if (url.includes("/v1/searches")) return fixture("POST_v1_searches.response.json");
  throw new Error(`no fixture for ${url}`);
}

/** A stand-in for one rendered card, carrying only what paint() reads off it. */
function cardStub(jobId, rank) {
  return { dataset: { jobId, rank: String(rank) } };
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

it("the shipped payload carries role_track, and grouping runs on it", () => {
  // THIS TEST USED TO PIN THE OPPOSITE, and the inversion is the deliverable.
  // It read "the shipped payload carries no role_track, so every row is
  // UNTRACKED", because role_track sat on job_facts (backend/schema.py:733 --
  // the old cite said `jobs` at :542 and was wrong about the table as well as
  // the line) and jobs_app did not select it, so it reached no response body.
  // It closed: "If this ever starts failing, the field has landed and grouping
  // begins working on its own -- which is the point of writing it this way
  // round." The field has landed. Nothing in tracks.mjs changed.
  const body = fixture("GET_v1_jobs.json");
  for (const job of body.jobs) {
    assert.ok("role_track" in job, `${job.id} lost role_track`);
  }
  // A null track is a real answer and not a gap -- "no track fits this" has to
  // be representable (backend/schema.py:715-723), and one row in every four is
  // roughly the live rate through the view. It buckets to UNTRACKED, which is
  // why UNTRACKED needs copy as good as any named track's.
  const seen = body.jobs.map((j) => tracks.trackOf(j));
  assert.ok(seen.includes(tracks.UNTRACKED), "no untracked row left to exercise");
  assert.ok(seen.some((t) => t !== tracks.UNTRACKED), "no tracked row to group");

  const groups = tracks.groupByTrack(body.jobs.map((j) => ({ ...j })));
  assert.ok(groups.length > 1, "grouping collapsed to one bucket");
  assert.deepEqual(groups.flatMap((g) => g.jobs.map((j) => j.rank)).sort(),
                   [1, 2, 3, 4], "grouping must not drop or duplicate a row");
  for (const g of groups) {
    assert.deepEqual(g.jobs.map((j) => j.rank), [...g.jobs.map((j) => j.rank)].sort(),
                     `${g.track} reordered its rows`);
  }
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
  // place. Neither is dropped -- schema.py:715-723 makes role_track NULLABLE
  // BY DESIGN, so "no track fits this" is an answer and not an absence.
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

// -- onboarding ----------------------------------------------------------------
//
// COVERED HERE FOR THE FIRST TIME. frontend/README.md recorded that this client
// "calls neither onboarding route" and that nothing checked the two onboarding
// fixtures against onboarding.py. Both are now false; the fixtures moved into
// shipped/ and verify_fixtures.py derives their shapes, and this is the client
// half of the same pair.

it("onboarding fits inside task 26's screen budget", () => {
  // tranche_five/26 § Definition of done: "Onboarding is <= 3 screens and
  // involves no file upload." Two, because 26 § Onboarding's third step is
  // literally "Nothing else -- resist adding steps", so a confirmation screen
  // would spend the budget on the one thing the task asked not to add.
  assert.ok(onboardingView.SCREENS.length <= 3,
            `${onboardingView.SCREENS.length} screens; the ceiling is 3`);
  assert.deepEqual(onboardingView.SCREENS, ["form", "seed"]);
});

it("there is no file upload anywhere in the client", async () => {
  // THE OTHER HALF OF THAT BULLET, and it is a privacy decision rather than an
  // unfinished feature (onboarding.py:37-43): a resume upload would mean
  // storing personal documents for thirty low-income adults on a residential
  // home connection. Checked in the rendered markup AND in every module's
  // source, because the second catches a file input built at runtime.
  const html = await renderOnboarding(fixture("GET_v1_onboarding.first_run.json"));
  assert.ok(!/type=["']?file/i.test(html), "the onboarding form has a file input");
  for (const file of fs.readdirSync(path.join(HERE, "js"))) {
    const source = codeOnly(fileText("js", file));
    assert.ok(!/type=["']file|FileReader|\.files\b/.test(source),
              `${file} reads a file; onboarding is a form, not an upload`);
  }
  assert.ok(!/type=["']file/.test(codeOnly(fileText("index.html"))),
            "index.html carries a file input");
});

it("every onboarding vocabulary is schema_web's, in order, with copy", () => {
  // ONE SOURCE, THREE ENFORCEMENTS. Each tuple generates a CHECK constraint on
  // builder_profiles (schema_web.py:543-577) AND is what
  // onboarding.validate_request() refuses outside of (:316-337), so a slug
  // invented in the client is a 400 on one Builder's submit and nowhere else.
  // The blurb-style requirement is the tracks.mjs one: a value with no copy is
  // a value somebody added and never gave words to.
  const vocabularies = [
    ["PRIOR_DOMAINS", onboardingView.PRIOR_DOMAIN_LABELS],
    ["SITUATIONS", onboardingView.SITUATION_LABELS],
    ["LOCATION_PREFS", onboardingView.LOCATION_PREF_LABELS],
    ["REMOTE_PREFS", onboardingView.REMOTE_PREF_LABELS],
    ["SCHEDULE_CONSTRAINTS", onboardingView.SCHEDULE_CONSTRAINT_LABELS],
  ];
  for (const [name, labels] of vocabularies) {
    const py = pyTuple("backend/webapp/schema_web.py", name);
    assert.deepEqual(Object.keys(labels), py,
                     `the client's ${name} has drifted from schema_web.py`);
    for (const [slug, text] of Object.entries(labels)) {
      assert.ok(text, `${name}.${slug} has no plain-language copy`);
      assert.ok(!text.includes("_"), `${name}.${slug}'s label is still a slug`);
    }
  }
});

it("the verdicts are VERDICT_EVENTS' keys, and the mapping stays server-side", () => {
  const verdicts = pyDict("backend/webapp/onboarding.py", "VERDICT_EVENTS");
  assert.deepEqual(Object.keys(onboardingView.VERDICT_LABELS), Object.keys(verdicts));
  // The client sends the VERDICT, never the event it maps to. Sending `save`
  // or `dismiss` here would be a second answer to a question onboarding.py:
  // 118-139 already answered with its reasoning attached, and the two would
  // drift -- which is the failure record_seed_judgements() routes through
  // jobs.record_events() to avoid in the first place.
  const source = fileText("js", "onboarding.mjs");
  for (const event of Object.values(verdicts)) {
    assert.ok(!new RegExp(`verdict:\\s*"${event}"`).test(source),
              `onboarding.mjs sends the event '${event}' as a verdict`);
  }
  assert.ok(!/from "\.\/events\.mjs"/.test(source),
            "onboarding.mjs imports events.mjs; a seed judgement must ride in "
            + "the POST body under the server's own request_id "
            + "(onboarding.py:474-495), not as a standalone event");
});

it("the seed size is inside 26's range and under the server's cap", () => {
  const cap = pyInt("backend/webapp/onboarding.py", "MAX_SEED_JUDGEMENTS");
  assert.ok(onboardingView.SEED_TARGET <= cap,
            `SEED_TARGET ${onboardingView.SEED_TARGET} exceeds `
            + `MAX_SEED_JUDGEMENTS ${cap}, which is a 422 from pydantic`);
  assert.ok(onboardingView.SEED_TARGET >= 15 && onboardingView.SEED_TARGET <= 20,
            "26 § Onboarding asks for 15-20 deliberately diverse postings");
});

it("the request body carries exactly the fields OnboardingRequest declares", () => {
  // THE SILENT FAILURE THIS EXISTS FOR. Pydantic ignores unknown keys, so
  // `prior_domains` for `prior_domain` is a 200 that stores nothing. Nothing
  // else on either side catches it.
  const declared = pyModelFields("backend/webapp/onboarding.py", "OnboardingRequest");
  const full = onboardingView.buildRequest({
    prior_domain: "hospitality", prior_years: 6, situation: "employed_seeking",
    location_pref: "nyc", remote_pref: "hybrid_ok", comp_floor: 55000,
    schedule_constraints: ["no_overnight"],
  }, new Map([["j1", "interested"], ["j2", "not_interested"]]));
  assert.deepEqual(Object.keys(full), declared,
                   "buildRequest() and OnboardingRequest have drifted");
  assert.deepEqual(full.seed_judgements, [
    { job_id: "j1", verdict: "interested" },
    { job_id: "j2", verdict: "not_interested" },
  ]);
  // And the frozen request fixture is the same shape, so a client author
  // typing against it lands on the model.
  assert.deepEqual(Object.keys(fixture("POST_v1_onboarding.request.json")), declared);
});

it("every field the endpoint accepts has a control, and no control is orphaned",
   async () => {
  // THE END-TO-END VERSION OF THE CHECK ABOVE, and the one that actually binds.
  // buildRequest() copies whatever it is handed, so passing it a literal only
  // proves the literal. This drives the real form and reads the `name`
  // attributes out of the rendered markup, which is what the browser will post,
  // so it fails in BOTH directions: a model field with no question on the
  // screen, and a question whose answer the server discards silently.
  const declared = pyModelFields("backend/webapp/onboarding.py", "OnboardingRequest")
    .filter((f) => f !== "seed_judgements");   // screen two, not a form control
  const html = await renderOnboarding(fixture("GET_v1_onboarding.first_run.json"));
  const controls = new Set(
    [...html.matchAll(/name="([a-z_]+)"/g)].map((m) => m[1]));
  for (const field of declared) {
    assert.ok(controls.has(field),
              `OnboardingRequest declares '${field}' and the form never asks it`);
  }
  for (const control of controls) {
    assert.ok(declared.includes(control),
              `the form asks '${control}', which OnboardingRequest does not `
              + `declare -- pydantic ignores unknown keys, so that answer is `
              + `discarded and the Builder is told it was saved`);
  }
});

/** Drive readAnswers() with the two FormData methods it actually takes. */
function answersFrom(fields, checked = []) {
  return onboardingView.readAnswers(
    (name) => (name in fields ? fields[name] : null),
    (name) => (name === "schedule_constraints" ? checked : []));
}

it("an untouched form sends nothing, and a blank number is never a zero", () => {
  // ABSENT MEANS PRESERVE on all seven columns -- the upsert is
  // coalesce(EXCLUDED.x, builder_profiles.x) (onboarding.py:432-444) -- so
  // omitting a field is how "I did not touch that question" is expressed. An
  // untouched <select> yields "" and an untouched number box yields "", and
  // BOTH have to come out as null: NULL means nobody asked, and 0 is a real
  // comp_floor meaning "no floor" (onboarding.py:81-83). Number("") is 0,
  // which is exactly how an empty box becomes a preference nobody expressed.
  const blank = answersFrom({
    prior_domain: "", prior_years: "", situation: "", location_pref: "",
    remote_pref: "", comp_floor: "",
  });
  for (const [field, value] of Object.entries(blank)) {
    if (field === "schedule_constraints") continue;
    assert.equal(value, null, `an empty '${field}' came back as ${value} `
                 + `instead of null; NULL is "nobody asked"`);
  }
  const body = onboardingView.buildRequest(blank, new Map());
  assert.deepEqual(Object.keys(body),
                   ["schedule_constraints", "seed_judgements"],
                   "a skipped form must send no preference keys");
  assert.deepEqual(body.seed_judgements, []);

  // A typed 0 IS an answer and must survive the same path.
  assert.equal(answersFrom({ comp_floor: "0" }).comp_floor, 0);
  assert.equal(answersFrom({ prior_years: "0" }).prior_years, 0);
});

it("an empty schedule_constraints is sent, because {} is not NULL", () => {
  // schema_web.py:238-245: `{}` is "asked, and there are none", NULL is
  // "nobody asked". The Builder was shown the boxes either way, so the empty
  // set is a real answer and has to reach the wire as [].
  const none = onboardingView.buildRequest(answersFrom({}, []), new Map());
  assert.ok("schedule_constraints" in none,
            "unticking every box must not collapse to 'nobody asked'");
  assert.deepEqual(none.schedule_constraints, []);

  const ticked = onboardingView.buildRequest(
    answersFrom({}, ["no_overnight"]), new Map());
  assert.deepEqual(ticked.schedule_constraints, ["no_overnight"]);
});

it("the seed draw spreads across tracks", () => {
  // ~~and is rank order while it cannot~~ -- IT CAN NOW, and this test passed
  // for the wrong reason on the day it started to. Its old body asserted the
  // draw was `[1, 2, 3]` because "role_track is in no response body, so
  // trackOf() puts every row in one bucket and the draw is the payload order
  // unchanged". The field landed, the round-robin went live, and the
  // assertion still held -- the top three shipped rows happen to sit in three
  // different buckets, so spread order and payload order coincide on exactly
  // this fixture. A green test whose stated premise is false is worth less
  // than a red one, so this asserts the PROPERTY instead of the sequence.
  const flat = fixture("GET_v1_jobs.json").jobs;
  const drawn = onboardingView.pickSeed(flat, 3);
  const drawnTracks = drawn.map((j) => tracks.trackOf(j));
  assert.equal(new Set(drawnTracks).size, drawn.length,
               "the draw repeated a track while an unused one was available");

  // Round-robin across buckets, so a Builder reacts to a spread rather than to
  // four near-identical top-of-list postings. Same property tracks.mjs's
  // grouping has and for the same reason -- written to start working on its
  // own rather than to be revisited. This arm is synthetic because it needs a
  // bucket with three members, which the shipped payload does not have.
  const tracked = [
    { id: "a", rank: 1, role_track: "software_engineering" },
    { id: "b", rank: 2, role_track: "software_engineering" },
    { id: "c", rank: 3, role_track: "software_engineering" },
    { id: "d", rank: 4, role_track: "data_and_analytics" },
    { id: "e", rank: 5, role_track: "technical_support" },
  ];
  assert.deepEqual(onboardingView.pickSeed(tracked, 3).map((j) => j.id),
                   ["a", "d", "e"], "the draw must not be three of one track");
  assert.equal(onboardingView.pickSeed(tracked, 99).length, 5,
               "asking for more than exists returns what exists");
});

it("a seed card names no score and raises no event", () => {
  for (const raw of fixture("GET_v1_jobs.json").jobs) {
    const html = onboardingView.seedCard(parseJobRow({ ...raw }));
    for (const forbidden of ["match_score", "fit_score", "primary_track",
                             "cohort", "data-act"]) {
      assert.ok(!html.includes(forbidden), `the seed card carries ${forbidden}`);
    }
    // No link off the card either: nothing is stored until Finish, so tapping
    // through would lose every answer given so far.
    assert.ok(!html.includes("href="), "a seed card links away mid-onboarding");
    for (const verdict of Object.keys(onboardingView.VERDICT_LABELS)) {
      assert.ok(html.includes(`data-verdict="${verdict}"`),
                `the seed card offers no '${verdict}' button`);
    }
  }
  const escaped = onboardingView.seedCard({
    id: "x", title: '<img src=x onerror="alert(1)">', company_name: "A & B",
  });
  assert.ok(!escaped.includes("<img"), "a job title reached innerHTML unescaped");
  assert.ok(escaped.includes("A &amp; B"));
});

it("the form reads both onboarding states out of the shipped fixtures", async () => {
  const firstRun = await renderOnboarding(fixture("GET_v1_onboarding.first_run.json"));
  assert.match(firstRun, /Let's set you up/,
               "a Builder who has never onboarded gets the first-run heading");
  // NULL prior_domain is "nobody asked" and must not preselect the domain
  // literally named 'none' -- schema_web.py:177-182 makes that load-bearing.
  assert.match(firstRun, /<option value=""\s+selected>Prefer not to say/);

  const done = await renderOnboarding(fixture("GET_v1_onboarding.json"));
  assert.match(done, /Your setup/, "a returning Builder is not onboarding again");
  assert.match(done, /<option value="hospitality" selected>/,
               "the stored prior_domain is not read back into the form");
  assert.match(done, /value="6"/, "the stored prior_years is not read back");

  // Every field optional, on both. A required attribute here would be the
  // client inventing a constraint the nullable columns refuse to express.
  assert.ok(!/\brequired\b/.test(firstRun + done),
            "a field is marked required; every column is nullable on purpose");
});

it("the two onboarding fixtures agree about the same Builder", () => {
  // One Builder cannot have two answers, the same rule the cohort_signal pair
  // is held to. The POST response's block and the completed GET's block are
  // the same read -- _state(), onboarding.py:502-514 -- so they must match.
  assert.deepEqual(fixture("GET_v1_onboarding.json").onboarding,
                   fixture("POST_v1_onboarding.response.json").onboarding);
});

it("completed_at carries no zone, because onboarded_at is TEXT", () => {
  // builder_profiles.onboarded_at is TEXT (schema_web.py:553) written by
  // lib.timeparse.utc_now_str(), whose docstring says '%Y-%m-%dT%H:%M:%S' is
  // load-bearing and "must not gain an offset". The fixture inherited a
  // trailing Z from the contract, which invented this response shape; a client
  // doing new Date(completed_at) on the real value reads it as LOCAL time.
  // Same trap first_seen sets, which format.mjs:45 handles by appending the Z.
  for (const name of ["GET_v1_onboarding.json", "POST_v1_onboarding.response.json"]) {
    const stamp = fixture(name).onboarding.completed_at;
    assert.match(stamp, /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/,
                 `${name}: completed_at is not utc_now_str()'s format`);
  }
});

// -- search --------------------------------------------------------------------
//
// TASK 25's SIX ROUTES, FROM THE CLIENT SIDE. verify_fixtures.py checks that the
// eleven search fixtures still describe search.py; this is the other direction.
// What it covers that a shape check cannot: a path typo is a 404 nobody sees
// until a Builder taps something, a suppressed watcher count is a correctly
// shaped null that is still a privacy failure if anything renders it as a zero,
// and "never an empty search box" is a product requirement that no key set can
// express.

it("the client calls every route search.py declares, and no other", async () => {
  // DERIVED FROM THE DECORATORS, because a path is the one part of an endpoint
  // a client can get wrong silently: a typo is a 404, and a 404 on a POST is
  // indistinguishable from "that search does not exist" in the error shape.
  const source = fs.readFileSync(path.join(REPO, "backend/webapp/search.py"), "utf8");
  const declared = [...source.matchAll(/@router\.(get|post)\("([^"]+)"\)/g)]
    .map((m) => [m[1].toUpperCase(), m[2]]);
  assert.equal(declared.length, 6, `search.py declares ${declared.length} routes`);

  // Every request the client makes, across the two views plus the three writes
  // no view issues on load.
  const seen = [];
  const record = (url, options = {}) => {
    seen.push([(options.method || "GET").toUpperCase(),
               String(url).split("?")[0]]);
    return searchFixtureFetch(String(url), options);
  };
  await renderSearch("/search", { respond: record });
  await renderSearch("/search/4", { respond: record });

  const before = globalThis.fetch;
  globalThis.fetch = async (url, options = {}) => ({
    ok: true, status: 200, json: async () => record(url, options),
  });
  try {
    await api.createSearch({ text: "grants operations automation" });
    await api.watchSearch(9);
    await api.unwatchSearch(9);
  } finally {
    globalThis.fetch = before;
  }

  const asPattern = (template) =>
    new RegExp(`^${template.replace(/\{[a-z_]+\}/g, "[^/]+")}$`);
  for (const [method, template] of declared) {
    assert.ok(
      seen.some(([m, p]) => m === method && asPattern(template).test(p)),
      `nothing in the client calls ${method} ${template}`);
  }
  for (const [method, path_] of seen) {
    assert.ok(
      declared.some(([m, t]) => m === method && asPattern(t).test(path_)),
      `the client calls ${method} ${path_}, which search.py does not route`);
  }
});

it("a null watcher_bucket renders NOTHING -- never a zero, never 'fewer than'",
   async () => {
  // THE FAILURE THIS PREVENTS, and it is a sharper version of the cohort_signal
  // one. null covers 0, 1, 2 AND 3 watchers indistinguishably, because
  // search_query_signal holds NO ROW below schema.SEARCH_MIN_WATCHERS = 4. The
  // floor is 4 rather than cohort_signal's 3 because a search query is
  // ATTACKER-CHOSEN -- an observer who suspects what someone is looking for can
  // type it, create the row and watch its bucket -- and because the planter is
  // always a watcher (DEC-85). Any copy that makes an absent badge readable as
  // "one to three" hands back exactly what the threshold withholds.
  for (const bucket of [null, undefined, "", 0]) {
    assert.equal(searchView._badge({ watcher_bucket: bucket }), "",
                 `a ${JSON.stringify(bucket)} bucket produced a badge`);
  }
  const forbidden =
    /\b0 watchers|no one|nobody|fewer than|be the first|less than \w+ watch/i;
  for (const hash of ["/search", "/search/4"]) {
    const html = await renderSearch(hash);
    assert.ok(!forbidden.test(html),
              `${hash}: a suppressed watcher count leaked into the copy`);
  }
  // And nothing on the screen offers a raw number of watchers under any name.
  const suppressed = fixture("GET_v1_searches.suggested.json").searches
    .filter((q) => q.watcher_bucket === null);
  assert.ok(suppressed.length, "no suppressed query left in the fixture");
  for (const query of suppressed) {
    assert.ok(!/watching this/.test(searchView._queryRow(query)),
              `query ${query.id} has no bucket and still claims watchers`);
  }
});

it("a populated bucket renders the bucket, and says Builders not others", async () => {
  const html = await renderSearch("/search");
  assert.match(html, /<strong>4-6 Builders<\/strong>\s*are watching this/,
               "the bucket string is rendered as the bucket string");
  // "other Builders" would be wrong by one whenever the reader is one of them,
  // and wrong in the flattering direction -- the same rule the cohort save
  // badge follows.
  assert.ok(!/other Builders/.test(html),
            "the count includes the reader, so 'other' overstates it");
  assert.ok(!/\bexactly\b|computed|first_requested/.test(html),
            "never an exact count, never a recency, never an identity");
});

it("the screen never opens on an empty search box", async () => {
  // 32-frontend.md § Design constraints: "Task 25 seeds search_queries from
  // role_track precisely because someone who does not know what role they want
  // cannot write a good query. Open on suggested tracks and seeded searches,
  // not a blank input." So the seeded catalogue is ABOVE the form in document
  // order, and it is there before anything is typed.
  const html = await renderSearch("/search");
  const suggested = html.indexOf("Suggested searches");
  const form = html.indexOf("<form");
  assert.ok(suggested !== -1, "the catalogue is not on the screen at all");
  assert.ok(form !== -1, "there is no way to type a search");
  assert.ok(suggested < form,
            "the input box is above the suggestions; a Builder with no "
            + "vocabulary for the role they want reaches the box first");
  for (const query of fixture("GET_v1_searches.suggested.json").searches) {
    assert.ok(html.includes(format.esc(query.text)),
              `the suggestion "${query.text}" is not rendered`);
  }
  // Empty on BOTH scopes is still not blank: the form and an explanation stay.
  const bare = await renderSearch("/search", {
    respond: (url) => (url.includes("scope=suggested")
      ? { searches: [], scope: "suggested" }
      : fixture("GET_v1_searches.mine.empty.json")),
  });
  assert.ok(/<form/.test(bare) && /No suggestions yet/.test(bare),
            "with both scopes empty the screen has nothing on it but a box");
});

it("the results list is a real render: every row is observed at its own rank",
   async () => {
  // THE REQUIREMENT THAT CANNOT BE ADDED LATER (32 § Non-negotiable). Unlike
  // the Saved crawl -- which fetches rows nobody saw and deliberately emits no
  // impressions -- these rows were genuinely put in front of a person in this
  // order, so they get real impressions under the server's own request_id.
  const body = fixture("GET_v1_searches_results.json");
  const cards = body.jobs.map((job) => cardStub(job.id, job.rank));
  const html = await renderSearch("/search/4", { cards });
  assert.deepEqual(observedCards, cards,
                   "the results screen rendered rows and observed none of them");
  for (const job of body.jobs) {
    assert.ok(html.includes(`data-rank="${job.rank}"`),
              `rank ${job.rank} is not on the card; events would have none`);
  }
  // rank is the SERVER's, never a DOM index: the ranks in the payload are what
  // every event echoes.
  assert.deepEqual(body.jobs.map((j) => j.rank), [1, 2]);
});

it("a search result is the same object a job list row is", () => {
  // search.py imports LIST_COLUMNS, STATE_FIELDS, COHORT_FIELDS and the joins
  // from jobs.py rather than restating them, so ONE renderer serves both lists.
  // The day these key sets diverge is the day the client needs two.
  const fromList = fixture("GET_v1_jobs.json").jobs[0];
  const fromSearch = fixture("GET_v1_searches_results.json").jobs[0];
  assert.deepEqual(Object.keys(fromSearch), Object.keys(fromList),
                   "the two lists have drifted into two shapes");
  assert.equal(fromSearch.id, fromList.id);
  // Rendered by the literally same function, and the output agrees.
  assert.equal(ui.jobCard(parseJobRow({ ...fromSearch })),
               ui.jobCard(parseJobRow({ ...fromList })));
});

it("no 0-100 score reaches the search results either", async () => {
  const html = await renderSearch("/search/4", {
    cards: fixture("GET_v1_searches_results.json").jobs
      .map((job) => cardStub(job.id, job.rank)),
  });
  for (const forbidden of ["match_score", "fit_score", "primary_track"]) {
    assert.ok(!html.includes(forbidden), `the results screen names ${forbidden}`);
  }
});

it("an empty result set says which of the two empties it is", async () => {
  // A query that has never run and a query that ran and found nothing are
  // different facts. No provider is called on the submit (search.py,
  // create_search), so "hasn't run yet" is the honest state of EVERY search the
  // moment it is created, and showing it as "found nothing" would read as a
  // verdict on the words the Builder chose.
  const neverRun = fixture("POST_v1_searches.response.json");
  assert.equal(neverRun.last_run_at, null);
  const fresh = await renderSearch("/search/57", {
    respond: (url) => (url.includes("/results")
      ? fixture("GET_v1_searches_results.empty.json") : neverRun),
  });
  assert.match(fresh, /hasn't run yet/i);
  assert.ok(!/found nothing|Nothing from this search/i.test(fresh),
            "a search that has never run was reported as having found nothing");

  const ran = { ...fixture("GET_v1_searches_by_id.json") };
  const empty = await renderSearch("/search/4", {
    respond: (url) => (url.includes("/results")
      ? fixture("GET_v1_searches_results.empty.json") : ran),
  });
  assert.match(empty, /Nothing from this search yet/);
  // Never blank, either way: 32 § Definition of done, "empty states are seeded".
  for (const html of [fresh, empty]) {
    assert.match(html, /href="#\//, "an empty state with nowhere to go");
  }
});

it("every refusal a Builder can cause has copy, derived from Python", () => {
  // A code with no entry falls through to the server's own message, which is
  // written for a log line and not for a person -- "query text normalises to
  // nothing" is a sentence about a normaliser. Both files are read because
  // search.py re-raises searchnorm.InvalidQuery as a ContractError carrying the
  // exception's own code, so four of the five appear as a literal only in the
  // top-level pipeline module.
  const codes = new Set();
  for (const relative of ["backend/webapp/search.py", "backend/searchnorm.py"]) {
    const source = fs.readFileSync(path.join(REPO, relative), "utf8");
    for (const m of source.matchAll(/(?:ContractError|InvalidQuery)\(\s*"([a-z_]+)"/g)) {
      codes.add(m[1]);
    }
  }
  assert.ok(codes.size >= 5, `only found ${codes.size} search error codes`);
  const source = fileText("js", "search.mjs");
  const map = source.match(/function searchErrorText[\s\S]*?\n}/);
  assert.ok(map, "searchErrorText is no longer a function in search.mjs");
  for (const code of codes) {
    assert.ok(new RegExp(`^\\s*${code}:`, "m").test(map[0]),
              `'${code}' is a refusal this client can cause and has no copy`);
  }
});

it("a query's role_track and a posting's are kept apart", () => {
  // ONE VOCABULARY, TWO SUBJECTS. search_queries.role_track is why a seeded
  // suggestion exists; job_facts.role_track is a posting's family. Both are
  // extract.ROLE_TRACK slugs and they never share a JSON object, so nothing
  // structural stops them being conflated -- only the copy does.
  assert.deepEqual(searchView.QUERY_TRACK_VOCABULARY, tracks.ROLE_TRACK,
                   "the search screen invented a second track vocabulary");
  const seeded = fixture("GET_v1_searches.suggested.json").searches[0];
  const row = searchView._queryRow(seeded);
  assert.match(row, /For roles like:/,
               "a seeded suggestion does not say what it is for");
  assert.ok(row.includes(tracks.labelFor(seeded.role_track).label),
            "the query's track is not rendered with tracks.mjs's own copy");
  // A builder-created query has role_track null and must claim no track.
  const mine = fixture("GET_v1_searches.mine.json").searches
    .find((q) => q.source === "builder");
  assert.equal(mine.role_track, null);
  assert.ok(!/For roles like:/.test(searchView._queryRow(mine)),
            "a query the Builder typed was given a track it does not have");
});

it("the search screen renders no timestamp a person's action produced", () => {
  // `first_requested_at` is deliberately not in any response: it is the moment
  // one identifiable person typed something, and timing is the strongest
  // deanonymiser available in a cohort who sit in a room together (search.py's
  // module docstring). `last_run_at` IS exposed and IS rendered, because that
  // is the pipeline's clock and no person's act. This asserts the client did
  // not reach for the other one under either spelling.
  const source = codeOnly(fileText("js", "search.mjs"));
  for (const forbidden of ["first_requested_at", "computed_at", "watcher_count"]) {
    assert.ok(!source.includes(forbidden),
              `search.mjs reads ${forbidden}, which no response carries`);
  }
  assert.match(searchView._lastRunLabel({ last_run_at: null }), /Hasn't run yet/);
  assert.match(
    searchView._lastRunLabel({ last_run_at: "2026-08-02T04:12:44",
                              result_count_last_run: 9 }),
    /9 postings/);
});

// -- the router ----------------------------------------------------------------

it("every route has a tab, and every tab has a route", () => {
  // app.mjs cannot be imported here: it reaches for document.getElementById at
  // module scope and boots. So this reads the table as text, which is also
  // what makes it catch the failure it is for -- a screen added to one of the
  // two places and not the other. markTab() matches data-tab against the
  // route's `name`, so the two lists are the same list.
  const app = codeOnly(fileText("js", "app.mjs"));
  const table = app.match(/const ROUTES = \[([\s\S]*?)\n\];/);
  assert.ok(table, "ROUTES is no longer a module-level array literal in app.mjs");
  const routes = [...table[1].matchAll(/name: "([a-z]+)"/g)].map((m) => m[1]);
  const tabs = [...codeOnly(fileText("index.html"))
    .matchAll(/data-tab="([a-z]+)"/g)].map((m) => m[1]);
  assert.ok(routes.includes("onboarding"), "there is no onboarding route");
  assert.ok(tabs.includes("onboarding"), "there is no onboarding tab");
  for (const tab of tabs) {
    assert.ok(routes.includes(tab), `tab '${tab}' routes nowhere`);
  }
  // `job` and the fallback are reachable and deliberately tabless: a detail
  // page belongs to whichever list it was opened from.
  assert.deepEqual(routes.filter((r) => !tabs.includes(r)), ["job"]);
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
