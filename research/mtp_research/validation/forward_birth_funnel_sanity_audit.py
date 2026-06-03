"""Sanity-audit the forward Pump.fun birth-to-trigger funnel.

This module is read-only. It inspects local forward observation artifacts and
does not collect data, call Helius, run backtests, or generate trading logic.
"""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from math import ceil
from pathlib import Path
from typing import Any


REPORT_ID = "forward_birth_funnel_sanity_audit_v0"
TRIGGER_LEVELS: dict[str, float] = {
    "10k": 10_000.0,
    "15k": 15_000.0,
    "20k": 20_000.0,
    "30k": 30_000.0,
    "50k": 50_000.0,
    "100k": 100_000.0,
    "500k": 500_000.0,
    "1m": 1_000_000.0,
}
REPORT_NAMES = {
    "dedupe_csv": "birth_funnel_dedupe_audit.csv",
    "provenance_csv": "birth_funnel_milestone_provenance.csv",
    "ordering_csv": "birth_funnel_milestone_ordering.csv",
    "freshness_csv": "birth_funnel_freshness_audit.csv",
    "bias_csv": "birth_funnel_followup_bias_audit.csv",
    "time_to_milestone_csv": "birth_funnel_time_to_milestone.csv",
    "manual_review_sample_csv": "birth_funnel_manual_review_sample.csv",
    "summary_json": "birth_funnel_sanity_summary.json",
    "summary_md": "birth_funnel_sanity_summary.md",
}
GUARDRAILS = [
    "audit_only",
    "no_network_calls",
    "no_helius_calls",
    "no_additional_collection",
    "no_private_keys",
    "no_wallet_execution",
    "no_transaction_signing",
    "no_buy_orders",
    "no_sell_orders",
    "no_swaps",
    "no_order_routing",
    "no_live_trading",
    "no_paper_trading",
    "no_pnl",
    "no_profitability_claims",
    "no_strategy_generation",
    "no_alerts",
    "no_threshold_optimization",
    "no_ml",
    "no_validation",
    "no_backtest",
]


@dataclass(frozen=True)
class LoadedJsonl:
    rows: list[dict[str, Any]]
    malformed_rows: int
    missing: bool


