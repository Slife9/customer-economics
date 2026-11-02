"""Shared state for the L1 rewards app: the loaded portfolio, the account
frame (cached), the assumptions being used (Excel defaults, editable in this
session), and formatting helpers."""
from __future__ import annotations
import copy
import hashlib
import io
import json
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
    "Reward stress book (100,000 customers) - built for this system":
        ROOT / "samples" / "reward_stress_100k_accounts.parquet",
}
DEFAULT_SAMPLE = next(iter(SAMPLES))
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


def prebuilt(root: str | Path) -> bool:
    """A bundled sample is a prebuilt account frame (.parquet), not a folder."""
    return str(root).endswith(".parquet")


@st.cache_resource(show_spinner=False, max_entries=2)
def account_frame(root: str, _key: str):
    return D.load_account_frame(root) if prebuilt(root) else D.account_frame(root)


def load(root: Path, label: str) -> None:
    added = [] if prebuilt(root) else ensure_reward_tables(root)
    t, meta = account_frame(str(root), f"{root}")
    st.session_state["root"] = str(root)
    st.session_state["label"] = label
    st.session_state["added_tables"] = added
    st.session_state["meta"] = meta


def load_sample(label: str) -> None:
    path = SAMPLES[label]
    if not path.exists():
        raise FileNotFoundError(f"{path.name} is not in samples/ - build it with `python -m rewards_app.build_sample`.")
    load(path, label)


def loaded() -> bool:
    return "root" in st.session_state


def require() -> None:
    """Every results page works straight away: the bundled sample is loaded
    the first time a page needs data."""
    if loaded():
        return
    try:
        with st.spinner("Loading the bundled 100,000-customer sample…"):
            load_sample(DEFAULT_SAMPLE)
    except FileNotFoundError as e:
        st.info(f"Load a portfolio on the **Load portfolio** page first. ({e})")
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
    """The segmented account frame, re-segmented only when the portfolio or
    the thresholds change (segmenting 100k+ accounts takes seconds). Treat
    as read-only."""
    key = (st.session_state["root"], json.dumps(cfg()["thresholds"], sort_keys=True))
    if st.session_state.get("_frame_key") != key:
        t, _ = account_frame(st.session_state["root"], st.session_state["root"])
        st.session_state["_frame"] = SG.assign(t, cfg())
        st.session_state["_frame_key"] = key
    return st.session_state["_frame"]


def run(scn: str | None = None, multiplier: float | None = None, t: pd.DataFrame | None = None):
    t = frame() if t is None else t
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
