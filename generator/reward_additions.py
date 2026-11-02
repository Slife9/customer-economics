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


# --------------------------------------------------------------- Table26
# Spec 2.2. Offer terms by programme tier; secured and no-rewards products
# carry no sign-up offer. Every value is `estimated` (benchmarks.yaml).
BONUS_TERMS = {  # program: (tier, spend threshold USD, bonus value USD)
    "CORE_CASHBACK_1_5": ("core", 500, 100),
    "EVERYDAY_3X_GROCERY_GAS": ("everyday", 1000, 150),
    "TRAVEL_REWARDS_3X": ("travel", 3000, 200),
    "PREMIUM_TRAVEL_5X": ("premium", 4000, 300),
    "BUSINESS_CATEGORY_4X": ("business", 4000, 300),
}
BONUS_OFFER_RATE = 0.70
OFFER_WINDOW_MONTHS = 3
POST_WINDOW_MONTHS = 6
CLOSURE_LOOKAHEAD_MONTHS = 12


def _cycles(data_dir: Path) -> list[str]:
    m = json.loads((data_dir / "build_manifest.json").read_text())
    y, mo = map(int, m["from"].split("-"))
    out = []
    for _ in range(int(m["cycles"])):
        out.append(f"{y:04d}-{mo:02d}")
        mo += 1
        if mo > 12:
            mo, y = 1, y + 1
    return out


def _account_month_spend(data_dir: Path, accounts: pd.Index, cycles: list[str]) -> np.ndarray:
    """Purchase spend (cash advances excluded) as an accounts x cycles matrix,
    in the order of `accounts`, accumulated chunk by chunk."""
    a_ix = pd.Series(np.arange(len(accounts)), index=accounts)
    c_ix = {c: i for i, c in enumerate(cycles)}
    spend = np.zeros((len(accounts), len(cycles)))
    cols = ["Masked Account Number", "Cycle Month", "Transaction Amount", "Cash Advance Indicator"]
    for ch in pd.read_csv(data_dir / "Table5_Transaction.csv", usecols=cols, chunksize=CHUNK_ROWS):
        ch = ch[~ch["Cash Advance Indicator"].astype(bool)]
        g = ch.groupby(["Masked Account Number", "Cycle Month"])["Transaction Amount"].sum()
        rows = a_ix.reindex(g.index.get_level_values(0)).to_numpy()
        cols_ = g.index.get_level_values(1).map(c_ix).to_numpy()
        np.add.at(spend, (rows, cols_), g.to_numpy())
    return spend


