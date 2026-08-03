export const meta = {
  name: 'orientation-from-code',
  description: 'Task 49 — rebuild understanding of the jobs pipeline from code, tests and git history; docs consulted last and adversarially',
  phases: [
    { title: 'Code' },
    { title: 'Evidence' },
    { title: 'Tasks' },
    { title: 'Docs' },
    { title: 'Figures' },
    { title: 'Verify' },
    { title: 'Synthesize' },
  ],
}

const ROOT = '/home/eric/apps/jobs'

const MANDATE = `
=== NON-NEGOTIABLE RULES FOR THIS BRIEF ===

1. **If any fact in this brief contradicts what you find in the code, STOP and report the
   contradiction instead of proceeding.** Put it in the \`contradictions\` field of your output
   and do not silently work around it. Briefs in this repo have contained factual errors before
   and only the subagents caught them.

2. **The existing documentation is NOT an input.** Do not open anything under \`docs/\` unless
   your brief explicitly assigns you documents to audit. Do not open \`.claude/CLAUDE.md\`,
   \`README.md\` files, or \`AUDIT.md\` / \`HANDOFF.md\` / \`MASTER-PLAN-pursuit.md\` /
   \`STANDING-GUIDANCE.md\` / \`DECISIONS.md\` for orientation. Your sources, in strict priority
   order:
     (a) the code itself
     (b) the three test suites (a passing test is a claim someone verified)
     (c) \`git log\` / \`git show\`
     (d) \`_comment\` fields inside \`backend/config/*.json\` (rationale that lives with the thing)
   Code beats tests beats git beats comments. Docs are last and only where assigned.

3. **Every claim you return must carry a \`file:line\` citation or a shell command that
   reproduces it.** An uncited claim is worthless to this task and will be discarded. Cite as
   \`backend/score.py:142\`, repo-relative.

4. **Read the artifact, not the summary.** A total is not a composition. If you are counting
   things, open a sample of the rows underneath the count. Do not trust a status line, a
   docstring, or a variable name — trust what executes.

5. **You are READ-ONLY.** Do not edit, write, create or delete any file in the repo. Do not
   \`git commit\`, \`git add\`, \`git stash\`, or \`git checkout\`. Read-only shell commands only.
   You may write scratch files ONLY under /tmp if you genuinely need them.

6. Repo root is ${ROOT}. \`cd ${ROOT}\` first. There is no pytest anywhere; \`unittest\` is stdlib.

7. Say "I could not determine X" rather than guessing. Unknowns are a finding. Confabulated
   detail poisons every task downstream of this one.
=== END RULES ===
`

const CODE_SCHEMA = {
  type: 'object',
  required: ['area', 'summary', 'facts', 'contradictions'],
  properties: {
    area: { type: 'string' },
    summary: { type: 'string', description: '5-12 sentences: what this area actually does when it runs' },
    facts: {
      type: 'array',
      description: 'Load-bearing facts, each cited. Aim for 10-30.',
      items: {
        type: 'object',
        required: ['claim', 'citation'],
        properties: {
          claim: { type: 'string' },
          citation: { type: 'string', description: 'repo-relative file:line, or a shell command' },
          confidence: { type: 'string', enum: ['certain', 'likely', 'unsure'] },
        },
      },
    },
    entrypoints: {
      type: 'array',
      items: {
        type: 'object',
        required: ['name', 'citation'],
        properties: { name: { type: 'string' }, citation: { type: 'string' }, invoked_by: { type: 'string' }, description: { type: 'string' } },
      },
    },
    data_flow: {
      type: 'array',
      description: 'What this area reads and writes: DB tables/views, files, HTTP endpoints',
      items: {
        type: 'object',
        required: ['store', 'operation', 'citation'],
        properties: { store: { type: 'string' }, operation: { type: 'string', enum: ['read', 'write', 'both'] }, citation: { type: 'string' }, note: { type: 'string' } },
      },
    },
    llm_calls: {
      type: 'array',
      description: 'Every site that costs a model call, with how the model is chosen',
      items: {
        type: 'object',
        required: ['site', 'citation'],
        properties: { site: { type: 'string' }, citation: { type: 'string' }, model_selection: { type: 'string' }, on_failure: { type: 'string' } },
      },
    },
    dead_or_suspect: {
      type: 'array',
      description: 'Code that appears unreachable, unfinished, contradicted by a sibling, or is a landmine',
      items: {
        type: 'object',
        required: ['what', 'citation', 'why'],
        properties: { what: { type: 'string' }, citation: { type: 'string' }, why: { type: 'string' } },
      },
    },
    open_questions: {
      type: 'array',
      description: 'Things you could not resolve from code, and what would resolve them',
      items: { type: 'object', required: ['question'], properties: { question: { type: 'string' }, needs: { type: 'string', enum: ['more-reading', 'a-running-database', 'the-owner', 'an-external-account', 'a-device'] } } },
    },
    contradictions: {
      type: 'array',
      description: 'Facts asserted in your brief that the code does NOT support. Empty array if none.',
      items: { type: 'string' },
    },
  },
}

// ---------------------------------------------------------------- Phase A: code

