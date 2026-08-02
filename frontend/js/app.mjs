// Boot, sign-in, and the router.
//
// SIGN-IN IS NOT REIMPLEMENTED HERE. backend/webapp/auth.py drives the whole
// OAuth 2.0 + PKCE flow server-side; the browser never receives a token, only
// an httpOnly session cookie whose sha256 is what the database stores. So the
// entire client half of authentication is: call GET /v1/me, and on a 401 send
// the browser to /v1/auth/login. There is no Google SDK on this page and there
// must not be -- auth.py's module docstring says in terms that the
// frontend-GIS variant of the flow needs full JWKS signature verification that
// this backend deliberately does not do.
//
// HASH ROUTES, so there is no server-side rewrite to configure and a deep link
// survives a reload without the API process needing a catch-all route.

import { me, logout, loginUrl, ApiError } from "./api.mjs";
import { setErrorHandler, flush, stopObserving } from "./events.mjs";
import { toast, hideToast, errorBlock } from "./ui.mjs";
import { esc } from "./format.mjs";
import * as today from "./today.mjs";
import * as saved from "./saved.mjs";
import * as detail from "./detail.mjs";

const view = document.getElementById("view");
const topbar = document.getElementById("topbar");

/** Torn down before the next screen paints, so a delegated click handler or an
 *  IntersectionObserver never outlives the list it belongs to. */
let teardown = () => {};
let user = null;

async function boot() {
  setErrorHandler(onEventError);
  document.getElementById("signout").addEventListener("click", signOut);
  addEventListener("hashchange", route);

  try {
    user = await me();
  } catch (e) {
    return showSignIn(e);
  }
  topbar.hidden = false;
  route();
}

// -- routing ---------------------------------------------------------------

function currentRoute() {
  const hash = location.hash.replace(/^#/, "") || "/today";
  const job = hash.match(/^\/job\/(.+)$/);
  if (job) return { name: "job", id: decodeURIComponent(job[1]) };
  if (hash.startsWith("/saved")) return { name: "saved" };
  return { name: "today" };
}

async function route() {
  hideToast();
  teardown();
  teardown = () => {};
  stopObserving();

  const target = currentRoute();
  markTab(target.name);
  try {
    if (target.name === "job") teardown = await detail.show(view, target.id);
    else if (target.name === "saved") teardown = await saved.show(view);
    else teardown = await today.show(view);
  } catch (e) {
    if (e instanceof ApiError && (e.isAuth || e.isForbidden)) return showSignIn(e);
    view.innerHTML = errorBlock(e);
    console.error(e);
  }
}

function markTab(name) {
  for (const link of topbar.querySelectorAll("[data-tab]")) {
    if (link.dataset.tab === name) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
}

// -- sign-in ---------------------------------------------------------------

function showSignIn(error) {
  topbar.hidden = true;
  // A 403 is "you are who you say you are and you are not on the allowlist"
  // (auth.py:117, :391-398). Sending that person round the login loop again
  // would be a dead end, so it gets its own screen.
  if (error instanceof ApiError && error.isForbidden) {
    view.innerHTML = `<div class="signin">
      <h1>This account isn't set up yet</h1>
      <p class="muted">${esc(error.message)}</p>
      <p class="muted small">Ask whoever runs the cohort to add your address.</p>
    </div>`;
    return;
  }
  const next = location.hash ? `/${location.hash}` : "/";
  view.innerHTML = `<div class="signin">
    <h1>Jobs</h1>
    <p class="muted">Entry-level, AI-adjacent roles in New York, picked for the cohort.</p>
    <a class="btn primary" href="${esc(loginUrl(next))}">Sign in with Google</a>
  </div>`;
}

async function signOut() {
  await flush();
  try {
    await logout();
  } catch (e) {
    console.warn("logout failed", e);
  }
  user = null;
  location.hash = "";
  showSignIn(null);
}

// -- event-loop failures ---------------------------------------------------

/**
 * A refused event batch.
 *
 * Every contract violation fails the WHOLE batch (jobs.py:503-512), so this is
 * loud rather than swallowed: silence is this system's documented failure mode
 * and a client that drops its own telemetry quietly is the same bug in a new
 * place. The codes worth naming to a person are the two that mean the client
 * is wrong about the vocabulary; the rest get the server's own message.
 */
function onEventError(error) {
  if (error.isAuth) return showSignIn(error);
  const known = {
    missing_request_id: "Lost track of this list. Reload to fix it.",
    missing_rank: "Lost track of this list. Reload to fix it.",
    unknown_event: "This app sent something the server does not accept.",
    server_derived_event: "This app sent something the server derives itself.",
    unknown_reason: "That reason isn't one the server knows.",
    reason_not_allowed: "That reason doesn't belong on that action.",
    dwell_not_allowed: "This app attached a reading time to the wrong action.",
  }[error.code];
  toast(known || `Couldn't record that: ${error.message}`);
}

boot();
