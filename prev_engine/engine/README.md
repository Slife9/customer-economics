# ProfitInsight Synthesis Engine

Generates demo portfolios for the customer economics system.

```bash
python run.py --profile default          --out ./out/demo
python run.py --profile negative_control --out ./out/negative_control
python validate/check.py       --data ./out/demo
python validate/circularity.py --root ./out
```

---

## The rule this engine is built around

**Generate causes. Never generate effects.**

Nothing here is named after anything the analytical engine reports. There is no
`n_unprofitable_customers` dial, no `underused_limit_count`, no `leakage_target`.
Profitability, underused limits, mispricing and cost concentration emerge from
latent customer traits meeting bank policy, or they do not emerge at all.

Three content types, handled differently:

| Type | What | How |
|---|---|---|
| **A** — discrete defects | wrong earn rule, interchange below card, fee never posted, rate below contract | planted, recorded in `_ground_truth/`, detectable only from evidence |
| **B** — emergent economics | who is unprofitable, which limits are idle, which programmes fail | never set; falls out of latents × policy |
| **C** — behavioural response | retention uplift, attrition on a rewards cut, price elasticity, cross-sell take-up | **not generated at all** |

Type C is deliberately absent. Those are causal questions about treatments that
were never applied. Synthesising them means inventing the answer and then
measuring your own invention. They come from a pilot's champion/challenger
design. A named gap survives model risk review; a fabricated elasticity does not.

---

## Architecture

```
config/
  mcc_catalog.csv              merchant categories
  interchange_rate_card.csv    rate by product tier x category  (contractual schedule)
  reward_rules.csv             base rate, bonus categories, caps  (published rule)
  redemption_channels.csv      cost per point by channel  (real money)
  benchmarks.yaml              realism ranges  <-- ALL UNVERIFIED, need citations

synth/
  latents.py       10 latent traits per customer         THE CAUSES
  policy.py        underwriting, limit, pricing, fee     THE BANK'S RULES
  transactions.py  spend, MCC from persona, interchange looked up from the card
  rewards.py       earn by rule, redeem by propensity, expire, carry liability
  cycles.py        balances, delinquency, CECL, US capital, cost drivers, defects

validate/
  check.py         Layer 1 consistency + Layer 2 realism
  circularity.py   negative control and variant comparison
```

**Latents and policy never see each other.** A real bank cannot observe credit
appetite either — that is precisely why it grants limits people do not use.

---

## What is measured, not set

These are computed from generated behaviour and reported in `build_manifest.json`:

- **blended reward earn rate** — earn rules applied per transaction via MCC
- **breakage** — produced by the expiry mechanism, not a parameter
- **effective interchange rate** — looked up from the rate card, never drawn

If any of these becomes an input, the engine has broken its own rule.

---

## Ground truth

`out/<profile>/_ground_truth/` — evaluation only, never joined into anything the
analytical engine reads.

- `Latent_Ground_Truth.csv` — the latent vector per customer
- `Defect_Ground_Truth.csv` — planted Type A failures with mechanism and impact

Layer 1 asserts that no latent or defect marker leaks into a published table.

---

## Validation, two layers

**Layer 1 — consistency (23 checks).** Keys join, balances are coherent, capital
follows 12 CFR 217 subpart D, CECL carries no IFRS 9 staging, ground truth
stays outside the published tables.

**Layer 2 — realism (15 checks).** Compares aggregates against published US
industry ranges. This is the layer that catches a dataset which is internally
perfect and externally absurd — a flat interchange rate, every programme earning
identically, a fee schedule contradicting the fee data. The previous dataset
passed 120 internal checks while carrying all three.

> **Every benchmark in `config/benchmarks.yaml` is marked `source: UNVERIFIED`.**
> They are indicative ranges only. Before this suite is relied on, each must be
> checked against a current published source and the citation written into the
> `source` field. Several of these figures move year to year. A benchmark
> without a citation is an opinion.

---

## Circularity test

`validate/circularity.py` builds the case that findings track causes:

1. **Negative control** — a clean portfolio with nothing planted, limits sized to
   appetite, better payment discipline. Defect findings must vanish and
   policy-driven findings must fall.
2. **Below-cost floor** — the clean book must *still* carry unprofitable
   customers. Low-spend, high-service customers are structurally unprofitable
   whatever the bank does. If this went near zero the generator would be
   flattering the product.
3. **Variants** — transactor-heavy, subprime-heavy and premium-heavy books must
   produce materially different aggregates. A metric stable across all of them
   is an artifact of code.

One assertion in this suite was wrong on first run: it expected the clean book to
have far fewer below-cost accounts. It does not, and should not. The assertion
was corrected rather than the data tuned to satisfy it. That floor is one of the
more useful things the engine produces — it is the share no lever can remove.

---

## Stage 1 scope

Built: card portfolio end to end — customers, transactions with MCC,
differentiated interchange, rule-based reward earn, redemption with channel
costs, points liability and expiry, account cycles, CECL, US standardized
capital with a separate economic track, cost drivers with call reasons, stepped
cost pools, hardship and SCRA suppression fields, planted defects, latent ground
truth, both validation layers, negative control and three variants.

**Not yet built:** deposits and loans (Tables 6 and 7), instalment plans
(Table 5), the card table (Table 3), FTP curve generation (currently assumed
flat 5.05% in circularity only), fee schedule with versioning (Table 13),
waivers (Table 14), limit-change event history, attrition and closure events,
acquisition cost by channel.

The architecture carries all of these. Each is a module following the same
latents-meet-policy pattern.

---

## Before this is used for anything client-facing

1. Cite every benchmark in `benchmarks.yaml`.
2. Build the remaining tables listed above.
3. Point the actual analytical engine at `out/negative_control` and confirm it
   reports little. That is the real circularity test; this suite only proves the
   data differs, not that the engine behaves.
4. Verify the Reg Z late fee safe harbor structure before posting late fees — it
   has been actively litigated and the current amounts need checking.
