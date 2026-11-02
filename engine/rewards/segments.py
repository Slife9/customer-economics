"""The reward model's screen and priority segment rules (Segment Definitions
sheet of the Reward Profitability Scenario Model v2), per card account.

Screen: open at the last cycle, not charged off, open >= 6 months, fully
loaded card profit < 0 and reward cost >= 50% of revenue. Both use the
reward-model P&L in data.py, which includes a sign-up bonus earned in the
trailing 12 cycles (the workbook counts bonus cost in the segment P&L).

Segments are mutually exclusive, first match wins, in this order:
relationship, quasi_cash, bonus_chasers, optimizers, low_spend, else
unassigned. Thresholds come from the assumptions config.

One interpretation, stated: the workbook's "inactive since bonus posted" is
read as no purchases after the 3-month offer window closes (the bonus posts
when the window ends), not after the month the threshold was crossed.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

ORDER = ["relationship", "quasi_cash", "bonus_chasers", "optimizers", "low_spend"]


def _rules(t: pd.DataFrame, th: dict) -> dict:
    """{segment: [(rule label, threshold text, actual series, met series)]}.
    A segment matches when all its rules are met; rules joined by OR are
    expressed as one rule."""
    pct = lambda s: s.map(lambda v: "n/a" if pd.isna(v) else f"{v:.0%}")
    usd = lambda s: s.map(lambda v: "n/a" if pd.isna(v) else f"${v:,.0f}")
    rel_met = (t["noncard_profit"] >= th["relationship_min_noncard_profit_usd"]) | \
              (t["deposit_balance"] >= th["relationship_min_deposit_balance_usd"])
    qc_met = (t["flagged_spend_share"] >= th["quasi_cash_min_spend_share"]) | \
             (t["effective_interchange"] <= th["quasi_cash_max_effective_interchange"])
    drop = th["bonus_chaser_min_spend_drop"]
    chase_met = (t["spend_change_after_window_pct"] <= -100 * drop) | t["inactive_after_window"]
    return {
        "relationship": [(
            "Non-card relationship profit or deposits",
            f">= ${th['relationship_min_noncard_profit_usd']:,.0f}/yr OR deposits >= ${th['relationship_min_deposit_balance_usd']:,.0f}",
            usd(t["noncard_profit"]) + " / " + usd(t["deposit_balance"]), rel_met)],
        "quasi_cash": [(
            "Quasi-cash / low-interchange spend share, or effective interchange",
            f">= {th['quasi_cash_min_spend_share']:.0%} OR <= {th['quasi_cash_max_effective_interchange']:.2%}",
            pct(t["flagged_spend_share"]) + " / " + t["effective_interchange"].map(lambda v: "n/a" if pd.isna(v) else f"{v:.2%}"),
            qc_met)],
        "bonus_chasers": [
            ("Account tenure", f"<= {th['bonus_chaser_max_tenure_months']} months",
             t["tenure_months"].map(lambda v: f"{v:.0f} months"), t["tenure_months"] <= th["bonus_chaser_max_tenure_months"]),
            ("Sign-up bonus paid (Table26)", "> $0", usd(t["bonus_paid"]), t["bonus_paid"] > 0),
            ("Spend after the window", f"down >= {drop:.0%} OR no purchases since the window",
             t["spend_change_after_window_pct"].map(lambda v: "n/a" if pd.isna(v) else f"{v:+.0f}%")
             + np.where(t["inactive_after_window"], " (inactive)", ""), chase_met)],
        "optimizers": [
            ("Months paid in full (of 12)", f">= {th['optimizer_min_paid_in_full_months']}",
             t["paid_in_full_months"].map(lambda v: f"{v:.0f}"), t["paid_in_full_months"] >= th["optimizer_min_paid_in_full_months"]),
            ("Bonus-category share of spend", f">= {th['optimizer_min_bonus_category_share']:.0%}",
             pct(t["bonus_category_share"]), t["bonus_category_share"] >= th["optimizer_min_bonus_category_share"]),
            ("Annual purchase spend", f">= ${th['optimizer_min_annual_spend_usd']:,.0f}",
             usd(t["spend"]), t["spend"] >= th["optimizer_min_annual_spend_usd"])],
        "low_spend": [
            ("Annual purchase spend", f"< ${th['low_spend_max_annual_spend_usd']:,.0f}",
             usd(t["spend"]), t["spend"] < th["low_spend_max_annual_spend_usd"]),
            ("Account tenure", f">= {th['low_spend_min_tenure_months']} months",
             t["tenure_months"].map(lambda v: f"{v:.0f} months"), t["tenure_months"] >= th["low_spend_min_tenure_months"]),
            ("Active months (of 12)", f">= {th['low_spend_min_active_months']}",
             t["active_months"].map(lambda v: f"{v:.0f}"), t["active_months"] >= th["low_spend_min_active_months"])],
    }


def screen(t: pd.DataFrame, th: dict) -> pd.Series:
    return (t["open_at_last"] & ~t["charged_off"]
            & (t["tenure_months"] >= th["screen_min_tenure_months"])
            & (t["fully_loaded_profit"] < th["screen_max_fully_loaded_profit_usd"])
            & (t["revenue"] > 0)
            & (t["reward_cost_incl_bonus"] >= th["screen_min_reward_cost_share_of_revenue"] * t["revenue"]))


def assign(t: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Adds `screened` and `segment` ('unassigned' if screened and no rule
    matches; NaN if not screened)."""
    th = cfg["thresholds"]
    t = t.copy()
    t["screened"] = screen(t, th)
    rules = _rules(t, th)
    seg = pd.Series(np.nan, index=t.index, dtype=object)
    free = t["screened"].copy()
    for name in ORDER:
        met = pd.concat([r[3].fillna(False) for r in rules[name]], axis=1).all(axis=1)
        hit = met & free
        seg[hit] = name
        free &= ~hit
    seg[free] = "unassigned"
    t["segment"] = seg
    return t


