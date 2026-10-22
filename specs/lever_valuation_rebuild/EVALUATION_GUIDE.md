# Evaluation guide: lever valuation rebuild and per-lever pages

Branch: `feature/lever-valuation-rebuild` (not merged to `main`, not deployed).
Method: `docs/LEVER_METHODOLOGY.md`. Spec: `SPEC_lever_valuation_rebuild.md` in this folder.

This guide tells an evaluator how to run the app locally, which data to load,
and, for each lever, what to check, the figure to expect, three customers to
open in the drill-down, and a sign-off checklist. Every figure below was
produced by the engine on this branch and checked by the commands in
section 2. None is typed in by hand.

---

## 1. Set up and run

```bash
git checkout feature/lever-valuation-rebuild
```

```bash
pip install -r app/requirements.txt
```

```bash
streamlit run app/Home.py
```

Open http://localhost:8501. Python 3.13 is what this branch was built and
tested on (Streamlit 1.54).

**Move between pages with the sidebar.** Typing a page URL into the
address bar starts a new Streamlit session, and the loaded portfolio is
gone (you will see "Run an analysis from the Home page first").

### Which data to load

| Source | How | What it is for | Time |
|---|---|---|---|
| **5k sample, live** | Sidebar **1 · Load a portfolio** → upload `samples/demo_portfolio.zip` → **Run analysis** | **The main evaluation.** The engine runs live; every customer example in section 4 is from this portfolio | ~10 s engine time locally |
| 50k sample, pre-computed | Sidebar → **Try it with the bundled sample portfolio** | The one-click demo. Same pages, pre-computed | ~2 s |
| 100k fixture, pre-computed | Sidebar **2 · Or load pre-computed results** → upload the 100k bundle → **Load bundle** | Scale and memory check | ~3 s after upload |

All three run under the **Case A (SLR, Category III)** leverage regime,
which every lever page shows as a read-only label. The STATUS.md "5k demo"
column is the audit fixture under Tier 1. Its L2 figure is $1,218 lower
because Tier 1 charges no leverage capital on unused lines.

The 100k bundle is not committed (187 MB). Build it from a 100k portfolio
with:

```bash
python engine/export_bundle.py --data <100k portfolio dir> --out bundle_100k_v2.zip --leverage-policy case_a_slr_category_iii --label "100k synthetic test fixture"
```

That takes about 3.5 minutes. To make the 100k portfolio itself, use
`python -m generator.run` with 100,000 customers and 36 months. That takes
much longer, so reuse an existing one where you can.

---

## 2. Automated checks (run these first)

```bash
python audit/audit_lever_estimates.py --bundle-100k <path to bundle_100k_v2.zip>
```

Expected output, as last run: **`279/279 CHECKS PASSED`**, on the 5k demo
(live pipeline) and the 100k bundle. It checks:

- every lever's components, totals and extras against the reference
  implementation (±0.5%; L4 ±15%, with totals judged on gross);
- the invariants;
- that every assumption moves the output;
- that per-customer contributions add up to the lever's components;
- that the "How it's calculated" steps equal the components;
- that the negative-control gate gives the same verdict under low, base and
  high.

Use `--skip-100k` for the 5k half only: 142 checks, about 1 minute.

---

## 3. Pages and layout (check once)

**Sidebar groups**

- **Overview:** Home, Portfolio Economics.
- **Strategies:** Strategy Overview, then L1–L6 (one page per lever).
- **Governance & Outputs:** Governance & Fairness, Downloads.
- **Reference:** Lever Playbook.

**What moved:**

- Liquidity, Leverage Capital and ML Credit Limit are now tabs on the **L2** page.
- ML fairness is on **Governance & Fairness**, linked from L2.
- Acquisition cost and payback is a tab on the **L6** page.

**Every lever page has two parts.**

*Overview & value*, in order:
1. What the lever does, with a link to the Playbook.
2. Who is in scope: the plain-English rules and the count by action.
3. What it could be worth: low, base and high. Each component carries a
   value type and a basis (measured or assumption), and anything
   assumption-based is marked "pilot required".
4. Assumptions: read-only, straight from `engine/config/lever_assumptions.json`.
5. What-if explorer: sliders that never change the configured figures.
6. "How it's calculated": every formula with this portfolio's numbers.
7. Regulation and safeguards.

*Customer drill-down*:
- A worklist with search, filters, sort and a CSV of the filtered view.
- A selected-customer panel with:
  - the profile, and the rules met or not met;
  - the recommended action and proposed change, and the calculation trace;
  - other levers the customer is in, with any **"review together"** flags;
  - protections and gates, and the data limitations;
  - the full economic workup;
  - admin review notes.

