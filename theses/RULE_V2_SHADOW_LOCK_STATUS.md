# Rule V2 Shadow Lock Status

Status: locked as paper-shadow config only.

Locked buy variants:

- `RULE_V2_20K_Q75_EFFICIENCY_RISK_FILTER`
- `RULE_V2_20K_Q75_EFFICIENCY_REPEAT_BUYER`

Locked shared exit:

- `EXIT_V2_PROFIT_LOCK_WITH_RUNNER`

Scope:

- Paper/shadow only.
- Starting paper cash: `$300`.
- Position size: `5%` of available paper cash/wallet value.
- Current Rule D config was not overwritten.
- No real trades, wallet execution, private keys, transaction signing, swaps, order routing, or live trading are enabled.

Primary lock artifacts:

- `/Users/dianeposs/Projects/meme-trader-pro/configs/rule_v2_shadow.json`
- `/Volumes/ORICO/MemeTraderPro/data/forward_observation/rule_v2_shadow/rule_v2_shadow_locked_config.json`
- `/Volumes/ORICO/MemeTraderPro/data/forward_observation/rule_v2_shadow/rule_v2_shadow_lock_manifest.json`
- `/Volumes/ORICO/MemeTraderPro/data/forward_observation/rule_v2_shadow/rule_v2_shadow_daily_status.md`
- `/Volumes/ORICO/MemeTraderPro/data/forward_observation/rule_v2_shadow/rule_v2_shadow_variant_summary.json`

Next logical step:

Wire V2 shadow candidate labeling into `rule_runtime_v1` after the actionable-candidate-quality bottleneck audit, so every confirmed 20k candidate reports which V2 gates passed or failed before any paper buy is allowed.
