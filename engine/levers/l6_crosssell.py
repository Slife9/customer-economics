"""L6 - Cross-sell and growth by value (channel quality review).

DEVIATION FROM THE LITERAL CONCEPT: the spec frames L6 as steering
"acquisition and cross-sell toward customers who actually earn." A per-
customer cross-sell take-up prediction is exactly the kind of causal
question section 7 forbids. This lever is built instead as CHANNEL QUALITY
REVIEW: rank acquisition channels by the customer value they actually
produced per acquisition dollar - a backward-looking finding about channels
already run, not a forward prediction about individuals.

Valuation (SPEC_lever_valuation_rebuild.md 4.6), correcting two defects:
  - Flow, not stock: moving budget changes only FUTURE acquisitions, so the
    value is a budget-neutral shift of the worst channel's annual spend to
    the best channel - never "gap x every existing account in the worst
    channel".
  - Units: one-off acquisition cost (CAC) is no longer subtracted from
    annual profit; channels are ranked by trailing-12m NEP per CAC dollar.
Valued at CHANNEL level - there is no per-customer figure.
"""
from __future__ import annotations
import pandas as pd

from .base import Lever, SizeResult, component, scenario
from . import assumptions as ASSUME

K = "Masked Customer Number"
IN_WINDOW_STATUSES = ("Recovered", "Not yet recovered")

METHOD_NOTE = (
    "Channel-level, using customers acquired within the observation window. "
    "Channels are ranked by mean trailing-12m NEP per dollar of acquisition "
    "cost. A configured share of the worst channel's annual acquisition "
    "spend moves to the best channel: the worst channel loses the customers "
    "that budget would have bought; the best channel gains customers at a "
    "higher marginal CAC and assumed lower incremental quality. Year-1 flow; "
    "a multi-year build is shown separately.")


def valuation_inputs(cv: pd.DataFrame, n_cycles: int) -> dict:
    years = n_cycles / 12 if n_cycles else 0.0
    if "acquisition_cost_usd" not in cv.columns or "acquisition_channel" not in cv.columns:
        return {"available": False, "reason": "no acquisition channel / cost data",
                "window_years": years, "channels": []}
    c = cv[cv["acquisition_channel"].notna()
           & cv["cac_payback_status"].astype(str).isin(IN_WINDOW_STATUSES)
           & cv["acquisition_cost_usd"].notna()]
    if not len(c):
        return {"available": False, "window_years": years, "channels": [],
                "reason": ("no customers with an acquisition cost were acquired "
                           "within the observation window")}
    g = (c.assign(acquisition_channel=c["acquisition_channel"].astype(str))
          .groupby("acquisition_channel")
          .agg(n=(K, "size"), nep=("trailing_12m_net_economic_profit", "mean"),
               cac=("acquisition_cost_usd", "mean"), spend=("acquisition_cost_usd", "sum")))
    g = g[g["cac"] > 0]
    if len(g) < 2:
        return {"available": False, "window_years": years, "channels": [],
                "reason": "fewer than two channels with acquisition cost data"}
    g["value_per_dollar"] = g["nep"] / g["cac"]
    rows = [{"channel": ch, "customers_in_window": int(r["n"]),
             "new_customers_per_year": float(r["n"] / years) if years else None,
             "mean_cac_usd": float(r["cac"]), "mean_trailing_12m_nep_usd": float(r["nep"]),
             "nep_per_cac_dollar": float(r["value_per_dollar"]),
             "annual_acquisition_spend_usd": float(r["spend"] / years) if years else None,
             "payback_years_simple": (float(r["cac"] / r["nep"]) if r["nep"] > 0 else None)}
            for ch, r in g.sort_values("value_per_dollar", ascending=False).iterrows()]
    return {"available": True, "window_years": years,
            "worst": g["value_per_dollar"].idxmin(), "best": g["value_per_dollar"].idxmax(),
            "channels": rows,
            "annual_acquisition_spend_usd": float(g["spend"].sum() / years) if years else 0.0}


