"""The four strategies (revision E, Stage 2): what executives see, built
from the levers underneath (config `strategies`).

    1 Right-size unused limits        risk-based decrease (rising risk), line
                                      decrease (occasional users, relationship)
    2 Re-engage active low-use        engagement campaign outside unused cards
    3 "Use it or lose it"             Invite (campaign for unused cards) ->
                                      90-day warning -> right-size / close
                                      (24+ months) -> don't reissue at expiry
    4 Stop automatic limit increases  suppress automatic increases

Every step's per-account effect comes from levers.run (same scenario, same
forward-looking frame), split by segment where a lever serves two strategies
(the campaign: unused cards under Strategy 3, everyone else under Strategy 2).

The warning step (config `warning`, an assumption to be tested in the pilot)
sits before every Strategy 3 action. Of the cards warned, shares resume use
(active-card economics: the reactivation responder's spend and balance, with
no offer costs), accept a lower limit (the right-sizing cut with no attrition,
spend loss or risk uplift), or close voluntarily (the whole line removed); the
rest get the planned action. Strategy 3 is a journey: a card that responds to
the Invite is not warned, so the actions are weighted by (1 - Invite
response). Each warned card costs the letter. The warning never carries a
fee. With warning.enabled = false the actions are the stand-alone lever values
(the setting before revision E).

Values per strategy: annual value (change in card profit + reduction in
expected drawdown loss) and its components, status, customers affected,
customers expected to leave, unused credit removed, and capital freed (a
one-time amount, never added to an annual value). The combined approved
value values the approved steps together (customers who receive two actions
are counted once), so the stand-alone values do not add up to it exactly.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from . import levers as L

STATUS_LABELS = {"approved": "Approved", "approved_test_only": "Approved: test only",
                 "awaiting_decision": "Awaiting decision", "proposed": "Proposed"}
DECREASE_LEVERS = ["line_decrease", "risk_based_decrease", "dormant_rightsizing", "transactor_rightsizing"]
ANNUAL = ["headline_value", "card_profit_change", "drawdown_change", "relationship_adjusted_change"]
COUNTS = ["accounts_leaving", "unused_removed", "capital_released"]


def step_status(cfg: dict, d: dict, s: dict) -> str:
    """A step's own status; B6 levers follow their approval flags."""
    if "status" in s:
        return s["status"]
    b6 = [lv for lv in s["levers"] if lv in L.B6_FLAG]
    if b6:
        return "approved" if all(cfg["levers"][L.B6_FLAG[lv]] for lv in b6) else "awaiting_decision"
    return d["status"]


def status_label(cfg: dict, key: str) -> str:
    d = cfg["strategies"]["definitions"][key]
    st = [step_status(cfg, d, s) for s in d["steps"]]
    if len(set(st)) == 1:
        return STATUS_LABELS[st[0]]
    first = d["steps"][0]
    rest = sorted(set(st[1:]))
    return (f"{first['name'].split(' (')[0]} {STATUS_LABELS[st[0]].lower()}; actions "
            + " / ".join(STATUS_LABELS[r].lower() for r in rest))


def lever_strategy(cfg: dict) -> dict[tuple[str, str], tuple[str, str]]:
    """(lever, segment) -> (strategy key, step key)."""
    out = {}
    for key in cfg["strategies"]["order"]:
        for s in cfg["strategies"]["definitions"][key]["steps"]:
            for lv in s["levers"]:
                for seg in (s["segments"] or ["*"]):
                    out[(lv, seg)] = (key, s["key"])
    return out


def strategy_of(cfg: dict, lever: str, segment: str) -> tuple[str, str] | None:
    m = lever_strategy(cfg)
    return m.get((lever, segment)) or m.get((lever, "*"))


def _seg(frame: pd.DataFrame, segments) -> pd.Series:
    return frame["rule_segment"].isin(segments) if segments else pd.Series(True, index=frame.index)


