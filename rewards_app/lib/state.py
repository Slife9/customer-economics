"""Shared state for the L1 rewards app: the loaded portfolio, the account
frame (cached), the assumptions being used (Excel defaults, editable in this
session), and formatting helpers."""
from __future__ import annotations
import copy
import hashlib
import io
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.rewards import assumptions as A, data as D, segments as SG, model as M  # noqa: E402

SAMPLES = {
    "Reward stress book (5,000 customers) - built for this system": ROOT / "samples" / "reward_stress_portfolio.zip",
    "Standard demo book (5,000 customers)": ROOT / "samples" / "demo_portfolio.zip",
}
SCRATCH = Path(tempfile.gettempdir()) / "profitinsight_rewards_app"
NEEDED = ["Table25_MCC_Reference.csv", "Table26_Signup_Bonus.csv", "Table27_Bureau_Inquiries.csv"]


# ------------------------------------------------------------------ loading
def extract_zip(data: bytes, label: str) -> Path:
    digest = hashlib.sha256(data).hexdigest()[:16]
    dest = SCRATCH / f"{label}_{digest}"
    if not list(dest.rglob("Table1_Customer.csv")):
        shutil.rmtree(dest, ignore_errors=True)
        dest.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for info in zf.infolist():
                name = info.filename.replace("\\", "/")
                if name.startswith("/") or ".." in name.split("/"):
                    raise ValueError(f"unsafe path in zip: {info.filename}")
                if info.is_dir():
                    continue
                target = dest / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zf.read(info))
    hits = list(dest.rglob("Table1_Customer.csv"))
    if not hits:
        raise ValueError("Table1_Customer.csv not found in the zip - upload a zipped portfolio folder.")
    return hits[0].parent


def ensure_reward_tables(root: Path) -> list[str]:
    """Tables 25-27 are needed. If absent but the folder is a generator
    build (has build_manifest.json), compute them; returns what was added."""
    missing = [n for n in NEEDED if not (root / n).exists()]
    if not missing:
        return []
    if not (root / "build_manifest.json").exists():
        raise ValueError(f"This portfolio has no {', '.join(missing)} and no build_manifest.json to "
                         f"derive them from. Generate it with the current generator.")
    from generator.reward_additions import add_reward_tables
    add_reward_tables(root)
    return missing


@st.cache_resource(show_spinner=False, max_entries=2)
def account_frame(root: str, _key: str):
    return D.account_frame(root)


def load(root: Path, label: str) -> None:
    added = ensure_reward_tables(root)
    t, meta = account_frame(str(root), f"{root}")
    st.session_state["root"] = str(root)
    st.session_state["label"] = label
    st.session_state["added_tables"] = added
    st.session_state["meta"] = meta


def loaded() -> bool:
    return "root" in st.session_state


def require() -> None:
    if not loaded():
        st.info("Load a portfolio on the **Load portfolio** page first.")
        st.stop()


# ------------------------------------------------------------- assumptions
def cfg() -> dict:
    if "cfg" not in st.session_state:
        st.session_state["cfg"], st.session_state["cfg_sha"] = A.load()
        st.session_state["cfg_default"] = copy.deepcopy(st.session_state["cfg"])
    return st.session_state["cfg"]


def cfg_edited() -> bool:
    cfg()
    return st.session_state["cfg"] != st.session_state["cfg_default"]


def reset_cfg() -> None:
    st.session_state["cfg"] = copy.deepcopy(st.session_state["cfg_default"])


def scenario() -> str:
    return st.session_state.get("scenario", "base")


# ----------------------------------------------------------------- results
def frame() -> pd.DataFrame:
    t, _ = account_frame(st.session_state["root"], st.session_state["root"])
    return SG.assign(t, cfg())


def run(scn: str | None = None, multiplier: float | None = None):
    t = frame()
    c = cfg()
    post = M.apply(t, c, A.levers_for(c, scn or scenario()), multiplier)
    return t, post, M.summary(t, post)


def seg_label(key: str) -> str:
    return cfg()["segment_labels"].get(key, key)


def edited_badge() -> None:
    if cfg_edited():
        st.warning("Assumptions edited in this session - figures differ from the workbook defaults. "
                   "Reset on **Levers & assumptions**.")


def caveat() -> None:
    st.caption("Every post-change figure is an expected value under illustrative assumptions from the "
               "Reward Profitability Scenario Model v2 - customer responses have not been measured on "
               "this portfolio. Pilot (champion / challenger) before acting.")


usd = lambda v: "" if pd.isna(v) else (f"-${-v:,.0f}" if v < 0 else f"${v:,.0f}")
pct = lambda v: "" if pd.isna(v) else f"{v:.1%}"
