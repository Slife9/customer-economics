# Issues found

Issues found while building the module that are outside its scope. None is fixed here; each is
recorded for the owner of the code concerned.

| # | Where | Issue | Action |
|---|---|---|---|
| 1 | `engine/levers/l2_lines.py` (all branches) | Expected loss avoided by a decrease uses lifetime PD as if annual (L1 branch: no annualisation; lever-valuation branch: divides by card life 3/2/1 years, so the high scenario is still lifetime-as-annual) | None; this module uses `PD 12 Month` |
| 2 | Rebuilt L2 page, `feature/lever-valuation-rebuild` | Carrying cost by group uses the old liquidity (4% yield gap) and leverage (SLR) logic, not brief §2 | Known issue on the other branch; no action |
| 3 | `engine/ml/` fairness test | Counts any ML action as "selected", increases included; the "5 metros on 100k" figure is text only (`STATUS.md` on the lever-valuation branch); 14 of 76 metros fail on the committed 50k bundle | Re-run planned with adverse actions and increases separated, saved to file |
| 4 | `generator/run.py` on `main` | `--profile negative_control` crashes in `rewards.earn` (empty WRONG_EARN_RULE subset). Fixed on `fix/negative-control-generation`, not on `main` | Fix cherry-picked here (`891bda2`, from `966988a`); `negative_control` back in the byte-identity check, baselined from the fix branch's code |
| 5 | Generator realism check on `main` | 4 of 22 Layer 2 benchmarks out of range on the demo (transactor share, average utilisation, 90+ delinquency, net charge-off rate) | Pre-existing; unchanged by this module |
| 6 | Table3 `Card Status` | The last card of a closed or charged-off account stays `active` | Table30 reports activation status within the account's open period |
| 7 | Table3 `Deactivation Cycle Index` | −1 means both "never deactivated" and "deactivated in the cycle before the window" | Table30 uses `Card Status` to tell them apart |
| 8 | Engine card ledger `capital_cost` | The old charge (Table9, current rules) is larger than the brief §2 charge on drawn balances (5k demo: $223,879 vs $45,508 a year), so replacing it raises card profit | Replaced, never added (answer 4); reported on the drill-down |
| 9 | Table4 `Ending Balance` / `Utilization` | Measured after the cycle's payment, so a full payer shows $0 drawn at every month end | The module uses Ending Balance for exposure (the reporting-date balance); statement balance (Ending + Payment) for the segment rules and the calibration |

## Expected merge clashes (for the future integration)

| File | Clash | Instruction |
|---|---|---|
| `generator/run.py` | The import block: `reward_additions as RA` (rewards branch) next to `unused_line_additions as ULA` and `unused_line_stress as ULS` (this branch) | **Keep both sides** |
| `generator/run.py` | The end of `build()`: `RA.add_reward_tables(out, seed)` (rewards branch) and `ULA.add_unused_line_tables(out, seed)` (this branch), both after `build_manifest.json` | **Keep both sides**; order does not matter (separate streams, separate tables) |
| `generator/run.py` | `PROFILES`: `reward_stress` and `unused_line_stress` added after `premium_heavy` | **Keep both sides** |
| `generator/run.py` | The `negative_control` fix is the same commit on both branches (`966988a` / cherry-picked `891bda2`) | Resolves cleanly |
