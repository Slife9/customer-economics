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

- Loads only the committed samples in `samples/unused_lines/` (stress book 100,000 customers,
  synthetic stress data; the 5k demo). Runtime peak about 1.5 GB.
- Build a dataset offline from a portfolio folder:
  `python -m unused_lines_app.build_sample --data <dir> --name <name> --label "<label>"`.
- Assumptions edited on **Levers & assumptions** apply to the session only (exploration).
- Streamlit Community Cloud: main file `unused_lines_app/Home.py`; requirements next to it; no
  secrets. Deployed: https://profitinsight-unused-lines.streamlit.app (steps in
  `specs/unused_line_management/EVALUATION_GUIDE.md`).
- Layout and style follow `rewards_app/` on `feature/l1-rewards-system` (`495b0ec`): copied, not
  merged.

Method: `docs/UNUSED_LINE_METHODOLOGY.md`. Tests: `python audit/audit_unused_line_module.py --regression`.
