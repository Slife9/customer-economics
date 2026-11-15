"""One row per card account: the measured trailing-12-cycle inputs of the
unused-line module (the module's per-account file).

Card P&L comes from the engine's card ledger (engine.core.ledger), read only,
never re-derived:
    card_net          net_economic_profit (revenue - reward - funding -
                      credit cost - cost to serve - capital)
    old_capital_cost  capital_cost, the engine's charge on drawn balances
                      under current rules; the module REPLACES it with the
                      brief s.2 capital charge (exposure.py), never adds to it
    credit_cost       measured provision, kept for the baseline (answer 4)
    fixed_cost        cost_to_serve_fixed_allocated (stays when an account
                      leaves; variable contribution = card profit + fixed)
    interchange       interchange_revenue
Everything else is read from the published tables:
    Table4   line, balances, statement balance (Ending Balance + Payment
             Made), paid in full, promotional / BT balance, utilisation
    Table5   spend, active months, last activity; Table5b plan balances
    Table8   PD 12 Month and LGD at the reporting date (never lifetime PD)
    Table9   Behavioral CCF (the measured LEQ for Unassigned, answer 7)
    Table7b  loan balances (aggregate retail exposure, $1M test)
    Table1 / Table6b  segment, deposits; Table29 score history; Table30
             activation; Table3 cards; Table20 automatic increases
The reporting date is the last cycle; "trailing 12" is the 12 cycles ending
there.
"""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np
import pandas as pd

from engine.core.contract import load_portfolio
from engine.core import ledger as LEDGER

K = "Masked Account Number"
C = "Masked Customer Number"
ZERO = 0.005  # a statement balance at or below half a cent is $0


def _opt(data_dir: Path, name: str, **kw) -> pd.DataFrame | None:
    p = data_dir / name
    return pd.read_csv(p, **kw) if p.exists() else None


