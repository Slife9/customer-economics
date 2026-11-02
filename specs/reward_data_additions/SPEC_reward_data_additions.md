# TASK: Add reward-profitability data to the synthetic generator (additive only)

## 0. Scope and the one hard rule

The L1 Rewards strategy needs data the generator does not produce today. This task **adds**
that information. It must **not change anything the generator already produces**.

**Hard rule:** for the same profile, seed, size and cycles, every existing output table
(Table1 to Table24, including the b/c sub-tables), `build_manifest.json`, the validation
reports and `_ground_truth/` must be **byte-identical** before and after this change. New
information goes into **new tables only**, generated from a **separate random stream**
(e.g. `seed + 7919`), so existing draws are never consumed or reordered.

Do not change distributions, APRs, balances, costs, reward rules, redemption costs or
customer behaviour. Those are known calibration gaps, logged as out of scope in §6.

Work on the feature branch convention already in use. Do not commit to `main`.

## 1. What is missing and why it is needed

| Need for L1 | Gap today | Addition |
|---|---|---|
| Identify quasi-cash / low-interchange spending | MCCs 9311, 9399, 4900 and 6300 exist and earn full points at low interchange, but nothing classifies them | **Table25 MCC reference** (§2.1) |
| Identify sign-up bonus chasers; cost sign-up bonuses | No sign-up bonus data at all | **Table26 sign-up bonus** (§2.2) |
| Confirm bonus chasers and serial card openers | No credit bureau inquiry data | **Table27 bureau inquiries** (§2.3) |
| Size the merchant-funded offers lever | No merchant offer data | **Table28 merchant offers** (§2.4, optional) |
| Compare synthetic data with the reward model's ranges | No reference benchmarks | **Reward calibration report** (§3) |

Not added here: a history of past reward changes and customer responses. Producing realistic
responses would require changing existing behaviour, which breaks the hard rule. The response
sensitivities therefore stay assumption-based until a pilot (or a later, approved generator
change) provides them. Record this in STATUS.md.

## 2. New tables

### 2.1 `Table25_MCC_Reference.csv` (reference data; no randomness)

One row per MCC that appears in `Table5_Transaction`, plus the standard quasi-cash codes
even if absent from the data.

| Column | Meaning |
|---|---|
| Merchant Category Code (MCC) | MCC |
| Merchant Category Description | As in Table5 where present |
| Quasi Cash Flag | True for cash-like spend: 4829, 6050, 6051, 6540, 7995 |
| Low Interchange Flag | True for low or fixed interchange: 9311, 9399, 4900, 6300, 6513, 6012, plus any MCC whose observed effective interchange rate in the generated data is ≤ 1.5% |
| Recommended Reward Treatment | `standard`, `reduced_earn`, `no_earn` (quasi-cash → `no_earn`; low interchange → `reduced_earn`) |
| Rationale | One line |

Observed effective interchange rates are computed from existing Table5 (interchange earned ÷
amount by MCC). This table reads existing outputs and never alters them.

### 2.2 `Table26_Signup_Bonus.csv` (one row per card account)

Derived from existing account, acquisition, transaction, cycle and attrition data, plus the
new random stream for offer terms only.

| Column | Rule |
|---|---|
| Masked Account Number | From Table2 |
| Bonus Offered | True for reward programmes other than `CORE_LOW_RATE_NO_REWARDS` and `SECURED_CASHBACK_1`; draw from the new stream with a programme-level offer rate (e.g. 70%) |
| Offer Spend Threshold USD | By programme tier, e.g. $500 / $1,000 / $3,000 / $4,000 for core / everyday / travel / premium and business |
| Offer Window Months | 3 |
| Bonus Value USD | By tier, e.g. $100 / $150 / $200 / $300 |
| Account Open Cycle Month | From Table2b / Table23 cohort |
| Window Observed | True only if the full offer window falls inside the data's 36 cycles (accounts opened earlier are pre-history) |
| Threshold Met | From **existing** Table5 purchases in the offer window |
| Bonus Earned Cycle Month | First month cumulative spend crossed the threshold |
| Bonus Paid USD | = Bonus Value if threshold met, else 0 |
| Spend Change After Window Pct | Mean monthly spend in the 6 months after the window vs during it (existing data) |
| Closed Within 12 Months Of Bonus | From existing Table22 attrition events |
| Clawback Applied | False (no clawback policy today) |

Notes:
- Bonus cost is **new information, not yet part of NEP**. Do not add it to the ledger in
  this task. The L1 module will report it as a separate, labelled cost until a decision is made.
