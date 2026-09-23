"""Data contract. Validate the input, refuse to run on unvalidated data.

INVARIANT (concept spec 5.1): ground truth must be structurally unreachable.
Any column containing latent/defect/planted/appetite/propensity/fluency/
persona raises on load. If those reach the engine every detection result is
circular and nobody can tell.

INVARIANT: a missing required table or column raises. This module never
warns and continues - a silent column rename upstream is how an analytics
platform starts producing confident wrong answers.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import pandas as pd

GROUND_TRUTH_MARKERS = ("latent", "defect", "planted", "appetite",
                        "propensity", "fluency", "persona")


class DataContractViolation(Exception):
    """Raised on any contract breach. Never caught silently by this module."""


REQUIRED = {
    "Table1_Customer.csv": [
        "Masked Customer Number", "Segment", "Age", "Stated Annual Income",
        "Credit Score", "Credit Score Band", "Customer Tenure Years", "State",
        "Hardship Status", "Accommodation Plan", "SCRA Flag",
    ],
    "Table2_Card_Account.csv": [
        "Masked Customer Number", "Masked Account Number", "Product Tier",
        "Reward Program Code", "Original Credit Limit", "Current Credit Limit",
        "Contractual Purchase APR", "Annual Fee", "Acquisition Channel",
    ],
    "Table4_Account_Cycle.csv": [
        "Masked Customer Number", "Masked Account Number", "Cycle Month",
        "Cycle Index", "Credit Limit", "Ending Balance", "Purchase Balance",
        "Utilization", "Purchases Authorized",
        "Purchase Interest", "Cash Advance Interest", "Promotional Interest",
        "Contractual Purchase APR", "Charged Purchase APR", "Days Past Due",
        "Delinquency Bucket", "Annual Fee Charged", "Late Fee Charged",
        "Account Type", "Hardship Status", "Accommodation Plan", "SCRA Flag",
        "Charged Off Indicator",
    ],
    "Table5_Transaction.csv": [
        "Masked Account Number", "Cycle Month", "Transaction Amount",
        "Merchant Category Code (MCC)", "Interchange Earned",
    ],
    "Table8_Risk_Parameters.csv": [
        "Masked Account Number", "Cycle Month", "PD 12 Month", "PD Lifetime",
        "LGD", "EAD", "Lifetime Expected Credit Loss",
        "Expected Credit Loss 12 Month", "Monthly Provision",
    ],
    "Table9_Capital_RWA.csv": [
        "Masked Account Number", "Cycle Month", "Regulatory Capital Charge Monthly",
        "Economic Capital Charge Monthly", "Regulatory CCF", "Behavioral CCF",
    ],
    "Table11_Cost_Pools.csv": [
        "Activity", "Allocation Tier", "Volume Band From", "Volume Band To",
        "Band Fixed Cost USD Monthly", "Marginal Unit Cost USD",
    ],
    "Table12_Cost_Drivers.csv": [
        "Masked Account Number", "Cycle Month", "Contact Center Calls",
        "Primary Call Reason", "Digital Sessions", "Collections Contacts",
        "Cards Issued", "Paper Statements Produced", "Electronic Statements Produced",
    ],
    "Table17_Reward_Redemption.csv": [
        "Masked Account Number", "Cycle Month", "Points Redeemed",
        "Redemption Channel", "Redemption Cost USD",
    ],
    "Table19_Reward_Expiry.csv": [
        "Masked Account Number", "Cycle Month", "Points Expired",
        "Points Earned Cycle Month",
    ],
}

OPTIONAL = {
    "Table5_Transaction.csv_extra": ["Points Earned"],
    # Only Channel is required if this table is present at all - Acquisition
    # Cost USD is checked separately, by L6 itself at runtime, because a
    # missing cost column should degrade ONE lever's sizing, not refuse the
    # entire analysis. A stale upload from before this column existed in the
    # generator was exactly the failure mode this softened.
    "Table23_Acquisition.csv": ["Masked Account Number", "Acquisition Channel"],
    "Table2b_Account_Open_Reference.csv": [
        "Masked Account Number", "Account Open Cycle Month",
    ],
    "Table6b_Deposit_Account_Cycle.csv": [
        "Masked Customer Number", "Ending Balance", "Interest Paid",
        "FTP Credit Value Monthly", "Cycle Month",
    ],
    "Table7b_Loan_Account_Cycle.csv": [
        "Masked Loan Account Number", "Current Balance", "Interest Accrued",
        "Cycle Month", "Charged Off Indicator",
    ],
    "Table22_Attrition_Events.csv": [
        "Masked Account Number", "Closure Cycle Month", "Closure Reason",
        "Voluntary Closure",
    ],
    "Table20_Limit_Change_Events.csv": [
        "Masked Account Number", "Cycle Month", "Old Credit Limit",
        "New Credit Limit", "Reason Code", "Adverse Action Notice Sent",
    ],
    "Table21_Rate_Change_Events.csv": [
        "Masked Account Number", "Cycle Month", "Old Purchase APR",
        "New Purchase APR", "Notice Sent Cycle Index",
    ],
    "Table7_Loan_Account.csv": ["Masked Customer Number", "Masked Loan Account Number"],
    "Table6_Deposit_Account.csv": ["Masked Customer Number", "Masked Deposit Account Number"],
}


def _check_ground_truth_leak(df: pd.DataFrame, name: str) -> None:
    for col in df.columns:
        low = col.lower()
        for marker in GROUND_TRUTH_MARKERS:
            if marker in low:
                raise DataContractViolation(
                    f"{name}: column '{col}' matches ground-truth marker "
                    f"'{marker}'. Refusing to load - this table must never "
                    f"carry a latent trait or a defect indicator. Every "
                    f"detection result downstream would be circular.")


@dataclass
class Portfolio:
    """Validated, loaded tables. Nothing downstream reads a raw CSV again."""
    root: Path
    tables: dict = field(default_factory=dict)

    def __getitem__(self, name: str) -> pd.DataFrame:
        return self.tables[name]

    def get(self, name: str, default=None):
        return self.tables.get(name, default)


def load_portfolio(root: Path | str) -> Portfolio:
    root = Path(root)
    if not root.exists():
        raise DataContractViolation(f"portfolio path does not exist: {root}")

    gt_dir = root / "_ground_truth"
    if gt_dir.exists():
        # The directory existing is fine and expected - it is evaluation-only.
        # What matters is that nothing in it, or shaped like it, is ever
        # loaded into `tables` below. It is deliberately never opened here.
        pass

    tables: dict[str, pd.DataFrame] = {}
    missing_tables = []
    for fname, required_cols in REQUIRED.items():
        p = root / fname
        if not p.exists():
            missing_tables.append(fname)
            continue
        df = pd.read_csv(p)
        _check_ground_truth_leak(df, fname)
        missing_cols = [c for c in required_cols if c not in df.columns]
        if missing_cols:
            raise DataContractViolation(
                f"{fname}: missing required column(s) {missing_cols}. "
                f"Refusing to run on an unvalidated data contract.")
        tables[fname] = df

    if missing_tables:
        raise DataContractViolation(
            f"Missing required table(s): {missing_tables}. "
            f"Refusing to run on an unvalidated data contract.")

    for fname, required_cols in OPTIONAL.items():
        real_name = fname.split("_extra")[0]
        p = root / real_name
        if not p.exists():
            continue
        df = pd.read_csv(p)
        _check_ground_truth_leak(df, real_name)
        missing_cols = [c for c in required_cols if c not in df.columns]
        if missing_cols:
            raise DataContractViolation(
                f"{real_name}: present but missing expected column(s) "
                f"{missing_cols}.")
        tables[real_name] = df

    return Portfolio(root=root, tables=tables)