def build_forward_birth_funnel_sanity_audit(
    data_root: Path | str = "/Volumes/ORICO/MemeTraderPro",
    *,
    output_dir: Path | str | None = None,
    write_outputs: bool = True,
) -> tuple[dict[str, Any], dict[str, Path]]:
    data_root = Path(data_root).expanduser()
    observation_root = data_root / "data" / "forward_observation" / "efficient_movers"
    raw_root = data_root / "data" / "raw" / "forward_observation" / "efficient_movers"
    report_root = (
        Path(output_dir).expanduser()
        if output_dir
        else data_root / "data" / "backtests" / "diagnostics" / "reports" / "forward_observation" / "efficient_movers"
    )

    candidates = _load_jsonl(observation_root / "candidates.jsonl")
    paths = _load_jsonl(observation_root / "candidate_paths.jsonl")
    events = _load_jsonl(observation_root / "candidate_events.jsonl")
    source_candidates = _load_jsonl(raw_root / "source_candidates.jsonl")

    birth_rows = [row for row in candidates.rows if _is_birth_watch_candidate(row)]
    source_birth_rows = [row for row in source_candidates.rows if _is_birth_watch_candidate(row)]
    birth_mints = {_mint(row) for row in birth_rows if _mint(row)}
    paths_by_mint = _group_by_mint([row for row in paths.rows if _mint(row) in birth_mints])
    events_by_mint = _group_by_mint([row for row in events.rows if _mint(row) in birth_mints])
    source_by_mint = _group_by_mint(source_birth_rows)

    strict_birth_rows = _strict_birth_rows(birth_rows, source_by_mint)
    raw_funnel_counts = _funnel_counts(birth_rows, paths_by_mint)
    strict_funnel_counts = _funnel_counts(strict_birth_rows, paths_by_mint)

    dedupe_rows, duplicate_counts = _build_dedupe_rows(birth_rows, paths_by_mint)
    provenance_rows, observed_milestones_by_mint = _build_provenance_rows(strict_birth_rows, paths_by_mint)
    ordering_rows = _build_ordering_rows(strict_birth_rows, paths_by_mint)
    freshness_rows = _build_freshness_rows(strict_birth_rows, paths_by_mint, events_by_mint, source_by_mint)
    bias_rows, bias_risk = _build_bias_rows(strict_birth_rows, paths_by_mint, events_by_mint)
    time_rows = _build_time_to_milestone_rows(strict_birth_rows, observed_milestones_by_mint)
    manual_rows = _build_manual_review_rows(strict_birth_rows, paths_by_mint, observed_milestones_by_mint, freshness_rows)

    observed_only_counts = _funnel_counts(strict_birth_rows, paths_by_mint, observed_milestones_by_mint=observed_milestones_by_mint)
    true_near_mints = {
        row["mint"]
        for row in freshness_rows
        if row["freshness_classification"] in {"true_birth_observed", "near_birth_observed"}
    }
    true_near_counts = _funnel_counts(
        [row for row in strict_birth_rows if _mint(row) in true_near_mints],
        paths_by_mint,
        observed_milestones_by_mint=observed_milestones_by_mint,
    )

    provenance_summary = dict(Counter(row["source_provenance"] for row in provenance_rows))
    ordering_summary = dict(Counter(row["ordering_status"] for row in ordering_rows))
    freshness_summary = dict(Counter(row["freshness_classification"] for row in freshness_rows))
    validity_classification = _classify_validity(
        duplicate_counts=duplicate_counts,
        provenance_rows=provenance_rows,
        ordering_rows=ordering_rows,
        freshness_rows=freshness_rows,
        strict_counts=strict_funnel_counts,
        observed_only_counts=observed_only_counts,
        bias_risk=bias_risk,
    )
    summary = {
        "report_id": REPORT_ID,
        "data_root": str(data_root),
        "observation_root": str(observation_root),
        "raw_root": str(raw_root),
        "report_root": str(report_root),
        "total_forward_candidates": len(candidates.rows),
        "raw_funnel_counts": raw_funnel_counts,
        "strict_deduped_funnel_counts": strict_funnel_counts,
        "observed_followup_only_funnel_counts": observed_only_counts,
        "true_near_birth_funnel_counts": true_near_counts,
        "duplicate_counts": duplicate_counts,
        "milestone_provenance_summary": provenance_summary,
        "milestone_ordering_summary": ordering_summary,
        "freshness_summary": freshness_summary,
        "followup_bias_summary": {
            "bias_risk": bias_risk,
            "group_counts": dict(Counter(row["group"] for row in bias_rows)),
        },
        "validity_classification": validity_classification,
        "recommendation": _recommendation(validity_classification),
        "file_row_counts": {
            "candidates": len(candidates.rows),
            "candidate_paths": len(paths.rows),
            "candidate_events": len(events.rows),
            "source_candidates": len(source_candidates.rows),
        },
        "malformed_row_counts": {
            "candidates": candidates.malformed_rows,
            "candidate_paths": paths.malformed_rows,
            "candidate_events": events.malformed_rows,
            "source_candidates": source_candidates.malformed_rows,
        },
        "missing_files": [
            name
            for name, loaded in {
                "candidates": candidates,
                "candidate_paths": paths,
                "candidate_events": events,
                "source_candidates": source_candidates,
            }.items()
            if loaded.missing
        ],
        "guardrails": GUARDRAILS,
        "network_calls_made": 0,
    }

    output_paths: dict[str, Path] = {}
    if write_outputs:
        report_root.mkdir(parents=True, exist_ok=True)
        output_paths = {
            "dedupe_csv": _write_csv(report_root / REPORT_NAMES["dedupe_csv"], dedupe_rows),
            "provenance_csv": _write_csv(report_root / REPORT_NAMES["provenance_csv"], provenance_rows),
            "ordering_csv": _write_csv(report_root / REPORT_NAMES["ordering_csv"], ordering_rows),
            "freshness_csv": _write_csv(report_root / REPORT_NAMES["freshness_csv"], freshness_rows),
            "bias_csv": _write_csv(report_root / REPORT_NAMES["bias_csv"], bias_rows),
            "time_to_milestone_csv": _write_csv(report_root / REPORT_NAMES["time_to_milestone_csv"], time_rows),
            "manual_review_sample_csv": _write_csv(report_root / REPORT_NAMES["manual_review_sample_csv"], manual_rows),
            "summary_json": _write_json(report_root / REPORT_NAMES["summary_json"], summary),
            "summary_markdown": _write_summary_markdown(report_root / REPORT_NAMES["summary_md"], summary),
            "status_markdown": _write_status_markdown(
                Path("theses") / "FORWARD_BIRTH_FUNNEL_SANITY_AUDIT_STATUS.md",
                summary,
            ),
        }
    return summary, output_paths


def classify_milestone_provenance(row: dict[str, Any]) -> tuple[str, bool]:
    source = str(row.get("source") or "").lower()
    event_type = str(row.get("event_type") or "").lower()
    if "later_outcome" in source or "outcome_label" in source or event_type == "later_outcome":
        return "later_outcome_label", False
    if "summary_peak" in source or "peak_label" in source:
        return "summary_peak_label", False
    if "snapshot" in source or event_type.endswith("snapshot"):
        return "observed_snapshot", True
    if "followup" in source and not _is_create_event(row):
        return "observed_followup_path", True
    if "trade_delta" in source or event_type in {"pumpfun_trade", "pumpfun_buy", "pumpfun_sell"}:
        return "observed_trade_delta", True
    return "unknown", False


