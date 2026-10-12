"""Live scoring: load the pre-trained, committed bundle and score whatever
portfolio is currently loaded in the app. Never retrains - see
train_credit_limit_model.py, which is the only place this bundle is ever
produced, as a deliberate, manual, offline step."""
from __future__ import annotations
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from . import features as F

ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
BUNDLE_PATH = ARTIFACT_DIR / "credit_limit_model_bundle.joblib"


class ModelBundleUnavailable(Exception):
    """No trained bundle found - run `python -m engine.ml.train_credit_limit_model`."""


def load_bundle(path: Path = BUNDLE_PATH) -> dict:
    if not path.exists():
        raise ModelBundleUnavailable(
            f"{path} does not exist. Train it first: "
            f"python -m engine.ml.train_credit_limit_model")
    return joblib.load(path)


def _prep_X(df: pd.DataFrame, feature_cols: list[str]) -> pd.DataFrame:
    X = df[feature_cols].copy()
    for c in F.CATEGORICAL_FEATURES:
        if c in X.columns:
            X[c] = X[c].astype("category")
    return X


def score(portfolio, bundle: dict | None = None) -> pd.DataFrame:
    """One row per account (latest eligible cycle), carrying every feature
    the decision engine needs plus the three predictions:
    predicted_risk_probability, predicted_3m_spend, predicted_3m_peak_balance.
    Predictions are null for accounts the model isn't ready to score
    (normal_score_ready == False) - the decision engine's own waterfall
    handles those by rule (INSUFFICIENT_HISTORY / NOT_ELIGIBLE), never by a
    fabricated score."""
    if bundle is None:
        bundle = load_bundle()
    sf = F.build_scoring_frame(portfolio)

    risk = bundle["risk"]
    if risk["deployed"] == "model":
        X_risk = _prep_X(sf, risk["features"])
    else:
        X_risk = sf[risk["features"]].fillna(pd.Series(risk["baseline_medians"]))
    raw_prob = risk["estimator"].predict_proba(X_risk)[:, 1]
    logit = np.clip(raw_prob, 1e-6, 1 - 1e-6)
    logit = np.log(logit / (1 - logit)).reshape(-1, 1)
    sf["predicted_risk_probability"] = risk["calibrator"].predict_proba(logit)[:, 1]
    sf["risk_model_deployed"] = risk["deployed"]

    for key, out_col, baseline_col_key in [
        ("spend", "predicted_3m_spend", "baseline_column"),
        ("peak_balance", "predicted_3m_peak_balance", "baseline_column"),
    ]:
        b = bundle[key]
        if b["deployed"] == "model":
            # Both targets are inherently non-negative dollar amounts
            # (spend, balance); the regressor has no such constraint and
            # can predict a small negative value for a near-zero account -
            # floor it rather than surface a nonsensical negative spend.
            sf[out_col] = np.clip(b["estimator"].predict(_prep_X(sf, b["features"])), 0, None)
        else:
            sf[out_col] = sf[b[baseline_col_key]].fillna(0.0).clip(lower=0)
        sf[f"{key}_model_deployed"] = b["deployed"]

    not_ready = ~sf["normal_score_ready"]
    sf.loc[not_ready, ["predicted_risk_probability", "predicted_3m_spend",
                       "predicted_3m_peak_balance"]] = np.nan
    return sf
