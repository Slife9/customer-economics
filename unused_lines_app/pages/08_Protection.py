import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from unused_lines_app.lib import state as S, style as Y, guide as G, results as R  # noqa: E402
from engine.governance import fairness as FAIR  # noqa: E402  (read only: the system's four-fifths threshold)

S.header("🛡️ Protecting customers and risks")
cfg = S.cfg()
f = S.frame()
stv = S.stress("base")
fa = S.fairness()
fs = fa["summary"]["module_decreases_and_closures"]
tr = S.treatment()
st_ = S.run("base")["strategies"]

# 1. headline sentence
Y.headline("Every action carries a recorded reason, cuts are gradual and reversible on request, protected customers "
           "are never touched, and a fair-lending review comes before any customer is contacted"
           + (f": cuts and closures {R.fairness_text(fa)}." if fs["groups_failing"] else "."))

# 2. status tiles
Y.tiles([R.fairness_tile(fa), R.robustness_tile(stv), R.rules_tile()])
st.write("")

# 3. customer safeguards
Y.band("Customer safeguards")
sg = G.safeguards(cfg)
c1, c2 = st.columns(2)
S.md("\n".join(f"- **{a}:** {b}" for a, b in sg[:4]), where=c1)
S.md("\n".join(f"- **{a}:** {b}" for a, b in sg[4:]), where=c2)

# 4. one chart: fairness by area
d = fa["module_decreases_and_closures"]
tested = d[d["status"] != "insufficient sample"].sort_values("ratio_to_population")
t = tested.head(15)
fig = go.Figure(go.Bar(
    y=[f"{g} ({s})" for g, s in zip(t["group"], t["status"])], x=t["ratio_to_population"], orientation="h",
    marker=dict(color=[Y.RED if s == "fail" else Y.GREEN for s in t["status"]], line=dict(color="#ffffff", width=1.5)),
    text=[f"{v:.2f}" for v in t["ratio_to_population"]], textposition="outside",
    customdata=t[["selected", "n"]],
    hovertemplate="%{y}: %{x:.2f} of the comparison rate<br>%{customdata[0]:,} of %{customdata[1]:,} cards"
                  "<extra></extra>"))
fig.add_vline(x=FAIR.FOUR_FIFTHS_THRESHOLD, line_dash="dot", line_color=Y.RED, annotation_text="four-fifths line",
              annotation_position="top")
fig.update_layout(title=f"Fairness: the {len(t)} areas with the lowest selection rate for cuts and closures "
                        f"({fs['groups_failing']} of {fs['groups_tested']} tested areas fail)",
                  height=130 + 30 * len(t), margin=dict(t=60, b=10, l=10),
                  xaxis=dict(title="Selection rate relative to the comparison rate",
                             range=[0, max(1.1, float(t["ratio_to_population"].max()) * 1.12)]),
                  yaxis=dict(autorange="reversed", title=""), showlegend=False, bargap=0.3)
st.plotly_chart(fig, width="stretch")
S.cap(f"{fa['proxy_method']}. Areas with fewer than {fa['min_selected_per_group']} cards selected are too small to "
      "test. The system's test flags an area selected less often than the comparison rate; for cuts and closures the "
      "usual concern is an area selected more often, so the fair-lending review should decide the method. A test by "
      "geography alone is a warning sign, not proof. Only the module's own cuts and closures are tested.")

# details
with st.expander("Rules that apply"):
    st.dataframe(pd.DataFrame(G.RULES, columns=["Action", "Requirement", "Reference"]), width="stretch",
                 hide_index=True)
    S.cap(G.COMPLIANCE_NOTE)
with st.expander("The main risks and how we manage them"):
    s2 = st_["strategies"]["re_engage"]["headline_value"]
    st.dataframe(pd.DataFrame(G.risks(R.fairness_text(fa), R.signed_short(s2)),
                              columns=["Risk", "Why it matters", "How it is managed"]), width="stretch", hide_index=True)
with st.expander("Pending corrections that may move the figures"):
    fixed = float(f.loc[f["screened"], "fixed_cost_engine"].mean()) if f["screened"].any() else 0.0
    st.dataframe(pd.DataFrame(G.pending_corrections(cfg, fixed), columns=["Correction", "In the system", "What may still change"]),
                 width="stretch", hide_index=True)
with st.expander("Notices by reason"):
    nt = R.notices(tr, cfg)
    st.dataframe(pd.DataFrame({"Reason": nt["code"].map(G.REASON_PLAIN), "Actions": nt["actions"].map(lambda v: f"{v:,}"),
                               "Adverse-action notice": nt["adverse_action_notice"].map({True: "required",
                                                                                         False: "not required"})}),
                 width="stretch", hide_index=True)
    S.cap(f"{cfg['treatment']['fee_restriction_text']}. Never an inactivity fee; the 90-day warning is never a fee.")
with st.expander("Fairness by area, every area"):
    st.dataframe(pd.DataFrame({"Area": d["group"], "Cards": d["n"].map(lambda v: f"{v:,}"),
                               "Selected": d["selected"].map(lambda v: f"{v:,}"), "Result": d["status"]}),
                 width="stretch", hide_index=True)
if S.analyst():
    with st.expander("Analyst: notice rules by reason code, fairness detail"):
        st.dataframe(nt, width="stretch", hide_index=True)
        st.dataframe(d, width="stretch", hide_index=True)
S.caveat()
