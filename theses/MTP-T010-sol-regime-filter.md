---
thesis_id: MTP-T010
name: SOL/CEX Regime Filter
status: planned
priority: low
strategy_family: market_regime
current_stage: research
primary_metric: walk_forward_avg_test_net_return
risk_level: medium
created_at: 2026-05-31
updated_at: 2026-05-31
---

# Thesis
Market regime may condition meme-token rule performance.

# Hypothesis
Meme-token rules perform better during favorable SOL/risk-on regimes and worse during risk-off regimes.

# Why This Might Work
Speculative token demand often depends on broader liquidity and risk appetite.

# Required Data
SOL price/volatility, CEX context, and meme-token research datasets.

# Required Features
SOL trend, SOL volatility, risk-on/risk-off regime labels, market context at snapshot time.

# Linked Rules
- None yet.

# Promotion Criteria
Regime filters improve out-of-sample stability without overfitting.

# Rejection Criteria
Regime labels add no stability or rely on unavailable future data.

# Current Evidence
Planned thesis only.

# Known Gaps
Needs SOL regime and CEX market context features.

# Next Actions
Add local market-regime feature capture.

# Notes
This thesis is not a live trading rule.
