"""The decision numbers, plain actions and status tiles of the decision pages,
computed from the cached results in state.py (nothing here recomputes the
model). Each decision number has one home page:

    1 the problem (accounts, annual loss)        Where the cost sits
    2 the cost of unused lines                   Where the cost sits
    3 approved annual value                      Actions and value
    4 value awaiting decision (B6)               Actions and value
    5 red flags                                  Risks and checks

The Executive summary shows them together and links to each home.
"""
from __future__ import annotations

import pandas as pd

from engine.unused_lines import levers as L, treatment as T
from unused_lines_app.lib import guide as G, state as S

HOME = {"problem": "cost", "cost": "cost", "approved": "actions", "awaiting": "actions", "flags": "risks"}
SHORT = {"line_decrease": "idle limits", "risk_based_decrease": "rising-risk limits",
         "engagement_campaign": "wake-up campaign", "dormant_rightsizing": "right-size",
         "dormant_closure": "close", "non_reissue_expired_dormant": "do not reissue",
         "suppress_automatic_increases": "stop increases", "transactor_rightsizing": "pay-in-full right-sizing"}
STATUS_TEXT = {"approved": "approved", "awaiting": "awaiting your decision", "extra": "extra (assumption-based)",
               "not recommended": "never recommended"}
STATUS_SHORT = {"approved": "", "awaiting": "awaiting decision", "extra": "extra", "not recommended": "never recommended"}
STATUS_ORDER = ["approved", "awaiting", "extra", "not recommended"]


def short(v: float) -> str:
    """$2.58M / $694k / $817 - for sentences."""
    a = abs(v)
    s = f"${a / 1e6:,.2f}M" if a >= 1e6 else (f"${a / 1e3:,.0f}k" if a >= 1e4 else f"${a:,.0f}")
    return ("-" if v < 0 else "") + s


def signed_short(v: float) -> str:
    return ("+" if v >= 0 else "") + short(v)


# ------------------------------------------------------------ 1, 2: problem and cost
def problem(f: pd.DataFrame) -> dict:
    sc = f[f["screened"]]
    return {"accounts": int(len(sc)), "open": int((f["open_at_reporting_date"] & ~f["charged_off"]).sum()),
            "card_profit": float(sc["card_profit"].sum()), "carrying": float(sc["carrying_cost"].sum()),
            "drawdown": float(sc["drawdown_el"].sum()), "ucl": float(sc["ucl"].sum()),
            "cost": float(sc["total_unused_line_cost"].sum())}


# ------------------------------------------------------------ 3, 4: value by action
def lever_status(lever: str, cfg: dict) -> str:
    if lever in G.NOT_RECOMMENDED:
        return "not recommended"
    if L.pending(cfg, lever):
        return "awaiting"
    return "extra" if lever in L.EXTRA_LEVERS else "approved"


def actions(run: dict, cfg: dict, analyst: bool) -> pd.DataFrame:
    """One row per plain action and status (the three actions executives
    see; transactor right-sizing in the analyst view only). Values are each
    lever on its own; the annual value with interactions is the summary's."""
    lt = run["levers"]
    tt = T.timing_table(lt, cfg)
    key = {v: k for k, v in L.LEVER_LABELS.items()}
    per = pd.DataFrame({"lever": [key[i] for i in lt.index], "customers": lt["accounts_targeted"].astype(float).values,
                        "annual": lt["headline_value"].astype(float).values,
                        "year1": tt["year1_value"].astype(float).values,
                        "leaving": lt["accounts_leaving"].astype(float).values,
                        "card_profit": lt["card_profit_change"].astype(float).values,
                        "drawdown_change": lt["drawdown_change"].astype(float).values,
                        "capital": lt["capital_released"].astype(float).values})
    per["status"] = [lever_status(k, cfg) for k in per["lever"]]
    groups = [(a, label, levers) for a, (label, levers) in G.ACTIONS.items()]
    if analyst:
        groups.append(("not_recommended", "Right-size pay-in-full customers", G.NOT_RECOMMENDED))
    rows = []
    for a, label, levers in groups:
        sub = per[per["lever"].isin(levers)]
        statuses = [x for x in STATUS_ORDER if x in set(sub["status"])]
        for stt in statuses:
            g = sub[sub["status"] == stt]
            part = "" if len(statuses) == 1 else ", ".join(SHORT[x] for x in g["lever"])
            tag = STATUS_SHORT[stt]
            name = label + (f": {part}" if part else "") + (f" ({tag})" if tag else "")
            chart = label + (f"<br>{part}" if part else "") + (f" ({tag})" if tag else "")
            rows.append({"action": a, "label": name, "chart_label": chart, "status": stt, "levers": list(g["lever"]),
                         **{c: float(g[c].sum()) for c in ["customers", "annual", "year1", "leaving", "card_profit",
                                                            "drawdown_change", "capital"]}})
    return pd.DataFrame(rows)


