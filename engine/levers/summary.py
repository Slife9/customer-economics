"""Portfolio lever summary (SPEC_lever_valuation_rebuild.md section 3).

  total (low/base/high) = L1 + L2 + L3 (year 1) + L4 (year 1) + L6 (year 1)
  L2's dormant right-sizing is included only when dormant_rightsizing_enabled
    is true (L2's value_scenarios() adds it as a component only then)
  L5 is reported separately - value at risk, conditional range, break-even -
    and is NEVER part of the total
  the same totals split by value_type and by evidence basis

A lever whose value cannot be computed (no scenarios, e.g. L6 without
acquisition cost data, or a pre-rebuild bundle) is listed as excluded with
its reason rather than silently counted as zero.
"""
from __future__ import annotations

from . import assumptions as ASSUME

IN_TOTAL = ("L1", "L2", "L3", "L4", "L6")


def portfolio_summary(sizes: dict) -> dict:
    out = {"levers_in_total": [], "excluded": {}, "scenarios": {}}
    for code in IN_TOTAL:
        s = sizes.get(code)
        if s is None or not s.has_scenarios:
            out["excluded"][code] = ("no corrected valuation available"
                                     if s is None or not s.basis else s.basis)
        else:
            out["levers_in_total"].append(code)
    for sc in ASSUME.SCENARIOS:
        total, by_type, by_basis, by_lever = 0.0, {}, {}, {}
        for code in out["levers_in_total"]:
            scen = sizes[code].scenarios[sc]
            by_lever[code] = scen["total_usd"]
            total += scen["total_usd"]
            for comp in scen["components"].values():
                by_type[comp["value_type"]] = by_type.get(comp["value_type"], 0.0) + comp["value_usd"]
                by_basis[comp["basis"]] = by_basis.get(comp["basis"], 0.0) + comp["value_usd"]
        out["scenarios"][sc] = {"total_usd": total, "by_lever": by_lever,
                                "by_value_type": by_type, "by_basis": by_basis}
    l5 = sizes.get("L5")
    if l5 is not None and l5.has_scenarios:
        out["L5_separately"] = {
            "value_at_risk_usd": l5.unpriced_context_usd,
            "conditional_net_usd": {sc: l5.scenarios[sc]["total_usd"] for sc in ASSUME.SCENARIOS},
            "breakeven_keep_rate_base": l5.scenarios["base"]["extras"]["breakeven_keep_rate"],
            "note": "Value at risk and a conditional estimate only - never in the total.",
        }
    return out
