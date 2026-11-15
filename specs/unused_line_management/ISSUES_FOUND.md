# Issues found

Issues found while building the module that are outside its scope. None is fixed here; each is
recorded for the owner of the code concerned.

| # | Where | Issue | Action |
|---|---|---|---|
| 1 | `engine/levers/l2_lines.py` (all branches) | Expected loss avoided by a decrease uses lifetime PD as if annual (L1 branch: no annualisation; lever-valuation branch: divides by card life 3/2/1 years, so the high scenario is still lifetime-as-annual) | None; this module uses `PD 12 Month` |
| 2 | Rebuilt L2 page, `feature/lever-valuation-rebuild` | Carrying cost by group uses the old liquidity (4% yield gap) and leverage (SLR) logic, not brief §2 | Known issue on the other branch; no action |
| 3 | `engine/ml/` fairness test | Counts any ML action as "selected", increases included; the "5 metros on 100k" figure is text only (`STATUS.md` on the lever-valuation branch); 14 of 76 metros fail on the committed 50k bundle | Re-run in Stage 6 with module cuts and closures, ML adverse actions and ML increases separated (#10); shown on the app's regulatory page |
| 4 | `generator/run.py` on `main` | `--profile negative_control` crashes in `rewards.earn` (empty WRONG_EARN_RULE subset). Fixed on `fix/negative-control-generation`, not on `main` | Fix cherry-picked here (`891bda2`, from `966988a`); `negative_control` back in the byte-identity check, baselined from the fix branch's code |
| 5 | Generator realism check on `main` | 4 of 22 Layer 2 benchmarks out of range on the demo (transactor share, average utilisation, 90+ delinquency, net charge-off rate) | Pre-existing; unchanged by this module |
| 6 | Table3 `Card Status` | The last card of a closed or charged-off account stays `active` | Table30 reports activation status within the account's open period |
| 7 | Table3 `Deactivation Cycle Index` | −1 means both "never deactivated" and "deactivated in the cycle before the window" | Table30 uses `Card Status` to tell them apart |
| 8 | Engine card ledger `capital_cost` | The old charge (Table9, current rules) is larger than the brief §2 charge on drawn balances (5k demo: $223,879 vs $45,508 a year), so replacing it raises card profit | Replaced, never added (answer 4); reported on the drill-down |
| 9 | Table4 `Ending Balance` / `Utilization` | Measured after the cycle's payment, so a full payer shows $0 drawn at every month end | The module uses Ending Balance for exposure (the reporting-date balance); statement balance (Ending + Payment) for the segment rules and the calibration |
| 10 | Fairness (four-fifths by metro, geography proxy) | Stress book: module decreases and closures fail in 14 of 64 metros, ML adverse actions in 17 of 66, ML increases in 59 of 66 (only 9 increases in the book, so the rates are noise). 5k demo: 19 of 48, 21 of 55, 34 of 55 | Flagged on the regulatory page; a fair-lending review is needed before any pilot. Synthetic data: metro effects come from the generator's population draws |
| 11 | Engine cost split | `cost_to_serve_fixed_allocated` is about $17 per account (workbook fixed cost $30–60), so screened accounts have a negative variable contribution and attrition after a cut can add profit; transactor right-sizing does not lose money in system mode | Reported; transactor right-sizing kept out of recommendations |
| 12 | Workbook vs system-mode screen | Without the undrawn-line loss, the workbook's own Credit-Deteriorating segment earns +$85 per account, so the system-mode screen keeps only its loss-making minority | Reported in the Stage 4 calibration; the drawdown sensitivity toggle shows the effect |
| 13 | Generator memory at scale | Building the 100k per-account file peaks at 15.6 GB (every raw table loaded through the engine's ledger); the 100k portfolio generation itself is also memory-heavy | **Future improvement: chunked generation** (and a chunked per-account build). Not implemented; the app loads only precomputed samples (0.3–0.4 GB) |
| 14 | Calibration gaps (stress book) | 25 of 43 workbook metrics within ±25%; outside: loss per screened account, Credit-Deteriorating share / balance / utilisation / PD, Sock-Drawer share and balances, Transactor share / balance / utilisation / spend, Unassigned share, Relationship revolving balance | Explained per metric in `STAGE4_REPORT.md`; no further calibration work (answer 3) |
| 15 | Go / no-go basis | Base improves at 1.5× on the headline (card profit + avoided drawdown loss) but not on card profit alone | Both shown; basis in config (`levers.system_mode.headline_value`) |

## Expected merge clashes (for the future integration)

| File | Clash | Instruction |
|---|---|---|
| `generator/run.py` | The import block: `reward_additions as RA` (rewards branch) next to `unused_line_additions as ULA` and `unused_line_stress as ULS` (this branch) | **Keep both sides** |
| `generator/run.py` | The end of `build()`: `RA.add_reward_tables(out, seed)` (rewards branch) and `ULA.add_unused_line_tables(out, seed)` (this branch), both after `build_manifest.json` | **Keep both sides**; order does not matter (separate streams, separate tables) |
| `generator/run.py` | `PROFILES`: `reward_stress` and `unused_line_stress` added after `premium_heavy` | **Keep both sides** |
| `generator/run.py` | The `negative_control` fix is the same commit on both branches (`966988a` / cherry-picked `891bda2`) | Resolves cleanly |

## Branch merge order (for the later integration; not done)

1. `fix/negative-control-generation`
2. `feature/reward-data-additions`
3. `feature/l1-rewards-system`
4. `feature/lever-valuation-rebuild`
5. `feature/unused-line-management`

Resolve `generator/run.py` by keeping both sides (table above). After the merge, re-run
`python audit/audit_unused_line_module.py --regression` and the reward data additions audit: the
byte-identity baselines of the two branches will need to be regenerated together, since each adds its
own tables to every profile.
