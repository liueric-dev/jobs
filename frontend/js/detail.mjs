// Job detail: the full posting, and the place an application is recorded.
//
// REQUESTING THIS IS NOT AN IMPRESSION (API-CONTRACT-v1.md § GET /v1/jobs/{id},
// and nothing server-side writes one). What it emits is `open`, with `dwell_ms`,
// ON EXIT -- which is also what makes the skip derivation work: the server
// treats every un-actioned impression above this rank in the same render as
// passed over (backend/webapp/jobs.py:772-781).
//
// `open` REQUIRES A RANK (RANK_REQUIRED_EVENTS, jobs.py:91), so a detail page
// reached with no render context -- a reload on #/job/<id>, a pasted link --
// emits NOTHING. See renders.js for why inventing a rank is the worse of the
// two options.
//
// A DISMISSED POSTING IS SERVED HERE ON PURPOSE (jobs.py:583-588). The list
// hides it; this does not, because the undo has to be reachable. That is what
// the banner at the top of a dismissed posting is for.

import { getJob } from "./api.mjs";
import { sendAction } from "./events.mjs";
import { contextFor, resolve } from "./renders.mjs";
import { toast, errorBlock, spinner } from "./ui.mjs";
import { esc, ageLabel, compLabel, placeLabel } from "./format.mjs";

export async function show(root, jobId) {
  root.innerHTML = spinner("Loading the posting…");

  let job;
  try {
    job = await getJob(jobId);
  } catch (e) {
    root.innerHTML = `<a class="back" href="#/today">← Back</a>` +
      (e.isMissing
        ? `<div class="error"><p><strong>That posting isn't on your list.</strong></p>
           <p class="muted">It may have closed, or it may belong to a different
           profile.</p><p><a href="#/today">Back to today</a></p></div>`
        : errorBlock(e));
    return () => {};
  }

  // A mutable holder rather than a value: the page paints immediately, and a
  // cold deep link resolves its render context in the background (renders.js
  // renders a real list to obtain a real request_id). Every handler and the
  // exit `open` read it at the moment they fire.
  const ctx = { value: contextFor(job.id) };
  if (!ctx.value) resolve(job.id).then((found) => { ctx.value = found; });

  const openedAt = Date.now();
  let openSent = false;

  /** The `open`, once, on the way out. */
  function sendOpen() {
    if (openSent) return;
    openSent = true;
    // `open` is one of the two events refused without a rank (jobs.py:91). No
    // rank means no position in any render, and a fabricated one is worse in
    // the training data than a missing open, which is merely absent.
    if (!ctx.value || ctx.value.rank == null) {
      console.info(`no rank for ${job.id}; not emitting open`);
      return;
    }
    sendAction(ctx.value.requestId, {
      event: "open",
      job_id: job.id,
      rank: ctx.value.rank,
      dwell_ms: Date.now() - openedAt,
    });
  }

  paint(root, job);

  const handler = (event) => onClick(event, root, job, ctx);
  root.addEventListener("click", handler);
  addEventListener("pagehide", sendOpen);

  return () => {
    root.removeEventListener("click", handler);
    removeEventListener("pagehide", sendOpen);
    sendOpen();
  };
}

function paint(root, job) {
  const age = ageLabel(job);
  const comp = compLabel(job);
  const place = placeLabel(job);
  const risks = Array.isArray(job.risk_factors) ? job.risk_factors : [];
  const tech = Array.isArray(job.key_technologies) ? job.key_technologies
    : Array.isArray(job.tech_stack) ? job.tech_stack : [];

  root.innerHTML = `
    <a class="back" href="#/today">← Back</a>

    ${job.dismissed ? dismissedBanner(job) : ""}

    <h1>${esc(job.title)}</h1>
    <p class="card-company">${esc(job.company_name)}</p>

    <ul class="meta">
      <li class="age${age.stale ? " is-old" : ""}${age.exact ? " is-exact" : ""}">${esc(age.text)}</li>
      ${place ? `<li>${esc(place)}</li>` : ""}
      ${comp
        ? `<li>${esc(comp.text)}${comp.estimated
            ? ' <span class="estimated">estimated, not stated by the employer</span>'
            : ""}</li>`
        : `<li class="muted">No pay stated</li>`}
      ${job.employment_type && job.employment_type !== "unknown"
        ? `<li>${esc(job.employment_type.replace(/_/g, " "))}</li>` : ""}
    </ul>

    ${job.gap_bridging_angle ? `
      <section class="detail-block">
        <h2>Why this could work for you</h2>
        <p>${esc(job.gap_bridging_angle)}</p>
      </section>` : `
      <section class="detail-block">
        <p class="muted">We haven't written up how your background fits this one yet.
           Read the posting below and judge for yourself.</p>
      </section>`}

    ${cohortSignal(job)}

    ${risks.length ? `
      <section class="detail-block">
        <h2>Worth knowing before you apply</h2>
        <ul class="risks">${risks.map((r) => `<li>${esc(r)}</li>`).join("")}</ul>
      </section>` : ""}

    ${tech.length ? `
      <section class="detail-block">
        <h2>Tools named in the posting</h2>
        <ul class="chips">${tech.map((t) => `<li class="chip">${esc(t)}</li>`).join("")}</ul>
      </section>` : ""}

    ${job.description_text ? `
      <section class="detail-block">
        <h2>The posting</h2>
        <div class="description">${esc(job.description_text)}</div>
      </section>` : ""}

    <section class="detail-block">
      <h2>Where this came from</h2>
      <p class="muted small">
        ${esc(job.platform || "unknown source")}${job.first_seen
          ? ` · first seen ${esc(job.first_seen.slice(0, 10))}` : ""}
        ${job.visa_sponsorship === "not_offered"
          ? " · visa sponsorship not offered" : ""}
      </p>
    </section>

    <div class="detail-actions">
      <a class="btn primary" href="${esc(job.job_url)}" target="_blank"
         rel="noopener noreferrer" data-act="apply">Apply</a>
      <button class="btn" type="button" data-act="save"
              aria-pressed="${job.saved ? "true" : "false"}">${job.saved ? "Saved" : "Save"}</button>
      <button class="btn" type="button" data-act="applied" ${job.applied ? "disabled" : ""}>
        ${job.applied ? "Applied ✓" : "I applied"}
      </button>
    </div>
  `;
}

