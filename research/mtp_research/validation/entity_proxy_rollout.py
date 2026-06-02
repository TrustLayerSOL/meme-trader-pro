"""Full strict-cohort entity-proxy rollout from offline lifecycle data."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from research.mtp_research.validation.entity_manipulation_feasibility import (
    _actor_creator_counts,
    _actor_launch_counts,
    _actors,
    _creator,
    _field_present,
    _first_minute_concentration,
    _group_by,
    _high_intensity_small_actor_set,
    _holder_state_by_mint,
    _int_or_zero,
    _latest_holder_field,
    _launch_age,
    _manual_review_sample,
    _pct,
    _proxy_missing_reasons,
    _quick_churn,
    _read_jsonl,
    _signature_launch_counts,
)


READINESS_READY = "entity_proxy_ready_for_T007"
READINESS_PARTIAL = "entity_proxy_partial_needs_review"
READINESS_BLOCKED = "entity_proxy_blocked"
REQUIRED_PROXY_FIELDS = [
    "creator_linked_share_proxy",
    "repeated_actor_overlap_proxy",
    "repeated_buyer_overlap_proxy",
    "synchronized_participation_proxy",
    "circularity_proxy",
    "churn_proxy",
]


def build_entity_proxy_rollout(
    *,
    candidates_path: Path | str,
    events_path: Path | str,
    holder_state_snapshots_path: Path | str,
) -> dict[str, Any]:
    candidates = _read_jsonl(candidates_path)
    selected_mints = {row.get("token_mint") or row.get("mint") for row in candidates}
    selected_mints.discard(None)
    events = _read_events_for_mints(events_path, selected_mints)
    holder_rows = _read_jsonl(holder_state_snapshots_path)
    holder_by_mint = _holder_state_by_mint(holder_rows, selected_mints)
    events_by_mint = _group_by(events, "token_mint")
    actor_launch_counts = _actor_launch_counts(events)
    actor_creator_counts = _actor_creator_counts(events, candidates)
    signature_launch_counts = _signature_launch_counts(events)
    proxy_rows = []
    for candidate in candidates:
        mint = candidate.get("token_mint") or candidate.get("mint")
        launch_events = sorted(
            events_by_mint.get(mint, []),
            key=lambda row: (_int_or_zero(row.get("block_time")), row.get("signature") or ""),
        )
        proxy_rows.append(
            _rollout_row(
                candidate,
                launch_events,
                holder_by_mint.get(mint, []),
                actor_launch_counts,
                actor_creator_counts,
                signature_launch_counts,
            )
        )
    audit = _audit(proxy_rows, len(candidates), len(events))
    readiness = _readiness(audit)
    return {
        "rollout_id": "entity_proxy_strict_cohort_v0",
        "scope": "data_enrichment_rollout_only",
        "methodology_flags": [
            "research_only",
            "data_enrichment_only",
            "no_thesis_cycle",
            "no_outcome_analysis",
            "no_backtest",
            "no_walk_forward_validation",
            "no_trading_rules",
            "no_entry_exit_logic",
            "no_threshold_optimization",
            "no_grid_search",
            "no_ml_black_boxes",
            "no_external_api_calls",
        ],
        "launches_processed": len(candidates),
        "events_processed": len(events),
        "proxy_rows": proxy_rows,
        "audit": audit,
        "readiness_classification": readiness,
        "t007_feasible": readiness == READINESS_READY,
        "next_recommendation": _next_recommendation(readiness),
        "blocked_proxy_families": [
            "funding_link_proxy",
            "safe_entity_resolution_groups",
            "grouped_entity_holder_share",
        ],
        "caveats": [
            "Actor overlap remains an overlap proxy only, not entity resolution.",
            "No manipulation claims are made.",
            "No outcomes were loaded or compared.",
            "Creator-linked share uses observed holder-state replay, not confirmed full-chain account state.",
        ],
    }


def write_entity_proxy_rollout_outputs(
    rollout: dict[str, Any],
    *,
    dataset_dir: Path | str,
    report_dir: Path | str,
) -> dict[str, Path]:
    dataset = Path(dataset_dir)
    reports = Path(report_dir)
    dataset.mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)
    jsonl_path = dataset / "entity_proxy_strict_cohort.jsonl"
    parquet_path = dataset / "entity_proxy_strict_cohort.parquet"
    audit_json_path = reports / "entity_proxy_strict_cohort_audit.json"
    audit_markdown_path = reports / "entity_proxy_strict_cohort_audit.md"
    with jsonl_path.open("w", encoding="utf-8") as f:
        for row in rollout["proxy_rows"]:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    _write_parquet(rollout["proxy_rows"], parquet_path)
    audit = dict(rollout["audit"])
    audit["storage_size"] = {
        "jsonl_bytes": jsonl_path.stat().st_size,
        "parquet_bytes": parquet_path.stat().st_size,
    }
    audit_report = {
        "rollout_id": rollout["rollout_id"],
        "launches_processed": rollout["launches_processed"],
        "events_processed": rollout["events_processed"],
        "readiness_classification": rollout["readiness_classification"],
        "t007_feasible": rollout["t007_feasible"],
        "audit": audit,
        "blocked_proxy_families": rollout["blocked_proxy_families"],
        "caveats": rollout["caveats"],
        "next_recommendation": rollout["next_recommendation"],
    }
    audit_json_path.write_text(json.dumps(audit_report, indent=2, sort_keys=True), encoding="utf-8")
    audit_markdown_path.write_text(_audit_markdown(audit_report), encoding="utf-8")
    return {
        "jsonl_path": jsonl_path,
        "parquet_path": parquet_path,
        "audit_json_path": audit_json_path,
        "audit_markdown_path": audit_markdown_path,
    }


def _rollout_row(
    candidate: dict[str, Any],
    events: list[dict[str, Any]],
    holder_rows: list[dict[str, Any]],
    actor_launch_counts: Counter,
    actor_creator_counts: Counter,
    signature_launch_counts: Counter,
) -> dict[str, Any]:
    mint = candidate.get("token_mint") or candidate.get("mint")
    creator = _creator(candidate)
    early_events = [event for event in events if _launch_age(candidate, event) is not None and _launch_age(candidate, event) <= 60]
    early_buyer_actors = {
        str(event["actor"])
        for event in early_events
        if event.get("actor") and str(event.get("side") or "").lower() in {"accumulate", "buy", "possible_buy"}
    }
    all_actors = _actors(events)
    shared_actors = sorted(actor for actor in all_actors if actor_launch_counts[actor] > 1)
    shared_actors_same_creator = sorted(actor for actor in all_actors if actor_creator_counts[(creator, actor)] > 1)
    repeated_signatures = sorted(
        {
            event.get("signature")
            for event in events
            if event.get("signature") and signature_launch_counts[event.get("signature")] > 1
        }
    )
    quick_churn = _quick_churn(events, candidate)
    first_minute_concentration = _first_minute_concentration(early_events)
    creator_share = _latest_holder_field(holder_rows, "creator_holder_share")
    repeated_buyer_count = len([actor for actor in early_buyer_actors if actor_launch_counts[actor] > 1])
    proxy_values = {
        "creator_linked_share_proxy": creator_share,
        "repeated_actor_overlap_proxy": len(shared_actors),
        "repeated_buyer_overlap_proxy": repeated_buyer_count,
        "synchronized_participation_proxy": first_minute_concentration,
        "circularity_proxy": len(quick_churn),
        "churn_proxy": _churn_rate(quick_churn, all_actors),
    }
    missing = _missing_reasons(proxy_values, events)
    confidence = _proxy_confidence(proxy_values, missing, events)
    return {
        "launch_id": candidate.get("launch_id"),
        "mint": mint,
        "creator": creator,
        "creator_linked_share_proxy": proxy_values["creator_linked_share_proxy"],
        "repeated_actor_overlap_proxy": proxy_values["repeated_actor_overlap_proxy"],
        "repeated_buyer_overlap_proxy": proxy_values["repeated_buyer_overlap_proxy"],
        "synchronized_participation_proxy": proxy_values["synchronized_participation_proxy"],
        "circularity_proxy": proxy_values["circularity_proxy"],
        "churn_proxy": proxy_values["churn_proxy"],
        "proxy_confidence": confidence,
        "proxy_missing_reason": ";".join(sorted(set(missing.values()))) if missing else None,
        "proxy_missing_reasons": missing,
        "event_count": len(events),
        "early_event_count_60s": len(early_events),
        "shared_actor_same_creator_count": len(shared_actors_same_creator),
        "repeated_signature_count": len(repeated_signatures),
        "high_event_intensity_small_actor_set": _high_intensity_small_actor_set(events),
        "manual_review_examples": {
            "shared_actors": shared_actors[:5],
            "shared_actors_same_creator": shared_actors_same_creator[:5],
            "repeated_signatures": repeated_signatures[:5],
            "quick_churn_actors": sorted(quick_churn)[:5],
        },
    }


def _missing_reasons(proxy_values: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, str]:
    pilot_style = {
        "creator_holder_share_30m_or_latest": proxy_values["creator_linked_share_proxy"],
        "shared_actor_count": proxy_values["repeated_actor_overlap_proxy"],
        "first_minute_actor_concentration": proxy_values["synchronized_participation_proxy"],
        "quick_buy_sell_churn_actor_count": proxy_values["circularity_proxy"],
    }
    reasons = _proxy_missing_reasons(pilot_style, events)
    for field, value in proxy_values.items():
        if value is None:
            reasons[field] = f"{field}_unavailable"
    if not any(_field_present(event, "fee_payer") or _field_present(event, "funding_source_wallet") for event in events):
        reasons["funding_link_proxy"] = "funding_link_fields_unavailable"
    return reasons


def _proxy_confidence(proxy_values: dict[str, Any], missing: dict[str, str], events: list[dict[str, Any]]) -> str:
    if not events:
        return "low"
    available_required = sum(1 for field in REQUIRED_PROXY_FIELDS if proxy_values.get(field) is not None)
    if available_required == len(REQUIRED_PROXY_FIELDS) and not missing:
        return "high"
    if available_required >= 4:
        return "medium"
    return "low"


def _churn_rate(churn_actors: set[str], all_actors: set[str]) -> float | None:
    if not all_actors:
        return None
    return len(churn_actors) / len(all_actors)


def _audit(proxy_rows: list[dict[str, Any]], launch_count: int, event_count: int) -> dict[str, Any]:
    proxy_coverage = {
        field: _field_coverage(proxy_rows, field)
        for field in REQUIRED_PROXY_FIELDS
    }
    missing_reasons = Counter()
    for row in proxy_rows:
        if row.get("proxy_missing_reason"):
            for reason in str(row["proxy_missing_reason"]).split(";"):
                if reason:
                    missing_reasons[reason] += 1
    confidence_distribution = dict(sorted(Counter(row["proxy_confidence"] for row in proxy_rows).items()))
    return {
        "launch_coverage": {
            "launches_expected": launch_count,
            "launches_processed": len(proxy_rows),
            "coverage_pct": _pct(len(proxy_rows), launch_count),
        },
        "events_processed": event_count,
        "proxy_coverage": proxy_coverage,
        "missing_reason_counts": dict(sorted(missing_reasons.items())),
        "confidence_distribution": confidence_distribution,
        "creator_linked_examples": _examples(proxy_rows, "creator_linked_share_proxy", reverse=True),
        "high_overlap_examples": _examples(proxy_rows, "repeated_actor_overlap_proxy", reverse=True),
        "low_overlap_examples": _examples(proxy_rows, "repeated_actor_overlap_proxy", reverse=False),
        "coverage_pct": min((stats["coverage_pct"] for stats in proxy_coverage.values()), default=0),
    }


def _readiness(audit: dict[str, Any]) -> str:
    required_coverage = min(
        audit["proxy_coverage"][field]["coverage_pct"]
        for field in REQUIRED_PROXY_FIELDS
    )
    launch_coverage = audit["launch_coverage"]["coverage_pct"]
    if launch_coverage >= 99 and required_coverage >= 95:
        return READINESS_READY
    if launch_coverage >= 90 and required_coverage >= 50:
        return READINESS_PARTIAL
    return READINESS_BLOCKED


def _next_recommendation(readiness: str) -> str:
    if readiness == READINESS_READY:
        return "T007 is feasible as a separate descriptive thesis design after reviewing proxy coverage and examples"
    if readiness == READINESS_PARTIAL:
        return "inspect missing proxy reasons before designing T007"
    return "do not design T007 until proxy coverage is repaired"


def _field_coverage(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    available = sum(1 for row in rows if row.get(field) is not None)
    return {
        "available_count": available,
        "missing_count": len(rows) - available,
        "coverage_pct": _pct(available, len(rows)),
    }


def _examples(rows: list[dict[str, Any]], field: str, *, reverse: bool, limit: int = 10) -> list[dict[str, Any]]:
    sorted_rows = sorted(
        [row for row in rows if row.get(field) is not None],
        key=lambda row: (row.get(field), row.get("mint") or ""),
        reverse=reverse,
    )
    return [
        {
            "launch_id": row.get("launch_id"),
            "mint": row.get("mint"),
            "creator": row.get("creator"),
            field: row.get(field),
            "proxy_confidence": row.get("proxy_confidence"),
        }
        for row in sorted_rows[:limit]
    ]


def _read_events_for_mints(path: Path | str, selected_mints: set[str]) -> list[dict[str, Any]]:
    events = []
    with Path(path).open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("token_mint") in selected_mints:
                events.append(row)
    return events


def _write_parquet(rows: list[dict[str, Any]], output_path: Path) -> None:
    import pandas as pd

    output_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(output_path, index=False)


def _audit_markdown(audit_report: dict[str, Any]) -> str:
    audit = audit_report["audit"]
    lines = [
        "# Entity Proxy Strict Cohort Audit",
        "",
        f"- Readiness classification: `{audit_report['readiness_classification']}`",
        f"- T007 feasible: `{audit_report['t007_feasible']}`",
        f"- Launches processed: `{audit_report['launches_processed']}`",
        f"- Events processed: `{audit_report['events_processed']}`",
        "- No thesis cycle was run.",
        "- No outcome analysis was run.",
        "- No manipulation claims are made.",
        "",
        "## Proxy Coverage",
        "",
        "| Proxy | Available | Missing | Coverage |",
        "|---|---:|---:|---:|",
    ]
    for field, stats in audit["proxy_coverage"].items():
        lines.append(f"| `{field}` | {stats['available_count']} | {stats['missing_count']} | {stats['coverage_pct']:.2f}% |")
    lines.extend(
        [
            "",
            "## Confidence Distribution",
            "",
            f"`{audit['confidence_distribution']}`",
            "",
            "## Missing Reasons",
            "",
            f"`{audit['missing_reason_counts']}`",
            "",
            "## Blocked Proxy Families",
            "",
            *[f"- `{item}`" for item in audit_report["blocked_proxy_families"]],
            "",
            "## Next Recommendation",
            "",
            audit_report["next_recommendation"],
            "",
        ]
    )
    return "\n".join(lines)
