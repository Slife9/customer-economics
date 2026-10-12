"""Panel feature engineering for the ML credit-limit model.

Deliberately decoupled from engine/core/ledger.py and engine/core/customer_view.py:
customer_view.py produces ONE row per customer (a trailing-12m snapshot as of
the latest cycle); training this model needs MANY rows per account (one per
as-of cycle, with trailing features and a forward-looking target). ledger.py
also hard-fails whenever reward-cost-per-point or breakage can't be measured,
or account-cycle counts don't reconcile - the right behavior for the P&L
ledger, wrong for a feature panel that should work on any contract-valid
upload regardless of whether its ledger happens to reconcile. So this module
reads Table4_Account_Cycle.csv and Table1/Table2 DIRECTLY from the raw
portfolio dict, never through ledger.build().

Formulas are ported from the sibling credit-limit-recommendation-system
(CLRS)'s features.py/decisions.py (see SYSTEM_BREAKDOWN.md Parts 4-5),
adapted to CES's own column names. Three deliberate exclusions, not
oversights:

  - Age: CLRS's own MODEL_CARD.md documents removing "customer_age" as a
    prohibited ECOA/Reg B basis after measuring the cost of removal. CES's
    Table1_Customer.csv has a required Age column; it is never passed to
    this model.
  - Charged Purchase APR: engine/run.py's MECHANISM_VARIED_IN_CONTROL["L3"]
    confirms repricing-tracks-risk is an active generator mechanism -
    contemporaneous charged APR may be a proxy for the generator's own
    latent risk state rather than an independent behavioral signal.
    Contractual Purchase APR (set at origination, not revised in response
    to behavior) is kept.
  - Masked Customer/Account Number: travel through for joining and audit,
    never reach the model - the same exclusion every lever in this repo
    already makes.

Only columns in engine/core/contract.py's REQUIRED list are used for the
CORE feature set, so the model behaves identically on any contract-valid
upload. Cash Advance Balance / Payment Made / Minimum Payment Due / Paid In
Full Indicator exist in the generator's output but are NOT contract-required;
used only if present, with a documented fallback otherwise (see
_payment_flags below).

Window arithmetic uses Cycle Index (integer), never Cycle Month string
sorting - an off-by-one here is a leakage bug in a training label, not a
cosmetic display issue.

The instalment block (CLRS Part 4.7) and the behavioural-score / economic-
stress-index features (CLRS Part 4.8) are not replicated: CES's instalment
tables are optional and not required by the data contract, and CES's
generator has no macro/economic-stress series at all. Fabricating either
would violate this repo's own "never invent a number you cannot measure"
rule. Documented in engine/ml/MODEL_CARD.md as a known scope gap.
"""
from __future__ import annotations
from typing import Optional

import numpy as np
import pandas as pd

ACCOUNT_ID = "Masked Account Number"
CUSTOMER_ID = "Masked Customer Number"
CYCLE_IDX = "Cycle Index"

# Every column the trained model is actually allowed to see. Age, Charged
# Purchase APR, and all identifiers are deliberately absent - see module
# docstring. history_cycles and the eligibility flags are used for gating,
# not passed to the estimator.
NUMERIC_FEATURES = [
    "current_limit", "current_balance", "available_credit", "latest_utilization",
    "utilization_3m_avg", "utilization_6m_avg", "utilization_6m_max", "utilization_12m_max",
    "months_utilization_over_70_6m", "months_utilization_over_90_6m",
    "utilization_trend_3m", "balance_6m_avg", "balance_6m_max", "balance_trend_3m",
    "spend_1m", "spend_3m_sum", "spend_6m_sum", "spend_6m_avg", "spend_trend_3m",
    "cash_advance_6m_sum",
    "on_time_payment_rate_6m", "missed_payments_6m", "late_payments_6m",
    "late_fees_6m", "minimum_only_rate_6m",
    "historical_max_dpd", "historical_delinquent_cycles",
    "months_since_last_delinquency", "cure_count", "consecutive_missed_payments",
    "account_tenure_months", "history_cycles",
    "contractual_purchase_apr", "annual_fee", "stated_annual_income",
    "credit_score", "customer_tenure_years",
]
CATEGORICAL_FEATURES = ["segment", "credit_score_band", "product_tier",
                        "account_type", "acquisition_channel"]
MODEL_FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES

TARGET_RISK = "target_risk_30dpd_3m"
TARGET_SPEND = "target_spend_3m"
TARGET_PEAK_BALANCE = "target_peak_balance_3m"


