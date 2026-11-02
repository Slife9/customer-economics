"""The Reward Profitability Scenario Model v2's formulas (Calc_* sheets),
applied per account.

Each account carries its measured baseline P&L lines (data.py) and a
`weight` (1 for a real account). For the account's segment the scenario's
levers and the segment's response sensitivities give, exactly as the workbook:

  new earn          = max(0, earn - cut)
  perceived cut     = 1 - (new/earn)(1 - excluded)(1 - cap)(1 - steering x pass-through)
  attrition         = min(max, multiplier x (cut/10% x a10 + fee/$100 x a_fee))
  spend change      = max(-1, multiplier x cut/10% x s10)     (retained accounts)
  rewards retained  = (1 - migrated)(1 - attrition)
  migrated retained = migrated (1 - product-change attrition)

Post-change lines are the baseline lines scaled the way the workbook scales
them (reward cost by spend x earn ratio x exclusions x cap x steering x
merchant funding; interest by the balance uplift less the promo give-up;
capital by the balance and undrawn line; and so on). Migrated accounts earn
non-rewards interchange on reduced spend and carry no reward or bonus cost.
Fixed cost is held constant: closing accounts removes only variable cost.

All figures are EXPECTED values under assumptions (pilot required), not a
forecast for any one customer. Segment 'unassigned' gets no lever (the
workbook routes it to credit / operations levers instead).
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from engine.rewards.assumptions import LEVERS, SEGMENTS

POST_LINES = ["interchange", "net_interest", "promo_cost", "annual_fee", "other_fee", "reward",
              "signup_bonus", "credit_loss", "network", "variable_opex", "capital"]


def _per_account(t: pd.DataFrame, mapping: dict) -> np.ndarray:
    return t["segment"].map(mapping).fillna(0.0).astype(float).to_numpy()


def apply(t: pd.DataFrame, cfg: dict, levers: dict, multiplier: float | None = None) -> pd.DataFrame:
    """Post-change expected P&L per screened account. `levers` is
    {lever: {segment: value}} (assumptions.levers_for or an edited copy)."""
    s = t[t["segment"].notna()].copy()
    pf = cfg["portfolio"]
    beh = cfg["behaviour"]
    m = pf["behavioural_response_multiplier"] if multiplier is None else multiplier
    L = {k: _per_account(s, levers[k]) for k in LEVERS}
    a10 = _per_account(s, beh["attrition_per_10pct_value_cut"])
    afee = _per_account(s, beh["attrition_per_100usd_fee_increase"])
    s10 = _per_account(s, beh["spend_change_per_10pct_value_cut"])

    earn = s["earn_rate"].to_numpy(dtype=float)
    new_earn = np.maximum(0.0, earn - L["earn_rate_reduction_pp"])
    ratio = np.divide(new_earn, earn, out=np.ones_like(earn), where=earn > 0)
    cut = np.where(earn > 0, 1 - ratio * (1 - L["excluded_spend_share"]) * (1 - L["bonus_category_cap_cut"])
                   * (1 - L["redemption_steering_cut"] * pf["redemption_steering_pass_through"]), 0.0)
    att = np.minimum(pf["max_attrition"], m * (cut / 0.1 * a10 + L["annual_fee_increase_usd"] / 100.0 * afee))
    dsp = np.maximum(-1.0, m * (cut / 0.1) * s10)
    mig = L["product_change_share"]
    rr = (1 - mig) * (1 - att)
    mm = mig * (1 - pf["product_change_attrition"])
    u = L["revolving_balance_uplift"]

    bal, line = s["revolving_balance"].to_numpy(dtype=float), s["credit_line"].to_numpy(dtype=float)
    ccf = pf["undrawn_ccf"]
    exposure0 = bal + ccf * np.maximum(0.0, line - bal)
    exposure1 = bal * (1 + u) + ccf * np.maximum(0.0, line - bal * (1 + u))
    cap_factor = np.divide(exposure1, exposure0, out=np.ones_like(exposure0), where=exposure0 > 0)
    reward_factor = ratio * (1 - L["excluded_spend_share"]) * (1 - L["bonus_category_cap_cut"]) \
        * (1 - L["redemption_steering_cut"]) * (1 - L["merchant_funded_share"])

    b = {k: s[k].to_numpy(dtype=float) for k in ["spend", "interchange", "net_interest", "annual_fee",
                                                 "other_fee", "reward", "signup_bonus", "credit_loss",
                                                 "network", "variable_opex", "capital", "fixed_cost",
                                                 "noncard_profit"]}
    w = s["weight"].to_numpy(dtype=float)
    post = pd.DataFrame(index=s.index)
    # rewards accounts retained
    post["interchange"] = b["interchange"] * rr * (1 + dsp)
    post["net_interest"] = b["net_interest"] * rr * (1 + u)
    post["promo_cost"] = bal * u * pf["promo_cost_on_incremental_balance"] * rr
    post["annual_fee"] = (b["annual_fee"] + L["annual_fee_increase_usd"] * w) * rr
    post["other_fee"] = b["other_fee"] * rr
    post["reward"] = b["reward"] * rr * (1 + dsp) * reward_factor
    post["signup_bonus"] = b["signup_bonus"] * rr * (1 - L["signup_bonus_cost_cut"])
    post["credit_loss"] = b["credit_loss"] * rr * (1 + u)
    post["network"] = b["network"] * rr * (1 + dsp)
    post["variable_opex"] = b["variable_opex"] * rr
    post["capital"] = b["capital"] * rr * cap_factor
    contrib_r = (post["interchange"] + post["net_interest"] - post["promo_cost"] + post["annual_fee"]
                 + post["other_fee"] - post["reward"] - post["signup_bonus"] - post["credit_loss"]
                 - post["network"] - post["variable_opex"] - post["capital"])
    # accounts migrated to a non-rewards card
    spend_mig = b["spend"] * (1 - pf["product_change_spend_reduction"])
    network_rate = np.divide(b["network"], b["spend"], out=np.zeros_like(b["spend"]), where=b["spend"] > 0)
    contrib_m = mm * (spend_mig * pf["non_rewards_interchange_rate"] + b["net_interest"]
                      + pf["non_rewards_annual_fee_usd"] * w + b["other_fee"] - b["credit_loss"]
                      - spend_mig * network_rate - b["variable_opex"] - b["capital"])
    post["migrated_contribution"] = contrib_m
    post["contribution"] = contrib_r + contrib_m
    post["fixed_cost"] = b["fixed_cost"]
    post["fully_loaded_profit"] = post["contribution"] - post["fixed_cost"]
    post["noncard_profit"] = b["noncard_profit"] * (rr + mm)
    post["relationship_adjusted_profit"] = post["fully_loaded_profit"] + post["noncard_profit"]
    post["revenue"] = (post["interchange"] + post["net_interest"] + post["annual_fee"] + post["other_fee"]
                       + mm * (spend_mig * pf["non_rewards_interchange_rate"] + b["net_interest"]
                               + pf["non_rewards_annual_fee_usd"] * w + b["other_fee"]))
    post["reward_cost"] = post["reward"]
    post["accounts_retained"] = w * (rr + mm)
    post["accounts_lost"] = w - post["accounts_retained"]
    post["perceived_value_cut"] = cut
    post["attrition"] = att
    post["spend_change"] = dsp
    post["segment"] = s["segment"]
    post["weight"] = w
    return post


def summary(t: pd.DataFrame, post: pd.DataFrame) -> pd.DataFrame:
    """By segment and total: the workbook's dashboard rows, baseline vs post."""
    s = t[t["segment"].notna()]
    rows = []
    groups = [(seg, s.index[s["segment"] == seg]) for seg in SEGMENTS + ["unassigned"]]
    groups.append(("total", s.index))
    for seg, idx in groups:
        b, p = s.loc[idx], post.loc[idx]
        accounts = b["weight"].sum()
        rows.append({
            "segment": seg, "accounts": accounts,
            "baseline_revenue": b["revenue"].sum(), "post_revenue": p["revenue"].sum(),
            "baseline_reward_cost": b["reward"].sum(), "post_reward_cost": p["reward_cost"].sum(),
            "baseline_signup_bonus": b["signup_bonus"].sum(), "post_signup_bonus": p["signup_bonus"].sum(),
            "baseline_contribution": b["contribution"].sum(), "post_contribution": p["contribution"].sum(),
            "baseline_fully_loaded_profit": b["fully_loaded_profit"].sum(),
            "post_fully_loaded_profit": p["fully_loaded_profit"].sum(),
            "baseline_relationship_adjusted_profit": b["relationship_adjusted_profit"].sum(),
            "post_relationship_adjusted_profit": p["relationship_adjusted_profit"].sum(),
            "accounts_lost": p["accounts_lost"].sum(),
            "attrition_rate": p["accounts_lost"].sum() / accounts if accounts else 0.0,
            "perceived_value_cut": (p["perceived_value_cut"] * p["weight"]).sum() / accounts if accounts else 0.0,
        })
    out = pd.DataFrame(rows).set_index("segment")
    out["change_fully_loaded_profit"] = out["post_fully_loaded_profit"] - out["baseline_fully_loaded_profit"]
    out["change_relationship_adjusted_profit"] = (out["post_relationship_adjusted_profit"]
                                                  - out["baseline_relationship_adjusted_profit"])
    out["baseline_reward_share_of_revenue"] = out["baseline_reward_cost"] / out["baseline_revenue"].where(out["baseline_revenue"] != 0)
    out["post_reward_share_of_revenue"] = out["post_reward_cost"] / out["post_revenue"].where(out["post_revenue"] != 0)
    out["baseline_profit_per_account"] = out["baseline_fully_loaded_profit"] / out["accounts"].where(out["accounts"] > 0)
    out["post_profit_per_account"] = out["post_fully_loaded_profit"] / (out["accounts"] - out["accounts_lost"]).where(out["accounts"] > 0)
    return out


