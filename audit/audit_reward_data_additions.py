"""Acceptance audit for the reward data additions (specs/reward_data_additions).
Run as a script, like every other file in this directory - there is no pytest
suite in this repo to join.

    python audit/audit_reward_data_additions.py
    python audit/audit_reward_data_additions.py --scale-dir <100k portfolio> \
        [--scale-json <timing JSON from the scale run>]

1. Byte-identity: regenerates demo and negative_control with the baseline
   settings (default seed, 5,000 customers, 36 cycles), runs both validators
   and the circularity report, and compares the SHA-256 of every file in
   specs/reward_data_additions/baseline_hashes.json.
2. Engine regression: python -m engine.run on that demo with --compare-to
   the negative control; run_summary.json must equal the engine baseline
   except data_dir and leverage_audit.run_timestamp_utc (they change on
   every run by design; NaN equals NaN).
3. Integrity of Tables 25-27 on both profiles (keys, months, threshold met
   recomputed independently from Table5, non-negative counts, MCC coverage,
   masked identifiers).
4. Determinism: the same seed gives byte-identical new tables; a different
   new-stream seed changes only the new-stream fields (and fields derived
   from them) while the existing data stays fixed.
5. Calibration report: produced for the demo (and the scale portfolio).
6. Scale (optional): integrity on a large portfolio built on this branch,
   plus the recorded time and peak memory of the added step.

Prints a PASS/FAIL table; exits 1 if any check FAILs.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from generator import reward_additions as RA  # noqa: E402

SPEC = ROOT / "specs" / "reward_data_additions"
PROFILES = ["demo", "negative_control"]
SEED = 20260921
NEW = ["Table25_MCC_Reference.csv", "Table26_Signup_Bonus.csv", "Table27_Bureau_Inquiries.csv"]
VOLATILE = {"/data_dir", "/leverage_audit/run_timestamp_utc"}
T26_STREAM = ["Bonus Offered", "Offer Spend Threshold USD", "Offer Window Months", "Bonus Value USD",
              "Threshold Met", "Bonus Earned Cycle Month", "Bonus Paid USD",
              "Closed Within 12 Months Of Bonus"]
T27_STREAM = ["Hard Inquiries", "New Trades Opened Elsewhere", "Inquiries Trailing 12m"]

RESULTS: list[tuple[str, str, str]] = []


def record(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((name, "PASS" if ok else "FAIL", detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  - {detail}" if detail else ""), flush=True)
    return ok


def sh(*args: str) -> None:
    subprocess.run([sys.executable, "-W", "ignore", *args], cwd=ROOT, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def hash_tree(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


# ------------------------------------------------------------- 1, 2
def byte_identity(work: Path) -> None:
    print("\n1. Byte-identity against the baseline", flush=True)
    t0 = time.time()
    for p in PROFILES:
        sh("-m", "generator.run", "--profile", p, "--out", str(work / p))
        sh("-m", "generator.validate.check", "--data", str(work / p))
    sh("-m", "generator.validate.circularity", "--root", str(work))
    base = json.loads((SPEC / "baseline_hashes.json").read_text())["files"]
    got = hash_tree(work)
    mismatched = [k for k in base if k in got and got[k] != base[k]]
    missing = [k for k in base if k not in got]
    added = sorted(k for k in got if k not in base)
    record("every pre-existing file byte-identical",
           not mismatched and not missing,
           f"{len(base)} baseline files; mismatched {mismatched or 0}; missing {missing or 0} "
           f"({time.time() - t0:.0f}s)")
    expected = sorted(f"{p}/{t}" for p in PROFILES for t in NEW)
    record("only the new tables were added", added == expected, f"added: {added}")


def _compare_summary(a, b, p="", out=None):
    out = [] if out is None else out
    if p in VOLATILE:
        return out
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                out.append(f"missing {p}/{k}")
            else:
                _compare_summary(a[k], b[k], f"{p}/{k}", out)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f"length {p}")
        else:
            for i, (u, v) in enumerate(zip(a, b)):
                _compare_summary(u, v, f"{p}[{i}]", out)
    elif isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b):
        pass
    elif a != b:
        out.append(f"{p}: {a!r} vs {b!r}")
    return out


def engine_regression(work: Path) -> None:
    print("\n2. Engine regression", flush=True)
    t0 = time.time()
    sh("-m", "engine.run", "--data", str(work / "demo"), "--out", str(work / "_engine"),
       "--compare-to", str(work / "negative_control"))
    base = json.loads((SPEC / "engine_baseline_run_summary.json").read_text())
    got = json.loads((work / "_engine" / "run_summary.json").read_text())
    note = "identical except data_dir and leverage_audit.run_timestamp_utc"
    # policy_sha256 hashes the policy file's raw bytes, so it also differs when
    # git checked the file out with other line endings (core.autocrlf: the
    # baseline came from a fresh checkout). Accept that one field only if the
    # baseline hash is exactly this policy file with CRLF or LF line endings.
    pb, pg = base["leverage_audit"]["policy_sha256"], got["leverage_audit"]["policy_sha256"]
    if pb != pg:
        raw = (ROOT / "engine" / "config" / got["leverage_audit"]["policy_file"]).read_bytes()
        lf = raw.replace(b"\r\n", b"\n")
        if pb in {hashlib.sha256(lf).hexdigest(), hashlib.sha256(lf.replace(b"\n", b"\r\n")).hexdigest()}:
            base = json.loads(json.dumps(base))
            base["leverage_audit"]["policy_sha256"] = pg
            note += "; policy_sha256 differs by line endings only (same policy file content)"
    diffs = _compare_summary(base, got)
    record("run_summary.json equals the engine baseline", not diffs,
           (f"{len(diffs)} differences: {diffs[:3]}" if diffs else note) + f" ({time.time() - t0:.0f}s)")


# ------------------------------------------------------------- 3
def _window_spend_independent(d: Path, t26: pd.DataFrame, cycles: list[str]) -> pd.DataFrame:
    """Recompute spend in each offer window from Table5 by a different route
    than the generator (merge transactions onto window months, chunked)."""
    c_ix = {c: i for i, c in enumerate(cycles)}
    w = t26.loc[t26["Window Observed"].astype(bool), ["Masked Account Number", "Account Open Cycle Index"]]
    o = w.set_index("Masked Account Number")["Account Open Cycle Index"]
    tot = pd.Series(0.0, index=o.index)
    monthly = []
    for ch in pd.read_csv(d / "Table5_Transaction.csv", chunksize=RA.CHUNK_ROWS,
                          usecols=["Masked Account Number", "Cycle Month", "Transaction Amount",
                                   "Cash Advance Indicator"]):
        ch = ch[~ch["Cash Advance Indicator"].astype(bool) & ch["Masked Account Number"].isin(o.index)]
        k = ch["Cycle Month"].map(c_ix) - o.reindex(ch["Masked Account Number"]).to_numpy()
        ch = ch[(k >= 0) & (k < RA.OFFER_WINDOW_MONTHS)].assign(k=k)
        monthly.append(ch.groupby(["Masked Account Number", "k"])["Transaction Amount"].sum())
    m = pd.concat(monthly).groupby(level=[0, 1]).sum().unstack(fill_value=0.0) if monthly else pd.DataFrame()
    m = m.reindex(index=o.index, columns=range(RA.OFFER_WINDOW_MONTHS), fill_value=0.0)
    return m


def integrity(d: Path, label: str, threshold_check: bool = True) -> None:
    print(f"\n3. Integrity - {label}", flush=True)
    cust = pd.read_csv(d / "Table1_Customer.csv", usecols=["Masked Customer Number"])
    acct = pd.read_csv(d / "Table2_Card_Account.csv", usecols=["Masked Customer Number", "Masked Account Number"])
    t25 = pd.read_csv(d / "Table25_MCC_Reference.csv")
    t26 = pd.read_csv(d / "Table26_Signup_Bonus.csv")
    t27 = pd.read_csv(d / "Table27_Bureau_Inquiries.csv")
    cycles = RA._cycles(d)

    j = t26[["Masked Account Number", "Masked Customer Number"]].merge(
        acct, on="Masked Account Number", how="outer", suffixes=("", "_t2"), indicator=True)
    record(f"{label}: Table26 joins 1:1 to Table2 (account and customer)",
           len(t26) == len(acct) and t26["Masked Account Number"].is_unique and (j["_merge"] == "both").all()
           and (j["Masked Customer Number"] == j["Masked Customer Number_t2"]).all(),
           f"{len(t26):,} rows vs {len(acct):,} accounts")
    record(f"{label}: Table27 customers join to Table1", set(t27["Masked Customer Number"]) == set(cust["Masked Customer Number"]),
           f"{t27['Masked Customer Number'].nunique():,} vs {len(cust):,}")
    full = (len(t27) == len(cust) * len(cycles)
            and not t27.duplicated(["Masked Customer Number", "Cycle Month"]).any()
            and sorted(t27["Cycle Month"].unique()) == cycles)
    record(f"{label}: Table27 has every customer-month exactly once", full,
           f"{len(t27):,} rows = {len(cust):,} x {len(cycles)}")

    neg = (t27[T27_STREAM + ["Trailing Window Months"]] < 0).any().any()
    trades_ok = (t27["New Trades Opened Elsewhere"] <= t27["Hard Inquiries"]).all()
    t27s = t27.sort_values(["Masked Customer Number", "Cycle Month"])
    roll = (t27s.groupby("Masked Customer Number")["Hard Inquiries"]
            .transform(lambda s: s.rolling(RA.TRAILING_MONTHS, min_periods=1).sum()).astype(int))
    record(f"{label}: counts non-negative; new trades <= inquiries; trailing-12m reproducible",
           not neg and trades_ok and (roll == t27s["Inquiries Trailing 12m"]).all())
    bonus_neg = (t26[["Offer Spend Threshold USD", "Bonus Value USD", "Bonus Paid USD",
                      "Spend In Offer Window USD"]] < 0).any().any()
    record(f"{label}: Table26 amounts non-negative", not bonus_neg)

    mccs = set()
    for ch in pd.read_csv(d / "Table5_Transaction.csv", chunksize=RA.CHUNK_ROWS, usecols=[RA.MCC_COL]):
        mccs |= set(ch[RA.MCC_COL].unique())
    missing = mccs - set(t25[RA.MCC_COL])
    must = set(RA.QUASI_CASH_MCCS) | set(RA.LOW_INTERCHANGE_MCCS)
    record(f"{label}: Table25 covers every MCC in Table5 plus the listed codes",
           not missing and must <= set(t25[RA.MCC_COL]) and t25[RA.MCC_COL].is_unique,
           f"{len(mccs)} MCCs in Table5, {len(t25)} rows")

    masked = (t26["Masked Account Number"].str.match(r"^ACC\d+$").all()
              and t26["Masked Customer Number"].str.match(r"^CUS\d+$").all()
              and t27["Masked Customer Number"].str.match(r"^CUS\d+$").all())
    record(f"{label}: identifiers are masked (CUS / ACC) only", bool(masked))

    if threshold_check:
        m = _window_spend_independent(d, t26, cycles)
        w = t26[t26["Window Observed"].astype(bool)].set_index("Masked Account Number")
        spend = m.sum(axis=1)
        offered = w["Bonus Offered"].astype(bool)
        thr = w["Offer Spend Threshold USD"]
        exp_met = offered & (spend.reindex(w.index) >= thr)
        got_met = w["Threshold Met"].eq(True)
        first = (m.cumsum(axis=1).ge(thr.reindex(m.index), axis=0)).idxmax(axis=1)
        exp_month = pd.Series([cycles[int(o) + int(k)] for o, k in zip(w["Account Open Cycle Index"], first.reindex(w.index))],
                              index=w.index).where(exp_met)
        got_month = w["Bonus Earned Cycle Month"].where(got_met)
        spend_ok = np.allclose(spend.reindex(w.index).to_numpy(), w["Spend In Offer Window USD"].to_numpy(), atol=0.011)
        pre = t26[~t26["Window Observed"].astype(bool)]
        record(f"{label}: Threshold Met / month earned / bonus paid reproducible from Table5",
               bool((exp_met == got_met).all() and exp_month.fillna("").eq(got_month.fillna("")).all()
                    and spend_ok and pre["Threshold Met"].isna().all()
                    and (w.loc[got_met, "Bonus Paid USD"] == w.loc[got_met, "Bonus Value USD"]).all()),
               f"{int(got_met.sum()):,} met of {int((offered).sum()):,} offered with the window observed; "
               f"{len(pre):,} pre-history accounts left blank")


# ------------------------------------------------------------- 4
def determinism(work: Path) -> None:
    print("\n4. Determinism", flush=True)
    d = work / "demo"
    a, b, c = work / "_det_a", work / "_det_b", work / "_det_c"
    RA.add_reward_tables(d, SEED, a)
    RA.add_reward_tables(d, SEED, b)
    same = all(hashlib.sha256((a / t).read_bytes()).digest() == hashlib.sha256((b / t).read_bytes()).digest()
               for t in NEW)
    in_build = all(hashlib.sha256((a / t).read_bytes()).digest() == hashlib.sha256((d / t).read_bytes()).digest()
                   for t in NEW)
    record("same seed -> byte-identical new tables (and equal to build()'s)", same and in_build)

    RA.add_reward_tables(d, SEED + 1, c)
    t25a, t25c = (pd.read_csv(x / NEW[0]) for x in (a, c))
    t26a, t26c = (pd.read_csv(x / NEW[1]) for x in (a, c))
    t27a, t27c = (pd.read_csv(x / NEW[2]) for x in (a, c))
    fixed26 = [col for col in t26a.columns if col not in T26_STREAM]
    fixed27 = [col for col in t27a.columns if col not in T27_STREAM]
    unchanged = (t25a.equals(t25c) and t26a[fixed26].equals(t26c[fixed26]) and t27a[fixed27].equals(t27c[fixed27]))
    changed = (not t26a["Bonus Offered"].equals(t26c["Bonus Offered"])
               and not t27a["Hard Inquiries"].equals(t27c["Hard Inquiries"]))
    record("different new-stream seed changes only new-stream fields", unchanged and changed,
           f"unchanged: Table25, Table26 {fixed26}, Table27 {fixed27}")
    base = json.loads((SPEC / "baseline_hashes.json").read_text())["files"]
    untouched = all(hashlib.sha256((d / Path(k).name).read_bytes()).hexdigest() == v
                    for k, v in base.items() if k.startswith("demo/") and k.count("/") == 1)
    record("existing demo files untouched by the extra runs", untouched)


# ------------------------------------------------------------- 5, 6
def calibration(d: Path, label: str) -> dict:
    print(f"\n5. Calibration report - {label}", flush=True)
    t0 = time.time()
    out = subprocess.run([sys.executable, "-W", "ignore", str(ROOT / "audit" / "reward_calibration_report.py"),
                          "--data", str(d)], cwd=ROOT, capture_output=True, text=True)
    ok = out.returncode == 0 and (d / "Validation_Report_Reward_Calibration.csv").exists()
    summary = json.loads(out.stdout) if ok else {}
    record(f"{label}: calibration report produced (informational, never fails)", ok,
           (f"screened {summary.get('screened_accounts')}; within {summary.get('within')}, "
            f"outside {summary.get('outside')}, not assessed {summary.get('not assessed')}"
            if ok else out.stderr[-300:]) + f" ({time.time() - t0:.0f}s)")
    return summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", default=None, help="where to generate (default: a temp dir, removed after)")
    ap.add_argument("--scale-dir", default=None, help="a large portfolio generated on this branch")
    ap.add_argument("--scale-json", default=None, help="timing/memory JSON recorded when it was generated")
    a = ap.parse_args()
    work = Path(a.workdir) if a.workdir else Path(tempfile.mkdtemp(prefix="reward_audit_"))
    if work.exists() and a.workdir:
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)
    try:
        byte_identity(work)
        engine_regression(work)
        for p in PROFILES:
            integrity(work / p, p)
        determinism(work)
        calibration(work / "demo", "demo 5k")
        if a.scale_dir:
            sd = Path(a.scale_dir)
            integrity(sd, f"scale {sd.name}")
            calibration(sd, f"scale {sd.name}")
            if a.scale_json:
                s = json.loads(Path(a.scale_json).read_text())
                record(f"scale {sd.name}: new tables built inside build()",
                       all(t in s["new_table_rows"] for t in NEW),
                       f"{s['customers']:,} customers; reward step {s['reward_step_seconds']}s, "
                       f"+{s['reward_step_added_gb']} GB over {s['reward_step_rss_before_gb']} GB; "
                       f"whole build {s['build_seconds_total']}s, peak {s['build_peak_rss_gb']} GB")
    finally:
        if not a.workdir:
            shutil.rmtree(work, ignore_errors=True)

    print("\n" + "=" * 100)
    for name, verdict, _ in RESULTS:
        print(f"{verdict:<5} {name}")
    n_fail = sum(v == "FAIL" for _, v, _ in RESULTS)
    print("=" * 100)
    print(f"{len(RESULTS) - n_fail}/{len(RESULTS)} PASSED" + (f", {n_fail} FAILED" if n_fail else ""))
    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
