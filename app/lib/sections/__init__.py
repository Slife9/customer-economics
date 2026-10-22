"""Page sections that used to be whole pages, now rendered inside the lever
pages' tabs (lever pages restructure, feature/lever-valuation-rebuild):

  liquidity.render        was app/pages/23_Liquidity.py     -> L2 page, carrying-cost tab
  ml_credit_limit.render  was app/pages/25_ML_Credit_Limit.py -> L2 page, ML second-opinion tab
  ml_credit_limit.render_fairness  (ML treatment fairness)   -> Governance & Fairness page
  acquisition.render      was app/pages/22_Acquisition_Cost.py -> L6 page

Content is moved verbatim except that each early `st.stop()` became a
`return`, so a missing-data message inside one tab no longer halts the
other tabs of the same page.
"""
