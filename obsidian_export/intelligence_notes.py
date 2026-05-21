from __future__ import annotations

from typing import Any

from obsidian_export.candidate_note import wallet_candidate_stem
from obsidian_export.markdown import (
    GENERATED_MARKER,
    as_dict,
    bullet_list,
    compact_number,
    short_datetime,
    short_id,
    table,
    wikilink,
    yaml_frontmatter,
)
from obsidian_export.signal_note import postmortem_stem, rejected_signal_stem
from obsidian_export.wallet_note import wallet_stem


def render_intelligence_notes(snapshot: dict[str, Any]) -> dict[str, str]:
    anomaly = build_anomaly_summary(snapshot)
    drift = build_drift_summary(snapshot)
    return {
        "Dashboards/MemeTraderPro Research Command Center.md": render_command_center(snapshot, anomaly, drift),
        "Dashboards/MemeTraderPro Anomaly Radar.md": render_anomaly_radar(snapshot, anomaly),
        "Dashboards/MemeTraderPro Drift Monitor.md": render_drift_monitor(drift),
        "Dashboards/Wallet Cycle Report.md": render_wallet_cycle_report(snapshot),
        "Dashboards/Wallet Candidate Quality.md": render_wallet_candidate_quality(snapshot),
        "Dashboards/Wallet Candidate Quality Review.md": render_wallet_candidate_quality_review(snapshot),
        "Dashboards/Wallet Candidate Evidence Plan.md": render_wallet_candidate_evidence_plan(snapshot),
        "Dashboards/Wallet Candidate Backfill Targets.md": render_wallet_candidate_backfill_targets(snapshot),
        "Dashboards/Wallet History Backfill.md": render_wallet_history_backfill(snapshot),
        "Dashboards/Wallet Evidence Enrichment.md": render_wallet_evidence_enrichment(snapshot),
        "Dashboards/Wallet Missing Market Context.md": render_wallet_missing_market_context(snapshot),
        "Dashboards/Wallet Replay Ecosystem Review.md": render_wallet_replay_review(snapshot),
        "Dashboards/Forward Signal Operator Review.md": render_forward_signal_operator_review(snapshot),
        "Dashboards/Forward Enhanced Observation.md": render_forward_enhanced_observation(snapshot),
        "Dashboards/MemeTraderPro Signal Lineage.md": render_signal_lineage(),
        "Dashboards/MemeTraderPro Daily Workflow.md": render_daily_workflow(anomaly, drift),
        "../SharedQuant/Dashboards/Quant Research Command Center.md": render_shared_quant_dashboard(),
        "../SharedQuant/Dashboards/Daily Review Checklist.md": render_shared_daily_review_checklist(),
    }


def build_anomaly_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    wallets = [row for row in snapshot.get("wallet_rows") or [] if isinstance(row, dict)]
    rejections = [row for row in snapshot.get("rejections") or [] if isinstance(row, dict)]
    postmortems = [row for row in snapshot.get("postmortems") or [] if isinstance(row, dict)]
    audit = as_dict(snapshot.get("wallet_candidate_audit"))
    candidates = [row for row in audit.get("candidates") or [] if isinstance(row, dict)]

    degraded = [
        row
        for row in wallets
        if as_dict(row.get("recommendation")).get("action") == "DEMOTION_REVIEW"
        or _score(row) <= 25
        or _wallet_roi(row) < -10
    ]
    rug_heavy = [
        row
        for row in wallets
        if int(row.get("rug_participation") or row.get("rug_count") or 0) >= 2
        or float(row.get("rug_participation_rate") or 0) >= 0.35
    ]
    rejected_winners = [
        row
        for row in rejections
        if str(as_dict(row.get("what would have happened afterward if traded")).get("status") or "").lower()
        in {"runner", "winner", "would_have_won", "missed_winner"}
    ]
    unresolved_postmortems = [
        row
        for row in postmortems
        if str(row.get("status") or "").lower() not in {"closed", "resolved", "archived"}
    ]
    promoted = [
        row
        for row in candidates
        if row.get("recommendation_action") == "PROMOTION_REVIEW" and not bool(row.get("review_resolved"))
    ]
    demoted = [
        row
        for row in candidates
        if row.get("recommendation_action") == "DEMOTION_REVIEW" and not bool(row.get("review_resolved"))
    ]
    return {
        "wallet_degradation": sorted(degraded, key=_wallet_alert_sort, reverse=True)[:25],
        "rug_heavy_wallets": sorted(rug_heavy, key=lambda row: int(row.get("rug_participation") or row.get("rug_count") or 0), reverse=True)[:25],
        "rejected_signal_winners": rejected_winners[:25],
        "unresolved_postmortems": unresolved_postmortems[:25],
        "promotion_reviews": promoted[:25],
        "demotion_reviews": demoted[:25],
        "replay_visibility": as_dict(snapshot.get("replay_visibility")),
    }


def build_drift_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    wallets = [row for row in snapshot.get("wallet_rows") or [] if isinstance(row, dict)]
    negative_expectancy = [row for row in wallets if _wallet_roi(row) < 0 and int(row.get("paper_watch_entries") or 0) >= 5]
    confidence_mismatch = [
        row
        for row in wallets
        if _score(row) >= 60 and _wallet_roi(row) < 0
    ]
    return {
        "wallet_score_drift": sorted(negative_expectancy, key=lambda row: _wallet_roi(row))[:25],
        "confidence_mismatch": sorted(confidence_mismatch, key=lambda row: _score(row), reverse=True)[:25],
        "signal_drift_queries": [
            "Rejected signals with later runner outcomes",
            "Paper lanes with rising negative PnL",
            "Wallets moving from promotion review to demotion review",
        ],
    }


