# Short-Window Expansion Discovery Status

## Refocus Rationale

The project is refocusing from launch survival/health toward short-window explosive expansion because prior descriptive health-oriented theses mostly failed or stayed weak, while T009 showed fast+narrow launches had stronger FDV-proxy runup than fast+broad launches.

## Trigger Thresholds Tested

- `15k`, `20k`, `30k` FDV-proxy triggers

## Forward Windows Tested

- `1m`, `2m`, `5m`, `10m`, `30m` max windows
- `1m`, `5m`, `30m` min windows

## Label Coverage

- Trigger 15k: `448`
- Trigger 20k: `422`
- Trigger 30k: `395`

## Explosive Label Counts At Trigger 20k

- Hit 50k within 5m: `348`
- Hit 100k within 10m: `284`
- Hit 2x before down 30pct: `4`

## Fast Narrow Vs Fast Broad

- Fast narrow hit rate: `0.0`
- Fast broad hit rate: `0.0`
- Difference: `0.0`

## Readiness

- Classification: `short_window_expansion_partial_needs_more_forward_path`
- Formal thesis justified next: `False`

## Limitations

- FDV-proxy labels are not true market-cap labels.
- Historical snapshots are launch-relative and coarse; live DexScreener/Axiom visibility may differ.
- No trading or execution recommendation is made.

## Outputs

- Labels JSON: `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/short_window_expansion_discovery/short_window_expansion_labels.json`
- Labels parquet: `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/short_window_expansion_discovery/short_window_expansion_labels.parquet`
- Summary JSON: `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/short_window_expansion_discovery/short_window_expansion_discovery_summary.json`
- Summary markdown: `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/short_window_expansion_discovery/short_window_expansion_discovery_summary.md`

## Guardrails

- No trading rules were generated.
- No thesis promotion, validation, backtest, walk-forward, paper/live trading, live trading, optimization, grid search, or ML was run.

## Next Recommendation

Improve forward-path coverage or add bounded DexScreener observation data before a formal thesis.
