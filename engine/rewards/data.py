"""One row per card account: the measured trailing-12-cycle P&L, split into
the reward model's lines, and every input the segment rules need.

P&L lines come from the engine's card ledger (engine.core.ledger), never
re-derived:
    interchange      interchange_revenue
    net_interest     interest_revenue - funding_cost
    annual_fee       Table4 Annual Fee Charged; other_fee = fee_revenue - annual_fee
    reward           reward_expense
    credit_loss      credit_cost
    variable_opex    cost_to_serve_marginal
    capital          capital_cost
    fixed_cost       cost_to_serve_fixed_allocated
    network          0 - the ledger carries no separate network/processing line
plus one line the ledger does not have:
    signup_bonus     Table26 Bonus Paid USD for a bonus earned in the trailing
                     12 cycles. A reward-model cost, labelled as such; it is
                     NOT part of the engine's net economic profit.
Non-card relationship profit (deposit + loan net) is per customer, split
equally across the customer's card accounts.
"""
from __future__ import annotations
from pathlib import Path

import numpy as np
import pandas as pd

from engine.core.contract import load_portfolio
from engine.core import ledger as LEDGER

K = "Masked Account Number"
C = "Masked Customer Number"
PNL_REVENUE = ["interchange", "net_interest", "annual_fee", "other_fee"]
PNL_COST = ["reward", "signup_bonus", "credit_loss", "network", "variable_opex", "capital"]


