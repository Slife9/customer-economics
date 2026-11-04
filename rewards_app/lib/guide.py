"""Recommended actions and regulation, summarised from the Reward
Profitability Scenario Model v2 (Segment Definitions, Lever Guide). One source
for the drill-down and the Lever guide page."""

SEGMENT_ACTIONS = {
    "relationship": {
        "why": "The card loses money on its own, but the household is valuable across deposits, lending or wealth.",
        "actions": ["Light touch: merchant-funded offers and redemption steering.",
                    "Prefer relationship pricing over earn cuts; check the full household before any change."],
        "watch": "A card-only P&L understates this customer; attrition also loses the deposit and loan profit.",
    },
    "quasi_cash": {
        "why": "Earns rewards on cash-like or low-interchange payments (wallet loads, money orders, rent, tax, utilities).",
        "actions": ["Stop earning on quasi-cash MCCs (Table25 'no_earn'); reduced earn on low-interchange ones.",
                    "Consider an annual fee for heavy users."],
        "watch": "Some of this spend (utilities, insurance) is ordinary everyday use - disclose exclusions clearly.",
    },
    "bonus_chasers": {
        "why": "Opened for the sign-up bonus, met the spend threshold, then went quiet or closed.",
        "actions": ["Bonus once per product family per 48 months; no bonus after 5+ new cards in 24 months.",
                    "Raise the threshold (e.g. $4,000 in 6 months); claw back if closed within 12 months.",
                    "Product change dormant accounts to a no-fee card."],
        "watch": "Changes apply to future acquisition only - never penalise a bonus already earned.",
    },
    "optimizers": {
        "why": "High spenders who pay in full and concentrate spend where the earn rate exceeds interchange.",
        "actions": ["Cap bonus categories (e.g. 3% up to $1,500 a quarter, then 1%).",
                    "Small base earn cut; an annual fee with offsetting benefits; revolve / installment offers."],
        "watch": "The most sensitive customers to a value cut - check the relationship first.",
    },
    "low_spend": {
        "why": "Long-tenured, regularly active, but spend too small to cover reward and fixed costs.",
        "actions": ["Product change to a non-rewards or flat 1% card, keeping the line and history.",
                    "Redemption steering and minimum redemption thresholds."],
        "watch": "Loyal customers - product change needs notice and fair treatment of points already earned.",
    },
    "unassigned": {
        "why": "Unprofitable, but no reward segment rule matches.",
        "actions": ["Not a rewards lever: diagnose the loss (credit, servicing, fraud) and route to the matching lever.",
                    "On this data most are flat-rate cash-back transactors - a refined rule may be needed."],
        "watch": "A large Unassigned group means the thresholds are too tight for this book.",
    },
}

LEVER_GUIDE = [
    ("Earn-rate reduction", "Cut the ongoing earn rate on future purchases.",
     "e.g. 1.50% to 1.25% base earn, 45+ days after notice; earned rewards unaffected.",
     "Reg Z 12 CFR 1026.9 change-in-terms notice and right to reject; no retroactive devaluation (UDAAP)."),
    ("Quasi-cash / low-interchange exclusions", "Stop or reduce earn on cash-like and low-interchange MCCs.",
     "0 points on 6540, 4829, 6051, 9311; 0.5% on rent processors and utilities.",
     "Disclose excluded categories clearly; change-in-terms notice."),
    ("Bonus-category cap", "Cap bonus earn per period, then a lower base rate.",
     "3% on grocery / gas / dining up to $1,500 a quarter, then 1%.",
     "Clear cap disclosure; change-in-terms notice."),
    ("Redemption steering", "Shift redemptions to lower-cost options; minimum thresholds.",
     "$25 minimum cash redemption; merchandise at 0.7-0.8 cents per point; auto-redeem default.",
     "No misleading redemption design (UDAAP)."),
    ("Annual fee increase", "Add or raise a fee, ideally with offsetting benefits.",
     "$95 fee with a $50 dining credit and anniversary bonus; year 1 waived for $25k+ spenders.",
     "Reg Z notice and right to reject; first-year fee cap of 25% of the line (1026.52)."),
    ("Merchant-funded offers", "Card-linked offers paid for by merchants.",
     "Auto-activated 10% back (up to $15) at 20+ merchants a month.",
     "Merchant agreements; offer terms. No cut in customer-perceived value."),
    ("Product change to non-rewards", "Move to a card that fits the usage, keeping account, line and history.",
     "No-fee 'Everyday' card, 1% flat, APR 2 pp lower; points converted at full value.",
     "Reg Z disclosures; fair treatment of points earned (UDAAP)."),
    ("Revolving balance stimulation", "Balance transfer or installment offers that build interest-bearing balance.",
     "3.99% BT for 12 months, 3% fee, score 700+; 'Plan It' on purchases $250+.",
     "Reg Z promotional-rate disclosures; avoid weakening credit."),
    ("Sign-up bonus controls", "Rules that stop bonuses going to customers who leave right after.",
     "$200 after $4,000 in 6 months; once per 48 months; clawback if closed within 12 months.",
     "Terms disclosed at application; consistent application (fair lending)."),
]

