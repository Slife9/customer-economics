"""The words of the app, in one place: plain-language names, the report's
definitions, assumptions and reasons, the four strategies, the rules, risks
and the implementation plan (revision E: the project report and the
stakeholder slides are the reference for structure and wording).

Every number in a sentence is formatted from the configuration (passed in as
`cfg`), never written here. All regulatory text is a summary for discussion,
to be confirmed by compliance.
"""

COMPLIANCE_NOTE = "Summaries for discussion; to be confirmed by the bank's compliance team."

# ---------------------------------------------------------------- plain names
# Executive view names (the report's); the analyst view uses config segments.labels.
PLAIN_SEGMENTS = {
    "deteriorating": "Customers at rising risk",
    "relationship": "Relationship customers",
    "dormant": "Unused cards",
    "sock_drawer": "Occasional users",
    "transactors": "Pay-in-full customers",
    "unassigned": "Other",
}


def group_rule(key: str, cfg: dict) -> str:
    """The rule a card must meet to join a group, as the report states it."""
    r = cfg["segments"]["rules"]
    d, rel, dor, so, tr = r["deteriorating"], r["relationship"], r["dormant"], r["sock_drawer"], r["transactors"]
    return {
        "deteriorating": f"Chance of default in the next year {d['pd_annual_min']:.0%} or more, OR credit score down "
                         f"{d['score_drop_6m_min']:.0f}+ points in 6 months",
        "relationship": f"Other products earn ${rel['noncard_profit_min_usd']:,.0f}+ a year, OR deposits of "
                        f"${rel['deposits_plus_investments_min_usd']:,.0f}+, OR a "
                        + " / ".join(rel["premium_segments"]) + " client",
        "dormant": f"No transaction for {dor['inactive_months_min']:.0f}+ months AND no balance all year",
        "sock_drawer": f"Active {so['active_months_max']:.0f} months a year or less AND spend under "
                       f"${so['spend_max_usd']:,.0f} a year",
        "transactors": f"Pay in full (or owe nothing) {tr['paid_in_full_months_min']:.0f}+ months of 12, AND busiest "
                       f"month under {tr['peak_utilisation_max']:.0%} of the limit, AND spend "
                       f"${tr['spend_min_usd']:,.0f}+ a year",
        "unassigned": "Lose money but meet none of the rules above",
    }[key]


def selection_tests(cfg: dict) -> list[tuple[str, str]]:
    """The six tests every selected card meets (key in segments.SCREEN_LABELS, text)."""
    sc = cfg["screen"]
    basis = ("at statement date, before the customer's payment" if cfg["balance_basis"]["screen"] == "statement_date"
             else "after the customer's payment")
    return [("screen.unprofitable", "It loses money after all costs, including the new capital and liquidity costs."),
            ("screen.utilisation", f"The customer uses under {sc['max_utilisation']:.0%} of the limit on average "
                                   f"({basis})."),
            ("screen.unused", f"At least ${sc['min_unused_usd']:,.0f} of the limit is unused."),
            ("screen.history", f"The card has been open at least {sc['min_history_months']:.0f} months."),
            ("screen.open", "It is open and not charged off."),
            ("screen.not_fraud_blocked", "It has no recent fraud-related card event.")]


# key: (analyst label, executive label, one-line definition shown on hover)
TERMS = {
    "screened": ("Screened accounts", "Cards selected",
                 "Open cards that lose money, use under 30% of the limit and have at least $5,000 unused."),
    "card_profit": ("Card profit under the assumed capital rules", "Card profit",
                    "The card's profit after all costs, with today's capital charge replaced by the assumed rules' "
                    "and the liquidity cost subtracted."),
    "unused": ("Unused line (UCL)", "Unused credit", "Credit limit minus balance: credit the customer could still borrow."),
    "carrying": ("Carrying cost", "Cost to hold", "Capital cost plus liquidity cost of keeping an unused line open."),
    "drawdown": ("Expected drawdown loss", "Expected drawdown loss",
                 "Expected loss from customers using their unused line just before defaulting."),
    "unused_cost": ("Total unused-line cost", "Total cost of unused lines", "Cost to hold plus expected drawdown loss."),
    "headline": ("Annual value", "Annual value",
                 "Change in card profit plus the reduction in expected drawdown loss, per year."),
    "capital": ("Capital released (one-time)", "Capital freed (one time)",
                "Capital no longer needed after the actions: a one-time amount, never added to the annual value."),
    "leaving": ("Accounts leaving (expected)", "Customers expected to leave",
                "Expected number of customers who close the card after an action."),
}

