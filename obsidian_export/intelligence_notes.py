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

## Review First

1. Open [[MemeTraderPro Anomaly Radar]].
2. Resolve any rejected-signal winners before tuning thresholds.
3. Review demotion candidates before trusting wallet-sourced signals.
4. Promote only when replay and postmortem evidence agree.
5. Log one daily observation in the daily report.

## Focus Dashboards

- [[MemeTraderPro Anomaly Radar]]
- [[MemeTraderPro Drift Monitor]]
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
