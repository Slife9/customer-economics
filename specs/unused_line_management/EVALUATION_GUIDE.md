# Evaluation guide - Unused Credit Line Management

For whoever signs the module off. Live app: https://profitinsight-unused-lines.streamlit.app (it shows
the version last pushed and rebooted; revision E is local until pushed). Everything below also runs
locally.

**Reference documents (revision E):** the app follows the project report
(`Unused_Credit_Line_Management_Project_Report.docx`) and the stakeholder slides
(`Unused_Credit_Line_Strategy_v2.pptx`) for structure, wording and definitions. The figures moved after
the calculation corrections: `FIGURES_CHANGED_SINCE_REPORT.md` lists every one, old vs new.

## 1. Run it

```bash
python -m pip install -r unused_lines_app/requirements.txt
```
```bash
python -m streamlit run unused_lines_app/Home.py --theme.baseFontSize 18
```

The app loads only the committed samples in `samples/unused_lines/` and stays under 2 GB.

**Which view:** the app opens in the **Executive view** (sidebar): nine pages that tell the report's
story in its order - the problem, how unused credit costs money, who the customers are, where the
cost sits, the four strategies, what they are worth, implementation, protecting customers and risks,
customer evidence - always on the stress book. The **Analyst view** adds the dataset switch (5k demo),
the levers under each strategy, formulas, value types, full tables and the Explore & reference pages
(What-if, Levers & lever guide, Data & calibration, Technical). A fresh session always starts in the
Executive view.

Tests (never claim a pass you did not run):

```bash
python audit/audit_unused_line_module.py --regression
```

With the rebuilt 100k bundle and its per-account file (local, not committed) the suite also runs the
§2.7 reconciliation and the 100k load test:

```bash
python audit/audit_unused_line_module.py --regression --bundle-100k <bundle_100k_v2.zip> --frame-100k <p100k_accounts.parquet> --frame-100k-json <p100k_frame.json>
```

Every report figure, before and after revision E, on a committed sample:

```bash
python audit/unused_line_report_figures.py --dataset stress
```

Rebuilding the inputs (offline; see the requirements below):

```bash
python -m generator.run --profile unused_line_stress --n 100000 --out <dir>/unused_line_stress
```
```bash
python -m unused_lines_app.build_sample --data <dir>/unused_line_stress --name stress --label "Unused-line stress book (100,000 customers) - synthetic stress data"
```

Revision E added six balance columns to the committed samples from their own monthly file:

```bash
python -m unused_lines_app.build_sample --name stress --update-balance-basis
```

### Build requirements (recorded, not a target)
Machine: Windows Server 10.0.26200, 4 CPUs, 34.4 GB RAM, Python 3.13.12.

| Step | Time | Peak memory |
|---|---|---|
| Stress book: generate 100k customers | 442 s | not recorded |
| Stress book sample (100k customers, 91,818 card accounts) | 374 s | 22.2 GB |
| 5k demo sample | 16 s | 0.91 GB |
| 100k per-account file (revision E, with the balance-basis columns) | 199 s | **15.6 GB** (offline only) |
| App at runtime (committed samples) | first Executive summary load about 8 s, then shared across sessions | under 2 GB (suite: all pages, both views, both datasets, one process) |

## 2. What to check, page by page (stress book, default settings, Executive view)

Every page: one headline sentence, at most four figure cards, one main chart, detail in expanders,
the report's terms (no PD / LGD / LEQ / RWA / LCR), the assumption label in the sidebar. All checked
by the suite.

