# Stage 1 audit: Unused Credit Line Management

Read-only audit, done before any code was written (14 Nov 2026). It covers the branches, the code
map, the workbook's full logic, the data audit, the §2.7 reference figures and where the code
contradicts the brief. Decisions taken since are in `DECISIONS.md`.

## 1. Branches (at audit time)

None of the feature branches was merged into `main` (`b660bb8`).

| Branch | Ahead of `main` | Contains |
|---|---|---|
| `feature/lever-valuation-rebuild` | 20 | Rebuilt L1–L6 valuation, six-strategy overview, new L2 page, bundle v2, 100k memory work |
| `feature/reward-data-additions` | 10 | Tables 25–27 and the byte-identity method |
| `fix/negative-control-generation` | 1 | Fix for the `negative_control` profile crash; inside the two branches below |
| `feature/l1-rewards-system` | 18 | L1 Rewards template + reward-data-additions + the fix |
| `docs/l1-reward-strategy-report` | 22 | L1 Rewards branch + the strategy report |

Decision (see `DECISIONS.md`): build on a clean branch from `main`, merging nothing.

## 2. Code map

### L2 line management (`engine/levers/l2_lines.py`)
- The brief's group names do not exist in code. Mapping: Dormant = ENGAGE /
  `REACTIVATION_CAMPAIGN`; Idle = DECREASE / `DECREASE_LIMIT`; Healthy = GROW_ENGAGEMENT /
  `DEEPEN_RELATIONSHIP_NO_LIMIT_CHANGE`; Stretched = INCREASE / `INCREASE_LIMIT`; plus a fifth,
  DECREASE_RISK_EXPOSURE (routed to L2), also `DECREASE_LIMIT`.
- Decrease target: `max(1.5 × peak utilisation × current limit, 1.10 × 12-month spend)`, floor $300.
  The brief says peak *balance*; the two agree only if the limit did not change in the year.
- Expected loss avoided uses `pd_lifetime` as if annual (L1 branch, `l2_lines.py:105`). The
  lever-valuation branch divides by card life 3/2/1 years, so its high scenario is still
  lifetime-as-annual.
- No annual PD exists in the customer view, ledger or bundle; `PD 12 Month` is only in raw Table8.
- Lever-valuation L2 already has a `dormant_rightsizing_enabled` flag and a carrying-cost table on
  the old liquidity/leverage logic. This module's flags live in their own config so L2 is unaffected.

### ML credit-limit model (`engine/ml/`)
- Seven labels, not five: adds INSUFFICIENT_HISTORY and NOT_ELIGIBLE.
- "25% per review" is three rules: ≤ 25% cut per account; ≤ 5% of accounts decreased per review;
  each cut ≥ 15% and ≥ $500.
- The fairness test counts any ML action as "selected" (increases included), not adverse actions
  only. "Fails in 5 metros on 100k" exists only as text in the lever-valuation `STATUS.md`; on the
  committed 50k bundle 14 of 76 metros fail.

### Old diagnostics (replaced, never reused)
- Liquidity `avg_undrawn × 5% × (8.5% − 4.5%)`; leverage `undrawn × 10% × 4% × 12%`; default policy
  Case B ($0), bundles built under Case A.
- `card_net` already deducts the old `capital_cost` on drawn balances: the module must replace it,
  never add the new charge on top.

### Reused read-only
- Fairness `four_fifths_test(cv, selected, "Metro Name")`, `suppression.run()`, `routing.route()`.

### L1 Rewards template
- Standalone `rewards_app/` with its own engine (`assumptions`, `data`, `segments`, `model`), pages
  and a shared lib (`state`, `style`, `guide`). Mirrored as `engine/unused_lines/` and
  `unused_lines_app/` (copied, not merged).

## 3. Workbook logic (`Unused_Line_RWA_Scenario_Model.xlsx`, all 9 sheets read cell by cell)

The three scenario calculation sheets have identical formulas apart from the lever rows they read.

**Baseline per segment**
- `U = max(0, line − balance)`; utilisation = balance / line
- revenue = spend × interchange + revolving × (APR − cost of funds) + annual fee + other fees
- ECL = PD × LGD × (balance + LEQ × U) (includes drawn-balance loss)
- RWA = (balance + CCF × U) × RW; capital charge = RWA × 10.5% × 12%
- liquidity = U × 5% × 0.75%
- contribution = revenue − (reward + ECL + variable cost + capital + liquidity)
- fully loaded = contribution − fixed; relationship-adjusted = fully loaded + relationship profit

**After levers**
- closures first; responders = campaign share × response rate
- attrition, spend loss = `min(1, multiplier × rate)` (the multiplier scales only these two)
- Cohort A (decreased, kept) = N × (1 − closure) × decrease share × (1 − attrition);
  new line = `min(old, max($500, balance × 1.2, old × (1 − cut)))`; balance and revolving
  + responders × incremental revolving; spend × (1 − spend loss) + responders × incremental spend;
  ECL with PD × (1 + PD uplift)
