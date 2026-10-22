"""L4 - Cost-to-serve migration. No customer-contact gate, usually the
fastest lever to prove.

Valuation (SPEC_lever_valuation_rebuild.md 4.4), correcting three defects:
  1. Annual means annual: the driver table is restricted to the trailing 12
     cycles before summing (the old method summed the full history).
  2. Only avoidable calls count (billing / rewards / rate queries), one per
     account-cycle whose recorded primary call reason is avoidable - Table 12
     records one primary reason per account per month, so this counts what
     is actually observed as avoidable rather than assuming every call that
     month shared it.
  3. A deflected call still costs digital sessions; a migrated statement
     still costs an e-statement. Unit costs are read from the cost pools
     (Table 11), falling back to lever_assumptions.json only if a pool is
     absent.

Capacity steps: the staffing (fixed) step a lower call volume might cross is
reported in extras ONLY, never in the total - the demo cost-pool bands are
scaled for a 5-8k account book and must be recalibrated for a real portfolio.
"""
from __future__ import annotations
import pandas as pd

from .base import Lever, SizeResult, component, scenario
from . import assumptions as ASSUME

AVOIDABLE_CALL_REASONS = {"billing_query", "rewards_query", "rate_query"}
TRAILING_CYCLES = 12
POOL_ACTIVITY = {"call": "contact_center_call", "digital_session": "digital_session",
                 "paper_statement": "statement_paper",
                 "electronic_statement": "statement_electronic"}

METHOD_NOTE = (
    "Trailing-12-cycle avoidable calls (billing, rewards, rate) and paper "
    "statements for this population. Saving per deflected call = call unit "
    "cost - digital session cost x sessions per deflected call; saving per "
    "migrated statement = paper - electronic statement cost (unit costs from "
    "the cost pools, Table 11). Scaled by the assumed deflection / migration "
    "rates, net of an excluded share (customers who must keep paper or phone "
    "service). Year 1 also pays a one-off outreach cost per customer.")


def _band(volume: float, bands: pd.DataFrame) -> tuple[float, float]:
    for _, b in bands.iterrows():
        if b["Volume Band From"] <= volume < b["Volume Band To"]:
            return float(b["Band Fixed Cost USD Monthly"]), float(b["Marginal Unit Cost USD"])
    last = bands.iloc[-1]
    return float(last["Band Fixed Cost USD Monthly"]), float(last["Marginal Unit Cost USD"])


def trailing_window(drivers: pd.DataFrame, n: int = TRAILING_CYCLES) -> pd.DataFrame:
    cycles = sorted(drivers["Cycle Month"].unique())[-n:]
    return drivers[drivers["Cycle Month"].isin(cycles)]


def customer_trailing_counts(drivers: pd.DataFrame) -> pd.DataFrame:
    """Per-customer annual avoidable calls and paper statements over the
    trailing 12 cycles (scaled to 12 months only if fewer cycles exist)."""
    window = trailing_window(drivers)
    n = int(window["Cycle Month"].nunique())
    scale = TRAILING_CYCLES / n if 0 < n < TRAILING_CYCLES else 1.0
    g = window.groupby("Masked Customer Number").agg(
        annual_avoidable_calls_t12=("Primary Call Reason",
                                    lambda s: s.isin(AVOIDABLE_CALL_REASONS).sum()),
        annual_paper_statements_t12=("Paper Statements Produced", "sum")).reset_index()
    g[["annual_avoidable_calls_t12", "annual_paper_statements_t12"]] = (
        g[["annual_avoidable_calls_t12", "annual_paper_statements_t12"]].astype(float) * scale)
    return g


