#!/usr/bin/env python3
"""
Contributor worker -- the script you run on YOUR machine to help collect job
postings.

WHAT IT DOES: asks the coordinating server which searches still need running,
runs them against Google Jobs using YOUR OWN SerpApi account, and sends the
raw results back. You never get or need database access; the server does all
the storing.

WHAT IT COSTS YOU: one SerpApi search credit per query it runs. SerpApi's free
tier is 250 searches/month. The server won't hand you more than your
configured per-run maximum, and it won't hand out a query that someone else
already ran recently, so credits don't get spent re-fetching the same thing.

DEPENDENCIES: none -- Python 3 standard library only. No database driver, no
pip install. That's deliberate, so this runs on any machine with Python.

SETUP -- either of these, and the environment wins if you use both:

    (a) config.json, the file you are handed when you opt in on the website.
        Drop it in this directory, BESIDE THIS SCRIPT, and type your own
        SerpApi key into the field that arrives empty:

            {
              "JOBS_API_BASE_URL": "https://<the server's address>",
              "JOBS_API_KEY": "<minted for you when you opted in>",
              "SERPAPI_API_KEY": "<your own key from serpapi.com>"
            }

        It is looked for beside this script and not in whatever directory you
        happened to run from, so a scheduled run finds it too.

    (b) the environment, which is what a debugging run overrides with:

            export JOBS_API_BASE_URL=https://<the server's address>
            export JOBS_API_KEY=<the key you were given>
            export SERPAPI_API_KEY=<your own SerpApi key from serpapi.com>

    Those three settings are the whole of config.json. MAX_QUERIES,
    HTTP_TIMEOUT and DEBUG are environment-only on purpose: how much to spend
    per run is the server's call, delivered in its answer to each poll, not a
    number frozen into a file at install time. Any other key in config.json is
    ignored.

RUN:
    python3 google-serpapi-worker.py
    MAX_QUERIES=3 python3 google-serpapi-worker.py     # take more per run
    DEBUG=1 python3 google-serpapi-worker.py           # verbose

SCHEDULE -- on a Mac, let the OS do it:
    python3 google-serpapi-worker.py --install     # write and load a launchd agent
    python3 google-serpapi-worker.py --uninstall   # unload and remove it

    launchd owns the schedule, so it survives reboot and sleep with no process
    to keep alive. Both are safe to run twice: --install replaces the agent
    rather than adding a second one, and --uninstall on a machine with no agent
    says so and exits 0.

    --uninstall removes the SCHEDULE ONLY. Your config.json, and the credential
    in it, stay exactly where the opt-in put them; delete that file yourself if
    you are handing the machine on.

SCHEDULE, anywhere that is not a Mac:
    launchd does not exist, so --install refuses rather than writing a file that
    will never fire. Use cron -- once a day is plenty:

    crontab -e
    0 9 * * * /usr/bin/python3 /path/to/this/dir/google-serpapi-worker.py

CHECK -- when something is not working:
    python3 google-serpapi-worker.py --check

    Prints one line per check -- the server answers, your credential is
    accepted, your SerpApi key is accepted -- and exits non-zero if any of them
    failed. It runs no search, so it costs you nothing and you can run it as
    often as you like. It is also how you confirm an --install worked: the
    agent itself does not run until its first scheduled time, so there is
    otherwise nothing to see.

IF A SEARCH FAILS: the script tells the server to release that query so
somebody else can pick it up right away, rather than leaving it locked. That
also means a failed run costs you nothing but the credit SerpApi already
charged.

WHAT THIS SENDS ABOUT YOU, AND WHAT IT DOES NOT: each poll reports this
script's version, how many SerpApi searches your account says are left, and
whatever went wrong on the last run -- so the operator can tell a machine that
is quietly up to date from one that has stopped working, without having to ask
you. That is all. Your SerpApi key never leaves this machine, no search result
is attributed to you beyond the counts already in the submission log, and
nothing here is read back to decide what you are given. The three facts wait
in `worker-state.json` beside this script between runs; delete it any time --
it holds no credential and the next run rebuilds what it needs.
"""

import argparse
import os
import sys
import json
import plistlib
import subprocess
import urllib.parse
import urllib.request
import urllib.error

#: Beside THIS SCRIPT, resolved from __file__ rather than from the working
#: directory. A relative path would find the file every time you ran the
#: worker by hand from this directory and miss it on every scheduled run,
#: which is the one that matters and the one nobody watches.
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

#: Beside the script too, and NOT a second config.json: nothing a Builder types
#: goes in here and deleting it loses nothing but one run's worth of report.
#: It is an OUTBOX -- facts this machine learned during a run, waiting for the
#: next poll to carry them.
#:
#: WHY THERE HAS TO BE ONE. A poll happens at the START of a run and the facts
#: worth reporting are produced by the END of it: what went wrong, and what the
#: SerpApi account had left afterwards. Nothing can be both discovered and
#: reported in one run without a second call to the server, so a run writes and
#: the next poll sends. That is also why each fact is sent ONCE and then
#: cleared: a value re-sent every hour would be re-stamped by the server every
#: hour, and a week-old balance would read as freshly confirmed forever.
STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "worker-state.json")


