# Population fixes: effect on lever counts and values (Stage A5)

Two population fixes from the spec, applied as a separate stage:

1. **L3** - accounts with tenure under 12 months are excluded even when added
   via `routed_lever == "L3"` (CARD Act first-year protection applies to every
   candidate).
2. **L5** - the closure-request signal uses the trailing 12 cycles only, not any
   closure-request contact in the full history.

Expectations regenerated with the spec's reference implementation on the
post-fix pipeline outputs (`audit/regenerate_lever_expectations.py`). 'Before' is
the reviewer's original `expected_values.json`.

### 5k demo (Tier 1 regime)

| Lever | Worklist before | Worklist after | Base before | Base after | Change |
|---|---:|---:|---:|---:|---:|
| L1 | 828 | 828 | 52,111.28 | 52,111.28 | no change |
| L2 | 2870 | 2870 | 34,990.29 | 34,990.29 | no change |
| L3 | 179 | 179 | 2,107.65 | 2,107.65 | no change |
| L4 | 2779 | 2779 | 5,709.82 | 5,709.82 | no change |
| L5 | 470 | 363 | -355.94 | -313.45 | +42.49 |
| L6 | 916 | 916 | 3,407.09 | 3,407.09 | no change |

- L5 `customers`: 470.0 -> 363.0
- L5 `value_at_risk`: 510953.06 -> 392702.5

### 100k bundle (Case A, SLR)

| Lever | Worklist before | Worklist after | Base before | Base after | Change |
|---|---:|---:|---:|---:|---:|
| L1 | 16321 | 16321 | 997,814.85 | 997,814.85 | no change |
| L2 | 56892 | 56892 | 676,637.40 | 676,637.40 | no change |
| L3 | 3561 | 3556 | 20,967.79 | 20,967.79 | no change |
| L4 | 57437 | 57437 | 114,066.19 | 114,066.19 | no change |
| L5 | 9754 | 7818 | 11,857.38 | 8,345.63 | -3,511.75 |
| L6 | 19138 | 19138 | 63,686.35 | 63,686.35 | no change |

- L5 `customers`: 9754.0 -> 7818.0
- L5 `value_at_risk`: 11566118.87 -> 9212531.61

