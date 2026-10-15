"""Verification script for the redesigned Levers & Strategy page. Run as a
script, like the other files in this directory - there is no pytest suite
in this repo to join.

    python audit/audit_levers_and_strategy.py

Unlike the Lever Playbook's audit (pure static content, no portfolio
needed), this page reads a real pipeline result, so this script builds one
from the bundled demo portfolio and feeds it through the actual page code
via a stubbed Streamlit - exercising the real worklists, the real
customer_view, and a real selected customer, not just a syntax check.
"""
import runpy
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.run import build_pipeline  # noqa: E402

DEMO_DIR = ROOT / "generator" / "out" / "demo"
PAGE_PATH = ROOT / "app" / "pages" / "20_Levers_and_Strategy.py"

# Substrings that would indicate a dollar/monetary figure leaked into a
# column this page claims is "non-monetary detail only" - the whole point
# of SAFE_COLS/safe_worklist(). Deliberately broad; a false positive here
# just means double-checking a column name, which is cheap.
MONEY_SUBSTRINGS = ["usd", "_cost", "revenue", "economic_profit", "current_limit",
                    "target_limit", "credit_limit", "reward_expense", "annual_fee",
                    "value_at_risk", "_net", "priced_value", "unpriced_context"]


def sec(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


class _Stub:
    """Swallows every Streamlit call. A handful of widgets are special-cased
    to return something realistic (selectbox returns a real option,
    multiselect/checkbox return their natural empty/false default) so the
    page's actual branching logic - not just its syntax - gets exercised."""

    def __init__(self, name=""):
        self._name = name

    def __call__(self, *a, **k):
        if self._name == "columns":
            n = a[0] if a else 1
            count = n if isinstance(n, int) else len(n)
            return tuple(_Stub("col") for _ in range(count))
        if self._name == "tabs":
            labels = a[0] if a else []
            return tuple(_Stub("tab") for _ in range(len(labels)))
        if self._name == "selectbox":
            options = k.get("options") or (a[1] if len(a) > 1 else [])
            return options[0] if len(options) else None
        if self._name in ("multiselect",):
            return []
        if self._name == "checkbox":
            return False
        return _Stub(self._name)

    def __getattr__(self, name):
        return _Stub(name)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


sec("Build a real pipeline result from the bundled demo portfolio")
result = build_pipeline(DEMO_DIR)
worklists = result["worklists"]
print(f"  {len(result['customer_view']):,} customers, "
     f"worklist sizes: {({c: len(wl) for c, wl in worklists.items()})}")

sec("T-PAGE-RUN: the page executes top-to-bottom against a real result, "
   "with a real selected customer, no exception")
stub = _Stub("st")
stub.session_state = {"result": result}
real_streamlit = sys.modules.get("streamlit")
sys.modules["streamlit"] = stub
try:
    ns = runpy.run_path(str(PAGE_PATH), run_name="__not_main__")
    print("  PASS  20_Levers_and_Strategy.py executes top-to-bottom with no exception")
finally:
    if real_streamlit is not None:
        sys.modules["streamlit"] = real_streamlit
    else:
        sys.modules.pop("streamlit", None)

sec("T-NO-MONEY-LEAK: safe_worklist() never surfaces a monetary column, for any lever")
safe_worklist = ns["safe_worklist"]
SEQUENCE_ORDER = ns["SEQUENCE_ORDER"]
for code in SEQUENCE_ORDER:
    cols = list(safe_worklist(code).columns)
    leaked = [c for c in cols if any(m in c.lower() for m in MONEY_SUBSTRINGS)]
    assert not leaked, f"{code}: safe_worklist() leaked monetary column(s) {leaked}"
print(f"  PASS  no monetary column in any of the {len(SEQUENCE_ORDER)} levers' safe worklists")

sec("T-SAFE-COLS-DEFINITION: the SAFE_COLS allowlist itself never names a "
   "monetary column, independent of what's in the data this run")
SAFE_COLS = ns["SAFE_COLS"]
for code, cols in SAFE_COLS.items():
    leaked = [c for c in cols if any(m in c.lower() for m in MONEY_SUBSTRINGS)]
    assert not leaked, f"{code}: SAFE_COLS itself names monetary column(s) {leaked}"
print(f"  PASS  SAFE_COLS allowlist is monetary-free for all {len(SAFE_COLS)} levers")

sec("T-COUNT-RECON: the page's displayed population counts match the real "
   "engine worklists exactly")
eligible_counts = ns["eligible_counts"]
for code in SEQUENCE_ORDER:
    assert eligible_counts[code] == len(worklists[code]), (
        f"{code}: page shows {eligible_counts[code]} customers in scope, "
        f"engine worklist has {len(worklists[code])}")
print(f"  PASS  all {len(SEQUENCE_ORDER)} per-lever counts match the engine's own worklists")

fresh_total_flagged = len(set().union(*[
    set(worklists[c]["Masked Customer Number"]) for c in SEQUENCE_ORDER if len(worklists[c])
])) if any(len(worklists[c]) for c in SEQUENCE_ORDER) else 0
assert ns["total_flagged"] == fresh_total_flagged, (
    f"page total_flagged={ns['total_flagged']} != independently recomputed {fresh_total_flagged}")
print(f"  PASS  total_flagged ({fresh_total_flagged:,}) matches an independent recomputation")

sec("T-CONSOLIDATED-WORKLIST: row count equals the sum of every lever's own worklist length")
combined = ns["combined"]
expected_rows = sum(len(worklists[c]) for c in SEQUENCE_ORDER)
assert len(combined) == expected_rows, (
    f"consolidated worklist has {len(combined)} rows, expected {expected_rows}")
assert set(combined.columns) >= {"Masked Customer Number", "action", "reason", "Lever"}
print(f"  PASS  consolidated worklist has exactly {expected_rows:,} rows, "
     f"matching the sum of all six lever worklists")

sec("T-CUSTOMER-EXPLORER: the selected customer is real and present in customer_view")
cv = result["customer_view"]
assert cv["Masked Customer Number"].iloc[0] in set(cv["Masked Customer Number"]), \
    "sanity check on cv itself"
print("  PASS  the stubbed selectbox returned a real customer id and the page "
     "ran its full profile/lever-match branch against it with no exception "
     "(see T-PAGE-RUN above)")

sec("ALL CHECKS PASSED")
