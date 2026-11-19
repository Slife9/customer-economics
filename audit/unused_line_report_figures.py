"""Every headline figure of the project report and slides, computed by the
module on a committed sample, under the current settings and under the
settings before revision E. Writes the "Figures changed since the report"
table (revision E, Stage 4).

    python audit/unused_line_report_figures.py [--dataset stress] [--md out.md] [--json out.json]
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "audit"))

from engine.unused_lines import assumptions as A, levers as L, strategies as ST, treatment as T  # noqa: E402
import unused_line_headline_figures as H  # noqa: E402
from unused_lines_app.lib.guide import PLAIN_SEGMENTS  # noqa: E402  (plain text only; no Streamlit)

OLD = {"balance_basis": {"screen": "after_payment", "cost": "after_payment", "lever_values": "average_12m"},
       "levers": {"system_mode": {"transactor_rightsizing_in_approved_value": True}},
       "warning": {"enabled": False}}


def report_figures(name: str, cfg: dict) -> dict:
    f = H.frame(name, cfg)
    sc = f[f["screened"]]
    open_ = int((f["open_at_reporting_date"] & ~f["charged_off"]).sum())
    g = sc.groupby("rule_segment")
    res = L.run(f, cfg, "base")
    s = ST.summary(ST.run(res, cfg), cfg)
    ap = s["approved_combined"]
    scen = {k: ST.evaluate(f, cfg, k)["approved_combined"]["headline_value"] for k in ["conservative", "aggressive"]}
    st15 = ST.evaluate(f, cfg, "base", cfg["stress_test"]["go_no_go_multiplier"])["approved_combined"]
    t = T.design(f, cfg, res, H.worklists(name))
    fa = T.fairness(f, t, cfg)["summary"]["module_decreases_and_closures"]
    d = sc[sc["rule_segment"] == "deteriorating"]
    p, q = d["met:deteriorating.pd"], d["met:deteriorating.score_drop"]
    out = {
        "Cards selected": len(sc), "Open cards": open_, "Share of open cards": len(sc) / open_,
        "Card profit (a year)": sc["card_profit"].sum(), "Card profit per card": sc["card_profit"].mean(),
        "Unused credit": sc["ucl"].sum(), "Unused credit per card": sc["ucl"].mean(),
        "Share of the limit used at statement date": sc["statement_balance_avg_12m"].sum() / sc["limit_avg_12m"].sum(),
        "Cards with no statement balance all year": (sc["cycles_zero_statement_12m"] >= sc["cycles_observed_12m"]).mean(),
        "Carrying cost": sc["carrying_cost"].sum(), "  of which capital": sc["capital_cost_unused"].sum(),
        "  of which liquidity": sc["liquidity_cost"].sum(), "Expected drawdown loss": sc["drawdown_el"].sum(),
        "Total cost of unused lines": sc["total_unused_line_cost"].sum(),
        "Cost to hold per $1,000 unused": sc["carrying_cost"].sum() / sc["ucl"].sum() * 1000,
        "Expected loss per $1,000 unused": sc["drawdown_el"].sum() / sc["ucl"].sum() * 1000,
    }
    for k in cfg["segments"]["order"]:
        lab = PLAIN_SEGMENTS[k]
        out[f"Group {lab}: cards"] = int(g.size().get(k, 0))
        for col, name_ in [("ucl", "unused"), ("carrying_cost", "cost to hold"), ("drawdown_el", "drawdown loss"),
                           ("total_unused_line_cost", "total cost"), ("card_profit", "card profit")]:
            out[f"Group {lab}: {name_}"] = float(g[col].sum().get(k, 0.0))
    out.update({
        "Rising risk: PD rule only / score rule only / both": f"{int((p & ~q).sum())} / {int((~p & q).sum())} / {int((p & q).sum())}",
        "Rising risk: share of all expected drawdown loss": d["drawdown_el"].sum() / sc["drawdown_el"].sum(),
        "Strategy 1 (right-size) on its own": s["strategies"]["right_size"]["headline_value"],
        "  rising-risk cuts": s["strategies"]["right_size"]["components"]["Customers at rising risk"],
        "  idle-line cuts (occasional users + relationship)": (
            s["strategies"]["right_size"]["components"]["Occasional users"]
            + s["strategies"]["right_size"]["components"]["Relationship customers"]),
        "Strategy 2 (re-engage) on its own": s["strategies"]["re_engage"]["headline_value"],
        "Strategy 3 Invite (campaign for unused cards)": s["strategies"]["use_it_or_lose_it"]["components"]["Invite (reactivation offer)"],
        "Strategy 3 actions (awaiting decision)": s["awaiting_decision"],
        "  right-sizing": s["strategies"]["use_it_or_lose_it"]["components"]["Right-size after the warning"],
        "  closure": s["strategies"]["use_it_or_lose_it"]["components"]["Close after the warning (24+ months unused)"],
        "  non-reissue": s["strategies"]["use_it_or_lose_it"]["components"]["Don't reissue at expiry"],
        "Strategy 4 (stop automatic increases), proposed": s["proposed"],
        "Approved value (combined)": ap["headline_value"],
        "  less expected drawdown loss": ap["drawdown_reduction"], "  card profit": ap["card_profit_change"],
        "Range cautious to bold": f"{scen['conservative']:,.0f} to {scen['aggressive']:,.0f}",
        "If customers react 50% more strongly": st15["headline_value"],
        "Customers expected to leave (approved)": ap["accounts_leaving"],
        "Unused credit removed (approved)": ap["unused_removed"],
        "Capital freed, one time (approved)": ap["capital_released"],
        "Total potential (approved + proposed + awaiting)": s["total_potential"],
        "90-day warning letters": s["warning_letters"],
        "Fairness: areas failing / tested / too small": f"{fa['groups_failing']} / {fa['groups_tested']} / {fa['groups_insufficient']}",
        "Fixed cost per selected card (engine)": sc["fixed_cost_engine"].mean(),
    })
    return out


def fmt(k: str, v) -> str:
    if isinstance(v, str):
        return v
    if "hare" in k or "no statement balance" in k:
        return f"{v:.1%}"
    if abs(v) >= 100 or isinstance(v, int):
        return f"{v:,.0f}"
    return f"{v:,.2f}"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="stress")
    ap.add_argument("--md", default=None)
    ap.add_argument("--json", default=None)
    a = ap.parse_args()
    cfg, _ = A.load()
    new = report_figures(a.dataset, cfg)
    old = report_figures(a.dataset, A.with_overrides(cfg, OLD))
    rows = [(k, fmt(k, old[k]), fmt(k, new[k]), "" if fmt(k, old[k]) == fmt(k, new[k]) else "changed") for k in new]
    md = "| Figure | Before revision E (report) | Now | |\n|---|---|---|---|\n" + "\n".join(
        f"| {k} | {o} | {n} | {c} |" for k, o, n, c in rows)
    print(md)
    if a.md:
        Path(a.md).write_text(md + "\n", encoding="utf-8")
    if a.json:
        Path(a.json).write_text(json.dumps({"before": old, "now": new}, indent=2, default=float) + "\n")