def _pre_rebuild_figure(population: pd.DataFrame, drivers: pd.DataFrame,
                        pools: pd.DataFrame) -> dict:
    """The pre-rebuild L4 figure, recomputed exactly as the old size() did
    (full history, all contact-centre calls, gross unit cost, plus any
    capacity-step saving) - kept ONLY as the starting point of the page's
    correction bridge, never as a value."""
    ids = set(population["Masked Customer Number"].dropna())
    drv = drivers[drivers["Masked Customer Number"].isin(ids)]
    marginal_total, step_total, unit = 0.0, 0.0, {}
    for activity, col in [("contact_center_call", "Contact Center Calls"),
                          ("statement_paper", "Paper Statements Produced")]:
        bands = pools[pools["Activity"] == activity]
        if not len(bands) or col not in drivers.columns:
            continue
        total_all = drivers[col].sum()
        avoidable = drv[col].sum()
        if avoidable <= 0:
            continue
        fixed_before, marginal = _band(total_all, bands)
        fixed_after, _ = _band(max(total_all - avoidable, 0), bands)
        unit[activity] = marginal
        marginal_total += avoidable * marginal
        if fixed_after < fixed_before:
            step_total += fixed_before - fixed_after
    return {"marginal_usd": float(marginal_total), "step_usd": float(step_total),
            "all_calls_full_history": float(drv["Contact Center Calls"].sum()),
            "avoidable_calls_full_history": float(
                drv["Primary Call Reason"].isin(AVOIDABLE_CALL_REASONS).sum()),
            "paper_full_history": float(drv["Paper Statements Produced"].sum()),
            "gross_unit_cost": unit}


def valuation_inputs(population: pd.DataFrame, drivers: pd.DataFrame,
                     pools: pd.DataFrame, config_unit_costs: dict) -> dict:
    window = trailing_window(drivers)
    n_window_cycles = int(window["Cycle Month"].nunique())
    ids = set(population["Masked Customer Number"].dropna())
    mine = window[window["Masked Customer Number"].isin(ids)]
    annual_calls = float(mine["Primary Call Reason"].isin(AVOIDABLE_CALL_REASONS).sum())
    annual_paper = float(mine["Paper Statements Produced"].sum())
    # Scale up only if fewer than 12 cycles exist (never the case for a
    # 36-cycle portfolio, but annual must stay annual on a short extract).
    if 0 < n_window_cycles < TRAILING_CYCLES:
        annual_calls *= TRAILING_CYCLES / n_window_cycles
        annual_paper *= TRAILING_CYCLES / n_window_cycles

    monthly_calls_all = float(window.groupby("Cycle Month")["Contact Center Calls"].sum().mean())
    unit_costs, sources = {}, {}
    for key, activity in POOL_ACTIVITY.items():
        bands = pools[pools["Activity"] == activity]
        if len(bands):
            vol = monthly_calls_all if key == "call" else 0.0
            unit_costs[key] = _band(vol, bands)[1]
            sources[key] = "cost pool (Table 11)"
        else:
            unit_costs[key] = float(config_unit_costs[key])
            sources[key] = "lever_assumptions.json (no cost pool)"

    call_bands = pools[pools["Activity"] == "contact_center_call"]
    return {
        "customers": int(len(population)),
        "window_cycles": n_window_cycles,
        "annual_avoidable_calls": annual_calls,
        "annual_paper_statements": annual_paper,
        "unit_costs": unit_costs,
        "unit_cost_sources": sources,
        "portfolio_monthly_calls": monthly_calls_all,
        "call_bands": [
            {"from": float(b["Volume Band From"]), "to": float(b["Volume Band To"]),
             "fixed_monthly_usd": float(b["Band Fixed Cost USD Monthly"])}
            for _, b in call_bands.iterrows()],
        "population_trailing_12m_cost_to_serve": float(population["cost_to_serve"].sum()),
        "pre_rebuild": _pre_rebuild_figure(population, drivers, pools),
    }


def _fixed_for(volume: float, bands: list) -> float:
    for b in bands:
        if b["from"] <= volume < b["to"]:
            return b["fixed_monthly_usd"]
    return bands[-1]["fixed_monthly_usd"] if bands else 0.0


