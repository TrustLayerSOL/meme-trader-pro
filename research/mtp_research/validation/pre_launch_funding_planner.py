"""Dry-run planner for pre-launch creator funding acquisition."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CLASSIFICATION_GO = "dry_run_pilot_go"
CLASSIFICATION_NEEDS_ADJUSTMENT = "dry_run_pilot_needs_adjustment"
CLASSIFICATION_BLOCKED = "dry_run_pilot_blocked"

LOOKBACK_PROFILES = {
    1: {
        "label": "1h",
        "base_signature_requests_per_creator": 1,
        "high_signature_requests_per_creator": 1,
        "base_transaction_requests_per_creator": 5,
        "high_transaction_requests_per_creator": 10,
        "raw_mb_per_creator_base": 0.5,
        "raw_mb_per_creator_high": 2.0,
        "runtime_minutes_base_per_creator": 0.10,
        "runtime_minutes_high_per_creator": 0.30,
    },
    6: {
        "label": "6h",
        "base_signature_requests_per_creator": 1,
        "high_signature_requests_per_creator": 1,
        "base_transaction_requests_per_creator": 10,
        "high_transaction_requests_per_creator": 20,
        "raw_mb_per_creator_base": 1.0,
        "raw_mb_per_creator_high": 4.0,
        "runtime_minutes_base_per_creator": 0.20,
        "runtime_minutes_high_per_creator": 0.60,
    },
    24: {
        "label": "24h",
        "base_signature_requests_per_creator": 1,
        "high_signature_requests_per_creator": 2,
        "base_transaction_requests_per_creator": 20,
        "high_transaction_requests_per_creator": 50,
        "raw_mb_per_creator_base": 2.0,
        "raw_mb_per_creator_high": 10.0,
        "runtime_minutes_base_per_creator": 0.40,
        "runtime_minutes_high_per_creator": 1.50,
    },
    168: {
        "label": "7d",
        "base_signature_requests_per_creator": 3,
        "high_signature_requests_per_creator": 6,
        "base_transaction_requests_per_creator": 50,
        "high_transaction_requests_per_creator": 150,
        "raw_mb_per_creator_base": 5.0,
        "raw_mb_per_creator_high": 30.0,
        "runtime_minutes_base_per_creator": 1.20,
        "runtime_minutes_high_per_creator": 4.80,
    },
}


def build_pre_launch_funding_dry_run_plan(
    *,
    candidates_path: Path | str,
    max_creators: int = 50,
    lookback_hours: int = 24,
    request_ceiling: int = 3000,
    hard_stop_projected_requests: int = 5000,
    creator_selection: str = "deterministic",
    dry_run: bool = True,
) -> dict[str, Any]:
    if not dry_run:
        raise ValueError("dry_run=True is required; this planner must not fetch data")
    if max_creators <= 0:
        raise ValueError("max_creators must be positive")
    if creator_selection != "deterministic":
        raise ValueError("only deterministic creator selection is supported")
    profile = _lookback_profile(lookback_hours)
    candidates = _read_jsonl(candidates_path)
    creator_rows = _creator_groups(candidates)
    selected = _select_creators(creator_rows, max_creators)
    request_estimate = _request_estimate(selected, profile, request_ceiling)
    storage_runtime = _storage_runtime_estimate(selected, profile)
    exact_later_execute_command = _later_execute_command(
        max_creators=max_creators,
        lookback_hours=lookback_hours,
        request_ceiling=request_ceiling,
        hard_stop_projected_requests=hard_stop_projected_requests,
    )
    stop_go = _stop_go(
        selected=selected,
        max_creators=max_creators,
        request_estimate=request_estimate,
        request_ceiling=request_ceiling,
        hard_stop_projected_requests=hard_stop_projected_requests,
        exact_later_execute_command=exact_later_execute_command,
    )
    return {
        "report_id": "pre_launch_funding_dry_run_plan_v0",
        "scope": {
            "dataset": "strict_launch_regime",
            "candidates_path": str(candidates_path),
            "launches_available": len(candidates),
            "unique_creators_available": len(creator_rows),
            "max_creators": max_creators,
            "selected_creator_count": len(selected),
            "launches_covered_by_selected_creators": sum(row["launch_count_in_strict_cohort"] for row in selected),
            "creator_selection": creator_selection,
            "dry_run": True,
            "network_calls_used": 0,
            "helius_calls_used": 0,
            "thesis_runs": 0,
            "backtests_run": 0,
        },
        "selected_creators": selected,
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


def write_pre_launch_funding_plan_outputs(report: dict[str, Any], *, output_dir: Path | str) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "pre_launch_funding_dry_run_plan.json"
    markdown_path = output / "pre_launch_funding_dry_run_plan.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(_markdown(report), encoding="utf-8")
    return {"json_path": json_path, "markdown_path": markdown_path}


def _select_creators(creator_rows: list[dict[str, Any]], max_creators: int) -> list[dict[str, Any]]:
    repeat = [row for row in creator_rows if row["launch_count_in_strict_cohort"] > 1]
    single = [row for row in creator_rows if row["launch_count_in_strict_cohort"] == 1]
    repeat.sort(key=lambda row: (-row["launch_count_in_strict_cohort"], row["first_launch_ts"], row["creator"]))
    single.sort(key=lambda row: (row["first_launch_ts"], row["creator"]))
    target_singletons = 0 if max_creators <= 2 else max(1, min(len(single), max_creators // 5))
    selected_repeat = repeat[: max(0, max_creators - target_singletons)]
    selected = list(selected_repeat)
    selected_creators = {row["creator"] for row in selected}
    if target_singletons:
        selected.extend(_time_distributed_rows([row for row in single if row["creator"] not in selected_creators], target_singletons))
    if len(selected) < max_creators:
        selected_creators = {row["creator"] for row in selected}
        remaining = [row for row in repeat + single if row["creator"] not in selected_creators]
        selected.extend(remaining[: max_creators - len(selected)])
    selected = selected[:max_creators]
    return [_selection_public_row(row) for row in selected]


def _time_distributed_rows(rows: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    if count <= 0 or not rows:
        return []
    if count >= len(rows):
        return rows
    selected = []
    used = set()
    for index in range(count):
        source_index = round(index * (len(rows) - 1) / max(1, count - 1))
        while source_index in used and source_index + 1 < len(rows):
            source_index += 1
        used.add(source_index)
        selected.append(rows[source_index])
    return selected


def _selection_public_row(row: dict[str, Any]) -> dict[str, Any]:
    reason = "repeat_creator_priority" if row["launch_count_in_strict_cohort"] > 1 else "singleton_time_distribution"
    return {
        "creator": row["creator"],
        "launch_count_in_strict_cohort": row["launch_count_in_strict_cohort"],
        "selected_launch_ids": row["selected_launch_ids"],
        "first_launch_time": row["first_launch_time"],
        "last_launch_time": row["last_launch_time"],
        "first_launch_ts": row["first_launch_ts"],
        "last_launch_ts": row["last_launch_ts"],
        "reason_selected": reason,
    }


def _creator_groups(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in candidates:
        creator = _creator(row)
        launch_ts = _int_or_none(row.get("launch_ts"))
        if not creator or launch_ts is None:
            continue
        grouped[creator].append(row)
    creator_rows = []
    for creator, rows in grouped.items():
        rows = sorted(rows, key=lambda row: (_int_or_none(row.get("launch_ts")) or 0, row.get("launch_id") or ""))
        first_ts = _int_or_none(rows[0].get("launch_ts")) or 0
        last_ts = _int_or_none(rows[-1].get("launch_ts")) or first_ts
        creator_rows.append(
            {
                "creator": creator,
                "launch_count_in_strict_cohort": len(rows),
                "selected_launch_ids": [str(row.get("launch_id")) for row in rows if row.get("launch_id")],
                "first_launch_ts": first_ts,
                "last_launch_ts": last_ts,
                "first_launch_time": _launch_time(rows[0], first_ts),
                "last_launch_time": _launch_time(rows[-1], last_ts),
            }
        )
    return creator_rows


def _request_estimate(selected: list[dict[str, Any]], profile: dict[str, Any], request_ceiling: int) -> dict[str, Any]:
    per_creator = []
    for row in selected:
        base_signature = int(profile["base_signature_requests_per_creator"])
        high_signature = int(profile["high_signature_requests_per_creator"])
        base_tx = int(profile["base_transaction_requests_per_creator"])
        high_tx = int(profile["high_transaction_requests_per_creator"])
        per_creator.append(
            {
                "creator": row["creator"],
                "lookback_window": profile["label"],
                "base_signature_requests": base_signature,
                "high_signature_requests": high_signature,
                "base_transaction_requests": base_tx,
                "high_transaction_requests": high_tx,
                "base_request_estimate": base_signature + base_tx,
                "high_request_estimate": high_signature + high_tx,
            }
        )
    base_total = sum(row["base_request_estimate"] for row in per_creator)
    high_total = sum(row["high_request_estimate"] for row in per_creator)
    return {
        "lookback_window": profile["label"],
        "base_projected_requests": base_total,
        "high_projected_requests": high_total,
        "request_equivalent_credit_estimate": {
            "base": base_total,
            "high": high_total,
            "unit": "request_equivalent_not_dashboard_credit_multiplier",
        },
        "request_ceiling": request_ceiling,
        "request_ceiling_status": "within_ceiling" if high_total <= request_ceiling else "above_ceiling",
        "per_creator": per_creator,
        "per_lookback_window": {
            profile_data["label"]: {
                "base_per_creator": profile_data["base_signature_requests_per_creator"]
                + profile_data["base_transaction_requests_per_creator"],
                "high_per_creator": profile_data["high_signature_requests_per_creator"]
                + profile_data["high_transaction_requests_per_creator"],
            }
            for profile_data in LOOKBACK_PROFILES.values()
        },
    }


def _storage_runtime_estimate(selected: list[dict[str, Any]], profile: dict[str, Any]) -> dict[str, Any]:
    count = len(selected)
    raw_base = count * float(profile["raw_mb_per_creator_base"])
    raw_high = count * float(profile["raw_mb_per_creator_high"])
    runtime_base = count * float(profile["runtime_minutes_base_per_creator"])
    runtime_high = count * float(profile["runtime_minutes_high_per_creator"])
    return {
        "expected_raw_json_size_mb": {"base": round(raw_base, 2), "high": round(raw_high, 2)},
        "expected_parsed_parquet_size_mb": {"base": round(raw_base * 0.2, 2), "high": round(raw_high * 0.2, 2)},
        "expected_runtime_minutes": {"base": round(runtime_base, 2), "high": round(runtime_high, 2)},
        "checkpoint_count": count,
        "resume_behavior_needed": "checkpoint after each creator and skip already persisted creator-window outputs",
    }


def _stop_go(
    *,
    selected: list[dict[str, Any]],
    max_creators: int,
    request_estimate: dict[str, Any],
    request_ceiling: int,
    hard_stop_projected_requests: int,
    exact_later_execute_command: str,
) -> dict[str, Any]:
    failed = []
    if len(selected) > max_creators:
        failed.append("selected_creators_above_max_creators")
    if request_estimate["high_projected_requests"] > request_ceiling:
        failed.append("projected_high_requests_above_request_ceiling")
    if request_estimate["high_projected_requests"] > hard_stop_projected_requests:
        failed.append("projected_high_requests_above_hard_stop")
    if not exact_later_execute_command.endswith("--execute"):
        failed.append("exact_real_command_missing")
    hard_failures = {"selected_creators_above_max_creators", "projected_high_requests_above_hard_stop", "exact_real_command_missing"}
    if any(reason in hard_failures for reason in failed):
        classification = CLASSIFICATION_BLOCKED
    elif failed:
        classification = CLASSIFICATION_NEEDS_ADJUSTMENT
    else:
        classification = CLASSIFICATION_GO
    return {
        "classification": classification,
        "passed_gates": [
            "selected_creators_within_max" if len(selected) <= max_creators else None,
            "projected_high_requests_within_request_ceiling"
            if request_estimate["high_projected_requests"] <= request_ceiling
            else None,
            "projected_high_requests_within_hard_stop"
            if request_estimate["high_projected_requests"] <= hard_stop_projected_requests
            else None,
            "exact_later_execute_command_generated" if exact_later_execute_command.endswith("--execute") else None,
            "no_network_calls_made",
        ],
        "failed_gates": failed,
        "request_ceiling": request_ceiling,
        "hard_stop_projected_requests": hard_stop_projected_requests,
    }


def _later_execute_command(
    *,
    max_creators: int,
    lookback_hours: int,
    request_ceiling: int,
    hard_stop_projected_requests: int,
) -> str:
    return (
        "./trading_env/bin/python -m research.mtp_research.validation.run_pre_launch_funding_collection "
        f"--creator-limit {max_creators} "
        f"--lookback-hours {lookback_hours} "
        "--max-signature-pages-per-creator 2 "
        "--max-transactions-per-creator 50 "
        "--max-total-transactions 2500 "
        f"--request-ceiling {request_ceiling} "
        f"--hard-stop-projected-requests {hard_stop_projected_requests} "
        "--execute"
    )


def _lookback_profile(lookback_hours: int) -> dict[str, Any]:
    if lookback_hours not in LOOKBACK_PROFILES:
        raise ValueError("lookback_hours must be one of: 1, 6, 24, 168")
    return LOOKBACK_PROFILES[lookback_hours]


def _creator(row: dict[str, Any]) -> str | None:
    metadata = row.get("metadata_json") or {}
    return row.get("creator_deployer") or row.get("creator") or metadata.get("creator_deployer")


def _launch_time(row: dict[str, Any], launch_ts: int) -> str:
    value = row.get("launch_time_utc")
    if value:
        return str(value)
    return datetime.fromtimestamp(launch_ts, tz=timezone.utc).isoformat()


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _read_jsonl(path: Path | str) -> list[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _markdown(report: dict[str, Any]) -> str:
    scope = report["scope"]
    request = report["request_estimate"]
    storage = report["storage_runtime_estimate"]
    stop_go = report["stop_go"]
    lines = [
        "# Pre-Launch Funding Dry-Run Plan",
        "",
        f"- Dry-run classification: `{report['dry_run_classification']}`",
        f"- Selected creators: `{scope['selected_creator_count']}`",
        f"- Launches covered: `{scope['launches_covered_by_selected_creators']}`",
        f"- Lookback window: `{request['lookback_window']}`",
        f"- Base projected requests: `{request['base_projected_requests']}`",
        f"- High projected requests: `{request['high_projected_requests']}`",
        f"- Request ceiling status: `{request['request_ceiling_status']}`",
        f"- Network calls used: `{scope['network_calls_used']}`",
        f"- Helius calls used: `{scope['helius_calls_used']}`",
        "- No network calls were made.",
        "- No thesis, backtest, validation, or trading workflow was run.",
        "",
        "## Selected Creators",
        "",
        "| Creator | Launches | First Launch | Last Launch | Reason |",
        "|---|---:|---|---|---|",
    ]
    for row in report["selected_creators"]:
        lines.append(
            f"| `{row['creator']}` | {row['launch_count_in_strict_cohort']} | "
            f"`{row['first_launch_time']}` | `{row['last_launch_time']}` | `{row['reason_selected']}` |"
        )
    lines.extend(
        [
            "",
            "## Storage And Runtime",
            "",
            f"- Raw JSON estimate MB: `{storage['expected_raw_json_size_mb']}`",
            f"- Parsed parquet estimate MB: `{storage['expected_parsed_parquet_size_mb']}`",
            f"- Runtime estimate minutes: `{storage['expected_runtime_minutes']}`",
            f"- Checkpoint count: `{storage['checkpoint_count']}`",
            f"- Resume behavior: {storage['resume_behavior_needed']}",
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
