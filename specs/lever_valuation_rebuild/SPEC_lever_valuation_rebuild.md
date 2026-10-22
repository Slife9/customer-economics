# TASK: Rebuild lever valuation (L1–L6) to the corrected, review-approved methodology

## 0. Authority and scope

A stakeholder review found that the engine's lever values are overstated or
inconsistent (the deck showed $37M–$60M a year for a 500k bank; the corrected
figure is about $10M). Each lever was rebuilt by hand, reviewed and approved.
**This task is the approved change to lever valuation.** It supersedes, for lever
sizing only, earlier instructions not to change lever logic.

Still do NOT change: NEP / ledger, CEV scoring and bands, suppression, dominant-cost
routing and its threshold, lever *populations* (except the two fixes in §4.3 and §4.5,
done as a separate stage), fairness tests, negative-control mechanics, the ML model,
or the liquidity and leverage diagnostic formulas.

Inspect the current repository first. It has moved on since review (results bundle,
`render.yaml`, redesigned pages). Trust the code over file names in this document.

## 1. Files supplied with this spec

| File | Purpose |
|---|---|
| `reference_lever_estimates.py` | Readable reference implementation of every corrected formula. Port the logic into `engine/levers/`; do not import it from the engine. |
| `lever_assumptions.json` | All business assumptions, with low / base / high scenarios. Copy to `engine/config/lever_assumptions.json`. |
| `expected_values.json` | Reference outputs on two fixtures: the bundled 5k demo and the 100k results bundle. Acceptance targets (§7). |

## 2. Principles

1. **Every value has a stated type**: `revenue`, `cost_saving`, `avoided_loss`,
   `lost_profit`, `cost`, `protected_value`.
2. **Every component has an evidence basis**: `measured` (derived from observed data
   and regulation) or `assumption` (depends on a customer response not yet observed).
   Anything resting on an `assumption` needs a pilot, and outputs must say so.
3. **Three scenarios, always**: `low`, `base`, `high`, driven only by
   `lever_assumptions.json`. No hard-coded response rates in lever code.
4. **Annual means annual.** Every flow is computed on a 12-month basis from the
   trailing 12 cycles, or annualised explicitly. Never sum the full history and call it a year.
5. **Flows, not stocks.** A change can only affect what it actually touches (new
   customers, new transactions, implemented actions).
6. **L5 stays unpriced.** It gets a conditional estimate and a break-even test, never
   a value in the portfolio total.

## 3. Output contract

Extend `SizeResult` (keep existing fields for backward compatibility):

```text
SizeResult
  priced_value_usd      = base-scenario total (None for L5)
  unpriced_context_usd  = L5 value at risk; otherwise None
  scenarios = {
    "low" | "base" | "high": {
      "components": { name: {"value_usd": float, "value_type": str, "basis": "measured"|"assumption"} },
      "total_usd": float,
      "extras": { lever-specific figures listed in §4 }
    }
  }
  assumptions_used      = the lever's block from lever_assumptions.json
  method_note           = one paragraph, plain English
```

Add a portfolio summary (run summary, bundle and app):
- low / base / high total = sum of L1, L2, L3 (year 1), L4 (year 1), L6 (year 1)
- L2 dormant right-sizing is added **only** if `dormant_rightsizing_enabled` is true
- L5 is reported separately (value at risk, conditional range, break-even), **never** in the total
- the same totals split by `value_type` and by `basis`

Record the assumptions file's SHA-256 in `run_summary.json` and the bundle manifest.
Bump the bundle schema version, and keep loading of old bundles working with a
clear "pre-rebuild valuation" label.

## 4. Lever methods

`n` = count, `mean` = population mean. All money is annual USD at the portfolio's own
scale (do not apply ×5; that scaling is presentation-only).

### 4.1 L1 Rewards & Promo Economics

Population and worklist unchanged.

- **Group 1** = `REVIEW_REWARD_PROGRAM_COST`; **Group 2** = `PILOT_ALIGNED_ANNUAL_FEE`.
- **Fee-eligible**: Group 2 with `reward_expense >= min_reward_multiple_of_fee × annual_fee_usd`.
- **Components**:
  - `fee_revenue` = n_elig × accept_share × fee (revenue, assumption)
  - `downgrade_reward_saving` = n_elig × downgrade_share × downgrade_reward_reduction × mean(reward_expense of eligible) (cost_saving, assumption)
  - `closure_card_profit_lost` = −n_elig × close_share × mean(card_net of eligible) (lost_profit, assumption)
  - `group1_programme_saving` = group1_reward_reduction × sum(reward_expense of Group 1) (cost_saving, assumption)
- **Extras**: `offered_fee`; `total_if_closers_leave_bank` (replace the card-profit loss with
  n_elig × close_share × mean relationship NEP).
- **Remove**: the old ceiling (total reward expense of Group 2).

### 4.2 L2 Line Management by Value

Population, actions and the decrease target-limit rule unchanged.

- **Defect 1, annualise default probability.** Expected loss uses `pd_lifetime`. Divide by
  `card_life_years` for an annual figure.
