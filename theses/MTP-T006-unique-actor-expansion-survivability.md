---
thesis_id: MTP-T006
name: Unique Actor Expansion / Organic Participation
status: active
priority: medium
strategy_family: participation_quality
current_stage: research
primary_metric: walk_forward_avg_test_net_return
risk_level: medium
created_at: 2026-05-31
updated_at: 2026-05-31
---

# Thesis
Organic actor expansion may be a stronger survival signal than raw volume.

# Hypothesis
A rising count of unique actors is a better survival signal than raw volume alone.

# Why This Might Work
Distributed participation can reduce dependence on a few wallets and may indicate broader demand.

# Required Data
Actor-level normalized events, feature snapshots, and outcome labels.

# Required Features
Unique actor count, actor expansion rate, quote volume, confidence-weighted flow.

# Linked Rules
- unique_actor_flow_basic

# Promotion Criteria
Unique-actor rules show consistent out-of-sample improvement and lower rug-like rates.

# Rejection Criteria
Actor count adds no out-of-sample signal or is dominated by noisy wallet churn.

# Current Evidence
Default exploratory rule exists.

# Known Gaps
Needs actor expansion features beyond raw count.

# Next Actions
Validate actor-count rule across chronological folds.

# Notes
This thesis is not a live trading rule.
