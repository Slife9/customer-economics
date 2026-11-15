# BRIEF: Build the Unused Credit Line Management module (L2 deep-dive)
## ProfitInsight Customer Economics System

This brief hands over everything agreed in the design discussions, so you can build the module
without re-deriving decisions. Read it fully, together with the other files in this package and the
attached workbook `Unused_Line_RWA_Scenario_Model.xlsx`, before writing code.

| File in this package | Purpose |
|---|---|
| `SPEC_unused_line_management.md` | This brief: background, agreed decisions, design, data, stages, tests |
| `unused_line_assumptions.json` | Every agreed setting (regulatory, business, scenario) in one config |
| `REGULATORY_RESEARCH_SUMMARY.md` | Verified regulatory findings with sources, and the working assumptions that override them |
| `OPEN_DECISIONS.md` | Decisions still pending, with the default to build in meanwhile |

Inspect the current repository first. It has changed during the project (lever valuation rebuild,
results bundle, the L1 Rewards module, reward data additions). Trust the code over this brief where
they differ, and report every difference that affects the plan.

---

## 0. How to work

1. Run `git status` and `git branch -a`. Stop and report any uncommitted changes.
2. Report which feature branches exist and whether they are merged into `main`:
   - `feature/lever-valuation-rebuild`
   - `feature/reward-data-additions`
   - the L1 Rewards module branch
   - any docs branches

   **Ask me which branch to start from** if `main` does not contain the L1 Rewards module.
3. Create `feature/unused-line-management` from the agreed base. Never commit to, merge into or push
   to `main`. Commit after every stage.
4. Copy this package into `specs/unused_line_management/` as the first commit.
5. **Follow the L1 Rewards module as the template.** It has the same structure: a dedicated engine
   and dedicated pages (overview, segments, scenario dashboard, levers & assumptions, customer
   drill-down, lever guide & regulation), all driven by a workbook-style scenario model. Reuse its
   patterns, components and styling rather than inventing new ones.
6. Report after every stage. Stop and ask when the code contradicts this brief.

---

## 1. Background

### 1.1 What exists today (verify in code)
- **L2 "Line Management by Value"** in `engine/levers/l2_lines.py` sorts card customers, using
  12 months of behaviour, into four groups:

  | Group | Rule | Action |
  |---|---|---|
  | Healthy | Pay-in-full, active | Leave alone (`DEEPEN_RELATIONSHIP_NO_LIMIT_CHANGE`) |
  | Dormant | Inactive | `REACTIVATION_CAMPAIGN`, never cut |
  | Idle line | Genuinely unused line | `DECREASE_LIMIT` |
  | Stretched | Uses most of the line, pays reliably | `INCREASE_LIMIT` |

  - No action before 12 months of history.
  - Decrease target = max(1.5 × peak 12-month balance, 110% × 12-month spend), floor $300.
- **The ML credit-limit model** (`engine/ml/`) gives an independent recommendation per card customer
  (maintain, decrease unused, freeze, increase, manual review), with reductions capped at 25% per
  review. Its treatment-fairness test currently fails the four-fifths rule in 5 metro areas on the
  100k run.
- **Liquidity and leverage diagnostics** exist (`annual_liquidity_cost`, `leverage_capital_cost`
  columns, configs `liquidity_policy.json`, `leverage_capital_policy.*.json`). They encode the
  **old** assumptions (4% yield gap; SLR Case A / Tier-1 Case B). **Do not use them for this module.**
  This module replaces that logic with §2.

### 1.2 Why a dedicated module
The workbook `Unused_Line_RWA_Scenario_Model.xlsx` shows unused lines carry three costs:
1. **drawdown credit loss**, the largest
2. **capital**
3. **liquidity**

It also shows they can be managed with segment-specific levers. As with rewards, the agreed approach
is a **dedicated module** with its own engine and pages that reproduces the workbook's logic on the
system's customer-level data, corrects the workbook's regulatory assumptions (§2), and integrates
with L2 and the ML model.