const CODE_AREAS = [
  {
    key: 'stages',
    label: 'code:four-stages',
    brief: `Read the four pipeline stages and the orchestrator, and describe what they ACTUALLY do today.

Files, in this order:
  backend/relevance.py, backend/extract.py, backend/match.py, backend/score.py
  backend/run-daily.py  (the nightly orchestrator)
  backend/profiles.py, backend/llm.py
  backend/config/*.json  — read the \`_comment\` fields; they are load-bearing rationale

Answer concretely, with file:line for each:
- For EACH of the four stages: what rows does it read, what rows does it write, what is the
  gate/filter that decides which postings it touches, and does it cost an LLM call?
- What EXACTLY does run-daily.py execute, in order? List every step with its line number. Is
  every step actually enabled, or are some skipped/commented/flag-gated? Does the step list
  match the four stages plus ingest, or is it something else?
- \`score_job()\`: is it pure (no I/O)? Prove it or disprove it by reading its body and every
  function it calls. Cite.
- Which score orders the user-facing list — \`match_score\` or \`fit_score\`? Find the actual
  ORDER BY / sort call that produces the list a user sees and cite it. If the sort lives in
  webapp/ or frontend/, say so and name the file even though it is another agent's area.
- \`match_reasons\`: what produces it, what shape is it, is it written on every row?
- The deferral-vs-failure distinction: find the code that decides whether a model response
  becomes a tombstone row versus writes nothing. Cite the branch. What exactly does a tombstone
  row look like (which columns, which values)?
- Version/cache-key columns: which version fields does each derived row record, where are their
  current values defined, and what is the staleness predicate? Name every version constant you
  find and its literal current value with a citation.
- backend/llm.py: which model is production, how is it selected, is it hardcoded or from env or
  config? What happens on 429 / timeout / 5xx versus on a malformed but successful response?

Also read backend/cohort.py and backend/searchqueries.py / backend/searchnorm.py enough to say
whether they participate in the nightly path or are standalone.`,
  },
  {
    key: 'ingest',
    label: 'code:ingest',
    brief: `Read the ingest layer and describe what sources actually flow today.

Files:
  backend/ingest/*.py  (ats.py, ats_sources.py, builtin-nyc.py, google-apify.py,
                        google-serpapi.py, hn-hiring.py, nyc-open-data.py,
                        weworkremotely.py, workday.py)
  backend/serp/*.py and backend/serp/providers/*.py
  backend/google_jobs.py, backend/ats_discovery.py, backend/ratelimit.py, backend/volume_floors.py

Answer with file:line:
- One row per ingest script: what source, what protocol (API/scrape), what auth/key it needs,
  what table it writes, whether it is wired into run-daily.py or only runs standalone, and
  whether it appears functional or stubbed.
- Which ingest scripts unpack \`upsert()\` as a bare tuple versus using \`upsert_checked\`? Grep
  for both and give the exact call sites. This is a known defect class — report the CURRENT
  state, not the historical one.
- The Workday pagination limit: find the literal value in the code and cite it.
- Throttle/partial-page handling: does any script reconcile collected counts against a \`total\`
  returned by the API? Which ones do and which do not? Cite.
- backend/serp/: what does the provider abstraction actually look like now? How many providers
  are implemented, what does dispatch.py choose between, and what does quota.py enforce? Is the
  seam real (callers go through it) or is it bypassed anywhere? Grep for direct provider imports
  outside serp/.
- Is there a second definition of the Google Jobs record shape anywhere? Grep for the field
  names and report every place the shape is defined.
- \`urlopen\` / \`requests\` / raw HTTP: grep the whole of backend/ for direct HTTP calls that do
  NOT go through backend/lib/http.py. List every site with a citation and say whether it looks
  deliberate.
- What does volume_floors.py enforce and where is it invoked from?`,
  },
  {
    key: 'schema',
    label: 'code:schema-and-lib',
    brief: `Read the database schema and the shared library, and describe the actual data model.

Files:
  backend/schema.py  (read it in full — it is the authority)
  backend/lib/*.py   (dbconn, envfile, http, ids, state, text, timeparse, upsert, __init__)
  backend/migrations/*.py
  backend/webapp/schema_web.py  (read for table list only; webapp behaviour is another agent's)

Answer with file:line:
- Enumerate EVERY table and view schema.py creates or alters. For each: its primary key, its
  purpose in one line, and the citation. Do not summarise — list them.
- The \`jobs\` table vs the \`jobs_app\` view: what exactly does the view filter or guarantee that
  the table does not? Quote the view definition with its line numbers.
- \`job_facts\`, \`job_matches\`, \`job_scores\`: what are their keys? Is extraction shared across
  profiles while scores are per-profile, or not? Prove it from the key definitions.
- List every version/provenance column on every derived table, with its citation, and say for
  each whether the code treats it as a cache key (participates in a staleness comparison) or as
  provenance only. Find the staleness query and cite it.
- \`add_missing_columns\`: what does it do, when does it run, and what columns does it add to
  which tables? This is where columns land without a migration — enumerate them.
- backend/lib/upsert.py: read \`UpsertResult\` and \`upsert_checked\` in full. What does
  \`__iter__\` yield, how many values, and what is \`.errors\`? Why does unpacking as a bare tuple
  lose information? Cite exact lines.
- backend/lib/http.py: what is its interface, what does it add over urlopen (retry? timeout?
  user-agent? rate limiting?), and who calls it?
- backend/lib/ids.py: what identity/digest functions exist and what feeds a stored digest?
- backend/migrations/: which migrations exist, are they idempotent, and is there any runner that
  invokes them or are they manual one-shots? Cite.
- Is \`lib/\` vendored from elsewhere or owned outright? Read backend/lib/__init__.py and say what
  it actually asserts.`,
  },
  {
    key: 'webapp',
    label: 'code:webapp',
    brief: `Read the webapp process and describe the HTTP surface it actually serves.

Files:
  backend/webapp/app.py, auth.py, config.py, db.py, jobs.py, label.py, onboarding.py,
  search.py, schema_web.py, manage_app_users.py
  backend/webapp/.env  — do NOT print secret values; report only which KEYS exist
  backend/webapp/pyvenv.cfg or .venv/pyvenv.cfg

Answer with file:line:
- Enumerate EVERY route: method, path, auth requirement, what it reads, what it returns. This
  is the most important part of your output — be exhaustive, one entry per route.
- Authentication: what is the actual mechanism (session cookie? bearer? Google SSO?). Where is
  the session minted, where is it verified, what is its lifetime, and what is the cookie's
  SameSite/Secure/HttpOnly configuration? Cite.
- CORS: what does the code allow, and which env vars name the allowed origins? Cite the literal
  defaults.
- The ordering of the job list: find the actual ORDER BY that produces the ranked list and quote
  it with line numbers. Which column sorts, which merely annotates? Does any LLM call sit
  between a request and an ordering? Trace the request path and prove it either way.
- Does the webapp read the \`jobs\` table directly anywhere, or always the \`jobs_app\` view?
  Grep for both and cite every site.
- Profiles / cohort: how does a request pick a profile, and what happens when a user has none?
- Events: what writes \`job_events\`, what fields does it record, and is \`rank\` recorded?
- Onboarding and labelling: what is built and what is a stub? Read the handlers, not the names.
- What port does it bind by default, and where is that defined?
- Does it import from backend/ top level or api/? Grep the sys.path inserts and every import
  that crosses a process boundary. The claimed invariant is that the three processes do not
  import each other — verify it or refute it.`,
  },
  {
    key: 'api',
    label: 'code:contributor-api',
    brief: `Read the contributor API process and describe what it is and whether it works.

Files:
  backend/api/app.py, contribution_report.py, manage_users.py, query_claims.py
  backend/api/contributor-worker/google-serpapi-worker.py
  backend/api/tests/*.py  (these are a SEPARATE third suite)
  backend/api/.venv/pyvenv.cfg  — report include-system-site-packages
  backend/api/.env — report KEY NAMES only, never values

Answer with file:line:
- Enumerate every route: method, path, auth, effect.
- The claim protocol: what is a claim, what is the lifecycle, what prevents double-claiming, and
  what is the metering/cap? Find the cap's literal value and cite it. Find what table the cap
  counts and confirm it counts the right one.
- The worker: what does contributor-worker/google-serpapi-worker.py do, how does it authenticate,
  and is it deployed anywhere (check deploy/ for a unit that references it)?
- Does this process share a database role/schema with the pipeline or webapp? Cite the connection
  setup.
- Its venv: confirm whether include-system-site-packages is false and what third-party packages
  it requires. Can system python3 import api/app.py? Test it read-only:
    cd ${ROOT}/backend/api && python3 -c "import app" 2>&1 | tail -3
  Report the actual output.
- Run its suite and report the exact runner output:
    cd ${ROOT}/backend/api && .venv/bin/python -m unittest discover -s tests 2>&1 | tail -25
- Is this process wired into deploy/? Which systemd unit, if any?
- Assess: is this alive, vestigial, or dead? Argue from evidence in the tree only.`,
  },
  {
    key: 'frontend',
    label: 'code:frontend',
    brief: `Read the frontend client and its two checkers, and report what actually renders.

Files:
  frontend/js/*.mjs  (api, app, crawl, detail, events, format, onboarding, renders, saved,
                      search, today, tracks, ui)
  frontend/serve.py, frontend/verify_fixtures.py, frontend/check_client.mjs
  frontend/*.html and any stylesheet
  frontend/fixtures/ if it exists

Answer with file:line:
- What screens exist as code, and for EACH one: is it reachable from the app's router/entry, does
  it call a real endpoint, and does it render real data or a placeholder? Read the render
  function bodies. A file existing is not a screen shipping.
- The routing: how does app.mjs decide what to show? Cite.
- js/api.mjs: enumerate every endpoint the client calls. Cross-check that list against what you
  can see — do any called endpoints not obviously exist? Just list them; another agent has the
  server side.
- Credentials: how does the client authenticate? Does it send cookies (credentials: 'include')?
  Cite the fetch options.
- serve.py: what origin/port does it mount on, and why does that matter for the cookie? Cite the
  actual port value and any --host flag.
- Is there a build step, npm, package.json, or any bundler anywhere under frontend/? Prove
  absence with a find/ls command and report the command.
- verify_fixtures.py and check_client.mjs: what does each actually assert? Run both and report
  exact output:
    cd ${ROOT}/backend/webapp && .venv/bin/python ${ROOT}/frontend/verify_fixtures.py 2>&1 | tail -20
    cd ${ROOT} && node frontend/check_client.mjs 2>&1 | tail -20
  If node is absent, say so.
- Which screens are NOT built? Be specific and cite the absence (no file, or file with a stub
  body at line N).`,
  },
  {
    key: 'evals',
    label: 'code:evals-and-tools',
    brief: `Read the measurement substrate — the evals package and backend/tools/ — and report what
each instrument measures and what it emits.

Files:
  backend/evals/*.py and backend/evals/tasks/*.py
  backend/evals/fixtures/  (list it; describe the corpora, do not read every line)
  backend/tools/*.py  (there are ~20; give each ONE line, then go deep on the ones below)

Go deep on:
  backend/evals/metrics.py, runner.py, corpus.py, labels.py, scratchdb.py, cache.py, cassettes.py
  backend/tools/relevance-report.py, audit-docs.py, audit-doc-links.py, label-findings.py,
  backend/tools/claude-ceiling-test.py, compare-models.py, calibrate-match.py

Answer with file:line:
- The self-consistency metrics: find the code that computes them. How many DISTINCT metrics does
  it compute, what is each one's exact name as it appears in the code, and what is each one's
  precise definition (the formula, from the implementation)? Cite each. This is the single most
  important thing you will report — three different correct percentages circulate in this repo
  for the same run and the metric name is what distinguishes them.
- \`--repeat N\`: is that a metric or a run parameter? Prove it from the argument parser and the
  metric functions.
- What ranking/quality metrics exist (average precision? precision@k?) and what are their exact
  implementations? Cite.
- The corpus: how is it selected and frozen? Is there anything that would let someone select by
  \`ORDER BY first_seen DESC\`, and does any code path still do that? Grep for it.
- The replay cache and cassettes: what is cached, keyed on what, and what does --no-cache change?
- scratchdb.py: what is the availability gate, and what does a module do when it is unavailable?
- committed result files: find every JSON/MD result artifact under backend/evals/ and
  docs/ingestion_tests/ (you MAY read the JSON result files — they are data, not prose docs) and
  report for each: n, date, model, and the metric values it contains, verbatim. Cite file:line
  or the JSON key path.
- backend/tools/audit-docs.py: what checks does it implement, what are they named (C1, C2...),
  and what is the current pass/fail? Run it read-only and report exact output:
    cd ${ROOT}/backend && python3 tools/audit-docs.py 2>&1 | tail -40
- Run backend/tools/relevance-report.py --dead and report exact output (tail -30).`,
  },
  {
    key: 'deploy',
    label: 'code:deploy-and-config',
    brief: `Read the deployment surface and the configuration, and report what would actually run on a
machine.

Files:
  deploy/systemd/*.service, deploy/systemd/*.timer, deploy/cloudflared/config.yml
  scripts/tranche-two-launcher.sh
  backend/config/*.json  (read the \`_comment\` fields carefully — they are the rationale record)
  backend/requirements.txt
  .gitignore
  backend/.env, backend/webapp/.env, backend/api/.env — report KEY NAMES ONLY, never values.
    Use: grep -o '^[A-Z_0-9]*=' on each file. Never print anything right of the '='.

Answer with file:line:
- One row per systemd unit: what does ExecStart run, as what user, on what schedule (for timers),
  with what WorkingDirectory and EnvironmentFile, and what OnFailure. Quote ExecStart verbatim.
- Do the units reference paths that actually exist in this tree? Check each ExecStart path
  against the filesystem and report every mismatch. This is a likely source of findings.
- Is there any unit for the contributor API, the webapp, the frontend server, backups, and the
  volume check? Which of those five have units and which do not?
- cloudflared config: what hostnames map to what local ports? Do those ports match the ports the
  webapp and api actually bind (you may grep for the port constants)?
- backend/config/*.json: enumerate every config file, what it configures, and summarise the
  \`_comment\` rationale. Where a \`_comment\` records a REJECTED alternative, quote it — that is
  the most valuable content in the repo and it must survive into the report.
- Postgres word boundaries: grep every config JSON and every .py for regex patterns containing
  \`\\\\b\` versus \`\\\\y\`. Report every \`\\\\b\` you find in anything that reaches Postgres, with a
  citation. In Postgres \`\\\\b\` is BACKSPACE and matches nothing.
- requirements.txt: what is in it? Is psycopg the only third-party dependency at the top level?
- Env key names: which keys does each of the three .env files define? Which keys does the code
  read that are NOT present in the corresponding .env (grep os.environ / getenv and diff)?`,
  },
]

