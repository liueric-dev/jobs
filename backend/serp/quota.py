"""The quota ledger. Its authority is the PROVIDER's counter, not this repo's.

WHY THAT SENTENCE IS THE WHOLE DESIGN
    DECISIONS.md, "EXP -- The repo's own SerpApi ledger undercounts real spend
    by 3.3x": before authorising the Google Jobs experiment, the orchestrator
    read google_jobs_query_stats, found 41 searches used this month and
    inferred 209 remaining. The SerpApi account itself read 137 used -- and 153
    after the experiment. Ninety-seven left, not two hundred and nine.

    ".claude/CLAUDE.md" names the class: "Silence is this system's failure mode.
    Exhausted keys, revoked keys, blocked scrapers and changed endpoints all
    return zero rows rather than raising." A ledger derived from rows this
    pipeline wrote is that failure mode with a number attached -- it is
    confident, it is checkable, and it is wrong in the dangerous direction.

    THE STRUCTURAL REASON IT UNDERCOUNTS, AND WHY A CAREFULLER LOCAL TALLY
    WOULD NOT FIX IT. At least four things spend one SerpApi account and only
    one of them is the nightly pipeline:

      ingest/google-serpapi.py                        the nightly bank
      api/contributor-worker/google-serpapi-worker.py a contributor's worker
      tools/verify-date-filter.py                     ~3 credits, by hand
      a second machine                                the multi-machine design
                                                      ingest/google-serpapi.py's
                                                      docstring is explicit about

    plus every crash between spending a credit and recording it. No amount of
    care inside one process can see the other three, so `check()` asks the
    vendor and `spend()` is only ever a within-run tally for reporting.

WHAT check() DOES WHEN IT CANNOT REACH THE VENDOR
    It ALLOWS. Refusing would convert a network blip into a night with no
    searches, and the failure it would be protecting against is already handled
    one layer down: an exhausted account answers the search itself with
    AccountRefused, which serp/__init__.py raises as ProviderRefused and
    dispatch declines to swallow. So the cost of allowing is one refused
    search; the cost of refusing is the whole bank. The unavailability is
    recorded and printed, never silent.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import serp  # noqa: E402

CONFIG_FILE = os.environ.get(
    "SERP_QUOTA_FILE",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "config", "serp-quota.json"))


def load_config(path=None):
    """The providers block, with `_`-prefixed documentation keys dropped.

    Keys beginning with `_` are load-bearing documentation in this repo's
    config JSON (".claude/CLAUDE.md") and every reader has to know to skip
    them -- the same treatment searchqueries.load_seeds() gives.
    """
    with open(path or CONFIG_FILE) as fh:
        cfg = json.load(fh)
    out = {}
    for name, entry in cfg["providers"].items():
        if name.startswith("_"):
            continue
        out[name] = {k: v for k, v in entry.items() if not k.startswith("_")}
    return out


class Reconciliation:
    """One provider's ledger, side by side with the vendor's own counter.

    `delta` is vendor-used minus locally-tallied, and it is the number the 3.3x
    finding is about. It is None when the two cannot be compared -- either the
    vendor was unreachable or the units do not meet (Apify counts dollars where
    this pipeline counts results). A None delta is reported as "not compared",
    never as zero: a reconciliation that silently reads as agreement when it
    never ran is the same defect one level up.
    """

    __slots__ = ("provider", "unit", "vendor_used", "vendor_left",
                 "vendor_allowance", "vendor_billed", "local_spend", "delta",
                 "note")

    def __init__(self, provider, *, unit=None, vendor_used=None,
                 vendor_left=None, vendor_allowance=None, vendor_billed=None,
                 local_spend=0, delta=None, note=None):
        self.provider = provider
        self.unit = unit
        self.vendor_used = vendor_used
        self.vendor_left = vendor_left
        self.vendor_allowance = vendor_allowance
        self.vendor_billed = vendor_billed
        self.local_spend = local_spend
        self.delta = delta
        self.note = note

    def line(self):
        if self.vendor_used is None:
            return (f"{self.provider}: vendor counter UNAVAILABLE "
                    f"({self.note}); this run spent {self.local_spend} "
                    f"{self.unit} by its own count")
        left = "?" if self.vendor_left is None else self.vendor_left
        head = (f"{self.provider}: vendor says {self.vendor_used} used, "
                f"{left} left")
        if self.delta is None:
            return (f"{head}; this run spent {self.local_spend} {self.unit}; "
                    f"NOT RECONCILED ({self.note})")
        return (f"{head}; vendor billed {self.vendor_billed} over this run "
                f"against {self.local_spend} {self.unit} counted here; "
                f"delta {self.delta:+d}")

    def __repr__(self):
        return f"Reconciliation({self.line()!r})"


class Ledger:
    """Per-provider allowance, a within-run tally, and the vendor as referee."""

    def __init__(self, config=None, *, creds_for=None, account_fn=None):
        self.config = config if config is not None else load_config()
        self.spent = {}
        #: The vendor's `used` figure BEFORE this run spent anything, taken by
        #: the first check(). Half of the only comparison that means something.
        self._baseline = {}
        self._latest = {}
        self._unavailable = {}
        self._creds_for = creds_for or self._creds_from_env
        self._account_fn = account_fn

    @staticmethod
    def _creds_from_env(name):
        from serp import dispatch
        return dispatch.credentials_for(name)

    def unit(self, name):
        return (self.config.get(name) or {}).get("unit")

    def account(self, name, *, refresh=False):
        """The vendor's counter. Read once per run unless `refresh`.

        The baseline read and the closing read are the two ends of the
        reconciliation, so this deliberately does NOT cache for the life of the
        object: caching the closing read onto the opening one would make every
        delta zero, which is the most convincing possible wrong number and
        exactly the shape evals/cache.py:78-94 records for repeat_index.
        """
        if not refresh and name in self._latest:
            return self._latest[name]
        mod = serp.resolve(name)
        fn = self._account_fn or mod.account
        try:
            data = fn(self._creds_for(name))
        except Exception as e:                  # noqa: BLE001 -- see below
            # Deliberately broad. Every failure of a FREE, ADVISORY read has
            # the same disposition -- record it and allow the run -- and
            # enumerating exception types here would mean a new provider's
            # client library could turn a nightly ingest into a crash by
            # raising something this tuple had not met.
            self._latest[name] = None
            self._unavailable[name] = f"{type(e).__name__}: {e}"
            return None
        self._latest[name] = data
        self._unavailable.pop(name, None)
        if name not in self._baseline:
            self._baseline[name] = data.get("used")
        return data

    def check(self, name):
        """Raise ProviderRefused if the VENDOR says there is nothing left.

        Also the call that takes the baseline, which is why it runs before the
        first search rather than being folded into reconcile().
        """
        entry = self.config.get(name) or {}
        data = self.account(name)
        if data is None:
            return                       # allow; see the module docstring
        left = data.get("left")
        if left is None:
            return
        reserve = entry.get("reserve") or 0
        if left - reserve <= 0:
            raise serp.ProviderRefused(
                f"{name}: {left} left against a reserve of {reserve} "
                f"(the vendor's own counter, not this pipeline's)")

    def spend(self, name, credits):
        """Tally what THIS RUN spent. Never the authority -- see reconcile()."""
        self.spent[name] = self.spent.get(name, 0) + int(credits)

    def reconcile(self, name):
        """What the vendor billed this run, against what this run thinks it spent.

        THE COMPARISON IS OVER THE RUN, NOT OVER THE MONTH, and that is the
        correction to the calculation that was out by 3.3x. "Vendor used minus
        everything we believe we have ever spent" cannot come out right: the
        account is also spent by a second machine, by
        api/contributor-worker/google-serpapi-worker.py and by
        tools/verify-date-filter.py, none of which this process can see, so the
        month-scale difference is a sum of four unknowns. A closing read minus
        an opening read taken minutes apart is one number about one run.

        A POSITIVE delta means something ELSE spent the account while this run
        was going -- expected on a multi-machine night, alarming on a quiet one.
        A NEGATIVE delta is the interesting direction and has a known innocent
        cause: SerpApi does not bill cached searches
        (ADDENDUM-google-jobs-providers.md section 2), so a query it served from
        its own cache is spent here and not billed there.
        """
        entry = self.config.get(name) or {}
        unit = entry.get("unit")
        local = self.spent.get(name, 0)
        data = self.account(name, refresh=True)
        if data is None:
            return Reconciliation(name, unit=unit, local_spend=local,
                                  note=self._unavailable.get(name, "unreachable"))
        vendor_unit = data.get("unit") or unit
        used = data.get("used")
        baseline = self._baseline.get(name)
        delta = billed = note = None
        if not entry.get("reconcilable"):
            note = (f"units do not meet -- this pipeline counts {unit}, the "
                    f"vendor counts {vendor_unit}")
        elif used is None:
            note = "vendor reported no usage figure"
        elif baseline is None:
            note = "no opening read -- check() never ran for this provider"
        else:
            billed = int(used - baseline)
            delta = billed - local
        return Reconciliation(name, unit=unit, vendor_used=used,
                              vendor_left=data.get("left"),
                              vendor_allowance=data.get("allowance"),
                              vendor_billed=billed, local_spend=local,
                              delta=delta, note=note)

    def report(self, names=None):
        """One line per provider this run touched. Printed, not returned as a
        number, for the reason evals/report.py gives about cost: the figure
        only means something beside the instrument that produced it."""
        names = names or sorted(self.spent) or sorted(self.config)
        return "\n".join(self.reconcile(n).line() for n in names)
