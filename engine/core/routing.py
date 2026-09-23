"""Routing: attribute each loss to its dominant cost, then to the lever that
addresses THAT cost (concept spec section 4, "why routing is the step that
matters").

Without this step a below-cost customer gets analyzed by all six levers and
none of them owns the finding. With it, a rewards-driven loss goes to L1 and
nothing else, a servicing-driven loss goes to L4 and nothing else.

DESIGN CHOICE (spec left this unspecified): credit-cost-dominant losses split
between L2 and L3 by comparing the customer's own charged APR to the median
charged APR of their own credit-score-band cohort. Priced meaningfully below
peers of the same risk -> L3 (a pricing gap, fixable by repricing). Priced in
line with peers and still loss-making -> L2 (the risk itself is the exposure;
trim it, don't reprice a rate that was never actually the problem).

A cost line only counts as "dominant" if it clears a materiality bar (40% of
total cost). Below that, no single lever fixes this customer - it is routed
to STRUCTURAL, which is the "roughly one in five, whatever the bank does"
floor from concept spec section 8. Reporting that floor honestly is a
finding, not a failure to route.

IMPORTANT: dominance is computed on cost_to_serve_MARGINAL, never the
blended cost_to_serve total. A completely unused card still carries a share
of the servicing platform's fixed capacity cost (allocated overhead - real,
but not caused by anything this customer did, and not something a lever
aimed at this one customer can change). Using the blended figure would route
every near-zero-activity account to L4 with "cost to serve dominant," which
is backwards: there is nothing to fix about THIS customer's servicing
behavior when they generate none. The fixed share still counts toward the
total-cost denominator (so the share math stays honest about the full loss),
it just never gets to be the reason a customer is routed anywhere.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from .suppression import SuppressedPopulation, require_suppressed

DOMINANCE_THRESHOLD = 0.40
PRICING_GAP_POINTS = 2.0

COST_TO_LEVER = {
    "reward_expense": "L1",
    "cost_to_serve_marginal": "L4",
    # credit_cost splits between L2/L3 below
    # funding_cost / capital_cost dominance has no dedicated lever - STRUCTURAL
}


def route(suppressed: SuppressedPopulation) -> SuppressedPopulation:
    """Takes and returns a SuppressedPopulation - routing only ever runs on
    an already-suppressed frame (concept spec 5.4: suppression before
    routing, never after). This is enforced by type, not by call order."""
    require_suppressed(suppressed)
    cv = suppressed.frame.copy()
    loss = cv[cv["is_below_cost"]].copy()
    if not len(loss):
        cv["routed_lever"] = pd.Series(dtype=object)
        cv["routing_reason"] = pd.Series(dtype=object)
        return SuppressedPopulation(cv, suppressed.suppressed)

    # Denominator: the FULL cost base, including the fixed-allocated share of
    # servicing overhead, so shares stay honest about the true total loss.
    full_cost_cols = ["reward_expense", "funding_cost", "credit_cost",
                      "cost_to_serve_marginal", "cost_to_serve_fixed_allocated",
                      "capital_cost"]
    total_cost = loss[full_cost_cols].sum(axis=1).replace(0, np.nan)

    # Candidates for "dominant cause": the fixed-allocated share is
    # deliberately excluded - it dilutes every other share correctly, but can
    # never itself be the reason a customer is routed anywhere, since no
    # per-customer lever changes a shared platform's fixed cost.
    candidate_cols = ["reward_expense", "funding_cost", "credit_cost",
                      "cost_to_serve_marginal", "capital_cost"]
    shares = loss[candidate_cols].div(total_cost, axis=0).fillna(0.0)
    dominant_col = shares.idxmax(axis=1)
    dominant_share = shares.max(axis=1)

    peer_apr = (cv.groupby("Credit Score Band")["latest_charged_apr"]
               .median().rename("peer_median_apr"))
    loss = loss.merge(peer_apr, on="Credit Score Band", how="left")

    friendly = {"cost_to_serve_marginal": "servicing cost this customer caused",
               "reward_expense": "reward_expense", "funding_cost": "funding_cost",
               "credit_cost": "credit_cost", "capital_cost": "capital_cost"}

    lever, reason = [], []
    for i, row in loss.reset_index(drop=True).iterrows():
        col, share = dominant_col.iloc[i], dominant_share.iloc[i]
        if share < DOMINANCE_THRESHOLD:
            lever.append("STRUCTURAL")
            reason.append(f"no single cost line exceeds {DOMINANCE_THRESHOLD:.0%} "
                          f"of total cost (largest: {friendly.get(col, col)} at "
                          f"{share:.0%}) - structurally below cost, not "
                          f"lever-fixable. Often a near-zero-activity account "
                          f"whose only real cost is a share of shared servicing "
                          f"overhead, not anything this customer caused.")
            continue
        if col == "credit_cost":
            gap = row["peer_median_apr"] - row["latest_charged_apr"]
            if pd.notna(gap) and gap >= PRICING_GAP_POINTS:
                lever.append("L3")
                reason.append(f"credit-cost dominant ({share:.0%}) and charged "
                              f"APR is {gap:.1f} pts below the {row['Credit Score Band']} "
                              f"peer median - pricing gap, not just exposure")
            else:
                lever.append("L2")
                reason.append(f"credit-cost dominant ({share:.0%}), priced in "
                              f"line with peers - the exposure itself is the issue")
        else:
            lever.append(COST_TO_LEVER.get(col, "STRUCTURAL"))
            reason.append(f"{friendly.get(col, col)} dominant at {share:.0%} of total cost")

    loss["routed_lever"] = lever
    loss["routing_reason"] = reason

    cv = cv.merge(loss[["Masked Customer Number", "routed_lever", "routing_reason"]],
                 on="Masked Customer Number", how="left")
    return SuppressedPopulation(cv, suppressed.suppressed)


def routing_summary(routed: SuppressedPopulation) -> pd.DataFrame:
    require_suppressed(routed)
    loss = routed.frame[routed.frame["is_below_cost"]]
    return (loss.groupby("routed_lever", dropna=False)
           .agg(customers=("Masked Customer Number", "nunique"),
               total_loss=("trailing_12m_net_economic_profit", "sum"))
           .assign(total_loss=lambda d: -d["total_loss"])
           .sort_values("total_loss", ascending=False))