// ------------------------------------------------------------ Phase B: evidence

const SUITE_SCHEMA = {
  type: 'object',
  required: ['suites', 'contradictions'],
  properties: {
    suites: {
      type: 'array',
      items: {
        type: 'object',
        required: ['name', 'command', 'ran', 'ok'],
        properties: {
          name: { type: 'string' },
          command: { type: 'string' },
          ran: { type: 'integer', description: 'the N from "Ran N tests"' },
          failures: { type: 'integer' },
          errors: { type: 'integer' },
          skipped: { type: 'integer' },
          ok: { type: 'boolean' },
          duration: { type: 'string' },
          raw_tail: { type: 'string', description: 'last ~10 lines of runner output verbatim' },
          skipped_modules: { type: 'array', items: { type: 'string' } },
        },
      },
    },
    notable: { type: 'array', items: { type: 'object', required: ['observation'], properties: { observation: { type: 'string' }, citation: { type: 'string' } } } },
    contradictions: { type: 'array', items: { type: 'string' } },
  },
}

const GIT_SCHEMA = {
  type: 'object',
  required: ['landed', 'contradictions'],
  properties: {
    landed: {
      type: 'array',
      description: 'One entry per task number you could attribute to commits',
      items: {
        type: 'object',
        required: ['task', 'verdict'],
        properties: {
          task: { type: 'string' },
          commits: { type: 'array', items: { type: 'string' } },
          verdict: { type: 'string', enum: ['landed', 'partially-landed', 'no-commit-found', 'reverted', 'dropped'] },
          files_touched: { type: 'array', items: { type: 'string' } },
          note: { type: 'string' },
        },
      },
    },
    timeline: { type: 'array', description: 'Notable inflection points in the history', items: { type: 'object', required: ['sha', 'what'], properties: { sha: { type: 'string' }, date: { type: 'string' }, what: { type: 'string' } } } },
    reverts_and_drops: { type: 'array', items: { type: 'object', required: ['what', 'sha'], properties: { what: { type: 'string' }, sha: { type: 'string' }, why: { type: 'string' } } } },
    contradictions: { type: 'array', items: { type: 'string' } },
  },
}