def _trailing(s: pd.Series, acct: pd.Series, window: int, how: str) -> pd.Series:
    g = s.groupby(acct).rolling(window, min_periods=1)
    out = getattr(g, how)()
    return out.reset_index(level=0, drop=True).reindex(s.index)


def _lag(s: pd.Series, acct: pd.Series, periods: int) -> pd.Series:
    return s.groupby(acct).shift(periods)


def _cycles_since_event(flag: pd.Series, acct: pd.Series) -> pd.Series:
    """Row-distance since the most recent True in `flag`, within each
    account, assuming the frame is already sorted by (account, Cycle Index).
    NaN before the first-ever event, 0 on the event row itself."""
    pos = np.arange(len(flag))
    event_pos = np.where(flag.to_numpy(), pos, -1)
    last_event_pos = pd.Series(event_pos, index=flag.index).groupby(acct).cummax()
    since = pos - last_event_pos.to_numpy()
    return pd.Series(np.where(last_event_pos.to_numpy() >= 0, since, np.nan), index=flag.index)


def _payment_flags(cyc: pd.DataFrame) -> pd.DataFrame:
    """Missed-payment / minimum-only-payment flags. Payment Made and
    Minimum Payment Due are generated by this repo's synthesizer but are
    NOT in engine/core/contract.py's REQUIRED list, so a contract-valid
    upload is not guaranteed to have them. When present, use the real
    payment amounts (matching CLRS's own definition). When absent, fall
    back to a Days-Past-Due-derived proxy - documented, not silent."""
    has_payment_data = {"Payment Made", "Minimum Payment Due"}.issubset(cyc.columns)
    out = pd.DataFrame(index=cyc.index)
    if has_payment_data:
        min_due = cyc["Minimum Payment Due"].fillna(0.0)
        paid = cyc["Payment Made"].fillna(0.0)
        out["missed_payment"] = (min_due > 0) & (paid < min_due)
        out["minimum_only"] = (min_due > 0) & (paid <= min_due * 1.10 + 1.0)
    else:
        out["missed_payment"] = cyc["Days Past Due"].fillna(0) > 0
        out["minimum_only"] = False
    out["late_fee"] = cyc["Late Fee Charged"].fillna(0.0) > 0
    out["has_payment_data"] = has_payment_data
    return out


def load_raw_cycles(portfolio) -> pd.DataFrame:
    """Table4_Account_Cycle.csv, sorted by (account, Cycle Index), merged
    with Table2_Card_Account.csv's Annual Fee/Acquisition Channel (both
    contract-required, account-level, not repeated on every cycle row)."""
    cyc = portfolio["Table4_Account_Cycle.csv"].copy()
    cyc = cyc.sort_values([ACCOUNT_ID, CYCLE_IDX]).reset_index(drop=True)

    accounts = portfolio["Table2_Card_Account.csv"][
        [ACCOUNT_ID, "Annual Fee", "Acquisition Channel", "Product Tier"]].copy()
    cyc = cyc.merge(accounts, on=ACCOUNT_ID, how="left", suffixes=("", "_acct"))
    if "Product Tier" not in cyc.columns and "Product Tier_acct" in cyc.columns:
        cyc["Product Tier"] = cyc["Product Tier_acct"]
    elif "Product Tier_acct" in cyc.columns:
        cyc["Product Tier"] = cyc["Product Tier"].fillna(cyc["Product Tier_acct"])

    has_cash_advance_data = "Cash Advance Balance" in cyc.columns
    if not has_cash_advance_data:
        cyc["Cash Advance Balance"] = 0.0
    cyc["has_cash_advance_data"] = has_cash_advance_data

    flags = _payment_flags(cyc)
    cyc = pd.concat([cyc, flags], axis=1)
    return cyc


def load_static(portfolio) -> pd.DataFrame:
    """Table1_Customer.csv's contract-required static attributes. Age is
    read for audit/model-card reporting only - see _exclude_age below."""
    cust = portfolio["Table1_Customer.csv"][
        [CUSTOMER_ID, "Segment", "Stated Annual Income", "Credit Score",
         "Credit Score Band", "Customer Tenure Years", "Age"]].copy()
    return cust


def _open_cycle_index(cyc: pd.DataFrame) -> pd.Series:
    """Each account's first observed Cycle Index, as a proxy for account
    open date - same fallback customer_view.py already uses when
    Table2b_Account_Open_Reference.csv isn't present."""
    return cyc.groupby(ACCOUNT_ID)[CYCLE_IDX].transform("min")


