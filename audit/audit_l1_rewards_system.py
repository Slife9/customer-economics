"""Acceptance audit for the L1 rewards system (engine/rewards, rewards_app,
the reward_stress generator profile). A script, like every other file here.

    python audit/audit_l1_rewards_system.py [--scale]

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
   - per-lever values (Shapley split) add up to each scenario's change by
     segment, and year 1 = value x the lever's year-1 share;
   - every app page renders without an exception.
2c. The bundled 100,000-customer sample (the app's default, a prebuilt
   account frame): the same checks, and with --scale, a fresh generator run
   at the same seed rebuilds it identically (about 30 minutes).
2d. Upload your data: the zip pre-check accepts complete portfolios and
   refuses incomplete ones; an upload missing Tables 25-27 but carrying a
   build manifest analyses identically; prepared .parquet files load, and
   any other parquet is refused.
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
BIG = ROOT / "samples" / "reward_stress_100k_accounts.parquet"
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
    t, meta = D.load_account_frame(root) if root.suffix == ".parquet" else D.account_frame(root)
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

    worst, ok = 0.0, True
    share = pd.Series({k: cfg["lever_timing"][k]["year1_share"] for k in A.LEVERS})
    for scn in A.SCENARIOS:
        lv = A.levers_for(cfg, scn)
        v = M.lever_values(t, cfg, lv)
        sm = M.summary(t, M.apply(t, cfg, lv))
        worst = max(worst, float((v.sum() - sm.loc[A.SEGMENTS, "change_fully_loaded_profit"]).abs().max()))
        ok &= all(v.loc[k, seg] == 0 for k in A.LEVERS for seg in A.SEGMENTS if lv[k][seg] == 0)
        ok &= abs(M.year_one(v, cfg).values.sum() - (v.sum(axis=1) * share).sum()) < 1e-6
    record(f"{label}: per-lever values add up to each scenario's change by segment; unused levers get 0; "
           f"year 1 = value x year-1 share (3 scenarios)", ok and worst < 1e-4, f"largest difference ${worst:.8f}")
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
if sample.suffix == ".parquet":
    root, added = sample, []; _, meta = D.load_account_frame(root)
else:
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
    n_pages = len(list((ROOT / "rewards_app" / "pages").glob("*.py")))
    for label, sample in (SAMPLES | {"100k sample": BIG}).items():
        out = subprocess.run([sys.executable, "-c", code, str(ROOT), str(sample)], capture_output=True, text=True)
        last = out.stdout.strip().splitlines()[-1] if out.stdout.strip() else out.stderr[-300:]
        record(f"{label}: all {n_pages} app pages render without an exception", last.startswith("OK"), last)


def upload_checks() -> None:
    print("\n2d. Upload your data", flush=True)
    import logging
    logging.disable(logging.WARNING)  # streamlit's bare-mode chatter
    from rewards_app.lib import state as S
    good = SAMPLES["reward_stress"].read_bytes()

    def rezip(drop=(), nest=""):
        src, buf = zipfile.ZipFile(io.BytesIO(good)), io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for i in src.infolist():
                if i.filename.split("/")[-1] not in drop:
                    z.writestr(nest + i.filename, src.read(i))
        return buf.getvalue()

    cases = [("complete zip", good, True), ("zip nested in a folder", rezip(nest="my_portfolio/"), True),
             ("Table9 and Table16 missing", rezip(drop={"Table9_Capital_RWA.csv", "Table16_Reward_Program_Rules.csv"}), False),
             ("Tables 25-27 missing, manifest present", rezip(drop=set(S.NEEDED)), True),
             ("Tables 25-27 and manifest missing", rezip(drop={*S.NEEDED, "build_manifest.json"}), False),
             ("not a zip", b"not a zip", False)]
    got = {name: S.check_zip(data)["ok"] for name, data, _ in cases}
    record("upload pre-check accepts complete zips and refuses incomplete ones before any build",
           all(got[name] == want for name, _, want in cases),
           ", ".join(f"{name}: {'accepted' if got[name] else 'refused'}" for name, *_ in cases))

    root = S.extract_zip(rezip(drop=set(S.NEEDED), nest="my_portfolio/"), "audit_upload")
    added = S.ensure_reward_tables(root)
    t_up = D.account_frame(root)[0]
    t_ref = D.account_frame(S.extract_zip(good, "audit_ref"))[0]
    same = t_up.equals(t_ref) and len(added) == 3
    record("an upload missing Tables 25-27 (manifest present) analyses identically to the complete zip", same,
           f"{len(t_up):,} accounts; computed {len(added)} tables")

    buf = io.BytesIO()
    pd.DataFrame({"a": [1]}).to_parquet(buf)
    try:
        S.save_parquet_upload(buf.getvalue())
        rejected = False
    except ValueError:
        rejected = True
    accepted = len(D.load_account_frame(S.save_parquet_upload(BIG.read_bytes()))[0]) > 0
    record("prepared .parquet upload: the app's own file loads; any other parquet is refused", accepted and rejected)


def big_sample_checks(cfg: dict, scale: bool, work: Path) -> None:
    print("\n2c. Bundled 100,000-customer sample (the app's default)", flush=True)
    t, meta = D.load_account_frame(BIG)
    record("100k sample: built from >= 100,000 customers of the reward_stress profile",
           meta.get("customers", 0) >= 100_000 and meta.get("profile") == "reward_stress" and len(t) > 0,
           f"{meta.get('customers', 0):,} customers generated, {t['customer'].nunique():,} with a card account, "
           f"{len(t):,} card accounts, {BIG.stat().st_size / 1e6:.1f} MB")
    portfolio_checks("100k sample", BIG, cfg)
    if not scale:
        print("  SKIP  100k sample rebuilds identically from a fresh generator run (pass --scale; ~30 min)")
        return
    from rewards_app import build_sample as B
    out = work / "regen_100k"
    B.generate(out, meta["customers"], meta["seed"])
    fresh, _ = D.account_frame(out)
    try:
        pd.testing.assert_frame_equal(fresh, t, check_exact=False, rtol=1e-12, atol=1e-9)
        same, detail = True, f"{len(fresh):,} accounts x {fresh.shape[1]} columns"
    except AssertionError as e:
        same, detail = False, str(e).splitlines()[0][:200]
    record("100k sample rebuilds identically from a fresh generator run (same seed)", same, detail)


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
        big_sample_checks(cfg, "--scale" in sys.argv, work)
        upload_checks()
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