### 1.3 The workbook in brief (read the file for exact values)
- **Population:** 93,000 unprofitable card accounts with utilisation < 30% and unused line ≥ $5,000.
  Baseline loss about −$9.04M a year; unused lines about $1.30B.
- **Segments**, priority order (read exact rules from its *Segment Definitions* sheet):
  1. Credit-Deteriorating Low-Use
  2. High-Line Relationship / Premium
  3. Dormant / Inactive
  4. Sock-Drawer Occasional Users
  5. Low-Utilization Transactors
  6. Unassigned
- **Cost of an unused line:**
  - drawdown expected loss = annual PD × LGD × LEQ × unused
  - capital = RWA × capital ratio × cost of equity
  - liquidity = unused × LCR outflow × negative carry
- **Levers:** line decreases with a floor (never below balance plus headroom), closures (dormant,
  after reactivation), engagement campaigns (extra spend and revolving balance, minus incentive and
  promo cost). Customer response: attrition and spend change.
- **Scenarios:** Conservative / Base / Aggressive, plus a stress test.
  - Base: about +$1.33M, about 8,470 accounts lost (9.1%), mostly dormant closures.
  - Transactor line cuts lose money (−$8k), which agrees with L2's "leave healthy alone".
  - Even Aggressive leaves the population loss-making: line management fixes only part of the loss.

### 1.4 Known workbook issues to correct (do not reproduce them)
| Workbook | Correct treatment |
|---|---|
| Risk weights 85% / 55% (2023 proposal), assigned per segment | **75% / 45% (March 2026 proposal), assigned per account** by the transactor test (§2.2) |
| Dormant segment at 85% | **75%** (no repayment history, so not a transactor) |
| "Capital released" shown beside profit change | Capital released is a **one-time stock**; the annual saving is already in profit. **Never add them** |
| Internal-model (IRB) regime | Not a regulatory scenario (the proposal removes advanced approaches for credit risk). At most an optional internal economic-capital view |
| Inactivity fees prohibited | Only inactivity **penalty** fees are prohibited (§3) |
| Liquidity buffer cost | Keep 5% × 0.75% per the agreed conservative assumption (§2.3), labelled as an assumption |

---

## 2. Agreed regulatory and economic rules (working assumptions)

All values are in `unused_line_assumptions.json`. **No hard-coded rates in code.**

### 2.1 Capital: March 2026 Basel III endgame treated as adopted
- **Working assumption (agreed):** the March 2026 expanded risk-based approach is treated as **final
  and in force from day one**, with no phase-in.
- **No card line ever receives a 0% CCF**, cancellable or not.
- **Scope toggle:** `apply_to` = `"category_I_III"` (**default**) or `"all_banks"`. Under the default,
  banks outside Categories I–III **also** use the same 10% / 45% / 75% treatment. The toggle mainly
  governs liquidity (§2.3) and labelling. Do not use the March 2026 standardized proposal's 0% CCF anywhere.
- **Per account:**
  - Unused line `UCL = max(limit − balance, 0)` (12-month average for cost; current for actions)
  - Exposure `E = balance + 0.10 × UCL`
  - `RWA = E × RW`, where RW is:
    - **45% transactor:** balance repaid in full at **every scheduled repayment date** for the
      previous **12 months**, and **no installment or plan balance**
    - **75% non-transactor:** includes **dormant / zero-balance cards**, which have no repayment
      history (provisional pending the question to the boss; configurable)
    - **100%** if the customer's aggregate retail exposure (all balances plus all unused limits,
      across products) exceeds **$1,000,000** (CPI-indexed in the proposal; configurable)
  - Capital = RWA × **10.5%** (business assumption); annual capital cost = capital × **12%** cost of
    equity (business assumption), so **RWA × 1.26%**.
- **Installment and balance offers move an account from 45% to 75%.** Model this in any lever that
  creates revolving or installment balances.
- **Operational risk:** bank-level only. **Exclude** from account and lever economics; show a
  portfolio-level note.
- **SLR: not calculated.** Risk-based capital is assumed to bind (agreed).

### 2.2 Transactor test data
Use per-cycle paid-in-full indicators per **account**, not per customer. If no installment flag
exists, add one via §5, or document the approximation (months paid in full only) and flag it.

