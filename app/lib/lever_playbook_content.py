"""Static content for the Lever Playbook page (app/pages/21_Lever_Playbook.py).

Kept as a plain, Streamlit-free data module so audit/audit_lever_playbook.py
can validate it (completeness, and that every numeric claim here still
matches the real engine constant it describes) without importing Streamlit
or running the app. This is reference content, independent of any uploaded
portfolio - it explains the machinery, the live numbers live on the Levers
& Strategy page.
"""
from __future__ import annotations

CORE_CONCEPTS = [
    {
        "title": "What does 'net economic profit' actually mean?",
        "body": """
Revenue the customer generates (interest, interchange, fees, and - if they
hold other products - deposit and loan value) **minus every real cost**:
what we pay out in rewards, the cost of funding the money we lend, expected
credit losses, the cost of servicing the account, and the capital we're
required to hold against it. Not revenue. Not "contribution margin" with
some costs left out. Everything, netted to one number, per customer, per
month.

Most banks can tell you a customer's revenue. Very few can tell you this
number, because the pieces usually live in different systems (risk, finance,
operations, capital) that were never joined at the customer level. That join
is most of what this system does.
""",
    },
    {
        "title": "Why does suppression happen before anything else?",
        "body": """
Customers in **hardship, on an accommodation plan, or covered by SCRA**
(the Servicemembers Civil Relief Act) are removed from the population
**before** any lever, any score, or any routing decision touches the data -
not flagged and reviewed afterward. This is enforced in the code itself: a
lever physically cannot receive a customer list that hasn't been through
suppression first.

The reasoning: a customer in genuine financial difficulty often *does*
generate high servicing cost and *does* look unprofitable - but that's an
obligation the bank has taken on, not a leakage problem to be optimized
away. Treating vulnerability as a cost-cutting opportunity is exactly the
kind of finding this system is built to never produce.
""",
    },
    {
        "title": "Why are some levers priced and others say 'None'?",
        "body": """
Every lever's value falls into one of two honest categories:

- **Priced** - a real dollar figure, calculated from data that already
  exists (what customers already did). Line management's expected-loss
  savings is priced this way: it uses the same risk model the bank already
  trusts, just applied to a smaller credit line.
- **None, with unpriced context** - used whenever the true value depends on
  how a customer would *respond* to something we've never actually done to
  them (would they accept a new fee? would a retention call change their
  mind? would they spend more at a higher rate?). No historical dataset can
  honestly answer a question about a treatment that was never tried. Rather
  than guess, the system reports **`None`** for the priced value and gives
  you context instead - like the size of the opportunity, or the value at
  risk - clearly labeled as context, not a forecast.

The only way to turn a `None` into a real number is to actually run the
test: a **champion/challenger pilot**, where a small group gets the new
treatment and a control group doesn't, and you measure the real difference.
""",
    },
    {
        "title": "What do 'Fast', 'Slow', and 'Pilot required' mean?",
        "body": """
This is about how soon a lever could realistically go into production - not
how good the finding is.

- **Fast** - no customer contact is needed, or if there is, no mandatory
  notice period stands in the way. You could start next week.
- **Slow** - the finding is real, but federal law requires a notice period
  and/or a fair-lending review before you can act (e.g., a 45-day notice
  before changing a fee or a rate). That's calendar time you can't shortcut,
  regardless of confidence in the analysis.
- **Pilot required** - a different kind of caution: we genuinely don't know
  what will happen, because it depends on a customer's reaction to a
  treatment that's never been tried. The only responsible path is a small
  controlled test before scaling anything.

**Why sequence by this instead of by lever number:** the fast levers prove
real, verified savings within a quarter with almost no friction, which is
exactly the track record that makes it easier to get sign-off later for the
slower, higher-permission levers. Starting with the slowest lever first is
faster on paper and stalls in legal review in practice.
""",
    },
]

SEQUENCE_ORDER = ["L4", "L2", "L6", "L1", "L5", "L3"]

