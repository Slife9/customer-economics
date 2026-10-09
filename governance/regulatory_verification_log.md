# Regulatory Verification Log: Leverage Capital Cost

One row per rule in `REGULATORY_RULEBOOK.md`. A human closes each row after checking the citation against the primary source (eCFR at ecfr.gov, the Federal Register, or the issuing agency's own site) - this log is seeded with every rule `OPEN`; nothing here has been independently verified yet.

| Rule ID | Citation checked | Source used | Date | Reviewer | Result |
|---|---|---|---|---|---|
| R-01 | 12 CFR 217.10 / 3.10 / 324.10 | | | | OPEN |
| R-02 | 12 CFR 6.4 / 208.43 / 324.403 | | | | OPEN |
| R-03 | 12 CFR 217.10; 84 FR 59230 | | | | OPEN |
| R-04 | 12 CFR 217.10 | | | | OPEN |
| R-05 | 12 CFR 217.10; 79 FR 57725 | | | | OPEN |
| R-06 | 12 CFR 217.10; 79 FR 57725 | | | | OPEN, HIGH PRIORITY |
| R-07 | 12 CFR 217.10; 12 CFR 217.33 | | | | OPEN |
| R-08 | 12 CFR 217.2 | | | | OPEN |
| R-09 | 12 CFR 217.33 | | | | OPEN |
| R-10 | 12 CFR 217.11; 79 FR 24528; 2025 eSLR recalibration | | | | OPEN, HIGH PRIORITY - recalibration status unverified |
| R-11 | 12 CFR 252.5; 12 CFR 217.2; 84 FR 59230 | | | | OPEN |
| R-12 | 12 CFR 217.12; 84 FR 61776; current required ratio | | | | OPEN - ratio value (9% as of 2019) unverified against any later change |
| R-13 | 12 CFR 217.10 | | | | OPEN |
| R-14 | Basel Framework LEV30 | | | | OPEN |
| R-15 | SR 11-7 (2011); OCC Bulletin 2011-12 | | | | OPEN - superseding guidance unverified |
| C-01 | 12 CFR 1002.2(c); 12 CFR 1002.9 | | | | OPEN |
| C-02 | 12 CFR 1026.9(g)(4) | | | | OPEN |
| C-03 | 15 U.S.C. 1691 et seq.; 12 CFR Part 1002 | | | | OPEN |

## Known gaps (not citation errors - scope/convention notes)

1. **R-13 period convention**: this system computes at the same customer-level, trailing-12-month grain as its other diagnostics, not per-account-per-ledger-period with quarterly month-end averaging. Documented in the module docstring and rulebook; not claimed as regulatory reporting equivalence.
2. **Product commitment-type classification** (R-08, M-05) is the bank's own legal determination. This dataset has exactly one undrawn-commitment-bearing product (`credit_card`); the policy schema still requires it be explicitly declared rather than assumed.
3. **Account-level additive cost assumes the SLR is binding.** In reality a bank's leverage cost only bites if the leverage ratio - not risk-based capital - is its binding constraint. This diagnostic reports the SLR-implied cost unconditionally when `slr_mode: true`; it does not model which constraint actually binds for a given bank.
4. **Case studies are illustrative profiles** (`leverage_capital_policy.case_a_slr_category_iii.json`, `leverage_capital_policy.case_b_tier1_regional.json`), not any real bank's financial figures.
5. **`inputs_verified: false`** on both shipped policy files by design (V-08 warns on every run) - every regulatory value is a default pending the verification this log tracks.
