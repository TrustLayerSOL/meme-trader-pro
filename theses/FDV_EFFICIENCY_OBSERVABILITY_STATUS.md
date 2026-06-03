# FDV-Efficiency Observability Status

This audit was created because FDV-efficiency remains the strongest historical separator, but it must be observable early enough before future entry-path research is justified.

- Trigger levels tested: `10k, 15k, 20k, 30k`
- Rows analyzed: `1143`
- Classification: `fdv_efficiency_observable_too_late`

## Observability Result
- 10k: observable `1143/1143`; leakage-safe `1143/1143`
- 15k: observable `1143/1143`; leakage-safe `1143/1143`
- 20k: observable `1143/1143`; leakage-safe `1143/1143`
- 30k: observable `1041/1143`; leakage-safe `1041/1143`

## Actionability Window Result
- 20k to 100k: median `0.0` seconds; >=30s `1.2248%`; >=60s `0.8749%`
- 20k to 500k: median `0.0` seconds; >=30s `0.8749%`; >=60s `0.6999%`

## Snapshot Latency Result
- 10k: median previous-gap `60.0` seconds; >60s `7.7865%`
- 15k: median previous-gap `60.0` seconds; >60s `8.3115%`
- 20k: median previous-gap `60.0` seconds; >60s `8.8364%`
- 30k: median previous-gap `60.0` seconds; >60s `9.318%`

## Limitations
- Snapshot-level replay is not continuous tick-level observability.
- FDV proxy is not true market cap.
- Actionability window is a timing diagnostic only.

## Next Recommendation
- `test_earlier_observability_sources_before_any_entry_path_research`

No thesis, validation, walk-forward validation, backtest, alerts, execution logic, optimization, ML, or strategy generation was run.
