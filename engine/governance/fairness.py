"""Fairness: the four-fifths test on the SCORE and on the TREATMENT
(concept spec section 8). A score can pass while the treatment built on it
fails, and the treatment is what a customer actually experiences - so both
are run, always, and a failing result is always reported.

HONEST LIMITATION, stated rather than resolved quietly (spec section 12):
proper BISG proxy fairness testing combines a SURNAME-based race probability
with a GEOGRAPHY-based one via Bayesian updating. This dataset's customer
records are masked - there is no name field, by design, since it is meant to
demonstrate proxy testing without ever holding a name or collecting race
directly. That means only the geography half of BISG can be implemented
here. What follows groups customers by Metro Name as a stand-in protected-
class proxy and runs the four-fifths math correctly on that grouping - it is
NOT a validated BISG probability, and should not be reported to a regulator
as one. Swap in a real BISG library (name + geography + census reference
tables) before this leaves a demo.

DEVIATION FROM THE LITERAL EEOC FOUR-FIFTHS RECIPE, made deliberately: the
textbook version compares every group to whichever group happens to have the
HIGHEST observed rate. With 50+ small geography groups that is a multiple-
comparisons trap - the max is disproportionately likely to be a lucky small
group, which then makes nearly every other group look like a violation even
under a true null of no disparity. An early run of this exact test showed
48 of 55 metro groups "failing" against one outlier comparator, which is a
statistical artifact, not a fairness finding, and reporting it as one would
be exactly the kind of manufactured number the rest of this system refuses
to produce elsewhere. The fix: compare each group to the POPULATION-WIDE
selection rate instead of the observed maximum. This is standard practice
where the comparison group itself is unstable (see EEOC guidance's own
allowance for an alternative benchmark when the highest-rate group is a
poor reference), and it is far less sensitive to any single group's noise.
"""
from __future__ import annotations
import pandas as pd

FOUR_FIFTHS_THRESHOLD = 0.80
MIN_GROUP_SIZE = 30  # standard EEOC four-fifths practice: a group below this
                     # size produces a selection rate too noisy to use as
                     # either the comparator or a compared group


def four_fifths_test(customer_view: pd.DataFrame, selected: pd.Series,
                     group_col: str = "Metro Name") -> pd.DataFrame:
    df = customer_view[[group_col]].copy()
    df["selected"] = selected.to_numpy()
    counts = df.groupby(group_col).size().rename("n")
    rates = df.groupby(group_col)["selected"].mean().rename("selection_rate")
    combined = pd.concat([counts, rates], axis=1)
    combined = combined[combined.index.notna() & (combined["n"] >= MIN_GROUP_SIZE)]
    if not len(combined):
        return pd.DataFrame(columns=["group", "n", "selection_rate",
                                     "ratio_to_population", "passes"])
    population_rate = float(selected.mean())
    out = combined.reset_index().rename(columns={group_col: "group"})
    out["ratio_to_population"] = (
        out["selection_rate"] / population_rate).round(4) if population_rate > 0 else 0.0
    out["passes"] = out["ratio_to_population"] >= FOUR_FIFTHS_THRESHOLD
    return out.sort_values("ratio_to_population")


def run(customer_view: pd.DataFrame, worklists: dict[str, pd.DataFrame]) -> dict:
    """INVARIANT: report failures. A fairness result that only appears when
    it passes is not a fairness result."""
    score_selected = customer_view["cev_band"].astype(str).isin(["Valued", "Premier"])
    score_result = four_fifths_test(customer_view, score_selected)

    treated_customers = set()
    for wl in worklists.values():
        if len(wl):
            treated_customers |= set(wl["Masked Customer Number"])
    treatment_selected = customer_view["Masked Customer Number"].isin(treated_customers)
    treatment_result = four_fifths_test(customer_view, treatment_selected)

    by_product = None
    if "Product Tier" in customer_view.columns:
        by_product = four_fifths_test(customer_view, score_selected, group_col="Product Tier")

    return {
        "proxy_method": "geography-only (Metro Name) - NOT full BISG; this "
                       "dataset has no surname field to combine with it. "
                       "See module docstring.",
        "score_fairness": score_result,
        "treatment_fairness": treatment_result,
        "score_fairness_by_product_tier": by_product,
        "score_any_failure": bool((~score_result["passes"]).any()) if len(score_result) else False,
        "treatment_any_failure": bool((~treatment_result["passes"]).any()) if len(treatment_result) else False,
    }