# When each lever pays off. Text only; the months and year-1 shares the
# figures use are in reward_model_assumptions.json (lever_timing), editable.
TIMING_HEADLINE = ("Most reward changes start paying within 2-3 months, once the 45-day notice runs out. "
                   "Fees and balance offers take about a year to reach full value.")

TIMING_DRIVERS = [
    ("Reg Z 45-day notice (12 CFR 1026.9(c))",
     "A significant change to account terms, such as a new or higher annual fee, needs 45 days' written notice "
     "before it takes effect."),
    ("Right to reject (1026.9(h))",
     "The customer can refuse the change and repay on the old terms, so not all customers start paying."),
    ("No fee increase in year one (1026.55)", "Accounts less than a year old must wait."),
    ("Reward programme terms",
     "Reward changes (earn rates, caps, exclusions, redemption rules) are mostly governed by the programme terms "
     "and fair-treatment (UDAAP) expectations, not a Reg Z fixed period. 45 days' notice is the safe design used "
     "here, and earned rewards must not be devalued."),
    ("New offers only",
     "Changes that apply only to new applications or new opt-in offers need no change-in-terms notice; they're "
     "disclosed upfront."),
    ("How the money arrives",
     "Fees are charged at each account's anniversary; reward savings only appear as customers spend or redeem; "
     "promotional interest only arrives after the promo ends."),
]

# (starts earning, full annual value), in LEVERS order
LEVER_TIMING = [
    ("After 45 days' notice plus about 1 month to prepare, so month 2-3. Applies to new purchases only.",
     "From month 3"),
    ("After 45 days' notice and merchant-code setup: month 2-3, on new transactions.", "From month 3"),
    ("After 45 days' notice: month 2-3. Savings show once customers hit the quarterly cap.",
     "From the first full quarter after launch, about month 4-6"),
    ("Promoting cheaper options: immediately. New minimums or changed redemption values: after 45 days' notice.",
     "Builds as points are redeemed, about month 6-9"),
    ("Notice takes 45 days, but the fee is charged on each account's anniversary after that. Accounts under 1 "
     "year old must wait. Customers can reject.",
     "Only once every account has passed an anniversary: about month 14"),
    ("No customer notice, but merchant agreements and the offers platform take about 3-6 months.",
     "From about month 6"),
    ("An opt-in offer is effective when the customer accepts (campaign month 1-3). A bank-initiated change needs "
     "45 days' notice.", "From about month 4"),
    ("New offers, so month 1. The balance-transfer fee is earned straight away.",
     "After the 12-month promotional rate ends, about month 13+, when the full APR applies"),
    ("New applications only, effective as soon as the new terms are published (month 1). Savings come when "
     "bonuses would have been paid, 3-6 months after opening.", "Builds as new accounts open, about month 12-18"),
]

TIMELINE = [
    ("Months 1-3", "Sign-up bonus controls, balance-transfer offers, product-change offers, redemption steering "
                   "(promotion only)"),
    ("Months 3-6", "Earn-rate reduction, quasi-cash exclusions, bonus-category caps"),
    ("Months 6-12", "Merchant-funded offers; the redemption rule changes paying off"),
    ("Month 12+", "Annual fee increases (at anniversaries) and the interest from balance offers reach full value"),
]

GUARDRAILS = [
    "Reg Z / CARD Act: 45-day change-in-terms notice and right to reject (12 CFR 1026.9); limits on APR "
    "increases on existing balances (1026.55); first-year fee cap of 25% of the line (1026.52).",
    "UDAAP: no retroactive devaluation or forfeiture of earned rewards; disclose caps and exclusions clearly.",
    "Fair lending (ECOA / Reg B): test segment treatments for disparate impact; apply criteria consistently.",
    "Co-brand contracts may require partner approval for reward changes.",
    "Test every change on a random 10-20% of a segment (champion / challenger) before full rollout.",
]
