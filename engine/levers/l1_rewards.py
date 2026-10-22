"""L1 - Rewards and promo economics.

The strongest play is usually not cutting rewards, it is charging for them
(concept spec section 6). Population and worklist are unchanged by the
valuation rebuild; valuation follows SPEC_lever_valuation_rebuild.md 4.1:

  Group 1  REVIEW_REWARD_PROGRAM_COST (routed loss-makers): a programme-level
           reward cost reduction.
  Group 2  PILOT_ALIGNED_ANNUAL_FEE (profitable, fee-free, reward-heavy).
           Fee-eligible = reward_expense >= min_reward_multiple_of_fee x fee.
           Of the eligible, some accept the fee, some downgrade to a cheaper
           reward tier, some close the card.

Every response share is a business assumption (lever_assumptions.json) - the
whole lever is assumption-based and needs a champion/challenger pilot.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from .base import Lever, SizeResult, component, scenario
from . import assumptions as ASSUME
from ..core.suppression import SuppressedPopulation

OPPORTUNITY_REWARD_VALUE_FLOOR = 100.0
K = "Masked Customer Number"

METHOD_NOTE = (
    "Fee-eligible Group 2 customers (reward cost at least the configured "
    "multiple of the proposed annual fee) are offered the fee: the share who "
    "accept pay it, the share who downgrade cut their reward cost, and the "
    "share who close take their card profit with them. Group 1 (routed "
    "reward-driven loss-makers) gets a programme-level reward cost reduction. "
    "All response shares are assumptions - pilot required.")


def valuation_inputs(cv: pd.DataFrame, wl: pd.DataFrame) -> dict:
    w = wl.merge(cv[[K, "card_net"]], on=K, how="left")
    g1 = w[w["action"] == "REVIEW_REWARD_PROGRAM_COST"]
    g2 = w[w["action"] == "PILOT_ALIGNED_ANNUAL_FEE"]
    return {
        "group1_customers": int(len(g1)),
        "group1_reward_expense_sum": float(g1["reward_expense"].sum()),
        "group2_customers": int(len(g2)),
        # Per-customer arrays (not aggregates) because the eligibility
        # threshold itself depends on two assumptions (fee, multiple).
        "group2_reward_expense": [float(v) for v in g2["reward_expense"]],
        "group2_card_net": [float(v) for v in g2["card_net"]],
        "group2_relationship_nep": [float(v) for v in g2["trailing_12m_net_economic_profit"]],
    }


def _mean(a: np.ndarray) -> float:
    return float(a.mean()) if len(a) else 0.0


def value_scenarios(inputs: dict, a: dict) -> dict:
    fee = float(a["annual_fee_usd"])
    threshold = float(a["min_reward_multiple_of_fee"]) * fee
    re = np.asarray(inputs["group2_reward_expense"], dtype=float)
    cn = np.asarray(inputs["group2_card_net"], dtype=float)
    nep = np.asarray(inputs["group2_relationship_nep"], dtype=float)
    elig = re >= threshold
    n = int(elig.sum())
    out = {}
    for s in ASSUME.SCENARIOS:
        acc = ASSUME.pick(a["accept_share"], s)
        dn = ASSUME.pick(a["downgrade_share"], s)
        cl = ASSUME.pick(a["close_share"], s)
        cut = ASSUME.pick(a["downgrade_reward_reduction"], s)
        g1cut = ASSUME.pick(a["group1_reward_reduction"], s)
        comp = {
            "fee_revenue": component(n * acc * fee, "revenue", "assumption"),
            "downgrade_reward_saving": component(
                n * dn * cut * _mean(re[elig]), "cost_saving", "assumption"),
            "closure_card_profit_lost": component(
                -n * cl * _mean(cn[elig]), "lost_profit", "assumption"),
            "group1_programme_saving": component(
                g1cut * inputs["group1_reward_expense_sum"], "cost_saving", "assumption"),
        }
        sc = scenario(comp)
        relationship_loss = -n * cl * _mean(nep[elig])
        sc["extras"] = {
            "annual_fee_usd": fee,
            "fee_eligibility_threshold_usd": threshold,
            # Named as in expected_values.json: the NUMBER of customers who
            # are offered the fee (fee-eligible Group 2), not the fee amount.
            "offered_fee": n,
            "group2_not_offered": int(len(re) - n),
            "total_if_closers_leave_bank": (sc["total_usd"]
                                            - comp["closure_card_profit_lost"]["value_usd"]
                                            + relationship_loss),
            "closers": n * cl,
        }
        out[s] = sc
    return out


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
        a = self.lever_assumptions()
        inputs = valuation_inputs(population, self.worklist(population))
        scen = value_scenarios(inputs, a)
        base = scen["base"]
        return SizeResult(
            priced_value_usd=round(base["total_usd"], 2),
            basis=METHOD_NOTE,
            caveat=(f"Assumption-based, pilot required. "
                    f"{base['extras']['offered_fee']} fee-eligible customers; "
                    f"if closers leave the bank entirely (not just the card) the "
                    f"base total is ${base['extras']['total_if_closers_leave_bank']:,.0f}."),
            unpriced_context_usd=None,
            scenarios=scen, assumptions_used=a, method_note=METHOD_NOTE,
            inputs=inputs, gate_value_usd=base["total_usd"])

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
