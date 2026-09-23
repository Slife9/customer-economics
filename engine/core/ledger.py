"""The economic ledger. Account x cycle P&L. Built once; nothing downstream
recomputes revenue or cost (concept spec section 3).

Three quantities are measured from data, never assumed (section 5.2):
  - cost per reward point   = redemption cost / points redeemed, by channel
  - breakage                = points expired / points earned, MATURED vintages only
  - effective interchange   = already booked per transaction (looked up from
                              the rate card at generation time); the ledger
                              reads it, it does not re-derive it

If any of the first two cannot be measured, this module raises. It does not
fall back to an assumption - an earlier prototype had them as sliders, which
was the right way to expose an unknown and the wrong way to ship a product.

Reward expense is ACCRUED as points are earned, at the measured cost per
point, net of measured breakage - not expensed as redemptions happen to be
cashed in that cycle. This is what section 10's validation item "reward
accrual equals measured cost net of measured breakage" is checking.

Cost to serve allocates Tier 1 (pure variable) and Tier 2 (stepped: a fixed
capacity component split evenly across active accounts, plus a marginal
component attributed by each account's own driver volume) only. Tier 3
corporate overhead is never allocated into this ledger (concept spec section
7: "never let corporate overhead into the decision metric").

Capital cost in the P&L uses the REGULATORY capital charge only. The economic
track (behavioral CCF) is carried as a separate diagnostic column for L2
sizing and is never summed into net economic profit - blending the two is
exactly what section 7 forbids.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from .contract import Portfolio, DataContractViolation

REVOLVING_FUNDING_TENOR_MONTHS = 12


class LedgerError(Exception):
    """A measured quantity could not be measured. The engine refuses to run
    rather than substitute an assumption."""


def _measure_cost_per_point(redemption: pd.DataFrame) -> dict[str, float]:
    if not len(redemption):
        raise LedgerError(
            "Table17_Reward_Redemption is empty - cost per reward point "
            "cannot be measured. Refusing to run rather than assume a rate.")
    by_channel = redemption.groupby("Redemption Channel").agg(
        cost=("Redemption Cost USD", "sum"), pts=("Points Redeemed", "sum"))
    by_channel = by_channel[by_channel["pts"] > 0]
    if not len(by_channel):
        raise LedgerError("No channel has redeemed points > 0; cost per "
                          "point cannot be measured.")
    per_channel_rate = (by_channel["cost"] / by_channel["pts"]).to_dict()
    blended = float(redemption["Redemption Cost USD"].sum()
                    / max(redemption["Points Redeemed"].sum(), 1e-9))
    per_channel_rate["_blended"] = blended
    return per_channel_rate


def _measure_breakage(tx_points_by_cycle: pd.DataFrame, expiry: pd.DataFrame,
                      cycles_sorted: list[str], maturity_lookback: int = 24) -> float:
    if not len(cycles_sorted):
        raise LedgerError("no cycles present; breakage cannot be measured.")
    cutoff = cycles_sorted[max(len(cycles_sorted) - maturity_lookback - 1, 0)]
    earned_matured = float(
        tx_points_by_cycle.loc[tx_points_by_cycle["Cycle Month"] <= cutoff,
                               "Points Earned"].sum())
    if earned_matured <= 0:
        raise LedgerError(
            "no matured point vintage (earned more than "
            f"{maturity_lookback} cycles before the window end) - breakage "
            "cannot be measured on this window. Refusing to assume a rate.")
    if not len(expiry) or "Points Earned Cycle Month" not in expiry.columns:
        raise LedgerError(
            "Table19_Reward_Expiry is missing or lacks 'Points Earned Cycle "
            "Month' - breakage cannot be tied to the vintage it belongs to.")
    expired_matured = float(
        expiry.loc[expiry["Points Earned Cycle Month"] <= cutoff,
                  "Points Expired"].sum())
    return expired_matured / earned_matured


def _stepped_cost_lookup(total_volume: float, bands: pd.DataFrame) -> tuple[float, float]:
    """(band_fixed_cost, marginal_rate) for the band `total_volume` falls in."""
    for _, b in bands.iterrows():
        if b["Volume Band From"] <= total_volume < b["Volume Band To"]:
            return float(b["Band Fixed Cost USD Monthly"]), float(b["Marginal Unit Cost USD"])
    last = bands.iloc[-1]
    return float(last["Band Fixed Cost USD Monthly"]), float(last["Marginal Unit Cost USD"])


ACTIVITY_DRIVER_COLUMN = {
    "contact_center_call": "Contact Center Calls",
    "collections_contact": "Collections Contacts",
    "branch_visit": "Branch Visits",
    "fraud_alert": "Fraud Alerts",
    "dispute_case": "Disputes Raised",
    "complaint_case": "Complaints Handled",
    "digital_session": "Digital Sessions",
    "payment_processing": "Payments Processed",
    "statement_paper": "Paper Statements Produced",
    "statement_electronic": "Electronic Statements Produced",
    "card_issuance": "Cards Issued",
}


def _cost_to_serve(drv: pd.DataFrame, pools: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Per (account, cycle) Tier 1 + Tier 2 cost to serve, split into two
    series that get reported separately - collapsing them into one number
    is what made a completely unused card look like it was "costing money to
    serve."

    MARGINAL: the share this specific account actually caused - its own call,
    session, and dispute volume, multiplied by the true per-unit variable
    cost. This is zero for an account with zero activity, correctly.

    FIXED (allocated): an even split of the servicing platform's shared
    capacity cost (the call center exists, the digital platform exists,
    whether or not this one account uses it) across every active account
    that cycle. This is standard activity-based costing - a real bank's
    aggregate P&L legitimately includes it - but it is NOT something a
    lever aimed at one customer can change, because closing or fixing this
    one account does not shrink the shared platform; the same fixed cost
    just gets reallocated across the accounts that remain. Routing (which
    cost dominates THIS customer's own situation) uses marginal only, for
    exactly that reason.
    """
    pools = pools[pools["Allocation Tier"] != "Tier 3"]
    marginal = pd.Series(0.0, index=drv.index)
    fixed_alloc = pd.Series(0.0, index=drv.index)
    n_active_by_cycle = drv.groupby("Cycle Month").size()

    for activity, col in ACTIVITY_DRIVER_COLUMN.items():
        if col not in drv.columns:
            continue
        bands = pools[pools["Activity"] == activity]
        if not len(bands):
            continue
        total_by_cycle = drv.groupby("Cycle Month")[col].sum()
        for cm, total_vol in total_by_cycle.items():
            fixed, marginal_rate = _stepped_cost_lookup(float(total_vol), bands)
            n_active = int(n_active_by_cycle.get(cm, 1))
            mask = drv["Cycle Month"] == cm
            fixed_share = fixed / max(n_active, 1)
            fixed_alloc.loc[mask] += fixed_share
            marginal.loc[mask] += drv.loc[mask, col].astype(float) * marginal_rate
    return marginal, fixed_alloc


