"""Lever valuation assumptions (engine/config/lever_assumptions.json).

Every business assumption a lever's value depends on lives in that one file,
as either a scalar or a {low, base, high} scenario dict. No lever module
hard-codes a response rate. The file's SHA-256 is recorded in
run_summary.json and the results-bundle manifest so every published figure
traces to the exact assumptions it was computed under.

Two vocabularies are fixed here and checked by audit/audit_lever_estimates.py:
  VALUE_TYPES  what kind of money a component is
  BASES        whether it rests on observed data/regulation ("measured") or on
               a customer response not yet observed ("assumption" - needs a
               pilot before anyone should rely on it)
"""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "lever_assumptions.json"

SCENARIOS = ("low", "base", "high")
LEVER_CODES = ("L1", "L2", "L3", "L4", "L5", "L6")
VALUE_TYPES = ("revenue", "cost_saving", "avoided_loss", "lost_profit", "cost",
               "protected_value")
BASES = ("measured", "assumption")


class LeverAssumptionsError(Exception):
    """The assumptions file is missing, malformed, or incomplete."""


def _validate(a: dict) -> None:
    missing = [c for c in LEVER_CODES if c not in a]
    if missing:
        raise LeverAssumptionsError(f"lever_assumptions.json has no block for {missing}")

    def walk(node, path):
        if isinstance(node, dict):
            if any(s in node for s in SCENARIOS):
                absent = [s for s in SCENARIOS if s not in node]
                if absent:
                    raise LeverAssumptionsError(
                        f"{path}: scenario dict is missing {absent}")
                return
            for k, v in node.items():
                walk(v, f"{path}.{k}")

    for code in LEVER_CODES:
        walk(a[code], code)


def load(path: Path | str | None = None) -> tuple[dict, str]:
    """Returns (assumptions, sha256 of the file's bytes)."""
    p = Path(path) if path else CONFIG_PATH
    try:
        raw = p.read_bytes()
    except FileNotFoundError:
        raise LeverAssumptionsError(f"lever assumptions file not found: {p}")
    a = json.loads(raw.decode("utf-8"))
    _validate(a)
    return a, hashlib.sha256(raw).hexdigest()


def pick(value, scenario: str):
    """The `scenario` entry of a {low, base, high} dict; a scalar unchanged."""
    if isinstance(value, dict) and scenario in value:
        return value[scenario]
    return value


def with_overrides(block: dict, overrides: dict) -> dict:
    """A copy of one lever's block with some values replaced. Used by the
    app's what-if explorer: an override for a scenario-dict key replaces all
    three scenarios with the same value, so the explorer shows one
    'what if this were X' figure rather than three."""
    out = copy.deepcopy(block)
    for k, v in overrides.items():
        if isinstance(out.get(k), dict) and any(s in out[k] for s in SCENARIOS):
            out[k] = {s: v for s in SCENARIOS}
        else:
            out[k] = v
    return out
