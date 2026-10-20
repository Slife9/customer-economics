# Customer Economics System

A profitability analytics engine and Streamlit app for US retail bank card portfolios, built for ProfitInsight. It turns raw account, transaction, and cost data into per-customer economic profit, and routes underperforming customers to the specific pricing, servicing, or credit-line lever most likely to fix it — with dollar-sized, evidence-based impact estimates instead of guesses.

## What it does

- Builds a full customer-level P&L (interchange revenue, rewards expense, funding cost, credit cost, servicing cost, capital cost) from portfolio data
- Flags below-cost customers and routes each one to the single lever most responsible for the loss: rewards pricing, credit line management, risk-based pricing, cost-to-serve, retention, or acquisition channel mix
- Sizes the dollar opportunity of each lever, and deliberately refuses to price outcomes the data can't actually support (labeled as unpriced context instead of a fabricated number)
- Validates every lever's effect against a negative control portfolio before it's reported as real
- Runs a fairness check on outcomes across customer geography
- Ships as a Streamlit app: upload a portfolio (zipped), get an executive summary, drill into any customer's full economic workup, and read a dedicated playbook explaining every lever and how it was sized

## Running it

```
cd app
pip install -r requirements.txt
streamlit run Home.py
```

A ready-to-use demo portfolio is bundled — the app's home page has a one-click "try the sample data" option, no upload needed to explore it. That button loads a pre-computed 50,000-customer results bundle (not a live engine run), so it also doubles as a live example of the results-bundle feature described below. A raw, smaller (5,000-customer) portfolio zip is still available under `samples/demo_portfolio.zip` for manually testing the normal upload-and-run path.

### Analyzing a portfolio too large to upload or re-run on the hosted app

The engine's memory use grows with portfolio size (roughly 7 GB RSS at
~48,500 customers), and a 50,000-customer portfolio is multiple GB on disk —
both well past what the hosted app's instance or upload limit can handle.
For a portfolio that size, run the engine locally and export a compact
**results bundle** instead:

```
python -m engine.export_bundle --data <portfolio_dir> --out <bundle.zip>
```

Add `--compare-to <control_dir>` to also compute and store the finished
negative-control gate report. Then, in the app, use the **"Load pre-computed
results (.zip)"** option in the sidebar (next to the normal portfolio
upload) to load that bundle directly — no re-analysis, no large upload. A
bundle never contains raw transactions or other large input tables (it's
Parquet + JSON, validated on load, never pickled), so a feature that
genuinely needs that detail — the per-customer transaction drill-down — says
so plainly instead of erring. See [`ARCHITECTURE.md`](ARCHITECTURE.md)
section 8a for the full format and what's deliberately left out, and
[`STATUS.md`](STATUS.md) for measured bundle size/time/memory.

## Project layout

- `generator/` — synthetic portfolio data generator (demo data only; no real customer data)
- `engine/` — the analysis pipeline: data contract validation, economic ledger, customer-level view, lever routing and sizing, governance checks
- `app/` — the Streamlit application
- `datagen_app/` — a second, standalone Streamlit app that generates a fresh synthetic test portfolio via a few sliders (scenario, size, horizon, data-quality issue rate), deployed separately so anyone can create new test data without touching the generator directly
- `samples/` — a ready-to-use demo portfolio, bundled for trying the app immediately

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the full technical reference — the engine's pipeline internals, every lever's logic, the bug-fix history, deployment details, and open items. `generator/README.md` and `app/README.md` cover those two pieces in their own depth.
