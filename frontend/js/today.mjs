// Today: the daily list, grouped by track.
//
// ONE RENDER, MANY PAGES. The first call has no cursor and starts a render;
// "Show more" passes next_cursor, which carries the same request_id and the
// next rank (backend/webapp/jobs.py:210-232). So `state.requestId` is set once
// and every event from this screen echoes it, including events raised from
// rows that arrived on page three.
//
// ORDER IS THE SERVER'S. The rows come back in match_score order
// (jobs.py:141) and nothing here re-sorts them by fit_score -- that would put
// an LLM call on the critical path for every posting, which .claude/CLAUDE.md
// states as an invariant in three separate files. Grouping changes which
// heading a row sits under; it never changes which row is above which.

import { listJobs } from "./api.mjs";
import { groupByTrack, CAVEAT, UNTRACKED } from "./tracks.mjs";
import { observe, sendAction, stopObserving } from "./events.mjs";
import { remember } from "./renders.mjs";
import { jobCard, askReason, toast, paintSaved, errorBlock, spinner } from "./ui.mjs";
import { esc } from "./format.mjs";

/** One page. Small enough that the first screen paints fast, large enough
 *  that a Builder on a phone is not tapping "Show more" every ten seconds. */
const PAGE = 25;

const state = { requestId: null, cursor: null, jobs: [], loading: false };

/** Returns a teardown. app.js calls it before routing anywhere else, so the
 *  delegated handler and the IntersectionObserver do not outlive the screen. */
export async function show(root) {
  state.requestId = null;
  state.cursor = null;
  state.jobs = [];
  root.innerHTML = `<h1>Today</h1>${spinner("Finding your postings…")}`;

  const handler = (event) => onClick(event, root);
  root.addEventListener("click", handler);
  const teardown = () => {
    root.removeEventListener("click", handler);
    stopObserving();
  };

  try {
    await loadPage();
  } catch (e) {
    root.innerHTML = `<h1>Today</h1>${errorBlock(e)}`;
    return teardown;
  }
  paint(root);
  return teardown;
}

async function loadPage() {
  state.loading = true;
  try {
    const body = await listJobs({ limit: PAGE, cursor: state.cursor });
    // The render id comes from the first page and never changes; a later page
    // returns the same one because it rode inside the cursor.
    state.requestId = body.request_id;
    state.cursor = body.next_cursor;
    state.jobs.push(...body.jobs);
    remember(body.request_id, body.jobs);
  } finally {
    state.loading = false;
  }
}

function paint(root) {
  stopObserving();
  const groups = groupByTrack(state.jobs);

  if (state.jobs.length === 0) {
    root.innerHTML = `<h1>Today</h1>${emptyState()}`;
    return;
  }

  // ONE GROUP AND IT IS THE FALLBACK: render no headings at all. A single
  // heading reading "Everything else" over the entire list is noise that
  // claims a grouping exists. This is the state the client is in today --
  // see tracks.js on why every row resolves to UNTRACKED.
  const bare = groups.length === 1 && groups[0].track === UNTRACKED;

  root.innerHTML = `
    <h1>Today</h1>
    <p class="lede">${state.jobs.length} posting${state.jobs.length === 1 ? "" : "s"} for you, strongest first.</p>
    ${groups.map((group) => renderGroup(group, bare)).join("")}
    ${state.cursor
      ? `<button class="btn wide" type="button" data-act="more">Show more</button>`
      : `<p class="muted small">That's everything for now. New postings arrive overnight.</p>`}
  `;

  for (const card of root.querySelectorAll(".card")) {
    const rank = Number(card.dataset.rank);
    if (Number.isFinite(rank)) {
      observe(card, state.requestId, card.dataset.jobId, rank);
    }
  }
}

function renderGroup(group, bare) {
  const head = bare ? "" : `
    <div class="group-head">
      <h2>${esc(group.label)}</h2>
      ${group.blurb ? `<p class="blurb">${esc(group.blurb)}</p>` : ""}
      <p class="group-caveat">${esc(CAVEAT)}</p>
    </div>`;
  return `<section class="group">${head}${group.jobs.map(jobCard).join("")}</section>`;
}

/** Never blank. 32-frontend.md: "Empty states are seeded, never blank." */
function emptyState() {
  return `<div class="empty">
    <p><strong>Nothing new right now.</strong></p>
    <p>The pipeline runs overnight, so this fills up in the morning. Postings you
       have already turned down stay hidden — that is why the list gets shorter
       as you use it.</p>
    <p><a href="#/saved">Look at what you saved</a></p>
  </div>`;
}

async function onClick(event, root) {
  const more = event.target.closest('[data-act="more"]');
  if (more) {
    event.preventDefault();
    more.disabled = true;
    more.textContent = "Loading…";
    try {
      await loadPage();
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
  const card = button.closest(".card");
  if (!card) return;
  const jobId = card.dataset.jobId;
  const job = state.jobs.find((j) => j.id === jobId);
  if (!job) return;
  event.preventDefault();

  if (button.dataset.act === "save") return toggleSave(job, root);
  if (button.dataset.act === "dismiss") return dismiss(job, root);
}

/** save / unsave. Optimistic: the state row is written server-side in the same
 *  transaction as the event (jobs.py:1017-1018), so the only way this diverges
 *  is a refused batch, which surfaces as a toast from app.js's error handler. */
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
 * Dismiss, with a reason, with an undo.
 *
 * The card leaves the list because the list hides dismissals by default
 * (jobs.py:458-459) and a card that stayed put would be lying about what a
 * refresh will show. The undo sends `undismiss`, which takes NO reason -- one
 * there is a 400 with code `reason_not_allowed` (jobs.py:694-699), because the
 * reason belongs to the dismissal being reversed and is already on that row.
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
      paint(root);
      await sendAction(state.requestId, { event: "undismiss", job_id: job.id });
      toast("Put back.");
    },
  });
}
