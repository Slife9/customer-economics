# Architecture & Handoff Reference

This is the deep technical reference for the Customer Economics System — written
so another engineer or AI agent opening this repo cold can understand what
exists, why it's built this way, what's already been debugged, and where to
extend it safely. It assumes no prior context beyond what's in this repo.

For narrower, already-good docs, see [`generator/README.md`](generator/README.md)
(the synthesis engine's own design log and validation results) and
[`app/README.md`](app/README.md) (how to run the analysis app, page by page).
This file covers everything those two don't: the **engine's** internals (which
have no README of their own), the full **bug-fix history**, the **deployed
apps**, and **open items**.

## 1. What this project is, in one paragraph

Two systems joined by a shared data contract. `generator/` synthesizes a
realistic card-portfolio dataset from first principles — nothing sampled from
real bank data — using a causal simulation where hidden customer traits
(latents) drive observable behavior, but are never themselves exposed.
`engine/` + `app/` take that dataset (or any dataset shaped like it) and
compute true net economic profit per customer, then route every below-cost
customer to one of six governed remediation strategies ("levers"), each
validated against a negative-control portfolio before its dollar value is
trusted. `datagen_app/` and `app/` are the two things a non-technical person
actually clicks on; everything else is the engine behind them.

## 2. Repository map

```
generator/        synthetic data generation (see generator/README.md)
engine/            the analytical product — pipeline, levers, governance (this file)
app/               Streamlit UI over engine/ (see app/README.md)
datagen_app/       Streamlit UI over generator/ — standalone, separately deployed
samples/           bundled demo_portfolio.zip + negative_control_portfolio.zip
prev_engine/       an earlier, flawed engine attempt — reference/audit only, not live
audit/             one-off scripts used to audit prev_engine before the rebuild
.streamlit/        shared theme config (applies to both deployed apps)
```

`generator/` and `engine/` share no code; they're joined only by the CSV
table contract (Table1_Customer.csv … Table24_Product_Holding_Timeline.csv).
Anything shaped like that contract can be analyzed, not just generator output.

## 3. Why synthetic data, and the rule that makes it trustworthy

There's no real bank data here — it's all simulated, specifically so the
analysis engine's findings can be checked against a *known* ground truth
instead of taken on faith. The rule that makes this work, enforced on both
sides:

**Generate causes, never effects.** `generator/synth/latents.py` draws hidden
traits (reliability, credit_appetite, affluence, digital_fluency, etc.) that
drive every downstream simulated behavior. Nothing past that point — not
`generator/synth/policy.py`, and absolutely nothing in `engine/` — is allowed
to see a latent directly. `engine/core/contract.py` enforces this at load
time: any column whose name contains `latent`, `defect`, `planted`,
`propensity`, `fluency`, or `persona` raises `DataContractViolation` and
refuses to load the portfolio at all. This is why `_ground_truth/` exists as
a sibling folder the engine never opens, rather than a column anywhere in the
published tables.

The practical upshot: the engine's findings about *this* synthetic portfolio
are falsifiable. We know what was actually planted, so the negative-control
gate (§7) can assert that a lever's claimed effect tracks its real cause,
not a generator artifact.

## 4. The engine pipeline (`engine/`)

Orchestrated by `engine/run.py:build_pipeline(data_dir)`. Seven stages, run in
this order, with stage 4→5 enforced by type (not just convention — see below):

```
contract → ledger → customer_view → suppression → routing → levers → governance
```

1. **`core/contract.py`** — the data contract. `REQUIRED` (table → required
   columns) and `OPTIONAL` dicts define the schema; a missing required table
   or column raises immediately, this module never warns and continues.
   `OPTIONAL` tables degrade gracefully (e.g. `Table23_Acquisition.csv`
   missing just means L6 ranks channels on gross value instead of net-of-CAC
   — it never blocks the whole run). See §3 for the ground-truth leak check.

2. **`core/ledger.py`** — builds `Table4_Account_Cycle`-grained economics:
   interest/interchange/fee revenue, `reward_expense` (measured from actual
   redemption data, not assumed), `funding_cost`, `credit_cost`, `cost_to_serve`
   (split into `cost_to_serve_marginal` + `cost_to_serve_fixed_allocated` —
   see the bug writeup in §6.12, this split is load-bearing for routing),
   `capital_cost` (0% CCF on undrawn cancellable card lines per 12 CFR
   217.33(b)(1), so an unused line correctly costs $0 in capital).

3. **`core/customer_view.py`** — rolls the ledger up across every product a
   customer holds (card + deposit + loan), computes trailing-12-month
   aggregates, CEV (Customer Economic Value) score and band (percentile rank
   of trailing-12m net economic profit into 5 bands: Detractor /
   Underperforming / Core / Valued / Premier), and the behavior aggregates L2
   needs (`avg_utilization_12m`, `peak_utilization_12m`, `spend_to_limit_ratio`,
   `transactor_share_12m`, `inactive_share_12m`, `account_age_months`).

4. **`core/suppression.py`** — removes hardship, accommodation-plan, and SCRA
   customers from ever being flagged or routed. Returns a `SuppressedPopulation`
   wrapper (not a plain DataFrame). **This is the key governance mechanism**:
   `core/routing.py:route()` calls `require_suppressed(suppressed)` on its
   input, so routing structurally cannot run on an un-suppressed frame — a
   future contributor who reorders the pipeline gets a runtime error, not a
   silent compliance bug.

5. **`core/routing.py`** — dominant-cost attribution. For every below-cost
   customer: compute each cost line's share of total cost; the largest share
   wins if it clears a 40% materiality bar (`DOMINANCE_THRESHOLD`), else the
   customer routes to `STRUCTURAL` (no single lever fixes them — reported
   honestly, not hidden). `credit_cost`-dominant customers split between L2
   (priced in line with risk peers → the exposure itself is the problem) and
   L3 (priced *below* peers → a pricing gap) by comparing charged APR to the
   credit-score-band peer median. **Critical detail, easy to regress**:
   dominance is computed on `cost_to_serve_marginal` only, never the blended
   `cost_to_serve` — see §6.12.

6. **`levers/`** — six lever classes, one per remediation strategy, each
   implementing the shared contract in `levers/base.py`:
   `population(suppressed) → who`, `size(population) → SizeResult`,
   `worklist(population) → one row per customer, one action, one reason`,
   `driver(customer_view) → the portfolio quantity this lever claims to move`
   (used only by the negative-control gate). `SizeResult.priced_value_usd`
   is `None` — never `0` — when pricing the outcome would require predicting
   an untested customer behavioral response (a "Type C" question, in the
   generator's own vocabulary). See §5 for all six.

7. **`governance/`** — `fairness.py` (four-fifths test on both the score and
   the treatment, across geography, against the population-average selection
   rate with a minimum group size of 30 — see §6.5 for why) and
   `negative_control.py` (the validation gate — see §7).

`core/outputs.py` produces the four downloadable artifacts: score file,
worklist export, leakage register, governance pack JSON.

## 5. The six levers

| Code | Name | Population | Sizing | Gates |
|---|---|---|---|---|
| L1 | Rewards & Promo Economics | Profitable, $0-fee, $100+/yr reward-value customers (opportunity) + routed losses | `None` — fee take-up is untested behavior. Reports the unpriced reward-cost ceiling. | Reg Z: 45-day notice, right to reject |
| L2 | Line Management by Value | Four-way split on 12mo behavior: DECREASE (idle) / ENGAGE (dormant) / GROW_ENGAGEMENT (transactor, protected) / INCREASE (stretched, good standing) | Priced: EL avoided (same PD/LGD as reserving) + peer-benchmarked incremental interest. Regulatory capital relief from decreases is **always $0 by design** (0% CCF). Economic capital relief reported separately, never blended in. | Reg B adverse-action notice on decreases |
| L3 | Value-Based Pricing | Priced ≥2pts below own credit-score-band peer median | `None` — repricing response is untested behavior. Reports the zero-elasticity ceiling. | CARD Act (no first-year increase, prospective only, 45-day notice), fair-lending review, champion/challenger test |
| L4 | Cost-to-Serve Migration | 3+ avoidable calls OR 6+ paper statements in trailing window | Priced: marginal unit cost × avoided volume, + fixed capacity cost **only** where avoided volume crosses a real capacity-band boundary | None — no customer contact, deploy now |
| L5 | Retention Targeting | Valued/Premier CEV band + (closure-request contact OR spend decline OR priced ≥2pts above peer) | `None` — retention uplift is untested behavior. Reports value-at-risk (today's trailing-12m profit), not recoverable value. | Held-out champion/challenger pilot |
| L6 | Channel Quality Review | Customers acquired via the bottom-third acquisition channel by net value after CAC | Priced: (best channel mean net value − worst channel mean net value) × worst-channel volume | None — internal budget decision, no customer contact |

Three of six (L1, L3, L5) can *never* return a priced number in this design —
that's intentional, not a missing feature. Don't "fix" this by adding a
heuristic take-up rate; the correct next step is a real champion/challenger
pilot (see §9).

## 6. Bug-fix history (engine side)

The generator's own bug history (causal breaks fixed before the rebuild) is
documented in `generator/README.md`. These are the **engine**-side bugs found
and fixed since, in roughly chronological order — useful context for anyone
touching `engine/core/` or `engine/levers/`:

1. **`reward_expense` off by 100x.** `cost_per_point["_blended"]` was already
   dollars-per-point; `ledger.py` divided by 100 again as if it were cents.
   Symptom: L1's population came back empty (no customer crossed the reward-
   value threshold). Fix: removed the extra `/100.0`.

2. **Negative-control gate comparing demo against itself.** `NEGCTL.check()`
   took one lever instance and called it against both demo and control data —
   but L4/L5/L6 bind portfolio-specific tables (drivers, acquisition) at
   `__init__`, so the demo-bound instance silently used demo's own tables for
   both sides. Evidence: L4's `driver_demo == driver_control` to the decimal.
   Fix: `check()` now takes `demo_lever` and `control_lever` as two separate
   instances; `run.py`'s orchestrator constructs both.

3. **`credit_cost` ~13x overcounted.** Was summed from `Expected Credit Loss
   12 Month` (a forward-looking balance-sheet snapshot, recomputed fresh every
   cycle) across all 36 cycles — effectively counting the same forward-looking
   number ~36 times. Fix: switched to `Monthly Provision` (the cycle-over-cycle
   change in Lifetime ECL — the actual P&L accrual). Verified: trailing-12mo
   totals flipped from negative/backwards-ordered to positive and correctly
   ordered.

4. **Fairness four-fifths test, spurious mass failures.** Original version
   compared every geography group's selection rate against whichever group
   happened to have the highest observed rate — a multiple-comparisons trap
   with many small groups. Fixed by adding `MIN_GROUP_SIZE = 30` and switching
   the reference from max-observed-group to population-average selection rate.

5. **L2 single-snapshot utilization couldn't tell idle from a disciplined
   transactor.** Both read 0% ending balance on statement day. Redesigned (see
   §5 table) to classify on trailing-12m average *and* peak utilization, spend-
   to-limit ratio, and transactor/inactive share — four outcomes instead of one.

6. **Segment chart misinterpretation risk** (not a bug, a design flaw a user
   caught): "Total NEP by segment," sorted by total dollars, made the largest
   segment look most valuable per-customer when it wasn't. Rebuilt as a combo
   chart: bars = total, line = mean, sorted by mean, with customer counts
   annotated on the x-axis.

7. **Waterfall chart inconsistency.** The executive-summary waterfall
   annualized over the full 36-cycle window while the headline KPI used
   trailing-12-months — two different numbers on one page. Fixed
   `revenue_cost_waterfall()` to accept and filter to the same
   `trailing_months` window as the customer view.

8. **Zip upload `AttributeError: '_LocalFileAsUpload' object has no attribute
   'seek'`.** `zipfile.ZipFile(uploaded_file)` needs a seekable object; the
   sample-data mock wrapper wasn't. Fixed via
   `zipfile.ZipFile(io.BytesIO(uploaded_file.getvalue()))`.

9. **Stale-cache directory bug.** `_extract_zip()` treated the destination
   directory's mere existence as proof of a successful prior extraction, but a
   failed attempt (from bug #8) left an empty directory that then got reused.
   Fixed by checking for `Table1_Customer.csv` inside it before trusting the
   cache.

10. **Acquisition table hard-required, shouldn't have been.** A stale upload
    predating the `Acquisition Cost USD` column failed the whole run for an
    unrelated reason. Moved `Table23_Acquisition.csv` to `OPTIONAL` in
    `contract.py`; `L6CrossSell` now checks `"Acquisition Cost USD" in
    acquisition.columns` and degrades to gross-value ranking (with an explicit
    caveat) if it's missing, instead of blocking the run.

11. **Streamlit process-cache gotcha (not a code bug, but costs real debugging
    time if you don't know it).** Streamlit's file-watcher hot-reloads page
    scripts under `app/pages/` automatically, but does **not** reload
    already-imported library modules from `engine/` (Python caches modules in
    `sys.modules` for the life of the process). After editing anything under
    `engine/`, "Clear cache & reload" in the sidebar is **not enough** — it
    only clears `st.cache_resource`, not the Python module cache. You need a
    full process restart (kill the Streamlit process, start it again).
    Symptom if you forget: a `KeyError` on a column name that very obviously
    exists in the code you just wrote.

12. **Cost-to-serve misattribution — the most significant fix.** A single
    blended `cost_to_serve` figure let a near-zero-activity account's *even
    share of shared servicing-platform overhead* (something it didn't cause)
    be large enough, relative to its tiny other costs, to make it look
    "servicing-dominant" and get routed to L4. Root cause: `ledger.py`'s
    `_cost_to_serve()` returned one number blending (a) the marginal cost this
    specific account's own calls/statements caused and (b) an even per-account
    split of the pool's fixed capacity cost. Fix: split into
    `cost_to_serve_marginal` and `cost_to_serve_fixed_allocated` as two
    separate ledger columns; `routing.py` now computes "dominant cause" using
    **only** the marginal share (the fixed-allocated share still counts toward
    the total-cost denominator, so loss totals stay honest — it just can never
    itself be the *reason* a customer is routed anywhere, since no per-customer
    lever changes a shared platform's fixed cost). Verified on the demo
    portfolio: `STRUCTURAL` bucket grew 73→275 customers, `L4` shrank
    554→329, **total NEP and total below-cost count were unchanged** — this
    was a reattribution fix, not a numbers fix.

## 7. The negative-control gate (how to not fool yourself)

`engine/governance/negative_control.py`, orchestrated by
`run.py:MECHANISM_VARIED_IN_CONTROL`. For each lever whose mechanism the
negative-control profile actually varies (`generator/run.py:CONTROL_MECHANISM`
— see `generator/README.md`'s table), asserts:

```
value_ratio <= driver_ratio * (1 + slack)
```

i.e. the lever's priced value must have fallen *at least as fast* as the
portfolio quantity (`driver()`) it claims to act on. If a lever's dollar value
stayed high while its claimed cause nearly vanished, that's evidence the
finding is a generator artifact, not a real pattern, and the gate reports FAIL.

**L5 and L6 have no mechanism varied in the current negative-control profile**
(`MECHANISM_VARIED_IN_CONTROL["L5"] = False`, `["L6"] = False`), so they are
*structurally* reported `INCONCLUSIVE`, never a false PASS. This is a known,
documented gap (see §9) — not a bug.

Current result on demo vs. negative_control: L1–L4 all PASS, L5/L6
INCONCLUSIVE by design.

## 8. The two deployed apps

Both deploy from **`github.com/Slife9/customer-economics`**, branch `main`,
via Streamlit Community Cloud, auto-redeploying on every push. The repo is
currently **public**.

| App | Entry point | Live URL | Purpose |
|---|---|---|---|
| Customer Economics System | `app/Home.py` | https://customer-economics-exut3amfwi9uesfmpqvm4j.streamlit.app/ | Upload a portfolio zip, see the full analysis |
| Portfolio Generator | `datagen_app/Home.py` | https://customer-economics-g36dfysbdmfgwf2f8ygmms.streamlit.app/ | Generate a fresh synthetic test portfolio via sliders (scenario, size 500–10,000, horizon 12–36mo, defect-rate multiplier 0–2x), download the zip |

`datagen_app/Home.py` is a thin UI wrapper: it calls
`generator.run.build(profile_name, out_dir, seed, n_months, n_customers,
overrides)` directly (the `overrides` kwarg was added specifically to let the
UI scale `DEMO_DEFECT_PREVALENCE` by a multiplier without touching the
`PROFILES` dict). It writes to a `tempfile.TemporaryDirectory()` and zips the
result in-memory for `st.download_button` — nothing is written to disk
outside the temp dir.

Both apps share the root `.streamlit/config.toml` theme automatically (Streamlit
resolves this relative to the repo root regardless of which app's entry point
is running).

## 9. Open items — real gaps, not yet built

In roughly most-to-least valuable order:

- **A champion/challenger test-design scaffold.** This is the actual unlock
  for L1, L3, and L5 ever returning a priced number — right now they correctly
  refuse to guess, but nothing in this repo helps someone *design* the pilot
  that would make pricing them legitimate.
- **Give the negative control a retention and a channel-mix mechanism to vary**,
  so L5 and L6 can be genuinely tested instead of structurally INCONCLUSIVE.
- **Uncertainty bands on lever sizing** (point estimates only today).
- **Adverse-action notice generation** (L2 flags that one's required; nothing
  generates the actual notice).
- **Month-over-month monitoring** — today's app is a single-snapshot analysis;
  there's no tracking of a lever's realized impact after action is taken.
- **Multi-card-per-customer cardinality** — the generator and engine currently
  assume a 1:1 customer:card relationship.
- **Scale testing at 10,000–50,000 customers** — works comfortably at demo
  scale (5,000); untested at real-bank scale, and `datagen_app`'s slider caps
  at 10,000 partly for Streamlit Cloud's free-tier compute budget, not because
  the engine is known to break above it.
- **A real BISG fairness proxy** — the current fairness test uses geography
  alone (no race/ethnicity is collected, per Reg B/ECOA, and no synthetic
  surname field exists to support actual BISG). Adding a synthetic name field
  to the generator would let this be done properly.
- **Three growth-lever ideas discussed but not built**: share-of-wallet growth
  (capture more of a loyal transactor's spend from competing cards), product
  upsell/tier migration, and deposit/loan cross-sell for card-only customers.
  All three would face the same Type-C causal ceiling L1/L3/L5 already do —
  buildable as unpriced-ceiling levers today, priced only after a pilot.

## 10. Invariants a future change must not break

These are the design decisions that make this system's findings trustworthy.
A change that violates one of these is a regression even if all tests pass:

1. **Never let a lever return a fabricated dollar value for a Type C
   (untested-behavioral-response) question.** Return `None`, not `0` — `0`
   reads as "worth nothing," `None` reads as "we will not invent this."
2. **Never let analysis code see a latent trait or a ground-truth column.**
   Enforced at load time in `contract.py` by name-pattern matching, not by
   convention or code review discipline.
3. **Suppression always runs before routing.** Enforced by the
   `SuppressedPopulation` type, not by call-order discipline — routing
   literally cannot accept a plain DataFrame.
4. **Routing's "dominant cause" is decided on `cost_to_serve_marginal`,
   never the blended `cost_to_serve`.** See §6.12 — this is the single
   easiest regression to reintroduce by accident if someone "simplifies" the
   cost columns back into one.
5. **A negative-control PASS requires an actual varied mechanism.** Never
   relabel an `INCONCLUSIVE` (no mechanism to test) as a PASS to make a lever
   look validated.
6. **After editing anything under `engine/`, fully restart the Streamlit
   process before testing in `app/`** — "Clear cache & reload" alone will not
   pick up the change (see §6.11).
