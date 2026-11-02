import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from rewards_app.lib import state as S, style as Y  # noqa: E402
from engine.core.contract import REQUIRED  # noqa: E402

st.title("📤 Upload your data")
st.caption("Upload a portfolio and the whole app - Overview, Scenario dashboard, Segments, Customer drill-down and "
           "Downloads - runs the L1 rewards analysis on it. The data stays on the machine running this app.")


@st.cache_resource(show_spinner=False)
def example_bytes() -> bytes:
    return S.EXAMPLE_UPLOAD.read_bytes() if S.EXAMPLE_UPLOAD.exists() else b""


# ---------------------------------------------------- data in use
S.require()
if S.loaded():
    meta = st.session_state["meta"]
    who = f"{meta['customers']:,} customers, " if meta.get("customers") else ""
    c1, c2 = st.columns([4, 1])
    c1.info(f"**Now analysing:** {st.session_state['label']} - {who}{meta['accounts']:,} card accounts, "
            f"{meta['first']} to {meta['last']}.")
    if not S.is_sample() and c2.button("Back to the bundled sample", width="stretch"):
        S.load_sample(S.DEFAULT_SAMPLE)
        st.session_state.pop("upload_done", None)
        st.rerun()

left, right = st.columns([3, 2], gap="large")

# ---------------------------------------------------- upload and run
with left:
    st.subheader("1. Choose a file")
    up = st.file_uploader("A zipped portfolio (the table CSVs), or a prepared .parquet file downloaded from this page",
                          type=["zip", "parquet"])
    if up is not None:
        data = up.getvalue()
        if up.name.lower().endswith(".zip"):
            chk = S.check_zip(data)
            st.subheader("2. Check")
            if chk["ok"]:
                st.success(f"**{up.name}** looks complete - {chk['tables']} tables, {chk['mb']:,.0f} MB unpacked.")
            for p in chk["problems"]:
                st.error(p)
            for n in chk["notes"]:
                st.caption("ℹ️ " + n)
        else:
            chk = {"ok": True, "mb": len(data) / 1e6}
            st.subheader("2. Check")
            st.success(f"**{up.name}** - a prepared account file ({chk['mb']:,.1f} MB); it loads in seconds.")

        st.subheader("3. Run the analysis")
        if chk["mb"] > 1000:
            st.caption(f"About {chk['mb'] / 1000:,.1f} GB of tables - building the account P&L will take several "
                       f"minutes.")
        if st.button("▶ Run the analysis on this data", type="primary", disabled=not chk["ok"], width="stretch"):
            st.session_state.pop("upload_done", None)
            with st.status("Running the L1 rewards analysis…", expanded=True) as status:
                try:
                    if up.name.lower().endswith(".parquet"):
                        st.write("Reading the prepared account file…")
                        root, added = S.save_parquet_upload(data), []
                    else:
                        st.write("1/4 Unpacking the tables…")
                        root = S.extract_zip(data, "upload")
                        st.write("2/4 Checking the reward tables…")
                        added = S.ensure_reward_tables(root)
                        st.write("3/4 Checking the data contract and building each account's 12-month P&L…")
                    _, meta = S.account_frame(str(root), str(root))
                    st.write("4/4 Screening, segmenting and valuing the reward levers…")
                    S.use(root, up.name, added, meta)
                    S.run("base")
                    st.session_state["upload_done"] = up.name
                    status.update(label="Analysis complete", state="complete", expanded=False)
                except Exception as e:  # contract violations and bad files, shown plainly
                    status.update(label="The analysis could not run on this file", state="error")
                    st.error(f"{type(e).__name__}: {e}")
            if st.session_state.get("upload_done") == up.name:
                st.rerun()  # every page, and the sidebar, now show the uploaded data

# ---------------------------------------------------- what to upload
with right:
    st.subheader("What to upload")
    st.markdown(
        "**A zip of the portfolio's table CSVs**, all in one folder, in the generator's format "
        "(the same as the six-lever app). The analysis needs:\n"
        f"- the engine's data contract: {len(REQUIRED)} tables, from `Table1_Customer.csv` to "
        "`Table19_Reward_Expiry.csv`;\n"
        "- `Table16_Reward_Program_Rules.csv`;\n"
        "- `Table25_MCC_Reference.csv` and `Table26_Signup_Bonus.csv`, or the generator's "
        "`build_manifest.json` to compute them from;\n"
        "- optionally `Table27_Bureau_Inquiries.csv`, plus deposit and loan tables for relationship value.\n\n"
        "**Or a prepared `.parquet` file** saved from this page after an earlier run - it skips the "
        "rebuild and loads in seconds.")
    with st.expander("All required tables"):
        st.markdown("\n".join(f"- `{n}`" for n in [*REQUIRED, *S.REWARD_REQUIRED, *S.DERIVABLE]))
    st.caption(f"Upload limit: {st.get_option('server.maxUploadSize'):,} MB.")
    ex = example_bytes()
    if ex:
        st.download_button("Download an example upload (5,000 customers)", ex, S.EXAMPLE_UPLOAD.name,
                           "application/zip", width="stretch")

# ---------------------------------------------------- result
if st.session_state.get("upload_done") and S.loaded() and st.session_state["label"] == st.session_state["upload_done"]:
    st.divider()
    st.subheader(f"Results for {st.session_state['label']}")
    t, post, sm = S.run("base")
    x, s = sm.loc["total"], t[t["screened"]]
    meta = st.session_state["meta"]
    if st.session_state.get("added_tables"):
        st.caption("Computed from build_manifest.json: " + ", ".join(st.session_state["added_tables"]))
    Y.cards([
        ("Card accounts analysed", f"{len(t):,}", f"{meta['first']} to {meta['last']}", Y.GREY),
        ("Unprofitable reward accounts", f"{len(s):,}", f"{len(s) / len(t):.1%} of card accounts" if len(t) else "",
         Y.AMBER),
        ("Their annual card loss", S.usd(s["fully_loaded_profit"].sum()), "trailing 12 months, measured", Y.RED),
        ("Base scenario: profit improvement", ("+" if x.change_fully_loaded_profit >= 0 else "")
         + S.usd(x.change_fully_loaded_profit), f"{x.accounts_lost:,.0f} accounts expected to leave", Y.GREEN),
    ])
    st.write("")
    b1, b2 = st.columns(2)
    S.page_link("overview", "See the full results on the Overview", "🏠", where=b1, width="stretch")
    with b2:
        st.download_button("Save the prepared data (.parquet) to reload instantly next time",
                           S.prepared_bytes(st.session_state["root"]),
                           f"{Path(st.session_state['label']).stem}_l1_rewards_prepared.parquet",
                           "application/octet-stream", width="stretch")
