"""Customer view: roll the ledger up across every product a customer holds.

Not cosmetic (concept spec 5.3). A customer losing money on their card while
their deposit relationship more than covers it is the strongest argument the
product has, and it is invisible in a card-only view. This module is where
that view gets built.

CEV = Customer Economic Value = percentile rank of trailing-12-month net
economic profit, banded into five named tiers. Bands are a communication
device, not the substance - the score is the number that matters.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

BAND_LABELS = ["Detractor", "Underperforming", "Core", "Valued", "Premier"]
NEUTRAL_BAND_USD = 25.0  # within +/- this, a customer is "Neutral" rather
                        # than Profit/Loss - avoids reading noise around zero
                        # as a hard flip between the two


def _trailing_window(cycles: list[str], months: int = 12) -> list[str]:
    return sorted(cycles)[-months:]


def build(ledger: dict, portfolio, trailing_months: int = 12) -> pd.DataFrame:
    portfolio_customers = portfolio["Table1_Customer.csv"]
    accounts = portfolio["Table2_Card_Account.csv"]
    annual_fee_total = accounts.groupby("Masked Customer Number")["Annual Fee"].sum().rename(
        "annual_fee_total")

    open_ref = portfolio.get("Table2b_Account_Open_Reference.csv")
    if open_ref is not None and "Account Open Cycle Month" in open_ref.columns:
        acct_open = accounts[["Masked Customer Number", "Masked Account Number"]].merge(
            open_ref[["Masked Account Number", "Account Open Cycle Month"]],
            on="Masked Account Number", how="left")
        earliest_open = acct_open.groupby("Masked Customer Number")[
            "Account Open Cycle Month"].min().rename("earliest_account_open_month")
    else:
        earliest_open = None

    card = ledger["card"]
    dep = ledger["deposit_by_customer"]
    loan = ledger["loan_by_customer"]

    window = _trailing_window(sorted(card["Cycle Month"].unique()), trailing_months)
    card_w = card[card["Cycle Month"].isin(window)]
    dep_w = dep[dep["Cycle Month"].isin(window)] if len(dep) else dep
    loan_w = loan[loan["Cycle Month"].isin(window)] if len(loan) else loan

    card_by_cust = card_w.groupby("Masked Customer Number").agg(
        product_tier=("Product Tier", "last"),
        card_net=("net_economic_profit", "sum"),
        card_revenue=("revenue", "sum"),
        reward_expense=("reward_expense", "sum"),
        funding_cost=("funding_cost", "sum"),
        credit_cost=("credit_cost", "sum"),
        cost_to_serve=("cost_to_serve", "sum"),
        cost_to_serve_marginal=("cost_to_serve_marginal", "sum"),
        cost_to_serve_fixed_allocated=("cost_to_serve_fixed_allocated", "sum"),
        capital_cost=("capital_cost", "sum"),
        n_card_accounts=("Masked Account Number", "nunique"),
        any_charged_off=("Charged Off Indicator", "any"),
        current_hardship=("Hardship Status", "last"),
        current_accommodation=("Accommodation Plan", "last"),
        current_scra=("SCRA Flag", "last"),
        latest_days_past_due=("Days Past Due", "last"),
        latest_utilization=("Utilization", "last"),
        # A single latest-cycle utilization reading cannot tell a genuinely
        # idle line apart from a disciplined transactor who pays to zero
        # every month - both show 0% at the statement date. Average and peak
        # utilization over the trailing window, plus actual spend volume
        # relative to the limit, are what separate the two.
        avg_utilization_12m=("Utilization", "mean"),
        peak_utilization_12m=("Utilization", "max"),
        trailing_12m_spend=("Purchases Authorized", "sum"),
        months_transactor_12m=("Account Type", lambda s: (s == "Transactor").sum()),
        months_revolver_12m=("Account Type", lambda s: (s == "Revolver").sum()),
        months_inactive_12m=("Account Type", lambda s: (s == "Inactive").sum()),
        months_observed_12m=("Account Type", "size"),
        latest_contractual_apr=("Contractual Purchase APR", "last"),
        latest_charged_apr=("Charged Purchase APR", "last"),
        current_limit=("Credit Limit", "last"),
        latest_purchase_balance=("Purchase Balance", "last"),
        pd_lifetime=("PD Lifetime", "last"),
        lgd=("LGD", "last"),
        behavioral_ccf=("Behavioral CCF", "last"),
        latest_cycle_index=("Cycle Index", "last"),
    ).reset_index()

    all_cycles_sorted = sorted(card["Cycle Month"].unique())
    cycle_position = {c: i for i, c in enumerate(all_cycles_sorted)}
    latest_position = len(all_cycles_sorted) - 1

    dep_by_cust = (dep_w.groupby("Masked Customer Number")["deposit_net"].sum()
                  .reset_index().rename(columns={"deposit_net": "deposit_net_12m"})
                  if len(dep_w) else pd.DataFrame(
                      columns=["Masked Customer Number", "deposit_net_12m"]))
    loan_by_cust = (loan_w.groupby("Masked Customer Number")["loan_net"].sum()
                   .reset_index().rename(columns={"loan_net": "loan_net_12m"})
                   if len(loan_w) else pd.DataFrame(
                       columns=["Masked Customer Number", "loan_net_12m"]))

    cv = portfolio_customers[["Masked Customer Number", "Segment", "Credit Score",
                              "Credit Score Band", "Customer Tenure Years", "State",
                              "Metro Name", "Hardship Status", "Accommodation Plan",
                              "SCRA Flag"]].copy()
    cv = cv.merge(card_by_cust, on="Masked Customer Number", how="left")
    cv = cv.merge(dep_by_cust, on="Masked Customer Number", how="left")
    cv = cv.merge(loan_by_cust, on="Masked Customer Number", how="left")
    cv = cv.merge(annual_fee_total, on="Masked Customer Number", how="left")
    if earliest_open is not None:
        cv = cv.merge(earliest_open, on="Masked Customer Number", how="left")

    for c in ["card_net", "card_revenue", "reward_expense", "funding_cost",
             "credit_cost", "cost_to_serve", "cost_to_serve_marginal",
             "cost_to_serve_fixed_allocated", "capital_cost", "n_card_accounts",
             "deposit_net_12m", "loan_net_12m", "annual_fee_total",
             "trailing_12m_spend", "avg_utilization_12m", "peak_utilization_12m",
             "months_transactor_12m", "months_revolver_12m", "months_inactive_12m",
             "months_observed_12m"]:
        if c in cv.columns:
            cv[c] = cv[c].fillna(0.0)
    cv = cv.rename(columns={"product_tier": "Product Tier"})

    # Account seasoning. NOTE: for accounts that predate the observation
    # window (most of them - see population.py), the generator floors the
    # recorded open month at the window's own start, so this UNDERSTATES
    # true age for long-tenured accounts. That understatement only ever
    # makes the seasoning gate below more conservative, never less - an
    # account this treats as "seasoned enough" really has been observed
    # that long; one it treats as "too new to judge" may in fact be older,
    # which just means a few genuinely-seasoned accounts wait needlessly
    # rather than a new account being mistaken for a seasoned one.
    if earliest_open is not None:
        cv["account_age_months"] = (
            latest_position - cv["earliest_account_open_month"].map(cycle_position)
        ).fillna(0).clip(lower=0)
    else:
        cv["account_age_months"] = cv["Customer Tenure Years"].fillna(0) * 12

    cv["spend_to_limit_ratio"] = np.divide(
        cv["trailing_12m_spend"], cv["current_limit"].replace(0, np.nan)).fillna(0.0)
    cv["transactor_share_12m"] = np.divide(
        cv["months_transactor_12m"], cv["months_observed_12m"].replace(0, np.nan)).fillna(0.0)
    cv["inactive_share_12m"] = np.divide(
        cv["months_inactive_12m"], cv["months_observed_12m"].replace(0, np.nan)).fillna(0.0)
    cv["holds_card"] = cv["n_card_accounts"] > 0
    cv["holds_deposit"] = cv["Masked Customer Number"].isin(
        dep_by_cust["Masked Customer Number"]) if len(dep_by_cust) else False
    cv["holds_loan"] = cv["Masked Customer Number"].isin(
        loan_by_cust["Masked Customer Number"]) if len(loan_by_cust) else False
    cv["products_held"] = (cv["holds_card"].astype(int) + cv["holds_deposit"].astype(int)
                           + cv["holds_loan"].astype(int))

    # This is the number the whole system exists to produce.
    cv["trailing_12m_net_economic_profit"] = (
        cv["card_net"] + cv["deposit_net_12m"] + cv["loan_net_12m"])

    # Card-only view, kept alongside for exactly the comparison section 5.3
    # asks for: how different does this customer look without the relationship?
    cv["card_only_net_economic_profit"] = cv["card_net"]
    cv["relationship_covers_card_loss"] = (
        (cv["card_net"] < 0)
        & (cv["trailing_12m_net_economic_profit"] >= 0))

    cv["cev_score"] = (cv["trailing_12m_net_economic_profit"]
                       .rank(pct=True, method="average") * 100).round(1)
    cv["cev_band"] = pd.cut(cv["cev_score"], bins=[0, 20, 40, 60, 80, 100.01],
                            labels=BAND_LABELS, right=False, include_lowest=True)

    cv["is_below_cost"] = cv["trailing_12m_net_economic_profit"] < 0

    cv["net_band"] = np.select(
        [cv["trailing_12m_net_economic_profit"] > NEUTRAL_BAND_USD,
        cv["trailing_12m_net_economic_profit"] < -NEUTRAL_BAND_USD],
        ["Profit", "Loss"], default="Neutral")

    return cv
