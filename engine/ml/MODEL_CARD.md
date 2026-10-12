# Model Card: ML Credit Limit Recommendation

This replicates the capability of the sibling `credit-limit-recommendation-system` repo
(CLRS) inside the Customer Economics System (CES), using CES's own data and conventions. It
is **CES's first real machine-learning component** - every other diagnostic in this repo
(liquidity cost, leverage capital, CAC payback, the six levers) is a deterministic function
over already-realized data. Read this card before trusting, extending, or deploying anything
this produces.

## What it does

Once per uploaded portfolio, for every credit card account: forecasts three things over the
next 3 billing cycles (probability of 30+ days past due, total spend, peak balance), then a
hand-written rules engine (`engine/ml/decisions.py`) turns those forecasts into one of seven
actions - `INCREASE`, `MAINTAIN`, `DECREASE_UNUSED_EXPOSURE`, `FREEZE_NO_INCREASE`,
`MANUAL_REVIEW`, `NOT_ELIGIBLE`, `INSUFFICIENT_HISTORY` - and a recommended dollar limit. **The
model never sets a limit.** It only supplies the three forecasts; every dollar figure traces
to an arithmetic rule a human wrote in `engine/config/ml_credit_limit_policy.json` and can
change without retraining anything.

## Training data

Five scenarios generated fresh by this repo's own generator (`generator/run.py`), not just the
bundled demo portfolio: `demo`, `transactor_heavy`, `subprime_heavy`, `premium_heavy`,
`negative_control`. One archive was judged too thin for a real chronological split plus an
unseen-account holdout, and a model fit on one distribution would be scored, uncorrected,
against every other scenario and against portfolios from 500 to 500,000 customers (this
repo's own generator size range). Every source file's SHA-256 and row count is recorded in
`engine/ml/artifacts/model_evidence.json`'s `data_manifest`, alongside the trained bundle's own
SHA-256 - anyone can verify exactly what produced a given run's numbers.

Retraining is a manual, offline operation:
```
python -m engine.ml.train_credit_limit_model
```
Never run from the live Streamlit app. The committed bundle (`credit_limit_model_bundle.joblib`)
is only ever **scored**, never retrained, inside the app.

## Targets

- **`target_risk_30dpd_3m`** (classification): will the account hit 30+ days past due at least
  once in the next 3 cycles? Not "will they default" or "charge off" - specifically 30+ DPD.
- **`target_spend_3m`** (regression): total purchase spend over the next 3 cycles.
- **`target_peak_balance_3m`** (regression): the highest balance the account will carry over
  the next 3 cycles - used for sizing a defensible reduction.

A row is only labeled if all 3 forward cycles exist (`target_complete`); an account near the
end of its history (closed, charged off, or simply out of future data) is dropped from
training rather than labeled on a truncated window. Already-delinquent rows
(`Days Past Due >= 30` as of the as-of cycle) are excluded from fitting - the model learns
**who becomes delinquent from a clean state**, not who currently is delinquent, a genuinely
different and more useful question.

## Anti-leakage discipline

- Window arithmetic uses `Cycle Index` (integer), never `Cycle Month` string-sorting.
- A hashed-account holdout bucket (`sha256(Dataset ID::account) % 10 == 0`) is carved out
  before the temporal split and evaluated separately - the "does this generalize to an account
  never seen during training" check.
- Of the remaining accounts, a strict chronological 60/20/20 split by `Cycle Index` - no row
  from a later cycle is ever used to help predict an earlier one.
- A governance gate: each target's candidate model is only deployed if it beats a simple,
  already-measured baseline by >=5% on validation (PR-AUC for risk, MAE for the two
  regressions). See **Results** below for which targets actually cleared this gate on CES's
  own data - it is not assumed to match CLRS's own result for the same target.

## Features excluded by design, not oversight

- **`Age`** - CLRS's own `MODEL_CARD.md` documents removing `customer_age` as a prohibited
  ECOA/Reg B basis after measuring the cost of removal. CES's `Table1_Customer.csv` has a
  required `Age` column; it is never passed to this model, from the first version shipped.
- **`Charged Purchase APR`** - `engine/run.py`'s own `MECHANISM_VARIED_IN_CONTROL["L3"] = True`
  confirms repricing-tracks-risk is an active generator mechanism. Contemporaneous charged APR
  may be a proxy for the generator's own latent risk state rather than an independent
  behavioral signal. Excluded pending a future ablation; not assumed safe either way.
  `Contractual Purchase APR` (set at origination, never revised) is kept.
- **Masked Customer/Account Number, Dataset ID** - travel through for joining and audit only.
- **Instalment-plan features and an economic-stress-index feature** (both present in CLRS,
  SYSTEM_BREAKDOWN.md Parts 4.7-4.8) - CES's instalment tables are optional, not contract-
  required, and CES's generator has no macro/economic-stress series at all. Fabricating either
  would violate this repo's own "never invent a number you cannot measure" rule.

## Results (this training run - see `model_evidence.json` for the authoritative numbers)

| Target | Deployed | Model (val) | Baseline (val) | Gate |
|---|---|---|---|---|
| Risk (PR-AUC, higher better) | model | 0.117 | 0.094 | model beat baseline by >=5% |
| Spend (MAE, lower better) | model | $778 | $872 | model beat baseline by >=5% |
| Peak balance (MAE, lower better) | model | $263 | $339 | model beat baseline by >=5% |

**All three targets shipped the model on CES's data.** This is a different outcome from CLRS,
which shipped the simple baseline for peak balance on its own data - stated here explicitly as
a CES-specific finding, not an assumption carried over from the sibling repo. Re-run the
training script and re-read `model_evidence.json` after any data or feature change; this table
is a snapshot, not a permanent fact about the model.

The risk target's absolute PR-AUC (0.117) looks unimpressive in isolation; read against the
3.66% base rate in the training data it represents roughly a 3.2x lift over random, and a 24%
relative improvement over the univariate baseline - consistent with how genuinely difficult
delinquency prediction is, even on measured, non-adversarial synthetic data.

## Deliberate improvements over a blind port

- **Expected loss uses CES's own measured per-customer `lgd`** (from `customer_view.py`,
  already computed for the engine's own capital/credit-cost figures) instead of a fabricated
  flat constant, falling back to a policy-configured value only when `lgd` is unavailable.
- **A fourth, independently documented credit-conversion-factor value.** The expected-loss
  money figure's `undrawn_exposure_conversion_factor` (20%) is CLRS's own EAD proxy assumption,
  ported as-is - do not confuse it with the 0% risk-based CCF (12 CFR 217.33), the 5%/10% LCR
  outflow rate (`engine/config/liquidity_policy.json`), or the 10% SLR CCF
  (`engine/config/leverage_capital_policy.*.json`). Four different regimes, four different
  numbers, on purpose.

## Scoring eligibility: only accounts still reporting as of "now"

`engine/ml/features.py:build_scoring_frame()` only scores accounts whose latest row falls on
the portfolio's own overall latest cycle. CES's generator simply stops emitting rows for an
account once it closes - by charge-off OR by ordinary voluntary closure/attrition (see
`generator/synth/cycles.py`) - and `Charged Off Indicator` only flags the first of those two.
Without this check, a churned account's last historical row would be scored as if the account
were still open today, on data that can be many months stale. An account not currently
reporting has nothing to recommend a limit change on, so it is excluded from the scoring frame
entirely rather than surfaced with a misleading action. This does not affect training: the
training panel deliberately keeps every historical row, including an account's pre-closure
snapshots, since those are legitimate "as of" points to learn from.

## Suppression, fairness, and the negative-control gap

- **`decisions.py` itself has no concept of suppression.** `decide()` will happily assign an
  actionable recommendation to a hardship/accommodation/SCRA customer, exactly like every other
  pre-suppression computation in this engine (liquidity cost, leverage capital, the six levers
  all work the same way). In the live app this is harmless: `engine/run.py` merges the `ml_*`
  columns into `cv` *before* `suppression.run(cv)` executes, so by the time
  `result["customer_view"]` reaches the new page, suppressed customers are already gone - the
  same free protection every other page in this repo gets, with zero suppression logic written
  on the page itself. `decisions.exclude_suppressed()` exists for the one case that bypasses
  this ordering - calling `decide()` directly, outside `build_pipeline()` (exactly what
  `audit/audit_ml_credit_limit.py` does to test this property in isolation) - and is not needed,
  and not called, inside the page.
- **A dedicated four-fifths fairness check runs on the ML "treatment"** (the customers who get
  `INCREASE`/`DECREASE_UNUSED_EXPOSURE`/`FREEZE_NO_INCREASE`, not `MAINTAIN`/`MANUAL_REVIEW`),
  via the existing `engine/governance/fairness.py:run()`, surfaced separately from the six
  levers' own fairness result (`result["ml_fairness"]`) so the Governance page's existing
  six-lever shape doesn't need to change.
- **No negative-control mechanism exists for this model.** `engine/run.py`'s
  `MECHANISM_VARIED_IN_CONTROL` dict declares which lever mechanisms the generator's negative
  control actually varies; nothing in the generator varies an ML model's behavior specifically.
  This is the first component in this repo structurally exempt from that gate - stated plainly
  here rather than silently skipped.

## What this explicitly does not claim

All of this was measured on simulated data generated by this same repo's own generator. It is
not an affordability assessment, not a creditworthiness decision, not automatic approval, not a
profit forecast, and not evidence of accuracy on real customers. Before any real use it would
need retraining on real data, fairness testing against a validated protected-class proxy (see
`fairness.py`'s own documented BISG limitation), adverse-action review, policy sign-off, drift
monitoring, and human governance - the same list the sibling CLRS repo states about itself.

## Out of scope for this version (stated, not silently dropped)

- A versioned model registry (CLRS's `artifacts/registry/v.../`) - this version ships one
  committed bundle + one evidence/manifest file.
- A `score_monthly.py`-style incremental monthly loop - this version scores whatever portfolio
  is uploaded fresh, same as every other CES page.
- The OpenAI narrative feature from CLRS - not relevant to CES's existing design.
- A generic ablation harness (CLRS's `run_ablation.py`) - the feature set is fixed and
  documented above; CES has no equivalent tool anywhere else either.
- Distribution-shift / drift detection between the training scenarios and an uploaded
  portfolio that looks substantially different (e.g. a much larger or differently-skewed one).
- Verified performance at the full 500,000-customer ceiling - scoring cost scales with account
  count (not account-months, since only the latest cycle survives per account), measured fast
  at demo scale (~5,000 accounts, a few seconds); not verified at the upper end of the
  generator's own size range.
