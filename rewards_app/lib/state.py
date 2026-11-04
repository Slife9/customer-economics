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
EXAMPLE_UPLOAD = ROOT / "samples" / "reward_stress_portfolio.zip"
SCRATCH = Path(tempfile.gettempdir()) / "profitinsight_rewards_app"
NEEDED = ["Table25_MCC_Reference.csv", "Table26_Signup_Bonus.csv", "Table27_Bureau_Inquiries.csv"]
# Beyond the engine's data contract, the reward model reads the programme
# rules; Tables 25-26 are needed too but can be computed from a generator
# build's manifest; Table27 is optional (inquiries then show as n/a).
REWARD_REQUIRED = ["Table16_Reward_Program_Rules.csv"]
DERIVABLE, OPTIONAL_REWARD = NEEDED[:2], NEEDED[2]


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


def check_zip(data: bytes) -> dict:
    """Quick pre-check of an uploaded zip from its file list alone, before the
    slow build: which folder holds the tables and what is missing."""
    from engine.core.contract import REQUIRED
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            infos = [i for i in zf.infolist() if not i.is_dir()]
    except zipfile.BadZipFile:
        return {"ok": False, "problems": ["This is not a valid zip file."], "notes": [], "tables": 0, "mb": 0}
    names = [i.filename.replace("\\", "/") for i in infos]
    anchors = [n for n in names if n.split("/")[-1] == "Table1_Customer.csv"]
    if not anchors:
        return {"ok": False, "problems": ["Table1_Customer.csv was not found. Zip the folder that holds the table "
                                          "CSVs (Table1_Customer.csv, Table2_Card_Account.csv, …)."],
                "notes": [], "tables": 0, "mb": 0}
    prefix = anchors[0][: -len("Table1_Customer.csv")]
    present = {n[len(prefix):] for n in names if n.startswith(prefix)}
    problems, notes = [], []
    missing = [n for n in [*REQUIRED, *REWARD_REQUIRED] if n not in present]
    if missing:
        problems.append("Missing required table(s): " + ", ".join(missing))
    absent = [n for n in DERIVABLE if n not in present]
    if absent and "build_manifest.json" not in present:
        problems.append(f"Missing {', '.join(absent)}, and there is no build_manifest.json to compute "
                        f"{'it' if len(absent) == 1 else 'them'} from.")
    elif absent:
        notes.append(f"{', '.join(absent)} will be computed from build_manifest.json.")
    if OPTIONAL_REWARD not in present:
        notes.append(f"{OPTIONAL_REWARD} " + ("will be computed from build_manifest.json."
                                              if "build_manifest.json" in present
                                              else "is absent - credit inquiries will show as n/a."))
    mb = sum(i.file_size for i in infos) / 1e6
    return {"ok": not problems, "problems": problems, "notes": notes,
            "tables": sum(n.endswith(".csv") for n in present), "mb": mb}


def ensure_reward_tables(root: Path) -> list[str]:
    """Tables 25-26 are needed and Table27 is used if present. Any that are
    absent are computed when the folder is a generator build (has
    build_manifest.json); returns what was added."""
    missing = [n for n in NEEDED if not (root / n).exists()]
    if not missing:
        return []
    if not (root / "build_manifest.json").exists():
        if any(n in missing for n in DERIVABLE):
            raise ValueError(f"This portfolio has no {', '.join(n for n in missing if n in DERIVABLE)} and no "
                             f"build_manifest.json to derive them from. Generate it with the current generator.")
        return []
    from generator.reward_additions import add_reward_tables
    add_reward_tables(root)
    return missing


def save_parquet_upload(data: bytes) -> Path:
    """A prepared account file uploaded back: store it and check it reads."""
    SCRATCH.mkdir(parents=True, exist_ok=True)
    path = SCRATCH / f"upload_{hashlib.sha256(data).hexdigest()[:16]}.parquet"
    if not path.exists():
        path.write_bytes(data)
    D.load_account_frame(path)  # raises ValueError if it is not a prepared L1 rewards file
    return path


def prepared_bytes(root: str) -> bytes:
    """The loaded portfolio as a prepared account file, to download and
    upload again later without rebuilding."""
    if prebuilt(root):
        return Path(root).read_bytes()
    t, meta = account_frame(root, root)
    out = Path(root).parent / f"{Path(root).name}_prepared.parquet"
    if not out.exists():
        D.save_account_frame(t, {**meta, "data_dir": st.session_state.get("label", "upload")}, out)
    return out.read_bytes()


def prebuilt(root: str | Path) -> bool:
    """A bundled sample is a prebuilt account frame (.parquet), not a folder."""
    return str(root).endswith(".parquet")


@st.cache_resource(show_spinner=False, max_entries=2)
def account_frame(root: str, _key: str):
    return D.load_account_frame(root) if prebuilt(root) else D.account_frame(root)


def load(root: Path, label: str) -> None:
    added = [] if prebuilt(root) else ensure_reward_tables(root)
    t, meta = account_frame(str(root), f"{root}")
    use(root, label, added, meta)


def use(root: Path, label: str, added: list[str], meta: dict) -> None:
    st.session_state["root"] = str(root)
    st.session_state["label"] = label
    st.session_state["added_tables"] = added
    st.session_state["meta"] = meta


def is_sample() -> bool:
    return st.session_state.get("label") in SAMPLES


PAGES: dict = {}  # url_path -> st.Page, registered by Home.py on every run


def page_link(url_path: str, label: str, icon: str, where=st, **kw) -> None:
    """Link to another page; plain text when a page runs on its own (tests)."""
    page = PAGES.get(url_path)
    if page is not None:
        where.page_link(page, label=label, icon=icon, **kw)
    else:
        where.markdown(f"{icon} **{label}**")


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
        st.info(f"Upload a portfolio on the **Upload your data** page first. ({e})")
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


def lever_values(scn: str | None = None, t: pd.DataFrame | None = None):
    """(annual, year 1) change in card profit per lever x segment for a
    scenario; the annual values add up to run()'s total change."""
    t = frame() if t is None else t
    c = cfg()
    v = M.lever_values(t, c, A.levers_for(c, scn or scenario()))
    return v, M.year_one(v, c)


def signed(v: float) -> str:
    return ("+" if v >= 0 else "") + usd(v)


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
