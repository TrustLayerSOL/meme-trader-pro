"""Replay-safe holder-state feasibility pilot from normalized lifecycle events."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


HOLDER_SNAPSHOT_AGES = [30, 180, 600, 1800, 7200]
MAX_LAUNCHES = 50
MAX_HOLDER_SNAPSHOTS = 250
HOLDER_DISTRIBUTION_SOURCE = "offline_normalized_event_delta_replay_v0"


def build_holder_state_pilot_report(
    *,
    candidates_path: Path | str,
    events_path: Path | str,
    launch_limit: int = MAX_LAUNCHES,
) -> dict[str, Any]:
    candidates = _select_candidates(_read_jsonl(candidates_path), launch_limit)
    events_by_mint = _events_by_mint(_read_jsonl(events_path), {row["token_mint"] for row in candidates})
    holder_snapshots: list[dict[str, Any]] = []
    for candidate in candidates:
        holder_snapshots.extend(_build_launch_holder_snapshots(candidate, events_by_mint.get(candidate["token_mint"], [])))

    attempted = len(candidates) * len(HOLDER_SNAPSHOT_AGES)
    built = sum(1 for row in holder_snapshots if row["holder_count"] is not None)
    missing = attempted - built
    missing_reasons = Counter(
        row["holder_snapshot_missing_reason"] for row in holder_snapshots if row["holder_snapshot_missing_reason"]
    )
    confidence_distribution = Counter(row["holder_snapshot_confidence"] for row in holder_snapshots)
    scale_snapshots = 1500 * len(HOLDER_SNAPSHOT_AGES)
    field_coverage = {
        "holder_count": _field_coverage(holder_snapshots, "holder_count", attempted),
        "top_holder_share": _field_coverage(holder_snapshots, "top_holder_share", attempted),
        "top_10_holder_share": _field_coverage(holder_snapshots, "top_10_holder_share", attempted),
        "creator_holder_share": _field_coverage(holder_snapshots, "creator_holder_share", attempted),
    }
    report = {
        "pilot_id": "holder_state_feasibility_pilot_v0",
        "scope": "data_readiness_pilot_only",
        "hard_limits": {
            "max_launches": MAX_LAUNCHES,
            "max_holder_snapshots": MAX_HOLDER_SNAPSHOTS,
            "snapshot_ages_seconds": HOLDER_SNAPSHOT_AGES,
        },
        "methodology_flags": [
            "research_only",
            "data_readiness_only",
            "no_thesis_rerun",
            "no_backtest",
            "no_walk_forward_validation",
            "no_trading_logic",
            "no_threshold_optimization",
            "no_grid_search",
            "no_ml_black_boxes",
            "no_silent_holder_state_inference",
        ],
        "offline_reconstruction_audit": _offline_reconstruction_audit(events_by_mint),
        "feasibility_audit": _feasibility_audit(events_by_mint),
        "launches_attempted": len(candidates),
        "launches_completed": len({row["launch_id"] for row in holder_snapshots if row["holder_count"] is not None}),
        "launches_failed": len(candidates) - len({row["launch_id"] for row in holder_snapshots if row["holder_count"] is not None}),
        "snapshots_attempted": attempted,
        "snapshots_built": built,
        "missing_snapshots": missing,
        "missing_reasons": dict(sorted(missing_reasons.items())),
        "missing_reason_counts": _missing_reason_counts(missing_reasons),
        "confidence_distribution": dict(sorted(confidence_distribution.items())),
        "field_coverage": field_coverage,
        "holder_count_coverage_pct": field_coverage["holder_count"]["coverage_pct"],
        "top_holder_share_coverage_pct": field_coverage["top_holder_share"]["coverage_pct"],
        "top_10_holder_share_coverage_pct": field_coverage["top_10_holder_share"]["coverage_pct"],
        "creator_holder_share_coverage_pct": field_coverage["creator_holder_share"]["coverage_pct"],
        "api_calls_used": 0,
        "helius_credits_used": 0,
        "api_requirements": {
            "used_in_pilot": False,
            "api_calls_used": 0,
            "helius_credits_used": 0,
            "estimated_historical_holder_snapshots_for_1500_launches": scale_snapshots,
            "estimated_minimum_calls_if_external_snapshot_endpoint_exists": scale_snapshots,
            "estimated_helius_credits_for_1500_launches": 0,
            "estimated_helius_credits_for_3000_launches": 0,
            "cost_note": (
                "No API calls were used. If historical holder snapshots require an external indexed endpoint, "
                "a naive scale-up is one holder-state request per launch-age snapshot."
            ),
        },
        "estimated_cost_to_scale_to_1500_launches": {
            "launches": 1500,
            "holder_snapshots": scale_snapshots,
            "offline_event_replay_api_calls": 0,
            "helius_credits": 0,
            "external_snapshot_api_calls_if_required": scale_snapshots,
        },
        "estimated_cost_to_scale_to_3000_launches": {
            "launches": 3000,
            "holder_snapshots": 3000 * len(HOLDER_SNAPSHOT_AGES),
            "offline_event_replay_api_calls": 0,
            "helius_credits": 0,
            "external_snapshot_api_calls_if_required": 3000 * len(HOLDER_SNAPSHOT_AGES),
        },
        "holder_distribution_source": HOLDER_DISTRIBUTION_SOURCE,
        "holder_snapshots": holder_snapshots,
        "feasibility_result": _feasibility_result(built, attempted),
        "t001_v2_feasible": built == attempted and field_coverage["top_holder_share"]["available_snapshots"] == attempted,
        "t002_v2_feasible": built == attempted and field_coverage["holder_count"]["available_snapshots"] == attempted,
        "t001_t002_v2_feasible": built == attempted,
        "next_recommendation": _next_recommendation(built, attempted),
    }
    return report


def write_holder_state_pilot_outputs(report: dict[str, Any], *, output_dir: Path | str) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "holder_state_pilot_summary.json"
    markdown_path = output / "holder_state_pilot_summary.md"
    quality_json_path = output / "holder_state_pilot_quality_report.json"
    quality_markdown_path = output / "holder_state_pilot_quality_report.md"
    feasibility_audit_path = output / "holder_state_feasibility_audit.md"
    rollout_recommendation_path = output / "holder_state_rollout_recommendation.md"
    snapshots_path = output / "holder_state_snapshots.jsonl"
    json_path.write_text(json.dumps(_public_report(report), indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(_markdown_report(report), encoding="utf-8")
    quality_json_path.write_text(json.dumps(_quality_report(report), indent=2, sort_keys=True), encoding="utf-8")
    quality_markdown_path.write_text(_quality_markdown_report(report), encoding="utf-8")
    feasibility_audit_path.write_text(_feasibility_audit_markdown(report), encoding="utf-8")
    rollout_recommendation_path.write_text(_rollout_recommendation_markdown(report), encoding="utf-8")
    with snapshots_path.open("w", encoding="utf-8") as f:
        for row in report["holder_snapshots"]:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return {
        "json_summary_path": json_path,
        "markdown_summary_path": markdown_path,
        "quality_json_path": quality_json_path,
        "quality_markdown_path": quality_markdown_path,
        "feasibility_audit_path": feasibility_audit_path,
        "rollout_recommendation_path": rollout_recommendation_path,
        "holder_snapshots_path": snapshots_path,
    }


def _select_candidates(rows: list[dict[str, Any]], launch_limit: int) -> list[dict[str, Any]]:
    limit = min(MAX_LAUNCHES, max(0, int(launch_limit)))
    eligible = [row for row in rows if row.get("token_mint") and row.get("launch_ts")]
    return sorted(eligible, key=lambda row: (int(row["launch_ts"]), row["token_mint"]))[:limit]


def _events_by_mint(rows: list[dict[str, Any]], mints: set[str]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        mint = row.get("token_mint")
        if mint in mints:
            grouped[mint].append(row)
    return {mint: sorted(events, key=lambda row: (int(row.get("block_time") or 0), row.get("signature") or "")) for mint, events in grouped.items()}


def _build_launch_holder_snapshots(candidate: dict[str, Any], events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    launch_ts = int(candidate["launch_ts"])
    token_mint = candidate["token_mint"]
    balances: dict[str, float] = {}
    event_index = 0
    previous_holders: set[str] | None = None
    snapshots: list[dict[str, Any]] = []
    for age in HOLDER_SNAPSHOT_AGES:
        snapshot_ts = launch_ts + age
        while event_index < len(events) and int(events[event_index].get("block_time") or 0) <= snapshot_ts:
            event = events[event_index]
            actor = event.get("actor")
            delta = _event_balance_delta(event)
            if actor and delta is not None:
                balances[str(actor)] = balances.get(str(actor), 0.0) + delta
                if balances[str(actor)] <= 0:
                    balances.pop(str(actor), None)
            event_index += 1
        current_holders = {holder for holder, balance in balances.items() if balance > 0}
        snapshot = _snapshot_row(
            candidate=candidate,
            launch_age_seconds=age,
            snapshot_ts=snapshot_ts,
            balances=balances,
            previous_holders=previous_holders,
            observed_events=len([event for event in events if int(event.get("block_time") or 0) <= snapshot_ts]),
        )
        snapshots.append(snapshot)
        if current_holders:
            previous_holders = current_holders
    return snapshots


def _snapshot_row(
    *,
    candidate: dict[str, Any],
    launch_age_seconds: int,
    snapshot_ts: int,
    balances: dict[str, float],
    previous_holders: set[str] | None,
    observed_events: int,
) -> dict[str, Any]:
    positive = {holder: balance for holder, balance in balances.items() if balance > 0}
    total = sum(positive.values())
    creator = _creator_wallet(candidate)
    if not positive or total <= 0:
        return _base_snapshot(candidate, launch_age_seconds, snapshot_ts, observed_events) | {
            "holder_count": None,
            "top_holder_share": None,
            "top_10_holder_share": None,
            "creator_holder_share": None,
            "creator_linked_share": None,
            "holder_snapshot_source": HOLDER_DISTRIBUTION_SOURCE,
            "holder_distribution_source": HOLDER_DISTRIBUTION_SOURCE,
            "holder_snapshot_confidence": "missing",
            "holder_snapshot_missing_reason": "no_observed_holder_balances_at_snapshot",
            "holder_retention_proxy": None,
            "holder_churn_proxy": None,
        }
    sorted_balances = sorted(positive.values(), reverse=True)
    current_holders = set(positive)
    retention = _retention_proxy(previous_holders, current_holders)
    return _base_snapshot(candidate, launch_age_seconds, snapshot_ts, observed_events) | {
        "holder_count": len(positive),
        "top_holder_share": sorted_balances[0] / total,
        "top_10_holder_share": sum(sorted_balances[:10]) / total,
        "creator_holder_share": _creator_holder_share(positive, total, creator),
        "creator_linked_share": _creator_holder_share(positive, total, creator),
        "holder_snapshot_source": HOLDER_DISTRIBUTION_SOURCE,
        "holder_distribution_source": HOLDER_DISTRIBUTION_SOURCE,
        "holder_snapshot_confidence": "medium",
        "holder_snapshot_missing_reason": None,
        "holder_retention_proxy": retention,
        "holder_churn_proxy": (1.0 - retention) if retention is not None else None,
    }


def _base_snapshot(candidate: dict[str, Any], launch_age_seconds: int, snapshot_ts: int, observed_events: int) -> dict[str, Any]:
    return {
        "launch_id": candidate["launch_id"],
        "token_mint": candidate["token_mint"],
        "pool_address": candidate.get("pool_address"),
        "venue": candidate.get("venue"),
        "launch_ts": int(candidate["launch_ts"]),
        "snapshot_ts": snapshot_ts,
        "launch_age_seconds": launch_age_seconds,
        "observed_event_count_through_snapshot": observed_events,
    }


def _event_balance_delta(event: dict[str, Any]) -> float | None:
    qty = _float_or_none(event.get("base_qty"))
    if qty is None:
        return None
    side = str(event.get("side") or "").lower()
    event_type = str(event.get("event_type") or "").lower()
    if side in {"buy", "accumulate"} or event_type in {"possible_buy", "token_accumulation", "pumpfun_buy"}:
        return abs(qty)
    if side in {"sell", "distribute"} or event_type in {"possible_sell", "token_distribution", "pumpfun_sell"}:
        return -abs(qty)
    return None


def _retention_proxy(previous_holders: set[str] | None, current_holders: set[str]) -> float | None:
    if not previous_holders:
        return None
    return len(previous_holders & current_holders) / len(previous_holders)


def _creator_wallet(candidate: dict[str, Any]) -> str | None:
    metadata = candidate.get("metadata_json") or {}
    return (
        candidate.get("creator_wallet")
        or candidate.get("creator_deployer")
        or metadata.get("creator_deployer")
        or metadata.get("creator_wallet")
    )


def _creator_holder_share(positive: dict[str, float], total: float, creator: str | None) -> float | None:
    if not creator or total <= 0:
        return None
    return positive.get(str(creator), 0.0) / total


def _offline_reconstruction_audit(events_by_mint: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    total_events = sum(len(events) for events in events_by_mint.values())
    events_with_actor = sum(1 for events in events_by_mint.values() for event in events if event.get("actor"))
    events_with_qty = sum(1 for events in events_by_mint.values() for event in events if _float_or_none(event.get("base_qty")) is not None)
    usable_events = sum(
        1
        for events in events_by_mint.values()
        for event in events
        if event.get("actor") and _event_balance_delta(event) is not None
    )
    return {
        "source": HOLDER_DISTRIBUTION_SOURCE,
        "tokens_with_events": len(events_by_mint),
        "total_events": total_events,
        "events_with_actor": events_with_actor,
        "events_with_base_qty": events_with_qty,
        "usable_balance_delta_events": usable_events,
        "offline_possible": usable_events > 0,
        "quality_note": (
            "This reconstructs observed holder balances from normalized lifecycle event deltas. "
            "It is replay-safe but not a confirmed full chain account-state snapshot."
        ),
    }


def _feasibility_audit(events_by_mint: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    offline_possible = _offline_reconstruction_audit(events_by_mint)["offline_possible"]
    return {
        "holder_count": {
            "already_available": False,
            "offline_reconstructable": offline_possible,
            "requires_external_reads": False,
            "notes": "Can be reconstructed as observed positive actor balances from normalized lifecycle event deltas.",
        },
        "top_holder_share": {
            "already_available": False,
            "offline_reconstructable": offline_possible,
            "requires_external_reads": False,
            "notes": "Can be derived from observed holder balances; not a confirmed full chain account-state snapshot.",
        },
        "top_10_holder_share": {
            "already_available": False,
            "offline_reconstructable": offline_possible,
            "requires_external_reads": False,
            "notes": "Can be derived from observed holder balances when event deltas are complete enough.",
        },
        "holder_retention": {
            "already_available": False,
            "offline_reconstructable": offline_possible,
            "requires_external_reads": False,
            "notes": "Retention proxy compares observed holders between launch-relative snapshots.",
        },
        "holder_churn": {
            "already_available": False,
            "offline_reconstructable": offline_possible,
            "requires_external_reads": False,
            "notes": "Churn proxy is one minus retention proxy when prior holder state exists.",
        },
        "creator_ownership": {
            "already_available": False,
            "offline_reconstructable": offline_possible,
            "requires_external_reads": False,
            "notes": "Creator holder share is deterministic when creator wallet exists in candidate metadata.",
        },
        "bundle_linked_ownership": {
            "already_available": False,
            "offline_reconstructable": False,
            "requires_external_reads": True,
            "notes": "Bundle-linked ownership requires explicit bundle or linked-wallet evidence; not inferred in this pilot.",
        },
        "entity_collapsed_ownership": {
            "already_available": False,
            "offline_reconstructable": False,
            "requires_external_reads": True,
            "notes": "Entity-collapsed ownership requires a separate audited entity-linkage workflow.",
        },
    }


def _feasibility_result(built: int, attempted: int) -> str:
    if attempted == 0 or built == 0:
        return "blocked"
    coverage = built / attempted
    if coverage >= 0.8:
        return "feasible_offline"
    return "feasible_with_api"


def _next_recommendation(built: int, attempted: int) -> str:
    result = _feasibility_result(built, attempted)
    if result == "feasible_offline":
        return "scale offline holder-state replay to the strict cohort, then rerun T001/T002 v2 after coverage audit"
    if result == "feasible_with_api":
        return "use offline replay where available and evaluate an indexed historical holder-state API for missing snapshots"
    return "blocked until historical holder-state snapshots can be sourced or normalized event coverage is repaired"


def _public_report(report: dict[str, Any]) -> dict[str, Any]:
    public = dict(report)
    public.pop("holder_snapshots", None)
    return public


def _quality_report(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "pilot_id": report["pilot_id"],
        "launch_coverage": {
            "launches_attempted": report["launches_attempted"],
            "launches_completed": report["launches_completed"],
            "launches_failed": report["launches_failed"],
        },
        "snapshot_coverage": {
            "snapshots_attempted": report["snapshots_attempted"],
            "snapshots_built": report["snapshots_built"],
            "snapshots_missing": report["missing_snapshots"],
        },
        "field_coverage": report["field_coverage"],
        "missing_reason_counts": report["missing_reason_counts"],
        "confidence_distribution": report["confidence_distribution"],
        "api_calls_used": report["api_calls_used"],
        "helius_credits_used": report["helius_credits_used"],
        "feasibility_result": report["feasibility_result"],
        "t001_v2_feasible": report["t001_v2_feasible"],
        "t002_v2_feasible": report["t002_v2_feasible"],
    }


def _markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# Holder-State Enrichment Feasibility Pilot",
        "",
        f"- Feasibility result: `{report['feasibility_result']}`",
        f"- Launches attempted: `{report['launches_attempted']}`",
        f"- Snapshots attempted: `{report['snapshots_attempted']}`",
        f"- Snapshots built: `{report['snapshots_built']}`",
        f"- Missing snapshots: `{report['missing_snapshots']}`",
        f"- Holder count coverage: `{report['holder_count_coverage_pct']:.2f}%`",
        f"- Top holder share coverage: `{report['top_holder_share_coverage_pct']:.2f}%`",
        f"- Top 10 holder share coverage: `{report['top_10_holder_share_coverage_pct']:.2f}%`",
        f"- Creator holder share coverage: `{report['creator_holder_share_coverage_pct']:.2f}%`",
        f"- API calls used: `{report['api_calls_used']}`",
        f"- Helius credits used: `{report['helius_credits_used']}`",
        f"- Holder distribution source: `{report['holder_distribution_source']}`",
        "",
        "## Missing Reasons",
        "",
    ]
    if report["missing_reasons"]:
        lines.extend(f"- `{reason}`: `{count}`" for reason, count in report["missing_reasons"].items())
    else:
        lines.append("- None")
    lines.extend(
        [
            "",
            "## Scale Estimate",
            "",
            f"- 1,500-launch holder snapshots: `{report['estimated_cost_to_scale_to_1500_launches']['holder_snapshots']}`",
            f"- Offline event-replay API calls: `{report['estimated_cost_to_scale_to_1500_launches']['offline_event_replay_api_calls']}`",
            f"- External snapshot calls if required: `{report['estimated_cost_to_scale_to_1500_launches']['external_snapshot_api_calls_if_required']}`",
            f"- Estimated Helius credits for 1,500 launches: `{report['api_requirements']['estimated_helius_credits_for_1500_launches']}`",
            f"- Estimated Helius credits for 3,000 launches: `{report['api_requirements']['estimated_helius_credits_for_3000_launches']}`",
            "",
            "## Feasibility For T001/T002 v2",
            "",
            f"- Feasible now: `{report['t001_t002_v2_feasible']}`",
            f"- T001 v2 feasible: `{report['t001_v2_feasible']}`",
            f"- T002 v2 feasible: `{report['t002_v2_feasible']}`",
            f"- Next recommendation: {report['next_recommendation']}",
            "",
            "## Quality Note",
            "",
            report["offline_reconstruction_audit"]["quality_note"],
            "",
            "No thesis was rerun. No strategy, execution, optimization, or promotion logic was generated.",
            "",
        ]
    )
    return "\n".join(lines)


def _quality_markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# Holder-State Pilot Quality Report",
        "",
        f"- Launches attempted: `{report['launches_attempted']}`",
        f"- Launches completed: `{report['launches_completed']}`",
        f"- Launches failed: `{report['launches_failed']}`",
        f"- Snapshots attempted: `{report['snapshots_attempted']}`",
        f"- Snapshots built: `{report['snapshots_built']}`",
        f"- Snapshots missing: `{report['missing_snapshots']}`",
        "",
        "## Field Coverage",
        "",
        "| Field | Available | Missing | Coverage |",
        "|---|---:|---:|---:|",
    ]
    for field, coverage in report["field_coverage"].items():
        lines.append(
            f"| `{field}` | {coverage['available_snapshots']} | {coverage['missing_snapshots']} | {coverage['coverage_pct']:.2f}% |"
        )
    lines.extend(["", "## Missing Reasons", ""])
    lines.extend(f"- `{reason}`: `{count}`" for reason, count in report["missing_reason_counts"].items())
    lines.extend(["", "## Confidence Distribution", ""])
    lines.extend(f"- `{confidence}`: `{count}`" for confidence, count in report["confidence_distribution"].items())
    return "\n".join(lines) + "\n"


def _feasibility_audit_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Holder-State Feasibility Audit",
        "",
        "This audit inspects whether holder-state fields can be reconstructed from existing normalized lifecycle events, lifecycle snapshots, launch census rows, token transfer evidence, and cached artifacts.",
        "",
        "| Field | Already Available | Offline Reconstructable | Requires External Reads | Notes |",
        "|---|---:|---:|---:|---|",
    ]
    for field, audit in report["feasibility_audit"].items():
        lines.append(
            f"| `{field}` | `{audit['already_available']}` | `{audit['offline_reconstructable']}` | "
            f"`{audit['requires_external_reads']}` | {audit['notes']} |"
        )
    lines.extend(
        [
            "",
            "## Direct Answers",
            "",
            f"1. Can `holder_count` be reconstructed offline? `{report['feasibility_audit']['holder_count']['offline_reconstructable']}`",
            f"2. Can `top_holder_share` be reconstructed offline? `{report['feasibility_audit']['top_holder_share']['offline_reconstructable']}`",
            f"3. Can `top_10_holder_share` be reconstructed offline? `{report['feasibility_audit']['top_10_holder_share']['offline_reconstructable']}`",
            f"4. Can holder retention be reconstructed offline? `{report['feasibility_audit']['holder_retention']['offline_reconstructable']}`",
            f"5. Can holder churn be reconstructed offline? `{report['feasibility_audit']['holder_churn']['offline_reconstructable']}`",
            f"6. Can creator ownership be reconstructed offline? `{report['feasibility_audit']['creator_ownership']['offline_reconstructable']}`",
            f"7. Can bundle-linked ownership be reconstructed offline? `{report['feasibility_audit']['bundle_linked_ownership']['offline_reconstructable']}`",
            "8. Fields requiring external reads: bundle-linked ownership and entity-collapsed ownership require separate audited external or linkage evidence.",
            "",
            report["offline_reconstruction_audit"]["quality_note"],
            "",
        ]
    )
    return "\n".join(lines)


def _rollout_recommendation_markdown(report: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Holder-State Rollout Recommendation",
            "",
            f"- Feasibility classification: `{report['feasibility_result']}`",
            f"- Expected implementation complexity: `medium`",
            f"- Expected storage impact for 1,500 launches: `7,500 JSONL snapshot rows plus report metadata`",
            f"- Expected runtime: `offline pass over normalized lifecycle events; no network-bound runtime in pilot`",
            f"- Expected API cost: `{report['api_requirements']['estimated_helius_credits_for_1500_launches']}` Helius credits for offline replay",
            f"- Expected coverage: `{report['holder_count_coverage_pct']:.2f}%` holder-count coverage in the 50-launch pilot",
            "",
            "## Major Risks",
            "",
            "- Offline replay reconstructs observed holder balances from normalized event deltas, not full chain account state.",
            "- Entity-collapsed, bundle-linked, and creator-linked ownership beyond exact creator wallet require separate audited evidence.",
            "- Coverage may change on later launches if normalized event deltas are sparse or incomplete.",
            "",
            "## Recommended Next Step",
            "",
            report["next_recommendation"],
            "",
            "Do not rerun T001/T002 until the strict-cohort holder-state rollout has its own coverage audit.",
            "",
        ]
    )


def _coverage_pct(available: int, total: int) -> float:
    return (available / total * 100) if total else 0.0


def _field_coverage(rows: list[dict[str, Any]], field: str, total: int) -> dict[str, Any]:
    available = sum(1 for row in rows if row.get(field) is not None)
    return {
        "available_snapshots": available,
        "missing_snapshots": total - available,
        "coverage_pct": _coverage_pct(available, total),
    }


def _missing_reason_counts(missing_reasons: Counter) -> dict[str, int]:
    return {
        "unavailable_source": 0,
        "missing_snapshot": sum(missing_reasons.values()),
        "insufficient_history": 0,
        "reconstruction_failed": 0,
        "unsupported": 0,
    }


def _read_jsonl(path: Path | str) -> list[dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
