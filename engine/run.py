"""ProfitInsight Customer Economics System - orchestrator.

    python -m engine.run --data ../generator/out/demo --out ./out/demo
    python -m engine.run --data ../generator/out/negative_control --out ./out/negative_control --compare-to ./out/demo

Pipeline (concept spec section 4):
    data contract -> ledger -> customer view -> suppression -> routing
    -> levers -> outputs -> governance

Each stage's result is passed to the next; nothing recomputes a figure a
prior stage already produced.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd

from .core.contract import load_portfolio, DataContractViolation
from .core import ledger as LEDGER
from .core import customer_view as CV
from .core import suppression as SUPP
from .core import routing as ROUTE
from .core import outputs as OUT
from .levers.l1_rewards import L1Rewards
from .levers.l2_lines import L2Lines
from .levers.l3_pricing import L3Pricing
from .levers.l4_cost_to_serve import L4CostToServe
from .levers.l5_retention import L5Retention
from .levers.l6_crosssell import L6CrossSell
from .governance import fairness as FAIR
from .governance import negative_control as NEGCTL

# Declares which lever mechanisms THIS repo's generator negative control
# actually varies (see generator/run.py:CONTROL_MECHANISM). This is a fact
# about that code, not a guess - keep it in sync if the generator changes.
MECHANISM_VARIED_IN_CONTROL = {
    "L1": True,   # fee_aligned_to_reward
    "L2": True,   # line_review_uses_observed_behavior
    "L3": True,   # repricing_tracks_risk
    "L4": True,   # digital_deflection_rate + review_discipline differ
    "L5": False,  # no retention mechanism exists to vary - by design (Type C)
    "L6": False,  # channel_mix is identical between demo and control
}


def _spend_decline(tx: pd.DataFrame) -> pd.DataFrame:
    """Observable trailing-3-vs-prior-3-month spend decline per customer.
    Used only by L5's population - a trend already in the published data,
    never a latent."""
    cycles = sorted(tx["Cycle Month"].unique())
    if len(cycles) < 6:
        return pd.DataFrame(columns=["Masked Customer Number", "spend_declined"])
    recent, prior = cycles[-3:], cycles[-6:-3]
    by_cust_cycle = tx.groupby(["Masked Customer Number", "Cycle Month"])[
        "Transaction Amount"].sum().reset_index()
    recent_sum = by_cust_cycle[by_cust_cycle["Cycle Month"].isin(recent)].groupby(
        "Masked Customer Number")["Transaction Amount"].sum()
    prior_sum = by_cust_cycle[by_cust_cycle["Cycle Month"].isin(prior)].groupby(
        "Masked Customer Number")["Transaction Amount"].sum()
    both = pd.DataFrame({"recent": recent_sum, "prior": prior_sum}).fillna(0)
    declined = (both["prior"] > 0) & ((both["recent"] / both["prior"]) <= 0.70)
    return declined.rename("spend_declined").reset_index()


def build_pipeline(data_dir: Path):
    portfolio = load_portfolio(data_dir)
    led = LEDGER.build(portfolio)
    cv = CV.build(led, portfolio)

    suppressed = SUPP.run(cv)
    routed = ROUTE.route(suppressed)

    drivers = portfolio["Table12_Cost_Drivers.csv"]
    accounts = portfolio["Table2_Card_Account.csv"]
    acquisition = portfolio.get("Table23_Acquisition.csv", pd.DataFrame(
        columns=["Masked Account Number", "Acquisition Channel"]))
    tx = portfolio["Table5_Transaction.csv"]
    pools = portfolio["Table11_Cost_Pools.csv"]
    spend_decline = _spend_decline(tx)

    levers = {
        "L1": L1Rewards(),
        "L2": L2Lines(),
        "L3": L3Pricing(),
        "L4": L4CostToServe(drivers, pools),
        "L5": L5Retention(drivers, spend_decline),
        "L6": L6CrossSell(acquisition, accounts),
    }

    populations, sizes, worklists = {}, {}, {}
    for code, lever in levers.items():
        pop = lever.population(routed)
        populations[code] = pop
        sizes[code] = lever.size(pop)
        worklists[code] = lever.worklist(pop)

    fairness_result = FAIR.run(routed.frame, worklists)
    rsum = ROUTE.routing_summary(routed)

    return {
        "portfolio": portfolio, "ledger": led, "customer_view": routed.frame,
        "suppressed": suppressed, "routed": routed, "levers": levers,
        "populations": populations, "sizes": sizes, "worklists": worklists,
        "fairness": fairness_result, "routing_summary": rsum,
    }


def run(data_dir: Path, out_dir: Path, compare_to: Path | None = None) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    result = build_pipeline(data_dir)

    latest_cycle = sorted(result["ledger"]["card"]["Cycle Month"].unique())[-1]
    sf = OUT.score_file(result["customer_view"], result["suppressed"].suppressed,
                        latest_cycle)
    sf.to_csv(out_dir / "score_file.csv", index=False)
    OUT.worklist_export(result["worklists"]).to_csv(out_dir / "worklist.csv", index=False)
    OUT.leakage_register(result["worklists"], result["sizes"]).to_csv(
        out_dir / "leakage_register.csv", index=False)
    result["ledger"]["card"].to_csv(out_dir / "ledger_account_cycle.csv", index=False)

    gate_report = pd.DataFrame()
    if compare_to is not None:
        control_result = build_pipeline(compare_to)
        gt_demo = portfolio_defect_count(data_dir)
        gt_ctrl = portfolio_defect_count(compare_to)
        gate_results = [NEGCTL.check_defects(gt_demo, gt_ctrl)]
        for code, lever in result["levers"].items():
            gate_results.append(NEGCTL.check(
                lever, control_result["levers"][code], MECHANISM_VARIED_IN_CONTROL[code],
                result["customer_view"], result["populations"][code],
                control_result["customer_view"], control_result["populations"][code]))
        gate_report = NEGCTL.report(gate_results)
        gate_report.to_csv(out_dir / "negative_control_gate.csv", index=False)

    pack = OUT.governance_pack(result["fairness"], gate_report,
                               result["routing_summary"], result["ledger"]["measured"])
    (out_dir / "governance_pack.json").write_text(json.dumps(pack, indent=2, default=str))

    summary = {
        "data_dir": str(data_dir),
        "customers": int(len(result["customer_view"])),
        "suppressed_customers": int(len(result["suppressed"].suppressed)),
        "below_cost_customers": int(result["customer_view"]["is_below_cost"].sum()),
        "structural_floor_share": float(
            (result["customer_view"]["routed_lever"] == "STRUCTURAL").sum()
            / max(int(result["customer_view"]["is_below_cost"].sum()), 1)),
        "routing_summary": result["routing_summary"].reset_index().to_dict("records"),
        "leakage_register": OUT.leakage_register(
            result["worklists"], result["sizes"]).to_dict("records"),
        "fairness_score_any_failure": result["fairness"]["score_any_failure"],
        "fairness_treatment_any_failure": result["fairness"]["treatment_any_failure"],
        "negative_control_gate": gate_report.to_dict("records") if len(gate_report) else None,
    }
    (out_dir / "run_summary.json").write_text(json.dumps(summary, indent=2, default=str))
    return summary


def portfolio_defect_count(data_dir: Path) -> int:
    gt = data_dir / "_ground_truth" / "Defect_Ground_Truth.csv"
    if not gt.exists():
        return 0
    df = pd.read_csv(gt)
    hard_types = {"UNPOSTED_CONTRACTUAL_FEE", "INTERCHANGE_BELOW_EXPECTED",
                 "PRICE_BELOW_CONTRACT", "WRONG_EARN_RULE", "PROMO_FAILED_TO_REVERT"}
    return int(df["Defect Type"].isin(hard_types).sum()) if len(df) else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--compare-to", default=None,
                    help="a second portfolio (the negative control) to run "
                        "the gate against")
    a = ap.parse_args()
    try:
        summary = run(Path(a.data), Path(a.out),
                     Path(a.compare_to) if a.compare_to else None)
    except DataContractViolation as e:
        print(f"DATA CONTRACT VIOLATION - refusing to run: {e}")
        raise SystemExit(1)
    print(json.dumps(summary, indent=2, default=str))