def load_config(path=CONFIG_PATH):
    """Read the config.json a Builder dropped beside this script.

    Absent is the ordinary case and returns {} -- an environment-configured
    run has no file, and saying anything about it would be noise. Present but
    broken is not ordinary, and gets its own message naming the file: a
    Builder who mistyped their JSON would otherwise be told to set variables
    they can see they already set, and go looking in their shell.

    Only the three settings below are read out of the result; any other key is
    ignored rather than rejected, so a stale file from an older opt-in keeps
    working.
    """
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        try:
            data = json.load(fh)
        except ValueError as e:
            raise ValueError(f"{path} is not valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise ValueError(f"{path} must hold a JSON object, "
                         f"not a {type(data).__name__}")
    unstringly = sorted(k for k, v in data.items() if not isinstance(v, str))
    if unstringly:
        raise ValueError(f"{path}: every value must be a string, and these are "
                         f"not: {', '.join(unstringly)}")
    return data


try:
    FILE_CONFIG = load_config()
except (OSError, ValueError) as e:
    print(f"worker FAILED: {e}")
    sys.exit(1)

# Environment first so a debugging run can override one setting without
# editing the file, then config.json. Each name is spelled out at both ends
# rather than looped over: webapp/tests/test_contribute.py reads THIS SOURCE
# to check that the file it writes and the settings this reads are the same
# three, and a loop over a tuple would leave it nothing to read.
JOBS_API_BASE_URL = (os.environ.get("JOBS_API_BASE_URL", "")
                     or FILE_CONFIG.get("JOBS_API_BASE_URL", "")).rstrip("/")
JOBS_API_KEY = (os.environ.get("JOBS_API_KEY", "")
                or FILE_CONFIG.get("JOBS_API_KEY", ""))
SERPAPI_API_KEY = (os.environ.get("SERPAPI_API_KEY", "")
                   or FILE_CONFIG.get("SERPAPI_API_KEY", ""))
# Not in config.json, deliberately: docs/adr/0007 decision 3 puts per-run
# policy in the server's poll response, not in a file written once at install.
MAX_QUERIES = int(os.environ.get("MAX_QUERIES", "1"))
HTTP_TIMEOUT = int(os.environ.get("HTTP_TIMEOUT", "45"))
DEBUG = os.environ.get("DEBUG", "") == "1"

#: Reverse-DNS because that is what launchd expects of a Label, and anchored on
#: this repo's own GitHub namespace rather than an invented domain. The plist is
#: named after it, which is the convention that lets `launchctl list` and a
#: directory listing be read against each other.
LAUNCH_AGENT_LABEL = "com.github.liueric-dev.jobs.contributor-worker"

#: THE LOCAL FLOOR. The shortest interval this worker will ever poll on, and
#: what --install writes into the plist.
#:
#: It was defined HERE, in T-29, before T-31 -- the row that introduced the
#: server-dictated interval and clamps it -- existed. T-29's acceptance criteria
#: require the plist's StartInterval to match "the local floor T-31 defines", so
#: the constant was introduced by whichever of the two landed first. T-31 HAS
#: NOW INHERITED THIS NAME AND THIS VALUE rather than declaring a second one:
#: clamp_poll_interval() floors against it and build_launch_agent() schedules on
#: it, so the number a run refuses to go below and the number launchd fires on
#: are one edit, not two that can drift into a worker polling on one and
#: scheduled on the other.
#:
#: One hour, for the reason T-31 states: a server that says "poll in 10 seconds"
#: must not be able to make thirty machines hammer one endpoint, while a server
#: that says "poll in six hours" is allowed to. A poll that is granted nothing
#: spends no SerpApi credit -- only a claimed query does -- so the cost this
#: bounds is the endpoint's, not the Builder's.
MIN_POLL_INTERVAL_SECONDS = 3600


#: What this machine says it is running, on every request and in every poll's
#: check-in. ONE CONSTANT AND NOT TWO SPELLINGS: the User-Agent on the wire and
#: the version the server stores are the same string, so an operator reading
#: `contribution_report.py` and an operator reading a proxy's access log are
#: reading the same fact. 1.1 is 1.0 plus T-35's check-in -- the protocol a
#: worker speaks changed, which is the only thing this number is for.
WORKER_VERSION = "1.1"
USER_AGENT = f"jobs-contributor-worker/{WORKER_VERSION}"


def log(msg):
    if DEBUG:
        print(f"[debug] {msg}", file=sys.stderr)


def read_outbox():
    """What the last run left for this poll to report. {} if there is nothing.

    EVERY FAILURE HERE IS AN EMPTY OUTBOX AND NEVER AN EXIT. This file is a
    convenience for the operator's report; a corrupted or unreadable one must
    not stop a machine collecting job postings, which is the thing it is for.
    Unlike config.json -- which is a Builder's own typing and gets a message
    naming the file -- nobody typed this, so there is nothing to send anyone to
    look at.
    """
    try:
        with open(STATE_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError) as e:
        log(f"could not read {STATE_PATH}: {e}")
        return {}


