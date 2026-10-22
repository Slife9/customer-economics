# Lever valuation methodology (L1–L6)

This is the corrected, review-approved method for valuing the six levers. The
method is set out in `specs/lever_valuation_rebuild/SPEC_lever_valuation_rebuild.md`.
The code is in `engine/levers/`, and every business assumption is in
`engine/config/lever_assumptions.json`.

> **Regulatory citations in this document are to be confirmed by compliance.**
> Rule IDs (R-xx, C-xx) refer to `governance/REGULATORY_RULEBOOK.md`.

## How every lever is valued

- **Three scenarios, always.** Every lever reports `low`, `base` and `high`.
  They are driven only by `lever_assumptions.json`, and no lever module
  hard-codes a response rate. The scenarios are not confidence intervals: `low`
  is a cautious set of business assumptions, and `high` is an optimistic one.
- **Annual flows.** Every figure is a 12-month flow, computed from the
  trailing 12 cycles or annualised explicitly. A change only affects what it
  actually touches: new customers, new transactions, or implemented actions.
- **Every component carries two labels.**
  - A **value type**: `revenue`, `cost_saving`, `avoided_loss`, `lost_profit`,
    `cost` or `protected_value`.
  - An **evidence basis**: `measured` (from observed data and regulation) or
    `assumption` (depends on a customer response not yet observed). Anything
    labelled `assumption` is **assumption-based and needs a pilot**.
- **Two functions per lever.** Each lever module has `valuation_inputs(...)`,
  which computes JSON-safe inputs from the data and is stored in a results
  bundle, and `value_scenarios(inputs, a)`, which is a pure function. The
  app's what-if explorer calls the same `value_scenarios`, so it can't drift
  from the engine.
- **Portfolio total.** `L1 + L2 + L3 (year 1) + L4 (year 1) + L6 (year 1)`.
  L2's dormant-line right-sizing is added only when
  `dormant_rightsizing_enabled` is true. **L5 is never in the total**: it is
  reported separately as value at risk, a conditional range and a break-even
  keep rate. The total is also split by value type and by basis
  (`engine/levers/summary.py`).
- **Traceability.** The SHA-256 of the assumptions file is recorded in
  `run_summary.json` and in the results-bundle manifest (bundle schema v2).
  A schema-v1 bundle still loads, labelled **"pre-rebuild valuation"**.

Notation: `n` is a count, `mean` is a population mean, and money is annual USD
at the portfolio's own scale.

---

## L1 Rewards & Promo Economics

**Purpose.** Charge for reward value already being delivered, rather than cut
rewards.

**Population (unchanged).** There are two groups:
- **Group 1** (`REVIEW_REWARD_PROGRAM_COST`): loss-makers routed to L1 because
  reward cost dominates their losses.
- **Group 2** (`PILOT_ALIGNED_ANNUAL_FEE`): profitable customers with no
  annual fee and at least $100 a year of reward cost.

**Who is offered the fee.** Group 2 customers with
`reward_expense ≥ min_reward_multiple_of_fee × annual_fee_usd` are
fee-eligible. The extras call the number of fee-eligible customers
`offered_fee`.

**Formula** (all components are assumptions):

| Component | Formula | Type |
|---|---|---|
| `fee_revenue` | n_eligible × accept_share × fee | revenue |
| `downgrade_reward_saving` | n_eligible × downgrade_share × downgrade_reward_reduction × mean(reward_expense, eligible) | cost_saving |
| `closure_card_profit_lost` | −n_eligible × close_share × mean(card_net, eligible) | lost_profit |
| `group1_programme_saving` | group1_reward_reduction × Σ reward_expense (Group 1) | cost_saving |

**Extras.**
- `total_if_closers_leave_bank`: the total with the card-profit loss
  replaced by n_eligible × close_share × mean relationship NEP, for the case
  where customers who close the card leave the bank entirely.
- The fee eligibility threshold.

**Removed.** The old ceiling (total Group 2 reward expense).

**Assumptions.** `annual_fee_usd`, `min_reward_multiple_of_fee`,
`accept_share`, `downgrade_share`, `close_share`,
`downgrade_reward_reduction`, `group1_reward_reduction`.

