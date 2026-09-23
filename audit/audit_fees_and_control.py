import json
from pathlib import Path
import numpy as np, pandas as pd

R = Path("initial_data")
DEMO = R / "portfolio_demo" / "demo"
cyc = pd.read_csv(DEMO / "Table2_Account_Cycle.csv")
cust = pd.read_csv(DEMO / "Table1_Credit_Card_Customer.csv")

print("=== FEE DECOMPOSITION")
n, ncyc = cust["Masked Account Number"].nunique(), cyc["Cycle Month"].nunique()
print(f"accounts {n:,}  cycles {ncyc}")
af = cyc["Card Annual Fee"]
print(f"\nCard Annual Fee: total {af.sum():,.0f}  per acct/yr {af.sum()/n/(ncyc/12):,.2f}")
print(f"  cycles with a nonzero annual fee: {(af>0).sum():,} of {len(cyc):,} "
      f"({(af>0).mean():.1%})")
per_acct = cyc[cyc['Card Annual Fee']>0].groupby("Masked Account Number").size()
print(f"  for accounts that pay one, times charged over {ncyc} cycles:")
print(per_acct.value_counts().sort_index().head(30).to_string())
print(f"\n  >>> an annual fee should hit ONCE per 12 cycles, i.e. {ncyc//12}x here")

lf = cyc["Late Fee Amount"]
print(f"\nLate Fee: total {lf.sum():,.0f}  per acct/yr {lf.sum()/n/(ncyc/12):,.2f}")
print(f"  incidence per cycle {(lf>0).mean():.4f}")
print(f"  distinct amounts: {sorted(lf[lf>0].unique())[:15]}")
print(f"  late fee charged while Days Past Due == 0: "
      f"{((lf>0) & (cyc['Days Past Due']==0)).sum():,}")

print("\n=== ANNUAL FEE vs CUSTOMER TABLE")
caf = cust.set_index("Masked Account Number")["Annual Fee"]
chg = cyc[cyc["Card Annual Fee"]>0].groupby("Masked Account Number")["Card Annual Fee"].first()
cmp = pd.DataFrame({"stated": caf, "charged": chg}).dropna()
print(f"  accounts where charged != stated: {(cmp.stated != cmp.charged).sum():,}")
print(f"  accounts with stated fee 0 but charged >0: "
      f"{((cmp.stated==0)&(cmp.charged>0)).sum():,}")
print(f"  accounts with stated fee >0 but never charged: "
      f"{(caf[caf>0].index.difference(chg.index)).size:,}")

print("\n=== MANIFEST vs ITS OWN DATA")
mani = json.loads((DEMO / "build_manifest.json").read_text())
print(json.dumps(mani, indent=2)[:900])
pts = pd.read_csv(DEMO / "Table4_Credit_Card_Transaction.csv",
                  usecols=["Points earned on transaction"])["Points earned on transaction"].sum()
ntx = sum(1 for _ in open(DEMO / "Table4_Credit_Card_Transaction.csv")) - 1
print(f"\n  actual transactions in folder : {ntx:,}")
print(f"  manifest says                 : {mani.get('transactions'):,}")
print(f"  actual points earned          : {pts:,.0f}")
print(f"  manifest points_earned        : {mani.get('measured_breakage',{}).get('points_earned'):,.0f}")

print("\n=== ACCOUNT TYPE STICKINESS")
at = cyc.sort_values(["Masked Account Number","Cycle Month"])
flips = at.groupby("Masked Account Number")["Account Type"].apply(
    lambda s: (s != s.shift()).sum() - 1)
print(f"  mean type changes per account over {ncyc} cycles: {flips.mean():.2f}")
print(f"  accounts changing type >12 times: {(flips>12).mean():.1%}")
print("  A real book: revolver/transactor status is sticky, a few flips at most.")

print("\n=== DELINQUENCY: ROLL AND CURE?")
dq = at.copy()
dq["prev"] = dq.groupby("Masked Account Number")["Days Past Due"].shift()
tr = pd.crosstab(dq["prev"], dq["Days Past Due"], normalize="index")
print(tr.round(3).to_string())

print("\n=== NEGATIVE CONTROL: WHAT ACTUALLY DIFFERS?")
cc = pd.read_csv(R/"portfolio_negative_control"/"negative_control"/"Table2_Account_Cycle.csv")
cu = pd.read_csv(R/"portfolio_negative_control"/"negative_control"/"Table1_Credit_Card_Customer.csv")
dd = pd.read_csv(DEMO/"Table12_Cost_Drivers.csv")
dc = pd.read_csv(R/"portfolio_negative_control"/"negative_control"/"Table12_Cost_Drivers.csv")
rows = [
 ("mean credit limit", cust["Credit Limit"].mean(), cu["Credit Limit"].mean()),
 ("mean APR", cust["Purchase Rate (APR)"].mean(), cu["Purchase Rate (APR)"].mean()),
 ("annual fee incidence", (cust["Annual Fee"]>0).mean(), (cu["Annual Fee"]>0).mean()),
 ("mean annual fee", cust["Annual Fee"].mean(), cu["Annual Fee"].mean()),
 ("late fee per acct", cyc["Late Fee Amount"].sum()/n, cc["Late Fee Amount"].sum()/cu["Masked Account Number"].nunique()),
 ("calls per acct", dd["Contact Center Calls"].sum()/n, dc["Contact Center Calls"].sum()/cu["Masked Account Number"].nunique()),
 ("digital sessions/acct", dd["Digital Sessions"].sum()/n, dc["Digital Sessions"].sum()/cu["Masked Account Number"].nunique()),
 ("mean utilization", cyc["Utilization"].mean(), cc["Utilization"].mean()),
 ("30+ dpd rate", (cyc["Days Past Due"]>=30).mean(), (cc["Days Past Due"]>=30).mean()),
]
print(f"  {'metric':24s} {'demo':>12s} {'control':>12s} {'delta':>9s}")
for k,a,b in rows:
    print(f"  {k:24s} {a:12,.4f} {b:12,.4f} {(b/a-1)*100 if a else 0:8.1f}%")
