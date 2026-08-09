// Search: the seeded catalogue, the Builder's own queries, and what one found.
//
// NEVER AN EMPTY SEARCH BOX. `git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_six/32-frontend.md` § "Design constraints
// from the population" states it as a constraint and tranche_four/25 says why
// the backend exists in that shape: "task 25 seeds search_queries from
// role_track precisely because someone who does not know what role they want
// cannot write a good query." So this screen OPENS on
// GET /v1/searches?scope=suggested and the text box sits under the suggestions
// rather than above them. A blank input in front of a career changer who does
// not yet have the vocabulary for the role they want is a dead end wearing the
// clothes of a feature.
//
// TWO VIEWS, ONE ROUTE. `#/search` is the catalogue; `#/search/<id>` is one
// query's results. One ROUTES row in app.mjs covers both because the id is read
// out of the hash here -- adding a second row would put the screen's own
// structure in a file that has no other reason to know it.
//
// THE RESULTS LIST IS A REAL RENDER, and that is the load-bearing difference
// from Saved. GET /v1/searches/{id}/results returns /v1/jobs' shape field for
// field, INCLUDING its own request_id and 1-based rank (search.py imports
// LIST_COLUMNS and the cursor codec from jobs.py rather than restating them).
// So these rows were genuinely put in front of a person, in this order, and
// they get real impressions -- unlike crawl.mjs, which fetches rows nobody saw
// and deliberately emits none. Every event from this screen echoes the pair the
// server issued, which is 32's one requirement that cannot be added later.
//
// A WATCHER COUNT IS A BUCKET OR IT IS NOTHING. See badge() below; that comment
// is the one to read before touching any copy on this screen.
//
// `role_track` ON A QUERY IS NOT `role_track` ON A POSTING, and this screen is
// the first place in the client where both exist. On a job row it is
// job_facts.role_track -- the posting's family, which tracks.mjs groups Today
// by. On a query object it is search_queries.role_track -- the track a SEEDED
// suggestion was generated from, i.e. why this row exists at all. They never
// share a JSON object, both are slugs out of the same extract.ROLE_TRACK
// vocabulary, and conflating them would produce a heading that reads as a claim
// about the postings underneath it. So the label under a suggestion says what
// the suggestion is FOR, and nothing on this screen groups postings by track.

import {
  listSearches, createSearch, getSearch, watchSearch, unwatchSearch,
  searchResults, ApiError,
} from "./api.mjs";
import { labelFor, ROLE_TRACK } from "./tracks.mjs";
import { observe, sendAction, stopObserving } from "./events.mjs";
import { remember } from "./renders.mjs";
import { jobCard, askReason, toast, paintSaved, errorBlock, spinner } from "./ui.mjs";
import { esc } from "./format.mjs";

/** One page of results. Same size Today uses, for the same reason. */
const PAGE = 25;

/** How many rows to ask for from each catalogue scope, and it is the
 *  endpoint's own MAX_LIMIT because nothing smaller is provably enough any
 *  more. This was 50, justified by "a Builder may watch at most
 *  MAX_QUERIES_PER_BUILDER = 20" -- T-33 removed that ceiling, so `mine` is now
 *  bounded by nothing but the Builder's patience and a smaller number here
 *  would silently drop the tail of a long list on a screen that has no
 *  pagination to reach it with. `suggested` is one row per role_track, which is
 *  nine, and is unaffected either way.
 *
 *  100 IS STILL A CEILING AND NOT A PROOF. A Builder watching more than a
 *  hundred searches loses the overflow, quietly, which is the failure mode this
 *  project's CLAUDE.md names first. The derived cap is 8 on the free tier, so
 *  it is a hundredfold off the realistic case -- but pagination here, not a
 *  bigger constant, is the actual fix if anyone ever gets near it. */
const CATALOGUE_LIMIT = 100;

const state = {
  queryId: null,
  query: null,
  suggested: [],
  mine: [],
  requestId: null,
  cursor: null,
  jobs: [],
  submitting: false,
};

/** `#/search` -> null, `#/search/4` -> "4". Anything else -> null, because the
 *  catalogue is a better answer to an unrecognised hash than an error is --
 *  the same rule app.mjs's fallback route follows. */
