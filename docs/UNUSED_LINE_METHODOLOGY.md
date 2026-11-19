# Unused Credit Line Management - methodology

The module behind `unused_lines_app/` and `engine/unused_lines/`. Part 1 is for business readers;
Part 2 is the technical reference. Every figure is an expected value under illustrative
assumptions; the recommended next step is always a pilot with a holdout.

> *Assumes the March 2026 Basel III endgame proposal is adopted as proposed; LCR outflow applied
> conservatively to all unused card lines. Capital ratio, cost of equity and carry are illustrative.*

---

## Part 1 - in plain language

### The question
Credit card lines that customers do not use still cost the bank money:

1. **Drawdown loss** - a customer in trouble may draw the line before defaulting.
2. **Capital** - under the March 2026 proposal (treated as adopted) 10% of every unused card line
   counts as exposure and needs capital.
3. **Liquidity** - the bank holds a buffer of liquid assets against unused lines (a conservative
   assumption: current law does not require it for cancellable card lines).

The module finds the card accounts where these costs make the card unprofitable, groups them like
the reference workbook (*Unused Line RWA Scenario Model*), values what line management could save,
and proposes an action per customer with the notices it would need.

### How it works, in five steps
1. **Measure each account** over the last 12 months: line, balance, spend, payments, risk. The
   balance behind the costs is the one outstanding during the month (the average of the
   statement-date and after-payment balances); usage for the selection is measured at statement date.
2. **Price the unused line**: carrying cost (capital + liquidity) and expected drawdown loss, kept in
   separate columns, never mixed under one label.
3. **Select**: cards that lose money (after the new capital and liquidity costs), use under 30% of
   the limit at statement date and have at least $5,000 unused.
4. **Group** in the report's order: customers at rising risk, relationship customers, unused cards,
   occasional users, pay-in-full customers, other.
