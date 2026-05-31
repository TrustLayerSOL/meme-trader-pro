---
thesis_id: MTP-T002
name: Post-Flush Mean Reversion
status: planned
priority: medium
strategy_family: post_flush_mean_reversion
current_stage: research
primary_metric: walk_forward_avg_test_net_return
risk_level: high
created_at: 2026-05-31
updated_at: 2026-05-31
---

# Thesis
Some early flushes may create rebound candidates if liquidity and participation remain intact.

# Hypothesis
Tokens that survive an early sharp drawdown while maintaining liquidity/participation may show short rebound opportunities.

# Why This Might Work
Panic selling can temporarily overshoot when participants and liquidity remain present.

# Required Data
Outcome labels, intratoken drawdown state, liquidity persistence, and clean post-flush event history.

# Required Features
First-flush detection, drawdown-state features, survival flags, liquidity persistence.

# Linked Rules
- None yet.

# Promotion Criteria
Walk-forward evidence across flush-state features with sufficient sample size and human review.

# Rejection Criteria
No rebound consistency, high rug-like drop rate, or inability to identify flush state cleanly.

# Current Evidence
Planned thesis only.

# Known Gaps
Needs first-flush detection features and drawdown-state features.

# Next Actions
Design flush-state feature snapshots.

# Notes
This thesis is not a live trading rule.