def remember(**facts):
    """Merge facts into the outbox for the next poll to carry.

    Merged rather than replaced, because a run can produce an error AND a
    reading, and the two arrive at different moments. Swallows its own failures
    for read_outbox()'s reason: a read-only directory is a machine that cannot
    report, not a machine that cannot work.
    """
    state = read_outbox()
    state.update(facts)
    try:
        with open(STATE_PATH, "w", encoding="utf-8") as fh:
            json.dump(state, fh)
    except OSError as e:
        log(f"could not write {STATE_PATH}: {e}")


def forget_outbox():
    """Drop what has just been delivered. Called only after the server took it."""
    try:
        os.remove(STATE_PATH)
    except OSError as e:
        if os.path.exists(STATE_PATH):
            log(f"could not clear {STATE_PATH}: {e}")


def api_post(path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{JOBS_API_BASE_URL}{path}",
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {JOBS_API_KEY}",
            "User-Agent": USER_AGENT,
        },
    )
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return json.loads(resp.read().decode())


def serpapi_search(query, location, date_chip):
    """Call SerpApi with the contributor's own key.

    hl=en&gl=us are pinned because without them Google intermittently returns
    non-English relative timestamps ("há 2 dias"), which the server's parser
    reads as "no date" and silently drops.
    """
    params = {
        "engine": "google_jobs",
        "q": query,
        "location": location,
        "hl": "en",
        "gl": "us",
        "api_key": SERPAPI_API_KEY,
    }
    if date_chip:
        params["chips"] = f"date_posted:{date_chip}"
    url = "https://serpapi.com/search.json?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        data = json.loads(resp.read().decode())
    if "error" in data:
        raise RuntimeError(data["error"])
    return data.get("jobs_results", [])


def clamp_poll_interval(asked):
    """The interval the server asked for, raised to the local floor.

    A FLOOR, NOT A RANGE, AND THE DIRECTION IS THE WHOLE POINT. "Poll in ten
    seconds" is raised to MIN_POLL_INTERVAL_SECONDS, because a server that has
    been changed, or compromised, or simply typo'd must not be able to turn
    thirty volunteers' machines into a load generator against one endpoint.
    "Poll in six hours" is honoured unchanged, because slowing down costs the
    Builder nothing and is how an operator waves machines off -- clamping that
    to an hour would make the one safe direction unavailable and turn a
    deliberate quiet period into thirty machines ignoring it. So: max(), never
    min(), and never a ceiling.

    ANYTHING THAT IS NOT A FINITE NUMBER IS THE FLOOR, INCLUDING ABSENCE. A
    server that predates docs/adr/0007 sends no interval at all, and that must
    behave exactly like the install that never heard of one -- which is what
    makes deploying the two ends in either order safe. `True` is excluded by
    hand because bool is an int in Python and `max(True, 3600)` would quietly
    read a flag as a cadence.
    """
    if isinstance(asked, bool) or not isinstance(asked, (int, float)):
        if asked is not None:
            log(f"poll interval is not a number ({asked!r}); using the floor")
        return MIN_POLL_INTERVAL_SECONDS
    try:
        seconds = int(asked)
    except (ValueError, OverflowError):
        # NaN and infinity: both survive isinstance and neither survives int().
        log(f"poll interval is not finite ({asked!r}); using the floor")
        return MIN_POLL_INTERVAL_SECONDS
    return max(seconds, MIN_POLL_INTERVAL_SECONDS)


def report_poll_interval(interval):
    """Say what cadence the server asked for, when it is not the one running.

    NOTHING HERE CHANGES THE SCHEDULE, AND SAYING SO IS THE POINT OF THE
    FUNCTION. The OS owns the schedule (docs/adr/0007 decision 2): launchd runs
    this script on the StartInterval written into the plist at --install time,
    which is MIN_POLL_INTERVAL_SECONDS and nothing else, because install_agent
    takes no interval from a Builder and none from the server. A run cannot
    move it either -- rewriting the plist would mean a scheduled run unloading
    and reloading the very agent that is running it, which this row does not
    build. So a server that moves the interval moves it at the next --install
    and not before.

    Which leaves a Builder who was told the cadence changed watching a machine
    that still polls hourly, with nothing on screen to say why. THAT is what
    this prints, and it prints only on the disagreement: the ordinary run, on
    the ordinary machine, where the ask and the schedule agree, stays silent.
    A paused worker being indistinguishable from a broken one is the failure
    this exists to prevent, so the line names the schedule as the schedule
    rather than reporting it as a fault.
    """
    if interval == MIN_POLL_INTERVAL_SECONDS:
        log(f"server asked for {interval}s, which is what is scheduled")
        return
    print(f"worker: the server asks to be polled every {interval // 60} "
          f"minutes; this machine is scheduled every "
          f"{MIN_POLL_INTERVAL_SECONDS // 60}, and a run cannot change that. "
          f"The schedule is the one written at --install. This is a schedule, "
          f"not a fault.")


