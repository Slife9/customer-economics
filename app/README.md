# ProfitInsight Customer Economics System — App

A Streamlit front end over `engine/`. Upload a zipped portfolio, it runs the
full pipeline (data contract → ledger → customer view → suppression →
routing → six levers → governance), and shows the result as an executive
summary, a per-lever strategy section, a per-customer drill-down, and the
governance/negative-control gate.

## Run it in VS Code

1. Open this repo as the VS Code workspace root.
2. Install dependencies (once):
   ```bash
   pip install -r app/requirements.txt
   ```
3. Either press **F5** (uses `.vscode/launch.json`, already configured), or
   from an integrated terminal:
   ```bash
   streamlit run app/Home.py
   ```
4. It opens at `http://localhost:8501`. Upload a portfolio zip in the
   sidebar — `samples/demo_portfolio.zip` is ready to go — or click **"Try
   it with the bundled sample portfolio"** to load
   `samples/demo_portfolio_50k_bundle.zip`, a pre-computed 50,000-customer
   results bundle, instantly (see ARCHITECTURE.md §8a). Neither of these
   two one-click paths currently demos the negative-control gate; to see
   that, run `python -m engine.run --compare-to <control_dir>` or export a
   bundle with `--compare-to` and load it (`samples/negative_control_portfolio.zip`
   is the matching control for the raw `demo_portfolio.zip`).

The **ML Credit Limit** page needs a trained model bundle to populate -
`engine/ml/artifacts/credit_limit_model_bundle.joblib` is already committed,
so no extra step is needed to try it. To retrain (e.g. after a feature
change), run `python -m engine.ml.train_credit_limit_model` - see
`engine/ml/MODEL_CARD.md`.

For a portfolio too large to upload or re-run here (see ARCHITECTURE.md
§8a), use **"Load pre-computed results (.zip)"** in the sidebar instead,
below the normal upload — it loads a bundle exported locally with
`python -m engine.export_bundle`, with no re-analysis needed.

## What to upload

A zip of a portfolio folder as produced by `generator/run.py` — i.e. the
contents of `generator/out/demo/` (or any folder with `Table1_Customer.csv`,
`Table2_Card_Account.csv`, etc. at its root, or one level deep inside the
zip). The `_ground_truth/` folder can be included or left out — the app
never reads it either way; it only uses it, if present, to check the
negative control gate's "zero planted defects" assertion.

## Pages

- **Home** — upload, run, executive summary (KPIs, revenue/cost waterfall,
  CEV band distribution, the card-only-vs-relationship-view finding).
- **Portfolio Economics** — the three measured-not-assumed quantities, cost
  waterfall, product mix, NEP by segment and score band, full customer table.
- **Levers & Strategy** — the sequencing roadmap, a strategy card per lever
  (population, priced value or an explicit "None, by design" with unpriced
  context, gates, sample worklist), and a customer drill-down showing every
  lever action recommended for one customer plus their full relationship
  waterfall and acquisition-cost payback status.
- **Acquisition Cost** — a lifetime view, deliberately separate from CEV:
  whether what it cost to acquire each customer has actually been earned back
  yet, and how long that took. Portfolio summary, payback-status and
  months-to-recover charts, a per-channel breakdown (complements L6), and a
  filterable customer-level table. Needs `Table23_Acquisition.csv` with an
  `Acquisition Cost USD` column to populate; degrades to an explanatory
  message without it.
- **Liquidity** — another diagnostic kept separate from CEV: the opportunity
  cost of holding the HQLA the US LCR rule (12 CFR 249) requires against each
  customer's unused credit line. Portfolio summary (undrawn exposure, required
  HQLA, annual cost, count needing individual assessment), a by-segment chart
  and table, and a filterable customer-level table. Policy inputs (outflow
  rate by segment, yield gap) live in `engine/config/liquidity_policy.json`.
- **ML Credit Limit** — CES's first real machine-learning diagnostic: a
  replica of the sibling `credit-limit-recommendation-system` repo's
  capability, trained offline on this repo's own generator output
  (`python -m engine.ml.train_credit_limit_model`), scored live against the
  committed bundle. Forecasts (risk, spend, peak balance) feed a ported
  pressure-score/stress-flag/9-step-waterfall rules engine for one of seven
  actions and a recommended limit — the model never sets a dollar figure.
  Shows L2's existing action alongside the ML action (two independent
  engines, agreement is a sanity check not a requirement), a dedicated
  fairness check on the ML treatment, and the same misleading-aggregate
  caveat on its money figures the sibling repo states about its own. Full
  detail in `engine/ml/MODEL_CARD.md`.
- **Governance & Fairness** — the negative-control gate chart and table, the
  four-fifths test on both score and treatment, and the suppression breakdown.
- **Downloads** — the five outputs (score file, worklist, leakage register,
  governance pack, ledger) as CSV/JSON.

## Regenerating the sample zips

```bash
cd generator
python run.py --profile demo --out ./out/demo
python run.py --profile negative_control --out ./out/negative_control
cd ..
Compress-Archive -Path generator/out/demo/* -DestinationPath samples/demo_portfolio.zip -Force
Compress-Archive -Path generator/out/negative_control/* -DestinationPath samples/negative_control_portfolio.zip -Force
```
