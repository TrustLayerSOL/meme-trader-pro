"""Feasibility audit for leakage-safe creator migration reputation fields."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


READINESS_READY = "creator_migration_reputation_ready_for_descriptive_thesis"
READINESS_ALL_COLLECTED_READY = "creator_migration_reputation_ready_for_all_collected_descriptive_thesis"
READINESS_PARTIAL = "creator_migration_reputation_partial_needs_migration_enrichment"
READINESS_BLOCKED = "creator_migration_reputation_blocked"

SAMPLE_COLUMNS = [
    "launch_id",
    "mint",
    "creator",
    "launch_time",
    "creator_prior_launch_count",
    "creator_prior_migration_count",
    "creator_prior_migration_rate",
    "creator_has_4plus_prior_migrations",
    "missing_reason",
]


def build_creator_migration_reputation_report(
    *,
    strict_candidates_path: Path | str,
    all_candidates_path: Path | str,
    events_path: Path | str,
    strict_outcomes_path: Path | str,
    all_outcomes_path: Path | str,
    migration_labels_path: Path | str | None = None,
    sample_limit: int = 100,
) -> dict[str, Any]:
    strict_candidates = _read_jsonl(strict_candidates_path)
    all_candidates = _read_jsonl(all_candidates_path)
    events = _read_jsonl(events_path)
    strict_outcomes = _read_jsonl(strict_outcomes_path)
    all_outcomes = _read_jsonl(all_outcomes_path)
    migration_labels = _read_jsonl(migration_labels_path) if migration_labels_path else []
    candidate_by_mint = {_mint(row): row for row in all_candidates if _mint(row)}
    strict_mints = {_mint(row) for row in strict_candidates if _mint(row)}
    migration_events = _migration_events(events)
    migration_records = _dedupe_migration_records([
        *_migration_records(migration_events, candidate_by_mint),
        *_migration_label_records(migration_labels, candidate_by_mint),
    ])
    strict_rows = _leakage_safe_rows(strict_candidates, migration_records)
    all_rows = _leakage_safe_rows(all_candidates, migration_records)
    observability = _migration_observability(
        strict_candidates=strict_candidates,
        all_candidates=all_candidates,
        events=events,
        migration_events=migration_events,
        migration_records=migration_records,
        strict_outcomes=strict_outcomes,
        all_outcomes=all_outcomes,
        strict_mints=strict_mints,
    )
    derived_summary = _derived_field_summary(strict_rows, all_rows, migration_records)
    computability = _computability(observability, derived_summary)
    readiness = _readiness(observability, derived_summary)
    sample_rows = strict_rows[:sample_limit]
    return {
        "report_id": "creator_migration_reputation_feasibility_v0",
        "scope": {
            "strict_candidates_path": str(strict_candidates_path),
            "all_candidates_path": str(all_candidates_path),
            "events_path": str(events_path),
            "strict_outcomes_path": str(strict_outcomes_path),
            "all_outcomes_path": str(all_outcomes_path),
            "migration_labels_path": str(migration_labels_path) if migration_labels_path else None,
            "strict_launches": len(strict_candidates),
            "all_collected_launches": len(all_candidates),
            "network_calls_used": 0,
            "external_fetches_used": 0,
            "thesis_runs": 0,
            "backtests_run": 0,
            "validation_runs": 0,
        },
        "field_availability": _field_availability(strict_candidates, all_candidates, events, strict_outcomes, all_outcomes),
        "migration_observability": observability,
        "leakage_safe_rule": {
            "same_creator_required": True,
            "migration_timestamp_required": True,
            "strictly_before_current_launch": True,
            "missing_migration_timestamp_counted_as_prior": False,
        },
        "leakage_safe_computability": computability,
        "derived_field_summary": derived_summary,
        "sample_rows": sample_rows,
        "readiness_classification": readiness,
        "t008_creator_migration_reputation_feasible_now": readiness in {READINESS_READY, READINESS_ALL_COLLECTED_READY},
        "t008_strict_regime_feasible_now": readiness == READINESS_READY,
        "t008_all_collected_feasible_now": readiness in {READINESS_READY, READINESS_ALL_COLLECTED_READY},
        "warning_flags": _warning_flags(observability, derived_summary, readiness),
        "next_recommendation": _next_recommendation(readiness),
        "methodology_flags": [
            "feasibility_audit_only",
            "no_external_fetches",
            "no_thesis_cycle",
            "no_backtest",
            "no_validation",
            "no_trading_logic",
            "no_threshold_optimization",
            "no_grid_search",
            "no_ml",
        ],
    }


def write_creator_migration_reputation_outputs(report: dict[str, Any], *, output_dir: Path | str) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "creator_migration_reputation_feasibility.json"
    markdown_path = output / "creator_migration_reputation_feasibility.md"
    sample_csv_path = output / "creator_migration_reputation_sample.csv"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(_markdown(report), encoding="utf-8")
    _write_sample_csv(report["sample_rows"], sample_csv_path)
    return {"json_path": json_path, "markdown_path": markdown_path, "sample_csv_path": sample_csv_path}


def _migration_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row for row in events
        if row.get("venue") == "pumpfun_migrate"
        or "migrate" in " ".join(row.get("metadata_json", {}).get("venue_reasons") or []).lower()
    ]


def _migration_records(
    migration_events: list[dict[str, Any]],
    candidate_by_mint: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    dedup: dict[tuple[str | None, str | None], dict[str, Any]] = {}
    for event in migration_events:
        mint = _mint(event)
        signature = event.get("signature")
        candidate = candidate_by_mint.get(mint or "")
        migration_time = _int_or_none(event.get("block_time"))
        record = {
            "mint": mint,
            "creator": _creator(candidate or {}),
            "migration_time": migration_time,
            "migration_signature": signature,
            "event_count": 1,
            "timestamp_available": migration_time is not None,
            "creator_available": _creator(candidate or {}) is not None,
        }
        key = (mint, signature)
        if key in dedup:
            dedup[key]["event_count"] += 1
            if dedup[key]["migration_time"] is None and migration_time is not None:
                dedup[key]["migration_time"] = migration_time
                dedup[key]["timestamp_available"] = True
        else:
            dedup[key] = record
    return list(dedup.values())


def _migration_label_records(
    labels: list[dict[str, Any]],
    candidate_by_mint: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    records = []
    for label in labels:
        if not (
            label.get("pumpfun_migrate_event_observed")
            or label.get("graduated_to_pumpswap")
            or label.get("migrated_to_raydium")
            or label.get("dex_pair_detected")
        ):
            continue
        mint = _mint(label)
        candidate = candidate_by_mint.get(mint or "")
        creator = label.get("creator") or _creator(candidate or {})
        migration_time = _timestamp_to_int(label.get("migration_time"))
        records.append(
            {
                "mint": mint,
                "creator": creator,
                "migration_time": migration_time,
                "migration_signature": label.get("migration_signature"),
                "event_count": 1,
                "timestamp_available": migration_time is not None,
                "creator_available": creator is not None,
            }
        )
    return records


def _dedupe_migration_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    dedup: dict[tuple[str | None, str | None], dict[str, Any]] = {}
    for record in records:
        key = (record.get("mint"), record.get("migration_signature"))
        if key in dedup:
            dedup[key]["event_count"] += record.get("event_count", 1)
            if dedup[key].get("migration_time") is None and record.get("migration_time") is not None:
                dedup[key]["migration_time"] = record["migration_time"]
                dedup[key]["timestamp_available"] = True
            if not dedup[key].get("creator") and record.get("creator"):
                dedup[key]["creator"] = record["creator"]
                dedup[key]["creator_available"] = True
        else:
            dedup[key] = dict(record)
    return list(dedup.values())


def _leakage_safe_rows(candidates: list[dict[str, Any]], migrations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    migrations_by_creator: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for migration in migrations:
        if migration.get("creator") and migration.get("migration_time") is not None:
            migrations_by_creator[str(migration["creator"])].append(migration)
    for rows in migrations_by_creator.values():
        rows.sort(key=lambda row: (row["migration_time"], row.get("mint") or ""))
    prior_launch_counts: Counter[str] = Counter()
    result = []
    for candidate in sorted(candidates, key=lambda row: (_launch_ts(row) or 0, _mint(row) or "")):
        creator = _creator(candidate)
        launch_ts = _launch_ts(candidate)
        prior_migrations = []
        if creator and launch_ts is not None:
            prior_migrations = [
                migration for migration in migrations_by_creator.get(creator, [])
                if migration["migration_time"] < launch_ts
            ]
        prior_count = len(prior_migrations)
        prior_launch_count = prior_launch_counts[creator] if creator else 0
        prior_rate = (prior_count / prior_launch_count) if prior_launch_count else None
        last_age = (launch_ts - prior_migrations[-1]["migration_time"]) if prior_migrations and launch_ts is not None else None
        missing_reason = _missing_reason(creator, launch_ts, prior_migrations)
        result.append(
            {
                "launch_id": candidate.get("launch_id"),
                "mint": _mint(candidate),
                "creator": creator,
                "launch_time": candidate.get("launch_time_utc") or launch_ts,
                "launch_ts": launch_ts,
                "creator_prior_launch_count": prior_launch_count,
                "creator_prior_migration_count": prior_count,
                "creator_prior_migration_rate": prior_rate,
                "creator_prior_failed_to_migrate_count": max(prior_launch_count - prior_count, 0),
                "creator_prior_last_migration_age_seconds": last_age,
                "creator_has_4plus_prior_migrations": prior_count >= 4,
                "missing_reason": missing_reason,
            }
        )
        if creator:
            prior_launch_counts[creator] += 1
    return result


def _missing_reason(creator: str | None, launch_ts: int | None, prior_migrations: list[dict[str, Any]]) -> str | None:
    if not creator:
        return "creator_missing"
    if launch_ts is None:
        return "launch_time_missing"
    if not prior_migrations:
        return "no_prior_migrations_for_creator"
    return None


def _migration_observability(
    *,
    strict_candidates: list[dict[str, Any]],
    all_candidates: list[dict[str, Any]],
    events: list[dict[str, Any]],
    migration_events: list[dict[str, Any]],
    migration_records: list[dict[str, Any]],
    strict_outcomes: list[dict[str, Any]],
    all_outcomes: list[dict[str, Any]],
    strict_mints: set[str | None],
) -> dict[str, Any]:
    migrated_mints = {_mint(row) for row in migration_records if _mint(row)}
    strict_migrated_mints = {mint for mint in migrated_mints if mint in strict_mints}
    outcome_migration_keys = _migrationish_keys(strict_outcomes + all_outcomes)
    timestamp_available_count = sum(1 for row in migration_records if row.get("timestamp_available"))
    return {
        "strict_total_launches": len(strict_candidates),
        "all_collected_total_launches": len(all_candidates),
        "normalized_event_rows": len(events),
        "pumpfun_migrate_event_rows": len(migration_events),
        "deduped_migration_records": len(migration_records),
        "unique_migrated_mints_observed": len(migrated_mints),
        "strict_unique_migrated_mints_observed": len(strict_migrated_mints),
        "migrated_launches_identifiable_from_events": len(migrated_mints),
        "strict_migrated_launches_identifiable_from_events": len(strict_migrated_mints),
        "migrated_launches_identifiable_from_outcomes": 0,
        "migrated_launches_identifiable_from_other_fields": 0,
        "outcome_migration_like_keys": sorted(outcome_migration_keys),
        "migration_timestamp_available_count": timestamp_available_count,
        "migration_timestamp_missing_count": len(migration_records) - timestamp_available_count,
        "creator_available_for_migrated_launches": sum(1 for row in migration_records if row.get("creator_available")),
        "creator_missing_for_migrated_launches": sum(1 for row in migration_records if not row.get("creator_available")),
    }


def _field_availability(
    strict_candidates: list[dict[str, Any]],
    all_candidates: list[dict[str, Any]],
    events: list[dict[str, Any]],
    strict_outcomes: list[dict[str, Any]],
    all_outcomes: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    return {
        "launch_id": _coverage(strict_candidates, lambda row: row.get("launch_id") is not None),
        "mint": _coverage(strict_candidates, lambda row: _mint(row) is not None),
        "creator_deployer": _coverage(strict_candidates, lambda row: _creator(row) is not None),
        "launch_time": _coverage(strict_candidates, lambda row: _launch_ts(row) is not None),
        "creation_signature": _coverage(strict_candidates, lambda row: _creation_signature(row) is not None),
        "migration_event_classification": _coverage(events, lambda row: row.get("venue") == "pumpfun_migrate"),
        "migration_timestamp": _coverage(_migration_events(events), lambda row: row.get("block_time") is not None),
        "migrated_mint": _coverage(_migration_events(events), lambda row: _mint(row) is not None),
        "migration_signature": _coverage(_migration_events(events), lambda row: row.get("signature") is not None),
        "outcome_migration_label": {
            "available_count": len(_migrationish_keys(strict_outcomes + all_outcomes)),
            "missing_count": len(strict_outcomes) + len(all_outcomes),
            "coverage_pct": 0.0,
            "classification": "unavailable",
        },
        "all_collected_creator_deployer": _coverage(all_candidates, lambda row: _creator(row) is not None),
    }


def _computability(observability: dict[str, Any], derived: dict[str, Any]) -> dict[str, dict[str, str]]:
    base = _base_computability(observability)
    return {
        "creator_prior_migration_count": {"classification": base, "rule": "same creator and migration_time < launch_time"},
        "creator_prior_migration_rate": {"classification": base, "rule": "prior migration count divided by prior launch count"},
        "creator_prior_launch_count": {"classification": "computable_now", "rule": "creator and launch_time are available"},
        "creator_prior_failed_to_migrate_count": {"classification": base, "rule": "prior launch count minus prior migration count"},
        "creator_prior_last_migration_age_seconds": {"classification": base, "rule": "launch_time minus latest prior migration_time"},
        "creator_has_4plus_prior_migrations": {
            "classification": "computable_now" if derived["launches_with_4plus_prior_migrations"] > 0 else "computable_partial",
            "rule": "prior migration count >= 4; currently empty means not testable as a filter",
        },
    }


def _base_computability(observability: dict[str, Any]) -> str:
    if observability["deduped_migration_records"] <= 0:
        return "blocked_missing_migration_labels"
    if observability["migration_timestamp_available_count"] <= 0:
        return "blocked_missing_migration_time"
    if observability["creator_available_for_migrated_launches"] <= 0:
        return "blocked_missing_creator"
    return "computable_now"


def _derived_field_summary(
    strict_rows: list[dict[str, Any]],
    all_rows: list[dict[str, Any]],
    migration_records: list[dict[str, Any]],
) -> dict[str, Any]:
    creators_with_migrations = {row["creator"] for row in migration_records if row.get("creator") and row.get("migration_time") is not None}
    strict_creators_with_prior = {row["creator"] for row in strict_rows if row["creator_prior_migration_count"] > 0}
    all_creators_with_prior = {row["creator"] for row in all_rows if row["creator_prior_migration_count"] > 0}
    return {
        "creators_with_at_least_1_migration_event": len(creators_with_migrations),
        "strict_creators_with_at_least_1_prior_migration": len(strict_creators_with_prior),
        "all_creators_with_at_least_1_prior_migration": len(all_creators_with_prior),
        "strict_launches_with_creator_prior_migration_count_available": len(strict_rows),
        "all_launches_with_creator_prior_migration_count_available": len(all_rows),
        "launches_with_4plus_prior_migrations": sum(1 for row in strict_rows if row["creator_has_4plus_prior_migrations"]),
        "all_launches_with_4plus_prior_migrations": sum(1 for row in all_rows if row["creator_has_4plus_prior_migrations"]),
        "strict_launches_with_at_least_1_prior_migration": sum(1 for row in strict_rows if row["creator_prior_migration_count"] > 0),
        "all_launches_with_at_least_1_prior_migration": sum(1 for row in all_rows if row["creator_prior_migration_count"] > 0),
    }


def _readiness(observability: dict[str, Any], derived: dict[str, Any]) -> str:
    if observability["deduped_migration_records"] <= 0:
        return READINESS_BLOCKED
    if observability["migration_timestamp_available_count"] <= 0 or observability["creator_available_for_migrated_launches"] <= 0:
        return READINESS_BLOCKED
    if derived["launches_with_4plus_prior_migrations"] <= 0:
        if derived["all_launches_with_4plus_prior_migrations"] >= 30 and derived["all_launches_with_at_least_1_prior_migration"] >= 30:
            return READINESS_ALL_COLLECTED_READY
        return READINESS_PARTIAL
    if derived["strict_launches_with_at_least_1_prior_migration"] < 30:
        return READINESS_PARTIAL
    return READINESS_READY


def _warning_flags(observability: dict[str, Any], derived: dict[str, Any], readiness: str) -> list[str]:
    flags = ["feasibility_only", "no_thesis_run"]
    if observability["pumpfun_migrate_event_rows"] <= 2:
        flags.append("migration_events_sparse_likely_undercounted")
    if observability["migrated_launches_identifiable_from_outcomes"] == 0:
        flags.append("outcome_migration_labels_unavailable")
    if derived["launches_with_4plus_prior_migrations"] == 0:
        flags.append("four_plus_prior_migration_filter_empty")
    if readiness == READINESS_ALL_COLLECTED_READY:
        flags.append("strict_regime_four_plus_empty_use_all_collected_only")
    if readiness not in {READINESS_READY, READINESS_ALL_COLLECTED_READY}:
        flags.append("migration_enrichment_needed_before_t008")
    return flags


def _next_recommendation(readiness: str) -> str:
    if readiness == READINESS_READY:
        return "design a descriptive T008 protocol, but do not run it without a separate instruction"
    if readiness == READINESS_ALL_COLLECTED_READY:
        return "design T008 on the all-collected cohort only; keep strict-regime T008 blocked until the 4+ prior migration cohort is non-empty"
    if readiness == READINESS_PARTIAL:
        return "enrich migration/graduation labels beyond the first 120m lifecycle window before T008"
    return "do not pursue creator migration reputation until migration labels with timestamps are available"


def _migrationish_keys(rows: list[dict[str, Any]]) -> set[str]:
    keys = set()
    for row in rows:
        for key in row.keys():
            if "migrat" in key.lower() or "graduat" in key.lower():
                keys.add(key)
        metadata = row.get("metadata_json")
        if isinstance(metadata, dict):
            for key in metadata.keys():
                if "migrat" in key.lower() or "graduat" in key.lower():
                    keys.add(f"metadata_json.{key}")
    return keys


def _coverage(rows: list[dict[str, Any]], predicate) -> dict[str, Any]:
    total = len(rows)
    available = sum(1 for row in rows if predicate(row))
    return {
        "available_count": available,
        "missing_count": total - available,
        "coverage_pct": _pct(available, total),
        "classification": "available" if available == total and total else "partial" if available else "unavailable",
    }


def _write_sample_csv(rows: list[dict[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SAMPLE_COLUMNS)
        writer.writeheader()
        for row in rows[:100]:
            writer.writerow({key: row.get(key) for key in SAMPLE_COLUMNS})


def _markdown(report: dict[str, Any]) -> str:
    obs = report["migration_observability"]
    derived = report["derived_field_summary"]
    lines = [
        "# Creator Migration Reputation Feasibility",
        "",
        f"- Readiness classification: `{report['readiness_classification']}`",
        f"- T008 Creator Migration Reputation feasible now: `{report['t008_creator_migration_reputation_feasible_now']}`",
        f"- T008 strict-regime feasible now: `{report.get('t008_strict_regime_feasible_now')}`",
        f"- T008 all-collected feasible now: `{report.get('t008_all_collected_feasible_now')}`",
        f"- Strict launches: `{obs['strict_total_launches']}`",
        f"- All-collected launches: `{obs['all_collected_total_launches']}`",
        f"- Pump.fun migrate event rows: `{obs['pumpfun_migrate_event_rows']}`",
        f"- Unique migrated mints observed: `{obs['unique_migrated_mints_observed']}`",
        f"- Migration timestamp available count: `{obs['migration_timestamp_available_count']}`",
        f"- Creators with at least 1 migration event: `{derived['creators_with_at_least_1_migration_event']}`",
        f"- Strict launches with 4+ prior migrations: `{derived['launches_with_4plus_prior_migrations']}`",
        "- No thesis cycle was run.",
        "- No backtest, validation, external fetch, or trading workflow was run.",
        "",
        "## Field Availability",
        "",
        "| Field | Classification | Available | Missing | Coverage |",
        "|---|---|---:|---:|---:|",
    ]
    for field, stats in report["field_availability"].items():
        lines.append(
            f"| `{field}` | `{stats['classification']}` | {stats['available_count']} | "
            f"{stats['missing_count']} | {stats['coverage_pct']:.2f}% |"
        )
    lines.extend(["", "## Leakage-Safe Computability", "", "| Field | Classification | Rule |", "|---|---|---|"])
    for field, stats in report["leakage_safe_computability"].items():
        lines.append(f"| `{field}` | `{stats['classification']}` | {stats['rule']} |")
    lines.extend(
        [
            "",
            "## Data Quality Concerns",
            "",
            "- Current migration evidence is sparse and likely undercounted.",
            "- Migration may occur outside the first 120m lifecycle window.",
            "- Outcome rows do not currently expose migration/graduation labels.",
            "- PumpSwap/Raydium migration markers are not joined into creator history.",
            "- Missing migration timestamps are not counted as prior migrations.",
            "",
            "## Next Recommendation",
            "",
            report["next_recommendation"],
        ]
    )
    return "\n".join(lines) + "\n"


def _mint(row: dict[str, Any] | None) -> str | None:
    if not row:
        return None
    return row.get("token_mint") or row.get("mint")


def _creator(row: dict[str, Any]) -> str | None:
    metadata = row.get("metadata_json") or {}
    return row.get("creator_deployer") or row.get("creator") or metadata.get("creator_deployer")


def _creation_signature(row: dict[str, Any]) -> str | None:
    metadata = row.get("metadata_json") or {}
    return row.get("creation_signature") or row.get("signature") or metadata.get("creation_signature")


def _launch_ts(row: dict[str, Any]) -> int | None:
    return _int_or_none(row.get("launch_ts") or row.get("block_time"))


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _timestamp_to_int(value: Any) -> int | None:
    parsed_int = _int_or_none(value)
    if parsed_int is not None:
        return parsed_int
    if not isinstance(value, str) or not value:
        return None
    try:
        return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None


def _pct(count: int, total: int) -> float:
    return (count / total * 100) if total else 0.0


def _read_jsonl(path: Path | str) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    with p.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
