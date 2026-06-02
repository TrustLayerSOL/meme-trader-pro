"""Strict-cohort holder-state rollout from normalized lifecycle event deltas."""

from __future__ import annotations

import json
import time
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
from typing import Any

from research.mtp_research.validation.holder_state_pilot import (
    HOLDER_DISTRIBUTION_SOURCE,
    HOLDER_SNAPSHOT_AGES,
)


SNAPSHOT_LABELS = {
    30: "30s",
    180: "3m",
    600: "10m",
    1800: "30m",
    7200: "120m",
}
READINESS_READY = "holder_state_ready_for_T001_T002_v2"
READINESS_PARTIAL = "holder_state_partial_needs_review"
READINESS_BLOCKED = "holder_state_blocked"
SYSTEM_PROGRAM = "11111111111111111111111111111111"
TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
ASSOCIATED_TOKEN_PROGRAM = "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTnHQuwwXQf"
PUMP_FUN_PROGRAM_ID = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
KNOWN_PROGRAM_ACCOUNTS = {SYSTEM_PROGRAM, TOKEN_PROGRAM, ASSOCIATED_TOKEN_PROGRAM, PUMP_FUN_PROGRAM_ID}


def build_holder_state_rollout(
    *,
    candidates_path: Path | str,
    events_path: Path | str,
    max_launches: int | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    candidates = _select_candidates(_read_jsonl(candidates_path), max_launches=max_launches)
    events_by_mint = _events_by_mint(_read_jsonl(events_path), {row["token_mint"] for row in candidates})
    holder_snapshots: list[dict[str, Any]] = []
    negative_balance_events: list[dict[str, Any]] = []
    balance_warnings: list[dict[str, Any]] = []
    exclusion_events: list[dict[str, Any]] = []
    sell_without_prior_events: list[dict[str, Any]] = []
    duplicate_events: list[dict[str, Any]] = []
    for candidate in candidates:
        snapshots, negatives, warnings, exclusions, sells_without_prior, duplicates = _build_launch_snapshots(
            candidate,
            events_by_mint.get(candidate["token_mint"], []),
        )
        holder_snapshots.extend(snapshots)
        negative_balance_events.extend(negatives)
        balance_warnings.extend(warnings)
        exclusion_events.extend(exclusions)
        sell_without_prior_events.extend(sells_without_prior)
        duplicate_events.extend(duplicates)

    expected = len(candidates) * len(HOLDER_SNAPSHOT_AGES)
    built = sum(1 for row in holder_snapshots if row["holder_count"] is not None)
    snapshots_with_holder_values = sum(1 for row in holder_snapshots if (row["holder_count"] or 0) > 0)
    valid_zero_holder_snapshots = sum(1 for row in holder_snapshots if row.get("holder_snapshot_confidence") == "valid_zero")
    insufficient_prior_state_snapshots = sum(1 for row in holder_snapshots if row.get("holder_snapshot_missing_reason") == "insufficient_prior_state")
    missing_event_data_snapshots = sum(1 for row in holder_snapshots if row.get("holder_snapshot_missing_reason") == "missing_event_data")
    ambiguous_event_only_snapshots = sum(1 for row in holder_snapshots if row.get("holder_snapshot_missing_reason") == "ambiguous_event_only")
    missing = expected - built
    field_coverage = {
        "holder_count": _field_coverage(holder_snapshots, "holder_count", expected),
        "top_holder_share": _field_coverage(holder_snapshots, "top_holder_share", expected),
        "top_10_holder_share": _field_coverage(holder_snapshots, "top_10_holder_share", expected),
        "creator_holder_share": _field_coverage(holder_snapshots, "creator_holder_share", expected),
    }
    known_creator_rows = [
        row for row in holder_snapshots if row.get("creator_wallet") and row.get("holder_count") is not None
    ]
    missing_known_creator_share = sum(1 for row in known_creator_rows if row.get("creator_holder_share") is None)
    readiness = _readiness_classification(
        snapshot_coverage=field_coverage["holder_count"]["coverage_pct"],
        suspicious_negative_balance_count=len(negative_balance_events),
        insufficient_prior_state_pct=_pct(insufficient_prior_state_snapshots, expected),
        missing_known_creator_share=missing_known_creator_share,
        caveat_present=True,
    )
    sell_without_prior_unique_launches = len({row["launch_id"] for row in sell_without_prior_events})
    sell_without_prior_unique_mints = len({row["mint"] for row in sell_without_prior_events})
    runtime_seconds = time.perf_counter() - started
    return {
        "rollout_id": "strict_cohort_holder_state_rollout_v0",
        "scope": "data_enrichment_rollout_only",
        "methodology_flags": [
            "research_only",
            "data_enrichment_only",
            "no_thesis_rerun",
            "no_backtest",
            "no_walk_forward_validation",
            "no_trading_logic",
            "no_threshold_optimization",
            "no_grid_search",
            "no_ml_black_boxes",
            "observed_delta_replay_not_full_chain_state",
        ],
        "snapshot_ages_seconds": HOLDER_SNAPSHOT_AGES,
        "launches_attempted": len(candidates),
        "launches_completed": len({row["launch_id"] for row in holder_snapshots if row["holder_count"] is not None}),
        "launches_failed": len(candidates) - len({row["launch_id"] for row in holder_snapshots if row["holder_count"] is not None}),
        "snapshots_expected": expected,
        "snapshot_rows_written": len(holder_snapshots),
        "snapshots_built": built,
        "snapshots_with_holder_values": snapshots_with_holder_values,
        "valid_zero_holder_snapshots": valid_zero_holder_snapshots,
        "insufficient_prior_state_snapshots": insufficient_prior_state_snapshots,
        "missing_event_data_snapshots": missing_event_data_snapshots,
        "ambiguous_event_only_snapshots": ambiguous_event_only_snapshots,
        "missing_snapshots": missing,
        "field_coverage": field_coverage,
        "holder_count_coverage_pct": field_coverage["holder_count"]["coverage_pct"],
        "top_holder_share_coverage_pct": field_coverage["top_holder_share"]["coverage_pct"],
        "top_10_holder_share_coverage_pct": field_coverage["top_10_holder_share"]["coverage_pct"],
        "creator_holder_share_coverage_pct": field_coverage["creator_holder_share"]["coverage_pct"],
        "confidence_distribution": dict(sorted(Counter(row["holder_snapshot_confidence"] for row in holder_snapshots).items())),
        "missing_reason_counts": _missing_reason_counts(holder_snapshots),
        "zero_holder_snapshots": sum(1 for row in holder_snapshots if row["holder_count"] in (None, 0)),
        "suspicious_negative_balance_count": len(negative_balance_events),
        "suspicious_negative_balance_examples": negative_balance_events[:10],
        "excluded_ambiguous_event_count": sum(1 for row in exclusion_events if row["excluded_event_reason"] == "ambiguous_swap_direction"),
        "excluded_program_pool_account_event_count": sum(
            1
            for row in exclusion_events
            if row["excluded_event_reason"] in {"program_account_excluded", "bonding_curve_account_excluded", "pool_account_excluded"}
        ),
        "excluded_event_reason_counts": dict(sorted(Counter(row["excluded_event_reason"] for row in exclusion_events).items())),
        "excluded_event_examples": exclusion_events[:20],
        "sell_without_prior_observed_balance_count": len(sell_without_prior_events),
        "sell_without_prior_observed_balance_unique_launches": sell_without_prior_unique_launches,
        "sell_without_prior_observed_balance_unique_mints": sell_without_prior_unique_mints,
        "sell_without_prior_observed_balance_examples": sell_without_prior_events[:20],
        "sell_without_prior_observed_balance_all": sell_without_prior_events,
        "duplicate_event_skipped_count": len(duplicate_events),
        "duplicate_event_examples": duplicate_events[:20],
        "balance_conservation_warnings": balance_warnings[:20],
        "balance_conservation_warning_count": len(balance_warnings),
        "share_distribution": {
            "top_holder_share": _distribution(row.get("top_holder_share") for row in holder_snapshots),
            "top_10_holder_share": _distribution(row.get("top_10_holder_share") for row in holder_snapshots),
            "creator_holder_share": _distribution(row.get("creator_holder_share") for row in holder_snapshots),
        },
        "examples": {
            "high_concentration_launches": _example_launches(holder_snapshots, reverse=True),
            "low_concentration_launches": _example_launches(holder_snapshots, reverse=False),
        },
        "runtime_seconds": runtime_seconds,
        "storage_size": {},
        "api_calls_used": 0,
        "helius_credits_used": 0,
        "readiness_classification": readiness,
        "readiness_criteria": {
            "min_snapshot_coverage_pct": 95.0,
            "max_insufficient_prior_state_pct": 5.0,
            "snapshot_coverage_pass": field_coverage["holder_count"]["coverage_pct"] >= 95.0,
            "insufficient_prior_state_pct": _pct(insufficient_prior_state_snapshots, expected),
            "insufficient_prior_state_pass": _pct(insufficient_prior_state_snapshots, expected) <= 5.0,
            "no_unexplained_negative_balances": len(negative_balance_events) == 0,
            "negative_balances_eliminated_or_classified": len(negative_balance_events) == 0,
            "program_pool_bonding_curve_accounts_excluded": True,
            "no_missing_creator_share_for_known_creator": missing_known_creator_share == 0,
            "observed_delta_replay_caveat_present": True,
        },
        "is_confirmed_full_chain_snapshot": False,
        "caveat": (
            "Holder-state rows are observed delta replay snapshots reconstructed from normalized lifecycle events; "
            "they are not confirmed full-chain account-state snapshots."
        ),
        "t001_v2_feasible": readiness == READINESS_READY,
        "t002_v2_feasible": readiness == READINESS_READY,
        "holder_snapshots": holder_snapshots,
    }


def write_holder_state_rollout_outputs(
    rollout: dict[str, Any],
    *,
    dataset_dir: Path | str,
    report_dir: Path | str,
) -> dict[str, Path]:
    dataset = Path(dataset_dir)
    reports = Path(report_dir)
    dataset.mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)
    jsonl_path = dataset / "strict_cohort_holder_state_snapshots.jsonl"
    parquet_path = dataset / "strict_cohort_holder_state_snapshots.parquet"
    audit_json_path = reports / "holder_state_strict_cohort_audit.json"
    audit_markdown_path = reports / "holder_state_strict_cohort_audit.md"

    with jsonl_path.open("w", encoding="utf-8") as f:
        for row in rollout["holder_snapshots"]:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    _write_parquet(rollout["holder_snapshots"], parquet_path)
    rollout["storage_size"] = {
        "jsonl_bytes": jsonl_path.stat().st_size,
        "parquet_bytes": parquet_path.stat().st_size,
    }
    audit_json_path.write_text(json.dumps(_audit_report(rollout), indent=2, sort_keys=True), encoding="utf-8")
    audit_markdown_path.write_text(_audit_markdown(rollout), encoding="utf-8")
    return {
        "jsonl_path": jsonl_path,
        "parquet_path": parquet_path,
        "audit_json_path": audit_json_path,
        "audit_markdown_path": audit_markdown_path,
    }


