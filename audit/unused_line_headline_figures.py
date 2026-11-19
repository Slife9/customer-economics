"""Headline figures of the Unused Credit Line Management module on the
committed app samples (samples/unused_lines/<dataset>), as the app computes
them. Used to report before / after for every calculation change.

    python audit/unused_line_headline_figures.py [--json out.json] [--set key.path=value ...]

--set overrides an assumption for this run only (e.g.
drawdown_risk.leq_source=workbook_segment); values are read as JSON, falling
back to a string.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.unused_lines import assumptions as A, data as D, segments as SG  # noqa: E402
from engine.unused_lines import levers as L, strategies as ST, treatment as T  # noqa: E402

SAMPLES = ROOT / "samples" / "unused_lines"


def frame(name: str, cfg: dict) -> pd.DataFrame:
    """The app's frame: the per-account file, protected customers from the
    engine view, then segments and costs."""
    acc, meta = D.load_account_frame(SAMPLES / name / "accounts.parquet")
    ev = pd.read_parquet(SAMPLES / name / "engine_view.parquet").set_index("Masked Customer Number")
    acc["protected"] = acc["customer"].map(ev["protected"]).fillna(False).astype(bool)
    acc["suppression_reason"] = acc["customer"].map(ev["suppression_reason"]).fillna("")
    return SG.build(acc, meta, cfg)


def worklists(name: str) -> dict:
    ev = pd.read_parquet(SAMPLES / name / "engine_view.parquet")
    return {c: ev.loc[ev[f"in_{c}"], ["Masked Customer Number"]] for c in ["L1", "L3", "L5"] if f"in_{c}" in ev}


def figures(name: str, cfg: dict) -> dict:
    f = frame(name, cfg)
    sc = f[f["screened"]]
    res = L.run(f, cfg, "base")
    s = L.summary(res, cfg, f)
    go = cfg["stress_test"]["go_no_go_multiplier"]
    g = L.summary(L.run(f, cfg, "base", go), cfg, f)["workbook_levers_headline"]
    t = T.design(f, cfg, res, worklists=worklists(name))
    acted = t[t["recommended_levers"] != "none"]
    codes = acted["all_reason_codes"].str.split("; ").explode()
    scope = res["scope"]
    per = {k: float(v[scope]["headline_value"].sum()) for k, v in res["per_lever"].items()}
    camp = res["per_lever"]["engagement_campaign"][scope]["headline_value"].groupby(f["rule_segment"]).sum()
    st = ST.summary(ST.run(res, cfg), cfg)
    return {
        "strategies": {k: {"value": v["headline_value"], "status": v["status_label"], "customers": v["customers"],
                           "leaving": v["accounts_leaving"], "unused_removed": v["unused_removed"],
                           "capital_freed": v["capital_released"], "components": v["components"]}
                       for k, v in st["strategies"].items()},
        "approved_combined": st["approved_combined"],
        "proposed": st["proposed"], "awaiting_decision": st["awaiting_decision"],
        "total_potential": st["total_potential"], "warning_letters": st["warning_letters"],
        "screened_accounts": int(len(sc)),
        "unused_credit": float(sc["ucl"].sum()),
        "per_lever_value": per,
        "campaign_value_by_segment": {k: float(v) for k, v in camp.items()},
        "approved_unused_removed": s["workbook_levers_headline"]["unused_removed"],
        "approved_accounts_leaving": s["workbook_levers_headline"]["accounts_leaving"],
        "card_profit": float(sc["card_profit"].sum()),
        "carrying_cost": float(sc["carrying_cost"].sum()),
        "drawdown_loss": float(sc["drawdown_el"].sum()),
        "base_annual_value": s["workbook_levers_headline"]["headline_value"],
        "base_card_profit_change": s["workbook_levers_headline"]["card_profit_change"],
        "pending_b6_value": s["pending_approval"]["headline_value"],
        "extra_levers_value": s["extra_levers"]["headline_value"],
        "stress_1_5x_value": g["headline_value"],
        "stress_1_5x_card_profit_change": g["card_profit_change"],
        "capital_released": s["capital_released_one_time"],
        "accounts_with_action": int(len(acted)),
        "primary_reason_codes": acted["reason_code"].value_counts().to_dict(),
        "all_reason_codes": codes.value_counts().to_dict(),
    }


def _parse(sets: list[str]) -> dict:
    out: dict = {}
    for s in sets:
        key, val = s.split("=", 1)
        try:
            v = json.loads(val)
        except json.JSONDecodeError:
            v = val
        d = out
        *path, last = key.split(".")
        for p in path:
            d = d.setdefault(p, {})
        d[last] = v
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=None)
    ap.add_argument("--set", nargs="*", default=[])
    ap.add_argument("--datasets", nargs="*", default=["stress", "demo"])
    a = ap.parse_args()
    cfg, _ = A.load()
    if a.set:
        cfg = A.with_overrides(cfg, _parse(a.set))
    out = {d: figures(d, cfg) for d in a.datasets}
    print(json.dumps(out, indent=2))
    if a.json:
        Path(a.json).write_text(json.dumps(out, indent=2) + "\n")
