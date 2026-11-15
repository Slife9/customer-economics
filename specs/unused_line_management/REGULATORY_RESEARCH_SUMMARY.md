# Regulatory research summary (as verified, Nov 2026) and the working assumptions

Research was done with an AI with browsing access, using official primary sources (Federal Register,
eCFR, Federal Reserve, CFPB, FASB, BIS, EUR-Lex, PRA). **Confirm with the bank's compliance and
regulatory capital teams before external use.**

## A. Verified findings

| # | Topic | Finding | Source |
|---|---|---|---|
| 1 | March 2026 expanded risk-based proposal | Published 19 Mar 2026 (Doc. 2026-05959); comments closed 18 Jun 2026; **not final** as of 13 Nov 2026 | Federal Register |
| 2 | Scope | Mandatory for **Category I and II**; others may opt in | Proposal II.A–II.B |
| 3 | Card risk weights | **45% transactor, 75% non-transactor, 100%** other retail | Proposal IV.A.3 |
| 4 | Transactor definition | "balance has been repaid in full at each scheduled repayment date for the previous twelve months"; per facility; installment balances disqualify; **zero-balance dormant card not expressly covered** (Basel CRE20.66, EU CRR3 Art. 4(1)(152), PRA rules give no exception for credit cards; EU requires 12 months of repayment history) | Proposal IV.A.3; BIS; EUR-Lex; PRA |
| 5 | CCF | **10%** for unconditionally cancellable commitments (card lines generally qualify); other commitments 20/40/50/100% | Proposed §__.112(b) |
| 6 | Regulatory retail | **$1M** aggregate retail exposure per obligor and affiliates (incl. unfunded), CPI-indexed | Proposal IV.A.3 |
| 7 | Internal models | Advanced (IRB) approaches removed for credit and operational risk | Proposal II.B |
| 8 | Output floor | **None**; single expanded calculation | Proposal II.B, Q6 |
| 9 | Standardized proposal (non Cat I–II) | 27 Mar 2026 (Doc. 2026-05960): **keeps 0% CCF** for cancellable commitments; other-assets RW 100% → 90% | 91 FR 15332 |
| 10 | SLR | 10% CCF on cancellable commitments; 3% minimum; **applies to Category I–III** (217.10(a)(1)(v)); enhanced SLR (final, effective 1 Apr 2026) only for GSIBs and covered subsidiaries | 12 CFR 217.10; 90 FR 55248 |
| 11 | LCR | 5% outflow on **committed** retail facilities; **"committed" means not unconditionally cancellable**, so cancellable card lines are **not** committed | 12 CFR 249.3, 249.32(e)(1)(ii) |
| 12 | LCR scope | Cat I/II full; Cat III full or 85% (wSTWF); Cat IV 70% if wSTWF ≥ $50bn, else none | FRB BHC Supervision Manual 1060.20 |
| 13 | CECL | **No allowance** on unfunded unconditionally cancellable card lines | ASC 326-20-30-11; 326-20-55-54 to 56 |
| 14 | Reg B | Line decrease and closure can be adverse action (30-day notice); **actions in connection with inactivity, default or delinquency excluded** | 12 CFR 1002.2(c)(2)(ii), 1002.9 |
| 15 | Reg Z, decrease | 45 days before over-limit fee or penalty rate due to a lower limit; **no general prior notice** for the decrease | 1026.9(c)(2)(vi), (g)(4) |
| 16 | Reg Z, inactivity | Inactivity **penalty** fees prohibited; periodic fees disclosed at opening contemplated | 1026.52(b)(2)(i)(B); 1026.6(b)(2)(ii)(A) |
| 17 | Reg Z, increases | Ability-to-pay applies to limit increases on existing accounts | 1026.51(a)(1)(i) |
| 18 | FCRA | Score disclosure if FCRA adverse-action conditions are met and a bureau-based numerical score was used | FCRA §615 |
| 19 | Rewards | No federal reward-specific notice period; UDAAP per CFPB Circular 2024-07 | CFPB |
| 20 | Annual fees | 45-day significant-change notice; right to reject (with exceptions); renewal notice 30 days or one cycle (1026.9(e)); first-year limits (1026.55, 1026.52(a) 25% cap) | Reg Z |

## B. Working assumptions that deliberately override current law (agreed)

| Topic | Current law | Working assumption used in the module |
|---|---|---|
| Risk-based CCF on card lines | 0% (and kept at 0% in the standardized proposal) | **10% for every card line, every bank** |
| Proposal status | Not final | **Treated as adopted, effective day one** |
| Card risk weights | 100% (current standardized) | **45% / 75% / 100%** per §A3–A6 |
| Dormant cards | Not addressed | **75%** (provisional; question sent to the boss) |
| LCR on cancellable card lines | No outflow (not committed) | **5% on all unused card lines** (conservative), cost at **0.75%** carry, Category I–III by default |
| SLR | Applies Cat I–III | **Not calculated**; risk-based capital assumed to bind |
| Operational risk | Bank-level framework | Excluded from account economics; note only |

Every output must carry the assumption label in `unused_line_assumptions.json`.
