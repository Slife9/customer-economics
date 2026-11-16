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
# Memory: every cache below is st.cache_resource - one copy per server
# process, shared by all sessions, never copied on access - and holds either
# the dataset itself or small result tables. A 100k-customer frame is about
# 0.2 GB; keeping one per session (or full per-lever tables per run) is what
# exhausted the hosted instance. Treat every returned object as read-only.
@st.cache_resource(show_spinner=False, max_entries=2)
def _load(name: str):
    d = DATASETS[name]
    acc, meta = D.load_account_frame(d / "accounts.parquet")
    info = json.loads((d / "meta.json").read_text())
    ev = pd.read_parquet(d / "engine_view.parquet")
    return acc, meta, info, ev


def monthly_for(name: str, account: str) -> pd.DataFrame:
    """The 12 cycles of one account, read straight from the file (no copy of
    the whole table in memory)."""
    import pyarrow.parquet as pq
    t = pq.read_table(DATASETS[name] / "monthly.parquet", filters=[("Masked Account Number", "=", account)])
    return t.to_pandas()


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


def _cfg_json() -> str:
    return json.dumps(cfg(), sort_keys=True)


# ----------------------------------------------------------------- results
@st.cache_resource(show_spinner="Segmenting the accounts…", max_entries=3)
def _frame(name: str, cfg_json: str) -> pd.DataFrame:
    acc, meta, _, ev = _load(name)
    acc = acc.copy()
    prot = ev.set_index("Masked Customer Number")
    acc["protected"] = acc["customer"].map(prot["protected"]).fillna(False).astype(bool)
    acc["suppression_reason"] = acc["customer"].map(prot["suppression_reason"]).fillna("")
    return SG.build(acc, meta, json.loads(cfg_json))


def frame() -> pd.DataFrame:
    """The segmented, costed account frame (shared; recomputed only when the
    dataset or the assumptions change). Read-only."""
    return _frame(dataset(), _cfg_json())


@st.cache_resource(show_spinner="Valuing the levers…", max_entries=10)
def _run(name: str, cfg_json: str, scn: str, multiplier: float) -> dict:
    c = json.loads(cfg_json)
    f = _frame(name, cfg_json)
    res = L.run(f, c, scn, multiplier)
    out = {"summary": L.summary(res, c, f), "levers": L.lever_table(res, c, f),
           "segments": L.segment_table(res, c, f)}
    # Only what the treatment designer needs is kept from the per-account run.
    out["res"] = {"scope": res["scope"],
                  "selection": res["selection"][["decrease", "campaign", "closure", "cut", "new_line"]],
                  "per_lever": {k: res["per_lever"][k][["eligible"]] for k in L.EXTRA_LEVERS}}
    return out


def run(scn: str | None = None, multiplier: float = 1.0) -> dict:
    return _run(dataset(), _cfg_json(), scn or scenario(), float(multiplier))


@st.cache_resource(show_spinner="Running the stress test…", max_entries=3)
def _stress(name: str, cfg_json: str, scn: str) -> pd.DataFrame:
    return L.stress(_frame(name, cfg_json), json.loads(cfg_json), scn)


def stress(scn: str = "base") -> pd.DataFrame:
    return _stress(dataset(), _cfg_json(), scn)


def worklists() -> dict:
    ev = data()[3]
    return {code: ev.loc[ev[f"in_{code}"], ["Masked Customer Number"]] for code in ["L1", "L3", "L5"]
            if f"in_{code}" in ev}


@st.cache_resource(show_spinner="Designing the treatments…", max_entries=3)
def _treatment(name: str, cfg_json: str) -> pd.DataFrame:
    c = json.loads(cfg_json)
    f = _frame(name, cfg_json)
    res = _run(name, cfg_json, c["treatment"]["scenario_for_recommendations"], 1.0)["res"]
    ev = _load(name)[3]
    wl = {code: ev.loc[ev[f"in_{code}"], ["Masked Customer Number"]] for code in ["L1", "L3", "L5"]
          if f"in_{code}" in ev}
    return T.design(f, c, res, ev, wl)


def treatment() -> pd.DataFrame:
    return _treatment(dataset(), _cfg_json())


@st.cache_resource(show_spinner="Running the fairness test…", max_entries=3)
def _fairness(name: str, cfg_json: str) -> dict:
    acc, _, _, ev = _load(name)
    cv = ev.merge(acc[["customer", "metro"]].drop_duplicates("customer").rename(
        columns={"customer": "Masked Customer Number", "metro": "Metro Name"}), on="Masked Customer Number", how="left")
    return T.fairness(_frame(name, cfg_json), _treatment(name, cfg_json), cv)


def fairness() -> dict:
    return _fairness(dataset(), _cfg_json())


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
