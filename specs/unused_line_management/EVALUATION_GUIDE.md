# Evaluation guide - Unused Credit Line Management

For whoever signs the module off. Live app: https://profitinsight-unused-lines.streamlit.app; everything below also runs locally.

## 1. Run it

```bash
python -m pip install -r unused_lines_app/requirements.txt
```
```bash
python -m streamlit run unused_lines_app/Home.py --theme.baseFontSize 18
```

The app loads only the committed samples in `samples/unused_lines/` and stays under 2 GB (measured
peak 0.62 GB with the 100k stress book, all pages, both datasets, two sessions).

**Which dataset:** start with the **stress book** (sidebar, default): synthetic stress data tuned
toward the reference workbook's population, so every segment has accounts. Then switch to the **5k
demo** (the standard illustrative bank) to see the module on a normal book, where most screened
accounts are Relationship / Premium.

Tests (never claim a pass you did not run):

```bash
python audit/audit_unused_line_module.py --regression
```

With the rebuilt 100k bundle and its per-account file (local, not committed) the suite also runs the
§2.7 reconciliation and the 100k load test:

```bash
python audit/audit_unused_line_module.py --regression --bundle-100k <bundle_100k_v2.zip> --frame-100k <p100k_accounts.parquet> --frame-100k-json <p100k_frame.json>
```

Rebuilding the inputs (offline; see the requirements below):

```bash
python -m generator.run --profile unused_line_stress --n 100000 --out <dir>/unused_line_stress
```
```bash
python -m unused_lines_app.build_sample --data <dir>/unused_line_stress --name stress --label "Unused-line stress book (100,000 customers) - synthetic stress data"
```

### Build requirements (recorded, not a target)
Machine: Windows Server 10.0.26200, 4 CPUs, 34.4 GB RAM, Python 3.13.12.

| Step | Time | Peak memory |
|---|---|---|
| Stress book: generate 100k customers | 442 s | not recorded |
| Stress book sample (100k customers, 91,818 card accounts) | 374 s | 22.2 GB |
| 5k demo sample | 16 s | 0.91 GB |
| 100k portfolio generation | 357 s | not recorded |
| 100k bundle export (lever-valuation branch code) | 197 s | not recorded |
| 100k per-account file | 131 s | **15.6 GB** (offline only; chunked generation logged as a future improvement) |
| App at runtime (committed samples) | first Overview load about 4 s, then shared across sessions | 0.62 GB (AppTest, all pages, both datasets, two sessions) |

## 2. What to check, page by page (stress book, default settings)

| Page | Check | Expected |
|---|---|---|
| Every page | Assumption label at the top; value-type legend; "synthetic stress data" note | Present |
| Overview | Screened accounts | **40,530** of 88,232 open |
| | Card profit; unused lines | **−$2,579,382**; **$573.4M** |
| | Carrying cost; expected drawdown loss (beside profit) | **$693,984**; **$1,633,129** |
| | Base annual value = card profit change + avoided drawdown loss | **+$175,389** (−$9,609 + $184,998) |
| | Capital released, one-time, never in the annual value | **$113,865** |
| | 1.5× stress | **+$155,257, go** |
| | Pending approval (B6); extra levers | **+$519,808**; **+$191,794**, both apart from the headline |
| Scenario dashboard | Conservative ≤ Base ≤ Aggressive | +$125,670 ≤ +$175,389 ≤ +$210,933 |
| | Year 1 vs full, by lever; workbook / extra / pending subtotals | Shown side by side |
| | Workbook-reproduction panel | Base +$1,329,137, 8,470 accounts lost, exactly the workbook's Dashboard |
| Segments | Counts | Deteriorating 1,460; Relationship 5,513; Dormant 15,076; Sock-Drawer 6,139; Transactors 6,337; Unassigned 6,005 |
| | Drawdown toggle sensitivity | +7,328 accounts, $637,348 more loss after drawdown |
| Regulatory settings | Worked examples | $13.20 (dormant), $10.56 (revolver), $7.54 (transactor) a year |
| | "Category IV or other" with default scope | Liquidity cost goes to $0; capital unchanged |
| | Current US rules view | RWA from unused lines $0; no liquidity cost; SLR shown |
| | Fairness | Four-fifths by metro on the module's own decreases and closures; failures flagged in red; metros with fewer than 30 selected accounts show "insufficient sample" |
| Levers & assumptions | Any edit | "Exploration only" warning on every page; Reset restores the defaults |
| | B6 on | Pending levers move into the headline (Base becomes about +$500,700) |
| Lever guide | Every lever | Status, reason code, compliance column, timing column |
| Customer drill-down | Formula trace | Every number with its formula; values tagged by type |
| | Transactor test | 12 cycles, each pass / fail with the reason |
| | Review notes | Download labelled "review notes, not an approval record" |

