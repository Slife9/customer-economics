"""Acceptance audit for the L1 rewards system (engine/rewards, rewards_app,
the reward_stress generator profile). A script, like every other file here.

    python audit/audit_l1_rewards_system.py

1. Workbook reproduction: fed the workbook's own five segments, the model
   reproduces the Reward Profitability Scenario Model v2's Calc sheets
   (specs/l1_rewards_system/workbook_expected_results.json, extracted from the
   workbook with its sha256) - 90 values + 3 totals, to the cent.
2. On both bundled samples (reward_stress and demo):
   - reconciliation: fully loaded card profit + sign-up bonus = the engine's
     net economic profit, every account;
   - segmentation: only screened accounts have a segment, exactly one each;
     the rule trace agrees with the assignment;
   - model invariants: all levers at 0 leave every account unchanged;
     unassigned accounts never change; leave probability within [0, cap];
     accounts lost within [0, accounts];
   - every app page renders without an exception.
3. reward_stress profile: the same seed regenerates the bundled sample
   byte for byte, and its segment mix populates every segment.
Byte-identity of the existing profiles is covered by
audit/audit_reward_data_additions.py (run it too).

Prints a PASS/FAIL table; exits 1 if any check FAILs.
"""
from __future__ import annotations
import hashlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import warnings
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.rewards import assumptions as A, data as D, model as M, segments as SG  # noqa: E402

SPEC = ROOT / "specs" / "l1_rewards_system"
SAMPLES = {"reward_stress": ROOT / "samples" / "reward_stress_portfolio.zip",
           "demo": ROOT / "samples" / "demo_portfolio.zip"}
RESULTS: list[tuple[str, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, "PASS" if ok else "FAIL"))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  - {detail}" if detail else ""), flush=True)


def workbook_reproduction(cfg: dict) -> None:
    print("\n1. Workbook reproduction", flush=True)
    exp = json.loads((SPEC / "workbook_expected_results.json").read_text())
    worst, n, totals_ok = 0.0, 0, True
    for scn in A.SCENARIOS:
        t = M.excel_reference_accounts(cfg)
        post = M.apply(t, cfg, A.levers_for(cfg, scn))
        mine = {"baseline_fully_loaded_profit": t["fully_loaded_profit"], "post_revenue": post["revenue"],
                "post_reward_cost": post["reward_cost"], "accounts_lost": post["accounts_lost"],
                "post_fully_loaded_profit": post["fully_loaded_profit"],
                "post_relationship_adjusted_profit": post["relationship_adjusted_profit"]}
        for seg, vals in exp[scn]["segments"].items():
            for k, v in vals.items():
                worst = max(worst, abs(float(mine[k][seg]) - v)); n += 1
        change = post["fully_loaded_profit"].sum() - t["fully_loaded_profit"].sum()
        totals_ok &= abs(change - exp[scn]["total_change_fully_loaded_profit"]) < 0.01
    record("model reproduces the workbook's Calc sheets", worst < 0.01 and totals_ok,
           f"{n} values + 3 totals; largest difference ${worst:.6f} "
           f"(workbook sha256 {exp['_source']['workbook_sha256'][:12]}...)")


def extract(sample: Path, work: Path) -> Path:
    dest = work / sample.stem
    with zipfile.ZipFile(sample) as z:
        for i in z.infolist():
            if not i.is_dir():
                p = dest / i.filename.replace("\\", "/")
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(z.read(i))
    return next(dest.rglob("Table1_Customer.csv")).parent


