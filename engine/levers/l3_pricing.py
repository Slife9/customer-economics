"""L3 - Value-based pricing.

The gap this lever addresses opens because risk drifts after origination
while the rate does not (concept spec section 6). Population is any account
priced meaningfully below its own current-risk peer cohort - not just the
ones already loss-making, since a mispriced account that hasn't tipped into
loss yet is still the same finding.

Sizing is deliberately capped at a naive, zero-elasticity estimate. The real
value of repricing depends on how customers respond - attrition, revolve
behavior - and that is a causal question about a treatment never applied
(section 7). This lever always returns priced_value_usd=None for exactly
that reason; the naive ceiling is reported as context only.
"""
from __future__ import annotations
import pandas as pd

from .base import Lever, SizeResult

PRICING_GAP_POINTS = 2.0
FIRST_YEAR_MONTHS = 12


class L3Pricing(Lever):
    code = "L3"
    name = "Value-based pricing"
    gates = ["CARD Act: no increase in the first year",
            "CARD Act: prospective on new transactions only, 45 days notice",
            "Fair lending review of the repricing worklist",
            "Champion/challenger test before broad rollout"]

    def population(self, pop) -> pd.DataFrame:
        pop = super().population(pop)
        cv = pop.frame
        peer_apr = cv.groupby("Credit Score Band")["latest_charged_apr"].transform("median")
        gap = peer_apr - cv["latest_charged_apr"]
        eligible = (gap >= PRICING_GAP_POINTS) & (cv["Customer Tenure Years"] * 12
                                                  >= FIRST_YEAR_MONTHS)
        out = cv[eligible | (cv["routed_lever"] == "L3")].copy()
        out["peer_median_apr"] = peer_apr[out.index]
        out["pricing_gap_points"] = gap[out.index]
        return out

    def size(self, population: pd.DataFrame) -> SizeResult:
        naive = float((population["pricing_gap_points"] / 100.0 / 12.0
                      * population["latest_purchase_balance"] * 12).sum())
        return SizeResult(
            priced_value_usd=None,
            basis="repricing value depends on how customers respond - "
                 "attrition and revolve behavior under a new rate - which is "
                 "a causal question about a treatment never applied (concept "
                 "spec section 7). Not sizeable from historical data alone.",
            unpriced_context_usd=round(naive, 2),
            caveat=f"${naive:,.0f}/yr is the zero-elasticity ceiling: what the "
                   f"gap is worth if every customer stayed and paid it. Real "
                   f"value requires a champion/challenger test.")

    def worklist(self, population: pd.DataFrame) -> pd.DataFrame:
        wl = population.copy()
        wl["action"] = "REPRICE_TO_PEER_MEDIAN"
        wl["current_apr"] = wl["latest_charged_apr"]
        wl["target_apr"] = wl["peer_median_apr"]
        wl["applies_to_new_transactions_only"] = True
        wl["notice_days_required"] = 45
        wl["first_year_protected"] = wl["Customer Tenure Years"] * 12 < FIRST_YEAR_MONTHS
        wl["reason"] = wl.apply(
            lambda r: f"{r['pricing_gap_points']:.1f} pts below "
                     f"{r['Credit Score Band']} peer median", axis=1)
        return wl[["Masked Customer Number", "action", "reason", "current_apr",
                  "target_apr", "applies_to_new_transactions_only",
                  "notice_days_required", "first_year_protected"]]

    def driver(self, customer_view: pd.DataFrame) -> float:
        """Mean pricing gap to peer median - shrinks where the bank actually
        reprices to track drifting risk instead of pricing once at
        origination and never again."""
        cv = customer_view
        peer_apr = cv.groupby("Credit Score Band")["latest_charged_apr"].transform("median")
        return float((peer_apr - cv["latest_charged_apr"]).clip(lower=0).mean())
