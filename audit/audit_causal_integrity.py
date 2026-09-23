"""Independent diagnostic on the initially synthesized portfolios.

Tests things the shipped Layer 2 suite does not: causal integrity, latent
recoverability, defect detectability from evidence, and schema completeness
against the data requirements spec.
"""
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(sys.argv[1])
DEMO = ROOT / "portfolio_demo" / "demo"
CTRL = ROOT / "portfolio_negative_control" / "negative_control"
VAR = ROOT / "portfolio_variants"

def load(p, name, **kw):
    return pd.read_csv(p / name, **kw)

def sec(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)

cust = load(DEMO, "Table1_Credit_Card_Customer.csv")
cyc = load(DEMO, "Table2_Account_Cycle.csv")
lat = load(DEMO, "_ground_truth/Latent_Ground_Truth.csv")
gt = load(DEMO, "_ground_truth/Defect_Ground_Truth.csv")
drv = load(DEMO, "Table12_Cost_Drivers.csv")
risk = load(DEMO, "Table8_Risk_Parameters.csv")
cap = load(DEMO, "Table9_Capital_RWA.csv")

cust_c = load(CTRL, "Table1_Credit_Card_Customer.csv")
cyc_c = load(CTRL, "Table2_Account_Cycle.csv")
lat_c = load(CTRL, "_ground_truth/Latent_Ground_Truth.csv")

TXCOLS = ["Masked Account Number", "Cycle Month", "Transaction amount",
          "Merchant Category Code (MCC)", "Interchange earned",
          "Interchange Rate Applied", "Points earned on transaction", "Earn Basis"]
tx = load(DEMO, "Table4_Credit_Card_Transaction.csv", usecols=TXCOLS)

# ---------------------------------------------------------------- schema gaps
sec("1. SCHEMA COMPLETENESS vs SPEC")
required = {
    "Customer (5.1)": (cust.columns, [
        ("state / ZIP geography", ["State", "ZIP", "Zip Code"]),
        ("tenure with bank", ["Tenure", "Customer Tenure"]),
        ("credit score band", ["Credit Score Band", "Score Band"]),
        ("accommodation plan", ["Accommodation", "Accommodation Plan"]),
    ]),
    "Card Account (5.2)": (cust.columns, [
        ("account open date", ["Account Open Date", "Open Date"]),
        ("first-year flag", ["First Year", "First Year Flag"]),
        ("CONTRACTUAL APR (separate from charged)", ["Contractual APR", "Contract APR"]),
        ("original credit limit", ["Original Credit Limit"]),
    ]),
    "Account Cycle (5.3)": (cyc.columns, [
        ("minimum payment", ["Minimum Payment", "Minimum Payment Due"]),
        ("payment made", ["Payment Made", "Payment Amount"]),
        ("delinquency bucket", ["Delinquency Bucket"]),
        ("cash balance split", ["Cash Balance", "Cash Advance Balance"]),
        ("promo EXPIRY cycle", ["Promotional Expiry", "Promotional Expiry Cycle",
                                "Promo Expiry Cycle"]),
        ("statement delivery pref", ["Statement Delivery", "Statement Delivery Preference"]),
    ]),
    "Transaction (5.4)": (tx.columns if False else
                          pd.read_csv(DEMO / "Table4_Credit_Card_Transaction.csv",
                                      nrows=1).columns, [
        ("transaction / posting date", ["Transaction Date", "Posting Date"]),
        ("cash advance indicator", ["Cash Advance", "Cash Advance Indicator"]),
        ("foreign flag / FX markup", ["Foreign Transaction", "FX Markup"]),
        ("disputed flag", ["Disputed", "Disputed Flag"]),
    ]),
}
for tbl, (cols, checks) in required.items():
    cols = set(cols)
    for label, cands in checks:
        hit = [c for c in cands if c in cols]
        print(f"  {'OK  ' if hit else 'MISS'}  {tbl:22s} {label}")

sec("1b. TABLES ABSENT ENTIRELY")
present = {p.name for p in DEMO.glob("Table*.csv")}
for n, t in [(3, "Card"), (5, "Installment Plan"), (6, "Deposit Account"),
             (7, "Loan Account"), (10, "FTP Curve"), (13, "Fee Schedule"),
             (14, "Waivers"), (20, "Limit Change Events"), (21, "Rate Change Events"),
             (22, "Attrition Events"), (23, "Acquisition")]:
    if not any(f"Table{n}_" in p for p in present):
        print(f"  MISSING  Table{n:<3} {t}")

# ------------------------------------------------------- latent recoverability
sec("2. LATENT RECOVERABILITY (acceptance criterion 6)")
acct_util = cyc.groupby("Masked Account Number")["Utilization"].mean()
m = cust.merge(lat, on="Masked Customer Number")
m["mean_util"] = m["Masked Account Number"].map(acct_util)
calls = drv.groupby("Masked Account Number")["Contact Center Calls"].sum()
sess = drv.groupby("Masked Account Number")["Digital Sessions"].sum()
m["tot_calls"] = m["Masked Account Number"].map(calls)
m["tot_sessions"] = m["Masked Account Number"].map(sess)
spend = tx.groupby("Masked Account Number")["Transaction amount"].sum()
m["tot_spend"] = m["Masked Account Number"].map(spend)

