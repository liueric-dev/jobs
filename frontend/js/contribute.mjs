// Contribute: get the token the Apify actor carries (docs/adr/0012).
//
// NOTHING IS FETCHED ON SHOW, on purpose. The only call this screen makes is
// the mint, and every mint revokes the previous token. So opening the tab must
// never call it; only the button does, and it asks first.
//
// THE TOKEN IS SHOWN ONCE AND KEPT NOWHERE. api/ stores only its hash and
// contribute.py keeps nothing, so it lives in this screen's DOM until the
// Builder navigates away. It is not put in localStorage, a URL or a log.

import { optIn } from "./api.mjs";
import { esc } from "./format.mjs";
import { errorBlock, toast } from "./ui.mjs";

const ACTOR_HELP = [
  "In Apify Console, open the actor shared with you: <strong>Pursuit jobs: Google Jobs contributor</strong>.",
  "Paste the token into <strong>Jobs API token</strong>, leave the rest as is, and click <strong>Save &amp; Start</strong> once to check it works.",
  "Add a daily <strong>Schedule</strong> for it. One search a day costs about $0.15 of your own Apify credit, so it stays inside the free plan.",
];

export async function show(root) {
  root.innerHTML = page();
  const handler = (event) => onClick(event, root);
  root.addEventListener("click", handler);
  return () => root.removeEventListener("click", handler);
}

function page() {
  return `<h1>Contribute</h1>
  <p>Help find postings for the whole cohort. You run a small Apify actor on a
  schedule in your own Apify account. It asks this site which Google Jobs searches
  are due, runs them, and sends the results back.</p>
  <ol class="small">${ACTOR_HELP.map((step) => `<li>${step}</li>`).join("")}</ol>
  <div id="token-slot">
    <button class="btn primary" type="button" data-get-token>Get actor token</button>
    <p class="muted small">Getting a token replaces the one you had. Any actor still
    using the old one stops working until you paste in the new one.</p>
  </div>`;
}

async function onClick(event, root) {
  if (event.target.closest("[data-copy-token]")) {
    const value = root.querySelector("[data-token]")?.value ?? "";
    try {
      await navigator.clipboard.writeText(value);
      toast("Token copied.");
    } catch {
      // The clipboard API needs a secure context and permission. The field
      // stays selectable either way, so copying by hand still works.
      toast("Couldn't copy. Select the token and copy it yourself.");
    }
    return;
  }

  const button = event.target.closest("[data-get-token]");
  if (!button) return;
  if (button.dataset.confirmed !== "1") {
    // Asking inline rather than with window.confirm(). The rest of the client
    // never uses a blocking dialog, and a second tap on the same place is
    // just as deliberate.
    button.dataset.confirmed = "1";
    button.textContent = "Tap again to replace any existing token";
    return;
  }

  button.disabled = true;
  button.textContent = "Getting your token…";
  const slot = root.querySelector("#token-slot");
  try {
    const body = await optIn();
    slot.innerHTML = tokenBlock(body.actor_token);
  } catch (e) {
    slot.innerHTML = errorBlock(e, "#/contribute");
  }
}

export function tokenBlock(token) {
  return `<label class="small" for="actor-token"><strong>Your actor token</strong>. It is
  shown only this once. Copy it now.</label>
  <input id="actor-token" class="token" type="text" readonly spellcheck="false"
    autocomplete="off" value="${esc(token)}" data-token>
  <button class="btn" type="button" data-copy-token>Copy</button>`;
}
