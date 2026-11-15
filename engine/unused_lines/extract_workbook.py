"""Extract the Unused Line RWA Scenario Model's inputs and reference outputs.

    python -m engine.unused_lines.extract_workbook

Reads specs/unused_line_management/Unused_Line_RWA_Scenario_Model.xlsx (cached
values; the workbook is never recalculated) and writes
config/workbook_model.json: the per-segment Assumptions, the portfolio-wide
inputs, the capital regime table, the three scenarios' levers and the
Dashboard's figures. The workbook's sha256 is recorded inside, so a changed
workbook is visible. Everything in it is an illustrative industry-average
estimate from the workbook, not portfolio data.

The module reads this file only in workbook-reproduction mode and as the
default lever and response values; the agreed regulatory settings live in
unused_line_assumptions.json.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[2]
WORKBOOK = ROOT / "specs" / "unused_line_management" / "Unused_Line_RWA_Scenario_Model.xlsx"
OUT = Path(__file__).parent / "config" / "workbook_model.json"

# Workbook column order (C..G) and the module's segment keys.
COLS = "CDEFG"
SEGMENTS = ["dormant", "sock_drawer", "transactors", "deteriorating", "relationship"]
SEGMENT_ROWS = {  # Assumptions sheet
    "accounts": 6, "credit_line": 7, "balance": 8, "revolving_balance": 9, "spend": 10,
    "interchange_rate": 11, "reward_rate": 12, "apr": 13, "annual_fee": 14, "other_fee": 15,
    "pd_annual": 16, "leq": 17, "variable_cost": 18, "fixed_cost": 19, "relationship_profit": 20,
    "response_rate": 24, "attrition_after_decrease": 25, "spend_loss_after_decrease": 26,
    "pd_increase_after_decrease": 27,
}
PORTFOLIO_ROWS = {
    "cost_of_funds": 31, "lgd": 32, "capital_ratio": 33, "cost_of_equity": 34,
    "lcr_outflow": 35, "negative_carry": 36, "promo_cost_rate": 37, "incentive_per_responder": 38,
    "minimum_line": 39, "headroom_over_balance": 40, "behavioural_response_multiplier": 41,
}
REGIME_ROWS = {"basel_endgame_2023": (45, 46), "current_us_standardized": (47, 48),
               "internal_model_irb": (49, 50)}
LEVER_ROWS = {"decrease_share": 0, "decrease_cut": 1, "closure_share": 2, "campaign_share": 3,
              "incremental_spend": 4, "incremental_revolving": 5, "campaign_cost": 6}
SCENARIO_FIRST_ROW = {"conservative": 6, "base": 17, "aggressive": 28}
DASHBOARD = {  # name: (baseline col/row, {scenario: col})
    "accounts": 9, "credit_line": 10, "undrawn": 11, "rwa": 13, "capital_charge": 14,
    "liquidity_cost": 15, "expected_credit_loss": 16, "revenue": 17, "contribution": 18,
    "fully_loaded_profit": 19, "relationship_adjusted_profit": 20,
}
SCENARIO_COL = {"conservative": "C", "base": "D", "aggressive": "E"}


def _row(ws, r: int) -> dict:
    return {s: float(ws[f"{c}{r}"].value) for s, c in zip(SEGMENTS, COLS)}


def extract() -> dict:
    raw = WORKBOOK.read_bytes()
    wb = openpyxl.load_workbook(WORKBOOK, data_only=True)
    a, lv, d = wb["Assumptions"], wb["Levers"], wb["Dashboard"]
    seg = {s: {} for s in SEGMENTS}
    for name, r in SEGMENT_ROWS.items():
        for s, v in _row(a, r).items():
            seg[s][name] = v
    regimes = {k: {"ccf": _row(a, rc), "risk_weight": _row(a, rr)} for k, (rc, rr) in REGIME_ROWS.items()}
    levers = {scn: {name: _row(lv, first + off) for name, off in LEVER_ROWS.items()}
              for scn, first in SCENARIO_FIRST_ROW.items()}
    dash = {"baseline": {k: float(d[f"B{r}"].value) for k, r in DASHBOARD.items()}}
    for scn, col in SCENARIO_COL.items():
        dash[scn] = {k: float(d[f"{col}{r}"].value) for k, r in DASHBOARD.items()}
        dash[scn]["change_in_fully_loaded_profit"] = float(d[f"{col}21"].value)
        dash[scn]["capital_released"] = float(d[f"{col}22"].value)
        dash[scn]["accounts_lost"] = float(d[f"{col}23"].value)
    base_by_segment = {s: {"baseline_profit": float(d[f"B{32 + i}"].value),
                           "change_in_profit": float(d[f"D{32 + i}"].value),
                           "capital_released": float(d[f"H{32 + i}"].value)}
                       for i, s in enumerate(SEGMENTS)}
    regime_table = {k: {"total_rwa": float(d[f"B{r}"].value), "undrawn_rwa": float(d[f"C{r}"].value)}
                    for k, r in zip(REGIME_ROWS, (41, 42, 43))}
    return {
        "_source": "Unused Line RWA Scenario Model (workbook cached values)",
        "_label": "estimated - source: Unused Line RWA Scenario Model (illustrative industry averages)",
        "_workbook_sha256": hashlib.sha256(raw).hexdigest(),
        "segments": seg,
        "portfolio": {k: float(a[f"C{r}"].value) for k, r in PORTFOLIO_ROWS.items()},
        "regimes": regimes,
        "levers": levers,
        "dashboard_reference": {**dash, "base_by_segment": base_by_segment, "regime_table": regime_table},
    }


if __name__ == "__main__":
    OUT.write_text(json.dumps(extract(), indent=2) + "\n")
    print(f"wrote {OUT}")
