"""Reference implementation of the corrected lever estimates (L1-L6).

Purpose: a small, readable calculator that reproduces the rebuilt figures agreed
in review, so the engine implementation can be checked against it. It works from
the pipeline's customer view and lever worklists (the same tables a results
bundle carries). It is NOT the engine; port the logic into engine/levers/.

Usage (from a pipeline result or a loaded bundle):
    est = estimate_all(cv, worklists, cycles=36, assumptions=load("lever_assumptions.json"))
"""
from __future__ import annotations
import json
import numpy as np
import pandas as pd

K = "Masked Customer Number"
SCEN = ("low", "base", "high")


def load(path):
    with open(path) as f:
        return json.load(f)


def _pick(a, s):
    """Return the scenario value s from a {low, base, high} dict, or a scalar unchanged."""
    return a[s] if isinstance(a, dict) and s in a else a


# ---------------------------------------------------------------- L1
def l1(cv, wl, A):
    a = A["L1"]
    w = wl.merge(cv[[K, "card_net"]], on=K)
    grp_b = w[w["action"] == "REVIEW_REWARD_PROGRAM_COST"]
    opp = w[w["action"] == "PILOT_ALIGNED_ANNUAL_FEE"]
    out = {}
    for s in SCEN:
        fee = a["annual_fee_usd"]
        elig = opp[opp["reward_expense"] >= a["min_reward_multiple_of_fee"] * fee]
        n = len(elig)
        acc, dn, cl = _pick(a["accept_share"], s), _pick(a["downgrade_share"], s), _pick(a["close_share"], s)
        cut, bcut = _pick(a["downgrade_reward_reduction"], s), _pick(a["group1_reward_reduction"], s)
        comp = {
            "fee_revenue": n * acc * fee,
            "downgrade_reward_saving": n * dn * cut * elig["reward_expense"].mean() if n else 0.0,
            "closure_card_profit_lost": -n * cl * elig["card_net"].mean() if n else 0.0,
            "group1_programme_saving": bcut * grp_b["reward_expense"].sum(),
        }
        total = sum(comp.values())
        rel_loss = -n * cl * elig["trailing_12m_net_economic_profit"].mean() if n else 0.0
        out[s] = dict(components=comp, total=total,
                      total_if_closers_leave_bank=total - comp["closure_card_profit_lost"] + rel_loss,
                      offered_fee=n)
    return out


# ---------------------------------------------------------------- L2
def l2(cv, wl, A):
    a = A["L2"]
    pop = wl[[K, "action"]].merge(cv, on=K)
    dec = pop[pop["action"] == "DECREASE_LIMIT"]
    inc = pop[pop["action"] == "INCREASE_LIMIT"]
    dorm = pop[pop["action"] == "REACTIVATION_CAMPAIGN"]
    # Decrease target limit: engine's existing rule (unchanged).
    tgt = np.maximum(dec["peak_utilization_12m"] * dec["current_limit"] * 1.5,
                     dec["trailing_12m_spend"] * 1.10).clip(lower=300)
    cut = (dec["current_limit"] - tgt).clip(lower=0)
    el_lifetime = (cut * dec["pd_lifetime"] * dec["lgd"] * dec["behavioral_ccf"]).sum()

    def rate(df, col):
        ok = (df["avg_undrawn_12m"] > 0) & df[col].notna()
        return (df[col] / df["avg_undrawn_12m"]).where(ok, 0.0)

    liq = (cut * rate(dec, "annual_liquidity_cost")).sum()
    lev = (cut * rate(dec, "leverage_capital_cost")).sum()
    cards = cv[cv["holds_card"]]
    funding_rate = cards["funding_cost"].sum() / (cards["latest_utilization"] * cards["current_limit"]).sum()
    active = cv[cv["holds_card"] & (cv["months_inactive_12m"] == 0)]["card_net"].mean()
    dorm_carry = (dorm["annual_liquidity_cost"].fillna(0) + dorm["leverage_capital_cost"].fillna(0)).sum()
    out = {}
    for s in SCEN:
        impl, life = _pick(a["decrease_implemented"], s), _pick(a["card_life_years"], s)
        use, react, camp = _pick(a["headroom_used"], s), _pick(a["reactivation_rate"], s), _pick(a["campaign_cost_usd"], s)
        new_lim = inc["current_limit"] * a["increase_pct"]
        new_bal = new_lim * use
        interest = (new_bal * inc["latest_charged_apr"] / 100 * (1 - inc["transactor_share_12m"])).sum()
        fund = (new_bal * funding_rate).sum()
        el_add = (new_bal * inc["pd_lifetime"] / life * inc["lgd"]).sum()
        lev_add = ((new_lim - new_bal) * rate(inc, "leverage_capital_cost")).sum()
        comp = {
            "decrease_credit_loss_avoided": el_lifetime * impl / life,
            "decrease_liquidity_avoided": liq * impl,
            "decrease_slr_capital_freed": lev * impl,
            "increase_interest": interest,
            "increase_funding_cost": -fund,
            "increase_extra_credit_loss": -el_add,
            "increase_extra_slr_capital": -lev_add,
            "reactivation_net": len(dorm) * react * (active - dorm["card_net"].mean()) - len(dorm) * camp,
        }
        total = sum(comp.values())
        dr = dorm_carry * (1 - react) * _pick(a["dormant_rightsize_implemented"], s) * _pick(a["dormant_rightsize_reduction"], s)
        out[s] = dict(components=comp, total=total,
                      dormant_rightsizing=dr,
                      total_with_dormant_rightsizing=total + dr)
    return out


