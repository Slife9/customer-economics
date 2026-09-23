"""
ProfitInsight synthesis engine v2.

    python run.py --profile demo              --out ./out/demo
    python run.py --profile negative_control  --out ./out/negative_control
    python run.py --profile transactor_heavy  --out ./out/variant_transactor_heavy
    python run.py --profile subprime_heavy    --out ./out/variant_subprime_heavy
    python run.py --profile premium_heavy     --out ./out/variant_premium_heavy

Generate causes, never effects. No parameter here is named after anything the
analytical engine reports.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from generator.synth import (latents as L, population as POP, policy as P,
                             transactions as TX, cycles as CY, rewards as RW,
                             risk as RISK, capital as CAP, cost as COST,
                             deposits as DEP, loans as LOAN, ftp as FTP,
                             fees as FEES, defects as DEF, cards as CARDS,
                             installments as INST, timeline as TL)

ROOT = Path(__file__).parent
CFG = ROOT / "config"

# Negative control mechanism dials - every lever's mechanism is varied here,
# not just limit generosity. See PROFILES below.
CONTROL_MECHANISM = {
    "limit_generosity": 0.78,
    "line_review_uses_observed_behavior": True,
    "fee_aligned_to_reward": True,
    "digital_deflection_rate": 0.66,
    "waiver_rate": 0.05,
    "review_discipline": 0.97,
    "repricing_tracks_risk": True,
    "promo_share": 0.07,
    "defect_prevalence": {},
}

DEMO_DEFECT_PREVALENCE = {
    "UNPOSTED_CONTRACTUAL_FEE": 0.030,
    "EXPIRED_CONCESSION": 0.12,
    "PROMO_FAILED_TO_REVERT": 0.055,
    "INTERCHANGE_BELOW_EXPECTED": 0.028,
    "PRICE_BELOW_CONTRACT": 0.022,
    "WRONG_EARN_RULE": 0.032,
}

PROFILES = {
    "demo": {
        "n": 5000, "limit_generosity": 1.0, "promo_share": 0.18,
        "digital_deflection_rate": 0.40, "waiver_rate": 0.14,
        "review_discipline": 0.90, "fee_aligned_to_reward": False,
        "line_review_uses_observed_behavior": False,
        "repricing_tracks_risk": False,
        "defect_prevalence": DEMO_DEFECT_PREVALENCE,
    },
    "negative_control": {
        "n": 5000, **CONTROL_MECHANISM,
    },
    "transactor_heavy": {
        "n": 2000, "limit_generosity": 1.0, "promo_share": 0.10,
        "digital_deflection_rate": 0.40, "waiver_rate": 0.14,
        "review_discipline": 0.90, "fee_aligned_to_reward": False,
        "line_review_uses_observed_behavior": False,
        "repricing_tracks_risk": False,
        "defect_prevalence": DEMO_DEFECT_PREVALENCE,
        "latent_tilt": {"reliability": 0.85, "credit_appetite": -0.55},
    },
    "subprime_heavy": {
        "n": 2000, "limit_generosity": 0.85, "promo_share": 0.24,
        "digital_deflection_rate": 0.34, "waiver_rate": 0.16,
        "review_discipline": 0.90, "fee_aligned_to_reward": False,
        "line_review_uses_observed_behavior": False,
        "repricing_tracks_risk": False,
        "defect_prevalence": DEMO_DEFECT_PREVALENCE,
        "score_shift_z": -0.85, "latent_tilt": {"reliability": -0.70},
    },
    "premium_heavy": {
        "n": 2000, "limit_generosity": 1.25, "promo_share": 0.14,
        "digital_deflection_rate": 0.46, "waiver_rate": 0.20,
        "review_discipline": 0.90, "fee_aligned_to_reward": False,
        "line_review_uses_observed_behavior": False,
        "repricing_tracks_risk": False,
        "defect_prevalence": DEMO_DEFECT_PREVALENCE,
        "score_shift_z": 0.55,
        "latent_tilt": {"affluence": 0.95},
        "channel_mix": [0.30, 0.28, 0.06, 0.24, 0.12],
    },
}


def cycle_list(start="2023-01", n=36):
    y, m = map(int, start.split("-"))
    out = []
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


def build(profile_name: str, out: Path, seed: int, n_cycles: int, n_override: int | None,
          overrides: dict | None = None):
    prof = dict(PROFILES[profile_name])
    prof["name"] = profile_name
    if n_override:
        prof["n"] = n_override
    if overrides:
        prof.update(overrides)
    rng = np.random.default_rng(seed)
    cycles = cycle_list(n=n_cycles)
    n, n_cyc = prof["n"], len(cycles)
    out.mkdir(parents=True, exist_ok=True)

    geo = pd.read_csv(CFG / "geography.csv", dtype={"ZIP3": str})
    age0 = np.clip(rng.gamma(5.2, 5.4, n) + 19, 19, 92).round().astype(int)
    lat = L.draw_latents(n, age0, rng, prof)
    cust = POP.build_customers(n, lat, geo, cycles, rng, prof)
    accounts = POP.build_card_accounts(cust, lat, cycles, rng, prof)
    open_idx = accounts["Account Open Cycle Index"].to_numpy()

    mcc, rate_card = TX.load_config(CFG)
    tx = TX.generate(accounts, lat, cycles, open_idx, np.full(n, n_cyc), mcc, rate_card, rng)

    sim = CY.simulate(accounts, cust, lat, tx, cycles, rng, prof)
    cyc = sim["cycles"]
    closed_at = sim["closed_at"]

    # Transactions only exist while the account is open; re-clip against the
    # realized closure/charge-off cycle now that it is known.
    tx = tx[tx["_cycle_ix"] < tx["Masked Account Number"].map(
        pd.Series(closed_at, index=accounts["Masked Account Number"])).to_numpy()].copy()

    # ---------------- card (plastic-level events) --------------------------
    card_events = CARDS.generate(accounts, lat, cycles, closed_at, rng)
    cards_issued_lookup = CARDS.cards_issued_per_account_cycle(card_events, accounts, n_cyc)

    # ---------------- fee events, waivers -------------------------------
    fee_events = sim["fee_events"]
    waivers = FEES.grant_waivers(fee_events, accounts, cycles, rng,
                                 prof.get("waiver_rate", 0.14),
                                 prof.get("review_discipline", 0.48))

    # ---------------- defects (Type A), planted before rewards.earn ------
    tables = {"accounts": accounts, "cyc": cyc, "tx": tx,
             "fee_events": fee_events, "waivers": waivers}
    gt_main, wrong_earn_accts = DEF.plant(tables, cycles, rng,
                                          prof.get("defect_prevalence", {}))
    fee_events = tables["fee_events"]
    waivers = tables["waivers"]

    # ---------------- rewards ---------------------------------------------
    rules, channels = RW.load_config(CFG)
    tx_before = tx.copy()
    tx = RW.earn(tx, accounts, rules, wrong_earn_accts)
    gt_earn = DEF.wrong_earn_ground_truth(
        RW.earn(tx_before, accounts, rules, set()), tx, wrong_earn_accts)
    red, exp, liab = RW.redeem_and_expire(tx, accounts, lat, rules, channels,
                                          cycles, closed_at, rng)
    breakage = RW.measure_breakage(tx, exp, cycles, rules)

    ground_truth = pd.concat([gt_main, gt_earn], ignore_index=True) if len(gt_main) or len(gt_earn) \
        else pd.DataFrame(columns=["Masked Account Number", "Defect Type",
                                   "Description", "Cycles Affected",
                                   "Estimated Total Impact"])

    # ---------------- risk, capital, cost -----------------------------------
    risk = RISK.estimate(cyc, cust, rng, prof)
    net_loss = RISK.charge_off_and_recovery(cyc, cycles, rng)
    cap = CAP.compute(cyc, sim["limit_events"], {})
    drv = COST.drivers(cyc, lat, accounts, rng, prof, cards_issued_lookup)
    pools = COST.load_pools(CFG)
    monthly_cost = COST.allocate_monthly_cost(drv, pools, n)

    # ---------------- deposits, loans, FTP -----------------------------------
    ftp_curve = FTP.build_curve(cycles, rng)
    dep_accts = DEP.build_accounts(cust, lat, n_cyc, rng, prof)
    dep_cyc = DEP.simulate_cycles(dep_accts, lat, cycles, ftp_curve,
                                  cust["Stated Annual Income"].to_numpy(), rng) \
        if len(dep_accts) else pd.DataFrame()
    loan_accts, loan_cyc = LOAN.build_and_simulate(cust, lat, cycles, rng, prof)

    fee_recon = FEES.reconcile_entitled_vs_charged(fee_events, accounts, cyc,
                                                   pd.read_csv(CFG / "fee_schedule.csv"),
                                                   waivers)

    # ---------------- installment plans -------------------------------------
    plans, plan_cyc = INST.generate(tx, accounts, lat, cycles, closed_at, rng)

    # ---------------- product holding timeline --------------------------------
    timeline = TL.build(cust, accounts, closed_at, sim["charged_off_at"],
                        sim["attrition_events"], dep_accts, loan_accts, loan_cyc,
                        plans, cycles)

    # ---------------- emit published tables ---------------------------------
    cust.to_csv(out / "Table1_Customer.csv", index=False)
    accounts.drop(columns=["Account Open Cycle Index"]).to_csv(
        out / "Table2_Card_Account.csv", index=False)
    accounts[["Masked Account Number", "Account Open Cycle Index"]].assign(
        **{"Account Open Cycle Month": accounts["Account Open Cycle Index"].map(
            lambda i: cycles[i] if 0 <= i < n_cyc else cycles[0])}
    ).to_csv(out / "Table2b_Account_Open_Reference.csv", index=False)

    card_events.to_csv(out / "Table3_Card.csv", index=False)

    cyc.drop(columns=[c for c in ["_acct_ix"] if c in cyc.columns]).to_csv(
        out / "Table4_Account_Cycle.csv", index=False)
    tx.drop(columns=["_acct_ix", "_cycle_ix"]).to_csv(
        out / "Table5_Transaction.csv", index=False)
    plans.to_csv(out / "Table5a_Installment_Plan.csv", index=False)
    plan_cyc.to_csv(out / "Table5b_Installment_Plan_Cycle.csv", index=False)

    if len(dep_accts):
        dep_accts.drop(columns=["_latent_ix"]).to_csv(
            out / "Table6_Deposit_Account.csv", index=False)
        dep_cyc.to_csv(out / "Table6b_Deposit_Account_Cycle.csv", index=False)
    if len(loan_accts):
        loan_accts.to_csv(out / "Table7_Loan_Account.csv", index=False)
        loan_cyc.to_csv(out / "Table7b_Loan_Account_Cycle.csv", index=False)

    risk.to_csv(out / "Table8_Risk_Parameters.csv", index=False)
    net_loss.to_csv(out / "Table8b_Charge_Off_And_Recovery.csv", index=False)
    cap.to_csv(out / "Table9_Capital_RWA.csv", index=False)
    ftp_curve.to_csv(out / "Table10_FTP_Curve.csv", index=False)
    pools.to_csv(out / "Table11_Cost_Pools.csv", index=False)
    drv.to_csv(out / "Table12_Cost_Drivers.csv", index=False)
    pd.DataFrame([{"Activity": k, "Portfolio Monthly Cost USD": v}
                 for k, v in monthly_cost.items()]).to_csv(
        out / "Table12b_Cost_Pool_Monthly_Totals.csv", index=False)

    pd.read_csv(CFG / "fee_schedule.csv").to_csv(out / "Table13_Fee_Schedule.csv", index=False)
    fee_events.to_csv(out / "Table13b_Fee_Events.csv", index=False)
    fee_recon.to_csv(out / "Table13c_Fee_Entitled_Vs_Charged.csv", index=False)
    waivers.to_csv(out / "Table14_Waivers_And_Exceptions.csv", index=False)

    pd.read_csv(CFG / "interchange_rate_card.csv").to_csv(
        out / "Table15_Interchange_Rate_Card.csv", index=False)
    pd.read_csv(CFG / "reward_program_rules.csv").to_csv(
        out / "Table16_Reward_Program_Rules.csv", index=False)
    red.to_csv(out / "Table17_Reward_Redemption.csv", index=False)
    liab.to_csv(out / "Table18_Reward_Liability.csv", index=False)
    exp.to_csv(out / "Table19_Reward_Expiry.csv", index=False)

    RATE_EVENT_COLS = ["Masked Account Number", "Cycle Month", "Old Purchase APR",
                      "New Purchase APR", "Reason Code", "Notice Sent Cycle Index",
                      "Applies To New Transactions Only"]
    limit_events_out = sim["limit_events"] if len(sim["limit_events"]) else pd.DataFrame(
        columns=["Masked Account Number", "Cycle Month", "Old Credit Limit",
                "New Credit Limit", "Change Direction", "Reason Code",
                "Customer Requested", "Adverse Action Notice Sent"])
    rate_events_out = sim["rate_events"] if len(sim["rate_events"]) else pd.DataFrame(
        columns=RATE_EVENT_COLS)
    attrition_events_out = sim["attrition_events"] if len(sim["attrition_events"]) else \
        pd.DataFrame(columns=["Masked Account Number", "Closure Cycle Month",
                              "Closure Reason", "Voluntary Closure", "Balance At Closure"])
    limit_events_out.to_csv(out / "Table20_Limit_Change_Events.csv", index=False)
    rate_events_out.to_csv(out / "Table21_Rate_Change_Events.csv", index=False)
    attrition_events_out.to_csv(out / "Table22_Attrition_Events.csv", index=False)
    acq_cost = P.acquisition_cost(accounts["Acquisition Channel"].to_numpy(), rng)
    accounts[["Masked Account Number", "Acquisition Channel"]].assign(
        **{"Acquisition Cost USD": acq_cost,
           "Acquisition Cohort Month": accounts["Account Open Cycle Index"].map(
               lambda i: cycles[i] if 0 <= i < n_cyc else "predates_window")}
    ).to_csv(out / "Table23_Acquisition.csv", index=False)
    timeline.to_csv(out / "Table24_Product_Holding_Timeline.csv", index=False)

    # ---------------- ground truth: never read by the analytical engine -----
    gtdir = out / "_ground_truth"
    gtdir.mkdir(exist_ok=True)
    lat_gt = lat.drop(columns=["channel_affinity"]).copy()
    lat_gt.insert(0, "Masked Customer Number", cust["Masked Customer Number"].to_numpy())
    lat_gt.insert(1, "acquisition_channel", lat["channel_affinity"].to_numpy())
    lat_gt.to_csv(gtdir / "Latent_Ground_Truth.csv", index=False)
    ground_truth.to_csv(gtdir / "Defect_Ground_Truth.csv", index=False)
    (gtdir / "README.txt").write_text(
        "Evaluation-only. Never join into any table the analytical engine reads.\n"
        "Latents and the true default hazard are the causes.\n"
        "Defects are planted Type A failures with mechanism and impact.\n")

    n_defect_accts = ground_truth["Masked Account Number"].nunique() if len(ground_truth) else 0
    meta = {
        "profile": profile_name, "seed": seed, "customers": int(n),
        "cycles": n_cyc, "from": cycles[0], "to": cycles[-1],
        "transactions": int(len(tx)), "account_cycles": int(len(cyc)),
        "planted_defects": int(len(ground_truth)),
        "planted_defect_accounts": int(n_defect_accts),
        "defect_counts_by_type": ground_truth["Defect Type"].value_counts().to_dict()
        if len(ground_truth) else {},
        "measured_breakage": breakage,
        "measured_blended_earn_rate_points_per_dollar": float(
            tx["Points Earned"].sum() / max(tx["Transaction Amount"].sum(), 1)),
        "measured_blended_earn_rate_value_per_dollar": float(
            (tx["Points Earned"] * tx["Masked Account Number"].map(
                accounts.set_index("Masked Account Number")["Reward Program Code"]
                .map(rules.set_index("Program Code")["Nominal Point Value Cents"])
            ) / 100.0).sum() / max(tx["Transaction Amount"].sum(), 1)),
        "measured_interchange_rate": float(
            tx["Interchange Earned"].sum() / max(tx["Transaction Amount"].sum(), 1)),
        "measured_average_utilization": float(cyc["Utilization"].mean()),
        "measured_revolver_share": float((cyc["Account Type"] == "Revolver").mean()),
        "note": "Breakage, blended earn rate, interchange rate, utilization and "
                "revolver share are MEASURED outputs of generated behavior, "
                "never input parameters.",
    }
    (out / "build_manifest.json").write_text(json.dumps(meta, indent=2, default=str))
    return meta


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="demo", choices=list(PROFILES))
    ap.add_argument("--out", default="./out/demo")
    ap.add_argument("--seed", type=int, default=20260921)
    ap.add_argument("--cycles", type=int, default=36)
    ap.add_argument("--n", type=int, default=None)
    a = ap.parse_args()
    m = build(a.profile, Path(a.out), a.seed, a.cycles, a.n)
    print(json.dumps(m, indent=2, default=str))
