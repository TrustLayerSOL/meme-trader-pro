---
thesis_id: MTP-T009
name: Social/Attention Confirmation
status: planned
priority: medium
strategy_family: attention_confirmation
current_stage: research
primary_metric: walk_forward_avg_test_net_return
risk_level: medium
created_at: 2026-05-31
updated_at: 2026-05-31
---

# Thesis
External attention confirmation may improve on-chain flow hypotheses.

# Hypothesis
On-chain flow confirmed by DexScreener/Jupiter/Raydium attention proxies performs better than on-chain flow alone.

# Why This Might Work
Attention signals may indicate broader discovery and reduce false positives from isolated flow.

# Required Data
DexScreener, Jupiter, Raydium, and local on-chain feature snapshots.

# Required Features
Attention proxy, recent listing visibility, venue presence, boosted/profile metadata.

# Linked Rules
- None yet.

# Promotion Criteria
Attention-confirmed variants outperform base on-chain rules out of sample.

# Rejection Criteria
Attention proxies add no signal or create lookahead/selection bias.

# Current Evidence
Planned thesis only.

# Known Gaps
Needs real DexScreener/Jupiter/Raydium ingestors.

# Next Actions
Replace placeholder ingestors with safe local evidence capture.

# Notes
This thesis is not a live trading rule.
