# Evaluation guide - Unused Credit Line Management

For whoever signs the module off. Everything below runs locally; nothing is deployed.

## 1. Run it

```bash
python -m pip install -r unused_lines_app/requirements.txt
```
```bash
python -m streamlit run unused_lines_app/Home.py --theme.baseFontSize 18
```

The app loads only the committed samples in `samples/unused_lines/` and stays under 2 GB (measured
peak 0.42 GB on the live server, all pages, both datasets).

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
python -m generator.run --profile unused_line_stress --out <dir>/unused_line_stress
```
```bash
python -m unused_lines_app.build_sample --data <dir>/unused_line_stress --name stress --label "Unused-line stress book (10,000 customers) - synthetic stress data"
```

### Build requirements (recorded, not a target)
Machine: Windows Server 10.0.26200, 4 CPUs, 34.4 GB RAM, Python 3.13.12.

| Step | Time | Peak memory |
|---|---|---|
| Stress book sample (10k) | 35 s | 2.35 GB |
| 5k demo sample | 16 s | 0.91 GB |
| 100k portfolio generation | 357 s | not recorded |
| 100k bundle export (lever-valuation branch code) | 197 s | not recorded |
| 100k per-account file | 131 s | **15.6 GB** (offline only; chunked generation logged as a future improvement) |
| App at runtime (committed samples) | page loads ≤ 1.7 s | 0.29 GB (AppTest), 0.42 GB (live server) |

## 2. What to check, page by page (stress book, default settings)

| Page | Check | Expected |
|---|---|---|
| Every page | Assumption label at the top; value-type legend; "synthetic stress data" note | Present |
| Overview | Screened accounts | **4,652** of 8,833 open |
| | Card profit; unused lines | **−$344,894**; **$67.6M** |
| | Carrying cost; expected drawdown loss (beside profit) | **$81,204**; **$193,433** |
| | Base annual value = card profit change + avoided drawdown loss | **+$22,239** (−$1,078 + $23,317) |
| | Capital released, one-time, never in the annual value | **$14,228** |
| | 1.5× stress | **+$19,708, go** |
| | Pending approval (B6); extra levers | **+$52,685**; **+$25,078**, both apart from the headline |
| Scenario dashboard | Conservative ≤ Base ≤ Aggressive | +$16,081 ≤ +$22,239 ≤ +$27,022 |
| | Year 1 vs full, by lever; workbook / extra / pending subtotals | Shown side by side |
| | Workbook-reproduction panel | Base +$1,329,137, 8,470 accounts lost, exactly the workbook's Dashboard |
| Segments | Counts | Deteriorating 173; Relationship 618; Dormant 1,497; Sock-Drawer 686; Transactors 867; Unassigned 811 |
| | Drawdown toggle sensitivity | +614 accounts, $63,901 more loss after drawdown |
| Regulatory settings | Worked examples | $13.20 (dormant), $10.56 (revolver), $7.54 (transactor) a year |
| | "Category IV or other" with default scope | Liquidity cost goes to $0; capital unchanged |
| | Current US rules view | RWA from unused lines $0; no liquidity cost; SLR shown |
| | Fairness | Failures flagged in red for module cuts and closures, ML adverse actions and ML increases |
| Levers & assumptions | Any edit | "Exploration only" warning on every page; Reset restores the defaults |
| | B6 on | Pending levers move into the headline (Base becomes about +$54,000) |
| Lever guide | Every lever | Status, reason code, compliance column, timing column |
| Customer drill-down | Formula trace | Every number with its formula; values tagged by type |
| | Transactor test | 12 cycles, each pass / fail with the reason |
| | Review notes | Download labelled "review notes, not an approval record" |

5k demo (default settings): 890 screened (Relationship 555); card profit −$61,296; carrying cost
$10,630; drawdown loss $9,926; Base +$817; capital released $1,307; 1.5× +$635 (go).

### Example customers (stress book, Customer drill-down)

| Segment | Typical | Borderline (card profit nearest $0) | Review together |
|---|---|---|---|
| Credit-Deteriorating | ACC0005391 (−$42; no action: not in the Base share) | ACC0001455 (−$0.71; risk-based decrease, adverse action + FCRA check) | ACC0001995 (L1 rewards) |
| Relationship / Premium | ACC0007024 (−$153; L3 pricing) | ACC0002343 (−$2.15; L1 + L5) | ACC0000008 (L1 rewards) |
| Dormant | ACC0007062 (dormant right-sizing, pending approval; campaign) | ACC0004089 (dormant right-sizing, pending) | ACC0000023 (closure and non-reissue, pending; L3) |
| Sock-Drawer | ACC0005188 (suppress automatic increases) | ACC0009989 (line decrease, adverse action, 45-day fee restriction) | ACC0000341 (campaign; L3) |
| Transactors | ACC0009187 (no line action: right-sizing never recommended; L1) | ACC0001764 (−$0.03) | ACC0000011 (L1) |
| Unassigned | ACC0005492 (no lever) | ACC0001323 (−$0.04) | ACC0000009 (L1) |

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
- [ ] ML model shown as a second opinion only
- [ ] Fairness failures reviewed by fair lending
- [ ] Compliance has confirmed the regulatory summary (Reg B, Reg Z, FCRA, LCR, capital)
- [ ] Finance has replaced the illustrative capital ratio, cost of equity and carry, or accepted them
- [ ] Decisions B4–B8 taken (config only)
- [ ] Pilot design agreed (10% holdout, stratified by segment)

## 5. Deployment preparation (not deployed)
Streamlit Community Cloud, like the L1 Rewards app:

1. Push the branch (only when asked) to the GitHub repository.
2. On share.streamlit.io: **New app** → repository and branch `feature/unused-line-management` →
   main file path **`unused_lines_app/Home.py`**.
3. Advanced settings: Python 3.13. The requirements are read from `unused_lines_app/requirements.txt`
   (pinned) next to the entry point.
4. No secrets are needed: the app reads only the committed samples in `samples/unused_lines/`.
5. Deploy; open each page on both datasets; check the figures in section 2.

Render stays on hold. The six-lever app (`app/`) and its deployment are unchanged.
