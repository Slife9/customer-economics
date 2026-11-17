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
peak 0.85 GB with the 100k stress book: every page, both views, both datasets, one process).

**Which view:** the app opens in the **Executive view** (sidebar): five decision pages in plain
language. Switch to the **Analyst view** for formulas, value types, full tables and the Explore &
reference pages (What-if, Lever guide & regulation, Data & calibration, Technical). A fresh session
always starts in the Executive view, so a direct link to an analyst page opens the summary.

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
| App at runtime (committed samples) | first Executive summary load about 6 s, then shared across sessions | 0.85 GB (AppTest, all pages, both views, both datasets, one process) |

## 2. What to check, page by page (stress book, default settings, Executive view)

Every decision page follows one template: a headline sentence, at most four cards (one larger), one
chart, "What this means" (three takeaways), "What to decide / do", and Details. The assumption label
is in the sidebar on every page. Each decision number has one home page; the Executive summary
shows them together and links to it.

| Page | Check | Expected |
|---|---|---|
| **Executive summary** | Headline sentence | "40,530 card accounts lose money while holding large unused lines. Approved actions are worth +$175k a year; dormant-card actions worth +$520k more await your decision." |
| | Four cards (annual value larger) | Accounts losing money with large unused lines **40,530**; Cost of unused lines **$2.33M** ($694k holding + $1.63M expected losses); Annual value **+$175k**; Awaiting your decision **+$520k** |
| | Chart: annual value by the three plain actions | Trim unused limits +$199k (approved); Wake up or close dormant cards −$38k approved + $520k awaiting; Stop automatic increases +$192k (extra) |
| | Status tiles | Robustness: watch, still pays off at 1.5x; Fairness: act, 2 metros fail; Data calibration: watch, 25 of 43; Rules assumed: watch, proposal not law; Decisions pending: 4 open |
| | Decisions box | Dormant-card actions (B6) +$520k; fair-lending review (Albuquerque, Birmingham); pilot with a 10% holdout |
| | One-time capital freed | $113,865, not annual |
| **Where the cost sits** (home of the problem and the cost) | Cards | 40,530 accounts (45.9% of 88,232 open; $573.36M unused); annual loss −$2.58M; holding $694k; expected losses $1.63M |
| | Six group cards (plain names) | Customers at rising risk 1,460; Valuable relationship customers 5,513; Unused cards 15,076; Occasional users 6,139; Pay-in-full customers 6,337; Other 6,005 |
| | Headline and chart | Customers at rising risk carry the largest share ($817k of $2.33M); holding cost vs expected losses by group (rising-risk customers $19k vs $798k) |
| | Details | Full table; rules and thresholds; screen sensitivity (+7,328 accounts, $637,348 more loss); analyst: LEQ account vs workbook by group (B2) |
| **Actions and value** (home of approved value and value awaiting decision) | Cards | Annual value **+$175k**; year 1 +$146k; awaiting your decision +$520k; customers leaving 214 |
| | Chart and 5-column table | Annual value with year 1 by action: Trim unused limits 2,506 customers, +$199,016, +$169,164, 138 leaving |
| | Scenarios | Conservative +$125,670 ≤ Base +$175,389 ≤ Aggressive +$210,933 |
| | Details (analyst) | By lever, by segment, how the value is built (card profit alone −$9,609; reduction in drawdown loss +$184,998; relationship-adjusted −$68,862), fixed-cost setting (B5: engine +$175,389 vs workbook +$217,245, 54,204 screened), timing |
| **Risks and checks** (home of the red flags) | Tiles | Robustness, Fairness (2 fail, 68 pass, 6 too few to test), Rules assumed, Notices required (2,506 adverse-action notices; 26,981 actions flagged for compliance) |
| | Chart | Annual value at 1x-2x: +$175k, +$164k, +$155k, +$148k, +$141k; analyst view adds card profit alone |
| | Worked example | A $10,000 unused card costs $13.20 a year to hold ($9.45 capital + $3.75 liquidity) |
| | Details | Notices by reason code; fairness by metro ("insufficient sample" below 30 selected); parameters; current US rules comparison |
| **Customer evidence** | Recommendation card | e.g. ACC0070665 (limit cut example): "Reduce limit from $52,000 to $39,000. Reason: rising credit risk. Adverse-action notice: required." |
| | Three key facts | Unused amount; annual cost to the bank of the unused line; drawdown risk (PD imputed flagged) |
| | Review | Agree / Disagree / Need more information, with a note; downloads labelled "review notes, not an approval record" (this account, or every account reviewed in the session) |
| | Details | Calculation trace (both LEQ values, PD imputed flag), transactor test month by month, rules met / not met, other worklists |
| **What-if** (analyst) | Any edit | "Exploration only"; a warning on every page; Reset restores the defaults |
| | B6 on | Pending levers move into the annual value (Base +$500,730) |
| | LEQ source / fixed-cost basis | account Behavioral CCF (measured_account): Base +$120,339; workbook fixed cost: Base +$217,245 |
| | "Category IV or other" | Liquidity cost goes to $0; capital unchanged |
| **Lever guide** (analyst) | Every lever | Plain action, status, reason code, adverse-action notice, compliance, timing; reason-code notice rules |
| **Technical** (analyst) | Reconciliation (B4) | card_net −$2,000,170 + old capital $124,981 − new capital $489,183 − liquidity $215,011 = −$2,579,382 (screened); check $0.00 |
| | Workbook reproduction | Base +$1,329,137, 8,470 accounts lost, exactly the workbook's Dashboard |

