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

import { me, getOnboarding, logout, loginUrl, ApiError } from "./api.mjs";
import { setErrorHandler, flush, stopObserving } from "./events.mjs";
import { toast, hideToast, errorBlock } from "./ui.mjs";
import { esc } from "./format.mjs";
import * as today from "./today.mjs";
import * as saved from "./saved.mjs";
import * as detail from "./detail.mjs";
import * as onboarding from "./onboarding.mjs";

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
  // If it redirected, the hashchange it caused does the routing. Calling
  // route() here as well would render the screen twice and fetch its data
  // twice, because a hash assignment queues hashchange as its own task rather
  // than dispatching it inline.
  if (await sendFirstRunToOnboarding()) return;
  route();
}

/**
 * A Builder who has never onboarded lands on the form instead of the list.
 *
 * THIS IS TASK 26's FIRST DONE BULLET, on the client side: "a Builder signs in
 * with Google and reaches a ranked list without any manual DB work". The row
 * that used to need a CLI is a builder_profiles row, and this is the only
 * thing on the page that puts a first-run Builder in front of the form that
 * creates it.
 *
 * IT IS A NUDGE, NOT A GATE, AND THAT IS DELIBERATE ON TWO COUNTS. It fires
 * only when the Builder did not ask for something specific -- an empty hash or
 * #/today -- so a deep link into a posting still resolves. And it never blocks
 * the list: every onboarding field is optional server-side, so a Builder who
 * skips it is a Builder with NULLs, which is the honest state and is exactly
 * what the nullable columns mean (schema_web.py:228-232). Gating the list on a
 * form would lose people at screen zero, in a population where
 * 26 § Onboarding says "every additional screen loses someone".
 *
 * A FAILED CHECK NEVER COSTS ANYONE THEIR LIST. If GET /v1/onboarding is down
 * or refuses, this logs and routes normally. The failure mode of an onboarding
 * probe must not be "nobody can see any postings".
 *
 * Returns true when it redirected, so boot() can leave the routing to the
 * hashchange rather than doing it twice.
 */
async function sendFirstRunToOnboarding() {
  const hash = location.hash.replace(/^#/, "");
  if (hash && hash !== "/" && hash !== "/today") return false;
  try {
    const body = await getOnboarding();
    if (body && body.onboarding && !body.onboarding.completed) {
      location.hash = "#/onboarding";
      return true;
    }
  } catch (e) {
    console.warn("could not read onboarding state; going to the list", e);
  }
  return false;
}

// -- routing ---------------------------------------------------------------

/**
 * The routing table. ONE ENTRY PER SCREEN, and adding a screen is adding a row.
 *
 * WHY A TABLE AND NOT THE IF-CHAIN IT REPLACED. Three screens fit in an
 * if-chain; the surfaces table in tranche_six/32-frontend.md lists six, and
 * the chain had the route match in one function and the dispatch in another,
 * so a fourth screen meant editing two places that could disagree. A row here
 * carries `name` (which is also the `data-tab` value markTab looks for),
 * `pattern`, and `show`, which returns the screen's teardown.
 *
 * ORDER MATTERS: first match wins, so `/job/:id` sits above the prefix
 * patterns. The last row is the fallback and its pattern must match anything.
 *
 * TO ADD Search (task 25's screen, which has no route and no table yet): write
 * js/search.mjs exporting `show(root)`, import it, add
 * `{ name: "search", pattern: /^\/search/, show: (root) => search.show(root) }`
 * above the fallback, and add one <a data-tab="search"> to index.html. Nothing
 * else in this file changes.
 */
const ROUTES = [
  {
    name: "job",
    pattern: /^\/job\/(.+)$/,
    show: (root, match) => detail.show(root, decodeURIComponent(match[1])),
  },
  { name: "saved", pattern: /^\/saved/, show: (root) => saved.show(root) },
  {
    name: "onboarding",
    pattern: /^\/onboarding/,
    show: (root) => onboarding.show(root),
  },
  // The fallback. Anything unrecognised is Today rather than a 404 screen: a
  // hash this client does not know is a stale bookmark, and the list is a
  // better answer to one than an error is.
  { name: "today", pattern: /^.*$/, show: (root) => today.show(root) },
];

function currentRoute() {
  const hash = location.hash.replace(/^#/, "") || "/today";
  for (const entry of ROUTES) {
    const match = hash.match(entry.pattern);
    if (match) return { ...entry, match };
  }
  return null;   // unreachable: the last pattern matches everything.
}

async function route() {
  hideToast();
  teardown();
  teardown = () => {};
  stopObserving();

  const target = currentRoute();
  markTab(target.name);
  try {
    teardown = await target.show(view, target.match);
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