def render_command_center(snapshot: dict[str, Any], anomaly: dict[str, Any], drift: dict[str, Any]) -> str:
    frontmatter = _frontmatter("research_command_center")
    replay_review = as_dict(snapshot.get("wallet_replay_review"))
    replay_summary = as_dict(replay_review.get("summary"))
    cycle = as_dict(snapshot.get("wallet_cycle_report"))
    cycle_counts = as_dict(cycle.get("counts"))
    cycle_queue = as_dict(cycle.get("review_queue"))
    quality = as_dict(snapshot.get("wallet_candidate_quality_report"))
    quality_summary = as_dict(quality.get("summary"))
    quality_review = as_dict(snapshot.get("wallet_candidate_quality_review"))
    quality_review_summary = as_dict(quality_review.get("summary"))
    evidence_plan = as_dict(snapshot.get("wallet_candidate_evidence_plan"))
    evidence_plan_summary = as_dict(evidence_plan.get("summary"))
    backfill_targets = as_dict(snapshot.get("wallet_candidate_backfill_targets"))
    backfill_summary = as_dict(backfill_targets.get("summary"))
    history_backfill = as_dict(snapshot.get("wallet_history_backfill"))
    history_summary = as_dict(history_backfill.get("summary"))
    evidence_enrichment = as_dict(snapshot.get("wallet_evidence_enrichment"))
    enrichment_summary = as_dict(evidence_enrichment.get("summary"))
    missing_context = as_dict(snapshot.get("wallet_missing_market_context"))
    missing_context_summary = as_dict(missing_context.get("summary"))
    forward_rollup = as_dict(snapshot.get("forward_signal_operator_rollup"))
    forward_summary = as_dict(forward_rollup.get("summary"))
    enhanced_observation = as_dict(snapshot.get("forward_enhanced_observation"))
    enhanced_summary = as_dict(enhanced_observation.get("summary"))
    priority_rows = _priority_queue_rows(
        anomaly,
        drift,
        replay_summary,
        cycle_queue,
        evidence_plan_summary,
        backfill_summary,
        enrichment_summary,
        missing_context_summary,
        forward_summary,
        enhanced_summary,
    )
    frontmatter["p0_count"] = _p0_count(priority_rows)
    body = f"""# MemeTraderPro Research Command Center

{GENERATED_MARKER}

## What This Dashboard Does

This is the daily MemeTraderPro operating surface. It tells you which wallet, signal, replay, and evidence-quality issues deserve attention before you open detailed generated folders.

## What Matters Today

{_priority_queue_table(priority_rows)}

## Operational Snapshot

{_operational_snapshot_table(cycle_counts, quality_summary, quality_review_summary, replay_summary, history_summary)}

## Evidence Quality Changes

{_evidence_quality_table(replay_summary, evidence_plan_summary, backfill_summary, enrichment_summary, missing_context_summary)}

## Review First

1. Open [[MemeTraderPro Anomaly Radar]].
2. Resolve any rejected-signal winners before tuning thresholds.
3. Review demotion candidates before trusting wallet-sourced signals.
4. Promote only when replay and postmortem evidence agree.
5. Log one daily observation in the daily report.

## Open Only If Needed

{bullet_list([
    "[[MemeTraderPro Anomaly Radar]] - wallet degradation, rejected-signal winners, unresolved postmortems",
    "[[MemeTraderPro Drift Monitor]] - wallet-score drift and confidence mismatch",
    "[[Wallet Candidate Evidence Plan]] - replay/outcome evidence gaps",
    "[[Wallet Missing Market Context]] - token-context backfill targets",
    "[[Wallet Replay Ecosystem Review]] - replay-safe wallet evidence",
    "[[Forward Signal Operator Review]] - repaired forward-signal wallet review before any trust decision",
    "[[Forward Enhanced Observation]] - priority wallet lane for future forward evidence only",
    "[[Wallet Review Decisions]] - saved human review decisions",
])}

## Not Raw Data

This page is the queue. Use folder tables only after an anomaly or experiment points there.
"""
    return _note(frontmatter, body)


def _priority_queue_rows(
    anomaly: dict[str, Any],
    drift: dict[str, Any],
    replay_summary: dict[str, Any],
    cycle_queue: dict[str, Any],
    evidence_plan_summary: dict[str, Any],
    backfill_summary: dict[str, Any],
    enrichment_summary: dict[str, Any],
    missing_context_summary: dict[str, Any],
    forward_summary: dict[str, Any],
    enhanced_summary: dict[str, Any],
) -> list[tuple[str, str, int, str, str]]:
    return [
        (
            "P0",
            "Rejected-signal winners",
            len(anomaly["rejected_signal_winners"]),
            "Filter may be blocking later runners.",
            "[[Rejected Signal Winners]]",
        ),
        (
            "P0",
            "Wallet degradation",
            len(anomaly["wallet_degradation"]),
            "Wallet edge deteriorated; review before trusting wallet-sourced signals.",
            "[[MemeTraderPro Anomaly Radar]]",
        ),
        (
            "P1",
            "Unresolved postmortems",
            len(anomaly["unresolved_postmortems"]),
            "Open failures create stale assumptions if not closed.",
            "[[MemeTraderPro Anomaly Radar]]",
        ),
        (
            "P1",
            "Wallet-score drift",
            len(drift["wallet_score_drift"]),
            "Negative expectancy can indicate stale wallet weights.",
            "[[MemeTraderPro Drift Monitor]]",
        ),
        (
            "P1",
            "Demotion reviews",
            _count_value(cycle_queue.get("demotion_review")) + len(anomaly["demotion_reviews"]),
            "Bad wallets should be reviewed before new signal weighting.",
            "[[Wallets Pending Review]]",
        ),
        (
            "P2",
            "Replay coverage gaps",
            _count_value(evidence_plan_summary.get("needs_replay_coverage")) + _count_value(replay_summary.get("low_coverage_wallets")),
            "Evidence is too thin for promotion/demotion confidence.",
            "[[Wallet Candidate Evidence Plan]]",
        ),
        (
            "P2",
            "Market-context gaps",
            _count_value(enrichment_summary.get("missing_market_context_rows")) + _count_value(missing_context_summary.get("target_mints")),
            "Wallet evidence is less useful without entry/liquidity context.",
            "[[Wallet Missing Market Context]]",
        ),
        (
            "P2",
            "Wallet-history backfill",
            _count_value(backfill_summary.get("needs_wallet_history")),
            "Backfill targets can become future reviewable wallets.",
            "[[Wallet Candidate Backfill Targets]]",
        ),
        (
            "P1",
            "Forward-signal manual review",
            _count_value(forward_summary.get("manual_review_required")),
            "Repaired forward evidence is review-worthy but still cannot mutate wallet trust.",
            "[[Forward Signal Operator Review]]",
        ),
        (
            "P1",
            "Enhanced observation wallets",
            _count_value(enhanced_summary.get("enhanced_observation_wallets")),
            "Priority wallets need future evidence before any trust discussion.",
            "[[Forward Enhanced Observation]]",
        ),
    ]


def _priority_queue_table(rows: list[tuple[str, str, int, str, str]]) -> str:
    active = [row for row in rows if row[2] > 0]
    if not active:
        return "No high-priority MemeTraderPro issues surfaced in this export."
    return table(
        ["Priority", "Issue", "Count", "Why It Matters", "Open"],
        [[priority, issue, _count(count), why, link] for priority, issue, count, why, link in active[:8]],
    )


def _p0_count(rows: list[tuple[str, str, int, str, str]]) -> int:
    return sum(1 for priority, _issue, count, _why, _link in rows if priority == "P0" and count > 0)