/**
 * "Other Builders saved this", when there are enough of them to say so.
 *
 * WRITTEN DEFENSIVELY BECAUSE THE FIELD IS LANDING WHILE THIS IS WRITTEN.
 * `cohort_signal` is task 28's and was absent from every response body when
 * this client was built; it is being added to the list and detail payloads by
 * another stream (`backend/webapp/jobs.py`, `cohort_signal(save_bucket)`,
 * returning `{save_bucket}` or null). So this renders it if it is there and
 * nothing at all if it is not, which is also the correct behaviour forever:
 * null is the answer for BOTH "nobody saved this" and "one or two Builders
 * did", and the suppression below three is a privacy control. Absence must not
 * be readable as "exactly one or two", so there is no "fewer than three" copy
 * here and there must never be.
 *
 * NEVER AN EXACT COUNT, NEVER A RECENCY, NEVER AN IDENTITY. The bucket string
 * is rendered as the bucket string. `computed_at` is deliberately not served
 * (`backend/schema.py`) because a per-posting timestamp that moves when the
 * underlying set moves hands back the recency channel the bucketing closes.
 *
 * "BUILDERS", NOT "OTHER BUILDERS", AND THE WORD MATTERS. The fold is
 * `COUNT(DISTINCT app_user_id)` across the whole cohort profile
 * (`backend/cohort.py:114`) — it counts everyone with a live save, INCLUDING
 * whoever is reading this page. "3-5 other Builders" would therefore be wrong
 * by one exactly when the reader is one of them, and wrong in the direction
 * that inflates the number. This is the same class of mistake as rendering
 * null as a zero: a true-sounding sentence the payload does not support.
 */
function cohortSignal(job) {
  const bucket = job.cohort_signal && job.cohort_signal.save_bucket;
  if (!bucket) return "";
  return `<section class="detail-block">
    <p class="banner"><strong>${esc(bucket)} Builders</strong> saved this posting.</p>
  </section>`;
}

function dismissedBanner(job) {
  return `<div class="banner">
    <p><strong>You hid this one.</strong>${job.dismiss_reason
      ? ` You said: ${esc(job.dismiss_reason.replace(/_/g, " "))}.` : ""}</p>
    <button class="btn" type="button" data-act="undismiss">Put it back on my list</button>
  </div>`;
}

async function onClick(event, root, job, ctx) {
  const target = event.target.closest("[data-act]");
  if (!target) return;
  const act = target.dataset.act;
  const requestId = ctx.value ? ctx.value.requestId : null;
  // undefined, not null: events.js strips absent fields, and a save or an
  // applied raised from a detail page legitimately has no position
  // (jobs.py:83-91). A null here would read as a claim about rank 0.
  const rank = ctx.value && ctx.value.rank != null ? ctx.value.rank : undefined;

  if (act === "apply") {
    // The link is NOT the event. Following it is not evidence of applying --
    // most of these open an ATS form the Builder may abandon. `applied` is
    // recorded only when they say so, which is what the toast asks.
    if (job.applied) return;
    toast("Did you finish the application?", {
      label: "Yes, I applied",
      run: () => markApplied(root, job, requestId, rank),
    }, 20000);
    return;
  }

  event.preventDefault();

  if (act === "save") {
    job.saved = !job.saved;
    target.setAttribute("aria-pressed", job.saved ? "true" : "false");
    target.textContent = job.saved ? "Saved" : "Save";
    // Rank is optional on a save and is omitted when this page was opened
    // cold: a detail page has no position in any render (jobs.py:83-91).
    await sendAction(requestId, {
      event: job.saved ? "save" : "unsave", job_id: job.id, rank,
    });
    toast(job.saved ? "Saved." : "Removed from saved.");
    return;
  }

  if (act === "applied") return markApplied(root, job, requestId, rank);

  if (act === "undismiss") {
    job.dismissed = false;
    job.dismiss_reason = null;
    await sendAction(requestId, { event: "undismiss", job_id: job.id });
    paint(root, job);
    toast("Back on your list.");
  }
}

/** `applied`, never `apply` (DEC-73). Sending `apply` is a 400 with code
 *  `unknown_event` -- jobs.py:52-53 is the closed vocabulary and the existing
 *  rows in job_events are the part of the disagreement that could not move.
 *
 *  There is no un-apply: CLIENT_EVENT_NAMES has no inverse for it, so the
 *  button is one-way and says so by going disabled. */
async function markApplied(root, job, requestId, rank) {
  if (job.applied) return;
  job.applied = true;
  const button = root.querySelector('[data-act="applied"]');
  if (button) { button.disabled = true; button.textContent = "Applied ✓"; }
  await sendAction(requestId, { event: "applied", job_id: job.id, rank });
  toast("Marked as applied. Good luck.");
}