// -------------------------------------------------------------- Phase C: tasks

const TASKS_SCHEMA = {
  type: 'object',
  required: ['tasks', 'contradictions'],
  properties: {
    tasks: {
      type: 'array',
      items: {
        type: 'object',
        required: ['id', 'file', 'claimed_status', 'evidence_status', 'evidence'],
        properties: {
          id: { type: 'string' },
          title: { type: 'string' },
          file: { type: 'string' },
          claimed_status: { type: 'string', description: 'verbatim from the task file Status line' },
          evidence_status: { type: 'string', enum: ['DONE', 'PARTIAL', 'NOT-DONE', 'DROPPED', 'UNVERIFIABLE', 'NOT-AN-IMPLEMENTATION'] },
          mismatch: { type: 'boolean', description: 'true if claimed_status and evidence_status disagree' },
          evidence: { type: 'array', items: { type: 'object', required: ['dod_item', 'met', 'citation'], properties: { dod_item: { type: 'string' }, met: { type: 'string', enum: ['yes', 'no', 'partial', 'unverifiable'] }, citation: { type: 'string' } } } },
          residual_work: { type: 'string', description: 'what is left, concretely' },
          blocked_on: { type: 'string', enum: ['nothing', 'more-work', 'the-owner', 'an-external-account', 'a-device', 'a-running-database'] },
          note: { type: 'string' },
        },
      },
    },
    contradictions: { type: 'array', items: { type: 'string' } },
  },
}

// --------------------------------------------------------------- Phase D: docs

const DOCS_SCHEMA = {
  type: 'object',
  required: ['disagreements', 'docs_read', 'contradictions'],
  properties: {
    docs_read: { type: 'array', items: { type: 'object', required: ['path', 'lines', 'kind'], properties: { path: { type: 'string' }, lines: { type: 'integer' }, kind: { type: 'string', description: 'the kind: declared in frontmatter, or "none"' }, verdict: { type: 'string', enum: ['accurate', 'mostly-accurate', 'partly-stale', 'substantially-wrong', 'unverifiable'] } } } },
    disagreements: {
      type: 'array',
      description: 'Every place a doc claims something the code does not support. Be exhaustive.',
      items: {
        type: 'object',
        required: ['doc', 'doc_claim', 'code_says', 'code_citation', 'severity'],
        properties: {
          doc: { type: 'string', description: 'path:line of the claim' },
          doc_claim: { type: 'string', description: 'quote it' },
          code_says: { type: 'string' },
          code_citation: { type: 'string' },
          severity: { type: 'string', enum: ['high', 'medium', 'low'], description: 'high = would cause a wrong decision or wrong code' },
          kind: { type: 'string', enum: ['stale', 'never-true', 'figure-without-instrument', 'contradicts-another-doc', 'names-a-nonexistent-file', 'unverifiable-claim', 'internally-inconsistent'] },
        },
      },
    },
    confirmations: { type: 'integer', description: 'count of doc claims you checked that the code DID support' },
    contradictions: { type: 'array', items: { type: 'string' } },
  },
}

const FIGURES_SCHEMA = {
  type: 'object',
  required: ['figures', 'contradictions'],
  properties: {
    figures: {
      type: 'array',
      items: {
        type: 'object',
        required: ['value', 'subject', 'status'],
        properties: {
          value: { type: 'string', description: 'the number as written, e.g. "85.2% [77.6-90.6]"' },
          subject: { type: 'string', description: 'what it measures, e.g. seniority_level self-consistency' },
          metric_name: { type: 'string', description: 'the EXACT metric name from the code, or "UNNAMED - this is the problem"' },
          instrument: { type: 'string', description: 'the code that computes it, file:line' },
          n: { type: 'string' },
          date: { type: 'string' },
          model: { type: 'string' },
          owning_doc: { type: 'string', description: 'the one doc that owns it per one-figure-one-owner' },
          also_appears_in: { type: 'array', items: { type: 'string' }, description: 'path:line for every other occurrence' },
          reproducing_command: { type: 'string' },
          status: { type: 'string', enum: ['current', 'superseded', 'orphan-no-instrument', 'contradicted', 'provisional'] },
          note: { type: 'string' },
        },
      },
    },
    contradictions: { type: 'array', items: { type: 'string' } },
  },
}

const VERDICT_SCHEMA = {
  type: 'object',
  required: ['refuted', 'reason'],
  properties: {
    refuted: { type: 'boolean', description: 'true if the claimed disagreement is NOT real' },
    reason: { type: 'string' },
    corrected_claim: { type: 'string', description: 'if partially right, the accurate version' },
    citation: { type: 'string' },
    severity_adjusted: { type: 'string', enum: ['high', 'medium', 'low'] },
  },
}

// ================================================================== execution

phase('Code')
log(`Reading ${CODE_AREAS.length} code areas + 3 evidence agents. Docs are NOT an input to this phase.`)

