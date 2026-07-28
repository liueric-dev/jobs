"""The labelling surface: a web page a Builder can use, and nothing else.

WHY THIS IS A SERVER-RENDERED PAGE AND NOT A JSON ENDPOINT
    Labels come from ~10 Builder volunteers (task 29), not from the person who
    wrote the harness. `docs/ingestion_tests/03-metrics-and-golden-set.md:101`
    specifies a CLI --

        python3 -m evals label --corpus ... --n 30

    -- which is correct for the author and useless for a volunteer. It needs a
    checkout, a Python, a DATABASE_URL and a terminal.

    A JSON API would not fix that on its own. `frontend/` in this repo contains
    one file and it is `.gitkeep`, so there is nothing to render a form. Until
    that changes, an endpoint returning JSON is reachable by curl and by
    nobody else. So this module returns HTML: a `<form>`, a POST, a redirect to
    the next posting. No JavaScript at all, no build step, no framework, no
    external asset -- which also means it keeps working when frontend/ is
    eventually filled with something that has an opinion.

WHY THIS IS IN webapp/ AND NOT api/
    `07-metrics-and-golden-set.md:53` says to reuse the existing auth "since
    Google SSO and sessions already exist". They do -- in THIS package
    (auth.py), not in `api/`. `api/` is the contributor work queue: bearer
    tokens hashed in `api_keys` (api/app.py:159), a caller assumed hostile, and
    a `jobs_api` role deliberately granted nothing on any pipeline table.
    Putting a browser session flow there would relax the one property three
    sections of its README exist to defend. See this package's README, "Why
    this is not part of ../api/".

NO JAVASCRIPT MEANS THE CSRF STORY IS THE SAME ONE /v1/events HAS
    The session cookie is SameSite=Lax (auth.py:425), so a browser does not
    attach it to a cross-site POST. A form on someone else's page therefore
    submits unauthenticated and is rejected by require_user. That is the same
    argument README's "Known gaps" already makes for POST /v1/events; a token
    would be belt-and-braces here too.

THE ALLOWLIST IS STILL THE ACCESS CONTROL
    Any active `app_users` row may label. Task 29's ten Builders are ten
    `manage_app_users.py add` invocations and nothing else. A Google login for
    an address with no row is 403 and creates nothing -- unchanged.

WHAT IS RECORDED AS THE LABELLER IS app_users.id, NOT THE EMAIL
    The eval tables are analysis data that gets exported, diffed and quoted.
    An opaque id is enough to compute inter-annotator agreement, which is the
    only thing the identity is for, and it keeps a volunteer's address out of
    every JSONL this produces.

THIS MODULE CANNOT WRITE A MODEL'S ANSWER
    Every value goes through evals.labels.validate() and every row carries the
    signed-in user's id as labeller_id. There is no batch route, no import, no
    seed and no default. An unlabelled field is submitted as an abstention or
    not at all.
"""

import html
import logging
import urllib.parse

import config  # noqa: F401  (must come first -- performs the sys.path insert)

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from auth import User, require_user
from db import db

from evals import labels as labels_mod

log = logging.getLogger("webapp.label")

router = APIRouter()

#: Enough of the posting for a human to answer the questions. The full
#: description_text is shown deliberately -- 03-metrics-and-golden-set.md:127
#: is explicit that the point is a human judgement on THE SAME INPUT THE MODEL
#: GOT, and a `summary` would be showing them the model's reading of it instead.
_DETAIL_COLUMNS = ("id", "title", "company_name", "location_raw", "platform",
                   "description_text")


#: Hard cap on the request body. The form is six short fields and two ids, so
#: a legitimate submit is a few hundred bytes. Enforced BEFORE parsing, the
#: same argument api/app.py:284 makes: a hostile body should be rejected on
#: sight, not after being deserialized into memory.
MAX_FORM_BYTES = 64 * 1024


async def _form(request):
    """Parse an urlencoded form body with the standard library.

    NOT `await request.form()`. Starlette routes that through python-multipart,
    which this service does not have and which is a dependency added to a
    browser-facing process to parse a format `urllib.parse` has handled since
    forever. The form below carries no file upload and no `enctype`, so the
    browser sends `application/x-www-form-urlencoded` and this is the whole
    parser. This package has form previously declined a dependency it did not
    need (README, "The one place a dependency was not added"); this is the
    same call, with much less at stake.
    """
    raw = await request.body()
    if len(raw) > MAX_FORM_BYTES:
        raise HTTPException(status_code=413, detail="payload too large")
    ctype = (request.headers.get("content-type") or "").split(";")[0].strip()
    if ctype and ctype != "application/x-www-form-urlencoded":
        raise HTTPException(status_code=415,
                            detail="expected application/x-www-form-urlencoded")
    return dict(urllib.parse.parse_qsl(raw.decode("utf-8", "replace"),
                                       keep_blank_values=True))


