"""Product Holding Timeline: customer x product x event.

Assembled from events that already exist in the other product tables - it
adds no new behavior of its own, only a unified view of the cross-sell
sequence: which product a customer opened or closed, and when. This is what
lets tenure and cross-sell sequencing be read directly instead of inferred
by joining half a dozen tables.
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def build(cust: pd.DataFrame, accounts: pd.DataFrame, closed_at: np.ndarray,
         charged_off_at: np.ndarray, attrition_events: pd.DataFrame,
         dep_accounts: pd.DataFrame, loan_accounts: pd.DataFrame,
         loan_cyc: pd.DataFrame, plans: pd.DataFrame, cycles: list[str]) -> pd.DataFrame:
    n_cyc = len(cycles)
    rows = []

    def cyc_month(i):
        return cycles[i] if 0 <= i < n_cyc else ""

    # ---- card account open/close --------------------------------------
    acct_cust = accounts.set_index("Masked Account Number")["Masked Customer Number"]
    open_idx = accounts["Account Open Cycle Index"].to_numpy()
    attr_reason = (attrition_events.drop_duplicates("Masked Account Number", keep="first")
                  .set_index("Masked Account Number")["Closure Reason"]
                  if len(attrition_events) else pd.Series(dtype=object))
    for i, acc in enumerate(accounts["Masked Account Number"].to_numpy()):
        oi = int(open_idx[i])
        rows.append({"Masked Customer Number": acct_cust[acc], "Product Type": "CARD",
                    "Product Reference": acc, "Event Type": "OPEN",
                    "Event Cycle Month": cyc_month(oi),
                    "Predates Observation Window": oi < 0})
        ca = int(closed_at[i])
        if ca < n_cyc:
            reason = attr_reason.get(acc, "CHARGE_OFF" if charged_off_at[i] >= 0 else "CLOSURE")
            rows.append({"Masked Customer Number": acct_cust[acc], "Product Type": "CARD",
                        "Product Reference": acc, "Event Type": "CLOSE",
                        "Event Cycle Month": cyc_month(ca),
                        "Predates Observation Window": False, "Close Reason": reason})

    # ---- deposit account open ------------------------------------------
    if len(dep_accounts):
        for _, r in dep_accounts.iterrows():
            oi = int(r["Deposit Account Open Cycle Index"])
            rows.append({
                "Masked Customer Number": r["Masked Customer Number"],
                "Product Type": f"DEPOSIT_{str(r['Deposit Account Type']).upper()}",
                "Product Reference": r["Masked Deposit Account Number"],
                "Event Type": "OPEN", "Event Cycle Month": cyc_month(oi),
                "Predates Observation Window": oi < 0})

    # ---- loan account open/close ----------------------------------------
    if len(loan_accounts):
        loan_cust = loan_accounts.set_index("Masked Loan Account Number")["Masked Customer Number"]
        loan_open = loan_accounts.set_index("Masked Loan Account Number")["Origination Cycle Index"]
        loan_type = loan_accounts.set_index("Masked Loan Account Number")["Loan Type"]
        for lacc in loan_accounts["Masked Loan Account Number"]:
            oi = int(loan_open[lacc])
            rows.append({
                "Masked Customer Number": loan_cust[lacc],
                "Product Type": f"LOAN_{str(loan_type[lacc]).upper()}",
                "Product Reference": lacc, "Event Type": "OPEN",
                "Event Cycle Month": cyc_month(oi), "Predates Observation Window": oi < 0})
        if len(loan_cyc):
            last = loan_cyc.sort_values("Cycle Month").groupby(
                "Masked Loan Account Number").last()
            paid_off = last[(last["Current Balance"] <= 0.5) & (~last["Charged Off Indicator"])]
            charged_off = last[last["Charged Off Indicator"]]
            for lacc, r in paid_off.iterrows():
                rows.append({"Masked Customer Number": loan_cust[lacc],
                            "Product Type": f"LOAN_{str(loan_type[lacc]).upper()}",
                            "Product Reference": lacc, "Event Type": "CLOSE",
                            "Event Cycle Month": r["Cycle Month"],
                            "Predates Observation Window": False,
                            "Close Reason": "PAID_OFF"})
            for lacc, r in charged_off.iterrows():
                rows.append({"Masked Customer Number": loan_cust[lacc],
                            "Product Type": f"LOAN_{str(loan_type[lacc]).upper()}",
                            "Product Reference": lacc, "Event Type": "CLOSE",
                            "Event Cycle Month": r["Cycle Month"],
                            "Predates Observation Window": False,
                            "Close Reason": "CHARGE_OFF"})

    # ---- installment plan open/close -------------------------------------
    if len(plans):
        plan_cust = accounts.set_index("Masked Account Number")["Masked Customer Number"]
        for _, r in plans.iterrows():
            cust_id = plan_cust.get(r["Masked Account Number"])
            rows.append({"Masked Customer Number": cust_id, "Product Type": "INSTALLMENT_PLAN",
                        "Product Reference": r["Masked Plan Number"], "Event Type": "OPEN",
                        "Event Cycle Month": r["Origination Cycle Month"],
                        "Predates Observation Window": False})
            if r["Status"] in ("completed", "defaulted"):
                rows.append({"Masked Customer Number": cust_id,
                            "Product Type": "INSTALLMENT_PLAN",
                            "Product Reference": r["Masked Plan Number"], "Event Type": "CLOSE",
                            "Event Cycle Month": "", "Predates Observation Window": False,
                            "Close Reason": r["Status"].upper()})

    df = pd.DataFrame(rows)
    for col in ("Close Reason",):
        if col not in df.columns:
            df[col] = ""
    df["Close Reason"] = df["Close Reason"].fillna("")
    return df.sort_values(["Masked Customer Number", "Event Cycle Month"]).reset_index(drop=True)
