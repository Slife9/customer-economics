"""Unused-line calibration report (specs/unused_line_management, brief section 5).

    python audit/unused_line_calibration_report.py --data <portfolio dir> [--out <dir>]

Compares a generated portfolio with the segment inputs of the Unused Line RWA
Scenario Model (workbook *Assumptions* sheet) and writes
`Validation_Report_Unused_Line_Calibration.csv` into `--out` (default: the
portfolio directory). Informational only: an `outside` row is a known
calibration gap, not a failure; the script exits 0 once it has written the
report.

Profit is the module's (engine/unused_lines): the engine's card_net with the
old capital charge replaced by the brief s.2 charge and the liquidity cost
subtracted; drawdown loss beside it (answers 3 and 4). Two loss rows compare
like with like:
  card profit                     vs the workbook's fully loaded profit
                                  without its loss on the undrawn line
  card profit - drawdown loss     vs the workbook's fully loaded profit
                                  (-$97.25 per account)

The segment rules here are an independent, simplified reading of the
workbook's Segment Definitions (thresholds from the module's config), written
before the module's own segment engine (Stage 4), which is cross-checked
against it. Balance, utilisation and unused line are measured on the 12-month
average statement balance (Ending Balance + Payment Made), the workbook's
meaning; the screen uses Table4's own Utilization and the current unused line.

Population, per card account, trailing 12 cycles:
  screen    open at the reporting date, not charged off, open >= 12 months,
            profit < 0 on the configured basis (default: card profit less
            drawdown loss, the workbook's), average utilisation < 30%, current
            unused line >= $5,000 (fraud-blocked proxy not applied here)
  1 Credit-Deteriorating  PD 12 Month >= 4%, or bureau score down >= 40
                          points over 6 months (Table29)
  2 Relationship          non-card profit >= $150 a year, or deposits >=
                          $25,000, or Segment Premier / Private Banking
  3 Dormant               no transactions and a $0 balance in all 12 cycles
  4 Sock-Drawer           active <= 4 of 12 cycles and spend < $2,500
  5 Transactors           paid in full >= 10 of 12 (a $0 statement counts as
                          nothing due), peak statement utilisation < 15%,
                          spend >= $6,000
  6 Unassigned            none of the above
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.unused_lines import assumptions as A, data as D, exposure as X  # noqa: E402

REPORT = "Validation_Report_Unused_Line_Calibration.csv"
SOURCE = ("estimated - source: Unused Line RWA Scenario Model, Assumptions sheet "
          "(illustrative inputs)")
BAND = 0.25
ZERO_TOLERANCE = {"usd": 10.0, "rate": 0.001}  # for a reference of exactly 0
ORDER = ["deteriorating", "relationship", "dormant", "sock_drawer", "transactors"]
PROFIT_BASIS = {"card_profit_less_drawdown_loss": "profit_after_drawdown", "card_profit": "card_profit"}


def references(cfg: dict) -> tuple[dict, dict]:
    """Per-segment reference metrics and the per-account loss references,
    computed from the workbook model (nothing typed in)."""
    seg = cfg["workbook"]["segments"]
    p = cfg["workbook"]["portfolio"]
    n_all = sum(s["accounts"] for s in seg.values())
    ref = {}
    for k in ORDER:
        s = seg[k]
        und = s["credit_line"] - s["balance"]
        ref[k] = {"Share of screened accounts": s["accounts"] / n_all, "Credit line USD": s["credit_line"],
                  "Balance USD": s["balance"], "Utilisation": s["balance"] / s["credit_line"],
                  "Unused line USD": und, "Revolving balance USD": s["revolving_balance"],
                  "Annual spend USD": s["spend"], "PD 12 month": s["pd_annual"]}
    wb = X.workbook_baseline(cfg)
    undrawn_el = sum(seg[k]["accounts"] * seg[k]["pd_annual"] * p["lgd"] * seg[k]["leq"]
                     * (seg[k]["credit_line"] - seg[k]["balance"]) for k in ORDER)
    fully = wb.loc["total", "fully_loaded_profit"] / n_all
    return ref, {"after_drawdown": fully, "before_drawdown": fully + undrawn_el / n_all}


def _row(segment, metric, observed, reference, accounts=None, note="", at_most=False):
    missing = observed is None or (isinstance(observed, float) and np.isnan(observed))
    base = {"Segment": segment, "Metric": metric, "Observed": None if missing else round(float(observed), 6),
            "Reference": None if reference is None else round(float(reference), 6),
            "Accounts": None if accounts is None else int(accounts), "Reference Source": SOURCE, "Note": note}
    if missing or reference is None:
        return base | {"Band Low": None, "Band High": None, "Within Band": "not assessed"}
    if at_most:
        lo, hi = None, reference
        ok = observed <= reference
    elif reference == 0:
        # A +/-25% band around zero is empty; allow a rounding-size amount.
        lo, hi = 0.0, ZERO_TOLERANCE["usd" if "USD" in metric else "rate"]
        ok = abs(observed) <= hi
    else:
        lo, hi = sorted([reference * (1 - BAND), reference * (1 + BAND)])
        ok = lo - 1e-9 <= observed <= hi + 1e-9
    return base | {"Band Low": None if lo is None else round(lo, 6), "Band High": round(hi, 6),
                   "Within Band": "within" if ok else "outside"}


def rule_segment(t: pd.DataFrame, cfg: dict) -> np.ndarray:
    """The workbook's rules in priority order, on every account (they do not
    depend on profit)."""
    r = cfg["segments"]["rules"]
    pif = t["cycles_paid_in_full_12m"] + t["cycles_zero_statement_12m"]
    rules = [
        (t["pd_12m"] >= r["deteriorating"]["pd_annual_min"])
        | (t["bureau_score_change_6m"] <= -r["deteriorating"]["score_drop_6m_min"]),
        (t["noncard_profit"] >= r["relationship"]["noncard_profit_min_usd"])
        | (t["deposit_balance"] >= r["relationship"]["deposits_plus_investments_min_usd"])
        | t["customer_segment"].isin(r["relationship"]["premium_segments"]),
        (t["active_months_12m"] == 0) & (t["months_with_balance_12m"] == 0),
        (t["active_months_12m"] <= r["sock_drawer"]["active_months_max"])
        & (t["spend_12m"] < r["sock_drawer"]["spend_max_usd"]),
        (pif >= r["transactors"]["paid_in_full_months_min"])
        & (t["peak_statement_utilisation_12m"] < r["transactors"]["peak_utilisation_max"])
        & (t["spend_12m"] >= r["transactors"]["spend_min_usd"]),
    ]
    return np.select(rules, ORDER, default="unassigned")


def frame(data_dir: Path, cfg: dict) -> pd.DataFrame:
    """Rules on every account, then LEQ by the rule's segment (Unassigned:
    the measured portfolio Behavioral CCF), then the s.2 costs."""
    acc, meta = D.account_frame(data_dir)
    acc["rule_segment"] = rule_segment(acc, cfg)
    acc["leq"] = acc["rule_segment"].map(cfg["drawdown_risk"]["leq_by_segment"]).fillna(
        meta["leq_unassigned_measured"])
    t = X.account_costs(acc, cfg)
    t["profit_after_drawdown"] = t["card_profit"] - t["drawdown_el"]
    return t


def assign(t: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    sc = cfg["screen"]
    screened = (t["open_at_reporting_date"] & ~t["charged_off"]
                & (t["account_age_months"] >= sc["min_history_months"])
                & (t[PROFIT_BASIS[sc["profit_basis"]]] < 0) & (t["utilisation_avg_12m"] < sc["max_utilisation"])
                & (t["ucl_current"] >= sc["min_unused_usd"]))
    return t.assign(screened=screened, segment=np.where(screened, t["rule_segment"], ""))


def report(data_dir: Path, out_dir: Path) -> dict:
    cfg, _ = A.load()
    labels = cfg["segments"]["labels"]
    ref, loss_ref = references(cfg)
    t = assign(frame(data_dir, cfg), cfg)
    sc = t[t["screened"]]
    n = len(sc)
    open_n = int((t["open_at_reporting_date"] & ~t["charged_off"]).sum())
    rows = [
        _row("Screen", "Screened share of open card accounts", n / max(open_n, 1), None, n,
             "No workbook reference (93,000 screened of an unstated book)"),
        _row("Screen", "Card profit per screened account USD", sc["card_profit"].mean() if n else None,
             loss_ref["before_drawdown"], n,
             "Module card profit (new capital and liquidity, measured credit cost) vs the workbook's "
             "fully loaded profit without its loss on the undrawn line"),
        _row("Screen", "Card profit less drawdown loss per screened account USD",
             sc["profit_after_drawdown"].mean() if n else None, loss_ref["after_drawdown"], n,
             "Workbook-comparable: the workbook's fully loaded profit includes the undrawn-line loss"),
    ]
    for k in ORDER:
        g = sc[sc["segment"] == k]
        has = len(g) > 0
        bal = g["statement_balance_avg_12m"]
        obs = {
            "Share of screened accounts": len(g) / n if n else None,
            "Credit line USD": g["limit_current"].mean() if has else None,
            "Balance USD": bal.mean() if has else None,
            "Utilisation": (bal / g["limit_current"]).mean() if has else None,
            "Unused line USD": (g["limit_current"] - bal).clip(lower=0).mean() if has else None,
            "Revolving balance USD": g["revolving_balance_avg_12m"].mean() if has else None,
            "Annual spend USD": g["spend_12m"].mean() if has else None,
            "PD 12 month": g["pd_12m"].mean() if has else None,
        }
        for metric, r in ref[k].items():
            rows.append(_row(labels[k], metric, obs[metric], r, len(g)))
    un = sc["segment"].eq("unassigned")
    rows.append(_row(labels["unassigned"], "Share of screened accounts (at most)", un.mean() if n else None,
                     cfg["segments"]["rules"]["unassigned"]["share_target_max"], int(un.sum()), at_most=True))
    df = pd.DataFrame(rows)
    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_dir / REPORT, index=False)
    v = df["Within Band"].value_counts()
    return {"screened_accounts": n, "open_card_accounts": open_n,
            "segments": {labels.get(k, k): int(c) for k, c in sc["segment"].value_counts().items()},
            "within": int(v.get("within", 0)), "outside": int(v.get("outside", 0)),
            "not assessed": int(v.get("not assessed", 0)), "report": str(out_dir / REPORT)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", default=None, help="where to write the report (default: --data)")
    a = ap.parse_args()
    d = Path(a.data)
    print(json.dumps(report(d, Path(a.out) if a.out else d), indent=2, default=str))
