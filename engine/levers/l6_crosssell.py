"""L6 - Cross-sell and growth by value.

DEVIATION FROM THE LITERAL CONCEPT: the spec frames L6 as steering
"acquisition and cross-sell toward customers who actually earn." A per-
customer cross-sell take-up prediction is exactly the kind of causal
question section 7 forbids - no historical dataset says who WOULD accept an
offer never made. This lever is built instead as CHANNEL QUALITY REVIEW:
rank acquisition channels by the customer value they actually produced, net
of what they cost to acquire - a correlational, backward-looking finding
about channels already run, not a forward prediction about individuals.
This keeps the lever's substance (channels differ in quality, steer spend
accordingly) while staying inside what the data can honestly support.
"""
from __future__ import annotations
import pandas as pd

from .base import Lever, SizeResult


class L6CrossSell(Lever):
    code = "L6"
    name = "Cross-sell and growth by value (channel quality review)"
    gates = []

    def __init__(self, acquisition: pd.DataFrame, accounts: pd.DataFrame):
        self.acquisition = acquisition
        # If cost data wasn't part of this upload, rank by gross value only
        # and say so explicitly - never assume a cost. A missing column here
        # degrades this one lever; it must never block the rest of the run.
        self.has_cost = "Acquisition Cost USD" in acquisition.columns
        self.accounts = accounts

    def _channel_value(self, population_source: pd.DataFrame) -> pd.DataFrame:
        if not len(self.acquisition) or "Acquisition Channel" not in self.acquisition.columns:
            return pd.DataFrame(columns=["n", "mean_net_value", "mean_acq_cost",
                                        "mean_net_value_after_cac"])
        acct_to_cust = self.accounts.set_index(
            "Masked Account Number")["Masked Customer Number"]
        acq = self.acquisition.copy()
        acq["Masked Customer Number"] = acq["Masked Account Number"].map(acct_to_cust)
        m = acq.merge(population_source[["Masked Customer Number",
                                        "trailing_12m_net_economic_profit"]],
                     on="Masked Customer Number", how="left")
        agg = {"n": ("Masked Customer Number", "nunique"),
              "mean_net_value": ("trailing_12m_net_economic_profit", "mean")}
        if self.has_cost:
            agg["mean_acq_cost"] = ("Acquisition Cost USD", "mean")
        by_channel = m.groupby("Acquisition Channel").agg(**agg)
        if self.has_cost:
            by_channel["mean_net_value_after_cac"] = (
                by_channel["mean_net_value"] - by_channel["mean_acq_cost"])
        else:
            by_channel["mean_acq_cost"] = None
            by_channel["mean_net_value_after_cac"] = by_channel["mean_net_value"]
        return by_channel.sort_values("mean_net_value_after_cac", ascending=False)

    def population(self, pop) -> pd.DataFrame:
        pop = super().population(pop)
        cv = pop.frame
        ranked = self._channel_value(cv)
        worst_channels = ranked.tail(max(len(ranked) // 3, 1)).index.tolist()

        acct_to_cust = self.accounts.set_index(
            "Masked Account Number")["Masked Customer Number"]
        acq = self.acquisition.copy()
        acq["Masked Customer Number"] = acq["Masked Account Number"].map(acct_to_cust)
        cust_to_channel = acq.set_index("Masked Customer Number")["Acquisition Channel"]

        out = cv[cv["Masked Customer Number"].map(cust_to_channel).isin(
            worst_channels)].copy()
        out["acquisition_channel"] = out["Masked Customer Number"].map(cust_to_channel)
        self._ranked_cache = ranked
        return out

    def size(self, population: pd.DataFrame) -> SizeResult:
        ranked = getattr(self, "_ranked_cache", self._channel_value(population))
        if len(ranked) < 2:
            return SizeResult(None, basis="fewer than 2 channels present, or no "
                             "acquisition data was included in this upload")
        best, worst = ranked.iloc[0], ranked.iloc[-1]
        gap = best["mean_net_value_after_cac"] - worst["mean_net_value_after_cac"]
        priced = gap * worst["n"]
        cost_note = ("" if self.has_cost else " NOTE: this upload has no "
                    "'Acquisition Cost USD' column, so this ranks channels by "
                    "gross customer value only, not net of acquisition cost - "
                    "a channel that looks best here could still be the most "
                    "expensive to run.")
        return SizeResult(
            priced_value_usd=round(float(priced), 2),
            basis=f"({best.name} mean net value ${best['mean_net_value_after_cac']:,.0f} "
                 f"- {worst.name} mean net value ${worst['mean_net_value_after_cac']:,.0f}) "
                 f"x {int(worst['n'])} accounts acquired via {worst.name}",
            caveat="a correlational, backward-looking channel comparison, not "
                  "a guarantee the same volume is available at the same cost "
                  "through the better channel - directional, not a "
                  f"promise.{cost_note}")

    def worklist(self, population: pd.DataFrame) -> pd.DataFrame:
        wl = population.copy()
        wl["action"] = "REVIEW_ACQUISITION_CHANNEL_MIX"
        wl["reason"] = wl["acquisition_channel"].map(
            lambda c: f"acquired via {c}, a bottom-tier channel by net value after CAC")
        return wl[["Masked Customer Number", "action", "reason",
                  "acquisition_channel", "trailing_12m_net_economic_profit"]]

    def driver(self, customer_view: pd.DataFrame) -> float:
        """Spread between the best and worst channel's net value after CAC.
        This dataset's negative control does not vary channel mix or
        quality, so expect this lever to report inconclusive at the gate -
        that is the honest result, not a bug."""
        ranked = self._channel_value(customer_view)
        if len(ranked) < 2:
            return 0.0
        return float(ranked["mean_net_value_after_cac"].iloc[0]
                    - ranked["mean_net_value_after_cac"].iloc[-1])
