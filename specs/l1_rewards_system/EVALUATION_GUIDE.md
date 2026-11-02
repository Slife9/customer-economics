# Evaluation guide: L1 rewards system

Branch `feature/l1-rewards-system`. It builds on `feature/reward-data-additions`,
which in turn builds on `fix/negative-control-generation`. **Merge in that
order.** Nothing here is on `main` or deployed.

**What it is.** A standalone app and model for the L1 rewards lever only. It
applies the *Reward Profitability Scenario Model v2* to a portfolio's own
data:
1. Screen the unprofitable reward accounts.
2. Segment them by the workbook's priority rules.
3. Value the workbook's nine levers per account, with its customer-response
   assumptions.

**Decisions taken with you:**
- a standalone app, not part of the six-lever app;
- a new generator profile, `reward_stress`, instead of changing existing
  data;
- the Excel defaults, editable in the app.

---

## 1. Run it

Engine, app and audits:

```bash
pip install -r app/requirements.txt
```

Generator:

```bash
pip install -r datagen_app/requirements.txt
```

```bash
streamlit run rewards_app/Home.py
```

On **Load portfolio**, choose **Reward stress book** and click **Load
sample**. The first load takes about 20 seconds while it builds the account
P&L from the engine's ledger. Move between pages with the sidebar.

To generate the stress book yourself (same seed, byte-identical to the
bundled sample):

```bash
python -m generator.run --profile reward_stress --out generator/out/reward_stress
```

## 2. Run the tests

```bash
python audit/audit_l1_rewards_system.py
```

```bash
python audit/audit_reward_data_additions.py
```

As last run: **13/13** and **23/23 PASSED**.

The first audit covers:
- the model reproducing the workbook (90 values + 3 totals, $0.00
  difference);
- reconciliation to the engine on both samples;
- segmentation and the rule trace;
- the model's invariants;
- all 8 app pages rendering;
- regenerating the bundled sample.

The second proves the existing demo and negative-control data, and the
engine's results, are byte-identical. Adding `reward_stress` changed
nothing that already existed.

## 3. What to check

**Scenario dashboard.** Expected on the reward stress book: 1,168 screened
accounts, which lose $188,937 a year in total. Their reward cost, including
sign-up bonuses, is 119.5% of their revenue.

| Scenario | Change in card profit | Accounts lost | Reward cost / revenue | At 1.5x response |
|---|---:|---:|---:|---:|
| Conservative | +$78,596 | 45 (3.9%) | 99% | +$79,978 |
| Base | **+$154,014** | 97 (8.3%) | 83% | +$148,990 |
| Aggressive | +$221,526 | 203 (17.3%) | 65% | +$194,677 |

Base by segment:

| Segment | Change in card profit |
|---|---:|
| Optimizers | +$116,404 |
| Relationship | +$14,433 |
| Quasi-Cash | +$11,523 |
| Bonus Chasers | +$8,926 |
| Low-Spend | +$2,727 |
| Unassigned | $0 (gets no reward lever) |

On the standard demo book: 636 screened accounts, and Base gives +$24,979.
Relationship customers dominate there (60%).

- [ ] The figures above match.
- [ ] The stress test still improves profit at 1.5x, as the workbook's
      guidance requires.

**Segments.**
- [ ] The mix against the workbook:

  | Segment | This book | Workbook |
  |---|---:|---:|
  | Optimizers | 27% | 26% |
  | Relationship | 14% | 13% |
  | Quasi-Cash | 14% | 10% |
  | Low-Spend | 11% | 32% |
  | Bonus Chasers | 8% | 19% |
  | Unassigned | 26% | < 10% |

- [ ] The "Why accounts are Unassigned" explanation makes sense. Most are
      flat-rate cash-back transactors, which the workbook's rules don't
      cover.

**Levers & assumptions.**
- [ ] Change one value, for example the Base earn-rate cut for Optimizers.
      The dashboard changes and shows an "edited" warning.
- [ ] Reset restores the workbook values.

**Customer drill-down.** Type `ACC0000007` (an Optimizer) and `ACC0000045`
(a Bonus Chaser).
- [ ] The screen and the rules explain why each account is where it is.
- [ ] The before/after P&L adds up.
- [ ] The recommended actions fit the segment.

**Data & calibration.**
- [ ] The reconciliation shows $0.00.
- [ ] The limitations are acceptable.

## 4. Design decisions to review

1. **Sign-up bonus counts in the screen and the P&L, as in the workbook.**
   The engine's own profit leaves it out. Without it, most bonus chasers
   never look unprofitable.
2. **"Inactive since the bonus posted"** is read as no purchases after the
   3-month offer window, because the bonus posts when the window closes.
3. **The ledger has no network / processing line.** The workbook charges
   0.1% of spend; here that line is $0.
4. **The engine's capital charge is scaled** for balance and line changes
   the way the workbook scales its own capital formula.
5. **`reward_stress` is a deliberately skewed stress book.** It uses four
   behaviour hooks that only this profile switches on. It fails several
   realism checks by design, as the other variant profiles do. Low-Spend and
   Bonus Chasers stay short of the workbook's shares, because both need
   accounts of a particular age.

## 5. Sign-off

- [ ] Both audits pass locally.
- [ ] The dashboard, segments and drill-down have been checked.
- [ ] The design decisions in section 4 are accepted.
- [ ] Merge order: `fix/negative-control-generation`, then
      `feature/reward-data-additions`, then this branch.

| Reviewer | Date | Decision | Notes |
|---|---|---|---|
| | | | |
