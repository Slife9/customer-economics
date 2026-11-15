# Issues found

Issues found while building the module that are outside its scope. None is fixed here; each is
recorded for the owner of the code concerned.

| # | Where | Issue | Action |
|---|---|---|---|
| 1 | `engine/levers/l2_lines.py` (all branches) | Expected loss avoided by a decrease uses lifetime PD as if annual (L1 branch: no annualisation; lever-valuation branch: divides by card life 3/2/1 years, so the high scenario is still lifetime-as-annual) | None; this module uses `PD 12 Month` |
| 2 | Rebuilt L2 page, `feature/lever-valuation-rebuild` | Carrying cost by group uses the old liquidity (4% yield gap) and leverage (SLR) logic, not brief §2 | Known issue on the other branch; no action |
| 3 | `engine/ml/` fairness test | Counts any ML action as "selected", increases included; the "5 metros on 100k" figure is text only (`STATUS.md` on the lever-valuation branch); 14 of 76 metros fail on the committed 50k bundle | Re-run planned with adverse actions and increases separated, saved to file |
| 4 | `generator/run.py` on `main` | `--profile negative_control` crashes in `rewards.earn` (empty WRONG_EARN_RULE subset). Fixed on `fix/negative-control-generation`, not on `main` | Byte-identity on this branch uses demo and the three variant profiles instead |
| 5 | Generator realism check on `main` | 4 of 22 Layer 2 benchmarks out of range on the demo (transactor share, average utilisation, 90+ delinquency, net charge-off rate) | Pre-existing; unchanged by this module |
| 6 | Table3 `Card Status` | The last card of a closed or charged-off account stays `active` | Table30 reports activation status within the account's open period |