def value_scenarios(inputs: dict, a: dict) -> dict:
    c = inputs["unit_costs"]
    call_saving = c["call"] - c["digital_session"] * float(a["sessions_per_deflected_call"])
    paper_saving = c["paper_statement"] - c["electronic_statement"]
    calls, paper, n = (inputs["annual_avoidable_calls"], inputs["annual_paper_statements"],
                       inputs["customers"])
    out = {}
    for s in ASSUME.SCENARIOS:
        keep = 1 - ASSUME.pick(a["excluded_share"], s)
        deflected = calls * ASSUME.pick(a["call_deflection"], s) * keep
        comp = {
            "calls_to_self_service": component(deflected * call_saving, "cost_saving", "assumption"),
            "paper_to_electronic": component(
                paper * ASSUME.pick(a["paper_migration"], s) * keep * paper_saving,
                "cost_saving", "assumption"),
            "outreach_cost_year1": component(
                -n * ASSUME.pick(a["outreach_cost_usd"], s), "cost", "measured"),
        }
        sc = scenario(comp)
        before = inputs["portfolio_monthly_calls"]
        after = max(before - deflected / 12, 0.0)
        fixed_before = _fixed_for(before, inputs["call_bands"])
        fixed_after = _fixed_for(after, inputs["call_bands"])
        sc["extras"] = {
            "from_year2": comp["calls_to_self_service"]["value_usd"]
                          + comp["paper_to_electronic"]["value_usd"],
            "annual_avoidable_calls": calls,
            "annual_paper_statements": paper,
            "avoided_calls_per_month": deflected / 12,
            "saving_per_deflected_call_usd": call_saving,
            "saving_per_migrated_statement_usd": paper_saving,
            "staffing_step": {
                "monthly_calls_before": before, "monthly_calls_after": after,
                "fixed_cost_monthly_before_usd": fixed_before,
                "fixed_cost_monthly_after_usd": fixed_after,
                "annual_step_saving_usd": 12 * (fixed_before - fixed_after),
                "note": ("Reported for information only, never in the total. The "
                         "demo cost-pool bands are scaled for a 5-8k account book "
                         "and must be recalibrated for a real portfolio."),
            },
        }
        out[s] = sc
    return out


