# ProfitInsight Synthesis Engine v2

Rebuilt from scratch against `Data_Requirements_Specification.md`. The
previous engine (in `../prev_engine`) is kept for reference only.

```bash
python run.py --profile demo              --out ./out/demo
python run.py --profile negative_control  --out ./out/negative_control
python run.py --profile transactor_heavy  --out ./out/variant_transactor_heavy
python run.py --profile subprime_heavy    --out ./out/variant_subprime_heavy
python run.py --profile premium_heavy     --out ./out/variant_premium_heavy

python -m validate.check --data ./out/demo
python -m validate.circularity --root ./out
```

Defaults: 5,000 customers (2,000 for variants), 36 monthly cycles from
2023-01. Override with `--n` and `--cycles`.

---

## What changed from the previous engine

An audit of the previously shipped `demo`/`negative_control`/variant CSVs
(see `../audit/`) found four causal breaks and one bookkeeping bug before any
rebuild started:

1. **Annual fees posted every cycle, not on the anniversary** - fee revenue
   was overstated ~12x. Fixed in `cycles.py` (`anniversary` gate).
2. **Utilization was the latent, not a measured output** - balance was
   generated as `appetite x limit` directly, so it could not respond to line
   policy. Fixed: balance now emerges from authorized spend minus payment,
   cycle over cycle, with the limit acting only as an authorization
   constraint (`cycles.py`).
3. **No absorbing charge-off state** - the delinquency transition matrix
   round-tripped forever; nothing ever left the book as a loss. Fixed: a
   proper roll/cure state machine with charge-off at 180 DPD, realized net
   credit loss, and post-charge-off recovery (`cycles.py`, `risk.py`).
4. **Account type was re-rolled every cycle** (10.9 changes/account over 24
   cycles). Fixed: derived from trailing 3-cycle behavior, sticky by
   construction (`cycles._derive_account_type`).
5. **The negative control varied only limit generosity** - fee policy and
   servicing efficiency were bit-for-bit identical to the demo book. Fixed:
   the control now varies the *mechanism* of every lever (see below), and
   population latents are never tilted to fabricate the comparison.

Also fixed along the way: credit score is now generated as a noisy
**observation of** the latents (not an independent draw weakly correlated to
them) - this is what gives the book a real charge-off gradient by score band;
a PD scorecard calibration bug that put average 12-month PD at 37%; a
non-accrual gap that let interest compound without bound past 90 DPD; and an
RNG seeding bug (`abs(hash(profile_name))`) that made every build
non-reproducible across processes.

---

## Architecture

```
config/            MCC catalogue, interchange rate card, reward program rules,
                    redemption channels, fee schedule, cost pools, US
                    geography, benchmarks.yaml (every entry cited)

synth/
  latents.py        12 latent traits + 3 correlated factors. THE CAUSES.
                     Never imports policy.py.
  population.py      customers, demographics, score-as-observation-of-latents,
                     hardship/SCRA, card accounts
  policy.py          underwriting, limits, pricing, fees, line review. THE
                     BANK'S RULES. Never imports latents.py - reads score,
                     segment, tenure and (for line review) an account's own
                     lagged observed behavior, never a latent.
  transactions.py    MCC-driven spend, dormancy, interchange looked up from
                     the rate card
  cycles.py          balance/payment/delinquency state machine, CARD Act
                     fields, promotional lifecycle, limit/rate/attrition
                     events
  rewards.py         earn by published rule, FIFO redemption ledger, expiry
                     mechanism -> breakage is measured, never set
  risk.py            CECL (ASC 326) scorecard with model error against the
                     true hazard; charge-off and recovery
  capital.py         US standardized capital (12 CFR 217 subpart D), dual
                     regulatory/economic tracks
  cost.py            cost drivers with a call-reason taxonomy; stepped cost
                     pools
  deposits.py        deposit accounts, FTP-credit revenue
  loans.py           personal/auto loans
  ftp.py             SOFR-referenced funding curve
  fees.py            waiver population, entitled-vs-charged reconciliation
  defects.py         planted Type A failures with real evidence trails
  cards.py           plastic-level reissue events, feeds Cost Drivers back
  installments.py    installment plan origination and runoff
  timeline.py        Product Holding Timeline, assembled from other tables

validate/
  check.py           Layer 1 (35 consistency checks) + Layer 2 (22 realism
                     checks against cited benchmarks)
  circularity.py     negative control and variant comparison, 8 assertions
```

