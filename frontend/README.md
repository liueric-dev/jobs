# frontend/

Frozen API fixtures. No application code yet — task 32 builds against these.

`docs/tasks/refactor/API-CONTRACT-v1.md` § *Mocking* asks for one realistic
response per endpoint, frozen as JSON, so the client can be built before the
backend lands and so the fixtures become contract tests both sides run
afterwards. This is that, split in two, because the frozen contract and the
shipped API genuinely differ and **that difference is the frontend's whole
problem**.

```
fixtures/shipped/    what GET /v1/jobs returns TODAY. Derived from the code.
fixtures/contract/   the target shape in API-CONTRACT-v1.md. Derived from the doc.
verify_fixtures.py   re-derives every shape claim in shipped/ from the source.
```

Build the client's types against `contract/`. Build the client's **parser**
against `shipped/`, because that is what the server sends.

## Real vs aspirational

| endpoint | route today | fixture set |
|---|---|---|
| `GET /v1/jobs` | yes, `jobs.py:336` | both — shapes differ |
| `GET /v1/jobs/{id}` | yes, `jobs.py:440` | both — shapes differ |
| `POST /v1/events` | yes, `jobs.py:753` | both — **request shapes agree** |
| `GET /v1/me` | yes, `auth.py:450` | both — contract adds an onboarding block |
| `GET /v1/searches` | **no route, no table** | `contract/` only |
| `POST /v1/searches` | **no route, no table** | `contract/` only |
| `POST /v1/onboarding` | **no route, no table** | `contract/` only |

Every aspirational file is named `ASPIRATIONAL_*`. `search_queries` and
`builder_profiles` exist nowhere in `schema.py` or `schema_web.py` — these three
are not "unimplemented endpoints", they are a feature with no storage.

Everything in `shipped/` is real, has a route today, and is checked by
`verify_fixtures.py`. Nothing in `contract/` is checked by anything, because
there is no code to check it against.

## Verifying and regenerating `shipped/`

```bash
python3 frontend/verify_fixtures.py      # exit 0 if the fixtures still match the code
```

Stdlib only, no venv — it reads the constants out of
`backend/webapp/{jobs,auth,schema_web}.py` with `ast` rather than importing
them, because those modules import `fastapi` and `pydantic`, which live only in
`webapp/.venv`.

It checks **shape**, not values: the exact key set and order of every job
object, the top-level keys of every response, the event vocabulary, the dismiss
vocabulary, that `rank` runs 1..N across the two pages, that `next_cursor`
really decodes to the last row of page one, and that every error `code` is one
`jobs.py` can actually raise. It does not check that Mount Sinai is hiring.

There is no generator. Regenerating means editing the JSON by hand and running
the verifier — which is the honest arrangement, and the one
`.claude/CLAUDE.md` describes for `docs/ingest/*.md`: treat "never hand-edit" as
applying to a generator that exists, and here there is none.

`fixtures/shipped/MANIFEST.json` records the `file:line` every shape was derived
from, one entry per fixture. It is a sidecar rather than a `_comment` key inside
each fixture on purpose: those bodies are byte-faithful, and an extra key would
be a lie in the shape of documentation.

## Three contract fields are BLOCKED, not merely unimplemented

The gap between the two directories is mostly work nobody has done yet. Three
items are different — they are waiting on something, and no amount of frontend
work moves them. **One of the three had its blocker removed on 2026-08-01,
while these fixtures were being written**; it is recorded below as it now
stands, not as it was.

**`bucket` — blocked on task 30, which is itself gated on task 29's labels.**
Task 30 contains the within-band experiment that decides whether a numeric
score is ever justified; until it runs there is no defensible way to draw the
`strong` / `worth_a_look` / `stretch` boundaries. Task 29 needs a second
labeller before 30 has anything to run on. Guessing thresholds here would
produce a field that looks authoritative and is arbitrary. **Still blocked.**

**Removing raw `match_score` / `fit_score` — blocked on `bucket` existing
first.** The contract says *"no 0–100 score appears anywhere; `bucket` carries
the claim"*. `bucket` does not exist, so removing the raw scores now would leave
the API unable to express relevance at all — strictly worse than the
divergence. This is a deferral with a named blocker, not a decision, and it is
decided by task 30 landing. `min_score` is a public query parameter today for
the same reason. **Still blocked**, transitively on the one above.

