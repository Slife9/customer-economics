"""
Circularity test.

Two questions this answers:

1. Does the negative control come back clean? A portfolio generated with no
   planted defects, tighter limits and sensible pricing should produce far
   less "opportunity" than the demo book. If it does not, the detection logic
   is manufacturing findings rather than detecting them.

2. Do portfolios that SHOULD differ actually differ? A transactor-heavy book
   and a subprime book must produce materially different aggregates. A metric
   that is stable across all of them is an artifact of code, not a property
   of the data.

    python validate/circularity.py --root ./out
"""
from __future__ import annotations
import argparse
from pathlib import Path
import pandas as pd
import numpy as np

UC = {"Contact Center Calls": 5.83, "Digital Sessions": 0.025, "Branch Visits": 1.71,
      "Payments Processed": 0.093, "Collections Contacts": 78.45, "Fraud Alerts": 12.30,
      "Disputes Raised": 4.26, "Complaints Handled": 16.57, "Cards Issued": 1.17,
      "Statements Produced": 0.63}


def profile_metrics(d: Path) -> dict:
    c = pd.read_csv(d / "Table1_Credit_Card_Customer.csv")
    cy = pd.read_csv(d / "Table2_Account_Cycle.csv", low_memory=False)
    tx = pd.read_csv(d / "Table4_Credit_Card_Transaction.csv", low_memory=False)
    rk = pd.read_csv(d / "Table8_Risk_Parameters.csv")
    cp = pd.read_csv(d / "Table9_Capital_RWA.csv")
    dv = pd.read_csv(d / "Table12_Cost_Drivers.csv")
    red = pd.read_csv(d / "Table17_Reward_Redemption.csv")
    gt = pd.read_csv(d / "_ground_truth" / "Defect_Ground_Truth.csv")

    n = c["Masked Account Number"].nunique()
    svc = sum(dv[k].sum() * v for k, v in UC.items() if k in dv.columns)
    rev = (cy["Purchase Interest"].sum() + cy["Promotional Interest"].sum()
           + cy["Late Fee Amount"].sum() + tx["Interchange earned"].sum()
           + c["Annual Fee"].sum() * (cy["Cycle Month"].nunique() / 12))
    rewards = red["Redemption Cost USD"].sum()
    el = rk["Expected Loss Monthly"].sum()
    cap = cp["Regulatory Capital Charge Monthly"].sum()
    fund = (cy["Average Daily Balance"] * 0.0505 / 12).sum()
    net = rev - rewards - el - svc - cap - fund

    # Opportunity proxies an engine would report. None of these were set.
    underused = cy.groupby("Masked Account Number").agg(
        u=("Utilization", "mean"), l=("Credit Limit", "last"))
    n_underused = int(((underused.u < 0.05) & (underused.l > 5000)).sum())

    per = (cy.groupby("Masked Account Number")["Purchase Interest"].sum()
           + cy.groupby("Masked Account Number")["Late Fee Amount"].sum()
           + tx.groupby("Masked Account Number")["Interchange earned"].sum().reindex(
               cy["Masked Account Number"].unique()).fillna(0))
    per_cost = (dv.groupby("Masked Account Number").apply(
        lambda g: sum(g[k].sum() * v for k, v in UC.items() if k in g.columns))
        + rk.groupby("Masked Account Number")["Expected Loss Monthly"].sum())
    joined = pd.concat([per.rename("r"), per_cost.rename("c")], axis=1).fillna(0)
    n_below_cost = int((joined.r < joined.c).sum())

    return {
        "accounts": n,
        "planted defects": len(gt),
        "net economic profit": net,
        "per account": net / n,
        "% below cost": n_below_cost / n,
        "underused limits": n_underused / n,
        "avg utilization": cy["Utilization"].mean(),
        "revolver share": (cy["Account Type"] == "Revolver").mean(),
        "rewards / revenue": rewards / rev,
        "ECL / balance": rk["Lifetime ECL"].sum() / max(cy["Ending Balance"].sum(), 1),
        "servicing / account / yr": svc / n / (cy["Cycle Month"].nunique() / 12),
    }


def main(root: Path):
    profiles = [p for p in ["demo", "negative_control", "transactor_heavy",
                            "subprime_heavy", "premium_heavy"] if (root / p).exists()]
    M = {p: profile_metrics(root / p) for p in profiles}
    df = pd.DataFrame(M)

    PCT = {"% below cost", "underused limits", "avg utilization", "revolver share",
           "rewards / revenue", "ECL / balance"}
    MON = {"net economic profit", "per account", "servicing / account / yr"}
    rows = {}
    for i in df.index:
        if i in PCT:
            rows[i] = df.loc[i].map(lambda v: f"{v:.1%}")
        elif i in MON:
            rows[i] = df.loc[i].map(lambda v: f"${v:,.0f}")
        else:
            rows[i] = df.loc[i].map(lambda v: f"{int(v):,}")
    print(pd.DataFrame(rows).T.to_string())

    out, verdicts = [], []
    if "negative_control" in M and "demo" in M:
        a, b = M["demo"], M["negative_control"]
        verdicts += [
            # Defect-attributable findings MUST vanish - nothing was planted.
            ("negative control carries no planted defects",
             b["planted defects"] == 0, f"{int(b['planted defects'])} defects"),
            # Policy-driven findings must fall sharply.
            ("negative control has materially fewer underused limits",
             b["underused limits"] < a["underused limits"] * 0.75,
             f"{b['underused limits']:.1%} vs {a['underused limits']:.1%}"),
            ("negative control is more profitable per account",
             b["per account"] > a["per account"],
             f"${b['per account']:.0f} vs ${a['per account']:.0f}"),
            # Structural losses must NOT vanish. A clean book still carries
            # customers who are unprofitable because they are cheap to have
            # and expensive to serve. If this went near zero the generator
            # would be flattering the product.
            ("below-cost floor survives on a clean book",
             0.05 < b["% below cost"] < a["% below cost"],
             f"{b['% below cost']:.1%} clean vs {a['% below cost']:.1%} demo "
             f"- the floor no lever can remove"),
        ]
    if {"transactor_heavy", "subprime_heavy"} <= set(M):
        t, s = M["transactor_heavy"], M["subprime_heavy"]
        verdicts += [
            ("transactor book revolves less than subprime book",
             t["revolver share"] < s["revolver share"] - 0.05,
             f"{t['revolver share']:.1%} vs {s['revolver share']:.1%}"),
            ("subprime book carries higher expected loss",
             s["ECL / balance"] > t["ECL / balance"] * 1.2,
             f"{s['ECL / balance']:.2%} vs {t['ECL / balance']:.2%}"),
        ]
    print("\nCIRCULARITY VERDICTS")
    for name, ok, detail in verdicts:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}  ({detail})")
    df.to_csv(root / "Circularity_Report.csv")
    return df


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="./out")
    main(Path(ap.parse_args().root))