def _job(conn, job_id):
    """Read `jobs`, NOT the `jobs_app` view that jobs.py uses.

    Two reasons, and neither is a relaxation of the tenancy rule. First, two
    of the three strata are rows `jobs_app` cannot return -- a gate-rejected
    posting has no `job_facts` row, and the view exists to join one. A form
    that could only show surfaced rows would silently drop the strata that
    make recall estimable, which is the whole point of the sample.

    Second, axis A is profile-independent by construction, so there is no
    per-profile view of it to scope to. What bounds what a labeller can see is
    membership of the eval set (checked in submit_label), not a profile.
    """
    cols = ", ".join(_DETAIL_COLUMNS)
    row = conn.execute(
        f"SELECT {cols} FROM jobs WHERE id = %s", (job_id,)).fetchone()
    return dict(zip(_DETAIL_COLUMNS, row)) if row else None


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

#: Inline, because there is no static file route in this service and adding
#: one to serve nine rules would be the larger change. Sized for reading a job
#: description on a phone, since that is where a volunteer will actually do
#: this.
_CSS = """
:root { color-scheme: light dark; }
body { font: 16px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
       margin: 0 auto; max-width: 44rem; padding: 1.5rem 1.1rem 5rem; }
h1 { font-size: 1.2rem; margin: 0 0 .2rem; }
.meta { color: #767676; font-size: .9rem; margin-bottom: 1.2rem; }
.desc { border: 1px solid #8884; border-radius: 8px; padding: .9rem 1rem;
        max-height: 28rem; overflow-y: auto; white-space: pre-wrap;
        font-size: .93rem; }
fieldset { border: 0; border-top: 1px solid #8884; margin: 1.6rem 0 0;
           padding: 1rem 0 0; }
legend { font-weight: 600; padding: 0; }
label.opt { display: block; padding: .42rem .1rem; }
button { font-size: 1rem; padding: .7rem 1.4rem; border-radius: 8px;
         border: 1px solid #8886; cursor: pointer; margin-top: 1.5rem; }
.progress { color: #767676; font-size: .9rem; margin-bottom: 1rem; }
.hint { color: #767676; font-size: .87rem; margin: .1rem 0 .5rem; }
"""


def _page(title, body):
    return HTMLResponse(
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        f"<title>{html.escape(title)}</title><style>{_CSS}</style></head>"
        f"<body>{body}</body></html>")


def _render_form(job, question_list, label_set, done, total, overlap):
    e = html.escape
    parts = [
        f"<div class=progress>{done} of {total} done"
        + ("  &middot; shared posting" if overlap else "") + "</div>",
        f"<h1>{e(job.get('title') or '(no title)')}</h1>",
        # Escaped per field and joined afterwards, so the separator survives
        # as markup and nothing from the corpus ever can. Postings are
        # scraped HTML from seven sources; treating any of it as trusted here
        # would be stored XSS against the one page volunteers are sent to.
        "<div class=meta>" + " &middot; ".join(
            e(str(x)) for x in (job.get("company_name"),
                                job.get("location_raw"),
                                job.get("platform")) if x) + "</div>",
        f"<div class=desc>{e(job.get('description_text') or '(no description)')}</div>",
        "<form method=post action='/v1/label'>",
        f"<input type=hidden name=job_id value='{e(job['id'])}'>",
        f"<input type=hidden name=label_set value='{e(label_set)}'>",
    ]
    for q in question_list:
        parts.append(f"<fieldset><legend>{e(q.prompt)}</legend>")
        if q.axis == labels_mod.AXIS_A:
            parts.append("<p class=hint>Answer from what the posting says, "
                         "not from what you think the job is really like.</p>")
        else:
            parts.append("<p class=hint>Your own view. There is no right "
                         "answer to this one.</p>")
        name = f"{q.axis}:{q.field}"
        for choice in q.choices:
            cid = e(f"{name}:{choice}")
            parts.append(
                f"<label class=opt for='{cid}'>"
                f"<input type=radio id='{cid}' name='{e(name)}' "
                f"value='{e(choice)}'> {e(choice.replace('_', ' '))}</label>")
        # The abstention is an option on the form, always, and is checked by
        # default on nothing. A labeller with no way to say "I cannot tell"
        # guesses, and a guess recorded as a label is exactly the failure this
        # whole table exists to avoid.
        parts.append(
            f"<label class=opt for='{e(name)}:unsure'>"
            f"<input type=radio id='{e(name)}:unsure' name='{e(name)}' "
            f"value='unsure'> I can't tell from this posting</label>")
        parts.append("</fieldset>")
    parts.append("<button type=submit>Save and next</button></form>")
    return _page("Label a job", "".join(parts))


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------

