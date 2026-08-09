// Turning payload fields into something a person would say.
//
// NO 0-100 SCORE IS RENDERED ANYWHERE, and that is enforced here rather than
// remembered at each call site. The payload still carries `match_score` and
// `fit_score` because `bucket` does not exist -- it is task 30's, and task 30
// is blocked on task 29's labels -- so API-CONTRACT-v1.md's "no 0-100 score
// appears anywhere" is a rule the client honours that the API cannot yet
// express. reasonsFor() below drops every `delta` for exactly that reason: the
// deltas ARE the score, itemised.

/** Escape for interpolation into innerHTML. Everything here goes through it;
 *  company names and titles are third-party strings off a job board. */
export function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

// -- posting age -----------------------------------------------------------

/**
 * How old the posting is, and how sure we are of that.
 *
 * PROMINENT ON PURPOSE. 32-frontend.md § "Honest about the market": in a
 * market where the great majority of job seekers report hitting a ghost job,
 * age is the most reliable staleness signal available and it is actionable.
 *
 * TWO DIFFERENT DATES, LABELLED DIFFERENTLY. `posted_at_ts` is when the
 * employer says it went up and is null on plenty of rows -- Con Edison in the
 * fixtures is one (backend/schema.py:696, and jobs.py:140 coalesces it to
 * -infinity purely to sort). `first_seen` is when this pipeline first saw it,
 * which is an upper bound on the age and never the employer's claim. Showing
 * the second under the first's label would be a small lie in the one place
 * this screen asks to be trusted.
 */
export function postingAge(job, now = new Date()) {
  const posted = job.posted_at_ts ? new Date(job.posted_at_ts) : null;
  if (posted && !Number.isNaN(posted.getTime())) {
    return { days: daysBetween(posted, now), exact: true };
  }
  // first_seen is TEXT in '%Y-%m-%dT%H:%M:%S' with no zone (schema.py:353-354).
  const seen = job.first_seen ? new Date(`${job.first_seen}Z`) : null;
  if (seen && !Number.isNaN(seen.getTime())) {
    return { days: daysBetween(seen, now), exact: false };
  }
  return { days: null, exact: false };
}

function daysBetween(then, now) {
  return Math.max(0, Math.floor((now - then) / 86400000));
}

/** Old enough that it is worth saying so in a different colour. Chosen, not
 *  measured: there is no staleness measurement in this repo to cite, and a
 *  threshold presented as if there were would be worse than an honest guess. */
export const STALE_AFTER_DAYS = 30;

export function ageLabel(job, now = new Date()) {
  const { days, exact } = postingAge(job, now);
  if (days === null) return { text: "No date on this posting", stale: false };
  const when = days === 0 ? "today"
    : days === 1 ? "yesterday"
    : days < 7 ? `${days} days ago`
    : days < 14 ? "last week"
    : days < 60 ? `${Math.round(days / 7)} weeks ago`
    : `${Math.round(days / 30)} months ago`;
  return {
    text: exact ? `Posted ${when}` : `First seen ${when}`,
    stale: days >= STALE_AFTER_DAYS,
  };
}

// -- compensation ----------------------------------------------------------

/**
 * Pay, and whether the employer actually said it.
 *
 * `comp.is_estimated` IS IN THE CONTRACT AND IS IN NO RESPONSE BODY. The
 * contract requires it honoured (API-CONTRACT-v1.md § "comp.is_estimated"),
 * and the shipped payload has `salary`, `comp_min`, `comp_max` and
 * `comp_currency` and no provenance flag at all: `is_estimated` appears
 * nowhere in backend/schema.py, and the only mention in the tree is
 * `comp_is_estimated` in backend/evals/mock_corpus.py:101, which is a fixture
 * key. Adzuna, the source the contract names as predicting salary, is a stub
 * (backend/tools/ats-discover.py:57, task 15).
 *
 * So this reads the flag under either of the two names it might land under and
 * qualifies the figure when it is set. When it is ABSENT the figure is shown
 * plainly -- which is right today and becomes wrong the moment a predicting
 * source lands without the column. That is a backend gap, recorded in
 * frontend/README.md; it is not something a client can close.
 */