def _operational_snapshot_table(
    cycle_counts: dict[str, Any],
    quality_summary: dict[str, Any],
    quality_review_summary: dict[str, Any],
    replay_summary: dict[str, Any],
    history_summary: dict[str, Any],
) -> str:
    rows = [
        ["Wallet universe", _count(cycle_counts.get("active_paper_watch_wallets")), "Active paper-watch wallets"],
        ["Blocked wallets", _count(cycle_counts.get("blocked_paper_watch_wallets")), "Excluded from wallet-sourced trust"],
        ["Active candidates", _count(quality_summary.get("active_candidates")), "Candidate review pool"],
        ["Promotion-ready", _count(quality_review_summary.get("promotion_review_ready")), "Needs human review, not auto-apply"],
        ["Replay reviewable", _count(replay_summary.get("reviewable_wallets")), "reviewable wallets: " + str(_count(replay_summary.get("reviewable_wallets")))],
        ["History evidence", _count(history_summary.get("total_evidence_rows_created")), "Rows created from wallet-history backfill"],
    ]
    return table(["Area", "Count", "Meaning"], rows)


def _evidence_quality_table(
    replay_summary: dict[str, Any],
    evidence_plan_summary: dict[str, Any],
    backfill_summary: dict[str, Any],
    enrichment_summary: dict[str, Any],
    missing_context_summary: dict[str, Any],
) -> str:
    rows = [
        ["Low replay coverage", _count(replay_summary.get("low_coverage_wallets")), "Collect replay before trusting review outcome"],
        ["Needs replay evidence", _count(evidence_plan_summary.get("needs_replay_coverage")), "Candidate evidence is incomplete"],
        ["Needs outcome coverage", _count(evidence_plan_summary.get("needs_outcome_coverage")), "Validation gap"],
        ["Wallet history targets", _count(backfill_summary.get("needs_wallet_history")), "Backfill source behavior"],
        ["Enriched evidence rows", _count(enrichment_summary.get("enriched_rows")), "Evidence quality improved"],
        ["Missing market context", _count(enrichment_summary.get("missing_market_context_rows")), "Backfill liquidity/price context"],
        ["Target mints missing context", _count(missing_context_summary.get("target_mints")), "Prioritize context collection"],
    ]
    return table(["Evidence Signal", "Count", "Action"], rows)


def render_wallet_candidate_quality(snapshot: dict[str, Any]) -> str:
    report = as_dict(snapshot.get("wallet_candidate_quality_report"))
    summary = as_dict(report.get("summary"))
    rows = [row for row in report.get("ranked_candidates") or [] if isinstance(row, dict)][:25]
    frontmatter = _frontmatter("wallet_candidate_quality_report")
    body = f"""# Wallet Candidate Quality

{GENERATED_MARKER}

## What This Dashboard Does

Review-only ranking of candidate wallets by current evidence quality. This does not promote, demote, or trade wallets.

## Summary

- Active candidates: {_count(summary.get("active_candidates"))}
- Blocked candidates: {_count(summary.get("blocked_candidates"))}
- Strong observations: {_count(summary.get("strong_observation"))}
- Paper-watch review: {_count(summary.get("paper_watch_review"))}
- Hold review: {_count(summary.get("hold_review"))}
- Reject review: {_count(summary.get("reject_review"))}

## Top Ranked Candidates

{_candidate_quality_table(rows)}
"""
    return _note(frontmatter, body)


def render_wallet_candidate_quality_review(snapshot: dict[str, Any]) -> str:
    report = as_dict(snapshot.get("wallet_candidate_quality_review"))
    summary = as_dict(report.get("summary"))
    rows = [row for row in report.get("shortlist") or [] if isinstance(row, dict)][:25]
    frontmatter = _frontmatter("wallet_candidate_quality_review")
    body = f"""# Wallet Candidate Quality Review

{GENERATED_MARKER}

## What This Dashboard Does

Review-only cross-check of top candidate-quality wallets against replay and outcome evidence. This does not approve or apply wallet-list changes.

## Summary

- Total reviewed: {_count(summary.get("total_reviewed"))}
- Promotion review ready: {_count(summary.get("promotion_review_ready"))}
- Observe more: {_count(summary.get("observe_more"))}
- Risk review: {_count(summary.get("risk_review"))}
- Reject review: {_count(summary.get("reject_review"))}

## Shortlist

{_candidate_quality_review_table(rows)}
"""
    return _note(frontmatter, body)


def render_wallet_candidate_evidence_plan(snapshot: dict[str, Any]) -> str:
    report = as_dict(snapshot.get("wallet_candidate_evidence_plan"))
    summary = as_dict(report.get("summary"))
    rows = [row for row in report.get("coverage_queue") or [] if isinstance(row, dict)][:25]
    frontmatter = _frontmatter("wallet_candidate_evidence_plan")
    body = f"""# Wallet Candidate Evidence Plan

{GENERATED_MARKER}

## What This Dashboard Does

Review-only collection plan for top candidate wallets. Use this to decide where more replay/outcome evidence is needed before wallet promotion review.

## Summary

- Total candidates: {_count(summary.get("total_candidates"))}
- Ready for review: {_count(summary.get("ready_for_review"))}
- Needs replay coverage: {_count(summary.get("needs_replay_coverage"))}
- Needs outcome coverage: {_count(summary.get("needs_outcome_coverage"))}
- Risk review: {_count(summary.get("risk_review"))}

## Coverage Queue

{_candidate_evidence_plan_table(rows)}
"""
    return _note(frontmatter, body)


def render_wallet_candidate_backfill_targets(snapshot: dict[str, Any]) -> str:
    report = as_dict(snapshot.get("wallet_candidate_backfill_targets"))
    summary = as_dict(report.get("summary"))
    rows = [row for row in report.get("targets") or [] if isinstance(row, dict)][:25]
    frontmatter = _frontmatter("wallet_candidate_backfill_targets")
    body = f"""# Wallet Candidate Backfill Targets

{GENERATED_MARKER}

## What This Dashboard Does

Review-only target list for filling evidence gaps in the strongest candidate wallets. Use this to decide whether the next step is wallet-history collection, outcome-label backfill, more replay events, or risk review.

## Summary

- Total targets: {_count(summary.get("total_targets"))}
- Needs wallet history: {_count(summary.get("needs_wallet_history"))}
- Needs outcome-label backfill: {_count(summary.get("needs_outcome_label_backfill"))}
- Needs more replay events: {_count(summary.get("needs_more_replay_events"))}
- Risk review: {_count(summary.get("risk_review"))}
- Ready or hold: {_count(summary.get("ready_or_hold"))}

## Targets

{_candidate_backfill_targets_table(rows)}
"""
    return _note(frontmatter, body)