### 2.3 Liquidity
- **5% LCR outflow on all unused card lines**: a **conservative assumption** (agreed), even though
  under current law cancellable card lines are not "committed" facilities.
- **Cost** = unused × 5% × **0.75% negative carry** (agreed: funding cost minus HQLA yield). Not the
  old 4% yield gap.
- Applies under the toggle: Category I–III banks by default; all banks under `all_banks`.

### 2.4 Drawdown credit risk (applies under any rules)
- Expected drawdown loss = **annual PD** × LGD × LEQ × unused.
- **Use annual PD, never lifetime PD.** The old L2 formula treated lifetime PD as annual; that defect
  is logged in the lever valuation spec.
- LEQ by segment from the workbook (configurable).
- **CECL:** no allowance on unused cancellable lines, so this is an **economic** cost, not a provision.

### 2.5 Label every output
> *"Assumes the March 2026 Basel III endgame proposal is adopted as proposed; LCR outflow applied
> conservatively to all unused card lines. Capital ratio, cost of equity and carry are illustrative."*

### 2.6 Optional comparison view: current US rules (recommended, not required)
A read-only toggle showing the same portfolio under current law:
- 0% CCF on cancellable lines, 100% risk weight on drawn balances
- **no** LCR outflow for cancellable lines
- SLR at a 10% CCF and 3% minimum for Category I–III

Its purpose is to show stakeholders how much of the value depends on the assumptions. Never make it
the default.

### 2.7 Reference figures already computed (100k bundle, ×5 = 500k bank)
Under §2.1–2.3, from the existing customer view (transactor = 12/12 months paid in full and not
dormant; 27% of card customers):

| Measure | 500k bank | Per 100k |
|---|---|---|
| Unused lines | $2.69B | $537.8M |
| RWA from unused lines | $165.8M | $33.2M |
| Annual capital cost | $2.09M | $0.418M |
| HQLA | $134.5M | $26.9M |
| Annual liquidity cost | $1.01M | $0.202M |
| **Total carrying cost** | **$3.10M** | **$0.620M** |

By L2 group (500k):

| Group | Carrying cost | Card profit after carrying cost |
|---|---|---|
| Dormant | $1.16M | −$0.81M |
| Idle | $0.47M | −$4.03M |
| Healthy | $0.90M | $9.52M |
| Stretched | $0.10M | $8.39M |

Use these as cross-checks. Differences must be explained, e.g. a better transactor test.

---

## 3. Agreed customer rules and compliance gates

| Action | Rule to encode |
|---|---|
| Decrease or closure **for credit reasons** | Reg B **adverse action**: notice within 30 days with reasons, or the right to request them (12 CFR 1002.2(c), 1002.9) |
| Decrease or closure **because of inactivity** | Generally **not** adverse action (12 CFR 1002.2(c)(2)(ii)). Requires a genuine inactivity reason |
| Every line action | **Mandatory reason code** (inactivity / credit deterioration / idle-line right-sizing / customer request / other); it drives the notice workflow |
| Credit score used | FCRA score disclosure **only if** FCRA adverse-action conditions are met and a bureau-based score was used |
| After a decrease | No over-limit fee or penalty rate based on the lower limit until **45 days** after notice (1026.9(c)(2)(vi), (g)(4)). No general prior-notice period for the decrease itself |
| Any increase | Reg Z **ability-to-pay** check (1026.51) |
| Inactivity | Inactivity **penalty** fees prohibited (1026.52(b)); a periodic fee disclosed at opening is a separate matter. **Never propose an inactivity fee lever** |
| Fair lending | Four-fifths test on who receives decreases, closures and increases (reuse the existing fairness module) |
| Customer harm | Gradual cuts (≤ 25% per review, as the ML policy does), floors, reinstatement route; note credit-utilisation and credit-score effects |
| Protected customers | Suppression before anything (existing logic) |

All references to be labelled "summary for discussion; to be confirmed by compliance".

---

## 4. Module design

