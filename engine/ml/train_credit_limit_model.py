"""Offline training for the ML credit-limit model. Never run from the live
Streamlit app - retraining is a deliberate, manual, rerun-this-script
operation, exactly the sibling credit-limit-recommendation-system's own
train_models.py / score_monthly.py split.

Trains on FIVE scenarios generated fresh from this repo's own generator
(demo, transactor_heavy, subprime_heavy, premium_heavy, negative_control),
not just the bundled demo portfolio - one archive is too thin for a real
chronological split plus an unseen-account holdout, and a model fit on one
distribution would be scored, uncorrected, against every other scenario and
against portfolios from 500 to 500,000 customers.

Anti-leakage discipline (mirrors the sibling repo's own, see its
SYSTEM_BREAKDOWN.md Parts 5-7):
  - A hashed-account holdout bucket (sha256(Dataset ID + "::" + account) % 10
    == 0) is carved out BEFORE the temporal split and evaluated separately -
    the "does this generalize to an account never seen during training"
    check.
  - Of the remaining accounts, a temporal split by Cycle Index (60/20/20)
    keeps validation and test strictly LATER than anything used for
    training - no row from cycle 30 is ever used to help predict cycle 20.
  - A governance gate: a candidate model is only deployed if it beats a
    deliberately simple, already-measured baseline by >=5% on validation
    (PR-AUC for risk, MAE for the two regressions). Otherwise the baseline
    ships and the candidate is recorded as rejected, visible in the
    evidence file - never silently swapped in because it's "more
    sophisticated." This is the same discipline the six existing levers
    apply to themselves (never fabricate value that isn't earned).

Run with:
    python -m engine.ml.train_credit_limit_model
"""
from __future__ import annotations
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, mean_absolute_error

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.core.contract import load_portfolio  # noqa: E402
from engine.ml import features as F  # noqa: E402
from generator.run import build as generate_portfolio, PROFILES  # noqa: E402

ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
SCRATCH = ROOT / "engine" / "ml" / "_train_scratch"
SCENARIOS = ["demo", "transactor_heavy", "subprime_heavy", "premium_heavy", "negative_control"]
N_CYCLES = 36
SEED = 20261009
IMPROVEMENT_GATE = 0.05
TRAIN_FRAC, VAL_FRAC = 0.60, 0.20  # remaining 0.20 is test


def _hash_bucket(account_id: str, n: int = 10) -> int:
    return int(hashlib.sha256(account_id.encode()).hexdigest(), 16) % n


def _file_hashes(portfolio_dir: Path) -> dict:
    hashes = {}
    for f in sorted(portfolio_dir.glob("Table*.csv")):
        hashes[f.name] = {"sha256": hashlib.sha256(f.read_bytes()).hexdigest(),
                          "rows": sum(1 for _ in open(f, encoding="utf-8")) - 1}
    return hashes


def _generate_scenarios() -> dict:
    manifest = {}
    SCRATCH.mkdir(parents=True, exist_ok=True)
    panels = []
    for name in SCENARIOS:
        out_dir = SCRATCH / name
        print(f"generating {name}...")
        generate_portfolio(name, out_dir, SEED, N_CYCLES, None)
        manifest[name] = {"n_customers": PROFILES[name]["n"], "n_cycles": N_CYCLES,
                          "files": _file_hashes(out_dir)}
        portfolio = load_portfolio(out_dir)
        panel = F.build_training_panel(portfolio)
        panel["Dataset ID"] = name
        panel["_holdout_bucket"] = (panel["Dataset ID"] + "::" + panel[F.ACCOUNT_ID]).map(_hash_bucket)
        panels.append(panel)
        print(f"  {name}: {len(panel):,} rows, "
             f"{int(panel['model_training_eligible'].sum()):,} training-eligible")
    full = pd.concat(panels, ignore_index=True)
    return full, manifest