def account_frame(data_dir: Path | str) -> tuple[pd.DataFrame, dict]:
    data_dir = Path(data_dir)
    portfolio = load_portfolio(data_dir)
    led = LEDGER.build(portfolio)
    L = led["card"]
    cycles = sorted(L["Cycle Month"].unique())
    last12, last = cycles[-12:], cycles[-1]
    n_cyc = len(cycles)

    l12 = L[L["Cycle Month"].isin(last12)]
    t = l12.groupby(K).agg(
        customer=(C, "first"), interest=("interest_revenue", "sum"), funding=("funding_cost", "sum"),
        interchange=("interchange_revenue", "sum"), fee_revenue=("fee_revenue", "sum"),
        reward=("reward_expense", "sum"), credit_loss=("credit_cost", "sum"),
        variable_opex=("cost_to_serve_marginal", "sum"), fixed_cost=("cost_to_serve_fixed_allocated", "sum"),
        capital=("capital_cost", "sum"), engine_nep=("net_economic_profit", "sum"))
    t["net_interest"] = t["interest"] - t["funding"]

    cyc = portfolio["Table4_Account_Cycle.csv"]
    c12 = cyc[cyc["Cycle Month"].isin(last12)]
    t["annual_fee"] = c12.groupby(K)["Annual Fee Charged"].sum().reindex(t.index).fillna(0.0)
    t["other_fee"] = t["fee_revenue"] - t["annual_fee"]
    t["paid_in_full_months"] = c12.groupby(K)["Paid In Full Indicator"].sum().reindex(t.index).fillna(0)
    rb = np.where(c12["Purchase Interest"] > 0, c12["Purchase Balance"], 0.0)
    t["revolving_balance"] = pd.Series(rb, index=c12.index).groupby(c12[K]).mean().reindex(t.index).fillna(0.0)
    latest = cyc[cyc["Cycle Month"] == last].set_index(K)
    t["open_at_last"] = t.index.isin(latest.index)
    t["charged_off"] = latest["Charged Off Indicator"].reindex(t.index).fillna(True).astype(bool)
    t["credit_line"] = latest["Credit Limit"].reindex(t.index).fillna(0.0)
    t["apr"] = latest["Charged Purchase APR"].reindex(t.index) / 100.0

    acct = portfolio["Table2_Card_Account.csv"].set_index(K)
    t["program"] = acct["Reward Program Code"].reindex(t.index)
    t["product_tier"] = acct["Product Tier"].reindex(t.index)
    rules = pd.read_csv(data_dir / "Table16_Reward_Program_Rules.csv").set_index("Program Code")
    nominal = acct["Reward Program Code"].map(rules["Nominal Point Value Cents"]) / 100.0
    bonus_cats = acct["Reward Program Code"].map(rules["Bonus Reward Categories"]).fillna("")

    t25 = pd.read_csv(data_dir / "Table25_MCC_Reference.csv")
    flagged = set(t25.loc[t25["Recommended Reward Treatment"] != "standard", "Merchant Category Code (MCC)"])
    tx = portfolio["Table5_Transaction.csv"]
    purchases = tx[~tx["Cash Advance Indicator"].astype(bool)]
    p12 = purchases[purchases["Cycle Month"].isin(last12)]
    is_bonus_cat = [rc in str(bc).split("|") for rc, bc in
                    zip(p12["Reward Category"], bonus_cats.reindex(p12[K]).to_numpy())]
    g = pd.DataFrame({
        K: p12[K], "spend": p12["Transaction Amount"], "ic_tx": p12["Interchange Earned"],
        "points_value": p12["Points Earned"] * nominal.reindex(p12[K]).to_numpy(),
        "flagged_spend": np.where(p12["Merchant Category Code (MCC)"].isin(flagged), p12["Transaction Amount"], 0.0),
        "bonus_category_spend": np.where(is_bonus_cat, p12["Transaction Amount"], 0.0),
    }).groupby(K).sum()
    t = t.join(g, how="left")
    for col in ["spend", "ic_tx", "points_value", "flagged_spend", "bonus_category_spend"]:
        t[col] = t[col].fillna(0.0)
    t["active_months"] = p12.groupby(K)["Cycle Month"].nunique().reindex(t.index).fillna(0)
    t["earn_rate"] = (t["points_value"] / t["spend"].where(t["spend"] > 0)).fillna(0.0)
    t["effective_interchange"] = t["ic_tx"] / t["spend"].where(t["spend"] > 0)
    t["flagged_spend_share"] = t["flagged_spend"] / t["spend"].where(t["spend"] > 0)
    t["bonus_category_share"] = t["bonus_category_spend"] / t["spend"].where(t["spend"] > 0)

    # Sign-up bonus (Table26) - reward-model cost, not engine NEP.
    t26 = pd.read_csv(data_dir / "Table26_Signup_Bonus.csv").set_index(K)
    t["open_index"] = t26["Account Open Cycle Index"].reindex(t.index)
    t["tenure_months"] = n_cyc - t["open_index"]          # pre-window accounts exceed n_cyc
    t["bonus_paid"] = t26["Bonus Paid USD"].reindex(t.index).fillna(0.0)
    earned = t26["Bonus Earned Cycle Month"].reindex(t.index)
    t["bonus_earned_month"] = earned
    t["signup_bonus"] = np.where(earned.isin(last12), t["bonus_paid"], 0.0)
    t["spend_change_after_window_pct"] = t26["Spend Change After Window Pct"].reindex(t.index)
    window_end = t["open_index"] + 2
    c_ix = {c: i for i, c in enumerate(cycles)}
    last_purchase_ix = purchases.groupby(K)["Cycle Month"].max().map(c_ix).reindex(t.index)
    t["inactive_after_window"] = (t["bonus_paid"] > 0) & ~(last_purchase_ix > window_end).fillna(False)

    t27_path = data_dir / "Table27_Bureau_Inquiries.csv"
    if t27_path.exists():
        t27 = pd.read_csv(t27_path, usecols=[C, "Cycle Month", "Inquiries Trailing 12m"])
        inq = t27[t27["Cycle Month"] == last].set_index(C)["Inquiries Trailing 12m"]
        t["inquiries_12m"] = inq.reindex(t["customer"]).to_numpy()
    else:
        t["inquiries_12m"] = np.nan

    dep, loan = led["deposit_by_customer"], led["loan_by_customer"]
    noncard = (dep[dep["Cycle Month"].isin(last12)].groupby(C)["deposit_net"].sum()
               .add(loan[loan["Cycle Month"].isin(last12)].groupby(C)["loan_net"].sum(), fill_value=0.0))
    cards_per_customer = t.groupby("customer").size()
    t["noncard_profit"] = (noncard.reindex(t["customer"]).fillna(0.0).to_numpy()
                           / cards_per_customer.reindex(t["customer"]).to_numpy())
    dep_tab = portfolio.get("Table6b_Deposit_Account_Cycle.csv")
    dep_bal = (dep_tab[dep_tab["Cycle Month"] == last].groupby(C)["Ending Balance"].sum()
               if dep_tab is not None and len(dep_tab) else pd.Series(dtype=float))
    t["deposit_balance"] = dep_bal.reindex(t["customer"]).fillna(0.0).to_numpy()

    t["network"] = 0.0
    t["weight"] = 1.0
    t = add_totals(t)
    meta = {"cycles": n_cyc, "first": cycles[0], "last": last, "trailing": last12,
            "accounts": int(len(t)), "data_dir": str(data_dir)}
    return t, meta


def add_totals(t: pd.DataFrame) -> pd.DataFrame:
    t["revenue"] = t[PNL_REVENUE].sum(axis=1)
    t["reward_cost_incl_bonus"] = t["reward"] + t["signup_bonus"]
    t["contribution"] = t["revenue"] - t[PNL_COST].sum(axis=1)
    t["fully_loaded_profit"] = t["contribution"] - t["fixed_cost"]
    t["relationship_adjusted_profit"] = t["fully_loaded_profit"] + t["noncard_profit"]
    return t