### 4.1 Components (mirror the L1 Rewards module)
1. **Bank profile and regulatory settings:** category toggle (default I–III), the current-rules
   comparison toggle (optional), and all §2 parameters. Shown on a "Regulatory settings" page with
   the assumption label.
2. **Account exposure and cost layer**, per account:
   - unused line (average and current)
   - transactor test, RW, exposure, RWA
   - capital cost
   - liquidity cost
   - drawdown expected loss
   - total carrying cost
   - card contribution, fully loaded card profit, relationship-adjusted profit
3. **Screen:** the workbook screen (unprofitable, utilisation < 30%, unused ≥ $5,000), all
   thresholds configurable.
4. **Segments:** the workbook's six, in priority order, with rules read from the workbook and
   mapped to system data. Record which rules are exact, approximated or impossible with current
   data; §5 data fills gaps.
5. **Lever library:** read the workbook's *Levers* and *Lever Guide* sheets. At minimum:
   - line decrease with floor
   - risk-based decrease for credit-deteriorating accounts
   - dormant closure after failed reactivation (**feature-flagged, see OPEN_DECISIONS**)
   - reactivation / engagement campaign
   - transactor right-sizing (expected to lose money; keep it to demonstrate that)
   - suppressing automatic line increases
   - non-reissue of expired dormant cards (if the workbook has it)
6. **Customer response model:** the workbook's attrition and spend responses by segment and lever,
   with the attrition cap and stress multiplier. Leavers lose **variable contribution plus
   relationship profit**; fixed costs stay.
7. **Scenarios** (Conservative / Base / Aggressive) and the **stress test** (1×–2×). Go/no-go rule:
   Base must still improve profit at 1.5×.
8. **Treatment designer:** per account, the recommended lever(s), reason code, notice type, ML
   second opinion and agreement flag, "review together" flags for conflicts with L1, L3 or L5, and
   pilot cell assignment (treatment / holdout).
9. **Timing:** when each lever's value arrives (decreases immediate after approval; capital and
   liquidity saving from the next reporting date; reactivation over campaign months; over-limit and
   penalty restrictions for 45 days after notice), with year-1 realisation per lever as config.
10. **Outputs:**
    - profit change by scenario and segment
    - accounts leaving
    - unused lines removed
    - **RWA reduction and one-time capital released (shown separately from annual savings)**
    - carrying cost before and after
    - value by type (avoided loss / cost saving / revenue / lost profit)

### 4.2 Pages (reuse L1 Rewards page patterns)
- **Overview:** today's measured KPIs, scenario KPIs, key takeaways, stress result, assumption label
- **Regulatory settings:** toggles, parameters, worked example per account type, current-rules comparison
- **Segments:** definitions, counts, unused lines, carrying cost, loss
- **Scenario dashboard:** by segment and lever
- **Levers & assumptions:** editable in session only, never saved to config
- **Lever guide & regulation:** each lever with the compliance column and the timing column
- **Customer drill-down:**
  - profile
  - account-level exposure and RWA trace (every number with its formula)
  - transactor test months
  - segment rule met / not met
  - recommended action and reason code
  - notice requirements
  - ML recommendation and agreement
  - other levers the customer is in
  - downloadable review notes ("review notes, not an approval record")

### 4.3 Integration with L2 and the six-strategy view
- **Scope (pending B7):** build so that both modes are configurable:
  - **(a)** workbook scope: unprofitable low-use accounts only
  - **(b)** full line management: also the L2 increase logic for stretched customers

  Default to **(a)** for the module, and keep L2's existing increase valuation unchanged in the
  six-strategy view.
- Expose a summary the six-strategy overview can read (base / low / high, value types).
- Do not change L1, L3–L6 or core engine calculations.

---

## 5. Data: additive only

**Rule (as for the reward data additions):** do not change anything the generator already produces.
Same seed, profile, size and cycles must give byte-identical existing tables. New information goes
in **new tables**, generated from a **separate random stream**. Check which table numbers are free;
the reward additions may already use Table25–Table28.

**Audit first**, then add only what is missing and needed:

