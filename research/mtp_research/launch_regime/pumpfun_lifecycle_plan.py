"""Dry-run planning for Pump.fun first-two-hour lifecycle collection."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from research.mtp_research.ingestion.pumpfun_creation_census import (
    PumpFunCreationCensusRow,
    load_census_rows,
)
from research.mtp_research.launch_regime.builder import SNAPSHOT_AGES, LaunchRegimeConfig


PACIFIC = ZoneInfo("America/Los_Angeles")
DEFAULT_CENSUS_PATH = Path("data/normalized/pumpfun_creation_census.jsonl")
DEFAULT_PRECISION_SUMMARY_PATH = Path("data/backtests/diagnostics/reports/pumpfun_precision_auto_summary.json")
DEFAULT_PLAN_PATH = Path("data/backtests/diagnostics/reports/pumpfun_lifecycle_collection_plan.json")
DEFAULT_MARKDOWN_PLAN_PATH = Path("data/backtests/diagnostics/reports/pumpfun_lifecycle_collection_plan.md")


def build_pumpfun_lifecycle_plan(
    *,
    census_path: Path | str = DEFAULT_CENSUS_PATH,
    precision_summary_path: Path | str = DEFAULT_PRECISION_SUMMARY_PATH,
    target_launches: int = 2500,
    signature_pages_per_launch: int = 1,
    max_transactions_per_launch: int = 100,
    targets_per_launch: int = 1,
    max_rpc_requests: int = 300_000,
    config: LaunchRegimeConfig | None = None,
) -> dict[str, Any]:
    """Create a no-network lifecycle collection plan from verified Pump.fun creates."""
    config = config or LaunchRegimeConfig()
    rows = load_census_rows(census_path)
    accepted_rows = [row for row in rows if _accepted_launch_row(row)]
    deduped_rows = _dedupe_by_mint(accepted_rows)
    eligible_rows = [row for row in deduped_rows if _in_configured_regime(row, config)]
    selected_rows = eligible_rows[:target_launches]
    precision_summary = _load_precision_summary(precision_summary_path)

    estimated_signature_requests = len(selected_rows) * signature_pages_per_launch * targets_per_launch
    estimated_transaction_requests = len(selected_rows) * max_transactions_per_launch * targets_per_launch
    estimated_total_rpc_requests = estimated_signature_requests + estimated_transaction_requests
    expected_snapshot_rows = len(selected_rows) * len(SNAPSHOT_AGES)
    expected_outcome_rows = len(selected_rows)
    warnings = _warning_flags(
        precision_summary=precision_summary,
        selected_count=len(selected_rows),
        target_launches=target_launches,
        estimated_total_rpc_requests=estimated_total_rpc_requests,
        max_rpc_requests=max_rpc_requests,
    )
    blocker_flags = _blocker_flags(warnings)
    regime_counts = Counter(_launch_regime_name(row) for row in selected_rows)
    weekday_counts = Counter(_local_dt(row).strftime("%A") for row in selected_rows)
    accepted_weekday_counts = Counter(_local_dt(row).strftime("%A") for row in accepted_rows)
    accepted_hour_counts = Counter(_local_dt(row).hour for row in accepted_rows)
    accepted_window_counts = Counter(_window_bucket(row, config) for row in accepted_rows)

    return {
        "census_path": str(census_path),
        "precision_summary_path": str(precision_summary_path),
        "census_rows": len(rows),
        "accepted_census_rows": len(accepted_rows),
        "deduped_accepted_launches": len(deduped_rows),
        "eligible_launches": len(eligible_rows),
        "selected_launches": len(selected_rows),
        "target_launches": target_launches,
        "collection_scope": "first_two_hours_only",
        "max_lifecycle_seconds": config.max_lifecycle_seconds,
        "snapshot_ages_seconds": SNAPSHOT_AGES,
        "expected_snapshot_rows": expected_snapshot_rows,
        "expected_outcome_rows": expected_outcome_rows,
        "expected_research_rows": expected_snapshot_rows + expected_outcome_rows,
        "targets_per_launch": targets_per_launch,
        "target_account_role": "bonding_curve",
        "selected_with_bonding_curve": sum(1 for row in selected_rows if row.bonding_curve),
        "signature_pages_per_launch": signature_pages_per_launch,
        "max_transactions_per_launch": max_transactions_per_launch,
        "estimated_signature_requests": estimated_signature_requests,
        "estimated_transaction_requests": estimated_transaction_requests,
        "estimated_total_rpc_requests": estimated_total_rpc_requests,
        "estimated_credits": estimated_total_rpc_requests,
        "expected_raw_transactions_up_to": estimated_transaction_requests,
        "launch_regime_counts": dict(sorted(regime_counts.items())),
        "launch_weekday_counts": dict(sorted(weekday_counts.items())),
        "accepted_weekday_counts": dict(sorted(accepted_weekday_counts.items())),
        "accepted_hour_local_counts": dict(sorted(accepted_hour_counts.items())),
        "accepted_configured_window_counts": dict(sorted(accepted_window_counts.items())),
        "first_selected_block_time": min((row.block_time for row in selected_rows if row.block_time is not None), default=None),
        "last_selected_block_time": max((row.block_time for row in selected_rows if row.block_time is not None), default=None),
        "precision_gate": precision_summary,
        "network_calls": 0,
        "plan_reasonable": not blocker_flags,
        "warning_flags": warnings,
        "next_safe_action": _next_safe_action(warnings),
    }


def write_pumpfun_lifecycle_plan(plan: dict[str, Any], output_path: Path | str = DEFAULT_PLAN_PATH) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output_path


def write_pumpfun_lifecycle_plan_markdown(
    plan: dict[str, Any],
    output_path: Path | str = DEFAULT_MARKDOWN_PLAN_PATH,
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Pump.fun Lifecycle Collection Plan",
        "",
        "Dry-run planning report only. This does not collect lifecycle data, run backtests, run walk-forward validation, promote theses, paper trade, or live trade.",
        "",
        f"- Census rows: `{plan['census_rows']}`",
        f"- Accepted census rows: `{plan['accepted_census_rows']}`",
        f"- Eligible launches: `{plan['eligible_launches']}`",
        f"- Selected launches: `{plan['selected_launches']}`",
        f"- Collection scope: `{plan['collection_scope']}`",
        f"- Max lifecycle seconds: `{plan['max_lifecycle_seconds']}`",
        f"- Expected snapshot rows: `{plan['expected_snapshot_rows']}`",
        f"- Expected outcome rows: `{plan['expected_outcome_rows']}`",
        f"- Estimated signature requests: `{plan['estimated_signature_requests']}`",
        f"- Estimated transaction requests: `{plan['estimated_transaction_requests']}`",
        f"- Estimated total RPC requests: `{plan['estimated_total_rpc_requests']}`",
        f"- Estimated credits: `{plan['estimated_credits']}`",
        f"- Network calls: `{plan['network_calls']}`",
        f"- Plan reasonable: `{plan['plan_reasonable']}`",
        f"- Warning flags: `{plan['warning_flags']}`",
        f"- Next safe action: `{plan['next_safe_action']}`",
        "",
        "## Launch Regime Coverage",
        "",
        f"- Regime counts: `{plan['launch_regime_counts']}`",
        f"- Weekday counts: `{plan['launch_weekday_counts']}`",
        f"- Accepted census weekday counts: `{plan['accepted_weekday_counts']}`",
        f"- Accepted census hour counts: `{plan['accepted_hour_local_counts']}`",
        f"- Accepted census configured-window counts: `{plan['accepted_configured_window_counts']}`",
    ]
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path


def _accepted_launch_row(row: PumpFunCreationCensusRow) -> bool:
    return bool(row.accepted and row.mint and row.block_time is not None)


def _dedupe_by_mint(rows: list[PumpFunCreationCensusRow]) -> list[PumpFunCreationCensusRow]:
    by_mint: dict[str, PumpFunCreationCensusRow] = {}
    for row in sorted(rows, key=lambda item: (item.block_time or 0, item.creation_signature, item.instruction_index or -1)):
        if row.mint:
            by_mint.setdefault(row.mint, row)
    return list(by_mint.values())


def _local_dt(row: PumpFunCreationCensusRow) -> datetime:
    return datetime.fromtimestamp(int(row.block_time or 0), tz=PACIFIC)


def _in_configured_regime(row: PumpFunCreationCensusRow, config: LaunchRegimeConfig) -> bool:
    return _window_bucket(row, config) == "configured_weekday_window"


def _window_bucket(row: PumpFunCreationCensusRow, config: LaunchRegimeConfig) -> str:
    local = _local_dt(row)
    seconds_since_midnight = local.hour * 3600 + local.minute * 60 + local.second
    if local.weekday() not in config.weekdays:
        return "outside_configured_weekday"
    if any(start <= seconds_since_midnight <= end for start, end in config.windows):
        return "configured_weekday_window"
    return "configured_weekday_outside_time_window"


def _launch_regime_name(row: PumpFunCreationCensusRow) -> str:
    local = _local_dt(row)
    seconds_since_midnight = local.hour * 3600 + local.minute * 60 + local.second
    if 6 * 3600 <= seconds_since_midnight <= 12 * 3600:
        return "mon_tue_wed_0600_1200_pt"
    if 17 * 3600 <= seconds_since_midnight <= 22 * 3600:
        return "mon_tue_wed_1700_2200_pt"
    return "outside_configured_regime"


def _load_precision_summary(path: Path | str) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        return {"acceptable_for_scaling": False, "warning_flags": ["precision_summary_missing"]}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {"acceptable_for_scaling": False, "warning_flags": ["precision_summary_invalid"]}


def _warning_flags(
    *,
    precision_summary: dict[str, Any],
    selected_count: int,
    target_launches: int,
    estimated_total_rpc_requests: int,
    max_rpc_requests: int,
) -> list[str]:
    warnings: list[str] = []
    if not precision_summary.get("acceptable_for_scaling"):
        warnings.append("precision_gate_not_acceptable_for_scaling")
    if selected_count == 0:
        warnings.append("no_launches_selected")
    if selected_count < target_launches:
        warnings.append("selected_launches_below_target")
    if estimated_total_rpc_requests > max_rpc_requests:
        warnings.append("estimated_rpc_requests_exceed_cap")
    return warnings


def _blocker_flags(warnings: list[str]) -> list[str]:
    return [
        warning for warning in warnings
        if warning
        in {
            "precision_gate_not_acceptable_for_scaling",
            "no_launches_selected",
            "estimated_rpc_requests_exceed_cap",
        }
    ]


def _next_safe_action(warnings: list[str]) -> str:
    if "precision_gate_not_acceptable_for_scaling" in warnings:
        return "complete_precision_review_before_lifecycle_collection"
    if "no_launches_selected" in warnings:
        return "inspect_census_regime_filter_before_lifecycle_collection"
    if "estimated_rpc_requests_exceed_cap" in warnings:
        return "lower_lifecycle_collection_bounds_before_execute"
    return "review_plan_then_run_tiny_bounded_lifecycle_pilot"
