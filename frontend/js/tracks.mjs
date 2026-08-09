// The track vocabulary, the plain-language labels, and the grouping.
//
// THE VOCABULARY IS extract.ROLE_TRACK (backend/extract.py:305-308), DEC-77.
// Nine snake_case values, and they are what is actually stored on
// job_facts.role_track (backend/schema.py:740 -- NOT jobs.role_track at :542,
// which is the profiles DDL and was wrong about the table as well as the
// line). Rejected: score.TRACKS
// (backend/score.py:281-282), the five Title Case values that arrive on every
// row as `primary_track`. Reason: ROLE_TRACK is the stored value and is
// already slug-shaped, so grouping by it needs no mapping layer and invents no
// second vocabulary.
//
// ~~AND YET NOTHING IN THIS FILE HAS A TRACK TO GROUP BY TODAY.~~ THERE IS ONE
// NOW, and not one line of this file changed to make it work -- which was the
// bet. The paragraph here used to read: `role_track` is not in the jobs_app
// view, therefore not in LIST_COLUMNS, therefore not in any response body, so
// every row resolves to null and lands in UNTRACKED. Both of those two lines
// are now written -- `f.role_track` is the last entry of schema._APP_VIEW_SQL
// and "role_track" the last of jobs.LIST_COLUMNS, both LAST because
// CREATE OR REPLACE VIEW can only append and a reorder sends ensure_app_view
// down a DROP VIEW that takes every GRANT with it. This file was written to
// group by the field the moment it appeared, and it did.
// See frontend/README.md § "What building against these fixtures turned up",
// item 1.
//
// THE SEARCH SCREEN READS THE SAME VOCABULARY FOR A DIFFERENT SUBJECT, and the
// two must not be conflated. `search_queries.role_track` is why a SEEDED QUERY
// exists; `job_facts.role_track` -- everything in this file -- is what kind of
// job a POSTING is. Same nine slugs, and they never share a JSON object.
// js/search.mjs's header states the rule; nothing here groups a query.
//
// THE AXIS IS NOT A FACT ABOUT A POSTING, and the UI must not present it as
// one. backend/evals/fixtures/results/selfcheck-n120-2026-08-02.json owns the
// figures and both reproduce from it -- .fields.role_track.overall.agree2 is
// 0.8870 at n_comparable 115, so 11.3% of postings change whether they belong
// to ANY track between two runs of the same prompt at temperature 0. NAME THE
// METRIC when quoting this: agree2, not pairwise and not unanimous. Separately
// and on a different instrument, humans answered `no_track_fits` on 15 of 36
// labelled postings -- a prevalence, not an instability, and neither number
// bounds the other. Hence CAVEAT below, rendered under every group heading.

/** The nine, in the order extract.py declares them. */
export const ROLE_TRACK = [
  "software_engineering", "technical_support", "business_analysis",
  "product_and_marketing", "solutions_and_implementation",
  "data_and_analytics", "revenue_operations", "business_systems",
  "business_operations",
];

/** The bucket every posting with no usable track falls into. Not one of the
 *  nine, and deliberately not a slug that could be mistaken for one. */
export const UNTRACKED = "__untracked__";

/**
 * Plain language, per 32-frontend.md: "No 'match score,' no 'relevance,' no
 * jargon inherited from the schema. A label should read like something a
 * person would say."
 */
const LABELS = {
  software_engineering: {
    label: "Building software",
    blurb: "Roles where you write and ship code.",
  },
  technical_support: {
    label: "Technical support",
    blurb: "Roles where you help people get software working.",
  },
  business_analysis: {
    label: "Business analysis",
    blurb: "Roles where you work out what a team needs and write it down clearly.",
  },
  product_and_marketing: {
    label: "Product and marketing",
    blurb: "Roles where you shape what gets built, and how it gets explained.",
  },
  solutions_and_implementation: {
    label: "Setting products up for customers",
    blurb: "Roles where you configure a product for a customer and make it fit how they work.",
  },
  data_and_analytics: {
    label: "Working with data",
    blurb: "Roles where you clean, check and report on numbers.",
  },
  revenue_operations: {
    label: "Keeping sales running",
    blurb: "Roles that look after a sales team's tools, pipeline and numbers.",
  },
  business_systems: {
    label: "The systems a company runs on",
    blurb: "Roles that configure things like Salesforce and Workday for the people who use them.",
  },
  business_operations: {
    label: "Keeping the business running",
    blurb: "Roles that hold the day-to-day of an organisation together.",
  },
  [UNTRACKED]: {
    label: "Everything else",
    blurb: "These haven't been sorted into a group. That is normal, not a problem with the posting.",
  },
};

/** The sentence that keeps a heading from reading as a claim. */
export const CAVEAT =
  "Groups are a rough guide. The same posting can land in a different group on " +
  "a different day, so read the role, not the heading.";

export function labelFor(track) {
  return LABELS[track] || { label: humanise(track), blurb: "" };
}

/** `some_slug_here` -> `Some slug here`. The fallback for a track this file
 *  has no copy for -- which happens the day someone adds a tenth to
 *  extract.ROLE_TRACK and not to this file. Ugly on purpose: it should be
 *  visible, not invisible. */
export function humanise(slug) {
  if (!slug) return "";
  const spaced = String(slug).replace(/_/g, " ");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/**
 * The track a posting belongs to, or UNTRACKED.
 *
 * A value outside the nine is treated as no track rather than passed through:
 * the vocabulary is closed (extract._enum, backend/extract.py:754, maps
 * anything unrecognised to null before it is ever stored), so a stray value
 * reaching here means the response is from a newer server than this file, and
 * inventing a group for it would put one posting under a heading nobody wrote.
 */
export function trackOf(job) {
  const raw = job.role_track;
  return ROLE_TRACK.includes(raw) ? raw : UNTRACKED;
}

/**
 * Group a page of jobs into ordered track groups.
 *
 * ORDER. Groups are ordered by their best (lowest) `rank`, and rows inside a
 * group stay in rank order. That keeps the strongest posting at the top of the
 * page and preserves the payload order everywhere else -- match_score order,
 * never fit_score, which would put an LLM call on the ordering path
 * (.claude/CLAUDE.md, three files' worth of invariants). It is deliberately
 * NOT a claim about which track is better: within-track and between-track
 * ordering is task 30's and task 30 is blocked. UNTRACKED sorts by the same
 * rule as the rest and is not pinned to the bottom -- pinning it would be an
 * ordering claim, and today it holds every row.
 *
 * `rank` on each row is the server's and is never recomputed here. It is
 * global across the render (jobs.py:564-565) and it is what every event echoes.
 */
export function groupByTrack(jobs) {
  const groups = new Map();
  for (const job of jobs) {
    const track = trackOf(job);
    if (!groups.has(track)) groups.set(track, { track, ...labelFor(track), jobs: [] });
    groups.get(track).jobs.push(job);
  }
  for (const group of groups.values()) {
    group.jobs.sort((a, b) => a.rank - b.rank);
    group.bestRank = group.jobs[0].rank;
  }
  return [...groups.values()].sort((a, b) => a.bestRank - b.bestRank);
}