def render_wallet_history_backfill(snapshot: dict[str, Any]) -> str:
    report = as_dict(snapshot.get("wallet_history_backfill"))
    summary = as_dict(report.get("summary"))
    rows = [row for row in report.get("wallets") or [] if isinstance(row, dict)][:25]
    frontmatter = _frontmatter("wallet_history_backfill")
    body = f"""# Wallet History Backfill

{GENERATED_MARKER}

## What This Dashboard Does

Review-only wallet-history backfill report. This records fetched wallet evidence and block reasons without promoting, demoting, or trading.

## Summary

- Wallets processed: {_count(summary.get("wallets_processed"))}
- Successfully backfilled: {_count(summary.get("wallets_successfully_backfilled"))}
- Partially backfilled: {_count(summary.get("wallets_partially_backfilled"))}
- Blocked: {_count(summary.get("wallets_blocked"))}
- Evidence rows created: {_count(summary.get("total_evidence_rows_created"))}
- Ready for candidate review: {_count(summary.get("ready_for_candidate_review"))}

## Wallets

{_wallet_history_backfill_table(rows)}
"""
    return _note(frontmatter, body)


def render_wallet_evidence_enrichment(snapshot: dict[str, Any]) -> str:
    report = as_dict(snapshot.get("wallet_evidence_enrichment"))
    summary = as_dict(report.get("summary"))
    rows = [row for row in report.get("evidence_records") or [] if isinstance(row, dict)][:25]
    frontmatter = _frontmatter("wallet_evidence_enrichment")
    body = f"""# Wallet Evidence Enrichment

{GENERATED_MARKER}

## What This Dashboard Does

Review-only enrichment report. This attaches decision-time-safe market context and later outcome labels to wallet-history evidence without promoting, demoting, or trading.

## Summary

- Evidence rows: {_count(summary.get("total_evidence_rows"))}
- Enriched rows: {_count(summary.get("enriched_rows"))}
- Missing market context: {_count(summary.get("missing_market_context_rows"))}
- Missing outcome labels: {_count(summary.get("missing_outcome_label_rows"))}
- Rows with entry context: {_count(summary.get("rows_with_entry_context"))}
- Rows with known outcome: {_count(summary.get("rows_with_known_outcome"))}

## Evidence Rows

{_wallet_evidence_enrichment_table(rows)}
"""
    return _note(frontmatter, body)


def render_wallet_missing_market_context(snapshot: dict[str, Any]) -> str:
    report = as_dict(snapshot.get("wallet_missing_market_context"))
    summary = as_dict(report.get("summary"))
    rows = [row for row in report.get("targets") or [] if isinstance(row, dict)][:25]
    frontmatter = _frontmatter("wallet_missing_market_context")
    body = f"""# Wallet Missing Market Context

{GENERATED_MARKER}

## What This Dashboard Does

Review-only target list for wallet evidence rows that still lack decision-time market context. This identifies mints and time windows for future snapshot/tick backfill; it does not fetch data, promote wallets, or trade.

## Summary

- Target mints: {_count(summary.get("target_mints"))}
- Missing-context evidence rows: {_count(summary.get("missing_market_context_rows"))}
- Wallets affected: {_count(summary.get("wallets_affected"))}
- Targets with known outcomes: {_count(summary.get("targets_with_known_outcomes"))}

## Targets

{_wallet_missing_market_context_table(rows)}
"""
    return _note(frontmatter, body)


def render_wallet_replay_review(snapshot: dict[str, Any]) -> str:
    review = as_dict(snapshot.get("wallet_replay_review"))
    report = str(review.get("operator_report_markdown") or "").strip()
    if not report:
        summary = as_dict(review.get("summary"))
        report = "\n\n".join(
            [
                "# Wallet Replay Ecosystem Review",
                "Review-only. No wallet replay report is available yet.",
                "## Summary",
                f"- Reviewable wallets: `{summary.get('reviewable_wallets') or 0}`",
                f"- Low-coverage wallets: `{summary.get('low_coverage_wallets') or 0}`",
                f"- Co-entry pairs: `{summary.get('co_entry_pairs') or 0}`",
            ]
        )
    frontmatter = _frontmatter("wallet_replay_ecosystem_review")
    if report.startswith("# Wallet Replay Ecosystem Review"):
        report = report.split("\n", 1)[1].lstrip() if "\n" in report else ""
    body = f"""# Wallet Replay Ecosystem Review

## What This Dashboard Does

This shows replay-safe wallet evidence: which wallets have enough replay coverage, which remain low coverage, and where co-entry behavior may affect wallet trust.

{report}
"""
    return _note(frontmatter, body)


def render_forward_signal_operator_review(snapshot: dict[str, Any]) -> str:
    rollup = as_dict(snapshot.get("forward_signal_operator_rollup"))
    summary = as_dict(rollup.get("summary"))
    wallets = [row for row in rollup.get("wallets") or [] if isinstance(row, dict)][:25]
    checks: list[str] = []
    for row in wallets:
        for check in row.get("required_human_checks") or []:
            text = str(check)
            if text and text not in checks:
                checks.append(text)

    frontmatter = _frontmatter("forward_signal_operator_review")
    frontmatter["manual_review_required"] = _count_value(summary.get("manual_review_required"))
    frontmatter["repeatability_supported"] = _count_value(summary.get("repeatability_supported"))
    body = f"""# Forward Signal Operator Review

{GENERATED_MARKER}

## What This Dashboard Does

This is the one-file Obsidian review surface for repaired forward-signal wallets. It is for human review only. It does not approve wallet trust, wallet-list changes, or execution.

## Current Decision

{table(
    ["Area", "Count", "Meaning"],
    [
        ["Wallets", _count(summary.get("wallets")), "Wallets included in the forward-signal rollup"],
        ["Manual review required", _count(summary.get("manual_review_required")), "Human review needed before any future trust discussion"],
        ["Repeatability supported", _count(summary.get("repeatability_supported")), "Evidence survived the repeatability validator"],
        ["Promotions allowed", _count(summary.get("promotions_allowed")), "Must remain zero in this artifact"],
        ["Trust mutations allowed", _count(summary.get("trust_mutations_allowed")), "Must remain zero in this artifact"],
        ["Wallet-list mutations allowed", _count(summary.get("wallet_list_mutations_allowed")), "Must remain zero in this artifact"],
    ],
)}

## Wallets To Review

{_forward_signal_operator_wallet_table(wallets)}

## Required Human Checks

{bullet_list(checks or ["No required checks were emitted by the rollup."])}

## Safety

- Promotions allowed: `{summary.get("promotions_allowed", 0)}`
- Trust mutations allowed: `{summary.get("trust_mutations_allowed", 0)}`
- Wallet-list mutations allowed: `{summary.get("wallet_list_mutations_allowed", 0)}`
"""
    return _note(frontmatter, body)