def main():
    missing = [n for n, v in (
        ("JOBS_API_BASE_URL", JOBS_API_BASE_URL),
        ("JOBS_API_KEY", JOBS_API_KEY),
        ("SERPAPI_API_KEY", SERPAPI_API_KEY),
    ) if not v]
    if missing:
        # With no config.json this is byte for byte the message it has always
        # been -- a Builder with nothing set is being told about their shell,
        # and pointing them at a file that is not there would be a wrong lead.
        # With one present, the file is named, because that is where they will
        # have typed the value that did not take.
        where = (f" in {CONFIG_PATH} or in the environment"
                 if os.path.exists(CONFIG_PATH) else "")
        print(f"worker FAILED: set {', '.join(missing)}{where} "
              f"(see this file's header)")
        sys.exit(1)

    # THE POLL IS ALSO THE CHECK-IN (T-35). The three reported fields ride on
    # the request the worker already makes, so a machine that is up says so by
    # doing its ordinary work and nothing has to be told to phone home
    # separately. Two of them come out of the outbox the last run left; the
    # version is known now. All three are optional on the server, so an older
    # server ignores them rather than refusing this.
    outbox = read_outbox()
    try:
        claimed = api_post("/v1/queries/claim", {
            "max": MAX_QUERIES,
            "worker_version": USER_AGENT,
            "quota_remaining": outbox.get("quota_remaining"),
            "last_error": outbox.get("last_error"),
        })
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:300]
        message = f"could not claim queries (HTTP {e.code}): {detail}"
        # Remembered for the NEXT poll, which is the only one that can carry it
        # -- this one is the request that just failed. A server that is down
        # for a day therefore learns about the day when it comes back, rather
        # than about nothing.
        remember(last_error=message)
        print(f"worker FAILED: {message}")
        sys.exit(1)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
        message = f"could not reach {JOBS_API_BASE_URL}: {e}"
        remember(last_error=message)
        print(f"worker FAILED: {message}")
        sys.exit(1)

    # Delivered. Cleared HERE and not before the request, so a poll that never
    # arrived leaves the facts waiting for the next one instead of dropping
    # them into a failed HTTP call.
    forget_outbox()

    # BEFORE the nothing-to-do exit below, deliberately. The interval rides on
    # every claim reply including the empty one, and the empty one is the
    # common one -- reading it after the early return would mean the machines
    # with no work, the ones an operator most wants to slow down, are the only
    # ones never told.
    report_poll_interval(clamp_poll_interval(claimed.get("poll_interval_seconds")))

    # REPORTED, NOT OBEYED. The server has already granted nothing -- this
    # branch skips no work, spends no credit and decides nothing, and if it were
    # deleted the run would behave identically. What would change is what the
    # Builder reads: a paused machine and a machine with nothing stale to do
    # both print a line about having nothing to do, and "a paused worker being
    # indistinguishable from a broken one" (see report_poll_interval) is the
    # same failure one step along. The server's pause is the source of truth and
    # this is the only thing said about it locally, which is what keeps it from
    # becoming a second one.
    #
    # `.get`, and a truth test rather than `is True`: a server that predates
    # this sends no key at all, exactly as with the poll interval, so either end
    # may be deployed first.
    if claimed.get("paused"):
        print("worker: paused by the server -- no queries were claimed and no "
              "SerpApi credit was spent. Nothing is wrong with this machine, "
              "and it will pick up again on its own when the operator resumes "
              "it; the schedule keeps running so that it can.")
        # A paused machine keeps REPORTING (0007's dormancy consequence), and a
        # balance is part of what it reports -- the reading costs no credit, so
        # a pause has no reason to stop taking it.
        remember_quota()
        return

    queries = claimed.get("queries", [])
    if not queries:
        # Not an error: it means everything is already up to date. Exiting 0
        # keeps cron quiet on the (common) days there's nothing to do.
        print("worker: nothing to do -- no stale queries available right now.")
        remember_quota()
        return

    submitted = failed = 0
    for q in queries:
        dataset = q["dataset"]
        log(f"claimed {dataset} ({q['query']!r} @ {q['location']}, chip={q.get('date_chip')})")
        try:
            results = serpapi_search(q["query"], q["location"], q.get("date_chip"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
                json.JSONDecodeError, RuntimeError, OSError) as e:
            print(f"worker: search failed for {q['slug']}: {e}", file=sys.stderr)
            remember(last_error=f"search failed for {q['slug']}: {e}")
            try:
                api_post(f"/v1/queries/{urllib.parse.quote(dataset)}/release",
                         {"reason": str(e)[:200]})
                log(f"released {dataset}")
            except Exception as release_err:
                # The claim will expire on its own; not worth failing over.
                log(f"could not release {dataset}: {release_err}")
            failed += 1
            continue

        try:
            resp = api_post(f"/v1/queries/{urllib.parse.quote(dataset)}/submit",
                            {"jobs": results})
            submitted += 1
            log(f"submitted {len(results)} results for {q['slug']}: {resp}")
        except urllib.error.HTTPError as e:
            message = (f"submit failed for {q['slug']} (HTTP {e.code}): "
                       f"{e.read().decode()[:200]}")
            print(f"worker: {message}", file=sys.stderr)
            remember(last_error=message)
            failed += 1
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
            print(f"worker: submit failed for {q['slug']}: {e}", file=sys.stderr)
            remember(last_error=f"submit failed for {q['slug']}: {e}")
            failed += 1

    print(f"worker: {submitted} submitted, {failed} failed, {len(queries)} claimed.")
    # AFTER the searches, not before them, so the balance reported next poll is
    # the one this run left behind. Taken even on the failure path below: a run
    # that spent credits and then could not submit them has still spent them,
    # and that is the run whose balance an operator most wants to see.
    remember_quota()
    if failed and not submitted:
        sys.exit(1)


# --------------------------------------------------------------------------
# docs/adr/0007 decision 2: the OS owns the schedule.
#
# NOTHING BELOW MAY BE NAMED `main*`, AND THE TEXT THAT OPENS main()'S OWN
# DEFINITION MAY NOT APPEAR AGAIN ANYWHERE IN THIS FILE -- not in a function
# name, not in a comment, not in a docstring. webapp/tests/test_contribute.py's
# TestTheWorkerContract splits this source on that text and reads the LAST
# piece, looking for the three required settings. It is a substring split, not
# a function boundary, so a second occurrence silently re-anchors it past the
# settings it exists to read and turns the WEBAPP suite red from here. (This
# comment was written with the literal in it, twice, and the webapp suite
# caught it.) For the same reason the unset-settings check stays inside main()
# rather than moving into a helper shared with the flags below.
# --------------------------------------------------------------------------


def _home_dir(home=None):
    return home if home is not None else os.path.expanduser("~")


def launch_agent_path(home=None):
    return os.path.join(_home_dir(home), "Library", "LaunchAgents",
                        f"{LAUNCH_AGENT_LABEL}.plist")


def launch_agent_log_path(home=None):
    """Where a scheduled run's output goes.

    A launchd job has no terminal attached, so without this every run this
    agent makes is invisible -- including the failures, which are the only ones
    anybody needs to see.
    """
    return os.path.join(_home_dir(home), "Library", "Logs",
                        "jobs-contributor-worker.log")


def build_launch_agent(interval=MIN_POLL_INTERVAL_SECONDS, home=None):
    """The plist, as a dict. Pure: no file, no launchctl, no platform check.

    NO `WorkingDirectory` KEY, DELIBERATELY. config.json is resolved from
    __file__ (see CONFIG_PATH), and api/tests/test_contributor_worker.py exists
    to keep it that way -- its whole premise is that this agent sets no cwd
    worth relying on. Pinning one here would make that property untested on the
    one run nobody watches, which is the run it was written for.

    Both program arguments are absolute for the same reason: `sys.executable`
    rather than "python3" so the agent keeps using the interpreter the Builder
    installed with, and the script by absolute path so nothing resolves against
    whatever directory launchd happens to hand it.
    """
    return {
        "Label": LAUNCH_AGENT_LABEL,
        "ProgramArguments": [sys.executable, os.path.abspath(__file__)],
        "StartInterval": int(interval),
        # False so that --install itself never spends a SerpApi credit: the
        # Builder confirms the install with --check (T-30), which is specified
        # to cost nothing, rather than by a surprise search.
        "RunAtLoad": False,
        "StandardOutPath": launch_agent_log_path(home),
        "StandardErrorPath": launch_agent_log_path(home),
    }


def run_launchctl(args):
    """Run launchctl and return (exit code, whatever it said).

    Passed in by the callers below rather than called directly, so the file
    half of --install/--uninstall can be tested off a Mac. This function itself
    only ever runs on Darwin -- cli() refuses everywhere else.
    """
    proc = subprocess.run(  # noqa: S603 -- argv is an absolute path and a module-level constant, never a Builder's input
        ["/bin/launchctl", *args],
        capture_output=True, text=True, check=False)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def install_agent(home=None, interval=MIN_POLL_INTERVAL_SECONDS,
                  launchctl=run_launchctl):
    """Write the agent and load it. Running it twice leaves one agent.

    Idempotence is structural rather than checked: the plist has one path,
    derived from the label, so a second install overwrites the first file
    instead of adding a second one. The unload before the write is what makes
    that true of launchd as well as of the directory -- launchd holds the copy
    of the plist it read at load time, so replacing the file underneath a
    loaded job leaves the old schedule running.
    """
    path = launch_agent_path(home)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    os.makedirs(os.path.dirname(launch_agent_log_path(home)), exist_ok=True)
    if os.path.exists(path):
        # A failure here is not fatal: the ordinary cause is an agent that is
        # present but not loaded, and the load below is what has to work.
        code, output = launchctl(["unload", "-w", path])
        if code != 0:
            log(f"unload before reinstall said: {output}")
    with open(path, "wb") as fh:
        plistlib.dump(build_launch_agent(interval, home), fh)
    code, output = launchctl(["load", "-w", path])
    if code != 0:
        print(f"worker FAILED: wrote {path} but launchctl would not load it: "
              f"{output}")
        return 1
    print(f"worker: installed. It will run every "
          f"{interval // 60} minutes, and after a reboot.")
    print(f"worker:   agent {path}")
    print(f"worker:   log   {launch_agent_log_path(home)}")
    return 0


def uninstall_agent(home=None, launchctl=run_launchctl):
    """Unload the agent and remove it. Running it twice is not an error.

    THE CREDENTIAL IS LEFT ALONE, AND THAT IS NOT AN OVERSIGHT. Whether
    --uninstall should also remove the config.json that T-28 taught this script
    to read is DEV_TASKS.md's OQ-27, third bullet -- an owner decision about
    other people's machines, open when this was built. So this removes the
    schedule, says where the credential still is, and decides nothing.
    """
    path = launch_agent_path(home)
    if not os.path.exists(path):
        print(f"worker: no agent installed at {path}; nothing to remove.")
        return 0
    code, output = launchctl(["unload", "-w", path])
    if code != 0:
        # Deleting the plist now would leave launchd holding a job with no file
        # left to unload it by, which is worse than not having tried.
        print(f"worker FAILED: launchctl would not unload {path}: {output}")
        return 1
    os.remove(path)
    print(f"worker: removed the agent at {path}. Nothing is scheduled now.")
    if os.path.exists(CONFIG_PATH):
        print(f"worker: {CONFIG_PATH} is left in place and still holds your "
              f"credential. Delete it yourself if you are passing this machine on.")
    return 0


# --------------------------------------------------------------------------
# T-30: --check. The one command to run when something is wrong.
#
# Three checks, printed one line each, and NOTHING HERE SPENDS A SERPAPI
# CREDIT -- see check_serpapi and check_credential for how each avoids it. A
# diagnostic that charged a Builder for asking whether they were set up would
# be answering the question by making it worse.
# --------------------------------------------------------------------------

#: SerpApi's account endpoint. It reports plan state -- including how many
#: searches are left in the cycle -- WITHOUT RUNNING ONE, which is the whole
#: reason --check asks it rather than firing a throwaway search and seeing
#: whether it comes back. T-32's budget pacing reads this same response, so
#: the two rows share one endpoint and one shape.
SERPAPI_ACCOUNT_URL = "https://serpapi.com/account"

#: What --check offers to release when it asks the server whether the
#: credential works. NOTHING CAN EVER HOLD A CLAIM ON IT: every real dataset
#: name is built server-side as "google_jobs:query:<slug>" out of the server's
#: own query bank (api/app.py:486), and no slug is spelled like this.
CHECK_PROBE_DATASET = "google_jobs:query:__check__"


def redacted(text):
    """Whatever the far end said, minus anything of yours it quoted back.

    --check prints response bodies, because what the server actually objected
    to is the useful half of a failure. A body is also the one place a key can
    come back at you: an error that helpfully echoes the credential it rejected
    would put it on a terminal, in a scrollback, in the screenshot a Builder
    pastes into a chat asking for help. The command that exists to make a bad
    key visible must not be the one that makes a good key public.
    """
    for secret in (JOBS_API_KEY, SERPAPI_API_KEY):
        if secret and len(secret) >= 8:
            text = text.replace(secret, "<redacted>")
    return text


def probe(request, timeout=None):
    """Send one request and return (status, body), treating an HTTP error
    status as an ANSWER rather than as a failure.

    urllib raises on 4xx, and every status this row turns on is a 4xx: 401 is
    the credential being rejected, 409 is the credential being accepted (see
    check_credential). Letting those raise would collapse "the server said no"
    into "the server said nothing", which is the one distinction the row's
    acceptance criteria name. What still raises is a non-answer -- DNS, a
    refused connection, a timeout, TLS -- and the callers report that as
    unreachable, which is what it is.

    THE BODY COMES BACK WHOLE, AND THE TRUNCATION HAPPENS WHERE IT IS PRINTED.
    Cutting it here instead cost an afternoon: every scripted answer in the
    suite is a short one, so a 400-character cap looked fine until --check was
    pointed at the real SerpApi account endpoint, whose answer is longer than
    that -- and a valid key came back as "answered 200 with something that is
    not JSON". A parser must see the whole document; only a message quoting it
    to a human needs a length.
    """
    try:
        with urllib.request.urlopen(request, timeout=timeout or HTTP_TIMEOUT) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def check_base_url(send=probe):
    """Is JOBS_API_BASE_URL an address where this service answers?

    /v1/health (api/app.py:254) needs no credential, so this separates "your
    address is wrong" from "your key is wrong" -- which the next check depends
    on, and which the row requires be distinguishable in the output.
    """
    if not JOBS_API_BASE_URL:
        return False, "base URL", ("JOBS_API_BASE_URL is not set "
                                   "(see this file's header).")
    url = f"{JOBS_API_BASE_URL}/v1/health"
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT})
    try:
        status, body = send(request)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return False, "base URL", (f"nothing answered at {url} "
                                   f"({redacted(str(e))}). Check the address, "
                                   f"and check you are online.")
    if status != 200:
        return False, "base URL", (f"{url} answered HTTP {status}, not 200. "
                                   f"Something is at that address, but it is "
                                   f"not this service.")
    try:
        healthy = json.loads(body).get("ok") is True
    except ValueError:
        healthy = False
    if not healthy:
        # A captive portal, a parked domain and a proxy error page all answer
        # 200. Reading the body is what tells them apart from the service.
        return False, "base URL", (f"{url} answered 200, but not with this "
                                   f"service's health response "
                                   f"({redacted(body)[:120]}).")
    return True, "base URL", f"{JOBS_API_BASE_URL} answered at /v1/health."


