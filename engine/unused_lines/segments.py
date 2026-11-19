"""Screen and segments (workbook Segment Definitions, brief s.4.1 items 3-4).

Order of work, per account:
1. The segment rules run on every account (they do not depend on profit),
   first match wins, in the workbook's priority order.
2. LEQ: the account's measured Behavioral CCF, or the workbook LEQ of that
   segment (config drawdown_risk.leq_source; Unassigned: the measured
   portfolio Behavioral CCF), then the s.2 costs (exposure.account_costs).
3. The screen keeps unprofitable low-use accounts; a screened account's
   segment is its rule segment, anyone else has none. The utilisation test
   uses the statement-date balance by default (balance_basis.screen).
4. The same costs on today's line and balance, as now_* columns, for the
   forward-looking lever values (levers.forward_frame).

System-mode screen (answer 2): card profit < 0, where card profit is the
module's (measured credit cost, the old capital charge replaced, the new
liquidity cost subtracted). Expected drawdown loss is shown beside it; the
sensitivity toggle `screen.include_expected_drawdown_loss` deducts it.
Workbook-reproduction mode does not use this module: it runs on the
workbook's own segment inputs (exposure.workbook_baseline).

Every rule keeps the account's actual value, the threshold and met / not met
(rule_trace), for the drill-down. The segmentation transactor rule (>= 10 of
12) is separate from the regulatory transactor test (12 of 12,
exposure.risk_weights) and labelled so everywhere.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from . import exposure as X

RULE_LABELS = {
    "deteriorating.pd": "PD 12 Month at least {pd_annual_min:.0%}",
    "deteriorating.score_drop": "Bureau score down at least {score_drop_6m_min:.0f} points in 6 months (Table29, synthetic)",
    "relationship.noncard_profit": "Non-card relationship profit at least ${noncard_profit_min_usd:,.0f} a year",
    "relationship.deposits": "Deposits at least ${deposits_plus_investments_min_usd:,.0f} (investments not available - approximate)",
    "relationship.premium": "Segment Premier / Private Banking (premium proxy - approximate)",
    "dormant.inactive": "No transaction for at least {inactive_months_min:.0f} months",
    "dormant.zero_balance": "$0 balance in every one of the last 12 cycles",
    "sock_drawer.active": "Active in at most {active_months_max:.0f} of 12 months",
    "sock_drawer.spend": "Annual spend below ${spend_max_usd:,.0f}",
    "transactors.paid": "Paid in full (or nothing due) in at least {paid_in_full_months_min:.0f} of 12 cycles (segmentation rule, not the regulatory test)",
    "transactors.peak": "Peak statement utilisation below {peak_utilisation_max:.0%}",
    "transactors.spend": "Annual spend at least ${spend_min_usd:,.0f}",
}
SCREEN_LABELS = {
    "screen.unprofitable": "Card profit below $0",
    "screen.utilisation": "Average utilisation below {max_utilisation:.0%}",
    "screen.unused": "Unused line at least ${min_unused_usd:,.0f}",
    "screen.history": "Open at least {min_history_months:.0f} months",
    "screen.open": "Open and not charged off at the reporting date",
    "screen.not_fraud_blocked": "No fraud-compromise card event in the last 2 cycles (fraud-block proxy - approximate)",
}


def rule_trace(acc: pd.DataFrame, cfg: dict) -> dict[str, tuple[pd.Series, float, pd.Series]]:
    """{rule id: (actual value, threshold, met)} for every account."""
    r = cfg["segments"]["rules"]
    d, rel, dor, sock, tr = (r["deteriorating"], r["relationship"], r["dormant"], r["sock_drawer"],
                             r["transactors"])
    paid = acc["cycles_paid_in_full_12m"] + (acc["cycles_zero_statement_12m"] if tr["nothing_due_counts_as_paid"] else 0)
    drop = -acc["bureau_score_change_6m"]
    out = {
        "deteriorating.pd": (acc["pd_12m"], d["pd_annual_min"], acc["pd_12m"] >= d["pd_annual_min"]),
        "deteriorating.score_drop": (drop, d["score_drop_6m_min"], drop >= d["score_drop_6m_min"]),
        "relationship.noncard_profit": (acc["noncard_profit"], rel["noncard_profit_min_usd"],
                                        acc["noncard_profit"] >= rel["noncard_profit_min_usd"]),
        "relationship.deposits": (acc["deposit_balance"], rel["deposits_plus_investments_min_usd"],
                                  acc["deposit_balance"] >= rel["deposits_plus_investments_min_usd"]),
        "relationship.premium": (acc["customer_segment"], np.nan,
                                 acc["customer_segment"].isin(rel["premium_segments"])),
        "dormant.inactive": (acc["months_since_last_transaction"], dor["inactive_months_min"],
                             acc["months_since_last_transaction"] >= dor["inactive_months_min"]),
        "dormant.zero_balance": (acc["months_with_balance_12m"], dor["balance_max_usd"],
                                 acc["months_with_balance_12m"] == 0),
        "sock_drawer.active": (acc["active_months_12m"], sock["active_months_max"],
                               acc["active_months_12m"] <= sock["active_months_max"]),
        "sock_drawer.spend": (acc["spend_12m"], sock["spend_max_usd"], acc["spend_12m"] < sock["spend_max_usd"]),
        "transactors.paid": (paid, tr["paid_in_full_months_min"], paid >= tr["paid_in_full_months_min"]),
        "transactors.peak": (acc["peak_statement_utilisation_12m"], tr["peak_utilisation_max"],
                             acc["peak_statement_utilisation_12m"] < tr["peak_utilisation_max"]),
        "transactors.spend": (acc["spend_12m"], tr["spend_min_usd"], acc["spend_12m"] >= tr["spend_min_usd"]),
    }
    return {k: (v, t, m.fillna(False).astype(bool)) for k, (v, t, m) in out.items()}


def rule_segment(trace: dict, cfg: dict, index: pd.Index) -> pd.Series:
    met = {k: v[2] for k, v in trace.items()}
    rules = [
        met["deteriorating.pd"] | met["deteriorating.score_drop"],
        met["relationship.noncard_profit"] | met["relationship.deposits"] | met["relationship.premium"],
        met["dormant.inactive"] & met["dormant.zero_balance"],
        met["sock_drawer.active"] & met["sock_drawer.spend"],
        met["transactors.paid"] & met["transactors.peak"] & met["transactors.spend"],
    ]
    order = cfg["segments"]["order"]
    return pd.Series(np.select(rules, order[:5], default=order[5]), index=index, name="rule_segment")


def screen(c: pd.DataFrame, cfg: dict, include_drawdown: bool | None = None) -> dict[str, pd.Series]:
    """{criterion: met} on a costed frame, plus "screened"."""
    sc = cfg["screen"]
    with_el = sc["include_expected_drawdown_loss"] if include_drawdown is None else include_drawdown
    profit = c["card_profit"] - (c["drawdown_el"] if with_el else 0.0)
    util = c["statement_utilisation_avg_12m" if cfg["balance_basis"]["screen"] == "statement_date"
             else "utilisation_avg_12m"]
    out = {
        "screen.unprofitable": (profit < 0) if sc["require_unprofitable"] else pd.Series(True, index=c.index),
        "screen.utilisation": util < sc["max_utilisation"],
        "screen.unused": c["ucl_current"] >= sc["min_unused_usd"],
        "screen.history": c["account_age_months"] >= sc["min_history_months"],
        "screen.open": c["open_at_reporting_date"] & ~c["charged_off"],
        "screen.not_fraud_blocked": ~c["fraud_event_recent"].astype(bool) if sc["exclude_fraud_blocked_proxy"]
        else pd.Series(True, index=c.index),
    }
    out = {k: v.fillna(False).astype(bool) for k, v in out.items()}
    s = pd.Series(True, index=c.index)
    for v in out.values():
        s &= v
    out["screened"] = s
    return out


def dormant_confirmation(acc: pd.DataFrame) -> pd.DataFrame:
    """Confirming signals for a dormant account (informational, never a rule)."""
    return pd.DataFrame({
        "confirm_card_not_activated": acc["current_card_activation"].eq("not_activated"),
        "confirm_card_due_for_reissue": acc["card_expires_within_12m"].fillna(False).astype(bool),
        "confirm_no_digital_sessions": acc["digital_sessions_12m"].eq(0),
    }, index=acc.index)


def build(acc: pd.DataFrame, meta: dict, cfg: dict) -> pd.DataFrame:
    """The costed, segmented account frame: rule segment and LEQ, s.2 costs,
    screen criteria, `screened`, `segment` (screened accounts only), the
    drawdown sensitivity flag, and the rule trace's met flags."""
    trace = rule_trace(acc, cfg)
    out = acc.copy()
    out["rule_segment"] = rule_segment(trace, cfg, acc.index)
    for k, v in X.leq_columns(out, cfg, meta["leq_unassigned_measured"]).items():
        out[k] = v
    out = X.account_costs(out, cfg)
    # forward-looking values (balance_basis.lever_values = current): the same
    # costs on today's line and balance, kept beside the 12-month figures
    now = X.account_costs(out[[c for c in out if c not in X.BALANCE_DEPENDENT]], cfg, basis="current")
    for k in X.BALANCE_DEPENDENT:
        out[f"now_{k}"] = now[k]
    for k, v in trace.items():
        out[f"met:{k}"] = v[2]
    sc = screen(out, cfg)
    for k, v in sc.items():
        out[k if k == "screened" else f"met:{k}"] = v
    alt = screen(out, cfg, include_drawdown=not cfg["screen"]["include_expected_drawdown_loss"])["screened"]
    out["screened_drawdown_sensitivity"] = alt
    out["segment"] = np.where(out["screened"], out["rule_segment"], "")
    out = pd.concat([out, dormant_confirmation(out)], axis=1)
    return out