LEVERS = [
    {
        "code": "L4", "icon": "⚙️", "name": "Cost-to-Serve Migration",
        "module": "engine/levers/l4_cost_to_serve.py",
        "speed": "Fast", "gate": "None",

        "problem": "Some customers generate avoidable servicing cost - calls "
                  "that a self-service option could have handled, paper "
                  "statements when digital would do.",
        "why_it_matters": "Servicing cost is usually the single largest "
                          "controllable expense line in card operations, and "
                          "unlike credit losses it compounds every month a "
                          "customer isn't migrated - it is also the one lever "
                          "with no regulatory gate, so it is the fastest way "
                          "to prove the whole program works before asking for "
                          "permission on anything harder.",
        "population": "Accounts with 3+ avoidable calls (billing/rewards/rate "
                      "queries) or 6+ paper statements in the trailing window, "
                      "plus anyone already routed here because servicing cost "
                      "is their dominant loss driver.",
        "data_needed": [
            "Table12_Cost_Drivers.csv - Primary Call Reason, Paper Statements "
            "Produced, Masked Account Number",
            "Table11_Cost_Pools.csv - Allocation Tier, Volume Band From/To, "
            "Band Fixed Cost USD Monthly, Marginal Unit Cost USD",
            "customer_view's routed_lever / routing_reason (already-routed loss cases)",
        ],
        "actions": [
            "3+ avoidable calls in the trailing window -> ENABLE_SELF_SERVICE: "
            "steer to IVR/app/web self-service for billing, rewards, and rate "
            "queries specifically (the three reasons counted as avoidable).",
            "6+ paper statements -> MIGRATE_TO_DIGITAL_STATEMENTS: an opt-in "
            "e-statement campaign with proper E-SIGN consent, not a silent "
            "default change.",
            "Already routed here on dominant cost -> same two actions, "
            "documented by the routing engine's own stated reason.",
        ],
        "sequence": [
            "Pull avoidable-call and paper-statement volumes per customer from "
            "the cost-driver table.",
            "Flag anyone crossing either threshold (the two flags can overlap).",
            "Issue the digital nudge / self-service offer through existing "
            "servicing channels - no account term changes, so no legal notice "
            "is required.",
            "Track 90 days of post-nudge driver volume for the same customers.",
            "Recompute the capacity-band sizing monthly: avoided volume only "
            "becomes a real, bookable dollar once it crosses a fixed-cost "
            "step boundary in the cost pool; below that, only the marginal "
            "per-unit savings is real.",
        ],
        "teams": [
            ("Servicing Operations", "owns the self-service deflection channels"),
            ("Digital / Product", "owns the e-statement migration UX and consent flow"),
            ("Finance / FP&A", "owns the cost-pool bands; confirms a capacity step was actually crossed before any fixed-cost savings are booked"),
            ("Compliance", "E-SIGN consent and statement-format rules"),
            ("Data / Analytics", "reruns the ledger pipeline monthly to re-measure"),
        ],
        "approvals": "No regulatory gate on the customer action itself. "
                    "Finance sign-off IS required before booking any FIXED "
                    "cost-pool savings - they only exist once deflected volume "
                    "crosses a capacity-band boundary and headcount/vendor "
                    "capacity is actually resized; marginal per-unit savings "
                    "can be claimed as soon as they're realized.",
        "testing": "No treatment/control split is needed for the nudge itself "
                  "(it changes a channel offer, not a term), but run a "
                  "champion/challenger on WHICH nudge message or channel "
                  "drives the most deflection, holding back a random ~10% as "
                  "a true control so uplift isn't confused with normal "
                  "seasonal volume swings.",
        "kpis": [
            ("Avoidable call volume", "trailing 90-day count, by reason code", "Monthly"),
            ("Paper statement count", "trailing 90-day count", "Monthly"),
            ("Marginal $ saved", "avoided volume x the current band's marginal unit cost", "Monthly"),
            ("Fixed $ realized", "booked ONLY after Finance confirms a step boundary was crossed and capacity resized", "Quarterly"),
            ("Self-service / e-statement adoption rate", "share of flagged customers who actually migrated", "Monthly"),
            ("Complaint / callback rate", "on migrated customers, vs. portfolio baseline", "Monthly"),
        ],
        "risks": [
            "Booking fixed-cost savings before capacity is actually resized - "
            "claiming savings that were never realized.",
            "Migrating a customer to self-service who genuinely needed a "
            "human - complaint and attrition risk.",
            "E-statement opt-in without proper E-SIGN consumer-consent "
            "documentation.",
            "Treating the shared-overhead allocation as if one customer's "
            "migration changes it - it doesn't; only the marginal, "
            "customer-caused share ever moves.",
        ],
        "evolution": "**Expand** once marginal savings show up in the ledger "
                    "for two consecutive cycles with no rise in complaints. "
                    "**Revise** the avoidable-call / paper-statement "
                    "thresholds if too many flagged customers turn out to "
                    "have called for one genuinely necessary reason. **Stop** "
                    "nudging any customer who re-requests paper or calls back "
                    "for the same reason within 60 days of migration - that's "
                    "a signal the deflection failed them, not a target to "
                    "push harder.",
        "worked_example": "Illustrative, not live data: a customer with 4 "
                         "billing-query calls and 8 paper statements in the "
                         "trailing year is flagged for both "
                         "MIGRATE_TO_DIGITAL_STATEMENTS and "
                         "ENABLE_SELF_SERVICE. If the statement cost pool's "
                         "current band has a $0.42/statement marginal cost, "
                         "migrating this one customer alone saves roughly "
                         "$3.36/yr - trivial by itself, which is exactly why "
                         "this lever only matters at the scale of thousands "
                         "of similar accounts, and only becomes a material, "
                         "bookable number once enough volume crosses the "
                         "pool's fixed-cost step.",
        "checklist": [
            "Confirm Table12_Cost_Drivers.csv and Table11_Cost_Pools.csv are "
            "loaded for this run",
            "Confirm the current capacity band for each avoidable activity "
            "before claiming any fixed savings",
            "Draft self-service nudge copy for app / IVR",
            "Draft e-statement opt-in flow with E-SIGN consent",
            "Hold out a random control group for the channel A/B test",
            "Schedule a 90-day re-pull of driver volumes",
            "Get Finance sign-off before booking any fixed-cost savings",
            "Monitor complaint / callback rate weekly for the first 60 days",
        ],
        "constants": {"AVOIDABLE_CALL_THRESHOLD": 3, "PAPER_STATEMENT_THRESHOLD": 6},
    },
    {
        "code": "L2", "icon": "📈", "name": "Line Management by Value",
        "module": "engine/levers/l2_lines.py",
        "speed": "Fast (decreases) / Moderate (increases)",
        "gate": "Reg B adverse action notice on any decrease",

        "problem": "A credit line can be wrong in either direction: far more "
                  "than a customer will ever use, or too tight for a customer "
                  "who would spend more given room.",
        "why_it_matters": "Idle exposure is risk the bank carries for no "
                          "reason, and a too-tight line on a good customer is "
                          "foregone interest and interchange every month it "
                          "stays that way - both sides compound, and both are "
                          "invisible if you only ever look at a single "
                          "snapshot month instead of a full year of behavior.",
        "population": "Four outcomes from a 12-month behavioral profile, not "
                      "one: DECREASE (avg utilization <=10%, peak <=20%, "
                      "light spend, 12+ months seasoned, good standing), "
                      "ENGAGE (the same idle profile but also >=50% of "
                      "months inactive - dormant, a reactivation candidate, "
                      "never a cut candidate), GROW_ENGAGEMENT (heavy spend "
                      "relative to the limit with >=50% of months paid in "
                      "full - active and valuable despite a low ending "
                      "balance, explicitly NOT touched), and INCREASE (peak "
                      "utilization >=75%, 0 days past due, score >=660). "
                      "Credit-cost-dominant routed losses get "
                      "DECREASE_RISK_EXPOSURE independently of utilization.",
        "data_needed": [
            "Credit Limit, Ending Balance, Utilization - monthly, trailing 12mo",
            "Purchases Authorized - for spend_to_limit_ratio",
            "Account Type (Transactor / Revolver / Inactive) - monthly, for "
            "transactor_share_12m and inactive_share_12m",
            "Days Past Due (latest), Credit Score, account open date (seasoning)",
            "PD Lifetime, LGD, Behavioral CCF - the same risk model already in production",
            "annual_liquidity_cost and leverage_capital_cost - already computed per customer",
        ],
        "actions": [
            "DECREASE / DECREASE_RISK_EXPOSURE -> cut the limit to "
            "max(peak_utilization x current_limit x 1.5, trailing-12mo "
            "spend x 1.10), floored at $300, WITH a Reg B adverse-action "
            "notice sent before the cut takes effect.",
            "INCREASE -> raise the limit toward the peer (same Credit Score "
            "Band) median peak-utilization headroom; no notice required.",
            "ENGAGE -> no limit action; hand to Marketing/Retention for a fee "
            "waiver review (if an annual fee exists), a spend-activation "
            "bonus, and a digital wallet enrollment prompt.",
            "GROW_ENGAGEMENT -> no limit action; category-based bonus offer "
            "and loyalty/status review - protect this relationship, the "
            "limit is explicitly not the constraint.",
        ],
        "sequence": [
            "Build the 12-month behavioral profile per account (avg/peak "
            "utilization, spend-to-limit, transactor/inactive share, seasoning).",
            "Classify into exactly one of the five outcomes.",
            "For any decrease: draft and send the Reg B notice FIRST; apply "
            "the cut only after the notice's effective date.",
            "For any increase: apply the same cycle, no notice needed.",
            "For ENGAGE / GROW_ENGAGEMENT: hand the worklist to Marketing/"
            "Retention with zero credit-line action attached.",
            "Re-score the full population every cycle, so a reactivated "
            "ENGAGE customer or a newly-cut DECREASE customer isn't "
            "re-flagged on a stale snapshot.",
        ],
        "teams": [
            ("Credit Risk", "owns PD/LGD/behavioral CCF and signs off on the target-limit formula"),
            ("Compliance / Legal", "Reg B adverse-action notice content and timing"),
            ("Collections / Servicing Ops", "executes the system limit change"),
            ("Marketing / Retention", "runs ENGAGE and GROW_ENGAGEMENT campaigns"),
            ("Model Risk", "periodically validates the origination risk model is still appropriate for this re-underwriting use"),
        ],
        "approvals": "Reg B adverse-action notice is mandatory on every "
                    "decrease, with the specific reason stated. A four-fifths "
                    "fairness test runs on the DECREASE and INCREASE "
                    "treatment populations (not just the score) before "
                    "go-live. Suppressed customers (hardship/accommodation/"
                    "SCRA) never reach this lever at all.",
        "testing": "Champion/challenger on the INCREASE side only - hold back "
                  "a random sample of INCREASE-eligible accounts at their "
                  "current limit for a full 12-month seasoning cycle to "
                  "confirm the peer-benchmarked headroom actually converts "
                  "to incremental interest/interchange before scaling. The "
                  "DECREASE side is a model-backed risk-exposure reduction, "
                  "not a behavioral bet, so it doesn't need the same kind of "
                  "held-back test - it needs the realized-loss tracking in "
                  "the KPIs below instead.",
        "kpis": [
            ("Realized expected-loss avoided", "actual charge-offs on the DECREASE cohort vs. the pre-cut expected-loss estimate", "Quarterly"),
            ("Realized incremental interest/interchange", "INCREASE cohort actual vs. the peer-benchmark estimate", "Quarterly"),
            ("Adverse-action complaint/dispute rate", "on the DECREASE cohort", "Monthly"),
            ("Reactivation rate", "ENGAGE cohort who resume active use", "Monthly"),
            ("Attrition rate", "all five cohorts vs. portfolio baseline", "Quarterly"),
            ("Four-fifths fairness ratio", "on each cohort, post-launch", "Quarterly"),
        ],
        "risks": [
            "A 12-month average still can't rule out a customer who needs "
            "that room for a one-time event right after the cut.",
            "Reg B notice errors or timing mistakes create real legal exposure.",
            "Disparate impact if DECREASE or INCREASE selection correlates "
            "with a protected-class proxy even though it's driven by "
            "utilization and risk alone.",
            "Booking regulatory capital relief that doesn't exist - an "
            "undrawn card line carries a 0% risk-based CCF (12 CFR "
            "217.33(b)(1)), so a decrease frees no regulatory capital, only "
            "economic capital and (separately) liquidity cost.",
        ],
        "evolution": "**Expand** the DECREASE cohort once realized charge-offs "
                    "in the first 90 days track the modeled expected-loss "
                    "estimate and complaints stay at baseline; expand "
                    "INCREASE once the held-back challenger group confirms "
                    "incremental usage. **Revise** the idle-utilization or "
                    "seasoning thresholds if the split is misclassifying "
                    "known-good seasonal spenders. **Stop** issuing further "
                    "decreases in a cohort immediately if a fair-lending "
                    "review flags disparate impact, pending legal/compliance "
                    "resolution.",
        "worked_example": "Illustrative, not live data: a $5,000-limit "
                         "account with 12-month average utilization 4%, peak "
                         "9%, trailing spend of $600/yr, seasoned 18 months, "
                         "0 days past due -> target limit = "
                         "max(9% x $5,000 x 1.5, $600 x 1.10) = max($675, "
                         "$660) = $675, so DECREASE_LIMIT to about $675, Reg "
                         "B notice sent first. Compare a second $5,000-limit "
                         "account with 85% peak utilization, paid in full "
                         "every month, score 710 -> flagged INCREASE instead, "
                         "no notice required.",
        "checklist": [
            "Confirm every account has 12 full months of utilization/spend "
            "history before classifying",
            "Draft the Reg B adverse-action notice template with the "
            "specific decrease reason",
            "Run the four-fifths fairness test on DECREASE and INCREASE "
            "cohorts before go-live",
            "Confirm suppressed customers are excluded",
            "Set up the 12-month INCREASE challenger holdout",
            "Hand ENGAGE / GROW_ENGAGEMENT lists to Marketing with no credit "
            "action attached",
            "Schedule monthly re-scoring so cohorts update as behavior changes",
            "Confirm the bank's leverage regime (Tier 1 vs. SLR) before "
            "quoting any capital-relief figure",
        ],
        "constants": {"MIN_SEASONING_MONTHS": 12, "IDLE_AVG_UTIL_CEILING": 0.10,
                     "IDLE_PEAK_UTIL_CEILING": 0.20, "IDLE_SPEND_TO_LIMIT_CEILING": 0.50,
                     "DORMANT_SPEND_TO_LIMIT_CEILING": 0.15, "DORMANT_INACTIVE_SHARE_FLOOR": 0.50,
                     "ACTIVE_TRANSACTOR_SHARE_FLOOR": 0.50, "IDLE_LIMIT_FLOOR": 1000.0,
                     "STRETCHED_PEAK_UTIL_FLOOR": 0.75},
    },
    {
        "code": "L6", "icon": "🧭", "name": "Channel Quality Review",
        "module": "engine/levers/l6_crosssell.py",
        "speed": "Fast", "gate": "None",

        "problem": "Not every acquisition channel brings in equally valuable "
                  "customers - a channel can look cheap per account and "
                  "still be expensive per dollar of value delivered.",
        "why_it_matters": "Acquisition spend is committed before a single "
                          "customer's true economics are known; a channel "
                          "that's quietly underperforming keeps consuming "
                          "budget every quarter it goes unmeasured, while the "
                          "fix - a budget reallocation - needs no customer "
                          "contact and no regulatory gate at all.",
        "population": "Ranks acquisition channels by mean net value after "
                      "acquisition cost (CAC); flags accounts acquired "
                      "through the bottom third of channels for a "
                      "spend-reallocation review - a budget decision, not an "
                      "individual customer action.",
        "data_needed": [
            "Acquisition table - Acquisition Channel, Acquisition Cost USD "
            "(if present in the upload)",
            "Account-to-customer mapping (Table2_Card_Account.csv)",
            "trailing_12m_net_economic_profit per customer",
        ],
        "actions": [
            "Rank channels by mean net value after CAC on the current book.",
            "Flag accounts acquired via the bottom third of channels for "
            "REVIEW_ACQUISITION_CHANNEL_MIX - a sourcing/budget review, not "
            "a customer-facing action.",
            "If Acquisition Cost USD wasn't in the upload, the ranking is "
            "gross-value-only and must be labeled as such before anyone "
            "acts on it.",
        ],
        "sequence": [
            "Compute mean net value after CAC per channel on the current book.",
            "Identify the bottom-third channels by that measure.",
            "Route the finding to Acquisition Marketing as a budget/sourcing "
            "review - never as a per-customer treatment.",
            "If cost data is missing, flag the gross-value-only caveat "
            "before any budget decision is made.",
            "Re-run quarterly - a channel's true value takes a few cycles to "
            "season into measurable interest/interchange, so comparing too "
            "early understates it.",
        ],
        "teams": [
            ("Acquisition Marketing", "owns channel budget allocation"),
            ("Finance", "owns Acquisition Cost USD data quality"),
            ("Analytics", "reruns the ranking and confirms cost-adjusted value is used wherever the data supports it"),
        ],
        "approvals": "None - this never touches an individual customer's "
                    "terms or experience. Where a flagged channel serves an "
                    "underserved market segment, a CRA/fair-lending gut-check "
                    "on who loses access is still warranted before cutting "
                    "its budget, even though no formal notice is required.",
        "testing": "Not a customer-level pilot - no individual is treated "
                  "differently. The real test is a media-mix test: shift a "
                  "small, deliberate share of acquisition spend from the "
                  "worst channel to the best for one full quarter and "
                  "compare the new cohort's early value trajectory to a "
                  "continued-worst-channel control cohort, since the "
                  "ranking itself is explicitly correlational, not causal.",
        "kpis": [
            ("Mean net value after CAC by channel", "quarterly channel ranking", "Quarterly"),
            ("Channel mix of new originations", "% of volume shifted away from bottom-third channels", "Quarterly"),
            ("Early-cohort value trajectory", "newly acquired accounts from the reallocated budget vs. the old mix", "Quarterly"),
        ],
        "risks": [
            "Treating a correlational channel ranking as a guarantee the "
            "same volume is available at the same cost through a 'better' "
            "channel.",
            "Shutting down a channel that serves an underserved segment for "
            "purely economic reasons without a CRA/fair-lending review of "
            "who loses application access.",
            "Acting on a cost-blind ranking when Acquisition Cost USD wasn't "
            "in the upload.",
        ],
        "evolution": "**Expand** the reallocation once a full quarter's "
                    "reallocated-channel cohort shows value in line with the "
                    "historical best-channel average. **Revise** the "
                    "bottom-third cutoff if it's flagging a channel that's "
                    "small but genuinely still profitable. **Stop/reverse** "
                    "the reallocation if a CRA or fair-lending review raises "
                    "concerns about who gets excluded from channel access.",
        "worked_example": "Illustrative, not live data: Direct Mail customers "
                         "average $420/yr net value after a $180 average "
                         "acquisition cost; Digital customers average "
                         "$610/yr net value after a $95 average acquisition "
                         "cost. The $190/yr gap, times however many customers "
                         "came through Direct Mail this period, is the "
                         "context figure for a budget conversation - not a "
                         "promise that redirecting that spend to Digital "
                         "reproduces the same $610, since Digital's current "
                         "customers may differ from who Direct Mail actually "
                         "reaches.",
        "checklist": [
            "Confirm Acquisition Cost USD is present in this upload",
            "Re-rank channels for this quarter",
            "Identify the bottom-third channels",
            "Brief Acquisition Marketing on the ranking and its "
            "correlational caveat",
            "Design the media-mix test - reallocate a small share of spend "
            "first, not all of it",
            "Flag any channel serving an underserved segment for a CRA/"
            "fair-lending check before reducing its budget",
            "Re-measure the reallocated cohort's value after one full quarter",
        ],
        "constants": {},
    },
    {
        "code": "L1", "icon": "🎁", "name": "Rewards & Promo Economics",
        "module": "engine/levers/l1_rewards.py",
        "speed": "Slow", "gate": "Reg Z: 45 days notice + right to reject",

        "problem": "Some customers take out more reward value every year "
                  "than the relationship earns back - and the strongest fix "
                  "is usually not cutting the rewards program, it's charging "
                  "a fee that matches the value already being delivered.",
        "why_it_matters": "Reward cost is a real cash outflow every cycle a "
                          "fee-free high-reward account stays fee-free; left "
                          "alone it quietly subsidizes exactly the customers "
                          "who need it least, while the program-level version "
                          "of the same problem (rewards driving a portfolio "
                          "loss outright) points to a vendor/earn-rate "
                          "renegotiation instead of any one customer's fee.",
        "population": "Two distinct groups, not one: customers routed here "
                      "because reward cost is their dominant loss driver "
                      "(a program-design question), and - a separate, "
                      "arguably more important group - profitable customers "
                      "taking >=$100/yr in reward value while paying no "
                      "annual fee at all (a fee opportunity).",
        "data_needed": [
            "reward_expense - trailing 12mo, per customer",
            "annual_fee_total - trailing 12mo, per customer",
            "is_below_cost / routed_lever / routing_reason from customer_view",
        ],
        "actions": [
            "Dominant reward-cost loss driver -> REVIEW_REWARD_PROGRAM_COST: "
            "a Product/vendor-level question about the earn rate or "
            "redemption cost itself, independent of any one customer's fee.",
            "Profitable, $0 annual fee, reward_expense >= $100/yr -> "
            "PILOT_ALIGNED_ANNUAL_FEE: a champion/challenger test "
            "introducing a fee aligned to the reward value already "
            "delivered, with Reg Z's 45-day notice and right to reject.",
        ],
        "sequence": [
            "Identify the fee-free, high-reward-value cohort.",
            "Design a small randomized pilot introducing a modest fee tied "
            "to a reward tier.",
            "Send the Reg Z 45-day notice with the right-to-reject "
            "disclosure to the treatment arm only.",
            "Hold a matched control group at $0 fee.",
            "Measure acceptance vs. closure vs. reward-usage change over the "
            "following 2-3 statement cycles.",
            "Only after the pilot, decide whether to scale the fee, adjust "
            "its amount, or abandon it.",
        ],
        "teams": [
            ("Product / Rewards Program Management", "fee structure design"),
            ("Compliance / Legal", "Reg Z notice content and right-to-reject mechanics"),
            ("Marketing / Communications", "customer-facing notice and messaging"),
            ("Finance", "books the pilot's real revenue/retention trade-off"),
            ("Vendor Management", "renegotiates reward cost itself for the REVIEW_REWARD_PROGRAM_COST cohort"),
        ],
        "approvals": "Reg Z's 45-day advance written notice before "
                    "introducing or increasing a fee is mandatory and sets "
                    "the floor on how fast this can move, regardless of "
                    "analysis confidence. The customer's right to reject "
                    "(typically by closing the account under prior terms) "
                    "must be automatic, not case-by-case.",
        "testing": "True champion/challenger required - a self-selected "
                  "pilot with no held-back control group can't separate 'the "
                  "fee caused this' from 'this cohort was already drifting.' "
                  "Track closure rate, reward redemption behavior, and spend "
                  "change in both arms for at least 2 full statement cycles "
                  "after the notice period elapses.",
        "kpis": [
            ("Fee acceptance rate", "accounts that stay vs. close after notice", "Per pilot cycle"),
            ("Realized fee revenue vs. forgone reward cost", "net effect, treatment arm", "Per pilot cycle"),
            ("Closure rate", "pilot vs. control", "Per pilot cycle"),
            ("Complaint volume", "referencing the fee change", "Monthly"),
            ("Reward redemption rate change", "both arms", "Per pilot cycle"),
        ],
        "risks": [
            "Customers close rather than pay the new fee, destroying more "
            "value than the fee recovers.",
            "Reputational/complaint risk from any fee introduction.",
            "The pilot cohort isn't representative of the broader fee-free "
            "population.",
            "Conflating REVIEW_REWARD_PROGRAM_COST (program/vendor-level) "
            "with PILOT_ALIGNED_ANNUAL_FEE (customer-level) - they need "
            "separate owners and separate timelines.",
        ],
        "evolution": "**Expand** the fee pilot to the full fee-free, "
                    "high-reward cohort only if closure rate stays below an "
                    "agreed threshold and net revenue (fee minus lost "
                    "reward-driven spend/interchange) is positive. "
                    "**Revise** the fee amount or tier structure if "
                    "acceptance is low but closures aren't the cause (e.g., "
                    "spend simply drops). **Stop and unwind** - including "
                    "offering an opt-out - if complaint volume or closure "
                    "rate spikes well above the control arm.",
        "worked_example": "Illustrative, not live data: a customer earning "
                         "$340/yr in rewards with a $0 annual fee is flagged "
                         "PILOT_ALIGNED_ANNUAL_FEE; a matched control group "
                         "of similar fee-free, high-reward customers is held "
                         "at $0 fee while the pilot group gets a 45-day "
                         "notice introducing a $95 annual fee positioned "
                         "against the reward value already received. "
                         "Separately, a customer whose own reward cost is "
                         "the dominant driver of a portfolio loss is flagged "
                         "REVIEW_REWARD_PROGRAM_COST - a program-design "
                         "question for Product, not an individual fee decision.",
        "checklist": [
            "Confirm the fee-free, high-reward cohort meets the $100/yr floor",
            "Draft the Reg Z 45-day notice with right-to-reject language",
            "Design a matched control group for the pilot",
            "Get Legal/Compliance sign-off on notice content",
            "Launch the pilot and log closure/spend/redemption in both arms",
            "Review results after 2-3 statement cycles before any scale decision",
            "Route REVIEW_REWARD_PROGRAM_COST cases separately to Product/"
            "Vendor Management, not the fee pilot",
        ],
        "constants": {"OPPORTUNITY_REWARD_VALUE_FLOOR": 100.0},
    },
    {
        "code": "L5", "icon": "🛟", "name": "Retention Targeting",
        "module": "engine/levers/l5_retention.py",
        "speed": "Pilot required",
        "gate": "None to flag risk; a pilot before acting on it",

        "problem": "Retention budget is a scarce resource and should go to "
                  "the customers actually worth keeping - not by balance or "
                  "tenure, but by real economic value.",
        "why_it_matters": "A save-desk team with a fixed budget and no "
                          "value-based prioritization spends the same effort "
                          "on a marginal customer as a top-value one; "
                          "meanwhile the real cost of doing nothing - the "
                          "value at risk - is both measurable today and "
                          "completely different from the value a save "
                          "campaign could actually recover.",
        "population": "High-value (Valued/Premier band) customers showing at "
                      "least one OBSERVABLE warning sign: a closure-request "
                      "contact, a trailing spend decline of 30%+ (3 months "
                      "vs. the prior 3), or a price position 2+ points above "
                      "their Credit Score Band peer median. Built only from "
                      "signals the bank can actually see.",
        "data_needed": [
            "cev_band (Valued/Premier) per customer",
            "Primary Call Reason == closure_request, from Table12_Cost_Drivers.csv",
            "spend_decline flag - trailing 3mo vs. prior 3mo, from "
            "Table5_Transaction.csv",
            "latest_charged_apr vs. Credit Score Band peer median",
        ],
        "actions": [
            "Any Valued/Premier customer with >=1 warning signal -> "
            "RETENTION_OUTREACH, routed to a save-desk conversation - not an "
            "automatic offer.",
            "Prioritize the outreach queue by value at risk (trailing-12mo "
            "NEP), highest first, given limited retention capacity.",
        ],
        "sequence": [
            "Pull the three observable signals for the Valued/Premier population.",
            "Flag anyone with at least one signal; log which signal(s) fired.",
            "Prioritize outreach by value at risk given limited retention "
            "budget/capacity.",
            "Route each flagged customer to a save-desk conversation matched "
            "to their actual signal - a closure-request contact needs a "
            "different conversation than a pricing complaint.",
            "Design and run a champion/challenger retention-offer pilot - "
            "the real uplift question - before committing budget at scale.",
            "Re-pull signals every cycle; spend decline and pricing gaps "
            "shift month to month.",
        ],
        "teams": [
            ("Retention / Loyalty (\"save desk\")", "runs the outreach"),
            ("Marketing", "designs the offer once a pilot validates one"),
            ("Pricing / Risk", "confirms the priced_above_peer signal"),
            ("Compliance", "ensures outreach never drifts into a credit decision needing its own separate notice"),
        ],
        "approvals": "No regulatory gate on flagging risk itself. ANY concrete "
                    "offer tested in the pilot (a fee waiver, a rate match, a "
                    "bonus) must clear whatever gate applies to THAT offer - "
                    "e.g., a rate change still triggers CARD Act/Reg Z "
                    "mechanics even inside a retention conversation. 'No "
                    "gate' applies only to identifying who's at risk, never "
                    "to whatever is ultimately offered.",
        "testing": "Mandatory champion/challenger before claiming any "
                  "retention save: randomly split the flagged, prioritized "
                  "population into a treatment arm (receives outreach/offer) "
                  "and a true control (receives nothing), then compare "
                  "actual closure and spend-recovery rates between arms over "
                  "the following 2-3 cycles. The lever's own value is "
                  "explicitly priced as None until this exists.",
        "kpis": [
            ("Value at risk", "trailing-12mo NEP of the flagged cohort - a fact about today, not a forecast", "Monthly"),
            ("Closure rate", "treatment vs. control", "Per pilot cycle"),
            ("Spend-recovery rate", "treatment vs. control", "Per pilot cycle"),
            ("Cost per retained customer", "outreach cost / customers who didn't close that would otherwise have been expected to", "Per pilot cycle"),
            ("Signal precision", "share of flagged customers who actually deteriorated further vs. recovered with no contact", "Quarterly"),
        ],
        "risks": [
            "Spending retention budget on customers who would have stayed "
            "anyway, with no control group to prove otherwise.",
            "Treating 'value at risk' as if it were 'value recoverable' - "
            "the exact forecasting error this lever's own code refuses to make.",
            "Outreach that feels invasive to a customer who made one routine call.",
            "Signal staleness if spend-decline or pricing-gap data isn't "
            "refreshed every cycle.",
        ],
        "evolution": "**Expand** the offer design portfolio-wide only once "
                    "the champion/challenger arms show a sustained "
                    "difference in closure/spend-recovery rates. **Revise** "
                    "the signal set if closure-request contacts turn out to "
                    "be a weak predictor relative to spend decline or "
                    "pricing gap. **Stop** outreach on anyone who explicitly "
                    "opts out, and re-route repeat false positives (flagged, "
                    "contacted, no further deterioration across multiple "
                    "cycles) back to Analytics to refine the thresholds.",
        "worked_example": "Illustrative, not live data: a Premier-band "
                         "customer makes a closure-request call in month 10 "
                         "of the trailing window and is also priced 2.4 "
                         "points above their Credit Score Band peer median - "
                         "flagged for RETENTION_OUTREACH with both signals "
                         "logged, prioritized near the top of the queue by "
                         "their $3,200 trailing-12mo value at risk, and "
                         "routed into the champion/challenger pilot rather "
                         "than an automatic offer.",
        "checklist": [
            "Confirm the Valued/Premier band filter is current this cycle",
            "Pull closure-request, spend-decline, and pricing-gap signals fresh",
            "Prioritize the outreach queue by value at risk",
            "Design the treatment offer AND a true held-back control group",
            "Confirm any concrete offer (rate, fee) clears its own separate "
            "regulatory gate",
            "Track closure/spend-recovery in both arms for 2-3 cycles",
            "Suppress further contact for anyone who opts out",
            "Feed repeat false positives back to Analytics",
        ],
        "constants": {"SPEND_DECLINE_THRESHOLD": 0.30, "RATE_ABOVE_PEER_POINTS": 2.0},
    },
    {
        "code": "L3", "icon": "💲", "name": "Value-Based Pricing",
        "module": "engine/levers/l3_pricing.py",
        "speed": "Slowest",
        "gate": "CARD Act (no year-1 increase, new-transactions-only, 45 "
               "days notice) + fair lending review + a pilot",

        "problem": "A customer's risk drifts after the account is opened, "
                  "but the interest rate they were given at origination "
                  "usually doesn't - so pricing gradually falls out of line "
                  "with the actual cost of serving that customer.",
        "why_it_matters": "Every month a mispriced account goes unaddressed "
                          "is revenue the bank is entitled to and isn't "
                          "collecting, but this is also the single most "
                          "legally constrained lever here - acting too fast "
                          "or on a poorly-reviewed selection carries real "
                          "CARD Act and fair-lending exposure, which is "
                          "exactly why it is sequenced last.",
        "population": "Any account priced 2+ points below its own current-"
                      "risk peer cohort median (by Credit Score Band) and "
                      "past the CARD Act first-year protection - not only "
                      "accounts already showing a loss.",
        "data_needed": [
            "latest_charged_apr, per customer",
            "Credit Score Band peer-median APR (computed from the same cohort)",
            "Customer Tenure Years - for first-year protection",
            "latest_purchase_balance - for the zero-elasticity ceiling estimate",
            "routed_lever / routing_reason from customer_view",
        ],
        "actions": [
            "2+ point gap to peer-median APR, past first-year protection -> "
            "REPRICE_TO_PEER_MEDIAN, applied to NEW TRANSACTIONS ONLY, never "
            "the existing balance.",
        ],
        "sequence": [
            "Compute each account's gap to its peer-median APR.",
            "Exclude anyone still in their CARD Act-protected first 12 months.",
            "Run a mandatory fair-lending review of the resulting worklist "
            "BEFORE any notice goes out - specifically whether the "
            "selection correlates with a protected class beyond what risk "
            "alone explains.",
            "Design a champion/challenger pilot: reprice a randomized "
            "subset, hold a matched control at the old rate.",
            "Send the 45-day CARD Act notice to the pilot's treatment arm only.",
            "Apply the new rate to new transactions only, once the notice "
            "period elapses.",
            "Measure attrition and revolve-behavior change in both arms for "
            "several cycles before any decision to scale.",
            "Only after a clean pilot and fair-lending review, extend to the "
            "remaining eligible population through the same notice-and-wait "
            "mechanics.",
        ],
        "teams": [
            ("Credit Risk / Pricing", "owns the peer-median benchmark and target rate"),
            ("Fair Lending / Compliance", "mandatory pre-rollout review of the selection"),
            ("Legal", "CARD Act notice content and timing"),
            ("Model Risk", "periodic validation that peer-median-by-score-band remains an appropriate benchmark"),
            ("Finance", "tracks the pilot's P&L"),
        ],
        "approvals": "CARD Act bars any increase in the account's first "
                    "year, applies prospectively to new transactions only "
                    "(never the existing balance), and requires 45 days' "
                    "written notice. A fair-lending review of exactly who "
                    "the repricing worklist selects is required before "
                    "rollout, not optional. A champion/challenger pilot is "
                    "required before any portfolio-wide rollout.",
        "testing": "The slowest, highest-permission lever here by design - "
                  "pilot first, always, on a randomized subset with a true "
                  "held-back control, run for enough cycles to observe both "
                  "attrition and revolve-behavior change, since both drive "
                  "the real (not zero-elasticity) value.",
        "kpis": [
            ("Realized repricing revenue", "vs. the zero-elasticity ceiling estimate", "Per pilot cycle"),
            ("Attrition rate", "treatment vs. control", "Per pilot cycle"),
            ("Revolve-balance change", "treatment vs. control", "Per pilot cycle"),
            ("Complaint volume", "referencing the rate change", "Monthly"),
            ("Fair-lending review outcome", "pass / flag on the selected population", "Per review"),
            ("Four-fifths ratio", "on who actually got repriced, post-rollout", "Per review"),
        ],
        "risks": [
            "The zero-elasticity ceiling is explicitly a best case, not a "
            "forecast - booking it as expected revenue overstates the "
            "lever's value.",
            "Attrition could erase some or all of the modeled gain.",
            "A repricing selection that inadvertently correlates with a "
            "protected class even though it's driven by objective risk-peer "
            "comparison.",
            "CARD Act violations (repricing an existing balance, missing "
            "the notice window, touching a first-year account) carry real "
            "legal and regulatory exposure.",
        ],
        "evolution": "**Expand** to the remaining eligible population only "
                    "after the pilot's attrition and revolve-behavior "
                    "results clear whatever hurdle Finance/Risk set in "
                    "advance, and only after a clean fair-lending review. "
                    "**Revise** the 2-point gap threshold or the peer-cohort "
                    "definition if the review suggests a fairer risk-peer "
                    "grouping. **Stop** the rollout immediately - and unwind "
                    "future-dated changes where legally possible - if the "
                    "fair-lending review or the pilot's own complaint/"
                    "attrition data raises a red flag.",
        "worked_example": "Illustrative, not live data: a customer in the "
                         "700-739 Credit Score Band is charged 18.9% while "
                         "their peer-cohort median is 21.2% (a 2.3-point "
                         "gap) and has held the account 3 years (past "
                         "first-year protection) -> flagged "
                         "REPRICE_TO_PEER_MEDIAN, target 21.2%, new "
                         "transactions only, 45-day notice required. The "
                         "naive, zero-elasticity ceiling on their $4,000 "
                         "revolving balance is roughly $92/yr (2.3pts x "
                         "$4,000) - the maximum possible value if this one "
                         "customer changed nothing in response, not a "
                         "prediction.",
        "checklist": [
            "Exclude any account still in its CARD Act first-year protection",
            "Run the fair-lending review of the selection BEFORE drafting notices",
            "Confirm the repricing worklist applies to new transactions only",
            "Draft the 45-day CARD Act notice",
            "Design the champion/challenger split with a true control",
            "Track attrition and revolve-behavior in both arms for several cycles",
            "Re-run the four-fifths fairness test on the actual post-rollout population",
            "Hold the scale decision until both the pilot results and the "
            "fair-lending review are clean",
        ],
        "constants": {"PRICING_GAP_POINTS": 2.0, "FIRST_YEAR_MONTHS": 12},
    },
]

REQUIRED_LEVER_FIELDS = [
    "code", "icon", "name", "module", "speed", "gate", "problem",
    "why_it_matters", "population", "data_needed", "actions", "sequence",
    "teams", "approvals", "testing", "kpis", "risks", "evolution",
    "worked_example", "checklist", "constants",
]
