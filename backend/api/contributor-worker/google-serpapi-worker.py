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

IF A SEARCH FAILS: the script tells the server to release that query so
somebody else can pick it up right away, rather than leaving it locked. That
also means a failed run costs you nothing but the credit SerpApi already
charged.
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
#: It is defined HERE, in T-29, and not in T-31 -- the row that introduces the
#: server-dictated interval and clamps it. T-29's acceptance criteria require
#: the plist's StartInterval to match "the local floor T-31 defines", and T-31
#: is unbuilt, so the constant is introduced by whichever of the two lands
#: first. T-31 INHERITS THIS NAME AND THIS VALUE; it should clamp against this
#: constant rather than declaring a second one, because two floors that drift
#: apart is a worker polling on one number and scheduled on another.
#:
#: One hour, for the reason T-31 states: a server that says "poll in 10 seconds"
#: must not be able to make thirty machines hammer one endpoint, while a server
#: that says "poll in six hours" is allowed to. A poll that is granted nothing
#: spends no SerpApi credit -- only a claimed query does -- so the cost this
#: bounds is the endpoint's, not the Builder's.
MIN_POLL_INTERVAL_SECONDS = 3600


def log(msg):
    if DEBUG:
        print(f"[debug] {msg}", file=sys.stderr)


def api_post(path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{JOBS_API_BASE_URL}{path}",
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {JOBS_API_KEY}",
            "User-Agent": "jobs-contributor-worker/1.0",
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
    req = urllib.request.Request(url, headers={"User-Agent": "jobs-contributor-worker/1.0"})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        data = json.loads(resp.read().decode())
    if "error" in data:
        raise RuntimeError(data["error"])
    return data.get("jobs_results", [])


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

    try:
        claimed = api_post("/v1/queries/claim", {"max": MAX_QUERIES})
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:300]
        print(f"worker FAILED: could not claim queries (HTTP {e.code}): {detail}")
        sys.exit(1)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
        print(f"worker FAILED: could not reach {JOBS_API_BASE_URL}: {e}")
        sys.exit(1)

    queries = claimed.get("queries", [])
    if not queries:
        # Not an error: it means everything is already up to date. Exiting 0
        # keeps cron quiet on the (common) days there's nothing to do.
        print("worker: nothing to do -- no stale queries available right now.")
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
            print(f"worker: submit failed for {q['slug']} (HTTP {e.code}): "
                  f"{e.read().decode()[:200]}", file=sys.stderr)
            failed += 1
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
            print(f"worker: submit failed for {q['slug']}: {e}", file=sys.stderr)
            failed += 1

    print(f"worker: {submitted} submitted, {failed} failed, {len(queries)} claimed.")
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
    args = parser.parse_args(argv)

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