Review notes live in the browser session only. They are labelled "review
notes, not an approval or audit record" and can be downloaded as a CSV.

**Strategy Overview** has one table covering all six levers: customers,
actions, base and low–high value, value types, evidence and readiness. It
links to each lever page. Expected portfolio total on the 5k (Case A),
L1+L2+L3+L4+L6:

| | Low | Base | High |
|---|---:|---:|---:|
| 5k sample (live) | $56,347 | **$99,012** | $134,534 |
| 50k sample | $515,881 | **$933,804** | $1,277,612 |
| 100k fixture | $1,014,502 | **$1,863,622** | $2,559,031 |

L5 is never in these totals.

**Global checks**
- [ ] No dead links in the sidebar or the in-page links. None of the removed
      controls has come back: the generator link, the Clear cache button,
      the negative-control upload, or the leverage-regime dropdown.
- [ ] Only masked IDs (`CUS…`) appear anywhere.
- [ ] Every assumption-based figure says "pilot required". Nothing is
      described as a forecast.

---

## 4. Per lever

Base figures are year 1, Case A. "In scope" is the worklist size. Example
customers are on the **5k sample**. Type the ID into "…or type any masked
ID" on that lever's **Customer drill-down** tab. The values shown are the
expected values under base assumptions, as the page says. They are not
predictions for that customer.