- Because existing behaviour is unchanged, true bonus chasers will be **rare** in the data.
  That is expected; do not plant them.

### 2.3 `Table27_Bureau_Inquiries.csv` (customer × cycle)

| Column | Rule |
|---|---|
| Masked Customer Number, Cycle Month | All customers and cycles |
| Hard Inquiries | New stream; Poisson with a base monthly rate (about 0.05), raised for customers with existing signals: account opened in the last 6 months, an attrition event in the next 3 months, or high utilisation |
| New Trades Opened Elsewhere | New stream; a fraction of inquiries (about 40%) |
| Inquiries Trailing 12m | Rolling sum |

Document the rates as `estimated` benchmarks. Any correlation must be drawn **from** existing
outputs; nothing in existing tables changes.

### 2.4 `Table28_Merchant_Offers.csv` and `Table28b_Merchant_Offer_Activations.csv` (optional)

Build only after §2.1–2.3 pass.
- **Offers:** offer ID, merchant category, reward rate, cap, merchant-funded share (e.g. 100%), active months.
- **Activations:** account, offer, month, qualifying spend (existing Table5 spend in that
  category), reward amount, merchant-funded amount.

These are **hypothetical offer data for sizing the lever only**. They must not alter existing
reward cost or interchange, and must be labelled as such in the table README.

## 3. Reward calibration report (informational, never fails the build)

Add `Validation_Report_Reward_Calibration.csv`. It compares the generated data with the
reference ranges of the *Reward Profitability Scenario Model v2*, per segment (Optimizers,
Quasi-Cash, Bonus Chasers, Low-Spend, Relationship, Unassigned), using the model's screen
(fully loaded card profit < 0 and reward cost ≥ 50% of revenue) and priority rules:

| Metric | Reference (model base) |
|---|---|
| Segment mix of the screened population | 26 / 10 / 19 / 32 / 13 % (Unassigned < 10%) |
| Annual spend | 24k / 30k / 6k / 4k / 15k |
| Interchange rate | 2.2 / 1.2 / 2.1 / 2.0 / 2.1 % |
| Reward earn rate | 2.6 / 2.0 / 1.8 / 1.5 / 2.5 % |
| Revolving balance | 500 / 800 / 300 / 400 / 1,000 |
| APR | 22 / 21 / 24 / 24 / 20 % |
| Reward cost as % of revenue | about 79% overall |
| Redemption cost per $1 of face value | 0.6–1.0 for travel/transfer/merchandise; 1.0 for cash back |

Report observed value, reference value, and `within / outside` a ±25% band. Tag every
reference as `estimated — source: Reward Profitability Scenario Model v2 (illustrative
industry averages)`. **This report must not fail validation**, because the gaps are known
and deliberately not fixed here.

## 4. Contract, engine and app

- Register the new tables in the data contract as **optional**. The engine must run
  unchanged when they are absent (older portfolios and bundles).
- Do **not** change any engine calculation in this task. The L1 rewards module that consumes
  these tables is a separate spec.
- Generator app: add the new tables to the download zip. No UI changes beyond that.

## 5. Tests (run them; do not claim results not executed)

1. **Byte-identity regression.** Generate the demo and negative-control profiles (5k, seed as
   today) on `main` and on the branch. SHA-256 of every pre-existing file must match.
2. **Engine regression.** `python -m engine.run` on the branch output gives a `run_summary.json`
   identical to `main` (the new tables are ignored by the current engine).
3. **New-table integrity:**
   - keys join to Table1/Table2
   - no missing months
   - threshold-met logic reproducible from Table5
   - inquiry counts non-negative
   - MCC reference covers every MCC in Table5
4. **Determinism.** Same seed gives identical new tables; a different seed changes only the
   new-stream fields.
5. **Calibration report** produced for the 5k demo and the 100k profile. Include its summary
   in the report.

## 6. Out of scope (log in STATUS.md)

- Recalibrating segment mix, revolving balances, APRs, earn rates and redemption cost per
  point to the reward model's ranges. The current data has 59% Relationship, about 3%
  Optimizers, near-zero revolving balances for unprofitable reward accounts, and transfer-partner
  redemptions costing 1.78× face value.
- Planting bonus-chaser or quasi-cash behaviour.
- Reward change history with customer responses.
- Adding sign-up bonus cost to NEP.

## 7. Deliverables

- New tables and their README entries
- Calibration report
- Updated data contract (optional tables)
- Test results (byte-identity table, engine regression, integrity checks)
- STATUS.md update
- Regenerated sample zips that differ from today's **only** by the added files