def build_trailing_features(cyc: pd.DataFrame, static: pd.DataFrame) -> pd.DataFrame:
    """One row per (account, cycle), trailing-window features only - the
    golden rule (CLRS SYSTEM_BREAKDOWN.md 4.1): every feature uses the
    current row and earlier rows of THE SAME ACCOUNT, never a later one."""
    acct = cyc[ACCOUNT_ID]
    out = cyc[[CUSTOMER_ID, ACCOUNT_ID, "Cycle Month", CYCLE_IDX]].copy()

    current_balance = cyc["Ending Balance"].fillna(0.0)
    limit = cyc["Credit Limit"]
    out["current_limit"] = limit
    out["current_balance"] = current_balance
    out["available_credit"] = (limit - current_balance).clip(lower=0)
    util = (current_balance / limit.replace(0, np.nan))
    out["latest_utilization"] = util
    out["utilization_3m_avg"] = _trailing(util, acct, 3, "mean")
    out["utilization_6m_avg"] = _trailing(util, acct, 6, "mean")
    out["utilization_6m_max"] = _trailing(util, acct, 6, "max")
    out["utilization_12m_max"] = _trailing(util, acct, 12, "max")
    over_70 = (util >= 0.70).astype(float)
    over_90 = (util >= 0.90).astype(float)
    out["months_utilization_over_70_6m"] = _trailing(over_70, acct, 6, "sum")
    out["months_utilization_over_90_6m"] = _trailing(over_90, acct, 6, "sum")
    out["utilization_trend_3m"] = util - _lag(util, acct, 3)
    out["balance_6m_avg"] = _trailing(current_balance, acct, 6, "mean")
    out["balance_6m_max"] = _trailing(current_balance, acct, 6, "max")
    out["balance_trend_3m"] = current_balance - _lag(current_balance, acct, 3)

    spend = cyc["Purchases Authorized"].fillna(0.0)
    out["spend_1m"] = spend
    out["spend_3m_sum"] = _trailing(spend, acct, 3, "sum")
    out["spend_6m_sum"] = _trailing(spend, acct, 6, "sum")
    out["spend_6m_avg"] = _trailing(spend, acct, 6, "mean")
    out["spend_trend_3m"] = spend - _lag(spend, acct, 3)

    cash_adv = cyc["Cash Advance Balance"].fillna(0.0)
    out["cash_advance_6m_sum"] = _trailing(cash_adv, acct, 6, "sum")

    on_time = (~cyc["missed_payment"]).astype(float)
    out["on_time_payment_rate_6m"] = _trailing(on_time, acct, 6, "mean")
    out["missed_payments_6m"] = _trailing(cyc["missed_payment"].astype(float), acct, 6, "sum")
    out["late_payments_6m"] = out["missed_payments_6m"]  # CES has no separate "late but not missed" state
    out["late_fees_6m"] = _trailing(cyc["late_fee"].astype(float), acct, 6, "sum")
    out["minimum_only_rate_6m"] = _trailing(cyc["minimum_only"].astype(float), acct, 6, "mean")

    dpd = cyc["Days Past Due"].fillna(0)
    delinquent = dpd >= 30
    out["historical_max_dpd"] = dpd.groupby(acct).expanding().max().reset_index(level=0, drop=True)
    out["historical_delinquent_cycles"] = delinquent.astype(float).groupby(acct).cumsum()
    out["months_since_last_delinquency"] = _cycles_since_event(delinquent, acct)
    prev_delinquent = _lag(delinquent, acct, 1).fillna(False)
    cure_event = prev_delinquent & (~delinquent)
    out["cure_count"] = cure_event.astype(float).groupby(acct).cumsum()
    # Vectorized consecutive-streak trick: a block id that increments each
    # time the flag resets to False, then a cumsum of the flag within each
    # (account, block) - avoids an O(n) Python loop on a column that is
    # also computed on the live scoring path, not just offline training.
    missed = cyc["missed_payment"].astype(int)
    block_id = (~cyc["missed_payment"]).groupby(acct).cumsum()
    out["consecutive_missed_payments"] = missed.groupby([acct, block_id]).cumsum()

    open_idx = _open_cycle_index(cyc)
    out["account_tenure_months"] = (cyc[CYCLE_IDX] - open_idx).clip(lower=0)
    out["history_cycles"] = acct.groupby(acct).cumcount() + 1

    out["contractual_purchase_apr"] = cyc["Contractual Purchase APR"]
    out["annual_fee"] = cyc["Annual Fee"]
    out["product_tier"] = cyc["Product Tier"].astype("category")
    out["account_type"] = cyc["Account Type"].astype("category")
    out["acquisition_channel"] = cyc["Acquisition Channel"].astype("category")

    out = out.merge(static, on=CUSTOMER_ID, how="left")
    out = out.rename(columns={"Stated Annual Income": "stated_annual_income",
                              "Credit Score": "credit_score",
                              "Customer Tenure Years": "customer_tenure_years",
                              "Segment": "segment", "Credit Score Band": "credit_score_band"})
    out["segment"] = out["segment"].astype("category")
    out["credit_score_band"] = out["credit_score_band"].astype("category")

    out["is_active"] = ~cyc["Charged Off Indicator"].fillna(False)
    out["is_current"] = dpd == 0
    out["valid_limit"] = limit > 0
    out["normal_score_ready"] = ((out["history_cycles"] >= 6) & out["is_active"]
                                 & out["valid_limit"])
    out["_latest_days_past_due"] = dpd
    out["_has_payment_data"] = cyc["has_payment_data"]
    out["_has_cash_advance_data"] = cyc["has_cash_advance_data"]
    return out


