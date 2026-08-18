// Onboarding: the structured form, then the seed judgements. Two screens.
//
// TWO, NOT THREE, AND THE BUDGET IS THREE. tranche_five/26 § Onboarding lists
// three steps and the third is literally "Nothing else -- resist adding steps.
// The population includes people for whom this is a first technical product;
// every additional screen loses someone." So the third step is honoured by not
// existing: there is no confirmation screen and no welcome screen. Finishing
// posts the form and lands the Builder on Today, with the outcome in a toast.
// SCREENS below is the whole list and check_client.mjs asserts its length
// against the task's ceiling, because "<= 3 screens" is a definition-of-done
// bullet and a bullet nothing checks is a bullet that drifts.
//
// NO FILE UPLOAD, AND IT IS A PRIVACY DECISION RATHER THAN AN UNFINISHED
// FEATURE. backend/webapp/onboarding.py:37-43 states it for the server: a
// resume upload would mean storing personal documents for thirty low-income
// adults on a residential home connection, and a structured form yields the
// same matching-relevant fields without ever holding the document. There is no
// <input type="file"> on this page and there must not be one; check_client.mjs
// asserts the rendered markup contains none.
//
// EVERY FIELD IS OPTIONAL, INCLUDING ALL OF THEM. Each column is nullable and
// NULL means NOBODY ASKED rather than "no" (schema_web.py:290-294), and
// OnboardingRequest defaults every field to None (onboarding.py:270-277) for
// the stated reason that "you may skip this" is the actual product
// requirement. So this screen has a "Skip for now" on it and submitting an
// entirely blank form is legal. A required field here would be the client
// inventing a constraint the schema refuses to express.
//
// IT EMITS NO EVENTS THROUGH events.mjs. The judgements ride inside the POST
// body and the SERVER mints their request_id (onboarding.py:478) -- a seed set
// is its own render, and it is honest to name it as one. Sending them as
// impressions or saves under the LIST's request_id would claim they were part
// of a render they were not, and would arm derive_skips against rows nobody was
// shown. Same reasoning crawl.mjs:17-20 already applies to the Saved crawl.
//
// WHAT THE FOUR PREFERENCES DO TODAY: they are stored, and they filter
// nothing. onboarding.resolved_for() is the read half and its own docstring
// says "NOTHING CALLS THIS ON THE LIST PATH YET" (onboarding.py:246-252) --
// jobs.list_jobs() does not filter on location_pref, remote_pref, comp_floor or
// tracks. So the copy on this screen says the answers are saved and does NOT
// say they change the list. Promising a filter that does not run is the same
// class of mistake as rendering a suppressed count as a zero.

import { getOnboarding, postOnboarding } from "./api.mjs";
import { crawlAll } from "./crawl.mjs";
import { trackOf } from "./tracks.mjs";
import { toast, errorBlock, spinner } from "./ui.mjs";
import { esc, ageLabel, compLabel, placeLabel, reasonsFor } from "./format.mjs";

/** The screens, in order. The ceiling is three (26 § Definition of done). */
export const SCREENS = ["form", "seed"];

/** How many postings to put in front of a Builder. 26 § Onboarding asks for
 *  "15-20 deliberately diverse postings"; this is the middle of that range.
 *  The server's own cap is MAX_SEED_JUDGEMENTS = 40 (onboarding.py:145) and
 *  exists for the reason EventBatch's does -- an unbounded list is a way to
 *  make one request cost an arbitrary number of inserts. check_client.mjs
 *  re-derives both numbers out of Python and asserts this sits under the cap
 *  and inside the range. */
export const SEED_TARGET = 18;

