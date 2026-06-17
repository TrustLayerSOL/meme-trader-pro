from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

from research.mtp_research.validation.t007_thesis_ready_gate import (
    evaluate_t007_full_path_readiness_gate,
)


LIFECYCLE_STATUSES = {
    "full_path",
    "near_full_missing_execution_cost",
    "migration_plus_depth_only",
    "migration_only_preexisting",
    "migration_only_replay_unresolved",
    "migration_only_replay_not_run",
    "migration_only_launched_after_campaign",
    "birth_seen_sample_rejected",
    "birth_seen_not_admitted",
    "birth_seen_admitted_missing_curve",
    "birth_seen_admitted_missing_trade_flow",
    "birth_seen_admitted_missing_migration_link",
    "migration_only_source_miss",
    "backfill_possible",
    "backfill_not_possible",
    "unknown",
}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if _is_placeholder_row(row):
            continue
        rows.append(row)
    return rows


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _is_placeholder_row(row: Mapping[str, Any]) -> bool:
    return any(str(value) == "schema_ready_pending_live_source" for value in row.values())


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), sort_keys=True) + "\n")


def _write_csv(path: Path, rows: list[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = _fieldnames(rows)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(dict(row) for row in rows)


def _fieldnames(rows: list[Mapping[str, Any]]) -> list[str]:
    preferred = [
        "mint",
        "readiness_bucket",
        "full_path_ready",
        "first_missing_link",
        "global_migration_seen",
        "quote_asset",
        "pool_address",
        "migration_signature",
        "birth_seen",
        "admitted",
        "sample_rejected",
        "capacity_rejected",
        "tracking_tier",
        "curve_observations_count",
        "highest_progress_pct",
        "threshold_crossings_count",
        "velocity_features_available",
        "trade_flow_available",
        "buyer_breadth_available",
        "holder_distribution_available",
        "dev_behavior_available",
        "post_migration_observations_available",
        "executable_quote_available",
        "pumpswap_swap_event_available",
        "execution_cost_join_available",
        "execution_cost_join_decision_time_safe",
        "backfill_status",
    ]
    keys = sorted({key for row in rows for key in row})
    return preferred + [key for key in keys if key not in preferred]


def _mint_of(row: Mapping[str, Any]) -> str:
    for key in ("mint", "token_mint", "base_mint", "created_mint"):
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _first_present(row: Mapping[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def _pool_of(row: Mapping[str, Any]) -> str:
    for key in ("pool_or_pair_address", "pool_address", "pair_address", "pool"):
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _signature_of(row: Mapping[str, Any]) -> str:
    for key in ("signature", "migration_signature", "transaction_signature"):
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _campaign_window(manifest: Mapping[str, Any], source_status: Mapping[str, Any]) -> tuple[float | None, float | None]:
    start = _float(
        _first_present(
            manifest,
            ["started_at", "source_start_time", "campaign_start_time", "wall_clock_source_start"],
        )
        or _first_present(source_status, ["started_at", "source_start_time", "campaign_start_time", "wall_clock_source_start"])
    )
    end = _float(
        _first_present(
            manifest,
            ["ended_at", "source_stop_time", "campaign_end_time", "wall_clock_source_stop"],
        )
        or _first_present(source_status, ["ended_at", "source_stop_time", "campaign_end_time", "wall_clock_source_stop"])
    )
    if end is None and start is not None:
        duration = _float(
            _first_present(
                manifest,
                ["actual_duration_seconds", "source_duration_seconds", "requested_duration_seconds"],
            )
            or _first_present(source_status, ["actual_source_duration_seconds", "actual_duration_seconds", "source_duration_seconds"])
        )
        if duration is not None:
            end = start + duration
    return start, end


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _event_time(row: Mapping[str, Any]) -> float | None:
    for key in (
        "decision_time",
        "feature_observed_at",
        "migration_received_at",
        "crossing_received_at",
        "collector_observed_at",
        "received_at",
        "block_time",
        "created_at",
        "timestamp",
    ):
        value = _float(row.get(key))
        if value is not None:
            return value
    return None


def _group_by_mint(rows: Iterable[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        mint = _mint_of(row)
        if mint:
            grouped.setdefault(mint, []).append(dict(row))
    return grouped


def _first_time(rows: Iterable[Mapping[str, Any]]) -> float | None:
    values = [_event_time(row) for row in rows]
    values = [value for value in values if value is not None]
    return min(values) if values else None


def _progress(row: Mapping[str, Any]) -> float | None:
    for key in ("computed_progress_pct", "progress_pct", "candidate_progress_pct", "highest_progress_pct", "last_progress_pct"):
        value = _float(row.get(key))
        if value is not None:
            return value
    return None


def _highest_progress(rows: Iterable[Mapping[str, Any]]) -> float | None:
    values = [_progress(row) for row in rows]
    values = [value for value in values if value is not None]
    return max(values) if values else None


def _sample_rejected(rows: Iterable[Mapping[str, Any]]) -> bool:
    for row in rows:
        reason = str(row.get("admission_reason") or row.get("rejection_reason") or "").lower()
        if "sample_rejected" in reason or _bool(row.get("sample_rejected")):
            return True
    return False


def _capacity_rejected(rows: Iterable[Mapping[str, Any]]) -> bool:
    for row in rows:
        reason = str(row.get("admission_reason") or row.get("rejection_reason") or "").lower()
        if "capacity" in reason or _bool(row.get("capacity_rejected")):
            return True
    return False


def _active_pruned(rows: Iterable[Mapping[str, Any]]) -> bool:
    for row in rows:
        reason = str(row.get("active_pruned_reason") or row.get("prune_reason") or row.get("stop_reason") or "").lower()
        if reason and reason not in {"none", "not_pruned", "complete"}:
            return True
        if _bool(row.get("active_pruned")):
            return True
    return False


def _has_depth(rows: Iterable[Mapping[str, Any]]) -> bool:
    for row in rows:
        for key in ("base_reserve_raw", "quote_reserve_raw", "pool_base_reserve", "pool_quote_reserve", "pool_liquidity_quote", "pool_liquidity_usd"):
            if row.get(key) not in (None, ""):
                return True
    return False


def _has_quote(rows: Iterable[Mapping[str, Any]]) -> bool:
    for row in rows:
        for key in ("price_impact_pct", "expected_output_quote", "effective_exit_price_quote_per_token", "quote_status"):
            if row.get(key) not in (None, ""):
                return True
    return False


def join_latest_prior_execution_cost(event_timestamp: Any, execution_rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    event_time = _float(event_timestamp)
    if event_time is None:
        return {
            "status": "not_available",
            "event_timestamp": None,
            "joined_decision_time": None,
            "execution_cost_status": None,
            "decision_time_safe": True,
        }
    best: Mapping[str, Any] | None = None
    best_time: float | None = None
    for row in execution_rows:
        row_time = _event_time(row)
        if row_time is None or row_time > event_time:
            continue
        if best_time is None or row_time > best_time:
            best = row
            best_time = row_time
    if best is None or best_time is None:
        return {
            "status": "not_available",
            "event_timestamp": event_time,
            "joined_decision_time": None,
            "execution_cost_status": None,
            "decision_time_safe": True,
        }
    return {
        "status": "joined",
        "event_timestamp": event_time,
        "joined_decision_time": best_time,
        "execution_cost_status": best.get("execution_cost_status"),
        "source_observation_reason": best.get("observation_reason"),
        "decision_time_safe": best_time <= event_time,
    }


def _backfill_status(mint: str, migration_rows: list[dict[str, Any]], birth_rows: list[dict[str, Any]], curve_rows: list[dict[str, Any]]) -> str:
    if birth_rows and curve_rows:
        return "not_needed"
    if any(_bool(row.get("birth_backfilled_from_replay")) for row in birth_rows):
        return "backfilled_birth_not_live"
    if not mint:
        return "backfill_not_possible"
    if migration_rows:
        return "backfill_possible"
    return "backfill_not_possible"


def _latest_backfill_job(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {}
    return max(rows, key=lambda row: _float(row.get("queued_at")) or _float(row.get("launch_time_from_replay")) or 0.0)


def _migration_source_coverage_row(
    lifecycle_row: Mapping[str, Any],
    *,
    backfill_job: Mapping[str, Any],
    campaign_start: float | None,
    campaign_end: float | None,
) -> dict[str, Any]:
    launch_time = _float(backfill_job.get("launch_time_from_replay"))
    birth_seen = _bool(lifecycle_row.get("birth_seen"))
    launched_before = bool(launch_time is not None and campaign_start is not None and launch_time < campaign_start)
    launched_during = bool(
        launch_time is not None
        and campaign_start is not None
        and campaign_end is not None
        and campaign_start <= launch_time <= campaign_end
    )
    launched_after = bool(launch_time is not None and campaign_end is not None and launch_time > campaign_end)
    backfill_status = str(backfill_job.get("status") or "")
    failure_reason = str(backfill_job.get("failure_reason") or "")
    if birth_seen:
        coverage_class = "LIVE_BIRTH_LINKED"
        source_miss_reason = ""
        explanation = "migration linked to a live birth row from the campaign"
    elif launched_before:
        coverage_class = "MIGRATION_ONLY_PREEXISTING"
        source_miss_reason = "launched_before_campaign"
        explanation = "migration was observed during the campaign, but replayed launch time predates the campaign window"
    elif launched_during:
        coverage_class = "MIGRATION_ONLY_SOURCE_MISS"
        source_miss_reason = "birth_route_not_watched"
        explanation = "replay found a launch during the campaign window, but the live birth lane did not emit a live birth row"
    elif launched_after:
        coverage_class = "MIGRATION_ONLY_LAUNCHED_AFTER_CAMPAIGN"
        source_miss_reason = "launch_after_campaign"
        explanation = "replayed launch time is after the campaign window and cannot be linked to this scan"
    elif backfill_status in {"failed", "rate_limited"} or failure_reason:
        coverage_class = "MIGRATION_ONLY_REPLAY_UNRESOLVED"
        source_miss_reason = failure_reason or backfill_status or "replay_unresolved"
        explanation = "migration was observed, but bounded replay did not recover a launch time"
    else:
        coverage_class = "MIGRATION_ONLY_REPLAY_NOT_RUN"
        source_miss_reason = "replay_not_run"
        explanation = "migration was observed without a live birth row and no replay job evidence was available"
    return {
        "mint": lifecycle_row.get("mint"),
        "migration_source_coverage_class": coverage_class,
        "source_miss_reason": source_miss_reason,
        "status_explanation": explanation,
        "birth_seen_live": birth_seen,
        "backfilled_birth_available": _bool(lifecycle_row.get("backfilled_birth_available")),
        "launch_signature_from_backfill": backfill_job.get("launch_signature_from_replay"),
        "launch_slot_from_backfill": backfill_job.get("launch_slot_from_replay"),
        "launch_time_from_backfill": backfill_job.get("launch_time_from_replay"),
        "campaign_start_time": campaign_start,
        "campaign_end_time": campaign_end,
        "launched_before_campaign": launched_before,
        "launched_during_campaign": launched_during,
        "launched_after_campaign": launched_after,
        "birth_source_should_have_seen_it": bool(launched_during),
        "birth_source_missed_it": bool(launched_during and not birth_seen),
        "backfill_job_status": backfill_status,
        "backfill_failure_reason": failure_reason,
        "migration_signature": lifecycle_row.get("migration_signature") or backfill_job.get("backfill_trigger_signature"),
        "pool_address": lifecycle_row.get("pool_address") or backfill_job.get("pool_or_pair_address"),
        "quote_asset": lifecycle_row.get("quote_asset") or backfill_job.get("quote_asset"),
    }


def _apply_migration_source_coverage(rows: list[dict[str, Any]], audit_rows: list[dict[str, Any]]) -> None:
    audit_by_mint = {str(row.get("mint") or ""): row for row in audit_rows}
    for row in rows:
        audit = audit_by_mint.get(str(row.get("mint") or ""))
        if not audit:
            continue
        row.update(
            {
                "migration_source_coverage_class": audit.get("migration_source_coverage_class"),
                "source_miss_reason": audit.get("source_miss_reason"),
                "launch_time_from_backfill": audit.get("launch_time_from_backfill"),
                "birth_source_should_have_seen_it": audit.get("birth_source_should_have_seen_it"),
                "birth_source_missed_it": audit.get("birth_source_missed_it"),
            }
        )
        if row.get("birth_seen"):
            continue
        coverage_class = str(audit.get("migration_source_coverage_class") or "")
        if coverage_class == "MIGRATION_ONLY_PREEXISTING":
            row["readiness_bucket"] = "migration_only_preexisting"
            row["coverage_status"] = "migration_only_preexisting"
            row["first_missing_link"] = "launch_before_campaign"
        elif coverage_class == "MIGRATION_ONLY_REPLAY_UNRESOLVED":
            row["readiness_bucket"] = "migration_only_replay_unresolved"
            row["coverage_status"] = "migration_only_replay_unresolved"
            row["first_missing_link"] = "launch_replay_unresolved"
        elif coverage_class == "MIGRATION_ONLY_REPLAY_NOT_RUN":
            row["readiness_bucket"] = "backfill_possible"
            row["coverage_status"] = "backfill_possible"
            row["first_missing_link"] = "birth_source_miss"
        elif coverage_class == "MIGRATION_ONLY_LAUNCHED_AFTER_CAMPAIGN":
            row["readiness_bucket"] = "migration_only_launched_after_campaign"
            row["coverage_status"] = "migration_only_launched_after_campaign"
            row["first_missing_link"] = "launch_after_campaign"
        elif coverage_class == "MIGRATION_ONLY_SOURCE_MISS":
            row["readiness_bucket"] = "migration_only_source_miss"
            row["coverage_status"] = "migration_only_source_miss"
            row["first_missing_link"] = "birth_source_miss"


def _build_migration_source_coverage_audit(
    lifecycle_rows: list[dict[str, Any]],
    *,
    backfill_jobs_by_mint: Mapping[str, list[dict[str, Any]]],
    manifest: Mapping[str, Any],
    source_status: Mapping[str, Any],
) -> list[dict[str, Any]]:
    campaign_start, campaign_end = _campaign_window(manifest, source_status)
    rows: list[dict[str, Any]] = []
    for row in lifecycle_rows:
        if not row.get("global_migration_seen"):
            continue
        mint = str(row.get("mint") or "")
        rows.append(
            _migration_source_coverage_row(
                row,
                backfill_job=_latest_backfill_job(list(backfill_jobs_by_mint.get(mint, []))),
                campaign_start=campaign_start,
                campaign_end=campaign_end,
            )
        )
    return rows


def _classify(
    *,
    birth_seen: bool,
    admitted: bool,
    sample_rejected: bool,
    active_pruned: bool,
    migration_seen: bool,
    curve_count: int,
    threshold_count: int,
    velocity_count: int,
    trade_flow_count: int,
    holder_dev_count: int,
    post_available: bool,
    quote_available: bool,
    swap_available: bool,
    execution_joined: bool,
    backfill_status: str,
) -> str:
    if (
        birth_seen
        and admitted
        and migration_seen
        and curve_count > 0
        and threshold_count > 0
        and velocity_count > 0
        and trade_flow_count > 0
        and holder_dev_count > 0
        and post_available
        and quote_available
        and swap_available
        and execution_joined
    ):
        return "full_path"
    if (
        birth_seen
        and admitted
        and migration_seen
        and curve_count > 0
        and threshold_count > 0
        and velocity_count > 0
        and trade_flow_count > 0
        and holder_dev_count > 0
        and post_available
        and quote_available
        and swap_available
    ):
        return "near_full_missing_execution_cost"
    if migration_seen and not birth_seen:
        return "migration_only_source_miss" if backfill_status == "backfill_not_possible" else "backfill_possible"
    if migration_seen and post_available and quote_available and not (birth_seen and admitted and curve_count > 0):
        return "migration_plus_depth_only"
    if birth_seen and sample_rejected:
        return "birth_seen_sample_rejected"
    if birth_seen and not admitted:
        return "birth_seen_not_admitted"
    if birth_seen and admitted and (active_pruned or curve_count <= 0):
        return "birth_seen_admitted_missing_curve"
    if birth_seen and admitted and trade_flow_count <= 0:
        return "birth_seen_admitted_missing_trade_flow"
    if birth_seen and admitted and not migration_seen:
        return "birth_seen_admitted_missing_migration_link"
    return "unknown"


def _first_missing_link(
    *,
    birth_seen: bool,
    admitted: bool,
    sample_rejected: bool,
    active_pruned: bool,
    curve_count: int,
    threshold_count: int,
    velocity_count: int,
    trade_flow_count: int,
    holder_dev_count: int,
    migration_seen: bool,
    post_available: bool,
    quote_available: bool,
    swap_available: bool,
    execution_joined: bool,
) -> str:
    if not birth_seen:
        return "birth_source_miss"
    if sample_rejected:
        return "sample_rejected"
    if not admitted:
        return "birth_seen_not_admitted"
    if active_pruned:
        return "admitted_but_pruned"
    if curve_count <= 0:
        return "curve_observation_missing"
    if threshold_count <= 0:
        return "threshold_not_crossed"
    if velocity_count <= 0:
        return "velocity_not_linked"
    if trade_flow_count <= 0:
        return "trade_flow_missing"
    if holder_dev_count <= 0:
        return "holder_dev_missing"
    if not migration_seen:
        return "migration_link_missing"
    if not post_available:
        return "post_migration_observation_missing"
    if not quote_available:
        return "executable_quote_missing"
    if not swap_available:
        return "pumpswap_swap_event_missing"
    if not execution_joined:
        return "execution_cost_join_missing"
    return "none"


def _build_row(mint: str, grouped: Mapping[str, dict[str, list[dict[str, Any]]]], execution_rows: list[dict[str, Any]]) -> dict[str, Any]:
    births = grouped["birth"].get(mint, [])
    live_births = [row for row in births if not _bool(row.get("birth_backfilled_from_replay"))]
    backfilled_births = [row for row in births if _bool(row.get("birth_backfilled_from_replay"))]
    curves = grouped["curve"].get(mint, [])
    thresholds = grouped["threshold"].get(mint, [])
    velocities = [*grouped["velocity"].get(mint, []), *grouped["acceleration"].get(mint, [])]
    trades = [*grouped["trade_flow"].get(mint, []), *grouped["organic_flow"].get(mint, [])]
    holder_dev = [*grouped["holder"].get(mint, []), *grouped["dev"].get(mint, [])]
    migrations = grouped["migration"].get(mint, [])
    posts = grouped["post"].get(mint, [])
    quotes = grouped["quote"].get(mint, [])
    swaps = grouped["swap"].get(mint, [])
    paths = grouped["path"].get(mint, [])

    migration = min(migrations, key=lambda row: _event_time(row) if _event_time(row) is not None else float("inf")) if migrations else {}
    birth_seen = bool(live_births)
    admitted = any(_bool(row.get("admitted")) for row in live_births)
    sample_rejected = _sample_rejected(live_births)
    capacity_rejected = _capacity_rejected(live_births)
    active_pruned = _active_pruned([*live_births, *paths])
    post_available = _has_depth(posts) or bool(posts)
    quote_available = _has_quote(quotes)
    swap_available = bool(swaps)
    execution_joins = {
        "birth": join_latest_prior_execution_cost(_first_time(live_births), execution_rows),
        "curve": join_latest_prior_execution_cost(_first_time(curves), execution_rows),
        "threshold": join_latest_prior_execution_cost(_first_time(thresholds), execution_rows),
        "migration": join_latest_prior_execution_cost(_first_time(migrations), execution_rows),
        "quote": join_latest_prior_execution_cost(_first_time(quotes), execution_rows),
    }
    execution_joined = any(join["status"] == "joined" for join in execution_joins.values())
    backfill = _backfill_status(mint, migrations, [*live_births, *backfilled_births], curves)
    migration_evidence_level = str(migration.get("migration_evidence_level") or "")
    migration_evidence_reason = str(migration.get("migration_evidence_reason") or "")
    status = _classify(
        birth_seen=birth_seen,
        admitted=admitted,
        sample_rejected=sample_rejected,
        active_pruned=active_pruned,
        migration_seen=bool(migrations),
        curve_count=len(curves),
        threshold_count=len(thresholds),
        velocity_count=len(velocities),
        trade_flow_count=len(trades),
        holder_dev_count=len(holder_dev),
        post_available=post_available,
        quote_available=quote_available,
        swap_available=swap_available,
        execution_joined=execution_joined,
        backfill_status=backfill,
    )
    first_missing = _first_missing_link(
        birth_seen=birth_seen,
        admitted=admitted,
        sample_rejected=sample_rejected,
        active_pruned=active_pruned,
        curve_count=len(curves),
        threshold_count=len(thresholds),
        velocity_count=len(velocities),
        trade_flow_count=len(trades),
        holder_dev_count=len(holder_dev),
        migration_seen=bool(migrations),
        post_available=post_available,
        quote_available=quote_available,
        swap_available=swap_available,
        execution_joined=execution_joined,
    )
    tracking_tiers = [str(row.get("tracking_tier") or row.get("tracking_tier_after") or "") for row in [*births, *paths] if row.get("tracking_tier") or row.get("tracking_tier_after")]
    return {
        "mint": mint,
        "readiness_bucket": status,
        "coverage_status": status,
        "full_path_ready": status == "full_path",
        "first_missing_link": first_missing,
        "global_migration_seen": bool(migrations),
        "migration_evidence_level": migration_evidence_level,
        "migration_evidence_reason": migration_evidence_reason,
        "migration_evidence_is_level_a_or_b": migration_evidence_level in {"LEVEL_A", "LEVEL_B"},
        "quote_asset": migration.get("quote_asset") or migration.get("quote_mint_symbol") or "",
        "pool_address": _pool_of(migration),
        "migration_signature": _signature_of(migration),
        "birth_seen": birth_seen,
        "live_birth_seen": birth_seen,
        "backfilled_birth_available": bool(backfilled_births),
        "birth_rows_total": len(births),
        "live_birth_rows_count": len(live_births),
        "backfilled_birth_rows_count": len(backfilled_births),
        "admitted": admitted,
        "sample_rejected": sample_rejected,
        "capacity_rejected": capacity_rejected,
        "tracking_tier": tracking_tiers[-1] if tracking_tiers else "",
        "active_tracking_pruned_before_curve_or_migration": active_pruned,
        "curve_observations_count": len(curves),
        "highest_progress_pct": _highest_progress([*curves, *paths, *migrations]),
        "threshold_crossings_count": len(thresholds),
        "velocity_features_available": bool(velocities),
        "velocity_acceleration_count": len(velocities),
        "trade_flow_available": bool(trades),
        "trade_flow_count": len(trades),
        "buyer_breadth_available": any(row.get("unique_buyers_since_launch") not in (None, "") for row in trades),
        "holder_distribution_available": bool(grouped["holder"].get(mint, [])),
        "dev_behavior_available": bool(grouped["dev"].get(mint, [])),
        "holder_dev_count": len(holder_dev),
        "post_migration_observations_available": post_available,
        "post_migration_observations_count": len(posts),
        "executable_quote_available": quote_available,
        "executable_quote_count": len(quotes),
        "pumpswap_swap_event_available": swap_available,
        "pumpswap_swap_events_count": len(swaps),
        "execution_cost_join_available": execution_joined,
        "execution_cost_join_decision_time_safe": all(join["decision_time_safe"] for join in execution_joins.values()),
        "execution_cost_at_birth_status": execution_joins["birth"]["status"],
        "execution_cost_at_threshold_status": execution_joins["threshold"]["status"],
        "execution_cost_at_migration_status": execution_joins["migration"]["status"],
        "execution_cost_at_quote_status": execution_joins["quote"]["status"],
        "backfill_status": backfill,
    }


def _rate(numerator: int, denominator: int) -> float:
    return float(numerator) / float(denominator) if denominator else 0.0


def _summary(
    rows: list[dict[str, Any]],
    source_status: Mapping[str, Any] | None = None,
    migration_source_audit_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    source = dict(source_status or {})
    migrated_rows = [row for row in rows if row.get("global_migration_seen")]
    migrated = len(migrated_rows)
    buckets = Counter(str(row.get("readiness_bucket") or "unknown") for row in migrated_rows)
    legacy_backfill_possible = sum(
        1
        for row in migrated_rows
        if not row.get("birth_seen") and row.get("backfill_status") == "backfill_possible"
    )
    if legacy_backfill_possible and not buckets.get("backfill_possible"):
        buckets["backfill_possible"] = legacy_backfill_possible
    first_missing = Counter(str(row.get("first_missing_link") or "unknown") for row in migrated_rows)
    migration_source_classes = Counter(str(row.get("migration_source_coverage_class") or "unknown") for row in migration_source_audit_rows or [])
    full = buckets.get("full_path", 0)
    birth_seen = sum(1 for row in migrated_rows if row.get("birth_seen"))
    admitted = sum(1 for row in migrated_rows if row.get("admitted"))
    curve = sum(1 for row in migrated_rows if int(row.get("curve_observations_count") or 0) > 0)
    trade = sum(1 for row in migrated_rows if row.get("trade_flow_available"))
    post = sum(1 for row in migrated_rows if row.get("post_migration_observations_available"))
    quote = sum(1 for row in migrated_rows if row.get("executable_quote_available"))
    swap = sum(1 for row in migrated_rows if row.get("pumpswap_swap_event_available"))
    execution = sum(1 for row in migrated_rows if row.get("execution_cost_join_available"))
    source_miss = sum(1 for row in migrated_rows if row.get("first_missing_link") == "birth_source_miss")
    backfilled_not_live = sum(1 for row in migrated_rows if row.get("backfilled_birth_available"))
    sample_loss = sum(1 for row in migrated_rows if row.get("first_missing_link") == "sample_rejected")
    curve_missing = sum(1 for row in migrated_rows if row.get("first_missing_link") == "curve_observation_missing")
    trade_missing = sum(1 for row in migrated_rows if row.get("first_missing_link") == "trade_flow_missing")
    migration_backfill_failed = sum(1 for row in migrated_rows if row.get("backfill_status") == "backfill_not_possible")
    migration_level_a_count = sum(1 for row in migrated_rows if row.get("migration_evidence_level") == "LEVEL_A")
    migration_level_b_count = sum(1 for row in migrated_rows if row.get("migration_evidence_level") == "LEVEL_B")
    migration_level_c_candidate_count = sum(1 for row in migrated_rows if row.get("migration_evidence_level") in {"LEVEL_C", "CANDIDATE"})
    evidence_complete = sum(
        1
        for row in migrated_rows
        if row.get("migration_evidence_level") in {"LEVEL_A", "LEVEL_B"}
        and row.get("global_migration_seen")
        and row.get("pool_address")
    )
    return {
        "summary_id": "T007BD_FULL_PATH_LIFECYCLE_SUMMARY",
        "lifecycle_schema_version": "t007bd_full_path_lifecycle_v1",
        "total_lifecycle_mints": len(rows),
        "migrated_unique_mints": migrated,
        "full_path_migrated_mints": full,
        "strict_full_paths": full,
        "full_path_migrated_rate": _rate(full, migrated),
        "near_full_migrated_mints": buckets.get("near_full_missing_execution_cost", 0),
        "migration_plus_depth_only_mints": buckets.get("migration_plus_depth_only", 0),
        "coverage_buckets": dict(sorted(buckets.items())),
        "first_missing_link_counts": dict(sorted(first_missing.items())),
        "first_missing_link_breakdown": dict(sorted(first_missing.items())),
        "migration_source_coverage_class_counts": dict(sorted(migration_source_classes.items())),
        "migration_only_preexisting_count": migration_source_classes.get("MIGRATION_ONLY_PREEXISTING", 0),
        "migration_only_replay_unresolved_count": migration_source_classes.get("MIGRATION_ONLY_REPLAY_UNRESOLVED", 0),
        "migration_only_replay_not_run_count": migration_source_classes.get("MIGRATION_ONLY_REPLAY_NOT_RUN", 0),
        "true_birth_source_miss_count": migration_source_classes.get("MIGRATION_ONLY_SOURCE_MISS", 0),
        "live_birth_linked_migration_count": migration_source_classes.get("LIVE_BIRTH_LINKED", 0),
        "migrated_birth_seen_rate": _rate(birth_seen, migrated),
        "migrated_admitted_rate": _rate(admitted, migrated),
        "migrated_curve_observation_rate": _rate(curve, migrated),
        "migrated_trade_flow_rate": _rate(trade, migrated),
        "migrated_post_migration_observation_rate": _rate(post, migrated),
        "migrated_post_migration_quote_rate": _rate(quote, migrated),
        "migrated_pumpswap_swap_event_rate": _rate(swap, migrated),
        "migrated_execution_cost_join_rate": _rate(execution, migrated),
        "source_miss_count": source_miss,
        "backfilled_birth_not_live_count": backfilled_not_live,
        "sample_loss_count": sample_loss,
        "curve_observation_missing_count": curve_missing,
        "trade_flow_missing_count": trade_missing,
        "migration_backfill_failed_count": migration_backfill_failed,
        "migration_level_a_count": migration_level_a_count,
        "migration_level_b_count": migration_level_b_count,
        "migration_level_c_candidate_count": migration_level_c_candidate_count,
        "evidence_complete_migrated_mints": evidence_complete,
        "evidence_completeness_rate": _rate(evidence_complete, migrated),
        "queue_drops": int(_float(source.get("queue_drops") or source.get("queue_dropped_count")) or 0),
        "thin_queue_drops": int(_float(source.get("thin_queue_drops") or source.get("thin_probe_queue_drops")) or 0),
        "capacity_rejected": int(_float(source.get("capacity_rejected") or source.get("capacity_rejected_births")) or 0),
        "source_duration_quality_status": source.get("source_duration_quality_status") or "not_evaluated",
        "source_ended_early": _bool(source.get("source_ended_early")),
        "source_duration_completion_ratio": _float(source.get("source_duration_completion_ratio")),
        "requested_source_duration_seconds": _float(source.get("requested_source_duration_seconds") or source.get("source_duration_seconds")),
        "actual_source_duration_seconds": _float(source.get("actual_source_duration_seconds")),
        "websocket_keepalive_timeout_count": int(_float(source.get("websocket_keepalive_timeout_count")) or 0),
        "websocket_reconnect_count": int(_float(source.get("websocket_reconnect_count")) or 0),
        "subscription_connect_status": str(source.get("subscription_connect_status") or ""),
        "valuation_ladder_suppressed": True,
        "mayhem_untouched": True,
        "trading_disabled": True,
        "paper_trading_disabled": True,
        "wallet_signing_disabled": True,
        "edge_claim_allowed": False,
        "helius_developer_source_supported": True,
    }


def _summary_md(summary: Mapping[str, Any], gate: Mapping[str, Any]) -> str:
    lines = [
        "# T007BD Full Path Lifecycle Coverage Summary",
        "",
        "No live scan was run by this analysis.",
        "",
        f"- Migrated unique mints: `{summary.get('migrated_unique_mints')}`",
        f"- Full-path migrated mints: `{summary.get('full_path_migrated_mints')}`",
        f"- Full-path migrated rate: `{summary.get('full_path_migrated_rate')}`",
        f"- Migration plus depth only: `{summary.get('migration_plus_depth_only_mints')}`",
        f"- Source miss count: `{summary.get('source_miss_count')}`",
        f"- True during-window birth source miss count: `{summary.get('true_birth_source_miss_count')}`",
        f"- Preexisting migration-only count: `{summary.get('migration_only_preexisting_count')}`",
        f"- Replay unresolved migration-only count: `{summary.get('migration_only_replay_unresolved_count')}`",
        f"- Sample loss count: `{summary.get('sample_loss_count')}`",
        f"- Curve observation missing count: `{summary.get('curve_observation_missing_count')}`",
        f"- Trade flow missing count: `{summary.get('trade_flow_missing_count')}`",
        "",
        "## Gate",
        "",
        f"- Can run 10m feature proof: `{gate.get('can_run_10m_feature_proof')}`",
        f"- Can run 60m thesis scan: `{gate.get('can_run_60m_thesis_scan')}`",
        f"- Can run 2h+ scan: `{gate.get('can_run_2h_plus_scan')}`",
        f"- Long scan status: `{gate.get('long_scan_status')}`",
        f"- Blocking reasons: `{gate.get('blocking_reasons')}`",
    ]
    return "\n".join(lines) + "\n"


def build_lifecycle_outputs(archive_root: Path | str, output_root: Path | str | None = None, *, write_outputs: bool = True) -> dict[str, Any]:
    archive = Path(archive_root)
    output = Path(output_root) if output_root is not None else archive
    rows_by_family = {
        "birth": _group_by_mint(_read_jsonl(archive / "birth_audit.jsonl")),
        "curve": _group_by_mint(_read_jsonl(archive / "curve_observations.jsonl")),
        "threshold": _group_by_mint(_read_jsonl(archive / "true_curve_threshold_crossings.jsonl") or _read_jsonl(archive / "threshold_crossings.jsonl")),
        "velocity": _group_by_mint(_read_jsonl(archive / "curve_velocity_events.jsonl")),
        "acceleration": _group_by_mint(_read_jsonl(archive / "curve_acceleration_events.jsonl")),
        "trade_flow": _group_by_mint(_read_jsonl(archive / "trade_flow_events.jsonl")),
        "organic_flow": _group_by_mint(_read_jsonl(archive / "organic_flow_events.jsonl")),
        "holder": _group_by_mint(_read_jsonl(archive / "holder_distribution_snapshots.jsonl")),
        "dev": _group_by_mint(_read_jsonl(archive / "dev_behavior_events.jsonl")),
        "migration": _group_by_mint(_read_jsonl(archive / "global_migration_events.jsonl")),
        "post": _group_by_mint(_read_jsonl(archive / "post_migration_observations.jsonl")),
        "quote": _group_by_mint(_read_jsonl(archive / "executable_quote_observations.jsonl")),
        "swap": _group_by_mint(_read_jsonl(archive / "pumpswap_swap_events.jsonl")),
        "path": _group_by_mint(_read_jsonl(archive / "token_path_summary.jsonl")),
    }
    execution_rows = _read_jsonl(archive / "execution_cost_observations.jsonl")
    mints = sorted({mint for grouped in rows_by_family.values() for mint in grouped})
    rows = [_build_row(mint, rows_by_family, execution_rows) for mint in mints]
    source_status = _read_json(archive / "collector_summary.json") or _read_json(archive / "summary.json") or _read_json(archive / "live_status.json")
    manifest = _read_json(archive / "campaign_manifest.json")
    backfill_jobs_by_mint = _group_by_mint(_read_jsonl(archive / "migration_backfill_jobs.jsonl"))
    migration_source_audit_rows = _build_migration_source_coverage_audit(
        rows,
        backfill_jobs_by_mint=backfill_jobs_by_mint,
        manifest=manifest,
        source_status=source_status,
    )
    _apply_migration_source_coverage(rows, migration_source_audit_rows)
    summary = _summary(rows, source_status, migration_source_audit_rows)
    gate = evaluate_t007_full_path_readiness_gate(summary)
    if write_outputs:
        _write_jsonl(output / "lifecycle_ledger.jsonl", rows)
        _write_csv(output / "lifecycle_coverage_matrix.csv", rows)
        _write_jsonl(output / "migration_source_coverage_audit.jsonl", migration_source_audit_rows)
        _write_csv(output / "migration_source_coverage_audit.csv", migration_source_audit_rows)
        _write_json(output / "lifecycle_coverage_summary.json", {**summary, "gate": gate})
        (output / "lifecycle_coverage_summary.md").write_text(_summary_md(summary, gate), encoding="utf-8")
    return {"rows": rows, "summary": summary, "gate": gate, "migration_source_audit_rows": migration_source_audit_rows}


def build_lifecycle_live_status_payload(archive_root: Path | str, status: Mapping[str, Any] | None = None) -> dict[str, Any]:
    result = build_lifecycle_outputs(archive_root, write_outputs=False)
    summary = dict(result["summary"])
    summary.update(
        {
            "queue_drops": (status or {}).get("queue_drops", summary.get("queue_drops", 0)),
            "thin_queue_drops": (status or {}).get("thin_probe_queue_drops", summary.get("thin_queue_drops", 0)),
            "capacity_rejected": (status or {}).get("capacity_rejected", summary.get("capacity_rejected", 0)),
        }
    )
    gate = evaluate_t007_full_path_readiness_gate(summary)
    return {
        "watcher_schema_version": "t007bd_full_path_lifecycle_watcher_v1",
        "full_path_lifecycle_status": "available",
        "full_path_lifecycle_summary": summary,
        "full_path_readiness_gate": gate,
        "migrated_unique_mints": summary["migrated_unique_mints"],
        "strict_full_path_migrated_mints": summary["full_path_migrated_mints"],
        "full_path_migrated_mints": summary["full_path_migrated_mints"],
        "full_path_migrated_rate": summary["full_path_migrated_rate"],
        "migration_plus_depth_only_mints": summary["migration_plus_depth_only_mints"],
        "coverage_buckets": summary["coverage_buckets"],
        "first_missing_link_counts": summary["first_missing_link_counts"],
        "source_miss_count": summary["source_miss_count"],
        "sample_loss_count": summary["sample_loss_count"],
        "curve_observation_missing_count": summary["curve_observation_missing_count"],
        "trade_flow_missing_count": summary["trade_flow_missing_count"],
        "migration_backfill_failed_count": summary["migration_backfill_failed_count"],
        "migrated_birth_seen_rate": summary["migrated_birth_seen_rate"],
        "migrated_curve_observation_rate": summary["migrated_curve_observation_rate"],
        "migrated_trade_flow_rate": summary["migrated_trade_flow_rate"],
        "migrated_post_migration_quote_rate": summary["migrated_post_migration_quote_rate"],
        "migrated_execution_cost_join_rate": summary["migrated_execution_cost_join_rate"],
        "evidence_completeness_rate": summary.get("evidence_completeness_rate", 0.0),
        "migration_level_a_count": summary.get("migration_level_a_count", 0),
        "migration_level_b_count": summary.get("migration_level_b_count", 0),
        "can_run_10m_feature_proof": gate["can_run_10m_feature_proof"],
        "can_run_60m_thesis_scan": gate["can_run_60m_thesis_scan"],
        "can_run_2h_plus_scan": gate["can_run_2h_plus_scan"],
        "long_scan_status": gate["long_scan_status"],
        "full_path_blocking_reasons": gate["blocking_reasons"],
        "helius_developer_source_supported": gate["helius_developer_source_supported"],
    }
