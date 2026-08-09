"""The labelling surface: a web page a Builder can use, and nothing else.

WHY THIS IS A SERVER-RENDERED PAGE AND NOT A JSON ENDPOINT
    Labels come from ~10 Builder volunteers (task 29), not from the person who
    wrote the harness. `git show refactor-freeze-2026-08-02:docs/ingestion_tests/03-metrics-and-golden-set.md:101`
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
    `git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_two/07-metrics-and-golden-set.md:53` says to reuse the existing auth "since
    Google SSO and sessions already exist". They do -- in THIS package
    (auth.py), not in `api/`. `api/` is the contributor work queue: bearer
    tokens hashed in `api_keys` (api/app.py:145), a caller assumed hostile, and
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
#: description_text is shown deliberately -- `git show refactor-freeze-2026-08-02:docs/ingestion_tests/03-metrics-and-golden-set.md:127`
#: is explicit that the point is a human judgement on THE SAME INPUT THE MODEL
#: GOT, and a `summary` would be showing them the model's reading of it instead.
_DETAIL_COLUMNS = ("id", "title", "company_name", "location_raw", "platform",
                   "description_text")


#: Hard cap on the request body. The form is six short fields and two ids, so
#: a legitimate submit is a few hundred bytes. Enforced BEFORE parsing, the
#: same argument api/app.py:449 makes: a hostile body should be rejected on
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
        f"SELECT {cols} FROM jobs WHERE id = %s", (job_id,)).fetchone()  # noqa: S608 -- splices _DETAIL_COLUMNS, a module-level constant
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
.logout { text-align: right; margin-bottom: .8rem; }
.logout button { font-size: .82rem; padding: .3rem .7rem; margin-top: 0; }
"""

#: Plain <form>, not a link, because logout is a POST (auth.py:430) -- and
#: no JavaScript, same reason the rest of this module has none (module
#: docstring, "NO JAVASCRIPT MEANS..."). Every _page() call happens after
#: require_user() already succeeded (label_form()), so it is always safe to
#: show this.
_LOGOUT = ("<form class=logout method=post action='/v1/auth/logout'>"
          "<button type=submit>Log out</button></form>")


def _page(title, body):
    return HTMLResponse(
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        f"<title>{html.escape(title)}</title><style>{_CSS}</style></head>"
        f"<body>{_LOGOUT}{body}</body></html>")


#: How one value renders, because "no track fits" as a bare slug sits next to
#: "I can't tell from this posting" and the two are the exact pair this form
#: must not let a volunteer conflate. See labels.NO_TRACK_FITS: one is a
#: verdict about the vocabulary, the other is an abstention, and they are
#: stored as different things precisely so they can be told apart later.
_CHOICE_LABELS = {
    "no_track_fits": "none of these describes this role",
}


def parse_round(raw):
    """A submitted or queried round, as 1 or 2. Never anything else.

    AN ALLOWLIST OF TWO, NOT int(). record()'s ON CONFLICT DO NOTHING means a
    bogus round writes a THIRD round that no agreement function reads --
    intra_annotator() compares rounds 1 and 2, and everything else is
    round-1-scoped -- so it would cost a volunteer's attention and be invisible
    to every report. `round_no` also has no CHECK on the column, so this
    function is where the invariant lives.

    Module-level and named without an underscore so it can be tested directly.
    It was previously inline in submit_label(), and the test for it
    re-implemented the expression instead of calling it -- which passes whatever
    the route does, i.e. asserts nothing.
    """
    return 2 if (raw or "").strip() == "2" else 1