Executive view hides formulas, value-type badges, technical column names and wide tables (checked by
the suite). Analyst labels: Screened accounts, Carrying cost, Drawdown loss, Headline value,
Go/no-go, Pending approval (B6), Capital released.

5k demo (default settings): 890 screened (Valuable relationship customers 555); card profit
−$61,296; holding cost $10,630; expected losses $9,926; Base +$817; capital released $1,307; 1.5×
+$635 (go); fairness: every metro "insufficient sample".

Figures after revision B (17 Nov 2026): B1 changes nothing on the samples (only closed or charged-off
accounts lack a PD); B2's default is the workbook segment LEQ (decided 17 Nov 2026), so the
headline figures equal those before the revision; B3 changes only the reason codes; B5's default
(engine allocation) changes nothing.

### Example customers (stress book, Customer evidence)

| Group | Typical | Borderline (card profit nearest $0) | Limit cut | Review together |
|---|---|---|---|---|
| Customers at rising risk | ACC0072117 (−$39.80; stop automatic increases) | ACC0099245 (−$0.04; no action: not in the Base share) | ACC0070665 ($52,000 → $39,000) | ACC0000358 (L3 pricing) |
| Valuable relationship customers | ACC0013339 (−$119.16; wake-up campaign) | ACC0061128 (−$0.00; stop increases; L5) | ACC0038232 ($93,250 → $69,938) | ACC0000036 (L1 rewards) |
| Unused cards | ACC0068951 (right-size and do not reissue, awaiting decision; campaign) | ACC0036779 (right-size, do not reissue; awaiting) | ACC0008733 ($48,000 → $36,000, awaiting decision) | ACC0000308 (L3 pricing) |
| Occasional users | ACC0071275 (campaign; stop automatic increases) | ACC0003226 (−$0.03; no action) | ACC0058976 ($22,750 → $17,062) | ACC0000042 (L1 rewards) |
| Pay-in-full customers | ACC0096027 (stop increases; no cut: right-sizing never recommended) | ACC0049370 (−$0.01) | none | ACC0000000 (L1 rewards) |
| Other | ACC0077565 (stop increases; no limit lever) | ACC0091120 (−$0.01) | none | ACC0000043 (L1 rewards) |

The page offers these per group directly (Example: typical / borderline / limit cut / review
together).

## 3. Known limits (read before signing)
- Calibration: 25 of 43 workbook metrics within ±25% on the stress book; every gap explained in
  `STAGE4_REPORT.md`. Credit-Deteriorating is under-represented by construction under the
  system-mode screen.
- Transactor right-sizing does not lose money in system mode (the engine's fixed-cost split); it is
  never recommended.
- Fairness failures (`ISSUES_FOUND.md` #10): a fair-lending review is needed before any pilot.
- The go / no-go passes on the headline (incl. avoided drawdown loss); card profit alone is negative
  already at 1×.
- Fixed cost: the engine allocates $2.91 per screened account on the stress book (workbook $30–60);
  the workbook basis (B5) screens 54,204 accounts and gives Base +$217,245.
- LEQ: the default is the workbook segment LEQ. The account Behavioral CCF (setting
  `measured_account`) is a generator parameter (0.42 / 0.798) that flattens LEQ to about 0.42
  (`ISSUES_FOUND.md` #16): stress book Base +$120,339.
- §2.7: the module's own carrying cost is +6.1% against the brief because of the agreed transactor
  test; with the plan / promotional rule off it is within 3.5% (tested).

## 4. Sign-off checklist
- [ ] `python audit/audit_unused_line_module.py --regression` runs with 0 failures on this machine
- [ ] Workbook reproduction exact (Base +$1,329,137; 8,470 accounts lost)
- [ ] Worked examples $13.20 / $10.56 / $7.54
- [ ] Assumption label in the sidebar on every page; the stress book is labelled synthetic; value types in the analyst view
- [ ] Executive view: plain labels, one headline basis (annual value = change in card profit + reduction in expected drawdown loss)
- [ ] Capital released never added to an annual value
- [ ] Carrying cost and drawdown loss in separate columns everywhere
- [ ] B6 levers outside the headline while their flags are off
- [ ] Every action has a specific reason code (OTHER below 1%); inactivity actions have no adverse-action notice; credit and idle-line ones do
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
