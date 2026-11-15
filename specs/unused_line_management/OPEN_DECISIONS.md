# Open decisions (pending with the boss) and the default to build meanwhile

| # | Decision | Default to build | How to build it |
|---|---|---|---|
| B5 | Dormant zero-balance cards: transactor (45%) or not (75%)? | **75%** | Config `risk_weight_dormant_zero_balance`; one setting |
| B6 | Are dormant right-sizing and dormant closures (after failed reactivation) allowed? | **Off** in the default results | Implement both levers fully behind flags `dormant_rightsizing_enabled` and `dormant_closure_enabled`; always show their value separately as "pending approval" |
| B7 | Scope: unprofitable low-use accounts only (workbook) or full line management incl. increases (L2)? | **Workbook scope** for the module | `scope_mode` toggle; L2 increase valuation stays as it is in the six-strategy view |
| B8 | Role of the ML credit-limit model | **Second opinion only** (shown in the drill-down with an agreement flag; not a decision input) | `ml_model_role`; note the ML fairness flag in 5 metro areas on every page that shows ML output |
| B4 | Capital ratio, cost of equity | 10.5% / 12% | Config; labelled as business assumptions |
| D | Base branch and dataset | Ask at Stage 1 | Build and test on the 100k results bundle and the 5k demo; a dedicated "unused line stress book" may be proposed, like the reward stress book |

When a decision arrives, it should need **only a config change**, not code changes.
