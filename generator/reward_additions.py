"""
Reward-profitability data additions (specs/reward_data_additions).

A post-processing step that READS a finished portfolio's published tables and
WRITES new tables only:

    Table25_MCC_Reference.csv        reference data, no randomness
    Table26_Signup_Bonus.csv         offer terms from the new stream; the rest
                                     derived from existing tables
    Table27_Bureau_Inquiries.csv     counts from the new stream, raised by
                                     signals read from existing tables

Nothing the generator already writes is read-modified-written, and none of
the generator's own random draws are consumed: this step has its own stream,
`SeedSequence(seed + STREAM_OFFSET)`, spawned into one independent child per
table, so adding a table later cannot shift another table's draws.

    python -m generator.reward_additions --data <portfolio dir>

build() calls add_reward_tables() last, after build_manifest.json is written.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

STREAM_OFFSET = 7919
CHUNK_ROWS = 500_000
MCC_COL = "Merchant Category Code (MCC)"

# --------------------------------------------------------------- Table25
# Spec 2.1. Descriptions for codes the generator never emits are the standard
# network names, so the reference is usable on real data too.
QUASI_CASH_MCCS = {
    4829: "Wire Transfers and Money Orders",
    6050: "Quasi Cash - Financial Institution",
    6051: "Quasi Cash - Non-Financial Institution",
    6540: "Stored Value Card Purchase / Load",
    7995: "Betting and Gambling",
}
LOW_INTERCHANGE_MCCS = {
    9311: "Tax Payments",
    9399: "Government Services",
    4900: "Utilities Electric Gas Water",
    6300: "Insurance Sales and Premiums",
    6513: "Real Estate Agents and Managers - Rentals",
    6012: "Financial Institutions - Merchandise and Services",
}
LOW_INTERCHANGE_RATE_PCT = 1.5


def _mcc_aggregates(data_dir: Path) -> pd.DataFrame:
    """Purchases (cash advances excluded) by MCC, read in chunks."""
    parts = []
    cols = [MCC_COL, "Merchant Category Description", "Transaction Amount",
            "Interchange Earned", "Cash Advance Indicator"]
    for ch in pd.read_csv(data_dir / "Table5_Transaction.csv", usecols=cols,
                          chunksize=CHUNK_ROWS):
        ch = ch[~ch["Cash Advance Indicator"].astype(bool)]
        parts.append(ch.groupby(MCC_COL).agg(
            desc=("Merchant Category Description", "first"),
            n=("Transaction Amount", "size"),
            amt=("Transaction Amount", "sum"),
            ie=("Interchange Earned", "sum")))
    agg = pd.concat(parts).groupby(level=0).agg(
        desc=("desc", "first"), n=("n", "sum"), amt=("amt", "sum"), ie=("ie", "sum"))
    return agg


def table25_mcc_reference(data_dir: Path) -> pd.DataFrame:
    agg = _mcc_aggregates(data_dir)
    codes = sorted(set(agg.index.astype(int)) | set(QUASI_CASH_MCCS) | set(LOW_INTERCHANGE_MCCS))
    rows = []
    for mcc in codes:
        present = mcc in agg.index
        a = agg.loc[mcc] if present else None
        rate = round(float(a["ie"] / a["amt"] * 100.0), 4) if present and a["amt"] > 0 else None
        quasi = mcc in QUASI_CASH_MCCS
        listed_low = mcc in LOW_INTERCHANGE_MCCS
        observed_low = rate is not None and rate <= LOW_INTERCHANGE_RATE_PCT
        low = listed_low or observed_low
        if quasi:
            treatment = "no_earn"
            why = "Cash-like spend: earns rewards while carrying little or no interchange."
        elif low:
            treatment = "reduced_earn"
            why = ("Low or fixed interchange by network category"
                   if listed_low else
                   f"Observed effective interchange {rate:.2f}% is at or below "
                   f"{LOW_INTERCHANGE_RATE_PCT:.1f}%")
            if listed_low and observed_low:
                why += f"; observed {rate:.2f}% here"
            why += " - full-rate rewards can exceed the interchange earned."
        else:
            treatment = "standard"
            why = "Interchange covers a standard earn rate."
        rows.append({
            MCC_COL: mcc,
            "Merchant Category Description": (a["desc"] if present else
                                              QUASI_CASH_MCCS.get(mcc) or LOW_INTERCHANGE_MCCS.get(mcc)),
            "Present In Data": present,
            "Purchase Transactions": int(a["n"]) if present else 0,
            "Purchase Amount USD": round(float(a["amt"]), 2) if present else 0.0,
            "Observed Effective Interchange Rate Pct": rate,
            "Quasi Cash Flag": quasi,
            "Low Interchange Flag": low,
            "Recommended Reward Treatment": treatment,
            "Rationale": why,
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------- driver
def add_reward_tables(data_dir: Path | str, seed: int | None = None) -> dict:
    """Build and write the new tables for the portfolio in `data_dir`.
    `seed` defaults to the build manifest's seed; the new stream is
    SeedSequence(seed + STREAM_OFFSET). Returns {file name: row count}."""
    data_dir = Path(data_dir)
    if seed is None:
        seed = int(json.loads((data_dir / "build_manifest.json").read_text())["seed"])
    tables = {
        "Table25_MCC_Reference.csv": table25_mcc_reference(data_dir),
    }
    for name, df in tables.items():
        df.to_csv(data_dir / name, index=False)
    return {name: len(df) for name, df in tables.items()}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="a generated portfolio directory")
    ap.add_argument("--seed", type=int, default=None,
                    help="base seed (defaults to build_manifest.json's)")
    a = ap.parse_args()
    print(json.dumps(add_reward_tables(Path(a.data), a.seed), indent=2))
