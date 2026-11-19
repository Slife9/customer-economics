"""Lever guide, segment actions, plain-language names and regulation,
summarised from the Unused Line RWA Scenario Model (Segment Definitions,
Lever Guide) and the brief's compliance table. One source for every page.
All regulatory text is a summary for discussion; to be confirmed by
compliance. Timing comes from config (`timing`), not from here."""

COMPLIANCE_NOTE = "Summary for discussion; to be confirmed by compliance."

# ---------------------------------------------------------------- plain names
# Executive view names; the analyst view uses config segments.labels.
PLAIN_SEGMENTS = {
    "deteriorating": "Customers at rising risk",
    "relationship": "Valuable relationship customers",
    "dormant": "Unused cards",
    "sock_drawer": "Occasional users",
    "transactors": "Pay-in-full customers",
    "unassigned": "Other",
}

# key: (analyst label, executive label, one-line definition shown on hover)
TERMS = {
    "screened": ("Screened accounts", "Accounts losing money with large unused lines",
                 "Open cards with card profit below $0, average use under 30% of the line and at least $5,000 unused."),
    "card_profit": ("Card profit under the assumed capital rules", "Annual loss on these cards",
                    "The main engine's card profit with today's capital charge replaced by the March 2026 "
                    "proposal's and the liquidity buffer cost subtracted."),
    "carrying": ("Carrying cost", "Cost of holding unused lines",
                 "Capital held against the unused part of the line, plus the cost of the liquidity buffer, per year."),
    "drawdown": ("Drawdown loss", "Expected losses if lines are used before default",
                 "Annual PD x loss given default x share of the unused line drawn before default x unused line."),
    "unused_cost": ("Total unused-line cost", "Cost of unused lines",
                    "Cost of holding unused lines plus expected losses if they are drawn before default."),
    "headline": ("Headline value", "Annual value",
                 "Change in card profit plus the reduction in expected drawdown losses, per year."),
    "go_no_go": ("Go/no-go", "Still worth it if customers react more strongly?",
                 "Annual value when attrition, spend loss and risk after a cut are 1.5 times the estimate "
                 "and campaign response is 1.5 times lower."),
    "pending": ("Pending approval (B6)", "Awaiting your decision",
                "Dormant-card actions (right-size, close, do not reissue): valued in full, not in the annual "
                "value until approved."),
    "capital": ("Capital released", "One-time capital freed (not annual)",
                "Capital no longer needed after the actions: a one-time amount, never added to the annual value."),
    "extra": ("Extra levers (assumption-based)", "Extra, assumption-based",
              "Levers not in the reference workbook, valued on stated assumptions; shown apart."),
    "year1": ("Year-1 value", "Year-1 value", "The share of the annual value realised in the first year."),
    "leaving": ("Accounts leaving", "Customers leaving",
                "Expected number of customers who close the card after the action (expected value)."),
}

# ------------------------------------------------------------ plain actions
# The three actions executives see; each lever belongs to one. Transactor
# right-sizing is never recommended and appears in the analyst view only.
ACTIONS = {
    "trim": ("Trim unused limits", ["line_decrease", "risk_based_decrease"]),
    "dormant": ("Wake up or close dormant cards",
                ["engagement_campaign", "dormant_rightsizing", "dormant_closure", "non_reissue_expired_dormant"]),
    "stop": ("Stop automatic increases", ["suppress_automatic_increases"]),
}
NOT_RECOMMENDED = ["transactor_rightsizing"]
LEVER_PLAIN = {
    "line_decrease": "Trim idle limits",
    "risk_based_decrease": "Trim limits of customers at rising risk",
    "dormant_rightsizing": "Right-size unused cards",
    "transactor_rightsizing": "Right-size pay-in-full customers (not recommended, by policy)",
    "dormant_closure": "Close unused cards after a failed wake-up campaign",
    "engagement_campaign": "Wake-up (reactivation) campaign",
    "suppress_automatic_increases": "Stop automatic limit increases",
    "non_reissue_expired_dormant": "Do not reissue expiring unused cards",
}
REASON_PLAIN = {
    "IDLE_LINE_RIGHTSIZING": "idle line",
    "CREDIT_DETERIORATION": "rising credit risk",
    "INACTIVITY": "inactivity",
    "INACTIVITY_NON_REISSUE": "inactivity (card not reissued)",
    "ENGAGEMENT_CAMPAIGN": "low use - engagement offer",
    "SUPPRESS_AUTO_INCREASE": "low use and losing money",
    "CUSTOMER_REQUEST": "customer request",
    "OTHER": "other",
}