**Latents and policy share no imports.** Policy sees score, segment,
product, tenure, and - for periodic line review only - the account's own
lagged observed utilization. It never sees a latent directly.

---

## The negative control varies every lever's mechanism

| Lever | Demo mechanism | Control mechanism |
|---|---|---|
| Limits | blind origination policy only | + periodic review against **observed** utilization (lagged, never a latent) |
| Fees | priced off product tier | annual fee capped at 85% of the program's published expected reward value |
| Servicing | 40% digital deflection | 66% digital deflection |
| Waivers | 48%→90%\* review discipline | 97% review discipline (few concessions go untracked) |
| Repricing | never reprices after origination | periodic risk-based repricing (CARD Act compliant: not in year 1) |
| Defects | ~3-5.5% per type, planted | **zero** - `defect_prevalence: {}` |

\* the demo profile's review discipline was raised from 0.48 to 0.90 during
calibration so `WAIVER_NO_EXPIRY` didn't dominate the defect mix - see
`run.py:DEMO_DEFECT_PREVALENCE`.

Population latents are **never tilted** between demo and control. Every
difference in the comparison report comes from a policy mechanism, not from
swapping in better customers. `validate/circularity.py` asserts this
explicitly (8/8 assertions pass, see `out/Circularity_Report.csv`).

---

## Validation

**Layer 1 (consistency), 35 checks.** All pass. Includes: no over-limit
balance beyond a documented realistic tolerance (15% of limit or $50 - a
larger residual is expected right after a `RISK_DETERIORATION` limit cut,
which does not force immediate paydown), zero CCF on cancellable undrawn
lines, no IFRS 9 staging, ground truth never leaks into a published column,
the Card table's in-window issuance count matches Cost Drivers' `Cards
Issued` exactly, installment plan balances never go negative, and every
timeline row references a real customer.

**Layer 2 (realism), 22 checks against `config/benchmarks.yaml`.** Every
benchmark carries either a real citation (`confidence: sourced`) or an
explicit, honest `confidence: estimated` flag where no primary source could
be found - never a fabricated citation. On the demo portfolio, 18/22 pass;
the remaining 4 (`transactor_share`, `average_utilization`,
`delinquency_90plus_rate_balance_based`, `net_charge_off_rate`) are close
misses after nine rounds of calibration and were left as-is rather than
chased further, per the spec's own warning: *"near-perfect agreement with
every benchmark should be treated as evidence of overfitting, not success."*

**On the variant portfolios, several Layer 2 checks fail by design.**
`benchmarks.yaml` describes a **blended US industry book**.
`subprime_heavy` correctly shows ECL share and attrition above that
blended range; `premium_heavy` and `transactor_heavy` correctly show annual
fee incidence above it (both skew toward fee-bearing premium products). This
is acceptance criterion 5 working as intended - a variant that stayed inside
blended-book ranges would be the actual failure.

Run `python -m validate.check --data <dir>` for the full report on any
build; `Validation_Report_Consistency.csv` and `Validation_Report_Realism.csv`
land in that directory.

---

## Planted defects (Type A)

| Defect | Mechanism | Evidence required |
|---|---|---|
| `UNPOSTED_CONTRACTUAL_FEE` | ~55% of an affected account's annual-fee charges silently dropped from Fee Events | Fee Schedule says due; Fee Events shows a gap |
| `EXPIRED_CONCESSION` | a waiver's status stays "active" past its own review date | Waiver review date vs. today |
| `WAIVER_NO_EXPIRY` | a waiver granted with no review date at all | absence of a review date - emerges from the `review_discipline` policy dial, not independently sampled |
| `PROMO_FAILED_TO_REVERT` | promotional rate keeps being charged past the account's own recorded expiry cycle | Promotional Status vs. Promotional Expiry Cycle Index vs. rate actually charged |
| `INTERCHANGE_BELOW_EXPECTED` | booked interchange scaled to 55-80% of the rate-card-entitled amount | Interchange Rate Applied vs. Table15 rate card |
| `PRICE_BELOW_CONTRACT` | charged APR held 1.5-4.0 points below the account's own contractual APR | Table2 Contractual Purchase APR vs. Charged Purchase APR |
| `WRONG_EARN_RULE` | base earn rate applied on transactions whose MCC qualified for the program's bonus category | Table16 program rule vs. Table5 earn basis |

