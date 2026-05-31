"""Span summaries for offline evidence artifacts."""

from __future__ import annotations

from typing import Any, Iterable


def summarize_raw_span(raw_records: Iterable[Any]) -> dict[str, Any]:
    return _summarize(raw_records, time_attr="block_time")


def summarize_normalized_event_span(events: Iterable[Any]) -> dict[str, Any]:
    return _summarize(events, time_attr="block_time")


def summarize_feature_span(feature_snapshots: Iterable[Any]) -> dict[str, Any]:
    return _summarize(feature_snapshots, time_attr="snapshot_ts")


def summarize_outcome_span(outcome_labels: Iterable[Any]) -> dict[str, Any]:
    return _summarize(outcome_labels, time_attr="snapshot_ts")


def summarize_dataset_span(dataset_rows: Iterable[Any]) -> dict[str, Any]:
    return _summarize(dataset_rows, time_attr="snapshot_ts")


def compare_artifact_spans(
    *,
    raw_records: Iterable[Any] = (),
    normalized_events: Iterable[Any] = (),
    feature_snapshots: Iterable[Any] = (),
    clean_outcome_labels: Iterable[Any] = (),
    clean_dataset_rows: Iterable[Any] = (),
    diagnostic_outcome_labels: Iterable[Any] = (),
    diagnostic_dataset_rows: Iterable[Any] = (),
) -> dict[str, Any]:
    report = {
        "raw": summarize_raw_span(raw_records),
        "normalized_events": summarize_normalized_event_span(normalized_events),
        "feature_snapshots": summarize_feature_span(feature_snapshots),
        "clean_outcomes": summarize_outcome_span(clean_outcome_labels),
        "clean_dataset": summarize_dataset_span(clean_dataset_rows),
        "diagnostic_outcomes": summarize_outcome_span(diagnostic_outcome_labels),
        "diagnostic_dataset": summarize_dataset_span(diagnostic_dataset_rows),
        "warning_flags": [],
    }
    warnings: list[str] = report["warning_flags"]
    raw_span = report["raw"]["time_span_seconds"]
    feature_span = report["feature_snapshots"]["time_span_seconds"]
    raw_token_count = report["raw"]["token_count"]

    for name in (
        "normalized_events",
        "feature_snapshots",
        "clean_outcomes",
        "clean_dataset",
        "diagnostic_outcomes",
        "diagnostic_dataset",
    ):
        span = report[name]["time_span_seconds"]
        token_count = report[name]["token_count"]
        if raw_span and span is not None and span < raw_span * 0.5:
            warnings.append(f"{name}_span_much_smaller_than_raw")
        if feature_span and name not in {"feature_snapshots"} and span is not None and span < feature_span * 0.5:
            warnings.append(f"{name}_span_much_smaller_than_features")
        if raw_token_count and token_count and token_count < raw_token_count * 0.5:
            warnings.append(f"{name}_token_count_much_smaller_than_raw")
    report["warning_flags"] = sorted(set(warnings))
    return report


def _summarize(records: Iterable[Any], *, time_attr: str) -> dict[str, Any]:
    rows = list(records)
    times = [
        int(getattr(row, time_attr))
        for row in rows
        if getattr(row, time_attr, None) is not None
    ]
    token_mints = {
        getattr(row, "token_mint")
        for row in rows
        if getattr(row, "token_mint", None)
    }
    time_min = min(times) if times else None
    time_max = max(times) if times else None
    return {
        "row_count": len(rows),
        "token_count": len(token_mints),
        "time_min": time_min,
        "time_max": time_max,
        "time_span_seconds": max(0, time_max - time_min) if time_min is not None and time_max is not None else None,
    }