class L4CostToServe(Lever):
    code = "L4"
    name = "Cost-to-serve migration"
    gates = []

    def __init__(self, drivers: pd.DataFrame, pools: pd.DataFrame):
        self.drivers = drivers
        self.pools = pools[pools["Allocation Tier"] != "Tier 3"]

    def population(self, pop) -> pd.DataFrame:
        pop = super().population(pop)
        cv = pop.frame
        routed = cv["routed_lever"] == "L4"
        # Broader migration candidates: high avoidable-call volume or paper
        # statement delivery, independent of whether they are yet a loss.
        # Drivers are keyed by account; roll to customer via the SAME
        # customer number the driver table already carries (one join, not
        # a coincidental key match on today's 1:1 card cardinality).
        cust_drv = self.drivers.groupby("Masked Customer Number").agg(
            avoidable_calls=("Primary Call Reason",
                            lambda s: s.isin(AVOIDABLE_CALL_REASONS).sum()),
            paper_statements=("Paper Statements Produced", "sum"),
        ).reset_index()
        cv = cv.merge(cust_drv, on="Masked Customer Number", how="left")
        cv["avoidable_calls"] = cv["avoidable_calls"].fillna(0)
        cv["paper_statements"] = cv["paper_statements"].fillna(0)
        migratable = (cv["avoidable_calls"] >= 3) | (cv["paper_statements"] >= 6)
        out = cv[routed | migratable].copy()
        # Additive (not used by the population rule above, which is
        # unchanged): each customer's own trailing-12-cycle volumes - the
        # figures the valuation and the drill-down's per-customer trace use.
        t12 = customer_trailing_counts(self.drivers)
        out = out.merge(t12, on="Masked Customer Number", how="left")
        out[["annual_avoidable_calls_t12", "annual_paper_statements_t12"]] = out[
            ["annual_avoidable_calls_t12", "annual_paper_statements_t12"]].fillna(0.0)
        return out

    def size(self, population: pd.DataFrame) -> SizeResult:
        a = self.lever_assumptions()
        inputs = valuation_inputs(population, self.drivers, self.pools, a["unit_costs"])
        scen = value_scenarios(inputs, a)
        base = scen["base"]
        return SizeResult(
            priced_value_usd=round(base["total_usd"], 2),
            basis=METHOD_NOTE,
            caveat=(f"Assumption-based (deflection and migration rates), pilot "
                    f"required. From year 2 (no outreach cost): "
                    f"${base['extras']['from_year2']:,.0f}/yr. Any staffing-step "
                    f"saving is reported separately and never included."),
            unpriced_context_usd=None,
            scenarios=scen, assumptions_used=a, method_note=METHOD_NOTE,
            inputs=inputs, gate_value_usd=base["total_usd"])

    def worklist(self, population: pd.DataFrame) -> pd.DataFrame:
        wl = population.copy()
        wl["action"] = "REVIEW"
        wl.loc[wl["paper_statements"] >= 6, "action"] = "MIGRATE_TO_DIGITAL_STATEMENTS"
        wl.loc[wl["avoidable_calls"] >= 3, "action"] = "ENABLE_SELF_SERVICE"
        wl["reason"] = wl.apply(
            lambda r: (r["routing_reason"] if r.get("routed_lever") == "L4"
                      else f"{int(r['avoidable_calls'])} avoidable calls, "
                          f"{int(r['paper_statements'])} paper statements "
                          f"over the full data window"), axis=1)
        return wl[["Masked Customer Number", "action", "reason",
                  "avoidable_calls", "paper_statements",
                  "annual_avoidable_calls_t12", "annual_paper_statements_t12"]]

    def driver(self, customer_view: pd.DataFrame) -> float:
        """Total avoidable driver volume portfolio-wide - should shrink under
        higher digital deflection and better collections efficiency."""
        d = self.drivers
        avoidable = d["Primary Call Reason"].isin(AVOIDABLE_CALL_REASONS).sum()
        paper = d["Paper Statements Produced"].sum() if "Paper Statements Produced" in d.columns else 0
        return float(avoidable + paper)


# ---------------------------------------------------------------------------
# Explanations for the customer drill-down. Additive only: same thresholds
# and formulas as population()/value_scenarios(); the audit checks that
# customer contributions sum to the components and steps equal them.

AVOIDABLE_CALL_THRESHOLD = 3
PAPER_STATEMENT_THRESHOLD = 6


def selection_rules(row) -> dict:
    calls, paper = row["avoidable_calls"], row["paper_statements"]
    sets = {
        "ENABLE_SELF_SERVICE (avoidable calls)": [
            {"rule": "Avoidable calls (billing / rewards / rate), full data window",
             "threshold": f">= {AVOIDABLE_CALL_THRESHOLD}", "actual": f"{calls:.0f}",
             "met": bool(calls >= AVOIDABLE_CALL_THRESHOLD)}],
        "MIGRATE_TO_DIGITAL_STATEMENTS (paper statements)": [
            {"rule": "Paper statements, full data window", "threshold": f">= {PAPER_STATEMENT_THRESHOLD}",
             "actual": f"{paper:.0f}", "met": bool(paper >= PAPER_STATEMENT_THRESHOLD)}],
        "REVIEW (routed servicing-cost loss)": [
            {"rule": "Routed to L4 (servicing cost this customer caused dominates a below-cost "
                     "relationship)", "threshold": "routed_lever = L4",
             "actual": str(row.get("routed_lever")), "met": row.get("routed_lever") == "L4"}],
    }
    matched = next((k for k, r in sets.items() if all(x["met"] for x in r)), None)
    return {"matched": matched, "rule_sets": sets,
            "precedence": ("Any one rule set is enough to be in scope. The action follows the "
                           "first one met: self-service if calls qualify, else digital statements "
                           "if paper qualifies, else review (routed).")}