def render_forward_enhanced_observation(snapshot: dict[str, Any]) -> str:
    report = as_dict(snapshot.get("forward_enhanced_observation"))
    summary = as_dict(report.get("summary"))
    wallets = [row for row in report.get("wallets") or [] if isinstance(row, dict)][:25]
    frontmatter = _frontmatter("forward_enhanced_observation")
    frontmatter["enhanced_observation_wallets"] = _count_value(summary.get("enhanced_observation_wallets"))
    body = f"""# Forward Enhanced Observation

{GENERATED_MARKER}

## What This Dashboard Does

This is the priority observation lane for forward-signal wallets that showed repeatable runner behavior but are still not trusted. It tells us which wallets deserve closer future tracking without approving promotion, wallet-list changes, wallet-trust changes, or execution.

## Summary

{table(
    ["Area", "Count", "Meaning"],
    [
        ["Enhanced observation wallets", _count(summary.get("enhanced_observation_wallets")), "Wallets to watch more closely"],
        ["Minimum next forward signals", _count(summary.get("minimum_next_forward_signals_per_wallet")), "Minimum future observations before another review"],
        ["Minimum distinct next token mints", _count(summary.get("minimum_distinct_next_token_mints_per_wallet")), "Breadth requirement for future behavior"],
        ["Promotions allowed", _count(summary.get("promotions_allowed")), "Must remain zero in this artifact"],
        ["Trust mutations allowed", _count(summary.get("wallet_trust_mutations_allowed")), "Must remain zero in this artifact"],
        ["Wallet-list mutations allowed", _count(summary.get("wallet_list_mutations_allowed")), "Must remain zero in this artifact"],
    ],
)}

## Wallets

{_forward_enhanced_observation_table(wallets)}

## Required Next Checks

{bullet_list(_forward_enhanced_observation_checks(wallets))}

## Safety

- Promotions allowed: `{summary.get("promotions_allowed", 0)}`
- Trust mutations allowed: `{summary.get("wallet_trust_mutations_allowed", 0)}`
- Wallet-list mutations allowed: `{summary.get("wallet_list_mutations_allowed", 0)}`
"""
    return _note(frontmatter, body)


def render_wallet_cycle_report(snapshot: dict[str, Any]) -> str:
    report = as_dict(snapshot.get("wallet_cycle_report"))
    counts = as_dict(report.get("counts"))
    queue = as_dict(report.get("review_queue"))
    decisions = as_dict(report.get("review_decisions"))
    replay = as_dict(report.get("replay"))
    latest_apply = as_dict(report.get("latest_apply"))
    latest_summary = as_dict(latest_apply.get("summary"))
    attention = report.get("attention") if isinstance(report.get("attention"), list) else []
    pending = as_dict(report.get("pending_candidates"))
    demotions = [row for row in pending.get("demotion_review") or [] if isinstance(row, dict)]
    promotions = [row for row in pending.get("promotion_review") or [] if isinstance(row, dict)]
    frontmatter = _frontmatter("wallet_cycle_report")
    body = f"""# Wallet Cycle Report

{GENERATED_MARKER}

## What This Dashboard Does

This shows wallet-list operating state: active/blocked wallets, pending promotion and demotion reviews, replay coverage, latest apply results, and attention flags.

## Core Counts

- Tracked wallets: {_count(counts.get("tracked_wallets"))}
- Active paper-watch wallets: {_count(counts.get("active_paper_watch_wallets"))}
- Blocked paper-watch wallets: {_count(counts.get("blocked_paper_watch_wallets"))}
- Bad wallets: {_count(counts.get("bad_wallets"))}

## Review Queue

- Pending promotion reviews: {_count(queue.get("promotion_review"))}
- Pending demotion reviews: {_count(queue.get("demotion_review"))}
- Resolved reviews: {_count(queue.get("resolved"))}
- Approved promotions: {_count(decisions.get("approved_promotion"))}
- Approved demotions: {_count(decisions.get("approved_demotion"))}

## Replay Coverage

- Replay events: {_count(replay.get("events"))}
- Replay wallets: {_count(replay.get("wallets"))}
- Co-entry pairs: {_count(replay.get("co_entry_pairs"))}
- Repeated pairs: {_count(replay.get("repeated_pair_count"))}

## Attention

{bullet_list([str(item) for item in attention] or ["No attention flags"])}

## Latest Apply

- Promoted: {_count(latest_summary.get("promoted"))}
- Demoted: {_count(latest_summary.get("demoted"))}
- Skipped: {_count(latest_summary.get("skipped"))}
- Backup: `{latest_apply.get("backup_dir") or "none"}`

## Pending Demotion Reviews

{_cycle_candidate_table(demotions)}

## Pending Promotion Reviews

{_cycle_candidate_table(promotions)}
"""
    return _note(frontmatter, body)


def render_anomaly_radar(snapshot: dict[str, Any], anomaly: dict[str, Any]) -> str:
    frontmatter = _frontmatter("anomaly_radar")
    replay = anomaly["replay_visibility"]
    body = f"""# MemeTraderPro Anomaly Radar

{GENERATED_MARKER}

## What This Dashboard Does

This surfaces wallet degradation, rejected-signal winners, rug-heavy wallets, unresolved postmortems, and replay anomalies that need review before trusting new wallet-driven signals.

## Wallet Degradation

{_wallet_table(anomaly["wallet_degradation"])}

## Promoted / Demoted Wallet Reviews

### Promotion Review

{_candidate_table(anomaly["promotion_reviews"])}

### Demotion Review

{_candidate_table(anomaly["demotion_reviews"])}

## Rejected-Signal Winners

{_rejected_winner_table(anomaly["rejected_signal_winners"])}

## Rug-Heavy Wallets

{_wallet_table(anomaly["rug_heavy_wallets"])}

## Unresolved Postmortems

{_postmortem_table(anomaly["unresolved_postmortems"])}

## Replay Anomalies

- Replay mode: {replay.get("mode") or "unknown"}
- Replay records: {as_dict(replay.get("counts")).get("records") or "unknown"}
- Review target: replay mismatches, missed runners, skipped winners, wallet-source disagreement.
"""
    return _note(frontmatter, body)