- Cohort B = N × (1 − closure) × (1 − decrease share): same campaign effects, no spend loss
- campaign cost = share targeted × cost + responders × $25 + responders × incremental revolving × 3%
- fixed cost held constant; relationship profit kept on survivors; capital released = −ΔRWA × 10.5%

**Segment rules (priority order) and mapping to system data**

| Rule | Mapping | Source |
|---|---|---|
| Screen: profit < 0, avg utilisation < 30%, unused ≥ $5k, open ≥ 12 months, not charged off/closed | Exact | customer view, Table2b, Table22 |
| Screen: not fraud-blocked | Approximated | Table3 FRAUD_COMPROMISE |
| 1 Deteriorating: PD ≥ 4% | Exact | Table8 `PD 12 Month` |
| 1 Deteriorating: score down ≥ 40 in 6 months | New data | Table29 |
| 2 Relationship: non-card profit ≥ $150 | Exact | deposit + loan net |
| 2 Relationship: deposits + investments ≥ $25k | Approximated | deposits only |
| 2 Relationship: premium / private bank | Approximated | Table1 `Segment` |
| 3 Dormant: no activity ≥ 12 months and $0 balance | Exact | Table4 / Table5 |
| 3 Dormant confirmation: activation | New data | Table30 |
| 4 Sock-Drawer: active ≤ 4 of 12 and spend < $2.5k | Exact | Table4 / Table5 |
| 5 Transactors: PIF ≥ 10/12, peak util < 15%, spend ≥ $6k | Exact with care | statement balance = ending + payment |

**Inputs**: 19 baseline + 4 response inputs per segment, 11 portfolio-wide, 7 levers per scenario
and segment, 3 capital regimes. Two brief levers have no model lever (Lever Guide only): suppressing
automatic increases (Table20 history) and non-reissue (Table3 reissue cost).

**Workbook issues beyond brief §1.4** (recorded, not reproduced): Relationship at 55% despite a $500
revolving balance; closures not conditional on failed reactivation; 24+ vs 12 months inactivity;
Lever Guide sizing text vs flat % cut; two transactor definitions (10/12 vs 12/12); campaign
balances never move RW to 75%; headline uses card not relationship-adjusted profit; stress
multiplier does not touch response rate or PD uplift; Unassigned has no economics.

**Hand checks**: Base +$1,329,136.92 and 8,470 accounts lost (9.1%); baseline −$9,044,043;
corrected baseline at 75%/45% credit RWA $117,937,500, capital cost $1,486,013, liquidity $487,688;
all three brief §7 worked examples reproduce.

## 4. Data audit

| Need | Status |
|---|---|
| Paid in full by account and cycle | Exists (Table4); False when statement balance is $0 |
| Installment / plan balances | Exists (Table5a/5b, Table4 Promotional Balance) |
| Monthly behaviour / bureau score | Missing → Table29 |
| Card activation | Missing → Table30 (reissue/expiry exist in Table3) |
| Digital engagement | Partial (Table12 `Digital Sessions`) |
| Line-change history incl. automatic increases | Exists (Table20 PROACTIVE_INCREASE) |
| Unconditionally cancellable flag | Exists (Table2, always True) |
| Aggregate retail exposure | Derivable (cards + Table7b loans) |
| Household ID, investments | Missing (approximated) |

## 5. §2.7 reference figures (committed 50k bundle × 10; the 100k bundle is not on disk)

| Measure | Brief | 50k × 10 |
|---|---|---|
| Unused lines | $2.69B | $2.697B |
| RWA from unused lines | $165.8M | $167.1M |
| Capital cost | $2.09M | $2.105M |
| HQLA | $134.5M | $134.9M |
| Liquidity cost | $1.01M | $1.011M |
| Total carrying cost | $3.10M | $3.117M (+0.5%) |
| Transactor share | 27% | 26.2% |

Carrying cost by L2 group reproduces within ~2% (Dormant 1.17, Idle 0.47, Healthy 0.91,
Stretched 0.10 $M). Card profit after carrying cost does not (Dormant −1.19 vs −0.81; Idle −5.39 vs
−4.03; Healthy 9.01 vs 9.52; Stretched 8.61 vs 8.39 $M), most likely 50k-vs-100k sampling in lumpy
credit losses; unconfirmed without the 100k bundle. §2.7's transactor test uses the account-type
label (trailing 3 cycles), not the paid-in-full indicator.

## 6. Code vs brief
1. L2 group names; target on peak utilisation, not peak balance.
2. ML has 7 actions; the 25% rule means three different things.
3. ML fairness claim not backed by a saved result; test counts any action.
4. No annual PD in the customer view or bundle.
5. Installment data already exists.
