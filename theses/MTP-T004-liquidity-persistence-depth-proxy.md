---
thesis_id: MTP-T004
name: Liquidity Persistence / Depth Proxy
status: planned
priority: high
strategy_family: liquidity_quality
current_stage: research
primary_metric: walk_forward_avg_test_net_return
risk_level: high
created_at: 2026-05-31
updated_at: 2026-05-31
---

# Thesis
Liquidity persistence may separate tradable launches from fragile launches.

# Hypothesis
Tokens with persistent liquidity and lower quote-impact proxies perform better and fail less often.

# Why This Might Work
Persistent liquidity can reduce execution drag and lower immediate failure risk.

# Required Data
Pool liquidity, depth, quote impact, and outcome labels.

# Required Features
Liquidity persistence, depth proxy, quote impact proxy, no-future-liquidity rate.

# Linked Rules
- None yet.

# Promotion Criteria
Validated liquidity-quality features improve test-fold results and reduce failure outcomes.

# Rejection Criteria
Liquidity proxies fail to improve net outcomes or are too noisy to measure.

# Current Evidence
Planned thesis only.

# Known Gaps
Needs real liquidity/depth/quote impact features.

# Next Actions
Add local liquidity feature sources.

# Notes
This thesis is not a live trading rule.
