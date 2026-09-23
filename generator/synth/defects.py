"""Planted Type A defects: discrete operational failures with a mechanism.

Each defect mutates already-generated tables so it leaves the SAME evidence a
real failure would leave - never a marker column. Detection must require
comparing two tables (schedule vs. charged, rate card vs. booked, contractual
vs. charged APR, waiver review date vs. today, promo expiry vs. status).

Prevalence is set PER DEFECT TYPE over its own eligible population, not as a
flat share of all accounts - a flat 3% of a 5,000-account book leaves some
defect types with too few positives to size anything against.
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def plant(tables: dict, cycles: list[str], rng: np.random.Generator,
         prevalence: dict) -> pd.DataFrame:
    """Mutates `tables` in place. Returns the Defect_Ground_Truth frame.

    `tables` keys used: accounts, cyc, tx, fee_events, waivers, wrong_earn_out
    (a set this function populates for rewards.earn to consume).
    """
    gt_rows = []
    accounts = tables["accounts"]
    cyc = tables["cyc"]
    tx = tables["tx"]

    # ---------------------------------------------------------- 1. UNPOSTED_CONTRACTUAL_FEE
    fee_paying = accounts[accounts["Annual Fee"] > 0]["Masked Account Number"]
    n1 = int(len(fee_paying) * prevalence.get("UNPOSTED_CONTRACTUAL_FEE", 0.0))
    victims1 = set(rng.choice(fee_paying.to_numpy(), size=min(n1, len(fee_paying)),
                              replace=False)) if n1 > 0 else set()
    if victims1:
        fe = tables["fee_events"]
        drop_mask = fe["Masked Account Number"].isin(victims1) & (fe["Fee Code"] == "ANNUAL_FEE")
        # Drop roughly half of this account's annual-fee charges - a fee that
        # is due most years but silently skipped some years, not every year,
        # which is what makes it distinguishable from a policy of not charging.
        idx_to_drop = fe[drop_mask].sample(frac=0.55, random_state=int(rng.integers(1e6))).index
        impact = fe.loc[idx_to_drop, "Fee Amount Charged"].sum()
        by_acct = fe.loc[idx_to_drop].groupby("Masked Account Number").agg(
            n=("Fee Amount Charged", "size"), amt=("Fee Amount Charged", "sum"))
        tables["fee_events"] = fe.drop(index=idx_to_drop)
        for acct, r in by_acct.iterrows():
            gt_rows.append({
                "Masked Account Number": acct, "Defect Type": "UNPOSTED_CONTRACTUAL_FEE",
                "Description": "Annual fee due under the fee schedule was not "
                               "posted in Fee Events for one or more anniversary cycles.",
                "Cycles Affected": int(r["n"]), "Estimated Total Impact": round(r["amt"], 2)})

    # ---------------------------------------------------------- 2/3. Waivers past terms
    waivers = tables["waivers"]
    if len(waivers):
        has_rev = waivers[waivers["Has Review Date"]]
        n2 = int(len(has_rev) * prevalence.get("EXPIRED_CONCESSION", 0.0))
        v2 = has_rev.sample(n=min(n2, len(has_rev)),
                            random_state=int(rng.integers(1e6))) if n2 > 0 else has_rev.iloc[0:0]
        for wid in v2["Waiver ID"]:
            waivers.loc[waivers["Waiver ID"] == wid, "Status"] = "expired_still_active"
        no_rev = waivers[~waivers["Has Review Date"]]
        n3 = len(no_rev)
        for _, w in v2.iterrows():
            gt_rows.append({
                "Masked Account Number": w["Masked Account Number"],
                "Defect Type": "EXPIRED_CONCESSION",
                "Description": "Waiver passed its review date but continued "
                               "suppressing the fee.",
                "Cycles Affected": 1, "Estimated Total Impact": np.nan})
        for _, w in no_rev.iterrows():
            gt_rows.append({
                "Masked Account Number": w["Masked Account Number"],
                "Defect Type": "WAIVER_NO_EXPIRY",
                "Description": "Waiver was granted with no review date, so it "
                               "cannot be reviewed for continued suitability.",
                "Cycles Affected": 1, "Estimated Total Impact": np.nan})

    # ---------------------------------------------------------- 4. PROMO_FAILED_TO_REVERT
    has_expiry = cyc[cyc["Promotional Expiry Cycle Index"] >= 0][
        "Masked Account Number"].unique()
    n4 = int(len(has_expiry) * prevalence.get("PROMO_FAILED_TO_REVERT", 0.0))
    v4 = set(rng.choice(has_expiry, size=min(n4, len(has_expiry)), replace=False)) \
        if n4 > 0 and len(has_expiry) else set()
    if v4:
        m = cyc["Masked Account Number"].isin(v4)
        past_expiry = m & (cyc["Cycle Index"] >= cyc["Promotional Expiry Cycle Index"]) \
            & (cyc["Promotional Expiry Cycle Index"] >= 0)
        # The promo rate that WAS in force before expiry, carried forward as
        # the rate that keeps being charged - this is the failure to revert.
        last_promo_rate = (cyc.loc[m].sort_values("Cycle Index")
                          .groupby("Masked Account Number")["Promotional Rate In Force"]
                          .transform(lambda s: s.ffill()))
        stuck_rate = last_promo_rate.reindex(cyc.index).fillna(0.0)
        cyc.loc[past_expiry, "Promotional Status"] = "Active"
        cyc.loc[past_expiry, "Promotional Rate In Force"] = stuck_rate[past_expiry]
        # Interest should have reverted to the contractual rate; the shortfall
        # is the impact (evidence: rate charged vs. expiry-cycle status).
        extra_bal = cyc.loc[past_expiry, "Promotional Balance"]
        should_rate = cyc.loc[past_expiry, "Charged Purchase APR"].to_numpy() / 100.0 / 12.0
        was_rate = stuck_rate[past_expiry].to_numpy() / 100.0 / 12.0
        shortfall = extra_bal.to_numpy() * (should_rate - was_rate)
        cyc.loc[past_expiry, "Promotional Interest"] = np.maximum(
            cyc.loc[past_expiry, "Promotional Interest"] - shortfall, 0)
        by_acct = pd.DataFrame({
            "Masked Account Number": cyc.loc[past_expiry, "Masked Account Number"],
            "shortfall": shortfall}).groupby("Masked Account Number").agg(
                n=("shortfall", "size"), amt=("shortfall", "sum"))
        for acct, r in by_acct.iterrows():
            gt_rows.append({
                "Masked Account Number": acct, "Defect Type": "PROMO_FAILED_TO_REVERT",
                "Description": "Promotional rate remained in force past its "
                               "recorded expiry cycle.",
                "Cycles Affected": int(r["n"]), "Estimated Total Impact": round(r["amt"], 2)})

    # ---------------------------------------------------------- 5. INTERCHANGE_BELOW_EXPECTED
    n5_accts = accounts["Masked Account Number"].sample(
        n=max(int(len(accounts) * prevalence.get("INTERCHANGE_BELOW_EXPECTED", 0.0)), 0),
        random_state=int(rng.integers(1e6))) if len(accounts) else pd.Series([], dtype=object)
    v5 = set(n5_accts)
    if v5 and len(tx):
        m = tx["Masked Account Number"].isin(v5)
        under_factor = rng.uniform(0.55, 0.80, m.sum())
        entitled = tx.loc[m, "Interchange Earned"].to_numpy()
        tx.loc[m, "Interchange Earned"] = np.round(entitled * under_factor, 4)
        shortfall = entitled - tx.loc[m, "Interchange Earned"].to_numpy()
        by_acct = pd.DataFrame({
            "Masked Account Number": tx.loc[m, "Masked Account Number"],
            "shortfall": shortfall}).groupby("Masked Account Number").agg(
                n=("shortfall", "size"), amt=("shortfall", "sum"))
        for acct, r in by_acct.iterrows():
            gt_rows.append({
                "Masked Account Number": acct, "Defect Type": "INTERCHANGE_BELOW_EXPECTED",
                "Description": "Interchange booked below the rate card's "
                               "entitled rate for this product tier and category.",
                "Cycles Affected": int(r["n"]), "Estimated Total Impact": round(r["amt"], 2)})

    # ---------------------------------------------------------- 6. PRICE_BELOW_CONTRACT
    n6 = int(len(accounts) * prevalence.get("PRICE_BELOW_CONTRACT", 0.0))
    v6 = set(rng.choice(accounts["Masked Account Number"].to_numpy(),
                        size=min(n6, len(accounts)), replace=False)) if n6 > 0 else set()
    if v6:
        m = cyc["Masked Account Number"].isin(v6)
        gap = rng.uniform(1.5, 4.0, m.sum())
        old_charged = cyc.loc[m, "Charged Purchase APR"].to_numpy()
        new_charged = np.maximum(cyc.loc[m, "Contractual Purchase APR"].to_numpy() - gap, 9.99)
        cyc.loc[m, "Charged Purchase APR"] = new_charged
        # Recompute purchase interest at the mispriced rate for consistency.
        avg_bal = cyc.loc[m, "Purchase Balance"].to_numpy()
        implied_shortfall = avg_bal * (old_charged - new_charged) / 100.0 / 12.0
        by_acct = pd.DataFrame({
            "Masked Account Number": cyc.loc[m, "Masked Account Number"],
            "shortfall": np.maximum(implied_shortfall, 0)}).groupby(
                "Masked Account Number").agg(n=("shortfall", "size"),
                                             amt=("shortfall", "sum"))
        for acct, r in by_acct.iterrows():
            gt_rows.append({
                "Masked Account Number": acct, "Defect Type": "PRICE_BELOW_CONTRACT",
                "Description": "Charged purchase APR was below the account's "
                               "contractual APR.",
                "Cycles Affected": int(r["n"]), "Estimated Total Impact": round(r["amt"], 2)})

    # ---------------------------------------------------------- 7. WRONG_EARN_RULE
    n7 = int(len(accounts) * prevalence.get("WRONG_EARN_RULE", 0.0))
    v7 = set(rng.choice(accounts["Masked Account Number"].to_numpy(),
                        size=min(n7, len(accounts)), replace=False)) if n7 > 0 else set()
    tables["wrong_earn_accounts"] = v7
    # Ground truth for this type is appended after rewards.earn() runs, by the
    # caller, since the impact (bonus points foregone) is only known then.

    return pd.DataFrame(gt_rows), v7


def wrong_earn_ground_truth(tx_before: pd.DataFrame, tx_after: pd.DataFrame,
                            wrong_earn_accounts: set) -> pd.DataFrame:
    if not wrong_earn_accounts:
        return pd.DataFrame(columns=["Masked Account Number", "Defect Type",
                                     "Description", "Cycles Affected",
                                     "Estimated Total Impact"])
    diff = tx_before["Points Earned"].to_numpy() - tx_after["Points Earned"].to_numpy()
    df = pd.DataFrame({
        "Masked Account Number": tx_after["Masked Account Number"],
        "diff": diff})
    df = df[df["Masked Account Number"].isin(wrong_earn_accounts) & (df["diff"] > 0)]
    by_acct = df.groupby("Masked Account Number").agg(n=("diff", "size"), amt=("diff", "sum"))
    rows = [{"Masked Account Number": a, "Defect Type": "WRONG_EARN_RULE",
            "Description": "Base earn rate was applied on transactions that "
                           "qualified for the program's bonus category.",
            "Cycles Affected": int(r["n"]),
            "Estimated Total Impact": round(r["amt"] * 0.01, 2)}
           for a, r in by_acct.iterrows()]
    return pd.DataFrame(rows)