def _selected(res: dict, cfg: dict, lever: str) -> pd.Series:
    """The accounts a lever selects in this scenario."""
    sel, g = res["selection"], res["frame"]
    if lever in DECREASE_LEVERS:
        return sel["decrease"] & (g["rule_segment"].map(cfg["levers"]["system_mode"]["lever_by_segment"]) == lever)
    if lever == "dormant_closure":
        return sel["closure"].copy()
    if lever == "engagement_campaign":
        return sel["campaign"].copy()
    return res["per_lever"][lever]["eligible"].astype(bool)


def _zero(index) -> pd.DataFrame:
    return pd.DataFrame(0.0, index=index, columns=L.OUT_COLS)


def _warned(res: dict, cfg: dict, lever: str, targeted: pd.Series) -> tuple[pd.DataFrame, pd.Series]:
    """A Strategy 3 action with the 90-day warning in front of it, per
    account; and the expected number of letters per account."""
    g, sel, P, per = res["frame"], res["selection"], res["params"], res["per_lever"]
    action = per[lever][L.OUT_COLS].where(targeted, 0.0)
    if not cfg["warning"]["enabled"]:
        return action, pd.Series(0.0, index=g.index)
    sh = cfg["warning"]["response_shares"]
    rest = 1.0 - sum(sh.values())
    none = sel.assign(decrease=False, campaign=False, closure=False)
    close = L.value(g, cfg, none.assign(closure=targeted), P, {"closure": True})
    P0 = P.assign(attrition=0.0, spend_loss=0.0, pd_uplift=0.0)
    lower = L.value(g, cfg, none.assign(decrease=targeted & sel["cut_possible"]), P0, {"decrease": True})
    resume = L.value(g, cfg, none.assign(campaign=targeted), P.assign(response=1.0), {"campaign": True},
                     offer_costs=False)
    eff = (sh["resume_use"] * resume[L.OUT_COLS] + sh["accept_lower_limit"] * lower[L.OUT_COLS]
           + sh["close_voluntarily"] * close[L.OUT_COLS] + rest * action)
    # Invite responders are not warned: the journey weights the actions by 1 - response
    invited = sel["campaign"] & (g["rule_segment"] == "dormant")
    reach = (1.0 - P["response"].where(invited, 0.0)).where(targeted, 0.0)
    eff = eff.mul(reach, axis=0)
    letters = reach
    cost = letters * cfg["warning"]["letter_cost_usd"]
    for c in ["card_profit_change", "relationship_adjusted_change", "headline_value"]:
        eff[c] = eff[c] - cost
    eff["lost_profit"] = eff["lost_profit"] - cost
    return eff, letters


def run(res: dict, cfg: dict) -> dict:
    """Per-account effects of every strategy step for one levers.run result."""
    g, scope = res["frame"], res["scope"]
    out = {}
    for key in cfg["strategies"]["order"]:
        d = cfg["strategies"]["definitions"][key]
        for s in d["steps"]:
            seg = _seg(g, s["segments"]) & scope
            eff, tgt, letters = _zero(g.index), pd.Series(False, index=g.index), pd.Series(0.0, index=g.index)
            for lv in s["levers"]:
                t = _selected(res, cfg, lv) & seg
                if s.get("warning"):
                    e, n = _warned(res, cfg, lv, t)
                    letters = letters + n
                else:
                    e = res["per_lever"][lv][L.OUT_COLS].where(t, 0.0)
                eff = eff + e
                tgt = tgt | t
            out[(key, s["key"])] = {"effect": eff, "targeted": tgt, "letters": letters,
                                    "status": step_status(cfg, d, s), "name": s["name"]}
    return {"steps": out, "scope": scope, "res": res}


def _totals(eff: pd.DataFrame, targeted: pd.Series) -> dict:
    t = eff[ANNUAL + COUNTS].sum()
    return {**{k: float(t[k]) for k in ANNUAL + COUNTS}, "drawdown_reduction": float(-t["drawdown_change"]),
            "customers": int(targeted.sum())}


