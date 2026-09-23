"""L1 - Rewards and promo economics.

The strongest play is usually not cutting rewards, it is charging for them
(concept spec section 6). Cutting a program's earn rate is a behavioral
question (would the customer spend less, would they leave?) that this
dataset cannot answer - Type C, forbidden. Charging a fee aligned to value
already delivered is not a behavioral question at all; it is a statement
about what is happening today. That is the only part of L1 sized here.
"""
from __future__ import annotations
import pandas as pd

from .base import Lever, SizeResult
from ..core.suppression import SuppressedPopulation

OPPORTUNITY_REWARD_VALUE_FLOOR = 100.0


class L1Rewards(Lever):
    code = "L1"
    name = "Rewards and promo economics"
    gates = ["Reg Z: 45 days notice and right to reject on a new/changed fee"]

    def population(self, pop) -> pd.DataFrame:
        pop = super().population(pop)
        cv = pop.frame
        routed = cv["routed_lever"] == "L1"
        opportunity = ((cv["reward_expense"] >= OPPORTUNITY_REWARD_VALUE_FLOOR)
                       & (cv["annual_fee_total"] <= 0.01)
                       & (~cv["is_below_cost"]))
        out = cv[routed | opportunity].copy()
        out["l1_reason"] = "routed_loss"
        out.loc[opportunity[opportunity].index.intersection(out.index),
               "l1_reason"] = "fee_free_high_reward_opportunity"
        return out

    def size(self, population: pd.DataFrame) -> SizeResult:
        opp = population[population["l1_reason"] == "fee_free_high_reward_opportunity"]
        unpriced = float(opp["reward_expense"].sum())
        return SizeResult(
            priced_value_usd=None,
            basis="Charging for value already delivered is a policy change; "
                 "how many customers would accept the new fee vs. close the "
                 "account is a behavioral response to an untried treatment "
                 "(concept spec section 7) and cannot be sized from this data.",
            unpriced_context_usd=unpriced,
            caveat=f"{len(opp)} profitable customers currently take reward "
                   f"value with no annual fee, totalling ${unpriced:,.0f}/yr "
                   f"in accrued reward cost the relationship never recovers. "
                   f"That figure is context for a fee decision, not a revenue "
                   f"forecast - actual capture depends on take-up under a "
                   f"champion/challenger test.")

    def worklist(self, population: pd.DataFrame) -> pd.DataFrame:
        wl = population.copy()
        wl["action"] = wl["l1_reason"].map({
            "routed_loss": "REVIEW_REWARD_PROGRAM_COST",
            "fee_free_high_reward_opportunity": "PILOT_ALIGNED_ANNUAL_FEE",
        })
        wl["reason"] = wl.apply(
            lambda r: (r["routing_reason"] if r["l1_reason"] == "routed_loss"
                      else f"${r['reward_expense']:,.0f}/yr reward cost, $0 annual fee"),
            axis=1)
        wl["notice_days_required"] = 45
        wl["customer_right_to_reject"] = True
        return wl[["Masked Customer Number", "action", "reason",
                  "trailing_12m_net_economic_profit", "reward_expense",
                  "annual_fee_total", "notice_days_required",
                  "customer_right_to_reject"]]

    def driver(self, customer_view: pd.DataFrame) -> float:
        """Mean unrecovered reward subsidy across accounts with meaningful
        reward value - should shrink where fee policy is aligned to value."""
        cv = customer_view
        eligible = cv[cv["reward_expense"] >= OPPORTUNITY_REWARD_VALUE_FLOOR]
        if not len(eligible):
            return 0.0
        gap = (eligible["reward_expense"] - eligible["annual_fee_total"]).clip(lower=0)
        return float(gap.mean())
