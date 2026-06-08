# Rule V2 Shadow Lock Status

Status: locked as paper-shadow config only.

Locked buy variants:

- `BUY_V2_Q75_EFFICIENCY_RISK`
- `BUY_V2_Q75_EFFICIENCY_REPEAT_BUYER`

Locked shared exit:

- `EXIT_V2_PROFIT_LOCK_WITH_RUNNER`

Scope:

- Paper/shadow only.
- Starting paper cash: `$300`.
- Position size: `5%` of available paper cash/wallet value.
- Current Rule D historical artifacts were not overwritten.
- V2 paper-shadow variant decisions are wired into `rule_runtime_v1`.
- Every V2 simulated sell keeps post-sell tracking for later max FDV, missed upside, 200k/500k/1m continuation, and collapse protection.
- No real trades, wallet execution, private keys, transaction signing, swaps, order routing, or live trading are enabled.

Primary lock artifacts:

- `/Users/dianeposs/Projects/meme-trader-pro/configs/rule_v2_shadow.json`
- `/Volumes/ORICO/MemeTraderPro/data/forward_observation/rule_v2_shadow/rule_v2_shadow_locked_config.json`
- `/Volumes/ORICO/MemeTraderPro/data/forward_observation/rule_v2_shadow/rule_v2_shadow_lock_manifest.json`
- `/Volumes/ORICO/MemeTraderPro/data/forward_observation/rule_v2_shadow/rule_v2_shadow_daily_status.md`
- `/Volumes/ORICO/MemeTraderPro/data/forward_observation/rule_v2_shadow/rule_v2_shadow_variant_summary.json`

Next logical step:

Run a short paper-only proof campaign and compare V2 variant buys, exits, rejected candidates, and post-sell missed-upside tracking.