const groundTruth = await parallel([
  ...CODE_AREAS.map(a => () => agent(
    `${MANDATE}\n\nYou are reading ONE area of a job-discovery pipeline at ${ROOT}. Area: **${a.key}**.\n\n${a.brief}\n\nReturn the structured object. Be exhaustive on \`facts\` and \`data_flow\`; those are what the whole downstream task rests on.`,
    { label: a.label, phase: 'Code', schema: CODE_SCHEMA }
  ).then(r => r && { ...r, _key: a.key })),

  () => agent(
    `${MANDATE}\n\nRun all THREE test suites in this repo and report the exact runner output. Do not summarise numbers from memory or from any document — run the commands.\n\n    cd ${ROOT}/backend && python3 -m unittest discover -s tests 2>&1 | tail -30\n    cd ${ROOT}/backend/webapp && .venv/bin/python -m unittest discover -s tests 2>&1 | tail -30\n    cd ${ROOT}/backend/api && .venv/bin/python -m unittest discover -s tests 2>&1 | tail -30\n\nFor each: report the literal "Ran N tests in Xs" line, the OK/FAILED line, and the counts of\nfailures/errors/skips. If a suite fails to start, report the traceback tail — that is a finding,\nnot an obstacle.\n\nThen, for the backend suite ONLY, re-run with -v and identify which test MODULES skipped entirely\nand why (several gate on a scratch database being available):\n    cd ${ROOT}/backend && python3 -m unittest discover -s tests -v 2>&1 | grep -iE 'skipped|skip' | sort | uniq -c | sort -rn | head -40\n\nAlso answer, with citations:\n- Is the skip gate driven by an env var, and does the module load an .env file before evaluating\n  it? Find the gate code and cite it.\n- Is pytest installed in ANY of the three interpreters? Check each and report.\n- How many test FILES exist in each suite (find | wc -l), and note explicitly that a file count\n  and a test count are different things.\n\nNever report a test count you did not see the runner print.`,
    { label: 'evidence:test-suites', phase: 'Evidence', schema: SUITE_SCHEMA }
  ).then(r => r && { ...r, _key: 'suites' }),

  () => agent(
    `${MANDATE}\n\nRead the git history for tasks numbered 01 through 29 and report what actually landed.\n\nThe repo has 187 commits. Start with:\n    cd ${ROOT} && git log --oneline --no-decorate\n    cd ${ROOT} && git log --format='%h|%ad|%s' --date=short\n\nFor each task number 01..29, find the commit(s) that implemented it. Commit subjects in this repo\noften begin with the task number (e.g. "23 — the provider seam closes"). Use\n    git log --oneline --grep='<N>'\nand also read subjects directly, since some tasks landed under a descriptive subject with no number.\n\nFor each task, verify the attribution by opening the commit:\n    git show --stat <sha>\nand confirm the files touched are plausibly that task's work. A commit whose SUBJECT mentions a\ntask but whose DIFF touches only documentation did not implement it — say so.\n\nAlso report:\n- Every revert, drop, or reversal you can find (grep subjects for revert/drop/reverse/undo, and\n  read the diffs).\n- Commits that changed a status line in a task file WITHOUT touching code — these are status\n  edits, not work.\n- The date range of the history and the commit count per day.\n\nDo NOT read the task .md files for this — you are establishing what git says independently, so\nthat it can be cross-checked against the task files by a different agent.`,
    { label: 'evidence:git-01-29', phase: 'Evidence', schema: GIT_SCHEMA }
  ).then(r => r && { ...r, _key: 'git-a' }),

  () => agent(
    `${MANDATE}\n\nRead the git history for tasks numbered 30 through 54 and report what actually landed.\n\nSame method as the 01-29 pass:\n    cd ${ROOT} && git log --format='%h|%ad|%s' --date=short\n    git log --oneline --grep='<N>'\n    git show --stat <sha>\n\nPay particular attention to:\n- Task 47: there are TWO task files numbered 47 in this tree (one under tranche_seven, one under\n  tranche_eight). Determine from git which one(s) landed, and treat them as separate tasks\n  47-seven and 47-eight in your output.\n- Task 34: there appear to be duplicate task files numbered 34. Report what git says about it.\n- Tasks 48-54 (tranche nine) — what has landed, if anything.\n- The most recent commits: what is the current HEAD, what did it do, and is the tree clean?\n    git status --porcelain && git log -1 --stat\n\nAlso report:\n- Every revert, drop, or reversal.\n- Commits that only edited documentation status lines without touching code.\n- Whether any task number has NO commit attributable to it at all.\n\nDo NOT read the task .md files for this pass.`,
    { label: 'evidence:git-30-54', phase: 'Evidence', schema: GIT_SCHEMA }
  ).then(r => r && { ...r, _key: 'git-b' }),
])

const gt = groundTruth.filter(Boolean)
log(`Ground truth in: ${gt.map(g => g._key).join(', ')}`)

const stopped = gt.flatMap(g => (g.contradictions || []).map(c => `[${g._key}] ${c}`))
if (stopped.length) log(`${stopped.length} brief-contradiction(s) reported by code/evidence agents.`)

// Compact digest for the downstream phases.
const codeAreas = gt.filter(g => g.facts)
const digest = codeAreas.map(a =>
  `### AREA: ${a.area} (${a._key})\n${a.summary}\n\nFACTS:\n` +
  (a.facts || []).map(f => `- ${f.claim}  [${f.citation}]`).join('\n') +
  ((a.data_flow || []).length ? `\n\nDATA FLOW:\n` + a.data_flow.map(d => `- ${d.operation} ${d.store}  [${d.citation}]`).join('\n') : '') +
  ((a.llm_calls || []).length ? `\n\nLLM CALLS:\n` + a.llm_calls.map(l => `- ${l.site}  [${l.citation}] model:${l.model_selection || '?'}`).join('\n') : '') +
  ((a.dead_or_suspect || []).length ? `\n\nSUSPECT:\n` + a.dead_or_suspect.map(d => `- ${d.what}: ${d.why}  [${d.citation}]`).join('\n') : '')
).join('\n\n')

const suites = gt.find(g => g._key === 'suites')
const suiteLine = suites
  ? (suites.suites || []).map(s => `${s.name}: Ran ${s.ran}, ok=${s.ok}, fail=${s.failures ?? '?'}, err=${s.errors ?? '?'}, skip=${s.skipped ?? '?'} [${s.command}]`).join('\n')
  : 'test suites: NOT AVAILABLE — the suite agent failed. Do not quote any test count.'

const gitDigest = gt.filter(g => g.landed).flatMap(g => g.landed)
  .map(l => `- task ${l.task}: ${l.verdict} ${(l.commits || []).join(',')}${l.note ? ' — ' + l.note : ''}`).join('\n')

const GROUND = `
=== GROUND TRUTH ESTABLISHED FROM CODE (by other agents, all citations verified against the tree) ===
This is the reference you check documents against. It came from the code, not from any document.
If YOU find the code disagrees with anything below, that is itself a finding — report it in
\`contradictions\`.

${digest}

=== TEST SUITES, AS THE RUNNER PRINTED THEM ===
${suiteLine}

=== WHAT GIT SAYS LANDED ===
${gitDigest}
=== END GROUND TRUTH ===
`

log(`Ground-truth digest built: ~${Math.round(GROUND.length / 4)} tokens. Fanning out to tasks, docs and figures.`)

phase('Tasks')

