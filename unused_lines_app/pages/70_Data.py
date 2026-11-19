import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from unused_lines_app.lib import state as S, style as Y  # noqa: E402

S.header("🧪 Data & calibration")
S.analyst_only()
i = S.info()

Y.band("The dataset in use")
S.md(
    f"- **{i['label']}** - generator profile `{i['profile']}`, seed {i['seed']}, {i['customers']:,} customers, "
    f"{i['card_accounts']:,} card accounts, {i['cycles']} months ({i['from']} to {i['to']}).\n"
    f"- Precomputed offline by `python -m unused_lines_app.build_sample` in {i['build_seconds']} s, peak memory "
    f"{i['build_peak_memory_gb']} GB, on {i['machine']['os']}, {i['machine']['cpus']} CPUs, {i['machine']['ram_gb']} GB RAM. "
    "The app loads only these files: " + ", ".join(f"{k} ({v} MB)" for k, v in i["files_mb"].items()) + ".\n"
    "- Choose the dataset in the sidebar. The stress book is **synthetic stress data** tuned toward the reference "
    "workbook's population; the 5k demo is the standard illustrative bank.")

Y.band("Data used, and what is synthetic")
st.dataframe(pd.DataFrame([
    ("Table4 account cycles", "Line, balances (after payment; statement balance = after payment + payment made, "
     "used for the 30% test and, with the after-payment balance, the midpoint balance for costs), paid in full, "
     "promotional / BT balance", "measured"),
    ("Table5 / Table5b", "Spend and activity; installment plan balances", "measured"),
    ("Table8 risk parameters", "PD 12 Month (annual) and LGD at the reporting date - never lifetime PD; a missing "
     "PD takes the segment average (B1)", "measured"),
    ("Table9", "Behavioral CCF: each account's LEQ under the measured_account setting (B2; the workbook LEQ is the "
     "default); a generator parameter on this synthetic data (0.42 / 0.798)", "measured"),
    ("Table29 score history", "Behaviour and bureau score by month (score-drop rule) - SYNTHETIC addition, partly "
     "correlated with PD by construction", "synthetic"),
    ("Table30 card activation", "Activation of every plastic (dormant confirmation) - SYNTHETIC addition", "synthetic"),
    ("Engine (read only)", "Card ledger (card_net), suppression, L1 / L3 / L5 worklists", "measured"),
    ("Reference workbook", "Segment rules, LEQ, lever shares, response rates", "workbook"),
], columns=["Source", "Used for", "Type"]), width="stretch", hide_index=True)

Y.band("Calibration against the reference workbook (informational; never a failure)")
cal = S.calibration()
if cal is not None:
    v = cal["Within Band"].value_counts()
    S.md(f"**{int(v.get('within', 0))}** of {int(v.get('within', 0) + v.get('outside', 0))} metrics within ±25% of "
                "the workbook's segment inputs" + (" (measured when the stress profile was tuned, on its 10,000-customer "
                "book; the 100,000-customer book uses the same profile)" if S.dataset() == "stress" else "")
                + ". Reasons for every metric outside the band: "
                "`specs/unused_line_management/STAGE4_REPORT.md`.")
    st.dataframe(cal[["Segment", "Metric", "Observed", "Reference", "Within Band", "Accounts", "Note"]],
                 width="stretch", hide_index=True)

Y.band("Your own portfolio")
S.md("Generate or export a portfolio folder in the system's table format, then build a dataset offline:\n\n"
            "```\npython -m unused_lines_app.build_sample --data <portfolio dir> --name mine --label \"My bank\"\n```\n"
            "and add it to `DATASETS` in `unused_lines_app/lib/state.py`. The full build reads every raw table "
            "(a 100k-customer portfolio peaks at about 15-22 GB); the app itself stays well under 2 GB.")