def excel_reference_accounts(cfg: dict) -> pd.DataFrame:
    """The workbook's five segments as five weighted 'accounts', with every
    baseline line computed exactly as the workbook's Calc rows 7-23 do.
    Running apply() on these must reproduce the workbook's totals."""
    ref, pf = cfg["excel_reference_baseline"], cfg["portfolio"]
    rows = []
    for seg in SEGMENTS:
        n = ref["accounts"][seg]
        spend, bal, line = ref["annual_spend_usd"][seg], ref["revolving_balance_usd"][seg], ref["credit_line_usd"][seg]
        earn = ref["earn_rate"][seg]
        cap = (bal + pf["undrawn_ccf"] * max(0.0, line - bal)) * pf["capital_ratio"] * pf["cost_of_equity"]
        rows.append({
            "segment": seg, "weight": n, "earn_rate": earn,
            "spend": n * spend, "interchange": n * spend * ref["interchange_rate"][seg],
            "net_interest": n * bal * (ref["apr"][seg] - pf["cost_of_funds"]),
            "annual_fee": n * ref["annual_fee_usd"][seg], "other_fee": n * ref["other_fee_income_usd"][seg],
            "reward": n * spend * earn * ref["redemption_rate"][seg] * ref["cost_per_dollar_redeemed"][seg],
            "signup_bonus": n * ref["signup_bonus_cost_usd"][seg],
            "credit_loss": n * bal * ref["credit_loss_rate"][seg],
            "network": n * spend * ref["network_cost_rate"],
            "variable_opex": n * ref["variable_opex_usd"][seg], "capital": n * cap,
            "fixed_cost": n * ref["fixed_cost_usd"][seg], "noncard_profit": n * ref["noncard_profit_usd"][seg],
            # per-account quantities the capital and promo lines use, scaled by weight
            "revolving_balance": n * bal, "credit_line": n * line,
        })
    t = pd.DataFrame(rows).set_index("segment", drop=False)
    t.index.name = None
    from engine.rewards.data import add_totals
    return add_totals(t)
