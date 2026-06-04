# Partial Forward Strategy Preview Status

Sample label: `partial_birth_coverage_long_lifecycle_sample`

This sample is partial because the forward collector missed a class of Pump.fun births before the parser/hydration fixes. It is usable for tentative path diagnostics only.

Births observed: `1`
Mints analyzed: `1`
Crossed 20k: `0`
Crossed 1M: `0`
Quality warnings: `['known_partial_birth_coverage_collection_bug']`

Approved uses: tentative entry/exit design, path analysis, field coverage audit, and disabled paper/shadow scaffold design.

Prohibited uses: live trading, final validation, profitability claims, final conversion-rate estimates, and production strategy deployment.

Tentative entry candidates:
- `PBCL_ENTRY_10K_EFFICIENCY_HIGH_BUCKET`: 10k efficiency high-bucket shadow entry design
- `PBCL_ENTRY_20K_CONFIRMATION_EFFICIENCY`: 20k confirmation efficiency shadow entry design
- `PBCL_ENTRY_15K_SPEED_FLOW_BALANCED`: 15k speed plus flow balance shadow entry design

Tentative exit candidates:
- `PBCL_EXIT_NO_RECLAIM_10M`: No-reclaim after drawdown shadow exit design
- `PBCL_EXIT_TRAILING_DRAWDOWN_WITH_GRACE`: Milestone trailing drawdown with grace shadow exit design
- `PBCL_EXIT_MAX_AGE_OR_INACTIVE`: Inactive/max-age maturity shadow exit design

Paper/shadow scaffold status: `paper_shadow_scaffold_ready_disabled`

No live trades, paper trades, orders, swaps, alerts, or execution actions were run.

Reports: `/private/var/folders/x9/dq8sv7hj50j3j38_n6tmdv180000gn/T/pytest-of-dianeposs/pytest-571/test_partial_forward_strategy_1/data/backtests/diagnostics/reports/forward_observation/official_lifecycle_watch_v1`
