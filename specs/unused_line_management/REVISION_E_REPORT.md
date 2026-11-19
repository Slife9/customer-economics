# Revision E: simplify the system to match the slides and the project report

19 Nov 2026, branch `feature/unused-line-management` (not pushed, merged or deployed). Reference documents:
`Unused_Credit_Line_Strategy_v2.pptx` and `Unused_Credit_Line_Management_Project_Report.docx`, both read
in full. Stage 0 (audit, approved on the recommendations): `REVISION_E_STAGE0_AUDIT.md`.

Commits: `467c16d` (Stages 1–2), `f028322` (Stage 3), then the Stage 4 documentation. Every new
setting is in `engine/unused_lines/config/unused_line_assumptions.json` with its default, and its old
value kept as an option. Nothing outside the module, its app, samples, tests and docs changed (suite
guardrail).

## Stage 1: calculation corrections

**1a.** B1 (missing PD) and B3 (reason codes) were already done. B2 stays the workbook LEQ, as decided:
Table9's Behavioral CCF has the meaning of LEQ, but on this data it is a two-value generator parameter
(0.42 / 0.798), not measured behaviour.

**1b. Balance basis** (`balance_basis`):

| Setting | Default (new) | Old value (option) |
|---|---|---|
| `screen` (the 30% test) | `statement_date`: 12-month average of statement balance / limit | `after_payment` |
| `cost` (drawn balance behind every cost) | `midpoint`: (statement + after payment) / 2 | `after_payment` |
| `lever_values` (forward-looking values) | `current`: today's line and balance on the cost basis | `average_12m` |

- `data.balance_basis_columns` builds six columns per account. The committed samples gained them from
  their own monthly file (`build_sample.py --update-balance-basis`), with every existing column byte
  for byte the same (checked). The 100k per-account file was rebuilt from the raw portfolio (199 s,
  15.6 GB).
- `segments.build` keeps today's costs as `now_*` columns; `levers.forward_frame` values every lever on
  them. Past profit and the cost picture keep the 12-month average.