@router.get("/v1/label", response_class=HTMLResponse)
def label_form(request: Request):
    """The page. Redirects to Google rather than 401ing on a signed-out user.

    A 401 is right for /v1/jobs, which a frontend calls and handles. This is a
    URL a volunteer pastes into a browser from an email, and the correct
    response to "not signed in" there is to sign them in.
    """
    try:
        user = require_user(request)
    except HTTPException as e:
        if e.status_code == 401:
            return RedirectResponse("/v1/auth/login?next=/v1/label",
                                    status_code=302)
        raise

    with db() as conn:
        label_set = labels_mod.active_set(conn)
        if not label_set:
            return _page("Nothing to label", _NO_SET)
        item = labels_mod.next_item(conn, label_set, user.id)
        done, total = labels_mod.progress(conn, label_set, user.id)
        if item is None:
            return _page("All done", _ALL_DONE.format(total=total))
        job = _job(conn, item["job_id"])

    if job is None:
        # The set names a job id the corpus no longer has. Not fatal and not
        # silently skipped either: a set whose rows are disappearing is a set
        # whose digest no longer describes what anyone labelled.
        log.warning("label set %s references missing job %s",
                    label_set, item["job_id"])
        return _page("Posting unavailable", _MISSING_JOB)

    return _render_form(job, labels_mod.questions(), label_set, done, total,
                        item["overlap"])


@router.post("/v1/label")
async def submit_label(request: Request, user: User = Depends(require_user)):
    """Record one person's answers about one posting, then show the next.

    The form is read from the raw body rather than declared as typed
    parameters because the question set comes from evals.labels.questions(),
    which reads its vocabulary from extract.py -- so the field names are not
    known at import time and pinning them here would be the copy that drifts.
    See _form() for why that is stdlib parsing rather than request.form().

    303, not 302: this is POST-then-redirect, and 303 is the status that tells
    the browser to follow it with GET. A back button on a 302 re-submits.
    """
    form = await _form(request)
    job_id = (form.get("job_id") or "").strip()
    label_set = (form.get("label_set") or "").strip()
    if not job_id or not label_set:
        raise HTTPException(status_code=400, detail="missing job_id or label_set")

    with db() as conn:
        # The posting must be in the set. Without this, a hand-crafted POST
        # could put labels on arbitrary job ids and quietly widen the eval set
        # past the one its digest pins.
        in_set = conn.execute(
            "SELECT 1 FROM eval_label_items WHERE label_set = %s AND job_id = %s",
            (label_set, job_id)).fetchone()
        if not in_set:
            raise HTTPException(status_code=404,
                                detail="that posting is not in this label set")

        written = 0
        for q in labels_mod.questions():
            raw = form.get(f"{q.axis}:{q.field}")
            if raw is None:
                # Not answered at all. Distinct from an abstention, and NOT
                # written: an unanswered question is missing data, and
                # recording it as "I can't tell" would invent a judgement.
                continue
            try:
                # profile comes from the SESSION, never from the form. That is
                # the same tenancy rule jobs.py:5 states, and here it is also
                # what keeps axis B rows attributable to a cohort.
                written += bool(labels_mod.record(
                    conn, axis=q.axis, job_id=job_id, field=q.field,
                    value=raw, labeller_id=user.id, label_set=label_set,
                    profile=user.profile if q.axis == labels_mod.AXIS_B
                            else None))
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
        conn.commit()

    log.info("%d label(s) from %s on %s", written, user.id, job_id)
    return RedirectResponse("/v1/label", status_code=303)


@router.get("/v1/label/progress")
def label_progress(user: User = Depends(require_user)):
    """For anyone who does want JSON. Reports only this labeller's own count."""
    with db() as conn:
        label_set = labels_mod.active_set(conn)
        if not label_set:
            return {"label_set": None, "done": 0, "total": 0}
        done, total = labels_mod.progress(conn, label_set, user.id)
    return {"label_set": label_set, "done": done, "total": total}


_NO_SET = (
    "<h1>Nothing to label yet</h1><p>No eval set has been drawn. Whoever set "
    "this up needs to run <code>python3 -m evals label sample</code>.</p>")

_ALL_DONE = (
    "<h1>All done &mdash; thank you</h1><p>You have labelled all {total} "
    "postings in this set. Nothing else is needed from you.</p>")

_MISSING_JOB = (
    "<h1>That posting is unavailable</h1><p>It was in the set but is no longer "
    "in the corpus. This has been logged; please tell whoever sent you the "
    "link.</p>")