def _render_form(job, question_list, label_set, done, total, overlap,
                 round_no=1, blank=False):
    e = html.escape
    parts = [
        f"<div class=progress>{done} of {total} done"
        + ("  &middot; shared posting" if overlap else "")
        + ("  &middot; second look" if round_no != 1 else "") + "</div>",
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
        f"<input type=hidden name=round_no value='{int(round_no)}'>",
    ]
    if blank:
        parts.append(
            "<p class=hint><strong>Nothing was saved.</strong> This is the same "
            "posting again because no answer came through. Answer at least one "
            "question &mdash; and if you cannot judge this posting at all, pick "
            "<em>I can't tell from this posting</em> on each one, which is a "
            "real answer and moves you on.</p>")
    if round_no != 1:
        # Say what is being asked, or a volunteer reads the repeat as a bug and
        # "corrects" it to whatever they said last time -- which is the one
        # answer that makes the measurement worthless.
        parts.append(
            "<p class=hint>You answered this posting before. Answer it again "
            "from the posting, not from memory &mdash; if you now think "
            "differently, say what you think now.</p>")
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
                f"value='{e(choice)}'> "
                f"{e(_CHOICE_LABELS.get(choice, choice.replace('_', ' ')))}"
                "</label>")
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

    round_no = parse_round(request.query_params.get("round"))
    n_waiting = 0        # set below on round 2; read in the exhaustion branch

    with db() as conn:
        label_set = labels_mod.active_set(conn)
        if not label_set:
            return _page("Nothing to label", _NO_SET)
        if round_no == 2:
            # The delay is the measurement, not politeness -- see
            # labels.ROUND_TWO_DELAY_DAYS. Refusing with a DATE rather than
            # with an empty page is the difference between "come back Tuesday"
            # and "you are finished", which are the two states a volunteer
            # would otherwise have to guess between.
            ready, n_waiting, earliest = labels_mod.round_two_ready(
                conn, label_set, user.id)
            if not n_waiting:
                return _page("Nothing to re-check", _NO_ROUND_ONE)
            if not ready:
                return _page("Not yet", _TOO_SOON.format(
                    when=earliest[:10], n=n_waiting))
        item = labels_mod.next_item(conn, label_set, user.id,
                                    round_no=round_no)
        done, total = labels_mod.progress(conn, label_set, user.id,
                                          round_no=round_no)
        if item is None:
            # "EXHAUSTED FOR NOW" IS NOT "ALL DONE", and on round 2 the two are
            # easy to confuse into a data loss. round_two_ready() opens the
            # round off the labeller's EARLIEST round-1 answer, while
            # next_item() admits rows one at a time as each reaches seven days.
            # A volunteer who answered the overlap block across two sittings
            # therefore has rows that are ready and rows that are not, and
            # telling them "nothing else is needed from you" ends their
            # participation in the one measurement that has no second chance.
            if round_no == 2 and done < n_waiting:
                return _page("That is all for now", _MORE_LATER.format(
                    done=done, waiting=n_waiting,
                    days=labels_mod.ROUND_TWO_DELAY_DAYS))
            if round_no == 2:
                # Round 2 gets its OWN completion message and it speaks only
                # about the second look. _ALL_DONE's total is the overlap block
                # size, so a labeller who answered 6 of 10 in round 1 and
                # re-checked all 6 would be told "all 10 ... nothing else is
                # needed" while four are still outstanding in ROUND 1. Same
                # split-sitting trigger as the bug this branch already fixes.
                return _page("Second look complete",
                             _ROUND_TWO_DONE.format(done=done))
            return _page("All done", _ALL_DONE.format(total=total))
        job = _job(conn, item["job_id"])
        # Round 2 asks back only what this person actually answered, so a
        # question left blank or abstained the first time is not re-presented.
        # labels.round_one_answers() carries the reasoning; the short version is
        # that a first answer given at round-2 time has nowhere correct to go
        # and one of the two places it could go bypasses the seven-day delay.
        questions = labels_mod.questions()
        if round_no == 2:
            answered = labels_mod.round_one_answers(
                conn, label_set, item["job_id"], user.id)
            questions = [q for q in questions if q.field in answered]

    if job is None:
        # The set names a job id the corpus no longer has. Not fatal and not
        # silently skipped either: a set whose rows are disappearing is a set
        # whose digest no longer describes what anyone labelled.
        log.warning("label set %s references missing job %s",
                    label_set, item["job_id"])
        return _page("Posting unavailable", _MISSING_JOB)

    return _render_form(job, questions, label_set, done, total,
                        item["overlap"], round_no=round_no,
                        blank=request.query_params.get("blank") == "1")


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

    round_no = parse_round(form.get("round_no"))

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

        # Round 2 has two more preconditions, and one query answers both.
        # Queried here rather than trusted from the form for the same reason
        # `profile` is taken from the session: the round is the difference
        # between a first answer and a revision, and a revision of nothing is
        # not a measurement.
        round_one_fields = set()
        if round_no == 2:
            # (a) It must be an overlap row. next_item()'s round-2 branch only
            # ever serves those, so a non-overlap round-2 row can only arrive
            # from a hand-edited form -- and it would be folded into the
            # intra-annotator ceiling with no delay behind it, which is the one
            # figure that ceiling must not contain.
            if not conn.execute(
                    "SELECT 1 FROM eval_label_items "
                    "WHERE label_set = %s AND job_id = %s AND overlap",
                    (label_set, job_id)).fetchone():
                raise HTTPException(
                    status_code=400,
                    detail="round 2 re-asks the shared postings only")
            # (b) Which FIELDS may be re-asked: answered in round 1, not
            # abstained, and matured. See labels.round_one_answers() for why
            # each exclusion is there -- one of them is a delay bypass.
            # Re-checked here and not only at render time, because the render
            # bounds what a browser SHOWS and this bounds what gets STORED.
            round_one_fields = labels_mod.round_one_answers(
                conn, label_set, job_id, user.id)
            if not round_one_fields:
                raise HTTPException(
                    status_code=400,
                    detail="nothing on this posting is due for a second look")

        written = 0
        for q in labels_mod.questions():
            raw = form.get(f"{q.axis}:{q.field}")
            if raw is None:
                # Not answered at all. Distinct from an abstention, and NOT
                # written: an unanswered question is missing data, and
                # recording it as "I can't tell" would invent a judgement.
                continue
            # A round-2 submission may only touch fields that are due for one.
            # The form did not render the others, so this rejects only a
            # hand-crafted POST -- and it rejects it silently per field rather
            # than 400ing the whole submission, because the fields that ARE due
            # are legitimate answers and should not be lost to one bad field.
            if round_no == 2 and q.field not in round_one_fields:
                continue
            try:
                # profile comes from the SESSION, never from the form. That is
                # the same tenancy rule jobs.py:5 states, and here it is also
                # what keeps axis B rows attributable to a cohort.
                written += bool(labels_mod.record(
                    conn, axis=q.axis, job_id=job_id, field=q.field,
                    value=raw, labeller_id=user.id, label_set=label_set,
                    round_no=round_no,
                    profile=user.profile if q.axis == labels_mod.AXIS_B
                            else None))
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
        conn.commit()

    log.info("%d label(s) from %s on %s (round %d)",
             written, user.id, job_id, round_no)
    # The round has to survive the redirect, or a round-2 answer sends the
    # labeller back to a round-1 queue that is already exhausted and the page
    # says "All done" halfway through their second look.
    #
    # AND A SUBMIT THAT WROTE NOTHING HAS TO SAY SO. next_item() serves the next
    # posting this labeller has no row for, so a fully-blank submit re-serves
    # the SAME posting -- correctly, since nothing was recorded, but on screen
    # it is indistinguishable from a broken page, and a volunteer who thinks the
    # form is stuck stops. The intended exit from a posting nobody can judge is
    # "I can't tell" on every question, which writes rows and advances; this
    # says that instead of leaving them to infer it. Six questions make a blank
    # submit likelier than five did.
    query = "?round=2" if round_no == 2 else ""
    if not written:
        query += ("&" if query else "?") + "blank=1"
    return RedirectResponse("/v1/label" + query, status_code=303)


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