def render_drift_monitor(drift: dict[str, Any]) -> str:
    frontmatter = _frontmatter("drift_monitor")
    body = f"""# MemeTraderPro Drift Monitor

{GENERATED_MARKER}

## What This Dashboard Does

This tracks wallet-score drift and confidence mismatch so stale wallet weights, negative expectancy, and decaying signal quality are visible before tuning or trading decisions.

## Wallet-Score Drift

{_wallet_table(drift["wallet_score_drift"])}

## Confidence Mismatch

Wallets with high confidence but negative realized/replay expectancy.

{_wallet_table(drift["confidence_mismatch"])}

## Signal Drift Checks

{bullet_list(drift["signal_drift_queries"])}

## Static Drift Queues

- [[Top Wallets]]
- [[Wallets Pending Review]]
- [[Rug Association Watchlist]]
"""
    return _note(frontmatter, body)


def render_signal_lineage() -> str:
    frontmatter = _frontmatter("signal_lineage")
    body = f"""# MemeTraderPro Signal Lineage

{GENERATED_MARKER}

## What This Dashboard Does

This explains how MemeTraderPro evidence connects from signal to wallet, rejected signal or paper trade, replay finding, postmortem, and wallet review decision.

## Lineage Model

signal -> wallet -> rejected signal / paper trade -> replay finding -> postmortem -> wallet review decision

## Recent Rejected Signal Lineage

Open [[Rejected Signal Winners]] before drilling into raw rejected-signal detail.

## Postmortem Lineage

```dataview
TABLE generated_at, token_mint, paper_lane, classifications, triggering_wallets
FROM "MemeTraderPro/Postmortems"
WHERE type = "postmortem"
SORT generated_at DESC
LIMIT 50
```

## Wallet Review Lineage

```dataview
TABLE recommendation_action, audit_status, known_outcomes, promotion_score, demotion_score
FROM "MemeTraderPro/WalletCandidateReviews"
WHERE type = "wallet_candidate_review"
SORT known_outcomes DESC
LIMIT 50
```
"""
    return _note(frontmatter, body)


def render_daily_workflow(anomaly: dict[str, Any], drift: dict[str, Any]) -> str:
    frontmatter = _frontmatter("daily_workflow")
    body = f"""# MemeTraderPro Daily Research Workflow

{GENERATED_MARKER}

## What This Dashboard Does

This is the daily operating checklist for MemeTraderPro. Use it to review the command center, clear anomalies, check drift, record one observation, and turn repeated issues into hypotheses.

## Daily Review

1. Review [[MemeTraderPro Research Command Center]].
2. Clear [[MemeTraderPro Anomaly Radar]] top rows.
3. Check [[MemeTraderPro Drift Monitor]] for wallet-score drift.
4. Create one observation note in today's daily report.
5. Convert repeated anomalies into one hypothesis or experiment.

## Today's Queue Counts

- Wallet degradation: {len(anomaly["wallet_degradation"])}
- Rejected-signal winners: {len(anomaly["rejected_signal_winners"])}
- Unresolved postmortems: {len(anomaly["unresolved_postmortems"])}
- Wallet-score drift: {len(drift["wallet_score_drift"])}

## Do Not Browse

Start from the queue counts. Open raw folders only from a specific anomaly row.
"""
    return _note(frontmatter, body)


def render_shared_quant_dashboard() -> str:
    frontmatter = {
        "type": "shared_quant_dashboard",
        "source": "shared_quant",
        "generated_by": "quant_research_exporters",
    }
    body = """# Quant Research Command Center

GENERATED BY QUANT RESEARCH EXPORTERS - DO NOT EDIT BELOW THIS LINE

## What This Dashboard Does

This is the cross-project command center. It tells you which project surface to open first across Prop API, MemeTraderPro, NorthStar, and Threat Radar.

## What Matters Today

| Priority | Surface | Open | Why It Matters |
| --- | --- | --- | --- |
| P0 | Source-data health | [[Prop API Dashboard]] | Parser, coverage, and export blockers can invalidate NorthStar research. |
| P0 | Wallet intelligence drift | [[MemeTraderPro Research Command Center]] | Wallet degradation, replay gaps, and market-context gaps affect signal trust. |
| P0 | Betting model reliability | [[NorthStar Research Command Center]] | Calibration, CLV, replay, and EV review determine whether props are usable. |
| P0 | Token threat escalation | [[Daily Threat Radar Dashboard]] | High-risk warnings, false negatives, and unresolved reviews need fast attention. |

## Review First

1. Open [[Prop API Dashboard]] before trusting any new NorthStar inputs.
2. Open [[MemeTraderPro Research Command Center]] for wallet degradation, replay gaps, and market-context gaps.
3. Open [[NorthStar Research Command Center]] for positive-EV review, calibration drift, CLV drift, and replay failures.
4. Open [[Daily Threat Radar Dashboard]] for high-risk token warnings and unresolved validation reviews.
5. Update one experiment, postmortem, replay review, or parser/source fix.

## Cross-Project Command Centers

- [[MemeTraderPro Research Command Center]]
- [[NorthStar Research Command Center]]
- [[Prop API Dashboard]]
- [[Daily Threat Radar Dashboard]]

## Open Only If Needed

- [[MemeTraderPro Anomaly Radar]] - wallet degradation, rejected-signal winners, unresolved postmortems
- [[MemeTraderPro Drift Monitor]] - wallet score drift and confidence mismatch
- [[NorthStar Anomaly Radar]] - EV anomalies, missed winners, unresolved postmortems
- [[NorthStar Drift Monitor]] - calibration, CLV, confidence, and regime drift
- [[Milestone 7 Proof Report]] - Threat Radar validation proof and review queue
- [[Weekly Threat Intelligence Summary]] - Threat Radar pattern review

## Prop API Data Health

```dataview
TABLE coverage_percent, dates_covered, missing_date_ranges, accepted_rows, rejected_rows, export_readiness
FROM "PropAPI/CoverageReports"
WHERE type = "prop_api_coverage_summary"
SORT file.mtime DESC
LIMIT 5
```

## Prop API Parser Health

```dataview
TABLE issue_count, duplicate_count, missing_player_count, missing_odds_count, malformed_count
FROM "PropAPI/ParserIssues"
WHERE type = "prop_api_parser_issues"
SORT file.mtime DESC
LIMIT 10
```

## Threat Radar High-Risk Warnings

```dataview
TABLE risk_score, risk_level, confidence, validation_classification
FROM "ThreatRadar/HighRiskWarnings"
WHERE type = "high_risk_warning"
SORT risk_score DESC
LIMIT 10
```

## Threat Radar Validation Reviews

```dataview
TABLE classification
FROM "ThreatRadar/ValidationReviews"
WHERE type = "validation_review"
SORT file.mtime DESC
LIMIT 10
```

## Shared Postmortem Queue

```dataview
TABLE source, sport, market, status, validation_status
FROM "NorthStar/Postmortems" OR "MemeTraderPro/Postmortems"
WHERE type = "postmortem"
SORT file.mtime DESC
LIMIT 50
```

## Shared Experiment Queue

```dataview
TABLE source, sport, market, status, validation_status
FROM "NorthStar/Experiments"
WHERE type = "experiment"
SORT file.mtime DESC
LIMIT 50
```
"""
    return _note(frontmatter, body)


