# Revision, Part B: calculation corrections

17 Nov 2026, branch `feature/unused-line-management` (not pushed, merged or deployed).

Every new setting is in `engine/unused_lines/config/unused_line_assumptions.json` with its default;
nothing outside the module changed. Figures below are from `audit/unused_line_headline_figures.py`
on the committed app samples (JSON in `figures/`). Each column adds one correction to the one
before it.

## Before / after

**Stress book (100,000 customers, 91,818 card accounts)**

| | Before | B1 missing PD | + B2 account LEQ (default) | B5 alternative: workbook fixed cost |
|---|---|---|---|---|
| Screened accounts | 40,530 | 40,530 | 40,530 | 54,204 |
| Card profit (screened) | −$2,579,382 | −$2,579,382 | −$2,579,382 | −$4,656,995 |
| Carrying cost | $693,984 | $693,984 | $693,984 | $939,533 |
| Drawdown loss | $1,633,129 | $1,633,129 | **$1,473,986** | $1,921,040 |
| Base annual value | +$175,389 | +$175,389 | **+$120,339** | +$152,405 |
| Pending (B6) value | +$519,808 | +$519,808 | +$529,424 | +$529,823 |
| 1.5× stress result | +$155,257 (go) | +$155,257 | **+$107,385 (go)** | +$133,761 (go) |
| 1.5× card profit alone | −$15,752 | −$15,752 | −$15,752 | −$24,176 |

**5k demo (3,988 card accounts)**

| | Before | B1 missing PD | + B2 account LEQ (default) | B5 alternative: workbook fixed cost |
|---|---|---|---|---|
| Screened accounts | 890 | 890 | 890 | 1,011 |
| Card profit (screened) | −$61,296 | −$61,296 | −$61,296 | −$78,574 |
| Carrying cost | $10,630 | $10,630 | $10,630 | $12,326 |
| Drawdown loss | $9,926 | $9,926 | **$13,485** | $15,251 |
| Base annual value | +$817 | +$817 | **+$639** | +$597 |
| Pending (B6) value | +$4,376 | +$4,376 | +$4,429 | +$4,491 |
| 1.5× stress result | +$635 (go) | +$635 | **+$508 (go)** | +$418 (go) |

B3, B4, B6 and B7 change no figure. The default fixed-cost basis (B5) is the engine allocation, so
the default column is "+ B2"; the last column is the alternative setting.

## B1. Missing PD no longer means zero risk
- `exposure.pd_used()`: a missing PD takes the average PD of the account's rule segment
  (accounts with a PD), then the portfolio average; `pd_imputed` flags it. Setting
  `drawdown_risk.missing_pd = "segment_average"` (validated: it cannot be set to anything that
  means zero). The segment rules still use the measured PD only.
- **Imputed:** 3,543 accounts on the stress book and 426 on the demo, all of them closed or
  charged off at the reporting date. **None is screened**, so no headline figure changes.
- Shown in the drill-down's calculation trace (Part C).

## B2. Each account's measured LEQ
- **Confirmed first:** Table9 `Behavioral CCF` has the same meaning as LEQ. The generator
  (`generator/synth/capital.py`) defines `Economic EAD = drawn + undrawn × Behavioral CCF`, "the
  pre-default drawdown a cancellable line does not stop": the share of the unused line drawn before
  default. So I went ahead.
- **But it is not an account-level measurement on this data.** It is a generator parameter with two
  values: 0.42, or 0.798 for an account with a `RISK_DETERIORATION` limit event. The code uses an
  event at any time; its comment says "trailing 6 cycles". On the stress book 87,673 accounts carry
  0.42 and 602 carry 0.798. The default therefore sets LEQ to about 0.42 for every segment:
  - Credit-Deteriorating falls from 0.70 to 0.42 (drawdown loss $798k → $481k).
  - Relationship rises from 0.15 to 0.42 ($53k → $149k).
  - Transactors rise from 0.20 to 0.42 ($75k → $158k).
  - This is why the Base value falls by a third: the riskiest lines' avoided loss shrinks. Logged as
    `ISSUES_FOUND.md` #16. The switch `drawdown_risk.leq_source = "workbook_segment"` gives back the
    previous figures exactly.
  - **Recommendation:** keep the workbook LEQ as the default until the bank has a real measured
    LEQ. I followed the instruction and made `measured_account` the default.
- `exposure.leq_columns()` keeps three columns: `leq_measured`, `leq_workbook` and the `leq` in use,
  plus `leq_source`. A missing measured value falls back to the workbook segment LEQ.