def screen_trace(row: pd.Series, th: dict) -> list[dict]:
    rev = row["revenue"]
    share = row["reward_cost_incl_bonus"] / rev if rev > 0 else np.nan
    return [
        {"rule": "Open at the last cycle, not charged off", "threshold": "yes",
         "actual": "yes" if row["open_at_last"] and not row["charged_off"] else "no",
         "met": bool(row["open_at_last"] and not row["charged_off"])},
        {"rule": "Account open at least", "threshold": f"{th['screen_min_tenure_months']} months",
         "actual": f"{row['tenure_months']:.0f} months", "met": bool(row["tenure_months"] >= th["screen_min_tenure_months"])},
        {"rule": "Fully loaded card profit, trailing 12 (incl. sign-up bonus)", "threshold": "< $0",
         "actual": f"${row['fully_loaded_profit']:,.2f}", "met": bool(row["fully_loaded_profit"] < th["screen_max_fully_loaded_profit_usd"])},
        {"rule": "Reward cost (incl. sign-up bonus) as % of revenue",
         "threshold": f">= {th['screen_min_reward_cost_share_of_revenue']:.0%}",
         "actual": "n/a" if np.isnan(share) else f"{share:.0%}",
         "met": bool(rev > 0 and share >= th["screen_min_reward_cost_share_of_revenue"])},
    ]


def segment_trace(t: pd.DataFrame, account: str, cfg: dict) -> dict:
    """Every rule for every segment, against one account, in priority order."""
    th = cfg["thresholds"]
    row_frame = t.loc[[account]]
    rules = _rules(row_frame, th)
    out = []
    for name in ORDER:
        rs = [{"rule": r[0], "threshold": r[1], "actual": str(r[2].iloc[0]), "met": bool(r[3].fillna(False).iloc[0])}
              for r in rules[name]]
        out.append({"segment": name, "all_met": all(r["met"] for r in rs), "rules": rs})
    return {"screen": screen_trace(t.loc[account], th), "segments": out,
            "assigned": t.loc[account, "segment"] if "segment" in t.columns else None}
