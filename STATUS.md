# STATUS: Lever valuation rebuild (branch `feature/lever-valuation-rebuild`)

This branch implements `specs/lever_valuation_rebuild/SPEC_lever_valuation_rebuild.md`
(Part A) and is followed on the same branch by per-lever pages (Part B). It
is not merged to `main`; merging happens only after review and
certification. The full method is in `docs/LEVER_METHODOLOGY.md`.

## Part A: valuation rebuild (done)

| Stage | Commit | What |
|---|---|---|
| A1 audit | (report only) | Located sizing, its consumers and the gate. The reference reproduces `expected_values.json` exactly on our fixtures |
| A2 | `2c24685` | `engine/config/lever_assumptions.json`, its loader, and the extended `SizeResult` |
| A3 | `a067fac` | Corrected L1–L6 valuation; the gate reads the driver-linked value |
| A4 | `4aad7c5`, `88101dc` | `audit/audit_lever_estimates.py`; bundle schema v2 brought forward for the 100k fixture; the L4 tolerance rule |
| A5 | `08d73ce` | Population fixes (L3 first-year, L5 12-cycle closure signal); regenerated expectations |
| A6 | `a4ccf68` | Portfolio summary in `run_summary.json`; the leakage register carries scenarios; minimal scenario display |
| A7 | this commit | `docs/LEVER_METHODOLOGY.md`, ARCHITECTURE.md, this file |

**Acceptance, as run:** `python audit/audit_lever_estimates.py` gives
**213/213 checks passing**, on the 5k demo (full pipeline, Tier 1) and the
100k v2 bundle (Case A).
- L1, L2, L3, L5 and L6 are within 0.5% of the reference in every scenario,
  component and extra.
- L4 is within ±15%, judged on gross for totals.
- All invariants pass, every assumption moves the output, and the gate
  verdict is the same under low, base and high.

**Corrected values, base scenario** (portfolio total = L1+L2+L3+L4+L6;
L5 shown separately):

| | 5k demo (Tier 1) | 100k bundle (Case A) |
|---|---:|---:|
| L1 | $52,111 | $997,815 |
| L2 | $34,990 | $676,637 |
| L3 (year 1) | $2,108 | $20,968 |
| L4 (year 1) | $5,178 | $104,516 |
| L6 (year 1) | $3,407 | $63,686 |
| **Portfolio total, low / base / high** | **$55k / $98k / $133k** | **$1.01M / $1.86M / $2.56M** |
| L5 value at risk (not in total) | $392,703 | $9,212,532 |
| L5 conditional net, base (not in total) | −$313 | $8,346 |

For comparison, the pre-rebuild 5k figures were: L4 $62,829, L6 $276,937,
and L1/L3 with no priced value at all.

**Decisions taken with the user:**
1. **Negative-control gate input.** The gate compares each driver with
   `gate_value_usd`, the base value of only the components that driver
   measures. For L2 that's the decrease side; for L1, L3 and L4 it's the
   full base total. The pass rule is unchanged. The full corrected L2 total
   moves in both directions, so comparing it with L2's one-directional
   idle-limit driver flipped L2 to a scope-mismatch FAIL (0.79 against
   0.21). With this change L2 passes at 0.07. 5k demo against control: L1–L4
   PASS, L5/L6 INCONCLUSIVE, the same as before the rebuild.
2. **L4 acceptance tolerance.** L4 totals are judged against ±15% of the
   gross amounts being netted, and components are still judged at ±15% each.
   L4's low total is a near-cancelling net, so a ±15% band on the net would
   reject an in-band 7–8% difference in savings.
3. **The "Try it" button** keeps the 50k pre-computed bundle, which will be
   re-exported in the new schema. The 5k live run is still available by
   uploading `samples/demo_portfolio.zip`.

**Implementation notes:**
- Avoidable calls are counted as account-cycles whose recorded primary
  reason is avoidable. Summing every call in those months would add about 9%.
- L4 unit costs are read from Table 11, which matches the config today; the
  config values are a fallback only.
- The trailing-12-cycle window has 6–10% less avoidable volume than the
  reference's full history scaled by 12/36.
- Historical leave rates on the 5k demo: 7.1% a year for Valued/Premier, and
  13.7% within 12 months after a closure-request contact. The configured base
  is 10%, and neither observed rate overwrites config.
- The population-fix deltas are in
  `specs/lever_valuation_rebuild/POPULATION_FIX_DELTAS.md`.

