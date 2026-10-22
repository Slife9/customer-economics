"""L5 - Retention targeting. Spend the retention budget by worth, not by
balance or tenure.

Population uses only OBSERVABLE warning signals - a recent closure-request
contact, a meaningful spend decline, or a price position well above peers -
never a latent trait the engine cannot see anyway.

Valuation (SPEC_lever_valuation_rebuild.md 4.5): L5 stays UNPRICED -
priced_value_usd is always None and L5 is never part of a portfolio total.
What is reported: value at risk (trailing-12-month profit of the at-risk
customers - a fact about today), a CONDITIONAL estimate of what an outreach
programme would keep under assumed leave / keep rates, and the break-even
keep rate the programme would need to pay for itself. Historical leave
rates from Table 22 are shown next to the configured leave rate for
comparison; they never overwrite it.
"""
from __future__ import annotations
import pandas as pd

from .base import Lever, SizeResult, component, scenario
from . import assumptions as ASSUME

K = "Masked Customer Number"
SPEND_DECLINE_THRESHOLD = 0.30
HIGH_VALUE_BANDS = {"Valued", "Premier"}
RATE_ABOVE_PEER_POINTS = 2.0
SIGNALS = ("closure_request_contact", "spend_declining", "priced_above_peer")
FOLLOW_UP_CYCLES = 12

METHOD_NOTE = (
    "Unpriced. Value at risk = trailing-12-month NEP of high-value customers "
    "showing a warning signal. Conditional estimate: of those contacted, an "
    "assumed share would leave within a year, and outreach keeps an assumed "
    "share of them; costs are an outreach contact for everyone plus an offer "
    "for those who take it up. Break-even keep rate = cost per contact / "
    "(leave rate x mean value at risk).")


def historical_leave_rates(cv: pd.DataFrame, drivers: pd.DataFrame,
                           attrition: pd.DataFrame | None,
                           accounts: pd.DataFrame) -> dict:
    """Observed voluntary-closure rates (Table 22), for comparison with the
    configured leave_rate. Returns figures with their denominators, or a
    reason when the data cannot support them."""
    if attrition is None or not len(attrition) or "Voluntary Closure" not in attrition.columns:
        return {"available": False,
                "reason": "No Table22_Attrition_Events.csv (voluntary closures) in this portfolio."}
    cycles = sorted(drivers["Cycle Month"].unique())
    pos = {c: i for i, c in enumerate(cycles)}
    last = len(cycles) - 1
    acct_to_cust = accounts.set_index("Masked Account Number")["Masked Customer Number"]
    vol = attrition[attrition["Voluntary Closure"].astype(bool)].copy()
    vol[K] = vol["Masked Account Number"].map(acct_to_cust)
    vol["_pos"] = vol["Closure Cycle Month"].map(pos)
    vol = vol.dropna(subset=[K, "_pos"])

    hv = set(cv.loc[cv["cev_band"].astype(str).isin(HIGH_VALUE_BANDS), K])
    trailing = vol[vol["_pos"] > last - FOLLOW_UP_CYCLES]
    hv_closed = len(set(trailing[K]) & hv)

    req = drivers[drivers["Primary Call Reason"] == "closure_request"][[K, "Cycle Month"]].copy()
    req["_pos"] = req["Cycle Month"].map(pos)
    first_req = req.groupby(K)["_pos"].min()
    followable = first_req[first_req <= last - FOLLOW_UP_CYCLES]
    first_close = vol.groupby(K)["_pos"].min()
    joined = pd.DataFrame({"req": followable}).join(first_close.rename("close"), how="left")
    left = ((joined["close"] >= joined["req"])
            & (joined["close"] <= joined["req"] + FOLLOW_UP_CYCLES))
    hv_joined = joined[joined.index.isin(hv)]
    hv_left = left[left.index.isin(hv)]
    return {
        "available": True,
        "valued_premier_annual_rate": (hv_closed / len(hv)) if hv else None,
        "valued_premier_customers": len(hv),
        "valued_premier_voluntary_closures_trailing_12": hv_closed,
        "after_closure_request_rate": float(left.mean()) if len(joined) else None,
        "after_closure_request_customers": int(len(joined)),
        "after_closure_request_valued_premier_rate": float(hv_left.mean()) if len(hv_joined) else None,
        "after_closure_request_valued_premier_customers": int(len(hv_joined)),
        "definition": ("Valued/Premier rate: share of currently Valued/Premier customers "
                       "with a voluntary closure in the trailing 12 cycles. After-request "
                       "rate: share of customers whose first closure-request contact has a "
                       "full 12 cycles of follow-up who closed voluntarily within those 12 "
                       "cycles (same month included)."),
    }