**1c.** Pay-in-full right-sizing stays out of the recommendations by policy, and is now also out of the
approved value (`transactor_rightsizing_in_approved_value = false`). Before, the approved $175,389
included $14.4k from cutting 944 pay-in-full limits, which the recommendations never contained. The
"shown to demonstrate it loses money" wording is gone (it shows +$15.6k in Base, partly because the
engine's fixed-cost allocation is low).

**Effect, one setting at a time (stress book, Base):**

| Step | Selected | Approved value | Unused removed | Leavers | Capital freed |
|---|---|---|---|---|---|
| Old settings | 40,530 | +$175,389 | $23.02M | 214 | $113,865 |
| + pay-in-full cuts out of the approved value | 40,530 | +$160,977 | $13.99M | 138 | $55,784 |
| + statement-date screen | 40,241 (−289) | +$159,490 | $13.86M | 137 | $54,912 |
| + midpoint balance for costs | 41,192 (+951) | +$158,970 | $13.91M | 138 | $56,382 |
| + today's unused line for values | 41,192 | +$156,105 | $14.11M | 138 | $58,774 |

The midpoint balance raises the drawn balance, so the capital on it rises and 951 near-break-even cards
become loss-making. The brief expected only the ~294 cards leaving; see open question 1.

## Stage 2: four strategies

- `engine/unused_lines/strategies.py`, config `strategies`. Each strategy is a set of steps (levers ×
  groups) with a status. The levers stay underneath, in the Analyst view.
- **2a.** The campaign splits exactly by group: unused cards → Strategy 3's Invite, everyone else →
  Strategy 2 (audit-checked).
- **2b. The 90-day warning** (config `warning`, labelled "assumption; to be tested in the pilot"):
  - Notice: 90 days.
  - Responses: resume use 10%, accept a lower limit 20%, close voluntarily 10%; the rest get the
    planned action.
  - Reset rule: $100 of spend in 90 days.
  - Letter: $1.
  - Value of each response: resumed use earns the reactivation responder's spend and balance without
    offer costs; a lower limit removes the right-sizing cut, with no attrition, spend loss or risk
    uplift; closure removes the whole line.
  - Invite responders are not warned, so the actions are weighted by 1 − Invite response.
  - `assumptions.validate` refuses any fee in the warning settings.
- **2c.** For each strategy the system reports:
  - stand-alone value and components, status, customers, leavers, unused removed, capital freed
    (one-time);
  - the combined approved value, valued together;
  - proposed, awaiting decision and total potential.
- `treatment.design` records each action's strategy, and whether the warning comes first.

## Before / after (Base; "old" = every revision-E setting at its old value, which reproduces Stage 0 exactly)

**Stress book**

| | Old (= report) | Stage 1 (warning off) | Stage 2 (all defaults) |
|---|---|---|---|
| Cards selected | 40,530 | 41,192 | 41,192 |
| Unused credit | $573,363,462 | $572,837,099 | $572,837,099 |
| Carrying cost | $693,984 | $692,639 | $692,639 |
| Expected drawdown loss | $1,633,129 | $1,625,466 | $1,625,466 |
| Strategy 1 | +$199,016 | +$194,980 | +$194,980 |
| Strategy 2 (without the Invite) | −$16,445 (report: −$38k incl. Invite) | −$17,281 | −$17,281 |
| Strategy 3 Invite | −$21,752 | −$21,752 | −$21,752 |
| Strategy 3 actions | +$519,808 | +$525,989 | +$516,234 |
| Strategy 4 | +$191,794 | +$193,704 | +$193,704 |
| Approved (combined) | +$175,389 | +$156,105 | +$156,105 |
| 1.5× stress (approved) | +$155,257 | +$133,872 | +$133,872 |
| Total potential | +$886,991 | +$875,798 | +$866,043 |

**5k demo**

| | Old | Stage 1 | Stage 2 |
|---|---|---|---|
| Cards selected | 890 | 890 | 890 |
| Unused credit | $8,726,729 | $8,588,767 | $8,588,767 |
| Carrying / drawdown | $10,630 / $9,926 | $10,465 / $9,754 | $10,465 / $9,754 |
| Strategies 1 / 2 / Invite / 3 actions / 4 | +$1,325 / −$271 / −$256 / +$4,376 / +$2,568 | +$1,248 / −$282 / −$256 / +$4,446 / +$2,573 | +$1,248 / −$282 / −$256 / +$4,438 / +$2,573 |
| Approved | +$817 | +$715 | +$715 |
| 1.5× stress | +$635 | +$498 | +$498 |

Strategy 3's actions with the warning (stress book): right-sizing +$86k → **+$163k** (voluntary
closures and accepted cuts without attrition), closure +$239k → **+$194k** and non-reissue +$201k →
**+$159k** (customers who keep their card). 13,823 letters.

Figures: `figures/E0_old_settings.json`, `E1_stage1.json`, `E2_stage2_defaults.json`,
`E3_measured_leq.json`, `E3_workbook_fixed_cost.json`, `E_report_figures_stress.{md,json}`.

## Stage 3: the app