5k demo (default settings): 890 screened (Relationship 555); card profit −$61,296; carrying cost
$10,630; drawdown loss $9,926; Base +$817; capital released $1,307; 1.5× +$635 (go).

### Example customers (stress book, Customer drill-down)

| Segment | Typical | Borderline (card profit nearest $0) | Review together |
|---|---|---|---|
| Credit-Deteriorating | ACC0072117 (−$39.80; suppress automatic increases) | ACC0099245 (−$0.04; no action: not in the Base share) | ACC0000358 (L3 pricing) |
| Relationship / Premium | ACC0013339 (−$119.16; engagement campaign) | ACC0061128 (−$0.00) | ACC0000036 (L1 rewards) |
| Dormant | ACC0068951 (dormant right-sizing and non-reissue, pending approval; campaign) | ACC0036779 (dormant right-sizing, non-reissue; pending) | ACC0000308 (L3 pricing) |
| Sock-Drawer | ACC0071275 (campaign; suppress automatic increases) | ACC0003226 (−$0.03; no action) | ACC0000042 (L1 rewards) |
| Transactors | ACC0096027 (no line action: right-sizing never recommended) | ACC0049370 (−$0.01) | ACC0000000 (L1 rewards) |
| Unassigned | ACC0077565 (no workbook lever) | ACC0091120 (−$0.01) | ACC0000043 (L1 rewards) |

The drill-down offers these three per segment directly (Example: typical / borderline / review
together).

## 3. Known limits (read before signing)
- Calibration: 25 of 43 workbook metrics within ±25% on the stress book; every gap explained in
  `STAGE4_REPORT.md`. Credit-Deteriorating is under-represented by construction under the
  system-mode screen.
- Transactor right-sizing does not lose money in system mode (the engine's fixed-cost split); it is
  never recommended.
- Fairness failures (`ISSUES_FOUND.md` #10): a fair-lending review is needed before any pilot.
- The go / no-go passes on the headline (incl. avoided drawdown loss); card profit alone is negative
  at 1.5×.
- §2.7: the module's own carrying cost is +6.1% against the brief because of the agreed transactor
  test; with the plan / promotional rule off it is within 3.5% (tested).

## 4. Sign-off checklist
- [ ] `python audit/audit_unused_line_module.py --regression` runs with 0 failures on this machine
- [ ] Workbook reproduction exact (Base +$1,329,137; 8,470 accounts lost)
- [ ] Worked examples $13.20 / $10.56 / $7.54
- [ ] Every page shows the assumption label and value types; the stress book is labelled synthetic
- [ ] Capital released never added to an annual value
- [ ] Carrying cost and drawdown loss in separate columns everywhere
- [ ] B6 levers outside the headline while their flags are off
- [ ] Every action has a reason code; inactivity actions have no adverse-action notice; credit ones do
- [ ] No inactivity fee anywhere
- [ ] No ML output anywhere in the module (B8: ML model not used)
- [ ] Fairness failures reviewed by fair lending
- [ ] Compliance has confirmed the regulatory summary (Reg B, Reg Z, FCRA, LCR, capital)
- [ ] Finance has replaced the illustrative capital ratio, cost of equity and carry, or accepted them
- [ ] Decisions B4–B7 taken (config only); B8 decided
- [ ] Pilot design agreed (10% holdout, stratified by segment)

## 5. Deployment
Deployed on 16 Nov 2026: **https://profitinsight-unused-lines.streamlit.app** (branch
`feature/unused-line-management`, Python 3.13). It redeploys on every push to the branch. Steps used,
for a redeploy elsewhere:

1. Push the branch (only when asked) to the GitHub repository.
2. On share.streamlit.io: **New app** → repository and branch `feature/unused-line-management` →
   main file path **`unused_lines_app/Home.py`**.
3. Advanced settings: Python 3.13. The requirements are read from `unused_lines_app/requirements.txt`
   (pinned) next to the entry point.
4. No secrets are needed: the app reads only the committed samples in `samples/unused_lines/`.
5. Deploy; open each page on both datasets; check the figures in section 2.

Render stays on hold. The six-lever app (`app/`) and its deployment are unchanged.