def check_credential(base_url_ok, send=probe):
    """Does the server recognise JOBS_API_KEY?

    THE PROBE IS A RELEASE OF A DATASET NOBODY CAN HOLD, AND THE 409 IS THE
    PASS. Every authenticated route on that server does something. /v1/queries/
    claim locks rows out of the pool for CLAIM_TTL_MINUTES apiece and meters
    the caller against a daily cap (query_claims.py:1085, api/app.py:437-451), so
    checking a credential with it would spend the allowance being checked, and
    on a day when the bank is stale it would leave real queries claimed by a
    worker that was only asking a question. Release is the one authenticated
    route that can be made to change nothing: it authenticates FIRST and asks
    whether the caller holds the claim SECOND (api/app.py:635, :637), so a
    dataset the query bank cannot produce reaches the credential check, writes
    no submission_log row, commits nothing, and comes back 409.

    That ordering is the assumption this check rests on, and it is pinned from
    the server's side by api/tests/test_worker_check.py rather than assumed --
    reversed, this would tell a Builder their good credential was bad.
    """
    if not JOBS_API_KEY:
        return False, "credential", ("JOBS_API_KEY is not set "
                                     "(see this file's header).")
    if not base_url_ok:
        # Not "failed": unknowable. Saying the credential is bad because the
        # address is wrong sends a Builder to ask for a new key they do not
        # need, and the one they have would fail the same way afterwards.
        return False, "credential", ("not checked -- the server never "
                                     "answered, so nothing here would mean "
                                     "anything. Fix the base URL first.")
    url = (f"{JOBS_API_BASE_URL}/v1/queries/"
           f"{urllib.parse.quote(CHECK_PROBE_DATASET)}/release")
    request = urllib.request.Request(
        url,
        data=json.dumps({"reason": "--check: credential probe, no claim held"}).encode(),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {JOBS_API_KEY}",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        status, body = send(request)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return False, "credential", (f"the server answered /v1/health but not "
                                     f"this ({redacted(str(e))}).")
    if status == 401:
        return False, "credential", (f"the server does not recognise this "
                                     f"JOBS_API_KEY (HTTP 401: "
                                     f"{redacted(body)[:160]}). Ask for a new "
                                     f"one where you opted in.")
    if status == 409 or 200 <= status < 300:
        # 409 is the expected pass, per the docstring. A 2xx would mean the
        # server thought this worker held a claim on a dataset its own query
        # bank cannot name -- impossible rather than good, but it is still an
        # authenticated answer, and this check only reports on the credential.
        return True, "credential", "accepted -- the server knows this key."
    return False, "credential", (f"unexpected answer: HTTP {status} "
                                 f"({redacted(body)[:160]}). The key may be "
                                 f"fine; something else is not.")


