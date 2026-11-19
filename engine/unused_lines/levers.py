"""System-mode levers, customer response, scenarios and the stress test
(brief s.4.1 items 5-7, Stage 5).

Runs on the segmented account frame (segments.build). Lever intensities
(share of a segment targeted, campaign economics, responses) come from the
workbook model by scenario and segment; sizing, floors and eligibility from
config `levers.system_mode`. Expected values per account:

line decrease (segment lever: line_decrease / risk_based_decrease /
dormant_rightsizing / transactor_rightsizing)
    new line = max(target, minimum line, balance x 1.2); the cut is at most
    25% of the line per review (one review in year 1) and at least 15% and
    $500, or there is no cut. Survivors (1 - attrition) keep the new line and
    lose spend-loss x spend margin; PD rises by the uplift (deteriorating).
    Leavers lose variable contribution (card profit + fixed cost) and
    relationship profit; fixed cost stays.
dormant closure (B6)
    eligible: dormant, inactive >= 24 months; closes only if it does not
    respond to the reactivation campaign (inactivity reason).
engagement campaign
    responders = share targeted x response rate; each adds spend (margin at
    the workbook's interchange - reward rate) and revolving balance (account
    APR - cost of funds), costs the incentive and promo give-up, and moves
    from 45% to 75% (a campaign / installment balance disqualifies a
    transactor). Every targeted survivor costs the campaign cost.
extra levers (assumption-based; not in the reference workbook)
    suppress automatic increases: next year's increase avoided (Table20);
    non-reissue of expired dormant cards (B6): reissue cost saved + the line
    closed at expiry.

Stress: attrition, spend loss and PD uplift x multiplier, response rate /
multiplier (configurable). Capital released = -change in RWA x capital ratio,
a one-time stock reported apart from every annual value.

Forward-looking values use today's unused line (balance_basis.lever_values =
current, revision E 1b: forward_frame); the 12-month average explains past
profit. Pay-in-full (transactor) right-sizing is valued but left out of the
approved total by policy (transactor_rightsizing_in_approved_value, 1c).
"""
from __future__ import annotations
import hashlib

import numpy as np
import pandas as pd

from . import assumptions as A
from . import exposure as X

WORKBOOK_LEVERS = ["line_decrease", "risk_based_decrease", "dormant_rightsizing", "transactor_rightsizing",
                   "dormant_closure", "engagement_campaign"]
EXTRA_LEVERS = ["suppress_automatic_increases", "non_reissue_expired_dormant"]
LEVER_LABELS = {
    "line_decrease": "Line decrease with floor",
    "risk_based_decrease": "Risk-based decrease (credit-deteriorating)",
    "dormant_rightsizing": "Dormant right-sizing",
    "transactor_rightsizing": "Pay-in-full right-sizing (not recommended, by policy)",
    "dormant_closure": "Dormant closure after failed reactivation",
    "engagement_campaign": "Reactivation / engagement campaign",
    "suppress_automatic_increases": "Suppress automatic line increases (assumption-based)",
    "non_reissue_expired_dormant": "Non-reissue of expired dormant cards (assumption-based)",
}
B6_FLAG = {"dormant_rightsizing": "dormant_rightsizing_enabled", "dormant_closure": "dormant_closure_enabled",
           "non_reissue_expired_dormant": "dormant_closure_enabled"}
VALUE_TYPES = ["avoided_loss", "cost_saving", "revenue", "lost_profit"]
OUT_COLS = ["accounts_leaving", "unused_removed", "rwa_change", "capital_released", "carrying_before",
            "carrying_after", "drawdown_before", "drawdown_after", "card_profit_change",
            "relationship_adjusted_change", "drawdown_change", "headline_value"] + VALUE_TYPES


def pending(cfg: dict, lever: str) -> bool:
    """A B6 lever whose flag is off: valued, but outside the headline."""
    return lever in B6_FLAG and not cfg["levers"][B6_FLAG[lever]]


def excluded(cfg: dict, lever: str) -> bool:
    """A lever valued for analysts but outside the approved total by policy."""
    return (lever == "transactor_rightsizing"
            and not cfg["levers"]["system_mode"]["transactor_rightsizing_in_approved_value"])