KEY_TERMS = [
    ("Unused (undrawn) line", "Credit limit minus balance: credit the customer could still borrow"),
    ("Carrying cost", "Capital cost plus liquidity cost of keeping an unused line open"),
    ("Drawdown risk", "Expected loss from customers using their unused line just before defaulting"),
    ("Risk weight", "How risky the regulator treats an exposure: 45% for transactors, 75% otherwise"),
    ("Transactor", "A customer who paid in full at every due date for the past 12 months"),
    ("Conversion factor (CCF)", "Share of an unused line counted as exposure for capital: 10% under the assumed rules"),
    ("Negative carry", "The gap between the cost of funding liquid assets and what they earn"),
    ("Adverse action", "A decision unfavourable to the customer that requires a notice with reasons (Reg B)"),
    ("Holdout", "A random group that receives no action, used to measure each strategy's true effect"),
    ("Four-fifths test", "A fairness screen: a group selected at under 80% of the comparison rate is flagged"),
]


# ---------------------------------------------------------- assumptions
def assumptions_table(cfg: dict) -> list[tuple[str, str, str, str]]:
    """(value, used for, type, why we use it), as in the report."""
    cap, liq, sb = cfg["capital"], cfg["liquidity"], cfg["balance_basis"]
    leq = cfg["drawdown_risk"]["leq_by_segment"]
    basis = {"midpoint": "the average of the statement-date and after-payment balance",
             "after_payment": "the balance after the month's payment"}[sb["cost"]]
    return [
        (f"Unused line = limit − balance ({basis}), 12-month average", "All costs", "Measured / derived",
         "Standard definition of undrawn credit; the average smooths seasonal swings. Actions are valued on today's "
         "unused line"),
        (f"{cap['ccf_unused_card_lines']:.0%} of the unused line counted as exposure", "Capital", "Regulatory (assumed)",
         "March 2026 Basel III endgame proposal, treated as adopted"),
        (f"Risk weight {cap['risk_weight_transactor']:.0%} / {cap['risk_weight_non_transactor']:.0%} "
         f"({cap['risk_weight_non_qualifying_retail']:.0%} above ${cap['regulatory_retail_aggregate_limit_usd'] / 1e6:,.0f}M "
         "of total exposure)", "Capital", "Regulatory (assumed)",
         f"{cap['risk_weight_transactor']:.0%} if paid in full at every due date for 12 months; "
         f"{cap['risk_weight_non_transactor']:.0%} otherwise, including dormant cards, which have no repayment history"),
        (f"Capital ratio {cap['capital_ratio']:.1%}", "Capital", "Business",
         "Basel 8% minimum plus the 2.5% capital conservation buffer"),
        (f"Cost of equity {cap['cost_of_equity']:.0%}", "Capital", "Business",
         "Typical return bank shareholders expect; finance to confirm"),
        (f"{liq['lcr_outflow_unused_card_lines']:.0%} of the unused line held in liquid assets", "Liquidity",
         "Regulatory (conservative)", "The liquidity rule's outflow rate for committed retail lines, applied to all "
                                      "unused card lines for prudence"),
        (f"Negative carry {liq['negative_carry']:.2%}", "Liquidity", "Business",
         "Funding cost minus the lower yield on safe, liquid assets"),
        ("Chance of default in a year", "Drawdown", "Measured",
         "The account's own 12-month default probability (its group's average if missing)"),
        ("Loss if the customer defaults", "Drawdown", "Measured",
         f"The account's own loss rate (portfolio average of {cfg['workbook']['portfolio']['lgd']:.0%} if missing)"),
        ("Share of the unused line drawn before default", "Drawdown", "Workbook estimate",
         "From the reference model by customer group: " + ", ".join(
             f"{PLAIN_SEGMENTS[k].lower()} {leq[k]:.0%}" for k in ["deteriorating", "sock_drawer", "dormant",
                                                                   "transactors", "relationship"])
         + "; other cards use the portfolio average"),
    ]


