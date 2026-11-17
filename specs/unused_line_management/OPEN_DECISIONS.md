# Open decisions (pending with the boss) and the default to build meanwhile

| # | Decision | Default to build | How to build it |
|---|---|---|---|
| B5 | Dormant zero-balance cards: transactor (45%) or not (75%)? | **75%** | Config `risk_weight_dormant_zero_balance`; one setting |
| B6 | Are dormant right-sizing and dormant closures (after failed reactivation) allowed? | **Off** in the default results | Implement both levers fully behind flags `dormant_rightsizing_enabled` and `dormant_closure_enabled`; always show their value separately as "pending approval" |
| B7 | Scope: unprofitable low-use accounts only (workbook) or full line management incl. increases (L2)? | **Workbook scope** for the module | `scope_mode` toggle; L2 increase valuation stays as it is in the six-strategy view |
| B8 | Role of the ML credit-limit model | **Decided (17 Nov 2026): the ML model is not used in this module.** No agreement flag, no ML columns, no ML fairness test | Removed: `ml_model_role` and every ML read in `engine/unused_lines/` and `unused_lines_app/`; `engine/ml/` itself is unchanged |
| B4 | Capital ratio, cost of equity | 10.5% / 12% | Config; labelled as business assumptions |
| D | Base branch and dataset | Ask at Stage 1 | Build and test on the 100k results bundle and the 5k demo; a dedicated "unused line stress book" may be proposed, like the reward stress book |

When a decision arrives, it should need **only a config change**, not code changes.
