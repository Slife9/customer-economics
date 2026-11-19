# Decisions log

Decisions received after the Stage 1 audit, newest first. Open decisions with the boss
(B4–B7) are in `OPEN_DECISIONS.md` and stay behind config flags.

## 19 Nov 2026: revision E - align with the project report and slides

The project report and the stakeholder slides are the reference for structure, wording, definitions
and figures. Decided after the Stage 0 audit (`REVISION_E_STAGE0_AUDIT.md`), on the recommendations:

| Decision | Where it lives |
|---|---|
| **B2 stays the workbook LEQ.** Table9's Behavioral CCF means the share of the unused line drawn before default, but on this data it is a two-value generator parameter, not measured behaviour | `drawdown_risk.leq_source = workbook_segment` (unchanged) |
| **The 90-day warning goes to every unused card selected for a Strategy 3 action** (right-size, close, don't reissue), after the Invite; Invite responders are not warned. Response shares, the reset rule and the letter cost are assumptions to be tested in the pilot; never a fee | Config `warning`; `strategies._warned` |
| **App content not in the report** moves to the analyst view (dataset switch, scenario switch, year-1 timing, the 1×–2× curve, calibration tile, review / download tools, per-group value of approved actions) or is removed ("increases" fairness note); "Valuable relationship customers" becomes "Relationship customers" | `unused_lines_app/` |
| 1b balance basis: statement-date 30% test; midpoint balance for costs; actions valued on today's unused line; old settings kept as options | Config `balance_basis` |
| 1c pay-in-full right-sizing excluded from the recommendations *and* the approved value, by policy; valued for analysts | `levers.system_mode.transactor_rightsizing_in_approved_value = false` |
| Four strategies, each built from the levers; the campaign split between Strategy 2 and Strategy 3's Invite | Config `strategies`; `engine/unused_lines/strategies.py` |

## 17 Nov 2026: B2 default - the workbook LEQ

The workbook segment LEQ is the default (`drawdown_risk.leq_source = "workbook_segment"`) until the
bank has a measured LEQ: the synthetic Behavioral CCF is a two-value generator parameter
(`ISSUES_FOUND.md` #16). The account-level setting stays available on What-if. Headline figures
return to their values before revision B (stress book Base +$175,389). Suite after the change: 122/122
(`REVISION_D_AUDIT.txt`).

## 17 Nov 2026: calculation corrections (revision B)

| # | Decision | Where it lives |
|---|---|---|
| B1 | A missing PD takes the segment's average PD (accounts with a PD), then the portfolio average; flagged `pd_imputed` | `drawdown_risk.missing_pd`, `exposure.pd_used` |
| B2 | LEQ per account = Table9 Behavioral CCF (same definition as LEQ; see `ISSUES_FOUND.md` #16), workbook segment LEQ as fallback; switch `measured_account` / `workbook_segment` (default since the decision above) | `drawdown_risk.leq_source`, `exposure.leq_columns` |
| B3 | Specific reason codes with their notice rules: `IDLE_LINE_RIGHTSIZING`, `CREDIT_DETERIORATION`, `INACTIVITY`, `INACTIVITY_NON_REISSUE`, `ENGAGEMENT_CAMPAIGN`, `SUPPRESS_AUTO_INCREASE`; `OTHER` below 1% of actions | `treatment.reason_codes`, `treatment.reason_by_lever` |
| B4 | The module's card profit is labelled "card profit under the assumed capital rules", with a reconciliation from the main engine's card profit | `exposure.reconciliation` |
| B5 | Fixed cost basis: `engine_allocated` (default) or `workbook_segment` | `costs.fixed_cost_basis`, `exposure.fixed_costs` |
| B6 | Executives see one figure: annual value = change in card profit + reduction in expected drawdown loss; card profit alone and relationship-adjusted values in the analyst view; the robustness statement states its basis | `levers.robustness_statement`; app |
| B7 | Balances are measured after the month's payment (reporting-date balance). **Superseded by revision E (1b):** the midpoint balance for costs and the statement date for the 30% test, by default | Methodology; config `balance_basis` |

## 17 Nov 2026: B8 final - the ML model plays no role in this module

| Decision | Where it lives |
|---|---|
| **B8: ML model not used in this module.** The agreement flag, the ML columns (`ml_action`, `ml_primary_reason`, `ml_recommended_limit`), the ML rule text and the two ML fairness tests (adverse actions, increases) are removed from `engine/unused_lines/`, `unused_lines_app/`, the tests, the docs and the per-account sample files. `engine/ml/` is not modified; the module simply stops reading it | `treatment.py`, `build_sample.py`, `samples/unused_lines/*/engine_view.parquet`, audit check "B8" |
| Fairness covers the module's own actions only: decreases and closures, and increases if the module ever produces any. A metro with fewer than 30 selected accounts (config `treatment.fairness.min_selected_per_group`) shows "insufficient sample" instead of pass / fail | `treatment.fairness`, config `treatment.fairness` |

## 15 Nov 2026: answers 2–9 and the Stage 2 notes

| # | Decision | Where it lives |
|---|---|---|
| 2 | Word re-save discarded (`git stash drop`) | Done |
| 3 | **Carrying cost** = capital + liquidity; **drawdown loss** beside it; **total unused-line cost** = all three. Three separate columns in every table and the drill-down; drawdown loss never under "carrying cost" | `engine/unused_lines/exposure.py` |
| 4 | Profit view: start from `card_net`, **replace** the old capital charge with the new one, **subtract** the new liquidity cost; keep the **measured** credit cost; drawdown loss **beside** profit, not deducted; lever changes use annual PD × LGD × LEQ (Table8 `PD 12 Month`, never lifetime). A separate **workbook-reproduction mode** uses the workbook's modelled loss throughout | `exposure.account_costs`, `exposure.workbook_baseline` |
| 5 | Regulatory transactor test (45%): a $0 statement cycle passes; all 12 cycles at $0 → 75%; any plan, promotional or BT balance, or a cycle not paid in full → 75%; under 12 months → 75%. The workbook's ≥ 10/12 rule stays a separate, labelled segment rule | `config/unused_line_assumptions.json` `transactor_test`, `exposure.risk_weights` |
| 6 | Table29 / Table30 approved, additive, labelled synthetic; the score-drop and PD ≥ 4% rules are partly correlated by construction (both read Table8 PD), documented. Household and investments approximated (deposits + `Segment`), labelled | `DATA_ADDITIONS.md` |
| 7 | Unassigned LEQ = portfolio mean Behavioral CCF (measured); automatic-increase suppression valued from Table20; non-reissue from Table3 reissue cost; all "assumption-based; not in the reference workbook", shown separately from the workbook levers in every total | config `drawdown_risk`, `levers.extra_levers` |
| 8 | 100k bundle rebuilt locally, read-only, not committed, for §2.7 and the memory test | `STAGE3_REPORT.md` |
| 9 | Build the `unused_line_stress` profile (synthetic stress data), new profile only, every parameter tagged `estimated - source: Unused Line RWA Scenario Model`; run the module on it and on the 5k demo | `generator/synth/unused_line_stress.py` |

Stage 2 notes: the `negative_control` fix (`966988a`) is cherry-picked (`891bda2`) and
`negative_control` is in the byte-identity check, baselined from the fix branch's code; the expected
`generator/run.py` merge clashes are in `ISSUES_FOUND.md`; stale worktree records pruned.

Settings added in Stage 3 that the brief did not specify (to confirm):
- `bank_profile.bank_category` (default Categories I–III, as in §2.7): decides whether liquidity
  applies under the default `apply_to`.
- `screen.profit_basis` (default card profit less drawdown loss, the workbook's fully loaded basis):
  the screen only; the displayed profit follows answer 4.

## 15 Nov 2026: base branch (replaces the earlier answer to Question 1)

- `feature/unused-line-management` is created from `main` (`b660bb8`). Neither
  `feature/lever-valuation-rebuild` nor `feature/l1-rewards-system` is merged into it.
- Standalone app, like the rewards system: `engine/unused_lines/` and `unused_lines_app/`, with its
  own engine, pages, per-account data file and precomputed sample.
- The L1 Rewards system is a reference only. Shared UI pieces (state, style, guide components,
  page layout) are **copied** with a note of the source branch and commit, never merged, and kept
  self-contained so the two apps can evolve independently.
- New tables start at **Table29** (`Table29_Score_History`, `Table30_Card_Activation`).
  Tables 25–28 stay reserved for the reward additions so nothing clashes at merge time.
- Generator additions are additive only: existing tables on `main` byte-identical, separate random
  stream, baseline hash check.
- No longer applicable: the `STATUS.md` merge resolution; exposing a summary to the six-strategy
  overview (skipped for now; outputs are designed so they *can* be read later: low / base / high
  and value types).
- The rebuilt L2 page's use of the old carrying-cost logic is recorded in `ISSUES_FOUND.md` as a
  known issue on the other branch; no action.
- Still applies: L2, the ML model, NEP, CEV, suppression, routing and the fairness module are read
  and called only. The §2.7 reconciliation and the 2 GB memory test may read data or bundles from
  other branches or a local scratch area, read-only. The ML fairness re-run (adverse actions vs
  increases, saved to file).

