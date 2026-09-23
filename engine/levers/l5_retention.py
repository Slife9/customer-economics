"""L5 - Retention targeting. Spend the retention budget by worth, not by
balance or tenure.

Population uses only OBSERVABLE warning signals - a recent closure-request
contact, a meaningful spend decline, or a price position well above peers -
never a latent trait the engine cannot see anyway. Sizing always returns
None: retention uplift from an intervention is a causal question about a
treatment never applied (concept spec section 7). What IS reported is value
at risk - the trailing-12-month profit these customers represent - which is
a fact about today, not a prediction about tomorrow.
"""
from __future__ import annotations
import pandas as pd

from .base import Lever, SizeResult

SPEND_DECLINE_THRESHOLD = 0.30
HIGH_VALUE_BANDS = {"Valued", "Premier"}
RATE_ABOVE_PEER_POINTS = 2.0


class L5Retention(Lever):
    code = "L5"
    name = "Retention targeting"
    gates = []

    def __init__(self, drivers: pd.DataFrame, spend_decline: pd.DataFrame):
        """`spend_decline` is a (Masked Customer Number, spend_declined) frame
        the orchestrator precomputes from Table5_Transaction - trailing 3
        months vs. the prior 3, an observable trend, not a latent."""
        self.drivers = drivers
        self.spend_decline = spend_decline

    def population(self, pop) -> pd.DataFrame:
        pop = super().population(pop)
        cv = pop.frame
        high_value = cv["cev_band"].astype(str).isin(HIGH_VALUE_BANDS)

        closure_signal = (self.drivers.groupby("Masked Customer Number")["Primary Call Reason"]
                          .apply(lambda s: (s == "closure_request").any())
                          .rename("closure_request_signal"))
        cv = cv.merge(closure_signal, on="Masked Customer Number", how="left")
        cv["closure_request_signal"] = cv["closure_request_signal"].fillna(False)
        cv = cv.merge(self.spend_decline, on="Masked Customer Number", how="left")
        cv["spend_declined"] = cv["spend_declined"].fillna(False)

        peer_apr = cv.groupby("Credit Score Band")["latest_charged_apr"].transform("median")
        priced_above_peer = (cv["latest_charged_apr"] - peer_apr) >= RATE_ABOVE_PEER_POINTS

        at_risk = high_value & (cv["closure_request_signal"] | cv["spend_declined"]
                                | priced_above_peer)
        out = cv[at_risk].copy()
        out["risk_signals"] = out.apply(lambda r: ", ".join(filter(None, [
            "closure_request_contact" if r["closure_request_signal"] else "",
            "spend_declining" if r["spend_declined"] else "",
            "priced_above_peer" if (r["latest_charged_apr"]
                                    - peer_apr.get(r.name, 0)) >= RATE_ABOVE_PEER_POINTS else "",
        ])), axis=1)
        return out

    def size(self, population: pd.DataFrame) -> SizeResult:
        value_at_risk = float(population["trailing_12m_net_economic_profit"].sum())
        return SizeResult(
            priced_value_usd=None,
            basis="retention uplift from an intervention is a causal response "
                 "to a treatment never applied (concept spec section 7) - not "
                 "derivable from historical data",
            unpriced_context_usd=round(value_at_risk, 2),
            caveat=f"${value_at_risk:,.0f} is the trailing-12-month value these "
                   f"{len(population)} customers represent if nothing changes - "
                   f"value AT RISK, not value recoverable. Actual retention "
                   f"uplift requires a champion/challenger pilot.")

    def worklist(self, population: pd.DataFrame) -> pd.DataFrame:
        wl = population.copy()
        wl["action"] = "RETENTION_OUTREACH"
        wl["reason"] = wl["risk_signals"]
        return wl[["Masked Customer Number", "action", "reason",
                  "trailing_12m_net_economic_profit", "cev_band"]].rename(
            columns={"trailing_12m_net_economic_profit": "value_at_risk_usd"})

    def driver(self, customer_view: pd.DataFrame) -> float:
        """No mechanism in this dataset targets retention directly - this
        exists so the negative control gate can correctly report L5 as
        inconclusive rather than fabricate a pass."""
        raise NotImplementedError(
            "L5 has no driver: retention is not a mechanism this dataset's "
            "negative control varies. The gate should report L5 inconclusive.")