// --------------------------------------------------------------------------
// The vocabularies, in plain language
// --------------------------------------------------------------------------
//
// EVERY SLUG BELOW IS backend/webapp/schema_web.py's, AND THE ORDER IS TOO.
// Each tuple there generates a CHECK constraint on builder_profiles or
// app_users (schema_web.py:657-664, :512), and onboarding.validate_request()
// (:316-337) refuses anything outside it with a 400 -- so a slug invented here
// is a 400 on one Builder's submit and nowhere else. check_client.mjs
// re-derives all five tuples from Python and fails on a value with no copy,
// which is the same arrangement tracks.mjs has for ROLE_TRACK and format.mjs
// has for DISMISS_REASONS.
//
// THE COPY IS THE PART THAT CANNOT BE GENERATED. 32-frontend.md: "No jargon
// inherited from the schema. A label should read like something a person would
// say." `hybrid_ok` humanises to "Hybrid ok", which is a slug wearing a hat.

/** Prior domain. NULL and `none` are DIFFERENT ANSWERS and the difference is
 *  load-bearing: schema_web.py:239-244 spends a paragraph on it. `none` is a
 *  real answer about a real person -- "I have not worked in any of these" --
 *  and NULL means nobody asked. So "Prefer not to say" is the absence of a
 *  selection and is NOT an option in this list. */
export const PRIOR_DOMAIN_LABELS = {
  healthcare: "Healthcare",
  education: "Education",
  retail: "Retail",
  hospitality: "Hospitality, food or events",
  logistics: "Logistics, warehousing or delivery",
  administration: "Office and administration",
  trades: "A skilled trade",
  military: "The military",
  other: "Something else",
  none: "None of these — this is my first line of work",
};

/** Current situation. The one onboarding field that is about urgency rather
 *  than matching (schema_web.py:315-316): nothing scores or filters on it. */
export const SITUATION_LABELS = {
  employed_seeking: "Working now, and looking",
  unemployed_seeking: "Not working, and looking",
  in_program: "In the program full time",
  other: "Something else",
};

/** Where they will work. Three values because the read path has exactly two
 *  booleans, `location_is_nyc` and `location_is_remote` (schema_web.py:348-354);
 *  a richer vocabulary would be a promise the list cannot keep. */
export const LOCATION_PREF_LABELS = {
  nyc: "In New York City",
  remote: "Remote",
  either: "Either is fine",
};

/** A THRESHOLD, NOT A SET, and the copy has to carry that or the answers are
 *  wrong. schema_web.py:363-371: this is "the least-flexible arrangement a
 *  Builder will accept", read as "this or better" over extract.REMOTE_POLICY.
 *  `onsite_ok` is the PERMISSIVE end -- it means "onsite is acceptable too",
 *  not "onsite only" -- which reads backwards from the slug and is why every
 *  label below is a sentence rather than a word. It is also the shared default
 *  (onboarding.DEFAULTS, :87-92), for relevance.DISABLED's reason: a
 *  preference nobody expressed must not silently filter. */
export const REMOTE_PREF_LABELS = {
  onsite_ok: "I'll go in every day if the job needs it",
  hybrid_ok: "Some days in the office, some days at home",
  remote_only: "Fully remote only",
};

/** Hard scheduling limits, as a set. ONE VALUE, and that is the honest size of
 *  it: `no_overnight` is the only constraint attested anywhere in the repo
 *  (schema_web.py:381-387). Rendered as checkboxes rather than a select
 *  because the column is TEXT[] and `{}` -- "asked, and there are none" -- is
 *  a different answer from NULL. */
export const SCHEDULE_CONSTRAINT_LABELS = {
  no_overnight: "I can't work overnight shifts",
};

/** The two verdicts, and the words on the buttons. The slugs are
 *  onboarding.VERDICT_EVENTS' keys (onboarding.py:139) and the mapping onto
 *  real events is the SERVER's: `interested` -> save, `not_interested` ->
 *  dismiss, decided there with the reasoning. This client sends the verdict,
 *  never the event, so the mapping cannot drift into two answers. */
export const VERDICT_LABELS = {
  interested: "Interested",
  not_interested: "Not for me",
};

