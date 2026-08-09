// Shared rendering: the job card, the toast, the dismiss reason sheet.
//
// Today and Saved render the same card and offer the same two actions, so it
// lives here once. Every string that reaches innerHTML goes through esc() --
// titles and company names are third-party strings off a job board.

import { esc, ageLabel, compLabel, placeLabel, reasonsFor, DISMISS_REASONS }
  from "./format.mjs";

/**
 * One posting, as a card.
 *
 * NO SCORE, ANYWHERE. Not match_score, not fit_score, not a delta out of
 * match_reasons. What carries the claim instead is `gap_bridging_angle` --
 * 32-frontend.md § "Show the reasoning, not the number": the transferable-
 * skills story is what makes a posting legible to a career changer, and the
 * bucket that does not exist yet would only ever have been a label on it.
 *
 * AN UNSCORED POSTING IS NORMAL AND IS RENDERED ANYWAY. jobs_app LEFT JOINs
 * job_scores (backend/schema.py:818) and scoring is budget-limited, so
 * fit_score, primary_track, gap_bridging_angle, risk_factors and
 * key_technologies are null together on a posting the nightly run has not
 * reached. The card falls back to `summary`, labelled as the posting's own
 * words rather than as a fit story, because those are different claims.
 */
export function jobCard(job) {
  const age = ageLabel(job);
  const comp = compLabel(job);
  const place = placeLabel(job);
  const reasons = reasonsFor(job);
  const angle = job.gap_bridging_angle;

  const meta = [
    `<li class="age${age.stale ? " is-old" : ""}">${esc(age.text)}</li>`,
    place ? `<li>${esc(place)}</li>` : "",
    comp
      ? `<li>${esc(comp.text)}${comp.estimated
          ? ' <span class="estimated">estimated, not stated by the employer</span>'
          : ""}</li>`
      : `<li class="muted">No pay stated</li>`,
  ].join("");

  // WHEN THERE IS NO FIT STORY, THE SUMMARY IS THE CARD, not a footnote. This
  // was styled faint and italic until it was rendered against the live
  // database, back when `gap_bridging_angle` was null on every row -- scoring
  // was budget-limited and this profile had no scores yet. That changed
  // 2026-08-05: the budget went nonzero and most of the shortlist now has a
  // narrative, so this fallback renders only for the unscored remainder, not
  // every card. De-emphasising the only text on the card made the whole list
  // look broken when this was written, and nothing about that argument
  // depended on the count being 100% -- it still applies to whichever cards
  // fall back. The ::before marker is what keeps the two claims apart: one is
  // a fit story written for this Builder, the other is the posting describing
  // itself.
  const body = angle
    ? `<p class="angle">${esc(angle)}</p>`
    : job.summary
      ? `<p class="angle from-posting">${esc(job.summary)}</p>`
      : "";

  const chips = reasons.length
    ? `<ul class="chips">${reasons.map((r) => `<li class="chip">${esc(r)}</li>`).join("")}</ul>`
    : "";

  return `
<article class="card${job.dismissed ? " is-dismissed" : ""}" data-job-id="${esc(job.id)}" data-rank="${esc(job.rank ?? "")}">
  <a class="card-link" href="#/job/${encodeURIComponent(job.id)}">
    <h3 class="card-title">${esc(job.title)}</h3>
    <p class="card-company">${esc(job.company_name)}</p>
    <ul class="meta">${meta}</ul>
    ${body}
    ${chips}
  </a>
  <div class="actions">
    <button class="btn" type="button" data-act="save" aria-pressed="${job.saved ? "true" : "false"}">
      ${job.saved ? "Saved" : "Save"}
    </button>
    <button class="btn" type="button" data-act="dismiss">Not for me</button>
  </div>
</article>`;
}

/** Flip a card's Save button without re-rendering the list. */
export function paintSaved(root, jobId, saved) {
  const button = root.querySelector(
    `[data-job-id="${cssEscape(jobId)}"] [data-act="save"]`);
  if (!button) return;
  button.setAttribute("aria-pressed", saved ? "true" : "false");
  button.textContent = saved ? "Saved" : "Save";
}

function cssEscape(value) {
  return (window.CSS && CSS.escape) ? CSS.escape(value)
    : String(value).replace(/[^\w-]/g, "\\$&");
}

// -- toast -----------------------------------------------------------------

let toastTimer = null;

/**
 * A short message, optionally with one undo.
 *
 * The undo is the whole reason a dismiss is a single tap: a Builder who has to
 * be sure before acting acts less, and the dismissal is the signal this list
 * gets better from.
 */
export function toast(message, undo = null, ms = 6000) {
  const el = document.getElementById("toast");
  el.innerHTML = `<span></span>`;
  el.firstChild.textContent = message;
  if (undo) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = undo.label || "Undo";
    button.addEventListener("click", () => { hideToast(); undo.run(); });
    el.appendChild(button);
  }
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(hideToast, ms);
}

export function hideToast() {
  clearTimeout(toastTimer);
  const el = document.getElementById("toast");
  el.hidden = true;
  el.innerHTML = "";
}

// -- dismiss reason sheet --------------------------------------------------

/**
 * Ask why. Resolves to a reason slug, `null` for "skip the question", or
 * `undefined` for "never mind, keep it".
 *
 * SKIPPABLE ON PURPOSE. 32-frontend.md: "A dismiss with `other` is still worth
 * more than a dismiss the Builder abandoned because the form was tedious." The
 * skip resolves to null, and the caller sends a `dismiss` with no reason at
 * all -- which is legal (jobs.py:694, reason is only validated when present)
 * and honest, where a silently substituted `other` would be a made-up answer.
 */
export function askReason() {
  const backdrop = document.getElementById("reason-sheet");
  const list = document.getElementById("reason-list");
  list.innerHTML = DISMISS_REASONS
    .map(([slug, text]) =>
      `<button class="btn" type="button" data-reason="${esc(slug)}">${esc(text)}</button>`)
    .join("");

  return new Promise((resolve) => {
    function finish(value) {
      backdrop.hidden = true;
      backdrop.removeEventListener("click", onClick);
      document.removeEventListener("keydown", onKey);
      resolve(value);
    }
    function onClick(event) {
      const chosen = event.target.closest("[data-reason]");
      if (chosen) return finish(chosen.dataset.reason);
      if (event.target.closest("[data-reason-skip]")) return finish(null);
      if (event.target.closest("[data-reason-cancel]") || event.target === backdrop) {
        return finish(undefined);
      }
    }
    function onKey(event) {
      if (event.key === "Escape") finish(undefined);
    }
    backdrop.hidden = false;
    backdrop.addEventListener("click", onClick);
    document.addEventListener("keydown", onKey);
    list.querySelector("button")?.focus();
  });
}

// -- generic blocks --------------------------------------------------------

export function errorBlock(error, retryHref = "#/today") {
  const code = error && error.code ? ` <code>${esc(error.code)}</code>` : "";
  return `<div class="error">
    <p><strong>Something went wrong.</strong>${code}</p>
    <p class="muted">${esc(error && error.message ? error.message : String(error))}</p>
    <p><a href="${esc(retryHref)}">Try again</a></p>
  </div>`;
}

export function spinner(text = "Loading…") {
  return `<p class="muted">${esc(text)}</p>`;
}
