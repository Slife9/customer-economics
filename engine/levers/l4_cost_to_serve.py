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
        return cv[routed | migratable].copy()

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
                          f"in trailing window"), axis=1)
        return wl[["Masked Customer Number", "action", "reason",
                  "avoidable_calls", "paper_statements"]]

    def driver(self, customer_view: pd.DataFrame) -> float:
        """Total avoidable driver volume portfolio-wide - should shrink under
        higher digital deflection and better collections efficiency."""
        d = self.drivers
        avoidable = d["Primary Call Reason"].isin(AVOIDABLE_CALL_REASONS).sum()
        paper = d["Paper Statements Produced"].sum() if "Paper Statements Produced" in d.columns else 0
        return float(avoidable + paper)
