"""A reference page, independent of whatever portfolio is loaded: what each
lever is, why it's built the way it is, and a genuinely actionable
implementation playbook for taking it from finding to production. The
Levers & Strategy page shows this quarter's live numbers; this page is the
operating manual underneath them.
"""
from __future__ import annotations
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.lib.lever_playbook_content import CORE_CONCEPTS, LEVERS, SEQUENCE_ORDER


def esc(text: str) -> str:
    """Escape a literal '$' before handing free text to st.markdown/st.info -
    otherwise Streamlit's markdown renderer treats a pair of '$' anywhere in
    the same string as LaTeX math delimiters and silently mangles every
    dollar figure between them."""
    return text.replace("$", "\\$")


st.set_page_config(page_title="Lever Playbook", page_icon="📖", layout="wide")
st.title("📖 Lever Playbook")
st.caption("A practical implementation manual for each lever - who it's for, "
          "what to do, in what order, who signs off, how to test it, how to "
          "measure it, and when to expand, revise, or stop it. This page "
          "doesn't depend on any uploaded data - it's the reference, not the "
          "report. For this quarter's live numbers, see **Levers & Strategy**.")

LEVERS_BY_CODE = {lv["code"]: lv for lv in LEVERS}

st.divider()
st.header("Quick navigation")
nav_md = "  ·  ".join(
    f"[{LEVERS_BY_CODE[code]['icon']} {code}](#lever-{code.lower()})"
    for code in SEQUENCE_ORDER)
st.markdown(f"Jump to a lever: {nav_md}")

st.divider()
st.header("Core concepts, before the six levers")
for i, c in enumerate(CORE_CONCEPTS):
    with st.expander(c["title"], expanded=(i == 0)):
        st.markdown(c["body"])

st.divider()
st.header("The six levers - implementation playbooks")
st.caption("Levers are ordered by how fast they can go into production, not "
          "by number - see 'What do Fast, Slow, and Pilot required mean?' above.")

for code in SEQUENCE_ORDER:
    lv = LEVERS_BY_CODE[code]
    st.markdown(f'<a name="lever-{code.lower()}"></a>', unsafe_allow_html=True)
    st.subheader(f"{lv['icon']} {lv['code']} — {lv['name']}")
    badge1, badge2 = st.columns(2)
    badge1.metric("Speed to deploy", lv["speed"])
    badge2.metric("Compliance gate", lv["gate"])

    tab_over, tab_exec, tab_gov, tab_meas, tab_tech = st.tabs([
        "1 · Problem & Fit", "2 · Execution", "3 · Governance & Testing",
        "4 · Measurement & Risk", "5 · Technical Reference",
    ])

    with tab_over:
        st.markdown(f"**What problem are we solving?**  \n{esc(lv['problem'])}")
        st.markdown(f"**Why does it matter?**  \n{esc(lv['why_it_matters'])}")
        st.markdown(f"**Which customers are suitable?**  \n{esc(lv['population'])}")
        st.info(f"**Worked example** (illustrative, not live data): "
               f"{esc(lv['worked_example'])}")

    with tab_exec:
        st.markdown("**What data do we need?**")
        for d in lv["data_needed"]:
            st.markdown(f"- {esc(d)}")
        st.markdown("**What exactly should the bank do?**")
        for a in lv["actions"]:
            st.markdown(f"- {esc(a)}")
        st.markdown("**In what order should the actions be performed?**")
        for i, step in enumerate(lv["sequence"], 1):
            st.markdown(f"{i}. {esc(step)}")
        st.markdown("**Implementation checklist**")
        for i, item in enumerate(lv["checklist"]):
            st.checkbox(esc(item), key=f"checklist_{code}_{i}")

    with tab_gov:
        st.markdown("**Which teams are responsible?**")
        st.table({"Team": [t for t, _ in lv["teams"]],
                 "Role in this lever": [r for _, r in lv["teams"]]})
        st.markdown(f"**What approvals and safeguards are required?**  \n{esc(lv['approvals'])}")
        st.markdown(f"**How should the intervention be tested?**  \n{esc(lv['testing'])}")

    with tab_meas:
        st.markdown("**How do we measure whether it worked?**")
        st.table({"KPI": [k for k, _, _ in lv["kpis"]],
                 "Definition": [d for _, d, _ in lv["kpis"]],
                 "Cadence": [c for _, _, c in lv["kpis"]]})
        st.markdown("**What could go wrong?**")
        for r in lv["risks"]:
            st.markdown(f"- {esc(r)}")
        st.markdown(f"**When should this expand, be revised, or stop?**  \n{esc(lv['evolution'])}")

    with tab_tech:
        st.markdown(f"**Engine module:** `{lv['module']}`")
        if lv["constants"]:
            st.markdown("**Governing constants** (the exact thresholds the "
                        "code above uses - change the engine, and this table "
                        "changes with it):")
            st.code("\n".join(f"{k} = {v}" for k, v in lv["constants"].items()),
                   language="python")
        else:
            st.caption("This lever has no tunable numeric thresholds - its "
                      "logic is a ranking/comparison, not a cutoff.")

st.divider()
st.caption("For this quarter's actual numbers against these definitions, see "
          "**Levers & Strategy**. This page is the reference and the "
          "implementation manual; that page is the report.")