function queryIdFromHash() {
  const match = location.hash.replace(/^#/, "").match(/^\/search\/([^/]+)$/);
  return match ? decodeURIComponent(match[1]) : null;
}

/** Returns a teardown. app.mjs calls it before routing anywhere else, so the
 *  delegated handlers and the IntersectionObserver do not outlive the screen. */
export async function show(root) {
  reset();
  state.queryId = queryIdFromHash();

  const onClickHandler = (event) => onClick(event, root);
  const onSubmitHandler = (event) => onSubmit(event);
  root.addEventListener("click", onClickHandler);
  root.addEventListener("submit", onSubmitHandler);
  const teardown = () => {
    root.removeEventListener("click", onClickHandler);
    root.removeEventListener("submit", onSubmitHandler);
    stopObserving();
  };

  root.innerHTML = spinner(state.queryId ? "Loading this search…"
                                         : "Loading searches…");
  try {
    if (state.queryId) await loadResults();
    else await loadCatalogue();
  } catch (e) {
    root.innerHTML = `<h1>Search</h1>${errorBlock(e, "#/search")}`;
    return teardown;
  }
  paint(root);
  return teardown;
}

function reset() {
  state.queryId = null;
  state.query = null;
  state.suggested = [];
  state.mine = [];
  state.requestId = null;
  state.cursor = null;
  state.jobs = [];
  state.submitting = false;
}

// -- loading ----------------------------------------------------------------

/**
 * The catalogue: two requests, deliberately.
 *
 * The contract fixture (fixtures/contract/ASPIRATIONAL_GET_v1_searches.json)
 * shows ONE response nesting `{suggested, mine}`. The shipped route returns
 * `{searches, scope}` and takes a `scope` parameter, so the two lists are two
 * calls. Recorded as a deviation in frontend/README.md rather than papered
 * over: the shipped shape is the one that ships, and inventing a merged object
 * here would hide a difference the next client author has to know about.
 *
 * They are issued together rather than in sequence -- neither depends on the
 * other, and a Builder on a phone should wait for one round trip, not two.
 */
async function loadCatalogue() {
  const [suggested, mine] = await Promise.all([
    listSearches({ scope: "suggested", limit: CATALOGUE_LIMIT }),
    listSearches({ scope: "mine", limit: CATALOGUE_LIMIT }),
  ]);
  state.suggested = suggested.searches;
  state.mine = mine.searches;
}

/**
 * One query and its first page of results.
 *
 * THE QUERY OBJECT IS FETCHED SEPARATELY AND THAT IS NOT A ROUND TRIP WASTED:
 * the results envelope carries `query_id` and nothing else about the query --
 * not its text, not its watch state, not whether it has ever run. A results
 * page that could not name the search it belongs to would be a list with no
 * heading, and the "this has not run yet" state is only readable from
 * `last_run_at`.
 */
async function loadResults() {
  const [query, page] = await Promise.all([
    getSearch(state.queryId),
    searchResults(state.queryId, { limit: PAGE }),
  ]);
  state.query = query;
  takePage(page);
}

function takePage(body) {
  // The render id comes from the first page and never changes; a later page
  // returns the same one because it rode inside the cursor.
  state.requestId = body.request_id;
  state.cursor = body.next_cursor;
  state.jobs.push(...body.jobs);
  remember(body.request_id, body.jobs);
}

// -- painting ---------------------------------------------------------------

function paint(root) {
  stopObserving();
  root.innerHTML = state.queryId ? resultsScreen() : catalogueScreen();
  if (!state.queryId) return;
  for (const card of root.querySelectorAll(".card")) {
    const rank = Number(card.dataset.rank);
    if (Number.isFinite(rank)) {
      observe(card, state.requestId, card.dataset.jobId, rank);
    }
  }
}

// -- the catalogue ----------------------------------------------------------

function catalogueScreen() {
  return `
    <h1>Search</h1>
    <p class="lede">Pick one of these, or describe the work you want.</p>
    ${suggestedBlock()}
    ${mineBlock()}
    ${searchForm()}
    <p class="muted small">Searches run overnight, so a new one has nothing in it
       until tomorrow. That is why the list above is worth starting from.</p>
  `;
}

/**
 * The seeded catalogue. THIS IS THE FIRST THING ON THE SCREEN, above the form.
 *
 * The label under each one is `labelFor(query.role_track)` -- tracks.mjs's
 * plain-language copy for the track this SUGGESTION was seeded from. It
 * describes the search, never the postings it returns; see the file header.
 */
function suggestedBlock() {
  if (state.suggested.length === 0) {
    // Seeded queries are written by the pipeline, one per role_track, and they
    // never decay (searchnorm.UNDECAYABLE_SOURCES). An empty catalogue means
    // the seeder has not run, which is a real state and not the Builder's
    // fault -- so say so rather than showing a bare box.
    return `<section class="group">
      <div class="group-head"><h2>Suggested searches</h2></div>
      <div class="empty">
        <p><strong>No suggestions yet.</strong></p>
        <p>These are set up for the whole group and appear once the overnight run
           has been through. In the meantime you can describe the work yourself.</p>
      </div>
    </section>`;
  }
  return `<section class="group">
    <div class="group-head">
      <h2>Suggested searches</h2>
      <p class="blurb">Set up for the whole group, one per kind of role. Watch the
         ones you want and they will keep bringing in new postings.</p>
    </div>
    ${state.suggested.map(queryRow).join("")}
  </section>`;
}

function mineBlock() {
  if (state.mine.length === 0) {
    return `<section class="group">
      <div class="group-head"><h2>Your searches</h2></div>
      <div class="empty">
        <p><strong>You aren't watching any searches yet.</strong></p>
        <p>Watching one means it runs again every night and new postings turn up
           here. Start with a suggestion above.</p>
      </div>
    </section>`;
  }
  return `<section class="group">
    <div class="group-head">
      <h2>Your searches</h2>
      <p class="blurb">These run again every night.</p>
    </div>
    ${state.mine.map(queryRow).join("")}
  </section>`;
}

/** One query in a list. A card, so it matches the postings visually and gets
 *  the same 44px tap targets. */
function queryRow(query) {
  const track = query.role_track ? labelFor(query.role_track) : null;
  const isSeeded = query.source !== "builder";
  return `
<article class="card query-card" data-query-id="${esc(query.id)}">
  <a class="card-link" href="#/search/${encodeURIComponent(query.id)}">
    <h3 class="card-title">${esc(query.text)}</h3>
    <p class="card-company">${esc(query.location)}</p>
    ${track && isSeeded
      ? `<p class="query-track">For roles like: ${esc(track.label)}</p>` : ""}
    <ul class="meta">
      <li>${esc(lastRunLabel(query))}</li>
      ${badge(query)}
    </ul>
  </a>
  <div class="actions">
    <button class="btn" type="button" data-act="${query.watching ? "unwatch" : "watch"}"
            aria-pressed="${query.watching ? "true" : "false"}">
      ${query.watching ? "Watching" : "Watch this"}
    </button>
  </div>
</article>`;
}

/**
 * How many people are watching this — or, far more often, nothing at all.
 *
 * `watcher_bucket` IS NULL OR IT IS A LABEL, AND NULL RENDERS NOTHING. Not a
 * zero, not a greyed dash, not "fewer than four", not "be the first". The
 * suppression IS the privacy control (DEC-85): the row does not exist below
 * schema.SEARCH_MIN_WATCHERS = 4, so null is the answer for 0, 1, 2 AND 3
 * watchers indistinguishably, and any copy that makes absence readable as
 * "one to three" hands back exactly what the threshold withholds. In a
 * thirty-person cohort who sit in a room together, one watcher is close to an
 * identifier — and a search query is worse than a save count here, because an
 * observer can CREATE the query they want to watch. That chosen-plaintext
 * capability is why the floor is 4 where cohort_signal's is 3.
 *
 * At today's cohort size every value is null, so nothing-at-all is the main
 * path, not the edge case.
 *
 * "Builders", never "other Builders": the fold counts every distinct watcher
 * including the reader, so "other" would be wrong by one exactly when the
 * reader is one of them. Same rule the cohort save badge follows.
 */
function badge(query) {
  if (!query.watcher_bucket) return "";
  return `<li class="watchers"><strong>${esc(query.watcher_bucket)} Builders</strong>
          are watching this</li>`;
}

/** When the pipeline last ran it. `last_run_at` is the PIPELINE's clock and is
 *  safe to show; `first_requested_at` is the moment one identifiable person
 *  typed something and is deliberately not in any response (search.py). */
function lastRunLabel(query) {
  if (!query.last_run_at) return "Hasn't run yet";
  const found = query.result_count_last_run;
  if (found === null || found === undefined) return "Ran overnight";
  return found === 1 ? "Found 1 posting last night"
                     : `Found ${found} postings last night`;
}

/**
 * The box. UNDER the suggestions, never above them, and never the whole screen.
 *
 * Location is a separate field with the cohort's own city pre-filled, because
 * searchnorm.DEFAULT_LOCATION is "New York, NY" and leaving it blank would make
 * a Builder type the one thing the whole product already assumes.
 */
function searchForm() {
  return `<section class="group">
    <div class="group-head">
      <h2>Describe it yourself</h2>
      <p class="blurb">Plain words work best — the kind of job, not a job title
         you found somewhere.</p>
    </div>
    <form class="onboard search-form">
      <div class="field">
        <label for="q-text">What kind of work?</label>
        <input id="q-text" name="text" type="text" maxlength="200"
               autocomplete="off" placeholder="grants operations, automation">
        <p class="hint">The words a person would use, not a job title you copied
           from somewhere. "ai operations" and "AI Operations!" are the same
           search — spelling and punctuation don't matter.</p>
      </div>
      <div class="field">
        <label for="q-location">Where?</label>
        <input id="q-location" name="location" type="text" maxlength="120"
               autocomplete="off" value="New York, NY">
      </div>
      <div class="onboard-actions">
        <button class="btn primary" type="submit" data-act="submit">Start this search</button>
      </div>
    </form>
  </section>`;
}

// -- one query's results ----------------------------------------------------

function resultsScreen() {
  const query = state.query;
  const track = query && query.role_track ? labelFor(query.role_track) : null;
  return `
    <a class="back" href="#/search">← All searches</a>
    <h1>${esc(query ? query.text : "This search")}</h1>
    <p class="card-company">${esc(query ? query.location : "")}</p>
    <ul class="meta">
      <li>${esc(query ? lastRunLabel(query) : "")}</li>
      ${query ? badge(query) : ""}
    </ul>
    ${track && query.source !== "builder"
      ? `<p class="query-track">For roles like: ${esc(track.label)}</p>` : ""}
    <div class="detail-actions">
      <button class="btn" type="button"
              data-act="${query && query.watching ? "unwatch" : "watch"}"
              aria-pressed="${query && query.watching ? "true" : "false"}">
        ${query && query.watching ? "Watching" : "Watch this"}
      </button>
    </div>
    ${state.jobs.length === 0 ? resultsEmptyState() : `
      <p class="lede">${state.jobs.length} posting${state.jobs.length === 1 ? "" : "s"}
         from this search, strongest first.</p>
      ${state.jobs.map(jobCard).join("")}
      ${state.cursor
        ? `<button class="btn wide" type="button" data-act="more">Show more</button>`
        : `<p class="muted small">That's everything this search has found.</p>`}
    `}
  `;
}

/**
 * Empty, and never blank — and the two reasons for empty are different answers.
 *
 * A query that has never run has nothing to say yet, which is the honest state
 * of every search the moment it is created: no provider is called on the
 * submit (search.py, create_search). A query that HAS run and returned nothing
 * is a different fact, and the most likely cause is the one worth naming — the
 * results route joins jobs_app, so a posting that did not pass the pipeline's
 * relevance gate is filtered out here exactly as it would be from Today.
 */
function resultsEmptyState() {
  const query = state.query;
  if (!query || !query.last_run_at) {
    return `<div class="empty">
      <p><strong>This one hasn't run yet.</strong></p>
      <p>Searches go out overnight rather than the moment you press the button, so
         come back tomorrow and this will have filled in. Nothing is lost in the
         meantime — it will keep running as long as you are watching it.</p>
      <p><a href="#/today">Today's postings</a></p>
    </div>`;
  }
  return `<div class="empty">
    <p><strong>Nothing from this search yet.</strong></p>
    <p>It ran, and nothing it found was an entry-level role in New York that we
       could stand behind. It will run again tonight.</p>
    <p><a href="#/search">Try one of the suggested searches</a></p>
  </div>`;
}

// -- interaction ------------------------------------------------------------

async function onSubmit(event) {
  const form = event.target.closest("form");
  if (!form) return;
  event.preventDefault();
  if (state.submitting) return;

  const data = new FormData(form);
  const text = String(data.get("text") || "").trim();
  const location = String(data.get("location") || "").trim();
  if (!text) {
    // The server would answer this with `empty_query` (searchnorm.validate).
    // Saying it here costs one round trip less and no correctness: the check is
    // "did they type anything", not a second normaliser -- reimplementing
    // normalize() in the client is precisely what searchnorm.py's docstring
    // says would quietly halve the cache hit rate.
    toast("Type a few words about the work you want.");
    return;
  }

  state.submitting = true;
  const button = form.querySelector('[data-act="submit"]');
  if (button) { button.disabled = true; button.textContent = "Starting…"; }
  try {
    const query = await createSearch({ text, location: location || null });
    // The notice goes out BEFORE the navigation, because goTo() triggers a
    // hashchange that repaints the screen, and a toast raised after it would
    // be attached to a view that is already being replaced.
    const notice = planWarningText(query);
    if (notice) toast(notice);
    // Idempotent on the normalised key, so this may be a row somebody else
    // created — same id, their spelling, their run history. Going to it is
    // right either way and the results screen tells the truth about which.
    goTo(`#/search/${encodeURIComponent(query.id)}`);
  } catch (e) {
    state.submitting = false;
    if (button) { button.disabled = false; button.textContent = "Start this search"; }
    toast(searchErrorText(e));
    console.error(e);
  }
}

/** Navigation is a hash assignment and nothing else: app.mjs's `hashchange`
 *  listener does the routing, so this must NOT also call anything that paints,
 *  or the screen renders twice and fetches twice. Same reason boot() leaves
 *  routing to the hashchange after sending a first-run Builder to onboarding. */
function goTo(hash) {
  location.hash = hash;
}

/**
 * The refusals a Builder can actually cause, in words.
 *
 * THERE IS NO too_many_searches ENTRY AND THERE MUST NOT BE ONE. It was here,
 * and T-33 deleted it with the 400 it described: watching past the plan is a
 * warning carried on a 2xx now (see planWarningText), not a refusal. Copy for
 * a refusal the server cannot issue is copy no one can ever check.
 *
 * The normalisation codes all mean "there were no usable words in that".
 */
/**
 * The soft warning create/watch may carry on a SUCCESSFUL response, in words,
 * or null when there is nothing to say.
 *
 * A NOTICE AND NOT AN ERROR, and the copy has to hold that line. The save
 * worked; the Builder keeps the keyword; what changed is only how often it
 * will be re-asked. Anything that reads as "we didn't do that" would put the
 * refusal back in the Builder's head after T-33 took it out of the server.
 *
 * The server's own `message` is not shown. It names the plan's nightly figure,
 * which is a fact about a SerpApi invoice, and docs/adr/0007 decision 5 keeps
 * claims, cadence and quota out of this UI entirely.
 */
function planWarningText(query) {
  if (!query || !query.warning) return null;
  return query.warning.code === "watching_past_plan"
    ? "Saved. You're watching more searches than we can refresh every night, "
      + "so some will update less often."
    : null;
}

function searchErrorText(error) {
  if (!(error instanceof ApiError)) return "Couldn't start that search.";
  return {
    empty_query: "Type a few words about the work you want.",
    empty_location: "That location didn't come through. Try a city name.",
    query_too_long: "That's too long — a few words works better than a sentence.",
    location_too_long: "That location is too long.",
  }[error.code] || `Couldn't start that search: ${error.message}`;
}

async function onClick(event, root) {
  const more = event.target.closest('[data-act="more"]');
  if (more) {
    event.preventDefault();
    more.disabled = true;
    more.textContent = "Loading…";
    try {
      takePage(await searchResults(state.queryId,
                                   { limit: PAGE, cursor: state.cursor }));
      paint(root);
    } catch (e) {
      more.disabled = false;
      more.textContent = "Show more";
      toast("Could not load more postings.");
      console.error(e);
    }
    return;
  }

  const button = event.target.closest("[data-act]");
  if (!button) return;
  const act = button.dataset.act;

  if (act === "watch" || act === "unwatch") {
    event.preventDefault();
    return toggleWatch(button, root, act);
  }

  const card = button.closest(".card");
  if (!card || !card.dataset.jobId) return;
  const job = state.jobs.find((j) => j.id === card.dataset.jobId);
  if (!job) return;
  event.preventDefault();

  if (act === "save") return toggleSave(job, root);
  if (act === "dismiss") return dismiss(job, root);
}

/**
 * Watch / unwatch, on either view.
 *
 * NOT OPTIMISTIC, unlike save. A save writes a per-Builder state row this
 * client already knows the outcome of; a watch can be REFUSED by the cap, and
 * the response is the query re-read by the server, which is also the only place
 * a changed `watcher_bucket` could come from -- the service holds no grant to
 * write one and this client must never compute one. So the row is repainted
 * from what came back, not from what was hoped for.
 */
async function toggleWatch(button, root, act) {
  const card = button.closest("[data-query-id]");
  const queryId = card ? card.dataset.queryId : state.queryId;
  if (queryId === null || queryId === undefined) return;

  button.disabled = true;
  try {
    const updated = act === "watch" ? await watchSearch(queryId)
                                    : await unwatchSearch(queryId);
    applyQuery(updated);
    paint(root);
    // The warning REPLACES the plain confirmation rather than following it:
    // its copy already opens with "Saved.", and two toasts for one tap reads
    // as two things having happened.
    toast(planWarningText(updated)
          || (updated.watching ? "Watching. New postings will turn up here."
                               : "Stopped watching."));
  } catch (e) {
    button.disabled = false;
    toast(searchErrorText(e));
    console.error(e);
  }
}

/** Put a re-read query back wherever this screen is holding it. `mine` is a
 *  membership list, so a watch adds to it and an unwatch removes it — which is
 *  what the next load would show and therefore what this one must. */
function applyQuery(updated) {
  if (state.query && String(state.query.id) === String(updated.id)) {
    state.query = updated;
  }
  const replace = (list) => list.map(
    (q) => (String(q.id) === String(updated.id) ? updated : q));
  state.suggested = replace(state.suggested);
  state.mine = updated.watching
    ? (state.mine.some((q) => String(q.id) === String(updated.id))
        ? replace(state.mine) : [...state.mine, updated])
    : state.mine.filter((q) => String(q.id) !== String(updated.id));
}

/** save / unsave, identical to Today's: the state row is written server-side in
 *  the same transaction as the event, so the only way this diverges is a
 *  refused batch, which surfaces as a toast from app.mjs's error handler. */
async function toggleSave(job, root) {
  job.saved = !job.saved;
  paintSaved(root, job.id, job.saved);
  await sendAction(state.requestId, {
    event: job.saved ? "save" : "unsave",
    job_id: job.id,
    rank: job.rank,
  });
  toast(job.saved ? "Saved." : "Removed from saved.");
}

/**
 * Dismiss, with a reason, with an undo — the same flow Today has, because it is
 * the same act on the same kind of row.
 *
 * The card leaves the list because the results route hides dismissals by
 * default too (`bs.dismissed_at IS NULL` unless include_dismissed, search.py),
 * so a card that stayed put would be lying about what a refresh shows. The undo
 * sends `undismiss` with NO reason: one there is a 400 with code
 * `reason_not_allowed`, because the reason belongs to the dismissal being
 * reversed and is already on that row.
 */
async function dismiss(job, root) {
  const reason = await askReason();
  if (reason === undefined) return;      // "never mind, keep it"

  job.dismissed = true;
  state.jobs = state.jobs.filter((j) => j.id !== job.id);
  paint(root);

  await sendAction(state.requestId, {
    event: "dismiss",
    job_id: job.id,
    rank: job.rank,
    reason: reason ?? undefined,          // null means the question was skipped
  });

  toast("Hidden. We'll send you fewer like it.", {
    label: "Undo",
    run: async () => {
      job.dismissed = false;
      state.jobs.push(job);
      state.jobs.sort((a, b) => a.rank - b.rank);
      paint(root);
      await sendAction(state.requestId, { event: "undismiss", job_id: job.id });
      toast("Put back.");
    },
  });
}

// -- exported for the checker -----------------------------------------------
//
// check_client.mjs drives show() against the shipped fixtures for everything it
// can, but three things are worth asserting directly: that the badge refuses a
// falsy bucket in every form, that the two lists on the catalogue are built
// from the two scopes rather than merged, and that the query-track copy is
// keyed off the same vocabulary tracks.mjs holds.

export { badge as _badge, queryRow as _queryRow, lastRunLabel as _lastRunLabel,
         planWarningText as _planWarningText };

/** The track vocabulary a query's `role_track` is drawn from. Re-exported so
 *  the checker can assert this screen reads the SAME closed set the posting
 *  axis does, rather than a second copy — one vocabulary, two meanings, and
 *  the meanings are kept apart by the copy, not by a second list. */
export const QUERY_TRACK_VOCABULARY = ROLE_TRACK;
