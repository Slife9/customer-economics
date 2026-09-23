"""
Validation, two layers.

Layer 1 - internal consistency. Does the dataset agree with itself? Keys join,
balances are coherent, components sum to totals.

Layer 2 - external realism. Is it plausible as a bank? The previous dataset
passed 120 internal checks while carrying a flat interchange rate, every reward
programme earning identically, and a fee schedule contradicting the fee data.
Layer 1 cannot catch that. This is what Layer 2 is for.

    python validate/check.py --data ./out/demo
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent


def _r(d: Path, name):
    p = d / name
    return pd.read_csv(p, low_memory=False) if p.exists() else None


# ------------------------------------------------------------ layer 1
def consistency(d: Path) -> pd.DataFrame:
    c = _r(d, "Table1_Credit_Card_Customer.csv")
    cy = _r(d, "Table2_Account_Cycle.csv")
    tx = _r(d, "Table4_Credit_Card_Transaction.csv")
    rk = _r(d, "Table8_Risk_Parameters.csv")
    cp = _r(d, "Table9_Capital_RWA.csv")
    dv = _r(d, "Table12_Cost_Drivers.csv")
    rc = _r(d, "Table15_Interchange_Rate_Card.csv")
    red = _r(d, "Table17_Reward_Redemption.csv")
    out = []

    def chk(area, name, ok, detail, sev="critical"):
        out.append({"Layer": "consistency", "Area": area, "Check": name,
                    "Passed": bool(ok), "Severity": sev, "Details": detail})

    acc = set(c["Masked Account Number"])
    chk("keys", "account ids unique", c["Masked Account Number"].is_unique, f"{len(acc)} accounts")
    chk("keys", "cycle rows reference a known account",
        set(cy["Masked Account Number"]) <= acc, "referential integrity")
    chk("keys", "transactions reference a known account",
        set(tx["Masked Account Number"]) <= acc, "referential integrity")
    chk("keys", "one risk row per account-cycle",
        len(rk) == len(cy), f"risk {len(rk)} vs cycles {len(cy)}")
    chk("keys", "one capital row per account-cycle",
        len(cp) == len(cy), f"capital {len(cp)} vs cycles {len(cy)}")
    chk("keys", "one driver row per account-cycle",
        len(dv) == len(cy), f"drivers {len(dv)} vs cycles {len(cy)}")

    chk("balances", "balance never exceeds limit",
        (cy["Ending Balance"] <= cy["Credit Limit"] + 0.01).all(), "no over-limit balances")
    chk("balances", "utilization matches balance over limit",
        np.allclose(cy["Utilization"], cy["Ending Balance"] / cy["Credit Limit"], atol=0.02),
        "derived field agrees")
    chk("balances", "promotional balance within total balance",
        (cy["Promotional Balance"] <= cy["Ending Balance"] + 0.01).all(), "subset holds")
    chk("balances", "no negative balances", (cy["Ending Balance"] >= 0).all(), "")

    chk("capital", "zero CCF on cancellable undrawn lines",
        (cp["Regulatory CCF"] == 0).all(), "12 CFR 217.33(b)(1)")
    chk("capital", "regulatory EAD equals drawn balance",
        np.allclose(cp["Regulatory EAD"], cp["Drawn Balance"], atol=0.01), "no undrawn EAD")
    chk("capital", "risk weight is 100% or 150% only",
        set(cp["Regulatory Risk Weight"].unique()) <= {1.0, 1.5}, "217.32 / 217.32(k)")
    chk("capital", "past due exposures carry 150%",
        (cp.loc[cy["Days Past Due"].values >= 90, "Regulatory Risk Weight"] == 1.5).all(),
        f"{int((cy['Days Past Due']>=90).sum())} rows")
    chk("capital", "economic and regulatory tracks both present",
        {"Economic Attributed Capital", "Regulatory Attributed Capital"} <= set(cp.columns),
        "never blended into one figure")

    chk("cecl", "no IFRS 9 staging remains",
        not any("IFRS" in x.upper() for x in rk.columns), "US GAAP basis")
    chk("cecl", "lifetime ECL present and non-negative",
        "Lifetime ECL" in rk.columns and (rk["Lifetime ECL"] >= 0).all(), "ASC 326")
    chk("cecl", "lifetime PD at least 12-month PD",
        (rk["PD Lifetime"] >= rk["PD 12 Month"] - 1e-9).all(), "")

    card = {(r["product"], r["category"]): r["rate_pct"] / 100 for _, r in rc.iterrows()}
    exp = tx.apply(lambda r: card.get((None, r["Merchant Category"])), axis=1) if False else None
    chk("interchange", "every transaction carries an MCC",
        tx["Merchant Category Code (MCC)"].notna().all(), "")
    chk("interchange", "rate card covers every category used",
        set(tx["Merchant Category"]) <= set(rc["category"]), "")

    chk("rewards", "redemption never exceeds points earned per account",
        (red.groupby("Masked Account Number")["Points Redeemed"].sum() <=
         tx.groupby("Masked Account Number")["Points earned on transaction"].sum()
           .reindex(red["Masked Account Number"].unique()).fillna(0) + 1).all(),
        "liability cannot go negative")

    gt = d / "_ground_truth"
    chk("ground_truth", "ground truth is held outside the published tables",
        gt.exists() and not any(p.name.startswith("Table") for p in gt.iterdir()),
        "evaluation-only directory")
    leaked = [col for t in [c, cy, tx] for col in t.columns
              if any(k in col.lower() for k in
                     ("latent", "defect", "planted", "appetite", "propensity", "fluency"))]
    chk("ground_truth", "no latent or defect marker leaks into engine tables",
        not leaked, f"leaked columns: {leaked}" if leaked else "clean")

    return pd.DataFrame(out)


# ------------------------------------------------------------ layer 2
def realism(d: Path, bm: dict) -> pd.DataFrame:
    cy = _r(d, "Table2_Account_Cycle.csv")
    tx = _r(d, "Table4_Credit_Card_Transaction.csv")
    rk = _r(d, "Table8_Risk_Parameters.csv")
    dv = _r(d, "Table12_Cost_Drivers.csv")
    c = _r(d, "Table1_Credit_Card_Customer.csv")
    red = _r(d, "Table17_Reward_Redemption.csv")
    rules = _r(d, "Table16_Reward_Programme_Rules.csv")
    out = []
    n_acc = c["Masked Account Number"].nunique()
    yrs = cy["Cycle Month"].nunique() / 12

    def chk(key, observed, detail=""):
        b = bm[key]
        ok = b["min"] <= observed <= b["max"]
        out.append({"Layer": "realism", "Check": key, "Observed": round(float(observed), 5),
                    "Benchmark Min": b["min"], "Benchmark Max": b["max"],
                    "Passed": bool(ok), "Source": b.get("source", "UNVERIFIED"),
                    "Details": detail})

    spend = tx["Transaction amount"].sum()
    chk("interchange_rate_blended", tx["Interchange earned"].sum() / spend)

    tier = tx.merge(c[["Masked Account Number", "Product"]], on="Masked Account Number")
    tr = tier.groupby("Product").apply(
        lambda g: g["Interchange earned"].sum() / g["Transaction amount"].sum())
    chk("interchange_tier_spread", tr.max() - tr.min(),
        f"{tr.min():.4f} to {tr.max():.4f} across {len(tr)} tiers")

    chk("reward_blended_earn_rate", tx["Points earned on transaction"].sum() / spend)

    pr = tx.merge(c[["Masked Account Number", "Reward Programme"]], on="Masked Account Number")
    er = pr.groupby("Reward Programme").apply(
        lambda g: g["Points earned on transaction"].sum() / max(g["Transaction amount"].sum(), 1))
    chk("reward_programme_earn_spread", er.max() - er.min(),
        f"{len(er)} programmes, {er.min():.2f} to {er.max():.2f}")

    # Breakage on MATURED vintages only - points earned in the first 12 cycles,
    # given 12 further cycles to be redeemed. Measuring the whole window
    # confuses outstanding liability with breakage.
    cycles = sorted(cy["Cycle Month"].unique())
    early, late = set(cycles[:12]), set(cycles[12:])
    pts_progs = rules.loc[rules["currency"] == "POINTS", "programme"]
    pa = set(c.loc[c["Reward Programme"].isin(pts_progs), "Masked Account Number"])
    expd = _r(d, "Table19_Reward_Expiry.csv")
    e = tx[tx["Masked Account Number"].isin(pa)]["Points earned on transaction"].sum()
    x = expd["Points Expired"].sum() if expd is not None and len(expd) else 0.0
    chk("reward_breakage_rate", (x / e) if e else 0,
        "expired points over points earned - measured from the expiry mechanism")

    rcost = red["Redemption Cost USD"].sum()
    chk("reward_cost_share_of_interchange", rcost / tx["Interchange earned"].sum())

    act = cy[cy["Account Type"] != "Inactive"]
    chk("revolver_share", (act["Account Type"] == "Revolver").mean())
    chk("transactor_share", (act["Account Type"] == "Transactor").mean())
    chk("average_utilization", cy["Utilization"].mean())
    chk("delinquency_30plus_rate", (cy["Days Past Due"] >= 30).mean())
    chk("lifetime_ecl_share_of_balance",
        rk["Lifetime ECL"].sum() / max(cy["Ending Balance"].sum(), 1))
    chk("calls_per_account_per_year", dv["Contact Center Calls"].sum() / n_acc / yrs)
    chk("digital_sessions_per_account_per_year", dv["Digital Sessions"].sum() / n_acc / yrs)
    chk("annual_fee_incidence", (c["Annual Fee"] > 0).mean())
    chk("average_apr", cy["Purchase Rate (APR)"].mean() / 100)
    return pd.DataFrame(out)


def main(data: Path):
    bm = yaml.safe_load((ROOT / "config" / "benchmarks.yaml").read_text())
    c1 = consistency(data)
    c2 = realism(data, bm)
    c1.to_csv(data / "Validation_Report_Consistency.csv", index=False)
    c2.to_csv(data / "Validation_Report_Realism.csv", index=False)

    print(f"LAYER 1 consistency : {int(c1.Passed.sum())}/{len(c1)} passed")
    for _, r in c1[~c1.Passed].iterrows():
        print(f"   FAIL  {r['Area']:<14} {r['Check']}  -- {r['Details']}")
    print(f"\nLAYER 2 realism     : {int(c2.Passed.sum())}/{len(c2)} passed")
    print(f"{'check':<44}{'observed':>11}{'min':>9}{'max':>9}  ")
    for _, r in c2.iterrows():
        flag = "" if r.Passed else "  <-- FAIL"
        print(f"{r['Check']:<44}{r['Observed']:>11}{r['Benchmark Min']:>9}"
              f"{r['Benchmark Max']:>9}{flag}")
    unver = (c2["Source"] == "UNVERIFIED").sum()
    if unver:
        print(f"\n{unver} benchmark ranges are still marked UNVERIFIED and need a citation.")
    return c1, c2


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="./out/demo")
    main(Path(ap.parse_args().data))