export function compLabel(job) {
  const estimated = job.comp_is_estimated ?? job.is_estimated ?? null;
  const money = compRange(job);
  if (!money) return null;
  return { text: money, estimated: estimated === true };
}

function compRange(job) {
  const { comp_min: lo, comp_max: hi, comp_currency: currency } = job;
  if (lo != null || hi != null) {
    const unit = currency === "USD" || currency == null ? "$" : `${currency} `;
    const fmt = (n) => `${unit}${Number(n).toLocaleString("en-US")}`;
    if (lo != null && hi != null) return `${fmt(lo)} – ${fmt(hi)}`;
    return lo != null ? `From ${fmt(lo)}` : `Up to ${fmt(hi)}`;
  }
  // `salary` is coalesce(j.salary_text, currency || ' ' || min-max)
  // (schema.py:795-796), so it is the employer's own string only when
  // salary_text was set. With comp_min/comp_max both null it is the employer's
  // string by construction.
  return job.salary || null;
}

// -- where and how ---------------------------------------------------------

export function placeLabel(job) {
  const bits = [];
  if (job.location_raw) bits.push(job.location_raw);
  else if (job.location_is_nyc) bits.push("New York, NY");
  const policy = {
    onsite: "On site",
    hybrid: "Hybrid",
    remote_local: "Remote, in the area",
    remote_anywhere: "Remote, anywhere",
  }[job.remote_policy];
  if (policy) bits.push(policy);
  return bits.join(" · ");
}

// -- why it is here --------------------------------------------------------

/** Plain-language readings of the rule names match.py writes into
 *  match_reasons. Anything unmatched falls through to a humanised slug, which
 *  is deliberately a bit ugly: a new rule should be visible, not silent. */
const RULE_TEXT = {
  "ai:uses_ai_tools": "Uses AI tools day to day",
  "ai:builds_llm_features": "Builds AI features",
  "ai:core_ml_research": "Machine-learning research",
  "flag:gap_friendly_language": "Welcomes career changers and people returning to work",
  "flag:nyc": "In New York City",
  "flag:remote": "Can be done remotely",
};

const ARCHETYPE_PREFIX = "Kind of role: ";

/**
 * The reasons this posting is on the list, as words.
 *
 * ONLY THE POSITIVE ONES, AND NEVER THE NUMBER. Each entry in match_reasons is
 * {rule, delta} (match.py writes it as json.dumps, hence api.js parsing it).
 * The deltas sum to `match_score`, so printing them prints the score in
 * pieces. `base` is dropped because "this is a job posting" is not a reason,
 * and negatives are dropped because a card is not the place to argue with the
 * ranker -- the honest negatives are `risk_factors` on the detail page, which
 * are written for a person rather than derived from weights.
 */
export function reasonsFor(job, limit = 3) {
  const reasons = Array.isArray(job.match_reasons) ? job.match_reasons : [];
  const out = [];
  for (const entry of reasons) {
    if (!entry || typeof entry !== "object") continue;
    const { rule, delta } = entry;
    if (!rule || rule === "base" || !(Number(delta) > 0)) continue;
    if (RULE_TEXT[rule]) { out.push(RULE_TEXT[rule]); continue; }
    if (rule.startsWith("archetype:")) {
      out.push(ARCHETYPE_PREFIX + humanWords(rule.slice("archetype:".length)));
      continue;
    }
    out.push(humanWords(rule.replace(/^[a-z_]+:/, "")));
  }
  return out.slice(0, limit);
}

function humanWords(slug) {
  const spaced = String(slug).replace(/[_:]/g, " ").trim();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

// -- the dismiss vocabulary ------------------------------------------------

/**
 * schema_web.DISMISS_REASONS (backend/webapp/schema_web.py:272-273), in that
 * order, with the words a person would use. The slug is what goes on the wire;
 * an unknown one is a 400 with code `unknown_reason` (jobs.py:700-705).
 */
export const DISMISS_REASONS = [
  ["wrong_level", "Wrong level for me"],
  ["wrong_role", "Not the kind of work I want"],
  ["wrong_location", "Wrong place"],
  ["bad_company", "Not this company"],
  ["stale_posting", "Looks like it's already gone"],
  ["other", "Another reason"],
];