def current_law(cfg: dict) -> list[tuple[str, str, str]]:
    cap, cr, liq = cfg["capital"], cfg["current_rules_comparison"], cfg["liquidity"]
    return [
        ("Capital on unused card lines", f"{cr['ccf_unconditionally_cancellable']:.0%} conversion factor, so no "
         "risk-based capital", f"{cap['ccf_unused_card_lines']:.0%} for every card line, every bank"),
        ("Status of the March 2026 proposal", "Published, not final", "Treated as adopted from day one"),
        ("Liquidity on cancellable card lines", "No outflow (not \"committed\" facilities)",
         f"{liq['lcr_outflow_unused_card_lines']:.0%} on all unused card lines, Category I–III banks by default"),
        ("Leverage ratio (SLR)", "Applies to Category I–III banks",
         "Not calculated; risk-based capital assumed to be the binding constraint"),
    ]


# ---------------------------------------------------------- strategies
def strategy_text(key: str, cfg: dict) -> dict:
    """What, who (Base case), why, for one strategy, from the report."""
    lv = cfg["workbook"]["levers"]["base"]
    sm = cfg["levers"]["system_mode"]
    dt = sm["decrease_target"]
    wn = cfg["warning"]
    sh = wn["response_shares"]
    reset = (f"at least ${wn['min_spend_to_reset_usd']:,.0f} of spend in the {wn['notice_days']} days"
             if wn["min_use_to_reset"] == "min_spend" else "one transaction")
    return {
        "right_size": {
            "what": "Reduce limits that are far larger than the customer needs or their risk justifies.",
            "who": [f"Customers at rising risk: {lv['decrease_share']['deteriorating']:.0%} of them, highest chance "
                    f"of default first; limit towards current balance + {dt['deteriorating']['multiple'] - 1:.0%}.",
                    f"Occasional users: {lv['decrease_share']['sock_drawer']:.0%} of them, largest unused line first; "
                    f"limit towards {dt['sock_drawer']['multiple']:g} times their highest monthly statement balance.",
                    f"Relationship customers: {lv['decrease_share']['relationship']:.0%} of them, with a smaller cut."],
            "why": "Less unused credit leaves less to draw before a default, the largest cost, and lowers capital and "
                   "liquidity cost. Rising-risk customers come first: they carry almost half the drawdown risk.",
            "short_who": "Customers at rising risk · occasional users · a few relationship customers",
        },
        "re_engage": {
            "what": "Offers that encourage customers to use the card more, such as a spend incentive.",
            "who": [f"{lv['campaign_share']['sock_drawer']:.0%} of occasional users, "
                    f"{lv['campaign_share']['transactors']:.0%} of pay-in-full customers and "
                    f"{lv['campaign_share']['relationship']:.0%} of relationship customers, chosen at random within "
                    "each group.",
                    f"Costs counted: the contact cost per customer, a ${cfg['workbook']['portfolio']['incentive_per_responder']:,.0f} "
                    "incentive for responders, and a promotional cost on any new balance."],
            "why": "A customer who uses the card again brings interchange and sometimes interest. At today's offer "
                   "costs the campaign costs more than it earns, so it is tested in the pilot with cheaper, "
                   "better-targeted offers and scaled only if it pays.",
            "short_who": "Occasional users · pay-in-full customers · relationship customers",
        },
        "use_it_or_lose_it": {
            "what": "A four-step journey for unused cards: invite, warn with a choice, act, don't reissue.",
            "who": [f"Invite: a reactivation offer ({lv['campaign_share']['dormant']:.0%} of unused cards in the Base case).",
                    f"Warn with a choice: {wn['notice_days']} days' notice that the limit will be lowered or the card "
                    "closed if it stays unused; the customer can keep using it, keep a lower limit, or close it. "
                    f"Use that resets the clock: {reset}. Never a fee.",
                    f"Act: for cards still unused, right-size the line, or close it if unused for "
                    f"{sm['closure_min_inactive_months']}+ months (longest inactive first).",
                    "Don't reissue: let dormant cards that expire within the year lapse, saving the reissue cost."],
            "why": "Dormant cards earn nothing but carry cost and drawdown risk. The warning makes the process fair "
                   "and transparent: customers who value the card come back, and the rest leave without surprise.",
            "short_who": "Unused cards",
            "warning": [(f"Resume use (spend {reset})", sh["resume_use"]),
                        ("Accept a lower limit", sh["accept_lower_limit"]),
                        ("Close voluntarily", sh["close_voluntarily"]),
                        ("No response: the planned action goes ahead", 1 - sum(sh.values()))],
        },
        "stop_auto_increases": {
            "what": "Switch off the bank's proactive limit increases for selected customers who received one in the "
                    "past year. Customers can still ask, with the normal ability-to-pay check.",
            "who": ["Any selected card that received an automatic increase in the past 12 months.",
                    "Valued from the bank's own history of automatic increases (the same amount avoided next year): "
                    "assumption-based, not in the reference model."],
            "why": "Each automatic increase adds unused credit, cost and drawdown risk to customers who already use "
                   "little of their limit. The simplest strategy to start: a rule change with no customer contact.",
            "short_who": "Any selected card that received an automatic increase",
        },
    }[key]