// --------------------------------------------------------------------------
// State
// --------------------------------------------------------------------------

const state = {
  screen: SCREENS[0],
  completed: false,
  /** The seven fields OnboardingRequest accepts, and only those. A field this
   *  client sends that the model does not declare is DISCARDED SILENTLY --
   *  pydantic ignores unknown keys -- so the Builder would answer a question
   *  that went nowhere and get a 200 saying it worked. That is this system's
   *  documented failure mode in miniature, and it is why check_client.mjs
   *  re-derives the field names out of onboarding.py instead of reading them
   *  here. */
  answers: {
    prior_domain: null,
    prior_years: null,
    situation: null,
    location_pref: null,
    remote_pref: null,
    comp_floor: null,
    schedule_constraints: null,
  },
  /** job_id -> "interested" | "not_interested" */
  verdicts: new Map(),
  seed: [],
  seedError: null,
  submitting: false,
};

function reset() {
  state.screen = SCREENS[0];
  state.completed = false;
  for (const key of Object.keys(state.answers)) state.answers[key] = null;
  state.verdicts = new Map();
  state.seed = [];
  state.seedError = null;
  state.submitting = false;
}

// --------------------------------------------------------------------------
// The seed set
// --------------------------------------------------------------------------

/**
 * Pick the postings to react to, spread as widely as the payload allows.
 *
 * 26 asks for postings "drawn across `role_track`s". ~~THERE IS NO role_track
 * TO DRAW ACROSS~~ -- THERE IS, as of the commit that added `f.role_track` to
 * the `jobs_app` view. The column is on job_facts (backend/schema.py:745; the
 * old cite here said :542, which is the profiles DDL and was wrong about the
 * table as well as the line), and the view not selecting it was the finding
 * frontend/README.md § "What building against these fixtures turned up" opened
 * with.
 *
 * The draw was written round-robin over trackOf() anyway, against a field that
 * was always null, so that it would start working on its own rather than be
 * revisited. THAT IS WHAT HAPPENED: not one line in this file changed and the
 * draw became diverse. The bet is worth recording because the cost of losing
 * it was one degenerate bucket and the alternative was a comment promising to
 * do it later.
 *
 * RANK ORDER IS PRESERVED INSIDE EVERY BUCKET and the buckets are visited in
 * best-rank order, so with one bucket the output is the payload order
 * unchanged. Nothing here re-sorts by fit_score -- that would put an LLM call
 * on an ordering path (.claude/CLAUDE.md, stated in three files).
 */
export function pickSeed(jobs, target = SEED_TARGET) {
  const buckets = new Map();
  for (const job of jobs) {
    const track = trackOf(job);
    if (!buckets.has(track)) buckets.set(track, []);
    buckets.get(track).push(job);
  }
  const queues = [...buckets.values()];
  const picked = [];
  for (let round = 0; picked.length < target; round++) {
    let took = false;
    for (const queue of queues) {
      if (round >= queue.length) continue;
      picked.push(queue[round]);
      took = true;
      if (picked.length === target) break;
    }
    if (!took) break;
  }
  return picked;
}

async function loadSeed() {
  state.seedError = null;
  try {
    // The crawl, not a single page: it is one render, it emits no impressions
    // (crawl.mjs), and one page of 25 is not enough to spread across nine
    // buckets the day there are nine. Its request_id is deliberately unused --
    // the seed set gets the server's own.
    const { jobs } = await crawlAll();
    state.seed = pickSeed(jobs);
  } catch (e) {
    state.seedError = e;
    state.seed = [];
  }
}

// --------------------------------------------------------------------------
// The request body
// --------------------------------------------------------------------------