def valuation_inputs(population: pd.DataFrame, wl: pd.DataFrame, history: dict) -> dict:
    by_signal = {}
    sig = population["risk_signals"].fillna("")
    for s in SIGNALS:
        has = sig.str.contains(s, regex=False)
        by_signal[s] = {"customers": int(has.sum()),
                        "value_at_risk_usd": float(
                            population.loc[has, "trailing_12m_net_economic_profit"].sum())}
    return {
        "customers": int(len(wl)),
        "value_at_risk_usd": float(wl["value_at_risk_usd"].sum()),
        "mean_value_at_risk_usd": float(wl["value_at_risk_usd"].mean()) if len(wl) else 0.0,
        "by_signal": by_signal,
        "historical_leave_rates": history,
    }


def value_scenarios(inputs: dict, a: dict) -> dict:
    n, v = inputs["customers"], inputs["mean_value_at_risk_usd"]
    out = {}
    for s in ASSUME.SCENARIOS:
        leave = ASSUME.pick(a["leave_rate"], s)
        keep = ASSUME.pick(a["keep_rate"], s)
        outreach = ASSUME.pick(a["outreach_cost_usd"], s)
        take = ASSUME.pick(a["offer_takeup"], s)
        offer = ASSUME.pick(a["offer_cost_usd"], s)
        comp = {
            "value_kept": component(n * leave * keep * v, "protected_value", "assumption"),
            "outreach_cost": component(-n * outreach, "cost", "measured"),
            "offer_cost": component(-n * take * offer, "cost", "assumption"),
        }
        sc = scenario(comp)
        cost_per_contact = outreach + take * offer
        sc["extras"] = {
            "net_conditional": sc["total_usd"],
            "breakeven_keep_rate": (cost_per_contact / (leave * v)) if leave * v else None,
            "configured_leave_rate": leave,
            "configured_keep_rate": keep,
            "value_at_risk": inputs["value_at_risk_usd"],
            "customers": n,
            "by_signal": inputs["by_signal"],
            "historical_leave_rates": inputs["historical_leave_rates"],
        }
        out[s] = sc
    return out