def validate_milestone_ordering(
    *,
    create_time: float | None,
    first_followup_time: float | None,
    milestone_times: dict[str, float | None],
) -> list[str]:
    violations: list[str] = []
    if create_time is None:
        violations.append("missing_create_time")
    if first_followup_time is None:
        violations.append("missing_followup_time")
    if create_time is not None and first_followup_time is not None and first_followup_time < create_time:
        violations.append("impossible_time_order")

    pairs = [
        ("10k", "20k", "20k_before_10k"),
        ("20k", "50k", "50k_before_20k"),
        ("50k", "100k", "100k_before_50k"),
        ("100k", "500k", "500k_before_100k"),
        ("500k", "1m", "1m_before_500k"),
    ]
    for earlier, later, label in pairs:
        earlier_time = milestone_times.get(earlier)
        later_time = milestone_times.get(later)
        if earlier_time is not None and later_time is not None and later_time < earlier_time:
            violations.append(label)
    populated_times = [value for value in milestone_times.values() if value is not None]
    if len(populated_times) != len(set(populated_times)):
        violations.append("same_timestamp_multiple_milestones")
    return violations or ["no_violation"]


def classify_birth_freshness(
    create_signature_exists: bool,
    create_event_type: str | None,
    create_time: float | None,
    first_followup_time: float | None,
    first_followup_fdv: float | None,
) -> str:
    if not create_signature_exists or create_event_type != "pumpfun_create" or create_time is None:
        return "unknown_birth_freshness"
    if first_followup_fdv is not None:
        if first_followup_fdv >= 100_000:
            return "first_followup_already_above_100k"
        if first_followup_fdv >= 50_000:
            return "first_followup_already_above_50k"
        if first_followup_fdv >= 20_000:
            return "first_followup_already_above_20k"
        if first_followup_fdv >= 10_000:
            return "first_followup_already_above_10k"
    if first_followup_time is None:
        return "unknown_birth_freshness"
    delta = first_followup_time - create_time
    if delta <= 15:
        return "true_birth_observed"
    if delta <= 60:
        return "near_birth_observed"
    return "first_followup_after_activity"


def classify_followup_bias(*, total_births: int, fdv_followup: int, no_fdv_evidence: int, crossed_10k: int) -> str:
    if total_births <= 0:
        return "unknown_bias_risk"
    followup_rate = fdv_followup / total_births
    if followup_rate >= 0.9:
        return "low_bias_risk"
    if followup_rate >= 0.5:
        return "medium_bias_risk"
    return "high_bias_risk"