def _unit_savings(inputs: dict, a: dict) -> tuple:
    c = inputs["unit_costs"]
    return (c["call"] - c["digital_session"] * float(a["sessions_per_deflected_call"]),
            c["paper_statement"] - c["electronic_statement"])


def customer_contributions(rows: pd.DataFrame, inputs: dict, a: dict,
                           scenario: str = "base") -> pd.DataFrame:
    call_saving, paper_saving = _unit_savings(inputs, a)
    keep = 1 - ASSUME.pick(a["excluded_share"], scenario)
    out = pd.DataFrame(index=rows.index)
    out["calls_to_self_service"] = (rows["annual_avoidable_calls_t12"].fillna(0)
                                    * ASSUME.pick(a["call_deflection"], scenario) * keep * call_saving)
    out["paper_to_electronic"] = (rows["annual_paper_statements_t12"].fillna(0)
                                  * ASSUME.pick(a["paper_migration"], scenario) * keep * paper_saving)
    out["outreach_cost_year1"] = -float(ASSUME.pick(a["outreach_cost_usd"], scenario))
    out["total"] = out.sum(axis=1)
    return out


def customer_trace(row, inputs: dict, a: dict, scenario: str = "base") -> list:
    c = customer_contributions(pd.DataFrame([row]), inputs, a, scenario).iloc[0]
    call_saving, paper_saving = _unit_savings(inputs, a)
    u = inputs["unit_costs"]
    keep = 1 - ASSUME.pick(a["excluded_share"], scenario)
    return [
        {"component": "saving per deflected call",
         "formula": "call cost - digital session cost x sessions per deflected call",
         "substituted": f"${u['call']:.2f} - ${u['digital_session']:.2f} x {a['sessions_per_deflected_call']}",
         "value": call_saving},
        {"component": "calls_to_self_service",
         "formula": "this customer's avoidable calls (trailing 12 cycles) x call_deflection x "
                    "(1 - excluded_share) x saving per call",
         "substituted": (f"{row['annual_avoidable_calls_t12']:.0f} x "
                         f"{ASSUME.pick(a['call_deflection'], scenario)} x {keep:.2f} x ${call_saving:.2f}"),
         "value": c["calls_to_self_service"]},
        {"component": "paper_to_electronic",
         "formula": "this customer's paper statements (trailing 12 cycles) x paper_migration x "
                    "(1 - excluded_share) x (paper - e-statement cost)",
         "substituted": (f"{row['annual_paper_statements_t12']:.0f} x "
                         f"{ASSUME.pick(a['paper_migration'], scenario)} x {keep:.2f} x ${paper_saving:.2f}"),
         "value": c["paper_to_electronic"]},
        {"component": "outreach_cost_year1", "formula": "one outreach per customer, year 1 only",
         "substituted": f"-${ASSUME.pick(a['outreach_cost_usd'], scenario)}", "value": c["outreach_cost_year1"]},
        {"component": "TOTAL year 1 (expected value, base assumptions)", "formula": "sum of the above",
         "substituted": "", "value": c["total"]},
        {"component": "Staffing step", "formula": "portfolio level only - a lower call volume removes "
                      "cash only if the whole book crosses a capacity band; never allocated to a customer",
         "substituted": "", "value": float("nan")},
    ]


