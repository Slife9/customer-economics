# Regulatory Rulebook: Leverage Capital Cost on Unused Credit Lines

**Version:** 1.0.0 (draft for verification)
**Owner:** model governance
**Used by:** `engine/core/leverage_capital.py`, policy files `engine/config/leverage_capital_policy.*.json`, the Leverage Diagnostic page (`app/pages/24_Leverage_Capital.py`), `audit/audit_leverage_capital.py`, the run audit record (`result["leverage_audit"]`)

This document supersedes nothing in this repo - it was supplied by the project owner (`SPEC_leverage_capital_cost_v2.md` and this rulebook, delivered as a spec package) to extend the existing liquidity cost diagnostic pattern with a second, separate capital regime.

## Verification status of this document

This register was drafted without live access to the regulations. **Every citation and every regulatory value below is `OPEN` until a reviewer checks it against the primary source** (eCFR at ecfr.gov, the Federal Register, or the agency's own site) and records the result in `governance/regulatory_verification_log.md`. Section references in particular must be checked, because regulations are renumbered and amended. Items marked **HIGH PRIORITY** are known to have changed recently or carry the most weight in the calculation.

## How to read this register

- **R-xx** regulatory rules: what the law or regulation requires.
- **M-xx** methodology rules: internal design decisions, with the reason for each. These are not regulation and must never be described as such.
- **C-xx** consumer protection and fair lending rules that apply when the system recommends limit changes.
- Each rule has a **Code location** and **Test** field, filled in below for this implementation.

The US capital rules are issued in parallel by three agencies. The same requirement appears in three places:

| Agency | Supervises | Capital rule |
|---|---|---|
| Federal Reserve (Regulation Q) | Bank holding companies, state member banks | 12 CFR Part 217 |
| OCC | National banks, federal savings associations | 12 CFR Part 3 |
| FDIC | State non-member banks | 12 CFR Part 324 |

Citations below give the Fed section; the OCC and FDIC equivalents use the same section number under their own part (e.g. §217.10, §3.10, §324.10) unless stated otherwise.

---

## Summary index

| ID | Rule | Used in | Code location | Test | Status |
|---|---|---|---|---|---|
| R-01 | Basic Tier 1 leverage ratio, on-balance-sheet only | Tier 1 mode | `leverage_capital.compute()` (`slr_mode == False` branch) | T-02 | OPEN |
| R-02 | Well-capitalised leverage threshold (PCA) | Display only, Leverage page | `app/pages/24_Leverage_Capital.py` | display check | OPEN |
| R-03 | SLR applies to Category I, II, III | Policy validation | `validate_policy()` V-02/V-03 | T-06 | OPEN |
| R-04 | SLR minimum 3% | SLR mode, target ratio | `leverage_capital.compute()` (`target_ratio`) | T-01 | OPEN, HIGH PRIORITY |
| R-05 | Total leverage exposure includes off-balance-sheet items | SLR mode | `leverage_capital.compute()` | T-07 | OPEN |
| R-06 | 10% CCF for unconditionally cancellable commitments in SLR | SLR mode | `leverage_capital_policy.*.json: slr_ccf_by_commitment_type.UNCONDITIONALLY_CANCELLABLE` | T-01 | OPEN, HIGH PRIORITY |
| R-07 | Other commitments use standardized-approach CCFs in SLR | SLR mode | `leverage_capital_policy.*.json: slr_ccf_by_commitment_type.NON_UCC_*` | T-03 | OPEN |
| R-08 | Definition of unconditionally cancellable commitment | Product classification | `leverage_capital_policy.*.json: product_commitment_type` | T-06 (V-07) | OPEN |
| R-09 | Risk-based capital: 0% CCF for unconditionally cancellable commitments | Contrast / caveat | `l2_lines.py` caveat text; `leverage_capital_policy.*.json: risk_based_ccf_ucc` | display check | OPEN |
| R-10 | Enhanced SLR for US GSIBs | Case A settings | `leverage_capital_policy.*.json: eslr_buffer`; `validate_policy()` V-05 | T-06 | OPEN, HIGH PRIORITY |
| R-11 | Category I to IV definitions (tailoring) | Policy validation | `validate_policy()` | T-06 | OPEN |
| R-12 | Community Bank Leverage Ratio | Validation V-04 | `validate_policy()` V-04 | T-06 | OPEN |
| R-13 | SLR averaging convention | Gap register, module docstring | `engine/core/leverage_capital.py` docstring | documentation check | OPEN |
| R-14 | Basel III leverage framework (international reference) | Background | module docstring | - | OPEN |
| R-15 | SR 11-7 model risk management | Governance | this document, verification log | - | OPEN |
| M-01 to M-07 | Methodology rules | Throughout | see below | - | Internal |
| C-01 to C-04 | Consumer protection and fair lending | L2 DECREASE | `l2_lines.py` (adverse-action gate already existed; see note under C-01) | - | OPEN |

---

## Regulatory rules

### R-01 Basic Tier 1 leverage ratio
- **Plain English:** every US bank must hold Tier 1 capital of at least 4% of its average on-balance-sheet assets. Off-balance-sheet items, including unused credit lines, are not in the denominator.
- **Requirement:** Tier 1 capital ÷ average total consolidated assets (less deductions) ≥ 4%
- **Citation:** 12 CFR 217.10 (Fed); 12 CFR 3.10 (OCC); 12 CFR 324.10 (FDIC)
- **Applies to:** all banks subject to the capital rule (SLR banks face this **and** the SLR)
- **System effect:** in Tier 1 mode, unused lines are not charged
- **Policy field:** `tier1_leverage_minimum`
- **Code location:** `engine/core/leverage_capital.py:compute()` | **Test:** T-02

### R-02 Well-capitalised leverage threshold (Prompt Corrective Action)
- **Plain English:** an insured bank needs a leverage ratio of at least 5% to be classified "well capitalised."
- **Citation:** 12 CFR 6.4 (OCC); 12 CFR 208.43 (Fed); 12 CFR 324.403 (FDIC)
- **System effect:** informational display only; not used in any calculation
- **Policy field:** `tier1_leverage_well_capitalised`
- **Code location:** `app/pages/24_Leverage_Capital.py` | **Test:** display check

### R-03 SLR applicability
- **Plain English:** only the largest banking organisations, those in Categories I, II and III, must meet the Supplementary Leverage Ratio.
- **Citation:** 12 CFR 217.10; tailoring final rule, 84 FR 59230 (November 1, 2019)
- **System effect:** basis for validation rules V-02, V-03
- **Policy field:** `slr_mode`, `bank_category`
- **Code location:** `engine/core/leverage_capital.py:validate_policy()` | **Test:** T-06

### R-04 SLR minimum
- **Plain English:** SLR banks must hold Tier 1 capital of at least 3% of total leverage exposure.
- **Requirement:** Tier 1 capital ÷ total leverage exposure ≥ 3%
- **Citation:** 12 CFR 217.10
- **Policy field:** `slr_minimum`
- **Code location:** `engine/core/leverage_capital.py:compute()` (`target_ratio`) | **Test:** T-01

### R-05 Total leverage exposure includes off-balance-sheet items
- **Plain English:** the SLR denominator adds off-balance-sheet exposures, such as unused commitments, to on-balance-sheet assets.
- **Citation:** 12 CFR 217.10 (definition of total leverage exposure); SLR final rule, 79 FR 57725 (September 26, 2014)
- **System effect:** the reason unused lines are charged in SLR mode
- **Code location:** `engine/core/leverage_capital.py:compute()` | **Test:** T-07

### R-06 10% CCF for unconditionally cancellable commitments (HIGH PRIORITY)
- **Plain English:** in the SLR, 10% of the unused amount of a commitment the bank can cancel at any time counts as exposure. Retail credit card lines are the main example.
- **Citation:** 12 CFR 217.10 (total leverage exposure); 79 FR 57725 (2014)
- **Policy field:** `slr_ccf_by_commitment_type.UNCONDITIONALLY_CANCELLABLE`
- **Code location:** `engine/config/leverage_capital_policy.*.json` | **Test:** T-01

### R-07 Other commitments use standardized-approach CCFs
- **Plain English:** in the SLR, commitments that are not unconditionally cancellable use the CCFs from the standardized approach: 20% if the original maturity is one year or less, 50% if longer.
- **Citation:** 12 CFR 217.10 (total leverage exposure, by reference); 12 CFR 217.33 (off-balance-sheet exposures)
- **Policy field:** `slr_ccf_by_commitment_type.NON_UCC_*`
- **Code location:** `engine/config/leverage_capital_policy.*.json` | **Test:** T-03

### R-08 Definition of unconditionally cancellable commitment
- **Plain English:** a commitment the bank may refuse to extend credit under at any time, with or without cause, to the extent permitted by law. Retail credit card lines are generally treated as such. Whether other products (for example HELOCs, where consumer law restricts when a line can be frozen) qualify is a legal determination.
- **Citation:** 12 CFR 217.2 (definitions)
- **System effect:** drives `product_commitment_type`; see M-05. This repo's dataset only carries undrawn commitments for `credit_card` - no HELOC/other revolving product exists in the data, so the question does not arise here, but the policy schema still requires an explicit classification rather than assuming it.
- **Code location:** `engine/config/leverage_capital_policy.*.json: product_commitment_type` | **Test:** T-06 (V-07)

### R-09 Risk-based capital: 0% CCF for unconditionally cancellable commitments
- **Plain English:** under risk-based capital, unused cancellable lines need no capital. This is why the existing L2 caveat says risk-based relief is "$0 by design."
- **Citation:** 12 CFR 217.33 (standardized approach)
- **Policy field:** `risk_based_ccf_ucc` (contrast only)
- **Code location:** `engine/levers/l2_lines.py` caveat text | **Test:** display check

### R-10 Enhanced SLR for US GSIBs (HIGH PRIORITY)
- **Plain English:** the largest US banks (GSIBs, Category I) carry an additional leverage buffer above the 3% SLR at the holding company, and historically a higher well-capitalised SLR at their bank subsidiaries.
- **Citation:** 12 CFR 217.11 (buffers); eSLR final rule, 79 FR 24528 (May 1, 2014); **2025 eSLR recalibration rulemaking: verify final rule, calibration and effective date**
- **System effect:** `eslr_buffer` must be 0 unless category is I (V-05)
- **Policy field:** `eslr_buffer`
- **Code location:** `engine/core/leverage_capital.py:validate_policy()` V-05 | **Test:** T-06

### R-11 Category definitions (tailoring)
- **Plain English:** large banking organisations are sorted by size and risk indicators. Roughly: Category I is US GSIBs; II is $700B+ or significant cross-jurisdictional activity; III is $250B+, or $100B+ with large weighted short-term wholesale funding, nonbank assets, or off-balance-sheet exposure; IV is other $100B+ organisations.
- **Citation:** 12 CFR 252.5 (Regulation YY); 12 CFR 217.2 (definitions); 84 FR 59230 (2019)
- **System effect:** `bank_category` values and validation
- **Note:** categories are based on averages over recent quarters and change with growth and mergers. A real bank's category must come from its current regulatory filings (e.g. FR Y-9C, FR Y-15).
- **Code location:** `engine/core/leverage_capital.py:validate_policy()` | **Test:** T-06

### R-12 Community Bank Leverage Ratio (CBLR)
- **Plain English:** qualifying banks under $10B may opt into a single, simpler leverage ratio instead of the full risk-based framework. It is on-balance-sheet based, so unused lines are not charged. CBLR banks are not SLR banks.
- **Citation:** 12 CFR 217.12; CBLR final rule, 84 FR 61776 (November 13, 2019). **Verify the current required ratio** (set at 9% in 2019; changes have been proposed since).
- **System effect:** validation V-04
- **Code location:** `engine/core/leverage_capital.py:validate_policy()` V-04 | **Test:** T-06

### R-13 SLR averaging convention
- **Plain English:** for SLR reporting, on-balance-sheet assets are averaged daily over the quarter and off-balance-sheet exposures are averaged over the three month-ends of the quarter.
- **Citation:** 12 CFR 217.10 (total leverage exposure)
- **System effect:** this system computes at the same customer-level, trailing-12-month grain as every other diagnostic in it (reusing `avg_undrawn_12m` from the liquidity cost diagnostic), not per-account-per-ledger-period with quarterly month-end averaging. This is a deliberate consistency choice with the rest of the engine, not a claim of regulatory reporting equivalence. See the gap register.
- **Code location:** `engine/core/leverage_capital.py` module docstring | **Test:** documentation check

### R-14 Basel III leverage ratio (international reference)
- **Plain English:** the international standard US rules are based on. It also applies a 10% CCF to unconditionally cancellable commitments in the leverage exposure measure.
- **Citation:** Basel Framework, LEV30 (exposure measurement), Basel Committee on Banking Supervision
- **System effect:** background only. US rules (R-01 to R-13) govern the calculation.

### R-15 Model risk management (SR 11-7)
- **Plain English:** supervisory guidance requiring sound development, validation, documentation, and governance of models.
- **Citation:** Federal Reserve SR Letter 11-7 (April 4, 2011); OCC Bulletin 2011-12. **Verify current status and any superseding guidance.**
- **System effect:** this document, the verification log, and the per-run audit record (`result["leverage_audit"]`) are this system's methodology documentation, gap register, and audit trail for this feature.

---

## Methodology rules (internal, not regulation)

### M-01 Diagnostic only, never blended into NEP
- **Rule:** leverage capital cost is never added to NEP, CEV scores, or any headline total.
- **Reason:** a bank's binding capital requirement is the higher of its risk-based and leverage requirements, not the sum. The system already charges risk-based capital ($0 for cards, R-09) and liquidity cost (a separate regime entirely) - adding leverage cost inside NEP would double count whenever risk-based capital is binding, and would conflate three different rulebooks into one number.
- **Test:** T-04, T-05
- **This repo has no CELTV or PLI concept** (those are from a different system than this one) - M-01's intent is carried out here against this system's actual headline figures: `trailing_12m_net_economic_profit`, `cev_score`, `cev_band`, `is_below_cost`.

### M-02 Symmetry in limit decisions
- **Rule:** L2's DECREASE shows leverage capital freed; INCREASE shows leverage capital consumed.
- **Reason:** crediting cuts without charging increases biases recommendations toward cuts.
- **Test:** T-11

### M-03 Explicit toggle
- **Rule:** `slr_mode` is set by a person (the active policy file, chosen on the Home page) and never inferred from asset size or category in code.
- **Reason:** regulatory status is a legal fact about the bank, confirmed from filings; the category field is only a cross-check (V-02, V-03).
- **Test:** T-06 (V-01)

### M-04 Drawn balances out of scope
- **Rule:** this module charges only the unused portion of commitments (`avg_undrawn_12m`).
- **Reason:** drawn balances are on-balance-sheet and already covered by existing capital logic.

### M-05 Product classification is the bank's determination
- **Rule:** each product with undrawn commitments must be classified in `product_commitment_type`. In SLR mode, an unclassified product with undrawn commitments stops the run (V-07).
- **Reason:** whether a product is unconditionally cancellable is a legal question (R-08). The system applies the classification; it does not make it. This dataset has exactly one such product (`credit_card`); `products_without_commitments` documents the rest (term loans, deposits) as explicitly not applicable.

### M-06 Eligibility
- **Rule:** undrawn = max(limit − balance, 0); this module reuses `customer_view.avg_undrawn_12m`, which already excludes charged-off accounts and floors over-limit balances at $0 (see `engine/core/customer_view.py`'s liquidity cost section, which computes the same base).
- **Test:** T-09

### M-07 No imputation
- **Rule:** missing limits or balances are excluded, never filled in with an assumption.
- **Reason:** imputed exposure would put unaudited numbers into a capital diagnostic. **Inherited scope note:** `avg_undrawn_12m` is zero-filled for customers with no card record at all (consistent with how the liquidity cost diagnostic already treats this case) - a customer with genuinely no card data reads as $0 exposure, not as a flagged gap. This mirrors an existing, already-shipped design choice rather than introducing a new one.

---

## Consumer protection and fair lending

Turning SLR mode on makes credit line decreases look more valuable. These rules apply to every DECREASE recommendation.

### C-01 Adverse action notice (ECOA / Regulation B)
- **Plain English:** an unfavourable change in the terms of an existing account, such as reducing a credit limit, is generally an adverse action that requires a notice to the customer with the principal reasons.
- **Citation:** 12 CFR 1002.2(c) (definition of adverse action); 12 CFR 1002.9 (notifications)
- **System effect:** L2's DECREASE/DECREASE_RISK_EXPOSURE actions already carry `adverse_action_notice_required = True` in the worklist (this predates the leverage feature - the gate was already in place for every DECREASE, and continues to apply identically whether SLR mode is on or off).

### C-02 Credit card limit reductions (Regulation Z)
- **Plain English:** after a card issuer reduces a credit limit, it is restricted from imposing over-limit fees or penalty rates that result from the reduction until a notice period has passed.
- **Citation:** 12 CFR 1026.9(g)(4)
- **System effect:** documented in L2's `gates` list (`"Reg B adverse action notice on any decrease"`); unchanged by this feature.

### C-03 Fair lending
- **Plain English:** credit decisions, including line reductions, must not discriminate on a prohibited basis, including through disparate impact.
- **Citation:** Equal Credit Opportunity Act, 15 U.S.C. 1691 et seq.; Regulation B, 12 CFR Part 1002
- **System effect:** the existing fairness analysis (`engine/governance/fairness.py`, four-fifths rule) runs on every DECREASE recommendation regardless of `slr_mode`, because `slr_mode` only changes the DOLLAR VALUE attached to an already-determined population - it never changes which customers are selected for DECREASE. **Scoped down from the spec:** a literal side-by-side re-run of fairness under both toggle positions in the same report was not built in this pass (see STATUS.md) since the population is provably identical either way; this note stands in for that comparison until/unless a full dual-run view is wanted.

### C-04 Reasons for decisions
- **Rule:** the system produces recommendations, not customer notices. Capital cost is an internal economic factor and is not presented as a customer-facing reason.
- **Reason:** adverse action reasons must reflect the factors actually used in a credit decision and are the bank's compliance determination. L2's `worklist()` reason strings cite behavioral evidence (utilization, spend, seasoning) - never capital cost - consistent with this rule, unchanged by this feature.

---

## Revision history

| Version | Date | Change | By |
|---|---|---|---|
| 1.0.0 | | Initial draft; all items OPEN (as supplied) | project owner |
| 1.0.1 | 2026-10-09 | Code location / Test columns filled in during implementation; C-03 scope note added | build agent |
