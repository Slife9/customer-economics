# Revision, Part C: the app redesigned for decision-makers

17 Nov 2026, branch `feature/unused-line-management` (not pushed, merged or deployed).

**Goal:** a stakeholder finds the decision-relevant information within seconds on every page.
No information was removed: it was reorganised into five decision pages and an analyst layer.

## What changed

### Views (C1)
- **Sidebar switch "Executive view / Analyst view"**, Executive by default. The switches write
  straight to session state, so changing view keeps the page's own selections.
- **Executive view:**
  - Plain labels with a one-line definition on hover (the ⓘ on each card).
  - Plain segment names ("Unused cards", "Occasional users", …) and the three plain actions.
  - No formulas, value-type badges, technical column names or wide tables.
  - The Explore & reference pages are hidden.
- **Analyst view:**
  - Everything, with the technical labels: Screened accounts, Carrying cost, Drawdown loss, Headline
    value, Go/no-go, Pending approval (B6), Capital released.
  - Formulas, value types and full tables.
  - Card profit alone and relationship-adjusted values (B6).
  - The B2 / B4 / B5 comparisons.
  - Explore & reference: What-if, Lever guide & regulation, Data & calibration, Technical.
- **One page template:**
  1. headline sentence generated from the results;
  2. at most four cards, one larger;
  3. one main chart;
  4. "What this means" (three takeaways of at most 20 words);
  5. "What to decide / do";
  6. Details tabs.
- **Status tiles** (traffic light with an icon and a word, never colour alone):
  - robustness (with its basis, B6);
  - fairness (module actions only);
  - data calibration (share of metrics in band; thresholds in config `presentation`);
  - rules assumed (March 2026 proposal);
  - decisions pending.
- **The five decision numbers, each with one home page** (`lib/results.py`):
  - problem and cost → Where the cost sits;
  - approved value and value awaiting decision → Actions and value;
  - red flags → Risks and checks.
- **Three plain actions:**
  - Trim unused limits (idle-line and risk-based decreases);
  - Wake up or close dormant cards (campaign, dormant right-sizing, closure, non-reissue);
  - Stop automatic increases.
  - Transactor right-sizing appears in the analyst view only.
- The assumption label stays in the sidebar on every page.

### Pages and navigation (C2)

| Page | View | Built from |
|---|---|---|
| Executive summary (landing) | both | new |
| Where the cost sits | both | Overview + Segments |
| Actions and value | both | Scenario dashboard |
| Risks and checks | both | Regulatory settings + stress + fairness |
| Customer evidence | both | Customer drill-down |
| What-if (levers & assumptions) | analyst | Levers & assumptions + the bank-profile toggles + the B2 / B5 / fairness settings |
| Lever guide & regulation | analyst | Lever guide (+ reason-code notice rules) |
| Data & calibration | analyst | Datasets & calibration |
| Technical | analyst | new: reconciliation (B4), workbook reproduction, value-type legend, methodology links |

**Executive summary:**
- Headline sentence; four cards (problem, cost of unused lines, approved value larger, awaiting
  decision), each linking to its home page.
- One horizontal bar chart of annual value by the three plain actions, coloured approved /
  awaiting decision / extra.
- The five status tiles.
- Decisions box: dormant-card actions (B6) with value; fair-lending review with the failing metros;
  pilot with a holdout.
- One line on one-time capital freed; links to every page.

**Where the cost sits:**
- Six compact group cards (plain name, accounts, annual loss, cost of unused lines, recommended
  action, value).
- One chart of holding cost vs expected losses by group.
- Details: full table, rules and thresholds, screen sensitivity, LEQ account vs workbook (B2,
  analyst).

**Actions and value:**
- Small scenario selector.
- One chart of annual value by action with year 1 alongside.
- The 5-column table (Action, Customers affected, Annual value, Year-1 value, Customers leaving).
- Details: by lever, by segment, how the value is built, the fixed-cost setting (B5), timing.

**Risks and checks:**
- Four tiles: robustness, fairness, rules assumed, notices required by reason code.
- The stress chart and one worked example.
- Details: notices by reason code, fairness by metro, parameters, current-rules comparison.

**Customer evidence:**
- A plain recommendation card, e.g. "Reduce limit from $52,000 to $39,000. Reason: rising credit
  risk. Adverse-action notice: required."
- Three key facts: unused amount, annual cost to the bank, drawdown risk.
- Review buttons (Agree / Disagree / Need more information, with a note) feeding the review-notes
  download, labelled "review notes, not an approval record". It covers this account or every
  account reviewed in the session.