def render_shared_daily_review_checklist() -> str:
    frontmatter = {
        "type": "shared_daily_review_checklist",
        "source": "shared_quant",
        "generated_by": "quant_research_exporters",
    }
    body = """# Daily Review Checklist

GENERATED BY QUANT RESEARCH EXPORTERS - DO NOT EDIT BELOW THIS LINE

## What This Dashboard Does

This verifies whether each project exporter refreshed today and whether any command center has active P0 rows that should be reviewed first.

## Daily Review Complete

Use this page to confirm that each project exporter has refreshed today and whether any project has P0 rows.

## Exporter Freshness

```dataview
TABLE source, p0_count, file.mtime AS refreshed, choice(date(file.mtime) = date(today), "yes", "no") AS ran_today
FROM "MemeTraderPro/Dashboards" OR "NorthStar/Dashboards" OR "PropAPI/Dashboards" OR "ThreatRadar/Dashboards"
WHERE contains(["research_command_center", "prop_api_dashboard", "daily_threat_radar_dashboard"], type)
SORT source ASC
```

## P0 Rows Present

```dataview
TABLE source, p0_count, file.link AS dashboard
FROM "MemeTraderPro/Dashboards" OR "NorthStar/Dashboards" OR "PropAPI/Dashboards" OR "ThreatRadar/Dashboards"
WHERE contains(["research_command_center", "prop_api_dashboard", "daily_threat_radar_dashboard"], type) AND p0_count > 0
SORT p0_count DESC
```

## Review Order

1. If any exporter shows `ran_today = no`, run that exporter before reviewing stale dashboards.
2. If any dashboard has `p0_count > 0`, open that dashboard first.
3. If all exporters ran today and P0 is empty, review P1/P2 rows from the project command centers.
4. Record one daily observation or close one stale review item.
"""
    return _note(frontmatter, body)


def _frontmatter(note_type: str) -> dict[str, Any]:
    return {
        "type": note_type,
        "source": "memetraderpro",
        "generated_by": "memetraderpro",
    }


def _note(frontmatter: dict[str, Any], body: str) -> str:
    return f"{yaml_frontmatter(frontmatter)}\n\n{body.rstrip()}\n"


def _wallet_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "No wallet anomalies currently surfaced."
    return table(
        ["Wallet", "Action", "Score", "ROI", "Signals", "Rugs", "Runners"],
        [
            [
                wikilink(wallet_stem(str(row.get("wallet"))), short_id(row.get("wallet"))),
                as_dict(row.get("recommendation")).get("action") or row.get("status"),
                compact_number(_score(row), 1),
                compact_number(_wallet_roi(row), 2),
                row.get("signal_count") or row.get("total_signals") or row.get("signals"),
                row.get("rug_participation") or row.get("rug_count") or 0,
                row.get("runner_participation") or row.get("runner_count") or 0,
            ]
            for row in rows[:10]
        ],
    )


def _candidate_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "No unresolved candidate reviews in this category."
    return table(
        ["Wallet", "Candidate", "Status", "Known Outcomes", "Promotion", "Demotion"],
        [
            [
                wikilink(wallet_stem(str(row.get("wallet"))), short_id(row.get("wallet"))),
                wikilink(wallet_candidate_stem(row), "review"),
                row.get("audit_status"),
                as_dict(row.get("evidence")).get("known_outcomes"),
                as_dict(row.get("evidence")).get("promotion_score"),
                as_dict(row.get("evidence")).get("demotion_score"),
            ]
            for row in rows[:10]
        ],
    )


def _cycle_candidate_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "No rows."
    return table(
        ["Wallet", "Action", "Known", "Score", "Status"],
        [
            [
                wikilink(wallet_candidate_stem(row), short_id(row.get("wallet"))),
                row.get("recommendation_action") or "",
                _count(row.get("known_outcomes")),
                compact_number(row.get("score") or 0),
                row.get("audit_status") or "",
            ]
            for row in rows[:10]
        ],
    )


def _candidate_quality_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "No ranked candidate rows currently surfaced."
    return table(
        ["Wallet", "Quality", "Recommendation", "Winners", "Early", "Risk"],
        [
            [
                str(row.get("wallet") or ""),
                compact_number(row.get("quality_score") or 0, 1),
                row.get("recommended_observation") or "",
                _count(row.get("winner_mints")),
                _count(row.get("early_buy_events")),
                ", ".join(str(item) for item in row.get("risk_flags") or []) or "none",
            ]
            for row in rows[:10]
        ],
    )


def _candidate_quality_review_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "No candidate-quality review rows currently surfaced."
    return table(
        ["Wallet", "Quality", "Action", "Replay Known", "Fillable", "Gaps"],
        [
            [
                str(row.get("wallet") or ""),
                compact_number(row.get("quality_score") or 0, 1),
                as_dict(row.get("recommendation")).get("action") or "",
                _count(as_dict(row.get("replay")).get("known_15m")),
                _count(as_dict(row.get("replay")).get("fillable_events")),
                ", ".join(str(item) for item in row.get("evidence_gaps") or []) or "none",
            ]
            for row in rows[:10]
        ],
    )


def _candidate_evidence_plan_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "No candidate evidence plan rows currently surfaced."
    return table(
        ["Wallet", "Priority", "Next Action", "Missing Replay", "Missing Fillable", "Missing Outcomes"],
        [
            [
                str(row.get("wallet") or ""),
                compact_number(row.get("priority_score") or 0, 1),
                row.get("next_action") or "",
                _count(as_dict(row.get("missing")).get("replay_known_15m")),
                _count(as_dict(row.get("missing")).get("fillable_events")),
                _count(as_dict(row.get("missing")).get("known_outcomes")),
            ]
            for row in rows[:10]
        ],
    )


def _candidate_backfill_targets_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "No candidate backfill target rows currently surfaced."
    return table(
        ["Wallet", "Priority", "Next Step", "Local Events", "Unknown 15m", "Missing Replay", "Missing Outcomes"],
        [
            [
                str(row.get("wallet") or ""),
                compact_number(row.get("priority_score") or 0, 1),
                row.get("next_collection_step") or "",
                _count(row.get("local_replay_events")),
                _count(row.get("unknown_15m_events")),
                _count(as_dict(row.get("missing")).get("replay_known_15m")),
                _count(as_dict(row.get("missing")).get("known_outcomes")),
            ]
            for row in rows[:10]
        ],
    )


