"""The figures the pages show, computed from the cached results in state.py
(nothing here recomputes the model). Revision E: the project report's
figures, in its order: the problem, the cost, the groups, the four
strategies and what they are worth, then the checks.
"""
from __future__ import annotations

import pandas as pd

from engine.unused_lines import strategies as ST
from unused_lines_app.lib import guide as G

STATUS_ORDER = ["approved", "approved_test_only", "awaiting_decision", "proposed"]


def short(v: float) -> str:
    """$573M / $2.58M / $694k / $817 - for sentences."""
    a = abs(v)
    s = (f"${a / 1e6:,.0f}M" if a >= 1e8 else f"${a / 1e6:,.2f}M" if a >= 1e6
         else f"${a / 1e3:,.0f}k" if a >= 1e4 else f"${a:,.0f}")
    return ("−" if v < 0 else "") + s


def signed_short(v: float) -> str:
    return ("+" if v >= 0 else "") + short(v)


# ------------------------------------------------------------ the problem and its cost
def problem(f: pd.DataFrame) -> dict:
    sc = f[f["screened"]]
    open_ = int((f["open_at_reporting_date"] & ~f["charged_off"]).sum())
    limits = float(sc["limit_avg_12m"].sum())
    return {"accounts": int(len(sc)), "open": open_, "share": len(sc) / max(open_, 1),
            "card_profit": float(sc["card_profit"].sum()), "per_card": float(sc["card_profit"].mean()) if len(sc) else 0.0,
            "ucl": float(sc["ucl"].sum()), "ucl_per_card": float(sc["ucl"].mean()) if len(sc) else 0.0,
            "carrying": float(sc["carrying_cost"].sum()), "capital": float(sc["capital_cost_unused"].sum()),
            "liquidity": float(sc["liquidity_cost"].sum()), "drawdown": float(sc["drawdown_el"].sum()),
            "cost": float(sc["total_unused_line_cost"].sum()),
            "limits": limits, "statement_balance": float(sc["statement_balance_avg_12m"].sum()),
            "used_at_statement": float(sc["statement_balance_avg_12m"].sum()) / max(limits, 1.0),
            "no_statement_balance": float((sc["cycles_zero_statement_12m"] >= sc["cycles_observed_12m"]).mean())
            if len(sc) else 0.0}


def funnel(f: pd.DataFrame, cfg: dict) -> list[tuple[str, int]]:
    """Open cards still in after each of the six tests, in the report's order."""
    m = f["met:screen.open"].copy()
    out = []
    for key, text in G.selection_tests(cfg):
        if key != "screen.open":
            m &= f[f"met:{key}"]
        out.append((text, int(m.sum())))
    return out


