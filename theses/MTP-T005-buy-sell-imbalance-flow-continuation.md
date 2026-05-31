---
thesis_id: MTP-T005
name: Buy/Sell Imbalance and Confidence-Weighted Flow Continuation
status: active
priority: high
strategy_family: flow_momentum
current_stage: research
primary_metric: walk_forward_avg_test_net_return
risk_level: high
created_at: 2026-05-31
updated_at: 2026-05-31
---

# Thesis
Early buy/sell flow imbalance may predict short-horizon continuation.

# Hypothesis
High buy/sell imbalance and positive confidence-weighted flow predict short-horizon continuation.

# Why This Might Work
Flow imbalance can represent demand pressure before price fully adjusts.

# Required Data
Normalized trade events, confidence scores, feature snapshots, and outcome labels.

# Required Features
Buy/sell imbalance, confidence-weighted net flow, possible buy/sell counts.

# Linked Rules
- positive_flow_basic
- buy_imbalance_basic

# Promotion Criteria
Positive walk-forward test-fold consistency after costs and sufficient selected sample.

# Rejection Criteria
Positive in-sample behavior that degrades out of sample or fails after costs.

# Current Evidence
Default exploratory rules exist.

# Known Gaps
Needs larger clean ResearchDatasetStore population.

# Next Actions
Evaluate linked rules through walk-forward reports.

# Notes
This thesis is not a live trading rule.
