"""Zip upload -> extracted portfolio -> full engine pipeline, cached in
Streamlit session state so navigating between pages never re-runs analysis."""
from __future__ import annotations
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

from engine.core.contract import load_portfolio, DataContractViolation  # noqa: E402
from engine.run import build_pipeline, portfolio_defect_count, MECHANISM_VARIED_IN_CONTROL  # noqa: E402
from engine.governance import negative_control as NEGCTL  # noqa: E402
from engine.core import outputs as OUT  # noqa: E402

SCRATCH = Path(tempfile.gettempdir()) / "profitinsight_app"
SCRATCH.mkdir(exist_ok=True)


def _extract_zip(uploaded_file, label: str) -> Path:
    digest = hashlib.sha256(uploaded_file.getvalue()).hexdigest()[:16]
    dest = SCRATCH / f"{label}_{digest}"
    # A directory existing is not proof extraction succeeded - a prior
    # attempt that failed partway (e.g. a bad zip) can leave an empty or
    # partial folder behind, which would otherwise be silently treated as a
    # valid cache hit. Require the expected table to actually be there.
    if dest.exists() and list(dest.rglob("Table1_Customer.csv")):
        return _find_portfolio_root(dest)
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True, exist_ok=True)
    # BytesIO uniformly handles both Streamlit's UploadedFile (already
    # file-like) and the plain-bytes _LocalFileAsUpload wrapper used for the
    # bundled sample data - zipfile itself needs a seekable object, and
    # relying on the caller's object to already be one was the bug here.
    with zipfile.ZipFile(io.BytesIO(uploaded_file.getvalue())) as zf:
        zf.extractall(dest)
    return _find_portfolio_root(dest)


def _find_portfolio_root(extracted_dir: Path) -> Path:
    """The zip may have the CSVs at its root or nested one level deep (e.g.
    zipping the 'demo' folder itself). Find wherever Table1_Customer.csv
    actually landed."""
    hits = list(extracted_dir.rglob("Table1_Customer.csv"))
    if not hits:
        raise DataContractViolation(
            "Table1_Customer.csv not found anywhere in the uploaded zip. "
            "Upload a zipped portfolio folder as produced by "
            "generator/run.py (e.g. the 'demo' or 'negative_control' folder).")
    return hits[0].parent


@st.cache_resource(show_spinner=False)
def _cached_pipeline(portfolio_root_str: str, _cache_key: str):
    portfolio_root = Path(portfolio_root_str)
    return build_pipeline(portfolio_root)


def run_pipeline_for_upload(uploaded_file, label: str) -> tuple[dict, Path]:
    root = _extract_zip(uploaded_file, label)
    result = _cached_pipeline(str(root), str(root))
    return result, root


class _LocalFileAsUpload:
    """Adapts a path already on disk to the same .getvalue()/.name interface
    Streamlit's UploadedFile exposes, so `_extract_zip` doesn't need a
    separate code path for the bundled sample zips."""

    def __init__(self, path: Path):
        self._path = path
        self.name = path.name

    def getvalue(self) -> bytes:
        return self._path.read_bytes()


def run_pipeline_for_sample(path: Path, label: str) -> tuple[dict, Path]:
    return run_pipeline_for_upload(_LocalFileAsUpload(path), label)


def run_negative_control_gate(demo_result: dict, control_result: dict) -> pd.DataFrame:
    gt_demo = 0
    gt_ctrl = 0
    gt_dir_demo = demo_result["portfolio"].root / "_ground_truth" / "Defect_Ground_Truth.csv"
    gt_dir_ctrl = control_result["portfolio"].root / "_ground_truth" / "Defect_Ground_Truth.csv"
    if gt_dir_demo.exists():
        gt_demo = portfolio_defect_count(demo_result["portfolio"].root)
    if gt_dir_ctrl.exists():
        gt_ctrl = portfolio_defect_count(control_result["portfolio"].root)

    results = [NEGCTL.check_defects(gt_demo, gt_ctrl)]
    for code, lever in demo_result["levers"].items():
        results.append(NEGCTL.check(
            lever, control_result["levers"][code], MECHANISM_VARIED_IN_CONTROL[code],
            demo_result["customer_view"], demo_result["populations"][code],
            control_result["customer_view"], control_result["populations"][code]))
    return NEGCTL.report(results)


def leakage_register(result: dict) -> pd.DataFrame:
    return OUT.leakage_register(result["worklists"], result["sizes"])


def worklist_export(result: dict) -> pd.DataFrame:
    return OUT.worklist_export(result["worklists"])


def score_file(result: dict) -> pd.DataFrame:
    latest_cycle = sorted(result["ledger"]["card"]["Cycle Month"].unique())[-1]
    return OUT.score_file(result["customer_view"], result["suppressed"].suppressed,
                          latest_cycle)


def clear_scratch():
    shutil.rmtree(SCRATCH, ignore_errors=True)
    SCRATCH.mkdir(exist_ok=True)
