"""Reward calibration report (specs/reward_data_additions, section 3).

    python audit/reward_calibration_report.py --data <portfolio dir>

Compares a generated portfolio with the reference ranges of the Reward
Profitability Scenario Model v2 and writes
`Validation_Report_Reward_Calibration.csv` into the portfolio directory.

It runs AFTER generation, as a separate script, because the reward model's
screen needs fully loaded card profit, which only the engine computes (cost
pools, capital, credit cost). It builds the engine's card ledger
(engine.core.ledger) and nothing else, and changes no engine calculation.

Within Band is within / outside / not assessed (no data or no model
reference). Informational only: an `outside` row is a known calibration gap (spec 6),
not a failure. The script always exits 0 once it has written the report.

Population and rules, per card account, trailing 12 cycles:
  screen    open at the last cycle, not charged off, open >= 6 months,
            fully loaded card profit < 0 and reward cost >= 50% of revenue
  1 Relationship  customer non-card profit (deposit + loan net) >= $150 a
                  year, or deposit balances >= $25,000 (latest cycle)
  2 Quasi-Cash    spend share in Table25 non-standard MCCs >= 25%, or
                  effective interchange <= 1.50%
  3 Bonus Chasers tenure <= 18 months, bonus paid (Table26), and spend down
                  >= 60% after the window or no purchases since the bonus
  4 Optimizers    paid in full >= 10 of 12 months, programme bonus-category
                  share of spend >= 50%, annual spend >= $12,000
  5 Low-Spend     annual spend < $6,000, tenure >= 36 months, active >= 9
  6 Unassigned    none of the above
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

REPORT = "Validation_Report_Reward_Calibration.csv"
SOURCE = ("estimated - source: Reward Profitability Scenario Model v2 "
          "(illustrative industry averages)")
BAND = 0.25
SEGMENTS = ["Optimizers / Transactors", "Quasi-Cash Users", "Sign-Up Bonus Chasers",
            "Low-Spend Loyalists", "Relationship Customers"]
# Model base, in SEGMENTS order (spec 3).
REFERENCE = {
    "Share of screened accounts": [0.26, 0.10, 0.19, 0.32, 0.13],
    "Annual spend USD": [24000, 30000, 6000, 4000, 15000],
    "Interchange rate": [0.022, 0.012, 0.021, 0.020, 0.021],
    "Reward earn rate": [0.026, 0.020, 0.018, 0.015, 0.025],
    "Revolving balance USD": [500, 800, 300, 400, 1000],
    "APR": [0.22, 0.21, 0.24, 0.24, 0.20],
}
UNASSIGNED_MAX = 0.10
REWARD_COST_SHARE_OVERALL = 0.79
# Redemption cost per $1 of face value: 1.0 for cash back / statement credit,
# 0.6-1.0 for travel, transfer and merchandise (spec 3).
REDEMPTION_REFERENCE = {
    "statement_credit": (1.0, 1.0), "cash_back": (1.0, 1.0),
    "travel_portal": (0.6, 1.0), "transfer_partner": (0.6, 1.0),
    "merchandise": (0.6, 1.0),
}


def _row(segment, metric, observed, ref_lo, ref_hi=None, accounts=None, note=""):
    ref_hi = ref_lo if ref_hi is None else ref_hi
    lo, hi = ref_lo * (1 - BAND), ref_hi * (1 + BAND)
    if observed is None or (isinstance(observed, float) and np.isnan(observed)):
        verdict = "not assessed"
    else:
        verdict = "within" if lo <= observed <= hi else "outside"
    return {"Segment": segment, "Metric": metric,
            "Observed": None if verdict == "not assessed" else round(float(observed), 6),
            "Reference": ref_lo if ref_lo == ref_hi else f"{ref_lo}-{ref_hi}",
            "Band Low": round(lo, 6), "Band High": round(hi, 6),
            "Within Band": verdict, "Accounts": None if accounts is None else int(accounts),
            "Reference Source": SOURCE, "Note": note}


def account_frame(data_dir: Path) -> tuple[pd.DataFrame, dict]:
    """One row per card account with everything the screen, the rules and
    the metrics need, over the trailing 12 cycles."""
    portfolio = load_portfolio(data_dir)
    led = LEDGER.build(portfolio)
    L = led["card"]
    cycles = sorted(L["Cycle Month"].unique())
    last12, last = cycles[-12:], cycles[-1]
    n_cyc = len(cycles)
    K = "Masked Account Number"

    t = L[L["Cycle Month"].isin(last12)].groupby(K).agg(
        cust=("Masked Customer Number", "first"), revenue=("revenue", "sum"),
        reward=("reward_expense", "sum"), nep=("net_economic_profit", "sum"))

    cyc = portfolio["Table4_Account_Cycle.csv"]
    c12 = cyc[cyc["Cycle Month"].isin(last12)]
    t["paid_in_full_months"] = c12.groupby(K)["Paid In Full Indicator"].sum()
    rb = np.where(c12["Purchase Interest"] > 0, c12["Purchase Balance"], 0.0)
    t["revolving_balance"] = pd.Series(rb, index=c12.index).groupby(c12[K]).mean()
    latest = cyc[cyc["Cycle Month"] == last].set_index(K)
    t["open_at_last"] = t.index.isin(latest.index)
    t["charged_off"] = latest["Charged Off Indicator"].reindex(t.index).fillna(True).astype(bool)
    t["apr"] = latest["Charged Purchase APR"].reindex(t.index) / 100.0

    tx = portfolio["Table5_Transaction.csv"]
    p12 = tx[tx["Cycle Month"].isin(last12) & ~tx["Cash Advance Indicator"].astype(bool)]
    acct = portfolio["Table2_Card_Account.csv"].set_index(K)
    rules = pd.read_csv(data_dir / "Table16_Reward_Program_Rules.csv").set_index("Program Code")
    nominal = acct["Reward Program Code"].map(rules["Nominal Point Value Cents"]) / 100.0
    bonus_cats = acct["Reward Program Code"].map(rules["Bonus Reward Categories"]).fillna("")
    t25 = pd.read_csv(data_dir / "Table25_MCC_Reference.csv")
    flagged = set(t25.loc[t25["Recommended Reward Treatment"] != "standard",
                          "Merchant Category Code (MCC)"])
    is_bonus_cat = [rc in str(bc).split("|") for rc, bc in
                    zip(p12["Reward Category"], bonus_cats.reindex(p12[K]).to_numpy())]
    g = pd.DataFrame({
        K: p12[K], "amt": p12["Transaction Amount"], "ie": p12["Interchange Earned"],
        "pts_value": p12["Points Earned"] * nominal.reindex(p12[K]).to_numpy(),
        "flagged_amt": np.where(p12["Merchant Category Code (MCC)"].isin(flagged), p12["Transaction Amount"], 0.0),
        "bonus_amt": np.where(is_bonus_cat, p12["Transaction Amount"], 0.0),
    }).groupby(K).sum()
    t = t.join(g, how="left").fillna({"amt": 0.0, "ie": 0.0, "pts_value": 0.0,
                                      "flagged_amt": 0.0, "bonus_amt": 0.0})
    t["active_months"] = p12.groupby(K)["Cycle Month"].nunique().reindex(t.index).fillna(0)

    t26 = pd.read_csv(data_dir / "Table26_Signup_Bonus.csv").set_index(K)
    t["open_ix"] = t26["Account Open Cycle Index"].reindex(t.index)
    t["tenure_months"] = n_cyc - t["open_ix"]  # pre-window accounts: > n_cyc
    t["bonus_paid"] = t26["Bonus Paid USD"].reindex(t.index).fillna(0.0)
    t["spend_change_after"] = t26["Spend Change After Window Pct"].reindex(t.index)
    earned = t26["Bonus Earned Cycle Month"].reindex(t.index)
    last_purchase = tx[~tx["Cash Advance Indicator"].astype(bool)].groupby(K)["Cycle Month"].max()
    t["inactive_since_bonus"] = earned.notna() & ~(last_purchase.reindex(t.index) > earned).fillna(False)

    dep_net = led["deposit_by_customer"]
    loan_net = led["loan_by_customer"]
    noncard = (dep_net[dep_net["Cycle Month"].isin(last12)].groupby("Masked Customer Number")["deposit_net"].sum()
               .add(loan_net[loan_net["Cycle Month"].isin(last12)].groupby("Masked Customer Number")["loan_net"].sum(),
                    fill_value=0.0))
    t["noncard_profit"] = noncard.reindex(t["cust"]).fillna(0.0).to_numpy()
    dep = portfolio.get("Table6b_Deposit_Account_Cycle.csv")
    dep_bal = (dep[dep["Cycle Month"] == last].groupby("Masked Customer Number")["Ending Balance"].sum()
               if dep is not None and len(dep) else pd.Series(dtype=float))
    t["deposit_balance"] = dep_bal.reindex(t["cust"]).fillna(0.0).to_numpy()

    red = portfolio["Table17_Reward_Redemption.csv"].copy()
    red["face_usd"] = red["Points Redeemed"] * nominal.reindex(red[K]).to_numpy()
    per_channel = red.groupby("Redemption Channel")[["Redemption Cost USD", "face_usd"]].sum()
    meta = {"cycles": n_cyc, "last": last, "accounts": int(len(t)),
            "redemption_cost_per_face_dollar": (per_channel["Redemption Cost USD"]
                                                / per_channel["face_usd"]).to_dict()}
    return t, meta


def segment(t: pd.DataFrame) -> pd.DataFrame:
    t = t.copy()
    t["screened"] = (t["open_at_last"] & ~t["charged_off"] & (t["tenure_months"] >= 6)
                     & (t["nep"] < 0) & (t["revenue"] > 0) & (t["reward"] >= 0.5 * t["revenue"]))
    eff_ic = t["ie"] / t["amt"].where(t["amt"] > 0)
    rules = [
        ("Relationship Customers", (t["noncard_profit"] >= 150) | (t["deposit_balance"] >= 25000)),
        ("Quasi-Cash Users", (t["flagged_amt"] / t["amt"].where(t["amt"] > 0) >= 0.25) | (eff_ic <= 0.015)),
        ("Sign-Up Bonus Chasers", (t["tenure_months"] <= 18) & (t["bonus_paid"] > 0)
         & ((t["spend_change_after"] <= -60) | t["inactive_since_bonus"])),
        ("Optimizers / Transactors", (t["paid_in_full_months"] >= 10)
         & (t["bonus_amt"] / t["amt"].where(t["amt"] > 0) >= 0.5) & (t["amt"] >= 12000)),
        ("Low-Spend Loyalists", (t["amt"] < 6000) & (t["tenure_months"] >= 36) & (t["active_months"] >= 9)),
    ]
    seg = pd.Series("Unassigned", index=t.index)
    assigned = pd.Series(False, index=t.index)
    for name, cond in rules:
        hit = cond.fillna(False) & ~assigned
        seg[hit] = name
        assigned |= hit
    t["segment"] = seg
    return t


def build_report(data_dir: Path) -> tuple[pd.DataFrame, dict]:
    t, meta = account_frame(data_dir)
    t = segment(t)
    s = t[t["screened"]]
    n = len(s)
    rows = []
    rows.append(_row("All screened", "Reward cost as % of revenue",
                     s["reward"].sum() / s["revenue"].sum() if n else np.nan,
                     REWARD_COST_SHARE_OVERALL, accounts=n,
                     note=f"{n:,} of {meta['accounts']:,} card accounts pass the screen"))
    for i, name in enumerate(SEGMENTS):
        g = s[s["segment"] == name]
        m = len(g)
        amt = g["amt"].sum()
        obs = {
            "Share of screened accounts": m / n if n else np.nan,
            "Annual spend USD": g["amt"].mean() if m else np.nan,
            "Interchange rate": g["ie"].sum() / amt if amt else np.nan,
            "Reward earn rate": g["pts_value"].sum() / amt if amt else np.nan,
            "Revolving balance USD": g["revolving_balance"].mean() if m else np.nan,
            "APR": g["apr"].mean() if m else np.nan,
        }
        for metric, ref in REFERENCE.items():
            rows.append(_row(name, metric, obs[metric], ref[i], accounts=m,
                             note="no screened accounts in this segment" if not m else ""))
    un = (s["segment"] == "Unassigned").sum()
    share = un / n if n else np.nan
    rows.append({**_row("Unassigned", "Share of screened accounts", share, UNASSIGNED_MAX, accounts=int(un)),
                 "Reference": f"< {UNASSIGNED_MAX}", "Band Low": 0.0, "Band High": UNASSIGNED_MAX,
                 "Within Band": "not assessed" if np.isnan(share) else ("within" if share < UNASSIGNED_MAX else "outside"),
                 "Note": "model guidance: keep below ~10% or refine thresholds"})
    for ch, cost in sorted(meta["redemption_cost_per_face_dollar"].items()):
        if ch in REDEMPTION_REFERENCE:
            lo, hi = REDEMPTION_REFERENCE[ch]
            rows.append(_row("All accounts", f"Redemption cost per $1 face value: {ch}", cost, lo, hi,
                             note="all redemptions in the data window"))
        else:
            rows.append({**_row("All accounts", f"Redemption cost per $1 face value: {ch}", cost, 1.0),
                         "Reference": "none in model", "Band Low": None, "Band High": None,
                         "Within Band": "not assessed", "Note": "channel not covered by the model's reference"})
    meta["screened"] = n
    meta["segment_counts"] = s["segment"].value_counts().to_dict()
    out = pd.DataFrame(rows)
    out["Accounts"] = out["Accounts"].astype("Int64")
    return out, meta


def main(data_dir: Path) -> dict:
    report, meta = build_report(data_dir)
    report.to_csv(data_dir / REPORT, index=False)
    summary = {"report": str(data_dir / REPORT), "screened_accounts": meta["screened"],
               "segment_counts": meta["segment_counts"],
               "within": int((report["Within Band"] == "within").sum()),
               "outside": int((report["Within Band"] == "outside").sum()),
               "not assessed": int((report["Within Band"] == "not assessed").sum())}
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    a = ap.parse_args()
    print(json.dumps(main(Path(a.data)), indent=2, default=str))