- Drawdown loss by segment under both settings is in the analyst view (Part C, "Where the cost
  sits" → Details):

| Stress book, screened | Accounts | Account LEQ | Workbook LEQ |
|---|---|---|---|
| Credit-Deteriorating | 1,460 | $480,717 | $798,265 |
| Relationship / Premium | 5,513 | $148,949 | $53,191 |
| Dormant | 15,076 | $330,369 | $314,086 |
| Sock-Drawer | 6,139 | $188,884 | $224,357 |
| Transactors | 6,337 | $157,977 | $75,227 |
| Unassigned | 6,005 | $167,089 | $168,003 |
| **Total** | 40,530 | **$1,473,986** | **$1,633,129** |

## B3. Specific reason codes replace OTHER
- `treatment.reason_codes` is now one entry per code, each with its action, notice text,
  `adverse_action_notice`, `fcra_check` and `compliance_flag`. The six codes in the brief are
  mapped from the levers, and `design()` adds a `compliance_flags` column. `assumptions.validate()`
  refuses a lever whose code has no notice rule.
- **OTHER: 0% of actions** on both samples (target below 1%; the audit checks it).

| Primary reason code (stress book) | Before | After |
|---|---|---|
| OTHER | 17,549 | 0 |
| SUPPRESS_AUTO_INCREASE | – | 11,147 |
| ENGAGEMENT_CAMPAIGN | – | 6,402 |
| INACTIVITY | 11,404 | 11,208 |
| INACTIVITY_NON_REISSUE | – | 196 |
| IDLE_LINE_RIGHTSIZING | 1,790 | 1,790 |
| CREDIT_DETERIORATION | 716 | 716 |

All codes per action (an account can have several): SUPPRESS_AUTO_INCREASE 22,237;
ENGAGEMENT_CAMPAIGN 11,677; INACTIVITY 11,208; INACTIVITY_NON_REISSUE 2,954; IDLE_LINE_RIGHTSIZING
1,790; CREDIT_DETERIORATION 716. Demo: OTHER 455 → 0 (primary).

The prompt mentions 2,132 of 3,566 OTHER; that count is from an earlier, smaller sample. On the
current samples OTHER was 17,549 of 31,459 (stress book) and 455 of 614 (demo).

## B4. Card profit comparable with the main system
- Labelled "card profit under the assumed capital rules" (`exposure` docstring, guide terms, every
  page in Part C).
- `exposure.reconciliation()`, shown in the analyst view (Part C, Technical). Screened accounts on
  the stress book:

| Step | USD a year |
|---|---|
| Main engine card profit (card_net) | −$2,000,170 |
| + old capital charge inside card_net (current rules), added back | +$124,981 |
| − new capital cost (assumed capital rules) | −$489,183 |
| − liquidity cost (LCR buffer carry) | −$215,011 |
| − fixed cost difference (setting minus engine allocation) | $0 |
| = Card profit under the assumed capital rules (module) | −$2,579,382 |
| Check (module minus the sum of the steps) | $0.00 |

- **Note on the prompt's formula:** it reads "main engine card profit − old capital charge + new
  capital cost + liquidity cost = module card profit". The signs are reversed. `card_net` already
  has the old charge subtracted, so the module **adds it back** and **subtracts** the new capital and
  liquidity costs, as above. The audit checks this to the cent on both portfolios.

## B5. Fixed cost per account is a setting
- `costs.fixed_cost_basis`: `engine_allocated` (default) or `workbook_segment` (the workbook's
  $30–60 by segment; Unassigned: the five segments weighted by their account counts).
  `exposure.fixed_costs()`.
- Card profit falls by the difference. The variable contribution (card profit + fixed cost) is
  unchanged, because fixed cost stays when an account leaves. So lever values change only through
  which accounts are in scope (audit-checked).
- **Measured engine allocation per screened account:**
  - **$2.91** on the 100k stress book;
  - **$16.66** on the generated 10k stress portfolio (the "about $17" in the brief);
  - **$34.70** on the 5k demo.
- The issue stays logged (`ISSUES_FOUND.md` #11, updated).
- Base under both settings is in the analyst view (Part C, "Actions and value" → Details):
  - Stress book: +$120,339 (engine) vs +$152,405 (workbook; 54,204 screened).
  - Demo: +$639 vs +$597.

## B6. One headline basis, stated once
- Executives see one figure: annual value = change in card profit + reduction in expected drawdown
  loss. Card profit alone and relationship-adjusted values are in the analyst view only (Part C).
- `levers.robustness_statement()` generates the robustness wording from the results. Both samples
  give: "Passes at 1.5x on value including reduced risk; card profit alone is negative already at
  1x". Card profit alone is −$9,609 at 1×, so "turns negative at 1.5×" would not be true.

## B7. Methodology note on balances
In `docs/UNUSED_LINE_METHODOLOGY.md` (per-account section) and the `exposure.py` docstring:
balances are measured after the month's payment. That is right for regulatory exposure and
slightly overstates a pay-in-full customer's unused line.

## Files changed
- **Engine:**
  - `engine/unused_lines/config/unused_line_assumptions.json`: `drawdown_risk.missing_pd`,
    `leq_source`, `costs`, `treatment.reason_codes`, `other_max_share_of_actions`, `reason_by_lever`,
    value types.
  - `assumptions.py`: validation of the new settings.
  - `exposure.py`: `pd_used`, `leq_columns`, `fixed_costs`, `reconciliation`, B7 note.
  - `segments.py`: LEQ via `leq_columns`.
  - `levers.py`: PD in use, `robustness_statement`.
  - `treatment.py`: notice rules per code, `compliance_flags`.
- **Tests:** `audit/audit_unused_line_module.py`:
  - new section 13 (B1, B2, B4, B5);
  - B3 and B6 checks;
  - drawdown invariant on the PD in use.
- **Docs:** methodology, `DECISIONS.md`, `ISSUES_FOUND.md` (#10, #11, #15, #16, #17), evaluation
  guide figures.

## Tests run
`python audit/audit_unused_line_module.py --regression --bundle-100k … --frame-100k …
--frame-100k-json …`: **120/120 PASSED**. Log: `REVISION_B_AUDIT.txt`.
- **Unchanged checks still pass:**
  - Worked examples ($13.20 / $10.56 / $7.54).
  - Workbook reproduction (±1%; Base +$1,329,137, 8,470 accounts lost).
  - §2.7 cross-checks.
  - Byte identity of every existing generator profile (74/74).
  - Engine regression.
- **New checks:** B1, B2, B3 (OTHER 0.00%), B4 (to the cent), B5 and B6 on both generated portfolios.
- **App:** every existing page on both datasets; peak 0.63 GB.