def build(portfolio: Portfolio) -> dict[str, pd.DataFrame]:
    """Returns {'card': ..., 'deposit_by_customer': ..., 'loan_by_customer': ...,
    'measured': {...}} - the card ledger is account x cycle; the other two are
    already rolled to customer x cycle since that is all customer_view.py needs
    from them."""
    cyc = portfolio["Table4_Account_Cycle.csv"]
    tx = portfolio["Table5_Transaction.csv"]
    risk = portfolio["Table8_Risk_Parameters.csv"]
    cap = portfolio["Table9_Capital_RWA.csv"]
    drv = portfolio["Table12_Cost_Drivers.csv"]
    pools = portfolio["Table11_Cost_Pools.csv"]
    redemption = portfolio["Table17_Reward_Redemption.csv"]
    expiry = portfolio["Table19_Reward_Expiry.csv"]

    cycles_sorted = sorted(cyc["Cycle Month"].unique())

    # ---- measured quantities (raise if they cannot be measured) -----------
    cost_per_point = _measure_cost_per_point(redemption)
    if "Points Earned" not in tx.columns:
        raise LedgerError(
            "Table5_Transaction.csv has no 'Points Earned' column - reward "
            "accrual cannot be measured.")
    tx_points_by_cycle = tx.groupby("Cycle Month", as_index=False)["Points Earned"].sum()
    breakage_rate = _measure_breakage(tx_points_by_cycle, expiry, cycles_sorted)

    # ---- revenue ------------------------------------------------------------
    interest_rev = (cyc["Purchase Interest"] + cyc["Cash Advance Interest"]
                    + cyc["Promotional Interest"])
    interchange_by_ac = tx.groupby(["Masked Account Number", "Cycle Month"],
                                   as_index=False)["Interchange Earned"].sum()
    points_by_ac = tx.groupby(["Masked Account Number", "Cycle Month"],
                              as_index=False)["Points Earned"].sum()

    key_cols = ["Masked Account Number", "Cycle Month"]
    L = cyc[["Masked Customer Number", "Masked Account Number", "Cycle Month",
            "Cycle Index", "Product Tier", "Credit Limit", "Ending Balance",
            "Purchase Balance", "Utilization", "Purchases Authorized",
            "Days Past Due", "Delinquency Bucket",
            "Account Type", "Hardship Status", "Accommodation Plan", "SCRA Flag",
            "Charged Off Indicator", "Contractual Purchase APR",
            "Charged Purchase APR"]].copy()
    L["interest_revenue"] = interest_rev.to_numpy()
    fee_cols = [c for c in ["Annual Fee Charged", "Late Fee Charged",
                            "Balance Transfer Fee Charged"] if c in cyc.columns]
    L["fee_revenue"] = cyc[fee_cols].sum(axis=1).to_numpy()
    L = L.merge(interchange_by_ac, on=key_cols, how="left")
    L = L.merge(points_by_ac, on=key_cols, how="left")
    L["Interchange Earned"] = L["Interchange Earned"].fillna(0.0)
    L["Points Earned"] = L["Points Earned"].fillna(0.0)
    L = L.rename(columns={"Interchange Earned": "interchange_revenue",
                          "Points Earned": "points_earned"})

    # ---- rewards expense: accrued at measured cost, net of measured breakage
    # cost_per_point is already USD per point (Redemption Cost USD / Points
    # Redeemed straight from Table17) - no further unit conversion needed.
    L["reward_expense"] = (L["points_earned"] * cost_per_point["_blended"]
                           * (1.0 - breakage_rate))

    # ---- funding cost ---------------------------------------------------------
    ftp = portfolio.get("Table10_FTP_Curve.csv")
    if ftp is not None and len(ftp):
        ftp_t = ftp[ftp["Tenor Months"] == REVOLVING_FUNDING_TENOR_MONTHS].set_index(
            "Cycle Month")["Rate Percent"]
        L["funding_rate"] = L["Cycle Month"].map(ftp_t).fillna(ftp_t.mean())
    else:
        L["funding_rate"] = 4.5
    L["funding_cost"] = L["Ending Balance"] * L["funding_rate"] / 100.0 / 12.0

    # ---- credit cost: the MONTHLY PROVISION, not a point-in-time 12-month-
    # forward EL estimate. "Expected Credit Loss 12 Month" is a forward-
    # looking balance-sheet figure recomputed every cycle - summing it across
    # 36 cycles would count the same forward-looking loss roughly 36 times
    # over. The P&L line a bank actually books each month is the CHANGE in
    # the required allowance: the provision.
    risk_m = risk[["Masked Account Number", "Cycle Month", "Monthly Provision",
                   "PD Lifetime", "LGD", "EAD"]]
    L = L.merge(risk_m, on=key_cols, how="left")
    L["credit_cost"] = L["Monthly Provision"].fillna(0.0)

    # ---- capital cost: regulatory only in the P&L; economic kept separate --
    cap_m = cap[["Masked Account Number", "Cycle Month",
                "Regulatory Capital Charge Monthly", "Economic Capital Charge Monthly",
                "Behavioral CCF"]]
    L = L.merge(cap_m, on=key_cols, how="left")
    L["capital_cost"] = L["Regulatory Capital Charge Monthly"].fillna(0.0)
    L["capital_cost_economic_diagnostic_only"] = L[
        "Economic Capital Charge Monthly"].fillna(0.0)

    # ---- cost to serve: Tier 1 + Tier 2 only, split marginal vs. allocated -
    drv2 = drv.copy()
    marginal, fixed_alloc = _cost_to_serve(drv2, pools)
    drv2["_cts_marginal"] = marginal.to_numpy()
    drv2["_cts_fixed"] = fixed_alloc.to_numpy()
    cts = drv2.groupby(key_cols, as_index=False)[["_cts_marginal", "_cts_fixed"]].sum().rename(
        columns={"_cts_marginal": "cost_to_serve_marginal",
                "_cts_fixed": "cost_to_serve_fixed_allocated"})
    L = L.merge(cts, on=key_cols, how="left")
    L["cost_to_serve_marginal"] = L["cost_to_serve_marginal"].fillna(0.0)
    L["cost_to_serve_fixed_allocated"] = L["cost_to_serve_fixed_allocated"].fillna(0.0)
    # Kept as the sum for the P&L total (a real bank's aggregate P&L
    # legitimately includes allocated overhead) - but routing.py deliberately
    # uses cost_to_serve_marginal, not this blended figure, to decide whether
    # servicing cost is a fixable, THIS-customer-caused dominant cause.
    L["cost_to_serve"] = L["cost_to_serve_marginal"] + L["cost_to_serve_fixed_allocated"]

    # ---- net economic profit ------------------------------------------------
    L["revenue"] = L["interest_revenue"] + L["interchange_revenue"] + L["fee_revenue"]
    L["total_cost"] = (L["reward_expense"] + L["funding_cost"] + L["credit_cost"]
                       + L["cost_to_serve"] + L["capital_cost"])
    L["net_economic_profit"] = L["revenue"] - L["total_cost"]

    # ---- reconciliation: assert, do not warn --------------------------------
    _reconcile(L, tx, redemption, cyc)

    # ---- deposit and loan ledgers, rolled to customer x cycle ---------------
    dep_cyc = portfolio.get("Table6b_Deposit_Account_Cycle.csv")
    if dep_cyc is not None and len(dep_cyc):
        dep_cyc = dep_cyc.copy()
        dep_cyc["deposit_net"] = (
            dep_cyc["FTP Credit Value Monthly"] - dep_cyc["Interest Paid"]
            + dep_cyc.get("Maintenance Fee Charged", 0.0)
            + dep_cyc.get("NSF Fee Amount", 0.0))
        deposit_by_customer = dep_cyc.groupby(
            ["Masked Customer Number", "Cycle Month"], as_index=False)["deposit_net"].sum()
    else:
        deposit_by_customer = pd.DataFrame(
            columns=["Masked Customer Number", "Cycle Month", "deposit_net"])

    loan_cyc = portfolio.get("Table7b_Loan_Account_Cycle.csv")
    if loan_cyc is not None and len(loan_cyc):
        lc = loan_cyc.copy()
        lc["loan_funding_cost"] = lc["Current Balance"] * 4.5 / 100.0 / 12.0
        lc["loan_net"] = lc["Interest Accrued"] - lc["loan_funding_cost"]
        loan_by_customer = lc.groupby(
            ["Masked Customer Number", "Cycle Month"], as_index=False)["loan_net"].sum()
    else:
        loan_by_customer = pd.DataFrame(
            columns=["Masked Customer Number", "Cycle Month", "loan_net"])

    measured = {
        "cost_per_point_blended": cost_per_point["_blended"],
        "cost_per_point_by_channel": {k: v for k, v in cost_per_point.items()
                                      if k != "_blended"},
        "breakage_rate_matured_vintages": breakage_rate,
        "loan_note": "loan ledger uses interest revenue less a flat FTP funding "
                     "cost only - no per-loan ECL/capital table exists in this "
                     "dataset, so loan risk/capital cost is NOT represented. "
                     "Treat loan_net as an upper bound, not a full P&L.",
    }
    return {"card": L, "deposit_by_customer": deposit_by_customer,
           "loan_by_customer": loan_by_customer, "measured": measured}