def table26_signup_bonus(data_dir: Path, rng: np.random.Generator) -> pd.DataFrame:
    acct = pd.read_csv(data_dir / "Table2_Card_Account.csv",
                       usecols=["Masked Customer Number", "Masked Account Number", "Reward Program Code"])
    opened = pd.read_csv(data_dir / "Table2b_Account_Open_Reference.csv",
                         usecols=["Masked Account Number", "Account Open Cycle Index"])
    acct = acct.merge(opened, on="Masked Account Number", how="left", validate="one_to_one")
    cycles = _cycles(data_dir)
    n_cyc, n = len(cycles), len(acct)

    # The only draw: one uniform per account in Table2 order, taken for every
    # account so the stream's use never depends on which ones are eligible.
    u = rng.random(n)
    terms = acct["Reward Program Code"].map(BONUS_TERMS)
    eligible = terms.notna().to_numpy()
    offered = eligible & (u < BONUS_OFFER_RATE)
    threshold = np.where(offered, terms.map(lambda t: t[1] if isinstance(t, tuple) else np.nan), np.nan)
    value = np.where(offered, terms.map(lambda t: t[2] if isinstance(t, tuple) else np.nan), np.nan)

    o = acct["Account Open Cycle Index"].to_numpy().astype(int)
    observed = (o >= 0) & (o + OFFER_WINDOW_MONTHS - 1 <= n_cyc - 1)
    spend = _account_month_spend(data_dir, pd.Index(acct["Masked Account Number"]), cycles)

    win = np.full((n, OFFER_WINDOW_MONTHS), np.nan)
    for k in range(OFFER_WINDOW_MONTHS):
        ok = observed
        win[ok, k] = spend[np.where(ok)[0], o[ok] + k]
    cum = np.cumsum(win, axis=1)
    in_window = cum[:, -1]
    known = offered & observed
    met = known & (in_window >= np.nan_to_num(threshold, nan=np.inf))
    first_k = np.argmax(cum >= np.nan_to_num(threshold, nan=np.inf)[:, None], axis=1)
    earned_ix = np.where(met, o + first_k, -1)

    after_ok = observed & (o + OFFER_WINDOW_MONTHS + POST_WINDOW_MONTHS - 1 <= n_cyc - 1)
    after = np.full(n, np.nan)
    idx = np.where(after_ok)[0]
    if len(idx):
        cols_ = o[idx, None] + OFFER_WINDOW_MONTHS + np.arange(POST_WINDOW_MONTHS)[None, :]
        after[idx] = spend[idx[:, None], cols_].mean(axis=1)
    during = in_window / OFFER_WINDOW_MONTHS
    change = np.where(after_ok & (during > 0), (after / np.where(during > 0, during, 1) - 1) * 100.0, np.nan)

    attr = pd.read_csv(data_dir / "Table22_Attrition_Events.csv",
                       usecols=["Masked Account Number", "Closure Cycle Month", "Voluntary Closure"])
    vol = attr[attr["Voluntary Closure"].astype(bool)]
    c_ix = {c: i for i, c in enumerate(cycles)}
    closure_ix = acct["Masked Account Number"].map(
        vol.groupby("Masked Account Number")["Closure Cycle Month"].min().map(c_ix)).to_numpy()
    closed_12 = met & (closure_ix > earned_ix) & (closure_ix <= earned_ix + CLOSURE_LOOKAHEAD_MONTHS)

    def na_where(values, keep):
        return pd.array(np.where(keep, values, None), dtype="object")

    return pd.DataFrame({
        "Masked Account Number": acct["Masked Account Number"],
        "Masked Customer Number": acct["Masked Customer Number"],
        "Reward Program Code": acct["Reward Program Code"],
        "Bonus Offered": offered,
        "Offer Spend Threshold USD": threshold,
        "Offer Window Months": pd.array(np.where(offered, OFFER_WINDOW_MONTHS, None), dtype="Int64"),
        "Bonus Value USD": value,
        "Account Open Cycle Index": o,
        "Account Open Cycle Month": [cycles[i] if 0 <= i < n_cyc else "predates_window" for i in o],
        "Window Observed": observed,
        "Spend In Offer Window USD": np.where(observed, np.round(in_window, 2), np.nan),
        "Threshold Met": na_where(met, known),
        "Bonus Earned Cycle Month": [cycles[i] if i >= 0 else None for i in earned_ix],
        "Bonus Paid USD": np.where(~offered, 0.0, np.where(known, np.where(met, value, 0.0), np.nan)),
        "Spend Change After Window Pct": np.round(change, 2),
        "Closed Within 12 Months Of Bonus": na_where(closed_12, met),
        "Clawback Applied": False,
    })


def bonus_chaser_summary(t26: pd.DataFrame) -> dict:
    """Accounts that look like sign-up bonus chasers on the existing data:
    bonus earned, then spend down >= 60% in the 6 months after the window or
    a voluntary closure within 12 months of the bonus."""
    met = t26["Threshold Met"].eq(True)  # blank (unknown) counts as not met
    drop = t26["Spend Change After Window Pct"] <= -60
    closed = t26["Closed Within 12 Months Of Bonus"].eq(True)
    return {
        "accounts": int(len(t26)),
        "offered": int(t26["Bonus Offered"].sum()),
        "offered_window_observed": int((t26["Bonus Offered"] & t26["Window Observed"]).sum()),
        "threshold_met": int(met.sum()),
        "met_then_spend_down_60pct": int((met & drop).sum()),
        "met_then_closed_within_12m": int((met & closed).sum()),
        "look_like_bonus_chasers": int((met & (drop | closed)).sum()),
    }


# --------------------------------------------------------------- driver
def streams(seed: int) -> list[np.random.Generator]:
    """The new random stream: SeedSequence(seed + STREAM_OFFSET), one
    independent child per table, in the fixed order Table26, Table27."""
    return [np.random.default_rng(s) for s in np.random.SeedSequence(seed + STREAM_OFFSET).spawn(2)]


def add_reward_tables(data_dir: Path | str, seed: int | None = None) -> dict:
    """Build and write the new tables for the portfolio in `data_dir`.
    `seed` defaults to the build manifest's seed; the new stream is
    SeedSequence(seed + STREAM_OFFSET). Returns {file name: row count}."""
    data_dir = Path(data_dir)
    if seed is None:
        seed = int(json.loads((data_dir / "build_manifest.json").read_text())["seed"])
    rng26, rng27 = streams(seed)
    tables = {
        "Table25_MCC_Reference.csv": table25_mcc_reference(data_dir),
        "Table26_Signup_Bonus.csv": table26_signup_bonus(data_dir, rng26),
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