SUMMARY_COLS = ["ucl", "rwa_unused", "capital_required_unused", "carrying_cost", "drawdown_el",
                "total_unused_line_cost", "card_profit", "relationship_adjusted_profit"]


def summary(frame: pd.DataFrame, cfg: dict, mask: pd.Series | None = None) -> pd.DataFrame:
    """By segment (workbook order) and total: accounts, unused lines, carrying
    cost, drawdown loss, total unused-line cost, card and relationship-adjusted
    profit. Carrying cost and drawdown loss are separate columns."""
    m = frame["screened"] if mask is None else mask
    f = frame[m]
    by = f.groupby("rule_segment")
    t = by[SUMMARY_COLS].sum().reindex(cfg["segments"]["order"]).fillna(0.0)
    t.insert(0, "accounts", by.size().reindex(cfg["segments"]["order"]).fillna(0).astype(int))
    t.loc["total"] = t.sum()
    t["share_of_screened"] = t["accounts"] / max(len(f), 1)
    t["card_profit_per_account"] = t["card_profit"] / t["accounts"].where(t["accounts"] > 0)
    t.index = [cfg["segments"]["labels"].get(i, "Total") if i != "total" else "Total" for i in t.index]
    return t


def drawdown_sensitivity(frame: pd.DataFrame) -> dict:
    """What the 'screen including expected drawdown loss' toggle changes."""
    base, alt = frame["screened"], frame["screened_drawdown_sensitivity"]
    extra = alt & ~base
    return {"accounts_screened_default": int(base.sum()), "accounts_screened_toggle": int(alt.sum()),
            "extra_accounts": int(extra.sum()) - int((base & ~alt).sum()),
            "extra_card_profit": float(frame.loc[extra, "card_profit"].sum()),
            "extra_drawdown_el": float(frame.loc[extra, "drawdown_el"].sum()),
            "extra_loss_after_drawdown": float((frame.loc[extra, "card_profit"] - frame.loc[extra, "drawdown_el"]).sum())}
