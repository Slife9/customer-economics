# Decisions log

Decisions received after the Stage 1 audit, newest first. Open decisions with the boss
(B4–B8) are in `OPEN_DECISIONS.md` and stay behind config flags.

## 15 Nov 2026: base branch (replaces the earlier answer to Question 1)

- `feature/unused-line-management` is created from `main` (`b660bb8`). Neither
  `feature/lever-valuation-rebuild` nor `feature/l1-rewards-system` is merged into it.
- Standalone app, like the rewards system: `engine/unused_lines/` and `unused_lines_app/`, with its
  own engine, pages, per-account data file and precomputed sample.
- The L1 Rewards system is a reference only. Shared UI pieces (state, style, guide components,
  page layout) are **copied** with a note of the source branch and commit, never merged, and kept
  self-contained so the two apps can evolve independently.
- New tables start at **Table29** (`Table29_Score_History`, `Table30_Card_Activation`).
  Tables 25–28 stay reserved for the reward additions so nothing clashes at merge time.
- Generator additions are additive only: existing tables on `main` byte-identical, separate random
  stream, baseline hash check.
- No longer applicable: the `STATUS.md` merge resolution; exposing a summary to the six-strategy
  overview (skipped for now; outputs are designed so they *can* be read later: low / base / high
  and value types).
- The rebuilt L2 page's use of the old carrying-cost logic is recorded in `ISSUES_FOUND.md` as a
  known issue on the other branch; no action.
- Still applies: L2, the ML model, NEP, CEV, suppression, routing and the fairness module are read
  and called only. The §2.7 reconciliation and the 2 GB memory test may read data or bundles from
  other branches or a local scratch area, read-only. The ML fairness re-run (adverse actions vs
  increases, saved to file).

## Answers to Questions 2–9

Referred to as "given" in the 15 Nov message but **not received in this session**. Until they
arrive, the work below uses only what does not depend on them, and the Stage 1 proposals are
**not** treated as accepted:

| # | Question | Status |
|---|---|---|
| 2 | Word re-save of the strategy report | Parked in `git stash` on the docs branch, nothing lost |
| 3 | Carrying cost = capital + liquidity, drawdown EL beside it | Pending |
| 4 | Credit loss in the profit view | Pending |
| 5 | Transactor test details | Pending |
| 6 | New data | Table29 / Table30 confirmed by the 15 Nov message; household and investments pending |
| 7 | Unassigned LEQ; valuation of the two levers without workbook values | Pending |
| 8 | Rebuild the 100k bundle | Pending |
| 9 | Unused-line stress generator profile | Pending (not built) |