const TASK_GROUPS = [
  { key: 'tranche-1-2-3', label: 'tasks:01-21', dirs: 'docs/tasks/refactor/tranche_one/, tranche_two/, tranche_three/', note: 'Tasks 04, 05 and 06 are MEASUREMENTS — their deliverable is a committed number with its method and date, not code. Task 02 produces a register, not fixes. Judge them on whether the number/register exists, is committed, and carries its method — not on whether code changed.' },
  { key: 'tranche-4-5-6', label: 'tasks:22-35', dirs: 'docs/tasks/refactor/tranche_four/, tranche_five/, tranche_six/', note: 'Task 22 is a timeboxed SPIKE whose deliverable is a decision, not merged code. Task 30 contains an experiment whose result decides the design. Task 29 is a labelling session whose deliverable is a report. Also: docs/tasks/refactor/34-documentation-cleanup.md and docs/tasks/refactor/tranche_six/34-documentation-cleanup.md BOTH exist — compare them and report whether they are the same file, a duplicate, or two different tasks.' },
  { key: 'tranche-7-8', label: 'tasks:36-47', dirs: 'docs/tasks/refactor/tranche_seven/, tranche_eight/', note: 'CRITICAL: there are TWO task files numbered 47 — tranche_seven/47-widen-the-c4-match-body.md (claims todo) and tranche_eight/47-split-the-entry-point.md (claims DONE). Treat them as separate tasks and say so explicitly. Several of these tasks are documentation-policy tasks whose done-ness is checkable by running backend/tools/audit-docs.py — run it and use the result as evidence.' },
  { key: 'tranche-9', label: 'tasks:48-54', dirs: 'docs/tasks/refactor/tranche_nine/', note: 'This is the CURRENT tranche. Task 49 is the task being executed right now by the agent that spawned you — report its state as of before this run. Be precise about what 48 actually did (git says it landed as HEAD~... — verify).' },
]

const docsPhase = await parallel([
  // --- Phase C: task-completion verification
  ...TASK_GROUPS.map(g => () => agent(
    `${MANDATE}

**EXCEPTION to rule 2 for you specifically:** you ARE assigned documents — the task files in
${g.dirs}. Read them. But read them as CLAIMS TO BE TESTED, never as facts. The Status line at
the top of a task file is a claim someone typed; your job is to check it against the tree.

${GROUND}

Your job: for EVERY task file in ${g.dirs}, determine whether it is genuinely done **by evidence
in the tree**, not by its status column.

Method, per task file:
1. Read the file completely, especially its **Definition of done** checklist.
2. For EACH Definition-of-done item, go find the evidence in the code / tests / git. Cite
   file:line or a command. An item you cannot verify is \`unverifiable\`, not \`yes\`.
3. Set \`evidence_status\` from the items, not from the Status line.
4. Set \`mismatch: true\` whenever the Status line and your evidence_status disagree — in EITHER
   direction. Tasks in this repo have been marked todo while done, and the reverse is equally
   available. Both are findings.
5. If work remains, describe it concretely in \`residual_work\`, and set \`blocked_on\` — the
   distinction between "needs more work" and "needs the owner / an account / a device" is a
   required output of this whole exercise.

${g.note}

Do not take a status line's word for anything. Do not mark something DONE because a commit
subject mentions its number — open the diff.`,
    { label: g.label, phase: 'Tasks', schema: TASKS_SCHEMA }
  ).then(r => r && { ...r, _key: g.key })),

  // --- Phase D: adversarial doc audit
  () => agent(
    `${MANDATE}

**EXCEPTION to rule 2:** you ARE assigned documents to audit adversarially.

${GROUND}

Audit these documents against the ground truth above and against the code directly:
  docs/tasks/refactor/AUDIT.md
  docs/tasks/refactor/HANDOFF.md
  docs/tasks/refactor/MASTER-PLAN-pursuit.md
  docs/tasks/refactor/STANDING-GUIDANCE.md

Method: go claim by claim. For every factual assertion — a file path, a line number, a count, a
percentage, a "this is done", a "this is how it works", a dependency arrow — go check it against
the code. Record every claim that the code does not support.

Specifically hunt for:
- Cited \`file:line\` references that no longer resolve (the file moved, the line moved, or the
  line says something else). Open them. This is the highest-yield check in the repo.
- Named files, scripts, tools or directories that DO NOT EXIST. Test each with ls.
- Counts (of tests, of tasks, of defects, of documents) that disagree with what the runner or the
  filesystem says. The test-suite numbers above came from the actual runner.
- Status claims that disagree with git.
- Figures quoted without their metric name or their n.
- Claims that contradict a DIFFERENT one of these four documents. Cross-reference them.
- Dependency/blocking arrows between tasks that the code shows are wrong or cyclic.

\`docs_read\`: report each file's real line count (wc -l) and its declared frontmatter \`kind:\`.
\`confirmations\`: count the claims you checked that DID hold — the ratio matters.

If you find zero disagreements, you did not look. These four documents total thousands of lines
written across many sessions and the tree has moved under them.`,
    { label: 'docs:roots', phase: 'Docs', schema: DOCS_SCHEMA }
  ).then(r => r && { ...r, _key: 'docs-roots' }),

  () => agent(
    `${MANDATE}

**EXCEPTION to rule 2:** you ARE assigned documents to audit adversarially.

${GROUND}

Audit these against the code:
  docs/ingest/*.md  (ats, builtin-nyc, contributor-api, DEFECTS, engagement-events, extract,
                     google-apify, google-serpapi, hn-hiring, match, nyc-open-data, score,
                     weworkremotely, workday)
  docs/RUNBOOK.md, docs/README.md

These purport to describe specific ingest scripts and pipeline stages. For each one, open the
script it describes and check it claim by claim: the endpoint, the auth, the table written, the
pagination, the rate limits, the failure behaviour, the field mapping.

Specifically hunt for:
- Frontmatter that declares \`script:\` or \`generated:\` when NO generator exists. Test it: does
  the named generator file exist? Run \`ls\` on it. A doc claiming to be generated by a script
  that was never written is a high-severity finding.
- \`code_at:\` / commit-pin frontmatter pointing at commits that do not contain the code they
  claim to pin. Check with \`git show <sha> --stat\`.
- Described behaviour that the script does not implement (dead sections describing removed code).
- Missing behaviour: script features with no doc coverage.
- docs/ingest/DEFECTS.md specifically: it is a defect register. For EVERY defect it lists as
  open, check whether the code still has the defect. For every one it lists as closed, check
  whether it is actually closed. Both directions are findings. Report the D-number for each.
- docs/RUNBOOK.md: every command it gives — does it run? Check paths and interpreters exist. Do
  NOT execute anything destructive or anything that hits a network or a database; just verify the
  paths, flags and interpreters are real.

\`docs_read\`: real line count and declared \`kind:\` for each.`,
    { label: 'docs:ingest-and-runbook', phase: 'Docs', schema: DOCS_SCHEMA }
  ).then(r => r && { ...r, _key: 'docs-ingest' }),

  () => agent(
    `${MANDATE}

**EXCEPTION to rule 2:** you ARE assigned documents to audit adversarially.

${GROUND}

Audit these against the code and the actual measurement artifacts:
  docs/MEASUREMENT-TRAPS.md, docs/scoring.md, docs/scoring-measured-2026-07-27.md,
  docs/score-validation.md, docs/labelling-report-2026-08-02.md,
  docs/ingestion_tests/*.md and the .json result files there,
  docs/facts-v3-diff.md, docs/role-track-derivation.md, docs/jsonld-coverage.md,
  docs/mock-acceptance.md, docs/pursuit-description-gate.md, docs/pursuit-gate-volume.md,
  docs/ats-token-discovery.md, docs/google-jobs-query-experiment.md, docs/jobspy-spike.md

For every measurement these documents report, check:
- Is the instrument that produced it still in the tree, and does it still compute what the doc
  says? Cite the instrument file:line.
- Is the n stated? Is the metric NAMED? A percentage without its metric name is unusable here —
  the code computes multiple distinct self-consistency metrics over the same run and they yield
  different correct percentages.
- Does the doc give a command that reproduces the figure from committed data? Check the command's
  paths and flags exist (read the argparse). Do not run anything that costs money or hits a
  network.
- Is the figure superseded by a later, larger-n measurement? Say which supersedes which and cite
  both.
- docs/MEASUREMENT-TRAPS.md: how many traps does it actually list? Count them by reading. Does it
  state its own count anywhere, and does the stated count match the real one?

\`docs_read\`: real line count and declared \`kind:\` for each.`,
    { label: 'docs:measurements', phase: 'Docs', schema: DOCS_SCHEMA }
  ).then(r => r && { ...r, _key: 'docs-measure' }),

  () => agent(
    `${MANDATE}

**EXCEPTION to rule 2:** you ARE assigned documents to audit adversarially. One of them is
\`.claude/CLAUDE.md\`, the project instruction file every session loads first. It is the
highest-leverage document in the repo: an error in it propagates into every future session.

${GROUND}

Audit, against the code:
  .claude/CLAUDE.md            <-- go through this one line by line, it is the priority
  docs/DOCS-POLICY.md
  docs/WORKING-METHOD.md
  docs/tasks/refactor/DECISIONS.md
  docs/tasks/refactor/OPEN-QUESTIONS.md
  docs/tasks/refactor/API-CONTRACT-v1.md
  docs/tasks/refactor/CLAUDE_UPDATES.md
  docs/tasks/refactor/SOURCING-STRATEGY.md
  README.md, backend/README.md, deploy/README.md, docs/archive/README.md

For .claude/CLAUDE.md specifically, test EVERY assertion:
- every command it gives — do the paths, flags and interpreters exist? Run the read-only ones.
- every file/script/tool it names — \`ls\` each one. It explicitly claims some things do NOT exist
  ("there is no tools/ at the repo root", "there is no tools/lib-parity.sh"); verify those
  negative claims too, in both directions.
- every architectural invariant it states — verify against the code, do not assume.
- every figure it quotes — is the metric named, is the n stated, does the instrument agree?
- the ports it names, the venv claims, the dependency claims, the "three suites" claim.
- claims about what is built vs not built in the frontend.
- its strikethrough/superseded passages: is the superseding claim itself still true?

For docs/DOCS-POLICY.md: it claims N rules each with a script or marked unenforced. Count the
rules, find each rule's enforcing check in backend/tools/audit-docs.py (read the check names),
and report every rule with NO enforcement that is not marked unenforced, and every check in the
script with no corresponding rule.

For DECISIONS.md and OPEN-QUESTIONS.md: sample at least 15 decisions/questions and check each
against the code. Report every decision recorded as made whose code does not reflect it, and
every question recorded as open that the code has already answered.

For API-CONTRACT-v1.md: diff it against the routes actually served (see ground truth above and
read backend/webapp/app.py and backend/api/app.py directly). Report every route in the contract
not served, and every route served not in the contract.`,
    { label: 'docs:claude-md-and-policy', phase: 'Docs', schema: DOCS_SCHEMA }
  ).then(r => r && { ...r, _key: 'docs-claudemd' }),

  // --- Phase E: figures census
  () => agent(
    `${MANDATE}

**EXCEPTION to rule 2:** you are assigned a repo-wide sweep that includes documents.

${GROUND}

Build a complete census of **every figure in circulation in this repo**, with its instrument.

The motivating problem, stated precisely: this repo runs a self-consistency evaluation and the
code computes SEVERAL DISTINCT METRICS over the same run. Different correct percentages for the
same run circulate in different documents, and a percentage quoted without its metric name is a
rumour with a decimal point. Your output must make it impossible to confuse them.

Method:
1. FIRST, find the instruments. Read backend/evals/metrics.py and everything it is called from.
   Enumerate every metric the code computes, with its exact identifier as it appears in the
   source, its formula from the implementation, and its file:line. Do this from the CODE before
   you read any document, so the document numbers get matched to real metrics rather than the
   reverse.
2. Read the committed result artifacts — the JSON files under docs/ingestion_tests/ and anything
   under backend/evals/ — and record the metric values verbatim from the data, with their n,
   date, model and the JSON key path.
3. THEN sweep the repo for quoted figures:
       cd ${ROOT} && grep -rnE '[0-9]+\\.[0-9]+%|[0-9]{2,}%|n=[0-9]+' --include='*.md' . | head -300
   plus the same over .py and .json. Expect many hits; triage to the ones that are claims about
   system behaviour or model quality.
4. For each figure: which metric is it, which run produced it, is it current or superseded, which
   single document OWNS it, and everywhere else it appears.

Flag as \`orphan-no-instrument\` any figure you cannot trace to code that computes it.
Flag as \`superseded\` any figure replaced by a later or larger-n run, and name the successor.
Flag as \`contradicted\` any figure that disagrees with another quotation of the same measurement.

Include non-model figures too: test counts, task counts, defect counts, document counts, volume
floors, cost/quota numbers, coverage percentages, line budgets. For each, name the instrument
that produces it (a command, a script) or mark it as having none.

Be exhaustive. This census is a deliverable in its own right.`,
    { label: 'figures:census', phase: 'Figures', schema: FIGURES_SCHEMA }
  ).then(r => r && { ...r, _key: 'figures' }),
])

