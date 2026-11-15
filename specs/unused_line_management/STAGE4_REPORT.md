# Stage 4 report: screen and segments

Branch `feature/unused-line-management`, base `main` `b660bb8`. 16 Nov 2026.

## Built

- `engine/unused_lines/segments.py`:
  - **Screen (system mode, answer 2):** card profit < 0, where card profit uses the measured credit
    cost, the old capital charge replaced by the new one and the new liquidity cost subtracted.
    Drawdown loss is shown beside it, not deducted. The other criteria: average utilisation < 30%,
    unused line ≥ $5,000, open ≥ 12 months, open and not charged off, no fraud-compromise card event
    in the last 2 cycles (proxy, labelled approximate). Every threshold is in config.
  - **Sensitivity toggle** `screen.include_expected_drawdown_loss` (default off), with a report of
    the extra accounts and loss it brings in.
  - **Six segments in priority order**, first match wins. The rules run on every account; LEQ comes
    from the segment (Unassigned: the measured Behavioral CCF); then the §2 costs; then the screen.
  - **Rule trace:** for every rule and screen criterion, the account's value, the threshold and
    met / not met (`met:*` columns), for the drill-down. Dormant confirmation signals (Table30
    activation, Table3 reissue due, Table12 digital sessions) are informational.
  - The **segmentation transactor rule** (≥ 10/12, a $0 statement counts as nothing due) is
    separate from the **regulatory test** (12/12, answer 5) and labelled so.
  - Summaries by segment: accounts, unused lines, carrying cost, drawdown loss, total unused-line
    cost, card profit, relationship-adjusted profit.
- The per-account file adds digital sessions, the current card's issue reason and age, interchange,
  the fixed part of cost to serve, and the peak statement balance.
- The calibration report now uses the module's own screen and segments, keeps its independent
  reading of the rules, and reports their agreement (100% on both books).

## Results (annual)

**Stress book (10k, synthetic stress data)**, 4,652 screened:

| Segment | Accounts | Share | Unused lines | Carrying cost | Drawdown loss | Total unused-line cost | Card profit | Relationship-adjusted |
|---|---|---|---|---|---|---|---|---|
| Credit-Deteriorating | 173 | 3.7% | $1.95M | $2,510 | $99,124 | $101,634 | −$14,913 | −$12,191 |
| Relationship / Premium | 618 | 13.3% | $16.75M | $21,167 | $5,947 | $27,113 | −$151,621 | $631,852 |
| Dormant | 1,497 | 32.2% | $13.66M | $18,025 | $30,282 | $48,307 | −$87,743 | −$87,334 |
| Sock-Drawer | 686 | 14.7% | $6.03M | $6,846 | $25,433 | $32,279 | −$24,725 | −$24,725 |
| Transactors | 867 | 18.6% | $17.29M | $19,212 | $9,930 | $29,142 | −$32,017 | −$32,078 |
| Unassigned | 811 | 17.4% | $11.89M | $13,444 | $22,718 | $36,162 | −$33,875 | −$33,930 |
| **Total** | **4,652** | | **$67.57M** | **$81,204** | **$193,433** | **$274,637** | **−$344,894** | **$441,594** |

Drawdown toggle on: 5,266 screened (+614), $63,901 more loss after drawdown.

**5k demo**, 890 screened: Relationship 555 (62%), Dormant 161, Unassigned 142,
Credit-Deteriorating 16, Transactors 9, Sock-Drawer 7. Total unused-line cost $20,557; card profit
−$61,296; drawdown toggle +51 accounts, $4,877.

## Calibration (stress book): 25 of 43 within ±25%

Five key metrics (answer 3): **in band:** Dormant, Relationship and Sock-Drawer shares; unused line
for all five segments; Relationship and Dormant utilisation. **Outside:** the rows below. One tuning
pass was made on them (dormant, sock-drawer and transactor lines; transactor weight); no further
calibration work.

| Segment | Metric | Observed | Reference | Reason |
|---|---|---|---|---|
| Screen | Card profit per screened account | −$74.14 | −$36.95 | The reference is the workbook's average without undrawn-line loss over all 93,000 accounts, including Credit-Deteriorating, which is profitable on that basis (+$85); the screened workbook population is −$48.45. The rest is lower engine revenue on screened accounts |
| Credit-Deteriorating | Share | 3.7% | 8.6% | **By construction:** without drawdown loss the workbook's own segment earns +$85 per account, so the system-mode screen keeps only the loss-making minority |
| Credit-Deteriorating | Balance, utilisation, revolving | $441, 3.3%, $308 | $1,500, 12.5%, $1,200 | The screen keeps the low-balance accounts (interest income makes high-balance ones profitable) |
| Credit-Deteriorating | Spend | $1,547 | $2,500 | Same selection |
| Credit-Deteriorating | PD | 9.7% | 6.0% | Same selection: the loss-makers are the higher-PD accounts |
| Relationship | Revolving balance | $11 | $500 | Generator: affluent customers pay in full |
| Sock-Drawer | Share | 14.7% | 21.5% | Some occasional users spend over $2,500 or go fully dormant |
| Sock-Drawer | Balance, utilisation, revolving | $112, 1.3%, $28 | $300, 3%, $100 | Revolving builds interest, which makes the account profitable and drops it from the screen |
| Sock-Drawer | Spend | $953 | $1,500 | The ≤ 4 months and < $2,500 rules cut off the higher spenders |
| Transactors | Share | 18.6% | 26.9% | The engine's cost to serve is about half the workbook's, so higher-spending transactors make money |
| Transactors | Balance, utilisation, spend | $1,005, 5.0%, $11,993 | $1,500, 7.5%, $18,000 | Same: the screen keeps the lower spenders |
| Unassigned | Share | 17.4% | ≤ 10% | Mostly transactor-type accounts that miss the peak-utilisation or spend rule |

## Tests run

- `audit/audit_unused_line_data_additions.py`: **74/74 passed** (byte-identity of all 197 baseline
  files including `negative_control`; engine regression; integrity on six books).
- `audit/audit_unused_line_module.py` (with the 100k bundle and per-account file): **54/54 passed**,
  including 8 new Stage 4 checks on each book: agreement with the independent reading, first match
  wins, screen criteria, drawdown toggle, summaries, thresholds from config, segmentation vs
  regulatory transactor rule, Unassigned economics.
