# STATUS: Pre-computed results bundle

Built so the hosted Streamlit app (2 GB instance) can show a large portfolio
without re-running the engine on it or accepting a multi-gigabyte upload.
Additive only — no engine calculation, threshold, routing rule, suppression
rule, fairness test, negative-control logic, or ML logic was changed. See
`ARCHITECTURE.md` §8a for the full design and format.

## What was built

- **`engine/core/bundle_schema.py`** (new) — the single source of truth for
  the bundle format, shared by the writer and the loader: schema version,
  size/tolerance constants, file-name constants, `LeverStub`, and
  `compute_headline_totals()` (used both when writing the manifest and when
  validating a loaded bundle, so the two can never compute it differently).
- **`engine/export_bundle.py`** (new) — `python -m engine.export_bundle
  --data <dir> [--compare-to <dir>] --out <bundle.zip>`. Calls
  `engine.run.build_pipeline()` and, when `--compare-to` is given, the
  existing `negative_control` gate logic — no new calculation anywhere in
  this file. Writes `manifest.json` (provenance, leverage policy name,
  customer/cycle counts, per-file SHA-256 + row count, headline totals) plus
  Parquet tables and small JSON objects into a zip.
- **`app/lib/results_bundle.py`** (new) — `load_bundle_from_bytes()`:
  validates (manifest/schema version, per-file hash + row count, path
  traversal, max uncompressed size, headline-total reconciliation within
  tolerance) then reconstructs a `result` dict pages can read with no
  changes, using real `SuppressedPopulation`/`SizeResult` constructors (never
  pickle/joblib). Exposes `BundleTableUnavailable` for the few raw-table
  dependencies a bundle doesn't carry.
- **`app/Home.py`** (modified) — sidebar "Load pre-computed results (.zip)"
  option below the existing upload/sample buttons; on load, shows the
  bundle's metadata (file name, size, export timestamp, leverage policy,
  data source) in an info panel; wires the bundle's own gate report (if any)
  into `st.session_state["gate_report"]`, exactly like the sample-portfolio
  path already does for a live-run gate.
- **`app/pages/10_Portfolio_Economics.py`** and
  **`app/pages/20_Levers_and_Strategy.py`** (modified) — the handful of
  places that read a raw portfolio table (effective-interchange-rate
  denominator; the customer drill-down's transaction and per-activity
  cost-to-serve tabs) now catch `BundleTableUnavailable` and show a plain
  message instead of letting an exception reach the page. A live engine run
  never raises here, so these pages are byte-for-byte unchanged on that path.
- **`audit/audit_results_bundle.py`** (new) — equivalence test, same
  print/assert style as every other `audit/*.py` script. Runs the pipeline
  directly on the bundled demo + its negative control, exports a bundle from
  the same two portfolios, loads it back, and asserts every page-visible
  value matches.
- **`app/requirements.txt`** — added `pyarrow==23.0.0` (previously absent;
  confirmed installed in the dev environment at the same version already).
- **`ARCHITECTURE.md`**, **`README.md`**, **`app/README.md`** — documented
  (see ARCHITECTURE.md §8a for the full design).

## Measurements (actually run, this session)

All on one Windows development machine (32 GB RAM). "5k" is the bundled demo
portfolio (`generator/out/demo`, 5,000 generated customers); "50k" is a
freshly generated 50,000-customer, 36-cycle portfolio (profile `demo`, seed
`20260921`) used only for this measurement, matching the 152s/2.8GB
generation benchmark already documented in `ARCHITECTURE.md` §9.

| | 5k (4,856 post-suppression) | 50k (48,508 post-suppression) |
|---|---|---|
| `build_pipeline()` peak RSS | 601.5 MB | 7,098.0 MB (~7.0 GB) |
| Export time (no control) | 12.2 s | 109.8 s |
| Bundle size | 10.46 MB | **94.28 MB** |
| Bundle load time | 0.31 s | 2.29 s |
| Load peak RSS (whole process) | 322.7 MB | **1,547.6 MB** |