/**
 * The answers and the verdicts, as OnboardingRequest wants them.
 *
 * A FIELD NOBODY ANSWERED IS OMITTED, NOT SENT AS null. Both are accepted --
 * every field defaults to None -- but the UPSERT is `coalesce(EXCLUDED.x,
 * builder_profiles.x)` on all seven (onboarding.py:438-449), i.e. ABSENT MEANS
 * PRESERVE. So on a re-submission an omitted field keeps the Builder's earlier
 * answer, which is what "I did not touch that question" means. Sending an
 * explicit null does the same thing today; omitting it is what the intent
 * actually is, and events.mjs's clean() makes the same distinction for the same
 * reason.
 *
 * `schedule_constraints: []` IS SENT WHEN THE BUILDER UNTICKED EVERYTHING, and
 * that is not the same as omitting it: `{}` is "asked, and there are none",
 * NULL is "nobody asked" (schema_web.py:303-307). The form knows which of the
 * two happened, so it says so.
 */
export function buildRequest(answers, verdicts) {
  const body = {};
  for (const [key, value] of Object.entries(answers)) {
    if (value !== null && value !== undefined) body[key] = value;
  }
  body.seed_judgements = [...verdicts.entries()]
    .map(([job_id, verdict]) => ({ job_id, verdict }));
  return body;
}

// --------------------------------------------------------------------------
// Rendering
// --------------------------------------------------------------------------

export async function show(root) {
  reset();
  root.innerHTML = spinner("Loading…");

  try {
    const body = await getOnboarding();
    state.completed = Boolean(body.onboarding && body.onboarding.completed);
    // The two fields the endpoint reads back are the two it stores outside
    // builder_profiles' preference columns, so they are the only ones that can
    // be pre-filled. prior_domain lives on app_users because it is a fact
    // about the labeller rather than a matching input (onboarding.py:553-559).
    if (body.onboarding) {
      state.answers.prior_domain = body.onboarding.prior_domain ?? null;
      state.answers.prior_years = body.onboarding.prior_years ?? null;
    }
  } catch (e) {
    root.innerHTML = errorBlock(e, "#/onboarding");
    return () => {};
  }

  const onSubmit = (event) => onFormSubmit(event, root);
  const handler = (event) => onClick(event, root);
  root.addEventListener("click", handler);
  root.addEventListener("submit", onSubmit);

  paint(root);
  return () => {
    root.removeEventListener("click", handler);
    root.removeEventListener("submit", onSubmit);
  };
}

function paint(root) {
  root.innerHTML = state.screen === "seed" ? seedScreen() : formScreen();
}

/** "Step 1 of 2". Rendered from SCREENS so it cannot disagree with the list. */
function stepLabel() {
  const index = SCREENS.indexOf(state.screen) + 1;
  return `<p class="step">Step ${index} of ${SCREENS.length}</p>`;
}

// -- screen 1: the form -----------------------------------------------------

function formScreen() {
  const a = state.answers;
  return `
    ${stepLabel()}
    <h1>${state.completed ? "Your setup" : "Let's set you up"}</h1>
    <p class="lede">${state.completed
      ? "Change anything here and it will be saved over your last answers."
      : "A few questions so we know who we're picking postings for. "
        + "Every one is optional — skip anything you'd rather not answer."}</p>

    <form class="onboard" novalidate>
      ${select("prior_domain", "What kind of work have you done before?",
               PRIOR_DOMAIN_LABELS, a.prior_domain)}

      <div class="field">
        <label for="ob-prior_years">How many years, roughly?</label>
        <input id="ob-prior_years" name="prior_years" type="number" inputmode="numeric"
               min="0" max="60" step="1" value="${esc(a.prior_years ?? "")}">
      </div>

      ${select("situation", "Where are you right now?",
               SITUATION_LABELS, a.situation)}

      ${select("location_pref", "Where do you want to work?",
               LOCATION_PREF_LABELS, a.location_pref)}

      ${select("remote_pref", "How much of it can be in an office?",
               REMOTE_PREF_LABELS, a.remote_pref)}

      <div class="field">
        <label for="ob-comp_floor">Is there a salary you need to clear?</label>
        <input id="ob-comp_floor" name="comp_floor" type="number" inputmode="numeric"
               min="0" step="1000" placeholder="e.g. 55000"
               value="${esc(a.comp_floor ?? "")}">
        <p class="hint">A yearly figure, before tax. Leave it blank if you'd
           rather not put a number on it.</p>
      </div>

      <fieldset class="field">
        <legend>Anything that rules a job out?</legend>
        ${Object.entries(SCHEDULE_CONSTRAINT_LABELS).map(([slug, text]) => `
          <label class="check">
            <input type="checkbox" name="schedule_constraints" value="${esc(slug)}"
                   ${(a.schedule_constraints || []).includes(slug) ? "checked" : ""}>
            <span>${esc(text)}</span>
          </label>`).join("")}
      </fieldset>

      <p class="hint">We don't ask for a CV and there's nothing to upload.
         These answers are saved to your profile.</p>

      <div class="onboard-actions">
        <button class="btn primary wide" type="submit">Next</button>
        <a class="linkish wide" href="#/today">Skip for now</a>
      </div>
    </form>`;
}