def _wallet_history_backfill_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "No wallet-history backfill rows currently surfaced."
    return table(
        ["Wallet", "Status", "Target Status", "Evidence Rows", "Confidence"],
        [
            [
                str(row.get("wallet") or ""),
                row.get("status") or "",
                row.get("target_status") or "",
                _count(row.get("evidence_rows_created")),
                compact_number(as_dict(row.get("metrics")).get("evidence_confidence_score") or 0, 1),
            ]
            for row in rows[:10]
        ],
    )


def _wallet_evidence_enrichment_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "No enriched wallet-evidence rows currently surfaced."
    return table(
        ["Wallet", "Mint", "Status", "Action", "Entry Price", "Liquidity", "Outcome", "Confidence"],
        [
            [
                str(row.get("wallet") or ""),
                str(row.get("token_mint") or ""),
                row.get("enrichment_status") or "",
                row.get("observed_action") or "",
                compact_number(as_dict(row.get("estimated_entry_context")).get("price") or 0, 6),
                compact_number(as_dict(row.get("estimated_entry_context")).get("liquidity") or 0, 1),
                as_dict(row.get("later_token_outcome")).get("outcome_type") or "unknown",
                compact_number(row.get("confidence_score") or 0, 1),
            ]
            for row in rows[:10]
        ],
    )


def _wallet_missing_market_context_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "No missing market-context targets currently surfaced."
    return table(
        ["Mint", "Step", "Rows", "Wallets", "Known Outcomes", "Start", "End"],
        [
            [
                str(row.get("token_mint") or ""),
                row.get("next_collection_step") or "",
                _count(row.get("evidence_rows")),
                _count(row.get("unique_wallets")),
                _count(row.get("known_outcome_rows")),
                short_datetime(as_dict(row.get("backfill_window")).get("start_time")),
                short_datetime(as_dict(row.get("backfill_window")).get("end_time")),
            ]
            for row in rows[:10]
        ],
    )


def _forward_signal_operator_wallet_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "No forward-signal operator review rows currently surfaced."
    return table(
        [
            "Wallet",
            "Decision",
            "Validation",
            "Runner Rows",
            "Unknown 15m",
            "Runner Mints",
            "Span Seconds",
            "Top Mint",
            "Mutation Locks",
        ],
        [
            [
                str(row.get("wallet") or ""),
                row.get("decision_type") or "",
                row.get("validation_status") or "",
                _count(row.get("runner_rows")),
                _count(row.get("unknown_15m_rows")),
                _count(row.get("runner_distinct_token_mints")),
                compact_number(row.get("runner_signal_span_seconds") or 0, 1),
                _top_forward_token_mint(row),
                _forward_mutation_locks(row),
            ]
            for row in rows[:10]
        ],
    )


def _top_forward_token_mint(row: dict[str, Any]) -> str:
    mints = [item for item in row.get("top_token_mints") or [] if isinstance(item, dict)]
    if not mints:
        return "none"
    top = mints[0]
    mint = str(top.get("token_mint") or "")
    rows = _count(top.get("rows"))
    return f"{mint} ({rows})" if mint else f"unknown ({rows})"


def _forward_mutation_locks(row: dict[str, Any]) -> str:
    locked = []
    if not bool(row.get("promotion_allowed")):
        locked.append("promotion")
    if not bool(row.get("wallet_trust_mutation_allowed")):
        locked.append("trust")
    if not bool(row.get("wallet_list_mutation_allowed")):
        locked.append("list")
    return ", ".join(locked) or "none"


def _forward_enhanced_observation_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "No enhanced-observation wallets currently surfaced."
    return table(
        [
            "Wallet",
            "Lane",
            "Action",
            "Trust",
            "Runner Rows",
            "Unknown 15m",
            "Runner Mints",
            "Next Signals",
            "Next Mints",
            "Mutation Locks",
        ],
        [
            [
                str(row.get("wallet") or ""),
                row.get("observation_lane") or "",
                row.get("review_action") or "",
                row.get("trust_status") or "",
                _count(as_dict(row.get("evidence_summary")).get("runner_rows")),
                _count(as_dict(row.get("evidence_summary")).get("unknown_15m_rows")),
                _count(as_dict(row.get("evidence_summary")).get("runner_distinct_token_mints")),
                _count(row.get("minimum_next_forward_signals")),
                _count(row.get("minimum_distinct_next_token_mints")),
                _forward_mutation_locks(row),
            ]
            for row in rows[:10]
        ],
    )


def _forward_enhanced_observation_checks(rows: list[dict[str, Any]]) -> list[str]:
    checks: list[str] = []
    for row in rows:
        recommendation = str(row.get("operator_recommendation") or "")
        if recommendation and recommendation not in checks:
            checks.append(recommendation)
        for check in row.get("required_next_checks") or []:
            text = str(check)
            if text and text not in checks:
                checks.append(text)
    return checks or ["No enhanced-observation checks were emitted."]


def _count(value: Any) -> str:
    return f"{_count_value(value):,}"


def _count_value(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _rejected_winner_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "No rejected-signal winners currently surfaced."
    return table(
        ["Rejected Signal", "Mint", "Reason", "Outcome"],
        [
            [
                wikilink(rejected_signal_stem(row), "rejection"),
                row.get("mint") or as_dict(row.get("signal context")).get("mint"),
                row.get("rejection reason"),
                as_dict(row.get("what would have happened afterward if traded")).get("status"),
            ]
            for row in rows[:10]
        ],
    )


def _postmortem_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "No unresolved postmortems currently surfaced."
    return table(
        ["Postmortem", "Mint", "Status", "Lane"],
        [
            [
                wikilink(postmortem_stem(row), "postmortem"),
                row.get("mint") or row.get("token_mint"),
                row.get("status"),
                row.get("paper_lane"),
            ]
            for row in rows[:10]
        ],
    )


def _score(row: dict[str, Any]) -> float:
    for value in (
        as_dict(row.get("behavior_score")).get("score"),
        as_dict(row.get("confidence")).get("score"),
        row.get("confidence_score"),
        row.get("score"),
    ):
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def _wallet_roi(row: dict[str, Any]) -> float:
    for value in (
        as_dict(row.get("behavior_profile")).get("wallet_roi"),
        row.get("paper_watch_expectancy"),
        row.get("average_pnl_after_signal"),
        row.get("roi"),
    ):
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def _wallet_alert_sort(row: dict[str, Any]) -> float:
    return abs(min(_wallet_roi(row), 0)) + max(0, 50 - _score(row))