def _temporal_split(panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Returns (train, val, test, unseen_account_holdout). The holdout
    bucket is carved out first and evaluated separately; the remaining
    accounts split by Cycle Index, strictly chronological."""
    holdout = panel[panel["_holdout_bucket"] == 0]
    rest = panel[panel["_holdout_bucket"] != 0]

    max_idx = int(rest[F.CYCLE_IDX].max())
    train_cut = int(max_idx * TRAIN_FRAC)
    val_cut = int(max_idx * (TRAIN_FRAC + VAL_FRAC))
    train = rest[rest[F.CYCLE_IDX] <= train_cut]
    val = rest[(rest[F.CYCLE_IDX] > train_cut) & (rest[F.CYCLE_IDX] <= val_cut)]
    test = rest[rest[F.CYCLE_IDX] > val_cut]
    return train, val, test, holdout


def _prep_X(df: pd.DataFrame) -> pd.DataFrame:
    X = df[F.MODEL_FEATURES].copy()
    for c in F.CATEGORICAL_FEATURES:
        X[c] = X[c].astype("category")
    return X


def _train_risk(train, val, test, holdout) -> dict:
    tr = train[train["model_training_eligible"]]
    va = val[val["model_training_eligible"]]
    te = test[test["model_training_eligible"]]
    ho = holdout[holdout["model_training_eligible"]]

    X_tr, y_tr = _prep_X(tr), tr[F.TARGET_RISK].astype(int)
    X_va, y_va = _prep_X(va), va[F.TARGET_RISK].astype(int)

    model = HistGradientBoostingClassifier(
        categorical_features="from_dtype", random_state=SEED, max_iter=200)
    model.fit(X_tr, y_tr)
    model_pr_auc = average_precision_score(y_va, model.predict_proba(X_va)[:, 1])

    baseline_features = ["on_time_payment_rate_6m", "utilization_6m_avg",
                         "historical_delinquent_cycles"]
    baseline_medians = tr[baseline_features].median()
    Xb_tr = tr[baseline_features].fillna(baseline_medians)
    Xb_va = va[baseline_features].fillna(baseline_medians)
    baseline = LogisticRegression(max_iter=500)
    baseline.fit(Xb_tr, y_tr)
    baseline_pr_auc = average_precision_score(y_va, baseline.predict_proba(Xb_va)[:, 1])

    deploy_model = model_pr_auc >= baseline_pr_auc * (1 + IMPROVEMENT_GATE)
    chosen = model if deploy_model else baseline
    chosen_features = F.MODEL_FEATURES if deploy_model else baseline_features

    raw_prob_va = (chosen.predict_proba(_prep_X(va) if deploy_model else Xb_va)[:, 1])
    logit_va = np.clip(raw_prob_va, 1e-6, 1 - 1e-6)
    logit_va = np.log(logit_va / (1 - logit_va)).reshape(-1, 1)
    calibrator = LogisticRegression(C=1e3, max_iter=500)
    calibrator.fit(logit_va, y_va)

    def _score(df_split, label):
        if not len(df_split):
            return None
        Xs = _prep_X(df_split) if deploy_model else df_split[baseline_features].fillna(
            baseline_medians)
        prob = chosen.predict_proba(Xs)[:, 1]
        y_true = df_split[F.TARGET_RISK].astype(int)
        return float(average_precision_score(y_true, prob)) if y_true.nunique() > 1 else None

    evidence = {
        "deployed": "model" if deploy_model else "baseline",
        "model_val_pr_auc": float(model_pr_auc),
        "baseline_val_pr_auc": float(baseline_pr_auc),
        "improvement_required": IMPROVEMENT_GATE,
        "test_pr_auc": _score(te, "test"),
        "unseen_account_holdout_pr_auc": _score(ho, "holdout"),
        "base_rate_train": float(y_tr.mean()),
    }
    bundle = {"estimator": chosen, "calibrator": calibrator,
             "features": chosen_features, "deployed": evidence["deployed"],
             "baseline_medians": None if deploy_model else baseline_medians.to_dict()}
    return bundle, evidence


def _train_regression(train, val, test, holdout, target_col: str,
                      baseline_col: str, name: str) -> tuple[dict, dict]:
    tr = train[train["model_training_eligible"]]
    va = val[val["model_training_eligible"]]
    te = test[test["model_training_eligible"]]
    ho = holdout[holdout["model_training_eligible"]]

    X_tr, y_tr = _prep_X(tr), tr[target_col]
    X_va, y_va = _prep_X(va), va[target_col]

    model = HistGradientBoostingRegressor(
        categorical_features="from_dtype", random_state=SEED, max_iter=200)
    model.fit(X_tr, y_tr)
    model_mae = mean_absolute_error(y_va, model.predict(X_va))

    baseline_pred_va = va[baseline_col].fillna(0.0)
    baseline_mae = mean_absolute_error(y_va, baseline_pred_va)

    deploy_model = model_mae <= baseline_mae * (1 - IMPROVEMENT_GATE)

    def _score(df_split):
        if not len(df_split):
            return None
        pred = model.predict(_prep_X(df_split)) if deploy_model else df_split[baseline_col].fillna(0.0)
        return float(mean_absolute_error(df_split[target_col], pred))

    evidence = {
        "deployed": "model" if deploy_model else "baseline",
        "model_val_mae": float(model_mae),
        "baseline_val_mae": float(baseline_mae),
        "improvement_required": IMPROVEMENT_GATE,
        "test_mae": _score(te),
        "unseen_account_holdout_mae": _score(ho),
    }
    bundle = {"estimator": model if deploy_model else None,
             "baseline_column": baseline_col, "deployed": evidence["deployed"],
             "features": F.MODEL_FEATURES}
    return bundle, evidence


def main():
    panel, data_manifest = _generate_scenarios()
    train, val, test, holdout = _temporal_split(panel)
    print(f"train={len(train):,} val={len(val):,} test={len(test):,} "
         f"unseen_account_holdout={len(holdout):,}")

    risk_bundle, risk_evidence = _train_risk(train, val, test, holdout)
    print(f"risk: deployed={risk_evidence['deployed']} "
         f"model_pr_auc={risk_evidence['model_val_pr_auc']:.3f} "
         f"baseline_pr_auc={risk_evidence['baseline_val_pr_auc']:.3f}")

    spend_bundle, spend_evidence = _train_regression(
        train, val, test, holdout, F.TARGET_SPEND, "spend_3m_sum", "spend")
    print(f"spend: deployed={spend_evidence['deployed']} "
         f"model_mae={spend_evidence['model_val_mae']:.2f} "
         f"baseline_mae={spend_evidence['baseline_val_mae']:.2f}")

    peak_bundle, peak_evidence = _train_regression(
        train, val, test, holdout, F.TARGET_PEAK_BALANCE, "balance_6m_max", "peak_balance")
    print(f"peak_balance: deployed={peak_evidence['deployed']} "
         f"model_mae={peak_evidence['model_val_mae']:.2f} "
         f"baseline_mae={peak_evidence['baseline_val_mae']:.2f}")

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    bundle = {
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
        "sklearn_version": sklearn.__version__,
        "joblib_version": joblib.__version__,
        "seed": SEED,
        "scenarios": SCENARIOS,
        "numeric_features": F.NUMERIC_FEATURES,
        "categorical_features": F.CATEGORICAL_FEATURES,
        "risk": risk_bundle,
        "spend": spend_bundle,
        "peak_balance": peak_bundle,
    }
    bundle_path = ARTIFACT_DIR / "credit_limit_model_bundle.joblib"
    joblib.dump(bundle, bundle_path)
    bundle_sha256 = hashlib.sha256(bundle_path.read_bytes()).hexdigest()

    evidence = {
        "trained_at_utc": bundle["trained_at_utc"],
        "sklearn_version": bundle["sklearn_version"],
        "joblib_version": bundle["joblib_version"],
        "bundle_sha256": bundle_sha256,
        "scenarios": SCENARIOS,
        "data_manifest": data_manifest,
        "row_counts": {"total_panel_rows": int(len(panel)),
                      "train": int(len(train)), "val": int(len(val)),
                      "test": int(len(test)), "unseen_account_holdout": int(len(holdout))},
        "targets": {"risk_30dpd_3m": risk_evidence, "spend_3m": spend_evidence,
                   "peak_balance_3m": peak_evidence},
        "excluded_features": ["Age (ECOA/Reg B prohibited basis)",
                              "Charged Purchase APR (possible L3 repricing-mechanism proxy)"],
    }
    (ARTIFACT_DIR / "model_evidence.json").write_text(json.dumps(evidence, indent=2, default=str))
    print(f"\nWrote {bundle_path} (sha256 {bundle_sha256[:16]}...) and model_evidence.json")


if __name__ == "__main__":
    main()