def value_scenarios(inputs: dict, a: dict) -> dict:
    if not inputs.get("available"):
        return {}
    by = {r["channel"]: r for r in inputs["channels"]}
    w, b = by[inputs["worst"]], by[inputs["best"]]
    shifted = float(a["budget_shift_share"]) * w["annual_acquisition_spend_usd"]
    lost_n = shifted / w["mean_cac_usd"]
    r = 1 - float(a["annual_attrition"])
    build = sum(r ** i for i in range(int(a["build_years"])))
    out = {}
    for s in ASSUME.SCENARIOS:
        mult = ASSUME.pick(a["marginal_cac_multiplier"], s)
        q = ASSUME.pick(a["incremental_quality"], s)
        gained_n = shifted / (b["mean_cac_usd"] * mult)
        comp = {
            "profit_lost_worst_channel": component(
                -lost_n * w["mean_trailing_12m_nep_usd"], "lost_profit", "assumption"),
            "profit_gained_best_channel": component(
                gained_n * b["mean_trailing_12m_nep_usd"] * q, "revenue", "assumption"),
        }
        sc = scenario(comp)
        sc["extras"] = {
            "after_n_years": sc["total_usd"] * build,
            "build_years": int(a["build_years"]),
            "worst": inputs["worst"], "best": inputs["best"],
            "budget_shifted_usd": shifted,
            "customers_lost": lost_n, "customers_gained": gained_n,
            "breakeven_quality": (w["nep_per_cac_dollar"]
                                  / (b["mean_trailing_12m_nep_usd"] / (b["mean_cac_usd"] * mult))),
            "annual_acquisition_spend_usd": inputs["annual_acquisition_spend_usd"],
            "channel_table": inputs["channels"],
        }
        out[s] = sc
    return out


