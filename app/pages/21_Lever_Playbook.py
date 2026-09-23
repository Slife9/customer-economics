"""A reference page, independent of whatever portfolio is loaded: what each
lever is, why it's built the way it is, and the real-world banking and
regulatory context behind it. The Levers & Strategy page shows this quarter's
live numbers; this page explains the machinery underneath them.
"""
from __future__ import annotations
import streamlit as st

st.set_page_config(page_title="Lever Playbook", page_icon="📖", layout="wide")
st.title("📖 Lever Playbook")
st.caption("How each lever thinks, why it's built that way, and how it maps "
          "to real US banking practice. This page doesn't depend on any "
          "uploaded data — it's the reference, not the report.")

st.divider()
st.header("Core concepts, before the six levers")

with st.expander("What does 'net economic profit' actually mean?", expanded=True):
    st.markdown("""
Revenue the customer generates (interest, interchange, fees, and — if they
hold other products — deposit and loan value) **minus every real cost**:
what we pay out in rewards, the cost of funding the money we lend, expected
credit losses, the cost of servicing the account, and the capital we're
required to hold against it. Not revenue. Not "contribution margin" with
some costs left out. Everything, netted to one number, per customer, per
month.

Most banks can tell you a customer's revenue. Very few can tell you this
number, because the pieces usually live in different systems (risk, finance,
operations, capital) that were never joined at the customer level. That join
is most of what this system does.
""")

with st.expander("Why does suppression happen before anything else?"):
    st.markdown("""
Customers in **hardship, on an accommodation plan, or covered by SCRA**
(the Servicemembers Civil Relief Act) are removed from the population
**before** any lever, any score, or any routing decision touches the data —
not flagged and reviewed afterward. This is enforced in the code itself: a
lever physically cannot receive a customer list that hasn't been through
suppression first.

The reasoning: a customer in genuine financial difficulty often *does*
generate high servicing cost and *does* look unprofitable — but that's an
obligation the bank has taken on, not a leakage problem to be optimized
away. Treating vulnerability as a cost-cutting opportunity is exactly the
kind of finding this system is built to never produce.
""")

with st.expander("Why are some levers priced and others say 'None'?"):
    st.markdown("""
Every lever's value falls into one of two honest categories:

- **Priced** — a real dollar figure, calculated from data that already
  exists (what customers already did). Line management's expected-loss
  savings is priced this way: it uses the same risk model the bank already
  trusts, just applied to a smaller credit line.
- **None, with unpriced context** — used whenever the true value depends on
  how a customer would *respond* to something we've never actually done to
  them (would they accept a new fee? would a retention call change their
  mind? would they spend more at a higher rate?). No historical dataset can
  honestly answer a question about a treatment that was never tried. Rather
  than guess, the system reports **`None`** for the priced value and gives
  you context instead — like the size of the opportunity, or the value at
  risk — clearly labeled as context, not a forecast.

The only way to turn a `None` into a real number is to actually run the
test: a **champion/challenger pilot**, where a small group gets the new
treatment and a control group doesn't, and you measure the real difference.
""")

with st.expander("What do 'Fast', 'Slow', and 'Pilot required' mean?"):
    st.markdown("""
This is about how soon a lever could realistically go into production — not
how good the finding is.

- **Fast** — no customer contact is needed, or if there is, no mandatory
  notice period stands in the way. You could start next week.
- **Slow** — the finding is real, but federal law requires a notice period
  and/or a fair-lending review before you can act (e.g., a 45-day notice
  before changing a fee or a rate). That's calendar time you can't shortcut,
  regardless of confidence in the analysis.
- **Pilot required** — a different kind of caution: we genuinely don't know
  what will happen, because it depends on a customer's reaction to a
  treatment that's never been tried. The only responsible path is a small
  controlled test before scaling anything.

**Why sequence by this instead of by lever number:** the fast levers prove
real, verified savings within a quarter with almost no friction, which is
exactly the track record that makes it easier to get sign-off later for the
slower, higher-permission levers. Starting with the slowest lever first is
faster on paper and stalls in legal review in practice.
""")

st.divider()
st.header("The six levers")

