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
streamlit run rewards_app/Home.py --theme.baseFontSize 18
```

The app opens on the **Overview**, with the bundled 100,000-customer reward
stress book already loaded. That book is
`samples/reward_stress_100k_accounts.parquet`, an 11 MB per-account frame;
the raw tables of a 100k book come to about 5 GB. Move between pages with
the sidebar.

To rebuild the 100k sample (same seed, about 15 minutes):

```bash
python -m rewards_app.build_sample
```

The 5,000-customer stress book (`samples/reward_stress_portfolio.zip`) stays
as the audit's regression fixture. Regenerate it with:

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

As last run: **20/20 PASSED** with `--scale` (19/19 without), and **23/23
PASSED**.

The first audit covers:
- the model reproducing the workbook (90 values + 3 totals, $0.00
  difference);
- reconciliation to the engine on the two 5k samples and on the 100k sample;
- segmentation and the rule trace;
- the model's invariants;
- all 9 app pages rendering on all three samples;
- regenerating the bundled 5k sample byte for byte.

Add `--scale` to also rebuild the 100k sample from a fresh generator run
and compare it, which takes about 30 minutes.

The second proves the existing demo and negative-control data, and the
engine's results, are byte-identical. Adding `reward_stress` changed
nothing that already existed.

## 3. What to check

**Overview (landing page).** Expected on the 100k book:
- 100,000 customers, of whom 89,139 hold a card account. The others have
  only deposits or loans.
- 19,915 unprofitable reward accounts (22.3%), losing $3,201,716 a year.
- Their reward cost, including sign-up bonuses, is 123.6% of their revenue.

- [ ] The eight figure cards, the key takeaways and the eight charts make the
      headline clear within a couple of minutes.
- [ ] Switching the scenario updates the cards and the segment charts.

**Scenario dashboard.** Expected on the 100k book. Reward cost / revenue
here excludes sign-up bonuses (117.6% today):

| Scenario | Change in card profit | Accounts lost | Reward cost / revenue | At 1.5x response |
|---|---:|---:|---:|---:|
| Conservative | +$1,486,494 | 790 (4.0%) | 103% | +$1,518,642 |
| Base | **+$2,965,252** | 1,714 (8.6%) | 86% | +$2,887,454 |
| Aggressive | +$4,275,448 | 3,556 (17.9%) | 67% | +$3,802,016 |

Base by segment:

| Segment | Change in card profit |
|---|---:|
| Optimizers | +$2,251,033 |
| Relationship | +$331,861 |
| Quasi-Cash | +$186,564 |
| Bonus Chasers | +$155,713 |
| Low-Spend | +$40,080 |
| Unassigned | $0 (gets no reward lever) |

- [ ] The figures above match.
- [ ] The stress test still improves profit at 1.5x, as the workbook's
      guidance requires.

**Segments.**
- [ ] The mix of the 19,915 accounts: Optimizers 27.5%, Relationship 14.7%,
      Quasi-Cash 14.7%, Low-Spend 9.0%, Bonus Chasers 8.5%, Unassigned 25.5%.
      The page shows this portfolio only; there is no comparison with the
      workbook's illustrative figures.
- [ ] The "Why accounts are Unassigned" explanation makes sense. Most are
      flat-rate cash-back transactors, which the segment rules don't cover.

**Levers & assumptions.**
- [ ] Change one value, for example the Base earn-rate cut for Optimizers.
      The dashboard changes and shows an "edited" warning.
- [ ] Reset restores the workbook values.

**Customer drill-down.** Type `ACC0000021` (an Optimizer) and `ACC0000225`
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
6. **The 100k sample ships as a per-account frame, not raw tables.** The
   raw tables come to 5 GB. The frame holds every figure the app uses and is
   rebuilt by `python -m rewards_app.build_sample`. The 5k samples remain
   the audit's byte-identity fixtures.
7. **Presentation.** Text is enlarged for this app only: CSS, chart fonts,
   and `--theme.baseFontSize 18` for the tables. The shared
   `.streamlit/config.toml` is unchanged, so the six-lever app looks as
   before.

## 5. Sign-off

- [ ] Both audits pass locally.
- [ ] The dashboard, segments and drill-down have been checked.
- [ ] The design decisions in section 4 are accepted.
- [ ] Merge order: `fix/negative-control-generation`, then
      `feature/reward-data-additions`, then this branch.

| Reviewer | Date | Decision | Notes |
|---|---|---|---|
| | | | |