- **Defect 2, value increases.** The current headroom-below-peer formula is structurally $0
  for stretched accounts. Replace it with the method below.
- **Decreases** (`DECREASE_LIMIT`), cut = current_limit − target (≥ 0):
  - `decrease_credit_loss_avoided` = Σ(cut × pd_lifetime × lgd × behavioral_ccf) × decrease_implemented ÷ card_life_years (avoided_loss, measured; implementation is an assumption)
  - `decrease_liquidity_avoided` = Σ(cut × annual_liquidity_cost ÷ avg_undrawn_12m) × decrease_implemented (cost_saving, measured)
  - `decrease_slr_capital_freed` = same with `leverage_capital_cost` (cost_saving, measured; $0 under the Tier 1 regime)
- **Increases** (`INCREASE_LIMIT`), new limit = current_limit × increase_pct, new balance = new limit × headroom_used:
  - `increase_interest` = Σ(new balance × APR × (1 − transactor_share_12m)) (revenue, assumption)
  - `increase_funding_cost` = −Σ(new balance × funding_rate), where funding_rate = Σ funding_cost ÷ Σ(latest_utilization × current_limit) over card holders (cost)
  - `increase_extra_credit_loss` = −Σ(new balance × pd_lifetime ÷ card_life_years × lgd) (avoided_loss, negative)
  - `increase_extra_slr_capital` = −Σ((new limit − new balance) × leverage rate) (cost)
- **Reactivation** (`REACTIVATION_CAMPAIGN`):
  - `reactivation_net` = n × reactivation_rate × (mean card_net of active card holders − mean card_net of dormant) − n × campaign_cost_usd (revenue, assumption)
- **`DEEPEN_RELATIONSHIP_NO_LIMIT_CHANGE`** = $0, always.
- **Optional dormant right-sizing** (feature flag, default **off**, pending business decision):
  - carrying cost of dormant lines × (1 − reactivation_rate) × dormant_rightsize_implemented × dormant_rightsize_reduction (cost_saving, assumption)
  - Report it in `extras` regardless of the flag; add it to totals only when enabled.
- **Extras**: the carrying-cost table by L2 group (unused lines, HQLA, liquidity cost, SLR cost,
  card_net before and after carrying cost). It is the core of the L2 story.

### 4.3 L3 Value-Based Pricing

- **Population fix (separate stage, §6 step 5).** Accounts with tenure < 12 months must be
  excluded even when added via `routed_lever == "L3"`. The reference already excludes them.
- **Target revolvers only**: revolving balance = latest_purchase_balance × (1 − transactor_share_12m) > 0.
  Report flagged vs targeted counts.
- **Components**, with full = Σ(gap ÷ 100 × revolving balance) over targeted:
  - `extra_interest` (year 1) = full × year1_balance_repriced × (1 − attrition) × (1 − balance_reduction_stayers) (revenue, assumption)
  - `card_profit_lost` = −n × attrition × mean(card_net) (lost_profit, assumption)
  - `notice_cost` = −n × notice_cost_usd (cost)
- **Extras**: `steady_state` (repriced share = 1), `total_if_leavers_leave_bank`, flagged / targeted counts.
- **Remove**: the zero-elasticity ceiling on whole balances (it repriced existing balances,
  which the CARD Act prohibits, and included pay-in-full customers).

### 4.4 L4 Cost-to-Serve Migration

- **Defect 1, three years counted as one.** Restrict the driver table to the **trailing 12 cycles**
  before summing. The reference scales by 12/cycles because a bundle lacks raw drivers; the
  engine has them, so window properly.
- **Defect 2, all calls counted.** Count only calls whose `Primary Call Reason` is in
  AVOIDABLE_CALL_REASONS (billing, rewards, rate).
- **Defect 3, digital replacement ignored.** Read unit costs from the cost pools (Table 11):
  call, digital session, paper statement, electronic statement. Saving per deflected call =
  call − digital_session × sessions_per_deflected_call. Saving per statement = paper − electronic.
- **Components**:
  - `calls_to_self_service` = annual avoidable calls × call_deflection × (1 − excluded_share) × saving per call (cost_saving, assumption)
  - `paper_to_electronic` = annual paper statements × paper_migration × (1 − excluded_share) × saving per statement (cost_saving, assumption)
  - `outreach_cost_year1` = −n × outreach_cost_usd (cost)
- **Extras**: `from_year2` (no outreach cost), annual avoidable calls, annual paper statements,
  avoided calls per month.
- **Staffing step**: compare **monthly** call volume before and after against the **monthly**
  bands. Report any step saving in `extras` only, never in totals, with a note that the demo
  cost-pool bands are scaled for a 5–8k book and must be recalibrated for real portfolios.

### 4.5 L5 Retention Targeting

- `priced_value_usd` stays **None**.
- `unpriced_context_usd` = value at risk (unchanged).
- **Conditional scenarios**:
  - `value_kept` = n × leave_rate × keep_rate × mean value at risk (protected_value, assumption)
  - `outreach_cost` = −n × outreach_cost_usd
  - `offer_cost` = −n × offer_takeup × offer_cost_usd