**Regulation.**
- Reg Z: 45 days' advance notice of a new or changed fee, with the right to
  reject it (12 CFR 1026.9(c)(2), 1026.9(h)).
- The first-year fee limit (12 CFR 1026.52(a)).

**Cautions.** The whole lever is assumption-based. Run a champion/challenger
pilot on fee acceptance before relying on the figure.

---

## L2 Credit Lines & Unused-Line Cost

**Purpose.** Move limits in both directions, and price the carrying cost of
unused lines.

**Population, actions and decrease target rule (unchanged).**
- Actions: `DECREASE_LIMIT`, `INCREASE_LIMIT`, `REACTIVATION_CAMPAIGN` and
  `DEEPEN_RELATIONSHIP_NO_LIMIT_CHANGE`.
- Target limit for a decrease: `max(peak_util × limit × 1.5, trailing_12m_spend × 1.10)`,
  with a floor of $300. The cut is `limit − target`, never below 0.

**Defects corrected.**
- Lifetime default probability is annualised by dividing by `card_life_years`.
- Increases are now valued on headroom actually used. The old formula, based
  on headroom below the peer median, was structurally $0 for stretched
  accounts.

**Formula.**

| Component | Formula | Type | Basis |
|---|---|---|---|
| `decrease_credit_loss_avoided` | Σ(cut × PD_lifetime × LGD × behavioural CCF) × decrease_implemented ÷ card_life_years | avoided_loss | measured |
| `decrease_liquidity_avoided` | Σ(cut × annual_liquidity_cost ÷ avg_undrawn_12m) × decrease_implemented | cost_saving | measured |
| `decrease_slr_capital_freed` | the same, using `leverage_capital_cost` ($0 under the Tier 1 regime) | cost_saving | measured |
| `increase_interest` | Σ(new balance × APR × (1 − pay-in-full share)) | revenue | assumption |
| `increase_funding_cost` | −Σ(new balance × funding rate) | cost | assumption |
| `increase_extra_credit_loss` | −Σ(new balance × PD_lifetime ÷ card_life_years × LGD) | avoided_loss | assumption |
| `increase_extra_slr_capital` | −Σ((new limit − new balance) × SLR rate) | cost | assumption |
| `reactivation_net` | n × reactivation_rate × (mean card_net of active card holders − mean card_net of dormant) − n × campaign_cost | revenue | assumption |

The increase terms use:
- new limit = limit × `increase_pct`
- new balance = new limit × `headroom_used`
- funding rate = Σ funding_cost ÷ Σ(latest utilisation × limit), across card holders

`DEEPEN_RELATIONSHIP_NO_LIMIT_CHANGE` is always worth $0.

**Dormant right-sizing.** This is an optional feature flag, off by default and
pending a business decision. The value is the carrying cost of dormant lines
× (1 − reactivation_rate) × `dormant_rightsize_implemented` ×
`dormant_rightsize_reduction`. It always appears in the extras, and is added to
the total only when the flag is enabled.

**Extras.** A carrying-cost table by L2 group: unused lines, HQLA, liquidity
cost, SLR cost, and card_net before and after carrying cost. It is the core of
the L2 story.

**Regulation.**
- Reg B adverse-action notice on any decrease (C-01, 12 CFR 1002.9).
- Reg Z on limit reductions (C-02).
- Fair-lending review (C-03).
- Risk-based capital charges 0% CCF on unconditionally cancellable lines (R-09).
- The SLR charges them at 10% CCF (R-05, R-06), and the Tier 1 regime doesn't
  charge them (R-01).
- LCR outflow on undrawn retail commitments (12 CFR Part 249).

**Cautions.**
- The decrease side is measured, apart from the implementation share.
- Increases and reactivation are assumption-based and need a pilot.

---

## L3 Value-Based Pricing

**Purpose.** Reprice accounts whose risk has drifted since origination while
their rate hasn't.

**Population.** Charged APR is at least 2 points below the median of the
customer's credit-score-band peers, or the account was routed to L3.
**Population fix (Stage A5):** accounts with tenure under 12 months are
excluded, even when routed (CARD Act first-year protection).

**Who is targeted.** Revolvers only. Revolving balance = latest purchase
balance × (1 − pay-in-full share) > 0. Flagged and targeted counts are both
reported.

