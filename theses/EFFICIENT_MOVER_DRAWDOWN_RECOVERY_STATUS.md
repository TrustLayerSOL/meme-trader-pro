# Efficient-Mover Drawdown Recovery Status

This report was created to distinguish recoverable drawdown proxies from terminal drawdown proxies inside the high-FDV-efficiency universe.

## Efficient-Mover Population
- `{'definition': 'same fixed high-FDV-efficiency universe used in prior audits', 'rows': 391, 'milestone_tier_distribution': {'reached_1m_plus': 334, 'reached_500k_but_never_1m': 53, 'reached_200k_but_never_500k': 4}, 'date_distribution_top10': {'2026-06-01': 203, '2026-01-28': 30, '2026-01-27': 12, '2026-05-25': 12, '2026-01-22': 11, '2026-05-26': 11, '2026-04-23': 9, '2026-04-21': 7, '2026-02-11': 6, '2026-03-26': 6}, 'creator_distribution_top10': {'3XoHvXJ5KddicA4e9ZExmLtaUwmbnWJdtNuyHT7qu1LE': 29, '7grLweaPFKVHq9nfPKrqGApepuMWtdUnJaZBwStsrsSb': 28, 'CTJj4LMFNzG6TJxGS7wvzFYRFweQ8Fv3QLQnKjroYpeH': 27, '5xaqSs2XFgwSpxPKsx8EG4DK3uzBq9tn7FiA3WxT3as5': 26, '8YQ3mCRCbTU3ZVhNwJNWsTxsHv2PjMBY7bZ2Q2VSka7Q': 19, '6JwSanEGNjP98Ph8sdxaVz8knSpV4y6vx2wuAm4VSJbG': 14, '3edPnHeZDoXtDor2oqU83YJSGRLiGDuqUnxZW3EVi5JL': 14, '8RkczELy9HFmjcTyotJRtzNNvwkE5AJWMhS8F8cFxpPF': 13, 'EpupiXZVpHHKrLin3AVLmb74gGgaxGi2DR6jSX4CpueU': 8, 'C5SDCNbtG7jJ9mFDeRXDk8hUu87HGepz7mDWwsT54nMe': 7}, 'launches_with_path_data': 391, 'path_data_coverage_pct': 100.0}`

## Drawdown Event Counts
- By level: `{'20pct': 57, '30pct': 57, '40pct': 57, '50pct': 57}`
- By classification: `{'terminal_drawdown_proxy': 216, 'recoverable_drawdown_proxy': 8, 'data_limited_drawdown': 4}`

## 30% Trailing Stop Diagnostic
- `{'diagnostic_name': '30pct_trailing_stop_diagnostic', 'drawdown_30pct_events': 57, 'recoverable_count': 2, 'terminal_count': 54, 'data_limited_count': 1, 'recoverable_pct': 3.5088, 'terminal_pct': 94.7368, 'data_limited_pct': 1.7544, 'later_reached_higher_milestone_count': 0, 'would_have_exited_too_early_count': 0, 'appears_too_blunt': False, 'interpretation': 'Descriptive diagnostic only; this does not create a stop, sell rule, or execution recommendation.'}`

## Strongest Candidate Features
- None with sufficient support.

## Readiness
- `drawdown_recovery_report_data_limited`

## Next Recommendation
- `expand_or_repair_drawdown_path_coverage_before_exit_thesis`

## Limitations
- Snapshot-level paths are not continuous tick-level paths.
- Drawdown labels are descriptive FDV/valuation-proxy path labels, not trade outcomes.
- Several holder/top-holder/creator-flow deltas are unavailable at drawdown timestamp and are marked as missing when absent.
- No sell rules, validation, backtest, optimization, alerts, or execution logic was created.