class L5Retention(Lever):
    code = "L5"
    name = "Retention targeting"
    gates = []

    def __init__(self, drivers: pd.DataFrame, spend_decline: pd.DataFrame,
                 accounts: pd.DataFrame | None = None,
                 attrition: pd.DataFrame | None = None):
        """`spend_decline` is a (Masked Customer Number, spend_declined) frame
        the orchestrator precomputes from Table5_Transaction - trailing 3
        months vs. the prior 3, an observable trend, not a latent.
        `accounts` and `attrition` (Table 22) are used only for the
        historical leave rates reported next to the configured assumption."""
        self.drivers = drivers
        self.spend_decline = spend_decline
        self.accounts = accounts
        self.attrition = attrition

    def population(self, pop) -> pd.DataFrame:
        pop = super().population(pop)
        cv = pop.frame
        self._cv = cv
        high_value = cv["cev_band"].astype(str).isin(HIGH_VALUE_BANDS)

        # A closure-request contact counts only if it happened in the trailing
        # 12 cycles - a call three years ago from a customer still here is not
        # a current warning sign (population fix, spec 4.5).
        recent_cycles = sorted(self.drivers["Cycle Month"].unique())[-FOLLOW_UP_CYCLES:]
        recent = self.drivers[self.drivers["Cycle Month"].isin(recent_cycles)]
        closure_signal = (recent.groupby("Masked Customer Number")["Primary Call Reason"]
                          .apply(lambda s: (s == "closure_request").any())
                          .rename("closure_request_signal"))
        cv = cv.merge(closure_signal, on="Masked Customer Number", how="left")
        cv["closure_request_signal"] = cv["closure_request_signal"].fillna(False)
        cv = cv.merge(self.spend_decline, on="Masked Customer Number", how="left")
        cv["spend_declined"] = cv["spend_declined"].fillna(False)

        peer_apr = cv.groupby("Credit Score Band")["latest_charged_apr"].transform("median")
        priced_above_peer = (cv["latest_charged_apr"] - peer_apr) >= RATE_ABOVE_PEER_POINTS

        at_risk = high_value & (cv["closure_request_signal"] | cv["spend_declined"]
                                | priced_above_peer)
        out = cv[at_risk].copy()
        # Additive columns for the drill-down (population unchanged).
        out["peer_median_apr"] = peer_apr[at_risk]
        out["priced_above_peer"] = priced_above_peer[at_risk]
        out["risk_signals"] = out.apply(lambda r: ", ".join(filter(None, [
            "closure_request_contact" if r["closure_request_signal"] else "",
            "spend_declining" if r["spend_declined"] else "",
            "priced_above_peer" if (r["latest_charged_apr"]
                                    - peer_apr.get(r.name, 0)) >= RATE_ABOVE_PEER_POINTS else "",
        ])), axis=1)
        return out

    def size(self, population: pd.DataFrame) -> SizeResult:
        a = self.lever_assumptions()
        cv = getattr(self, "_cv", population)
        history = (historical_leave_rates(cv, self.drivers, self.attrition, self.accounts)
                   if self.accounts is not None else
                   {"available": False, "reason": "accounts table not supplied"})
        inputs = valuation_inputs(population, self.worklist(population), history)
        scen = value_scenarios(inputs, a)
        base = scen["base"]
        var = inputs["value_at_risk_usd"]
        be = base["extras"]["breakeven_keep_rate"]
        return SizeResult(
            priced_value_usd=None,
            basis=METHOD_NOTE,
            caveat=(f"${var:,.0f} is the trailing-12-month value these "
                    f"{inputs['customers']} customers represent if nothing changes - "
                    f"value AT RISK, not value recoverable, and never part of a "
                    f"portfolio total. Conditional base net: "
                    f"${base['total_usd']:,.0f}; an outreach programme breaks even "
                    f"only if it keeps at least "
                    f"{'n/a' if be is None else f'{be:.0%}'} of would-be leavers."),
            unpriced_context_usd=round(var, 2),
            scenarios=scen, assumptions_used=a, method_note=METHOD_NOTE,
            inputs=inputs, gate_value_usd=None)

    def worklist(self, population: pd.DataFrame) -> pd.DataFrame:
        wl = population.copy()
        wl["action"] = "RETENTION_OUTREACH"
        wl["reason"] = wl["risk_signals"]
        return wl[["Masked Customer Number", "action", "reason",
                  "trailing_12m_net_economic_profit", "cev_band",
                  "closure_request_signal", "spend_declined", "priced_above_peer",
                  "peer_median_apr"]].rename(
            columns={"trailing_12m_net_economic_profit": "value_at_risk_usd"})

    def driver(self, customer_view: pd.DataFrame) -> float:
        """No mechanism in this dataset targets retention directly - this
        exists so the negative control gate can correctly report L5 as
        inconclusive rather than fabricate a pass."""
        raise NotImplementedError(
            "L5 has no driver: retention is not a mechanism this dataset's "
            "negative control varies. The gate should report L5 inconclusive.")


# ---------------------------------------------------------------------------
# Explanations for the customer drill-down. Additive only: same thresholds
# and formulas as population()/value_scenarios(); the audit checks that
# customer contributions sum to the components and steps equal them. Every
# per-customer figure is an EXPECTED value under the assumptions - L5 stays
# unpriced and is never part of a portfolio total.

def selection_rules(row) -> dict:
    band = str(row.get("cev_band"))
    hv = {"rule": "High-value customer", "threshold": "CEV band Valued or Premier",
          "actual": band, "met": band in HIGH_VALUE_BANDS}
    gap = row.get("latest_charged_apr", float("nan")) - row.get("peer_median_apr", float("nan"))
    sets = {
        "At risk: closure-request contact": [hv, {
            "rule": "Closure-request contact in the trailing 12 cycles", "threshold": "yes",
            "actual": "yes" if bool(row.get("closure_request_signal")) else "no",
            "met": bool(row.get("closure_request_signal"))}],
        "At risk: spend declining": [hv, {
            "rule": "Spend, last 3 months vs the prior 3",
            "threshold": f"fallen to <= {1 - SPEND_DECLINE_THRESHOLD:.0%}",
            "actual": "yes" if bool(row.get("spend_declined")) else "no",
            "met": bool(row.get("spend_declined"))}],
        "At risk: priced above peers": [hv, {
            "rule": "Charged APR above the credit-score-band median",
            "threshold": f">= {RATE_ABOVE_PEER_POINTS:.1f} pts above",
            "actual": "n/a" if pd.isna(gap) else
                      f"{row['latest_charged_apr']:.2f}% vs {row['peer_median_apr']:.2f}% ({gap:+.2f} pts)",
            "met": bool(row.get("priced_above_peer"))}],
    }
    matched = next((k for k, r in sets.items() if all(x["met"] for x in r)), None)
    return {"matched": matched, "rule_sets": sets,
            "precedence": "A high-value customer with ANY one signal is at risk; the matched set is "
                          "the first signal found (the reason column lists every signal)."}