**Formula.** The full-year gap value is Σ(gap ÷ 100 × revolving balance)
across targeted accounts.

| Component | Formula | Type | Basis |
|---|---|---|---|
| `extra_interest` (year 1) | full × year1_balance_repriced × (1 − attrition) × (1 − balance_reduction_stayers) | revenue | assumption |
| `card_profit_lost` | −n × attrition × mean(card_net) | lost_profit | assumption |
| `notice_cost` | −n × notice_cost_usd | cost | measured |

**Extras.**
- `steady_state`: the value once all balances are repriced.
- `total_if_leavers_leave_bank`.
- Flagged and targeted counts.

**Removed.** The old ceiling, which applied zero elasticity to whole balances.
It repriced existing balances, which the CARD Act prohibits, and it included
customers who pay in full.

**Regulation.**
- No rate increase in the first year (12 CFR 1026.55).
- A new rate applies to new transactions only (12 CFR 1026.55(b)).
- 45 days' notice (12 CFR 1026.9(c)(2)).
- Rate increases must be re-evaluated (12 CFR 1026.59).
- Fair-lending review of the repricing worklist (C-03).

**Cautions.**
- Assumption-based, so a champion/challenger test is needed.
- Note the steady-state vs year-1 gap.

---

## L4 Cost-to-Serve Migration

**Purpose.** Move avoidable servicing demand to cheaper channels.

**Population (unchanged).** Customers routed to L4, or with at least 3
avoidable calls or at least 6 paper statements.

**Defects corrected.**
1. **Three years were counted as one.** The driver table is now restricted to
   the trailing 12 cycles before anything is summed.
2. **All calls were counted.** Only account-cycles whose recorded primary call
   reason is avoidable (billing, rewards or rate queries) now count.
   - Table 12 records one primary reason per account per month, so this
     counts what is actually observed as avoidable.
   - On the 5k demo, summing every call in those months instead would add
     about 9%.
3. **Digital replacement was ignored.**
   - Saving per deflected call = call cost − digital-session cost ×
     `sessions_per_deflected_call`.
   - Saving per migrated statement = paper cost − electronic-statement cost.
   - Unit costs come from the cost pools (Table 11). `unit_costs` in the
     config is the fallback only when a pool is absent. Today the pool values
     equal the config values.

**Formula.**

| Component | Formula | Type | Basis |
|---|---|---|---|
| `calls_to_self_service` | annual avoidable calls × call_deflection × (1 − excluded_share) × saving per call | cost_saving | assumption |
| `paper_to_electronic` | annual paper statements × paper_migration × (1 − excluded_share) × saving per statement | cost_saving | assumption |
| `outreach_cost_year1` | −n × outreach_cost_usd | cost | measured |

**Extras.**
- `from_year2`: the total without the outreach cost.
- Annual avoidable calls and paper statements.
- Avoided calls per month.

**Staffing step.** Monthly call volume before and after is compared against
the monthly cost-pool bands. Any step saving is reported in extras only,
**never in the total**. The demo bands are scaled for a 5–8k account book and
must be recalibrated for a real portfolio.

**Regulation.**
- Electronic statements need E-SIGN consent (15 U.S.C. 7001(c)).
- Reg Z electronic delivery (12 CFR 1026.5(a)(1)(iii)).
- `excluded_share` covers customers who must keep paper or phone service.

**Cautions.**
- Deflection and migration rates are assumptions.
- The engine's trailing-12-cycle window has 6–10% less avoidable volume than
  the full-history average, because accounts close or go quiet over time.

---

## L5 Retention Targeting

**Purpose.** Spend the retention budget according to what customers are
worth.

**Population.** Valued or Premier customers showing at least one warning
signal:
- a closure-request contact,
- spend down at least 30% (3 months against the prior 3), or
- a rate at least 2 points above their peers.

**Population fix (Stage A5):** the closure-request signal now uses the
trailing 12 cycles only.

**Valuation: unpriced.** `priced_value_usd` is always None, and L5 is never in
a total. `unpriced_context_usd` is the value at risk: the trailing-12-month NEP
of these customers.