def portfolio_checks(label: str, root: Path, cfg: dict) -> pd.DataFrame:
    print(f"\n2. {label}", flush=True)
    t, meta = D.account_frame(root)
    diff = float((t["fully_loaded_profit"] + t["signup_bonus"] - t["engine_nep"]).abs().max())
    record(f"{label}: fully loaded + sign-up bonus = engine NEP, every account", diff < 1e-6,
           f"{len(t):,} accounts, largest difference ${diff:.8f}")

    t = SG.assign(t, cfg)
    seg_ok = (t["segment"].notna() == t["screened"]).all() and t.loc[t.screened, "segment"].isin(SG.ORDER + ["unassigned"]).all()
    rng = np.random.default_rng(0)
    sample_ids = rng.choice(t.index[t.screened], size=min(60, int(t.screened.sum())), replace=False)
    trace_ok = True
    for a in sample_ids:
        tr = SG.segment_trace(t, a, cfg)
        first = next((s["segment"] for s in tr["segments"] if s["all_met"]), "unassigned")
        trace_ok &= first == t.loc[a, "segment"] and all(r["met"] for r in tr["screen"])
    mix = t.loc[t.screened, "segment"].value_counts(normalize=True)
    record(f"{label}: one segment per screened account; rule trace agrees with the assignment",
           bool(seg_ok and trace_ok),
           f"{int(t.screened.sum()):,} screened; " + ", ".join(f"{k} {v:.0%}" for k, v in mix.items()))

    zero = {k: {s: 0.0 for s in A.SEGMENTS} for k in A.LEVERS}
    p0 = M.apply(t, cfg, zero)
    s = t[t.segment.notna()]
    unchanged = all(np.allclose(p0[c].to_numpy(), s[c].to_numpy(), atol=1e-9)
                    for c in ["fully_loaded_profit", "relationship_adjusted_profit", "reward", "interchange"])
    record(f"{label}: all levers at 0 leave every account unchanged", unchanged and float(p0["accounts_lost"].abs().max()) < 1e-12)
    ok = True
    for scn in A.SCENARIOS:
        p = M.apply(t, cfg, A.levers_for(cfg, scn))
        un = p["segment"] == "unassigned"
        ok &= np.allclose(p.loc[un, "fully_loaded_profit"], s.loc[un[un].index, "fully_loaded_profit"])
        ok &= bool(((p["attrition"] >= 0) & (p["attrition"] <= cfg["portfolio"]["max_attrition"] + 1e-12)).all())
        ok &= bool(((p["accounts_lost"] >= -1e-12) & (p["accounts_lost"] <= p["weight"] + 1e-12)).all())
    record(f"{label}: unassigned unchanged; leave probability and accounts lost within bounds (3 scenarios)", ok)
    return t


def app_pages(work: Path) -> None:
    print("\n2b. App pages", flush=True)
    code = r'''
import sys, warnings; warnings.filterwarnings("ignore")
from pathlib import Path
repo, sample = Path(sys.argv[1]), Path(sys.argv[2]); sys.path.insert(0, str(repo))
from streamlit.testing.v1 import AppTest
from rewards_app.lib import state as S
from engine.rewards import data as D
root = S.extract_zip(sample.read_bytes(), sample.stem); added = S.ensure_reward_tables(root); _, meta = D.account_frame(root)
bad = []
for page in sorted((repo / "rewards_app" / "pages").glob("*.py")):
    at = AppTest.from_file(str(page), default_timeout=300)
    for k, v in {"root": str(root), "label": sample.name, "meta": meta, "added_tables": added}.items():
        at.session_state[k] = v
    at.run()
    if len(at.exception) or len(at.error):
        bad.append(page.name)
print("BAD" if bad else "OK", ",".join(bad))
'''
    for label, sample in SAMPLES.items():
        out = subprocess.run([sys.executable, "-c", code, str(ROOT), str(sample)], capture_output=True, text=True)
        last = out.stdout.strip().splitlines()[-1] if out.stdout.strip() else out.stderr[-300:]
        record(f"{label}: all 8 app pages render without an exception", last.startswith("OK"), last)


def profile_checks(work: Path, cfg: dict) -> None:
    print("\n3. reward_stress profile", flush=True)
    out = work / "regen"
    subprocess.run([sys.executable, "-W", "ignore", "-m", "generator.run", "--profile", "reward_stress",
                    "--out", str(out)], cwd=ROOT, check=True, capture_output=True)
    z = zipfile.ZipFile(SAMPLES["reward_stress"])
    sample_hashes = {i.filename: hashlib.sha256(z.read(i)).hexdigest() for i in z.infolist()
                     if not i.filename.startswith("Validation_Report")}
    regen = {p.relative_to(out).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in out.rglob("*") if p.is_file()}
    bad = [k for k, v in sample_hashes.items() if regen.get(k) != v]
    record("same seed regenerates the bundled reward_stress sample byte for byte", not bad,
           f"{len(sample_hashes)} files compared" + (f"; differ: {bad[:5]}" if bad else ""))
    t = SG.assign(D.account_frame(out)[0], cfg)
    present = set(t.loc[t.screened, "segment"])
    record("reward_stress populates every reward segment", set(A.SEGMENTS) <= present,
           ", ".join(f"{k} {(t.segment == k).sum()}" for k in A.SEGMENTS))


def main() -> int:
    cfg, sha = A.load()
    work = Path(tempfile.mkdtemp(prefix="l1_rewards_audit_"))
    try:
        workbook_reproduction(cfg)
        for label, sample in SAMPLES.items():
            portfolio_checks(label, extract(sample, work), cfg)
        app_pages(work)
        profile_checks(work, cfg)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print("\n" + "=" * 90)
    for name, v in RESULTS:
        print(f"{v:<5} {name}")
    n_fail = sum(v == "FAIL" for _, v in RESULTS)
    print("=" * 90)
    print(f"{len(RESULTS) - n_fail}/{len(RESULTS)} PASSED" + (f", {n_fail} FAILED" if n_fail else ""))
    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