const second = docsPhase.filter(Boolean)
log(`Second wave in: ${second.map(s => s._key).join(', ')}`)

// Collect the disagreement list and verify it adversarially.
const allDisagreements = second.filter(s => s.disagreements).flatMap(s =>
  s.disagreements.map((d, i) => ({ ...d, _src: s._key, _id: `${s._key}#${i}` })))

log(`${allDisagreements.length} candidate doc/code disagreements collected. Verifying the high- and medium-severity ones adversarially.`)

phase('Verify')

const toVerify = allDisagreements
  .filter(d => d.severity === 'high' || d.severity === 'medium')
  .slice(0, 24)

if (allDisagreements.length > toVerify.length) {
  log(`NOTE: ${allDisagreements.length - toVerify.length} low-severity or overflow disagreements are reported UNVERIFIED and labelled as such. Nothing was silently dropped.`)
}

const verdicts = await parallel(toVerify.map(d => () =>
  agent(
    `${MANDATE}

You are a SKEPTIC. Another agent claims a document in this repo contradicts the code. Your job is
to **REFUTE** it. Default to \`refuted: true\` if you are uncertain — a false disagreement that
survives into the final report is worse than a missed one, because it will be acted on.

THE CLAIM:
  Document says (${d.doc}): "${d.doc_claim}"
  Agent asserts the code says: "${d.code_says}"
  Agent's citation: ${d.code_citation}
  Claimed kind: ${d.kind || 'unspecified'} / severity: ${d.severity}

Do this:
1. Open the document at the cited location. Does it actually say that? Quote it. Agents
   paraphrase and paraphrases drift. If the doc does not say what is claimed, refute.
2. Open the cited code location. Does it actually say what the agent claims? If the citation is
   wrong or the line has moved, that alone is grounds to refute — but check whether the claim is
   true at a DIFFERENT location before refuting, and if so supply the corrected citation.
3. Look for the charitable reading. Is the doc claim strikethrough'd, marked superseded, scoped
   to a date, hedged, or explicitly labelled as historical? A doc that says "~~X~~ superseded by
   Y" is NOT claiming X. Check the surrounding lines, not just the cited one.
4. Look for a THIRD location that reconciles them — a wrapper, an alias, a re-export, a config
   value, a different code path that makes the doc right after all.
5. Only if the disagreement survives all four: confirm it (\`refuted: false\`) and set
   \`severity_adjusted\` on the evidence you actually saw.

If the claim is partly right, set \`refuted: false\` and put the accurate, narrower version in
\`corrected_claim\` with a citation you personally verified.`,
    { label: `verify:${(d.doc || 'doc').split('/').pop().slice(0, 30)}`, phase: 'Verify', schema: VERDICT_SCHEMA }
  ).then(v => ({ ...d, _verdict: v }))
))