# ---------------------------------------------------------------- L3
def l3(cv, wl, A):
    a = A["L3"]
    w = wl.merge(cv, on=K)
    w = w[~w["first_year_protected"].astype(bool)]
    w = w.assign(gap=w["target_apr"] - w["current_apr"],
                 rev=w["latest_purchase_balance"] * (1 - w["transactor_share_12m"]))
    r = w[w["rev"] > 0]                       # target revolvers only
    n = len(r)
    full = (r["gap"] / 100 * r["rev"]).sum()
    out = {}
    for s in SCEN:
        rep, att = _pick(a["year1_balance_repriced"], s), _pick(a["attrition"], s)
        red, cost = _pick(a["balance_reduction_stayers"], s), _pick(a["notice_cost_usd"], s)
        lost = -n * att * r["card_net"].mean()
        ops = -n * cost
        interest_y1 = full * rep * (1 - att) * (1 - red)
        comp = {"extra_interest": interest_y1, "card_profit_lost": lost, "notice_cost": ops}
        out[s] = dict(components=comp, total=sum(comp.values()),
                      steady_state=full * (1 - att) * (1 - red) + lost + ops,
                      total_if_leavers_leave_bank=interest_y1 - n * att * r["trailing_12m_net_economic_profit"].mean() + ops,
                      targeted=n, flagged=len(w))
    return out


# ---------------------------------------------------------------- L4
def l4(cv, wl, A, cycles):
    """Worklist counts cover `cycles` months; the engine itself should window
    drivers to the trailing 12 cycles instead of scaling (see spec)."""
    a = A["L4"]
    calls = wl["avoidable_calls"].sum() * 12 / cycles
    paper = wl["paper_statements"].sum() * 12 / cycles
    c = a["unit_costs"]
    call_saving = c["call"] - c["digital_session"] * a["sessions_per_deflected_call"]
    paper_saving = c["paper_statement"] - c["electronic_statement"]
    out = {}
    for s in SCEN:
        keep = 1 - _pick(a["excluded_share"], s)
        comp = {
            "calls_to_self_service": calls * _pick(a["call_deflection"], s) * keep * call_saving,
            "paper_to_electronic": paper * _pick(a["paper_migration"], s) * keep * paper_saving,
            "outreach_cost_year1": -len(wl) * _pick(a["outreach_cost_usd"], s),
        }
        out[s] = dict(components=comp, total=sum(comp.values()),
                      from_year2=comp["calls_to_self_service"] + comp["paper_to_electronic"],
                      annual_avoidable_calls=calls, annual_paper_statements=paper)
    return out


# ---------------------------------------------------------------- L5
def l5(cv, wl, A):
    a = A["L5"]
    n = len(wl)
    v = wl["value_at_risk_usd"].mean()
    out = {}
    for s in SCEN:
        leave, keep = _pick(a["leave_rate"], s), _pick(a["keep_rate"], s)
        outreach, take, offer = _pick(a["outreach_cost_usd"], s), _pick(a["offer_takeup"], s), _pick(a["offer_cost_usd"], s)
        comp = {"value_kept": n * leave * keep * v, "outreach_cost": -n * outreach, "offer_cost": -n * take * offer}
        cost_per_contact = outreach + take * offer
        out[s] = dict(components=comp, net_conditional=sum(comp.values()),
                      breakeven_keep_rate=cost_per_contact / (leave * v),
                      value_at_risk=wl["value_at_risk_usd"].sum(), customers=n)
    return out


# ---------------------------------------------------------------- L6
def l6(cv, A, cycles):
    a = A["L6"]
    c = cv[cv["acquisition_channel"].notna() & cv["cac_payback_status"].isin(["Recovered", "Not yet recovered"])]
    years = cycles / 12
    g = c.groupby("acquisition_channel").agg(n=(K, "size"), nep=("trailing_12m_net_economic_profit", "mean"),
                                             cac=("acquisition_cost_usd", "mean"), spend=("acquisition_cost_usd", "sum"))
    g["value_per_dollar"] = g["nep"] / g["cac"]
    worst, best = g["value_per_dollar"].idxmin(), g["value_per_dollar"].idxmax()
    spend_yr = g.loc[worst, "spend"] / years
    out = {}
    for s in SCEN:
        shifted = a["budget_shift_share"] * spend_yr
        lost_n = shifted / g.loc[worst, "cac"]
        gained_n = shifted / (g.loc[best, "cac"] * _pick(a["marginal_cac_multiplier"], s))
        q = _pick(a["incremental_quality"], s)
        comp = {"profit_lost_worst_channel": -lost_n * g.loc[worst, "nep"],
                "profit_gained_best_channel": gained_n * g.loc[best, "nep"] * q}
        y1 = sum(comp.values())
        r = 1 - a["annual_attrition"]
        out[s] = dict(components=comp, total=y1,
                      after_n_years=y1 * sum(r ** i for i in range(a["build_years"])),
                      worst=worst, best=best, customers_lost=lost_n, customers_gained=gained_n,
                      breakeven_quality=(g.loc[worst, "nep"] / g.loc[worst, "cac"]) /
                                        (g.loc[best, "nep"] / (g.loc[best, "cac"] * _pick(a["marginal_cac_multiplier"], s))))
    return out


def estimate_all(cv, worklists, cycles, assumptions):
    A = assumptions
    return {
        "L1": l1(cv, worklists["L1"], A),
        "L2": l2(cv, worklists["L2"], A),
        "L3": l3(cv, worklists["L3"], A),
        "L4": l4(cv, worklists["L4"], A, cycles),
        "L5": l5(cv, worklists["L5"], A),
        "L6": l6(cv, A, cycles),
    }