def check_serpapi(send=probe):
    """Is SERPAPI_API_KEY accepted, and how much of the cycle is left?

    NO SEARCH IS RUN. The account endpoint answers with plan state and is not
    metered, so this costs nothing; a validating search would charge a Builder
    a credit for asking whether they were set up, which is the wrong first
    impression and is what the row forbids. The remaining count is printed
    because it is the number that makes the answer useful: a key that is
    accepted and has nothing left is a working install that will do no work.
    """
    if not SERPAPI_API_KEY:
        return False, "SerpApi key", (
            f"SERPAPI_API_KEY is not set. This one is yours, not the server's: "
            f"get it from serpapi.com and type it into {CONFIG_PATH}.")
    # The key is a query parameter, so the URL itself is a credential --
    # nothing below prints it, and every message that quotes the far end goes
    # through redacted() first.
    url = (f"{SERPAPI_ACCOUNT_URL}?"
           + urllib.parse.urlencode({"api_key": SERPAPI_API_KEY}))
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT})
    try:
        status, body = send(request)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return False, "SerpApi key", (f"serpapi.com did not answer "
                                      f"({redacted(str(e))}).")
    if status in (401, 403):
        return False, "SerpApi key", (f"SerpApi rejected this key (HTTP "
                                      f"{status}: {redacted(body)[:160]}). "
                                      f"Copy it again from serpapi.com; the "
                                      f"server never sees this one.")
    if status != 200:
        return False, "SerpApi key", (f"serpapi.com answered HTTP {status} "
                                      f"({redacted(body)[:160]}), which is "
                                      f"neither an acceptance nor a refusal.")
    try:
        account = json.loads(body)
    except ValueError:
        return False, "SerpApi key", ("serpapi.com answered 200 with "
                                      "something that is not JSON.")
    left = account.get("total_searches_left")
    if left is None:
        return True, "SerpApi key", ("accepted by SerpApi, which reported no "
                                     "remaining count.")
    plan = account.get("plan_name") or "your plan"
    return True, "SerpApi key", (f"accepted by SerpApi -- {left} searches left "
                                 f"on {plan} this cycle.")


