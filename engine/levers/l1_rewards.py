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


# ---------------------------------------------------------------------------
# Explanations for the customer drill-down. Additive only: they read the same
# module constants and formulas as population() and value_scenarios(), and
# audit/audit_lever_estimates.py checks they reconcile to the engine.
#   Group 1   REVIEW_REWARD_PROGRAM_COST (routed reward-driven losses)
#   Group 2   PILOT_ALIGNED_ANNUAL_FEE
#     2a      fee-eligible: offered the fee
#     2b      below the eligibility threshold: not offered the fee

def subgroup(row, a: dict) -> str:
    if row["action"] == "REVIEW_REWARD_PROGRAM_COST":
        return "Group 1"
    threshold = float(a["min_reward_multiple_of_fee"]) * float(a["annual_fee_usd"])
    return "Group 2a" if row["reward_expense"] >= threshold else "Group 2b"


def selection_rules(row, a: dict) -> dict:
    threshold = float(a["min_reward_multiple_of_fee"]) * float(a["annual_fee_usd"])
    g2 = [
        {"rule": "Reward cost, trailing 12 months", "threshold": f">= ${OPPORTUNITY_REWARD_VALUE_FLOOR:,.0f}",
         "actual": f"${row['reward_expense']:,.0f}", "met": bool(row["reward_expense"] >= OPPORTUNITY_REWARD_VALUE_FLOOR)},
        {"rule": "No annual fee today", "threshold": "<= $0.01",
         "actual": f"${row['annual_fee_total']:,.2f}", "met": bool(row["annual_fee_total"] <= 0.01)},
        {"rule": "Profitable relationship", "threshold": "trailing-12m NEP >= $0",
         "actual": f"${row['trailing_12m_net_economic_profit']:,.0f}",
         "met": bool(row["trailing_12m_net_economic_profit"] >= 0)},
    ]
    sets = {
        "Group 1 - routed reward-driven loss": [
            {"rule": "Routed to L1 (reward cost dominates a below-cost relationship)",
             "threshold": "routed_lever = L1", "actual": str(row.get("routed_lever")),
             "met": row.get("routed_lever") == "L1"}],
        "Group 2a - offered the fee": g2 + [
            {"rule": "Fee-eligible: reward cost covers the fee by the configured multiple",
             "threshold": f">= {a['min_reward_multiple_of_fee']} x ${a['annual_fee_usd']} = ${threshold:,.0f}",
             "actual": f"${row['reward_expense']:,.0f}", "met": bool(row["reward_expense"] >= threshold)}],
        "Group 2b - not offered the fee": g2 + [
            {"rule": "Below the fee-eligibility threshold", "threshold": f"< ${threshold:,.0f}",
             "actual": f"${row['reward_expense']:,.0f}", "met": bool(row["reward_expense"] < threshold)}],
    }
    if row["action"] == "REVIEW_REWARD_PROGRAM_COST":
        matched = "Group 1 - routed reward-driven loss"
    else:
        matched = next((k for k in ("Group 2a - offered the fee", "Group 2b - not offered the fee")
                        if all(r["met"] for r in sets[k])), None)
    return {"matched": matched, "rule_sets": sets,
            "precedence": ("A routed reward-driven loss is Group 1 even if it would also meet "
                           "Group 2's rules; Group 2 splits on the fee-eligibility threshold, "
                           "which moves with the configured fee and multiple.")}


def customer_contributions(rows: pd.DataFrame, inputs: dict, a: dict,
                           scenario: str = "base") -> pd.DataFrame:
    fee = float(a["annual_fee_usd"])
    threshold = float(a["min_reward_multiple_of_fee"]) * fee
    acc = ASSUME.pick(a["accept_share"], scenario)
    dn = ASSUME.pick(a["downgrade_share"], scenario)
    cl = ASSUME.pick(a["close_share"], scenario)
    cut = ASSUME.pick(a["downgrade_reward_reduction"], scenario)
    g1cut = ASSUME.pick(a["group1_reward_reduction"], scenario)
    g1 = rows["action"] == "REVIEW_REWARD_PROGRAM_COST"
    elig = (rows["action"] == "PILOT_ALIGNED_ANNUAL_FEE") & (rows["reward_expense"] >= threshold)
    out = pd.DataFrame(index=rows.index)
    out["fee_revenue"] = (acc * fee) * elig
    out["downgrade_reward_saving"] = (dn * cut * rows["reward_expense"]).where(elig, 0.0)
    out["closure_card_profit_lost"] = (-cl * rows["card_net"]).where(elig, 0.0)
    out["group1_programme_saving"] = (g1cut * rows["reward_expense"]).where(g1, 0.0)
    out = out.fillna(0.0).astype(float)
    out["total"] = out.sum(axis=1)
    return out


