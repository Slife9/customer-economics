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

from .base import Lever, SizeResult

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

        cv["l2_action"] = np.select(
            [dormant, idle_light_use, active_transactor, stretched, routed],
            ["ENGAGE", "DECREASE", "GROW_ENGAGEMENT", "INCREASE", "DECREASE_RISK_EXPOSURE"],
            default="")
        return cv[cv["l2_action"] != ""].copy()

    def size(self, population: pd.DataFrame) -> SizeResult:
        dec = population[population["l2_action"].isin(["DECREASE", "DECREASE_RISK_EXPOSURE"])]
        inc = population[population["l2_action"] == "INCREASE"]
        engage = population[population["l2_action"].isin(["ENGAGE", "GROW_ENGAGEMENT"])]

        # Target limit for a genuine trim: cover the peak balance actually
        # observed AND the actual annual spend cycled through it, with
        # headroom - never just the latest snapshot.
        target_limit_dec = np.maximum(
            dec["peak_utilization_12m"] * dec["current_limit"] * 1.5,
            dec["trailing_12m_spend"] * 1.10).clip(lower=300)
        limit_cut = (dec["current_limit"] - target_limit_dec).clip(lower=0)
        el_avoided = float((limit_cut * dec["pd_lifetime"] * dec["lgd"]
                           * dec["behavioral_ccf"]).sum())
        econ_capital_relief = float((limit_cut * dec["behavioral_ccf"] * 0.08).sum())

        peer_util = population.groupby("Credit Score Band")["peak_utilization_12m"].transform("median")
        headroom_gain = (peer_util - inc["peak_utilization_12m"]).clip(lower=0) * inc["current_limit"]
        incremental_interest = float((headroom_gain * inc["latest_charged_apr"] / 100.0).sum())

        priced = el_avoided + incremental_interest
        current_engage_revenue = float(engage["card_revenue"].sum())
        return SizeResult(
            priced_value_usd=round(priced, 2),
            basis="expected-loss avoided from EAD reduction (same PD/LGD the "
                 "bank already uses, target limit sized off PEAK utilization "
                 "and actual trailing spend - never a single snapshot) plus "
                 "peer-benchmarked incremental interest on genuinely "
                 "stretched good-standing accounts",
            caveat=f"regulatory capital relief from decreases is $0 by design "
                   f"(0% CCF on cancellable undrawn lines, 12 CFR 217.33(b)(1)). "
                   f"Economic capital relief (diagnostic only): "
                   f"${econ_capital_relief:,.0f}. {len(engage)} customers are "
                   f"flagged for engagement rather than a limit change - "
                   f"their current combined card revenue of "
                   f"${current_engage_revenue:,.0f}/yr is reported as context, "
                   f"not a forecast of what a campaign would recover (that "
                   f"requires a champion/challenger test, per section 7).",
            unpriced_context_usd=econ_capital_relief)

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