def account_frame(data_dir: Path | str) -> tuple[pd.DataFrame, dict]:
    data_dir = Path(data_dir)
    portfolio = load_portfolio(data_dir)
    led = LEDGER.build(portfolio)
    L = led["card"]
    cycles = sorted(L["Cycle Month"].unique())
    last12, last = cycles[-12:], cycles[-1]
    c_ix = {c: i for i, c in enumerate(cycles)}
    last_ix = c_ix[last]

    l12 = L[L["Cycle Month"].isin(last12)]
    t = l12.groupby(K).agg(
        customer=(C, "first"), card_net=("net_economic_profit", "sum"),
        old_capital_cost=("capital_cost", "sum"), credit_cost=("credit_cost", "sum"),
        revenue=("revenue", "sum"), reward=("reward_expense", "sum"),
        funding_cost=("funding_cost", "sum"), cost_to_serve=("cost_to_serve", "sum"),
        fixed_cost=("cost_to_serve_fixed_allocated", "sum"), interchange=("interchange_revenue", "sum"))
    bccf = L[L["Cycle Month"] == last].set_index(K)["Behavioral CCF"]
    t["behavioural_ccf"] = bccf.reindex(t.index)

    # ---- Table4: balances, statement, transactor test --------------------
    cyc = portfolio["Table4_Account_Cycle.csv"]
    c12 = cyc[cyc["Cycle Month"].isin(last12)].copy()
    c12["stmt"] = c12["Ending Balance"] + c12["Payment Made"]
    c12["ucl"] = (c12["Credit Limit"] - c12["Ending Balance"]).clip(lower=0)
    c12["zero"] = c12["stmt"] <= ZERO
    c12["paid"] = c12["Paid In Full Indicator"].astype(bool) & ~c12["zero"]
    c12["rev"] = np.where(c12["Purchase Interest"] > 0, c12["Purchase Balance"], 0.0)
    c12["stmt_util"] = c12["stmt"] / c12["Credit Limit"].where(c12["Credit Limit"] > 0)
    g = c12.groupby(K)
    t["cycles_observed_12m"] = g.size()
    t["cycles_zero_statement_12m"] = g["zero"].sum()
    t["cycles_paid_in_full_12m"] = g["paid"].sum()
    t["cycles_not_paid_12m"] = t["cycles_observed_12m"] - t["cycles_zero_statement_12m"] - t["cycles_paid_in_full_12m"]
    t["promotional_balance_12m"] = g["Promotional Balance"].max() > 0
    t["balance_avg_12m"] = g["Ending Balance"].mean()
    t["ucl_avg_12m"] = g["ucl"].mean()
    t["limit_avg_12m"] = g["Credit Limit"].mean()
    t["statement_balance_avg_12m"] = g["stmt"].mean()
    t["revolving_balance_avg_12m"] = g["rev"].mean()
    t["utilisation_avg_12m"] = g["Utilization"].mean()
    t["peak_statement_utilisation_12m"] = g["stmt_util"].max()
    t["peak_statement_balance_12m"] = g["stmt"].max()
    t["months_with_balance_12m"] = (c12["Ending Balance"] > ZERO).groupby(c12[K]).sum()
    latest = cyc[cyc["Cycle Month"] == last].set_index(K)
    t["open_at_reporting_date"] = t.index.isin(latest.index)
    t["charged_off"] = latest["Charged Off Indicator"].reindex(t.index).fillna(True).astype(bool)
    t["days_past_due"] = latest["Days Past Due"].reindex(t.index)
    t["limit_current"] = latest["Credit Limit"].reindex(t.index)
    t["balance_current"] = latest["Ending Balance"].reindex(t.index)
    t["ucl_current"] = (t["limit_current"] - t["balance_current"]).clip(lower=0)
    t["apr"] = latest["Charged Purchase APR"].reindex(t.index) / 100.0

    plan = _opt(data_dir, "Table5b_Installment_Plan_Cycle.csv",
                usecols=[K, "Cycle Month", "Remaining Principal"])
    if plan is not None and len(plan):
        p12 = plan[plan["Cycle Month"].isin(last12) & (plan["Remaining Principal"] > 0)]
        t["installment_plan_12m"] = t.index.isin(p12[K].unique())
    else:
        t["installment_plan_12m"] = False

    # ---- Table5: spend and activity -------------------------------------
    tx = portfolio["Table5_Transaction.csv"]
    x12 = tx[tx["Cycle Month"].isin(last12)]
    purchases = x12[~x12["Cash Advance Indicator"].astype(bool)]
    t["spend_12m"] = purchases.groupby(K)["Transaction Amount"].sum().reindex(t.index).fillna(0.0)
    t["cash_advance_12m"] = x12[x12["Cash Advance Indicator"].astype(bool)].groupby(K)[
        "Transaction Amount"].sum().reindex(t.index).fillna(0.0)
    t["active_months_12m"] = x12.groupby(K)["Cycle Month"].nunique().reindex(t.index).fillna(0).astype(int)
    last_tx = tx.groupby(K)["Cycle Month"].max().map(c_ix)
    t["months_since_last_transaction"] = (last_ix - last_tx.reindex(t.index)).fillna(len(cycles)).astype(int)

    # ---- Table8: annual PD and LGD at the reporting date ------------------
    risk = portfolio["Table8_Risk_Parameters.csv"]
    r_last = risk[risk["Cycle Month"] == last].set_index(K)
    t["pd_12m"] = r_last["PD 12 Month"].reindex(t.index)
    t["lgd"] = r_last["LGD"].reindex(t.index)

    # ---- account age, customer attributes --------------------------------
    open_ix = portfolio["Table2b_Account_Open_Reference.csv"].set_index(K)["Account Open Cycle Index"]
    t["account_age_months"] = (last_ix - open_ix.reindex(t.index) + 1).astype(int)
    cust = portfolio["Table1_Customer.csv"].set_index(C)
    for src, col in [("Segment", "customer_segment"), ("Credit Score", "credit_score"),
                     ("Metro Name", "metro"), ("Hardship Status", "hardship"), ("SCRA Flag", "scra")]:
        t[col] = cust[src].reindex(t["customer"]).to_numpy()
    acct = portfolio["Table2_Card_Account.csv"].set_index(K)
    t["product_tier"] = acct["Product Tier"].reindex(t.index)
    t["annual_fee"] = acct["Annual Fee"].reindex(t.index)

    # ---- non-card relationship ------------------------------------------
    dep, loan = led["deposit_by_customer"], led["loan_by_customer"]
    noncard = (dep[dep["Cycle Month"].isin(last12)].groupby(C)["deposit_net"].sum()
               .add(loan[loan["Cycle Month"].isin(last12)].groupby(C)["loan_net"].sum(), fill_value=0.0))
    cards = t.groupby("customer").size()
    t["noncard_profit"] = (noncard.reindex(t["customer"]).fillna(0.0).to_numpy()
                           / cards.reindex(t["customer"]).to_numpy())
    d6 = portfolio.get("Table6b_Deposit_Account_Cycle.csv")
    dep_bal = (d6[d6["Cycle Month"] == last].groupby(C)["Ending Balance"].sum()
               if d6 is not None and len(d6) else pd.Series(dtype=float))
    t["deposit_balance"] = dep_bal.reindex(t["customer"]).fillna(0.0).to_numpy()

    # ---- aggregate retail exposure per customer ($1M test) ----------------
    l7 = portfolio.get("Table7b_Loan_Account_Cycle.csv")
    loan_bal = (l7[l7["Cycle Month"] == last].groupby(C)["Current Balance"].sum()
                if l7 is not None and len(l7) else pd.Series(dtype=float))
    card_exp = (t["balance_current"].fillna(0) + t["ucl_current"].fillna(0)).groupby(t["customer"]).sum()
    t["retail_exposure_customer"] = (card_exp.reindex(t["customer"]).to_numpy()
                                     + loan_bal.reindex(t["customer"]).fillna(0.0).to_numpy())

    # ---- new tables (Stage 2) and line / card history --------------------
    t29 = _opt(data_dir, "Table29_Score_History.csv", usecols=[K, "Cycle Month", "Bureau Score",
                                                             "Bureau Score Change 6 Months"])
    if t29 is not None:
        s = t29[t29["Cycle Month"] == last].set_index(K)
        t["bureau_score"] = s["Bureau Score"].reindex(t.index)
        t["bureau_score_change_6m"] = s["Bureau Score Change 6 Months"].reindex(t.index)
    else:
        t["bureau_score"] = t["bureau_score_change_6m"] = np.nan
    cards3 = _opt(data_dir, "Table3_Card.csv")
    if cards3 is not None:
        cur = cards3.sort_values("Card Sequence Number").groupby(K).tail(1).set_index(K)
        t["current_card"] = cur["Masked Card Number"].reindex(t.index)
        t["current_card_issue_reason"] = cur["Issue Reason"].reindex(t.index)
        t["months_since_card_issue"] = last_ix - cur["Issue Cycle Index"].reindex(t.index)
        t["card_expiry_index"] = cur["Standard Expiry Cycle Index"].reindex(t.index)
        t["card_expires_within_12m"] = (t["card_expiry_index"] > last_ix) & (t["card_expiry_index"] <= last_ix + 12)
        fraud = cards3[(cards3["Deactivation Reason"] == "FRAUD_COMPROMISE")
                       & (cards3["Deactivation Cycle Index"] >= last_ix - 1)]
        t["fraud_event_recent"] = t.index.isin(fraud[K].unique())
        reissue = cards3[cards3["Issue Reason"] == "REISSUE_EXPIRED_RENEWAL"]["Reissue Cost USD"]
        t["reissue_cost_mean"] = float(reissue.mean()) if len(reissue) else np.nan
    t30 = _opt(data_dir, "Table30_Card_Activation.csv", usecols=["Masked Card Number", "Activation Status"])
    if t30 is not None and "current_card" in t:
        t["current_card_activation"] = t["current_card"].map(t30.set_index("Masked Card Number")["Activation Status"])
    else:
        t["current_card_activation"] = np.nan
    drv = portfolio["Table12_Cost_Drivers.csv"]
    t["digital_sessions_12m"] = drv[drv["Cycle Month"].isin(last12)].groupby(K)["Digital Sessions"].sum() \
        .reindex(t.index).fillna(0).astype(int)
    t20 = portfolio.get("Table20_Limit_Change_Events.csv")
    if t20 is not None and len(t20):
        pi = t20[t20["Cycle Month"].isin(last12) & (t20["Reason Code"] == "PROACTIVE_INCREASE")]
        g20 = pi.assign(add=pi["New Credit Limit"] - pi["Old Credit Limit"]).groupby(K)["add"]
        t["automatic_increases_12m"] = g20.size().reindex(t.index).fillna(0).astype(int)
        t["automatic_increase_amount_12m"] = g20.sum().reindex(t.index).fillna(0.0)
    else:
        t["automatic_increases_12m"], t["automatic_increase_amount_12m"] = 0, 0.0

    open_now = t["open_at_reporting_date"] & ~t["charged_off"]
    meta = {"cycles": len(cycles), "first": cycles[0], "last": last, "trailing": last12,
            "accounts": int(len(t)), "data_dir": str(data_dir),
            "leq_unassigned_measured": float(t.loc[open_now, "behavioural_ccf"].mean()),
            "reporting_cycle_index": last_ix}
    return t, meta


def save_account_frame(t: pd.DataFrame, meta: dict, path: Path | str) -> None:
    """One parquet file with the meta in its schema, so a large portfolio can
    be shipped without its raw tables."""
    import pyarrow as pa
    import pyarrow.parquet as pq
    table = pa.Table.from_pandas(t)
    md = dict(table.schema.metadata or {})
    md[b"unused_line_meta"] = json.dumps(meta, default=str).encode()
    pq.write_table(table.replace_schema_metadata(md), path, compression="zstd")


def load_account_frame(path: Path | str) -> tuple[pd.DataFrame, dict]:
    import pyarrow.parquet as pq
    table = pq.read_table(path)
    meta = json.loads(table.schema.metadata[b"unused_line_meta"])
    return table.to_pandas(), meta