- **Executive view (the report's order):**
  - Pages: Executive summary · The problem · How unused credit costs money · Customers and where the
    cost sits · The four strategies · What they are worth · Implementation · Protecting customers
    and risks · Customer evidence.
  - Always on the stress book.
  - One headline sentence, at most four cards, one main chart, detail in expanders.
  - No PD / LGD / LEQ / RWA / LCR.
- **Analyst view:**
  - The dataset switch, What-if (every new setting), Levers & lever guide (every lever with its
    strategy and stand-alone value), Data & calibration, Technical.
  - Extra expanders on the report pages.
- **Moved to the Analyst view** (as approved at Stage 0): the scenario switch, year-1 timing, the 1×–2×
  curve, the calibration tile, the review and download tools.
- **Removed:** the per-group value of approved actions and the "increases" fairness note.
- **Renamed:** "Valuable relationship customers" is now "Relationship customers".
- **Config additions:** the ACC-EXAMPLE inputs (`presentation.worked_example`) and the 15-month plan
  (`implementation`). No page writes a rate.
- **Two corrections found while checking the pages in the browser:**
  - The report's "most of the value is lower expected loss" holds for the approved value (all of it),
    but not for the total potential (52%). The sentence is now generated from the numbers.
  - The fairness chart showed 70 unnamed dots. It now shows the 15 lowest areas against the
    four-fifths line.
- Screenshots (Executive view): `screenshots/E01_summary.jpg` – `E05_strategies.jpg`,
  `E09_evidence.jpg`. The browser's capture tool was unreliable for the remaining three pages; they
  were checked on screen and by the suite.

## Stage 4: tests and documentation

**Tests actually run:**

| Run | Code | Result | Log |
|---|---|---|---|
| Full suite with `--regression`, 100k bundle and the rebuilt 100k file | `467c16d` (Stages 1–2) | 141/142 PASSED. The one failure was the new 1c check itself: on the 10k book some pay-in-full cards also get the campaign, whose balance removes some unused credit; the check took that for a cut. Rewritten to compare the approved value with the same calculation without pay-in-full cuts | `REVISION_E_STAGE12_AUDIT.txt` |
| Full suite with `--regression`, same inputs | `f028322` (Stage 3) | **144/144 PASSED** | `REVISION_E_AUDIT.txt` |
| AppTest: 13 pages × 2 views × 2 datasets, jargon scan | working tree before `f028322` | 52 runs, 0 exceptions, no jargon in the Executive view | – |

**The checks the brief asked for (all in the 144/144 run):**

| Check | Result |
|---|---|
| Worked examples $13.20 / $10.56 / $7.54; ACC-EXAMPLE $186.48 (capital $7.94 at 45%) | PASS |
| Workbook reproduction +$1,329,137; 8,470 leaving | PASS |
| Every new setting at its old value reproduces the Stage 0 figures exactly (stress book and demo) | PASS |
| Strategy values add up to their components | PASS (both generated portfolios) |
| Capital freed never added to annual value | PASS |
| The warning step never creates a fee | PASS (a fee setting is refused; letters cost only their configured amount) |
| OTHER below 1% | PASS (0%) |
| Byte-identity of existing generator outputs | PASS (74/74; 197 files) |
| Memory ≤ 2 GB on the committed samples | PASS (0.855 GB, every page, both views, both datasets) |

**Documentation updated:**
- `docs/UNUSED_LINE_METHODOLOGY.md`: balance basis, strategies, warning, results.
- `EVALUATION_GUIDE.md`: rewritten for the nine pages and the new figures.
- `STATUS.md` and `unused_lines_app/README.md`.
- `DECISIONS.md` (revision E), `OPEN_DECISIONS.md` (E1, the warning's assumptions).
- `ISSUES_FOUND.md`: #9, #10, plus new #18 (report statements) and #19 (pay-in-full cuts in the
  approved value).
- **`FIGURES_CHANGED_SINCE_REPORT.md`**: every headline figure that moved, old vs new, with its cause.
- New script: `audit/unused_line_report_figures.py`, which computes every report figure before and
  after.

## Open questions
1. **The midpoint balance brings 951 cards in.** The brief expected about 294 cards to leave. The
   midpoint also raises the capital on drawn balances, so the selection grows from 40,530 to 41,192.
   The alternative is to apply the midpoint to the unused line only, keeping the after-payment balance
   for drawn capital: then only the 289 would leave. Keep the midpoint for both (as specified)?
2. **The approved value falls to $156k**, mostly because pay-in-full cuts are now out of it (1c). Agree
   that the approved figure should match the recommendations?
3. **The warning raises right-sizing and lowers closure and non-reissue** (net Strategy 3 actions
   $516k vs $526k without it). The response shares are placeholders; confirm them, or give the
   pilot's targets.
4. **Strategy 3 is valued as a journey**: Invite responders are not warned. The report's $520k was
   each action on its own, without the Invite. Keep the journey basis?
5. Push and redeploy: not done; on request only.
