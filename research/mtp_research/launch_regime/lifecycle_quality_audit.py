"""Offline quality audit for launch-relative lifecycle artifacts."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


DEFAULT_REPORT_DIR = Path("data/backtests/diagnostics/reports")


def run_launch_lifecycle_quality_audit(
    *,
    launches_path: Path | str,
    snapshots_path: Path | str,
    outcomes_path: Path | str,
    events_path: Path | str,
    raw_path: Path | str | None = None,
    output_dir: Path | str = DEFAULT_REPORT_DIR,
) -> dict[str, Any]:
    launches = _load_jsonl(Path(launches_path))
    snapshots = _load_jsonl(Path(snapshots_path))
    outcomes = _load_jsonl(Path(outcomes_path))
    events = _load_jsonl(Path(events_path))
    raw_records = _load_jsonl(Path(raw_path)) if raw_path else []

    launch_mints = {row.get("token_mint") for row in launches if row.get("token_mint")}
    snapshot_mints = {row.get("token_mint") for row in snapshots if row.get("token_mint")}
    outcome_mints = {row.get("token_mint") for row in outcomes if row.get("token_mint")}
    event_mints = {row.get("token_mint") for row in events if row.get("token_mint")}

    event_venue_counts = Counter(row.get("venue") or "unknown" for row in events)
    event_classification_counts = Counter(row.get("venue") or "unknown" for row in events)
    launch_venue_counts = Counter(row.get("venue") or "unknown" for row in launches)
    launch_regime_counts = Counter(row.get("launch_regime") or "unknown" for row in launches)
    snapshot_age_counts = Counter(str(row.get("launch_age_seconds")) for row in snapshots)
    program_id_counts = _program_id_counts(events, raw_records)
    top_unknown_instruction_clusters = _top_unknown_instruction_clusters(events, raw_records)
    classification_examples = _classification_examples(events)
    unknown_examples = classification_examples.get("unknown_token_swap_candidate", [])
    per_launch_coverage = _per_launch_classification_coverage(launches, events)

    max_event_age_by_mint = _max_event_age_by_mint(launches, events)
    event_max_age_bucket_counts = Counter(_age_bucket(age) for age in max_event_age_by_mint.values())
    priced_snapshot_count = sum(1 for row in snapshots if _metadata_number(row, "priced_event_count") > 0)
    zero_event_snapshot_count = sum(1 for row in snapshots if _metadata_number(row, "event_count") == 0)
    priced_outcome_count = sum(1 for row in outcomes if _metadata_number(row, "priced_event_count") > 0)
    market_cap_unknown_outcome_count = sum(
        1 for row in outcomes
        if not (row.get("metadata_json") or {}).get("market_cap_available")
    )
    survived_counts = {
        key: sum(1 for row in outcomes if row.get(key))
        for key in ("survived_10m", "survived_30m", "survived_60m", "survived_120m")
    }

    report = {
        "launch_count": len(launches),
        "snapshot_count": len(snapshots),
        "outcome_count": len(outcomes),
        "event_count": len(events),
        "unique_launch_mints": len(launch_mints),
        "unique_snapshot_mints": len(snapshot_mints),
        "unique_outcome_mints": len(outcome_mints),
        "unique_event_mints": len(event_mints),
        "event_venue_counts": dict(sorted(event_venue_counts.items())),
        "event_classification_counts": dict(sorted(event_classification_counts.items())),
        "launch_venue_counts": dict(sorted(launch_venue_counts.items())),
        "launch_regime_counts": dict(sorted(launch_regime_counts.items())),
        "program_id_counts": dict(sorted(program_id_counts.items())),
        "top_unknown_instruction_clusters": top_unknown_instruction_clusters,
        "classification_examples": classification_examples,
        "unknown_examples": unknown_examples,
        "per_launch_event_classification_coverage": per_launch_coverage,
        "snapshot_age_counts": dict(sorted(snapshot_age_counts.items(), key=lambda item: int(item[0]))),
        "priced_snapshot_count": priced_snapshot_count,
        "zero_event_snapshot_count": zero_event_snapshot_count,
        "priced_outcome_count": priced_outcome_count,
        "market_cap_unknown_outcome_count": market_cap_unknown_outcome_count,
        "survived_counts": survived_counts,
        "event_max_age_bucket_counts": dict(sorted(event_max_age_bucket_counts.items())),
        "warning_flags": _warning_flags(
            launch_count=len(launches),
            snapshot_count=len(snapshots),
            outcome_count=len(outcomes),
            event_count=len(events),
            unique_event_mints=len(event_mints),
            unique_launch_mints=len(launch_mints),
            event_venue_counts=event_venue_counts,
            market_cap_unknown_outcome_count=market_cap_unknown_outcome_count,
            survived_counts=survived_counts,
            event_max_age_bucket_counts=event_max_age_bucket_counts,
        ),
        "network_calls": 0,
    }
    _write_reports(report, Path(output_dir))
    return report


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            text = line.strip()
            if text:
                rows.append(json.loads(text))
    return rows


def _max_event_age_by_mint(launches: list[dict[str, Any]], events: list[dict[str, Any]]) -> dict[str, int]:
    launch_ts_by_mint = {
        row["token_mint"]: int(row["launch_ts"])
        for row in launches
        if row.get("token_mint") and row.get("launch_ts") is not None
    }
    max_age: dict[str, int] = {}
    for event in events:
        mint = event.get("token_mint")
        block_time = event.get("block_time")
        if mint not in launch_ts_by_mint or block_time is None:
            continue
        age = int(block_time) - launch_ts_by_mint[mint]
        if age < 0:
            continue
        max_age[mint] = max(max_age.get(mint, 0), age)
    return max_age


def _age_bucket(age: int) -> str:
    if age >= 7200:
        return "gte_120m"
    if age >= 3600:
        return "gte_60m_lt_120m"
    if age >= 1800:
        return "gte_30m_lt_60m"
    if age >= 600:
        return "gte_10m_lt_30m"
    return "lt_10m"


def _metadata_number(row: dict[str, Any], key: str) -> float:
    value = (row.get("metadata_json") or {}).get(key, 0)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _program_id_counts(events: list[dict[str, Any]], raw_records: list[dict[str, Any]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for event in events:
        for program_id in (event.get("metadata_json") or {}).get("venue_matched_program_ids", []) or []:
            counts[str(program_id)] += 1
    if counts:
        return counts
    for record in raw_records:
        counts.update(_program_ids_from_raw_record(record))
    return counts


def _program_ids_from_raw_record(record: dict[str, Any]) -> list[str]:
    raw_json = record.get("raw_json") or {}
    instructions = list((raw_json.get("transaction", {}).get("message", {}).get("instructions") or []))
    for group in (raw_json.get("meta", {}).get("innerInstructions") or []):
        instructions.extend(group.get("instructions") or [])
    output = []
    for instruction in instructions:
        if isinstance(instruction, dict) and instruction.get("programId"):
            output.append(str(instruction["programId"]))
    return output


def _top_unknown_instruction_clusters(
    events: list[dict[str, Any]],
    raw_records: list[dict[str, Any]],
    limit: int = 10,
) -> list[dict[str, Any]]:
    unknown_signatures = {
        event.get("signature")
        for event in events
        if (event.get("venue") or "unknown") in {"unknown", "unknown_token_swap_candidate"}
    }
    by_signature = {record.get("signature"): record for record in raw_records}
    clusters: dict[tuple[str, str, int, str], dict[str, Any]] = {}
    for signature in unknown_signatures:
        record = by_signature.get(signature)
        if not record:
            continue
        raw_json = record.get("raw_json") or {}
        logs = _instruction_log_names(raw_json)
        instructions = list((raw_json.get("transaction", {}).get("message", {}).get("instructions") or []))
        for instruction in instructions:
            if not isinstance(instruction, dict):
                continue
            program_id = str(instruction.get("programId") or "unknown")
            data = instruction.get("data")
            data_prefix = data[:12] if isinstance(data, str) else ""
            account_count = len(instruction.get("accounts") or [])
            log_key = ",".join(logs[:3])
            key = (program_id, data_prefix, account_count, log_key)
            bucket = clusters.setdefault(
                key,
                {
                    "program_id": program_id,
                    "data_prefix": data_prefix,
                    "account_count": account_count,
                    "instruction_logs": logs[:5],
                    "count": 0,
                    "example_signatures": [],
                },
            )
            bucket["count"] += 1
            if len(bucket["example_signatures"]) < 3 and signature:
                bucket["example_signatures"].append(signature)
    return sorted(clusters.values(), key=lambda row: (-row["count"], row["program_id"]))[:limit]


def _instruction_log_names(raw_json: dict[str, Any]) -> list[str]:
    logs = raw_json.get("meta", {}).get("logMessages") or []
    output = []
    for log in logs:
        if isinstance(log, str) and "Instruction:" in log:
            output.append(log.split("Instruction:", 1)[1].strip())
    return output


def _classification_examples(events: list[dict[str, Any]], limit_per_class: int = 3) -> dict[str, list[dict[str, Any]]]:
    output: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        classification = event.get("venue") or "unknown"
        rows = output.setdefault(classification, [])
        if len(rows) < limit_per_class:
            rows.append(
                {
                    "signature": event.get("signature"),
                    "token_mint": event.get("token_mint"),
                    "block_time": event.get("block_time"),
                    "event_type": event.get("event_type"),
                    "side": event.get("side"),
                }
            )
    return dict(sorted(output.items()))


def _per_launch_classification_coverage(
    launches: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> dict[str, int]:
    known_classes = {"pumpfun_create", "pumpfun_buy", "pumpfun_sell", "pumpfun_migrate", "pumpswap_trade", "raydium_trade"}
    classifications_by_mint: dict[str, set[str]] = {}
    for event in events:
        mint = event.get("token_mint")
        if mint:
            classifications_by_mint.setdefault(mint, set()).add(event.get("venue") or "unknown")
    launches_with_known = 0
    launches_unknown_only = 0
    launches_without_events = 0
    for launch in launches:
        mint = launch.get("token_mint")
        classes = classifications_by_mint.get(mint or "")
        if not classes:
            launches_without_events += 1
        elif classes & known_classes:
            launches_with_known += 1
        else:
            launches_unknown_only += 1
    return {
        "launches_with_known_classification": launches_with_known,
        "launches_unknown_only": launches_unknown_only,
        "launches_without_events": launches_without_events,
    }


def _warning_flags(
    *,
    launch_count: int,
    snapshot_count: int,
    outcome_count: int,
    event_count: int,
    unique_event_mints: int,
    unique_launch_mints: int,
    event_venue_counts: Counter[str],
    market_cap_unknown_outcome_count: int,
    survived_counts: dict[str, int],
    event_max_age_bucket_counts: Counter[str],
) -> list[str]:
    warnings: list[str] = []
    if launch_count == 0:
        warnings.append("no_launches")
    if snapshot_count == 0:
        warnings.append("no_snapshots")
    if outcome_count == 0:
        warnings.append("no_outcomes")
    if event_count == 0:
        warnings.append("no_events")
    if unique_launch_mints and unique_event_mints < unique_launch_mints:
        warnings.append("event_mint_coverage_below_launch_count")
    unknown_events = event_venue_counts.get("unknown", 0) + event_venue_counts.get("unknown_token_swap_candidate", 0)
    if event_count and unknown_events / event_count >= 0.8:
        warnings.append("unknown_event_venue_dominant")
    if outcome_count and market_cap_unknown_outcome_count / outcome_count >= 0.8:
        warnings.append("market_cap_unavailable_for_threshold_outcomes")
    if outcome_count and survived_counts.get("survived_120m", 0) == 0 and event_max_age_bucket_counts.get("gte_120m", 0):
        warnings.append("survived_120m_label_mismatch_with_event_age")
    if outcome_count and survived_counts.get("survived_120m", 0) == 0:
        warnings.append("survived_120m_zero_requires_review")
    return warnings


def _write_reports(report: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "launch_lifecycle_quality_audit.json"
    md_path = output_dir / "launch_lifecycle_quality_audit.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(_markdown(report), encoding="utf-8")


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Launch Lifecycle Quality Audit",
        "",
        "Offline diagnostic report only. This does not run backtests, validation, paper trading, or live trading.",
        "",
        f"- launches: `{report['launch_count']}`",
        f"- snapshots: `{report['snapshot_count']}`",
        f"- outcomes: `{report['outcome_count']}`",
        f"- events: `{report['event_count']}`",
        f"- unique_event_mints: `{report['unique_event_mints']}`",
        f"- priced_snapshot_count: `{report['priced_snapshot_count']}`",
        f"- market_cap_unknown_outcome_count: `{report['market_cap_unknown_outcome_count']}`",
        f"- per_launch_event_classification_coverage: `{report['per_launch_event_classification_coverage']}`",
        f"- warning_flags: `{report['warning_flags']}`",
        f"- network_calls: `{report['network_calls']}`",
        "",
        "## Event Classifications",
        _format_counts(report["event_classification_counts"]),
        "",
        "## Event Venues",
        _format_counts(report["event_venue_counts"]),
        "",
        "## Program IDs",
        _format_counts(report["program_id_counts"]),
        "",
        "## Launch Regimes",
        _format_counts(report["launch_regime_counts"]),
        "",
        "## Survival Counts",
        _format_counts(report["survived_counts"]),
        "",
        "## Event Max Age Buckets",
        _format_counts(report["event_max_age_bucket_counts"]),
        "",
        "## Top Unknown Instruction Clusters",
        _format_unknown_clusters(report["top_unknown_instruction_clusters"]),
        "",
    ]
    return "\n".join(lines)


def _format_counts(counts: dict[str, int]) -> str:
    if not counts:
        return "- none"
    return "\n".join(f"- {key}: {value}" for key, value in sorted(counts.items()))


def _format_unknown_clusters(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "- none"
    return "\n".join(
        "- "
        f"program_id={row['program_id']} "
        f"data_prefix={row['data_prefix']} "
        f"account_count={row['account_count']} "
        f"count={row['count']} "
        f"logs={row['instruction_logs']} "
        f"examples={row['example_signatures']}"
        for row in rows
    )
