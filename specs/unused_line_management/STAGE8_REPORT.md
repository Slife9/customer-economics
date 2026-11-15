# Stage 8 report: full test suite

Branch `feature/unused-line-management`, base `main` `b660bb8`. 16 Nov 2026.

```
python audit/audit_unused_line_module.py --regression --bundle-100k <rebuilt 100k v2 bundle> \
    --frame-100k <its per-account parquet> --frame-100k-json <build timing>
```

**Result: 109/109 passed** (full output in `STAGE8_AUDIT_MODULE.txt`). The 100k bundle and its
per-account file were rebuilt locally, used read-only and not committed.

| Brief §7 test | Checks | Result |
|---|---|---|
| 1. Worked examples | Dormant $13.20, revolver $10.56, transactor $7.54, to the cent | Pass |
| 2. Workbook reproduction (85% / 55%) | Baseline −$9,044,043 and all 11 Dashboard items; Base +$1,329,137; 8,470 lost; all three scenarios and Base by segment: 0.0000% difference. Corrected: RWA $117,937,500, capital $1,486,012, liquidity $487,688; per-account Relationship correction (75%): baseline RWA $136.5M, Base +$1,309,742 | Pass |
| 3. §2.7 reconciliation (100k) | Brief's method within 0.6% overall, 1.7% by L2 group; the module's own figures +8.7% RWA / +6.1% carrying cost, explained by the agreed transactor test and tested (plan / promotional rule off: within 3.5%) | Pass |
| 4. Invariants | No 0% CCF (and refused in config); capital released never in an annual value; low ≤ base ≤ high; every action has a reason code; inactivity: no adverse-action notice, credit: notice + FCRA check; plan / campaign balances flip 45% → 75%; drawdown loss never in carrying cost; B6 levers out of the headline while off; protected customers get no action | Pass (both books) |
| 5. Toggles | Category and `apply_to` (liquidity only); current-rules view (read-only); scope mode B7 (population only); screen-drawdown toggle (adds accounts only); B5 (dormant accounts only); thresholds from config | Pass |
| 6. Regression | Byte-identity of all 197 baseline files across demo, negative_control (fix-branch baseline) and the three variants; engine `run_summary.json` unchanged; no change since `main` to L1–L6, L2, the ML model, NEP / CEV, suppression, routing, fairness, the six-lever app or existing generator modules | Pass |
| 7. Performance | App on the committed samples: every page on both datasets, peak 0.29 GB (AppTest), 0.42 GB (live server); 100k per-account file loads in 0.1 s at 0.30 GB; offline build of that file 143 s at 15.6 GB (recorded, offline only) | Pass |

Also checked: the segment engine agrees 100% with the calibration report's independent reading of
the rules; value types reconcile to the change in card profit; leavers keep fixed cost; the ML
model is a second opinion only (recommendations identical without it); pilot cells seeded and
stratified; year-1 timing; the three-way fairness test runs (its failures are findings, reported
in `ISSUES_FOUND.md` #10, not test failures).

Fixed during the stage (test code only): the "protected customers get no action" check looked at
numeric columns of the selection table; it now checks the action flags. The module was correct.
