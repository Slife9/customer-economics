"""L2 - Line management by value. Moves limits in BOTH directions.

Concept spec section 6 is explicit and counter-intuitive: under 12 CFR
217.33(b)(1) an undrawn card line is unconditionally cancellable and carries
a 0% CCF, so trimming it frees NO regulatory capital. This lever is sized on
expected-loss exposure avoided (a recomputation of ECL under a lower EAD,
using the same PD/LGD the bank already trusts) and, separately, on economic
capital relief - which is management information, never blended with the
regulatory figure that goes in the P&L.

REVISION: a single latest-cycle utilization reading cannot tell a genuinely
idle line apart from a disciplined transactor who pays to zero every month -
both read 0% at the statement date. A customer who spends heavily and pays
in full every month is not idle; they are exactly the customer a bank wants
to keep. Trimming their line on a snapshot misreading would be a real
credibility failure. This lever now looks at:

  - average AND peak utilization over the trailing 12 months, not the latest
    cycle alone
  - actual spend volume relative to the limit (spend_to_limit_ratio) - this
    is what separates "never uses it" from "cycles the whole limit every
    month via full payment"
  - the account-type mix over the window (share of months as Transactor vs.
    Inactive) - a real behavioral pattern, not a one-month snapshot
  - account seasoning (age) - a line is not touched before it has had a
    chance to show a real pattern
  - standing (days past due) and score, for the increase side

Four outcomes instead of one, so "idle" no longer means only "cut it":
  - DECREASE           genuinely idle: low utilization AND low spend velocity
  - ENGAGE             dormant: idle AND spend has actually stopped (see L4's
                        engagement-only accounts too) - a re-activation
                        candidate, not a cut candidate
  - GROW_ENGAGEMENT     an active, high-spend, pay-in-full transactor - the
                        opposite of idle; protect and deepen, do not touch
                        the limit
  - INCREASE            genuinely stretched: high peak utilization, good
                        standing, good score
  - DECREASE_RISK_EXPOSURE  credit-cost-dominant loss-makers routed here
                        independently of utilization (unchanged from before)
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from .base import Lever, SizeResult, component, scenario
from . import assumptions as ASSUME

K = "Masked Customer Number"
DECREASE_COMPONENTS = ("decrease_credit_loss_avoided", "decrease_liquidity_avoided",
                       "decrease_slr_capital_freed")

METHOD_NOTE = (
    "Decreases: expected credit loss avoided on the limit cut (lifetime PD "
    "annualised over the card life), plus the liquidity (LCR) and SLR "
    "carrying cost the cut frees, scaled by the share of decreases actually "
    "implemented. Increases: interest on the share of the new headroom the "
    "customer is assumed to use, less its funding cost, annualised credit "
    "loss and SLR capital. Reactivation: the assumed share of dormant "
    "customers who become typical active card holders, less campaign cost. "
    "Deepen-relationship actions are worth $0 by construction. Dormant-line "
    "right-sizing is reported separately and only added when enabled.")


def _per_undrawn_dollar(df: pd.DataFrame, col: str) -> pd.Series:
    """Each customer's own $ cost per $ of undrawn exposure - derived from the
    already-computed liquidity / leverage diagnostics, never a re-read policy
    constant. Customers with no rate on file contribute $0, not a guess."""
    ok = (df["avg_undrawn_12m"] > 0) & df[col].notna()
    return (df[col] / df["avg_undrawn_12m"]).where(ok, 0.0)


def decrease_target_limit(df: pd.DataFrame) -> pd.Series:
    """The engine's existing decrease rule (unchanged by the rebuild): cover
    the peak balance observed AND the actual annual spend, with headroom."""
    return np.maximum(df["peak_utilization_12m"] * df["current_limit"] * 1.5,
                      df["trailing_12m_spend"] * 1.10).clip(lower=300)


def valuation_inputs(cv: pd.DataFrame, wl: pd.DataFrame) -> dict:
    pop = wl[[K, "action"]].merge(cv, on=K, how="left")
    dec = pop[pop["action"] == "DECREASE_LIMIT"]
    inc = pop[pop["action"] == "INCREASE_LIMIT"]
    dorm = pop[pop["action"] == "REACTIVATION_CAMPAIGN"]

    cut = (dec["current_limit"] - decrease_target_limit(dec)).clip(lower=0)
    cards = cv[cv["holds_card"]]
    drawn = (cards["latest_utilization"] * cards["current_limit"]).sum()
    funding_rate = float(cards["funding_cost"].sum() / drawn) if drawn else 0.0
    active = cv[cv["holds_card"] & (cv["months_inactive_12m"] == 0)]["card_net"]

    # Increase-side terms are linear in increase_pct and headroom_used, so
    # they are stored as sums over current_limit and scaled in
    # value_scenarios() - exact, and lets the what-if explorer move both.
    lev_inc = _per_undrawn_dollar(inc, "leverage_capital_cost")

    carrying = []
    for action, g in pop.groupby("action", sort=False):
        liq = float(g["annual_liquidity_cost"].fillna(0).sum())
        slr = float(g["leverage_capital_cost"].fillna(0).sum())
        cn = float(g["card_net"].sum())
        carrying.append({
            "action": action, "customers": int(len(g)),
            "unused_lines_usd": float(g["avg_undrawn_12m"].sum()),
            "required_hqla_usd": float(g["required_hqla"].fillna(0).sum()),
            "liquidity_cost_usd": liq, "slr_cost_usd": slr,
            "card_net_usd": cn, "card_net_after_carrying_cost_usd": cn - liq - slr,
        })

    return {
        "decrease_customers": int(len(dec)),
        "decrease_limit_cut_usd": float(cut.sum()),
        "decrease_lifetime_expected_loss_usd": float(
            (cut * dec["pd_lifetime"] * dec["lgd"] * dec["behavioral_ccf"]).sum()),
        "decrease_liquidity_cost_usd": float(
            (cut * _per_undrawn_dollar(dec, "annual_liquidity_cost")).sum()),
        "decrease_slr_cost_usd": float(
            (cut * _per_undrawn_dollar(dec, "leverage_capital_cost")).sum()),
        "increase_customers": int(len(inc)),
        "increase_sum_current_limit": float(inc["current_limit"].sum()),
        "increase_sum_limit_x_apr_x_revolve": float(
            (inc["current_limit"] * inc["latest_charged_apr"] / 100
             * (1 - inc["transactor_share_12m"])).sum()),
        "increase_sum_limit_x_pd_x_lgd": float(
            (inc["current_limit"] * inc["pd_lifetime"] * inc["lgd"]).sum()),
        "increase_sum_limit_x_slr_rate": float((inc["current_limit"] * lev_inc).sum()),
        "funding_rate": funding_rate,
        "reactivation_customers": int(len(dorm)),
        "active_card_net_mean": float(active.mean()) if len(active) else 0.0,
        "dormant_card_net_mean": float(dorm["card_net"].mean()) if len(dorm) else 0.0,
        "dormant_carrying_cost_usd": float(
            (dorm["annual_liquidity_cost"].fillna(0) + dorm["leverage_capital_cost"].fillna(0)).sum()),
        "deepen_customers": int((pop["action"] == "DEEPEN_RELATIONSHIP_NO_LIMIT_CHANGE").sum()),
        "leverage_regime": str(cv["leverage_regime"].iloc[0]) if len(cv) else "",
        "carrying_cost_by_group": carrying,
    }


def value_scenarios(inputs: dict, a: dict) -> dict:
    pct = float(a["increase_pct"])
    enabled = bool(a.get("dormant_rightsizing_enabled", False))
    out = {}
    for s in ASSUME.SCENARIOS:
        impl = ASSUME.pick(a["decrease_implemented"], s)
        life = ASSUME.pick(a["card_life_years"], s)
        use = ASSUME.pick(a["headroom_used"], s)
        react = ASSUME.pick(a["reactivation_rate"], s)
        camp = ASSUME.pick(a["campaign_cost_usd"], s)
        n_dorm = inputs["reactivation_customers"]
        comp = {
            "decrease_credit_loss_avoided": component(
                inputs["decrease_lifetime_expected_loss_usd"] * impl / life,
                "avoided_loss", "measured"),
            "decrease_liquidity_avoided": component(
                inputs["decrease_liquidity_cost_usd"] * impl, "cost_saving", "measured"),
            "decrease_slr_capital_freed": component(
                inputs["decrease_slr_cost_usd"] * impl, "cost_saving", "measured"),
            "increase_interest": component(
                pct * use * inputs["increase_sum_limit_x_apr_x_revolve"], "revenue", "assumption"),
            "increase_funding_cost": component(
                -pct * use * inputs["increase_sum_current_limit"] * inputs["funding_rate"],
                "cost", "assumption"),
            "increase_extra_credit_loss": component(
                -pct * use * inputs["increase_sum_limit_x_pd_x_lgd"] / life,
                "avoided_loss", "assumption"),
            "increase_extra_slr_capital": component(
                -pct * (1 - use) * inputs["increase_sum_limit_x_slr_rate"], "cost", "assumption"),
            "reactivation_net": component(
                n_dorm * react * (inputs["active_card_net_mean"] - inputs["dormant_card_net_mean"])
                - n_dorm * camp, "revenue", "assumption"),
        }
        rightsizing = (inputs["dormant_carrying_cost_usd"] * (1 - react)
                       * ASSUME.pick(a["dormant_rightsize_implemented"], s)
                       * ASSUME.pick(a["dormant_rightsize_reduction"], s))
        total_excl = sum(c["value_usd"] for c in comp.values())
        if enabled:
            comp["dormant_rightsizing"] = component(rightsizing, "cost_saving", "assumption")
        sc = scenario(comp)
        sc["extras"] = {
            "dormant_rightsizing": rightsizing,
            "dormant_rightsizing_enabled": enabled,
            "total_with_dormant_rightsizing": total_excl + rightsizing,
            "total_without_dormant_rightsizing": total_excl,
            "carrying_cost_by_group": inputs["carrying_cost_by_group"],
            "funding_rate": inputs["funding_rate"],
            "leverage_regime": inputs["leverage_regime"],
        }
        out[s] = sc
    return out


MIN_SEASONING_MONTHS = 12
IDLE_AVG_UTIL_CEILING = 0.10
IDLE_PEAK_UTIL_CEILING = 0.20
IDLE_SPEND_TO_LIMIT_CEILING = 0.50
DORMANT_SPEND_TO_LIMIT_CEILING = 0.15
DORMANT_INACTIVE_SHARE_FLOOR = 0.50
ACTIVE_TRANSACTOR_SHARE_FLOOR = 0.50
IDLE_LIMIT_FLOOR = 1000.0
STRETCHED_PEAK_UTIL_FLOOR = 0.75


class L2Lines(Lever):
    code = "L2"
    name = "Line management by value"
    gates = ["Reg B adverse action notice on any decrease"]

    def population(self, pop) -> pd.DataFrame:
        pop = super().population(pop)
        cv = pop.frame.copy()

        seasoned = cv["account_age_months"] >= MIN_SEASONING_MONTHS
        good_standing = cv["latest_days_past_due"] == 0
        low_ending_balance = ((cv["avg_utilization_12m"] <= IDLE_AVG_UTIL_CEILING)
                              & (cv["peak_utilization_12m"] <= IDLE_PEAK_UTIL_CEILING))
        light_spend = cv["spend_to_limit_ratio"] <= IDLE_SPEND_TO_LIMIT_CEILING
        very_light_spend = cv["spend_to_limit_ratio"] <= DORMANT_SPEND_TO_LIMIT_CEILING
        mostly_inactive = cv["inactive_share_12m"] >= DORMANT_INACTIVE_SHARE_FLOOR
        heavy_spend_full_pay = ((cv["spend_to_limit_ratio"] > IDLE_SPEND_TO_LIMIT_CEILING)
                                & (cv["transactor_share_12m"] >= ACTIVE_TRANSACTOR_SHARE_FLOOR))

        dormant = (seasoned & good_standing & low_ending_balance & very_light_spend
                  & mostly_inactive & (cv["current_limit"] > IDLE_LIMIT_FLOOR))
        idle_light_use = (seasoned & good_standing & low_ending_balance & light_spend
                          & ~dormant & (cv["current_limit"] > IDLE_LIMIT_FLOOR))
        active_transactor = seasoned & good_standing & low_ending_balance & heavy_spend_full_pay
        stretched = ((cv["peak_utilization_12m"] >= STRETCHED_PEAK_UTIL_FLOOR)
                    & good_standing & (cv["Credit Score"] >= 660))
        routed = cv["routed_lever"] == "L2"
        # The full customer view - valuation needs portfolio-wide figures
        # (funding rate, typical active card holder) not just this population.
        self._cv = pop.frame

        cv["l2_action"] = np.select(
            [dormant, idle_light_use, active_transactor, stretched, routed],
            ["ENGAGE", "DECREASE", "GROW_ENGAGEMENT", "INCREASE", "DECREASE_RISK_EXPOSURE"],
            default="")
        return cv[cv["l2_action"] != ""].copy()

    def size(self, population: pd.DataFrame) -> SizeResult:
        a = self.lever_assumptions()
        cv = getattr(self, "_cv", population)
        inputs = valuation_inputs(cv, self.worklist(population))
        scen = value_scenarios(inputs, a)
        base = scen["base"]
        decrease_side = sum(base["components"][c]["value_usd"] for c in DECREASE_COMPONENTS)
        regime_note = ("SLR regime: unused lines carry leverage capital, so decreases "
                       "free it and increases consume it."
                       if inputs["leverage_regime"] == "SLR" else
                       "Tier 1 regime: unused lines carry no leverage capital (R-01), "
                       "so the SLR components are $0.")
        return SizeResult(
            priced_value_usd=round(base["total_usd"], 2),
            basis=METHOD_NOTE,
            caveat=(f"Decrease side is measured; increase and reactivation are "
                    f"assumption-based, pilot required. {regime_note} Dormant-line "
                    f"right-sizing (base ${base['extras']['dormant_rightsizing']:,.0f}/yr) "
                    f"is {'INCLUDED' if base['extras']['dormant_rightsizing_enabled'] else 'not included'} "
                    f"in the total."),
            unpriced_context_usd=None,
            scenarios=scen, assumptions_used=a, method_note=METHOD_NOTE,
            inputs=inputs,
            # Only the decrease side: L2's driver() measures idle-limit
            # dollars, which the increase/reactivation components do not act on.
            gate_value_usd=decrease_side)

    def worklist(self, population: pd.DataFrame) -> pd.DataFrame:
        wl = population.copy()
        wl["action"] = wl["l2_action"].map({
            "DECREASE": "DECREASE_LIMIT",
            "DECREASE_RISK_EXPOSURE": "DECREASE_LIMIT",
            "INCREASE": "INCREASE_LIMIT",
            "ENGAGE": "REACTIVATION_CAMPAIGN",
            "GROW_ENGAGEMENT": "DEEPEN_RELATIONSHIP_NO_LIMIT_CHANGE",
        })
        wl["adverse_action_notice_required"] = wl["action"] == "DECREASE_LIMIT"

        def _reason(r):
            if r["l2_action"] == "DECREASE_RISK_EXPOSURE":
                return r["routing_reason"]
            if r["l2_action"] == "DECREASE":
                return (f"avg util {r['avg_utilization_12m']:.0%}, peak "
                       f"{r['peak_utilization_12m']:.0%} over 12mo; spend "
                       f"only {r['spend_to_limit_ratio']:.0%} of ${r['current_limit']:,.0f} "
                       f"limit; {r['account_age_months']:.0f}mo seasoned")
            if r["l2_action"] == "ENGAGE":
                return (f"card unused {r['inactive_share_12m']:.0%} of trailing "
                       f"12mo, spend only {r['spend_to_limit_ratio']:.0%} of limit - "
                       f"reactivate before considering a cut")
            if r["l2_action"] == "GROW_ENGAGEMENT":
                return (f"pays in full {r['transactor_share_12m']:.0%} of months "
                       f"while cycling {r['spend_to_limit_ratio']:.0%} of "
                       f"${r['current_limit']:,.0f} limit through spend - active, "
                       f"valuable, NOT idle despite low ending balance")
            return (f"peak utilization {r['peak_utilization_12m']:.0%} over 12mo "
                   f"on ${r['current_limit']:,.0f} limit")

        wl["reason"] = wl.apply(_reason, axis=1)

        def _engagement_tactics(r):
            if r["l2_action"] == "ENGAGE":
                tactics = []
                if r["annual_fee_total"] > 0:
                    tactics.append("Fee waiver/downgrade review - a $0-usage "
                                   "account still paying a fee is a churn risk, "
                                   "not just an idle-limit risk")
                tactics.append("Spend-activation bonus (e.g. bonus points/cashback "
                               "on the next N purchases within 60-90 days)")
                tactics.append("Digital wallet enrollment prompt (Apple Pay / "
                               "Google Pay) - removes the top friction point "
                               "for a card that never got into regular rotation")
                return "; ".join(tactics)
            if r["l2_action"] == "GROW_ENGAGEMENT":
                return ("Category-based bonus offer to capture more of this "
                       "customer's spend from competing cards; loyalty/status "
                       "upgrade review given consistent full-pay behavior; "
                       "do NOT restrict the limit - it is not the constraint")
            return ""

        wl["suggested_engagement_tactics"] = wl.apply(_engagement_tactics, axis=1)
        return wl[["Masked Customer Number", "action", "reason", "current_limit",
                  "avg_utilization_12m", "peak_utilization_12m", "spend_to_limit_ratio",
                  "transactor_share_12m", "account_age_months",
                  "adverse_action_notice_required", "suggested_engagement_tactics"]]

    def driver(self, customer_view: pd.DataFrame) -> float:
        """Mean idle-limit magnitude, using PEAK utilization (not a snapshot)
        - dollars of limit that even the customer's highest observed balance
        over the trailing year never approached. Shrinks where limits are
        periodically right-sized against observed behavior instead of set
        once at origination."""
        cv = customer_view
        idle_amount = ((IDLE_PEAK_UTIL_CEILING - cv["peak_utilization_12m"]).clip(lower=0)
                      * cv["current_limit"])
        return float(idle_amount.mean())
