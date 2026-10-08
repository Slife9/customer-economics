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
import json
from pathlib import Path

import numpy as np
import pandas as pd

_LIQUIDITY_POLICY_PATH = Path(__file__).resolve().parents[1] / "config" / "liquidity_policy.json"

BAND_LABELS = ["Detractor", "Underperforming", "Core", "Valued", "Premier"]
NEUTRAL_BAND_USD = 25.0  # within +/- this, a customer is "Neutral" rather
                        # than Profit/Loss - avoids reading noise around zero
                        # as a hard flip between the two


def _trailing_window(cycles: list[str], months: int = 12) -> list[str]:
    return sorted(cycles)[-months:]


def _compute_cac_payback(ledger: dict, portfolio, cycle_position: dict,
                         earliest_open: pd.DataFrame | None) -> pd.DataFrame:
    """Lifetime payback view: has this customer's cumulative relationship
    profit, since their card was actually acquired, exceeded what it cost to
    acquire them - and if so, how many months did it take?

    Deliberately kept separate from trailing_12m_net_economic_profit (CEV).
    CAC is a one-time cost, not a monthly one; folding it into a trailing-
    window flow metric would require ASSUMING an amortization schedule (how
    many months to spread it over), which is a parameter, not a measurement.
    This instead measures the customer's real cumulative history and reports
    when it actually crossed the acquisition cost - or honestly says it
    hasn't, or that the data can't support an answer.

    A payback figure is only ever reported when the data can actually
    support it:
      - acquisition cost data must exist (Table23_Acquisition.csv with an
        'Acquisition Cost USD' column) - this table is optional, so many
        uploads won't have it
      - the account's open cycle must be a GENUINE observation, not the
        floor the generator applies to accounts that predate the data
        window (see generator/README.md) - an account open since cycle 0 of
        the window could be brand new or could be ten years old with its
        true open date floored to the window start, and there is no way to
        tell those apart from this data. Reporting a confident payback
        number for that account would be a guess dressed as a measurement,
        so it is reported as unknown instead.
    """
    out = portfolio["Table1_Customer.csv"][["Masked Customer Number"]].copy()
    out["acquisition_cost_usd"] = np.nan
    out["acquisition_channel"] = pd.NA
    out["cumulative_net_value_since_acquisition"] = np.nan
    out["cac_payback_months"] = np.nan
    out["cac_payback_status"] = "Unknown - no acquisition cost data"

    acquisition = portfolio.get("Table23_Acquisition.csv")
    if acquisition is None or "Acquisition Cost USD" not in acquisition.columns:
        return out

    accounts = portfolio["Table2_Card_Account.csv"]
    acct_to_cust = accounts.set_index("Masked Account Number")["Masked Customer Number"]
    acq = acquisition.copy()
    acq["Masked Customer Number"] = acq["Masked Account Number"].map(acct_to_cust)
    cac_by_cust = acq.groupby("Masked Customer Number").agg(
        acquisition_cost_usd=("Acquisition Cost USD", "sum"),
        acquisition_channel=("Acquisition Channel", "first")).reset_index()

    out = out.drop(columns=["acquisition_cost_usd", "acquisition_channel"]).merge(
        cac_by_cust, on="Masked Customer Number", how="left")
    has_cac = out["acquisition_cost_usd"].notna()
    out.loc[has_cac, "cac_payback_status"] = "Not yet recovered"

    if earliest_open is None:
        out.loc[has_cac, "cac_payback_status"] = "Unknown - predates observation window"
        return out

    # earliest_open is a Series indexed by Masked Customer Number (the
    # groupby key), not a DataFrame - see its construction above.
    open_position = earliest_open.map(cycle_position)
    genuine_open = open_position[open_position > 0]  # strictly after window start

    relevant = set(genuine_open.index) & set(out.loc[has_cac, "Masked Customer Number"])
    ambiguous = set(out.loc[has_cac, "Masked Customer Number"]) - relevant
    out.loc[out["Masked Customer Number"].isin(ambiguous), "cac_payback_status"] = \
        "Unknown - predates observation window"
    if not relevant:
        return out

    # Full (unwindowed) relationship history, customer x cycle - the same
    # three ledgers trailing_12m_net_economic_profit uses, just not clipped
    # to the trailing window.
    card_full = ledger["card"].groupby(
        ["Masked Customer Number", "Cycle Month"], as_index=False)["net_economic_profit"].sum()
    hist = card_full.merge(ledger["deposit_by_customer"],
                           on=["Masked Customer Number", "Cycle Month"], how="outer")
    hist = hist.merge(ledger["loan_by_customer"],
                      on=["Masked Customer Number", "Cycle Month"], how="outer")
    for c in ["net_economic_profit", "deposit_net", "loan_net"]:
        if c not in hist.columns:
            hist[c] = 0.0
    hist = hist.fillna({"net_economic_profit": 0.0, "deposit_net": 0.0, "loan_net": 0.0})
    hist["relationship_net"] = (hist["net_economic_profit"] + hist["deposit_net"]
                                + hist["loan_net"])
    hist["_pos"] = hist["Cycle Month"].map(cycle_position)
    hist = hist[hist["Masked Customer Number"].isin(relevant)]

    cac_map = out.set_index("Masked Customer Number")["acquisition_cost_usd"]

    def _payback(group: pd.DataFrame) -> pd.Series:
        cust = group.name
        open_pos = genuine_open[cust]
        cac_amt = float(cac_map[cust])
        g = group[group["_pos"] >= open_pos].sort_values("_pos")
        if not len(g):
            return pd.Series({"cumulative_net_value_since_acquisition": np.nan,
                              "cac_payback_months": np.nan,
                              "cac_payback_status": "Not yet recovered"})
        cum = g["relationship_net"].cumsum()
        hit = cum[cum >= cac_amt]
        if len(hit):
            months = float(g["_pos"].loc[hit.index[0]] - open_pos + 1)
            status = "Recovered"
        else:
            months = np.nan
            status = "Not yet recovered"
        return pd.Series({"cumulative_net_value_since_acquisition": float(cum.iloc[-1]) - cac_amt,
                          "cac_payback_months": months, "cac_payback_status": status})

    if len(hist):
        res = hist.groupby("Masked Customer Number").apply(_payback)
        out = out.set_index("Masked Customer Number")
        out.update(res)
        out = out.reset_index()

    return out


