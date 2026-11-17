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
1. **Measure each account** over the last 12 months: line, balance, spend, payments, risk.
2. **Price the unused line**: carrying cost (capital + liquidity) and expected drawdown loss, kept in
   separate columns, never mixed under one label.
3. **Screen**: unprofitable cards (after the new capital and liquidity costs) that use under 30% of
   the line and have at least $5,000 unused.
4. **Segment** in the workbook's order: Credit-Deteriorating, Relationship / Premium, Dormant,
   Sock-Drawer, Low-Utilization Transactors, Unassigned.
5. **Value the levers** (line decreases, reactivation campaigns; dormant right-sizing and closures
   only once approved) with the workbook's customer responses, then propose an action per account
   with its reason code, notice and a pilot cell. The ML credit-limit model plays no part (decision B8).

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
- **Pending approval** (dormant right-sizing, closures, non-reissue) and **extra levers**
  (suppressing automatic increases) are valued in full but shown apart from the headline.
- **The stress book** is synthetic stress data tuned toward the workbook's population; the **5k
  demo** is the standard illustrative bank.

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
| `levers.py` | System-mode levers, response, scenarios, extra levers, stress test |
| `workbook.py` | Workbook-reproduction mode (the Calc sheets) |
| `treatment.py` | Recommendations, reason codes, notices, review-together, pilot, fairness, timing |
| `generator/unused_line_additions.py` | Table29 score history, Table30 card activation (additive, own random stream) |
| `generator/synth/unused_line_stress.py` | The `unused_line_stress` profile (synthetic stress data) |
| `unused_lines_app/` | Streamlit app on precomputed samples (`build_sample.py`) |
| `audit/audit_unused_line_module.py` | The acceptance suite (brief s.7) |

### Per account (exposure.py)
- `UCL = max(limit − balance, 0)`: 12-month average for cost, reporting date for actions.
- **Balances (B7):** Table4 `Ending Balance`, measured **after** the month's payment (the
  reporting-date balance). This is appropriate for regulatory exposure, which is measured at the
  reporting date; it slightly overstates the unused line of a pay-in-full customer, whose balance
  between payments is higher than the month-end figure. Statement balance (ending balance +
  payment) is used for the segment rules and the transactor test.
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
  - **LEQ (B2):** `drawdown_risk.leq_source`. `measured_account` (default): the account's Table9
    Behavioral CCF at the reporting date (EAD = balance + CCF × unused line: the same definition as
    LEQ, the share of the unused line drawn before default), the workbook segment LEQ when it is
    missing. `workbook_segment`: the workbook's LEQ per segment (Unassigned: the measured portfolio
    mean). On the synthetic data the Behavioral CCF has two values (0.42; 0.798 after a
    risk-deterioration limit event), so the default sets LEQ near 0.42 for every segment
    (`ISSUES_FOUND.md` #16).
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
screen: card profit < 0 (toggle: less drawdown loss), average utilisation < 30%, unused ≥ $5,000,
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
Protected (suppressed) customers are outside scope.

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

### Data
Table29 (score history) and Table30 (card activation) are synthetic additions: additive only, from
`SeedSequence(seed + 104729)`; every existing table is byte-identical. The score-drop rule and the
PD ≥ 4% rule are partly correlated by construction (both read Table8 PD). Investments and household
are approximated (deposits + Segment).

### Results on the committed samples (default settings)
| | Stress book (100k customers) | 5k demo |
|---|---|---|
| Screened accounts | 40,530 | 890 |
| Card profit | −$2,579,382 | −$61,296 |
| Carrying cost / drawdown loss | $693,984 / $1,473,986 | $10,630 / $13,485 |
| Base annual value (headline) | +$120,339 | +$639 |
| Capital released, one-time (Base) | $113,865 | $1,307 |
| Pending approval / extra levers | +$529,424 / +$199,599 | +$4,429 / +$2,906 |
| 1.5× stress | +$107,385 (go; card profit alone −$15,752) | +$508 (go; card profit alone −$248) |
| Base with `leq_source = workbook_segment` | +$175,389 | +$817 |
| Base with `fixed_cost_basis = workbook_segment` | +$152,405 (54,204 screened) | +$597 (1,011 screened) |

Reconciliation, calibration, issues and decisions: `specs/unused_line_management/` (STAGE1–8
reports, `ISSUES_FOUND.md`, `DECISIONS.md`, `EVALUATION_GUIDE.md`).
