"""
Unused-line data additions (specs/unused_line_management, brief section 5).

A post-processing step that READS a finished portfolio's published tables and
WRITES new tables only:

    Table29_Score_History.csv      behaviour and bureau score per account and
                                   cycle; the behaviour score is derived from
                                   Table8 PD 12 Month, the bureau score adds
                                   delinquency (Table4) and noise from the new
                                   stream
    Table30_Card_Activation.csv    activation of every plastic in Table3; use
                                   (Table5) forces activation, the rest comes
                                   from the new stream

Nothing the generator already writes is read-modified-written, and none of
the generator's own random draws are consumed: this step has its own stream,
`SeedSequence(seed + STREAM_OFFSET)`, spawned into one independent child per
table, so adding a table later cannot shift another table's draws. The offset
differs from the reward additions' (7919), and the table numbers start at 29:
Tables 25-28 are reserved for the reward additions on their own branch.

    python -m generator.unused_line_additions --data <portfolio dir>

build() calls add_unused_line_tables() last, after build_manifest.json is
written. Every parameter below is `estimated` (illustrative, not sourced).
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

STREAM_OFFSET = 104729
CHUNK_ROWS = 500_000
ACCT = "Masked Account Number"
CUST = "Masked Customer Number"

# --------------------------------------------------------------- Table29
# Behaviour score: standard scorecard scaling of the account's smoothed
# 12-month PD - 20 points to double the good:bad odds, 660 at odds of 32:1
# (PD about 3%). Smoothing over 3 cycles removes the scorecard's month-to-month
# model error (risk.py draws it independently every cycle).
SCORE_MIN, SCORE_MAX = 300, 850
POINTS_TO_DOUBLE_ODDS = 20.0
ANCHOR_SCORE, ANCHOR_ODDS = 660.0, 32.0
SMOOTHING_CYCLES = 3
# Bureau score: Table1 Credit Score at the account's first observed cycle,
# then moving with the behaviour score, a delinquency penalty and noise.
BEHAVIOUR_PASS_THROUGH = 0.6
DPD_PENALTY_FROM_DAYS = 30
DPD_PENALTY_POINTS_PER_DAY = 2.0
DPD_PENALTY_CAP = 110.0
DPD_PENALTY_MONTHLY_RETENTION = 0.97
NOISE_AR = 0.85
NOISE_SD = 6.0
CHANGE_WINDOW = 6

# --------------------------------------------------------------- Table30
# A card used while it is live must have been activated by its first use.
# Activation lag after issue, in months, and the chance that a card never
# used in the window was activated anyway (higher when the whole account is
# inactive, since its earlier card was usually in use before the window).
ACTIVATION_LAG_MONTHS = [0, 1, 2]
ACTIVATION_LAG_WEIGHTS = [0.80, 0.15, 0.05]
P_ACTIVATED_NO_USE_ACTIVE_ACCOUNT = 0.35
P_ACTIVATED_NO_USE_INACTIVE_ACCOUNT = 0.55


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


def _accounts(data_dir: Path) -> pd.DataFrame:
    return pd.read_csv(data_dir / "Table2_Card_Account.csv", usecols=[CUST, ACCT])


def _matrix(data_dir: Path, table: str, value: str, acct_ix: pd.Index,
            c_ix: dict, n_cyc: int) -> np.ndarray:
    """Account x cycle matrix of one column; NaN where the account has no row."""
    m = np.full((len(acct_ix), n_cyc), np.nan)
    for ch in pd.read_csv(data_dir / table, usecols=[ACCT, "Cycle Month", value],
                          chunksize=CHUNK_ROWS):
        m[acct_ix.get_indexer(ch[ACCT]), ch["Cycle Month"].map(c_ix).to_numpy()] = ch[value].to_numpy()
    return m


def behaviour_score(pd12: np.ndarray) -> np.ndarray:
    """Unrounded behaviour score from an account x cycle PD matrix (NaN kept)."""
    valid = ~np.isnan(pd12)
    p = np.clip(np.where(valid, pd12, 0.5), 1e-6, 1 - 1e-6)
    logit = np.where(valid, np.log(p / (1 - p)), 0.0)
    w = SMOOTHING_CYCLES
    pad = np.zeros((len(p), w))
    s = np.cumsum(np.concatenate([pad, logit], axis=1), axis=1)
    k = np.cumsum(np.concatenate([pad, valid.astype(float)], axis=1), axis=1)
    smooth = (s[:, w:] - s[:, :-w]) / np.maximum(k[:, w:] - k[:, :-w], 1)
    factor = POINTS_TO_DOUBLE_ODDS / np.log(2.0)
    score = ANCHOR_SCORE + factor * (-smooth - np.log(ANCHOR_ODDS))
    return np.where(valid, score, np.nan)


def table29_score_history(data_dir: Path, rng: np.random.Generator) -> pd.DataFrame:
    cycles = _cycles(data_dir)
    n_cyc = len(cycles)
    c_ix = {c: i for i, c in enumerate(cycles)}
    acc = _accounts(data_dir)
    acct_ix = pd.Index(acc[ACCT])
    n = len(acc)
    anchor = acc[CUST].map(pd.read_csv(data_dir / "Table1_Customer.csv", usecols=[CUST, "Credit Score"])
                           .set_index(CUST)["Credit Score"]).to_numpy(dtype=float)

    pd12 = _matrix(data_dir, "Table8_Risk_Parameters.csv", "PD 12 Month", acct_ix, c_ix, n_cyc)
    dpd = np.nan_to_num(_matrix(data_dir, "Table4_Account_Cycle.csv", "Days Past Due", acct_ix, c_ix, n_cyc))
    valid = ~np.isnan(pd12)
    has_rows = valid.any(axis=1)
    ref = np.where(has_rows, valid.argmax(axis=1), n_cyc)

    beh = behaviour_score(pd12)
    beh_ref = beh[np.arange(n), np.minimum(ref, n_cyc - 1)]

    # Fixed-size draw (every account x cycle, C order), so the stream's use
    # never depends on which rows exist.
    z = rng.standard_normal((n, n_cyc))
    pen = np.zeros(n)
    noise = np.zeros(n)
    bureau = np.full((n, n_cyc), np.nan)
    for t in range(n_cyc):
        after = t > ref
        hit = np.where(dpd[:, t] >= DPD_PENALTY_FROM_DAYS,
                       np.minimum(DPD_PENALTY_POINTS_PER_DAY * dpd[:, t], DPD_PENALTY_CAP), 0.0)
        pen = np.maximum(hit, np.where(after, pen * DPD_PENALTY_MONTHLY_RETENTION, 0.0))
        noise = np.where(after, NOISE_AR * noise + NOISE_SD * z[:, t], 0.0)
        bureau[:, t] = anchor + BEHAVIOUR_PASS_THROUGH * (beh[:, t] - beh_ref) - pen + noise

    beh_i = np.clip(np.rint(beh), SCORE_MIN, SCORE_MAX)
    bur_i = np.clip(np.rint(bureau), SCORE_MIN, SCORE_MAX)
    bur_i[~valid] = np.nan
    lag = np.full_like(bur_i, np.nan)
    lag[:, CHANGE_WINDOW:] = bur_i[:, :-CHANGE_WINDOW]
    change = bur_i - lag

    a, t = np.nonzero(valid)
    return pd.DataFrame({
        CUST: acc[CUST].to_numpy()[a],
        ACCT: acc[ACCT].to_numpy()[a],
        "Cycle Month": np.array(cycles)[t],
        "Behaviour Score": beh_i[a, t].astype(int),
        "Bureau Score": bur_i[a, t].astype(int),
        "Bureau Score Change 6 Months": pd.array(change[a, t], dtype="Float64").round().astype("Int64"),
        "Months Of Score History": (t - ref[a] + 1).astype(int),
    })


# --------------------------------------------------------------- Table30
def table30_card_activation(data_dir: Path, rng: np.random.Generator) -> pd.DataFrame:
    cycles = _cycles(data_dir)
    n_cyc = len(cycles)
    c_ix = {c: i for i, c in enumerate(cycles)}
    acc = _accounts(data_dir)
    acct_ix = pd.Index(acc[ACCT])

    used = np.zeros((len(acc), n_cyc), dtype=bool)
    for ch in pd.read_csv(data_dir / "Table5_Transaction.csv", usecols=[ACCT, "Cycle Month"],
                          chunksize=CHUNK_ROWS):
        used[acct_ix.get_indexer(ch[ACCT]), ch["Cycle Month"].map(c_ix).to_numpy()] = True
    open_end = np.zeros(len(acc), dtype=int)  # one past the last cycle with a Table4 row
    for ch in pd.read_csv(data_dir / "Table4_Account_Cycle.csv", usecols=[ACCT, "Cycle Index"],
                          chunksize=CHUNK_ROWS):
        ix = acct_ix.get_indexer(ch[ACCT])
        np.maximum.at(open_end, ix, ch["Cycle Index"].to_numpy() + 1)

    cards = pd.read_csv(data_dir / "Table3_Card.csv",
                        usecols=["Masked Card Number", ACCT, "Card Sequence Number",
                                 "Issue Cycle Index", "Deactivation Cycle Index", "Card Status"])
    a = acct_ix.get_indexer(cards[ACCT])
    issue = cards["Issue Cycle Index"].to_numpy()
    # Table3 writes -1 both for "never deactivated" and for a deactivation in
    # the cycle before the window; Card Status tells them apart.
    never_deactivated = (cards["Card Status"] == "active").to_numpy()
    deact = cards["Deactivation Cycle Index"].to_numpy()
    start = np.maximum(issue, 0)
    end = np.minimum(np.where(never_deactivated, n_cyc, deact), open_end[a])
    live = np.maximum(end - start, 0)
    observed = end > 0

    t = np.arange(n_cyc)
    in_life = (t >= start[:, None]) & (t < end[:, None]) & used[a]
    any_use = in_life.any(axis=1)
    first_use = np.where(any_use, in_life.argmax(axis=1), -1)
    account_active = used.any(axis=1)[a]

    # Fixed-size draws (one of each per card, in Table3 order).
    lag = rng.choice(ACTIVATION_LAG_MONTHS, p=ACTIVATION_LAG_WEIGHTS, size=len(cards))
    u = rng.random(len(cards))

    act_if_used = issue + np.minimum(lag, first_use - issue)
    p_no_use = np.where(account_active, P_ACTIVATED_NO_USE_ACTIVE_ACCOUNT,
                        P_ACTIVATED_NO_USE_INACTIVE_ACCOUNT)
    act_no_use = issue + lag
    activated_no_use = (u < p_no_use) & (act_no_use < end)

    activated = np.where(any_use, True, activated_no_use) & observed
    act_ix = np.where(any_use, act_if_used, act_no_use)
    basis = np.select(
        [~observed, any_use & (act_if_used == first_use), any_use, activated_no_use],
        ["not_observed", "at_first_use", "before_first_use", "no_use_in_window"],
        default="not_activated")
    status = np.where(~observed, "not_observed", np.where(activated, "activated", "not_activated"))
    act_col = pd.array(np.where(activated, act_ix, 0), dtype="Int64")
    act_col[~activated] = pd.NA
    in_window = activated & (act_ix >= 0) & (act_ix < n_cyc)
    month = np.where(in_window, np.array(cycles)[np.clip(act_ix, 0, n_cyc - 1)], "")
    fu = pd.array(first_use, dtype="Int64")
    fu[~any_use] = pd.NA

    return pd.DataFrame({
        "Masked Card Number": cards["Masked Card Number"].to_numpy(),
        ACCT: cards[ACCT].to_numpy(),
        "Card Sequence Number": cards["Card Sequence Number"].to_numpy(),
        "Issue Cycle Index": issue,
        "Months Live In Window": live,
        "First Use Cycle Index": fu,
        "Activation Status": status,
        "Activation Cycle Index": act_col,
        "Activation Cycle Month": month,
        "Activation Basis": basis,
    })


# --------------------------------------------------------------- driver
def streams(seed: int) -> list[np.random.Generator]:
    """The new random stream: SeedSequence(seed + STREAM_OFFSET), one
    independent child per table, in the fixed order Table29, Table30."""
    return [np.random.default_rng(s) for s in np.random.SeedSequence(seed + STREAM_OFFSET).spawn(2)]


def add_unused_line_tables(data_dir: Path | str, seed: int | None = None,
                           out_dir: Path | str | None = None) -> dict:
    """Build and write the new tables for the portfolio in `data_dir`.
    `seed` defaults to the build manifest's seed; the new stream is
    SeedSequence(seed + STREAM_OFFSET). `out_dir` (default `data_dir`) is
    where the new files go - the audit writes elsewhere to compare runs.
    Returns {file name: row count}."""
    data_dir = Path(data_dir)
    out_dir = data_dir if out_dir is None else Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if seed is None:
        seed = int(json.loads((data_dir / "build_manifest.json").read_text())["seed"])
    rng29, rng30 = streams(seed)
    tables = {
        "Table29_Score_History.csv": table29_score_history(data_dir, rng29),
        "Table30_Card_Activation.csv": table30_card_activation(data_dir, rng30),
    }
    for name, df in tables.items():
        df.to_csv(out_dir / name, index=False)
    return {name: len(df) for name, df in tables.items()}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="a generated portfolio directory")
    ap.add_argument("--seed", type=int, default=None,
                    help="base seed (defaults to build_manifest.json's)")
    a = ap.parse_args()
    print(json.dumps(add_unused_line_tables(Path(a.data), a.seed), indent=2))
