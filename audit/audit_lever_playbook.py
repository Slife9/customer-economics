"""Verification script for the redesigned Lever Playbook content and page.
Run as a script, like the other files in this directory - there is no
pytest suite in this repo to join.

    python audit/audit_lever_playbook.py
"""
import importlib
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.lib.lever_playbook_content import (  # noqa: E402
    CORE_CONCEPTS, LEVERS, SEQUENCE_ORDER, REQUIRED_LEVER_FIELDS)


def sec(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


sec("T-STRUCTURE: every lever has every required field, non-empty")
# A minimum per field, not a blanket one: some levers genuinely have a
# single action (L3, L6) or a single data source, but sequence, teams,
# kpis, risks, and checklist are always multi-step/multi-party/multi-item
# by construction of a real implementation plan.
LIST_FIELD_MINIMUMS = {
    "data_needed": 1, "actions": 1, "sequence": 3, "teams": 3,
    "kpis": 3, "risks": 3, "checklist": 5,
}
for lv in LEVERS:
    missing = [f for f in REQUIRED_LEVER_FIELDS if f not in lv]
    assert not missing, f"{lv.get('code', '?')} missing fields: {missing}"
    for f, minimum in LIST_FIELD_MINIMUMS.items():
        assert isinstance(lv[f], list) and len(lv[f]) >= minimum, \
            f"{lv['code']}.{f} must be a list with at least {minimum} " \
            f"entries, got {lv[f]!r}"
    for f in ["problem", "why_it_matters", "population", "approvals", "testing",
             "evolution", "worked_example"]:
        assert isinstance(lv[f], str) and len(lv[f].strip()) >= 30, \
            f"{lv['code']}.{f} must be a substantive, non-trivial string"
    assert isinstance(lv["constants"], dict)
print(f"  PASS  all {len(LEVERS)} levers carry every required field with "
     f"substantive content")

sec("T-SEQUENCE: SEQUENCE_ORDER matches the levers' own codes exactly")
codes = {lv["code"] for lv in LEVERS}
assert set(SEQUENCE_ORDER) == codes, \
    f"SEQUENCE_ORDER {sorted(SEQUENCE_ORDER)} != lever codes {sorted(codes)}"
assert len(SEQUENCE_ORDER) == len(set(SEQUENCE_ORDER)), "SEQUENCE_ORDER has a duplicate"
print(f"  PASS  SEQUENCE_ORDER covers exactly {sorted(codes)}, no duplicates")

sec("T-MODULE-PATHS: every cited engine module actually exists in this repo")
for lv in LEVERS:
    p = ROOT / lv["module"]
    assert p.exists(), f"{lv['code']} cites {lv['module']}, which does not exist"
print(f"  PASS  all {len(LEVERS)} cited engine modules exist on disk")

sec("T-TEAMS-KPIS-SHAPE: teams are (name, role) pairs, KPIs are (name, "
   "definition, cadence) triples")
for lv in LEVERS:
    for t in lv["teams"]:
        assert isinstance(t, tuple) and len(t) == 2 and all(t), \
            f"{lv['code']}: malformed team entry {t!r}"
    for k in lv["kpis"]:
        assert isinstance(k, tuple) and len(k) == 3 and all(k), \
            f"{lv['code']}: malformed KPI entry {k!r}"
print("  PASS  every team and KPI entry is well-formed")

sec("T-CONSTANTS-DRIFT: numeric claims in the playbook still match the real "
   "engine constants they describe - catches the engine changing without "
   "this page being updated")
from engine.levers import l1_rewards, l2_lines, l3_pricing  # noqa: E402

CHECKS = [
    ("L1", "OPPORTUNITY_REWARD_VALUE_FLOOR", l1_rewards.OPPORTUNITY_REWARD_VALUE_FLOOR),
    ("L2", "MIN_SEASONING_MONTHS", l2_lines.MIN_SEASONING_MONTHS),
    ("L2", "IDLE_AVG_UTIL_CEILING", l2_lines.IDLE_AVG_UTIL_CEILING),
    ("L2", "IDLE_PEAK_UTIL_CEILING", l2_lines.IDLE_PEAK_UTIL_CEILING),
    ("L2", "IDLE_SPEND_TO_LIMIT_CEILING", l2_lines.IDLE_SPEND_TO_LIMIT_CEILING),
    ("L2", "DORMANT_SPEND_TO_LIMIT_CEILING", l2_lines.DORMANT_SPEND_TO_LIMIT_CEILING),
    ("L2", "DORMANT_INACTIVE_SHARE_FLOOR", l2_lines.DORMANT_INACTIVE_SHARE_FLOOR),
    ("L2", "ACTIVE_TRANSACTOR_SHARE_FLOOR", l2_lines.ACTIVE_TRANSACTOR_SHARE_FLOOR),
    ("L2", "IDLE_LIMIT_FLOOR", l2_lines.IDLE_LIMIT_FLOOR),
    ("L2", "STRETCHED_PEAK_UTIL_FLOOR", l2_lines.STRETCHED_PEAK_UTIL_FLOOR),
    ("L3", "PRICING_GAP_POINTS", l3_pricing.PRICING_GAP_POINTS),
    ("L3", "FIRST_YEAR_MONTHS", l3_pricing.FIRST_YEAR_MONTHS),
]
lv_by_code = {lv["code"]: lv for lv in LEVERS}
for code, const_name, live_value in CHECKS:
    claimed = lv_by_code[code]["constants"].get(const_name)
    assert claimed is not None, f"{code} playbook never recorded {const_name}"
    assert claimed == live_value, (
        f"{code}.{const_name}: playbook says {claimed}, engine/levers now has "
        f"{live_value} - the playbook text is stale, update it")
print(f"  PASS  all {len(CHECKS)} numeric claims match the live engine constants")

from engine.levers.l5_retention import SPEND_DECLINE_THRESHOLD, RATE_ABOVE_PEER_POINTS  # noqa: E402
l5 = lv_by_code["L5"]["constants"]
assert l5["SPEND_DECLINE_THRESHOLD"] == SPEND_DECLINE_THRESHOLD
assert l5["RATE_ABOVE_PEER_POINTS"] == RATE_ABOVE_PEER_POINTS
print("  PASS  L5's constants also match the live engine")

from engine.levers.l4_cost_to_serve import AVOIDABLE_CALL_REASONS  # noqa: E402
l4 = lv_by_code["L4"]["constants"]
assert l4["AVOIDABLE_CALL_THRESHOLD"] == 3, "L2's population() hardcodes >= 3 avoidable calls"
assert l4["PAPER_STATEMENT_THRESHOLD"] == 6, "L4's population() hardcodes >= 6 paper statements"
assert len(AVOIDABLE_CALL_REASONS) == 3, (
    f"L4 playbook describes 3 avoidable call reasons "
    f"(billing/rewards/rate query); engine now has {len(AVOIDABLE_CALL_REASONS)}")
print("  PASS  L4's avoidable-call-reason count and thresholds match the live engine")

sec("T-CORE-CONCEPTS: present and substantive")
assert len(CORE_CONCEPTS) >= 4
for c in CORE_CONCEPTS:
    assert len(c["title"]) > 10 and len(c["body"].strip()) > 100
print(f"  PASS  {len(CORE_CONCEPTS)} core-concept entries, all substantive")

sec("T-PAGE-SMOKE: the Streamlit page itself executes top-to-bottom without "
   "raising, given a stubbed Streamlit module (no live server/session needed, "
   "since this page never reads st.session_state)")


class _Noop:
    """Swallows every Streamlit call (st.header(...), a context-managed
    st.tabs(...), etc.) so the real page module can be exec'd exactly as
    written and only fail on an actual Python bug - never on the absence
    of a live Streamlit server. st.columns(n) and st.tabs([...]) are
    unpacked by the page (e.g. `a, b = st.columns(2)`), so their arity
    must match exactly what was asked for, not an arbitrary fixed count."""

    def __call__(self, *a, **k):
        if a:
            n = a[0]
            if isinstance(n, int):
                return tuple(_Noop() for _ in range(n))
            if isinstance(n, (list, tuple)):
                return tuple(_Noop() for _ in range(len(n)))
        return _Noop()

    def __getattr__(self, name):
        return _Noop()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


stub = _Noop()
real_streamlit = sys.modules.get("streamlit")
sys.modules["streamlit"] = stub
try:
    runpy.run_path(str(ROOT / "app" / "pages" / "21_Lever_Playbook.py"), run_name="__not_main__")
    print("  PASS  21_Lever_Playbook.py executes top-to-bottom with no exception")
finally:
    if real_streamlit is not None:
        sys.modules["streamlit"] = real_streamlit
    else:
        sys.modules.pop("streamlit", None)

sec("ALL CHECKS PASSED")