def safeguards(cfg: dict) -> list[tuple[str, str]]:
    sm = cfg["levers"]["system_mode"]
    tc = cfg["treatment"]
    return [
        ("Gradual cuts", f"at most {cfg['levers']['max_reduction_per_review']:.0%} of the limit per review "
                         f"({sm['reviews_in_year_one']} review in year one); a cut only if it is at least "
                         f"{sm['min_cut_share']:.0%} and ${sm['min_cut_usd']:,.0f}"),
        ("Floors", f"never below ${sm['floor_minimum_line_usd']:,.0f} or {sm['floor_balance_multiple']:g} times the balance"),
        ("A recorded reason", "for every action, which decides the notice: inactivity, credit deterioration, idle-line "
                              "right-sizing, engagement campaign, or suppressing an automatic increase"),
        ("Notices", "credit-based cuts: adverse-action notice within 30 days; inactivity-based actions generally none"),
        ("No penalties", f"no over-limit fees or penalty rates on the lower limit for "
                         f"{tc['fee_restriction_days_after_decrease']} days"),
        ("A fair warning", f"{cfg['warning']['notice_days']} days' notice with a choice before any dormant-card action; "
                           "never a fee"),
        ("Reinstatement", "customers can ask for their limit back"),
        ("Protected customers", "hardship and SCRA customers are excluded from every action"),
    ]


RULES = [
    ("Limit cut or closure for credit reasons", "Adverse-action notice within 30 days, with specific reasons or the "
     "right to request them", "Reg B, 12 CFR 1002.2(c), 1002.9"),
    ("Limit cut or closure because of inactivity", "Generally not an adverse action, if genuinely made because of "
     "inactivity", "Reg B, 12 CFR 1002.2(c)(2)(ii)"),
    ("Credit score used in a cut", "Score disclosure if the FCRA adverse-action conditions are met and a bureau-based "
     "score was used", "FCRA §615"),
    ("After any cut", "No over-limit fee or penalty rate based on the lower limit until 45 days after notice",
     "Reg Z, 12 CFR 1026.9(c)(2)(vi), (g)(4)"),
    ("Inactive accounts", "Inactivity penalty fees are prohibited, so the consequence is a lower limit or closure, "
     "never a fee", "Reg Z, 12 CFR 1026.52(b)"),
    ("Any limit increase", "Ability-to-pay assessment", "Reg Z, 12 CFR 1026.51"),
    ("\"Use it or lose it\" warning letter", "Must describe exactly what will happen and when, and the bank must do "
     "what it said", "UDAAP"),
]


def risks(fail_text: str, s2_value: str) -> list[tuple[str, str, str]]:
    return [
        ("Fairness", f"Cuts and closures {fail_text}", "Fair-lending review before any contact; re-test every cycle"),
        ("Rules assumed", "Capital and liquidity costs assume the March 2026 proposal is adopted",
         "Most of the value is drawdown risk, which applies under any rules"),
        ("Estimates", "Customer reactions, warning responses and drawdown shares come from the reference model or "
                      "are assumed", "Pilot with a holdout measures them; measured results replace the estimates"),
        ("Strategy 2", f"Re-engagement loses money at today's offer costs ({s2_value})",
         "Test cheaper, targeted offers; scale only if it pays"),
        ("Value basis", "Approved actions are slightly negative on card profit alone",
         "Report value as profit change plus risk reduced, stated clearly"),
        ("Synthetic data", "Figures come from a synthetic stress book tuned to the reference model",
         "Run the system on the bank's own data before final decisions"),
    ]


