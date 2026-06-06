# Rule Runtime v1 Safety Patch Summary

Updated: 2026-06-06T18:14:07.633797+00:00
Paper-only. Live trading, private keys, signing, swaps, and routing remain disabled.

- Duplicate confirmation patch: `True`
- Chase guard threshold: trigger `$20000.0`, max pct `0.15`, max entry `$23000.0`
- FDV provenance persistence: `True`
- Holder gate applied: `True`
- Mayhem label-only: `True`
- Stagnation exit added: `True`
- Duplicate same-state rejects: `1`
- Chase guard rejects: `0`
- Holder <=1 rejects: `0`
- Mayhem labels: `0`
- Dev-pump suspect labels: `3`
- Fake-volume suspect labels: `3`
- Stagnation exits: `0`
- Valid/voided/rejected paper buys: `0` / `1` / `5`
- Paper cash/wallet: `$300.0` / `$300.0`
- Monitor path: `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/forward_observation/rule_runtime_v1/rule_runtime_v1_monitor.html`
- Retroactive review path: `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/forward_observation/rule_runtime_v1/retroactive_paper_buy_safety_review.json`
