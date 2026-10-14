"""Verification script for the redesigned Executive Overview and Portfolio
Economics pages (Part J). Run as a script, like the other files in this
directory - there is no pytest suite in this repo to join.

    python audit/audit_executive_pages.py
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.core.contract import load_portfolio  # noqa: E402
from engine.core import ledger as LEDGER  # noqa: E402
from engine.core import customer_view as CV  # noqa: E402
from engine.core import suppression as SUPP  # noqa: E402
from engine.core import routing as ROUTING  # noqa: E402
from app.lib import charts as C  # noqa: E402

DEMO_DIR = ROOT / "generator" / "out" / "demo"
TOL = 1e-6


def sec(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


sec("Load demo portfolio and build the pipeline's own intermediate stages")
portfolio = load_portfolio(DEMO_DIR)
led = LEDGER.build(portfolio)
cv = CV.build(led, portfolio)
suppressed_pop = SUPP.run(cv)
routed_pop = ROUTING.route(suppressed_pop)
cv = routed_pop.frame
routing_tbl = ROUTING.routing_summary(routed_pop)
# The pages restrict result["ledger"]["card"] to cv's own (post-suppression)
# customers before using it - see the comment at the top of both Home.py
# and 10_Portfolio_Economics.py. Mirror that restriction here so this
# reconciliation checks what the pages actually show.
card_led = led["card"]
card_led = card_led[card_led["Masked Customer Number"].isin(cv["Masked Customer Number"])]
print(f"  {len(cv):,} customers, {card_led['Cycle Month'].nunique()} monthly cycles")

sec("T-NEP-RECON: Home page's headline NEP reconciles to an independent "
   "ledger-level total")
page_total_nep = cv["trailing_12m_net_economic_profit"].sum()
window = sorted(card_led["Cycle Month"].unique())[-12:]
ledger_total_nep = (card_led[card_led["Cycle Month"].isin(window)]["net_economic_profit"].sum()
                   + cv["deposit_net_12m"].sum() + cv["loan_net_12m"].sum())
assert abs(page_total_nep - ledger_total_nep) < max(abs(ledger_total_nep) * 1e-9, TOL), \
    "customer_view's own trailing-12mo NEP total must equal the ledger's, summed independently"
print(f"  PASS  cv total (${page_total_nep:,.0f}) == ledger-rebuilt total (${ledger_total_nep:,.0f})")

sec("T-CARD-NET-RECON: per-customer card_net equals the card ledger's own "
   "trailing-12mo net_economic_profit for that customer")
sample_ids = cv["Masked Customer Number"].sample(min(25, len(cv)), random_state=0)
for cust in sample_ids:
    expected = card_led[(card_led["Masked Customer Number"] == cust)
                       & (card_led["Cycle Month"].isin(window))]["net_economic_profit"].sum()
    actual = cv.loc[cv["Masked Customer Number"] == cust, "card_net"].iloc[0]
    assert abs(expected - actual) < TOL, f"{cust}: card_net mismatch ({actual} vs {expected})"
print(f"  PASS  card_net matches a fresh ledger recomputation for {len(sample_ids)} sampled customers")

sec("T-COMPONENT-SUM: card + deposit + loan nets sum to trailing-12mo NEP, per customer")
recon = (cv["card_net"] + cv["deposit_net_12m"] + cv["loan_net_12m"]
        - cv["trailing_12m_net_economic_profit"]).abs()
assert (recon < TOL).all(), "the three product nets must sum exactly to the headline NEP"
print(f"  PASS  all {len(cv):,} customers reconcile")

sec("T-BELOW-COST: below-cost count and total loss reconcile against a fresh computation")
fresh_below_cost = cv["trailing_12m_net_economic_profit"] < 0
assert (fresh_below_cost == cv["is_below_cost"]).all(), \
    "is_below_cost must exactly match a fresh NEP<0 computation"
fresh_total_loss = -cv.loc[fresh_below_cost, "trailing_12m_net_economic_profit"].sum()
page_total_loss = -cv.loc[cv["is_below_cost"], "trailing_12m_net_economic_profit"].sum()
assert abs(fresh_total_loss - page_total_loss) < TOL
print(f"  PASS  {int(fresh_below_cost.sum()):,} below-cost customers, "
     f"${page_total_loss:,.0f} total loss, both independently reconciled")

sec("T-ROUTING-RECON: routing_summary's customer counts sum to the below-cost population")
routed_total = int(routing_tbl["customers"].sum())
below_cost_n = int(cv["is_below_cost"].sum())
assert routed_total == below_cost_n, \
    f"routing_summary covers {routed_total} customers, below-cost population is {below_cost_n}"
print(f"  PASS  routing_summary customers ({routed_total:,}) == below-cost population ({below_cost_n:,})")

sec("T-PRODUCT-MIX: holds_card + holds_deposit + holds_loan sums reconcile "
   "against the products_held distribution")
sum_of_flags = int(cv["holds_card"].sum() + cv["holds_deposit"].sum() + cv["holds_loan"].sum())
sum_of_products_held = int(cv["products_held"].sum())
assert sum_of_flags == sum_of_products_held, \
    "the three per-product flags must sum to exactly the products_held total"
print(f"  PASS  sum of holds_* flags ({sum_of_flags:,}) == sum of products_held ({sum_of_products_held:,})")

sec("T-OWNERSHIP-NEP: the new product-ownership-vs-NEP chart's group sums "
   "reconcile to the portfolio total")
own = cv.groupby("products_held")["trailing_12m_net_economic_profit"].sum()
assert abs(own.sum() - page_total_nep) < max(abs(page_total_nep) * 1e-9, TOL), \
    "grouping by products_held must not drop or double-count any customer's NEP"
print(f"  PASS  sum across products-held groups (${own.sum():,.0f}) == portfolio total (${page_total_nep:,.0f})")

sec("T-DRILLDOWN: a sampled customer's reused waterfall chart total matches "
   "their own card_net in customer_view")
checked = 0
for cust in sample_ids:
    # Mirror the page: restrict to the PORTFOLIO's trailing window, not this
    # customer's own last-12-reporting-months (a churned/closed account's
    # own last 12 months can predate the portfolio's current window).
    cust_led = card_led[(card_led["Masked Customer Number"] == cust)
                       & (card_led["Cycle Month"].isin(window))]
    if not len(cust_led):
        continue
    fig = C.revenue_cost_waterfall(cust_led)
    chart_net = fig.data[0]["y"][-1]
    expected = cv.loc[cv["Masked Customer Number"] == cust, "card_net"].iloc[0]
    assert abs(chart_net - expected) < TOL, \
        f"{cust}: drill-down waterfall net ({chart_net}) != card_net ({expected})"
    checked += 1
assert checked > 0, "no sampled customer had card ledger history to check"
print(f"  PASS  drill-down waterfall net matches cv['card_net'] for {checked} sampled customers")

sec("ALL CHECKS PASSED")
