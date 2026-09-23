"""The negative control gate (concept spec section 8).

Not a fixed threshold - part of every finding is structural and survives on
any book, so a flat ratio cannot separate "tracks its cause" from "fires
regardless." Instead: a lever's value must fall AT LEAST AS FAST as the
driver it claims to act on.

    value_ratio <= driver_ratio * (1 + slack)

A control only tests a lever if it varies that lever's mechanism. Where it
does not, this reports INCONCLUSIVE - never a pass, never a build failure.
Marking an untested lever green is worse than failing it.

Which levers this dataset's negative control actually varies is a fact about
run.py's CONTROL_MECHANISM dict, not something inferred here. The caller
declares it explicitly, so the gate's "tested" claim always traces to a real
code diff in the generator, never a guess.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import pandas as pd

DEFAULT_SLACK = 0.15


@dataclass
class GateResult:
    lever_code: str
    status: str  # "PASS" | "FAIL" | "INCONCLUSIVE"
    driver_demo: Optional[float]
    driver_control: Optional[float]
    driver_ratio: Optional[float]
    value_demo: Optional[float]
    value_control: Optional[float]
    value_ratio: Optional[float]
    detail: str


def _lever_value(lever, population) -> Optional[float]:
    r = lever.size(population)
    v = r.priced_value_usd if r.is_priced else r.unpriced_context_usd
    return v


def check(demo_lever, control_lever, mechanism_varied: bool,
         demo_customer_view: pd.DataFrame, demo_population,
         control_customer_view: pd.DataFrame, control_population,
         slack: float = DEFAULT_SLACK) -> GateResult:
    """Takes the DEMO-bound and CONTROL-bound lever instances separately.

    A lever like L4/L5/L6 binds portfolio-specific tables (its own cost
    drivers, its own acquisition table) at construction. Reusing one
    instance's `.driver()`/`.size()` against the other portfolio's frames
    would silently compute both sides from the same underlying data and
    produce a meaningless ratio of 1.0 - which is exactly what happened
    before this was two arguments instead of one.
    """
    code = demo_lever.code
    if not mechanism_varied:
        return GateResult(code, "INCONCLUSIVE", None, None, None,
                          None, None, None,
                          f"the negative control does not vary {code}'s "
                          f"mechanism in this build - reported outstanding, "
                          f"not passed and not failed")

    try:
        driver_demo = demo_lever.driver(demo_customer_view)
        driver_control = control_lever.driver(control_customer_view)
    except NotImplementedError as e:
        return GateResult(code, "INCONCLUSIVE", None, None, None,
                          None, None, None, str(e))

    if driver_demo == 0:
        return GateResult(code, "INCONCLUSIVE", driver_demo, driver_control,
                          None, None, None, None,
                          f"{code} driver is zero on the demo book - "
                          f"no signal to test a ratio against")
    driver_ratio = driver_control / driver_demo

    value_demo = _lever_value(demo_lever, demo_population)
    value_control = _lever_value(control_lever, control_population)
    if value_demo is None or value_control is None or value_demo == 0:
        return GateResult(code, "INCONCLUSIVE", driver_demo, driver_control,
                          round(driver_ratio, 4), value_demo, value_control, None,
                          f"{code} value is not comparably priced on "
                          f"both books")
    value_ratio = value_control / value_demo
    passed = value_ratio <= driver_ratio * (1 + slack)
    detail = (f"value fell to {value_ratio:.2f}x of demo; driver fell to "
             f"{driver_ratio:.2f}x (+{slack:.0%} slack) - "
             f"{'value tracked its cause' if passed else 'value did NOT fall as fast as its driver - possible circularity'}")
    return GateResult(code, "PASS" if passed else "FAIL", driver_demo,
                      driver_control, round(driver_ratio, 4), value_demo,
                      value_control, round(value_ratio, 4), detail)


def check_defects(demo_ground_truth_count: int, control_ground_truth_count: int) -> GateResult:
    """The other half of the negative control: planted Type A defects must
    be at zero in the control, unconditionally - this is not mechanism-
    dependent, so it is never inconclusive."""
    status = "PASS" if control_ground_truth_count == 0 else "FAIL"
    return GateResult("DEFECTS", status, demo_ground_truth_count,
                      control_ground_truth_count,
                      None, None, None, None,
                      f"control carries {control_ground_truth_count} planted "
                      f"defects (must be 0)")


def report(results: list[GateResult]) -> pd.DataFrame:
    return pd.DataFrame([{
        "lever": r.lever_code, "status": r.status,
        "driver_demo": r.driver_demo, "driver_control": r.driver_control,
        "driver_ratio": r.driver_ratio, "value_demo": r.value_demo,
        "value_control": r.value_control, "value_ratio": r.value_ratio,
        "detail": r.detail,
    } for r in results])