def table(sr: dict, cfg: dict) -> pd.DataFrame:
    """One row per strategy step: its stand-alone annual value and parts."""
    rows = []
    for (key, step), v in sr["steps"].items():
        d = cfg["strategies"]["definitions"][key]
        rows.append({"strategy": key, "number": d["number"], "strategy_name": d["name"], "step": step,
                     "step_name": v["name"], "status": v["status"], "status_label": STATUS_LABELS[v["status"]],
                     "letters": float(v["letters"].sum()), **_totals(v["effect"], v["targeted"])})
    return pd.DataFrame(rows)


def summary(sr: dict, cfg: dict) -> dict:
    """Per strategy (stand-alone value and components), the combined approved
    value, the proposed and awaiting-decision totals and the total potential.
    Capital freed is one-time and reported apart from every annual value."""
    res = sr["res"]
    g, sel, P, scope = res["frame"], res["selection"], res["params"], res["scope"]
    tb = table(sr, cfg)
    strategies = {}
    for key in cfg["strategies"]["order"]:
        d = cfg["strategies"]["definitions"][key]
        part = tb[tb["strategy"] == key]
        tgt = pd.Series(False, index=g.index)
        eff = _zero(g.index)
        for s in d["steps"]:
            tgt = tgt | sr["steps"][(key, s["key"])]["targeted"]
            eff = eff + sr["steps"][(key, s["key"])]["effect"]
        strategies[key] = {"number": d["number"], "name": d["name"], "status_label": status_label(cfg, key),
                           **_totals(eff, tgt),
                           "components": {r.step_name: float(r.headline_value) for r in part.itertuples()},
                           "component_status": {r.step_name: r.status for r in part.itertuples()}}
    # combined approved value: approved steps valued together
    approved = tb[tb["status"].isin(["approved", "approved_test_only"])]
    keys = list(zip(approved["strategy"], approved["step"]))
    lever_of = {(k, st): s["levers"] for k in cfg["strategies"]["order"]
                for s in cfg["strategies"]["definitions"][k]["steps"] for st in [s["key"]]}
    warn_of = {(k, s["key"]): bool(s.get("warning")) for k in cfg["strategies"]["order"]
               for s in cfg["strategies"]["definitions"][k]["steps"]}
    dec = pd.Series(False, index=g.index)
    camp = pd.Series(False, index=g.index)
    extra = _zero(g.index)
    for k in keys:
        t = sr["steps"][k]["targeted"]
        levers = lever_of[k]
        if warn_of[k] or any(lv in L.EXTRA_LEVERS for lv in levers):
            extra = extra + sr["steps"][k]["effect"]
        elif any(lv in DECREASE_LEVERS for lv in levers):
            dec = dec | t
        elif "engagement_campaign" in levers:
            camp = camp | t
    if not L.excluded(cfg, "transactor_rightsizing"):   # the setting before revision E (1c)
        dec = dec | _selected(res, cfg, "transactor_rightsizing")
    core = L.value(g, cfg, sel.assign(decrease=sel["decrease"] & dec, campaign=sel["campaign"] & camp,
                                      closure=False), P, {"decrease": True, "campaign": True})
    comb = core[scope][L.OUT_COLS].sum() + extra[scope].sum()
    combined = {**{k: float(comb[k]) for k in ANNUAL + COUNTS}, "drawdown_reduction": float(-comb["drawdown_change"])}
    proposed = float(tb.loc[tb["status"] == "proposed", "headline_value"].sum())
    awaiting = float(tb.loc[tb["status"] == "awaiting_decision", "headline_value"].sum())
    return {"scenario": res["scenario"], "multiplier": res["multiplier"], "strategies": strategies,
            "approved_combined": combined, "proposed": proposed, "awaiting_decision": awaiting,
            "total_potential": combined["headline_value"] + proposed + awaiting,
            "warning_letters": float(tb["letters"].sum()), "table": tb}


def evaluate(f: pd.DataFrame, cfg: dict, scenario: str = "base", multiplier: float = 1.0) -> dict:
    """levers.run, then the strategies, for one scenario."""
    return summary(run(L.run(f, cfg, scenario, multiplier), cfg), cfg)
