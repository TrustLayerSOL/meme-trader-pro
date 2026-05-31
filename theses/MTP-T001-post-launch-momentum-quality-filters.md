---
thesis_id: MTP-T001
name: Post-Launch Momentum with Quality Filters
status: active
priority: high
strategy_family: post_launch_momentum
current_stage: research
primary_metric: walk_forward_avg_test_net_return
risk_level: high
created_at: 2026-05-31
updated_at: 2026-05-31
---

# Thesis
Post-launch momentum may exist when early participation and flow quality are strong enough.

# Hypothesis
Fresh Solana meme tokens that show early real participation, positive confidence-weighted flow, enough unique actors, and low sell pressure have better short-horizon forward returns than the broader launch universe.

# Why This Might Work
Early organic participation can indicate demand before liquidity decays or attention fades.

# Required Data
Clean local research dataset rows, normalized trade events, outcome labels, and walk-forward validation results.

# Required Features
Confidence-weighted flow, buy/sell imbalance, unique actor count, quote volume, sell pressure, label quality.

# Linked Rules
- positive_flow_basic
- buy_imbalance_basic
- unique_actor_flow_basic
- volume_and_flow_basic
- low_sell_pressure_basic

# Promotion Criteria
Consistent positive test-fold results, sufficient sample size, visible cost assumptions, and human review.

# Rejection Criteria
Weak or negative test-fold returns, low fold consistency, excessive rug-like outcomes, or insufficient clean context.

# Current Evidence
Initial rule and walk-forward infrastructure exists; evidence-bearing dataset population is still required.

# Known Gaps
Needs larger clean historical rows and stronger liquidity/depth features.

# Next Actions
Populate ResearchDatasetStore and rerun baseline, rule backtest, and walk-forward reports.

# Notes
This thesis is not a live trading rule.