**`cohort_signal` — the blocker was `job_events` having no `app_user_id`
column, and that column landed 2026-08-01. Now unblocked and unbuilt.** The
contract requires suppression below three saves, and "three *Builders*" was not
a question `job_events` could answer: it had a `profile` and no user id, and
thirty Builders share the one `pursuit` profile, so counting distinct rows
counted one person's three saves as three people's — a privacy control
returning a wrong answer, which is worse than returning `null`. Defects **D66**
and **D67** in `docs/ingest/DEFECTS.md` were the same missing column surfacing
in `state.seen` and `state.applied`, and both are now **fixed**: the join
resolves by `app_user_id` (`jobs.py:286-291`), `POST /v1/events` writes it, and
pre-column rows carry NULL and resolve to `false` for everyone rather than
`true` for everyone. **Task 28 itself is still unbuilt** — nothing computes the
`3-5` / `6-10` buckets or enforces the below-three suppression, so
`cohort_signal` is `null` in every `shipped/` fixture because the field does not
exist at all, not because the count was low.

If you are reading this well after 2026-08-01, check `docs/ingest/DEFECTS.md`
and `docs/tasks/refactor/HANDOFF.md` rather than trusting this section. The
blocked/unblocked status of a field is the fastest-rotting sentence in this
file.

Everything else the contract adds — `tracks[]`, `posting_age_days`,
`apply_url`, `description_html`, `closes_at`, `source{}`, and the nesting of
`comp{}` / `why{}` / `state{}` / `facts{}` — is task 32's, and is unblocked.

## Things a client author will get wrong if nobody says them

- **The event for an application is `applied`, not `apply`** (`DEC-73`).
  `job_events` is append-only with `SELECT, INSERT` and nothing else; the
  existing rows already say `applied` and are the only part of the disagreement
  that cannot be edited, so the code won and the contract moved. A client
  sending `apply` gets a 400 — see
  `shipped/errors/400_unknown_event.json`, which is that exact response.
- **`skip` is server-derived.** Sending it is a 400 with code
  `server_derived_event`, deliberately not `unknown_event`: the mistake is a
  category error, not a typo.
- **`request_id` and `rank` already ship.** Several documents say they do not;
  they landed with task 27 (`jobs.py:370`, `:424`, `:432`). `rank` is 1-based and global
  across the render, and it *continues across pages* — the render id and the
  next rank ride inside the opaque cursor, so page two starts at 5, not 1.
  A cursor issued before task 27 is a 400, not an upgrade.
- **Four fields arrive as JSON strings, not arrays.** `match_reasons`,
  `tech_stack`, `risk_factors` and `key_technologies` are TEXT columns holding
  `json.dumps(...)` output and the endpoint does not parse them. `JSON.parse`
  each one. The contract's `why.risk_factors` is a real array; the shipped
  `risk_factors` is `"[\"…\"]"`.
- **Two error shapes, not one.** The contract's `{"error": {code, message,
  request_id}}` envelope is registered for `ContractError` alone (`app.py:93`).
  A 401, a 403, a 404 and a malformed cursor come back as FastAPI's
  `{"detail": "…"}`. Both are in `shipped/errors/`; the second group is
  prefixed `NOT-ENVELOPED-`.
- **The shipped `state` has five fields, not three.** `seen` and
  `dismiss_reason` are there too, and all five are per-Builder as of
  2026-08-01. The detail endpoint deliberately does *not* hide a dismissed
  posting — undo has to be reachable — so
  `GET_v1_jobs_by_id.dismissed.json` is the state the undo flow renders from.
- **The profile is `pursuit`**, not the contract's `pursuit-cohort-2026a`, and
  job ids are 24-char sha256 prefixes (`lib/ids.py:33,36`), not the contract's
  illustrative `gh_acme_4821`.
- **An unscored posting is normal.** `jobs_app` LEFT JOINs `job_scores` and
  scoring is budget-limited, so `fit_score`, `primary_track`,
  `gap_bridging_angle`, `risk_factors` and `key_technologies` are all null
  together on a posting the nightly run has not reached. Render the row anyway.
- **`comp.is_estimated` must be honoured.** Adzuna predicts salary; showing a
  prediction as though the employer stated it is a trust problem, not a
  formatting one.
- **The track vocabulary is undecided.** The contract's one example,
  `ai_operations`, is a `role_archetype` value in `config/pursuit-criteria.json`,
  not a track. The only track vocabulary in the code is `score.TRACKS`
  (`score.py:281-282`). The `contract/` fixtures slugify those and put the
  stored Title Case in `label`; whoever implements task 32 has to actually
  decide this.

## Not covered here

`POST /v1/auth/logout` and the whole `/v1/label*` surface are implemented and
outside API-CONTRACT-v1.md. The eight `GET /v1/jobs` query parameters — `limit`,
`cursor`, `q`, `remote`, `nyc`, `min_score`, `since`, `include_dismissed` — are
implemented and undocumented in the contract; `include_dismissed` is for
debugging and is not part of the client contract (`jobs.py:346`, `:362-364`).
`Accept: application/vnd.jobs.v1+json` is in the contract and is not read
anywhere in `webapp/`.