def remember_quota(send=None):
    """Read what SerpApi says is left, into the outbox for the next poll.

    THE SAME UNMETERED ENDPOINT --check ALREADY USES, and the reason this can
    run on every scheduled run at all: the account route reports plan state
    without running a search, so a machine that polls hourly reports its balance
    hourly and is charged for none of it. `0007` decision 4 asks for allowance
    to be "recomputed per run from the contributor's own plan data" -- this is
    the run reading its own plan data, and TASKS.md's T-54 is what will read the
    number at the far end.

    IT REPORTS NOTHING RATHER THAN GUESSING. A refused key, an unreachable
    serpapi.com, an answer that is not JSON and a plan with no remaining count
    all leave the quota unreported, so the server keeps whatever it last heard
    together with the time it heard it -- an old number that says it is old
    beats a fresh zero that was never measured. The failure is remembered as an
    error instead, which is the honest thing to report about a machine whose
    SerpApi key has stopped working: it is the same fact --check would print,
    reaching the operator without anyone having to run --check.

    RAISES NOTHING. Every caller is at the end of a run that has already done
    its work; a report that could fail the run it reports on would be worse than
    no report.
    """
    if not SERPAPI_API_KEY:
        return
    url = (f"{SERPAPI_ACCOUNT_URL}?"
           + urllib.parse.urlencode({"api_key": SERPAPI_API_KEY}))
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        status, body = (send or probe)(request)
        if status != 200:
            remember(last_error=f"serpapi.com answered HTTP {status} to the "
                                f"account check: {redacted(body)[:160]}")
            return
        left = json.loads(body).get("total_searches_left")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError,
            AttributeError) as e:
        remember(last_error=f"could not read the SerpApi account: "
                            f"{redacted(str(e))}")
        return
    if isinstance(left, int) and not isinstance(left, bool):
        remember(quota_remaining=left)
    else:
        log(f"SerpApi reported no usable remaining count ({left!r})")