5. **Value four strategies** built from the levers underneath: (1) right-size unused limits,
   (2) re-engage active low-use customers, (3) "use it or lose it" for dormant cards (invite, a 90-day
   warning with a choice, act, don't reissue), (4) stop automatic limit increases. Actions are valued
   on today's unused line with the workbook's customer responses; each customer gets an action with
   its strategy, reason code, notice and a pilot cell. The ML credit-limit model plays no part (B8).

### Reading the results
- **Annual value** = change in card profit + reduction in expected drawdown loss. This is the one
  figure executives see; card profit alone and the relationship-adjusted value are in the analyst
  view. The reduction in drawdown loss is usually the larger part.
- **Card profit** in this module is *card profit under the assumed capital rules*: the main
  engine's card profit with today's capital charge replaced by the March 2026 proposal's and the
  liquidity buffer cost subtracted. It differs from the main engine's card profit for the same
  customer; the analyst view reconciles the two step by step.
- **Capital released** is a one-time amount of capital freed up. It is never added to the annual
  value.
- **Status of each strategy**: Strategy 1 approved; Strategy 2 approved for testing only (it loses
  money at today's offer costs); Strategy 3's Invite approved, its actions awaiting a decision (B6);
  Strategy 4 proposed. The **approved value** values the approved steps together (customers who
  receive two actions are counted once), so the stand-alone values do not add up to it exactly.
  **Total potential** = approved + proposed + awaiting a decision.
- **The 90-day warning** (Strategy 3) is modelled with assumed response shares (resume use 10%,
  accept a lower limit 20%, close voluntarily 10%; the rest get the planned action), a $1 letter, and
  never a fee: assumptions to be tested in the pilot.
- **Pay-in-full right-sizing** is not recommended, by policy (low risk, a marginal saving, the risk of
  upsetting good customers). It shows a small gain in Base, partly because the engine's fixed-cost
  allocation is low; it is valued for analysts only.
- **The stress book** is synthetic stress data tuned toward the workbook's population; the **5k
  demo** is the standard illustrative bank (analyst view).

### Reading the app
The app follows the project report and the stakeholder slides (revision E). The **Executive view**
has nine pages in the report's order and words: *Executive summary*, *The problem*, *How unused
credit costs money* (the ACC-EXAMPLE worked example, $186.48 a year), *Customers and where the cost
sits*, *The four strategies*, *What they are worth*, *Implementation*, *Protecting customers and
risks*, *Customer evidence*. Each has one headline sentence, at most four figure cards, one main
chart and the detail in expanders; no PD / LGD / LEQ / RWA / LCR. The **Analyst view** (sidebar)
adds the dataset switch, the levers under each strategy, formulas, value types, full tables, the
reconciliation to the main engine's card profit, the workbook-reproduction panel and the What-if
settings.

### What to be careful about
- Customer responses (attrition, spend loss, campaign response) are the workbook's illustrative
  estimates, not measured on this portfolio.
- The four-fifths fairness test by metro on the module's own cuts and closures fails in some areas
  (metros with too few selected accounts show "insufficient sample"): a fair-lending review is needed
  before any pilot.
- Regulatory references are a summary for discussion, to be confirmed by compliance.

---

## Part 2 - technical reference

### Code map
| File | Role |
|---|---|
| `engine/unused_lines/config/unused_line_assumptions.json` | Agreed settings: regulatory, business, screen, segments, levers, treatment, timing, open-decision flags |
| `engine/unused_lines/config/workbook_model.json` | The workbook's inputs and Dashboard figures (`extract_workbook.py`; sha256 recorded) |
| `assumptions.py` | Load and validate (no 0% CCF, annual PD only, segment coverage); session overrides |
| `data.py` | The per-account file from the engine's card ledger (read only) and the published tables |
| `exposure.py` | Transactor test, risk weights, exposure, RWA, capital, liquidity, drawdown loss, profit views, current-rules comparison, workbook baseline |
| `segments.py` | Screen, rules, segments, rule trace, summaries, drawdown sensitivity |
| `levers.py` | System-mode levers, response, scenarios, extra levers, stress test, forward-looking frame |
| `strategies.py` | The four strategies built from the levers, the 90-day warning step, approved / proposed / awaiting totals |
| `workbook.py` | Workbook-reproduction mode (the Calc sheets) |
| `treatment.py` | Recommendations, reason codes, notices, review-together, pilot, fairness, timing |
| `generator/unused_line_additions.py` | Table29 score history, Table30 card activation (additive, own random stream) |
| `generator/synth/unused_line_stress.py` | The `unused_line_stress` profile (synthetic stress data) |
| `unused_lines_app/` | Streamlit app on precomputed samples (`build_sample.py`); executive and analyst views; `lib/results.py` holds the decision numbers and status tiles |
| `audit/audit_unused_line_module.py` | The acceptance suite (brief s.7) |

### Per account (exposure.py)
- `UCL = max(limit − balance, 0)`: 12-month average to explain past profit and cost; today's line
  and balance for forward-looking values (`balance_basis.lever_values = current`, revision E; the
  setting `average_12m` is the basis before it).
- **Balances (B7, revision E 1b):** Table4 `Ending Balance` is measured **after** the month's
  payment; `Statement Balance` (ending balance + payment made) is before it. Config `balance_basis`:
  - `cost = midpoint` (default): the drawn balance for costs is (statement + after-payment) / 2, the
    proxy for the balance outstanding during the month; `after_payment` is the basis before E. The
    after-payment balance overstates the unused line of a customer who pays in full.
  - `screen = statement_date` (default): the 30% test uses the 12-month average of statement balance
    / limit; `after_payment` is the basis before E.
  - The $5,000 unused test and the line-sizing floors keep the reporting-date balance. Statement
    balance is used for the segment rules and the transactor test, as before.
  - On the stress book: 289 cards leave the selection on the statement-date test; the higher
    midpoint balance raises the capital on drawn balances, so 951 near-break-even cards join it
    (40,530 → 41,192). The committed samples carry the six columns, computed from their own monthly
    file (`build_sample.py --update-balance-basis`).
- **Risk weight** (answer 5): 45% only if, over the last 12 cycles, every cycle was paid in full or
  had a $0 statement, not all 12 were $0, and there was no installment, promotional or BT balance,
  with at least 12 months of history; 100% if the customer's aggregate retail exposure (card
  balances + unused lines + loans) exceeds $1M; otherwise 75% (dormant zero-balance: config B5).
- `E = balance + CCF × UCL`; `RWA = E × RW`; capital `= RWA × 10.5%` (a stock); capital cost
  `= capital × 12%`.
- HQLA `= UCL × 5%` when liquidity applies (Category I–III by default, or `all_banks`); liquidity cost
  `= HQLA × 0.75%`.
- Drawdown loss `= PD × LGD × LEQ × UCL`, annual PD only:
  - **PD (B1):** Table8 `PD 12 Month` at the reporting date. A missing PD takes the average PD of
    the account's rule segment (accounts with a PD), then the portfolio average, flagged
    `pd_imputed`; a missing PD never means zero risk. Segment rules use the measured PD only. On
    the committed samples only closed or charged-off accounts lack a PD (none is screened).
  - **LEQ (B2):** `drawdown_risk.leq_source`. `workbook_segment` (default, until the bank has a
    measured LEQ): the workbook's LEQ per segment (Unassigned: the measured portfolio mean).
    `measured_account`: the account's Table9 Behavioral CCF at the reporting date (EAD = balance +
    CCF × unused line: the same definition as LEQ, the share of the unused line drawn before
    default), the workbook segment LEQ when it is missing. On the synthetic data the Behavioral CCF
    has two values (0.42; 0.798 after a risk-deterioration limit event), so `measured_account` sets
    LEQ near 0.42 for every segment (`ISSUES_FOUND.md` #16).
- **Carrying cost** = capital cost on the unused part + liquidity cost; **total unused-line cost** =
  carrying cost + drawdown loss.
- **Card profit under the assumed capital rules (B4)** = engine `card_net` + the old capital charge −
  the new capital cost − liquidity cost (the old charge is replaced, never added to); measured credit
  cost kept; drawdown loss beside it. `exposure.reconciliation()` shows each step from the main
  engine's card profit and checks it to the cent.
- **Fixed cost (B5):** `costs.fixed_cost_basis`. `engine_allocated` (default): the engine's
  `cost_to_serve_fixed_allocated` over 12 cycles. `workbook_segment`: the workbook's fixed cost per
  account by segment ($30–60; Unassigned: the segments' average weighted by their account counts),
  which lowers card profit by the difference. Fixed cost stays when an account leaves, so lever
  values change only through the screened population.

### Screen and segments (segments.py)
Rules run on every account (first match wins), LEQ follows the rule's segment, then costs, then the
screen: card profit < 0 (toggle: less drawdown loss), average utilisation < 30% (statement date by
default, `balance_basis.screen`), unused ≥ $5,000,
open ≥ 12 months, open and not charged off, no recent fraud-compromise event (proxy). Each rule keeps
value, threshold and met / not met. The segmentation transactor rule (≥ 10 of 12, $0 statement
counts as nothing due) is not the regulatory test.

### Levers (levers.py), system mode
Selection per scenario and segment from the workbook's shares (decreases on the largest unused lines,
deteriorating on the highest PD; campaigns in a seeded order; closures on the longest inactive).
Line sizing: Lever Guide targets, new line ≥ max($500, balance × 1.2), cut ≤ 25% per review (one in
year 1), ≥ 15% and ≥ $500 or no cut. Per account, in expected values: survivors keep the new line,
lose spend × spend loss and take the PD uplift; leavers lose variable contribution (card profit +
fixed cost) and relationship profit, fixed cost stays; closures only if not reactivated (inactive
≥ 24 months, B6); campaign responders add spend and revolving balance and move from 45% to 75%.
Stress: attrition, spend loss and PD uplift × multiplier, response ÷ multiplier. Value types:
avoided loss, cost saving, revenue, lost profit. Capital released `= −ΔRWA × 10.5%`, one-time.
Protected (suppressed) customers are outside scope. Values run on `levers.forward_frame` (today's
unused line; the `now_*` columns built by `segments.build`). Pay-in-full (transactor) right-sizing is
valued but outside the approved total (`transactor_rightsizing_in_approved_value = false`, 1c); before
revision E it was inside it although never recommended, and made up $14.4k of the $175,389 and most
of the "$23.0M removed, 214 leaving, $114k capital freed".

### Strategies (strategies.py, revision E)
Config `strategies`: each strategy is a list of steps, each step levers × segments, with a status.

| Strategy | Steps (levers, groups) | Status |
|---|---|---|
| 1 Right-size unused limits | risk-based decrease (rising risk); line decrease (occasional users; relationship) | approved |
| 2 Re-engage active low-use | engagement campaign (occasional users, pay-in-full, relationship) | approved: test only |
| 3 "Use it or lose it" | Invite = engagement campaign (unused cards); right-size, close, don't reissue, each after the 90-day warning | Invite approved; actions follow the B6 flags (awaiting decision) |
| 4 Stop automatic increases | suppress automatic increases | proposed |

- Per-account effects come from `levers.run` (same scenario and multiplier); a lever's effect is
  split by group where it serves two strategies (the campaign), exactly.
- **The warning (config `warning`):** every unused card selected for a Strategy 3 action is warned,
  except Invite responders (the action is weighted by 1 − Invite response). Of those warned:
  `resume_use` keeps the card and earns the reactivation responder's spend and balance with no offer
  costs (`levers.value(..., offer_costs=False)`); `accept_lower_limit` gets the right-sizing cut with
  no attrition, spend loss or PD uplift; `close_voluntarily` closes (the whole line removed); the
  rest get the planned action. Each letter costs `letter_cost_usd`. `min_use_to_reset` decides who
  counts as resumed (default: $100 of spend in the 90 days). `assumptions.validate` refuses any fee in
  the warning settings. `warning.enabled = false` gives the stand-alone actions (before E).
- **Reporting:** per strategy the stand-alone annual value and its components, status, customers,
  leavers, unused removed and capital freed (one-time); the **approved combined** value (the approved
  steps valued together by `levers.value`, plus warned steps if B6 is approved); **proposed**,
  **awaiting decision** and **total potential**. With the defaults the approved combined value
  equals the levers' combined headline exactly.

### Workbook-reproduction mode (workbook.py)
The Calc sheets on the workbook's own inputs; the multiplier scales attrition and spend loss only.
Reproduces the Dashboard to the cent (Base +$1,329,136.92, 8,470 accounts lost).

### Treatment (treatment.py)
Reason codes (B3), one per lever, each with its notice rule in `treatment.reason_codes`:

| Action | Reason code | Notice |
|---|---|---|
| Idle-line decrease | `IDLE_LINE_RIGHTSIZING` | Adverse-action notice unless an exception applies; flagged for compliance |
| Risk-based decrease | `CREDIT_DETERIORATION` | Adverse-action notice; FCRA score check |
| Dormant right-sizing / closure | `INACTIVITY` | No adverse-action notice (Reg B inactivity exception) |
| Non-reissue of a dormant card | `INACTIVITY_NON_REISSUE` | As INACTIVITY; flagged for compliance confirmation |
| Reactivation / engagement campaign | `ENGAGEMENT_CAMPAIGN` | None (no change to terms) |
| Suppressing automatic increases | `SUPPRESS_AUTO_INCREASE` | None expected; flagged for compliance confirmation |

`OTHER` remains only for an action no code covers (target below 1% of actions; none today).
45-day fee / penalty-rate restriction after a decrease; no inactivity fee. The ML credit-limit model is not used (decision B8). Four-fifths by metro on the module's own
actions only: decreases and closures (and increases, if the module ever produces any; it produces
none today). A metro with fewer than `treatment.fairness.min_selected_per_group` (30) selected
accounts shows "insufficient sample" instead of pass / fail. Review-together flags from the L1 / L3 /
L5 worklists. Pilot: 10% holdout, seeded, stratified by segment. Timing: year-1 share per lever.
Each action records its strategy (`strategy`, `strategies`) and whether the 90-day warning comes
first (`warning_required`: every Strategy 3 action). The four-fifths test flags an area selected
*less* often than the comparison rate; for cuts and closures the usual concern is the opposite, so
the fair-lending review should decide the method (`ISSUES_FOUND.md` #10).

### Data
Table29 (score history) and Table30 (card activation) are synthetic additions: additive only, from
`SeedSequence(seed + 104729)`; every existing table is byte-identical. The score-drop rule and the
PD ≥ 4% rule are partly correlated by construction (both read Table8 PD). Investments and household
are approximated (deposits + Segment).

### Results on the committed samples (default settings, revision E)
| | Stress book (100k customers) | 5k demo |
|---|---|---|
| Cards selected | 41,192 | 890 |
| Card profit | −$2,513,594 | −$60,626 |
| Carrying cost / drawdown loss | $692,639 / $1,625,466 | $10,465 / $9,754 |
| Strategy 1 / 2 / 3 / 4 (each on its own) | +$194,980 / −$17,281 / +$494,482 / +$193,704 | +$1,248 / −$282 / +$4,182 / +$2,573 |
| Approved (combined) | +$156,105 | +$715 |
| Proposed / awaiting a decision | +$193,704 / +$516,234 | +$2,573 / +$4,438 |
| Total potential | +$866,043 | +$7,726 |
| Capital freed, one-time (approved) | $58,774 | $1,334 |
| 1.5× stress (approved) | +$133,872 (card profit alone −$33,253) | +$498 (card profit alone −$478) |
| Approved with `leq_source = measured_account` | +$94,693 | +$514 |
| Approved with `fixed_cost_basis = workbook_segment` | +$191,709 (54,666 selected) | +$627 (1,005 selected) |

Every revision-E setting switched back to its old value reproduces the figures before E exactly
(stress book: 40,530 selected, +$175,389). Before / after for every report figure:
`specs/unused_line_management/FIGURES_CHANGED_SINCE_REPORT.md`.

Reconciliation, calibration, issues and decisions: `specs/unused_line_management/` (STAGE1–8
reports, `ISSUES_FOUND.md`, `DECISIONS.md`, `EVALUATION_GUIDE.md`).