| Page | Check | Expected |
|---|---|---|
| **Executive summary** | Headline | "47% of open cards (41,192 of 88,232) lose money while holding $573M of unused credit that costs about $2.32M a year; four strategies could deliver up to about $866k a year, $156k of it already approved." |
| | Four cards | The problem **41,192 cards** (lose $2.51M a year, about 4% of limits used at statement date); The cost **$2.32M** ($693k to hold + $1.63M expected drawdown loss); Approved now **+$156k**; Total potential **+$866k** (+ $194k proposed + $516k awaiting) |
| | The four strategies | 1 Right-size +$195k (Approved); 2 Re-engage −$17k (Approved: test only); 3 Use it or lose it +$494k (Invite approved; actions awaiting decision); 4 Stop automatic increases +$194k (Proposed) |
| | Status tiles | Fairness: act, 1 area fails (Albuquerque; 70 tested, 6 too small); Robustness: watch, still worth it at 1.5x (+$134k; card profit alone −$33k); Rules assumed: watch, proposal not law |
| | What is needed | Pilot with a 10% holdout; decide on Strategy 3's actions; fair-lending review; finance confirms the capital ratio, cost of equity and carry |
| **The problem** | Cards | 41,192 (46.7% of open cards); card profit −$2.51M (−$61 per card); unused $573M ($13,907 per card); about 4% of the limit used at statement date |
| | Chart | Doughnut: 96% unused, 4% used (statement balance, 12-month average); the six selection tests beside it; about 40% of cards with no statement balance all year |
| **How unused credit costs money** | Worked example ACC-EXAMPLE | Capital $14,000 × 10% × 75% × 10.5% × 12% = $13.23; liquidity $14,000 × 5% × 0.75% = $5.25; drawdown $14,000 × 3% × 80% × 50% = $168.00; total **$186.48**; $7.94 capital at 45%. Every multiplier tagged measured / regulatory (assumed) / business / workbook estimate |
| | Portfolio line | Carrying cost $693k (capital $478k, liquidity $215k) + drawdown $1.63M = $2.32M; per $1,000 unused: $1.21 to hold, $2.84 expected loss |
| | Expanders | Assumptions with reasons; share drawn before default by group (70 / 50 / 40 / 20 / 15%, other 42%); current law vs working assumption; how it feeds into card profit |
| **Customers and where the cost sits** | Headline | Customers at rising risk are 4% of the cards but carry the largest cost, $810k a year and 49% of all expected drawdown loss |
| | Groups table | Rising risk 1,462; Relationship 5,431; Unused cards 15,076; Occasional users 6,170; Pay-in-full 6,869; Other 6,184, each with its rule |
| | Chart | Stacked cost to hold + expected drawdown loss by group; four takeaways |
| | How cards qualify | Rising risk 723 / 479 / 260 (PD only / score only / both), average chance of default 10% |
| **The four strategies** | Cards | What, who, why, status and value for each; Strategy 3 as its journey: Invite −$22k, right-size after the warning +$163k, close +$194k, don't reissue +$159k |
| | Warning step | Resume use 10% (≥ $100 of spend in 90 days), accept a lower limit 20%, close 10%, no response 60%; 13,823 letters at $1; never a fee |
| | What we don't do | Cut pay-in-full limits; act on "Other"; touch protected customers |
| **What they are worth** | Cards | Approved +$156k; Proposed +$194k; Awaiting a decision +$516k; Total potential +$866k |
| | Chart | Each strategy on its own, coloured by status; Strategy 2 and the Invite red (approved, lose money today) |
| | Approved actions | $156k = $181k less expected drawdown loss − $24k card profit; range $115k to $180k; 1.5× +$134k (still worth it); 138 leaving of 41,192; $14.1M unused removed; $59k capital freed (one time) |
| **Implementation** | Chart | 15-month timeline: prepare M1–2, pilot with 10% holdout M3–8, decide M9, roll out M10–15; Strategy 2 test only; Strategy 3 Invite → Warn → Act → Don't reissue |
| | Boxes | Before the pilot; pilot design and success criteria; roles; measures |
| **Protecting customers and risks** | Tiles, safeguards | Fairness, robustness, rules assumed; eight safeguards (25% per review, $500 / 1.2× floors, reasons, notices, 45 days, the 90-day warning, reinstatement, protected customers) |
| | Chart | The 15 areas with the lowest selection rate for cuts and closures against the four-fifths line (Albuquerque below it) |
| | Expanders | Rules (Reg B, inactivity exception, FCRA, Reg Z 45 days, inactivity fee ban, ability to pay, UDAAP for the warning letter); risks; pending corrections; notices by reason |
| **Customer evidence** | Recommendation card first | e.g. ACC0070665 (rising risk, limit cut): Strategy 1; reduce the limit from $52,000 to $39,000 (approved); CREDIT_DETERIORATION; adverse-action notice within 30 days; 45-day fee restriction. ACC0000018 (unused card): Strategy 3; right-size after the 90-day warning (awaiting decision); INACTIVITY; no adverse-action notice |
| | Then | Unused credit today, annual cost of the unused line, card profit; the full calculation trace; selection tests and group rules; the payment record month by month |
| **What-if** (analyst) | Any edit | "Exploration only"; a warning on every page; Reset restores the defaults |
| | Revision E settings | Balance basis (statement date / midpoint / today's line; "before E" options), pay-in-full cuts in the approved value, the warning (on/off, shares, reset rule, letter cost, notice days) |
| **Levers & lever guide** (analyst) | Every lever | Its strategy, status, stand-alone value, reason code, notice, compliance, timing |
| **Technical** (analyst) | Reconciliation (B4) | Main engine card profit to the module's card profit, step by step, check $0.00 |
| | Workbook reproduction | Base +$1,329,137, 8,470 accounts lost, exactly the workbook's Dashboard |

Example accounts offered on Customer evidence (stress book): typical, borderline (card profit nearest
$0), limit cut and 90-day warning per group - e.g. rising risk ACC0009830 / ACC0057157 / ACC0070665;
unused cards ACC0068951 / ACC0036779 / ACC0008733 / ACC0000018; occasional users ACC0019844 /
ACC0026981 / ACC0058976.

5k demo (analyst view, default settings): 890 selected; card profit −$60,626; holding cost $10,465;
expected losses $9,754; approved +$715; total potential +$7,726; fairness: every area too small to test.

## 3. Known limits (read before signing)
- The report and slides predate revision E: see `FIGURES_CHANGED_SINCE_REPORT.md` (selection 40,530 →
  41,192; approved $175k → $156k; total potential $887k → $866k; fairness 2 → 1 area). The report's
  "12 of 64 areas" is from the old 10k book; "294 cards" is 289 on the stress book.
- The 90-day warning's response shares and letter cost are assumptions to be tested in the pilot. The
  warning raises the value of right-sizing (voluntary closures and accepted cuts without attrition)
  and lowers closure and non-reissue (customers who keep their card).
- Pay-in-full right-sizing is excluded by policy; it shows a small gain in Base, partly because the
  engine allocates only $2.91 of fixed cost per selected card (workbook $30–60). With the workbook
  fixed cost (B5) 54,666 cards are selected and the approved value is +$191,709.
- LEQ: the default is the workbook segment LEQ. The account Behavioral CCF is a generator parameter
  (0.42 / 0.798; `ISSUES_FOUND.md` #16): with it the approved value is +$94,693.
- Fairness (`ISSUES_FOUND.md` #10): the test flags areas selected less often than the comparison
  rate; a fair-lending review should decide the method before any customer is contacted.
- Calibration: 25 of 43 workbook metrics within ±25% on the stress book (`STAGE4_REPORT.md`).
- §2.7: the module's own carrying cost is +6.1% against the brief because of the agreed transactor
  test; with the plan / promotional rule off it is within 5% (tested, on the after-payment basis the
  brief used).

## 4. Sign-off checklist
- [ ] `python audit/audit_unused_line_module.py --regression` runs with 0 failures on this machine
- [ ] Worked examples $13.20 / $10.56 / $7.54 and ACC-EXAMPLE $186.48
- [ ] Workbook reproduction exact (Base +$1,329,137; 8,470 accounts lost)
- [ ] Every revision-E setting at its old value reproduces the figures before E exactly
- [ ] Strategy values add up to their components; capital freed never added to an annual value
- [ ] The warning step never creates a fee
- [ ] Every action has a specific reason code (OTHER below 1%) and a strategy; inactivity actions have no adverse-action notice; credit and idle-line ones do
- [ ] Assumption label in the sidebar; the stress book labelled synthetic; executive pages free of PD / LGD / LEQ / RWA / LCR
- [ ] No ML output anywhere in the module (B8)
- [ ] Fairness failures reviewed by fair lending
- [ ] Compliance has confirmed the regulatory summary and the warning wording
- [ ] Finance has replaced the illustrative capital ratio, cost of equity and carry, or accepted them
- [ ] Decision on Strategy 3's actions (B6); pilot design agreed (10% holdout, stratified by group)

## 5. Deployment
Deployed on 16 Nov 2026: **https://profitinsight-unused-lines.streamlit.app** (branch
`feature/unused-line-management`, Python 3.13). A push does not always redeploy it: reboot it from
share.streamlit.io (app menu → Reboot). Steps used, for a redeploy elsewhere:

1. Push the branch (only when asked) to the GitHub repository.
2. On share.streamlit.io: **New app** → repository and branch `feature/unused-line-management` →
   main file path **`unused_lines_app/Home.py`**.
3. Advanced settings: Python 3.13. The requirements are read from `unused_lines_app/requirements.txt`
   (pinned) next to the entry point.
4. No secrets are needed: the app reads only the committed samples in `samples/unused_lines/`.
5. Deploy; open each page; check the figures in section 2.

Render stays on hold. The six-lever app (`app/`) and its deployment are unchanged.
