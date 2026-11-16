"""Shared state for the Unused Credit Line Management app: the dataset in use
(precomputed samples only - the app never runs the full build), the
assumptions (config defaults, editable in this session only), the cached
results, and formatting helpers.

Adapted from rewards_app/lib/state.py on feature/l1-rewards-system (495b0ec):
the page-link registry, the session-config pattern and the formatters are
copied; loading reads this module's samples. Not merged; self-contained.
"""
from __future__ import annotations
import copy
import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.unused_lines import assumptions as A, data as D, segments as SG  # noqa: E402
from engine.unused_lines import levers as L, treatment as T, exposure as X  # noqa: E402

SAMPLE_DIR = ROOT / "samples" / "unused_lines"
DATASETS = {"stress": SAMPLE_DIR / "stress", "demo": SAMPLE_DIR / "demo"}
DEFAULT_DATASET = "stress"
LABEL = ("Assumes the March 2026 Basel III endgame proposal is adopted as proposed; LCR outflow applied "
         "conservatively to all unused card lines. Capital ratio, cost of equity and carry are illustrative.")
PAGES: dict = {}  # url_path -> st.Page, registered by Home.py on every run


# ------------------------------------------------------------------ data
@st.cache_data(show_spinner=False, max_entries=4)
def _load(name: str):
    d = DATASETS[name]
    acc, meta = D.load_account_frame(d / "accounts.parquet")
    info = json.loads((d / "meta.json").read_text())
    ev = pd.read_parquet(d / "engine_view.parquet")
    return acc, meta, info, ev


@st.cache_data(show_spinner=False, max_entries=2)
def monthly(name: str) -> pd.DataFrame:
    return pd.read_parquet(DATASETS[name] / "monthly.parquet")


def dataset() -> str:
    return st.session_state.get("dataset", DEFAULT_DATASET)


def data():
    """(account frame, meta, dataset info, engine view) of the dataset in use."""
    return _load(dataset())


def info() -> dict:
    return data()[2]


# ------------------------------------------------------------- assumptions
def cfg() -> dict:
    if "cfg" not in st.session_state:
        st.session_state["cfg"], st.session_state["cfg_sha"] = A.load()
        st.session_state["cfg_default"] = copy.deepcopy(st.session_state["cfg"])
    return st.session_state["cfg"]


def cfg_edited() -> bool:
    cfg()
    return st.session_state["cfg"] != st.session_state["cfg_default"]


def set_cfg(new: dict) -> None:
    A.validate(new)
    st.session_state["cfg"] = new


def reset_cfg() -> None:
    st.session_state["cfg"] = copy.deepcopy(st.session_state["cfg_default"])


def scenario() -> str:
    return st.session_state.get("scenario", "base")


def _key(*parts) -> str:
    return json.dumps([dataset(), cfg()] + list(parts), sort_keys=True, default=str)


# ----------------------------------------------------------------- results
def frame() -> pd.DataFrame:
    """The segmented, costed account frame (recomputed only when the dataset
    or the assumptions change). Treat as read-only."""
    k = _key("frame")
    if st.session_state.get("_frame_key") != k:
        acc, meta, _, ev = data()
        acc = acc.copy()
        prot = ev.set_index("Masked Customer Number")
        acc["protected"] = acc["customer"].map(prot["protected"]).fillna(False).astype(bool)
        acc["suppression_reason"] = acc["customer"].map(prot["suppression_reason"]).fillna("")
        st.session_state["_frame"] = SG.build(acc, meta, cfg())
        st.session_state["_frame_key"] = k
    return st.session_state["_frame"]


def run(scn: str | None = None, multiplier: float = 1.0) -> dict:
    k = _key("run", scn or scenario(), multiplier)
    cache = st.session_state.setdefault("_runs", {})
    if k not in cache:
        if len(cache) > 6:
            cache.clear()
        f = frame()
        res = L.run(f, cfg(), scn or scenario(), multiplier)
        cache[k] = {"res": res, "summary": L.summary(res, cfg(), f), "levers": L.lever_table(res, cfg(), f),
                    "segments": L.segment_table(res, cfg(), f)}
    return cache[k]


def worklists() -> dict:
    ev = data()[3]
    return {code: ev.loc[ev[f"in_{code}"], ["Masked Customer Number"]] for code in ["L1", "L3", "L5"]
            if f"in_{code}" in ev}


def treatment() -> pd.DataFrame:
    k = _key("treatment")
    if st.session_state.get("_treat_key") != k:
        f = frame()
        res = run(cfg()["treatment"]["scenario_for_recommendations"])["res"]
        ev = data()[3]
        st.session_state["_treat"] = T.design(f, cfg(), res, ev, worklists())
        st.session_state["_treat_key"] = k
    return st.session_state["_treat"]


def fairness() -> dict:
    k = _key("fairness")
    if st.session_state.get("_fair_key") != k:
        ev = data()[3]
        acc = data()[0]
        cv = ev.merge(acc[["customer", "metro"]].drop_duplicates("customer").rename(
            columns={"customer": "Masked Customer Number", "metro": "Metro Name"}), on="Masked Customer Number", how="left")
        st.session_state["_fair"] = T.fairness(frame(), treatment(), cv)
        st.session_state["_fair_key"] = k
    return st.session_state["_fair"]


# ------------------------------------------------------------------ page bits
def page_link(url_path: str, label: str, icon: str, where=st, **kw) -> None:
    """Link to another page; plain text when a page runs on its own (tests)."""
    page = PAGES.get(url_path)
    if page is not None:
        where.page_link(page, label=label, icon=icon, **kw)
    else:
        where.markdown(f"{icon} **{label}**")


def header(title: str) -> None:
    """Page title, and a warning when assumptions are edited in this
    session. The dataset name and the assumption label sit in the sidebar
    (Home.py); the value-type key is on the Lever guide page."""
    st.title(title)
    if cfg_edited():
        st.warning("Assumptions edited in this session (exploration only) - figures differ from the agreed "
                   "defaults. Reset on **Levers & assumptions**.")


def caveat() -> None:
    st.caption("Every post-change figure is an expected value under illustrative assumptions - customer "
               "responses have not been measured on this portfolio. The recommended next step is always a "
               "pilot with a holdout.")


def seg_label(key: str) -> str:
    return cfg()["segments"]["labels"].get(key, key)


usd = lambda v: "" if pd.isna(v) else (f"-${-v:,.0f}" if v < 0 else f"${v:,.0f}")  # noqa: E731
pct = lambda v: "" if pd.isna(v) else f"{v:.1%}"  # noqa: E731


def signed(v: float) -> str:
    return ("+" if v >= 0 else "") + usd(v)
