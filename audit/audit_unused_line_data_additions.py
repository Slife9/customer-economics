"""Acceptance audit for the unused-line data additions (specs/unused_line_management,
Stage 2). Run as a script, like every other file in this directory - there is
no pytest suite in this repo to join.

    python audit/audit_unused_line_data_additions.py
    python audit/audit_unused_line_data_additions.py --scale-dir <large portfolio>

1. Byte-identity: regenerates demo, transactor_heavy, subprime_heavy and
   premium_heavy with the baseline settings (default seed, profile size,
   36 cycles), runs the validator on each and the circularity report, and
   compares the SHA-256 of every file in
   specs/unused_line_management/baseline_hashes.json (generated on main
   b660bb8 before this change). negative_control crashes on main
   (ISSUES_FOUND.md #4), so it is not in the baseline.
2. Engine regression: python -m engine.run on that demo; run_summary.json must
   equal the engine baseline except data_dir and
   leverage_audit.run_timestamp_utc (they change on every run by design).
3. Integrity of Table29 and Table30 on every profile: keys, scores
   reproducible from Table8/Table1 by an independent route, activation
   consistent with first use recomputed from Table5, masked identifiers.
4. Determinism: the same seed gives byte-identical new tables; a different
   new-stream seed changes only the new-stream fields.
5. Calibration report: produced for the demo (informational, never fails).
6. Scale (optional): the additions step on a large existing portfolio,
   written to a scratch directory (the portfolio is only read), with time and
   peak memory.

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

from generator import unused_line_additions as ULA  # noqa: E402

SPEC = ROOT / "specs" / "unused_line_management"
PROFILES = ["demo", "transactor_heavy", "subprime_heavy", "premium_heavy"]
SEED = 20260921
NEW = ["Table29_Score_History.csv", "Table30_Card_Activation.csv"]
VOLATILE = {"/data_dir", "/leverage_audit/run_timestamp_utc"}
T29_STREAM = ["Bureau Score", "Bureau Score Change 6 Months"]
T30_STREAM = ["Activation Status", "Activation Cycle Index", "Activation Cycle Month",
              "Activation Basis"]
ACCT, CUST = "Masked Account Number", "Masked Customer Number"

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
    sh("-m", "engine.run", "--data", str(work / "demo"), "--out", str(work / "_engine"))
    base = json.loads((SPEC / "engine_baseline_run_summary.json").read_text())
    got = json.loads((work / "_engine" / "run_summary.json").read_text())
    diffs = _compare_summary(base, got)
    record("run_summary.json equals the engine baseline", not diffs,
           (f"{len(diffs)} differences: {diffs[:3]}" if diffs
            else "identical except data_dir and leverage_audit.run_timestamp_utc")
           + f" ({time.time() - t0:.0f}s)")


# ------------------------------------------------------------- 3
def _behaviour_independent(t8: pd.DataFrame) -> pd.Series:
    """Behaviour score recomputed by a different route than the generator:
    per-account rolling mean of the PD log-odds in pandas, then the scaling."""
    s = t8.sort_values([ACCT, "Cycle Month"])
    p = s["PD 12 Month"].clip(1e-6, 1 - 1e-6)
    lo = np.log(p / (1 - p))
    sm = lo.groupby(s[ACCT]).transform(lambda x: x.rolling(ULA.SMOOTHING_CYCLES, min_periods=1).mean())
    score = ULA.ANCHOR_SCORE + ULA.POINTS_TO_DOUBLE_ODDS / math.log(2) * (-sm - math.log(ULA.ANCHOR_ODDS))
    return pd.Series(np.clip(np.rint(score), ULA.SCORE_MIN, ULA.SCORE_MAX).astype(int).to_numpy(),
                     index=pd.MultiIndex.from_frame(s[[ACCT, "Cycle Month"]]))


def integrity_t29(d: Path, label: str, new_dir: Path) -> None:
    acct = pd.read_csv(d / "Table2_Card_Account.csv", usecols=[CUST, ACCT])
    t8 = pd.read_csv(d / "Table8_Risk_Parameters.csv", usecols=[CUST, ACCT, "Cycle Month", "PD 12 Month"])
    t4 = pd.read_csv(d / "Table4_Account_Cycle.csv", usecols=[ACCT, "Cycle Month", "Days Past Due"])
    t1 = pd.read_csv(d / "Table1_Customer.csv", usecols=[CUST, "Credit Score"])
    t29 = pd.read_csv(new_dir / "Table29_Score_History.csv",
                      dtype={"Bureau Score Change 6 Months": "Int64"})

    keys = [ACCT, "Cycle Month"]
    j = t29[keys + [CUST]].merge(t8[keys + [CUST]], on=keys, how="outer", suffixes=("", "_t8"),
                                 indicator=True)
    record(f"{label}: Table29 rows 1:1 with Table8 account-cycles, customer matches",
           len(t29) == len(t8) and not t29.duplicated(keys).any() and (j["_merge"] == "both").all()
           and (j[CUST] == j[f"{CUST}_t8"]).all()
           and set(t29[ACCT]) <= set(acct[ACCT]),
           f"{len(t29):,} rows vs {len(t8):,}")

    beh = _behaviour_independent(t8)
    got = t29.set_index(keys)["Behaviour Score"]
    record(f"{label}: Behaviour Score reproducible from Table8 PD 12 Month",
           bool((got.reindex(beh.index) == beh).all()))

    in_range = t29[["Behaviour Score", "Bureau Score"]].apply(
        lambda c: c.between(ULA.SCORE_MIN, ULA.SCORE_MAX)).all().all()
    s = t29.sort_values(keys)
    lag = s.groupby(ACCT)["Bureau Score"].shift(ULA.CHANGE_WINDOW)
    chg = (s["Bureau Score"] - lag).astype("Int64")
    chg_ok = chg.fillna(-99999).eq(s["Bureau Score Change 6 Months"].fillna(-99999)).all()
    hist = s.groupby(ACCT).cumcount() + 1
    # Months are consecutive per account (no gaps), so the 6-cycle shift is 6 months.
    record(f"{label}: scores in 300-850; 6-month change and months of history reproducible",
           bool(in_range and chg_ok and (hist.to_numpy() == s["Months Of Score History"].to_numpy()).all()))

    first = s.groupby(ACCT).head(1).merge(t4, on=keys)
    anchor = first[CUST].map(t1.set_index(CUST)["Credit Score"])
    clean = first["Days Past Due"] < ULA.DPD_PENALTY_FROM_DAYS
    exp = np.clip(anchor, ULA.SCORE_MIN, ULA.SCORE_MAX)
    record(f"{label}: first-cycle Bureau Score equals Table1 Credit Score (no delinquency that cycle)",
           bool((first.loc[clean, "Bureau Score"] == exp[clean]).all()),
           f"{int(clean.sum()):,} of {len(first):,} accounts checked")

    m = s.merge(t4, on=keys)
    m["dpd30_recent"] = (m["Days Past Due"] >= 30).astype(int).groupby(m[ACCT]).transform(
        lambda x: x.rolling(ULA.CHANGE_WINDOW + 1, min_periods=1).max()).astype(bool)
    c = m["Bureau Score Change 6 Months"].astype(float)
    drop_d, drop_c = (c[m["dpd30_recent"]] <= -40).mean(), (c[~m["dpd30_recent"]] <= -40).mean()
    record(f"{label}: 40-point drops concentrate in recently delinquent accounts",
           bool(drop_d > 5 * drop_c),
           f"share of cycles with a drop >= 40: {drop_d:.1%} after 30+ DPD vs {drop_c:.2%} otherwise")

    masked = (t29[ACCT].str.match(r"^ACC\d+$").all() and t29[CUST].str.match(r"^CUS\d+$").all())
    record(f"{label}: Table29 identifiers are masked (CUS / ACC) only", bool(masked))


def integrity_t30(d: Path, label: str, new_dir: Path) -> None:
    t3 = pd.read_csv(d / "Table3_Card.csv")
    t30 = pd.read_csv(new_dir / "Table30_Card_Activation.csv",
                      dtype={"First Use Cycle Index": "Int64", "Activation Cycle Index": "Int64"},
                      keep_default_na=False, na_values={"First Use Cycle Index": [""],
                                                        "Activation Cycle Index": [""]})
    cycles = ULA._cycles(d)
    n_cyc = len(cycles)

    same = (len(t30) == len(t3) and t30["Masked Card Number"].is_unique
            and (t30["Masked Card Number"].to_numpy() == t3["Masked Card Number"].to_numpy()).all()
            and (t30[ACCT].to_numpy() == t3[ACCT].to_numpy()).all()
            and (t30["Issue Cycle Index"].to_numpy() == t3["Issue Cycle Index"].to_numpy()).all())
    record(f"{label}: Table30 rows 1:1 with Table3 cards, same order and keys", bool(same),
           f"{len(t30):,} cards")

    # First use recomputed by another route: merge each card's live period onto
    # the account's months with any Table5 row.
    tx = pd.concat([ch.drop_duplicates() for ch in pd.read_csv(
        d / "Table5_Transaction.csv", usecols=[ACCT, "Cycle Month"], chunksize=ULA.CHUNK_ROWS)]).drop_duplicates()
    c_ix = {c: i for i, c in enumerate(cycles)}
    tx["t"] = tx["Cycle Month"].map(c_ix)
    t4 = pd.read_csv(d / "Table4_Account_Cycle.csv", usecols=[ACCT, "Cycle Index"])
    open_end = t4.groupby(ACCT)["Cycle Index"].max() + 1
    cards = t3[["Masked Card Number", ACCT, "Issue Cycle Index", "Deactivation Cycle Index", "Card Status"]].copy()
    cards["start"] = cards["Issue Cycle Index"].clip(lower=0)
    cards["end"] = np.minimum(np.where(cards["Card Status"] == "active", n_cyc,
                                       cards["Deactivation Cycle Index"]),
                              cards[ACCT].map(open_end).fillna(0).astype(int))
    mm = cards.merge(tx[[ACCT, "t"]], on=ACCT)
    mm = mm[(mm["t"] >= mm["start"]) & (mm["t"] < mm["end"])]
    fu = mm.groupby("Masked Card Number")["t"].min().reindex(t30["Masked Card Number"])
    got_fu = t30.set_index("Masked Card Number")["First Use Cycle Index"]
    fu_ok = (fu.fillna(-1).astype(int).to_numpy() == got_fu.fillna(-1).astype(int).to_numpy()).all()
    live = (cards["end"] - cards["start"]).clip(lower=0)
    record(f"{label}: First Use and Months Live reproducible from Table5 / Table3 / Table4",
           bool(fu_ok and (live.to_numpy() == t30["Months Live In Window"].to_numpy()).all()),
           f"{int(fu.notna().sum()):,} cards used in the window")

    t30["end"] = cards["end"].to_numpy()
    act = t30["Activation Status"] == "activated"
    used = t30["First Use Cycle Index"].notna()
    ai = t30["Activation Cycle Index"]
    ok = (
        set(t30["Activation Status"]) <= {"activated", "not_activated", "not_observed"}
        and (t30.loc[used, "Activation Status"] == "activated").all()
        and (ai[used] <= t30.loc[used, "First Use Cycle Index"]).all()
        and (ai[act] >= t30.loc[act, "Issue Cycle Index"]).all()
        and (ai[act] < t30.loc[act, "end"]).all()
        and ai[~act].isna().all()
        and ((t30["Activation Status"] == "not_observed") == (t30["end"] <= 0)).all()
    )
    record(f"{label}: every used card activated by first use; activation inside the card's life",
           bool(ok), t30["Activation Status"].value_counts().to_dict().__repr__())

    in_win = act & (ai >= 0) & (ai < n_cyc)
    months_ok = all(t30.loc[in_win, "Activation Cycle Month"].to_numpy()
                    == np.array(cycles)[ai[in_win].astype(int).to_numpy()]) \
        and (t30.loc[~in_win, "Activation Cycle Month"] == "").all()
    record(f"{label}: Activation Cycle Month matches the index (blank outside the window)", bool(months_ok))
    masked = (t30["Masked Card Number"].str.match(r"^CRD\d+$").all() and t30[ACCT].str.match(r"^ACC\d+$").all())
    record(f"{label}: Table30 identifiers are masked (CRD / ACC) only", bool(masked))


def integrity(d: Path, label: str, new_dir: Path | None = None) -> None:
    """`new_dir` holds the new tables when they were written outside the
    portfolio (the scale check never writes into the portfolio)."""
    print(f"\n3. Integrity - {label}", flush=True)
    integrity_t29(d, label, new_dir or d)
    integrity_t30(d, label, new_dir or d)


# ------------------------------------------------------------- 4
def determinism(work: Path) -> None:
    print("\n4. Determinism", flush=True)
    d = work / "demo"
    a, b, c = work / "_det_a", work / "_det_b", work / "_det_c"
    ULA.add_unused_line_tables(d, SEED, a)
    ULA.add_unused_line_tables(d, SEED, b)
    digest = lambda p: hashlib.sha256(p.read_bytes()).digest()  # noqa: E731
    same = all(digest(a / t) == digest(b / t) for t in NEW)
    in_build = all(digest(a / t) == digest(d / t) for t in NEW)
    record("same seed -> byte-identical new tables (and equal to build()'s)", same and in_build)

    ULA.add_unused_line_tables(d, SEED + 1, c)
    t29a, t29c = (pd.read_csv(x / NEW[0]) for x in (a, c))
    t30a, t30c = (pd.read_csv(x / NEW[1]) for x in (a, c))
    fixed29 = [col for col in t29a.columns if col not in T29_STREAM]
    fixed30 = [col for col in t30a.columns if col not in T30_STREAM]
    unchanged = t29a[fixed29].equals(t29c[fixed29]) and t30a[fixed30].equals(t30c[fixed30])
    changed = (not t29a["Bureau Score"].equals(t29c["Bureau Score"])
               and not t30a["Activation Cycle Index"].equals(t30c["Activation Cycle Index"]))
    record("different new-stream seed changes only new-stream fields", unchanged and changed,
           f"unchanged: Table29 {fixed29}, Table30 {fixed30}")
    base = json.loads((SPEC / "baseline_hashes.json").read_text())["files"]
    untouched = all(hashlib.sha256((d / Path(k).name).read_bytes()).hexdigest() == v
                    for k, v in base.items() if k.startswith("demo/") and k.count("/") == 1)
    record("existing demo files untouched by the extra runs", untouched)


# ------------------------------------------------------------- 5, 6
def calibration(d: Path, label: str, out: Path) -> dict:
    print(f"\n5. Calibration report - {label}", flush=True)
    t0 = time.time()
    r = subprocess.run([sys.executable, "-W", "ignore", str(ROOT / "audit" / "unused_line_calibration_report.py"),
                        "--data", str(d), "--out", str(out)], cwd=ROOT, capture_output=True, text=True)
    ok = r.returncode == 0 and (out / "Validation_Report_Unused_Line_Calibration.csv").exists()
    summary = json.loads(r.stdout) if ok else {}
    record(f"{label}: calibration report produced (informational, never fails)", ok,
           (f"screened {summary.get('screened_accounts')} of {summary.get('open_card_accounts')}; "
            f"within {summary.get('within')}, outside {summary.get('outside')}, "
            f"not assessed {summary.get('not assessed')}" if ok else r.stderr[-300:])
           + f" ({time.time() - t0:.0f}s)")
    return summary


# Runs the additions step alone in a fresh process and reports its own peak
# memory (Windows peak working set, else ru_maxrss).
_SCALE_STEP = r"""
import json, sys, time
sys.path.insert(0, sys.argv[1])
from generator import unused_line_additions as ULA
t0 = time.time()
rows = ULA.add_unused_line_tables(sys.argv[2], None, sys.argv[3])
secs = time.time() - t0
try:
    import psutil
    mi = psutil.Process().memory_info()
    peak = getattr(mi, "peak_wset", None) or mi.rss
