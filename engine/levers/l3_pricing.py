"""L3 - Value-based pricing.

The gap this lever addresses opens because risk drifts after origination
while the rate does not (concept spec section 6). Population is any account
priced meaningfully below its own current-risk peer cohort.

Valuation (SPEC_lever_valuation_rebuild.md 4.3): the CARD Act only lets a
new rate apply to NEW transactions, so only REVOLVING balance generates
extra interest - and only the share of it repriced within year 1. Pay-in-
full transactors are flagged but not targeted (no interest to gain).
Accounts in their first year are excluded (CARD Act first-year protection).
Attrition, balance reduction among stayers and the repriced share are all
assumptions - pilot required.
"""
from __future__ import annotations
import pandas as pd

from .base import Lever, SizeResult, component, scenario
from . import assumptions as ASSUME

K = "Masked Customer Number"

METHOD_NOTE = (
    "Targets revolvers only (revolving balance = latest purchase balance x "
    "(1 - pay-in-full share) > 0). Full-year value = sum of (pricing gap x "
    "revolving balance); year 1 counts only the share of balance repriced "
    "under new-transactions-only rules, net of leavers and of stayers who "
    "pay down. Leavers take their card profit; each targeted account costs a "
    "notice. First-year accounts are excluded (CARD Act).")


def valuation_inputs(cv: pd.DataFrame, wl: pd.DataFrame) -> dict:
    w = wl.merge(cv, on=K, how="left")
    w = w[~w["first_year_protected"].astype(bool)]
    rev = w["latest_purchase_balance"] * (1 - w["transactor_share_12m"])
    gap = w["target_apr"] - w["current_apr"]
    r = w[rev > 0]
    return {
        "flagged": int(len(w)),
        "first_year_protected_excluded": int(len(wl) - len(w)),
        "targeted": int(len(r)),
        "full_year_gap_value_usd": float((gap[rev > 0] / 100 * rev[rev > 0]).sum()),
        "targeted_revolving_balance_usd": float(rev[rev > 0].sum()),
        "targeted_card_net_mean": float(r["card_net"].mean()) if len(r) else 0.0,
        "targeted_relationship_nep_mean": float(
            r["trailing_12m_net_economic_profit"].mean()) if len(r) else 0.0,
    }


def value_scenarios(inputs: dict, a: dict) -> dict:
    n = inputs["targeted"]
    full = inputs["full_year_gap_value_usd"]
    out = {}
    for s in ASSUME.SCENARIOS:
        rep = ASSUME.pick(a["year1_balance_repriced"], s)
        att = ASSUME.pick(a["attrition"], s)
        red = ASSUME.pick(a["balance_reduction_stayers"], s)
        cost = ASSUME.pick(a["notice_cost_usd"], s)
        lost = -n * att * inputs["targeted_card_net_mean"]
        ops = -n * cost
        y1 = full * rep * (1 - att) * (1 - red)
        comp = {
            "extra_interest": component(y1, "revenue", "assumption"),
            "card_profit_lost": component(lost, "lost_profit", "assumption"),
            "notice_cost": component(ops, "cost", "measured"),
        }
        sc = scenario(comp)
        sc["extras"] = {
            "steady_state": full * (1 - att) * (1 - red) + lost + ops,
            "total_if_leavers_leave_bank": y1 - n * att * inputs["targeted_relationship_nep_mean"] + ops,
            "targeted": n, "flagged": inputs["flagged"],
            "first_year_protected_excluded": inputs["first_year_protected_excluded"],
            "leavers": n * att,
        }
        out[s] = sc
    return out


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
        # CARD Act first-year protection applies to EVERY candidate, including
        # routed loss-makers - previously a routed account in its first year
        # slipped in via the `| routed` branch (population fix, spec 4.3).
        past_first_year = cv["Customer Tenure Years"] * 12 >= FIRST_YEAR_MONTHS
        out = cv[((gap >= PRICING_GAP_POINTS) | (cv["routed_lever"] == "L3"))
                 & past_first_year].copy()
        out["peer_median_apr"] = peer_apr[out.index]
        out["pricing_gap_points"] = gap[out.index]
        return out

    def size(self, population: pd.DataFrame) -> SizeResult:
        a = self.lever_assumptions()
        inputs = valuation_inputs(population, self.worklist(population))
        scen = value_scenarios(inputs, a)
        base = scen["base"]
        return SizeResult(
            priced_value_usd=round(base["total_usd"], 2),
            basis=METHOD_NOTE,
            caveat=(f"Assumption-based, pilot required. {inputs['targeted']} of "
                    f"{inputs['flagged']} flagged accounts revolve and are targeted. "
                    f"Steady state (all balances repriced): "
                    f"${base['extras']['steady_state']:,.0f}/yr."),
            unpriced_context_usd=None,
            scenarios=scen, assumptions_used=a, method_note=METHOD_NOTE,
            inputs=inputs, gate_value_usd=base["total_usd"])

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
