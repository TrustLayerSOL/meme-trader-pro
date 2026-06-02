# T009 FAST + BROAD EARLY LAUNCH QUALITY STATUS

## Thesis Description

Fast early growth is more meaningful when paired with broad, distributed participation.

## Dataset

- Dataset used: `all_collected`
- Launch count: `3000`
- Speed feature used: `valuation_proxy_usd_1m`
- Breadth feature used: `active_wallets_60s`
- Concentration fields used: `['top_holder_share_60s_or_nearest', 'top_10_holder_share_60s_or_nearest', 'creator_holder_share_60s_or_nearest']`

## Interaction Group Counts

- `fast_and_broad`: `402`
- `fast_and_narrow`: `341`
- `slow_and_broad`: `135`
- `slow_and_narrow`: `479`
- `middle_or_other`: `1643`

## Classification

- Classification: `no_signal`
- Chronological robustness recommended: `False`

## Comparison To T005 Baseline

- T005 classification: `weak_signal`
- T009 clearer than T005 baseline: `True`

## Limitations

- FDV proxy outcomes are used; true market-cap claims remain blocked.
- This is descriptive only and does not create a trading rule.
- Quantile buckets are predefined for description, not optimized thresholds.
- Holder-state overlays are observed delta replay, not confirmed full-chain account snapshots.
- Entity/concentration overlays are partial because sidecar coverage is not all-collected.

## Guardrails

- No thesis promotion was made.
- No validation, backtest, walk-forward, paper/live trading, trading logic, optimization, grid search, or ML workflow was run.
- No trading rules were generated.

## Outputs

- Markdown summary: `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/T009_fast_broad_launch_quality/T009_fast_broad_launch_quality_summary.md`
- JSON summary: `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/T009_fast_broad_launch_quality/T009_fast_broad_launch_quality_summary.json`

## Next Recommendation

Proceed to T010 Funding Lineage using the completed funding-link pilot.
