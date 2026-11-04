# L1 Rewards Profitability (standalone app)

```bash
streamlit run rewards_app/Home.py --theme.baseFontSize 18 --server.maxUploadSize 4000
```

Install with `pip install -r app/requirements.txt` (`rewards_app/requirements.txt`
is the same list, for Streamlit Community Cloud, which reads the file next to
the main file; deploy `rewards_app/Home.py`). The app opens on port
8501, or 8503 through the `profitinsight-rewards` launch config.
- `--theme.baseFontSize 18` enlarges the tables too; the rest of the app's
  larger text works without it.
- `--server.maxUploadSize 4000` (MB) lets large portfolios be uploaded. The
  shared `.streamlit/config.toml` allows 500 MB.

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

**Your own data.** Use **Upload your data** (in the sidebar on every page).
1. Upload a zip of the portfolio's table CSVs: the engine's data contract,
   plus Table16, and Table25/26 or the generator's `build_manifest.json`.
2. The page checks the zip's contents at once.
3. **Run the analysis** builds each account's P&L. This takes seconds for
   5k customers and a few minutes for 100k.
4. Every page then shows that portfolio.

Save the prepared `.parquet` the page offers. Uploading it later skips the
rebuild. A browser refresh starts a new session on the bundled sample.

| Page | What it shows |
|---|---|
| Overview (landing) | Figure cards (today, measured; with the levers, expected), key takeaways, and charts: profit today vs each scenario, profit gained vs accounts lost, segment mix, where the loss sits, the revenue-to-cost waterfall, the improvement by segment, the stress test, and reward cost % of revenue by segment |
| Scenario dashboard | The scenario comparison table (Baseline, Conservative, Base, Aggressive), results by segment for one scenario, and a stress test at 1.5x / 2x customer response |
| Segments | Screen funnel, segment mix and loss, segment profiles and charts, the rules, and why accounts end up Unassigned |
| Levers & assumptions | The model's defaults: levers by scenario and segment, customer response, portfolio rates, thresholds. Editable for this session, with reset and download |
| Customer drill-down | Worklist (filters, CSV). For one account: the screen and every segment rule, baseline and post-change P&L, leave probability and spend change, recommended actions |
| Upload your data | Upload a zipped portfolio or a prepared .parquet; instant check of the zip's contents; step-by-step run; headline results; save the prepared file; back to the bundled sample. Tables 25-27 are computed if missing and the zip has a build manifest |
| Data & calibration | Where each figure comes from, reconciliation to the engine, limitations |
| Downloads | Account results, segment summary, and the assumptions in use |
| Lever guide & regulation | What each lever is and when it pays; when each lever starts earning and reaches full value, its year-1 share, and its annual and year-1 value for a scenario (table, timeline, annual vs year-1 chart); what drives the timing; actions by segment; how the model works; US guardrails |

**What's measured and what's assumed.**
- **Measured:** each account's trailing-12-month P&L from the engine's card
  ledger, plus a sign-up bonus earned in that window. The bonus comes from
  Table26 and is a reward-model cost, not part of the engine's profit.
- **Assumed:** the levers, customer response and portfolio rates. These are
  the workbook's illustrative industry averages, kept in
  `engine/rewards/config/reward_model_assumptions.json` with the workbook's
  sha256.
- **Timing (estimated, not from the workbook):** when each lever starts
  earning, when it reaches full value, and the share of its annual value
  earned in year 1 (`lever_timing` in the same file, editable). Scenario
  figures are full annual values; the Year 1 figures on the Overview,
  Scenario dashboard and Lever guide split each scenario's change across
  the nine levers (Shapley values, which add up exactly to the total) and
  apply each lever's year-1 share.
- Every post-change figure is an expected value. Pilot before acting.

**Tests:** `python audit/audit_l1_rewards_system.py`. It includes
reproducing the workbook to the cent and checks on the 100k sample. Add
`--scale` to also prove that a fresh 100k generator run rebuilds the sample
identically, which takes about 30 minutes.
