# L1 Rewards Profitability (standalone app)

```bash
streamlit run rewards_app/Home.py
```

Install with `pip install -r app/requirements.txt`. The app opens on port
8501, or 8503 through the `profitinsight-rewards` launch config.

**What it does.** It finds the reward accounts that lose money, sorts them
into the segments of the *Reward Profitability Scenario Model v2*, and
values that workbook's nine reward levers on a portfolio's own data, under
Conservative, Base and Aggressive. Only the L1 rewards lever is covered; the
six-lever app in `app/` is separate and unchanged. The model lives in
`engine/rewards/`.

| Page | What it shows |
|---|---|
| Load portfolio | Bundled samples (`reward_stress`, `demo`) or an uploaded zip. Tables 25-27 are computed if missing and the folder has a build manifest |
| Scenario dashboard | The workbook's comparison (Baseline, Conservative, Base, Aggressive), results by segment for one scenario, and a stress test at 1.5x / 2x customer response |
| Segments | Screen funnel, segment mix and profiles against the workbook, the rules, and why accounts end up Unassigned |
| Levers & assumptions | The workbook's defaults: levers by scenario and segment, customer response, portfolio rates, thresholds. Editable for this session, with reset and download |
| Customer drill-down | Worklist (filters, CSV). For one account: the screen and every segment rule, baseline and post-change P&L, leave probability and spend change, recommended actions |
| Lever guide & regulation | What each lever is, actions by segment, how the model works, US guardrails |
| Data & calibration | Where each figure comes from, reconciliation to the engine, limitations |
| Downloads | Account results, segment summary, and the assumptions in use |

**What's measured and what's assumed.**
- **Measured:** each account's trailing-12-month P&L from the engine's card
  ledger, plus a sign-up bonus earned in that window. The bonus comes from
  Table26 and is a reward-model cost, not part of the engine's profit.
- **Assumed:** the levers, customer response and portfolio rates. These are
  the workbook's illustrative industry averages, kept in
  `engine/rewards/config/reward_model_assumptions.json` with the workbook's
  sha256.
- Every post-change figure is an expected value. Pilot before acting.

**Tests:** `python audit/audit_l1_rewards_system.py` (13 checks). It includes
reproducing the workbook to the cent.
