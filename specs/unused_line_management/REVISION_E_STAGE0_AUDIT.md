# Revision E, Stage 0: audit against the project report and slides

19 Nov 2026, branch `feature/unused-line-management` at `ed39f3a`. No code changed in this stage.
References: `Unused_Credit_Line_Management_Project_Report.docx` (report) and
`Unused_Credit_Line_Strategy_v2.pptx` (slides), both read in full. Figures below were reproduced
from the current code on the committed 100k stress sample (`samples/unused_lines/stress`), Base
scenario, current defaults.

## 1. State of the earlier corrections

| | Correction | Implemented? | Current default | Note |
|---|---|---|---|---|
| B1 | Missing PD → segment average | Yes (`exposure.pd_used`, `pd_imputed` flag) | `drawdown_risk.missing_pd = segment_average` | 3,543 accounts imputed on the stress book, all closed or charged off, **none selected**, so no figure moves. The report's "currently count as zero risk" is out of date |
| B2 | Measured LEQ (Table9 Behavioral CCF) | Yes, as a switch (`exposure.leq_columns`) | `drawdown_risk.leq_source = workbook_segment` | Applied and **left off by your decision of 17 Nov**. The meaning matches LEQ (generator: EAD = drawn + undrawn × CCF), but on this synthetic data it is a generator parameter with two values (0.42; 0.798 after a risk-deterioration event), not measured behaviour. Switched on, the stress-book Base value falls from +$175,389 to +$120,339 (`ISSUES_FOUND.md` #16) |
| B3 | Specific reason codes | Yes (one notice rule per code; validation) | Six specific codes; `OTHER` limit 1% | `OTHER` = **0%** of actions (stress book) |
| B4 | Card-profit reconciliation | Yes (`exposure.reconciliation`, analyst Technical page) | Label "card profit under the assumed capital rules" | Reconciles to the cent: −$2,000,170 + $124,981 − $489,183 − $215,011 = −$2,579,382 |
| B5 | Fixed-cost setting | Yes (`costs.fixed_cost_basis`) | `engine_allocated` | Alternative `workbook_segment`: Base +$217,245 (54,204 selected). The engine allocation is **$2.91** per selected card on the stress book (the report's "about $17" is the 10k book) |
| B6 | One headline basis | Yes (one value: card-profit change + lower expected loss; generated robustness sentence) | n/a | "Passes at 1.5x on value including reduced risk; card profit alone is negative already at 1x" |
| B7 | Balance note | Note only (methodology, `exposure.py` docstring) | Balances after payment | No calculation change yet: that is Stage 1b |

## 2. Report figures reproduced (stress book, Base)

| Figure | Report | Current app | Match |
|---|---|---|---|
| Cards selected / open cards | 40,530 / 88,232 (45.9%) | 40,530 / 88,232 | ✅ |
| Unused credit | $573,363,462 ($14,147 per card) | $573,363,462 ($14,147) | ✅ |
| Card profit | −$2,579,382 | −$2,579,382 | ✅ |
| Carrying cost (capital / liquidity) | $693,984 (≈ $0.48M / $0.22M) | $693,984 ($478,973 / $215,011) | ✅ |
| Expected drawdown loss | $1,633,129 | $1,633,129 | ✅ |
| Per $1,000 unused: hold / expected loss | $1.21 / $2.85 | $1.21 / $2.85 | ✅ |
| Groups | 1,460 / 5,513 / 15,076 / 6,139 / 6,337 / 6,005 | same | ✅ |
| Cost by group (unused, hold, drawdown, total, profit) | report table | same to $0.01M | ✅ |
| Rising risk: PD only / score only / both; average PD | 721 / 477 / 262; 10% | 721 / 477 / 262; 9.96% | ✅ |
| Relationship: other products / deposits / Premier; earnings each | 4,763 / 3,315 / 4,012; ≈ $1,270 | 4,763 / 3,315 / 4,012; $1,268 | ✅ |
| Unused cards: months since last use | ≈ 31 | 30.6 | ✅ |
| Occasional users: active months, spend | ≈ 2, $915 | 2.0, $915 | ✅ |
| Pay-in-full: spend, busiest month | ≈ $11,500, 9% | $11,487, 8.6% | ✅ |
| Other: busiest month ≥ 15% / spend < $6,000 | 2,874 / 3,905 | 2,874 / 3,905 | ✅ |
| ACC-EXAMPLE: capital / liquidity / carrying / drawdown / total | $13.23 / $5.25 / $18.48 / $168.00 / $186.48 | same | ✅ |
| ACC-EXAMPLE capital at 45% | $7.94 | $7.94 | ✅ |
| Approved value | $175,389 | $175,389 (drawdown −$184,998; card profit −$9,609) | ✅ |
| Range cautious – bold | $126k – $211k | $125,670 – $210,933 | ✅ |
| 1.5× stress | $155k | $155,257 | ✅ |
| Leavers / unused removed / capital freed | 214 / $23.0M / $114k | 213.8 / $23,016,724 / $113,865 | ✅ |
| Proposed (stop automatic increases) | $191,794 | $191,794 | ✅ |
| Awaiting decision | $519,808 | $519,808 | ✅ |
| Share of the limit used at statement date | about 5% | 4.5% ($26.0M of $574.4M) | ✅ |
| Cards with no statement balance all year | about 40% | 40.9% | ✅ |
| Unused credit if measured at statement date | −4.4% | −4.35% | ✅ |
| Selected cards using 30%+ at statement date | **294** | **289** | ❌ (5 fewer; same under every definition tried) |
| Fairness: areas failing | **12 of 64** | **2 of 76** (68 pass, 6 insufficient sample); 6 of 76 with no minimum sample | ❌ stale: 64 metros was the old 10k book (`ISSUES_FOUND.md` #10) |

## 3. Strategy stand-alone values (Base)

| Strategy | Report | Current levers | Match |
|---|---|---|---|
| 1. Right-size unused limits | ≈ $199k (rising risk $152k + idle lines $47k) | $151,676 + $47,340 = **$199,016** | ✅ |
| 2. Re-engage active low-use | ≈ −$38k | campaign, all groups: **−$38,197** | ✅, but see below |
| 3. Use it or lose it (actions) | ≈ $520k ($86k + $236k + $198k) | $86,103 + $236,188 + $197,517 = **$519,808** | ✅ |
| 4. Stop automatic increases | ≈ $192k | **$191,794** | ✅ |

**The −$38k includes the dormant-card invite.** By group, the campaign is: unused cards −$21,752,
pay-in-full −$6,737, occasional users −$6,497, relationship −$3,211. Once Stage 2a splits it,
Strategy 2 becomes about **−$16.4k** and Strategy 3's Invite step about **−$21.8k**. The approved
$175k doesn't change, because it already includes both.

Pay-in-full right-sizing (not recommended) is **+$14,289** in Base. The lever label still says
"shown to demonstrate it loses money" (`levers.py` LEVER_LABELS): Stage 1c removes that wording.

## 4. App content that is not in the report or slides

| Item (where now) | Proposal |
|---|---|
| Dataset switch with the 5k demo (sidebar, both views) | Analyst only; the Executive view stays on the stress book, as in the report |
| Scenario switch Conservative / Base / Aggressive (Actions page) | Analyst; the Executive view shows the range row |
| Year-1 value card and the Timing tab (year-1 shares) | Analyst; replaced by the report's 15-month timeline |
| "Value of approved actions" per group on the segment cards | Remove from Executive (the report values strategies, not groups); by-group table stays in Analyst |
| Screen sensitivity tab (expected loss counted in the screen) | Analyst |
| Robustness curve 1× – 2× (Risks page main chart) | Analyst; Executive shows the 1.5× figure in the value table |
| Status tiles for calibration and "decisions pending" (B4–B7 codes) | Calibration → Analyst. Pending tile → the report's "What is needed" card and "pending corrections" list |
| Notice counts (e.g. 2,506 adverse-action notices) | In an expander under the rules table |
| Dormant $10,000 worked example | Replaced by ACC-EXAMPLE; the three regression examples stay in tests and Technical |
| Current-rules tab with SLR figures | Executive: the report's 4-row current-law table; SLR figures Analyst |
| "Increases" fairness note (the module has no increases) | Remove |
| Review radio (Agree / Disagree), notes, CSV downloads, "Other worklists" (L1/L3/L5) on Customer evidence | Analyst (pilot review tools; not in the report) |
| Dormant confirmation signals (card not activated, due for reissue, no app use) | Analyst trace |
| Relationship-adjusted values, value types legend, fixed-cost and LEQ switches, bank profile, full line-management scope | Analyst (most already are) |
| Plain name "Valuable relationship customers" | Rename "Relationship customers" (report wording) |

## 5. Points where the report and the app will differ after Stage 1–2

- Fairness: the report says 12 of 64 areas; the module says 2 of 76 (6 insufficient sample).
  The slides and report need the current figure.
- Fixed cost: "about $17 per account" is the 10k book; the stress book is $2.91.
- Pending corrections: B1 and B3 are already done; B2 is done but switched off.
- Strategy 2 falls to about −$16k once the dormant invite moves to Strategy 3.
- Stage 1b lowers unused credit used for costs by about 2.2% (midpoint balance), takes 289 cards
  out of the selection, and values actions on today's unused line, which is 3.8% above the
  12-month average. Carrying cost, drawdown loss and every strategy value will move.
