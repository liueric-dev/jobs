// Saved: the postings this Builder kept.
//
// THERE IS NO ENDPOINT FOR THIS AND THAT IS THE WHOLE STORY OF THIS FILE.
// GET /v1/jobs takes eight query parameters -- limit, cursor, q, remote, nyc,
// min_score, since, include_dismissed (backend/webapp/jobs.py:412-420) -- and
// not one of them filters on state. `saved` is a per-row boolean resolved from
// builder_job_state at read time (jobs.py:332-343), so the only way to ask
// "what did I save" is to read every row and filter here. Recorded in
// frontend/README.md; it is a one-parameter backend change and this client
// does not own that file.
//
// THE CRAWL IS CHEAP TODAY AND WILL NOT ALWAYS BE. jobs_app holds 166 rows for
// the `pursuit` profile (measured 2026-08-02), so at the endpoint's MAX_LIMIT
// of 100 (jobs.py:40) this is two requests. MAX_PAGES caps it so that the day
// the corpus is ten times larger this degrades into a truncated list with a
// visible message rather than into thirty silent requests.
//
// THE CRAWL IS ONE RENDER, AND IT EMITS NO IMPRESSIONS. Following next_cursor
// continues the render page one started, so ranks run 1..N across the whole
// crawl and every event from this screen echoes that pair honestly. But an
// impression means "this row was examined", and the Builder never saw the rows
// this crawl filtered out. Emitting none also keeps derive_skips inert here:
// it reads impressions belonging to the render being opened from
// (jobs.py:895-899), finds none, and writes no skip rows -- so browsing Saved
// cannot fabricate negatives for postings nobody was shown.

import { sendAction } from "./events.mjs";
import { crawlAll, CRAWL_LIMIT, MAX_PAGES } from "./crawl.mjs";
import { jobCard, askReason, toast, paintSaved, errorBlock, spinner } from "./ui.mjs";

const state = { requestId: null, jobs: [], truncated: false };

export async function show(root) {
  state.requestId = null;
  state.jobs = [];
  state.truncated = false;
  root.innerHTML = `<h1>Saved</h1>${spinner("Looking through your postings…")}`;

  const handler = (event) => onClick(event, root);
  root.addEventListener("click", handler);
  const teardown = () => root.removeEventListener("click", handler);

  try {
    await crawl();
  } catch (e) {
    root.innerHTML = `<h1>Saved</h1>${errorBlock(e, "#/saved")}`;
    return teardown;
  }
  paint(root);
  return teardown;
}

async function crawl() {
  const { requestId, jobs, truncated } = await crawlAll();
  state.requestId = requestId;
  state.jobs = jobs.filter((job) => job.saved);
  state.truncated = truncated;
}

function paint(root) {
  if (state.jobs.length === 0) {
    root.innerHTML = `<h1>Saved</h1>${emptyState()}`;
    return;
  }
  // Rank order, which is the order Today showed them in. No grouping: a saved
  // list is short and already chosen, so headings would be noise.
  const jobs = [...state.jobs].sort((a, b) => a.rank - b.rank);
  root.innerHTML = `
    <h1>Saved</h1>
    <p class="lede">${jobs.length} posting${jobs.length === 1 ? "" : "s"} you kept.</p>
    ${jobs.map(jobCard).join("")}
    ${state.truncated
      ? `<p class="muted small">This list stops after ${CRAWL_LIMIT * MAX_PAGES} postings.
         Anything you saved beyond that is not shown here.</p>`
      : ""}
  `;
}

/** Never blank. */
function emptyState() {
  return `<div class="empty">
    <p><strong>Nothing saved yet.</strong></p>
    <p>Tap <em>Save</em> on anything you want to come back to. Saved postings stay
       here even after they drop off Today.</p>
    <p><a href="#/today">Go to today's postings</a></p>
  </div>`;
}

async function onClick(event, root) {
  const button = event.target.closest("[data-act]");
  if (!button) return;
  const card = button.closest(".card");
  if (!card) return;
  const job = state.jobs.find((j) => j.id === card.dataset.jobId);
  if (!job) return;
  event.preventDefault();

  if (button.dataset.act === "save") {
    // On this screen the button is always an unsave to begin with, but the
    // toggle is written generically so an undo can put it back.
    job.saved = !job.saved;
    paintSaved(root, job.id, job.saved);
    await sendAction(state.requestId, {
      event: job.saved ? "save" : "unsave", job_id: job.id, rank: job.rank,
    });
    if (!job.saved) {
      state.jobs = state.jobs.filter((j) => j.id !== job.id);
      paint(root);
      toast("Removed from saved.", {
        label: "Undo",
        run: async () => {
          job.saved = true;
          state.jobs.push(job);
          paint(root);
          await sendAction(state.requestId,
                           { event: "save", job_id: job.id, rank: job.rank });
        },
      });
    }
    return;
  }

  if (button.dataset.act === "dismiss") {
    const reason = await askReason();
    if (reason === undefined) return;
    state.jobs = state.jobs.filter((j) => j.id !== job.id);
    paint(root);
    await sendAction(state.requestId, {
      event: "dismiss", job_id: job.id, rank: job.rank, reason: reason ?? undefined,
    });
    toast("Hidden.", {
      label: "Undo",
      run: async () => {
        state.jobs.push(job);
        paint(root);
        await sendAction(state.requestId, { event: "undismiss", job_id: job.id });
      },
    });
  }
}