def _build_dedupe_rows(
    birth_rows: list[dict[str, Any]],
    paths_by_mint: dict[str, list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    rows: list[dict[str, Any]] = []
    duplicate_counts = {
        "raw_birth_rows": len(birth_rows),
        "unique_birth_mints": len({_mint(row) for row in birth_rows if _mint(row)}),
        "duplicate_mint_rows": 0,
        "duplicate_candidate_rows": 0,
        "duplicate_followup_rows": 0,
        "duplicate_milestone_rows": 0,
        "source_transition_duplicates": 0,
        "repeated_scanner_pass_duplicates": 0,
        "rows_removed_by_strict_dedupe": 0,
    }
    candidate_mints = Counter(_mint(row) for row in birth_rows if _mint(row))
    observation_ids = Counter(str(row.get("observation_id") or "") for row in birth_rows if row.get("observation_id"))
    sources_by_mint: dict[str, set[str]] = defaultdict(set)
    signatures_by_mint: dict[str, Counter[str]] = defaultdict(Counter)
    for row in birth_rows:
        mint = _mint(row)
        if mint:
            sources_by_mint[mint].add(str(row.get("source") or ""))
            signature = str(row.get("transaction_signature") or "")
            if signature:
                signatures_by_mint[mint][signature] += 1
    for mint, count in sorted(candidate_mints.items()):
        if count > 1:
            duplicate_counts["duplicate_mint_rows"] += count - 1
            rows.append({"mint": mint, "duplicate_cause": "duplicate_candidate_should_collapse", "duplicate_rows": count - 1})
        if len(sources_by_mint[mint]) > 1:
            duplicate_counts["source_transition_duplicates"] += 1
            rows.append({"mint": mint, "duplicate_cause": "source_transition", "duplicate_rows": 1})
        for signature, sig_count in signatures_by_mint[mint].items():
            if sig_count > 1:
                duplicate_counts["repeated_scanner_pass_duplicates"] += sig_count - 1
                rows.append({"mint": mint, "duplicate_cause": "repeated_scanner_signature", "signature": signature, "duplicate_rows": sig_count - 1})
    for observation_id, count in observation_ids.items():
        if count > 1:
            duplicate_counts["duplicate_candidate_rows"] += count - 1
            rows.append({"observation_id": observation_id, "duplicate_cause": "duplicate_candidate_should_collapse", "duplicate_rows": count - 1})

    followup_keys: Counter[tuple[Any, ...]] = Counter()
    milestone_keys: Counter[tuple[Any, ...]] = Counter()
    for mint, mint_paths in paths_by_mint.items():
        for row in mint_paths:
            if _is_create_event(row):
                continue
            key = (mint, _num(row.get("timestamp") or row.get("observed_at")), _num(row.get("fdv_proxy")), row.get("source"), row.get("event_type"))
            followup_keys[key] += 1
            fdv = _num(row.get("fdv_proxy"))
            if fdv is None:
                continue
            for level, threshold in TRIGGER_LEVELS.items():
                if fdv >= threshold:
                    milestone_keys[(mint, level, key[1], fdv)] += 1
    for key, count in followup_keys.items():
        if count > 1:
            duplicate_counts["duplicate_followup_rows"] += count - 1
            rows.append({"mint": key[0], "duplicate_cause": "legitimate_followup_update", "duplicate_rows": count - 1, "timestamp": key[1], "fdv_proxy": key[2]})
    for key, count in milestone_keys.items():
        if count > 1:
            duplicate_counts["duplicate_milestone_rows"] += count - 1
            rows.append({"mint": key[0], "duplicate_cause": "duplicate_milestone_row", "duplicate_rows": count - 1, "milestone": key[1], "timestamp": key[2], "fdv_proxy": key[3]})
    duplicate_counts["rows_removed_by_strict_dedupe"] = (
        duplicate_counts["duplicate_mint_rows"] + duplicate_counts["duplicate_followup_rows"] + duplicate_counts["duplicate_milestone_rows"]
    )
    if not rows:
        rows.append({"duplicate_cause": "none", "duplicate_rows": 0})
    return rows, duplicate_counts


def _build_provenance_rows(
    strict_birth_rows: list[dict[str, Any]],
    paths_by_mint: dict[str, list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, dict[str, Any]]]]:
    rows: list[dict[str, Any]] = []
    observed_by_mint: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for candidate in strict_birth_rows:
        mint = _mint(candidate)
        for level, threshold in TRIGGER_LEVELS.items():
            row = _first_threshold_row(paths_by_mint.get(mint, []), threshold)
            if row is None:
                continue
            provenance, replay_safe = classify_milestone_provenance(row)
            output = {
                "mint": mint,
                "milestone": level,
                "crossing_time": _num(row.get("timestamp") or row.get("observed_at")),
                "crossing_fdv": _num(row.get("fdv_proxy")),
                "source_file": "candidate_paths.jsonl",
                "source_row_type": row.get("event_type") or "path",
                "source_provenance": provenance,
                "inferred_from_max_or_peak": provenance in {"later_outcome_label", "summary_peak_label"},
                "replay_safe": replay_safe,
            }
            rows.append(output)
            if replay_safe and provenance in {"observed_followup_path", "observed_trade_delta", "observed_snapshot"}:
                observed_by_mint[mint][level] = output
    return rows, observed_by_mint


def _build_ordering_rows(
    strict_birth_rows: list[dict[str, Any]],
    paths_by_mint: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for candidate in strict_birth_rows:
        mint = _mint(candidate)
        create_time = _create_time(candidate)
        first_followup = _first_fdv_path(paths_by_mint.get(mint, []))
        milestone_times = {
            level: (_num(row.get("timestamp") or row.get("observed_at")) if row is not None else None)
            for level, threshold in TRIGGER_LEVELS.items()
            for row in [_first_threshold_row(paths_by_mint.get(mint, []), threshold)]
        }
        violations = validate_milestone_ordering(
            create_time=create_time,
            first_followup_time=_num(first_followup.get("timestamp") or first_followup.get("observed_at")) if first_followup else None,
            milestone_times=milestone_times,
        )
        rows.append(
            {
                "mint": mint,
                "create_time": create_time,
                "first_fdv_followup_time": _num(first_followup.get("timestamp") or first_followup.get("observed_at")) if first_followup else None,
                "ordering_status": "no_violation" if violations == ["no_violation"] else ";".join(violations),
                **{f"{level}_time": milestone_times.get(level) for level in TRIGGER_LEVELS},
            }
        )
    return rows


def _build_freshness_rows(
    strict_birth_rows: list[dict[str, Any]],
    paths_by_mint: dict[str, list[dict[str, Any]]],
    events_by_mint: dict[str, list[dict[str, Any]]],
    source_by_mint: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for candidate in strict_birth_rows:
        mint = _mint(candidate)
        source_rows = source_by_mint.get(mint, [])
        event_rows = events_by_mint.get(mint, [])
        create_event = next((row for row in event_rows if _is_create_event(row)), None)
        create_signature = str(candidate.get("transaction_signature") or "")
        if not create_signature and source_rows:
            create_signature = str(source_rows[0].get("transaction_signature") or "")
        if not create_signature and create_event:
            create_signature = str(create_event.get("transaction_signature") or "")
        first_fdv = _first_fdv_path(paths_by_mint.get(mint, []))
        first_fdv_time = _num(first_fdv.get("timestamp") or first_fdv.get("observed_at")) if first_fdv else None
        first_fdv_proxy = _num(first_fdv.get("fdv_proxy")) if first_fdv else None
        create_time = _create_time(candidate, source_rows=source_rows, create_event=create_event)
        classification = classify_birth_freshness(
            bool(create_signature),
            str((create_event or candidate).get("event_type") or ""),
            create_time,
            first_fdv_time,
            first_fdv_proxy,
        )
        rows.append(
            {
                "mint": mint,
                "create_signature_exists": bool(create_signature),
                "create_signature": create_signature,
                "create_event_type": (create_event or candidate).get("event_type"),
                "create_time": create_time,
                "first_followup_time": first_fdv_time,
                "time_from_create_to_first_followup": _delta(create_time, first_fdv_time),
                "first_observed_fdv": first_fdv_proxy,
                "first_observed_buy_count": first_fdv.get("buy_count") if first_fdv else None,
                "first_observed_event_count": first_fdv.get("event_count") if first_fdv else None,
                "first_followup_before_10k": first_fdv_proxy is not None and first_fdv_proxy < 10_000,
                "first_followup_before_15k": first_fdv_proxy is not None and first_fdv_proxy < 15_000,
                "first_followup_before_20k": first_fdv_proxy is not None and first_fdv_proxy < 20_000,
                "first_followup_already_above_10k": first_fdv_proxy is not None and first_fdv_proxy >= 10_000,
                "first_followup_already_above_20k": first_fdv_proxy is not None and first_fdv_proxy >= 20_000,
                "first_followup_already_above_50k": first_fdv_proxy is not None and first_fdv_proxy >= 50_000,
                "first_followup_already_above_100k": first_fdv_proxy is not None and first_fdv_proxy >= 100_000,
                "true_birth_observed": classification == "true_birth_observed",
                "freshness_classification": classification,
            }
        )
    return rows


def _build_bias_rows(
    strict_birth_rows: list[dict[str, Any]],
    paths_by_mint: dict[str, list[dict[str, Any]]],
    events_by_mint: dict[str, list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], str]:
    rows: list[dict[str, Any]] = []
    for candidate in strict_birth_rows:
        mint = _mint(candidate)
        fdv_paths = _fdv_paths(paths_by_mint.get(mint, []))
        event_rows = [row for row in events_by_mint.get(mint, []) if not _is_create_event(row)]
        trigger = any(_num(row.get("fdv_proxy")) is not None and _num(row.get("fdv_proxy")) >= 10_000 for row in fdv_paths)
        if trigger:
            group = "births_crossing_10k_plus"
        elif fdv_paths:
            group = "births_with_deterministic_fdv_followup"
        else:
            group = "births_with_no_fdv_evidence"
        event_times = [_num(row.get("transaction_time") or row.get("timestamp") or row.get("observed_at")) for row in event_rows]
        event_times = [value for value in event_times if value is not None]
        buy_sum = sum(int(_num(row.get("buy_count")) or 0) for row in paths_by_mint.get(mint, []) if not _is_create_event(row))
        sell_sum = sum(int(_num(row.get("sell_count")) or 0) for row in paths_by_mint.get(mint, []) if not _is_create_event(row))
        rows.append(
            {
                "mint": mint,
                "group": group,
                "number_of_signatures": len({row.get("transaction_signature") for row in event_rows if row.get("transaction_signature")}),
                "hydrated_transactions": len(event_rows),
                "trade_deltas": len(event_rows),
                "number_of_buys": buy_sum,
                "number_of_sells": sell_sum,
                "first_activity_time": min(event_times) if event_times else None,
                "last_activity_time": max(event_times) if event_times else None,
                "time_span": (max(event_times) - min(event_times)) if len(event_times) >= 2 else 0 if event_times else None,
                "source_availability": "fdv_path_available" if fdv_paths else "no_fdv_path_available",
                "missing_reason": None if fdv_paths else "no_deterministic_fdv_followup",
            }
        )
    total = len(strict_birth_rows)
    fdv = sum(1 for row in rows if row["group"] in {"births_with_deterministic_fdv_followup", "births_crossing_10k_plus"})
    crossed = sum(1 for row in rows if row["group"] == "births_crossing_10k_plus")
    risk = classify_followup_bias(total_births=total, fdv_followup=fdv, no_fdv_evidence=total - fdv, crossed_10k=crossed)
    return rows, risk


def _build_time_to_milestone_rows(
    strict_birth_rows: list[dict[str, Any]],
    observed_milestones_by_mint: dict[str, dict[str, dict[str, Any]]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for candidate in strict_birth_rows:
        mint = _mint(candidate)
        milestones = observed_milestones_by_mint.get(mint, {})
        if not milestones:
            continue
        create_time = _create_time(candidate)
        row: dict[str, Any] = {"mint": mint, "create_time": create_time}
        for level in TRIGGER_LEVELS:
            crossing = milestones.get(level)
            value = _delta(create_time, _num(crossing.get("crossing_time")) if crossing else None)
            row[f"create_to_{level}_seconds"] = value
            row[f"create_to_{level}_bucket"] = _time_bucket(value)
        for first, second in [("10k", "20k"), ("20k", "50k"), ("20k", "100k"), ("20k", "500k"), ("20k", "1m")]:
            first_time = _num(milestones.get(first, {}).get("crossing_time"))
            second_time = _num(milestones.get(second, {}).get("crossing_time"))
            row[f"{first}_to_{second}_seconds"] = _delta(first_time, second_time)
            row[f"{first}_to_{second}_bucket"] = _time_bucket(row[f"{first}_to_{second}_seconds"])
        rows.append(row)
    return rows


def _build_manual_review_rows(
    strict_birth_rows: list[dict[str, Any]],
    paths_by_mint: dict[str, list[dict[str, Any]]],
    observed_milestones_by_mint: dict[str, dict[str, dict[str, Any]]],
    freshness_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    freshness_by_mint = {row["mint"]: row for row in freshness_rows}
    crossed = [row for row in strict_birth_rows if observed_milestones_by_mint.get(_mint(row), {}).get("10k")]
    crossed.sort(key=lambda row: _num(observed_milestones_by_mint[_mint(row)]["10k"]["crossing_time"]) or float("inf"))
    rows: list[dict[str, Any]] = []
    for candidate in crossed[:25]:
        mint = _mint(candidate)
        milestones = observed_milestones_by_mint.get(mint, {})
        path_rows = _fdv_paths(paths_by_mint.get(mint, []))
        compact_paths = [
            {
                "timestamp": _num(row.get("timestamp") or row.get("observed_at")),
                "fdv_proxy": _num(row.get("fdv_proxy")),
                "source": row.get("source"),
                "event_type": row.get("event_type"),
            }
            for row in path_rows[:5]
        ]
        freshness = freshness_by_mint.get(mint, {})
        rows.append(
            {
                "mint": mint,
                "symbol": candidate.get("token_symbol"),
                "name": candidate.get("token_name"),
                "create_time": freshness.get("create_time"),
                "first_followup_time": freshness.get("first_followup_time"),
                "first_followup_fdv": freshness.get("first_observed_fdv"),
                **{f"crossed_{level}_time": milestones.get(level, {}).get("crossing_time") for level in TRIGGER_LEVELS},
                **{f"{level}_source_provenance": milestones.get(level, {}).get("source_provenance") for level in TRIGGER_LEVELS},
                "followup_rows": len(path_rows),
                "first_5_path_rows_compact_json": json.dumps(compact_paths, sort_keys=True),
                "sanity_notes": freshness.get("freshness_classification"),
            }
        )
    return rows


def _classify_validity(
    *,
    duplicate_counts: dict[str, int],
    provenance_rows: list[dict[str, Any]],
    ordering_rows: list[dict[str, Any]],
    freshness_rows: list[dict[str, Any]],
    strict_counts: dict[str, Any],
    observed_only_counts: dict[str, Any],
    bias_risk: str,
) -> str:
    if duplicate_counts.get("duplicate_mint_rows", 0) > 0:
        return "funnel_needs_dedupe_repair"
    if any(not row["replay_safe"] for row in provenance_rows):
        return "funnel_needs_milestone_provenance_repair"
    non_blocking_ordering = {"no_violation", "same_timestamp_multiple_milestones", "missing_followup_time"}
    severe_ordering = [row for row in ordering_rows if row["ordering_status"] not in non_blocking_ordering]
    if severe_ordering:
        return "funnel_inconclusive"
    crossed_10k = observed_only_counts.get("crossed_10k", 0) or 0
    if crossed_10k:
        fresh_count = sum(
            1
            for row in freshness_rows
            if row["freshness_classification"] in {"true_birth_observed", "near_birth_observed"}
            and _num(row.get("first_observed_fdv")) is not None
            and (_num(row.get("first_observed_fdv")) or 0) < 10_000
        )
        if fresh_count / crossed_10k < 0.5:
            return "funnel_needs_freshness_repair"
    if strict_counts.get("crossed_10k") != observed_only_counts.get("crossed_10k"):
        return "funnel_needs_milestone_provenance_repair"
    if bias_risk == "high_bias_risk":
        return "funnel_valid_but_active_sample_biased"
    return "funnel_valid_continue_scaling"


def _recommendation(validity_classification: str) -> str:
    if validity_classification == "funnel_valid_continue_scaling":
        return "Continue bounded scaling after reviewing the manual sample and same-timestamp jump-over rows."
    if validity_classification == "funnel_valid_but_active_sample_biased":
        return "Continue only with explicit active-sample bias tracking and larger birth inventory."
    if validity_classification == "funnel_needs_dedupe_repair":
        return "Repair duplicate birth mint collapse before continuing scale-up."
    if validity_classification == "funnel_needs_milestone_provenance_repair":
        return "Repair milestone provenance so only observed forward path crossings count."
    if validity_classification == "funnel_needs_freshness_repair":
        return "Repair birth freshness or follow-up timing before trusting trigger conversion rates."
    return "Do not continue scaling until inconclusive audit rows are manually reviewed."


def _funnel_counts(
    birth_rows: list[dict[str, Any]],
    paths_by_mint: dict[str, list[dict[str, Any]]],
    *,
    observed_milestones_by_mint: dict[str, dict[str, dict[str, Any]]] | None = None,
    target: int = 300,
) -> dict[str, Any]:
    births = len(birth_rows)
    fdv_followup = sum(1 for row in birth_rows if _fdv_paths(paths_by_mint.get(_mint(row), [])))
    if observed_milestones_by_mint is None:
        trigger_counts = {
            level: sum(1 for row in birth_rows if _first_threshold_row(paths_by_mint.get(_mint(row), []), threshold) is not None)
            for level, threshold in TRIGGER_LEVELS.items()
        }
    else:
        trigger_counts = {
            level: sum(1 for row in birth_rows if level in observed_milestones_by_mint.get(_mint(row), {}))
            for level in TRIGGER_LEVELS
        }
    crossed_10k = trigger_counts.get("10k", 0)
    crossed_20k = trigger_counts.get("20k", 0)
    counts: dict[str, Any] = {
        "birth_watch_count": births,
        "fdv_followup_count": fdv_followup,
        **{f"crossed_{level}": value for level, value in trigger_counts.items()},
        "birth_to_fdv_followup_rate": _rate(fdv_followup, births),
        "birth_to_10k_conversion_rate": _rate(crossed_10k, births),
        "birth_to_20k_conversion_rate": _rate(crossed_20k, births),
        "10k_to_20k_conversion_rate": _rate(crossed_20k, crossed_10k),
        "20k_to_100k_conversion_rate": _rate(trigger_counts.get("100k", 0), crossed_20k),
        "20k_to_500k_conversion_rate": _rate(trigger_counts.get("500k", 0), crossed_20k),
        "20k_to_1m_conversion_rate": _rate(trigger_counts.get("1m", 0), crossed_20k),
        "estimated_births_needed_for_300_crossed_10k": _estimated_births_needed(target, crossed_10k, births),
        "estimated_births_needed_for_300_crossed_20k": _estimated_births_needed(target, crossed_20k, births),
    }
    return counts


def _strict_birth_rows(
    birth_rows: list[dict[str, Any]],
    source_by_mint: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    best_by_mint: dict[str, dict[str, Any]] = {}
    for row in birth_rows:
        mint = _mint(row)
        if not mint:
            continue
        current = best_by_mint.get(mint)
        if current is None or _sort_time(row) < _sort_time(current):
            best_by_mint[mint] = row
    merged: list[dict[str, Any]] = []
    for mint, row in best_by_mint.items():
        source_rows = source_by_mint.get(mint, [])
        if source_rows:
            enriched = dict(source_rows[0])
            enriched.update({key: value for key, value in row.items() if value not in (None, "")})
            merged.append(enriched)
        else:
            merged.append(row)
    merged.sort(key=lambda row: (_sort_time(row), _mint(row)))
    return merged


def _first_threshold_row(paths: list[dict[str, Any]], threshold: float) -> dict[str, Any] | None:
    rows = [
        row
        for row in _fdv_paths(paths)
        if _num(row.get("fdv_proxy")) is not None and (_num(row.get("fdv_proxy")) or 0) >= threshold
    ]
    rows.sort(key=lambda row: (_num(row.get("timestamp") or row.get("observed_at")) or float("inf"), _num(row.get("fdv_proxy")) or 0))
    return rows[0] if rows else None


def _first_fdv_path(paths: list[dict[str, Any]]) -> dict[str, Any] | None:
    rows = _fdv_paths(paths)
    rows.sort(key=lambda row: (_num(row.get("timestamp") or row.get("observed_at")) or float("inf"), _num(row.get("fdv_proxy")) or 0))
    return rows[0] if rows else None


def _fdv_paths(paths: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in paths if not _is_create_event(row) and _num(row.get("fdv_proxy")) is not None]


def _is_birth_watch_candidate(row: dict[str, Any]) -> bool:
    if row.get("freshness_lane") == "birth_watch":
        return True
    if row.get("candidate_classification") == "pumpfun_birth_candidate_observed":
        return True
    return row.get("event_type") == "pumpfun_create" and "create_scanner" in str(row.get("source") or "")


def _is_create_event(row: dict[str, Any]) -> bool:
    return row.get("event_type") == "pumpfun_create"


def _create_time(
    candidate: dict[str, Any],
    *,
    source_rows: list[dict[str, Any]] | None = None,
    create_event: dict[str, Any] | None = None,
) -> float | None:
    values = [
        candidate.get("launch_time"),
        candidate.get("block_time"),
        candidate.get("transaction_time"),
        candidate.get("first_seen_time"),
        candidate.get("observed_at"),
    ]
    if source_rows:
        values = [source_rows[0].get("launch_time"), source_rows[0].get("block_time"), source_rows[0].get("transaction_time")] + values
    if create_event:
        values = [create_event.get("transaction_time"), create_event.get("timestamp"), create_event.get("observed_at")] + values
    for value in values:
        parsed = _num(value)
        if parsed is not None:
            return parsed
    return None


def _sort_time(row: dict[str, Any]) -> tuple[float, str]:
    value = _create_time(row)
    return (value if value is not None else float("inf"), str(row.get("observation_id") or ""))


def _group_by_mint(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        mint = _mint(row)
        if mint:
            grouped[mint].append(row)
    return grouped


def _mint(row: dict[str, Any]) -> str:
    return str(row.get("mint") or row.get("token_mint") or "")


def _time_bucket(seconds: float | None) -> str | None:
    if seconds is None:
        return None
    if seconds < 5:
        return "under_5s"
    if seconds < 15:
        return "5s_to_15s"
    if seconds < 30:
        return "15s_to_30s"
    if seconds < 60:
        return "30s_to_60s"
    if seconds < 120:
        return "1m_to_2m"
    if seconds < 300:
        return "2m_to_5m"
    if seconds < 600:
        return "5m_to_10m"
    return "10m_plus"


def _load_jsonl(path: Path) -> LoadedJsonl:
    if not path.exists():
        return LoadedJsonl(rows=[], malformed_rows=0, missing=True)
    rows: list[dict[str, Any]] = []
    malformed = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                value = json.loads(stripped)
            except json.JSONDecodeError:
                malformed += 1
                continue
            if isinstance(value, dict):
                rows.append(value)
            else:
                malformed += 1
    return LoadedJsonl(rows=rows, malformed_rows=malformed, missing=False)


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _write_summary_markdown(path: Path, summary: dict[str, Any]) -> Path:
    lines = [
        "# Forward Birth Funnel Sanity Summary",
        "",
        "- Guardrail: audit-only; no collection, Helius calls, trading, paper trading, validation, backtest, optimization, or ML.",
        f"- Total forward candidates: `{summary['total_forward_candidates']}`",
        f"- Raw funnel counts: `{summary['raw_funnel_counts']}`",
        f"- Strict deduped funnel counts: `{summary['strict_deduped_funnel_counts']}`",
        f"- Observed-followup-only counts: `{summary['observed_followup_only_funnel_counts']}`",
        f"- True/near-birth counts: `{summary['true_near_birth_funnel_counts']}`",
        f"- Duplicate counts: `{summary['duplicate_counts']}`",
        f"- Milestone provenance: `{summary['milestone_provenance_summary']}`",
        f"- Ordering summary: `{summary['milestone_ordering_summary']}`",
        f"- Freshness summary: `{summary['freshness_summary']}`",
        f"- Follow-up bias: `{summary['followup_bias_summary']}`",
        f"- Validity classification: `{summary['validity_classification']}`",
        f"- Recommendation: `{summary['recommendation']}`",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_status_markdown(path: Path, summary: dict[str, Any]) -> Path:
    lines = [
        "# Forward Birth Funnel Sanity Audit Status",
        "",
        "## Purpose",
        "",
        "This audit was created because the forward birth-to-trigger conversion numbers looked high enough to require a provenance, dedupe, freshness, and selection-bias check before continuing scale-up.",
        "",
        "## Counts",
        "",
        f"- Raw funnel numbers: `{summary['raw_funnel_counts']}`",
        f"- Strict deduped numbers: `{summary['strict_deduped_funnel_counts']}`",
        f"- Observed-followup-only numbers: `{summary['observed_followup_only_funnel_counts']}`",
        f"- True/near-birth observed numbers: `{summary['true_near_birth_funnel_counts']}`",
        "",
        "## Audit Results",
        "",
        f"- Milestone provenance result: `{summary['milestone_provenance_summary']}`",
        f"- Ordering result: `{summary['milestone_ordering_summary']}`",
        f"- Freshness result: `{summary['freshness_summary']}`",
        f"- Follow-up bias result: `{summary['followup_bias_summary']}`",
        f"- Validity classification: `{summary['validity_classification']}`",
        f"- Recommendation: `{summary['recommendation']}`",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _num(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _delta(start: float | None, end: float | None) -> float | None:
    if start is None or end is None:
        return None
    return end - start


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 6)


def _estimated_births_needed(target: int, crossed: int, births: int) -> int | None:
    if crossed <= 0 or births <= 0:
        return None
    return int(ceil(target / (crossed / births)))