| Need | Purpose | Likely status |
|---|---|---|
| Per-cycle paid-in-full by account | Transactor test | Exists (Account Cycle) |
| Installment or plan balances | Transactor test (any installment means 75%) | Probably missing; add |
| Behaviour or bureau score history (monthly) | Credit-Deteriorating segment (e.g. ≥ 40-point drop in 6 months) | Probably missing; add |
| Card activation and reissue status | Dormant confirmation; non-reissue lever | Probably missing; add |
| Digital engagement (logins) | Dormant and sock-drawer confirmation | Probably missing; add |
| Credit line change history, including automatic increases | Right-sizing, suppressing automatic increases | Check; add if missing |
| Facility terms: unconditionally cancellable flag | Eligibility for the 10% CCF label; default True for consumer cards | Missing; add as a reference table |
| Aggregate retail exposure per customer | $1M test | Derivable from existing tables |
| LEQ by segment | Drawdown loss | Assumption (config), not data |

Also add an **informational calibration report** comparing the generated data with the workbook's
segment ranges (never failing the build), as was done for rewards. Any correlation in new tables is
drawn **from** existing outputs; nothing existing changes.

---

## 6. Stages and reporting

1. **Audit:**
   - branches and code map (L2, ML, diagnostics, L1 Rewards template)
   - the workbook's full logic (every formula, segment rule, lever, parameter)
   - the data audit (§5)
   - confirm the §2.7 figures from the 100k bundle or current data
2. **Data additions (§5)**, with the byte-identity and engine regression tests.
3. **Regulatory settings and the account exposure and cost layer (§2):** worked-example unit tests.
4. **Screen and segments.**
5. **Levers, response model, scenarios, stress test.**
6. **Treatment designer, compliance gates, timing.**
7. **Pages and drill-down.**
8. **Tests (§7).**
9. **Docs and evaluation guide:**
   - `docs/UNUSED_LINE_METHODOLOGY.md`
   - ARCHITECTURE.md and STATUS.md updates
   - `specs/unused_line_management/EVALUATION_GUIDE.md` (commands, what to check, sign-off checklist)

After each stage, report: files changed, decisions taken, tests actually run, open questions.

---

## 7. Tests (run them; never claim a result you did not run)

Write `audit/audit_unused_line_module.py`, in the style of the existing audit scripts.

1. **Worked examples:**
   - dormant $10,000 card → exposure $1,000, RWA $750, capital $78.75, capital cost $9.45/yr, HQLA
     $500, liquidity $3.75/yr, total $13.20/yr
   - revolving $10,000 line with $2,000 balance → RWA $600 on the unused part, $7.56 + $3.00 = $10.56/yr
   - transactor → RWA $360, $4.54 + $3.00 = $7.54/yr
2. **Workbook reproduction:** feed the workbook's own inputs. With its original 85% / 55% weights
   the module must reproduce the workbook's dashboard (baseline, Base improvement, accounts lost)
   within ±1%. Then report the corrected figures under §2 (expected baseline credit RWA about $117.9M,
   capital cost about $1.49M, liquidity about $0.49M).
3. **Portfolio cross-check:** §2.7 figures within ±5%, with differences explained.
4. **Invariants:**
   - no card at 0% CCF
   - capital released never added to annual savings
   - low ≤ base ≤ high
   - every action has a reason code
   - inactivity-reason actions carry no adverse-action notice; credit-reason ones do
   - installment or balance offers flip RW to 75%
5. **Toggles:** category and comparison toggles change only what they should.
6. **Regression:**
   - existing pages and six-strategy figures unchanged, except where this brief says otherwise
   - byte-identity of existing generator outputs
7. **Performance:** the 100k bundle loads and pages render on a 2 GB instance. Report peak memory.

---

## 8. Guardrails
- Do not change NEP, CEV, suppression, routing, fairness tests, L1 or L3–L6, or the ML model.
- No hard-coded rates; everything comes from `unused_line_assumptions.json`.
- Clearly separate measured, assumed and regulatory values on every page.
- Masked identifiers only.
- Never present expected values as certain. The recommended next step is always a pilot with a holdout.
