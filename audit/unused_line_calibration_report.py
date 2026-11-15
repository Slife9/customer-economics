"""Unused-line calibration report (specs/unused_line_management, brief section 5).

    python audit/unused_line_calibration_report.py --data <portfolio dir> [--out <dir>]

Compares a generated portfolio with the segment inputs of the Unused Line RWA
Scenario Model (workbook *Assumptions* sheet) and writes
`Validation_Report_Unused_Line_Calibration.csv` into `--out` (default: the
portfolio directory).

It runs AFTER generation, as a separate script, because the workbook screen
needs fully loaded card profit, which only the engine computes. It builds the
engine's card ledger (engine.core.ledger) and nothing else, and changes no
engine calculation. Fully loaded card profit here is the engine's card
net_economic_profit, which still carries the OLD capital charge on drawn
balances and none of the brief section 2 carrying costs - the module replaces
that in Stage 3, so screen size and loss will move.

This is an independent, simplified reading of the workbook rules, written
before the module's own segment engine (Stage 4), which is cross-checked
against it later. Within Band is within / outside / not assessed.
Informational only: an `outside` row is a known calibration gap, not a
failure. The script always exits 0 once it has written the report.

Population and rules, per card account, trailing 12 cycles:
  screen    open at the last cycle, not charged off, open >= 12 months,
            fully loaded card profit < 0, average utilisation < 30%,
            current unused line >= $5,000 (fraud-blocked proxy not applied)
  1 Credit-Deteriorating  latest PD 12 Month >= 4%, or bureau score down
                          >= 40 points over 6 months (Table29)
  2 Relationship          customer non-card profit (deposit + loan net)
                          >= $150 a year, or deposit balances >= $25,000
                          (latest cycle), or Segment Premier / Private Banking
  3 Dormant               no transactions in 12 cycles and a $0 balance in
                          every one of them
  4 Sock-Drawer           active (any transaction) <= 4 of 12 cycles and
                          spend < $2,500
  5 Transactors           paid in full >= 10 of 12 (Table4 indicator as
                          written), peak statement utilisation < 15%
                          (ending balance + payment over the limit), spend
                          >= $6,000
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

from engine.core.contract import load_portfolio  # noqa: E402
from engine.core import ledger as LEDGER  # noqa: E402

REPORT = "Validation_Report_Unused_Line_Calibration.csv"
SOURCE = ("estimated - source: Unused Line RWA Scenario Model, Assumptions sheet "
          "(illustrative inputs)")
BAND = 0.25
K = "Masked Account Number"
SEGMENTS = ["Credit-Deteriorating", "Relationship / Premium", "Dormant / Inactive",
            "Sock-Drawer", "Low-Utilization Transactors"]
# Workbook Assumptions, in SEGMENTS order (its own column order differs).
REFERENCE = {
    "Share of screened accounts": [8000 / 93000, 10000 / 93000, 30000 / 93000,
                                   20000 / 93000, 25000 / 93000],
    "Credit line USD": [12000, 35000, 8000, 10000, 20000],
    "Balance USD": [1500, 3000, 0, 300, 1500],
    "Revolving balance USD": [1200, 500, 0, 100, 0],
    "Annual spend USD": [2500, 30000, 0, 1500, 18000],
    "PD 12 month": [0.06, 0.004, 0.01, 0.015, 0.005],
}
UNASSIGNED_MAX = 0.10
LOSS_PER_SCREENED_ACCOUNT = -9_044_043 / 93_000
SCREEN = {"max_utilisation": 0.30, "min_unused_usd": 5000, "min_history_months": 12}


def _row(segment, metric, observed, reference, accounts=None, note="", band=True):
    missing = observed is None or (isinstance(observed, float) and np.isnan(observed))
    if missing or reference is None:
        return {"Segment": segment, "Metric": metric,
                "Observed": None if missing else round(float(observed), 6),
                "Reference": reference, "Band Low": None, "Band High": None,
                "Within Band": "not assessed",
                "Accounts": None if accounts is None else int(accounts),
                "Reference Source": SOURCE, "Note": note}
    if not band:
        verdict, lo, hi = ("within" if observed <= reference else "outside"), None, reference
    else:
        lo, hi = sorted([reference * (1 - BAND), reference * (1 + BAND)])
        if reference == 0:
            lo, hi = 0.0, 0.0
        verdict = "within" if lo - 1e-9 <= observed <= hi + 1e-9 else "outside"
    return {"Segment": segment, "Metric": metric,
            "Observed": None if verdict == "not assessed" else round(float(observed), 6),
            "Reference": reference, "Band Low": None if lo is None else round(lo, 6),
            "Band High": round(hi, 6), "Within Band": verdict,
            "Accounts": None if accounts is None else int(accounts),
            "Reference Source": SOURCE, "Note": note}


def account_frame(data_dir: Path) -> pd.DataFrame:
    """One row per card account with everything the screen and the rules
    need, over the trailing 12 cycles."""
    portfolio = load_portfolio(data_dir)
    led = LEDGER.build(portfolio)
    L = led["card"]
    cycles = sorted(L["Cycle Month"].unique())
    last12, last = cycles[-12:], cycles[-1]

    t = L[L["Cycle Month"].isin(last12)].groupby(K).agg(
        cust=("Masked Customer Number", "first"), card_profit=("net_economic_profit", "sum"))

    cyc = portfolio["Table4_Account_Cycle.csv"]
    c12 = cyc[cyc["Cycle Month"].isin(last12)]
    g = c12.groupby(K)
    t["avg_util"] = g["Utilization"].mean()
    t["pif_months"] = g["Paid In Full Indicator"].sum()
    t["max_balance"] = g["Ending Balance"].max()
    stmt_util = (c12["Ending Balance"] + c12["Payment Made"]) / c12["Credit Limit"].where(c12["Credit Limit"] > 0)
    t["peak_stmt_util"] = stmt_util.groupby(c12[K]).max()
    rb = np.where(c12["Purchase Interest"] > 0, c12["Purchase Balance"], 0.0)
    t["revolving"] = pd.Series(rb, index=c12.index).groupby(c12[K]).mean()
    latest = cyc[cyc["Cycle Month"] == last].set_index(K)
    t["open_at_last"] = t.index.isin(latest.index)
    t["charged_off"] = latest["Charged Off Indicator"].reindex(t.index).fillna(True).astype(bool)
    t["line"] = latest["Credit Limit"].reindex(t.index)
    t["balance"] = latest["Ending Balance"].reindex(t.index)
    t["unused"] = (t["line"] - t["balance"]).clip(lower=0)

    open_ix = portfolio["Table2b_Account_Open_Reference.csv"].set_index(K)["Account Open Cycle Index"]
    t["months_open"] = len(cycles) - open_ix.reindex(t.index)

    tx = portfolio["Table5_Transaction.csv"]
    x12 = tx[tx["Cycle Month"].isin(last12)]
    t["spend"] = x12[~x12["Cash Advance Indicator"].astype(bool)].groupby(K)["Transaction Amount"].sum()
    t["active_months"] = x12.groupby(K)["Cycle Month"].nunique()
    t["tx_count"] = x12.groupby(K).size()
    t[["spend", "active_months", "tx_count"]] = t[["spend", "active_months", "tx_count"]].fillna(0)

    risk = portfolio["Table8_Risk_Parameters.csv"]
    t["pd12"] = risk[risk["Cycle Month"] == last].set_index(K)["PD 12 Month"].reindex(t.index)
    t29 = pd.read_csv(data_dir / "Table29_Score_History.csv",
                      usecols=[K, "Cycle Month", "Bureau Score Change 6 Months"])
    t["score_change_6m"] = t29[t29["Cycle Month"] == last].set_index(K)[
        "Bureau Score Change 6 Months"].reindex(t.index)

    cust = pd.read_csv(data_dir / "Table1_Customer.csv", usecols=["Masked Customer Number", "Segment"])
    t["segment_field"] = t["cust"].map(cust.set_index("Masked Customer Number")["Segment"])
    dep, loan = led["deposit_by_customer"], led["loan_by_customer"]
    noncard = (dep[dep["Cycle Month"].isin(last12)].groupby("Masked Customer Number")["deposit_net"].sum()
               .add(loan[loan["Cycle Month"].isin(last12)].groupby("Masked Customer Number")["loan_net"].sum(),
                    fill_value=0.0))
    t["noncard_profit"] = t["cust"].map(noncard).fillna(0.0)
    d6 = portfolio.get("Table6b_Deposit_Account_Cycle.csv")
    if d6 is not None and len(d6):
        dep_bal = d6[d6["Cycle Month"] == last].groupby("Masked Customer Number")["Ending Balance"].sum()
        t["deposit_balance"] = t["cust"].map(dep_bal).fillna(0.0)
    else:
        t["deposit_balance"] = 0.0
    return t


def assign(t: pd.DataFrame) -> pd.DataFrame:
    s = (t["open_at_last"] & ~t["charged_off"]
         & (t["months_open"] >= SCREEN["min_history_months"])
         & (t["card_profit"] < 0) & (t["avg_util"] < SCREEN["max_utilisation"])
         & (t["unused"] >= SCREEN["min_unused_usd"]))
    rules = [
        (t["pd12"] >= 0.04) | (t["score_change_6m"] <= -40),
        (t["noncard_profit"] >= 150) | (t["deposit_balance"] >= 25000)
        | t["segment_field"].isin(["Premier", "Private Banking"]),
        (t["tx_count"] == 0) & (t["max_balance"] == 0),
        (t["active_months"] <= 4) & (t["spend"] < 2500),
        (t["pif_months"] >= 10) & (t["peak_stmt_util"] < 0.15) & (t["spend"] >= 6000),
    ]
    seg = np.select(rules, SEGMENTS, default="Unassigned")
    return t.assign(screened=s, segment=np.where(s, seg, ""))


def report(data_dir: Path, out_dir: Path) -> dict:
    t = assign(account_frame(data_dir))
    sc = t[t["screened"]]
    n = len(sc)
    rows = [
        _row("Screen", "Screened share of open card accounts", n / max(int(t["open_at_last"].sum()), 1),
             None, n, "No workbook reference (93,000 screened of an unstated book)"),
        _row("Screen", "Fully loaded card loss per screened account USD",
             sc["card_profit"].mean() if n else None, LOSS_PER_SCREENED_ACCOUNT, n,
             "Engine card profit with the old drawn-balance capital charge"),
    ]
    for i, seg in enumerate(SEGMENTS):
        g = sc[sc["segment"] == seg]
        obs = {
            "Share of screened accounts": len(g) / n if n else None,
            "Credit line USD": g["line"].mean() if len(g) else None,
            "Balance USD": g["balance"].mean() if len(g) else None,
            "Revolving balance USD": g["revolving"].mean() if len(g) else None,
            "Annual spend USD": g["spend"].mean() if len(g) else None,
            "PD 12 month": g["pd12"].mean() if len(g) else None,
        }
        for metric, ref in REFERENCE.items():
            rows.append(_row(seg, metric, obs[metric], ref[i], len(g)))
    un = (sc["segment"] == "Unassigned").mean() if n else None
    rows.append(_row("Unassigned", "Share of screened accounts (at most)", un, UNASSIGNED_MAX,
                     int((sc["segment"] == "Unassigned").sum()), band=False))
    df = pd.DataFrame(rows)
    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_dir / REPORT, index=False)
    v = df["Within Band"].value_counts()
    return {"screened_accounts": n, "open_card_accounts": int(t["open_at_last"].sum()),
            "segments": sc["segment"].value_counts().to_dict(),
            "within": int(v.get("within", 0)), "outside": int(v.get("outside", 0)),
            "not assessed": int(v.get("not assessed", 0)), "report": str(out_dir / REPORT)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", default=None, help="where to write the report (default: --data)")
    a = ap.parse_args()
    d = Path(a.data)
    print(json.dumps(report(d, Path(a.out) if a.out else d), indent=2, default=str))