# Open decisions (OPEN_DECISIONS.md); B8 is decided.
DECISIONS_PENDING = [
    ("B6", "Dormant-card actions: right-size, close after a failed campaign, do not reissue"),
    ("B5", "Risk weight for dormant zero-balance cards (75% today, 45% possible)"),
    ("B7", "Scope: unprofitable low-use accounts only, or full line management"),
    ("B4", "Capital ratio and cost of equity (10.5% / 12%, illustrative)"),
]

SEGMENT_ACTIONS = {
    "deteriorating": {
        "why": "Risk is rising (PD at least 4% or the bureau score down 40+ points in 6 months) while most of the line is unused.",
        "actions": ["Risk-based line decrease to about balance + 20%, at most 25% per review.",
                    "Watch for rising cash advances, minimum-only payments and returned payments."],
        "watch": "Adverse action notice with reasons; a cut can raise utilisation and accelerate distress.",
        "plain_action": "Trim limits",
    },
    "relationship": {
        "why": "The card loses money but the customer is valuable across deposits, lending or private banking.",
        "actions": ["Light touch: small right-sizing only on very large unused lines; engagement offers.",
                    "Look at the whole relationship before any line action."],
        "watch": "Attrition loses the relationship profit too (deposits, loans).",
        "plain_action": "Light trim and offers",
    },
    "dormant": {
        "why": "No purchase, cash or balance activity for 12+ months and a $0 balance.",
        "actions": ["Reactivation campaign first; then right-size or close after failed reactivation (pending approval, B6).",
                    "Do not reissue an expiring card for a long-dormant account (pending approval, B6)."],
        "watch": "Inactivity closures follow the Reg B inactivity exception; give notice per the account terms.",
        "plain_action": "Wake up, then right-size or close (awaiting decision)",
    },
    "sock_drawer": {
        "why": "Used in at most 4 months a year for under $2,500 of spend.",
        "actions": ["Right-size the line to about 3-4x the peak balance; category or bill-pay offers."],
        "watch": "A line cut can push the card further out of the wallet.",
        "plain_action": "Trim limits and offers",
    },
    "transactors": {
        "why": "Pays in full, low peak utilisation, meaningful spend: profitable behaviour on an oversized line.",
        "actions": ["Leave the line alone: stop automatic increases rather than cut.",
                    "Revolve / installment offers only if they fit the customer (they move the account to 75%)."],
        "watch": "Not cut, by policy: low risk, a marginal saving, and the risk of upsetting good customers.",
        "plain_action": "Leave limits alone; stop automatic increases",
    },
    "unassigned": {
        "why": "Unprofitable and low-use, but no segment rule matches.",
        "actions": ["No unused-line lever: diagnose the loss and route to the matching lever."],
        "watch": "A large Unassigned group means the thresholds are too tight for this book.",
        "plain_action": "No limit action; offers and automatic-increase stop only",
    },
}

