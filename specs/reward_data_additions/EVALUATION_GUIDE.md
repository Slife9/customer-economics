# Evaluation guide: reward data additions

Branch: `feature/reward-data-additions`. Not merged and not deployed; nothing
on `main` or the Render service is changed.

The branch depends on **`fix/negative-control-generation`**, a one-line fix
merged into it. On `main` today the negative-control profile does not
generate at all: a regression from the 100k memory work, commit `161c5d5`.
**Review and merge that branch first.** The fix is byte-identical to `main`
for the demo profile, and byte-identical to the pre-regression output for the
negative control.

**What the branch adds.**
- Three new tables, written after everything else:
  - `Table25_MCC_Reference`
  - `Table26_Signup_Bonus`
  - `Table27_Bureau_Inquiries`
- A reward calibration report.
- Engine contract registration: the new tables are header-checked and never
  loaded.
- Updated sample zips.

**What it does not change.** Every existing output file is byte-identical,
and there are no engine calculation changes. Spec: `SPEC_reward_data_additions.md`.

---

## 1. Set up

```bash
git checkout feature/reward-data-additions
```

Generator and generator app:

```bash
pip install -r datagen_app/requirements.txt
```

Engine, audit and main app:

```bash
pip install -r app/requirements.txt
```

## 2. Generate data

```bash
python -m generator.run --profile demo --out generator/out/demo_rewards
```

```bash
python -m generator.run --profile negative_control --out generator/out/negative_control_rewards
```

Each takes about 20 s at 5,000 customers. Check that each folder contains
`Table25_MCC_Reference.csv`, `Table26_Signup_Bonus.csv` and
`Table27_Bureau_Inquiries.csv`, alongside the usual 37 files.

Calibration report, which runs after generation because it needs the
engine's card ledger (about 10 s):

```bash
python audit/reward_calibration_report.py --data generator/out/demo_rewards
```

To add the new tables to a portfolio generated before this branch:

```bash
python -m generator.reward_additions --data <portfolio dir>
```

## 3. Run the acceptance audit

```bash
python audit/audit_reward_data_additions.py
```

About 2 minutes. To include the scale check, add
`--scale-dir <large portfolio built on this branch>`. As last run, with the
100k portfolio, the result was **33/33 PASSED**. Section 6 has the full
table.

## 4. Generator app

```bash
streamlit run datagen_app/Home.py
```

- Generate a small portfolio (e.g. 1,000 customers), download the zip and
  open it.
- [ ] The zip contains `Table25_MCC_Reference.csv`, `Table26_Signup_Bonus.csv`
      and `Table27_Bureau_Inquiries.csv`.
- [ ] The app otherwise looks and behaves as before. There are no UI changes.

## 5. Main app

```bash
streamlit run app/Home.py
```

- Upload `samples/demo_portfolio.zip`, which now carries the new tables, and
  click **Run analysis**.
- [ ] The analysis runs and shows the same figures as before. The engine
      reads only the new tables' headers.
- [ ] With a 5k portfolio from §2 uploaded instead, the figures match the
      same portfolio generated on `main`.
- [ ] **Try it with the bundled sample** (50k results bundle) is unchanged.

## 6. Results as last run

| Check | Result |
|---|---|
| Byte-identity: all 80 baseline files (demo, negative control, validation reports, ground truth, circularity) | PASS |
| Only Tables 25-27 added per profile | PASS |
| Engine `run_summary.json` equals the baseline (see note) | PASS |
| Integrity on demo, negative control and 100k: joins, every customer-month, counts, MCC coverage, masked IDs, threshold met recomputed from Table5 | PASS (8 checks x 3 portfolios) |
| Determinism: same seed gives identical tables; a different stream seed changes only stream fields | PASS |
| Calibration report produced for 5k and 100k | PASS |
| 100k built inside `build()` | PASS |

The 100k build took 323 s in total. The reward step took 42.8 s of that and
added 0.64 GB on top of the 13.4 GB the generator already holds. Peak memory
for the whole build was 16.2 GB, set elsewhere in the build, not by this
step.

**Engine regression note.** Two fields are excluded from the
`run_summary.json` comparison because they change on every run:
`data_dir` and the run timestamp. One field, `policy_sha256`, is accepted
under a narrow rule:
- It hashes the leverage-policy file's raw bytes.
- The baseline came from a fresh git checkout, which has Windows line
  endings (`core.autocrlf`).
- The audit accepts the field only if the baseline hash equals the same
  file with the other line endings.

## 7. Calibration report summary

| | 5k demo | 100k |
|---|---:|---:|
| Accounts passing the screen (loss after all costs, rewards ≥ 50% of revenue) | 581 | 8,610 |
| Rewards as % of revenue, screened (reference 79%) | 88% | 93% |
| Within / outside / not assessed | 19 / 18 / 2 | 21 / 16 / 2 |

**Inside the reward model's ranges.**
- The overall reward cost share.
- Interchange and earn rates in almost every segment.
- APRs, except bonus chasers at 5k.
- Annual spend for Low-Spend and Relationship customers.
- Redemption cost for cash back, statement credit and merchandise.

**Biggest gaps.** These are all known, and out of scope in spec §6.

| Gap | Observed | Reference |
|---|---|---|
| Relationship Customers' share | 59–60% | 13% |
| Optimizers' share | 1.7–2.4% | 26% |
| Low-Spend share | 9–11% | 32% |
| Bonus Chasers' share | 0.2–0.3% | 19% (none planted, as intended) |
| Unassigned | 19–22% | < 10% |
| Revolving balances, every segment | $0–$71 | $300–$1,000 |
| Quasi-Cash spend | $7.6k–$10.5k | $30k |
| Transfer-partner redemption cost | 1.78× face | 0.6–1.0 |
| Travel-portal redemption cost | 1.48× face | 0.6–1.0 |

## 8. Points to decide

1. **Table25 adds telecom (4814) and college tuition (8220) to "reduced
   earn"**, because of the spec's "observed rate ≤ 1.5%" rule. Keep it, or
   flag only the named codes?
2. **Table26 bonus chasers.** On the 5k data, 67 of 315 bonus earners look
   like chasers on spend or closure, from the generator's normal dormancy.
   That's more than the "few" the spec expected. Nothing is planted.
3. **Table28 merchant offers (Stage 6)** has not been built. It's optional
   and waits for your go-ahead.

## 9. Sign-off checklist

- [ ] `fix/negative-control-generation` reviewed (merge it first).
- [ ] The audit run locally: all checks PASS.
- [ ] The new tables are present in a generated folder and in the
      generator-app zip.
- [ ] The main app shows identical figures with the new tables present.
- [ ] The calibration report has been read; the gaps are accepted as out of
      scope.
- [ ] Decisions in §8 made.
- [ ] Approved for merge (fix branch first, then this branch).

| Reviewer | Date | Decision | Notes |
|---|---|---|---|
| | | | |