def calculation_steps(inputs: dict, a: dict, scenario: str = "base") -> list:
    call_saving, paper_saving = _unit_savings(inputs, a)
    keep = 1 - ASSUME.pick(a["excluded_share"], scenario)
    calls, paper, n = (inputs["annual_avoidable_calls"], inputs["annual_paper_statements"],
                       inputs["customers"])
    defl = ASSUME.pick(a["call_deflection"], scenario)
    migr = ASSUME.pick(a["paper_migration"], scenario)
    out_c = ASSUME.pick(a["outreach_cost_usd"], scenario)
    u = inputs["unit_costs"]
    return [
        {"component": "saving per deflected call",
         "formula": "call - digital session x sessions_per_deflected_call (Table 11 unit costs)",
         "substituted": f"${u['call']:.2f} - ${u['digital_session']:.2f} x {a['sessions_per_deflected_call']}",
         "value": call_saving},
        {"component": "saving per migrated statement", "formula": "paper - electronic statement",
         "substituted": f"${u['paper_statement']:.2f} - ${u['electronic_statement']:.2f}", "value": paper_saving},
        {"component": "calls_to_self_service",
         "formula": "annual avoidable calls x call_deflection x (1 - excluded_share) x saving per call",
         "substituted": f"{calls:,.0f} x {defl} x {keep:.2f} x ${call_saving:.2f}",
         "value": calls * defl * keep * call_saving},
        {"component": "paper_to_electronic",
         "formula": "annual paper statements x paper_migration x (1 - excluded_share) x saving per statement",
         "substituted": f"{paper:,.0f} x {migr} x {keep:.2f} x ${paper_saving:.2f}",
         "value": paper * migr * keep * paper_saving},
        {"component": "outreach_cost_year1", "formula": "-customers x outreach_cost_usd",
         "substituted": f"-{n:,} x ${out_c}", "value": -n * out_c},
    ]


def correction_bridge(inputs: dict, a: dict, scenario: str = "base") -> list:
    """From the pre-rebuild system figure to the corrected year-1 value, one
    correction at a time. Each row is the running figure after that step."""
    pre = inputs.get("pre_rebuild")
    if not pre:
        return []
    g = pre["gross_unit_cost"]
    m_call = g.get("contact_center_call", inputs["unit_costs"]["call"])
    m_paper = g.get("statement_paper", inputs["unit_costs"]["paper_statement"])
    call_saving, paper_saving = _unit_savings(inputs, a)
    keep = 1 - ASSUME.pick(a["excluded_share"], scenario)
    calls, paper = inputs["annual_avoidable_calls"], inputs["annual_paper_statements"]
    y2 = (calls * ASSUME.pick(a["call_deflection"], scenario) * keep * call_saving
          + paper * ASSUME.pick(a["paper_migration"], scenario) * keep * paper_saving)
    y1 = y2 - inputs["customers"] * ASSUME.pick(a["outreach_cost_usd"], scenario)
    return [
        {"step": "Pre-rebuild system figure",
         "what": "all calls and paper statements, 3 years, gross unit cost, plus capacity-step saving",
         "value": pre["marginal_usd"] + pre["step_usd"]},
        {"step": "Capacity-step saving moved to extras",
         "what": "a step saving is never counted in the value", "value": pre["marginal_usd"]},
        {"step": "Only avoidable calls",
         "what": f"{pre['all_calls_full_history']:,.0f} -> {pre['avoidable_calls_full_history']:,.0f} calls",
         "value": pre["avoidable_calls_full_history"] * m_call + pre["paper_full_history"] * m_paper},
        {"step": "Annual, not 3 years (trailing 12 cycles)",
         "what": f"{calls:,.0f} avoidable calls, {paper:,.0f} paper statements a year",
         "value": calls * m_call + paper * m_paper},
        {"step": "Net of digital replacement cost",
         "what": f"${call_saving:.2f} per call, ${paper_saving:.2f} per statement",
         "value": calls * call_saving + paper * paper_saving},
        {"step": "Only what customers actually move (assumptions)",
         "what": "x deflection / migration rate x (1 - excluded share) = from year 2", "value": y2},
        {"step": "Less year-1 outreach = corrected year-1 value",
         "what": f"-{inputs['customers']:,} customers x outreach cost", "value": y1},
    ]
