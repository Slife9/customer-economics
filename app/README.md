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

The **ML second opinion** tab of the L2 page needs a trained model bundle to populate -
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

The sidebar is grouped (`app/Home.py` is the entrypoint and only builds the
navigation; the page registry is `app/lib/nav.py`):

**Overview**
- **Home** — upload, run, executive summary (KPIs, revenue/cost waterfall,
  CEV band distribution, the card-only-vs-relationship-view finding).
- **Portfolio Economics** — the three measured-not-assumed quantities, cost
  waterfall, product mix, NEP by segment and score band, full customer table.

**Strategies**
- **Strategy Overview** (formerly Levers & Strategy) — all six levers at a
  glance with base value and low–high range, the sequencing roadmap, and a
  customer lookup across every lever.
- **L1–L6 lever pages** — one page per lever (what it does, who is in scope,
  what it could be worth, assumptions, what-if explorer, how it's calculated,
  regulation, and a customer drill-down with admin review notes).
  - **L2 Credit Lines & Unused-Line Cost** also holds what used to be the
    **Liquidity** page (regulatory liquidity cost of unused lines, 12 CFR 249,
    policy inputs in `engine/config/liquidity_policy.json`) and the
    **ML Credit Limit** page (CES's machine-learning second opinion, trained
    offline with `python -m engine.ml.train_credit_limit_model`, plus the
    L2-vs-ML agreement view). Full ML detail in `engine/ml/MODEL_CARD.md`.
  - **L6 Channel Quality Review** also holds what used to be the
    **Acquisition Cost** page (CAC payback, a lifetime view kept separate from
    CEV; needs `Table23_Acquisition.csv` with `Acquisition Cost USD`).

**Governance & Outputs**
- **Governance & Fairness** — the negative-control gate chart and table, the
  four-fifths test on score and treatment, the ML treatment fairness check
  (moved here from the ML page), and the suppression breakdown.
- **Downloads** — the five outputs (score file, worklist, leakage register,
  governance pack, ledger) as CSV/JSON.

**Reference**
- **Lever Playbook** — what each lever is, how it is sized, and its gates.

## Regenerating the sample zips

```bash
cd generator
python run.py --profile demo --out ./out/demo
python run.py --profile negative_control --out ./out/negative_control
cd ..
Compress-Archive -Path generator/out/demo/* -DestinationPath samples/demo_portfolio.zip -Force
Compress-Archive -Path generator/out/negative_control/* -DestinationPath samples/negative_control_portfolio.zip -Force
```