- **Extras**:
  - `breakeven_keep_rate` = (outreach + takeup × offer) ÷ (leave_rate × mean value)
  - counts and value at risk by signal
  - **historical leave rates** from Table 22 (voluntary closures): the overall annual rate for
    Valued/Premier, and the rate within 12 months after a closure-request contact. Report them
    next to the configured `leave_rate`; do not overwrite config.
- **Population fix (separate stage, §6 step 5)**: the closure-request signal must use the
  trailing 12 cycles only, not any call in the full history.

### 4.6 L6 Channel Quality Review

- **Defect, stock not flow.** Replace `gap × all existing accounts in the worst channel`. Budget
  changes affect only **future** acquisitions.
- **Defect, unit mixing.** Stop subtracting one-off CAC from annual profit.
- **Inputs**: customers acquired **within the observation window** (`cac_payback_status` in
  {Recovered, Not yet recovered}), by channel: count per year (= n ÷ window years), mean
  trailing-12m NEP, mean CAC, annual spend.
  - worst channel = lowest NEP ÷ CAC
  - best channel = highest NEP ÷ CAC
- **Budget-neutral shift**, shifted = budget_shift_share × worst channel's annual spend:
  - `profit_lost_worst_channel` = −(shifted ÷ CAC_worst) × NEP_worst (lost_profit, assumption)
  - `profit_gained_best_channel` = shifted ÷ (CAC_best × marginal_cac_multiplier) × NEP_best × incremental_quality (revenue, assumption)
- **Extras**:
  - `after_n_years` = year-1 total × Σ_{i<build_years} (1 − annual_attrition)^i
  - customers lost and gained
  - `breakeven_quality`
  - the channel table
- **Sanity check** (assert in the audit): base total < total annual acquisition spend.

## 5. App and outputs

Wherever lever values appear (Home, Levers & Strategy, Downloads, bundle):
- show the **base** figure with the low–high range
- show the value type, and an "assumption-based, pilot required" tag where basis = assumption
- show L5 as value at risk plus break-even, never in a total

Keep presentation changes minimal; no redesign in this task. Update `leakage_register` /
run-summary fields to carry the scenario structure.

## 6. Stages (report after each)

1. **Audit.** Locate current sizing code, outputs and consumers (app pages, bundle export,
   negative-control gate). Confirm how the gate uses lever values. It must keep using lever
   `driver()` metrics; if it uses priced values anywhere, keep its pass logic unchanged and report.
2. **Config and contract.** Add `lever_assumptions.json`, its loader, and the extended `SizeResult`.
3. **Levers.** Implement §4.1–4.6 (without the §4.3 and §4.5 population fixes).
4. **Acceptance.** `audit/audit_lever_estimates.py` (§7) must pass on both fixtures.
5. **Population fixes.** Apply the L3 first-year exclusion and the L5 12-cycle closure signal.
   Report how counts and values change, and regenerate the fixture expectations, documenting the deltas.
6. **Outputs and app.** §3 summary, §5 display, bundle schema bump.
7. **Docs.** `docs/LEVER_METHODOLOGY.md` (one section per lever: purpose, population, formula,
   assumptions, value types, regulation, cautions), plus ARCHITECTURE.md and STATUS.md updates.

## 7. Acceptance tests — `audit/audit_lever_estimates.py`

Run as a script, in the same style as the other audit scripts.

- **Fixtures**: the bundled 5k demo (full pipeline, default leverage regime) and the 100k
  results bundle (Case A). Compare the engine's scenario outputs with `expected_values.json`.
- **Tolerance**:
  - **±0.5%** for L1, L2, L3, L5, L6 totals and components
  - **±15%** for L4, because the engine windows the trailing 12 cycles while the reference
    scales the full history by 12/36. Explain the observed difference.
- **Invariants**:
  - low ≤ base ≤ high for every total
  - L5 never in the portfolio total
  - L6 base < annual acquisition spend
  - L4 from_year2 ≤ trailing-12m servicing cost of its population
  - changing any assumption in config changes the output (sensitivity smoke test)
  - no component without `value_type` and `basis`
- Print a PASS/FAIL table. Do not claim results you did not execute.

### Key expected values (base scenario)

| Lever | 5k demo | 100k bundle |
|---|---|---|
| L1 total | 52,111 | 997,815 |
| L2 total (dormant right-sizing off) | 34,990 | 676,637 |
| L3 total, year 1 | 2,108 | 20,968 |
| L4 total, year 1 (±15%) | 5,710 | 114,066 |
| L5 conditional net | −356 | 11,857 |
| L6 total, year 1 | 3,407 | 63,686 |

Full low / base / high values, components and extras are in `expected_values.json`.

## 8. Related issues NOT in scope (log in STATUS.md only)

- Loan NEP carries no ECL or capital charge (an upper bound).
- ML treatment-fairness failures in 5 metros on the 100k run.
- Demo cost-pool staffing bands scaled for a 5–8k book.
- The L6 channel gap is planted by the generator (detection capability, not a finding).

## 9. Deliverables

- Code changes, the new config file and the audit script
- Methodology document
- Stage-by-stage report: files changed, the acceptance table actually run, population-fix
  deltas, and open issues
