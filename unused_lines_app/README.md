# Unused Credit Line Management app

Standalone Streamlit app over `engine/unused_lines/`: which card accounts carry costly unused lines,
what line management is worth, and what each customer would be offered, under the agreed working
assumptions (March 2026 Basel III endgame proposal treated as adopted; conservative LCR outflow).

```bash
python -m pip install -r unused_lines_app/requirements.txt
```
```bash
python -m streamlit run unused_lines_app/Home.py --theme.baseFontSize 18
```

- **Two views** (sidebar): **Executive** (default) - nine pages that follow the project report and
  the stakeholder slides, in their order and words (Executive summary, The problem, How unused credit
  costs money, Customers and where the cost sits, The four strategies, What they are worth,
  Implementation, Protecting customers and risks, Customer evidence), always on the stress book;
  **Analyst** - the same pages with formulas, value types, the levers and full tables, the dataset
  switch, plus Explore & reference (What-if, Levers & lever guide, Data & calibration, Technical).
- Every executive page: one headline sentence, at most four cards, one main chart, detail in
  expanders, no PD / LGD / LEQ / RWA / LCR (checked by the suite).
- Executives see four **strategies** (`engine/unused_lines/strategies.py`); the levers stay
  underneath, in the analyst view.
- Loads only the committed samples in `samples/unused_lines/` (stress book 100,000 customers,
  synthetic stress data; the 5k demo). Runtime under 2 GB (all pages, both views, both datasets, one
  process; measured by the suite).
- Build a dataset offline from a portfolio folder:
  `python -m unused_lines_app.build_sample --data <dir> --name <name> --label "<label>"`; add the
  revision-E balance columns to an existing sample with `--name <name> --update-balance-basis`.
- Assumptions edited on **What-if** (analyst view) apply to the session only (exploration).
- Streamlit Community Cloud: main file `unused_lines_app/Home.py`; requirements next to it; no
  secrets. Deployed: https://profitinsight-unused-lines.streamlit.app (steps in
  `specs/unused_line_management/EVALUATION_GUIDE.md`).
- Layout and style follow `rewards_app/` on `feature/l1-rewards-system` (`495b0ec`): copied, not
  merged.

Method: `docs/UNUSED_LINE_METHODOLOGY.md`. Tests: `python audit/audit_unused_line_module.py --regression`.
