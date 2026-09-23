"""Account cycles: the monthly state everything else reads.

Four things here are deliberately different from a naive generator.

1. BALANCE IS NOT appetite x limit. Spend accumulates, payments reduce it, and
   the credit limit binds only as an authorization constraint. A tight limit
   declines transactions and pushes utilization up; a generous limit lets the
   balance float wherever the customer carries it. Utilization therefore
   RESPONDS to limit policy instead of being a relabeled latent.

2. DELINQUENCY IS A STATE MACHINE with bucket persistence, cure, roll, and an
   absorbing charge-off at 180 days. Without an absorbing state there is no
   credit loss, and the score/risk gradient collapses.

3. ACCOUNT TYPE IS DERIVED FROM TRAILING BEHAVIOR over three cycles, so
   revolver/transactor status is sticky rather than re-rolled each month.

4. THE ANNUAL FEE POSTS ON THE ANNIVERSARY CYCLE ONLY. Posting it every cycle
   overstates fee revenue twelvefold and is invisible to a consistency check
   that only asks whether the charged amount equals the stated amount.

Payment allocation follows Reg Z 1026.53: amounts above the minimum go to the
highest-APR balance first.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from . import policy as P
from .latents import true_default_hazard

CHARGE_OFF_DPD = 180
BUCKETS = [0, 30, 60, 90, 120, 150, 180]


def _logistic(z):
    return 1.0 / (1.0 + np.exp(-z))


def simulate(accounts: pd.DataFrame, cust: pd.DataFrame, lat: pd.DataFrame,
             tx: pd.DataFrame, cycles: list[str], rng: np.random.Generator,
             profile: dict):
    n, n_cyc = len(accounts), len(cycles)
    ai = np.arange(n)

    appetite = lat["credit_appetite"].to_numpy()
    discipline = lat["payment_discipline"].to_numpy()
    satisfaction = lat["latent_satisfaction"].to_numpy().copy()
    price_sens = lat["price_sensitivity"].to_numpy()
    true_hazard = true_default_hazard(discipline, appetite)

    limit = accounts["Current Credit Limit"].to_numpy().astype(float)
    contract_apr = accounts["Contractual Purchase APR"].to_numpy().astype(float)
    charged_apr = contract_apr.copy()
    cash_apr = np.clip(contract_apr + 4.5, 0, 35.99)
    annual_fee = accounts["Annual Fee"].to_numpy().astype(float)
    open_idx = accounts["Account Open Cycle Index"].to_numpy()
    score = cust["Credit Score"].to_numpy()
    hardship = cust["Hardship Status"].to_numpy()
    scra = cust["SCRA Flag"].to_numpy()
    # SCRA caps the rate at 6% on obligations predating service.
    charged_apr = np.where(scra, np.minimum(charged_apr, 6.0), charged_apr)

    # ---- promotional offers -------------------------------------------
    promo_share = profile.get("promo_share", 0.18)
    has_promo = rng.random(n) < promo_share
    promo_start = np.where(has_promo, np.maximum(open_idx, 0)
                           + rng.integers(0, max(n_cyc // 2, 1), n), 10 ** 6)
    promo_term = rng.choice([6, 12, 15, 18, 21], n, p=[.14, .34, .18, .24, .10])
    promo_expiry = promo_start + promo_term
    promo_rate = np.where(rng.random(n) < 0.72, 0.0, 4.99)

    # ---- spend by account-cycle ---------------------------------------
    spend = np.zeros((n, n_cyc))
    cash_spend = np.zeros((n, n_cyc))
    if len(tx):
        g = tx.groupby(["_acct_ix", "_cycle_ix"])["Transaction Amount"].sum()
        idx = np.array(list(g.index.to_list()))
        spend[idx[:, 0], idx[:, 1]] = g.to_numpy()
        ca = tx[tx["Cash Advance Indicator"]]
        if len(ca):
            g2 = ca.groupby(["_acct_ix", "_cycle_ix"])["Transaction Amount"].sum()
            i2 = np.array(list(g2.index.to_list()))
            cash_spend[i2[:, 0], i2[:, 1]] = g2.to_numpy()
            spend[i2[:, 0], i2[:, 1]] -= g2.to_numpy()

    # ---- persistent payment mode --------------------------------------
    # Propensity to settle in full. Persistent per account, with small monthly
    # noise, so revolver/transactor status does not re-roll every cycle.
    pay_full_propensity = _logistic(
        -0.48 + 5.20 * (discipline - 0.5) - 1.60 * (appetite - 0.35))

    # ---- state ---------------------------------------------------------
    pur_bal = np.zeros(n)
    cash_bal = np.zeros(n)
    promo_bal = np.zeros(n)
    dpd = np.zeros(n, dtype=int)
    closed_at = np.full(n, n_cyc, dtype=int)
    charged_off_at = np.full(n, -1, dtype=int)
    violations_recent = np.zeros(n, dtype=int)
    last_violation_cycle = np.full(n, -99)
    paid_full_hist = np.zeros((n, n_cyc), dtype=bool)
    spend_hist = np.zeros((n, n_cyc))
    peak_util = np.zeros(n)
    months_active = np.zeros(n, dtype=int)

    rows = []
    limit_events, rate_events, attrition_events, fee_events = [], [], [], []
    declines = np.zeros((n, n_cyc))

    use_obs = profile.get("line_review_uses_observed_behavior", False)
    generosity = profile.get("limit_generosity", 1.0)
    repricing_tracks_risk = profile.get("repricing_tracks_risk", False)

    for c in range(n_cyc):
        live = (c >= open_idx) & (c < closed_at) & (charged_off_at < 0)
        months_active = months_active + live.astype(int)

        # ---- promotional state ----------------------------------------
        promo_active = live & (c >= promo_start) & (c < promo_expiry)
        promo_just_started = live & (c == promo_start)
        # A promotional balance transfer lands when the promo starts.
        bt_amount = np.where(promo_just_started,
                             np.clip(limit * rng.uniform(0.18, 0.55, n), 0,
                                     np.maximum(limit - pur_bal - cash_bal, 0)), 0.0)
        promo_bal = promo_bal + bt_amount
        bt_fee = np.where(bt_amount > 0, np.maximum(bt_amount * 0.03, 5.0), 0.0)

        # ---- authorization: the limit binds here ----------------------
        want = spend[:, c]
        want_cash = cash_spend[:, c]
        headroom = np.maximum(limit - (pur_bal + cash_bal + promo_bal), 0.0)
        auth = np.minimum(want + want_cash, headroom)
        declined = np.maximum(want + want_cash - auth, 0.0)
        declines[:, c] = np.where(live, declined, 0.0)
        share_cash = np.divide(want_cash, np.maximum(want + want_cash, 1e-9))
        auth_cash = auth * share_cash
        auth_pur = auth - auth_cash
        pur_bal = np.where(live, pur_bal + auth_pur, pur_bal)
        cash_bal = np.where(live, cash_bal + auth_cash, cash_bal)
        spend_hist[:, c] = np.where(live, auth, 0.0)

        # ---- interest -------------------------------------------------
        prev_full = paid_full_hist[:, c - 1] if c > 0 else np.zeros(n, bool)
        # Grace period: a settled account pays no purchase interest.
        grace = prev_full & (pur_bal <= auth_pur + 0.01)
        avg_daily_pur = np.maximum(pur_bal - 0.5 * auth_pur, 0.0)
        pur_int = np.where(grace, 0.0, avg_daily_pur * charged_apr / 100.0 / 12.0)
        cash_int = cash_bal * cash_apr / 100.0 / 12.0
        eff_promo_rate = np.where(promo_active, promo_rate, charged_apr)
        promo_int = promo_bal * eff_promo_rate / 100.0 / 12.0
        # Non-accrual at 90+ DPD: a real issuer stops accruing interest on a
        # severely delinquent balance, which is also why capital.py assigns
        # nonaccrual exposures the 150% risk weight. Without this the balance
        # compounds unboundedly on an account that has stopped paying at all.
        accruing = live & (dpd < 90)
        pur_int = np.where(accruing, pur_int, 0.0)
        cash_int = np.where(accruing, cash_int, 0.0)
        promo_int = np.where(accruing, promo_int, 0.0)

        # ---- fees ------------------------------------------------------
        # Annual fee posts on the anniversary cycle only.
        since_open = c - open_idx
        anniversary = live & (since_open >= 0) & (since_open % 12 == 0)
        af = np.where(anniversary, annual_fee, 0.0)

        was_delinquent = dpd >= 30
        within_six = (c - last_violation_cycle) <= 6
        late_fee_amt = np.where(was_delinquent,
                                np.where(within_six, 43.0, 32.0), 0.0)
        # Reg Z safe harbor: the fee may not exceed the minimum payment due.
        prior_bal = pur_bal + cash_bal + promo_bal
        min_due_prelim = np.maximum(np.minimum(prior_bal, 35.0),
                                    prior_bal * 0.01 + pur_int + cash_int + promo_int)
        late_fee_amt = np.minimum(late_fee_amt, np.maximum(min_due_prelim, 0.0))
        late_fee_amt = np.where(live, late_fee_amt, 0.0)
        last_violation_cycle = np.where(late_fee_amt > 0, c, last_violation_cycle)

        total_fees = af + late_fee_amt + bt_fee
        pur_bal = pur_bal + pur_int + total_fees
        cash_bal = cash_bal + cash_int
        promo_bal = promo_bal + promo_int

        statement_bal = pur_bal + cash_bal + promo_bal
        min_due = np.where(statement_bal <= 35.0, statement_bal,
                           np.maximum(35.0, statement_bal * 0.01
                                      + pur_int + cash_int + promo_int))
        min_due = np.clip(min_due, 0.0, statement_bal)

        # ---- delinquency intent, then payment ---------------------------
        # The state machine decides first; the payment follows from it. Doing
        # it the other way round lets a delinquent account pay its minimum the
        # next cycle and cure, so nothing ever rolls through to charge-off.
        was_delin = live & (dpd >= 30)

        # Roll probabilities by bucket, close to published US roll rates.
        roll_base = np.select(
            [dpd == 30, dpd == 60, dpd == 90, dpd == 120, dpd == 150],
            [0.30, 0.50, 0.70, 0.88, 0.95], default=0.0)
        roll_p = np.clip(roll_base * (1.20 - 0.45 * discipline), 0.0, 0.92)
        cure_p = (1.0 - roll_p) * (0.68 + 0.28 * discipline)
        u = rng.random(n)
        will_roll = was_delin & (u < roll_p)
        will_cure = was_delin & (u >= roll_p) & (u < roll_p + cure_p)
        will_hold = was_delin & ~will_roll & ~will_cure

        # Hardship suppresses the entry hazard: these customers are in a plan,
        # not simply missing payments.
        haz = true_hazard * np.where(hardship, 0.55, 1.0)
        noise = rng.normal(0, 0.45, n)
        pays_full = live & (dpd == 0) & (statement_bal > 0) & (_logistic(
            np.log(np.clip(pay_full_propensity, 1e-6, 1 - 1e-6)
                   / np.clip(1 - pay_full_propensity, 1e-6, 1)) + noise) > 0.5)
        entering = live & (dpd == 0) & ~pays_full & (rng.random(n) < haz)

        # A revolver pays a SHARE of the statement, not most of it. The balance
        # carried forward is what makes interest income and utilization emerge.
        pay_fraction = np.clip(
            0.012 + 0.10 * discipline - 0.03 * appetite + rng.normal(0, 0.03, n),
            0.01, 0.85)
        normal_pay = np.maximum(min_due, statement_bal * pay_fraction)

        payment = np.where(
            pays_full, statement_bal,
            np.where(entering | will_roll, 0.0,
                     np.where(will_hold, min_due * rng.uniform(0.15, 0.85, n),
                              np.where(will_cure,
                                       np.minimum(min_due * 2.0, statement_bal),
                                       normal_pay))))
        payment = np.clip(np.where(live, payment, 0.0), 0.0, statement_bal)

        # ---- Reg Z 1026.53 allocation -----------------------------------
        # The minimum is applied to the lowest-APR balance; anything above it
        # goes to the highest-APR balance first.
        rates = np.vstack([cash_apr, charged_apr, eff_promo_rate])
        bals = np.vstack([cash_bal, pur_bal, promo_bal])
        pay_left = payment.copy()
        min_part = np.minimum(pay_left, min_due)
        pay_left = pay_left - min_part
        order_low = np.argsort(rates, axis=0)
        for k in range(3):
            j = order_low[k]
            take = np.minimum(bals[j, ai], min_part)
            bals[j, ai] -= take
            min_part -= take
        order_high = np.argsort(-rates, axis=0)
        for k in range(3):
            j = order_high[k]
            take = np.minimum(bals[j, ai], pay_left)
            bals[j, ai] -= take
            pay_left -= take
        cash_bal, pur_bal, promo_bal = bals[0], bals[1], bals[2]

        paid_full_hist[:, c] = pays_full

        # ---- delinquency state transition ---------------------------------
        new_dpd = dpd.copy()
        new_dpd = np.where(entering, 30, new_dpd)
        new_dpd = np.where(will_cure, 0, new_dpd)
        new_dpd = np.where(will_roll, np.minimum(dpd + 30, CHARGE_OFF_DPD), new_dpd)
        dpd = np.where(live, new_dpd, dpd)

        charging_off = live & (dpd >= CHARGE_OFF_DPD)
        bucket = np.select(
            [dpd == 0, dpd == 30, dpd == 60, dpd == 90, dpd == 120, dpd == 150],
            ["Current", "1-29 DPD", "30-59 DPD", "60-89 DPD", "90-119 DPD",
             "120-179 DPD"], default="Charged Off")

        balance = pur_bal + cash_bal + promo_bal
        util = np.divide(balance, np.maximum(limit, 1.0))
        peak_util = np.where(live, np.maximum(peak_util, util), peak_util)

        # ---- emit the cycle row -------------------------------------------
        keep = live
        if keep.any():
            k = np.where(keep)[0]
            rows.append(pd.DataFrame({
                "Masked Customer Number": accounts["Masked Customer Number"].to_numpy()[k],
                "Masked Account Number": accounts["Masked Account Number"].to_numpy()[k],
                "Cycle Month": cycles[c],
                "Cycle Index": c,
                "Product Tier": accounts["Product Tier"].to_numpy()[k],
                "Reward Program Code": accounts["Reward Program Code"].to_numpy()[k],
                "Credit Limit": limit[k],
                "Ending Balance": np.round(balance[k], 2),
                "Average Daily Balance": np.round(
                    np.maximum(balance[k] - 0.4 * spend_hist[k, c], 0), 2),
                "Utilization": np.round(util[k], 4),
                "Purchase Balance": np.round(pur_bal[k], 2),
                "Cash Advance Balance": np.round(cash_bal[k], 2),
                "Promotional Balance": np.round(promo_bal[k], 2),
                "Purchase Interest": np.round(pur_int[k], 2),
                "Cash Advance Interest": np.round(cash_int[k], 2),
                "Promotional Interest": np.round(promo_int[k], 2),
                "Contractual Purchase APR": contract_apr[k],
                "Charged Purchase APR": charged_apr[k],
                "Promotional Rate In Force": np.where(promo_active[k], promo_rate[k], np.nan),
                "Promotional Status": np.where(
                    promo_active[k], "Active",
                    np.where(c >= promo_expiry[k], "Expired", "None")),
                "Promotional Expiry Cycle Index": np.where(
                    has_promo[k], promo_expiry[k], -1),
                "Purchases Authorized": np.round(spend_hist[k, c], 2),
                "Purchases Declined": np.round(declines[k, c], 2),
                "Minimum Payment Due": np.round(min_due[k], 2),
                "Payment Made": np.round(payment[k], 2),
                "Paid In Full Indicator": pays_full[k],
                "Days Past Due": dpd[k],
                "Delinquency Bucket": bucket[k],
                "Annual Fee Charged": np.round(af[k], 2),
                "Late Fee Charged": np.round(late_fee_amt[k], 2),
                "Balance Transfer Fee Charged": np.round(bt_fee[k], 2),
                "Statement Delivery Preference": np.where(
                    lat["digital_fluency"].to_numpy()[k] > 0.45, "electronic", "paper"),
                "First Year Indicator": (c - open_idx[k]) < 12,
                "Hardship Status": hardship[k],
                "Accommodation Plan": cust["Accommodation Plan"].to_numpy()[k],
                "SCRA Flag": scra[k],
                "Charged Off Indicator": charging_off[k],
            }))

        # ---- fee events ---------------------------------------------------
        for code, amt in (("ANNUAL_FEE", af), ("LATE_FEE", late_fee_amt),
                          ("BALANCE_TRANSFER_FEE", bt_fee)):
            m = np.where(amt > 0)[0]
            if len(m):
                fee_events.append(pd.DataFrame({
                    "Masked Account Number": accounts["Masked Account Number"].to_numpy()[m],
                    "Cycle Month": cycles[c],
                    "Fee Code": np.where(
                        code == "LATE_FEE",
                        np.where((c - last_violation_cycle[m]) <= 6,
                                 "LATE_FEE_SUBSEQUENT", "LATE_FEE_FIRST"), code),
                    "Fee Amount Charged": np.round(amt[m], 2),
                }))

        # ---- charge-off ------------------------------------------------
        if charging_off.any():
            k = np.where(charging_off)[0]
            charged_off_at[k] = c
            closed_at[k] = np.minimum(closed_at[k], c + 1)
            attrition_events.append(pd.DataFrame({
                "Masked Account Number": accounts["Masked Account Number"].to_numpy()[k],
                "Closure Cycle Month": cycles[c],
                "Closure Reason": "CHARGE_OFF",
                "Voluntary Closure": False,
                "Balance At Closure": np.round(balance[k], 2),
            }))

        # ---- line review, every sixth cycle ------------------------------
        if c > 0 and c % 6 == 0:
            draws = rng.random(n)
            for i in np.where(live)[0]:
                new_lim, reason = P.line_review(
                    float(limit[i]), float(peak_util[i]), int(months_active[i]),
                    int(dpd[i]), int(score[i]), generosity, use_obs,
                    float(draws[i]))
                if new_lim is not None and abs(new_lim - limit[i]) > 1:
                    limit_events.append({
                        "Masked Account Number": accounts["Masked Account Number"].to_numpy()[i],
                        "Cycle Month": cycles[c],
                        "Old Credit Limit": float(limit[i]),
                        "New Credit Limit": float(new_lim),
                        "Change Direction": "increase" if new_lim > limit[i] else "decrease",
                        "Reason Code": reason,
                        "Customer Requested": False,
                        "Adverse Action Notice Sent": new_lim < limit[i],
                    })
                    limit[i] = new_lim
                    peak_util[i] = 0.0

        # ---- repricing (CARD Act: not in the first year) ------------------
        if repricing_tracks_risk and c > 0 and c % 12 == 0:
            eligible = live & ((c - open_idx) >= 12) & (dpd == 0)
            target = P.contractual_apr(score, accounts["Product Tier"].to_numpy(), rng)
            move = eligible & (np.abs(target - charged_apr) > 2.0) & ~scra
            k = np.where(move)[0]
            for i in k:
                rate_events.append({
                    "Masked Account Number": accounts["Masked Account Number"].to_numpy()[i],
                    "Cycle Month": cycles[c],
                    "Old Purchase APR": float(charged_apr[i]),
                    "New Purchase APR": float(target[i]),
                    "Reason Code": "PERIODIC_RISK_REVIEW",
                    "Notice Sent Cycle Index": c - 2,
                    "Applies To New Transactions Only": True,
                })
            charged_apr[k] = target[k]

        # ---- satisfaction drift and voluntary attrition -------------------
        # Satisfaction responds to what the customer actually experienced.
        experienced = (late_fee_amt > 0).astype(float) * 0.055 \
            + (declines[:, c] > 0).astype(float) * 0.070 \
            + (af > 0).astype(float) * 0.030
        satisfaction = np.clip(
            satisfaction - experienced + rng.normal(0, 0.018, n) + 0.006, 0.02, 0.99)

        rate_gap = np.clip(charged_apr - 18.0, 0, None) / 12.0
        churn_z = (-5.05 - 2.30 * (satisfaction - 0.5) * 2.0
                   + 1.55 * price_sens * rate_gap
                   + 0.65 * (af > 0).astype(float))
        churn = live & (dpd == 0) & (rng.random(n) < _logistic(churn_z)) \
            & (months_active > 6) & (c < n_cyc - 1)
        if churn.any():
            k = np.where(churn)[0]
            closed_at[k] = c + 1
            attrition_events.append(pd.DataFrame({
                "Masked Account Number": accounts["Masked Account Number"].to_numpy()[k],
                "Closure Cycle Month": cycles[c],
                "Closure Reason": np.where(
                    price_sens[k] > 0.6, "RATE_DISSATISFACTION",
                    np.where(annual_fee[k] > 0, "FEE_DISSATISFACTION", "ATTRITION")),
                "Voluntary Closure": True,
                "Balance At Closure": np.round(balance[k], 2),
            }))

    cyc_df = pd.concat(rows, ignore_index=True)
    cyc_df = _derive_account_type(cyc_df)

    out = {
        "cycles": cyc_df,
        "limit_events": pd.DataFrame(limit_events),
        "rate_events": pd.DataFrame(rate_events),
        "attrition_events": pd.concat(attrition_events, ignore_index=True)
        if attrition_events else pd.DataFrame(),
        "fee_events": pd.concat(fee_events, ignore_index=True)
        if fee_events else pd.DataFrame(),
        "closed_at": closed_at,
        "charged_off_at": charged_off_at,
    }
    return out


def _derive_account_type(cyc: pd.DataFrame) -> pd.DataFrame:
    """Revolver / transactor / inactive from TRAILING THREE CYCLES.

    Derived, sticky, and able to migrate when behavior actually changes -
    rather than re-rolled independently each month.
    """
    cyc = cyc.sort_values(["Masked Account Number", "Cycle Index"]).copy()
    g = cyc.groupby("Masked Account Number", sort=False)
    full3 = g["Paid In Full Indicator"].transform(
        lambda s: s.rolling(3, min_periods=1).sum())
    spend3 = g["Purchases Authorized"].transform(
        lambda s: s.rolling(3, min_periods=1).sum())
    bal3 = g["Ending Balance"].transform(
        lambda s: s.rolling(3, min_periods=1).max())
    cyc["Account Type"] = np.where(
        (spend3 < 1.0) & (bal3 < 1.0), "Inactive",
        np.where(full3 >= 2, "Transactor", "Revolver"))
    return cyc
