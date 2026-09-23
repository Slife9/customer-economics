"""CECL risk parameters (ASC 326). US GAAP - there is no IFRS 9 staging here.

The important choice: PD, LGD and lifetime ECL are the BANK'S ESTIMATES,
produced by a scorecard that sees only cycle-to-date observables and carries
model error. They are not computed from the realized future.

If the allowance were computed from the truth, the bank would be clairvoyant,
expected loss would be exactly right, and every risk-mispricing finding the
analytical engine could produce would be an artifact. The true hazard is
written to ground truth instead, so the estimate can be scored against it.

No allowance is carried on unfunded unconditionally cancellable commitments
(ASC 326-20-30-11), so lifetime is bounded by drawn-balance runoff.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

# Reasonable-and-supportable forecast period, then straight-line reversion to
# a through-the-cycle mean. Stated as an assumption, as ASC 326 requires.
RS_FORECAST_MONTHS = 12
REVERSION_MONTHS = 12
EXPECTED_RUNOFF_MONTHS = 18
LGD_BASE = 0.74


def _logistic(z):
    return 1.0 / (1.0 + np.exp(-z))


def estimate(cyc: pd.DataFrame, cust: pd.DataFrame, rng: np.random.Generator,
             profile: dict) -> pd.DataFrame:
    """A behavioral scorecard over observables, with model error."""
    df = cyc[["Masked Customer Number", "Masked Account Number", "Cycle Month",
              "Cycle Index", "Ending Balance", "Credit Limit", "Utilization",
              "Days Past Due", "Delinquency Bucket", "Account Type"]].copy()
    score = cust.set_index("Masked Customer Number")["Credit Score"]
    tenure = cust.set_index("Masked Customer Number")["Customer Tenure Years"]
    df["_score"] = df["Masked Customer Number"].map(score).astype(float)
    df["_tenure"] = df["Masked Customer Number"].map(tenure).astype(float)

    # Observables only: score, utilization, delinquency, tenure, account type.
    # Calibrated so an average-quality account (score ~700, util ~0.25, dpd 0,
    # tenure ~10yr) lands near a 3% 12-month PD, with score and delinquency
    # doing most of the work - matching the roughly 4.5-6% annualized net
    # charge-off rate a real US card book runs.
    z = (-3.55
         - 0.0140 * (df["_score"] - 660.0)
         + 1.60 * np.clip(df["Utilization"], 0, 1.5)
         + 0.0500 * np.clip(df["Days Past Due"], 0, 180)
         - 0.020 * np.clip(df["_tenure"], 0, 25)
         + np.where(df["Account Type"] == "Revolver", 0.30, -0.30))
    # Model error: a real scorecard is not a perfect read of the hazard.
    z = z + rng.normal(0.0, 0.35, len(df))
    pd_12 = np.clip(_logistic(z), 0.0004, 0.90)

    # Lifetime over the expected runoff of a cancellable line, with the
    # reasonable-and-supportable period at the forecast rate and the remainder
    # reverting to a through-the-cycle mean.
    ttc = float(np.mean(pd_12))
    monthly = pd_12 / 12.0
    rs = 1.0 - (1.0 - monthly) ** RS_FORECAST_MONTHS
    rest_months = max(EXPECTED_RUNOFF_MONTHS - RS_FORECAST_MONTHS, 0)
    monthly_tcc = 0.5 * monthly + 0.5 * (ttc / 12.0)
    rev = 1.0 - (1.0 - monthly_tcc) ** rest_months
    pd_life = np.clip(1.0 - (1.0 - rs) * (1.0 - rev), pd_12, 0.995)

    lgd = np.clip(LGD_BASE + rng.normal(0, 0.035, len(df))
                  - 0.06 * np.clip(df["_score"] - 700, 0, 150) / 150.0, 0.55, 0.97)

    # EAD is the drawn balance. No allowance on the undrawn cancellable line.
    ead = df["Ending Balance"].to_numpy()
    lifetime_ecl = np.round(pd_life * lgd * ead, 2)
    ecl_12 = np.round(pd_12 * lgd * ead, 2)

    out = pd.DataFrame({
        "Masked Customer Number": df["Masked Customer Number"],
        "Masked Account Number": df["Masked Account Number"],
        "Cycle Month": df["Cycle Month"],
        "PD 12 Month": np.round(pd_12, 6),
        "PD Lifetime": np.round(pd_life, 6),
        "LGD": np.round(lgd, 4),
        "EAD": np.round(ead, 2),
        "Expected Credit Loss 12 Month": ecl_12,
        "Lifetime Expected Credit Loss": lifetime_ecl,
        "Measurement Basis": "CECL lifetime (ASC 326)",
        "Allowance On Unfunded Commitment": 0.0,
        "Unfunded Commitment Basis":
            "None - unconditionally cancellable (ASC 326-20-30-11)",
        "Reasonable And Supportable Months": RS_FORECAST_MONTHS,
        "Reversion Months": REVERSION_MONTHS,
        "Reversion Approach": "straight-line to through-the-cycle mean",
        "Expected Runoff Months": EXPECTED_RUNOFF_MONTHS,
    })
    # Monthly provision is the change in the allowance.
    out = out.sort_values(["Masked Account Number", "Cycle Month"])
    out["Monthly Provision"] = (out.groupby("Masked Account Number")
                                ["Lifetime Expected Credit Loss"].diff()
                                .fillna(out["Lifetime Expected Credit Loss"]).round(2))
    return out.reset_index(drop=True)


def charge_off_and_recovery(cyc: pd.DataFrame, cycles: list[str],
                            rng: np.random.Generator) -> pd.DataFrame:
    """Realized credit loss and post-charge-off recovery.

    Without this the P&L does not reconcile: an allowance exists but no loss is
    ever realized, and the roll-rate benchmarks have no terminal state.
    """
    co = cyc[cyc["Charged Off Indicator"]].copy()
    if not len(co):
        return pd.DataFrame(columns=[
            "Masked Account Number", "Charge Off Cycle Month",
            "Gross Charge Off Amount", "Recovery Cycle Month",
            "Recovery Amount", "Net Credit Loss"])
    idx = {c: i for i, c in enumerate(cycles)}
    rows = []
    for _, r in co.iterrows():
        gross = float(r["Ending Balance"])
        ci = idx[r["Cycle Month"]]
        # Recoveries arrive over the following year, typically 8-14% gross.
        rec_total = gross * np.clip(rng.normal(0.11, 0.045), 0.0, 0.42)
        lag = int(rng.integers(2, 10))
        rc = cycles[min(ci + lag, len(cycles) - 1)] if ci + lag < len(cycles) else ""
        rows.append({
            "Masked Account Number": r["Masked Account Number"],
            "Charge Off Cycle Month": r["Cycle Month"],
            "Gross Charge Off Amount": round(gross, 2),
            "Recovery Cycle Month": rc,
            "Recovery Amount": round(rec_total if rc else 0.0, 2),
            "Net Credit Loss": round(gross - (rec_total if rc else 0.0), 2),
        })
    return pd.DataFrame(rows)