How the examples were chosen (`pick_examples.py`, using the drill-down's own functions):
- **Typical:** in the lever's most common action, with a value nearest
  that action's median.
- **Borderline:** the in-scope customer closest to not being worth acting
  on: the smallest non-zero value. For L3, the smallest APR gap.
- **Joint review:** the first customer carrying a "review together" flag
  for this lever. L4 and L6 have no review-together pair, so for those it
  is the customer who appears in the most levers.

### L1 Rewards & Promo Economics

| | In scope | Low | **Base** | High |
|---|---:|---:|---:|---:|
| 5k | 828 | $36,305 | **$52,111** | $58,069 |
| 100k | 16,321 | $680,465 | **$997,815** | $1,110,310 |

The 5k base is made of:

| Component | Base |
|---|---:|
| Fee revenue | $24,144 |
| Downgrade reward saving | $23,448 |
| Card profit lost on closures | −$4,692 |
| Group 1 programme saving | $9,211 |

251 worklist customers (Group 2b) carry $0 because they are not offered the
fee: their reward cost doesn't cover it twice.

**What to check**

- Group 2a eligibility is reward cost ≥ 2.0 × the $95 fee, i.e. $190.
- The closure-risk view (if closers leave the bank) is shown next to the base.
- There is a fee-sensitivity chart.

| Example | ID | What you should see |
|---|---|---|
| Typical | `CUS0002764` | Group 2a. Reward cost $432 ≥ $190; NEP $1,346. Trace: 0.65 × $95 = $61.75 fee + 0.25 × 0.5 × $431.88 = $53.98 downgrade − 0.1 × $168.99 = −$16.90 closure → **$98.84**. Also in L3 |
| Borderline | `CUS0003068` | Reward cost $222, only just over $190. Its higher card profit ($882.95) makes the closure term −$88.30 → **$1.24**. Also in L2 (increase) |
| Joint review | `CUS0000036` | **L1 + L5: review together** (a new fee for a high-value customer showing a leave signal). **$86.10**. Also in L2 increase |

- [ ] Base, low and high match the table above.
- [ ] All three examples show the stated rules, trace and total.
- [ ] Fee changes cite Reg Z (45 days' notice, right to reject).

### L2 Credit Lines & Unused-Line Cost

| | In scope | Low | **Base** | High |
|---|---:|---:|---:|---:|
| 5k | 2,870 | $19,934 | **$36,209** | $53,676 |
| 100k | 56,892 | $365,273 | **$676,637** | $1,016,764 |

The 5k base is made of:

| Component | Basis | Base |
|---|---|---:|
| Decrease: credit loss avoided | measured | $8,915 |
| Decrease: liquidity avoided | measured | $7,021 |
| Decrease: SLR capital freed | measured | $1,345 |
| Increase: interest | assumption | $25,223 |
| Increase: funding cost | assumption | −$5,292 |
| Increase: extra credit loss | assumption | −$4,344 |
| Increase: extra SLR capital | assumption | −$127 |
| Reactivation, net | assumption | $3,468 |

989 deepen-relationship customers carry $0 by construction (no limit change).

**What to check**

The page has four tabs: Overview & value; Unused-line carrying cost (the
formulas come from the active policy files); ML second opinion with
L2-vs-ML agreement; and Customer drill-down.

- The regime label is read-only, and there is no dropdown.
- The negative-control gate uses the decrease side only. This was agreed
  during the build; see STATUS.md.

| Example | ID | What you should see |
|---|---|---|
| Typical | `CUS0003102` | REACTIVATION_CAMPAIGN (dormant): 100% inactive months, $10,250 limit. Trace 0.06 × ($62.76 − (−$55.99)) − $2.0 → **$5.13** |
| Borderline | `CUS0000505` | Also dormant, but its own card_net is $29.28, so reactivation barely pays: 0.06 × ($62.76 − $29.28) − $2 → **$0.01** |
| Joint review | `CUS0000094` | DECREASE_LIMIT (idle): $6,000 → $1,449, a cut of $4,551. Credit loss $11.01 + liquidity $7.28 + SLR $1.75 → **$20.04**. **L2 + L5: review together** |

- [ ] Figures match.
- [ ] The decrease customer shows the Reg B adverse-action notice.
- [ ] The ML compare shows agree or disagree for the selected customer.
- [ ] The ML fairness link goes to Governance & Fairness.

### L3 Value-Based Pricing

| | In scope | Low | **Base** | High |
|---|---:|---:|---:|---:|
| 5k | 179 | $1,978 | **$2,108** | $2,537 |
| 100k | 3,556 | $6,677 | **$20,968** | $35,006 |

The 5k base is made of:

| Component | Base |
|---|---:|
| Extra interest | $1,424 |
| Card profit lost | +$729 (positive: on the 5k, the expected leavers are on average loss-making) |
| Notices | −$45 |

134 flagged customers carry $0 because they pay in full: they are flagged
but not targeted. First-year accounts are excluded (CARD Act).

**What to check**

- Only revolving balance earns the gap.
- Year 1 counts only the share of balance repriced within the year.
- A steady-state figure is shown separately.

| Example | ID | What you should see |
|---|---|---|
| Typical | `CUS0003478` | 21.36% vs a peer median of 25.21% (3.85 pts); 68 months; revolving $1,007. Extra interest $16.07 − card profit $2.51 − notice $1.00 → **$12.56** |
| Borderline | `CUS0004236` | Gap exactly **2.00 pts**, right at the ≥ 2.0 threshold. Revolving $2,722: extra interest $22.54, card profit lost −$16.50, notice −$1 → **$5.04** |
| Joint review | `CUS0000525` | Gap 2.17 pts. A loss-making card (card_net −$155.29), so its expected leaving is a gain (+$12.42) → **$28.10**. **L2 + L3: review together** (limit increase and reprice at once) |

- [ ] Figures match.
- [ ] Pay-in-full and first-year customers are visibly not targeted.
- [ ] The CARD Act protections are listed.
- [ ] On the 100k bundle, `CUS0000363` is an example of an individual
      reprice with a **negative** expected value (−$70.82). That is
      expected, and the page should not hide it.

### L4 Cost-to-Serve Migration

| | In scope | Low | **Base** | High |
|---|---:|---:|---:|---:|
| 5k | 2,779 | $893 | **$5,178** | $9,065 |
| 100k | 57,437 | $17,046 | **$104,516** | $183,668 |

The 5k base is made of:

| Component | Base |
|---|---:|
| Calls moved to self-service | $1,821 |
| Paper moved to electronic | $4,746 |
| Year-1 outreach | −$1,390 |

**What to check**

- The correction bridge from the pre-rebuild figure: $62,829 → … → $5,178.
- Year 1 vs year 2 (no outreach cost).
- The staffing step is shown for information only and is never counted.
- Customers are selected on the **full data window**, but valued on the
  **trailing 12 cycles**, net of the digital cost (unit costs from the
  cost pools).

| Example | ID | What you should see |
|---|---|---|
| Typical | `CUS0000004` | ENABLE_SELF_SERVICE: 4 avoidable calls over the window (≥ 3), 2 in the last 12 cycles. Trace 2 × 0.35 × 0.90 × $2.04 = $1.29 − outreach $0.50 → **$0.79** |
| Borderline | `CUS0002965` | MIGRATE_TO_DIGITAL_STATEMENTS: 26 paper statements over the window, only 2 in the last 12 cycles. 2 × 0.5 × 0.9 × $0.69 = $0.62 − $0.50 → **$0.12** |
| Joint review | `CUS0000203` | L4 is in no review-together pair. This customer is in L1, L2, L4, L5 and L6: $1.29 calls + $3.73 paper − $0.50 → **$4.51**. Check that "Other levers" lists all five and raises no flag for L4 |

- [ ] Figures match.
- [ ] The bridge shows each correction step.
- [ ] The staffing step is excluded from the total.

### L5 Retention Targeting (unpriced)

| | In scope | Value at risk | Conditional low | **Conditional base** | Conditional high |
|---|---:|---:|---:|---:|---:|
| 5k | 363 | $392,703 | −$10,864 | **−$313** | $10,507 |
| 100k | 7,818 | $9,212,532 | −$228,687 | **$8,346** | $253,471 |

Base break-even keep rate on the 5k is **20.8%** (configured keep rate 20%).

**What to check**

- The page says "Unpriced" at the top, and L5 is in no total anywhere.
- Value at risk by signal.
- Historical leave rates are shown next to the configured 10%, and never
  overwrite it: 7.1% a year for Valued/Premier, and 13.7% within 12 months
  of a closure request, on the 5k.
- The break-even table.

| Example | ID | What you should see |
|---|---|---|
| Typical | `CUS0004393` | Valued; priced above peers (21.14% vs 18.64%, +2.50 pts). Value at risk $939.78; kept $18.80 − outreach $10 − offer $12.50 → **−$3.70**; break-even keep rate **23.9%** |
| Borderline | `CUS0002503` | Premier; spend declining. Value at risk $1,123.32 → **−$0.03**, almost exactly break-even (**20.0%**) |
| Joint review | `CUS0000036` | Valued; spend declining. Value at risk $757.59 → **−$7.35**; break-even **29.7%**. **L1 + L5: review together** |

- [ ] Figures match.
- [ ] The break-even rate shows as a percentage, not a dollar figure.
- [ ] Nothing on the page calls the conditional figure a forecast.

### L6 Channel Quality Review

| | In scope | Low | **Base** | High |
|---|---:|---:|---:|---:|
| 5k | 916 | −$2,763 | **$3,407** | $11,187 |
| 100k | 19,138 | −$54,959 | **$63,686** | $213,283 |

The 5k base is made of:

| Component | Base |
|---|---:|
| Profit lost in the worst channel (aggregator) | −$10,275 |
| Profit gained in the best channel | $13,682 |

**What to check**

- Valued at **channel** level, as a budget-neutral shift of future
  acquisition spend. The existing book is never touched, and there is no
  per-customer contribution.
- The multi-year build and a break-even quality figure are shown.
- The acquisition cost and payback tab.
- The worst channel on the page matches the worklist's channel (aggregator).

| Example | ID | What you should see |
|---|---|---|
| Typical | `CUS0000083` | Aggregator, ranked 5 of 5 ($158 per customer, NEP − CAC). Own NEP $285.10 and CAC $229.01, against channel means of $435.37 / $226.39 = 1.92x per CAC dollar. Per-customer contribution is blank by design |
| Borderline | `CUS0004748` | NEP $0.00: in scope only because of the channel, which shows selection is channel-level |
| Joint review | `CUS0000203` | L6 is in no review-together pair. A highly profitable aggregator customer (NEP $1,301.68) who is in five levers. Confirms L6 recommends nothing for this customer's own account |

- [ ] Figures match.
- [ ] Per-customer contribution is blank, with the channel-level caption.
- [ ] "Backward-looking and correlational" is stated.

---

## 5. Memory and scale (measured on this branch)

Two kinds of number are below. The **real-server** figures come from a
Streamlit server driven from a browser. The **AppTest** figures come from
one process rendering every page against the bundle. Both are Windows peak
working set. Linux RSS on a host may differ somewhat.

| | Steady state, lever pages | Peak |
|---|---:|---:|
| 100k bundle, real server (upload + load + all six lever pages) | 1,455–1,548 MB | **~2,090 MB**, for about 1 s while the ledger table is decoded |
| 100k bundle, AppTest, every page incl. Downloads | 1,313–1,373 MB | 1,777 MB |
| 50k sample (Try it), real server | 771 MB | 986 MB |
| 50k sample, AppTest, every page | 767–795 MB | 1,002 MB |

A second session pressing Try it adds 0 MB, because the sample is shared.

So on a **2 GB** instance:
- The lever pages fit the 100k bundle in steady state with about 500 MB to spare.
- The one-second load peak is right at the limit.
- The 50k Try it path fits comfortably.

`render.yaml` sets **`plan: free` (512 MB)**, which the 50k sample cannot
fit. See STATUS.md.

---

## 6. Sign-off

| Lever | Figures match | Examples checked | Regulation shown | Evaluator | Date | Notes |
|---|---|---|---|---|---|---|
| L1 | | | | | | |
| L2 | | | | | | |
| L3 | | | | | | |
| L4 | | | | | | |
| L5 | | | | | | |
| L6 | | | | | | |
| Global (section 3) | | | | | | |
| Audit, 279/279 (section 2) | | | | | | |