**Out of scope, logged here only (spec section 8):**
- Loan NEP carries no ECL or capital charge, so it is an upper bound.
- ML treatment fairness fails in 5 metros on the 100k run.
- The demo cost-pool staffing bands are scaled for a 5–8k book (relevant to
  L4's staffing step).
- The L6 channel gap is planted by the generator, so finding it shows the
  engine can detect it; it is not a business finding.
- Found in passing: the Downloads page takes about 34s on the 100k bundle,
  because it builds the full-ledger CSV before anyone clicks. This was
  already the case before this branch.

---

# Previous: Pre-computed results bundle

Built so the hosted Streamlit app (2 GB instance) can show a large portfolio
without re-running the engine on it or accepting a multi-gigabyte upload.
Additive only — no engine calculation, threshold, routing rule, suppression
rule, fairness test, negative-control logic, or ML logic was changed. See
`ARCHITECTURE.md` §8a for the full design and format.

## Follow-up round: real-world memory failure, and the "try it" button

After the first version shipped, loading a real 50,000-customer bundle on
the actual Render instance failed with a 502 (the backend process almost
certainly hit the instance's memory ceiling and was killed/restarted -
Render surfaces that as a generic connection error, not a diagnosable
message). Two contributing causes were identified and fixed:

1. **`app/lib/results_bundle.py`'s validation step decoded the two largest
   tables (the full ledger and customer view) into a complete pandas
   DataFrame twice** - once just to check the row count against the
   manifest, then again right after to actually use it. Fixed to read the
   row count from the Parquet file's own footer metadata
   (`pyarrow.parquet.ParquetFile(...).metadata.num_rows`) instead, which
   never materializes the column data. Measured effect at 50k: load peak
   RSS 1,547.6 MB → 1,507.6 MB, load time 2.29s → 1.56s.
2. **The engine's live-pipeline cache (`@st.cache_resource` on
   `pipeline_runner._cached_pipeline`) is shared server-wide and never
   expires.** A user who tried the bundled 5k sample first, then loaded a
   50k bundle, had both results resident in memory at once - this is almost
   certainly the larger contributor to the actual crash (confirmed: the
   user who hit the 502 had done exactly this sequence). Fixed: loading a
   bundle (`app/Home.py`) now drops the current session's own reference to
   any previously-loaded result and calls `_cached_pipeline.clear()` before
   building the new one. Trade-off worth stating plainly: this clears the
   cache for every session on that instance, not just the one loading the
   bundle - acceptable on a small, low-concurrency internal tool, but a real
   shared side effect, not a free fix.

The standalone measurement script used throughout this feature's
development cannot reproduce cause #2 (it never had two results cached at
once to begin with), so its effect is unverified by measurement - only by
the fix matching the exact failure sequence the user reported.

**The "Try it with the bundled sample portfolio" button now loads a
pre-computed 50,000-customer results bundle** (`samples/demo_portfolio_50k_bundle.zip`,
committed to the repo, 94.3 MB) instead of running the live engine on the
5,000-customer `samples/demo_portfolio.zip`. This was a deliberate choice,
not a default left in place: it doubles as a live example of the bundle
feature on first use, and it is much cheaper to load (no live
`build_pipeline()` call at all - the only memory cost is the bundle load
itself, not the ~7GB the live engine needs at this scale). Trade-off
accepted explicitly: this sample no longer demos the negative-control gate
(no paired 50k control was generated) - the Governance page's empty-gate
message was rewritten to say so plainly and point at how to see the gate
locally, since it previously pointed at a sidebar control that had already
been removed in an earlier change (a pre-existing staleness this surfaced,
not one this feature introduced). The raw `samples/demo_portfolio.zip` and
`samples/negative_control_portfolio.zip` files are unchanged and still used
by the manual-upload path documented in `app/README.md`.