/** One <select>, with the unanswered state as a real option.
 *
 *  THE PLACEHOLDER IS NOT A VALUE. Its option has value="" and maps back to
 *  null, which is the column's "nobody asked". For prior_domain that matters
 *  more than anywhere else: `none` is in the list below as its own answer,
 *  because "I have not worked in any of these" and "I did not say" are
 *  different facts about a person (schema_web.py:239-244). */
function select(name, question, labels, current) {
  const options = Object.entries(labels).map(([slug, text]) =>
    `<option value="${esc(slug)}"${current === slug ? " selected" : ""}>${esc(text)}</option>`
  ).join("");
  return `
    <div class="field">
      <label for="ob-${esc(name)}">${esc(question)}</label>
      <select id="ob-${esc(name)}" name="${esc(name)}">
        <option value=""${current == null ? " selected" : ""}>Prefer not to say</option>
        ${options}
      </select>
    </div>`;
}

// -- screen 2: the seed judgements ------------------------------------------

function seedScreen() {
  if (state.seedError) {
    return `${stepLabel()}<h1>A few real postings</h1>
      ${errorBlock(state.seedError, "#/onboarding")}
      <button class="btn wide" type="button" data-act="finish">
        Finish without these
      </button>`;
  }
  if (state.seed.length === 0) {
    return `${stepLabel()}<h1>A few real postings</h1>${emptyState()}`;
  }

  const judged = state.verdicts.size;
  return `
    ${stepLabel()}
    <h1>A few real postings</h1>
    <p class="lede">Say which of these you'd want and which you wouldn't. There
       is no wrong answer, and you can change your mind later on any of them.</p>
    <p class="hint">These become the first things your list learns from. Skip
       any you're not sure about.</p>

    ${state.seed.map(seedCard).join("")}

    <div class="onboard-actions sticky">
      <p class="tally">${judged} of ${state.seed.length} answered</p>
      <button class="btn primary wide" type="button" data-act="finish"
              ${state.submitting ? "disabled" : ""}>
        ${state.submitting ? "Saving…" : judged ? "Finish" : "Finish without answering"}
      </button>
      <button class="linkish wide" type="button" data-act="back">Back</button>
    </div>`;
}

/**
 * One posting, to react to.
 *
 * NOT ui.jobCard(). That card's two buttons raise real events immediately
 * (today.mjs, saved.mjs), and a judgement made here must NOT go out as a
 * standalone save or dismiss -- it rides in the POST body so the server can
 * mint one request_id naming the seed set as the render it was
 * (onboarding.py:474-478). The card is otherwise the same card, built from the
 * same format.mjs helpers, so the postings look like the ones on Today.
 *
 * NO SCORE, ANYWHERE, same as ui.jobCard: not match_score, not fit_score, and
 * reasonsFor() drops every delta because the deltas sum to match_score.
 * There is also no link off this card -- a Builder mid-onboarding who taps
 * through to a detail page loses the answers they have given so far, since
 * nothing is stored until Finish.
 */
