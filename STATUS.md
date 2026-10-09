# STATUS: Leverage Capital Cost (SPEC v2)

Built against `SPEC_leverage_capital_cost_v2.md` and `REGULATORY_RULEBOOK.md`
(delivered as a spec package). This repo has no `tests/`, no YAML actually in
use, no `governance/` folder at the root, and no existing SHA-256
model-registry/audit-trail pattern — stages below note where the spec's
literal ask was adapted to this codebase's real shape rather than built from
a convention that doesn't exist here.

## Stage 1 — Repo mapping (done)

Liquidity cost pattern mapped: `engine/config/liquidity_policy.json` (plain
JSON, `json.loads` inside the computing function, no caching at import time)
→ `customer_view.py:_compute_liquidity_cost()` (merged into `cv` inside
`build()`) → `engine/levers/l2_lines.py` (DECREASE savings derived from each
customer's own already-computed rate, never a re-read constant) → a
dedicated Streamlit page. Mirrored for leverage, with one structural
difference: leverage computation happens in `engine/run.py` right after
`CV.build()` returns (not inside `build()`), because the regime is a
per-run user choice (Home page toggle) rather than a fixed file — this
keeps `customer_view.build()`'s signature untouched.

No `tests/` directory or pytest anywhere in the repo (confirmed by search).
The only testing convention is `audit/` — standalone, print-based diagnostic
scripts run directly with `python`. Followed that convention:
`audit/audit_leverage_capital.py` (assert-driven, worked examples T-01/T-02/
T-03/T-08/T-09/T-13 plus the five validation-rule tests) — run it with:

```
python audit/audit_leverage_capital.py
```

All checks pass as of this writing (verified via the PowerShell tool during
the build, matching the spec's own worked-example numbers exactly: Case A
capital 32.00/cost 3.84, Case B all-zero, non-UCC-≤1y capital 64.00/cost
7.68).

`pyyaml` is a declared dependency in `app/requirements.txt` /
`datagen_app/requirements.txt` but is **not actually used anywhere** in the
live `engine/`/`app/` code — the real, exercised convention is JSON. Used
JSON for the two case policy files, matching `liquidity_policy.json` exactly,
rather than introducing the first real YAML usage in the repo.

## Stage 2 — Rule register (done)

`governance/REGULATORY_RULEBOOK.md` and `governance/regulatory_verification_log.md`
created at the repo root (no `governance/` folder existed there before —
only `engine/governance/` for the fairness/negative-control *code modules*,
a different thing entirely; don't confuse the two). Every rule from the
supplied rulebook is present, Code location and Test columns filled in
against this implementation, verification log seeded with every rule `OPEN`.

## Stage 3 — Policy schema, two case files, validation (done)

`engine/config/leverage_capital_policy.case_a_slr_category_iii.json` and
`...case_b_tier1_regional.json`, following the YAML schema in the spec
field-for-field but in JSON. `leverage_capital.validate_policy()` implements
V-01 through V-09 (errors: V-01, V-04, V-06, V-07-in-SLR-mode; warnings:
everything else) — verified in `audit_leverage_capital.py`.

## Stage 4 — Core calculation (done)

`engine/core/leverage_capital.py:compute()`. Matches the spec's formula and
worked examples exactly (see Stage 1 test results). One adaptation: operates
on `customer_view.avg_undrawn_12m` (the same trailing-12-month base the
liquidity cost diagnostic already uses) rather than per-account-per-ledger-
period, for consistency with every other customer-level figure in this
engine — documented as a gap (R-13) rather than silently assumed equivalent
to regulatory quarterly-average reporting.

Always computes a "shadow" SLR-as-if cost regardless of the active regime
(T-10: never read downstream when `slr_mode` is false) — this powers the
optional "if this bank were SLR" panel on the Leverage page.

## Stage 5 — Ledger/CEV/PLI integration (partially applicable)

**This system has no CELTV and no PLI concept** — those are from a different
system than this one; M-01's intent ("never blend into a headline figure")
was carried out against what this system actually has: `customer_view`
columns, `trailing_12m_net_economic_profit`, `cev_score`, `cev_band`,
`is_below_cost`. Verified unchanged under both policy toggles (identical
total NEP, $2,526,782.39, confirmed by direct script run for both Case A
and Case B against the bundled sample portfolio).

`engine/core/outputs.py:score_file()` carries `leverage_regime`,
`leverage_status`, `leverage_exposure`, `leverage_capital_cost` through to
the downloadable score file, with correct NA-handling for suppressed
customers (same pattern as the liquidity columns).

## Stage 6 — L2 wiring and consumer protection (done, with one scope note)

`engine/levers/l2_lines.py`: DECREASE/DECREASE_RISK_EXPOSURE now also prices
leverage capital freed; INCREASE now also *subtracts* leverage capital
consumed from its priced value (M-02 symmetry) — both $0 under Tier 1 by
construction, confirmed in the test run (T-11 equivalent, verified manually:
Case B run showed `$0`/`$0` for both; Case A run showed `$1,681/yr` freed).

**C-03 (fair lending side-by-side) scoped down**: the spec asks for the
existing fairness analysis to run under both toggle positions and be
reported side by side on the diagnostic page. Not built as a literal dual
pipeline re-run in this pass — `slr_mode` only changes the dollar value
attached to an already-determined DECREASE population, never which
customers are selected, so the population (and therefore the fairness
result) is provably identical either way. This is documented as a standing
note on the Leverage page and in the rulebook (C-03) rather than built as a
second, redundant pipeline execution. If you want the literal side-by-side
view anyway (e.g. for an auditor who wants to see it, not just be told it's
identical), that's a contained follow-up: re-run `FAIR.run()` against the
same `routed.frame` under the other policy's L2 sizing and diff the two
fairness dicts.

## Stage 7 — Run audit trail (done, scoped)

No pre-existing SHA-256 model-registry/audit-trail pattern exists anywhere
in this codebase to extend (confirmed by search — the only other `sha256`
usage in the app is an unrelated upload-cache key). Built a lightweight
per-run audit dict instead (`result["leverage_audit"]`, also written into
`run_summary.json` when run via the CLI `engine/run.py`): run timestamp,
active policy file name + SHA-256, `slr_mode`, rule IDs applied, validation
warnings, `inputs_verified`, and totals. This is attached to the run result,
not a persisted/queryable registry — a genuine registry (a database or
append-only log of every run ever made) would be new infrastructure for this
repo and was out of scope for this pass.

## Stage 8 — Leverage Diagnostic page (done, scoped)

`app/pages/24_Leverage_Capital.py`. Built: regime banner with verification-
status flag, plain-English explainer, portfolio KPIs, cost-as-%-of-NEP
context line, the "if this bank were SLR" shadow panel (Tier 1 mode only),
by-segment chart + table, the L2 leverage slice (points to Levers & Strategy
for the full picture rather than duplicating it), the rule-IDs-applied audit
expander, and a filterable customer-level table.

**Not built**: the interactive CCF/target-ratio/cost-of-capital sensitivity
("what-if") grid from spec §7.2.8. The two case-file toggle already lets a
user compare two concrete scenarios; a live slider-driven grid is a
meaningfully larger UI piece and was judged lower priority than getting the
core diagnostic, L2 wiring, and audit trail right in this pass.

## Stage 9 — Docs (done)

`ARCHITECTURE.md` §4 (new subsection before `core/suppression.py`) and
`app/README.md`'s page list both updated, matching the documentation
discipline already established in this repo for every prior feature. This
file (`STATUS.md`) stands in for the spec's own stage-by-stage status
tracking.

## Stage 10 — Regression and delivery

No zip package produced (this is a live, version-controlled repo, not a
drop-in patch delivery — changes are committed directly to `main` via git,
per how every other feature in this session has shipped). All new/changed
files:

**New:** `engine/core/leverage_capital.py`,
`engine/config/leverage_capital_policy.case_a_slr_category_iii.json`,
`engine/config/leverage_capital_policy.case_b_tier1_regional.json`,
`app/pages/24_Leverage_Capital.py`, `audit/audit_leverage_capital.py`,
`governance/REGULATORY_RULEBOOK.md`, `governance/regulatory_verification_log.md`,
`STATUS.md`.

**Modified:** `engine/run.py`, `engine/levers/l2_lines.py`,
`engine/core/outputs.py`, `app/lib/pipeline_runner.py`, `app/lib/charts.py`,
`app/Home.py`, `ARCHITECTURE.md`, `app/README.md`.

Regression-checked by hand (direct pipeline runs + browser walkthrough of
both regimes against the bundled sample portfolio) rather than an automated
regression suite, since none exists in this repo: total NEP, below-cost
count, and CEV distribution confirmed byte-identical between the two
`slr_mode` settings.