def run_checks(send=probe):
    """Every check, in the order in which one failure makes the next
    unknowable, and one line per check. Returns the exit code.
    """
    if os.path.exists(CONFIG_PATH):
        print(f"worker check: settings from {CONFIG_PATH}, and from the "
              f"environment where it is set.")
    else:
        print("worker check: no config.json beside this script; reading the "
              "environment only.")
    results = [check_base_url(send)]
    results.append(check_credential(results[0][0], send))
    results.append(check_serpapi(send))
    for ok, label, detail in results:
        print(f"  {'ok  ' if ok else 'FAIL'} {label}: {detail}")
    failed = [r for r in results if not r[0]]
    if failed:
        print(f"worker FAILED: {len(failed)} of {len(results)} checks did not "
              f"pass. No SerpApi search was run, so this cost you no credit.")
        return 1
    print(f"worker: all {len(results)} checks passed. No SerpApi search was "
          f"run, so this cost you no credit.")
    return 0


def cli(argv=None):
    """Parse the flags, or fall through to a run.

    A bare invocation must reach main() having printed nothing of its own: the
    no-argument path's exact stdout and exit code are pinned by T-28's
    api/tests/test_contributor_worker.py, and this row is the one that could
    have moved them.
    """
    parser = argparse.ArgumentParser(
        description="Run the contributor worker once, or manage the launchd "
                    "agent that runs it on a schedule (macOS).",
        epilog="With no flags, runs once and exits.")
    scheduling = parser.add_mutually_exclusive_group()
    scheduling.add_argument(
        "--install", action="store_true",
        help="write a launchd agent and load it, so the OS runs this on a "
             "schedule. Safe to run twice. macOS only.")
    scheduling.add_argument(
        "--uninstall", action="store_true",
        help="unload and remove that agent. Leaves config.json, and the "
             "credential in it, alone. macOS only.")
    # NOT A MEMBER OF THE GROUP ABOVE, DELIBERATELY. That group exists because
    # --install and --uninstall are two directions of one action, and asking
    # for both is a typo. --check is not a third direction: it changes nothing,
    # it works on every platform rather than only on macOS, and it is the thing
    # you run when one of those two went wrong. Putting it in the group would
    # also print it in the usage line as a third way to schedule, which it is
    # not. Combining it with either is refused below, in a sentence, rather
    # than by argparse's grammar.
    parser.add_argument(
        "--check", action="store_true",
        help="check this machine's setup and print a line per check: the "
             "server answers, your credential is accepted, your SerpApi key "
             "is accepted. Runs no search, so it costs you nothing. Exits "
             "non-zero if any check failed.")
    args = parser.parse_args(argv)

    if args.check and (args.install or args.uninstall):
        # Refused rather than silently ordered: a Builder who typed both meant
        # something specific by it, and guessing which half to do first is how
        # a diagnostic ends up reporting on a machine it just changed.
        print("worker FAILED: --check reports on your setup and changes "
              "nothing; --install and --uninstall change the schedule. Run "
              "one at a time.")
        return 1

    if args.check:
        return run_checks()

    if args.install or args.uninstall:
        if sys.platform != "darwin":
            # Not a warning-and-continue: a plist on a machine with no launchd
            # is a file that will never fire, and a Builder who saw "installed"
            # would have no reason to look again. docs/adr/0007 decision 7
            # makes this deliberate, and DEV_TASKS.md's OQ-24 is the census
            # that either confirms it or reopens it.
            print(f"worker FAILED: --install and --uninstall manage a launchd "
                  f"agent, which is macOS only, and this is {sys.platform}. "
                  f"Schedule it with cron instead (see this file's header).")
            return 1
        return install_agent() if args.install else uninstall_agent()

    main()
    return 0


if __name__ == "__main__":
    sys.exit(cli())
