# Stage 5 report: levers, customer response, scenarios, stress test

Branch `feature/unused-line-management`, base `main` `b660bb8`. 16 Nov 2026.

## Built

- `engine/unused_lines/workbook.py`: **workbook-reproduction mode**, the Calc sheets formula for
  formula on the workbook's segment inputs (closures first; two cohorts; campaign on both; fixed
  cost constant; the multiplier scales attrition and spend loss only). Original 85% / 55% weights
  by default; any weights as an option.
- `engine/unused_lines/levers.py`: **system mode** (default), per account, expected values:
  - **Workbook levers:** line decrease with floor (sock-drawer, relationship), risk-based decrease
    (credit-deteriorating, PD uplift), dormant right-sizing (B6), transactor right-sizing (kept to
    show its effect), dormant closure after failed reactivation (B6; inactivity only, ≥ 24 months),
    reactivation / engagement campaign.
  - **Sizing** (config `levers.system_mode`): Lever Guide targets (3.5× peak statement balance;
    transactors 1.5× peak, at least $5,000; deteriorating balance + 20%); new line ≥ max($500,
    balance × 1.2); cut ≤ 25% per review (one review in year 1), ≥ 15% and ≥ $500 or no cut.
  - **Selection:** the workbook's share of each segment; decreases on the largest unused lines
    (deteriorating: highest PD); campaigns in a seeded random order (a larger share targets a
    superset); closures on the longest inactive.
  - **Response:** attrition, spend loss and PD uplift by segment from the workbook, capped at 1,
    × the stress multiplier; response rate ÷ the multiplier (configurable). Leavers lose variable
    contribution + relationship profit; fixed cost stays. A campaign balance moves a 45% account to
    75%.
  - **Extra levers** (assumption-based; not in the reference workbook), always a separate
    subtotal: suppress automatic increases (Table20, next year's increase avoided × carrying cost
    and drawdown loss per $ of line); non-reissue of expired dormant cards (B6; Table3 reissue cost
    + the line closed at expiry; never double-counted with closures).
  - **Outputs** per scenario, segment and lever: change in card profit and relationship-adjusted
    profit, accounts leaving, unused lines removed, RWA change, carrying cost and drawdown loss
    before and after, value by type (avoided loss / cost saving / revenue / lost profit). Capital
    released is a one-time figure, never in an annual value. B6 levers are valued and shown as
    "pending approval" while their flag is off.
  - **Headline annual value** = change in card profit + reduction in expected drawdown loss
    (drawdown loss sits beside profit in the baseline; avoiding it is the main benefit of a cut).
    Both parts are always shown.
- Scope mode (B7): workbook scope (screened accounts) or full line management (every open,
  seasoned account); L2's increase valuation is not duplicated.

## Results

**Workbook reproduction (85% / 55%)**, exact to the cent: Conservative +$442,665 / 3,434 lost /
$527,305 released; Base +$1,329,137 / 8,470 / $1,422,889; Aggressive +$2,954,664 / 15,048 /
$2,972,904; Base by segment exact. Corrected weights: Relationship at 45%, baseline RWA $117.9M and
Base +$1,307,682 (capital released $1,244,094); Relationship at 75% (the per-account test puts most
revolving relationship accounts there), baseline RWA $136.5M and Base +$1,309,742.

**System mode, stress book (Base)**, annual:

| Lever | Targeted | Leaving | Unused removed | Δ card profit | Δ drawdown loss | Headline | Capital released (one-time) | Status |
|---|---|---|---|---|---|---|---|---|
| Line decrease with floor | 203 | 13 | $1.27M | +$2,564 | −$2,958 | +$5,522 | $8,929 | headline |
| Risk-based decrease | 86 | 3 | $0.29M | −$506 | −$19,750 | +$19,245 | $2,357 | headline |
| Transactor right-sizing | 130 | 10 | $1.23M | +$1,123 | −$662 | +$1,785 | $7,821 | headline* |
| Engagement campaign | 1,283 | 0 | $0.05M | −$4,322 | −$102 | −$4,220 | −$4,896 | headline |
| Dormant right-sizing | 748 | 15 | $2.46M | +$3,662 | −$4,734 | +$8,396 | $19,358 | pending approval |
| Dormant closure | 374 | 374 | $2.75M | +$15,660 | −$7,501 | +$23,161 | $21,658 | pending approval |
| Suppress automatic increases | 2,560 | 0 | $7.83M | +$9,382 | −$15,885 | +$25,267 | – | extra |
| Non-reissue, expired dormant | 330 | 330 | $3.01M | +$14,684 | −$6,737 | +$21,420 | $23,728 | extra, pending approval |

Scenario headline (workbook levers): Conservative +$16,173, Base +$22,366, Aggressive +$27,262.
Interaction between levers: $35. Stress test (Base): 1× +$22,366; 1.25× +$20,963; **1.5× +$19,822
(go)**; 1.75× +$18,845; 2× +$17,982. At 1.5× the change in card profit alone is −$1,929: the value
is the avoided drawdown loss.

**5k demo (Base):** headline +$798, capital released $1,300, pending approval +$4,382, extra
+$2,594; 1.5× +$618 (go).

\* **Transactor right-sizing does not lose money here**, unlike the workbook (−$7,554). The engine
allocates only $16.70 per account of cost to serve as fixed (workbook $60), so screened transactors
have a negative variable contribution (−$27.50; workbook +$25.70): a cut that makes some leave
removes a loss, and the capital and liquidity saving exceeds the small spend loss. It stays out of
recommendations (config `transactor_rightsizing_in_recommendations: false`).

## Tests run

`audit/audit_unused_line_module.py` sections 8 and 9 on the stress book and the 5k demo: all pass
(low ≤ base ≤ high; capital released never in an annual value; value types reconcile; cut rules;
closures and B6; the 45% → 75% flip; fixed cost stays; extra levers apart; scope mode; stress
test and go/no-go). Full run with the 100k checks: `STAGE5_AUDIT_MODULE.txt`.

## Open point (no stop: interpretation, results unchanged either way)

The go/no-go rule "Base must still improve profit at 1.5×" passes on the headline (card profit +
avoided drawdown loss) and fails on card profit alone (−$1,929). The module reports both; the
headline basis is set in config (`levers.system_mode.headline_value`).
