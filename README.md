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

A ready-to-use demo portfolio is bundled — the app's home page has a one-click "try the sample data" option, no upload needed to explore it.

## Project layout

- `generator/` — synthetic portfolio data generator (demo data only; no real customer data)
- `engine/` — the analysis pipeline: data contract validation, economic ledger, customer-level view, lever routing and sizing, governance checks
- `app/` — the Streamlit application
- `samples/` — a ready-to-use demo portfolio, bundled for trying the app immediately
