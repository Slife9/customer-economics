"""Workbook-reproduction mode: the Unused Line RWA Scenario Model's Calc sheets,
formula for formula, on its own segment inputs (config/workbook_model.json).

Used for the +/-1% reproduction test only; the system's results come from
levers.py on account data. Per segment, in the workbook's order of work:

    closures first; responders = campaign share x response rate
    attrition, spend loss = min(1, multiplier x rate)   (the multiplier scales
                                                         nothing else here)
    cohort A (decreased, retained) = N (1 - closure) decrease share (1 - attrition)
        line = min(old, max(minimum line, balance x (1 + headroom), old (1 - cut)))
        balance, revolving += responders x incremental revolving
        spend = spend (1 - spend loss) + responders x incremental spend
        expected loss with PD x (1 + PD increase)
    cohort B (not decreased) = N (1 - closure) (1 - decrease share), same campaign
    campaign cost = accounts x (share x cost + responders x incentive
                                + responders x incremental revolving x promo rate)
    fixed cost held constant; relationship profit kept on survivors
    capital released = -change in RWA x capital ratio (a one-time stock)
"""
from __future__ import annotations
import pandas as pd

from . import assumptions as A


def _cohort(n, line, bal, rev, spend, und, s, p, ccf, rw, pd_mult, camp):
    revenue = n * (spend * s["interchange_rate"] + rev * (s["apr"] - p["cost_of_funds"])
                   + s["annual_fee"] + s["other_fee"])
    reward = n * spend * s["reward_rate"]
    campaign = n * camp
    ecl = n * s["pd_annual"] * pd_mult * p["lgd"] * (bal + s["leq"] * und)
    var = n * s["variable_cost"]
    rwa = n * (bal + ccf * und) * rw
    capital = rwa * p["capital_ratio"] * p["cost_of_equity"]
    liquidity = n * und * p["lcr_outflow"] * p["negative_carry"]
    contribution = revenue - (reward + campaign + ecl + var + capital + liquidity)
    return {"accounts": n, "credit_line": n * line, "balance": n * bal, "undrawn": n * und,
            "revenue": revenue, "reward": reward, "campaign_cost": campaign, "expected_credit_loss": ecl,
            "rwa": rwa, "capital_charge": capital, "liquidity_cost": liquidity, "contribution": contribution}


def scenario(cfg: dict, name: str, multiplier: float | None = None, risk_weights: dict | None = None,
             ccf: dict | None = None) -> pd.DataFrame:
    """One scenario, by segment and total: baseline, post-change and change
    columns. Default weights and CCF are the workbook's 2023 regime."""
    if name not in A.SCENARIOS:
        raise A.AssumptionsError(f"unknown scenario {name!r}")
    wb = cfg["workbook"]
    p = wb["portfolio"]
    reg = wb["regimes"][cfg["workbook_reproduction"]["original_regime"]]
    rw_by = risk_weights or reg["risk_weight"]
    ccf_by = ccf or reg["ccf"]
    mult = p["behavioural_response_multiplier"] if multiplier is None else multiplier
    lv = wb["levers"][name]
    rows = {}
    for k, s in wb["segments"].items():
        N, line0, bal0, rev0 = s["accounts"], s["credit_line"], s["balance"], s["revolving_balance"]
        und0 = max(0.0, line0 - bal0)
        cut_share, cut, close = lv["decrease_share"][k], lv["decrease_cut"][k], lv["closure_share"][k]
        camp_share = lv["campaign_share"][k]
        resp = camp_share * s["response_rate"]
        attr = min(1.0, mult * s["attrition_after_decrease"])
        sloss = min(1.0, mult * s["spend_loss_after_decrease"])
        camp = camp_share * lv["campaign_cost"][k] + resp * p["incentive_per_responder"] \
            + resp * lv["incremental_revolving"][k] * p["promo_cost_rate"]

        base = _cohort(N, line0, bal0, rev0, s["spend"], und0, s, p, ccf_by[k], rw_by[k], 1.0, 0.0)
        base["fixed_cost"] = N * s["fixed_cost"]

        bal1 = bal0 + resp * lv["incremental_revolving"][k]
        rev1 = rev0 + resp * lv["incremental_revolving"][k]
        nA = N * (1 - close) * cut_share * (1 - attr)
        lineA = min(line0, max(p["minimum_line"], bal1 * (1 + p["headroom_over_balance"]), line0 * (1 - cut)))
        spendA = s["spend"] * (1 - sloss) + resp * lv["incremental_spend"][k]
        a = _cohort(nA, lineA, bal1, rev1, spendA, max(0.0, lineA - bal1), s, p, ccf_by[k], rw_by[k],
                    1 + s["pd_increase_after_decrease"], camp)
        nB = N * (1 - close) * (1 - cut_share)
        spendB = s["spend"] + resp * lv["incremental_spend"][k]
        b = _cohort(nB, line0, bal1, rev1, spendB, max(0.0, line0 - bal1), s, p, ccf_by[k], rw_by[k], 1.0, camp)

        post = {key: a[key] + b[key] for key in a}
        r = {}
        for key in ["accounts", "credit_line", "undrawn", "rwa", "capital_charge", "liquidity_cost",
                    "expected_credit_loss", "revenue"]:
            r[f"baseline_{key}"], r[f"post_{key}"] = base[key], post[key]
        fully0 = base["contribution"] - base["fixed_cost"]
        fully1 = post["contribution"] - base["fixed_cost"]
        r.update({
            "baseline_contribution": base["contribution"], "post_contribution": post["contribution"],
            "baseline_fully_loaded_profit": fully0, "post_fully_loaded_profit": fully1,
            "baseline_relationship_adjusted_profit": fully0 + N * s["relationship_profit"],
            "post_relationship_adjusted_profit": fully1 + post["accounts"] * s["relationship_profit"],
            "accounts_lost": N - post["accounts"],
            "change_in_undrawn": post["undrawn"] - base["undrawn"],
            "change_in_rwa": post["rwa"] - base["rwa"],
            "capital_released": -(post["rwa"] - base["rwa"]) * p["capital_ratio"],
            "change_in_fully_loaded_profit": fully1 - fully0,
        })
        r["change_in_relationship_adjusted_profit"] = (r["post_relationship_adjusted_profit"]
                                                       - r["baseline_relationship_adjusted_profit"])
        rows[k] = r
    df = pd.DataFrame(rows).T
    df.loc["total"] = df.sum()
    return df


def dashboard(cfg: dict, **kw) -> dict:
    """The workbook Dashboard's headline figures for every scenario."""
    out = {}
    for name in A.SCENARIOS:
        t = scenario(cfg, name, **kw).loc["total"]
        out[name] = {"change_in_fully_loaded_profit": float(t["change_in_fully_loaded_profit"]),
                     "change_in_relationship_adjusted_profit": float(t["change_in_relationship_adjusted_profit"]),
                     "capital_released": float(t["capital_released"]), "accounts_lost": float(t["accounts_lost"]),
                     "baseline_fully_loaded_profit": float(t["baseline_fully_loaded_profit"]),
                     "post_fully_loaded_profit": float(t["post_fully_loaded_profit"])}
    return out
