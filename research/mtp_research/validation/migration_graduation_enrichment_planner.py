"""Dry-run planner for migration/graduation label enrichment."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CLASSIFICATION_GO = "dry_run_pilot_go"
CLASSIFICATION_NEEDS_ADJUSTMENT = "dry_run_pilot_needs_adjustment"
CLASSIFICATION_BLOCKED = "dry_run_pilot_blocked"

WINDOW_PROFILES = {
    "24h": {
        "base_signature_requests_per_mint": 1,
        "high_signature_requests_per_mint": 3,
        "base_transaction_requests_per_mint": 5,
        "high_transaction_requests_per_mint": 25,
        "raw_mb_per_mint_base": 1.0,
        "raw_mb_per_mint_high": 7.5,
        "runtime_minutes_base_per_mint": 0.20,
        "runtime_minutes_high_per_mint": 0.90,
    },
    "72h": {
        "base_signature_requests_per_mint": 2,
        "high_signature_requests_per_mint": 6,
        "base_transaction_requests_per_mint": 10,
        "high_transaction_requests_per_mint": 50,
        "raw_mb_per_mint_base": 2.5,
        "raw_mb_per_mint_high": 15.0,
        "runtime_minutes_base_per_mint": 0.45,
        "runtime_minutes_high_per_mint": 1.80,
    },
    "7d": {
        "base_signature_requests_per_mint": 5,
        "high_signature_requests_per_mint": 15,
        "base_transaction_requests_per_mint": 25,
        "high_transaction_requests_per_mint": 100,
        "raw_mb_per_mint_base": 7.5,
        "raw_mb_per_mint_high": 40.0,
        "runtime_minutes_base_per_mint": 1.20,
        "runtime_minutes_high_per_mint": 4.80,
    },
}


def build_migration_graduation_enrichment_dry_run_plan(
    *,
    candidates_path: Path | str,
    mint_limit: int = 100,
    windows: list[str] | None = None,
    request_ceiling: int = 3000,
    hard_stop_projected_requests: int = 5000,
    selection: str = "deterministic",
    dry_run: bool = True,
) -> dict[str, Any]:
    if not dry_run:
        raise ValueError("dry_run=True is required; this planner must not fetch data")
    if mint_limit <= 0:
        raise ValueError("mint_limit must be positive")
    if selection != "deterministic":
        raise ValueError("only deterministic selection is supported")
    windows = windows or ["24h", "72h", "7d"]
    _validate_windows(windows)
    candidates = _read_jsonl(candidates_path)
    selected = _select_mints(candidates, mint_limit)
    request_estimate = _request_estimate(selected, windows, request_ceiling)
    storage_runtime = _storage_runtime_estimate(selected, windows)
    exact_later_execute_command = _later_execute_command(
        mint_limit=mint_limit,
        primary_window=request_estimate["primary_window"],
        request_ceiling=request_ceiling,
        hard_stop_projected_requests=hard_stop_projected_requests,
    )
    stop_go = _stop_go(
        selected=selected,
        mint_limit=mint_limit,
        request_estimate=request_estimate,
        request_ceiling=request_ceiling,
        hard_stop_projected_requests=hard_stop_projected_requests,
        exact_later_execute_command=exact_later_execute_command,
    )
    creator_count = len({row["creator"] for row in selected if row.get("creator")})
    return {
        "report_id": "migration_graduation_enrichment_dry_run_plan_v0",
        "scope": {
            "dataset": "all_collected_launches",
            "candidates_path": str(candidates_path),
            "launches_available": len(candidates),
            "mint_limit": mint_limit,
            "selected_mint_count": len(selected),
            "selected_creator_count": creator_count,
            "selection": selection,
            "dry_run": True,
            "network_calls_used": 0,
            "helius_calls_used": 0,
            "thesis_runs": 0,
            "backtests_run": 0,
            "validation_runs": 0,
        },
        "selected_mints": selected,
        "label_semantics": [
            "pumpfun_migrate_event_observed",
            "graduated_to_pumpswap",
            "migrated_to_raydium",
            "dex_pair_detected",
            "liquidity_pool_created_after_launch",
            "migration_time",
            "migration_source",
            "migration_confidence",
            "migration_missing_reason",
        ],
        "request_estimate": request_estimate,
        "storage_runtime_estimate": storage_runtime,
        "stop_go": stop_go,
        "dry_run_classification": stop_go["classification"],
        "exact_later_execute_command": exact_later_execute_command,
        "methodology_flags": [
            "dry_run_only",
            "no_network_calls",
            "no_helius_calls",
            "no_data_fetching",
            "no_t008",
            "no_thesis_cycle",
            "no_backtest",
            "no_validation",
            "no_trading_logic",
            "no_threshold_optimization",
            "no_grid_search",
            "no_ml",
        ],
    }


def write_migration_graduation_enrichment_plan_outputs(
    report: dict[str, Any],
    *,
    output_dir: Path | str,
) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "migration_graduation_enrichment_dry_run_plan.json"
    markdown_path = output / "migration_graduation_enrichment_dry_run_plan.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(_markdown(report), encoding="utf-8")
    return {"json_path": json_path, "markdown_path": markdown_path}


def _select_mints(candidates: list[dict[str, Any]], mint_limit: int) -> list[dict[str, Any]]:
    rows = [_candidate_row(row) for row in candidates if _mint(row) and _launch_ts(row) is not None]
    creator_counts = Counter(row["creator"] for row in rows if row.get("creator"))
    repeat_rows = [row for row in rows if row.get("creator") and creator_counts[row["creator"]] > 1]
    singleton_rows = [row for row in rows if not row.get("creator") or creator_counts[row["creator"]] <= 1]
    repeat_rows.sort(key=lambda row: (-creator_counts[row["creator"]], row["launch_ts"], row["mint"]))
    singleton_rows.sort(key=lambda row: (row["launch_ts"], row["mint"]))
    selected = _stable_repeat_singleton_interleave(repeat_rows, singleton_rows, mint_limit)
    return [_selection_public_row(row, creator_counts) for row in selected[:mint_limit]]


def _candidate_row(row: dict[str, Any]) -> dict[str, Any]:
    metadata = row.get("metadata_json") or {}
    return {
        "launch_id": row.get("launch_id"),
        "mint": _mint(row),
        "creator": _creator(row),
        "launch_ts": _launch_ts(row),
        "launch_time": row.get("launch_time_utc") or _timestamp(_launch_ts(row)),
        "bonding_curve": metadata.get("bonding_curve") or row.get("pool_address"),
        "associated_bonding_curve": metadata.get("associated_bonding_curve"),
        "creation_signature": metadata.get("creation_signature") or row.get("creation_signature"),
    }


def _selection_public_row(row: dict[str, Any], creator_counts: Counter) -> dict[str, Any]:
    reason = "repeat_creator_priority" if row.get("creator") and creator_counts[row["creator"]] > 1 else "singleton_time_distribution"
    return {
        "launch_id": row["launch_id"],
        "mint": row["mint"],
        "creator": row["creator"],
        "launch_time": row["launch_time"],
        "launch_ts": row["launch_ts"],
        "bonding_curve": row["bonding_curve"],
        "associated_bonding_curve": row["associated_bonding_curve"],
        "creation_signature": row["creation_signature"],
        "reason_selected": reason,
        "creator_launch_count_in_input": creator_counts.get(row["creator"], 0) if row.get("creator") else 0,
    }


def _stable_repeat_singleton_interleave(
    repeat_rows: list[dict[str, Any]],
    singleton_rows: list[dict[str, Any]],
    mint_limit: int,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    repeat_index = 0
    singleton_index = 0
    while len(selected) < mint_limit and (repeat_index < len(repeat_rows) or singleton_index < len(singleton_rows)):
        use_singleton = (len(selected) + 1) % 4 == 0 and singleton_index < len(singleton_rows)
        if use_singleton or repeat_index >= len(repeat_rows):
            selected.append(singleton_rows[singleton_index])
            singleton_index += 1
            continue
        selected.append(repeat_rows[repeat_index])
        repeat_index += 1
    return selected


def _request_estimate(selected: list[dict[str, Any]], windows: list[str], request_ceiling: int) -> dict[str, Any]:
    estimates = {}
    for window in windows:
        profile = WINDOW_PROFILES[window]
        base_per_mint = profile["base_signature_requests_per_mint"] + profile["base_transaction_requests_per_mint"]
        high_per_mint = profile["high_signature_requests_per_mint"] + profile["high_transaction_requests_per_mint"]
        estimates[window] = {
            "base_signature_requests": len(selected) * profile["base_signature_requests_per_mint"],
            "high_signature_requests": len(selected) * profile["high_signature_requests_per_mint"],
            "base_transaction_requests": len(selected) * profile["base_transaction_requests_per_mint"],
            "high_transaction_requests": len(selected) * profile["high_transaction_requests_per_mint"],
            "base_projected_requests": len(selected) * base_per_mint,
            "high_projected_requests": len(selected) * high_per_mint,
            "base_per_mint": base_per_mint,
            "high_per_mint": high_per_mint,
        }
    primary = windows[0]
    primary_estimate = estimates[primary]
    return {
        "primary_window": primary,
        "primary_base_projected_requests": primary_estimate["base_projected_requests"],
        "primary_high_projected_requests": primary_estimate["high_projected_requests"],
        "request_equivalent_credit_estimate": {
            "base": primary_estimate["base_projected_requests"],
            "high": primary_estimate["high_projected_requests"],
            "unit": "request_equivalent_not_dashboard_credit_multiplier",
        },
        "request_ceiling": request_ceiling,
        "request_ceiling_status": "within_ceiling" if primary_estimate["high_projected_requests"] <= request_ceiling else "above_ceiling",
        "windows": estimates,
    }


def _storage_runtime_estimate(selected: list[dict[str, Any]], windows: list[str]) -> dict[str, Any]:
    estimates = {}
    for window in windows:
        profile = WINDOW_PROFILES[window]
        estimates[window] = {
            "expected_raw_json_size_mb": {
                "base": round(len(selected) * profile["raw_mb_per_mint_base"], 2),
                "high": round(len(selected) * profile["raw_mb_per_mint_high"], 2),
            },
            "expected_parsed_parquet_size_mb": {
                "base": round(len(selected) * profile["raw_mb_per_mint_base"] * 0.2, 2),
                "high": round(len(selected) * profile["raw_mb_per_mint_high"] * 0.2, 2),
            },
            "expected_runtime_minutes": {
                "base": round(len(selected) * profile["runtime_minutes_base_per_mint"], 2),
                "high": round(len(selected) * profile["runtime_minutes_high_per_mint"], 2),
            },
        }
    return {
        "windows": estimates,
        "checkpoint_count": len(selected),
        "resume_behavior_needed": "checkpoint by mint + window + source and skip already persisted signatures",
    }


def _stop_go(
    *,
    selected: list[dict[str, Any]],
    mint_limit: int,
    request_estimate: dict[str, Any],
    request_ceiling: int,
    hard_stop_projected_requests: int,
    exact_later_execute_command: str,
) -> dict[str, Any]:
    failed = []
    primary_high = request_estimate["primary_high_projected_requests"]
    if len(selected) > mint_limit:
        failed.append("selected_mints_above_mint_limit")
    if primary_high > request_ceiling:
        failed.append("primary_high_requests_above_request_ceiling")
    if primary_high > hard_stop_projected_requests:
        failed.append("primary_high_requests_above_hard_stop")
    if not exact_later_execute_command.endswith("--execute"):
        failed.append("exact_real_command_missing")
    hard_failures = {"selected_mints_above_mint_limit", "primary_high_requests_above_hard_stop", "exact_real_command_missing"}
    if any(reason in hard_failures for reason in failed):
        classification = CLASSIFICATION_BLOCKED
    elif failed:
        classification = CLASSIFICATION_NEEDS_ADJUSTMENT
    else:
        classification = CLASSIFICATION_GO
    return {
        "classification": classification,
        "passed_gates": [
            "selected_mints_within_limit" if len(selected) <= mint_limit else None,
            "primary_high_requests_within_request_ceiling" if primary_high <= request_ceiling else None,
            "primary_high_requests_within_hard_stop" if primary_high <= hard_stop_projected_requests else None,
            "exact_later_execute_command_generated" if exact_later_execute_command.endswith("--execute") else None,
            "no_network_calls_made",
        ],
        "failed_gates": failed,
        "request_ceiling": request_ceiling,
        "hard_stop_projected_requests": hard_stop_projected_requests,
    }


def _later_execute_command(
    *,
    mint_limit: int,
    primary_window: str,
    request_ceiling: int,
    hard_stop_projected_requests: int,
) -> str:
    return (
        "./trading_env/bin/python -m research.mtp_research.validation.run_migration_graduation_enrichment_collection "
        f"--mint-limit {mint_limit} "
        f"--window {primary_window} "
        "--max-signature-pages-per-mint 3 "
        "--max-transactions-per-mint 25 "
        "--max-total-transactions 2500 "
        f"--request-ceiling {request_ceiling} "
        f"--hard-stop-projected-requests {hard_stop_projected_requests} "
        "--execute"
    )


def _validate_windows(windows: list[str]) -> None:
    unknown = [window for window in windows if window not in WINDOW_PROFILES]
    if unknown:
        raise ValueError(f"windows must be drawn from {sorted(WINDOW_PROFILES)}; got {unknown}")


def _mint(row: dict[str, Any]) -> str | None:
    return row.get("token_mint") or row.get("mint")


def _creator(row: dict[str, Any]) -> str | None:
    metadata = row.get("metadata_json") or {}
    return row.get("creator_deployer") or row.get("creator") or metadata.get("creator_deployer")


def _launch_ts(row: dict[str, Any]) -> int | None:
    try:
        value = row.get("launch_ts") or row.get("block_time")
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _timestamp(value: int | None) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()


def _read_jsonl(path: Path | str) -> list[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _markdown(report: dict[str, Any]) -> str:
    scope = report["scope"]
    request = report["request_estimate"]
    storage = report["storage_runtime_estimate"]
    stop_go = report["stop_go"]
    lines = [
        "# Migration / Graduation Enrichment Dry-Run Plan",
        "",
        f"- Dry-run classification: `{report['dry_run_classification']}`",
        f"- Selected mints: `{scope['selected_mint_count']}`",
        f"- Selected creators: `{scope['selected_creator_count']}`",
        f"- Primary window: `{request['primary_window']}`",
        f"- Base projected requests: `{request['primary_base_projected_requests']}`",
        f"- High projected requests: `{request['primary_high_projected_requests']}`",
        f"- Request ceiling status: `{request['request_ceiling_status']}`",
        f"- Network calls used: `{scope['network_calls_used']}`",
        f"- Helius calls used: `{scope['helius_calls_used']}`",
        "- No network calls were made.",
        "- No thesis, backtest, validation, or trading workflow was run.",
        "",
        "## Window Estimates",
        "",
        "| Window | Base Requests | High Requests | Raw MB Base | Raw MB High | Runtime Min Base | Runtime Min High |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for window, estimate in request["windows"].items():
        storage_estimate = storage["windows"][window]
        lines.append(
            f"| `{window}` | {estimate['base_projected_requests']} | {estimate['high_projected_requests']} | "
            f"{storage_estimate['expected_raw_json_size_mb']['base']} | {storage_estimate['expected_raw_json_size_mb']['high']} | "
            f"{storage_estimate['expected_runtime_minutes']['base']} | {storage_estimate['expected_runtime_minutes']['high']} |"
        )
    lines.extend(
        [
            "",
            "## Selected Mints",
            "",
            "| Mint | Creator | Launch Time | Reason |",
            "|---|---|---|---|",
        ]
    )
    for row in report["selected_mints"]:
        lines.append(f"| `{row['mint']}` | `{row['creator']}` | `{row['launch_time']}` | `{row['reason_selected']}` |")
    lines.extend(
        [
            "",
            "## Stop / Go",
            "",
            f"- Classification: `{stop_go['classification']}`",
            f"- Passed gates: `{[gate for gate in stop_go['passed_gates'] if gate]}`",
            f"- Failed gates: `{stop_go['failed_gates']}`",
            "",
            "## Exact Later Execute Command",
            "",
            "```bash",
            report["exact_later_execute_command"],
            "```",
        ]
    )
    return "\n".join(lines) + "\n"