def pending_corrections(cfg: dict, fixed_cost_per_card: float) -> list[tuple[str, str, str]]:
    """(item, status in the system, what may still change)."""
    dr = cfg["drawdown_risk"]["leq_source"]
    return [
        ("Measured drawdown share", "Built as a setting; the workbook estimate stays the default"
         if dr == "workbook_segment" else "In use (account values)",
         "The synthetic data's account value has only two levels; a run on the bank's own data can replace the "
         "estimate. The most influential input: it could move the value either way"),
        ("Missing default probabilities", "Done: the group's average, never zero", "None selected today"),
        ("Balance measurement", "Done: statement date for the selection, the midpoint for costs, today's line for "
                                "actions", "Re-run on the bank's own data"),
        ("Specific reason codes", "Done: one code per action, each with its notice rule", "Compliance to confirm"),
        ("90-day warning step", "Modelled; response shares are assumptions", "Measured in the pilot"),
        ("Fixed costs", f"Setting available; the engine allocates about ${fixed_cost_per_card:,.0f} per selected card "
                        "against $30–60 in the reference model", "Finance to confirm the right allocation"),
    ]


WHAT_IS_NEEDED = [
    "Approve a pilot with a {holdout:.0%} holdout in each customer group.",
    "Decide on the dormant-card actions (Strategy 3: right-size, close, don't reissue).",
    "Commission a fair-lending review before any customer is contacted.",
    "Finance to confirm the capital ratio, cost of equity and liquidity carry.",
]

PREPARE = [
    "Fair-lending review of who would receive cuts and closures.",
    "Compliance sign-off on reason codes, notices and the \"use it or lose it\" wording.",
    "Finance confirms the capital ratio, cost of equity and liquidity carry.",
    "Ideally, a run on the bank's own data (including a measured drawdown share).",
]

PILOT = [
    "A random {holdout:.0%} holdout in each customer group receives no action, so each strategy's true effect can be "
    "measured.",
    "Six months of treatment, with follow-up on losses.",
    "Success means: lower drawdowns and losses than the holdout, closures and complaints within agreed limits, no "
    "fairness failures, and value per account at or above the Base estimate.",
]

ROLES = [
    ("Credit Risk", "Owns limit policy, approves reductions, updates the automatic-increase rules"),
    ("Compliance & Legal", "Signs off reason codes, notices, the warning wording and the fair-lending review"),
    ("Operations", "Issues notices and warning letters, applies limit changes, handles reinstatement requests"),
    ("Marketing", "Designs and runs the reactivation and re-engagement offers"),
    ("Finance", "Confirms the capital and liquidity assumptions; tracks capital freed"),
    ("Analytics", "Runs the system, selects pilot and holdout groups, measures results"),
]

MEASURES = [
    ("Unused credit on treated accounts", "Whether exposure is falling", "Holdout"),
    ("Drawdowns before default", "Whether the main risk is shrinking", "Holdout"),
    ("Defaults and credit losses", "Whether losses fall, not just shift", "Holdout"),
    ("Card closures and spend", "The customer cost of the actions", "Holdout"),
    ("Reactivation rate", "Whether dormant customers come back", "Campaign target"),
    ("Responses to the 90-day warning", "Whether the assumed shares hold", "Assumed shares"),
    ("Complaints and reinstatement requests", "Customer impact", "Agreed limits"),
    ("Fairness by area", "That actions are not concentrated in particular communities", "Four-fifths test"),
    ("Capital and liquidity freed", "The regulatory benefit", "Finance reporting"),
]