The 50k engine peak (~7.0 GB) is notably **higher** than this project's own
prior ~6 GB linear-extrapolation estimate — confirming the bundle approach is
necessary, not just convenient, at this scale. Bundle size at 50k (94 MB)
comes in well under the <200 MB target. Load peak RSS (1.55 GB) fits a 2 GB
hosted instance with roughly 500 MB of headroom above the load itself —
enough for Streamlit and the rest of the app's own baseline, but not a large
margin; see Limitations below.

The 5k demo + its negative control (two pipeline runs) exports a 10.43 MB
bundle in 17.7 s and loads it in 0.70 s (measured inside
`audit/audit_results_bundle.py`'s own run, reported below).

## Equivalence test output (actually run)

```
python audit/audit_results_bundle.py
```

```
export time (demo + control): 17.7s
bundle size: 10.43 MB
load time: 0.70s

77/77 CHECKS PASSED
```

Covers: customer/below-cost/suppressed counts, portfolio NEP and total loss,
CEV-band distribution, routing summary (index order, customer counts, loss
amounts), all six levers' `SizeResult` fields and `.gates`, all six
worklists' row counts/action distributions/membership, both fairness tables
(score and treatment, selection rates and pass/fail), ML action counts and
ML treatment fairness, the full 9-column negative-control gate report
(status, driver ratio, value ratio), and the manifest's own reconciliation
totals. Exact equality for counts/strings, tolerance (≤$0.01 or ≤1e-4 on
ratios) for floats.

## Known limitations

- **`ml_fairness["score_fairness"]`, `["score_fairness_by_product_tier"]`,
  and `["score_any_failure"]` are not carried** in the bundle and come back
  `None` on a bundle-loaded result. A full grep of `app/pages/25_ML_Credit_Limit.py`
  confirms only `proxy_method`, `treatment_fairness`, and
  `treatment_any_failure` are ever read — `score_fairness` would in any case
  be numerically identical to the non-ML `fairness["score_fairness"]` (both
  score every customer by `cev_band` alone, independent of any worklist), so
  nothing is lost that a page displays.
- **`result["suppressed"].frame` on a bundle-loaded result is the
  post-routing `customer_view`, not the original pre-routing frame** the
  live engine would have produced. No page or prior audit reads `.frame`
  (only `.suppressed`), so this is unobservable from the UI — documented
  here rather than silently relied upon.
- **`result["leverage_policy"]`, `["leverage_warnings"]`, `["leverage_audit"]`,
  `["populations"]` come back as empty placeholders.** Confirmed by grep
  that no page reads any of these on a live result either (only
  `pipeline_runner.run_negative_control_gate` touches `populations`, and
  that function is never called against a bundle-loaded result — the bundle
  carries the finished gate instead). The leverage policy *name* a bundle
  was produced under is shown in the app's info panel from the manifest.
- **The per-customer transaction drill-down and per-activity cost-to-serve
  breakdown are unavailable** on a bundle-loaded result (no raw portfolio
  tables in the bundle, by design) — both show a plain message. Everything
  else on `20_Levers_and_Strategy.py`'s drill-down (the monthly P&L,
  full ledger view, and CSV exports) still works, since `ledger["card"]` is
  in the bundle.
- **~500 MB of load-time headroom on a 2 GB instance at 50k customers** is
  not a large margin once Streamlit's own baseline and any concurrent
  session are accounted for — this was measured as a standalone Python
  process, not inside the actual hosted Streamlit runtime. A portfolio
  meaningfully larger than 50,000 customers has not been measured and may
  need either a tighter table selection or a larger hosting tier.
- **Schema versioning is all-or-nothing**: `results_bundle.py` requires an
  exact schema-version match and refuses anything else outright. There is no
  migration path yet for an older bundle against a newer app build.