def by_action_status(acts: pd.DataFrame) -> pd.DataFrame:
    """Annual value by the three actions (rows) and status (columns), for the
    executive chart."""
    a = acts[acts["action"].isin(G.ACTIONS)]
    t = a.pivot_table(index="action", columns="status", values="annual", aggfunc="sum").reindex(list(G.ACTIONS))
    return t.reindex(columns=["approved", "awaiting", "extra"]).fillna(0.0)


# ------------------------------------------------------------ 5: red flags and status
def robustness_tile(stv: pd.DataFrame) -> tuple:
    g = stv.attrs["go_no_go"]
    colour = "red" if not g["go"] else ("green" if g["card_profit_change"] >= 0 else "amber")
    state = f"{'still pays off' if g['go'] else 'does not pay off'} at {g['multiplier']:g}x"
    return ("Robustness", colour, state, g["statement"] + ".")


def fairness_tile(fa: dict) -> tuple:
    s = fa["summary"]["module_decreases_and_closures"]
    if s["groups_failing"]:
        return ("Fairness", "red", f"{s['groups_failing']} metros fail",
                f"Four-fifths test on the module's own decreases and closures: {s['groups_failing']} fail, "
                f"{s['groups_tested'] - s['groups_failing']} pass, {s['groups_insufficient']} too few to test. "
                "Fair-lending review before any pilot.")
    if not s["groups_tested"]:
        return ("Fairness", "grey", "too few to test",
                f"Every metro has fewer than {fa['min_selected_per_group']} selected accounts.")
    return ("Fairness", "green", "no metro fails",
            f"{s['groups_tested']} metros pass; {s['groups_insufficient']} too few to test.")


def calibration_tile(cal: pd.DataFrame | None, cfg: dict) -> tuple:
    th = cfg["presentation"]["calibration_status"]
    if cal is None:
        return ("Data calibration", "grey", "no report", "No calibration report for this dataset.")
    v = cal["Within Band"].value_counts()
    within, assessed = int(v.get("within", 0)), int(v.get("within", 0) + v.get("outside", 0))
    share = within / max(assessed, 1)
    colour = "green" if share >= th["green_min_share"] else ("amber" if share >= th["amber_min_share"] else "red")
    return ("Data calibration", colour, f"{within} of {assessed} metrics in band",
            f"{share:.0%} of the measured metrics within ±25% of the reference workbook's segment inputs "
            "(synthetic data).")


def rules_tile() -> tuple:
    return ("Rules assumed", "amber", "proposal, not law",
            "Capital and liquidity follow the March 2026 Basel III endgame proposal treated as adopted; "
            "current US law gives cancellable card lines a 0% CCF.")


def decisions_tile(run: dict) -> tuple:
    v = run["summary"]["pending_approval"]["headline_value"]
    return ("Decisions pending", "amber", f"{len(G.DECISIONS_PENDING)} open",
            f"Dormant-card actions worth {signed_short(v)} a year await your decision (B6); "
            + ", ".join(sorted(k for k, _ in G.DECISIONS_PENDING[1:])) + " remain open as settings.")


def notices(treat: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Actions by reason code with their notice rule: every reason code of
    every account with an action."""
    acted = treat[treat["recommended_levers"] != "none"]
    codes = acted["all_reason_codes"].str.split("; ").explode()
    rc = cfg["treatment"]["reason_codes"]
    t = codes.value_counts().rename_axis("code").reset_index(name="actions")
    t["action"] = t["code"].map({k: v["action"] for k, v in rc.items()})
    t["notice"] = t["code"].map({k: v["notice"] for k, v in rc.items()})
    t["adverse_action_notice"] = t["code"].map({k: v["adverse_action_notice"] for k, v in rc.items()})
    t["compliance_flag"] = t["code"].map({k: v["compliance_flag"] for k, v in rc.items()})
    return t


def notices_tile(treat: pd.DataFrame, cfg: dict) -> tuple:
    t = notices(treat, cfg)
    aan = int(t.loc[t["adverse_action_notice"], "actions"].sum())
    flagged = int(t.loc[t["compliance_flag"] != "", "actions"].sum())
    accounts = int((treat["recommended_levers"] != "none").sum())
    return ("Notices required", "amber" if aan else "green", f"{aan:,} adverse-action notices",
            f"{int(t['actions'].sum()):,} actions on {accounts:,} accounts; {flagged:,} flagged for compliance "
            "confirmation. Inactivity actions need no adverse-action notice.")