# lever key: (what it does, example, compliance)
LEVERS = {
    "line_decrease": ("Line decrease with floor: right-size idle lines to the Lever Guide target.",
                      "Sock-drawer: $10,000 to about 3.5x the peak statement balance, at most 25% per review.",
                      "Reg B adverse action notice within 30 days unless an exception applies (not an inactivity "
                      "action); no over-limit fee or penalty rate on the lower limit for 45 days (Reg Z 1026.9)."),
    "risk_based_decrease": ("Risk-based decrease for credit-deteriorating accounts.",
                            "$12,000 line, $1,500 balance: towards balance + 20%, at most 25% per review.",
                            "Reg B adverse action notice with specific reasons; FCRA score disclosure if a bureau "
                            "score was used; 45-day fee / penalty-rate restriction; fair-lending review."),
    "dormant_rightsizing": ("Dormant right-sizing (pending approval, B6).",
                            "$8,000 dormant line cut by 25% at the next review.",
                            "Inactivity: no adverse action notice (Reg B 1002.2(c)(2)(ii)); reason code recorded."),
    "transactor_rightsizing": ("Pay-in-full right-sizing - valued for analysts; not recommended, by policy (low "
                               "risk, a marginal saving, risk of upsetting good customers). In Base it shows a small "
                               "gain, partly because the engine's fixed-cost allocation is low.",
                               "Peak plus headroom, at least $5,000.",
                               "Adverse action notice; most sensitive customers."),
    "dormant_closure": ("Dormant closure after failed reactivation (pending approval, B6).",
                        "Inactive 24+ months, no response to the campaign.",
                        "Inactivity exception (no adverse action notice); notice per the account terms; "
                        "never an inactivity fee (Reg Z 1026.52(b))."),
    "engagement_campaign": ("Reactivation / engagement campaign: offers that add spend and revolving balance.",
                            "$25 statement credit after $500 in 90 days; BT or installment offers.",
                            "No change to terms, no notice; clear offer terms (UDAAP); a campaign balance moves a "
                            "transactor from 45% to 75%."),
    "suppress_automatic_increases": ("Suppress automatic line increases on unprofitable low-use accounts "
                                     "(assumption-based; not in the reference workbook).",
                                     "No proactive increase while utilisation stays low.",
                                     "No notice expected (compliance to confirm); increases on request still go "
                                     "through the Reg Z ability-to-pay check."),
    "non_reissue_expired_dormant": ("Non-reissue of expired dormant cards (assumption-based; not in the reference "
                                    "workbook; pending approval, B6).",
                                    "A card expiring within 12 months on an account inactive 24+ months.",
                                    "Inactivity (compliance to confirm); notice per the account terms."),
}

NOTICE_RULES = [
    ("Decrease or closure for credit reasons", "Reg B adverse action notice within 30 days, with specific reasons "
     "or the right to request them (12 CFR 1002.2(c), 1002.9); FCRA score disclosure if a bureau-based score was used."),
    ("Idle-line decrease", "Reg B adverse action notice unless an exception applies; flagged for compliance."),
    ("Decrease, closure or non-reissue for inactivity (genuine)", "No adverse action notice (Reg B inactivity "
     "exception, 1002.2(c)(2)(ii)); the reason code is still recorded; non-reissue flagged for compliance."),
    ("Engagement campaign; suppressing automatic increases", "No change to terms: no notice (suppression flagged "
     "for compliance confirmation)."),
    ("Any decrease", "No over-limit fee or penalty rate based on the lower limit until 45 days after notice "
     "(Reg Z 1026.9(c)(2)(vi), (g)(4)); no general prior notice for the decrease itself."),
    ("Any increase", "Reg Z ability-to-pay check (1026.51)."),
    ("Never", "An inactivity fee: inactivity penalty fees are prohibited (Reg Z 1026.52(b))."),
    ("Fair lending", "Four-fifths test by metro on the module's own decreases and closures (and increases, if any)."),
    ("Protected customers", "Suppression first (hardship, SCRA): the system's existing suppression logic."),
]

METHODOLOGY_LINKS = [
    ("Methodology (plain language and technical)", "docs/UNUSED_LINE_METHODOLOGY.md"),
    ("Evaluation guide", "specs/unused_line_management/EVALUATION_GUIDE.md"),
    ("Decisions and open decisions", "specs/unused_line_management/DECISIONS.md, OPEN_DECISIONS.md"),
    ("Issues found", "specs/unused_line_management/ISSUES_FOUND.md"),
    ("Revision reports (A: ML removed, B: corrections, C: redesign)", "specs/unused_line_management/REVISION_*_REPORT.md"),
]
