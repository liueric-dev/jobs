"""Provider adapters. One function each, plus the data describing the account.

Every module here exposes exactly:

    NAME            the string a config file or a --provider flag names it by
    UNIT            what its allowance is denominated in -- and the units
                    DIFFER, which is why serp.SerpResult carries the unit
                    beside the number instead of adding them up
    fetch(query, location, creds, *, date_chip) -> raw
    credits_for(raw) -> int
    account(creds) -> dict, the provider's OWN counter, for serp.quota

`fetch` returns the provider's payload untouched. It does not normalise, does
not consult the ledger, does not cache and does not decide whether to retry --
serp/__init__.py owns all four, so that adding the ninth provider is one small
file rather than one small file plus four edits somewhere else.
"""