pairs = [("credit_appetite", "mean_util"), ("problem_rate", "tot_calls"),
         ("digital_fluency", "tot_sessions"), ("spend_level", "tot_spend"),
         ("payment_discipline", "Credit Score")]
for l, o in pairs:
    r = m[[l, o]].corr().iloc[0, 1]
    flag = "  <-- RECOVERABLE" if abs(r) > 0.85 else ""
    print(f"  corr({l:20s}, {o:14s}) = {r:+.3f}{flag}")

# ------------------------------------------------- utilization structurally pinned
sec("3. IS UTILIZATION A MEASURED OUTPUT OR THE LATENT ITSELF?")
print(f"  demo    mean limit = {cust['Credit Limit'].mean():9,.0f}   "
      f"mean utilization = {cyc['Utilization'].mean():.4f}")
print(f"  control mean limit = {cust_c['Credit Limit'].mean():9,.0f}   "
      f"mean utilization = {cyc_c['Utilization'].mean():.4f}")
dl = cust_c['Credit Limit'].mean() / cust['Credit Limit'].mean() - 1
du = cyc_c['Utilization'].mean() / cyc['Utilization'].mean() - 1
print(f"  limit change {dl:+.1%}  ->  utilization change {du:+.1%}")
print("  A large limit cut that does not move utilization means balance is")
print("  generated as appetite x limit, so utilization IS the latent.")

# --------------------------------------------------------- score risk gradient
sec("4. SCORE -> RISK GRADIENT (needed for Layer 2 charge-off by band)")
cb = cust[["Masked Account Number", "Credit Score"]].copy()
cb["band"] = pd.cut(cb["Credit Score"], [0, 600, 660, 720, 780, 900],
                    labels=["<600", "600-659", "660-719", "720-779", "780+"])
j = cyc.merge(cb, on="Masked Account Number")
g = j.groupby("band", observed=True).apply(
    lambda d: pd.Series({
        "n_acct": d["Masked Account Number"].nunique(),
        "30+ dpd rate": (d["Days Past Due"] >= 30).mean(),
        "mean util": d["Utilization"].mean()}), include_groups=False)
print(g.to_string(float_format=lambda v: f"{v:,.4f}"))
lo, hi = g["30+ dpd rate"].iloc[0], g["30+ dpd rate"].iloc[-1]
print(f"\n  delinquency ratio worst:best band = {lo / max(hi, 1e-9):,.1f}x")
print("  Real US card books run roughly 15-40x between these extremes.")

# ------------------------------------------------------------ account type mix
sec("5. ACCOUNT TYPE - EMERGENT OR ASSIGNED? (spec 5.3)")
print(cyc["Account Type"].value_counts(normalize=True).to_string(
    float_format=lambda v: f"{v:.4f}"))
at = cyc.groupby("Masked Account Number")["Account Type"].nunique()
print(f"\n  accounts whose type NEVER changes across 24 cycles: "
      f"{(at == 1).mean():.1%}")
print("  An emergent type should migrate as behaviour changes.")

# ------------------------------------------------------- acquisition channel
sec("6. ACQUISITION CHANNEL QUALITY (spec 5.12)")
mm = m.groupby("Acquisition Channel")[
    ["credit_appetite", "payment_discipline", "price_sensitivity",
     "relationship_propensity", "spend_level"]].mean()
print(mm.to_string(float_format=lambda v: f"{v:,.3f}"))
sd = mm.std() / mm.mean()
print(f"\n  cross-channel coefficient of variation:")
for k, v in sd.items():
    print(f"    {k:26s} {v:.4f}" + ("   <-- channel is noise" if v < 0.02 else ""))

# --------------------------------------------------------------- interchange
sec("7. INTERCHANGE DIFFERENTIATION")
txp = pd.read_csv(DEMO / "Table4_Credit_Card_Transaction.csv",
                  usecols=["Masked Account Number", "Transaction amount",
                           "Interchange earned", "Interchange Rate Applied",
                           "Merchant Category Code (MCC)"])
prod = cust.set_index("Masked Account Number")["Product"]
txp["Product"] = txp["Masked Account Number"].map(prod)
byp = txp.groupby("Product").apply(
    lambda d: d["Interchange earned"].sum() / d["Transaction amount"].sum(),
    include_groups=False)
print(byp.to_string(float_format=lambda v: f"{v:.5f}"))
print(f"\n  distinct rates in force: {txp['Interchange Rate Applied'].nunique()}")
print(f"  blended: {txp['Interchange earned'].sum() / txp['Transaction amount'].sum():.5f}")

# ----------------------------------------------------------------- breakage
sec("8. BREAKAGE - WHICH DEFINITION?")
red = load(DEMO, "Table17_Reward_Redemption.csv")
exp = load(DEMO, "Table19_Reward_Expiry.csv")
earned = txp_pts = pd.read_csv(DEMO / "Table4_Credit_Card_Transaction.csv",
                               usecols=["Points earned on transaction"]
                               )["Points earned on transaction"].sum()