LEVERS = [
    {
        "code": "L4", "icon": "⚙️", "name": "Cost-to-Serve Migration",
        "speed": "Fast", "gate": "None",
        "problem": "Some customers generate avoidable servicing cost - calls "
                  "that a self-service option could have handled, paper "
                  "statements when digital would do, collections contacts "
                  "that scale with headcount.",
        "population": "Customers routed here because servicing cost is their "
                      "single dominant cost, plus anyone with meaningfully "
                      "high avoidable-call volume or persistent paper "
                      "statement delivery, whether or not they're currently "
                      "a loss.",
        "sizing": "Priced. The key detail: servicing costs are stepped, not "
                 "smooth - a call center runs on headcount bands, so "
                 "avoiding calls only saves real cash once enough volume is "
                 "avoided to cross a staffing threshold. Below that, only "
                 "the marginal per-call cost (the actual variable expense, "
                 "not the full allocated cost) is counted as savings. This "
                 "is deliberately conservative - claiming the full unit "
                 "cost of an avoided call is a mistake a real CFO would "
                 "correctly reject.",
        "gate_detail": "None - no customer permission needed, nothing about "
                       "their account terms changes.",
        "analog": "Every large bank runs 'digital deflection' programs for "
                 "exactly this reason - it's usually the single largest, "
                 "fastest-to-prove cost lever in retail banking.",
    },
    {
        "code": "L2", "icon": "📈", "name": "Line Management by Value",
        "speed": "Fast (decreases) / Moderate (increases)",
        "gate": "Reg B adverse action notice on any decrease",
        "problem": "A credit line can be wrong in either direction: far more "
                  "than a customer will ever use (unnecessary risk exposure "
                  "we don't need to carry), or too tight for a customer who "
                  "would spend more given room.",
        "population": "This is the lever with the most domain nuance built "
                      "in, because a single month's utilization snapshot "
                      "lies: a disciplined customer who spends heavily and "
                      "pays to zero every month looks identical to a "
                      "genuinely idle account if you only check the ending "
                      "balance. The system instead looks at AVERAGE and "
                      "PEAK utilization over 12 months, actual spend "
                      "relative to the limit (a full-pay customer can cycle "
                      "well over 100% of their limit in annual spend while "
                      "showing 0% ending balance), how many of the last 12 "
                      "months they behaved as a transactor vs. sat "
                      "inactive, and how long the account has been open "
                      "(a line isn't touched before 12 months of history "
                      "exists to judge it by). This produces four distinct "
                      "outcomes, not one: DECREASE (genuinely idle), ENGAGE "
                      "(dormant - a reactivation candidate, never a cut "
                      "candidate), DEEPEN RELATIONSHIP (an active, valuable "
                      "pay-in-full customer - explicitly NOT touched), and "
                      "INCREASE (genuinely stretched, good standing).",
        "sizing": "Priced. Decreases are sized on expected-loss avoided "
                 "(recomputing loss exposure at a lower limit, using the "
                 "SAME risk model the bank already trusts) - never on "
                 "capital relief, because under US rules an undrawn card "
                 "line is unconditionally cancellable and carries a 0% "
                 "capital charge already (12 CFR 217.33(b)(1)). Trimming an "
                 "idle line frees no regulatory capital, full stop - any "
                 "vendor claiming otherwise for a US issuer is wrong. "
                 "Increases are sized against what a similar-risk peer "
                 "typically uses, not a prediction of this specific "
                 "customer's future behavior.",
        "gate_detail": "A decrease legally requires sending the customer an "
                       "adverse action notice (Reg B) explaining why. "
                       "Increases require no notice.",
        "analog": "Standard line management is universal in card issuing; "
                 "the multi-signal 'don't just look at one month' "
                 "discipline here matches how a mature risk/marketing team "
                 "would actually build this internally.",
    },
    {
        "code": "L6", "icon": "🧭", "name": "Channel Quality Review",
        "speed": "Fast", "gate": "None",
        "problem": "Not every acquisition channel brings in equally valuable "
                  "customers - a channel can look cheap per account and "
                  "still be expensive per dollar of value delivered.",
        "population": "Ranks acquisition channels (branch, digital, "
                      "aggregator, partner, direct mail) by the average "
                      "customer value they've actually produced, net of "
                      "what it cost to acquire them - then flags accounts "
                      "acquired through the weakest-performing channels for "
                      "a spend-reallocation review.",
        "sizing": "Priced, but explicitly correlational, not causal: it's a "
                 "backward-looking comparison of channels already run, not "
                 "a promise that shifting volume to a better channel would "
                 "reproduce the same result at the same cost. This is a "
                 "deliberate scope decision - a true prediction of 'how "
                 "many customers a given channel WOULD deliver' is exactly "
                 "the kind of untested-treatment question this system "
                 "refuses to invent an answer to.",
        "gate_detail": "None - this is a media/sourcing budget decision, "
                       "not something any individual customer experiences.",
        "analog": "Marketing attribution and channel-quality analysis is "
                 "standard practice in acquisition marketing; tying it to "
                 "fully-costed customer value (not just volume or CAC "
                 "alone) is the upgrade most teams haven't made yet.",
    },
    {
        "code": "L1", "icon": "🎁", "name": "Rewards & Promo Economics",
        "speed": "Slow", "gate": "Reg Z: 45 days notice + right to reject",
        "problem": "Some customers take out more reward value every year "
                  "than the relationship earns back - and the strongest "
                  "fix is usually not cutting the rewards program, it's "
                  "charging a fee that matches the value already being "
                  "delivered.",
        "population": "Customers routed here because reward cost is their "
                      "dominant loss driver, plus a separate and arguably "
                      "more important group: profitable customers taking "
                      "meaningful reward value every year while paying no "
                      "annual fee at all - an opportunity, not a loss.",
        "sizing": "None, by design. Whether a customer would accept a new "
                 "fee versus close the account is a behavioral response to "
                 "a change we haven't made yet - a textbook untested-"
                 "treatment question. What IS reported: the dollar value of "
                 "reward cost currently being delivered for free, as "
                 "context for a fee decision, never as a revenue forecast.",
        "gate_detail": "Reg Z requires 45 days' written notice before "
                       "introducing or increasing a fee, and gives the "
                       "customer the right to reject it (usually by closing "
                       "the account under the old terms).",
        "analog": "Card issuers already do this - premium travel cards are "
                 "explicitly funded by a mix of annual fee, interest, and "
                 "interchange BECAUSE rewards alone don't pay for "
                 "themselves; measuring rewards against interchange alone "
                 "makes a healthy premium program look broken.",
    },
    {
        "code": "L5", "icon": "🛟", "name": "Retention Targeting",
        "speed": "Pilot required",
        "gate": "None to flag risk; a pilot before acting on it",
        "problem": "Retention budget is a scarce resource and should go to "
                  "the customers actually worth keeping - not by balance or "
                  "tenure, but by real economic value.",
        "population": "High-value customers (Valued/Premier band) showing "
                      "at least one OBSERVABLE warning sign: a recent "
                      "closure-request contact, a meaningful spend decline, "
                      "or a price position well above what similar-risk "
                      "peers are charged. Deliberately built from signals "
                      "the bank can actually see - never a hidden trait the "
                      "system has no legitimate way to know.",
        "sizing": "None, by design - retention uplift from an intervention "
                 "is precisely a causal question about a treatment never "
                 "applied, and no historical dataset answers that "
                 "honestly. What's reported instead is VALUE AT RISK: what "
                 "these customers are worth today, if nothing changes - a "
                 "fact about the present, not a prediction of what an "
                 "intervention would recover.",
        "gate_detail": "No regulatory gate - the caution here is purely "
                       "about honesty in what can be claimed, not "
                       "compliance.",
        "analog": "Every retention/loyalty team in banking runs some "
                 "version of a save desk; the discipline here is refusing "
                 "to claim a save rate until a real champion/challenger "
                 "test has actually measured one.",
    },
    {
        "code": "L3", "icon": "💲", "name": "Value-Based Pricing",
        "speed": "Slowest",
        "gate": "CARD Act (no year-1 increase, new-transactions-only, 45 "
               "days notice) + fair lending review + a pilot",
        "problem": "A customer's risk drifts after the account is opened, "
                  "but the interest rate they were given at origination "
                  "usually doesn't - so pricing gradually falls out of line "
                  "with the actual cost of serving that customer.",
        "population": "Any account priced meaningfully below its own "
                      "current-risk peer group - customers of similar score "
                      "and product tier who are being charged a "
                      "meaningfully higher rate today - not only the ones "
                      "already showing a loss.",
        "sizing": "None, by design - repricing value depends entirely on "
                 "how customers respond (would they revolve less, would "
                 "they leave), which is a causal question this system will "
                 "not invent an answer to. The context figure shown is a "
                 "ZERO-ELASTICITY CEILING: what the pricing gap is worth "
                 "if literally every customer stayed and paid it - "
                 "explicitly the maximum possible number, not a realistic "
                 "one.",
        "gate_detail": "The most regulated lever here: CARD Act bars any "
                       "rate increase in a customer's first year, requires "
                       "45 days' notice, applies only to future charges "
                       "(never the existing balance), and needs a fair "
                       "lending review of who gets selected before rollout.",
        "analog": "Risk-based repricing is standard in principle across "
                 "lending; the reason it's slow in practice everywhere, not "
                 "just here, is this exact stack of CARD Act protections.",
    },
]

for lever in LEVERS:
    with st.expander(f"{lever['icon']}  **{lever['code']} — {lever['name']}**  "
                     f"·  {lever['speed']}", expanded=False):
        st.markdown(f"**The problem it solves:** {lever['problem']}")
        st.markdown(f"**Who ends up in scope:** {lever['population']}")
        st.markdown(f"**How it's sized:** {lever['sizing']}")
        st.markdown(f"**Compliance gate:** {lever['gate_detail']}")
        st.markdown(f"**Where this shows up in real banking:** {lever['analog']}")

st.divider()
st.caption("For this quarter's actual numbers against these definitions, see "
          "**Levers & Strategy**. This page is the reference; that page is "
          "the report.")