except ImportError:
    import resource
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
print(json.dumps({"rows": rows, "seconds": round(secs, 1), "peak_gb": round(peak / 1e9, 3)}))
"""


def scale(d: Path, out: Path) -> None:
    print(f"\n6. Scale - {d.name} (read only; new tables written to a scratch directory)", flush=True)
    m = json.loads((d / "build_manifest.json").read_text())
    r = subprocess.run([sys.executable, "-W", "ignore", "-c", _SCALE_STEP, str(ROOT), str(d), str(out)],
                       cwd=ROOT, capture_output=True, text=True)
    if r.returncode:
        record(f"scale {d.name}: additions step completes", False, r.stderr[-300:])
        return
    s = json.loads(r.stdout.strip().splitlines()[-1])
    record(f"scale {d.name}: additions step completes", True,
           f"{m['customers']:,} customers; {s['rows']}; {s['seconds']}s; peak {s['peak_gb']} GB")
    integrity(d, f"scale {d.name}", new_dir=out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", default=None, help="where to generate (default: a temp dir, removed after)")
    ap.add_argument("--scale-dir", default=None, help="a large existing portfolio (only read)")
    a = ap.parse_args()
    work = Path(a.workdir) if a.workdir else Path(tempfile.mkdtemp(prefix="unused_line_audit_"))
    if work.exists() and a.workdir:
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)
    try:
        byte_identity(work)
        engine_regression(work)
        for p in PROFILES:
            integrity(work / p, p)
        determinism(work)
        calibration(work / "demo", "demo 5k", work / "_calibration_demo")
        if a.scale_dir:
            scale(Path(a.scale_dir), work / "_scale")
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