def customer_trace(row, inputs: dict, a: dict, scenario: str = "base") -> list:
    c = customer_contributions(pd.DataFrame([row]), inputs, a, scenario).iloc[0]
    fee = float(a["annual_fee_usd"])
    acc = ASSUME.pick(a["accept_share"], scenario)
    dn = ASSUME.pick(a["downgrade_share"], scenario)
    cl = ASSUME.pick(a["close_share"], scenario)
    cut = ASSUME.pick(a["downgrade_reward_reduction"], scenario)
    g1cut = ASSUME.pick(a["group1_reward_reduction"], scenario)
    g = subgroup(row, a)
    re, cn = float(row["reward_expense"]), float(row["card_net"])
    if g == "Group 1":
        steps = [{"component": "group1_programme_saving",
                  "formula": "group1_reward_reduction x this customer's reward cost",
                  "substituted": f"{g1cut} x ${re:,.2f}", "value": c["group1_programme_saving"]}]
    elif g == "Group 2a":
        steps = [
            {"component": "fee_revenue", "formula": "accept_share x annual fee",
             "substituted": f"{acc} x ${fee}", "value": c["fee_revenue"]},
            {"component": "downgrade_reward_saving",
             "formula": "downgrade_share x downgrade_reward_reduction x this customer's reward cost",
             "substituted": f"{dn} x {cut} x ${re:,.2f}", "value": c["downgrade_reward_saving"]},
            {"component": "closure_card_profit_lost", "formula": "-close_share x this customer's card_net",
             "substituted": f"-{cl} x ${cn:,.2f}", "value": c["closure_card_profit_lost"]},
        ]
    else:
        steps = [{"component": "not offered the fee",
                  "formula": "reward cost below the eligibility threshold - no fee offered, $0",
                  "substituted": "", "value": 0.0}]
    steps.append({"component": "TOTAL (expected value, base assumptions)",
                  "formula": "sum of the above", "substituted": "", "value": c["total"]})
    return steps


def calculation_steps(inputs: dict, a: dict, scenario: str = "base") -> list:
    fee = float(a["annual_fee_usd"])
    threshold = float(a["min_reward_multiple_of_fee"]) * fee
    re = np.asarray(inputs["group2_reward_expense"], dtype=float)
    cn = np.asarray(inputs["group2_card_net"], dtype=float)
    elig = re >= threshold
    n = int(elig.sum())
    acc = ASSUME.pick(a["accept_share"], scenario)
    dn = ASSUME.pick(a["downgrade_share"], scenario)
    cl = ASSUME.pick(a["close_share"], scenario)
    cut = ASSUME.pick(a["downgrade_reward_reduction"], scenario)
    g1cut = ASSUME.pick(a["group1_reward_reduction"], scenario)
    m_re, m_cn = _mean(re[elig]), _mean(cn[elig])
    return [
        {"component": "fee-eligible customers (Group 2a)",
         "formula": "Group 2 with reward cost >= multiple x fee",
         "substituted": f"reward cost >= {a['min_reward_multiple_of_fee']} x ${fee} = ${threshold:,.0f}",
         "value": n},
        {"component": "fee_revenue", "formula": "n x accept_share x fee",
         "substituted": f"{n} x {acc} x ${fee}", "value": n * acc * fee},
        {"component": "downgrade_reward_saving",
         "formula": "n x downgrade_share x downgrade_reward_reduction x mean reward cost (eligible)",
         "substituted": f"{n} x {dn} x {cut} x ${m_re:,.2f}", "value": n * dn * cut * m_re},
        {"component": "closure_card_profit_lost", "formula": "-n x close_share x mean card_net (eligible)",
         "substituted": f"-{n} x {cl} x ${m_cn:,.2f}", "value": -n * cl * m_cn},
        {"component": "group1_programme_saving",
         "formula": "group1_reward_reduction x sum of Group 1 reward cost",
         "substituted": f"{g1cut} x ${inputs['group1_reward_expense_sum']:,.2f}",
         "value": g1cut * inputs["group1_reward_expense_sum"]},
    ]