def forward_frame(f: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """The frame the lever values run on: today's unused line and balance
    (the now_* columns from segments.build) under balance_basis.lever_values
    = current, else the 12-month figures unchanged."""
    if cfg["balance_basis"]["lever_values"] != "current":
        return f
    g = f.copy(deep=False)
    for k in X.BALANCE_DEPENDENT:
        g[k] = f[f"now_{k}"]
    return g


def _order(index: pd.Index, seed: int) -> pd.Series:
    """A stable pseudo-random rank per account (same accounts first in every
    scenario, so a larger share targets a superset)."""
    h = [int(hashlib.sha256(f"{seed}:{k}".encode()).hexdigest()[:12], 16) for k in index]
    return pd.Series(h, index=index).rank(method="first")


def sizing(f: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """New line and cut per account under the Lever Guide targets and floors."""
    sm = cfg["levers"]["system_mode"]
    limit = f["limit_current"].fillna(0.0)
    bal = f["balance_current"].fillna(0.0).clip(lower=0)
    target = pd.Series(np.nan, index=f.index)
    for seg, t in sm["decrease_target"].items():
        m = f["rule_segment"] == seg
        base = f["peak_statement_balance_12m"] if t["basis"] == "peak_statement_balance" else f["balance_current"]
        target[m] = np.maximum(base[m].fillna(0.0) * t["multiple"], t["minimum_usd"])
    floor = np.maximum(sm["floor_minimum_line_usd"], bal * sm["floor_balance_multiple"])
    new = np.maximum(target, floor)
    cap = cfg["levers"]["max_reduction_per_review"] * sm["reviews_in_year_one"]
    cut = (limit - new).clip(lower=0).clip(upper=limit * min(cap, 1.0))
    ok = (cut >= limit * sm["min_cut_share"]) & (cut >= sm["min_cut_usd"]) & target.notna()
    cut = cut.where(ok, 0.0)
    return pd.DataFrame({"target_line": target, "floor_line": floor, "cut": cut,
                         "new_line": limit - cut, "cut_possible": ok}, index=f.index)


def select(f: pd.DataFrame, cfg: dict, scenario: str, scope: pd.Series) -> pd.DataFrame:
    """Which accounts each workbook lever targets in a scenario."""
    sm, lv = cfg["levers"]["system_mode"], cfg["workbook"]["levers"][scenario]
    sz = sizing(f, cfg)
    rnd = _order(f.index, sm["selection"]["seed"])
    seg = f["rule_segment"]
    dec = pd.Series(False, index=f.index)
    camp = pd.Series(False, index=f.index)
    close = pd.Series(False, index=f.index)
    for s in A.WORKBOOK_SEGMENTS:
        m = scope & (seg == s)
        n = int(m.sum())
        if not n:
            continue
        # closure: inactive long enough; longest inactive, then largest line first
        elig_c = m & (f["months_since_last_transaction"] >= sm["closure_min_inactive_months"])
        k = min(int(round(lv["closure_share"][s] * n)), int(elig_c.sum()))
        if k:
            r = f.loc[elig_c].sort_values(["months_since_last_transaction", "ucl"], ascending=False).index[:k]
            close[r] = True
        # decrease: accounts where a cut is possible, not closed
        elig_d = m & sz["cut_possible"] & ~close
        k = min(int(round(lv["decrease_share"][s] * n)), int(elig_d.sum()))
        if k:
            key = "pd_12m" if sm["lever_by_segment"][s] == "risk_based_decrease" else "ucl"
            r = f.loc[elig_d].sort_values(key, ascending=False).index[:k]
            dec[r] = True
        k = int(round(lv["campaign_share"][s] * n))
        if k:
            camp[rnd[m].sort_values().index[:k]] = True
    return pd.DataFrame({"decrease": dec, "campaign": camp, "closure": close}, index=f.index).join(sz)


def _params(f: pd.DataFrame, cfg: dict, scenario: str, multiplier: float) -> pd.DataFrame:
    wb, sm = cfg["workbook"], cfg["levers"]["system_mode"]
    st = sm["stress_applies_to"]
    seg = f["rule_segment"]
    get = lambda d: seg.map(d).fillna(0.0).astype(float)  # noqa: E731
    S = {k: {s: v[k] for s, v in wb["segments"].items()} for k in
         ["response_rate", "attrition_after_decrease", "spend_loss_after_decrease", "pd_increase_after_decrease",
          "interchange_rate", "reward_rate"]}
    lv = wb["levers"][scenario]
    m = multiplier
    return pd.DataFrame({
        "attrition": np.minimum(1.0, get(S["attrition_after_decrease"]) * (m if st["attrition"] else 1.0)),
        "spend_loss": np.minimum(1.0, get(S["spend_loss_after_decrease"]) * (m if st["spend_loss"] else 1.0)),
        "pd_uplift": get(S["pd_increase_after_decrease"]) * (m if st["pd_uplift"] else 1.0),
        "response": get(S["response_rate"]) / (m if st["response_rate"] else 1.0),
        "incr_spend": get(lv["incremental_spend"]), "incr_rev": get(lv["incremental_revolving"]),
        "campaign_cost": get(lv["campaign_cost"]),
        "spend_margin_rate": get(S["interchange_rate"]) - get(S["reward_rate"]),
    }, index=f.index)


def _state(f, cfg, cut, bal_add, pd_mult, spend_loss):
    """Card profit, drawdown loss, RWA and carrying cost of a surviving
    account after a cut of `cut` and an added balance of `bal_add`."""
    bal = f["balance"] + bal_add
    ucl = (f["ucl"] - cut - bal_add).clip(lower=0)
    nonq = f["rw_basis"] == "non_qualifying_retail"
    rw = np.where((bal_add > 0) & ~nonq, np.maximum(f["rw"], cfg["capital"]["risk_weight_non_transactor"]), f["rw"])
    pd12 = f["pd_used"]
    lgd = f["lgd"].fillna(cfg["workbook"]["portfolio"]["lgd"])
    core = X._core(bal, ucl, rw, pd12 * pd_mult, lgd, f["leq"], cfg)
    cost_now = f["capital_cost"] + f["liquidity_cost"]
    cost_new = core["capital_cost"] + core["liquidity_cost"]
    credit = pd12 * (pd_mult - 1.0) * lgd * f["balance"] + pd12 * pd_mult * lgd * bal_add
    return {"cost_delta": cost_now - cost_new, "credit": credit, "drawdown": core["drawdown_el"],
            "rwa": core["rwa"], "carrying": core["carrying_cost"], "ucl": ucl}


def value(f: pd.DataFrame, cfg: dict, sel: pd.DataFrame, P: pd.DataFrame, use: dict,
          offer_costs: bool = True) -> pd.DataFrame:
    """Expected annual effect per account of the levers switched on in `use`
    ({"decrease", "closure", "campaign"}: bool), on the selection `sel`.
    offer_costs = False values renewed use without a campaign (no contact
    cost, incentive or promotional give-up): the warning step's 'resume use'."""
    wb = cfg["workbook"]["portfolio"]
    d = sel["decrease"] & use.get("decrease", False)
    c = sel["closure"] & use.get("closure", False)
    k = sel["campaign"] & use.get("campaign", False)
    r = P["response"].where(k, 0.0)
    p_close = c.astype(float) * (1 - r)
    p_alive = 1 - p_close
    resp = np.where(c & k, 1.0, r)                       # responders among the accounts still open
    a = P["attrition"].where(d, 0.0)
    cut = sel["cut"].where(d, 0.0)
    sl = P["spend_loss"].where(d, 0.0)
    up = 1 + P["pd_uplift"].where(d, 0.0)
    margin = (f["interchange"] - f["reward"]).clip(lower=0)
    apr = f["apr"].fillna(0.0)
    resp_rev = P["incr_spend"] * P["spend_margin_rate"] + P["incr_rev"] * (apr - wb["cost_of_funds"])
    camp_cost = np.where(k & offer_costs, P["campaign_cost"] + resp * (wb["incentive_per_responder"]
                                                                       + P["incr_rev"] * wb["promo_cost_rate"]), 0.0)

    n0 = _state(f, cfg, cut, 0.0, up, sl)                     # non-responder survivor
    n1 = _state(f, cfg, cut, P["incr_rev"], up, sl)           # responder survivor
    mix = lambda key: (1 - resp) * n0[key] + resp * n1[key]  # noqa: E731
    surv = p_alive * (1 - a)                                  # share of the account still open
    leave = p_alive * a + p_close                             # share closed or attrited
    var_contrib = f["card_profit"] + f["fixed_cost"]
    gross = var_contrib + f["capital_cost"] + f["liquidity_cost"]   # contribution before capital and liquidity

    cost_saving = surv * mix("cost_delta") + leave * (f["capital_cost"] + f["liquidity_cost"])
    revenue = surv * resp * resp_rev
    lost = -(leave * gross) - surv * (sl * margin + camp_cost)
    credit = -(surv * mix("credit"))
    card_change = cost_saving + revenue + lost + credit
    drawdown_after = surv * mix("drawdown")
    drawdown_change = drawdown_after - f["drawdown_el"]
    rwa_after = surv * mix("rwa")
    out = pd.DataFrame({
        "accounts_leaving": leave,
        "unused_removed": f["ucl"] - surv * mix("ucl"),
        "rwa_change": rwa_after - f["rwa"],
        "carrying_before": f["carrying_cost"], "carrying_after": surv * mix("carrying"),
        "drawdown_before": f["drawdown_el"], "drawdown_after": drawdown_after,
        "card_profit_change": card_change,
        "relationship_adjusted_change": card_change - leave * f["noncard_profit"],
        "drawdown_change": drawdown_change,
        "avoided_loss": credit - drawdown_change, "cost_saving": cost_saving, "revenue": revenue,
        "lost_profit": lost,
    }, index=f.index)
    out["capital_released"] = -out["rwa_change"] * cfg["capital"]["capital_ratio"]
    out["headline_value"] = out["card_profit_change"] - out["drawdown_change"]
    return out


def extra_levers(f: pd.DataFrame, cfg: dict, scope: pd.Series, closed: pd.Series) -> dict[str, pd.DataFrame]:
    """The two assumption-based levers, per account."""
    sm = cfg["levers"]["system_mode"]
    rate = A.annual_capital_cost_rate(cfg)
    outflow = cfg["liquidity"]["lcr_outflow_unused_card_lines"] if A.liquidity_applies(cfg) else 0.0
    lgd = f["lgd"].fillna(cfg["workbook"]["portfolio"]["lgd"])
    pd12 = f["pd_used"]
    per_ucl_carry = cfg["capital"]["ccf_unused_card_lines"] * f["rw"] * rate + outflow * cfg["liquidity"]["negative_carry"]
    per_ucl_el = pd12 * lgd * f["leq"]
    out = {}
    # suppress automatic increases: next year's increase avoided
    e = scope & (f["automatic_increases_12m"] > 0)
    avoided = f["automatic_increase_amount_12m"].where(e, 0.0)
    z = pd.Series(0.0, index=f.index)
    sup = pd.DataFrame({c: z for c in OUT_COLS}, index=f.index)
    sup["unused_removed"] = avoided
    sup["cost_saving"] = avoided * per_ucl_carry
    sup["card_profit_change"] = sup["cost_saving"]
    sup["relationship_adjusted_change"] = sup["cost_saving"]
    sup["avoided_loss"] = avoided * per_ucl_el
    sup["drawdown_change"] = -sup["avoided_loss"]
    sup["rwa_change"] = -avoided * cfg["capital"]["ccf_unused_card_lines"] * f["rw"]
    sup["carrying_before"] = f["carrying_cost"].where(e, 0.0)
    sup["carrying_after"] = sup["carrying_before"]
    sup["headline_value"] = sup["card_profit_change"] - sup["drawdown_change"]
    sup["capital_released"] = 0.0      # growth avoided, not capital released
    sup["eligible"] = e
    out["suppress_automatic_increases"] = sup
    # non-reissue: dormant accounts eligible for closure, card expiring, not closed already
    e2 = (scope & (f["rule_segment"] == "dormant") & f["card_expires_within_12m"].fillna(False).astype(bool)
          & (f["months_since_last_transaction"] >= sm["closure_min_inactive_months"]) & ~closed)
    w = e2.astype(float)
    gross = f["card_profit"] + f["fixed_cost"] + f["capital_cost"] + f["liquidity_cost"]
    nr = pd.DataFrame({c: z for c in OUT_COLS}, index=f.index)
    nr["accounts_leaving"] = w
    nr["unused_removed"] = w * f["ucl"]
    nr["rwa_change"] = -w * f["rwa"]
    nr["carrying_before"] = w * f["carrying_cost"]
    nr["drawdown_before"] = w * f["drawdown_el"]
    nr["cost_saving"] = w * (f["capital_cost"] + f["liquidity_cost"] + f["reissue_cost_mean"].fillna(0.0))
    nr["lost_profit"] = -w * gross
    nr["drawdown_change"] = -w * f["drawdown_el"]
    nr["avoided_loss"] = -nr["drawdown_change"]
    nr["card_profit_change"] = nr["cost_saving"] + nr["lost_profit"]
    nr["relationship_adjusted_change"] = nr["card_profit_change"] - w * f["noncard_profit"]
    nr["capital_released"] = -nr["rwa_change"] * cfg["capital"]["capital_ratio"]
    nr["headline_value"] = nr["card_profit_change"] - nr["drawdown_change"]
    nr["eligible"] = e2
    out["non_reissue_expired_dormant"] = nr
    return out


def scope_mask(f: pd.DataFrame, cfg: dict) -> pd.Series:
    """B7: workbook scope = the screened population; full line management =
    every open, seasoned card account (the screen's profit, utilisation and
    unused tests dropped). L2's increase valuation is not duplicated here.
    Protected (suppressed) customers are outside scope in both modes."""
    base = (f["screened"] if cfg["levers"]["scope_mode"] == "workbook_unprofitable_low_use"
            else f["met:screen.open"] & f["met:screen.history"] & f["met:screen.not_fraud_blocked"])
    # Protected customers (the system's suppression: hardship, SCRA, ...) get
    # no action, before anything else (brief s.3).
    if "protected" in f:
        base = base & ~f["protected"].fillna(False).astype(bool)
    return base


def run(f: pd.DataFrame, cfg: dict, scenario: str = "base", multiplier: float = 1.0) -> dict:
    """One scenario: per-account effects of every lever on its own, the
    combined headline (B6 levers excluded while their flag is off), and the
    pending-approval and extra-lever values."""
    f = forward_frame(f, cfg)
    scope = scope_mask(f, cfg)
    sel = select(f, cfg, scenario, scope)
    P = _params(f, cfg, scenario, multiplier)
    lever_of_seg = f["rule_segment"].map(cfg["levers"]["system_mode"]["lever_by_segment"])
    per = {}
    for lever in ["line_decrease", "risk_based_decrease", "dormant_rightsizing", "transactor_rightsizing"]:
        s2 = sel.copy()
        s2["decrease"] = sel["decrease"] & (lever_of_seg == lever)
        per[lever] = value(f, cfg, s2, P, {"decrease": True})
    per["dormant_closure"] = value(f, cfg, sel, P, {"closure": True})
    per["engagement_campaign"] = value(f, cfg, sel, P, {"campaign": True})
    # combined headline: every workbook lever whose flag allows it
    s3 = sel.copy()
    for lever in ["dormant_rightsizing", "transactor_rightsizing"]:
        if pending(cfg, lever) or excluded(cfg, lever):
            s3["decrease"] = s3["decrease"] & (lever_of_seg != lever)
    use = {"decrease": True, "campaign": True, "closure": not pending(cfg, "dormant_closure")}
    combined = value(f, cfg, s3, P, use)
    extra = extra_levers(f, cfg, scope, sel["closure"] & use["closure"])
    per.update(extra)
    return {"scenario": scenario, "multiplier": multiplier, "selection": sel, "params": P,
            "combined": combined, "per_lever": per, "scope": scope, "frame": f}


def lever_table(res: dict, cfg: dict, frame: pd.DataFrame) -> pd.DataFrame:
    """One row per lever: totals of every output, its group (workbook /
    extra) and status (headline / pending approval / excluded by policy)."""
    rows = {}
    for lever, eff in res["per_lever"].items():
        t = eff[OUT_COLS].sum()
        t["accounts_targeted"] = float(_targeted(res, lever, frame).sum())
        t["group"] = "extra (assumption-based; not in the reference workbook)" if lever in EXTRA_LEVERS else "workbook"
        t["status"] = ("pending approval" if pending(cfg, lever)
                       else "excluded by policy" if excluded(cfg, lever) else "headline")
        rows[LEVER_LABELS[lever]] = t
    return pd.DataFrame(rows).T


def _targeted(res: dict, lever: str, frame: pd.DataFrame) -> pd.Series:
    sel = res["selection"]
    if lever in ("line_decrease", "risk_based_decrease", "dormant_rightsizing", "transactor_rightsizing"):
        e = res["per_lever"][lever]
        return sel["decrease"] & (e["unused_removed"].abs() > 0)
    if lever == "dormant_closure":
        return sel["closure"]
    if lever == "engagement_campaign":
        return sel["campaign"]
    return res["per_lever"][lever]["eligible"]


def segment_table(res: dict, cfg: dict, frame: pd.DataFrame) -> pd.DataFrame:
    """Combined headline effect by segment."""
    c = res["combined"].join(frame[["rule_segment"]])
    g = c[res["scope"]].groupby("rule_segment")[OUT_COLS].sum()
    g = g.reindex(cfg["segments"]["order"]).fillna(0.0)
    g.loc["total"] = g.sum()
    return g


def summary(res: dict, cfg: dict, frame: pd.DataFrame) -> dict:
    """Headline totals with the extra levers and pending levers apart.
    Capital released is reported on its own and never added to annual values."""
    comb = res["combined"][res["scope"]][OUT_COLS].sum()
    lt = lever_table(res, cfg, frame)
    extra = lt[lt["group"] != "workbook"]
    pend = lt[lt["status"] == "pending approval"]
    annual = ["card_profit_change", "relationship_adjusted_change", "drawdown_change", "headline_value"]
    return {
        "scenario": res["scenario"], "multiplier": res["multiplier"],
        "workbook_levers_headline": {k: float(comb[k]) for k in annual + ["accounts_leaving", "unused_removed",
                                                                           "rwa_change"] + VALUE_TYPES},
        "extra_levers": {k: float(extra.loc[extra["status"] == "headline", k].sum()) for k in annual},
        "pending_approval": {k: float(pend[k].sum()) for k in annual},
        "capital_released_one_time": float(comb["capital_released"]),
        "capital_released_extra_one_time": float(extra.loc[extra["status"] == "headline", "capital_released"].sum()),
    }


def stress(frame: pd.DataFrame, cfg: dict, scenario: str = "base") -> pd.DataFrame:
    rows = []
    for m in cfg["stress_test"]["multipliers"]:
        s = summary(run(frame, cfg, scenario, m), cfg, frame)
        rows.append({"multiplier": m, **{f"wb_{k}": v for k, v in s["workbook_levers_headline"].items()},
                     "capital_released_one_time": s["capital_released_one_time"]})
    df = pd.DataFrame(rows).set_index("multiplier")
    go = cfg["stress_test"]["go_no_go_multiplier"]
    df.attrs["go_no_go"] = {"multiplier": go, "headline_value": float(df.loc[go, "wb_headline_value"]),
                            "card_profit_change": float(df.loc[go, "wb_card_profit_change"]),
                            "go": bool(df.loc[go, "wb_headline_value"] > 0)}
    df.attrs["go_no_go"]["statement"] = robustness_statement(df)
    return df


def robustness_statement(stv: pd.DataFrame) -> str:
    """B6: the go / no-go result with its basis stated, from the results:
    the headline basis (card profit + reduced drawdown loss) and where card
    profit alone turns negative."""
    go = stv.attrs["go_no_go"]
    m = go["multiplier"]
    neg = stv.index[stv["wb_card_profit_change"] < 0]
    out = f"{'Passes' if go['go'] else 'Fails'} at {m:g}x on value including reduced risk"
    if not len(neg):
        return out + "; card profit alone stays positive at every multiplier tested"
    first = float(neg.min())
    if first <= float(stv.index.min()):
        return out + f"; card profit alone is negative already at {first:g}x"
    return out + f"; card profit alone turns negative at {first:g}x"
