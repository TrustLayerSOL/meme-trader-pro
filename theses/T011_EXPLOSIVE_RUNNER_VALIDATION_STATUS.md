# T011 Explosive Runner Validation Status

- Validation design reference: `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/T011_validation_design/T011_validation_design.json`
- Primary split: `chronological_60_40`
- Primary trigger: `20000`
- Primary feature contrast: `fdv_per_event_at_trigger highest train quintile and event_count_at_trigger lowest train quintile`
- Primary outcome: `crossed_100k_after_20k`

## Training Cutoffs

- Event count lowest quintile max: `2.0`
- FDV per event highest quintile min: `660435.6822136429`

## Holdout Metrics

- Train rows: `253`
- Holdout rows: `169`
- Primary group support: `22`
- Baseline hit rate: `0.7041420118343196`
- Primary group hit rate: `1.0`
- Relative lift: `1.4201680672268906`

## Sensitivity Summary

- 70/30 relative lift: `1.6282051282051282`
- 15k trigger relative lift: `1.4634146341463414`
- 30k trigger relative lift: `1.3389830508474576`

## Leakage Check Summary

- All checks passed: `True`

## Classification

- Validation classification: `validation_failed`

## Limitations

- FDV/valuation proxy is used; true market-cap claims remain blocked.
- This is historical validation only, not thesis promotion or trading-system design.
- Primary buckets use train-derived quintiles and fixed design thresholds only.
- Snapshot timing around fast crossings may still compress trigger-path evidence.

## Outputs

- JSON summary: `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/T011_validation/T011_validation_summary.json`
- Markdown summary: `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/T011_validation/T011_validation_summary.md`
- Holdout rows: `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/T011_validation/T011_holdout_rows.csv`

## Guardrails

- No trading rules were generated.
- No thesis promotion, live trading, paper trading, alerts, optimization, grid search, or ML was run.

## Next Recommendation

Re-evaluate historical snapshot fidelity or run a current-market observation study before further validation.