All seven are planted (the previous engine only had four; three tables it
needed didn't exist yet). Ground truth lives in `_ground_truth/`, is never
joined into a published table (Layer 1 asserts this), and records mechanism +
cycles affected + dollar impact per account, not a marker column.

Prevalence is set per defect type over its own eligible population (see
`run.py:DEMO_DEFECT_PREVALENCE`), not as a flat share of all accounts, so
each type has enough positives to score a detector against.

---

## Known gaps - documented, not hidden

**All tables in the spec's inventory are now built**, including the three
completeness items that aren't load-bearing for any of the six levers:

- **Card** (`Table3_Card.csv`) - plastic-level reissue events (lost, stolen,
  damaged, fraud compromise, standard 48-month expiry), driven by the same
  `problem_rate`/`digital_fluency` latents that drive contact-center volume.
  `Table12_Cost_Drivers`'s `Cards Issued` column is read FROM this table
  (`cost.py:drivers(..., card_events=...)`), not drawn independently, so the
  two tables agree by construction - Layer 1 asserts this.
- **Installment Plan** (`Table5a`/`Table5b`) - a subset of large purchases
  converted to a fixed-term, mostly-0%-APR plan with a flat plan fee (the
  Amex Plan It / Citi Flex Pay model). **Scope note:** this is a standalone
  overlay - a transaction that becomes a plan still also contributes to the
  ordinary revolving Purchase Balance in `Table4_Account_Cycle`. Closing that
  gap would mean re-running the cycle simulation with plan-eligible spend
  excluded, which wasn't done in this pass. Treat the two as evidence of
  different things (what got converted vs. what is carried), not a fully
  reconciled pair.
- **Product Holding Timeline** (`Table24`) - assembled from OPEN/CLOSE events
  already present in the other product tables (card open/close, deposit open,
  loan origination/payoff/charge-off, plan origination/completion). Adds no
  new behavior of its own; deposit accounts were given a genuine open-cycle
  distribution (mostly predating the window, with a `relationship_propensity`
  -driven chance of a mid-window cross-sell) specifically so this table can
  show a real card-then-deposit sequence instead of every relationship
  starting on day one.

**Type C (behavioral response to an untried treatment) is deliberately
absent** per spec section 10 - no retention uplift, no price elasticity, no
campaign-outcome history. These are real gaps filled by a champion/challenger
pilot, not something this generator should ever fabricate.

**`calls_per_account_per_year` and `digital_sessions_per_account_per_year`
benchmarks are `confidence: estimated`** - no public issuer-level metric
exists; J.D. Power measures satisfaction, not volume. Flagged, not
fabricated.

**Tension to flag per the spec's standing instruction (section 14):** section
5.5 states that deposits earning more than cards is "the single strongest
argument for a relationship view" - that is a *finding*, and the spec
naming it as a desired outcome sits close to the causes-not-effects line.
`deposits.py`'s FTP-credit revenue and `deposit_propensity` are generated
independent of any card economics, so whether that relationship actually
holds in this build is not asserted here - check `Circularity_Report.csv`
and the published tables directly rather than taking the spec's framing as
confirmation.

---

## Regulatory basis

CECL (ASC 326, no IFRS 9 staging), US standardized capital (12 CFR 217
subpart D: 0% CCF on undrawn cancellable lines, 100%/150% risk weight, dual
regulatory/economic tracks never blended), CARD Act fields (open date,
first-year flag, no repricing in year 1, notice cycle on rate changes), Reg Z
late fee safe harbor ($32 first violation / $43 subsequent - the CFPB's $8
rule was vacated by the N.D. Tex. in April 2025 and the Bureau agreed to drop
it in May 2025), Reg B (no race/ethnicity collected; state/ZIP geography
generated for BISG-style proxy testing instead), SCRA rate cap, USD, FTP
curve referencing SOFR. American spelling throughout column names
(`Behavior`, `Program`, `Center`, `Authorized`).

`capital.py:CONFIG["regime"]` is the one-line switch for the March 2026
Basel III endgame re-proposal (net capital relief, not the 2023 version's
~19% increase - the 2023 proposal was formally rescinded). Verify the rule's
status before relying on it in a client engagement; it was still in comment
period (closed June 2026, finalization targeted Q4 2026) as of this build.