A real bug was caught before shipping this: the first export of
`demo_portfolio_50k_bundle.zip` used the engine's *default* leverage policy
(`case_b_tier1_regional`) rather than the one the app is hardcoded to
(`case_a_slr_category_iii`, set in `app/Home.py`'s `LEVERAGE_POLICY_NAME`) -
caught by checking the bundle's own metadata panel after loading it in a
local browser test, not by any automated check. Re-exported with
`--leverage-policy case_a_slr_category_iii` explicitly. **This is a real gap
in `audit/audit_results_bundle.py`'s equivalence test**: it never compares
the bundle's declared leverage policy against the value the app actually
passes anywhere, so a policy mismatch like this would not have been caught
by the test suite - only by a manual check. Worth hardening if this bundle
is regenerated again in the future.

## Second follow-up round: the 502 kept recurring; categorical dtypes; 100k

The 50,000-customer bundle continued to 502 on Render intermittently even
after the first round's fixes. Rather than guess further, measured exactly
where the loaded bundle's memory actually goes (table by table, via
`df.memory_usage(deep=True)`): `ledger_card` (1.4M rows, 41 columns) is a
97.8MB Parquet file that **expands to 858MB in memory** - six text columns
(`Masked Customer Number`, `Masked Account Number`, `Cycle Month`,
`Account Type`, `Product Tier`, `Delinquency Bucket`) account for ~490MB of
that, and critically, even 3-36-distinct-value columns (`Account Type`,
`Cycle Month`) cost nearly as much as the 50,000-distinct-value ID columns
(~80MB each) - the cost is almost entirely per-cell Python object overhead,
not content size, because pandas' default Parquet read expands a
dictionary-encoded column back into one full Python string object per row.

Fix: `engine/core/bundle_schema.py:optimize_dtypes_for_storage()`, applied
by the exporter to `customer_view` and `ledger_card` before writing -
stores these columns as pandas `category` dtype, which Parquet round-trips
losslessly (identical values; comparisons, `groupby`, CSV export all behave
the same). Measured: table memory 1,000.7MB -> 513.1MB (-49%); full bundle
load peak RSS 1,507.6MB -> 1,321.2MB (-12% end-to-end, less than the table
figure because validation/zip-decompression overhead doesn't shrink the
same way). Bundle file size on disk is unchanged (94.3MB) - Parquet was
already dictionary-encoding these columns efficiently; the fix is purely
about what pandas does with them after decoding. Re-ran
`audit/audit_results_bundle.py` after: still 77/77 passing. The committed
`samples/demo_portfolio_50k_bundle.zip` was re-exported with this fix.

**Separately, tested 100,000 customers** (at the user's request, to see how
far the approach scales). Generation itself crashed with a genuine
`MemoryError` - unrelated to the bundle feature, a previously-unknown limit
in the generator (only 50,000x36mo and 100,000x12mo had ever been
generated before; 100,000x36mo was new territory). Root-caused and fixed
three real bugs, all the same class of problem as the dtype fix above -
pandas eagerly consolidating/copying several large text columns into one
combined allocation:
- `generator/synth/transactions.py`: `TX.generate()`'s final
  `pd.DataFrame({...})` now passes `copy=False`, skipping pandas' default
  eager consolidation of this frame's 9 text columns into one >1GB array.
- `generator/run.py` and `generator/synth/rewards.py`: removed two
  redundant `.copy()` calls (the frame was already independent at each
  point - boolean-mask filtering already returns a copy, not a view - so
  the explicit `.copy()` served no purpose beyond forcing the same costly
  consolidation).
- `generator/run.py`: the `WRONG_EARN_RULE` ground-truth comparison
  previously kept a full second copy of the entire transaction table alive
  just to compute "what earn would have looked like without the defect."
  Narrowed to just the (typically ~3%) accounts the defect actually
  affects - verified at small scale that this gives **byte-identical**
  ground-truth output to the full-table comparison (`pd.testing.assert_frame_equal`
  passed), since `RW.earn()`'s only cross-row state, a per-account running
  bonus-spend cap, is computed independently per account and is unaffected
  by excluding other accounts' rows.

With all three fixes, 100,000 customers x 36 months now generates (253.7s)
and exports (a 186.7MB bundle) successfully, where it previously crashed
outright before reaching the engine at all. **However: loading that bundle
still measures ~2,467.8MB peak RSS even after the categorical-dtype fix -
likely still too large for a 2GB hosted instance.** This is stated plainly
as a known limitation, not implied to work: 100,000 customers is not
currently a safe target for the hosted app on its current instance size,
even though local generation and export now succeed. Export time at 100k
was also measured at ~23.5 minutes (vs ~1.8 minutes at 50k) - a
disproportionate, non-linear increase not fully explained by the fixes
above; flagged here rather than chased further given the time already
invested, and possibly contaminated by this machine's own memory pressure
from running several large operations back to back during testing.

`generator/synth/transactions.py` also carries two older, unrelated memory
fixes from earlier in this session (vectorizing a date-string construction
and a day-value dtype width issue) that had not yet been committed when
this round's fix landed in the same file - included together in one commit
since they are the same class of fix in the same file, after explicit
confirmation.

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
