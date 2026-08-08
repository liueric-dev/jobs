---
paths:
  - "backend/**/*.py"
---

# SQL landmines

**Postgres word boundary is `\y`, not `\b`.** In Postgres `\b` is BACKSPACE, so a `\b` pattern
silently matches nothing and quietly demotes everything it was meant to catch. This is why
`relevance.py` compiles `config/relevance.json` patterns to `\y`-bounded Postgres regexes rather
than reusing Python's `re` module, which would disagree with it silently on exactly this class of
pattern.

**A SQL fragment splices ahead of `WHERE`, and its bound params must lead.** `relevance.py`'s
`tier_sql`/`union_sql` build fragments meant to be spliced into a larger query textually before
that query's own `WHERE` clause; the fragment's own `%s` placeholders are positional and must be
supplied first, ahead of the caller's own params. `backend/webapp/jobs.py:303-324` is the worked
example of getting this right.

**Identifiers are spliced by f-string, and that is constants-only.** Table and column names in this
tree are interpolated with f-strings rather than `psycopg.sql.Identifier` — safe only because every
site splices a module-level `ALL_CAPS` constant, a fixed string literal, or `relevance.py`'s own SQL
compiler output, never a request parameter, a config value, or ATS/employer/labeller data. `T-16`
(`TASKS.md`) is the audit that walked all 113 sites in the tree individually and confirmed this
holds; each non-test site carries a `# noqa: S608` naming what it splices. If you add a new spliced
identifier, it must be a constant too — a runtime string here is the vulnerability this convention
exists to avoid.

**A `# noqa` on the opening line of an unterminated triple-quoted f-string is inert.** It becomes
part of the string rather than a comment, and it fails silently — nothing warns you, and `RUF100`
cannot see it either. `ruff` reports the finding at the line the statement *starts* on, which is
often not a line a directive can live on. **Put the directive on the line the string closes.** That
is why some sites in this tree carry the comment somewhere other than the row `ruff` prints; it is
deliberate, confirmed empirically while writing `T-16`'s 92 directives, and not a formatting slip
to tidy up.