print(f"  points earned          {earned:15,.0f}")
print(f"  points redeemed        {red['Points Redeemed'].sum():15,.0f}")
print(f"  points expired         {exp['Points Expired'].sum():15,.0f}")
print(f"\n  expired / earned              = {exp['Points Expired'].sum() / earned:.4f}"
      "   <- Layer 2 uses this")
print(f"  (earned - redeemed) / earned  = "
      f"{1 - red['Points Redeemed'].sum() / earned:.4f}   <- manifest uses this")
mani = json.loads((DEMO / "build_manifest.json").read_text())
print(f"\n  manifest breakage_rate: {mani.get('measured_breakage', {}).get('breakage_rate')}")
print(f"  manifest keys: {list(mani.get('measured_breakage', {}).keys())}")

# ---------------------------------------------------------- defect detectability
sec("9. PLANTED DEFECTS - DETECTABLE FROM EVIDENCE?")
print(gt["Defect Type"].value_counts().to_string())
print(f"\n  total planted: {len(gt)}   accounts: {gt['Masked Account Number'].nunique()}")
spec_types = ["UNPOSTED_CONTRACTUAL_FEE", "EXPIRED_CONCESSION", "WAIVER_NO_EXPIRY",
              "PROMO_FAILED_TO_REVERT", "INTERCHANGE_BELOW_EXPECTED",
              "PRICE_BELOW_CONTRACT", "WRONG_EARN_RULE"]
have = set(gt["Defect Type"])
for t in spec_types:
    print(f"  {'present' if t in have else 'ABSENT ':8s}  {t}")

sec("9b. CAN PRICE_BELOW_CONTRACT EVER BE DETECTED?")
print(f"  columns containing 'APR': "
      f"{[c for c in list(cust.columns) + list(cyc.columns) if 'APR' in c]}")
print("  Detection needs contractual APR held separately from charged APR.")

sec("9c. CAN PROMO_FAILED_TO_REVERT EVER BE DETECTED?")
print(f"  Promotional Status values: {sorted(cyc['Promotional Status'].dropna().unique())}")
print(f"  promo expiry cycle column present: "
      f"{any('Expiry' in c or 'Expir' in c for c in cyc.columns)}")

# ------------------------------------------------------------- hardship realism
sec("10. HARDSHIP / SCRA - CORRELATED WITH DIFFICULTY?")
print(f"  hardship prevalence {cust['Hardship'].mean():.4f}   "
      f"SCRA {cust['SCRA'].mean():.4f}")
print(f"  corr(hardship, payment_discipline) = "
      f"{m['Hardship'].astype(int).corr(m['payment_discipline']):+.4f}")
print(f"  corr(hardship, problem_rate)       = "
      f"{m['Hardship'].astype(int).corr(m['problem_rate']):+.4f}")
hj = cyc.merge(cust[["Masked Account Number", "Hardship"]], on="Masked Account Number")
print(f"  30+ dpd rate | hardship=True  {(hj[hj.Hardship]['Days Past Due'] >= 30).mean():.4f}")
print(f"  30+ dpd rate | hardship=False {(hj[~hj.Hardship]['Days Past Due'] >= 30).mean():.4f}")

# ------------------------------------------------------------------ spelling
sec("11. AMERICAN SPELLING (acceptance criterion 9)")
brit = ["Programme", "Behavioural", "Centre", "Instalment", "Utilisation", "Authorised"]
for f in sorted(DEMO.glob("*.csv")):
    hdr = pd.read_csv(f, nrows=0).columns
    bad = [c for c in hdr if any(b in c for b in brit)]
    if bad or any(b in f.name for b in brit):
        print(f"  {f.name}")
        if any(b in f.name for b in brit):
            print(f"      filename contains British spelling")
        for c in bad:
            print(f"      column: {c}")

# --------------------------------------------------------------- profitability
sec("12. PROFITABILITY SANITY (Layer 2 has NO benchmark for this)")
interest = cyc["Purchase Interest"].sum() + cyc["Promotional Interest"].sum()
ic = txp["Interchange earned"].sum()
fees = cyc["Late Fee Amount"].sum() + cyc["Card Annual Fee"].sum()
rw = red["Redemption Cost USD"].sum()
ecl = risk["Expected Loss Monthly"].sum()
capc = cap["Regulatory Capital Charge Monthly"].sum()
n = cust["Masked Account Number"].nunique()
yrs = cyc["Cycle Month"].nunique() / 12
print(f"  accounts {n:,}   years {yrs:.1f}")
for lbl, v in [("interest", interest), ("interchange", ic), ("fees", fees),
               ("rewards cost", -rw), ("expected loss", -ecl),
               ("capital charge", -capc)]:
    print(f"    {lbl:16s} {v:14,.0f}   per acct/yr {v / n / yrs:9,.2f}")
rev = interest + ic + fees
print(f"\n  revenue per account per year: {rev / n / yrs:,.2f}")
print("  US card industry runs roughly $350-550 revenue per active account/yr.")
