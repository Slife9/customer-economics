"""Account exposure and cost layer (brief s.2): the regulatory settings applied
per account.

Per card account, from the per-account file (data.py) and the assumptions:

    UCL                  max(limit - balance, 0); 12-month average for cost,
                         current for actions
    risk weight          transactor test (answer 5), $1M aggregate test
    exposure E           balance + CCF x UCL;  RWA = E x RW
    capital              RWA x capital ratio (a stock, never an annual saving)
    capital cost         capital x cost of equity (RWA x 1.26% a year)
    liquidity cost       UCL x LCR outflow x negative carry (when it applies)
    drawdown loss        annual PD x LGD x LEQ x UCL (never lifetime PD); a
                         missing PD takes the segment average (B1); LEQ is
                         the account's Behavioral CCF or the workbook's
                         segment LEQ (config drawdown_risk.leq_source, B2)

and three separate cost columns, never mixed under one label (answer 3):

    carrying cost        capital cost on the unused part + liquidity cost
    drawdown loss        beside it
    total unused-line    carrying cost + drawdown loss

The module's card profit, "card profit under the assumed capital rules"
(answer 4, B4), starts from the engine's card_net, REPLACES the old capital
charge with the new one and subtracts the liquidity cost; the measured credit
cost stays, and drawdown loss is shown beside the profit, never deducted from
it. With costs.fixed_cost_basis = workbook_segment (B5) the engine's fixed
cost allocation is swapped for the workbook's. reconciliation() shows each
step from the main engine's card profit.

Balances are Table4 Ending Balance: after the month's payment (the
reporting-date balance). Right for regulatory exposure; it slightly
overstates the unused line of a pay-in-full customer (B7).
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from . import assumptions as A

RW_BASIS_LABELS = {
    "transactor": "Transactor: paid in full (or nothing due) every cycle for 12 months",
    "dormant_zero_balance": "Dormant: $0 statement in all 12 cycles (no repayment history)",
    "plan_or_promotional_balance": "Installment plan, promotional or balance-transfer balance in 12 months",
    "not_paid_in_full": "At least one cycle with a balance not paid in full",
    "short_history": "Less than 12 months of history",
    "non_qualifying_retail": "Aggregate retail exposure above the regulatory retail limit",
}

# What each output column is, for labelling on every page (brief s.8).
VALUE_TYPE = {
    "measured": ["card_net", "old_capital_cost", "credit_cost", "balance", "ucl", "pd_12m", "pd_used", "lgd",
                 "noncard_profit", "leq_measured", "fixed_cost_engine"],
    "regulatory_assumed": ["ccf", "rw", "rw_basis", "exposure", "exposure_unused", "rwa", "rwa_unused",
                           "rwa_drawn", "hqla"],
    "business_assumption": ["capital_required", "capital_required_unused", "capital_cost",
                            "capital_cost_unused", "capital_cost_drawn", "liquidity_cost",
                            "carrying_cost"],
    "workbook_estimate": ["leq", "leq_workbook", "drawdown_el", "total_unused_line_cost"],
    "derived": ["card_profit", "relationship_adjusted_profit"],
}


def risk_weights(acc: pd.DataFrame, cfg: dict) -> tuple[pd.Series, pd.Series]:
    """Per-account risk weight and the reason for it (answer 5)."""
    cap, tt = cfg["capital"], cfg["transactor_test"]
    need = cap["transactor_months_required"]
    observed = acc["cycles_observed_12m"].fillna(0)
    short = (observed < need) | (acc["account_age_months"].fillna(0) < need) \
        if tt["short_history_is_non_transactor"] else pd.Series(False, index=acc.index)
    plan = (acc["installment_plan_12m"].astype(bool) | acc["promotional_balance_12m"].astype(bool)) \
        if (tt["plan_promotional_or_bt_balance_disqualifies"]
            and cap["installment_balance_disqualifies_transactor"]) else pd.Series(False, index=acc.index)
    all_zero = (acc["cycles_zero_statement_12m"] >= observed) & (observed > 0) \
        if tt["all_cycles_zero_is_dormant"] else pd.Series(False, index=acc.index)
    failed = acc["cycles_not_paid_12m"] > 0
    if not tt["zero_statement_cycle_passes"]:
        failed = failed | (acc["cycles_zero_statement_12m"] > 0)
    nonq = acc["retail_exposure_customer"] > cap["regulatory_retail_aggregate_limit_usd"]

    basis = np.select(
        [nonq, short, plan, all_zero, failed],
        ["non_qualifying_retail", "short_history", "plan_or_promotional_balance",
         "dormant_zero_balance", "not_paid_in_full"], default="transactor")
    rw = np.select(
        [basis == "non_qualifying_retail", basis == "dormant_zero_balance", basis == "transactor"],
        [cap["risk_weight_non_qualifying_retail"], cap["risk_weight_dormant_zero_balance"],
         cap["risk_weight_transactor"]], default=cap["risk_weight_non_transactor"])
    return pd.Series(rw, index=acc.index, name="rw"), pd.Series(basis, index=acc.index, name="rw_basis")


def pd_used(acc: pd.DataFrame, cfg: dict) -> tuple[pd.Series, pd.Series]:
    """B1: the annual PD used for drawdown loss, and whether it was imputed.
    A missing PD takes the average PD of the account's rule segment (accounts
    with a PD), falling back to the portfolio average: never zero."""
    if cfg["drawdown_risk"]["missing_pd"] != "segment_average":
        raise ValueError("only segment_average imputation is supported")
    p12 = acc["pd_12m"].astype(float)
    portfolio = float(p12.mean())
    if "rule_segment" in acc:
        fill = acc["rule_segment"].map(p12.groupby(acc["rule_segment"]).mean()).fillna(portfolio)
    else:
        fill = pd.Series(portfolio, index=acc.index)
    return p12.fillna(fill), p12.isna()


def leq_columns(acc: pd.DataFrame, cfg: dict, leq_unassigned: float) -> pd.DataFrame:
    """B2: the account's measured LEQ (Table9 Behavioral CCF at the reporting
    date), the workbook's segment LEQ (Unassigned: the measured portfolio
    mean, answer 7), the one used under drawdown_risk.leq_source, and where
    it came from."""
    wb = cfg["drawdown_risk"]["leq_by_segment"]
    seg = acc["rule_segment"] if "rule_segment" in acc else pd.Series("unassigned", index=acc.index)
    in_wb = seg.isin(list(wb))
    workbook = seg.map(wb).astype(float).fillna(leq_unassigned)
    measured = acc["behavioural_ccf"].astype(float)
    wb_src = pd.Series(np.where(in_wb, "workbook segment LEQ", "measured portfolio Behavioral CCF (Unassigned)"),
                       index=acc.index)
    if cfg["drawdown_risk"]["leq_source"] == "measured_account":
        leq = measured.fillna(workbook)
        src = wb_src.where(measured.isna(), "measured account Behavioral CCF (Table9)")
        src = src.where(measured.notna(), src + " - no account value")
    else:
        leq, src = workbook, wb_src
    return pd.DataFrame({"leq_measured": measured, "leq_workbook": workbook, "leq": leq, "leq_source": src},
                        index=acc.index)


def fixed_costs(acc: pd.DataFrame, cfg: dict) -> tuple[pd.Series, pd.Series]:
    """B5: (engine allocation, fixed cost used) per account a year. The
    workbook basis takes the workbook's fixed cost by segment; Unassigned
    (and an account without a segment) the workbook segments' fixed cost
    weighted by their account counts."""
    engine = (acc["fixed_cost_engine"] if "fixed_cost_engine" in acc else acc["fixed_cost"]).astype(float)
    if cfg["costs"]["fixed_cost_basis"] == "engine_allocated":
        return engine, engine
    wb = cfg["workbook"]["segments"]
    avg = sum(v["accounts"] * v["fixed_cost"] for v in wb.values()) / sum(v["accounts"] for v in wb.values())
    seg = acc["rule_segment"] if "rule_segment" in acc else pd.Series("", index=acc.index)
    return engine, seg.map({k: v["fixed_cost"] for k, v in wb.items()}).astype(float).fillna(avg)


def _core(balance, ucl, rw, pd12, lgd, leq, cfg: dict) -> dict:
    """The s.2 formulas on arrays (or scalars) - the single place they live."""
    cap, liq = cfg["capital"], cfg["liquidity"]
    ccf = cap["ccf_unused_card_lines"]
    rate = A.annual_capital_cost_rate(cfg)
    outflow = liq["lcr_outflow_unused_card_lines"] if A.liquidity_applies(cfg) else 0.0
    exposure_unused = ccf * ucl
    exposure = balance + exposure_unused
    rwa, rwa_unused = exposure * rw, exposure_unused * rw
    hqla = ucl * outflow
    out = {
        "ccf": ccf, "exposure": exposure, "exposure_unused": exposure_unused,
        "rwa": rwa, "rwa_unused": rwa_unused, "rwa_drawn": rwa - rwa_unused,
        "capital_required": rwa * cap["capital_ratio"],
        "capital_required_unused": rwa_unused * cap["capital_ratio"],
        "capital_cost": rwa * rate, "capital_cost_unused": rwa_unused * rate,
        "capital_cost_drawn": (rwa - rwa_unused) * rate,
        "hqla": hqla, "liquidity_cost": hqla * liq["negative_carry"],
        "drawdown_el": pd12 * lgd * leq * ucl,
    }
    out["carrying_cost"] = out["capital_cost_unused"] + out["liquidity_cost"]
    out["total_unused_line_cost"] = out["carrying_cost"] + out["drawdown_el"]
    return out


def account_costs(acc: pd.DataFrame, cfg: dict, basis: str = "average",
                  leq_unassigned: float | None = None) -> pd.DataFrame:
    """A copy of `acc` with the s.2 exposure, cost and profit columns.

    basis "average" (cost: 12-month average balance and UCL) or "current"
    (actions: the reporting-date line and balance). LEQ comes from an `leq`
    column when segments have set one, else leq_columns() (`leq_unassigned`:
    the measured portfolio Behavioral CCF, answer 7)."""
    if basis not in ("average", "current"):
        raise ValueError(f"basis must be 'average' or 'current', not {basis!r}")
    out = acc.copy()
    bal = out["balance_avg_12m" if basis == "average" else "balance_current"].fillna(0.0)
    ucl = out["ucl_avg_12m" if basis == "average" else "ucl_current"].fillna(0.0)
    out["balance"], out["ucl"] = bal, ucl
    out["rw"], out["rw_basis"] = risk_weights(out, cfg)
    if "leq" not in out or out["leq"].isna().all():
        if leq_unassigned is None:
            raise ValueError("no `leq` column and no leq_unassigned given")
        for k, v in leq_columns(out, cfg, leq_unassigned).items():
            out[k] = v
    out["pd_used"], out["pd_imputed"] = pd_used(out, cfg)
    out["fixed_cost_engine"], out["fixed_cost"] = fixed_costs(out, cfg)
    lgd = out["lgd"].fillna(cfg["workbook"]["portfolio"]["lgd"])
    for k, v in _core(bal, ucl, out["rw"], out["pd_used"], lgd, out["leq"], cfg).items():
        out[k] = v
    out["card_profit"] = (out["card_net"] + out["old_capital_cost"] - out["capital_cost"] - out["liquidity_cost"]
                          - (out["fixed_cost"] - out["fixed_cost_engine"]))
    out["relationship_adjusted_profit"] = out["card_profit"] + out["noncard_profit"]
    return out


def reconciliation(costs: pd.DataFrame, mask: pd.Series | None = None) -> pd.DataFrame:
    """B4: from the main engine's card profit to the module's card profit
    under the assumed capital rules, step by step, for the accounts in
    `mask` (default all)."""
    c = costs if mask is None else costs[mask]
    rows = [("Main engine card profit (card_net)", c["card_net"].sum()),
            ("+ old capital charge inside card_net (current rules), added back", c["old_capital_cost"].sum()),
            ("- new capital cost (assumed capital rules)", -c["capital_cost"].sum()),
            ("- liquidity cost (LCR buffer carry)", -c["liquidity_cost"].sum()),
            ("- fixed cost difference (setting minus engine allocation)",
             -(c["fixed_cost"] - c["fixed_cost_engine"]).sum())]
    steps = sum(v for _, v in rows)
    rows += [("= Card profit under the assumed capital rules (module)", c["card_profit"].sum()),
             ("Check: module figure minus the sum of the steps", c["card_profit"].sum() - steps)]
    return pd.DataFrame(rows, columns=["step", "usd"])


def worked_example(limit: float, balance: float, rw: float, cfg: dict,
                   pd12: float = 0.0, lgd: float = 0.0, leq: float = 0.0) -> dict:
    """One account, through the same formulas as account_costs()."""
    ucl = max(limit - balance, 0.0)
    out = {"limit": limit, "balance": balance, "ucl": ucl, "rw": rw}
    out.update({k: float(v) for k, v in _core(balance, ucl, rw, pd12, lgd, leq, cfg).items()})
    return out


def current_rules(costs: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """The same accounts under current US law (brief s.2.6), read-only:
    0% CCF on cancellable lines and 100% on drawn balances, no LCR outflow,
    and the SLR at a 10% CCF and 3% minimum for Category I-III (shown, not
    used: risk-based capital is assumed to bind)."""
    cr, cap = cfg["current_rules_comparison"], cfg["capital"]
    rate = A.annual_capital_cost_rate(cfg)
    bal, ucl = costs["balance"], costs["ucl"]
    rwa = (bal + cr["ccf_unconditionally_cancellable"] * ucl) * cr["risk_weight_drawn_card_balances"]
    slr_on = cfg["bank_profile"]["bank_category"] == A.CATEGORY_I_III
    slr_exposure = bal + cr["slr_ccf"] * ucl
    return pd.DataFrame({
        "rwa_current_rules": rwa,
        "capital_cost_current_rules": rwa * rate,
        "liquidity_cost_current_rules": ucl * cr["lcr_outflow_cancellable_card_lines"] * cfg["liquidity"]["negative_carry"],
        "slr_exposure": slr_exposure if slr_on else 0.0 * slr_exposure,
        "slr_capital_required": (slr_exposure * cr["slr_minimum"]) if slr_on else 0.0 * slr_exposure,
        "risk_based_capital_required_current_rules": rwa * cap["capital_ratio"],
    }, index=costs.index)


def totals(costs: pd.DataFrame, mask: pd.Series | None = None) -> dict:
    c = costs if mask is None else costs[mask]
    cols = ["ucl", "rwa", "rwa_unused", "capital_required", "capital_required_unused", "capital_cost",
            "capital_cost_unused", "hqla", "liquidity_cost", "carrying_cost", "drawdown_el",
            "total_unused_line_cost", "card_net", "old_capital_cost", "card_profit",
            "relationship_adjusted_profit"]
    out = {k: float(c[k].sum()) for k in cols}
    out["accounts"] = int(len(c))
    out["transactor_share"] = float((c["rw_basis"] == "transactor").mean()) if len(c) else float("nan")
    return out


# ------------------------------------------------- workbook reproduction mode
def workbook_baseline(cfg: dict, risk_weights_by_segment: dict | None = None,
                      ccf_by_segment: dict | None = None) -> pd.DataFrame:
    """The workbook's baseline, segment by segment, with its own formulas and
    modelled loss (answer 4's reproduction mode). Default weights and CCF are
    the workbook's 2023 regime; pass the corrected weights for s.2."""
    wb = cfg["workbook"]
    reg = wb["regimes"][cfg["workbook_reproduction"]["original_regime"]]
    rw = risk_weights_by_segment or reg["risk_weight"]
    ccf = ccf_by_segment or reg["ccf"]
    p = wb["portfolio"]
    rows = {}
    for s, a in wb["segments"].items():
        und = max(a["credit_line"] - a["balance"], 0.0)
        revenue = (a["spend"] * a["interchange_rate"] + a["revolving_balance"] * (a["apr"] - p["cost_of_funds"])
                   + a["annual_fee"] + a["other_fee"])
        reward = a["spend"] * a["reward_rate"]
        ecl = a["pd_annual"] * p["lgd"] * (a["balance"] + a["leq"] * und)
        rwa = (a["balance"] + ccf[s] * und) * rw[s]
        rwa_und = ccf[s] * und * rw[s]
        capital = rwa * p["capital_ratio"] * p["cost_of_equity"]
        liquidity = und * p["lcr_outflow"] * p["negative_carry"]
        contribution = revenue - (reward + ecl + a["variable_cost"] + capital + liquidity)
        fully = contribution - a["fixed_cost"]
        n = a["accounts"]
        rows[s] = {"accounts": n, "credit_line": n * a["credit_line"], "undrawn": n * und,
                   "rwa": n * rwa, "rwa_undrawn": n * rwa_und, "capital_charge": n * capital,
                   "liquidity_cost": n * liquidity, "expected_credit_loss": n * ecl,
                   "revenue": n * revenue, "contribution": n * contribution,
                   "fully_loaded_profit": n * fully,
                   "relationship_adjusted_profit": n * (fully + a["relationship_profit"])}
    df = pd.DataFrame(rows).T
    df.loc["total"] = df.sum()
    return df