class L6CrossSell(Lever):
    code = "L6"
    name = "Cross-sell and growth by value (channel quality review)"
    gates = []

    def __init__(self, acquisition: pd.DataFrame, accounts: pd.DataFrame,
                 n_cycles: int = 36):
        self.acquisition = acquisition
        self.n_cycles = n_cycles
        # If cost data wasn't part of this upload, rank by gross value only
        # and say so explicitly - never assume a cost. A missing column here
        # degrades this one lever; it must never block the rest of the run.
        self.has_cost = "Acquisition Cost USD" in acquisition.columns
        self.accounts = accounts

    def _channel_value(self, population_source: pd.DataFrame) -> pd.DataFrame:
        if not len(self.acquisition) or "Acquisition Channel" not in self.acquisition.columns:
            return pd.DataFrame(columns=["n", "mean_net_value", "mean_acq_cost",
                                        "mean_net_value_after_cac"])
        acct_to_cust = self.accounts.set_index(
            "Masked Account Number")["Masked Customer Number"]
        acq = self.acquisition.copy()
        acq["Masked Customer Number"] = acq["Masked Account Number"].map(acct_to_cust)
        m = acq.merge(population_source[["Masked Customer Number",
                                        "trailing_12m_net_economic_profit"]],
                     on="Masked Customer Number", how="left")
        agg = {"n": ("Masked Customer Number", "nunique"),
              "mean_net_value": ("trailing_12m_net_economic_profit", "mean")}
        if self.has_cost:
            agg["mean_acq_cost"] = ("Acquisition Cost USD", "mean")
        by_channel = m.groupby("Acquisition Channel").agg(**agg)
        if self.has_cost:
            by_channel["mean_net_value_after_cac"] = (
                by_channel["mean_net_value"] - by_channel["mean_acq_cost"])
        else:
            by_channel["mean_acq_cost"] = None
            by_channel["mean_net_value_after_cac"] = by_channel["mean_net_value"]
        return by_channel.sort_values("mean_net_value_after_cac", ascending=False)

    def population(self, pop) -> pd.DataFrame:
        pop = super().population(pop)
        cv = pop.frame
        self._cv = cv
        ranked = self._channel_value(cv)
        worst_channels = ranked.tail(max(len(ranked) // 3, 1)).index.tolist()

        acct_to_cust = self.accounts.set_index(
            "Masked Account Number")["Masked Customer Number"]
        acq = self.acquisition.copy()
        acq["Masked Customer Number"] = acq["Masked Account Number"].map(acct_to_cust)
        cust_to_channel = acq.set_index("Masked Customer Number")["Acquisition Channel"]

        out = cv[cv["Masked Customer Number"].map(cust_to_channel).isin(
            worst_channels)].copy()
        out["acquisition_channel"] = out["Masked Customer Number"].map(cust_to_channel)
        self._ranked_cache = ranked
        return out

    def size(self, population: pd.DataFrame) -> SizeResult:
        a = self.lever_assumptions()
        cv = getattr(self, "_cv", population)
        inputs = valuation_inputs(cv, self.n_cycles)
        scen = value_scenarios(inputs, a)
        if not scen:
            return SizeResult(
                None, basis=f"Cannot be computed: {inputs['reason']}.",
                caveat="No fabricated value - L6 needs acquisition channel and cost "
                       "data for customers acquired within the observation window.",
                assumptions_used=a, method_note=METHOD_NOTE, inputs=inputs)
        base = scen["base"]
        ex = base["extras"]
        return SizeResult(
            priced_value_usd=round(base["total_usd"], 2),
            basis=METHOD_NOTE,
            caveat=(f"Assumption-based, pilot required. Shifts "
                    f"${ex['budget_shifted_usd']:,.0f}/yr from {ex['worst']} to "
                    f"{ex['best']}; after {ex['build_years']} years of the same "
                    f"shift: ${ex['after_n_years']:,.0f}/yr. The best channel must "
                    f"deliver at least {ex['breakeven_quality']:.0%} of its current "
                    f"customer quality for the shift to break even."),
            unpriced_context_usd=None,
            scenarios=scen, assumptions_used=a, method_note=METHOD_NOTE,
            inputs=inputs, gate_value_usd=base["total_usd"])

    def worklist(self, population: pd.DataFrame) -> pd.DataFrame:
        wl = population.copy()
        wl["action"] = "REVIEW_ACQUISITION_CHANNEL_MIX"
        wl["reason"] = wl["acquisition_channel"].map(
            lambda c: f"acquired via {c}, a bottom-tier channel by net value after CAC")
        return wl[["Masked Customer Number", "action", "reason",
                  "acquisition_channel", "trailing_12m_net_economic_profit"]]

    def driver(self, customer_view: pd.DataFrame) -> float:
        """Spread between the best and worst channel's net value after CAC.
        This dataset's negative control does not vary channel mix or
        quality, so expect this lever to report inconclusive at the gate -
        that is the honest result, not a bug."""
        ranked = self._channel_value(customer_view)
        if len(ranked) < 2:
            return 0.0
        return float(ranked["mean_net_value_after_cac"].iloc[0]
                    - ranked["mean_net_value_after_cac"].iloc[-1])


# ---------------------------------------------------------------------------
# Explanations for the customer drill-down. Additive only. L6 is valued at
# CHANNEL level, so there is deliberately no customer_contributions(): the
# trace shows the customer's own inputs against their channel's averages.

def population_channel_ranking(cv: pd.DataFrame) -> pd.DataFrame:
    """The ranking population() uses to pick the bottom-third channels -
    mean trailing-12m NEP minus mean acquisition cost, per channel - rebuilt
    from the customer view so it is available in bundle mode too."""
    c = cv[cv["acquisition_channel"].notna()].copy()
    c["acquisition_channel"] = c["acquisition_channel"].astype(str)
    g = c.groupby("acquisition_channel").agg(
        customers=(K, "size"), mean_nep=("trailing_12m_net_economic_profit", "mean"),
        mean_cac=("acquisition_cost_usd", "mean"))
    g["mean_net_value_after_cac"] = g["mean_nep"] - g["mean_cac"].fillna(0)
    g = g.sort_values("mean_net_value_after_cac", ascending=False)
    n_bottom = max(len(g) // 3, 1)
    g["bottom_third"] = False
    g.iloc[-n_bottom:, g.columns.get_loc("bottom_third")] = True
    return g


def selection_rules(row, ranking: pd.DataFrame | None = None) -> list:
    ch = str(row.get("acquisition_channel"))
    rules = [{"rule": "Acquired through a known channel", "threshold": "channel on file",
              "actual": ch, "met": ch not in ("None", "nan", "")}]
    if ranking is not None and ch in ranking.index:
        bottom = ranking.index[ranking["bottom_third"]].tolist()
        r = ranking.loc[ch]
        rules.append({
            "rule": "Channel is in the bottom third by mean (NEP - acquisition cost)",
            "threshold": "bottom third: " + ", ".join(bottom),
            "actual": f"{ch}: ${r['mean_net_value_after_cac']:,.0f} per customer "
                      f"(rank {list(ranking.index).index(ch) + 1} of {len(ranking)})",
            "met": bool(r["bottom_third"])})
    return rules


def customer_trace(row, inputs: dict, a: dict, scenario: str = "base") -> list:
    """No per-customer value exists for L6 - the shift is valued per channel.
    Shows this customer's inputs against the channel averages instead."""
    ch = str(row.get("acquisition_channel"))
    by = {r["channel"]: r for r in inputs.get("channels", [])}
    steps = [{"component": "This customer's trailing-12m NEP", "formula": "observed",
              "substituted": "", "value": float(row.get("trailing_12m_net_economic_profit", 0.0))},
             {"component": "This customer's acquisition cost", "formula": "observed (Table 23)",
              "substituted": "", "value": float(row["acquisition_cost_usd"])
              if pd.notna(row.get("acquisition_cost_usd")) else float("nan")}]
    if ch in by:
        r = by[ch]
        steps += [
            {"component": f"Channel '{ch}' mean NEP (customers acquired in the window)",
             "formula": "mean over in-window acquisitions", "substituted": f"n = {r['customers_in_window']}",
             "value": r["mean_trailing_12m_nep_usd"]},
            {"component": f"Channel '{ch}' mean CAC", "formula": "mean over in-window acquisitions",
             "substituted": "", "value": r["mean_cac_usd"]},
            {"component": f"Channel '{ch}' NEP per CAC dollar", "formula": "mean NEP / mean CAC",
             "substituted": f"${r['mean_trailing_12m_nep_usd']:,.2f} / ${r['mean_cac_usd']:,.2f}",
             "value": r["nep_per_cac_dollar"]},
        ]
        role = ("WORST channel - budget would move away from it" if ch == inputs.get("worst") else
                "BEST channel - budget would move to it" if ch == inputs.get("best") else
                "neither the worst nor the best channel - not directly affected by the shift")
        steps.append({"component": "Role in the budget-neutral shift", "formula": role,
                      "substituted": "", "value": float("nan")})
    else:
        steps.append({"component": "Channel valuation",
                      "formula": "this channel has no in-window acquisitions with a cost on file",
                      "substituted": "", "value": float("nan")})
    steps.append({"component": "Per-customer contribution",
                  "formula": "none - L6 is valued at channel level (future acquisitions), "
                             "never per existing customer", "substituted": "", "value": float("nan")})
    return steps


def calculation_steps(inputs: dict, a: dict, scenario: str = "base") -> list:
    if not inputs.get("available"):
        return []
    by = {r["channel"]: r for r in inputs["channels"]}
    w, b = by[inputs["worst"]], by[inputs["best"]]
    share = float(a["budget_shift_share"])
    mult = ASSUME.pick(a["marginal_cac_multiplier"], scenario)
    q = ASSUME.pick(a["incremental_quality"], scenario)
    shifted = share * w["annual_acquisition_spend_usd"]
    lost_n = shifted / w["mean_cac_usd"]
    gained_n = shifted / (b["mean_cac_usd"] * mult)
    return [
        {"component": "budget shifted per year",
         "formula": "budget_shift_share x worst channel's annual acquisition spend",
         "substituted": f"{share} x ${w['annual_acquisition_spend_usd']:,.2f} ({inputs['worst']})",
         "value": shifted},
        {"component": "customers not acquired in the worst channel", "formula": "shifted / CAC_worst",
         "substituted": f"${shifted:,.2f} / ${w['mean_cac_usd']:,.2f}", "value": lost_n},
        {"component": "profit_lost_worst_channel", "formula": "-customers lost x NEP_worst",
         "substituted": f"-{lost_n:,.2f} x ${w['mean_trailing_12m_nep_usd']:,.2f}",
         "value": -lost_n * w["mean_trailing_12m_nep_usd"]},
        {"component": "customers gained in the best channel",
         "formula": "shifted / (CAC_best x marginal_cac_multiplier)",
         "substituted": f"${shifted:,.2f} / (${b['mean_cac_usd']:,.2f} x {mult})", "value": gained_n},
        {"component": "profit_gained_best_channel",
         "formula": "customers gained x NEP_best x incremental_quality",
         "substituted": f"{gained_n:,.2f} x ${b['mean_trailing_12m_nep_usd']:,.2f} x {q}",
         "value": gained_n * b["mean_trailing_12m_nep_usd"] * q},
    ]
