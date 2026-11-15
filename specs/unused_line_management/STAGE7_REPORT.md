# Stage 7 report: app pages and customer drill-down

Branch `feature/unused-line-management`, base `main` `b660bb8`. 16 Nov 2026.

## Built

Standalone app `unused_lines_app/`, mirroring the L1 Rewards app (`rewards_app/` on
`feature/l1-rewards-system` `495b0ec`: `lib/style.py` copied and adapted, `lib/state.py` adapted,
`Home.py` navigation pattern; copied, not merged, noted in each file).

    streamlit run unused_lines_app/Home.py --theme.baseFontSize 18

| Page | Content |
|---|---|
| Overview | Today's measured KPIs (screened accounts, card profit, unused lines, carrying cost, drawdown loss); scenario KPIs; capital released one-time; stress go/no-go; pending-approval and extra-lever subtotals apart; key takeaways; two charts |
| Regulatory settings | Category toggles (session only); every parameter with its value type; the three worked examples step by step; read-only current US rules comparison (incl. SLR); fairness, three ways, failures flagged prominently; the ML model's rules |
| Segments | Screen and the six rules with their data mapping (exact / approximate / new data); counts and economics by segment; drawdown sensitivity; mix vs the workbook; what each segment is |
| Scenario dashboard | Scenario and stress multiplier; by lever (workbook / extra / pending) and by segment; year 1 vs full annual value; capital released apart; stress chart and go/no-go; workbook-reproduction panel |
| Levers & assumptions | Editable in session only, labelled "exploration only": B5, B6, B7, the drawdown toggle, regulatory and business parameters, cut rules, pilot share, scenario lever table, responses and LEQ; reset |
| Lever guide & regulation | Each lever with status, reason code, compliance column and timing column; notice rules; cut rules; value-type key |
| Customer drill-down | Typical / borderline / review-together examples per segment or any account; profile; exposure and RWA trace with every formula; transactor test month by month; screen and segment rules met / not met with value and threshold; recommendation, reason code, notices, pilot cell; ML view and agreement; other worklists; downloadable review notes ("not an approval record") |
| Datasets & calibration | The dataset in use, build time, memory and machine; data sources and what is synthetic; the calibration report; building your own dataset offline |

Every page carries the assumption label and the value-type legend; the stress book carries the
"synthetic stress data" label. Datasets: stress book (default) and the 5k demo, in the sidebar.

**Protected customers:** while building the guide I found the module had not applied the system's
suppression. It now does, before anything else: the sample records the engine's suppressed
customers (stress book 107: SCRA 51, accommodation plan 30, hardship 26), and they are outside the
lever scope in both scope modes. The Base headline on the stress book moves from +$22,366 to
+$22,239 as a result.

## Samples (committed; the app loads only these)

`python -m unused_lines_app.build_sample --data <portfolio> --name <name> --label <label>`

| Dataset | Customers | Card accounts | Files | Build time | Build peak memory |
|---|---|---|---|---|---|
| Stress book (`unused_line_stress`, seed 20260921) | 10,000 | 9,184 | 2.6 MB | 35 s | 2.35 GB |
| 5k demo (`demo`, seed 20260921) | 5,000 | 3,988 | 1.2 MB | 16 s | 0.91 GB |

Proposed stress book size: **10,000 customers** (the profile's default): 2.6 MB on disk and about
0.3–0.4 GB at runtime, comfortably under the 2 GB limit.

Machine: Windows Server (10.0.26200), 4 CPUs, 34.4 GB RAM, Python 3.13.12.

## Tests run

- `audit/audit_unused_line_module.py` section 11: samples present; all 8 pages on both datasets
  without an exception (16 runs, slowest 1.7 s); peak **0.29 GB** in one process.
- Live server (`streamlit run`, all pages, both datasets): peak **0.42 GB**.
- Checked in the browser: Overview and Customer drill-down content end to end.
