"""Outputs (concept spec 5.6). The score file is the product; the rest
supports it.

    Score file          customer x month, for the bank's decision systems
    Worklist            customer x action, for operations
    Leakage register    finding with owner and amount, for finance to confirm
    Governance pack      model card, fairness, negative control
    Ledger              account x cycle, for finance to reconcile

INVARIANT: the score file blanks the reason for a suppressed customer. A
suppressed customer still gets a score (they exist, they have an economic
value) but never a reason or an action - that is what keeps a vulnerability
signal out of anything an operator could act on.
"""
from __future__ import annotations
import pandas as pd


def score_file(customer_view: pd.DataFrame, suppressed_customers: pd.DataFrame,
              cycle_month: str) -> pd.DataFrame:
    sf = customer_view[["Masked Customer Number", "cev_score", "cev_band",
                        "trailing_12m_net_economic_profit", "routed_lever",
                        "routing_reason", "products_held",
                        "relationship_covers_card_loss"]].copy()
    sf["Cycle Month"] = cycle_month
    sf["suppressed"] = False

    if len(suppressed_customers):
        supp = suppressed_customers[["Masked Customer Number",
                                     "suppression_reason"]].copy()
        supp["cev_score"] = pd.NA
        supp["cev_band"] = pd.NA
        supp["trailing_12m_net_economic_profit"] = pd.NA
        supp["routed_lever"] = pd.NA
        supp["routing_reason"] = pd.NA
        supp["products_held"] = pd.NA
        supp["relationship_covers_card_loss"] = pd.NA
        supp["Cycle Month"] = cycle_month
        supp["suppressed"] = True
        sf = pd.concat([sf.drop(columns=[]), supp.drop(columns=["suppression_reason"])],
                       ignore_index=True)

    return sf


def leakage_register(worklists: dict[str, pd.DataFrame], sizes: dict[str, "SizeResult"]) -> pd.DataFrame:
    rows = []
    for code, size in sizes.items():
        wl = worklists.get(code)
        rows.append({
            "lever": code,
            "population_count": len(wl) if wl is not None else 0,
            "priced_value_usd": size.priced_value_usd,
            "unpriced_context_usd": size.unpriced_context_usd,
            "basis": size.basis,
            "caveat": size.caveat,
            "owner": {"L1": "Cards Product", "L2": "Credit Risk", "L3": "Pricing",
                     "L4": "Servicing Operations", "L5": "Retention Marketing",
                     "L6": "Acquisition Marketing"}.get(code, "Unassigned"),
        })
    return pd.DataFrame(rows)


def worklist_export(worklists: dict[str, pd.DataFrame]) -> pd.DataFrame:
    frames = []
    for code, wl in worklists.items():
        if wl is None or not len(wl):
            continue
        f = wl.copy()
        f.insert(0, "lever", code)
        frames.append(f)
    if not frames:
        return pd.DataFrame(columns=["lever", "Masked Customer Number", "action", "reason"])
    return pd.concat(frames, ignore_index=True, sort=False)


def governance_pack(fairness_result: dict, gate_report: pd.DataFrame,
                    routing_summary: pd.DataFrame, measured: dict) -> dict:
    return {
        "model_card": {
            "purpose": "Customer Economic Value scoring and lever routing",
            "population": "US retail card customers, suppressing hardship/"
                          "accommodation/SCRA before any scoring or routing",
            "measured_quantities": measured,
        },
        "fairness": {
            "proxy_method": fairness_result["proxy_method"],
            "score_any_failure": fairness_result["score_any_failure"],
            "treatment_any_failure": fairness_result["treatment_any_failure"],
            "score_fairness": fairness_result["score_fairness"].to_dict("records"),
            "treatment_fairness": fairness_result["treatment_fairness"].to_dict("records"),
        },
        "negative_control_gate": gate_report.to_dict("records"),
        "routing_summary": routing_summary.reset_index().to_dict("records"),
    }
