"""US standardized capital, 12 CFR Part 217 subpart D.

Two tracks, carried separately and never blended:

REGULATORY track follows the rule literally: 0% CCF on unconditionally
cancellable undrawn card lines (217.33(b)(1)), 100% risk weight on retail
exposures (217.32; there is no US 75% regulatory-retail bucket), 150% at 90+
days past due or nonaccrual (217.32(k)). Trimming an idle line frees no
regulatory capital under this track - by design, since the CCF on undrawn is
already zero.

ECONOMIC track uses a behavioral CCF calibrated off the drawdown behavior in
limit_events (deteriorating accounts draw down before default), so a line
management lever has somewhere to show a capital effect. This is the
commercial justification for carrying two tracks: a real bank cannot free
regulatory capital by cutting an idle line, so any capital argument for line
management has to stand on the economic track and on loss exposure, not on
the reported RWA number.

CONFIG below is the one-line switch for the March 2026 Basel III endgame
re-proposal (net capital relief, not the 2023 version's ~19% increase) -
verify the current rule status before flipping it for a client engagement.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

CONFIG = {
    "regime": "current_2026",   # "current_2026" | "basel_endgame_reproposal_2026"
    "target_capital_ratio": 0.115,  # internal target, not a regulatory minimum
    "behavioral_ccf_base": 0.42,
}


def _regulatory_risk_weight(days_past_due: np.ndarray) -> np.ndarray:
    return np.where(days_past_due >= 90, 1.50, 1.00)


def compute(cyc: pd.DataFrame, limit_events: pd.DataFrame,
           config: dict | None = None) -> pd.DataFrame:
    cfg = {**CONFIG, **(config or {})}
    df = cyc[["Masked Customer Number", "Masked Account Number", "Cycle Month",
              "Ending Balance", "Credit Limit", "Days Past Due"]].copy()

    drawn = df["Ending Balance"].to_numpy()
    undrawn = np.maximum(df["Credit Limit"].to_numpy() - drawn, 0.0)

    reg_ccf = np.zeros(len(df))  # 217.33(b)(1): unconditionally cancellable
    reg_ead = drawn + undrawn * reg_ccf
    reg_rw = _regulatory_risk_weight(df["Days Past Due"].to_numpy())
    reg_rwa = reg_ead * reg_rw
    reg_capital = reg_rwa * cfg["target_capital_ratio"]

    # Behavioral CCF: rises with recent drawdown-on-deterioration signal.
    # Accounts with a RISK_DETERIORATION limit event in the trailing 6 cycles
    # carry a higher behavioral CCF, reflecting the pre-default drawdown a
    # cancellable line does not stop in practice.
    deteriorating = set()
    if len(limit_events):
        risky = limit_events[limit_events["Reason Code"] == "RISK_DETERIORATION"]
        deteriorating = set(risky["Masked Account Number"])
    is_deteriorating = df["Masked Account Number"].isin(deteriorating).to_numpy()
    beh_ccf = np.where(is_deteriorating, np.clip(cfg["behavioral_ccf_base"] * 1.9, 0, 1),
                       cfg["behavioral_ccf_base"])
    econ_ead = drawn + undrawn * beh_ccf
    econ_rw = np.where(df["Days Past Due"].to_numpy() >= 90, 1.65, 1.15)
    econ_capital = econ_ead * econ_rw * cfg["target_capital_ratio"]

    return pd.DataFrame({
        "Masked Customer Number": df["Masked Customer Number"],
        "Masked Account Number": df["Masked Account Number"],
        "Cycle Month": df["Cycle Month"],
        "Drawn Balance": np.round(drawn, 2),
        "Undrawn Commitment": np.round(undrawn, 2),
        "Unconditionally Cancellable": True,
        "Regulatory CCF": reg_ccf,
        "Regulatory EAD": np.round(reg_ead, 2),
        "Regulatory Risk Weight": reg_rw,
        "Regulatory RWA": np.round(reg_rwa, 2),
        "Target Capital Ratio": cfg["target_capital_ratio"],
        "Regulatory Attributed Capital": np.round(reg_capital, 2),
        "Regulatory Capital Charge Monthly": np.round(reg_capital / 12.0, 2),
        "Regulatory Basis": "12 CFR 217 subpart D",
        "Regime": cfg["regime"],
        "Behavioral CCF": np.round(beh_ccf, 4),
        "Economic EAD": np.round(econ_ead, 2),
        "Economic Attributed Capital": np.round(econ_capital, 2),
        "Economic Capital Charge Monthly": np.round(econ_capital / 12.0, 2),
        "Capital Approach": "dual track - regulatory and economic, never blended",
    })