export function seedCard(job) {
  const verdict = state.verdicts.get(job.id) || null;
  const age = ageLabel(job);
  const comp = compLabel(job);
  const place = placeLabel(job);
  const reasons = reasonsFor(job, 2);

  const meta = [
    `<li class="age${age.stale ? " is-old" : ""}${age.exact ? " is-exact" : ""}">${esc(age.text)}</li>`,
    place ? `<li>${esc(place)}</li>` : "",
    comp ? `<li>${esc(comp.text)}${comp.estimated
      ? ' <span class="estimated">estimated, not stated by the employer</span>'
      : ""}</li>` : "",
  ].join("");

  return `
<article class="card seed${verdict ? " is-judged" : ""}" data-job-id="${esc(job.id)}">
  <h3 class="card-title">${esc(job.title)}</h3>
  <p class="card-company">${esc(job.company_name)}</p>
  <ul class="meta">${meta}</ul>
  ${job.summary ? `<p class="angle from-posting">${esc(job.summary)}</p>` : ""}
  ${reasons.length
    ? `<ul class="chips">${reasons.map((r) => `<li class="chip">${esc(r)}</li>`).join("")}</ul>`
    : ""}
  <div class="actions">
    ${Object.entries(VERDICT_LABELS).map(([slug, text]) => `
      <button class="btn" type="button" data-verdict="${esc(slug)}"
              aria-pressed="${verdict === slug ? "true" : "false"}">${esc(text)}</button>`
    ).join("")}
  </div>
</article>`;
}

/** Never blank (32-frontend.md: "Empty states are seeded, never blank"). And
 *  this one is reachable: the crawl returns nothing for a Builder whose
 *  profile has no matched postings yet. */
function emptyState() {
  return `<div class="empty">
    <p><strong>There's nothing to show you yet.</strong></p>
    <p>The pipeline runs overnight, so postings appear in the morning. You can
       finish without this step — nothing here is required.</p>
    <button class="btn wide" type="button" data-act="finish">Finish</button>
  </div>`;
}

// --------------------------------------------------------------------------
// Behaviour
// --------------------------------------------------------------------------

/**
 * Turn raw form values into answers. Empty means null, never 0 and never "".
 *
 * A BLANK NUMBER IS NOT A ZERO. `comp_floor: 0` is a real answer meaning "no
 * floor" -- it is the bottom of the resolution merge and the reason
 * onboarding.DEFAULTS bottoms out at 0 rather than at None (onboarding.py:
 * 81-83) -- so coercing an empty box to 0 records a preference nobody
 * expressed, where NULL means nobody asked (schema_web.py:290-294).
 * `Number("")` is `0`, which is exactly how that bug gets written; every
 * conversion here goes through the empty check first.
 *
 * IT TAKES TWO ACCESSORS RATHER THAN A <form>, AND THAT IS NOT A CONCESSION TO
 * THE CHECKER. This is the only code in the file where a wrong answer is
 * SILENT: a 0 that should have been null passes validate_request(), stores
 * clean, and resolves through the merge as though a person chose it. Nothing
 * downstream can tell. So it is the part that most needs to be reachable
 * without a DOM, and `get`/`getAll` are FormData's own two methods, which
 * makes the browser wrapper below a one-liner rather than a translation layer.
 */