| Conditional component | Formula | Type | Basis |
|---|---|---|---|
| `value_kept` | n × leave_rate × keep_rate × mean value at risk | protected_value | assumption |
| `outreach_cost` | −n × outreach_cost_usd | cost | measured |
| `offer_cost` | −n × offer_takeup × offer_cost_usd | cost | assumption |

**Extras.**
- `breakeven_keep_rate` = (outreach + takeup × offer) ÷ (leave_rate × mean
  value at risk).
- Counts and value at risk by signal.
- **Historical leave rates** from Table 22 (voluntary closures), shown next to
  the configured `leave_rate` and never overwriting it:
  - the share of currently Valued/Premier customers with a voluntary closure
    in the trailing 12 cycles;
  - the share of customers with at least 12 cycles of follow-up after their
    first closure-request contact who closed voluntarily within those 12
    cycles.

**Regulation.**
- UDAAP (12 U.S.C. 5531, 5536).
- Fair-lending consistency in who gets retention offers (C-03).
- Reg Z notice if an offer changes account terms.

**Cautions.** This is a conditional estimate, not a forecast. Uplift has to
come from a pilot.

---

## L6 Channel Quality Review

**Purpose.** Steer acquisition spend towards the channels that produce
valuable customers.

**Population (unchanged).** Customers acquired through the bottom third of
channels, ranked by net value after acquisition cost.

**Defects corrected.**
- **Stock, not flow.** The old value was the gap × every existing account in
  the worst channel. A budget change only affects **future** acquisitions.
- **Unit mixing.** One-off acquisition cost is no longer subtracted from
  annual profit.

**Inputs.** Customers acquired *within the observation window* (CAC payback
status is Recovered or Not yet recovered), grouped by channel:
- count per year (n ÷ window years),
- mean trailing-12m NEP,
- mean CAC,
- annual spend.

The worst channel has the lowest NEP ÷ CAC, and the best has the highest.

**Formula.** The amount shifted is `budget_shift_share` × the worst channel's
annual spend. The shift is budget-neutral.

| Component | Formula | Type | Basis |
|---|---|---|---|
| `profit_lost_worst_channel` | −(shifted ÷ CAC_worst) × NEP_worst | lost_profit | assumption |
| `profit_gained_best_channel` | shifted ÷ (CAC_best × marginal_cac_multiplier) × NEP_best × incremental_quality | revenue | assumption |

**Extras.**
- `after_n_years` = year-1 total × Σ_{i<build_years} (1 − annual_attrition)^i.
- Customers lost and gained.
- `breakeven_quality`.
- The channel table.

**Level of valuation.** L6 is valued at channel level, so there is no
per-customer figure.

**Sanity check.** The base total is less than total annual acquisition spend.
The audit asserts this.

**Regulation.**
- FCRA prescreened offers (15 U.S.C. 1681b(c), 1681m(d)).
- Fair-lending and redlining review of where marketing goes (C-03).
- UDAAP.

**Cautions.**
- Marginal CAC and incremental quality are assumptions.
- In the synthetic demo the channel quality gap is planted by the generator,
  so finding it shows the engine can detect it; it is not a business finding.

---

## Decisions taken during implementation

1. **Negative-control gate input (approved by the user).** The gate's value
   side now reads `SizeResult.gate_value_usd`: the base-scenario value of only
   the components the lever's `driver()` measures.
   - L2: the decrease side.
   - L1, L3 and L4: the full base total.

   The pass rule in `negative_control.check()` is unchanged. Comparing L2's
   full total, which moves in both directions, against its one-directional
   idle-limit driver flipped L2 to FAIL. That was a mismatch of scope, not
   circularity: the control book has fewer idle lines and more stretched
   ones. Verdicts are identical under low, base and high
   (`audit/audit_lever_estimates.py`).
2. **L4 acceptance tolerance (approved by the user).** L4 totals are judged
   against ±15% of the gross amounts being netted, and each component is
   still judged at ±15%. The low-scenario total is a near-cancelling net, so
   a ±15% band on the net itself magnified an in-band 7–8% savings
   difference into about 24%.
3. **Avoidable calls are counted as account-cycles** whose recorded primary
   reason is avoidable. See L4 above.
4. **L4 unit costs are read from Table 11**, as the spec requires. The
   config's `unit_costs` is the fallback only.
