"""
ProfitInsight synthesis engine.

    python run.py --profile default          --out ./out/demo
    python run.py --profile negative_control --out ./out/negative_control
    python run.py --profile transactor_heavy --out ./out/variant_transactor

Design rule enforced throughout: generate causes, never effects. No parameter
in this engine is named after anything the analytical engine reports. There is
no n_unprofitable_customers dial. Profitability emerges or it does not.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from synth import latents as L, policy as P, transactions as TX, rewards as RW, cycles as CY

ROOT = Path(__file__).parent
CFG = ROOT / "config"

SEGMENTS = ["Retail", "Mass Market", "Mass Affluent", "Premier",
            "Small Business", "Private Banking", "Student"]
SEG_W = [0.42, 0.20, 0.15, 0.10, 0.065, 0.035, 0.03]

PROFILES = {
    "default": {"n": 5000, "generosity": 1.0, "promo_share": 0.12,
                "defect_prevalence": 0.035},
    # Clean book: nothing planted, tighter limits, sensible pricing.
    # If the engine still finds large opportunity here, it is manufacturing it.
    # Clean book: nothing planted, limits sized to appetite, better discipline.
    # Credit appetite is NOT tilted - doing so cut underused limits but raised
    # balances and therefore expected loss, confounding the comparison.
    "negative_control": {"n": 5000, "generosity": 0.62, "promo_share": 0.06,
                         "defect_prevalence": 0.0,
                         "latent_tilt": {"payment_discipline": 0.10}},
    "transactor_heavy": {"n": 2000, "generosity": 1.0, "promo_share": 0.08,
                         "defect_prevalence": 0.035,
                         "latent_tilt": {"payment_discipline": 0.22,
                                         "credit_appetite": -0.10}},
    "subprime_heavy": {"n": 2000, "generosity": 0.9, "promo_share": 0.15,
                       "defect_prevalence": 0.035, "score_shift": -95,
                       "latent_tilt": {"payment_discipline": -0.18}},
    "premium_heavy": {"n": 2000, "generosity": 1.25, "promo_share": 0.10,
                      "defect_prevalence": 0.035, "score_shift": 55,
                      "segment_weights": [0.18, 0.16, 0.24, 0.20, 0.09, 0.11, 0.02]},
}


def cycle_list(start="2023-01", n=24):
    y, m = map(int, start.split("-"))
    out = []
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


def build(profile_name: str, out: Path, seed: int = 20260920):
    prof = PROFILES[profile_name]
    rng = np.random.default_rng(seed + abs(hash(profile_name)) % 10000)
    cycles = cycle_list()
    n = prof["n"]
    out.mkdir(parents=True, exist_ok=True)

    # ---------- customers ----------
    segw = prof.get("segment_weights", SEG_W)
    segw = np.array(segw, dtype=float); segw /= segw.sum()
    segment = rng.choice(SEGMENTS, n, p=segw)
    score = np.clip(rng.normal(710 + prof.get("score_shift", 0), 78, n), 480, 850).round().astype(int)
    age = np.clip(rng.gamma(9.5, 4.6, n) + 18, 18, 92).round().astype(int)

    lat = L.draw_latents(n, segment, score, rng, prof)
    product = P.assign_product(score, segment, rng)
    programme = P.assign_programme(product, rng)
    limit = P.limit_policy(score, product, segment, rng, prof["generosity"])
    apr = P.pricing_policy(score, product, rng)
    annual_fee = P.assign_annual_fee(product, programme, rng)

    hardship = rng.random(n) < 0.021
    scra = rng.random(n) < 0.006
    dormant = rng.random(n) < 0.035

    cust_id = [f"CUS2{i:06d}" for i in range(n)]
    acct_id = [f"ACC7{i:06d}" for i in range(n)]

    accounts = pd.DataFrame({
        "Masked Customer Number": cust_id, "Masked Account Number": acct_id,
        "latent_idx": np.arange(n), "Segment": segment, "Age": age,
        "Credit Score": score, "Product": product, "Reward Programme": programme,
        "Credit Limit": limit, "Purchase Rate (APR)": apr, "Annual Fee": annual_fee,
        "Hardship": hardship, "SCRA": scra, "dormant": dormant,
        "Acquisition Channel": rng.choice(
            ["branch", "digital", "aggregator", "partner", "direct_mail"], n,
            p=[0.22, 0.34, 0.19, 0.13, 0.12]),
        "Provenance": f"synth:{profile_name}",
    })

    # ---------- transactions with MCC, interchange from the rate card ----------
    rate_card = TX.load_rate_card(CFG / "interchange_rate_card.csv")
    mcc_cat = TX.load_mcc(CFG / "mcc_catalog.csv")
    tx = TX.generate(accounts, lat, cycles, rate_card, mcc_cat, rng)

    # ---------- account cycles ----------
    cyc = CY.simulate_cycles(accounts, lat, cycles, rng, prof["promo_share"])

    # ---------- planted Type A defects ----------
    if prof["defect_prevalence"] > 0:
        tx, cyc, gt, wrong_earn = CY.plant_defects(
            accounts, cyc, tx, rng, prof["defect_prevalence"])
    else:
        gt = pd.DataFrame(columns=["Masked Account Number", "Defect Type",
                                   "Description", "Cycles Affected",
                                   "Estimated Total Impact"])
        wrong_earn = set()

    # ---------- rewards ----------
    rules = RW.load_rules(CFG / "reward_rules.csv")
    channels = RW.load_channels(CFG / "redemption_channels.csv")
    tx = RW.earn(tx, accounts, rules, wrong_earn)
    red, liab, expiry = RW.redeem(tx, accounts, lat, rules, channels, cycles, rng)
    breakage = RW.measure_breakage(tx, red, rules)

    # ---------- risk, capital, cost ----------
    risk = CY.risk_cecl(cyc, accounts, rng)
    cap = CY.capital_us(cyc)
    drv = CY.cost_drivers(cyc, accounts, lat, rng)
    pools = CY.cost_pools()

    # ---------- emit ----------
    pub = accounts.drop(columns=["latent_idx", "dormant"])
    pub.to_csv(out / "Table1_Credit_Card_Customer.csv", index=False)
    cyc.to_csv(out / "Table2_Account_Cycle.csv", index=False)
    tx.drop(columns=["Reward Programme"]).to_csv(
        out / "Table4_Credit_Card_Transaction.csv", index=False)
    risk.to_csv(out / "Table8_Risk_Parameters.csv", index=False)
    cap.to_csv(out / "Table9_Capital_RWA.csv", index=False)
    pools.to_csv(out / "Table11_Cost_Pools.csv", index=False)
    drv.to_csv(out / "Table12_Cost_Drivers.csv", index=False)
    pd.read_csv(CFG / "interchange_rate_card.csv").to_csv(
        out / "Table15_Interchange_Rate_Card.csv", index=False)
    pd.read_csv(CFG / "reward_rules.csv").to_csv(
        out / "Table16_Reward_Programme_Rules.csv", index=False)
    red.to_csv(out / "Table17_Reward_Redemption.csv", index=False)
    liab.to_csv(out / "Table18_Reward_Liability.csv", index=False)
    expiry.to_csv(out / "Table19_Reward_Expiry.csv", index=False)

    # ---------- ground truth: NEVER read by the analytical engine ----------
    gtdir = out / "_ground_truth"
    gtdir.mkdir(exist_ok=True)
    lg = lat.copy()
    lg.insert(0, "Masked Customer Number", cust_id)
    lg.to_csv(gtdir / "Latent_Ground_Truth.csv", index=False)
    gt.to_csv(gtdir / "Defect_Ground_Truth.csv", index=False)
    (gtdir / "README.txt").write_text(
        "These files are evaluation-only.\n"
        "They must never be joined into any table the analytical engine reads.\n"
        "Latents are the causes; defects are planted Type A failures.\n")

    meta = {"profile": profile_name, "seed": seed, "customers": int(n),
            "cycles": len(cycles), "from": cycles[0], "to": cycles[-1],
            "transactions": int(len(tx)), "account_cycles": int(len(cyc)),
            "planted_defects": int(len(gt)),
            "measured_breakage": {**breakage,
                "points_expired": float(expiry['Points Expired'].sum()) if len(expiry) else 0.0,
                "breakage_rate": float(expiry['Points Expired'].sum() /
                    max(tx['Points earned on transaction'].sum(), 1)) if len(expiry) else 0.0},
            "measured_blended_earn": float(
                tx["Points earned on transaction"].sum() /
                max(tx["Transaction amount"].sum(), 1)),
            "measured_interchange_rate": float(
                tx["Interchange earned"].sum() / max(tx["Transaction amount"].sum(), 1)),
            "note": "Breakage, blended earn and interchange rate are MEASURED "
                    "outputs of generated behaviour, not input parameters."}
    (out / "build_manifest.json").write_text(json.dumps(meta, indent=2))
    return meta


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="default", choices=list(PROFILES))
    ap.add_argument("--out", default="./out/demo")
    ap.add_argument("--seed", type=int, default=20260920)
    a = ap.parse_args()
    m = build(a.profile, Path(a.out), a.seed)
    print(json.dumps(m, indent=2))