def group_table(f: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    sc = f[f["screened"]]
    g = sc.groupby("rule_segment")
    order = cfg["segments"]["order"]
    t = pd.DataFrame({"cards": g.size(), "ucl": g["ucl"].sum(), "carrying": g["carrying_cost"].sum(),
                      "drawdown": g["drawdown_el"].sum(), "total": g["total_unused_line_cost"].sum(),
                      "card_profit": g["card_profit"].sum()}).reindex(order).fillna(0.0)
    t["share"] = t["cards"] / max(len(sc), 1)
    return t


def qualify(f: pd.DataFrame, key: str, cfg: dict) -> str:
    """How cards qualify for a group in practice (the report's bullets)."""
    sc = f[f["screened"] & (f["rule_segment"] == key)]
    if not len(sc):
        return "No cards in this group."
    if key == "deteriorating":
        p, s = sc["met:deteriorating.pd"], sc["met:deteriorating.score_drop"]
        return (f"{int((p & ~s).sum()):,} met the default-probability rule only, {int((~p & s).sum()):,} the "
                f"score-drop rule only and {int((p & s).sum()):,} both. Average chance of default "
                f"{sc['pd_used'].mean():.0%}.")
    if key == "relationship":
        return (f"{int(sc['met:relationship.noncard_profit'].sum()):,} met the other-products rule, "
                f"{int(sc['met:relationship.deposits'].sum()):,} the deposit rule and "
                f"{int(sc['met:relationship.premium'].sum()):,} the Premier / Private Banking rule (many meet more "
                f"than one). Their other products earn about ${sc['noncard_profit'].mean():,.0f} each a year.")
    if key == "dormant":
        return f"On average last used about {sc['months_since_last_transaction'].mean():.0f} months ago."
    if key == "sock_drawer":
        return (f"About {sc['active_months_12m'].mean():.0f} active months and ${sc['spend_12m'].mean():,.0f} of "
                "spend a year.")
    if key == "transactors":
        return (f"About ${sc['spend_12m'].mean():,.0f} of spend a year; their busiest month uses about "
                f"{sc['peak_statement_utilisation_12m'].mean():.0%} of the limit.")
    tr = cfg["segments"]["rules"]["transactors"]
    return (f"Mostly active spenders: {int((sc['peak_statement_utilisation_12m'] >= tr['peak_utilisation_max']).sum()):,} "
            f"used {tr['peak_utilisation_max']:.0%} or more of their limit in their busiest month and "
            f"{int((sc['spend_12m'] < tr['spend_min_usd']).sum()):,} spent under ${tr['spend_min_usd']:,.0f}, so they "
            "miss the pay-in-full rule.")


# ------------------------------------------------------------ the strategies
def strategy_rows(st_: dict) -> pd.DataFrame:
    """One row per strategy (stand-alone value, status, customers, leavers,
    unused removed, capital freed)."""
    rows = []
    for key, v in st_["strategies"].items():
        rows.append({"key": key, "number": v["number"], "name": v["name"], "status": v["status_label"],
                     "value": v["headline_value"], "card_profit": v["card_profit_change"],
                     "drawdown_reduction": v["drawdown_reduction"], "customers": v["customers"],
                     "leaving": v["accounts_leaving"], "unused_removed": v["unused_removed"],
                     "capital": v["capital_released"],
                     "components": "; ".join(f"{k} {signed_short(x)}" for k, x in v["components"].items())})
    return pd.DataFrame(rows)


def chart_bars(st_: dict, cfg: dict) -> pd.DataFrame:
    """Bars for the value chart: each strategy on its own, with Strategy 3's
    Invite (approved) apart from its actions (awaiting decision)."""
    tb = st_["table"]
    rows = []
    for key in cfg["strategies"]["order"]:
        part = tb[tb["strategy"] == key]
        d = cfg["strategies"]["definitions"][key]
        for status, g in part.groupby("status", sort=False):
            name = f"{d['number']}. {d['name']}"
            if part["status"].nunique() > 1:
                name += ": " + ("Invite" if (g["step"] == "invite").all() else "actions after the warning")
            v = float(g["headline_value"].sum())
            rows.append({"label": name, "status": status, "value": v,
                         "status_text": ST.STATUS_LABELS[status] + ("; loses money today" if v < 0 else "")})
    return pd.DataFrame(rows)


def value_mix(st_: dict) -> dict:
    """How much of the approved value and of the total potential is lower
    expected drawdown loss (the rest is card profit)."""
    tb = st_["table"]
    ap = st_["approved_combined"]
    later = tb[tb["status"].isin(["proposed", "awaiting_decision"])]
    total = ap["headline_value"] + later["headline_value"].sum()
    risk = ap["drawdown_reduction"] + later["drawdown_reduction"].sum()
    return {"approved_risk_share": ap["drawdown_reduction"] / ap["headline_value"] if ap["headline_value"] else 0.0,
            "total_risk_share": risk / total if total else 0.0, "total_risk": risk}


def mix_sentence(st_: dict) -> str:
    m = value_mix(st_)
    if m["total_risk_share"] > 0.6:
        out = "Most of it is lower expected loss rather than new revenue."
    else:
        out = (f"About {m['total_risk_share']:.0%} of it is lower expected loss; the rest is card profit, mostly from "
               "closing or right-sizing unused cards that lose money.")
    if m["approved_risk_share"] >= 1:
        out += " The approved value is all lower expected loss: card profit alone is slightly negative."
    return out


# ------------------------------------------------------------ status tiles
def robustness_tile(stv: pd.DataFrame) -> tuple:
    g = stv.attrs["go_no_go"]
    colour = "red" if not g["go"] else ("green" if g["card_profit_change"] >= 0 else "amber")
    state = f"{'still worth it' if g['go'] else 'not worth it'} at {g['multiplier']:g}x"
    return ("Robustness", colour, state,
            f"If customers react {(g['multiplier'] - 1):.0%} more strongly than assumed, approved actions are worth "
            f"{signed_short(g['headline_value'])} a year (value including reduced risk; card profit alone "
            f"{signed_short(g['card_profit_change'])}).")


def fairness_text(fa: dict) -> str:
    s = fa["summary"]["module_decreases_and_closures"]
    return (f"fail the four-fifths test in {s['groups_failing']} of {s['groups_tested']} areas "
            f"({s['groups_insufficient']} too small to test)")


def fairness_tile(fa: dict) -> tuple:
    s = fa["summary"]["module_decreases_and_closures"]
    if s["groups_failing"]:
        n = s["groups_failing"]
        return ("Fairness", "red", f"{n} area{' fails' if n == 1 else 's fail'}",
                f"Cuts and closures {fairness_text(fa)}: " + ", ".join(s["failing_groups"])
                + ". Fair-lending review before any customer is contacted.")
    if not s["groups_tested"]:
        return ("Fairness", "grey", "too few to test",
                f"Every area has fewer than {fa['min_selected_per_group']} cards selected for a cut or closure.")
    return ("Fairness", "green", "no area fails",
            f"{s['groups_tested']} areas pass; {s['groups_insufficient']} too small to test. Review before any pilot.")


def rules_tile() -> tuple:
    return ("Rules assumed", "amber", "proposal, not law",
            "Capital and liquidity costs assume the March 2026 Basel III endgame proposal is adopted; most of the "
            "value is drawdown risk, which applies under any rules.")


def calibration_tile(cal: pd.DataFrame | None, cfg: dict) -> tuple:
    th = cfg["presentation"]["calibration_status"]
    if cal is None:
        return ("Data calibration", "grey", "no report", "No calibration report for this dataset.")
    v = cal["Within Band"].value_counts()
    within, assessed = int(v.get("within", 0)), int(v.get("within", 0) + v.get("outside", 0))
    share = within / max(assessed, 1)
    colour = "green" if share >= th["green_min_share"] else ("amber" if share >= th["amber_min_share"] else "red")
    return ("Data calibration", colour, f"{within} of {assessed} metrics in band",
            f"{share:.0%} of the measured metrics within ±25% of the reference workbook's segment inputs.")


def notices(treat: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Actions by reason code with their notice rule: every reason code of
    every account with an action."""
    acted = treat[treat["recommended_levers"] != "none"]
    codes = acted["all_reason_codes"].str.split("; ").explode()
    rc = cfg["treatment"]["reason_codes"]
    t = codes.value_counts().rename_axis("code").reset_index(name="actions")
    t["action"] = t["code"].map({k: v["action"] for k, v in rc.items()})
    t["notice"] = t["code"].map({k: v["notice"] for k, v in rc.items()})
    t["adverse_action_notice"] = t["code"].map({k: v["adverse_action_notice"] for k, v in rc.items()}).astype(bool)
    t["compliance_flag"] = t["code"].map({k: v["compliance_flag"] for k, v in rc.items()})
    return t
