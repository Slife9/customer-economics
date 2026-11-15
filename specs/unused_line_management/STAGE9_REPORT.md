# Stage 9 report: documentation, evaluation guide, deployment preparation

Branch `feature/unused-line-management`, base `main` `b660bb8`. 16 Nov 2026. Not pushed, merged or
deployed.

## Written

| File | Content |
|---|---|
| `docs/UNUSED_LINE_METHODOLOGY.md` | Part 1 in plain language (the question, five steps, reading the results, cautions); Part 2 technical (code map, formulas per account, screen and segments, levers, workbook mode, treatment, data, results on the samples) |
| `ARCHITECTURE.md` | New §8b for the module (design, modes, config, data, app, docs, module invariants); repository map |
| `STATUS.md` | New section on top: what is done, how to test, build requirements with the machine spec, what is open |
| `specs/unused_line_management/EVALUATION_GUIDE.md` | Commands; which dataset to load; checks per page with expected figures; three example customers per segment (typical, borderline, review-together); known limits; sign-off checklist; Streamlit Community Cloud steps |
| `specs/unused_line_management/ISSUES_FOUND.md` | 15 issues (L2 lifetime-PD defect, old carrying-cost logic on the lever-valuation branch, chunked generation, calibration gaps, fairness, engine cost split, go / no-go basis, …), the merge clashes ("keep both sides") and the branch merge order |
| `unused_lines_app/README.md` | How to run, build a dataset, deploy |

## Deployment preparation (not deployed)
- Entry point `unused_lines_app/Home.py`; `unused_lines_app/requirements.txt` pinned to the versions
  tested here (streamlit 1.54.0, pandas 2.3.3, numpy 2.4.2, plotly 7.1.0, pyarrow 23.0.0, pyyaml
  6.0.3, scikit-learn 1.9.1, joblib 1.6.0).
- Committed samples only (3.8 MB in total); no secrets; the shared `.streamlit/config.toml` theme.
- Steps in the evaluation guide §5. Render stays on hold.

## Tests
No code changed in this stage; the Stage 8 suite (109/109) stands.