def customer_contributions(rows: pd.DataFrame, inputs: dict, a: dict,
                           scenario: str = "base") -> pd.DataFrame:
    leave = ASSUME.pick(a["leave_rate"], scenario)
    keep = ASSUME.pick(a["keep_rate"], scenario)
    out = pd.DataFrame(index=rows.index)
    out["value_kept"] = leave * keep * rows["value_at_risk_usd"].fillna(0.0)
    out["outreach_cost"] = -float(ASSUME.pick(a["outreach_cost_usd"], scenario))
    out["offer_cost"] = -float(ASSUME.pick(a["offer_takeup"], scenario)
                               * ASSUME.pick(a["offer_cost_usd"], scenario))
    out["total"] = out.sum(axis=1)
    return out


def customer_trace(row, inputs: dict, a: dict, scenario: str = "base") -> list:
    c = customer_contributions(pd.DataFrame([row]), inputs, a, scenario).iloc[0]
    leave = ASSUME.pick(a["leave_rate"], scenario)
    keep = ASSUME.pick(a["keep_rate"], scenario)
    take = ASSUME.pick(a["offer_takeup"], scenario)
    offer = ASSUME.pick(a["offer_cost_usd"], scenario)
    out_c = ASSUME.pick(a["outreach_cost_usd"], scenario)
    v = float(row["value_at_risk_usd"])
    be = (out_c + take * offer) / (leave * v) if leave * v > 0 else float("nan")
    return [
        {"component": "value at risk (this customer)", "formula": "trailing-12m NEP - a fact, not a forecast",
         "substituted": "", "value": v},
        {"component": "value_kept", "formula": "leave_rate x keep_rate x value at risk",
         "substituted": f"{leave} x {keep} x ${v:,.2f}", "value": c["value_kept"]},
        {"component": "outreach_cost", "formula": "one outreach contact", "substituted": f"-${out_c}",
         "value": c["outreach_cost"]},
        {"component": "offer_cost", "formula": "offer_takeup x offer_cost",
         "substituted": f"-{take} x ${offer}", "value": c["offer_cost"]},
        {"component": "CONDITIONAL NET (expected value, base assumptions - not in any total)",
         "formula": "sum of the above three", "substituted": "", "value": c["total"]},
        {"component": "break-even keep rate for this customer",
         "formula": "(outreach + takeup x offer) / (leave_rate x value at risk)",
         "substituted": f"(${out_c} + {take} x ${offer}) / ({leave} x ${v:,.2f})", "value": be},
    ]


def calculation_steps(inputs: dict, a: dict, scenario: str = "base") -> list:
    n, v = inputs["customers"], inputs["mean_value_at_risk_usd"]
    leave = ASSUME.pick(a["leave_rate"], scenario)
    keep = ASSUME.pick(a["keep_rate"], scenario)
    take = ASSUME.pick(a["offer_takeup"], scenario)
    offer = ASSUME.pick(a["offer_cost_usd"], scenario)
    out_c = ASSUME.pick(a["outreach_cost_usd"], scenario)
    return [
        {"component": "value_kept", "formula": "n x leave_rate x keep_rate x mean value at risk",
         "substituted": f"{n:,} x {leave} x {keep} x ${v:,.2f}", "value": n * leave * keep * v},
        {"component": "outreach_cost", "formula": "-n x outreach_cost_usd",
         "substituted": f"-{n:,} x ${out_c}", "value": -n * out_c},
        {"component": "offer_cost", "formula": "-n x offer_takeup x offer_cost_usd",
         "substituted": f"-{n:,} x {take} x ${offer}", "value": -n * take * offer},
        {"component": "breakeven_keep_rate",
         "formula": "(outreach + takeup x offer) / (leave_rate x mean value at risk)",
         "substituted": f"(${out_c} + {take} x ${offer}) / ({leave} x ${v:,.2f})",
         "value": (out_c + take * offer) / (leave * v) if leave * v else float("nan")},
    ]


def breakeven_table(inputs: dict, a: dict, leave_rates=(0.05, 0.07, 0.10, 0.12, 0.15)) -> list:
    """Break-even keep rate at a range of leave rates, base costs."""
    v = inputs["mean_value_at_risk_usd"]
    cost = (ASSUME.pick(a["outreach_cost_usd"], "base")
            + ASSUME.pick(a["offer_takeup"], "base") * ASSUME.pick(a["offer_cost_usd"], "base"))
    return [{"leave_rate": lr, "cost_per_contact_usd": cost,
             "breakeven_keep_rate": cost / (lr * v) if lr * v else None} for lr in leave_rates]