def _compute_liquidity_cost(cv: pd.DataFrame) -> pd.DataFrame:
    """The Liquidity Coverage Ratio (LCR) cost of undrawn exposure - a real,
    currently-in-force US rule (12 CFR 249), completely separate from
    capital. A card the bank can cancel at any time correctly costs $0 in
    regulatory CAPITAL (0% CCF, 12 CFR 217.33(b)(1)) - but regulators
    separately assume a share of all unused retail card commitments gets
    drawn in a 30-day stress window, and the bank must hold High Quality
    Liquid Assets ready for that, today, not under some future proposal.
    See engine/config/liquidity_policy.json for the rates and their source.

    Deliberately kept OUT of net_economic_profit and total_cost, for the
    same reason capital_cost_economic_diagnostic_only is kept separate:
    this is a policy assumption (an outflow rate, a yield gap), not a
    number read from generated data. Blending an assumed cost into the one
    figure the whole system measures everything against would be exactly
    the kind of "measured becomes assumed, silently" drift this project
    refuses to do elsewhere - report it, don't bury it in the headline.

    The Segment-based classification is a card-level proxy, not the true
    multi-product exposure check Basel's regulatory-retail test requires -
    see the concentration_threshold_note in the policy file. A customer
    flagged for individual assessment gets None here, never a guessed rate.
    """
    policy = json.loads(_LIQUIDITY_POLICY_PATH.read_text(encoding="utf-8"))
    rate_by_segment = policy["lcr_outflow_rate_by_segment"]
    default_rate = policy["default_outflow_rate"]
    review_segments = set(policy["individual_assessment_segments"])
    threshold = policy["concentration_threshold_usd"]
    yield_gap = policy["lending_yield_annual"] - policy["hqla_yield_annual"]

    out = cv[["Masked Customer Number", "Segment", "avg_undrawn_12m", "current_limit"]].copy()
    segment = out["Segment"].astype(str)

    in_review_list = out["Segment"].isin(review_segments)
    exceeds_threshold = in_review_list & (out["current_limit"] > threshold)
    base_rate = out["Segment"].map(rate_by_segment).fillna(default_rate)
    has_segment_rate = out["Segment"].isin(rate_by_segment.keys())

    out["lcr_outflow_rate"] = base_rate.where(~exceeds_threshold, np.nan)
    out["lcr_classification"] = np.select(
        [exceeds_threshold, in_review_list, has_segment_rate],
        [segment + f" - exceeds the ${threshold:,.0f} concentration threshold on "
                  f"card limit alone; needs individual assessment against the "
                  f"customer's full relationship exposure",
         segment + " - under the concentration threshold (card-limit check only, "
                  "not the full relationship), retail rate applied",
         segment + " - regulatory retail"],
        default=segment + " - no segment-specific rate on file, default retail rate applied")

    out["required_hqla"] = out["avg_undrawn_12m"] * out["lcr_outflow_rate"]
    out["annual_liquidity_cost"] = out["required_hqla"] * yield_gap

    return out[["Masked Customer Number", "lcr_outflow_rate", "lcr_classification",
               "required_hqla", "annual_liquidity_cost"]]


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
    card_w = card[card["Cycle Month"].isin(window)].copy()
    dep_w = dep[dep["Cycle Month"].isin(window)] if len(dep) else dep
    loan_w = loan[loan["Cycle Month"].isin(window)] if len(loan) else loan

    # Undrawn exposure - what the Liquidity Coverage Ratio's stress outflow
    # assumption applies to. Computed here, not read from any table: no
    # generator table provides it, it is this account's own limit minus
    # balance, same grain as everything else in card_w.
    card_w["_undrawn"] = (card_w["Credit Limit"] - card_w["Ending Balance"]).clip(lower=0)

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
        avg_undrawn_12m=("_undrawn", "mean"),
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

    cac = _compute_cac_payback(ledger, portfolio, cycle_position, earliest_open)
    cv = cv.merge(cac, on="Masked Customer Number", how="left")

    liquidity = _compute_liquidity_cost(cv)
    cv = cv.merge(liquidity, on="Masked Customer Number", how="left")

    for c in ["card_net", "card_revenue", "reward_expense", "funding_cost",
             "credit_cost", "cost_to_serve", "cost_to_serve_marginal",
             "cost_to_serve_fixed_allocated", "capital_cost", "n_card_accounts",
             "deposit_net_12m", "loan_net_12m", "annual_fee_total",
             "trailing_12m_spend", "avg_utilization_12m", "peak_utilization_12m",
             "avg_undrawn_12m", "months_transactor_12m", "months_revolver_12m",
             "months_inactive_12m", "months_observed_12m"]:
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
