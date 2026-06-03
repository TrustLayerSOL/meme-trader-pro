# Forward 50 Freshness Quality Audit Status

This audit was created because the forward collector reached the first 50-100 candidates very quickly, which raised a quality question: whether candidates were being observed near birth/pre-trigger, or mostly after they were already active and above fixed trigger levels.

Guardrail: this is forward-observation quality audit work only. It is not paper trading, live trading, validation, backtesting, strategy generation, or trading-rule deployment.

## Scope

- Candidate scope: `first_50_forward_observed_candidates`
- Candidates audited: `50`
- Current candidate rows present after collector stop: `173`
- Unique mints audited: `50`
- Source mix: `{'helius_program_logs_pumpfun': 17, 'helius_program_logs_pumpswap': 32, 'helius_program_logs_raydium': 1}`
- Network calls made by audit: `0`

## Results

- Freshness class distribution: `{'already_above_100k_candidate': 16, 'already_above_20k_candidate': 10, 'already_above_50k_candidate': 6, 'unknown_freshness': 18}`
- Duplicate/source-transition result: `{'unique_candidate': 50}`
- FDV proxy sanity result: `{'valid_fdv_proxy': 50}`
- Actionability timing result: `{'actionable_pre_15k_observed': 11, 'actionable_pre_20k_observed': 7, 'detected_too_late': 5, 'observed_after_100k': 11, 'observed_after_20k_before_100k': 11, 'observed_at_20k': 5}`
- Data completeness: `{'has_active_wallets': 1.0, 'has_buy_sell_counts': 1.0, 'has_drawdown_rows': 1.0, 'has_event_rows': 1.0, 'has_fdv_proxy': 1.0, 'has_holder_rows': 1.0, 'has_metadata_rows': 1.0, 'has_path_rows': 1.0, 'has_raw_source_rows': 1.0}`
- Status reconciliation mismatches: `16`
- Scale readiness classification: `forward_50_needs_source_freshness_repair`
- Recommendation: `B/C. Prioritize Pump.fun birth/new-launch feed and keep PumpSwap as a separate post-migration observation lane.`

## Interpretation

- The first-50 sample has controlled duplicate risk and valid FDV proxy coverage.
- The first-50 sample is not freshness-ready for scale because it does not prove birth/pre-10k observation and includes many already-above-trigger candidates.
- PumpSwap should be treated as a post-migration observation lane unless a separate freshness test proves otherwise.
- Raydium remains too thin to interpret as a primary lane.

## Report Paths

- `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/forward_observation/efficient_movers/forward_50_freshness_audit.csv`
- `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/forward_observation/efficient_movers/forward_50_source_freshness.csv`
- `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/forward_observation/efficient_movers/forward_50_duplicate_transition_audit.csv`
- `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/forward_observation/efficient_movers/forward_50_fdv_proxy_sanity.csv`
- `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/forward_observation/efficient_movers/forward_50_actionability_timing.csv`
- `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/forward_observation/efficient_movers/forward_50_data_completeness.csv`
- `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/forward_observation/efficient_movers/forward_50_status_reconciliation.csv`
- `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/forward_observation/efficient_movers/forward_50_freshness_quality_summary.json`
- `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/forward_observation/efficient_movers/forward_50_freshness_quality_summary.md`

## Next Required Action

Do not scale the current all-source forward collector as the main actionability dataset. First prioritize Pump.fun birth/new-launch detection and separate PumpSwap as a post-migration lane.
