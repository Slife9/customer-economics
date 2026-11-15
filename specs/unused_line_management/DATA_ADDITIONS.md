# Unused-line data additions (Stage 2)

Code: `generator/unused_line_additions.py`, called last in `generator/run.py build()`, after
`build_manifest.json` is written. Also runnable on an existing portfolio:

    python -m generator.unused_line_additions --data <portfolio dir>

## Rules kept

- **Additive only.** The step reads the published tables and writes two new files. No existing file
  is rewritten, and `build_manifest.json` does not mention the new tables, so it stays identical.
- **Separate random stream.** `SeedSequence(seed + 104729)`, spawned into one child per table
  (Table29, Table30). The generator's own `rng` is never touched. Every draw has a fixed size, so
  the stream's use does not depend on the data.
- **Numbering.** Table29 onward. Tables 25–28 are reserved for the reward additions
  (`feature/reward-data-additions`), so the branches do not clash when merged.
- **Masked identifiers only** (CUS / ACC / CRD).
- Every parameter is **estimated** (illustrative, not sourced); all are constants at the top of
  the module.

## Table29_Score_History

Grain: one row per card account and cycle, exactly the rows of `Table8_Risk_Parameters`.

| Column | Meaning | Source |
|---|---|---|
| Masked Customer Number, Masked Account Number, Cycle Month | Keys | Table8 |
| Behaviour Score | Scorecard scaling of the account's PD: 3-cycle mean of the PD log-odds, 660 at odds 32:1, 20 points to double the odds, 300–850 | Derived from Table8 `PD 12 Month` (no randomness) |
| Bureau Score | Table1 `Credit Score` at the first observed cycle; then + 0.6 × change in behaviour score − delinquency penalty + AR(1) noise (0.85, sd 6), 300–850 | Table1, Table4 `Days Past Due`, new stream |
| Bureau Score Change 6 Months | Bureau score minus its value 6 cycles earlier; blank in the first 6 cycles | Derived |
| Months Of Score History | Cycles observed so far, starting at 1 | Derived |

Delinquency penalty: 2 points per day past due from 30 days, capped at 110, kept at 97% a month
afterwards (the worse of the new and the decayed penalty).

What it is for: the workbook's Credit-Deteriorating rule (score down ≥ 40 points in 6 months).
On the 5k demo at the last cycle, 3.8% of open accounts show such a drop: 55% of accounts with 30+
days past due in the last 7 cycles, 0.3% of the rest.

Limitation: the generator issues one card per customer, so the bureau score is keyed by account.
With several cards per customer it would differ by card, which a real bureau score does not.

## Table30_Card_Activation

Grain: one row per plastic in `Table3_Card`, same order.

| Column | Meaning |
|---|---|
| Masked Card Number, Masked Account Number, Card Sequence Number, Issue Cycle Index | From Table3 |
| Months Live In Window | Cycles in the window between issue and deactivation (or account closure: last Table4 cycle + 1) |
| First Use Cycle Index | First cycle in the card's live period with any Table5 transaction on the account; blank if none |
| Activation Status | `activated`, `not_activated` or `not_observed` (card retired before the window) |
| Activation Cycle Index | Blank unless activated; negative before the window |
| Activation Cycle Month | Blank unless activated inside the window |
| Activation Basis | `at_first_use`, `before_first_use`, `no_use_in_window`, `not_activated`, `not_observed` |

Rules:
- A card used during its life is activated, at issue + a lag of 0/1/2 months (80/15/5%), never
  after its first use.
- A card never used during its life is activated with probability 35% if the account had other
  activity in the window, 55% if the account had none (its earlier card was usually in use before
  the window), and only if the activation falls before the card's life ends.
- Table3 writes −1 both for "never deactivated" and for a deactivation in the cycle before the
  window; `Card Status` tells them apart.

What it is for: dormant confirmation (card never activated) and the non-reissue lever.

## Stress profile `unused_line_stress` (Stage 3, answer 9)

**Synthetic stress data**, never the illustrative bank's headline without that label.

    python -m generator.run --profile unused_line_stress --out <dir>

- New profile only (10,000 customers; the demo's bank dials and defects; fewer balance-transfer
  promotions). Every existing profile stays byte-identical: its hooks run only when the profile
  carries `unused_line_archetypes`, so no other profile draws an extra random number.
- Code: `generator/synth/unused_line_stress.py`, plus profile-gated calls in `generator/run.py`
  `build()`. No existing generator module is edited (fewer merge clashes).
- Mechanism: 77% of customers are acquired as one of the workbook's **archetypes** (dormant,
  sock-drawer, transactor, deteriorating, relationship), the rest are standard customers. The
  archetype sets the population: latent traits (discipline, appetite, reliability, affluence,
  spend level, spending mix), segment, credit line, annual fee, product for relationship
  customers, account age, and when the card is used (dormant from some cycle, sock-drawer about
  one month in five, transactors within a steady monthly budget). Balances, payments,
  delinquency, PD, costs and profit still come from the generator's own logic.
- Every parameter is tagged `estimated - source: Unused Line RWA Scenario Model`, tuned on the
  10k book against the calibration report. The archetype is written to
  `_ground_truth/Unused_Line_Archetype.csv` (evaluation only; never read by the engine).

## Calibration report (informational)

`audit/unused_line_calibration_report.py` applies a simplified, independent reading of the workbook
screen and segment rules to a portfolio and compares segment shares, line, balance, utilisation,
unused line, revolving balance, spend and PD with the workbook's *Assumptions* sheet (±25% band;
a reference of exactly 0 allows $10 or 0.001). It never fails the build. The module's own segment
engine (Stage 4) will be cross-checked against it.

Since Stage 3 it uses the module's profit (engine/unused_lines): the rules run on every account,
LEQ comes from the rule's segment, then the §2 costs, then the screen on the configured profit
basis (default card profit less drawdown loss, the workbook's fully loaded basis). Two loss rows
compare like with like: card profit against the workbook's profit without its undrawn-line loss
(−$36.95 per account), and card profit less drawdown loss against its fully loaded profit
(−$97.25).

## Audit

`python audit/audit_unused_line_data_additions.py [--scale-dir <large portfolio>]`. It covers
byte-identity against `baseline_hashes.json` (generated on `main` `b660bb8`), the engine regression
against `engine_baseline_run_summary.json`, integrity, determinism, the calibration report, and
(optional) the step's time and peak memory on a large portfolio, read only.