export function readAnswers(get, getAll) {
  const text = (name) => {
    const value = get(name);
    return value === null || value === undefined || String(value).trim() === ""
      ? null : String(value);
  };
  const int = (name) => {
    const value = text(name);
    if (value === null) return null;
    const n = Number.parseInt(value, 10);
    return Number.isFinite(n) && n >= 0 ? n : null;
  };
  return {
    prior_domain: text("prior_domain"),
    prior_years: int("prior_years"),
    situation: text("situation"),
    location_pref: text("location_pref"),
    remote_pref: text("remote_pref"),
    comp_floor: int("comp_floor"),
    // Always an array, never null: the Builder was shown the boxes, so "none
    // ticked" is an answer. NULL would say nobody asked, and `{}` versus NULL
    // is a distinction schema_web.py:303-307 draws on purpose.
    schedule_constraints: (getAll("schedule_constraints") || []).map(String),
  };
}

function readForm(form) {
  const data = new FormData(form);
  Object.assign(state.answers,
                readAnswers((n) => data.get(n), (n) => data.getAll(n)));
}

async function onFormSubmit(event, root) {
  event.preventDefault();
  readForm(event.target);
  state.screen = "seed";
  root.innerHTML = `${stepLabel()}<h1>A few real postings</h1>
    ${spinner("Finding some postings…")}`;
  await loadSeed();
  if (state.screen === "seed") paint(root);
}

async function onClick(event, root) {
  const verdictButton = event.target.closest("[data-verdict]");
  if (verdictButton) {
    event.preventDefault();
    const card = verdictButton.closest(".card");
    if (!card) return;
    const jobId = card.dataset.jobId;
    const chosen = verdictButton.dataset.verdict;
    // Tapping the answer you already gave takes it back. A Builder who cannot
    // undo an answer answers less, which is the same reasoning the dismiss
    // undo rests on.
    if (state.verdicts.get(jobId) === chosen) state.verdicts.delete(jobId);
    else state.verdicts.set(jobId, chosen);
    paint(root);
    return;
  }

  const button = event.target.closest("[data-act]");
  if (!button) return;

  if (button.dataset.act === "back") {
    event.preventDefault();
    state.screen = "form";
    paint(root);
    return;
  }

  if (button.dataset.act === "finish") {
    event.preventDefault();
    await finish(root);
  }
}

/**
 * Post it, then leave.
 *
 * THE OUTCOME IS A TOAST AND NOT A THIRD SCREEN, per the two-screen budget at
 * the top of this file. What it has to carry is the one case the endpoint
 * reports and does not fail on: record_events() silently drops judgements for
 * postings outside this profile's match set, so `seed_judgements_recorded` can
 * legitimately be lower than what was sent (onboarding.py:594-602, which logs
 * it and deliberately does not 400 -- the form half has already landed and a
 * retry would re-write the judgements that did work). Saying nothing would be
 * this system's failure mode; failing would be worse than the discrepancy.
 */
async function finish(root) {
  if (state.submitting) return;
  state.submitting = true;
  paint(root);

  const sent = state.verdicts.size;
  try {
    const body = await postOnboarding(buildRequest(state.answers, state.verdicts));
    const recorded = body.seed_judgements_recorded ?? 0;
    const message = recorded < sent
      ? `You're set. ${recorded} of ${sent} postings were recorded — the rest `
        + `aren't on your list any more.`
      : "You're set. Here's your list.";
    location.hash = "#/today";
    // AFTER the hashchange, not before it. A hash assignment queues its event
    // as a separate task, so app.mjs's route() -- which opens with
    // hideToast() -- runs strictly after this function returns. Toasting
    // inline would show the message and have it wiped a tick later, which is
    // the one case where the Builder needed to read it: a recorded count lower
    // than what they answered.
    setTimeout(() => toast(message), 0);
  } catch (e) {
    state.submitting = false;
    paint(root);
    // A 400 here is a contract violation with a machine code -- an unknown
    // vocabulary value, a duplicate judgement, or a session naming a profile
    // that has no `profiles` row (onboarding.py:316-365, :577-582). The code
    // is shown because it is the only thing that makes such a report
    // actionable, which is errorBlock()'s existing rule.
    root.insertAdjacentHTML("afterbegin", errorBlock(e, "#/onboarding"));
    console.error(e);
  }
}