# ------------------------------------------------------------ levers (analyst)
LEVER_PLAIN = {
    "line_decrease": "Trim idle limits",
    "risk_based_decrease": "Trim limits of customers at rising risk",
    "dormant_rightsizing": "Right-size unused cards",
    "transactor_rightsizing": "Right-size pay-in-full customers (not recommended, by policy)",
    "dormant_closure": "Close unused cards (24+ months)",
    "engagement_campaign": "Reactivation / engagement campaign",
    "suppress_automatic_increases": "Stop automatic limit increases",
    "non_reissue_expired_dormant": "Do not reissue expiring unused cards",
}
REASON_PLAIN = {
    "IDLE_LINE_RIGHTSIZING": "idle line",
    "CREDIT_DETERIORATION": "rising credit risk",
    "INACTIVITY": "inactivity",
    "INACTIVITY_NON_REISSUE": "inactivity (card not reissued)",
    "ENGAGEMENT_CAMPAIGN": "low use: engagement offer",
    "SUPPRESS_AUTO_INCREASE": "low use: automatic increase withheld",
    "CUSTOMER_REQUEST": "customer request",
    "OTHER": "other",
}
NOT_RECOMMENDED = ["transactor_rightsizing"]

# lever key: (what it does, example, compliance)
LEVERS = {
    "line_decrease": ("Line decrease with floor: right-size idle lines to the Lever Guide target.",
                      "Occasional user: $10,000 towards 3.5x the peak statement balance, at most 25% per review.",
                      "Reg B adverse action notice within 30 days unless an exception applies (not an inactivity "
                      "action); no over-limit fee or penalty rate on the lower limit for 45 days (Reg Z 1026.9)."),
    "risk_based_decrease": ("Risk-based decrease for customers at rising risk.",
                            "$12,000 line, $1,500 balance: towards balance + 20%, at most 25% per review.",
                            "Reg B adverse action notice with specific reasons; FCRA score disclosure if a bureau "
                            "score was used; 45-day fee / penalty-rate restriction; fair-lending review."),
    "dormant_rightsizing": ("Dormant right-sizing after the 90-day warning (Strategy 3; awaiting decision, B6).",
                            "$8,000 dormant line cut by 25% at the next review.",
                            "Inactivity: no adverse action notice (Reg B 1002.2(c)(2)(ii)); reason code recorded."),
    "transactor_rightsizing": ("Pay-in-full right-sizing - valued for analysts; not recommended, by policy (low "
                               "risk, a marginal saving, risk of upsetting good customers). In Base it shows a small "
                               "gain, partly because the engine's fixed-cost allocation is low.",
                               "Peak plus headroom, at least $5,000.",
                               "Adverse action notice; most sensitive customers."),
    "dormant_closure": ("Dormant closure after the 90-day warning (Strategy 3; awaiting decision, B6).",
                        "Inactive 24+ months, no response to the invite or the warning.",
                        "Inactivity exception (no adverse action notice); notice per the account terms; "
                        "never an inactivity fee (Reg Z 1026.52(b))."),
    "engagement_campaign": ("Reactivation / engagement campaign: offers that add spend and revolving balance. "
                            "Unused cards: Strategy 3's Invite; everyone else: Strategy 2.",
                            "$25 statement credit after $500 in 90 days; BT or installment offers.",
                            "No change to terms, no notice; clear offer terms (UDAAP); a campaign balance moves a "
                            "transactor from 45% to 75%."),
    "suppress_automatic_increases": ("Suppress automatic line increases (Strategy 4; assumption-based; not in the "
                                     "reference workbook).",
                                     "No proactive increase while use stays low.",
                                     "No notice expected (compliance to confirm); increases on request still go "
                                     "through the Reg Z ability-to-pay check."),
    "non_reissue_expired_dormant": ("Non-reissue of expiring dormant cards after the 90-day warning (Strategy 3; "
                                    "assumption-based; awaiting decision, B6).",
                                    "A card expiring within 12 months on an account inactive 24+ months.",
                                    "Inactivity (compliance to confirm); notice per the account terms."),
}

METHODOLOGY_LINKS = [
    ("Methodology (plain language and technical)", "docs/UNUSED_LINE_METHODOLOGY.md"),
    ("Evaluation guide", "specs/unused_line_management/EVALUATION_GUIDE.md"),
    ("Decisions and open decisions", "specs/unused_line_management/DECISIONS.md, OPEN_DECISIONS.md"),
    ("Issues found", "specs/unused_line_management/ISSUES_FOUND.md"),
    ("Revision reports (A: ML removed, B: corrections, C: redesign, E: report alignment)",
     "specs/unused_line_management/REVISION_*_REPORT.md"),
    ("Figures changed since the report", "specs/unused_line_management/FIGURES_CHANGED_SINCE_REPORT.md"),
]
