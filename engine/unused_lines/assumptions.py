"""Unused-line module assumptions: the agreed regulatory settings and the
workbook's inputs, editable in session.

config/unused_line_assumptions.json  agreed working assumptions (brief s.2,
                                     OPEN_DECISIONS flags, segment rules)
config/workbook_model.json           the Unused Line RWA Scenario Model's
                                     inputs and Dashboard figures, extracted by
                                     extract_workbook.py (sha256 recorded)

No rate is written in code: every number the module uses comes from these two
files, and load() refuses a configuration that breaks an agreed rule (a 0% CCF
on a card line, a weight outside 0-150%, a missing segment).
"""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path

CONFIG_DIR = Path(__file__).parent / "config"
ASSUMPTIONS = CONFIG_DIR / "unused_line_assumptions.json"
WORKBOOK = CONFIG_DIR / "workbook_model.json"
WORKBOOK_SEGMENTS = ["dormant", "sock_drawer", "transactors", "deteriorating", "relationship"]
SEGMENTS = ["deteriorating", "relationship", "dormant", "sock_drawer", "transactors", "unassigned"]
SCENARIOS = ["conservative", "base", "aggressive"]
CATEGORY_I_III = "category_I_III"


class AssumptionsError(ValueError):
    pass


def load(path: Path | str | None = None, workbook_path: Path | str | None = None) -> tuple[dict, str]:
    """Returns (config, sha256 of the two files). The workbook model is under
    config["workbook"]."""
    p, w = Path(path) if path else ASSUMPTIONS, Path(workbook_path) if workbook_path else WORKBOOK
    raw, wraw = p.read_bytes(), w.read_bytes()
    cfg = json.loads(raw)
    cfg["workbook"] = json.loads(wraw)
    validate(cfg)
    return cfg, hashlib.sha256(raw + wraw).hexdigest()


def validate(cfg: dict) -> None:
    cap = cfg["capital"]
    if cap["ccf_unused_card_lines"] <= 0 or cap.get("zero_ccf_allowed_for_cards"):
        raise AssumptionsError("a card line may never receive a 0% CCF (brief s.2.1)")
    for k in ["risk_weight_transactor", "risk_weight_non_transactor",
              "risk_weight_dormant_zero_balance", "risk_weight_non_qualifying_retail"]:
        if not 0 < cap[k] <= 1.5:
            raise AssumptionsError(f"capital.{k} = {cap[k]} outside (0, 1.5]")
    for k in ["capital_ratio", "cost_of_equity"]:
        if not 0 < cap[k] < 1:
            raise AssumptionsError(f"capital.{k} = {cap[k]} outside (0, 1)")
    bp = cfg["bank_profile"]
    if bp["apply_to"] not in bp["apply_to_options"]:
        raise AssumptionsError(f"bank_profile.apply_to {bp['apply_to']!r} not in {bp['apply_to_options']}")
    if bp["bank_category"] not in bp["bank_category_options"]:
        raise AssumptionsError(f"bank_profile.bank_category {bp['bank_category']!r} not recognised")
    leq = cfg["drawdown_risk"]["leq_by_segment"]
    missing = [s for s in WORKBOOK_SEGMENTS if s not in leq]
    if missing:
        raise AssumptionsError(f"drawdown_risk.leq_by_segment missing {missing}")
    if cfg["drawdown_risk"]["pd_basis"] != "annual":
        raise AssumptionsError("drawdown loss uses annual PD only (brief s.2.4)")
    if cfg["segments"]["order"] != SEGMENTS:
        raise AssumptionsError(f"segments.order must be {SEGMENTS}")
    wb = cfg["workbook"]
    for scn in SCENARIOS:
        for lever, by_seg in wb["levers"][scn].items():
            if set(by_seg) != set(WORKBOOK_SEGMENTS):
                raise AssumptionsError(f"workbook levers {scn}.{lever} must cover {WORKBOOK_SEGMENTS}")


def liquidity_applies(cfg: dict) -> bool:
    """Brief s.2.3: Category I-III banks by default; every bank under all_banks."""
    bp = cfg["bank_profile"]
    return bp["apply_to"] == "all_banks" or bp["bank_category"] == CATEGORY_I_III


def annual_capital_cost_rate(cfg: dict) -> float:
    """Capital ratio x cost of equity (10.5% x 12% = 1.26% of RWA a year)."""
    return cfg["capital"]["capital_ratio"] * cfg["capital"]["cost_of_equity"]


def label(cfg: dict) -> str:
    return cfg["_label"]


def with_overrides(cfg: dict, overrides: dict) -> dict:
    """A validated copy of `cfg` with nested overrides, e.g.
    {"capital": {"risk_weight_dormant_zero_balance": 0.45}}. Session-only:
    nothing is written back to the config files."""
    out = copy.deepcopy(cfg)

    def merge(dst, src, path):
        for k, v in src.items():
            if k not in dst:
                raise AssumptionsError(f"unknown assumption {'.'.join(path + [k])}")
            if isinstance(v, dict) and isinstance(dst[k], dict):
                merge(dst[k], v, path + [k])
            else:
                dst[k] = v
    merge(out, overrides, [])
    validate(out)
    return out