def attach_targets(panel: pd.DataFrame, cyc: pd.DataFrame) -> pd.DataFrame:
    """Forward-looking targets, built by shifting each account's own series
    BACKWARDS (i.e. looking forward in time) by 1/2/3 cycles. Requires all
    3 forward cycles present (target_complete) - a row near the end of an
    account's history (closed, charged off, or simply out of future data)
    is dropped from training rather than labeled on a truncated window."""
    acct = cyc[ACCOUNT_ID]
    dpd = cyc["Days Past Due"].fillna(0)
    spend = cyc["Purchases Authorized"].fillna(0.0)
    balance = cyc["Ending Balance"].fillna(0.0)

    fwd_dpd = [dpd.groupby(acct).shift(-k) for k in (1, 2, 3)]
    fwd_spend = [spend.groupby(acct).shift(-k) for k in (1, 2, 3)]
    fwd_balance = [balance.groupby(acct).shift(-k) for k in (1, 2, 3)]

    target_complete = fwd_dpd[2].notna() & fwd_spend[2].notna() & fwd_balance[2].notna()

    risk = pd.concat(fwd_dpd, axis=1).max(axis=1) >= 30
    spend_sum = pd.concat(fwd_spend, axis=1).sum(axis=1, min_count=3)
    peak_balance = pd.concat(fwd_balance, axis=1).max(axis=1)

    panel = panel.copy()
    panel[TARGET_RISK] = risk.where(target_complete)
    panel[TARGET_SPEND] = spend_sum.where(target_complete)
    panel[TARGET_PEAK_BALANCE] = peak_balance.where(target_complete)
    panel["target_complete"] = target_complete
    # Already-delinquent months are excluded from fitting (CLRS 4.10): the
    # model learns "who BECOMES delinquent from a clean state", not "who
    # IS delinquent" - a materially different, more useful question.
    panel["model_training_eligible"] = (
        panel["normal_score_ready"] & target_complete & (panel["_latest_days_past_due"] < 30))
    return panel


def build_training_panel(portfolio) -> pd.DataFrame:
    """Full panel: every (account, cycle) row, with trailing features and
    forward targets. Used only by the offline training script."""
    cyc = load_raw_cycles(portfolio)
    static = load_static(portfolio)
    panel = build_trailing_features(cyc, static)
    panel = attach_targets(panel, cyc)
    return panel


def build_scoring_frame(portfolio) -> pd.DataFrame:
    """Latest eligible cycle per account only, features (no targets) - the
    fast path used inside the live app. Scoring cost is bounded by the
    number of accounts, not account-months, since only the last row per
    account survives the group-tail filter below.

    Only accounts whose own latest row falls on the PORTFOLIO'S overall
    latest cycle are scored. An account that churned or charged off earlier
    simply stops appearing in Table4_Account_Cycle.csv (see
    generator/synth/cycles.py) - without this check, that account's last
    historical row would be treated as "the current state" and scored as
    if still open, even though `Charged Off Indicator` only catches
    charge-off, not ordinary voluntary closure/attrition. An account that
    is not reporting as of the portfolio's current cycle has nothing to
    recommend a limit change on."""
    cyc = load_raw_cycles(portfolio)
    static = load_static(portfolio)
    panel = build_trailing_features(cyc, static)
    latest_per_account = panel.groupby(ACCOUNT_ID)[CYCLE_IDX].transform("max")
    portfolio_latest = panel[CYCLE_IDX].max()
    is_reporting_now = latest_per_account == portfolio_latest
    return panel[(panel[CYCLE_IDX] == latest_per_account) & is_reporting_now].reset_index(drop=True)