def write_missing_coverage_diagnostics(
    diagnostics: dict[str, Any],
    *,
    output_dir: Path | str,
) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "holder_state_missing_coverage_diagnostics.json"
    markdown_path = output / "holder_state_missing_coverage_diagnostics.md"
    sell_json_path = output / "holder_state_sell_without_prior_diagnostics.json"
    sell_markdown_path = output / "holder_state_sell_without_prior_diagnostics.md"
    json_path.write_text(json.dumps(diagnostics["missing_coverage"], indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(_missing_coverage_markdown(diagnostics["missing_coverage"]), encoding="utf-8")
    sell_json_path.write_text(json.dumps(diagnostics["sell_without_prior"], indent=2, sort_keys=True), encoding="utf-8")
    sell_markdown_path.write_text(_sell_without_prior_markdown(diagnostics["sell_without_prior"]), encoding="utf-8")
    return {
        "missing_coverage_json_path": json_path,
        "missing_coverage_markdown_path": markdown_path,
        "sell_without_prior_json_path": sell_json_path,
        "sell_without_prior_markdown_path": sell_markdown_path,
    }


def build_missing_coverage_diagnostics(
    *,
    candidates_path: Path | str,
    events_path: Path | str,
    rollout: dict[str, Any],
    max_launches: int | None = None,
) -> dict[str, Any]:
    candidates = _select_candidates(_read_jsonl(candidates_path), max_launches=max_launches)
    candidates_by_launch = {row["launch_id"]: row for row in candidates}
    events_by_mint = _events_by_mint(_read_jsonl(events_path), {row["token_mint"] for row in candidates})
    snapshots = rollout["holder_snapshots"]
    missing = [row for row in snapshots if row.get("holder_count") is None]
    by_launch = Counter(row["launch_id"] for row in missing)
    launch_diagnostics = [
        _launch_coverage_diagnostic(candidate, events_by_mint.get(candidate["token_mint"], []), snapshots)
        for candidate in candidates
    ]
    sell_events = list(rollout.get("sell_without_prior_observed_balance_examples") or [])
    # Include all classified sell-without-prior events when available from rollout internals.
    sell_events = rollout.get("sell_without_prior_observed_balance_all") or sell_events
    sell_diagnostics = _sell_without_prior_diagnostics(candidates_by_launch, events_by_mint, sell_events)
    return {
        "missing_coverage": {
            "report_id": "holder_state_missing_coverage_diagnostics_v0",
            "scope": "diagnostic_only",
            "total_missing_holder_value_snapshots": len(missing),
            "missing_snapshots_by_snapshot_window": _counter_dict(row.get("snapshot_label") for row in missing),
            "missing_snapshots_by_launch": _top_counts((row["launch_id"] for row in missing), limit=50),
            "launches_with_all_snapshots_missing": [
                launch_id for launch_id, count in sorted(by_launch.items()) if count == len(HOLDER_SNAPSHOT_AGES)
            ],
            "launches_with_early_present_later_missing": [
                item["launch_id"] for item in launch_diagnostics if item["early_present_later_missing"]
            ],
            "launches_with_later_present_early_missing": [
                item["launch_id"] for item in launch_diagnostics if item["later_present_early_missing"]
            ],
            "missing_reason_counts": _counter_dict(row.get("holder_snapshot_missing_reason") for row in missing),
            "snapshot_state_counts": _counter_dict(row.get("holder_snapshot_state") for row in snapshots),
            "launch_diagnostics_examples": launch_diagnostics[:50],
        },
        "sell_without_prior": sell_diagnostics,
    }


def build_negative_balance_diagnostics(
    *,
    candidates_path: Path | str,
    events_path: Path | str,
    max_launches: int | None = None,
) -> dict[str, Any]:
    """Summarize the legacy negative-balance failure mode before repaired replay rules."""
    candidates = _select_candidates(_read_jsonl(candidates_path), max_launches=max_launches)
    events_by_mint = _events_by_mint(_read_jsonl(events_path), {row["token_mint"] for row in candidates})
    negative_events: list[dict[str, Any]] = []
    duplicate_keys: Counter[tuple[str | None, str | None]] = Counter()
    for candidate in candidates:
        balances: dict[str, float] = {}
        positive_seen: set[str] = set()
        for event in events_by_mint.get(candidate["token_mint"], []):
            duplicate_keys[(event.get("signature"), event.get("event_id"))] += 1
            actor = event.get("actor")
            delta = _event_balance_delta(event)
            if not actor or delta is None:
                continue
            actor = str(actor)
            before = balances.get(actor, 0.0)
            after = before + delta
            if after < -1e-9:
                negative_events.append({
                    "launch_id": candidate["launch_id"],
                    "mint": candidate["token_mint"],
                    "signature": event.get("signature"),
                    "event_id": event.get("event_id"),
                    "block_time": event.get("block_time"),
                    "snapshot_window": _snapshot_window(candidate, event),
                    "classification": _event_classification(event),
                    "event_type": event.get("event_type"),
                    "venue": event.get("venue"),
                    "source": event.get("source"),
                    "actor": actor,
                    "actor_role": _actor_role(candidate, actor),
                    "base_qty": event.get("base_qty"),
                    "balance_before": before,
                    "delta": delta,
                    "balance_after": after,
                    "appears_before_positive_balance_seed": actor not in positive_seen,
                    "metadata_reasons": (event.get("metadata_json") or {}).get("reasons") or [],
                })
                after = 0.0
            balances[actor] = after
            if delta > 0:
                positive_seen.add(actor)
            if balances.get(actor, 0.0) <= 0:
                balances.pop(actor, None)

    duplicated = {key: count for key, count in duplicate_keys.items() if count > 1}
    first_by_launch: dict[str, dict[str, Any]] = {}
    for event in negative_events:
        first_by_launch.setdefault(event["launch_id"], event)
    return {
        "report_id": "holder_state_negative_balance_diagnostics_v0",
        "scope": "diagnostic_only",
        "total_negative_balance_events": len(negative_events),
        "unique_launches_affected": len({row["launch_id"] for row in negative_events}),
        "unique_mints_affected": len({row["mint"] for row in negative_events}),
        "negative_events_by_classification": _counter_dict(row["classification"] for row in negative_events),
        "negative_events_by_snapshot_window": _counter_dict(row["snapshot_window"] for row in negative_events),
        "negative_events_by_actor_role": _counter_dict(row["actor_role"] for row in negative_events),
        "negative_events_by_source": _counter_dict(row["source"] for row in negative_events),
        "top_repeated_negative_actors": _top_counts(row["actor"] for row in negative_events),
        "top_repeated_negative_mints": _top_counts(row["mint"] for row in negative_events),
        "before_positive_balance_seed_count": sum(1 for row in negative_events if row["appears_before_positive_balance_seed"]),
        "duplicate_event_signature_instruction_count": len(duplicated),
        "duplicate_event_signature_instruction_examples": [
            {"signature": key[0], "event_id": key[1], "count": count}
            for key, count in list(duplicated.items())[:20]
        ],
        "first_negative_event_per_affected_launch": list(first_by_launch.values())[:50],
        "negative_balance_event_examples": negative_events[:50],
    }


def write_negative_balance_diagnostics(
    diagnostics: dict[str, Any],
    *,
    output_dir: Path | str,
) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "negative_balance_diagnostics.json"
    markdown_path = output / "negative_balance_diagnostics.md"
    json_path.write_text(json.dumps(diagnostics, indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(_negative_balance_markdown(diagnostics), encoding="utf-8")
    return {"negative_balance_json_path": json_path, "negative_balance_markdown_path": markdown_path}


def _select_candidates(rows: list[dict[str, Any]], max_launches: int | None = None) -> list[dict[str, Any]]:
    eligible = [row for row in rows if row.get("launch_id") and row.get("token_mint") and row.get("launch_ts")]
    ordered = sorted(eligible, key=lambda row: (int(row["launch_ts"]), row["token_mint"]))
    if max_launches is not None:
        return ordered[:max(0, int(max_launches))]
    return ordered


def _event_classification(event: dict[str, Any]) -> str:
    venue = str(event.get("venue") or "")
    event_type = str(event.get("event_type") or "")
    for label in ["pumpfun_buy", "pumpfun_sell", "pumpfun_swap", "pumpfun_create", "pumpfun_migrate"]:
        if venue == label or event_type == label:
            return label
    return "other"


def _snapshot_window(candidate: dict[str, Any], event: dict[str, Any]) -> str:
    block_time = event.get("block_time")
    if block_time is None:
        return "missing_block_time"
    age = int(block_time) - int(candidate["launch_ts"])
    for snapshot_age in HOLDER_SNAPSHOT_AGES:
        if age <= snapshot_age:
            return SNAPSHOT_LABELS[snapshot_age]
    return "after_120m"


def _counter_dict(values) -> dict[str, int]:
    return dict(sorted(Counter(str(value) for value in values).items()))


def _top_counts(values, limit: int = 15) -> list[dict[str, Any]]:
    return [{"value": value, "count": count} for value, count in Counter(str(value) for value in values).most_common(limit)]


def _launch_coverage_diagnostic(
    candidate: dict[str, Any],
    events: list[dict[str, Any]],
    snapshots: list[dict[str, Any]],
) -> dict[str, Any]:
    launch_id = candidate["launch_id"]
    mint = candidate["token_mint"]
    launch_ts = int(candidate["launch_ts"])
    launch_snapshots = [row for row in snapshots if row["launch_id"] == launch_id]
    missing = [row for row in launch_snapshots if row.get("holder_count") is None]
    present_labels = {row["snapshot_label"] for row in launch_snapshots if row.get("holder_count") is not None}
    missing_labels = {row["snapshot_label"] for row in missing}
    first_event = min((int(row["block_time"]) for row in events if row.get("block_time") is not None), default=None)
    first_human_buy = min(
        (
            int(row["block_time"])
            for row in events
            if row.get("block_time") is not None
            and not _event_exclusion_reason(candidate, row)
            and (_event_balance_delta(row) or 0) > 0
        ),
        default=None,
    )
    first_sell_without_prior = min(
        (
            int(row["snapshot_time"])
            for row in missing
            if row.get("holder_snapshot_missing_reason") == "insufficient_prior_state"
        ),
        default=None,
    )
    deterministic_human_events = [
        row for row in events if row.get("block_time") is not None and not _event_exclusion_reason(candidate, row) and _event_balance_delta(row) is not None
    ]
    excluded_events = [row for row in events if _event_exclusion_reason(candidate, row)]
    ambiguous_events = [row for row in events if _event_exclusion_reason(candidate, row) == "ambiguous_swap_direction"]
    return {
        "launch_id": launch_id,
        "mint": mint,
        "missing_snapshot_count": len(missing),
        "missing_snapshot_labels": sorted(missing_labels),
        "present_snapshot_labels": sorted(present_labels),
        "early_present_later_missing": bool({"30s", "3m"} & present_labels and {"30m", "120m"} & missing_labels),
        "later_present_early_missing": bool({"30s", "3m"} & missing_labels and {"30m", "120m"} & present_labels),
        "first_event_age_seconds": (first_event - launch_ts) if first_event is not None else None,
        "first_deterministic_human_holder_buy_age_seconds": (first_human_buy - launch_ts) if first_human_buy is not None else None,
        "first_sell_without_prior_age_seconds": (first_sell_without_prior - launch_ts) if first_sell_without_prior is not None else None,
        "creator_seed_exists": False,
        "mint_seed_exists": False,
        "only_excluded_program_pool_events": bool(events and excluded_events and len(excluded_events) == len(events)),
        "only_ambiguous_swaps": bool(events and ambiguous_events and len(ambiguous_events) == len(events)),
        "no_deterministic_human_holder_events": len(deterministic_human_events) == 0,
    }


def _sell_without_prior_diagnostics(
    candidates_by_launch: dict[str, dict[str, Any]],
    events_by_mint: dict[str, list[dict[str, Any]]],
    sell_events: list[dict[str, Any]],
) -> dict[str, Any]:
    enriched: list[dict[str, Any]] = []
    for event in sell_events:
        candidate = candidates_by_launch.get(event["launch_id"])
        events = events_by_mint.get(event["mint"], []) if candidate else []
        actor = event.get("actor")
        event_time = event.get("block_time")
        prior_events = [
            row for row in events
            if row.get("actor") == actor
            and row.get("block_time") is not None
            and event_time is not None
            and int(row["block_time"]) < int(event_time)
        ]
        actor_prior_positive = any((_event_balance_delta(row) or 0) > 0 for row in prior_events)
        first_buy_time = min(
            (
                int(row["block_time"])
                for row in events
                if candidate
                and row.get("block_time") is not None
                and not _event_exclusion_reason(candidate, row)
                and (_event_balance_delta(row) or 0) > 0
            ),
            default=None,
        )
        enriched.append({
            **event,
            "actor_has_any_prior_buy_in_normalized_events": actor_prior_positive,
            "actor_has_any_prior_token_positive_delta": actor_prior_positive,
            "actor_is_creator": bool(candidate and _actor_role(candidate, actor) == "creator"),
            "actor_is_excluded_program_pool_bonding_curve": bool(candidate and _actor_role(candidate, actor) in {"bonding_curve", "associated_bonding_curve", "pool_address", "program_account", "mint_account"}),
            "actor_appears_in_create_or_init_accounts": bool(candidate and actor in {
                _creator_wallet(candidate),
                (candidate.get("metadata_json") or {}).get("bonding_curve"),
                (candidate.get("metadata_json") or {}).get("associated_bonding_curve"),
                candidate.get("pool_address"),
                candidate.get("token_mint"),
            }),
            "sells_before_first_deterministic_buy_in_launch_window": bool(
                event_time is not None and first_buy_time is not None and int(event_time) < first_buy_time
            ),
        })
    return {
        "report_id": "holder_state_sell_without_prior_diagnostics_v0",
        "scope": "diagnostic_only",
        "sell_without_prior_count": len(sell_events),
        "sell_without_prior_count_by_launch": _top_counts((row["launch_id"] for row in sell_events), limit=50),
        "sell_without_prior_count_by_actor": _top_counts((row.get("actor") for row in sell_events), limit=50),
        "sell_without_prior_count_by_snapshot_window": _counter_dict(row.get("snapshot_window") for row in sell_events),
        "event_age_seconds_distribution": _distribution(row.get("event_age_seconds") for row in sell_events),
        "actor_prior_buy_count": sum(1 for row in enriched if row["actor_has_any_prior_buy_in_normalized_events"]),
        "actor_prior_positive_delta_count": sum(1 for row in enriched if row["actor_has_any_prior_token_positive_delta"]),
        "actor_is_creator_count": sum(1 for row in enriched if row["actor_is_creator"]),
        "actor_is_excluded_program_pool_bonding_curve_count": sum(1 for row in enriched if row["actor_is_excluded_program_pool_bonding_curve"]),
        "actor_appears_in_create_or_init_accounts_count": sum(1 for row in enriched if row["actor_appears_in_create_or_init_accounts"]),
        "sells_before_first_deterministic_buy_in_launch_window_count": sum(1 for row in enriched if row["sells_before_first_deterministic_buy_in_launch_window"]),
        "examples": enriched[:50],
    }


def _events_by_mint(rows: list[dict[str, Any]], mints: set[str]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        mint = row.get("token_mint")
        if mint in mints:
            grouped[mint].append(row)
    return {
        mint: sorted(events, key=lambda row: (int(row.get("block_time") or 0), row.get("signature") or ""))
        for mint, events in grouped.items()
    }


def _build_launch_snapshots(
    candidate: dict[str, Any],
    events: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    launch_ts = int(candidate["launch_ts"])
    balances: dict[str, float] = {}
    previous_holders: set[str] | None = None
    event_index = 0
    negatives: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    sells_without_prior: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []
    snapshots: list[dict[str, Any]] = []
    observed_count = 0
    deterministic_human_event_count = 0
    human_positive_event_count = 0
    ambiguous_event_count = 0
    excluded_program_event_count = 0
    sell_without_prior_count = 0
    seen_event_keys: set[tuple[str | None, str | None]] = set()
    for age in HOLDER_SNAPSHOT_AGES:
        snapshot_ts = launch_ts + age
        while event_index < len(events) and int(events[event_index].get("block_time") or 0) <= snapshot_ts:
            event = events[event_index]
            event_key = (event.get("signature"), event.get("event_id"))
            if event_key in seen_event_keys:
                duplicates.append(_excluded_event(candidate, event, "duplicate_event_skipped"))
                event_index += 1
                continue
            seen_event_keys.add(event_key)
            actor = event.get("actor")
            exclusion_reason = _event_exclusion_reason(candidate, event)
            if exclusion_reason:
                exclusions.append(_excluded_event(candidate, event, exclusion_reason))
                if exclusion_reason == "ambiguous_swap_direction":
                    ambiguous_event_count += 1
                if exclusion_reason in {"program_account_excluded", "bonding_curve_account_excluded", "pool_account_excluded"}:
                    excluded_program_event_count += 1
                observed_count += 1
                event_index += 1
                continue
            delta = _event_balance_delta(event)
            if actor and delta is not None:
                deterministic_human_event_count += 1
                before = balances.get(str(actor), 0.0)
                after = before + delta
                if after < -1e-9:
                    reason = "sell_without_prior_observed_balance" if before <= 0 else "insufficient_prior_state"
                    sell_without_prior_count += 1
                    sells_without_prior.append({
                        "launch_id": candidate["launch_id"],
                        "mint": candidate["token_mint"],
                        "actor": str(actor),
                        "signature": event.get("signature"),
                        "block_time": event.get("block_time"),
                        "event_age_seconds": (int(event["block_time"]) - launch_ts) if event.get("block_time") is not None else None,
                        "snapshot_window": _snapshot_window(candidate, event),
                        "event_type": event.get("event_type"),
                        "venue": event.get("venue"),
                        "actor_role": _actor_role(candidate, actor),
                        "actor_had_prior_observed_buy": before > 0,
                        "actor_had_prior_token_positive_delta": before > 0,
                        "balance_before": before,
                        "delta": delta,
                        "balance_after": after,
                        "negative_balance_reason": reason,
                        "raw_pre_clamp_balance": before,
                        "negative_balance_flag": True,
                    })
                    after = 0.0
                elif delta > 0:
                    human_positive_event_count += 1
                balances[str(actor)] = after
                if balances[str(actor)] <= 0:
                    balances.pop(str(actor), None)
            observed_count += 1
            event_index += 1
        snapshot = _snapshot_row(
            candidate,
            age,
            snapshot_ts,
            balances,
            previous_holders,
            observed_count,
            total_event_count=len(events),
            deterministic_human_event_count=deterministic_human_event_count,
            human_positive_event_count=human_positive_event_count,
            ambiguous_event_count=ambiguous_event_count,
            excluded_program_event_count=excluded_program_event_count,
            sell_without_prior_count=sell_without_prior_count,
        )
        if snapshot["observed_holder_balance_sum"] is not None and snapshot["observed_holder_balance_sum"] < 0:
            warnings.append({"launch_id": candidate["launch_id"], "mint": candidate["token_mint"], "reason": "negative_balance_sum"})
        snapshots.append(snapshot)
        current_holders = {holder for holder, balance in balances.items() if balance > 0}
        if current_holders:
            previous_holders = current_holders
    return snapshots, negatives, warnings, exclusions, sells_without_prior, duplicates


def _snapshot_row(
    candidate: dict[str, Any],
    age: int,
    snapshot_ts: int,
    balances: dict[str, float],
    previous_holders: set[str] | None,
    observed_count: int,
    total_event_count: int,
    deterministic_human_event_count: int,
    human_positive_event_count: int,
    ambiguous_event_count: int,
    excluded_program_event_count: int,
    sell_without_prior_count: int,
) -> dict[str, Any]:
    positive = {holder: balance for holder, balance in balances.items() if balance > 0}
    total = sum(positive.values())
    creator = _creator_wallet(candidate)
    base = {
        "launch_id": candidate["launch_id"],
        "mint": candidate["token_mint"],
        "snapshot_label": SNAPSHOT_LABELS[age],
        "snapshot_age_seconds": age,
        "snapshot_time": snapshot_ts,
        "pool_address": candidate.get("pool_address"),
        "venue": candidate.get("venue"),
        "creator_wallet": creator,
        "holder_snapshot_source": HOLDER_DISTRIBUTION_SOURCE,
        "is_observed_delta_replay": True,
        "is_confirmed_full_chain_snapshot": False,
        "observed_event_count_through_snapshot": observed_count,
        "total_event_count_for_launch": total_event_count,
        "deterministic_human_event_count_through_snapshot": deterministic_human_event_count,
        "human_positive_event_count_through_snapshot": human_positive_event_count,
        "ambiguous_event_count_through_snapshot": ambiguous_event_count,
        "excluded_program_event_count_through_snapshot": excluded_program_event_count,
        "sell_without_prior_count_through_snapshot": sell_without_prior_count,
    }
    if not positive or total <= 0:
        zero_or_missing = _zero_or_missing_state(
            total_event_count=total_event_count,
            observed_count=observed_count,
            deterministic_human_event_count=deterministic_human_event_count,
            human_positive_event_count=human_positive_event_count,
            ambiguous_event_count=ambiguous_event_count,
            excluded_program_event_count=excluded_program_event_count,
            sell_without_prior_count=sell_without_prior_count,
        )
        if zero_or_missing["holder_count"] == 0:
            creator_share = 0.0 if creator else None
            return base | {
                "holder_count": 0,
                "top_holder_share": 0.0,
                "top_10_holder_share": 0.0,
                "creator_holder_share": creator_share,
                "observed_holder_balance_sum": 0.0,
                "holder_snapshot_confidence": "valid_zero",
                "holder_snapshot_state": zero_or_missing["state"],
                "holder_snapshot_missing_reason": zero_or_missing["reason"],
                "holder_retention_proxy": None,
                "holder_churn_proxy": None,
                "net_new_holders": 0,
                "exited_holder_count": None,
                "new_holder_count": None,
                "creator_linked_share": creator_share,
            }
        return base | {
            "holder_count": None,
            "top_holder_share": None,
            "top_10_holder_share": None,
            "creator_holder_share": None,
            "observed_holder_balance_sum": None,
            "holder_snapshot_confidence": "missing",
            "holder_snapshot_state": zero_or_missing["state"],
            "holder_snapshot_missing_reason": zero_or_missing["reason"],
            "holder_retention_proxy": None,
            "holder_churn_proxy": None,
            "net_new_holders": None,
            "exited_holder_count": None,
            "new_holder_count": None,
            "creator_linked_share": None,
        }
    sorted_balances = sorted(positive.values(), reverse=True)
    current_holders = set(positive)
    retention = _retention_proxy(previous_holders, current_holders)
    exited = len(previous_holders - current_holders) if previous_holders else None
    new = len(current_holders - previous_holders) if previous_holders else None
    return base | {
        "holder_count": len(positive),
        "top_holder_share": sorted_balances[0] / total,
        "top_10_holder_share": sum(sorted_balances[:10]) / total,
        "creator_holder_share": _creator_share(positive, total, creator),
        "observed_holder_balance_sum": total,
        "holder_snapshot_confidence": "medium",
        "holder_snapshot_state": "observed_human_holders",
        "holder_snapshot_missing_reason": None,
        "holder_retention_proxy": retention,
        "holder_churn_proxy": (1.0 - retention) if retention is not None else None,
        "net_new_holders": (new - exited) if new is not None and exited is not None else None,
        "exited_holder_count": exited,
        "new_holder_count": new,
        "creator_linked_share": _creator_share(positive, total, creator),
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


def _zero_or_missing_state(
    *,
    total_event_count: int,
    observed_count: int,
    deterministic_human_event_count: int,
    human_positive_event_count: int,
    ambiguous_event_count: int,
    excluded_program_event_count: int,
    sell_without_prior_count: int,
) -> dict[str, Any]:
    if sell_without_prior_count > 0:
        return {"holder_count": None, "state": "insufficient_prior_state", "reason": "insufficient_prior_state"}
    if total_event_count == 0:
        return {"holder_count": None, "state": "missing_event_data", "reason": "missing_event_data"}
    if deterministic_human_event_count == 0 and ambiguous_event_count > 0 and excluded_program_event_count == 0:
        return {"holder_count": None, "state": "ambiguous_event_only", "reason": "ambiguous_event_only"}
    if deterministic_human_event_count == 0:
        if excluded_program_event_count > 0:
            return {"holder_count": 0, "state": "excluded_program_only", "reason": "valid_zero_observed_human_holders"}
        if observed_count == 0:
            return {"holder_count": 0, "state": "no_deterministic_human_holder_events_yet", "reason": "valid_zero_observed_human_holders"}
        return {"holder_count": 0, "state": "valid_zero_observed_human_holders", "reason": "valid_zero_observed_human_holders"}
    if human_positive_event_count == 0:
        return {"holder_count": 0, "state": "valid_zero_observed_human_holders", "reason": "valid_zero_observed_human_holders"}
    return {"holder_count": 0, "state": "valid_zero_observed_human_holders", "reason": "valid_zero_observed_human_holders"}


def _event_exclusion_reason(candidate: dict[str, Any], event: dict[str, Any]) -> str | None:
    event_type = str(event.get("event_type") or "").lower()
    side = str(event.get("side") or "").lower()
    venue = str(event.get("venue") or "").lower()
    if event_type in {"pumpfun_swap", "swap_candidate"} or (venue == "pumpfun_swap" and side not in {"buy", "sell"}):
        return "ambiguous_swap_direction"
    actor = event.get("actor")
    role = _actor_role(candidate, actor)
    if role in {"bonding_curve", "associated_bonding_curve"}:
        return "bonding_curve_account_excluded"
    if role == "pool_address":
        return "pool_account_excluded"
    if role in {"program_account", "mint_account"}:
        return "program_account_excluded"
    return None


def _actor_role(candidate: dict[str, Any], actor: object) -> str:
    if not actor:
        return "unknown"
    actor = str(actor)
    metadata = candidate.get("metadata_json") or {}
    if actor == _creator_wallet(candidate):
        return "creator"
    if actor == metadata.get("bonding_curve"):
        return "bonding_curve"
    if actor == metadata.get("associated_bonding_curve"):
        return "associated_bonding_curve"
    if actor == candidate.get("pool_address"):
        return "pool_address"
    if actor == candidate.get("token_mint"):
        return "mint_account"
    if actor in KNOWN_PROGRAM_ACCOUNTS:
        return "program_account"
    return "unknown"


def _excluded_event(candidate: dict[str, Any], event: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "launch_id": candidate["launch_id"],
        "mint": candidate["token_mint"],
        "signature": event.get("signature"),
        "event_id": event.get("event_id"),
        "block_time": event.get("block_time"),
        "event_type": event.get("event_type"),
        "venue": event.get("venue"),
        "actor": event.get("actor"),
        "actor_role": _actor_role(candidate, event.get("actor")),
        "excluded_event_reason": reason,
    }


def _creator_wallet(candidate: dict[str, Any]) -> str | None:
    metadata = candidate.get("metadata_json") or {}
    return candidate.get("creator_wallet") or candidate.get("creator_deployer") or metadata.get("creator_deployer") or metadata.get("creator_wallet")


def _creator_share(positive: dict[str, float], total: float, creator: str | None) -> float | None:
    if not creator or total <= 0:
        return None
    return positive.get(str(creator), 0.0) / total


def _retention_proxy(previous_holders: set[str] | None, current_holders: set[str]) -> float | None:
    if not previous_holders:
        return None
    return len(previous_holders & current_holders) / len(previous_holders)


def _readiness_classification(
    *,
    snapshot_coverage: float,
    suspicious_negative_balance_count: int,
    insufficient_prior_state_pct: float,
    missing_known_creator_share: int,
    caveat_present: bool,
) -> str:
    if (
        snapshot_coverage >= 95.0
        and suspicious_negative_balance_count == 0
        and insufficient_prior_state_pct <= 5.0
        and missing_known_creator_share == 0
        and caveat_present
    ):
        return READINESS_READY
    if snapshot_coverage == 0 or suspicious_negative_balance_count > 0:
        return READINESS_BLOCKED
    return READINESS_PARTIAL


def _audit_report(rollout: dict[str, Any]) -> dict[str, Any]:
    public = dict(rollout)
    public.pop("holder_snapshots", None)
    return public


def _audit_markdown(rollout: dict[str, Any]) -> str:
    lines = [
        "# Holder-State Strict Cohort Audit",
        "",
        f"- Readiness classification: `{rollout['readiness_classification']}`",
        f"- Launches attempted: `{rollout['launches_attempted']}`",
        f"- Launches completed: `{rollout['launches_completed']}`",
        f"- Launches failed: `{rollout['launches_failed']}`",
        f"- Snapshots expected: `{rollout['snapshots_expected']}`",
        f"- Snapshot rows written: `{rollout['snapshot_rows_written']}`",
        f"- Snapshots built: `{rollout['snapshots_built']}`",
        f"- Snapshots with holder values: `{rollout['snapshots_with_holder_values']}`",
        f"- Valid zero-holder snapshots: `{rollout['valid_zero_holder_snapshots']}`",
        f"- Insufficient prior-state snapshots: `{rollout['insufficient_prior_state_snapshots']}`",
        f"- Missing event-data snapshots: `{rollout['missing_event_data_snapshots']}`",
        f"- Missing snapshots: `{rollout['missing_snapshots']}`",
        f"- Holder count coverage: `{rollout['holder_count_coverage_pct']:.2f}%`",
        f"- Top holder share coverage: `{rollout['top_holder_share_coverage_pct']:.2f}%`",
        f"- Top 10 holder share coverage: `{rollout['top_10_holder_share_coverage_pct']:.2f}%`",
        f"- Creator holder share coverage: `{rollout['creator_holder_share_coverage_pct']:.2f}%`",
        f"- Suspicious negative balance count: `{rollout['suspicious_negative_balance_count']}`",
        f"- Excluded ambiguous event count: `{rollout['excluded_ambiguous_event_count']}`",
        f"- Excluded program/pool/bonding curve event count: `{rollout['excluded_program_pool_account_event_count']}`",
        f"- Sell without prior observed balance count: `{rollout['sell_without_prior_observed_balance_count']}`",
        f"- Sell without prior observed balance unique launches: `{rollout['sell_without_prior_observed_balance_unique_launches']}`",
        f"- Duplicate event skipped count: `{rollout['duplicate_event_skipped_count']}`",
        f"- Balance conservation warning count: `{rollout['balance_conservation_warning_count']}`",
        f"- Runtime seconds: `{rollout['runtime_seconds']:.4f}`",
        f"- Storage size: `{rollout['storage_size']}`",
        "",
        "## Caveat",
        "",
        rollout["caveat"],
        "",
        "These rows are not full-chain holder-state snapshots.",
        "",
        "## Share Distributions",
        "",
        f"- Top holder share: `{rollout['share_distribution']['top_holder_share']}`",
        f"- Top 10 holder share: `{rollout['share_distribution']['top_10_holder_share']}`",
        f"- Creator holder share: `{rollout['share_distribution']['creator_holder_share']}`",
        "",
        "## Examples",
        "",
        f"- High concentration launches: `{rollout['examples']['high_concentration_launches']}`",
        f"- Low concentration launches: `{rollout['examples']['low_concentration_launches']}`",
        "",
        "No T001/T002 rerun was performed.",
        "",
    ]
    return "\n".join(lines)


def _negative_balance_markdown(diagnostics: dict[str, Any]) -> str:
    lines = [
        "# Holder-State Negative Balance Diagnostics",
        "",
        f"- Total negative balance events: `{diagnostics['total_negative_balance_events']}`",
        f"- Unique launches affected: `{diagnostics['unique_launches_affected']}`",
        f"- Unique mints affected: `{diagnostics['unique_mints_affected']}`",
        f"- Before positive balance seed count: `{diagnostics['before_positive_balance_seed_count']}`",
        f"- Duplicate signature/instruction count: `{diagnostics['duplicate_event_signature_instruction_count']}`",
        "",
        "## Counts",
        "",
        f"- By classification: `{diagnostics['negative_events_by_classification']}`",
        f"- By snapshot window: `{diagnostics['negative_events_by_snapshot_window']}`",
        f"- By actor role: `{diagnostics['negative_events_by_actor_role']}`",
        f"- By source: `{diagnostics['negative_events_by_source']}`",
        "",
        "## Top Repeats",
        "",
        f"- Actors: `{diagnostics['top_repeated_negative_actors']}`",
        f"- Mints: `{diagnostics['top_repeated_negative_mints']}`",
        "",
        "## Interpretation",
        "",
        "This report describes the legacy replay failure mode before conservative holder-delta repair rules are applied.",
        "It is diagnostic evidence only and does not make thesis or trading claims.",
        "",
    ]
    return "\n".join(lines)


def _missing_coverage_markdown(diagnostics: dict[str, Any]) -> str:
    lines = [
        "# Holder-State Missing Coverage Diagnostics",
        "",
        f"- Total missing holder-value snapshots: `{diagnostics['total_missing_holder_value_snapshots']}`",
        f"- Missing by window: `{diagnostics['missing_snapshots_by_snapshot_window']}`",
        f"- Missing reasons: `{diagnostics['missing_reason_counts']}`",
        f"- Snapshot states: `{diagnostics['snapshot_state_counts']}`",
        f"- Launches with all snapshots missing: `{len(diagnostics['launches_with_all_snapshots_missing'])}`",
        f"- Early present, later missing launches: `{len(diagnostics['launches_with_early_present_later_missing'])}`",
        f"- Later present, early missing launches: `{len(diagnostics['launches_with_later_present_early_missing'])}`",
        "",
        "This report separates valid zero observed human-holder snapshots from genuinely missing or insufficient replay states.",
        "It is a data-quality report only and does not rerun or promote theses.",
        "",
    ]
    return "\n".join(lines)


def _sell_without_prior_markdown(diagnostics: dict[str, Any]) -> str:
    lines = [
        "# Holder-State Sell Without Prior Diagnostics",
        "",
        f"- Sell without prior count: `{diagnostics['sell_without_prior_count']}`",
        f"- Count by snapshot window: `{diagnostics['sell_without_prior_count_by_snapshot_window']}`",
        f"- Event age seconds distribution: `{diagnostics['event_age_seconds_distribution']}`",
        f"- Actor prior buy count: `{diagnostics['actor_prior_buy_count']}`",
        f"- Actor prior positive delta count: `{diagnostics['actor_prior_positive_delta_count']}`",
        f"- Actor is creator count: `{diagnostics['actor_is_creator_count']}`",
        f"- Actor is excluded program/pool/bonding-curve count: `{diagnostics['actor_is_excluded_program_pool_bonding_curve_count']}`",
        f"- Actor appears in create/init accounts count: `{diagnostics['actor_appears_in_create_or_init_accounts_count']}`",
        f"- Sells before first deterministic buy count: `{diagnostics['sells_before_first_deterministic_buy_in_launch_window_count']}`",
        "",
        "These events are classified as insufficient prior state unless a deterministic acquisition exists earlier in normalized events.",
        "",
    ]
    return "\n".join(lines)


def _write_parquet(rows: list[dict[str, Any]], output_path: Path) -> None:
    import pandas as pd

    output_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(output_path, index=False)


def _field_coverage(rows: list[dict[str, Any]], field: str, total: int) -> dict[str, Any]:
    available = sum(1 for row in rows if row.get(field) is not None)
    return {"available_snapshots": available, "missing_snapshots": total - available, "coverage_pct": _pct(available, total)}


def _missing_reason_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counter = Counter(row["holder_snapshot_missing_reason"] for row in rows if row.get("holder_snapshot_missing_reason"))
    return dict(sorted(counter.items()))


def _distribution(values) -> dict[str, float | None]:
    clean = sorted(float(value) for value in values if value is not None)
    if not clean:
        return {"min": None, "median": None, "max": None}
    return {"min": clean[0], "median": median(clean), "max": clean[-1]}


def _example_launches(rows: list[dict[str, Any]], *, reverse: bool) -> list[dict[str, Any]]:
    usable = [row for row in rows if row.get("top_holder_share") is not None]
    ordered = sorted(usable, key=lambda row: (row["top_holder_share"], row["launch_id"], row["snapshot_age_seconds"]), reverse=reverse)
    return [
        {
            "launch_id": row["launch_id"],
            "mint": row["mint"],
            "snapshot_label": row["snapshot_label"],
            "top_holder_share": row["top_holder_share"],
            "holder_count": row["holder_count"],
        }
        for row in ordered[:5]
    ]


def _pct(available: int, total: int) -> float:
    return (available / total * 100) if total else 0.0


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _read_jsonl(path: Path | str) -> list[dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