#: Round 2 only. The rows mature one at a time, so an empty queue here usually
#: means "come back", not "finished" -- and saying the wrong one of those costs
#: the intra-annotator sample, which cannot be recollected. Names the count so a
#: volunteer can see there is more, without promising a date this page cannot
#: compute (the next row's is a function of when THEY answered it).
_MORE_LATER = (
    "<h1>That is all for now &mdash; thank you</h1><p>You have re-checked "
    "{done} of your {waiting} shared postings. The rest become available as "
    "each one reaches {days} days since you first answered it, so there is "
    "more to do here later &mdash; this is not the end of the second look.</p>"
    "<p>Come back to this link in a few days.</p>")

#: Round 2's own completion message. Deliberately says nothing about the set:
#: finishing the second look is not finishing round 1, and _ALL_DONE's
#: "nothing else is needed from you" would be false for anyone who still has
#: round-1 postings outstanding.
_ROUND_TWO_DONE = (
    "<h1>Second look complete &mdash; thank you</h1><p>You have re-checked all "
    "{done} of your shared postings. That is everything the second look needs."
    "</p><p>If you had postings left in the main list, they are still at "
    "<a href='/v1/label'>the main link</a>.</p>")

_NO_ROUND_ONE = (
    "<h1>Nothing to re-check</h1><p>The second look re-asks about the shared "
    "postings you have already answered, and you have not answered any of "
    "them yet. Start at <a href='/v1/label'>the main list</a>.</p>")

#: Names the DATE, not "later". A volunteer told "not yet" with no date either
#: gives up or retries daily; either way the operator hears nothing about it.
_TOO_SOON = (
    "<h1>Not yet &mdash; and that is on purpose</h1><p>The second look asks "
    "you the same {n} postings again to measure how much one person's answers "
    "vary. Asked too soon it measures what you <em>remember</em> saying "
    "instead, which is not a useful number.</p>"
    "<p>Come back on or after <strong>{when}</strong>.</p>")