def _reconcile(L: pd.DataFrame, tx: pd.DataFrame, redemption: pd.DataFrame,
              cyc: pd.DataFrame) -> None:
    """INVARIANT: the ledger reconciles to the dollar or the build fails."""
    tol = 1.0  # cents-level float noise across ~150k rows; not a loophole
    ledger_interchange = float(L["interchange_revenue"].sum())
    source_interchange = float(tx["Interchange Earned"].sum())
    if abs(ledger_interchange - source_interchange) > tol:
        raise LedgerError(
            f"Reconciliation failure: ledger interchange {ledger_interchange:,.2f} "
            f"!= Table5 interchange {source_interchange:,.2f}")

    ledger_interest = float(L["interest_revenue"].sum())
    source_interest = float((cyc["Purchase Interest"] + cyc["Cash Advance Interest"]
                             + cyc["Promotional Interest"]).sum())
    if abs(ledger_interest - source_interest) > tol:
        raise LedgerError(
            f"Reconciliation failure: ledger interest {ledger_interest:,.2f} "
            f"!= Table4 interest {source_interest:,.2f}")

    if len(L) != len(cyc):
        raise LedgerError(
            f"Reconciliation failure: ledger has {len(L)} rows, "
            f"Table4_Account_Cycle has {len(cyc)} rows. One ledger row per "
            f"account-cycle is required (validation section 10).")
