"""L1 rewards profitability system.

A standalone model of the Reward Profitability Scenario Model v2 applied to a
portfolio's own data: screen the unprofitable reward accounts, assign them to
the model's segments, and value the nine reward levers under the model's
customer-response assumptions - per account, then by segment and scenario.

    assumptions.py   load the Excel-derived defaults (config/), apply edits
    data.py          one row per card account: measured trailing-12 P&L and
                     every input the segment rules need
    segments.py      the screen and the priority segment rules, with a
                     per-account rule trace for the drill-down
    model.py         the Excel scenario formulas, applied per account

It reads the engine's card ledger (engine.core.ledger) and never changes any
engine calculation or any of the six levers.
"""
