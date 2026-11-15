# Stage 3 report: stress profile, regulatory settings and the account cost layer

Branch `feature/unused-line-management`, base `main` `b660bb8`. Run 15 Nov 2026.

## What was built

**1. `unused_line_stress` generator profile** (answer 9): synthetic stress data, new profile only.
See `DATA_ADDITIONS.md`. Calibration against the workbook: `CALIBRATION_unused_line_stress.csv`.

**2. Regulatory settings** (`engine/unused_lines/config/`)
- `unused_line_assumptions.json`: the handover file with the `read_from_workbook` placeholders
  filled (LEQ by segment, segment rules), answers 3, 5 and 7 encoded, value types listed, and two
  additions to confirm (`bank_profile.bank_category`, `screen.profit_basis`).
- `workbook_model.json`: extracted from the workbook by `extract_workbook.py` (sha256 recorded):
  segment inputs, portfolio inputs, capital regimes, the three scenarios' levers, Dashboard figures.
- `assumptions.py` loads and validates both. It refuses a 0% CCF, a lifetime PD basis or a missing
  segment, and applies overrides in session only.

**3. Per-account file** (`engine/unused_lines/data.py`): one row per card account, trailing 12
cycles, from the engine's card ledger (read only) and the published tables. Saved as one parquet
file (100k: 9.1 MB).

**4. Account exposure and cost layer** (`engine/unused_lines/exposure.py`)
- Transactor test per account (answer 5) and the $1M aggregate test give the risk weight and its
  reason.
- Exposure, RWA, capital (stock), capital cost, HQLA, liquidity cost, drawdown loss (annual PD).
- Three separate columns: **carrying cost** (capital on the unused part + liquidity), **drawdown
  loss**, **total unused-line cost** (answer 3).
- Card profit = `card_net` with the old capital charge **replaced** and liquidity subtracted;
  measured credit cost kept; drawdown loss beside it (answer 4).
- Current-rules comparison (read-only), worked examples through the same formulas, and the
  workbook-reproduction baseline.

## Tests actually run

| Audit | Result |
|---|---|
| `audit/audit_unused_line_data_additions.py` | **74/74 passed** (`STAGE3_AUDIT_DATA.txt`) |
| `audit/audit_unused_line_module.py` with the 100k bundle and per-account file | **38/38 passed** (`STAGE3_AUDIT_MODULE.txt`) |

Byte-identity: all **197** baseline files identical for demo, negative_control, transactor_heavy,
subprime_heavy and premium_heavy (plus validators and the circularity report); only Table29 and
Table30 added. The engine regression matches `run_summary.json`; the one `policy_sha256` difference
is line endings only (checked: same file content).

Module: worked examples to the cent; workbook baseline at 85% / 55% exact (0.0000%) on all 11
Dashboard items and by segment; corrected baseline $117,937,500 RWA, $1,486,012 capital cost,
$487,688 liquidity; invariants and toggles on the 5k demo and the stress book.

## §2.7 on the rebuilt 100k bundle (×5)

| | Brief | Brief's method | Module (own test) |
|---|---|---|---|
| Unused lines | $2.69B | $2,689M | $2,716M (+1.0%) |
| RWA from unused lines | $165.8M | $166.7M | $180.3M (+8.7%) |
| Capital cost | $2.09M | $2.10M | $2.27M (+8.7%) |
| HQLA | $134.5M | $134.5M | $135.8M (+1.0%) |
| Liquidity cost | $1.01M | $1.01M | $1.02M (+0.8%) |
| **Carrying cost** | **$3.10M** | **$3.11M** | **$3.29M (+6.1%)** |
| Transactor share | 27% | 26.1% | 16.5% |

By L2 group (brief's method), carrying cost and card profit after it are within 1.7% of the brief
(Dormant $1.163M / −$0.81M, Idle $0.473M / −$4.04M, Healthy $0.907M / $9.51M, Stretched
$0.098M / $8.39M). The Stage 1 card-profit gaps were 50k sampling.

The module's own figures are higher because its transactor test is the agreed one: plan,
promotional and BT balances disqualify (26.8% of accounts), which the account-type label in §2.7
ignores. Tested: with that rule off, the transactor share is 29.6% and every figure is within 3.5%.

## Module on both books (open accounts, annual)

| | 5k demo | Stress book 10k |
|---|---|---|
| Open card accounts | 3,559 | 8,811 |
| Unused lines | $27.2M | $126.0M |
| Carrying cost | $32,818 | $152,655 |
| Drawdown loss | $62,506 | $414,027 |
| Total unused-line cost | $95,324 | $566,682 |
| Card profit (engine `card_net`) | $136,097 | $63,672 |
| Card profit (module) | $268,618 | $161,301 |
| Transactor share (45%) | 18.5% | 23.6% |
| Screened (workbook screen) | 948 | 5,836 |

Card profit rises when the old capital charge is replaced: the engine's charge (Table9, current
rules) is larger than the §2 charge on drawn balances.

## Stress book calibration

25 of 43 metrics within ±25% (demo: 16). Screened mix: Dormant 31.8% (32%), Transactors 17.3%
(27%), Sock-Drawer 16.6% (22%), Relationship 12.0% (11%), Credit-Deteriorating 5.5% (9%),
Unassigned 16.9% (≤ 10%). Card profit less drawdown loss −$114.92 per screened account (−$97.25).

Outside and why:
- **Transactors** (share, spend $12.8k vs $18k, balance, utilisation): the engine's cost to serve
  is about half the workbook's ($50 vs $100 a year), so a transactor spending $18k makes money in
  the engine and the screen keeps the lower spenders. The workbook's own transactor sits at its
  peak-utilisation limit (peak < 15% needs the top month under 2× the average).
- **Unassigned 16.9%**: mostly transactor-archetype accounts that miss the peak or spend rule.
- **Credit-Deteriorating** (share, balance, revolving, PD 8.9% vs 6%): in the generator, balances
  build with spend, and lower payment discipline raises PD faster than it builds a revolving
  balance.
- **Dormant line** $10.4k vs $8k: accounts of other archetypes that stop using the card (the
  generator's own 8% dormancy floor) bring their larger lines.
- **Sock-Drawer** balances and spend, **Relationship** revolving balance: low, as above.
- **Card profit before drawdown loss** −$63.65 vs −$36.95 (the after-drawdown row is within band).

## Performance

- 100k per-account file from the raw portfolio: 131 s, **peak 15.6 GB**. An offline step (it loads
  every raw table through the engine's ledger); to be slimmed when the sample is built (Stage 7).
- Loading that file with the cost layer, fresh process: 0.2 s, **peak 0.30 GB** (the app's path).
- 100k portfolio generation 357 s; bundle export 197 s (rebuilt locally, not committed).
