# L1 Rewards Profitability (standalone app)

```bash
streamlit run rewards_app/Home.py --theme.baseFontSize 18
```

Install with `pip install -r app/requirements.txt`. The app opens on port
8501, or 8503 through the `profitinsight-rewards` launch config. The
`--theme.baseFontSize 18` flag enlarges the tables too; the rest of the
app's larger text works without it.

**What it does.** It finds the reward accounts that lose money, sorts them
into the segments of the *Reward Profitability Scenario Model v2*, and
values that workbook's nine reward levers on a portfolio's own data, under
Conservative, Base and Aggressive. Only the L1 rewards lever is covered; the
six-lever app in `app/` is separate and unchanged. The model lives in
`engine/rewards/`.

**Data.** The app opens on the bundled 100,000-customer sample, which loads
in a few seconds. It is `samples/reward_stress_100k_accounts.parquet`: the
per-account frame built from a `reward_stress` generator run (100,000
customers, default seed). The run's raw tables come to about 5 GB, too large
to ship. Rebuild the sample, which takes about 15 minutes:

```bash
python -m rewards_app.build_sample
```

Your own portfolio can be uploaded as a zip on **Load portfolio**.

| Page | What it shows |
|---|---|
| Overview (landing) | Figure cards (today, measured; with the levers, expected), key takeaways, and charts: profit today vs each scenario, profit gained vs accounts lost, segment mix, where the loss sits, the revenue-to-cost waterfall, the improvement by segment, the stress test, and reward cost % of revenue by segment |
| Scenario dashboard | The scenario comparison table (Baseline, Conservative, Base, Aggressive), results by segment for one scenario, and a stress test at 1.5x / 2x customer response |
| Segments | Screen funnel, segment mix and loss, segment profiles and charts, the rules, and why accounts end up Unassigned |
| Levers & assumptions | The model's defaults: levers by scenario and segment, customer response, portfolio rates, thresholds. Editable for this session, with reset and download |
| Customer drill-down | Worklist (filters, CSV). For one account: the screen and every segment rule, baseline and post-change P&L, leave probability and spend change, recommended actions |
| Load portfolio | The bundled sample, or an uploaded zip. Tables 25-27 are computed if missing and the folder has a build manifest |
| Data & calibration | Where each figure comes from, reconciliation to the engine, limitations |
| Downloads | Account results, segment summary, and the assumptions in use |
| Lever guide & regulation | What each lever is, actions by segment, how the model works, US guardrails |

**What's measured and what's assumed.**
- **Measured:** each account's trailing-12-month P&L from the engine's card
  ledger, plus a sign-up bonus earned in that window. The bonus comes from
  Table26 and is a reward-model cost, not part of the engine's profit.
- **Assumed:** the levers, customer response and portfolio rates. These are
  the workbook's illustrative industry averages, kept in
  `engine/rewards/config/reward_model_assumptions.json` with the workbook's
  sha256.
- Every post-change figure is an expected value. Pilot before acting.

**Tests:** `python audit/audit_l1_rewards_system.py`. It includes
reproducing the workbook to the cent and checks on the 100k sample. Add
`--scale` to also prove that a fresh 100k generator run rebuilds the sample
identically, which takes about 30 minutes.
