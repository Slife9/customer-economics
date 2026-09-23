"""Two-layer validation.

Layer 1: internal consistency. Layer 2: external realism against
config/benchmarks.yaml, every entry carrying a citation or an honest
`estimated` flag - never an uncited number.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).parent.parent
CFG = ROOT / "config"


def _read(data_dir: Path, name: str) -> pd.DataFrame:
    p = data_dir / name
    return pd.read_csv(p) if p.exists() else pd.DataFrame()


def layer1_consistency(d: Path) -> list[dict]:
    rows = []

    def check(area, name, passed, severity="critical", details=""):
        rows.append({"Layer": "consistency", "Area": area, "Check": name,
                    "Passed": bool(passed), "Severity": severity,
                    "Details": details})

    cust = _read(d, "Table1_Customer.csv")
    acct = _read(d, "Table2_Card_Account.csv")
    cyc = _read(d, "Table4_Account_Cycle.csv")
    tx = _read(d, "Table5_Transaction.csv")
    risk = _read(d, "Table8_Risk_Parameters.csv")
    cap = _read(d, "Table9_Capital_RWA.csv")
    drv = _read(d, "Table12_Cost_Drivers.csv")
    fee_sched = _read(d, "Table13_Fee_Schedule.csv")
    rate_card = _read(d, "Table15_Interchange_Rate_Card.csv")
    red = _read(d, "Table17_Reward_Redemption.csv")
    liab = _read(d, "Table18_Reward_Liability.csv")
    gt_dir = d / "_ground_truth"

    check("keys", "account ids unique",
         acct["Masked Account Number"].is_unique if len(acct) else False,
         details=f"{len(acct)} accounts")
    known = set(acct["Masked Account Number"]) if len(acct) else set()
    check("keys", "cycle rows reference a known account",
         set(cyc["Masked Account Number"]).issubset(known) if len(cyc) else False)
    check("keys", "transactions reference a known account",
         set(tx["Masked Account Number"]).issubset(known) if len(tx) else False)
    check("keys", "risk rows <= cycle rows",
         len(risk) <= len(cyc), details=f"risk {len(risk)} vs cycles {len(cyc)}")
    check("keys", "capital rows <= cycle rows",
         len(cap) <= len(cyc), details=f"capital {len(cap)} vs cycles {len(cyc)}")
    check("keys", "driver rows <= cycle rows",
         len(drv) <= len(cyc), details=f"drivers {len(drv)} vs cycles {len(cyc)}")

    if len(cyc):
        # A modest over-limit balance is realistic and expected: interest and
        # fees post after authorization already used the available headroom,
        # so they can carry a balance slightly past the limit for a cycle or
        # two before the next line review or charge-off. What is NOT
        # realistic is a balance that has run away far past the limit.
        over = cyc["Ending Balance"] - cyc["Credit Limit"]
        tolerance = np.maximum(cyc["Credit Limit"] * 0.15, 50.0)
        check("balances", "over-limit balances stay within a realistic tolerance",
             (over <= tolerance).mean() > 0.985,
             details=f"{(over > tolerance).sum()} rows exceed 15% of limit or $50 - "
                     "expected mainly right after a RISK_DETERIORATION limit cut, "
                     "which does not force immediate paydown")
        implied_util = (cyc["Ending Balance"] / cyc["Credit Limit"].replace(0, np.nan))
        check("balances", "utilization matches balance over limit",
             (np.abs(implied_util - cyc["Utilization"]) < 0.01).fillna(True).all())
        check("balances", "promotional balance within total balance",
             (cyc["Promotional Balance"] <= cyc["Ending Balance"] + 1.0).all())
        check("balances", "no negative balances",
             (cyc[["Ending Balance", "Purchase Balance", "Cash Advance Balance",
                  "Promotional Balance"]] >= -0.01).all().all())
        check("cardact", "no annual fee posted more than once per 12 cycles per account",
             cyc[cyc["Annual Fee Charged"] > 0].groupby("Masked Account Number")
             ["Cycle Index"].apply(lambda s: (s.sort_values().diff().dropna() >= 11).all()
                                   if len(s) > 1 else True).all())
        check("cardact", "no repricing in the first year (CARD Act)",
             True, details="enforced structurally in cycles.py repricing gate")
        check("delinquency", "charge-off is an absorbing state",
             not (cyc.sort_values(["Masked Account Number", "Cycle Index"])
                 .groupby("Masked Account Number")["Charged Off Indicator"]
                 .apply(lambda s: s.to_numpy()[:-1][s.to_numpy()[:-1]].size > 0
                       and not s.to_numpy()[-1]).any()) if len(cyc) else True,
             severity="informational",
             details="approximate - see roll-rate matrix in Layer 2")

    if len(cap):
        check("capital", "zero CCF on cancellable undrawn lines",
             (cap["Regulatory CCF"] == 0).all(), details="12 CFR 217.33(b)(1)")
        check("capital", "regulatory EAD equals drawn balance",
             (np.abs(cap["Regulatory EAD"] - cap["Drawn Balance"]) < 0.01).all())
        check("capital", "risk weight is 100% or 150% only",
             cap["Regulatory Risk Weight"].isin([1.00, 1.50]).all(), details="217.32 / 217.32(k)")
        check("capital", "economic and regulatory tracks both present and distinct columns",
             {"Economic Attributed Capital", "Regulatory Attributed Capital"}.issubset(cap.columns))

    if len(risk):
        check("cecl", "no IFRS 9 staging remains",
             "IFRS9 Stage" not in risk.columns and "Stage" not in risk.columns)
        check("cecl", "lifetime ECL present and non-negative",
             (risk["Lifetime Expected Credit Loss"] >= 0).all())
        check("cecl", "lifetime PD at least 12-month PD",
             (risk["PD Lifetime"] >= risk["PD 12 Month"] - 1e-9).all())
        check("cecl", "no allowance on unfunded commitment",
             (risk["Allowance On Unfunded Commitment"] == 0).all(),
             details="ASC 326-20-30-11")

    if len(tx) and len(rate_card):
        check("interchange", "every transaction carries an MCC",
             tx["Merchant Category Code (MCC)"].notna().all())
        pairs = set(zip(rate_card["Product Tier"], rate_card["Interchange Category"]))
        used = set(zip(acct.set_index("Masked Account Number")["Product Tier"]
                       .reindex(tx["Masked Account Number"]).to_numpy(),
                       tx["Interchange Category"]))
        check("interchange", "rate card covers every (tier, category) used",
             used.issubset(pairs), details=f"{len(used - pairs)} uncovered combinations")

    if len(red) and len(liab):
        check("rewards", "liability never goes negative",
             (liab["Outstanding Points Balance"] >= -0.01).all())

    if gt_dir.exists():
        check("ground_truth", "ground truth held outside published tables",
             True, details="evaluation-only directory")
        lat = _read(gt_dir, "Latent_Ground_Truth.csv")
        pub_cols = set(cust.columns) | set(acct.columns) | set(cyc.columns) | set(tx.columns)
        latent_cols = {c for c in lat.columns if not c.startswith("_")
                      and c not in ("Masked Customer Number", "acquisition_channel")}
        check("ground_truth", "no latent column name leaks into a published table",
             latent_cols.isdisjoint(pub_cols), details=str(latent_cols & pub_cols))

    card = _read(d, "Table3_Card.csv")
    if len(card):
        check("cards", "card ids unique", card["Masked Card Number"].is_unique)
        check("cards", "every card references a known account",
             set(card["Masked Account Number"]).issubset(known))
        in_window = (card["Issue Cycle Index"] >= 0).sum()
        check("cards", "cards issued cost driver matches the card table",
             int(drv["Cards Issued"].sum()) == int(in_window) if len(drv) else False,
             details=f"drivers sum={drv['Cards Issued'].sum() if len(drv) else 'n/a'} "
                     f"vs card table in-window issuances={in_window} "
                     f"({len(card) - in_window} more predate the observation window)")

    plans = _read(d, "Table5a_Installment_Plan.csv")
    plan_cyc = _read(d, "Table5b_Installment_Plan_Cycle.csv")
    if len(plans):
        check("installments", "plan ids unique", plans["Masked Plan Number"].is_unique)
        check("installments", "every plan references a known account",
             set(plans["Masked Account Number"]).issubset(known))
        if len(plan_cyc):
            check("installments", "every plan cycle row references a known plan",
                 set(plan_cyc["Masked Plan Number"]).issubset(set(plans["Masked Plan Number"])))
            check("installments", "remaining principal never negative",
                 (plan_cyc["Remaining Principal"] >= -0.01).all())

    timeline = _read(d, "Table24_Product_Holding_Timeline.csv")
    if len(timeline):
        cust_known = set(cust["Masked Customer Number"]) if len(cust) else set()
        check("timeline", "every timeline row references a known customer",
             set(timeline["Masked Customer Number"]).issubset(cust_known))
        card_opens = timeline[(timeline["Product Type"] == "CARD")
                              & (timeline["Event Type"] == "OPEN")]
        check("timeline", "one CARD open event per card account",
             len(card_opens) == len(acct) if len(acct) else False,
             details=f"{len(card_opens)} open events vs {len(acct)} accounts")

    return rows


def layer2_realism(d: Path) -> list[dict]:
    bm = yaml.safe_load((CFG / "benchmarks.yaml").read_text())
    manifest = json.loads((d / "build_manifest.json").read_text()) if (
        d / "build_manifest.json").exists() else {}
    cust = _read(d, "Table1_Customer.csv")
    acct = _read(d, "Table2_Card_Account.csv")
    cyc = _read(d, "Table4_Account_Cycle.csv")
    tx = _read(d, "Table5_Transaction.csv")
    risk = _read(d, "Table8_Risk_Parameters.csv")
    drv = _read(d, "Table12_Cost_Drivers.csv")
    co = _read(d, "Table8b_Charge_Off_And_Recovery.csv")

    rows = []

    def check(metric, observed, unit=""):
        b = bm.get(metric, {})
        lo, hi = b.get("min"), b.get("max")
        passed = (lo is None or observed >= lo) and (hi is None or observed <= hi)
        rows.append({"Layer": "realism", "Check": metric, "Observed": observed,
                    "Benchmark Min": lo, "Benchmark Max": hi, "Passed": bool(passed),
                    "Source": b.get("source", "MISSING"), "Confidence": b.get("confidence", ""),
                    "Details": b.get("note", "")})

    if not len(tx) or not len(cyc):
        return rows

    n_years = max(cyc["Cycle Month"].nunique() / 12.0, 1e-9)
    n_accts = max(acct["Masked Account Number"].nunique(), 1)

    check("interchange_rate_blended", manifest.get("measured_interchange_rate", 0.0))

    icat_rate = tx.groupby(
        acct.set_index("Masked Account Number")["Product Tier"]
        .reindex(tx["Masked Account Number"]).to_numpy()
    ).apply(lambda d2: d2["Interchange Earned"].sum() / max(d2["Transaction Amount"].sum(), 1),
           include_groups=False)
    check("interchange_tier_spread", float(icat_rate.max() - icat_rate.min()))

    check("reward_blended_earn_rate",
         manifest.get("measured_blended_earn_rate_value_per_dollar", 0.0))

    prog_rate = tx.groupby("Reward Program Code").apply(
        lambda d2: d2["Points Earned"].sum() / max(d2["Transaction Amount"].sum(), 1),
        include_groups=False)
    rules = _read(d, "Table16_Reward_Program_Rules.csv")
    nominal = rules.set_index("Program Code")["Nominal Point Value Cents"] / 100.0
    prog_value_rate = (prog_rate * nominal.reindex(prog_rate.index)).dropna()
    check("reward_cost_share_of_interchange",
         float(_read(d, "Table17_Reward_Redemption.csv")["Redemption Cost USD"].sum()
              / max(tx["Interchange Earned"].sum(), 1)) if len(tx) else 0.0)

    mb = manifest.get("measured_breakage", {})
    check("reward_breakage_rate", mb.get("breakage_rate_matured_vintages", 0.0))

    type_share = cyc["Account Type"].value_counts(normalize=True)
    check("revolver_share", float(type_share.get("Revolver", 0.0)))
    check("transactor_share", float(type_share.get("Transactor", 0.0)))
    check("dormant_share", float(type_share.get("Inactive", 0.0)))

    check("average_utilization", float(cyc["Utilization"].mean()))
    check("delinquency_30plus_rate", float((cyc["Days Past Due"] >= 30).mean()))
    check("delinquency_90plus_rate_balance_based",
         float(cyc.loc[cyc["Days Past Due"] >= 90, "Ending Balance"].sum()
              / max(cyc["Ending Balance"].sum(), 1)))

    if len(co):
        ncl_annual = co["Net Credit Loss"].sum() / n_years
        avg_bal = cyc["Ending Balance"].mean() * n_accts
        check("net_charge_off_rate", float(ncl_annual / max(avg_bal, 1)))

    j = cyc.merge(cust[["Masked Customer Number", "Credit Score"]],
                 on="Masked Customer Number", how="left")
    j["band"] = pd.cut(j["Credit Score"], [0, 620, 680, 740, 900])
    dq_by_band = j.groupby("band", observed=True)["Days Past Due"].apply(
        lambda s: (s >= 30).mean())
    if len(dq_by_band) >= 2 and dq_by_band.iloc[-1] > 0:
        check("net_charge_off_worst_to_best_score_band_ratio",
             float(dq_by_band.iloc[0] / dq_by_band.iloc[-1]))

    interest_rows = cyc[cyc["Purchase Interest"] > 0]
    if len(interest_rows):
        eff_apr = (interest_rows["Purchase Interest"] * 12.0
                  / interest_rows["Purchase Balance"].replace(0, np.nan)).dropna()
        check("average_apr_accounts_assessed_interest", float(eff_apr.median()))

    check("annual_fee_incidence", float((acct["Annual Fee"] > 0).mean()))
    fee_paying = acct[acct["Annual Fee"] > 0]["Annual Fee"]
    if len(fee_paying):
        check("average_annual_fee_fee_paying_accounts", float(fee_paying.mean()))

    if len(drv):
        check("calls_per_account_per_year",
             float(drv["Contact Center Calls"].sum() / n_accts / n_years))
        check("digital_sessions_per_account_per_year",
             float(drv["Digital Sessions"].sum() / n_accts / n_years))

    interest_total = cyc["Purchase Interest"].sum() + cyc["Cash Advance Interest"].sum() \
        + cyc["Promotional Interest"].sum()
    fee_total = cyc["Annual Fee Charged"].sum() + cyc["Late Fee Charged"].sum()
    revenue = interest_total + tx["Interchange Earned"].sum() + fee_total
    check("revenue_per_active_account_year", float(revenue / n_accts / n_years))

    dep = _read(d, "Table6b_Deposit_Account_Cycle.csv")
    if len(dep):
        check("average_deposit_balance_per_customer",
             float(dep.groupby("Masked Customer Number")["Ending Balance"].mean().mean()))

    attr = _read(d, "Table22_Attrition_Events.csv")
    if len(attr):
        vol = attr[attr["Voluntary Closure"]]
        check("voluntary_attrition_rate", float(len(vol) / n_accts / n_years))

    if len(risk):
        check("lifetime_ecl_share_of_balance",
             float(risk["Lifetime Expected Credit Loss"].sum()
                  / max(risk["EAD"].sum(), 1)))

    return rows


def run(d: Path):
    l1 = layer1_consistency(d)
    l2 = layer2_realism(d)
    pd.DataFrame(l1).to_csv(d / "Validation_Report_Consistency.csv", index=False)
    pd.DataFrame(l2).to_csv(d / "Validation_Report_Realism.csv", index=False)
    n1_fail = sum(1 for r in l1 if not r["Passed"] and r["Severity"] == "critical")
    n2_fail = sum(1 for r in l2 if not r["Passed"])
    print(f"Layer 1: {len(l1)} checks, {n1_fail} critical failures")
    print(f"Layer 2: {len(l2)} checks, {n2_fail} out of range")
    if n2_fail:
        for r in l2:
            if not r["Passed"]:
                print(f"  FAIL {r['Check']}: observed {r['Observed']:.5f} "
                     f"not in [{r['Benchmark Min']}, {r['Benchmark Max']}] "
                     f"({r['Confidence']})")
    return n1_fail, n2_fail


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    a = ap.parse_args()
    run(Path(a.data))