- A "limit cut" example added beside typical / borderline / review together.
- Details: full calculation trace (with the PD-imputed flag and both LEQ values), transactor test
  month by month, rules met / not met, other worklists.

## Files changed
- **Rewritten app shell:**
  - `unused_lines_app/Home.py`: views, navigation, Executive view hides Explore & reference.
  - `lib/state.py`: view, term, `analyst_only`, alternative-setting runs, calibration.
  - `lib/style.py`: template pieces, status tiles, larger card.
  - `lib/guide.py`: plain names, terms, actions, notice rules.
- **New:**
  - `lib/results.py`: decision numbers, actions, tiles.
  - Pages `01_Summary.py`, `02_Cost.py`, `03_Actions.py`, `04_Risks.py`, `05_Customers.py`,
    `40_What_If.py`, `80_Technical.py`.
- **Updated:** `50_Lever_Guide.py`, `70_Data.py`.
- **Removed (content moved):** `05_Overview.py`, `10_Regulatory.py`, `20_Segments.py`,
  `30_Dashboard.py`, `40_Levers.py`, `60_Customers.py`.
- **Config:** `presentation.calibration_status` (status-tile thresholds; presentation only).
- **Tests:** `audit/audit_unused_line_module.py` section 11 runs every page in both views on both
  datasets, and checks that the Executive view has:
  - no value-type badges;
  - no technical labels on the decision pages;
  - the analyst-only pages gated.
- **Docs:**
  - `EVALUATION_GUIDE.md`: new page names, views and expected figures; the outdated "label, legend
    and synthetic note at the top of every page" check removed; example customers with the
    limit-cut example.
  - `docs/UNUSED_LINE_METHODOLOGY.md` ("Reading the app"), `ARCHITECTURE.md` §8b, `STATUS.md`,
    `unused_lines_app/README.md`.
- **Screenshots** of each decision page in the Executive view (stress book):
  `screenshots/01_executive_summary.jpg` … `05_customer_evidence.jpg`.

## Before / after headline figures (Part B, unchanged by Part C)

> **Update:** with the workbook LEQ as the B2 default (decided after this report), the "after"
> figures equal the "before" ones except the reason codes: stress book drawdown loss $1,633,129,
> Base +$175,389, pending +$519,808, 1.5× +$155,257; demo $9,926, +$817, +$4,376, +$635. The
> table below is the account-LEQ setting. Screenshots were retaken with the new default.

| | Stress book before | Stress book after | Demo before | Demo after |
|---|---|---|---|---|
| Screened accounts | 40,530 | 40,530 | 890 | 890 |
| Card profit | −$2,579,382 | −$2,579,382 | −$61,296 | −$61,296 |
| Carrying cost | $693,984 | $693,984 | $10,630 | $10,630 |
| Drawdown loss | $1,633,129 | $1,473,986 | $9,926 | $13,485 |
| Base annual value | +$175,389 | +$120,339 | +$817 | +$639 |
| Pending (B6) | +$519,808 | +$529,424 | +$4,376 | +$4,429 |
| 1.5× stress | +$155,257 | +$107,385 | +$635 | +$508 |

Each correction's own effect is in `REVISION_B_REPORT.md`.

## Checked in the browser (local, port 8504)
- Every decision page in the Executive view on the stress book (screenshots above).
- The Analyst view adds the Explore & reference group, formulas and value-type badges.
- A view switch keeps the page's selections (after a fix: the switch no longer forces a rerun that
  dropped page widget state).
- The review buttons keep their choice and add the session download.
- A direct link to an analyst page in a fresh session opens the Executive summary (the page is not
  in the Executive navigation).

## Tests run
`python audit/audit_unused_line_module.py --regression --bundle-100k … --frame-100k …
--frame-100k-json …`: **122/122 PASSED**. Log: `REVISION_C_AUDIT.txt`.
- **App:**
  - 36 page runs (9 pages × 2 views × 2 datasets) with no exception.
  - Executive view: no value-type badges, no technical labels on the decision pages, analyst pages
    gated.
  - Analyst view: every page shows its full content.
  - Peak **0.855 GB** in one process (was 0.63 GB; the analyst view also values the alternative
    fixed-cost setting).
- **Unchanged from Part B:**
  - Worked examples, workbook reproduction, B1–B6 checks, §2.7 cross-checks, 100k load test.
  - Generator byte identity (74/74) and engine regression.
- **Takeaways:** every "What this means" takeaway has at most 20 words on both datasets (longest:
  20).
