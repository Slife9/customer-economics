"""Lever guide, segment actions and regulation, summarised from the Unused
Line RWA Scenario Model (Segment Definitions, Lever Guide) and the brief's
compliance table. One source for the Lever guide page and the drill-down.
All regulatory text is a summary for discussion; to be confirmed by
compliance. Timing comes from config (`timing`), not from here."""

COMPLIANCE_NOTE = "Summary for discussion; to be confirmed by compliance."

SEGMENT_ACTIONS = {
    "deteriorating": {
        "why": "Risk is rising (PD at least 4% or the bureau score down 40+ points in 6 months) while most of the line is unused.",
        "actions": ["Risk-based line decrease to about balance + 20%, at most 25% per review.",
                    "Watch for rising cash advances, minimum-only payments and returned payments."],
        "watch": "Adverse action notice with reasons; a cut can raise utilisation and accelerate distress.",
    },
    "relationship": {
        "why": "The card loses money but the customer is valuable across deposits, lending or private banking.",
        "actions": ["Light touch: small right-sizing only on very large unused lines; engagement offers.",
                    "Look at the whole relationship before any line action."],
        "watch": "Attrition loses the relationship profit too (deposits, loans).",
    },
    "dormant": {
        "why": "No purchase, cash or balance activity for 12+ months and a $0 balance.",
        "actions": ["Reactivation campaign first; then right-size or close after failed reactivation (pending approval, B6).",
                    "Do not reissue an expiring card for a long-dormant account (pending approval, B6)."],
        "watch": "Inactivity closures follow the Reg B inactivity exception; give notice per the account terms.",
    },
    "sock_drawer": {
        "why": "Used in at most 4 months a year for under $2,500 of spend.",
        "actions": ["Right-size the line to about 3-4x the peak balance; category or bill-pay offers."],
        "watch": "A line cut can push the card further out of the wallet.",
    },
    "transactors": {
        "why": "Pays in full, low peak utilisation, meaningful spend: profitable behaviour on an oversized line.",
        "actions": ["Leave the line alone: stop automatic increases rather than cut.",
                    "Revolve / installment offers only if they fit the customer (they move the account to 75%)."],
        "watch": "Most sensitive to cuts (top of wallet, bureau utilisation); right-sizing is shown only to demonstrate it.",
    },
    "unassigned": {
        "why": "Unprofitable and low-use, but no segment rule matches.",
        "actions": ["No unused-line lever: diagnose the loss and route to the matching lever."],
        "watch": "A large Unassigned group means the thresholds are too tight for this book.",
    },
}

# lever key: (what it does, example, compliance)
LEVERS = {
    "line_decrease": ("Line decrease with floor: right-size idle lines to the Lever Guide target.",
                      "Sock-drawer: $10,000 to about 3.5x the peak statement balance, at most 25% per review.",
                      "Reg B adverse action notice within 30 days (not an inactivity action); no over-limit fee or "
                      "penalty rate on the lower limit for 45 days (Reg Z 1026.9)."),
    "risk_based_decrease": ("Risk-based decrease for credit-deteriorating accounts.",
                            "$12,000 line, $1,500 balance: towards balance + 20%, at most 25% per review.",
                            "Reg B adverse action notice with specific reasons; FCRA score disclosure if a bureau "
                            "score was used; 45-day fee / penalty-rate restriction; fair-lending review."),
    "dormant_rightsizing": ("Dormant right-sizing (pending approval, B6).",
                            "$8,000 dormant line cut by 25% at the next review.",
                            "Inactivity: no adverse action notice (Reg B 1002.2(c)(2)(ii)); reason code recorded."),
    "transactor_rightsizing": ("Transactor right-sizing - shown to demonstrate its effect; never recommended.",
                               "Peak plus headroom, at least $5,000.",
                               "Adverse action notice; most sensitive customers."),
    "dormant_closure": ("Dormant closure after failed reactivation (pending approval, B6).",
                        "Inactive 24+ months, no response to the campaign.",
                        "Inactivity exception (no adverse action notice); notice per the account terms; "
                        "never an inactivity fee (Reg Z 1026.52(b))."),
    "engagement_campaign": ("Reactivation / engagement campaign: offers that add spend and revolving balance.",
                            "$25 statement credit after $500 in 90 days; BT or installment offers.",
                            "Clear offer terms (UDAAP); a campaign balance moves a transactor from 45% to 75%."),
    "suppress_automatic_increases": ("Suppress automatic line increases on unprofitable low-use accounts "
                                     "(assumption-based; not in the reference workbook).",
                                     "No proactive increase while utilisation stays low.",
                                     "No notice; increases on request still go through the Reg Z ability-to-pay check."),
    "non_reissue_expired_dormant": ("Non-reissue of expired dormant cards (assumption-based; not in the reference "
                                    "workbook; pending approval, B6).",
                                    "A card expiring within 12 months on an account inactive 24+ months.",
                                    "Inactivity; notice per the account terms."),
}

NOTICE_RULES = [
    ("Decrease or closure for credit reasons", "Reg B adverse action notice within 30 days, with specific reasons "
     "or the right to request them (12 CFR 1002.2(c), 1002.9); FCRA score disclosure if a bureau-based score was used."),
    ("Decrease or closure for inactivity (genuine)", "No adverse action notice (Reg B inactivity exception, "
     "1002.2(c)(2)(ii)); the reason code is still recorded."),
    ("Any decrease", "No over-limit fee or penalty rate based on the lower limit until 45 days after notice "
     "(Reg Z 1026.9(c)(2)(vi), (g)(4)); no general prior notice for the decrease itself."),
    ("Any increase", "Reg Z ability-to-pay check (1026.51)."),
    ("Never", "An inactivity fee: inactivity penalty fees are prohibited (Reg Z 1026.52(b))."),
    ("Fair lending", "Four-fifths test by metro on who receives decreases, closures and increases."),
    ("Protected customers", "Suppression first (hardship, SCRA): the system's existing suppression logic."),
]
