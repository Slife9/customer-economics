# Stage 6 report: treatment designer, compliance checks, timing

Branch `feature/unused-line-management`, base `main` `b660bb8`. 16 Nov 2026.

## Built

`engine/unused_lines/treatment.py`, with settings in config `treatment` and `timing`:

- **Per account in scope** (Base scenario's selection): recommended lever(s); line action (decrease
  / closure / none), new line and cut; **mandatory reason code** (`INACTIVITY`,
  `CREDIT_DETERIORATION`, `IDLE_LINE_RIGHTSIZING`, `CUSTOMER_REQUEST`, `OTHER`) for every action; the
  notice it triggers; adverse-action and FCRA flags; the 45-day over-limit fee / penalty-rate
  restriction after any decrease; the ability-to-pay flag (no increases in this module);
  "pending approval" for B6 levers; ML view and agreement flag; review-together flags; pilot cell.
- **Notices by reason** (summary for discussion; to be confirmed by compliance):
  - credit deterioration: Reg B adverse action notice within 30 days, plus an FCRA score disclosure
    check (a bureau-based score feeds both the PD and the score-drop rule);
  - idle-line right-sizing: treated as adverse action (a reduction not in connection with
    inactivity, default or delinquency);
  - inactivity: no adverse action notice (Reg B exception), reason code recorded;
  - campaigns and increase suppression: `OTHER`, no notice;
  - no lever proposes an inactivity fee (checked).
- **ML model, second opinion only**: all seven actions; its cut rules read from its own policy and
  code (≤ 25% per account, ≤ 5% of accounts per review, each cut ≥ 15% and ≥ $500); agreement
  flag: agree / disagree / ML has no view (insufficient history, not eligible, manual review, no
  score). Recommendations are identical with or without the ML view (checked).
- **Fairness**: the system's existing four-fifths test by metro, run three ways and saved: module
  decreases and closures, ML adverse actions (decrease, freeze), ML increases.
- **Review together**: customers also in the system's L1, L3 or L5 worklists on `main`
  (`engine.run.build_pipeline`, read only). No prioritisation rule.
- **Pilot cells**: 10% holdout, seeded, stratified by segment (configurable).
- **Timing**: start, full value and year-1 share per lever (config); year-1 and full annual value
  side by side.

## Results (stress book, Base)

- 4,652 accounts in scope; 3,566 with at least one action.
- Reason codes: inactivity 1,145; idle-line right-sizing 203; credit deterioration 86; other 2,132.
  Line actions: 1,037 decreases, 374 closures (pending approval).
- ML view: agree 2,988; disagree 1,626 (mostly module cuts where the ML model says MAINTAIN: it cuts
  at most 5% of accounts per review); no view 38.
- Pilot: 357 holdout, 3,209 treatment. Review together: 1,954 accounts (mostly L1 rewards).
- Year-1 vs full, headline levers: $32,670 vs $47,599 (workbook levers and extra levers).

**Fairness: failures, flagged.** Module decreases and closures fail the four-fifths test in 14 of 64
metros; ML adverse actions in 17 of 66; ML increases in 59 of 66 (9 increases in the whole book, so
those rates are noise). 5k demo: 19 of 48, 21 of 55, 34 of 55. A fair-lending review is needed before
any pilot (`ISSUES_FOUND.md` #10).

## Tests run

`audit/audit_unused_line_module.py` section 10 on the stress book and the 5k demo: 11 checks each,
all pass. Full run without the 100k checks: **96/96 passed**. The full run with 100k is in the
Stage 8 suite.
