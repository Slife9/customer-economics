# Revision, Part A: the ML credit-limit model removed from the module

17 Nov 2026, branch `feature/unused-line-management` (not pushed, merged or deployed).

**Decision B8 is final: the ML model plays no role in the unused-line module.**

## What changed

| File | Change |
|---|---|
| `engine/unused_lines/treatment.py` | Removed the ML action lists, `ml_rules_text()`, `agreement()`, the `ml` argument of `design()` and the four ML columns (`ml_action`, `ml_primary_reason`, `ml_recommended_limit`, `ml_agreement`). Fairness now runs on the module's own actions only (`FAIRNESS_TESTS`): decreases and closures, and increases if the module ever produces any (it produces none, and says so). Metros with fewer selected accounts than the configured minimum show **insufficient sample** instead of pass / fail |
| `engine/unused_lines/config/unused_line_assumptions.json` | Removed `ml_model_role`; added `treatment.fairness.min_selected_per_group` (default **30**) |
| `unused_lines_app/build_sample.py` | The engine view no longer keeps ML columns (docstring updated) |
| `samples/unused_lines/{stress,demo}/engine_view.parquet`, `meta.json` | ML columns dropped from the per-account sample files (the other columns unchanged); file sizes updated |
| `unused_lines_app/lib/state.py` | Treatment and fairness called without ML |
| `unused_lines_app/pages/10_Regulatory.py` | ML fairness tabs and the ML rules expander removed; fairness table shows the status column |
| `unused_lines_app/pages/60_Customers.py` | ML band and the ML line in the review notes removed |
| `unused_lines_app/pages/40_Levers.py`, `70_Data.py` | ML wording removed |
| `audit/audit_unused_line_module.py` | ML second-opinion and agreement checks replaced by: no ML column in the recommendations; fairness on module actions with "insufficient sample" below the minimum; guardrail that no file in `engine/unused_lines/` or `unused_lines_app/` reads the ML model |
| `audit/unused_line_headline_figures.py` (new) | Headline figures on the committed samples, used for every before / after in this revision |
| Docs | `docs/UNUSED_LINE_METHODOLOGY.md`, `ARCHITECTURE.md` §8b, `STATUS.md`, `EVALUATION_GUIDE.md`, `DECISIONS.md` (B8 entry), `OPEN_DECISIONS.md` (B8 decided) |

`engine/ml/` is not modified or deleted; the module simply stops reading it. Historical stage
reports (`STAGE1`–`STAGE9`) and the original brief are left as written: they record what was
built at the time.

## Recommendations and values are unchanged

- Headline figures on both committed samples are **identical** before and after
  (`figures/0_before.json` = `figures/A_after_ml_removal.json`, compared as JSON).
- Every per-account recommendation is **identical**: `design()` from the previous commit and the new
  one were run on the same inputs; every non-ML column matches exactly on all 40,141 stress-book
  rows and 880 demo rows; the only difference is the four ML columns.

| | Stress book (100k customers) | 5k demo |
|---|---|---|
| Screened accounts | 40,530 | 890 |
| Base annual value | +$175,389 | +$817 |
| Pending (B6) | +$519,808 | +$4,376 |
| 1.5× stress | +$155,257 | +$635 |

## Fairness, now on the module's own actions only

| | Stress book | 5k demo |
|---|---|---|
| Decreases and closures selected | 13,714 | 157 |
| Metros failing four-fifths | 2 (Albuquerque, Birmingham) | 0 |
| Metros passing | 68 | 0 |
| Insufficient sample (< 30 selected, or < 30 accounts) | 6 | 76 (every metro) |
| Increases | none produced, so no test | none |

Before, the same test reported 6 of 76 stress-book metros failing for decreases and closures; four
of those had fewer than 30 selected accounts and are now "insufficient sample".

One methodological point to note for the fair-lending review (not changed): the system's test
treats "selected" as the outcome compared, so a metro **fails when it receives fewer** decreases
than the population. For adverse actions the usual concern is the opposite (a group receiving
**more**). The test function belongs to the fairness module and is used as it is.

## Tests run

`python audit/audit_unused_line_module.py` (generates the demo and `unused_line_stress` portfolios,
then runs every check and every app page): **102/102 PASSED**. Log: `REVISION_A_AUDIT.txt`.

- New: "the ML credit-limit model plays no part (B8)" on both portfolios; the guardrail "the module
  and its app never read the ML credit-limit model" (24 source files scanned, none).
- Fairness on the generated stress portfolio (10k customers): 15 metros pass, 0 fail, 61
  insufficient sample (1,401 selected); demo: 76 insufficient sample.
- App: every page on both datasets, peak 0.61 GB.
- Not run in this part: `--regression` (generator byte identity; Part A changes no generator code) and
  the 100k cross-check inputs (not affected by this change). Both are run after Part B.