const checked = verdicts.filter(Boolean)
const confirmed = checked.filter(x => x._verdict && x._verdict.refuted === false)
const refuted = checked.filter(x => x._verdict && x._verdict.refuted === true)
const unverified = allDisagreements.filter(d => !toVerify.includes(d))

log(`Verified: ${confirmed.length} confirmed, ${refuted.length} refuted, ${unverified.length} reported unverified.`)

phase('Synthesize')

const payload = {
  code_areas: codeAreas,
  brief_contradictions: stopped,
  suites: suites ? suites.suites : null,
  suite_notes: suites ? suites.notable : null,
  git: gt.filter(g => g.landed).map(g => ({ key: g._key, landed: g.landed, timeline: g.timeline, reverts: g.reverts_and_drops })),
  tasks: second.filter(s => s.tasks).flatMap(s => s.tasks),
  figures: second.find(s => s._key === 'figures') || null,
  docs_read: second.filter(s => s.docs_read).flatMap(s => s.docs_read),
  disagreements_confirmed: confirmed.map(c => ({ doc: c.doc, doc_claim: c.doc_claim, code_says: c.code_says, code_citation: c.code_citation, severity: c._verdict.severity_adjusted || c.severity, kind: c.kind, corrected: c._verdict.corrected_claim, verifier_note: c._verdict.reason })),
  disagreements_refuted: refuted.map(r => ({ doc: r.doc, doc_claim: r.doc_claim, why_refuted: r._verdict.reason })),
  disagreements_unverified: unverified.map(u => ({ doc: u.doc, doc_claim: u.doc_claim, code_says: u.code_says, code_citation: u.code_citation, severity: u.severity })),
  counts: { candidates: allDisagreements.length, verified: checked.length, confirmed: confirmed.length, refuted: refuted.length, unverified: unverified.length },
}

const report = await agent(
  `${MANDATE}

You are writing the FINAL REPORT for task 49 — "rebuild the understanding of this system from the
code, not from the documents."

**You are NOT writing docs/STATE-OF-THE-SYSTEM.md.** The human will write that themselves from
your report. Do not create any file. Return the report as your text output. Do not use the
StructuredOutput tool; return prose+markdown.

Below is the complete output of ~20 agents that read the code, ran the three test suites, read
187 commits, checked every task file against the tree, and audited the documentation
adversarially against what the code says. Disagreements were then handed to skeptics instructed
to refute them; only survivors are in \`disagreements_confirmed\`.

YOUR JOB: synthesise, cross-check, and be honest about what is not known.

Cross-checking is the part that matters. Before you write anything:
- Where two agents describe the same thing, do they agree? Where they DISAGREE, say so
  explicitly and name both citations rather than picking one. An unresolved conflict between two
  readers is a finding, not something to smooth over.
- Where a task agent says DONE and a git agent found no commit, flag it.
- Where a figure appears with different values in different agents' output, flag it.
- Do not invent a citation. If a claim in the data below has no citation, either drop it or mark
  it "uncited — needs checking". Never manufacture a file:line.

Structure the report in exactly these seven sections:

**0. How this was produced, and what to distrust** — the method in a short paragraph; then the
   agents' own \`brief_contradictions\` (facts asserted in briefs that the code refuted); then
   the cross-reader conflicts you found; then what this pass could NOT establish and why.

**1. What the pipeline does today** — the four stages, what each reads and writes, what gates
   each, what costs an LLM call, and what the nightly run actually executes step by step. Every
   claim cited. Where the code contradicts a stated architectural invariant, say so here.

**2. What the surfaces are** — three processes, three interpreters, three suites; ports, venvs,
   env files, what imports what; the frontend: what it serves and what it does not. Include the
   real \`Ran N tests\` figures with their commands, and the skip counts.

**3. What is genuinely done** — by evidence. A table: task, claimed status, evidence status,
   the evidence. Then a separate short list of every MISMATCH in both directions, since those are
   the reason this task exists. Include the duplicate task numbers (34, 47).

**4. What is genuinely open** — split into two lists that must not be merged:
   **(a) needs work** — concrete, someone could pick it up; say what and where.
   **(b) needs the owner** — needs a decision, an account, a device, a payment, or a person.
   List (b) must be complete and specific enough to hand to task 53 unedited: each entry names
   the decision or resource required and what is blocked behind it. This is the most
   operationally valuable section; do not compress it.

**5. What the documents claim that the code does not support** — the confirmed disagreement
   list, ordered by severity, each with the doc quote, the code citation, and the verifier's
   note. Then a short subsection of the UNVERIFIED candidates, clearly labelled as unverified so
   nobody acts on them as if they were checked. Then the refuted candidates in one line each, so
   the next session does not re-raise them. Give the counts.

**6. Every figure in circulation, with its instrument** — a table: value, what it measures, the
   EXACT metric name from the code, the instrument's file:line, n, date, the command that
   reproduces it, which document owns it, everywhere else it appears, and status
   (current/superseded/orphan/contradicted). The self-consistency metrics get their own
   sub-table with the distinct metric names spelled out, because the whole point is that a number
   without its metric name is unusable.

Rules for the writing:
- \`file:line\`, repo-relative, on every claim. That is what makes this trustworthy.
- Where the evidence is thin, say "thin evidence" and say what would settle it.
- Do not hedge on things the agents established with citations. State them plainly.
- Length: this replaces a corpus. Be complete rather than brief — but every sentence must carry
  a fact, a citation, or an explicit uncertainty. No throat-clearing, no restating the task, no
  recommendations about what to do next (that is tasks 50-54's job, not this one's).

THE DATA:
${JSON.stringify(payload, null, 1)}`,
  { label: 'synthesize:report', phase: 'Synthesize', effort: 'xhigh' }
)

return {
  report,
  counts: payload.counts,
  agents_reporting: gt.length + second.length + checked.length + 1,
  brief_contradictions: stopped,
}