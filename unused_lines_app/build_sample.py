"""Precompute a dataset for the Unused Credit Line Management app (offline).

    python -m unused_lines_app.build_sample --data <portfolio dir> --name stress \
        --label "Unused-line stress book (100,000 customers) - synthetic stress data"

Writes samples/unused_lines/<name>/:
    accounts.parquet      the module's per-account file (engine/unused_lines/data.py)
    monthly.parquet       the 12 cycles behind each account's transactor test
    engine_view.parquet   per customer: the ML model's action (second opinion),
                          protected customers (the system's suppression: they
                          receive no action) and membership of the system's
                          L1 / L3 / L5 worklists,
                          from engine.run.build_pipeline (read only)
    meta.json             label, sizes, build time, peak memory, machine

The app loads only these files; it never runs this build (the full build needs
the raw portfolio and, at 100k customers, about 15.6 GB). Peak memory and time
are recorded for STATUS.md and the evaluation guide.
"""
from __future__ import annotations
import argparse
import json
import os
import platform
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.unused_lines import data as D  # noqa: E402

OUT = ROOT / "samples" / "unused_lines"
K, C = "Masked Account Number", "Masked Customer Number"


def monthly(data_dir: Path, accounts: pd.Index, last12: list[str]) -> pd.DataFrame:
    cols = [K, "Cycle Month", "Credit Limit", "Ending Balance", "Payment Made", "Paid In Full Indicator",
            "Promotional Balance", "Purchases Authorized", "Utilization", "Days Past Due"]
    c = pd.read_csv(data_dir / "Table4_Account_Cycle.csv", usecols=cols)
    c = c[c["Cycle Month"].isin(last12) & c[K].isin(accounts)].copy()
    plan = data_dir / "Table5b_Installment_Plan_Cycle.csv"
    if plan.exists():
        p = pd.read_csv(plan, usecols=[K, "Cycle Month", "Remaining Principal"])
        p = p[p["Cycle Month"].isin(last12)].groupby([K, "Cycle Month"])["Remaining Principal"].sum()
        c["Plan Balance"] = pd.MultiIndex.from_frame(c[[K, "Cycle Month"]]).map(p).fillna(0.0) \
            if len(p) else 0.0
    else:
        c["Plan Balance"] = 0.0
    c["Statement Balance"] = c["Ending Balance"] + c["Payment Made"]
    return c.sort_values([K, "Cycle Month"]).reset_index(drop=True)


def engine_view(data_dir: Path) -> pd.DataFrame:
    from engine import run as ER
    pipe = ER.build_pipeline(data_dir)
    cv = pipe["customer_view"]
    keep = [C] + [c for c in ["ml_action", "ml_primary_reason", "ml_recommended_limit"] if c in cv]
    supp = pipe["suppressed"].suppressed
    # The customer view is the population after suppression; add the
    # suppressed customers back so they can be shown as protected.
    out = pd.concat([cv[keep], supp[[c for c in keep if c in supp]]], ignore_index=True).drop_duplicates(C)
    sup = supp.set_index(C)["suppression_reason"]
    out["protected"] = out[C].isin(sup.index)
    out["suppression_reason"] = out[C].map(sup).fillna("")
    for code in ["L1", "L3", "L5"]:
        wl = pipe["worklists"].get(code)
        out[f"in_{code}"] = out[C].isin(set(wl[C])) if wl is not None and len(wl) else False
    return out


def build(data_dir: Path, name: str, label: str) -> dict:
    t0 = time.time()
    dest = OUT / name
    dest.mkdir(parents=True, exist_ok=True)
    acc, meta = D.account_frame(data_dir)
    t_frame = time.time() - t0
    meta = {**meta, "data_dir": label}
    D.save_account_frame(acc, meta, dest / "accounts.parquet")
    monthly(data_dir, acc.index, meta["trailing"]).to_parquet(dest / "monthly.parquet", compression="zstd")
    engine_view(data_dir).to_parquet(dest / "engine_view.parquet", compression="zstd")
    manifest = json.loads((data_dir / "build_manifest.json").read_text())
    peak = None
    try:
        import psutil
        mi = psutil.Process().memory_info()
        peak = round((getattr(mi, "peak_wset", None) or mi.rss) / 1e9, 2)
        ram = round(psutil.virtual_memory().total / 1e9, 1)
    except ImportError:
        ram = None
    info = {
        "label": label, "profile": manifest.get("profile"), "seed": manifest.get("seed"),
        "customers": int(manifest.get("customers", 0)), "card_accounts": int(len(acc)),
        "cycles": meta["cycles"], "from": meta["first"], "to": meta["last"],
        "build_seconds": round(time.time() - t0, 1), "account_frame_seconds": round(t_frame, 1),
        "build_peak_memory_gb": peak,
        "machine": {"os": platform.platform(), "python": platform.python_version(),
                    "cpus": os.cpu_count(), "ram_gb": ram},
        "files_mb": {p.name: round(p.stat().st_size / 1e6, 2) for p in dest.glob("*.parquet")},
    }
    (dest / "meta.json").write_text(json.dumps(info, indent=2) + "\n")
    return info


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="a generated portfolio directory")
    ap.add_argument("--name", required=True, help="folder name under samples/unused_lines")
    ap.add_argument("--label", required=True, help="dataset name shown in the app")
    a = ap.parse_args()
    print(json.dumps(build(Path(a.data), a.name, a.label), indent=2))
