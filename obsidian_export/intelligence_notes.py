from __future__ import annotations

from typing import Any

from obsidian_export.candidate_note import wallet_candidate_stem
from obsidian_export.markdown import (
    GENERATED_MARKER,
    as_dict,
    bullet_list,
    compact_number,
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
        "Dashboards/MemeTraderPro Signal Lineage.md": render_signal_lineage(),
        "Dashboards/MemeTraderPro Daily Workflow.md": render_daily_workflow(anomaly, drift),
        "../SharedQuant/Dashboards/Quant Research Command Center.md": render_shared_quant_dashboard(),
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
    body = f"""# MemeTraderPro Research Command Center

{GENERATED_MARKER}

## Action Queue

- Wallet degradation alerts: {len(anomaly["wallet_degradation"])}
- Promotion review candidates: {len(anomaly["promotion_reviews"])}
- Demotion review candidates: {len(anomaly["demotion_reviews"])}
- Rejected-signal winners: {len(anomaly["rejected_signal_winners"])}
- Unresolved postmortems: {len(anomaly["unresolved_postmortems"])}
- Wallet-score drift rows: {len(drift["wallet_score_drift"])}
- Wallet replay reviewable wallets: {replay_summary.get("reviewable_wallets") or 0}
- Wallet replay low-coverage wallets: {replay_summary.get("low_coverage_wallets") or 0}
- Active paper-watch wallets: {cycle_counts.get("active_paper_watch_wallets") or 0}
- Blocked paper-watch wallets: {cycle_counts.get("blocked_paper_watch_wallets") or 0}
- Pending wallet demotions: {cycle_queue.get("demotion_review") or 0}
- Active candidate-quality rows: {quality_summary.get("active_candidates") or 0}
- Strong candidate observations: {quality_summary.get("strong_observation") or 0}
- Candidate promotion-ready rows: {quality_review_summary.get("promotion_review_ready") or 0}
- Candidate evidence gaps needing replay: {evidence_plan_summary.get("needs_replay_coverage") or 0}
- Candidate wallet-history backfill targets: {backfill_summary.get("needs_wallet_history") or 0}
- Candidate outcome-label backfill targets: {backfill_summary.get("needs_outcome_label_backfill") or 0}
- Wallet-history evidence rows created: {history_summary.get("total_evidence_rows_created") or 0}
- Wallet evidence enriched rows: {enrichment_summary.get("enriched_rows") or 0}
- Wallet evidence missing market context: {enrichment_summary.get("missing_market_context_rows") or 0}
- Missing market-context target mints: {missing_context_summary.get("target_mints") or 0}

## Review First

1. Open [[MemeTraderPro Anomaly Radar]].
2. Resolve any rejected-signal winners before tuning thresholds.
3. Review demotion candidates before trusting wallet-sourced signals.
4. Promote only when replay and postmortem evidence agree.
5. Log one daily observation in the daily report.

## Focus Dashboards

- [[MemeTraderPro Anomaly Radar]]
- [[MemeTraderPro Drift Monitor]]
- [[Wallet Cycle Report]]
- [[Wallet Candidate Quality]]
- [[Wallet Candidate Quality Review]]
- [[Wallet Candidate Evidence Plan]]
- [[Wallet Candidate Backfill Targets]]
- [[Wallet History Backfill]]
- [[Wallet Evidence Enrichment]]
- [[Wallet Missing Market Context]]
- [[Wallet Replay Ecosystem Review]]
- [[MemeTraderPro Signal Lineage]]
- [[MemeTraderPro Daily Workflow]]
- [[Wallet Review Decisions]]
- [[Top Wallets]]
- [[Wallets Pending Review]]
- [[Rejected Signal Winners]]

## Not Raw Data

This page is the queue. Use folder tables only after an anomaly or experiment points there.
"""
    return _note(frontmatter, body)


def render_wallet_candidate_quality(snapshot: dict[str, Any]) -> str:
    report = as_dict(snapshot.get("wallet_candidate_quality_report"))
    summary = as_dict(report.get("summary"))
    rows = [row for row in report.get("ranked_candidates") or [] if isinstance(row, dict)][:25]
    frontmatter = _frontmatter("wallet_candidate_quality_report")
    body = f"""# Wallet Candidate Quality

{GENERATED_MARKER}

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
    return _note(frontmatter, f"{report}\n")


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
    body = f"""# Quant Research Command Center

{GENERATED_MARKER}

## Cross-Project Anomaly Radar

- [[MemeTraderPro Research Command Center]]
- [[MemeTraderPro Anomaly Radar]]
- [[MemeTraderPro Drift Monitor]]
- [[NorthStar Research Command Center]]
- [[NorthStar Anomaly Radar]]
- [[NorthStar Drift Monitor]]
- [[Prop API Dashboard]]

## Daily Research Loop

1. Review project command centers.
2. Check [[Prop API Dashboard]] for coverage, parser, source, and export readiness before trusting new prop inputs.
3. Resolve anomalies before browsing raw notes.
4. Promote one strong hypothesis into an experiment.
5. Close or update stale postmortems.
6. Record one daily observation.

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
                compact_number(_score(row), 4),
                compact_number(_wallet_roi(row), 6),
                row.get("signal_count") or row.get("total_signals") or row.get("signals"),
                row.get("rug_participation") or row.get("rug_count") or 0,
                row.get("runner_participation") or row.get("runner_count") or 0,
            ]
            for row in rows[:25]
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
            for row in rows[:25]
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
            for row in rows[:25]
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
                compact_number(row.get("quality_score") or 0, 6),
                row.get("recommended_observation") or "",
                _count(row.get("winner_mints")),
                _count(row.get("early_buy_events")),
                ", ".join(str(item) for item in row.get("risk_flags") or []) or "none",
            ]
            for row in rows[:25]
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
                compact_number(row.get("quality_score") or 0, 6),
                as_dict(row.get("recommendation")).get("action") or "",
                _count(as_dict(row.get("replay")).get("known_15m")),
                _count(as_dict(row.get("replay")).get("fillable_events")),
                ", ".join(str(item) for item in row.get("evidence_gaps") or []) or "none",
            ]
            for row in rows[:25]
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
                compact_number(row.get("priority_score") or 0, 6),
                row.get("next_action") or "",
                _count(as_dict(row.get("missing")).get("replay_known_15m")),
                _count(as_dict(row.get("missing")).get("fillable_events")),
                _count(as_dict(row.get("missing")).get("known_outcomes")),
            ]
            for row in rows[:25]
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
                compact_number(row.get("priority_score") or 0, 6),
                row.get("next_collection_step") or "",
                _count(row.get("local_replay_events")),
                _count(row.get("unknown_15m_events")),
                _count(as_dict(row.get("missing")).get("replay_known_15m")),
                _count(as_dict(row.get("missing")).get("known_outcomes")),
            ]
            for row in rows[:25]
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
                compact_number(as_dict(row.get("metrics")).get("evidence_confidence_score") or 0, 6),
            ]
            for row in rows[:25]
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
                compact_number(as_dict(row.get("estimated_entry_context")).get("liquidity") or 0, 6),
                as_dict(row.get("later_token_outcome")).get("outcome_type") or "unknown",
                compact_number(row.get("confidence_score") or 0, 6),
            ]
            for row in rows[:25]
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
                compact_number(as_dict(row.get("backfill_window")).get("start_time") or 0, 6),
                compact_number(as_dict(row.get("backfill_window")).get("end_time") or 0, 6),
            ]
            for row in rows[:25]
        ],
    )


def _count(value: Any) -> str:
    try:
        return f"{int(float(value or 0)):,}"
    except (TypeError, ValueError):
        return "0"


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
            for row in rows[:25]
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
            for row in rows[:25]
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
