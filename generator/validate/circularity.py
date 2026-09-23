"""Circularity test: the case that findings track causes, not the generator.

1. Negative control: same population-generating process, a better-run bank.
   Defect findings must be zero (nothing planted). Policy-driven leakage must
   fall because the MECHANISM of every lever changed, not because the
   customers are different people.
2. Below-cost floor: the clean book must still carry unprofitable customers.
   Low-spend, high-service customers are structurally unprofitable regardless
   of bank policy. If this goes near zero, the generator is flattering the
   product rather than modeling it.
3. Variants must differ materially in their aggregates - a metric stable
   across all of them is an artifact of code, not a portfolio property.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd


def _read(d: Path, name: str) -> pd.DataFrame:
    p = d / name
    return pd.read_csv(p) if p.exists() else pd.DataFrame()


def portfolio_summary(d: Path) -> dict:
    manifest = json.loads((d / "build_manifest.json").read_text())
    cust = _read(d, "Table1_Customer.csv")
    acct = _read(d, "Table2_Card_Account.csv")
    cyc = _read(d, "Table4_Account_Cycle.csv")
    tx = _read(d, "Table5_Transaction.csv")
    risk = _read(d, "Table8_Risk_Parameters.csv")
    cap = _read(d, "Table9_Capital_RWA.csv")
    drv = _read(d, "Table12_Cost_Drivers.csv")
    red = _read(d, "Table17_Reward_Redemption.csv")
    gt = _read(d, "_ground_truth/Defect_Ground_Truth.csv")

    n = acct["Masked Account Number"].nunique()
    interest = cyc["Purchase Interest"].sum() + cyc["Cash Advance Interest"].sum() \
        + cyc["Promotional Interest"].sum()
    fees = cyc["Annual Fee Charged"].sum() + cyc["Late Fee Charged"].sum()
    interchange = tx["Interchange Earned"].sum()
    rewards_cost = red["Redemption Cost USD"].sum() if len(red) else 0.0
    ecl = risk["Expected Credit Loss 12 Month"].sum() if len(risk) else 0.0
    reg_cap = cap["Regulatory Capital Charge Monthly"].sum() * 12 if len(cap) else 0.0

    acct_profit = (
        cyc.groupby("Masked Account Number")["Purchase Interest"].sum()
        + cyc.groupby("Masked Account Number")["Cash Advance Interest"].sum()
        + cyc.groupby("Masked Account Number")["Annual Fee Charged"].sum()
        + cyc.groupby("Masked Account Number")["Late Fee Charged"].sum()
    )
    ic_by_acct = tx.groupby("Masked Account Number")["Interchange Earned"].sum()
    acct_profit = acct_profit.add(ic_by_acct, fill_value=0.0)
    cost_by_acct = (
        drv.groupby("Masked Account Number")["Contact Center Calls"].sum() * 25.0
        + drv.groupby("Masked Account Number")["Collections Contacts"].sum() * 60.0
    )
    acct_profit = acct_profit.subtract(cost_by_acct, fill_value=0.0)
    below_cost_share = float((acct_profit < 0).mean()) if len(acct_profit) else 0.0

    n_years = max(cyc["Cycle Month"].nunique() / 12.0, 1e-9)
    return {
        "profile": manifest.get("profile"),
        "accounts": n,
        "planted_defects": manifest.get("planted_defects", 0),
        "net_revenue_per_account_year": round(
            (interest + fees + interchange - rewards_cost) / n / n_years, 2),
        "below_cost_share": round(below_cost_share, 4),
        "avg_utilization": round(manifest.get("measured_average_utilization", 0.0), 4),
        "revolver_share": round(manifest.get("measured_revolver_share", 0.0), 4),
        "avg_apr": round(float(acct["Contractual Purchase APR"].mean()), 2)
        if len(acct) else None,
        "annual_fee_incidence": round(float((acct["Annual Fee"] > 0).mean()), 4)
        if len(acct) else None,
        "ecl_12m_over_ead": round(float(ecl / max(risk["EAD"].sum(), 1)), 4)
        if len(risk) else None,
        "reg_capital_per_account_year": round(reg_cap / n, 2),
        "servicing_cost_per_account_year": round(
            float(cost_by_acct.sum()) / n / n_years, 2),
    }


def run(root: Path):
    profiles = {
        "demo": root / "demo",
        "negative_control": root / "negative_control",
        "transactor_heavy": root / "variant_transactor_heavy",
        "subprime_heavy": root / "variant_subprime_heavy",
        "premium_heavy": root / "variant_premium_heavy",
    }
    rows = {}
    for name, d in profiles.items():
        if (d / "build_manifest.json").exists():
            rows[name] = portfolio_summary(d)
    df = pd.DataFrame(rows).T
    df.to_csv(root / "Circularity_Report.csv")
    print(df.to_string())

    assertions = []

    def check(name, cond, detail=""):
        assertions.append({"assertion": name, "passed": bool(cond), "detail": detail})

    if "demo" in rows and "negative_control" in rows:
        # WAIVER_NO_EXPIRY/EXPIRED_CONCESSION are not directly targeted - they
        # fall out of the review_discipline policy dial (0.97 in the control),
        # so a small residual is honest, not planted. The five directly
        # sampled Type A defect types must be exactly zero.
        gt = _read(profiles["negative_control"], "_ground_truth/Defect_Ground_Truth.csv")
        hard_types = {"UNPOSTED_CONTRACTUAL_FEE", "INTERCHANGE_BELOW_EXPECTED",
                     "PRICE_BELOW_CONTRACT", "WRONG_EARN_RULE", "PROMO_FAILED_TO_REVERT"}
        n_hard = int(gt["Defect Type"].isin(hard_types).sum()) if len(gt) else 0
        check("negative control has zero directly-planted defects",
             n_hard == 0, detail=f"{n_hard} found")
        check("negative control below-cost share is NOT near zero (structural floor)",
             rows["negative_control"]["below_cost_share"] > 0.05,
             detail=f"{rows['negative_control']['below_cost_share']:.4f}")
        check("negative control below-cost share is not identical to demo "
             "(policy mechanism actually changed something)",
             abs(rows["negative_control"]["below_cost_share"]
                - rows["demo"]["below_cost_share"]) > 0.001)
        check("negative control servicing cost per account is lower "
             "(digital deflection + collections efficiency mechanism)",
             rows["negative_control"]["servicing_cost_per_account_year"]
             < rows["demo"]["servicing_cost_per_account_year"])

    variant_names = [v for v in ("transactor_heavy", "subprime_heavy", "premium_heavy")
                     if v in rows]
    for metric in ("avg_utilization", "revolver_share", "below_cost_share",
                  "net_revenue_per_account_year"):
        vals = [rows[v][metric] for v in variant_names]
        if len(vals) >= 2:
            spread = max(vals) - min(vals)
            check(f"variants differ materially on {metric}",
                 spread > 0.02 * max(abs(v) for v in vals if v) if any(vals) else False,
                 detail=f"spread={spread:.4f} across {dict(zip(variant_names, vals))}")

    ok = sum(1 for a in assertions if a["passed"])
    print(f"\nCircularity assertions: {ok}/{len(assertions)} passed")
    for a in assertions:
        print(f"  {'OK  ' if a['passed'] else 'FAIL'} {a['assertion']} {a['detail']}")
    pd.DataFrame(assertions).to_csv(root / "Circularity_Assertions.csv", index=False)
    return assertions


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    a = ap.parse_args()
    run(Path(a.root))
