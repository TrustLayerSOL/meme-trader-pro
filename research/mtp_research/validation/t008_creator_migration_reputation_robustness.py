"""Robustness review for T008 creator migration reputation."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from research.mtp_research.validation.creator_migration_reputation_thesis import (
    build_t008_creator_migration_reputation_report,
    _build_launch_rows,
    _is_positive_migration_or_graduation,
    _migration_records,
    _mint,
    _read_jsonl,
)


REPORT_ID = "T008_creator_migration_reputation_robustness"
ROBUSTNESS_CLASSIFICATIONS = {"stable_weak_signal", "unstable_weak_signal", "no_robust_signal", "data_limited"}


def build_t008_creator_migration_reputation_robustness_report(
    *,
    candidates_path: Path | str,
    outcomes_path: Path | str,
    migration_labels_path: Path | str,
    min_split_bucket_count: int = 25,
    data_limited_min_launches: int = 100,
) -> dict[str, Any]:
    base_report = build_t008_creator_migration_reputation_report(
        candidates_path=candidates_path,
        outcomes_path=outcomes_path,
        migration_labels_path=migration_labels_path,
        dataset_scope="all_collected",
    )
    candidates = _read_jsonl(candidates_path)
    outcomes_by_mint = {_mint(row): row for row in _read_jsonl(outcomes_path) if _mint(row)}
    labels = _read_jsonl(migration_labels_path)
    all_records = _migration_records(labels)
    rows = base_report["launch_rows"]
    full_direction = _primary_direction(rows)
    chronological = _chronological_robustness(rows, full_direction, min_split_bucket_count)
    source = _source_robustness(candidates, outcomes_by_mint, labels, full_direction, min_split_bucket_count)
    concentration = _concentration_robustness(candidates, outcomes_by_mint, all_records, rows, full_direction)
    prior_launch_comparison = _prior_launch_count_comparison(rows)
    outlier = _outlier_sensitivity(rows, full_direction)
    classification = _classify_robustness(
        base_report=base_report,
        rows=rows,
        chronological=chronological,
        source=source,
        concentration=concentration,
        prior_launch_comparison=prior_launch_comparison,
        outlier=outlier,
        data_limited_min_launches=data_limited_min_launches,
    )
    return {
        "report_id": REPORT_ID,
        "original_t008_classification": base_report["final_classification"],
        "robustness_classification": classification,
        "launch_count": len(rows),
        "dataset": {
            "dataset_scope": "all_collected",
            "candidates_path": str(candidates_path),
            "outcomes_path": str(outcomes_path),
            "migration_labels_path": str(migration_labels_path),
            "true_market_cap_claims": "blocked",
            "valuation_semantics": "fdv_proxy_only",
        },
        "methodology_flags": [
            "research_only",
            "robustness_review_only",
            "no_thesis_promotion",
            "no_trading_rules",
            "no_profitability_claims",
            "no_entry_exit_logic",
            "no_threshold_optimization",
            "no_grid_search",
            "no_ml_black_boxes",
            "no_walk_forward_validation",
            "no_future_leakage",
            "fdv_proxy_not_true_market_cap",
        ],
        "full_sample_direction": full_direction,
        "full_sample_primary_bucket_table": base_report["primary_bucket_table"],
        "chronological_robustness": chronological,
        "source_robustness": source,
        "creator_concentration_robustness": concentration,
        "prior_launch_count_comparison": prior_launch_comparison,
        "outlier_sensitivity": outlier,
        "validation_recommended": classification == "stable_weak_signal",
        "warning_flags": _warning_flags(base_report, classification, source, concentration),
        "limitations": _limitations(),
        "next_recommendation": _next_recommendation(classification),
        "reproducible_command": _reproducible_command(candidates_path, outcomes_path, migration_labels_path),
    }


def write_t008_robustness_outputs(
    report: dict[str, Any],
    *,
    output_dir: Path | str,
    status_path: Path | str,
) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "T008_creator_migration_reputation_robustness_summary.json"
    markdown_path = output / "T008_creator_migration_reputation_robustness_summary.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(_markdown_summary(report), encoding="utf-8")
    status = Path(status_path)
    status.parent.mkdir(parents=True, exist_ok=True)
    status.write_text(_status_markdown(report, markdown_path, json_path), encoding="utf-8")
    return {"json_summary_path": json_path, "markdown_summary_path": markdown_path, "status_path": status}


def _chronological_robustness(
    rows: list[dict[str, Any]],
    full_direction: str,
    min_split_bucket_count: int,
) -> dict[str, Any]:
    ordered = sorted(rows, key=lambda row: (row.get("launch_ts") or 0, row.get("token_mint") or ""))
    halves = _split_rows(ordered, ["first_half", "second_half"])
    thirds = _split_rows(ordered, ["first_third", "middle_third", "final_third"])
    return {
        "first_half_second_half": _summarize_splits(halves, full_direction, min_split_bucket_count),
        "thirds": _summarize_splits(thirds, full_direction, min_split_bucket_count),
        "monthly_buckets": _monthly_buckets(ordered, full_direction, min_split_bucket_count),
    }


def _source_robustness(
    candidates: list[dict[str, Any]],
    outcomes_by_mint: dict[str, dict[str, Any]],
    labels: list[dict[str, Any]],
    full_direction: str,
    min_split_bucket_count: int,
) -> dict[str, Any]:
    pumpfun_labels = [row for row in labels if row.get("pumpfun_migrate_event_observed")]
    dex_only_labels = [
        row for row in labels
        if row.get("dex_pair_detected") and not row.get("pumpfun_migrate_event_observed")
    ]
    exclude_dex_labels = [
        row for row in labels
        if not (row.get("dex_pair_detected") and not row.get("pumpfun_migrate_event_observed"))
    ]
    return {
        "combined_labels": _source_view(candidates, outcomes_by_mint, labels, full_direction, min_split_bucket_count),
        "pumpfun_only": _source_view(candidates, outcomes_by_mint, pumpfun_labels, full_direction, min_split_bucket_count),
        "dexscreener_only": _source_view(candidates, outcomes_by_mint, dex_only_labels, full_direction, min_split_bucket_count),
        "exclude_dexscreener_only": _source_view(candidates, outcomes_by_mint, exclude_dex_labels, full_direction, min_split_bucket_count),
        "depends_mainly_on_dexscreener_proxy": len(dex_only_labels) > len(pumpfun_labels) * 3,
    }


def _source_view(
    candidates: list[dict[str, Any]],
    outcomes_by_mint: dict[str, dict[str, Any]],
    labels: list[dict[str, Any]],
    full_direction: str,
    min_split_bucket_count: int,
) -> dict[str, Any]:
    records = _migration_records(labels)
    rows = _build_launch_rows(candidates, outcomes_by_mint, records)
    table = _bucket_table(rows, "creator_prior_migration_or_graduation_count_bucket")
    direction = _primary_direction(rows)
    return {
        "launch_count": len(rows),
        "positive_label_count": sum(1 for row in labels if _is_positive_migration_or_graduation(row)),
        "migration_records_used": len(records),
        "primary_bucket_table": table,
        "direction": direction,
        "direction_matches_full_sample": direction == full_direction and direction != "flat_or_unusable",
        "data_limited": _table_data_limited(table, min_split_bucket_count),
    }


def _concentration_robustness(
    candidates: list[dict[str, Any]],
    outcomes_by_mint: dict[str, dict[str, Any]],
    records: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    full_direction: str,
) -> dict[str, Any]:
    four_plus_rows = [row for row in rows if row["features"]["creator_prior_migration_or_graduation_count_bucket"] == "4_plus"]
    two_plus_rows = [row for row in rows if row["features"]["creator_has_2plus_prior_migrations_or_graduations"]]
    top_creators = [creator for creator, _ in Counter(row.get("creator") for row in four_plus_rows if row.get("creator")).most_common(3)]
    extreme_prior_launch_creators = {
        row.get("creator")
        for row in rows
        if row.get("creator") and (row["features"].get("creator_prior_launch_count") or 0) >= 20
    }
    return {
        "four_plus_bucket": _dominance(four_plus_rows),
        "two_plus_bucket": _dominance(two_plus_rows),
        "exclude_dominant_creator_in_4plus_bucket": _exclusion_view(
            candidates, outcomes_by_mint, records, top_creators[:1], full_direction
        ),
        "exclude_top_1_creator_by_4plus_share": _exclusion_view(
            candidates, outcomes_by_mint, records, top_creators[:1], full_direction
        ),
        "exclude_top_3_creators_by_4plus_share": _exclusion_view(
            candidates, outcomes_by_mint, records, top_creators[:3], full_direction
        ),
        "exclude_creators_with_extreme_prior_launch_counts": _exclusion_view(
            candidates, outcomes_by_mint, records, sorted(extreme_prior_launch_creators), full_direction
        ),
    }


def _exclusion_view(
    candidates: list[dict[str, Any]],
    outcomes_by_mint: dict[str, dict[str, Any]],
    records: list[dict[str, Any]],
    excluded_creators: list[str],
    full_direction: str,
) -> dict[str, Any]:
    excluded = set(excluded_creators)
    filtered_candidates = [
        row for row in candidates if _creator(row) not in excluded
    ]
    filtered_records = [
        row for row in records if row.get("creator") not in excluded
    ]
    rows = _build_launch_rows(filtered_candidates, outcomes_by_mint, filtered_records)
    direction = _primary_direction(rows)
    return {
        "excluded_creators": sorted(excluded),
        "launch_count": len(rows),
        "primary_bucket_table": _bucket_table(rows, "creator_prior_migration_or_graduation_count_bucket"),
        "direction": direction,
        "direction_matches_full_sample": direction == full_direction and direction != "flat_or_unusable",
    }


def _prior_launch_count_comparison(rows: list[dict[str, Any]]) -> dict[str, Any]:
    migration_table = _bucket_table(rows, "creator_prior_migration_or_graduation_count_bucket")
    prior_launch_table = _bucket_table(rows, "creator_prior_launch_count_bucket")
    migration_delta = _first_last_delta(migration_table)
    launch_delta = _first_last_delta(prior_launch_table)
    if migration_delta is None and launch_delta is None:
        read = "both_weak_or_noisy"
    elif migration_delta is not None and (launch_delta is None or abs(migration_delta) > abs(launch_delta)):
        read = "migration_graduation_more_informative"
    elif launch_delta is not None and abs(launch_delta) > abs(migration_delta or 0):
        read = "raw_prior_launch_count_more_informative"
    else:
        read = "both_weak_or_noisy"
    if read == "raw_prior_launch_count_more_informative":
        prolific_share = _dominance([row for row in rows if row["features"].get("creator_prior_launch_count_bucket") == "20_plus"])
        if prolific_share["launch_count"] > 0:
            read = "migration_reputation_may_proxy_prolific_creator_visibility"
    return {
        "migration_graduation_bucket_table": migration_table,
        "prior_launch_count_bucket_table": prior_launch_table,
        "migration_graduation_first_last_runup_delta": migration_delta,
        "raw_prior_launch_count_first_last_runup_delta": launch_delta,
        "read": read,
    }


def _outlier_sensitivity(rows: list[dict[str, Any]], full_direction: str) -> dict[str, Any]:
    return {
        "exclude_top_1pct_fdv_proxy_runups": _outlier_view(rows, full_direction, "runup", 0.99),
        "exclude_top_5pct_fdv_proxy_runups": _outlier_view(rows, full_direction, "runup", 0.95),
        "exclude_extreme_drawdowns": _outlier_view(rows, full_direction, "drawdown", 0.01),
    }


def _outlier_view(rows: list[dict[str, Any]], full_direction: str, field: str, q: float) -> dict[str, Any]:
    values = sorted(
        value for value in (_outcome_value(row, field) for row in rows)
        if value is not None
    )
    cutoff = _quantile(values, q)
    if field == "drawdown":
        filtered = [row for row in rows if cutoff is None or _outcome_value(row, field) is None or (_outcome_value(row, field) or 0) >= cutoff]
    else:
        filtered = [row for row in rows if cutoff is None or _outcome_value(row, field) is None or (_outcome_value(row, field) or 0) <= cutoff]
    direction = _primary_direction(filtered)
    return {
        "launch_count": len(filtered),
        "cutoff": cutoff,
        "primary_bucket_table": _bucket_table(filtered, "creator_prior_migration_or_graduation_count_bucket"),
        "direction": direction,
        "direction_matches_full_sample": direction == full_direction and direction != "flat_or_unusable",
    }


def _classify_robustness(
    *,
    base_report: dict[str, Any],
    rows: list[dict[str, Any]],
    chronological: dict[str, Any],
    source: dict[str, Any],
    concentration: dict[str, Any],
    prior_launch_comparison: dict[str, Any],
    outlier: dict[str, Any],
    data_limited_min_launches: int,
) -> str:
    if len(rows) < data_limited_min_launches or base_report["final_classification"] == "data_limited":
        return "data_limited"
    if base_report["final_classification"] == "no_signal":
        return "no_robust_signal"
    chronological_ok = _chronological_ok(chronological)
    source_ok = (
        source["pumpfun_only"]["direction_matches_full_sample"]
        and source["dexscreener_only"]["direction_matches_full_sample"]
    )
    concentration_ok = (
        concentration["exclude_top_1_creator_by_4plus_share"]["direction_matches_full_sample"]
        and concentration["four_plus_bucket"]["dominant_creator_share"] < 0.5
    )
    outlier_ok = (
        outlier["exclude_top_1pct_fdv_proxy_runups"]["direction_matches_full_sample"]
        and outlier["exclude_top_5pct_fdv_proxy_runups"]["direction_matches_full_sample"]
    )
    if chronological_ok and source_ok and concentration_ok and outlier_ok:
        return "stable_weak_signal"
    if any([chronological_ok, source_ok, outlier_ok]) and prior_launch_comparison["read"] != "migration_reputation_may_proxy_prolific_creator_visibility":
        return "unstable_weak_signal"
    return "no_robust_signal"


def _chronological_ok(chronological: dict[str, Any]) -> bool:
    halves = chronological["first_half_second_half"]["split_summaries"]
    thirds = chronological["thirds"]["split_summaries"]
    half_matches = sum(1 for row in halves if row["direction_matches_full_sample"])
    third_matches = sum(1 for row in thirds if row["direction_matches_full_sample"])
    return half_matches == len(halves) and third_matches >= 2


def _summarize_splits(
    splits: dict[str, list[dict[str, Any]]],
    full_direction: str,
    min_split_bucket_count: int,
) -> dict[str, Any]:
    summaries = []
    for name, rows in splits.items():
        table = _bucket_table(rows, "creator_prior_migration_or_graduation_count_bucket")
        direction = _primary_direction(rows)
        summaries.append(
            {
                "split": name,
                "launch_count": len(rows),
                "primary_bucket_counts": _bucket_counts(rows),
                "primary_bucket_table": table,
                "direction": direction,
                "direction_matches_full_sample": direction == full_direction and direction != "flat_or_unusable",
                "data_limited": _table_data_limited(table, min_split_bucket_count),
            }
        )
    return {
        "split_summaries": summaries,
        "matching_direction_count": sum(1 for row in summaries if row["direction_matches_full_sample"]),
        "data_limited_split_count": sum(1 for row in summaries if row["data_limited"]),
    }


def _monthly_buckets(
    rows: list[dict[str, Any]],
    full_direction: str,
    min_split_bucket_count: int,
) -> dict[str, Any]:
    # The launch census currently spans a short window, so monthly buckets are only emitted when
    # timestamp diversity actually exists.
    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        launch_ts = row.get("launch_ts")
        if launch_ts is None:
            continue
        month = _month_key(int(launch_ts))
        buckets.setdefault(month, []).append(row)
    if len(buckets) < 2:
        return {"available": False, "reason": "fewer_than_two_month_buckets", "split_summaries": []}
    return {
        "available": True,
        **_summarize_splits(dict(sorted(buckets.items())), full_direction, min_split_bucket_count),
    }


def _split_rows(rows: list[dict[str, Any]], names: list[str]) -> dict[str, list[dict[str, Any]]]:
    result = {}
    count = len(names)
    for index, name in enumerate(names):
        start = int(index * len(rows) / count)
        end = int((index + 1) * len(rows) / count)
        result[name] = rows[start:end]
    return result


def _bucket_table(rows: list[dict[str, Any]], feature: str) -> list[dict[str, Any]]:
    if feature == "creator_prior_migration_or_graduation_count_bucket":
        buckets = ("0", "1", "2_to_3", "4_plus")
    elif feature == "creator_prior_launch_count_bucket":
        buckets = ("0", "1", "2_to_4", "5_to_19", "20_plus")
    else:
        buckets = tuple(sorted({str(row["features"].get(feature)) for row in rows}))
    return [_bucket_summary(bucket, [row for row in rows if row["features"].get(feature) == bucket]) for bucket in buckets]


def _bucket_summary(bucket: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "bucket": bucket,
        "launch_count": len(rows),
        "sample_count": len(rows),
        "median_fdv_proxy_runup_120m": _median([_outcome_value(row, "runup") for row in rows]),
        "median_fdv_proxy_drawdown_120m": _median([_outcome_value(row, "drawdown") for row in rows]),
        "price_available_120m_rate": _true_rate(row["outcomes"].get("price_available_120m") for row in rows),
        "liquidity_proxy_available_120m_rate": _true_rate(row["outcomes"].get("liquidity_proxy_available_120m") for row in rows),
    }


def _primary_direction(rows: list[dict[str, Any]]) -> str:
    table = _bucket_table(rows, "creator_prior_migration_or_graduation_count_bucket")
    delta = _first_last_delta(table)
    if delta is None or delta == 0:
        return "flat_or_unusable"
    return "higher_prior_history_higher_runup" if delta > 0 else "higher_prior_history_lower_runup"


def _first_last_delta(table: list[dict[str, Any]]) -> float | None:
    non_empty = [row for row in table if row.get("sample_count", 0) > 0 and row.get("median_fdv_proxy_runup_120m") is not None]
    if len(non_empty) < 2:
        return None
    return non_empty[-1]["median_fdv_proxy_runup_120m"] - non_empty[0]["median_fdv_proxy_runup_120m"]


def _table_data_limited(table: list[dict[str, Any]], min_bucket_count: int) -> bool:
    non_empty = [row for row in table if row.get("sample_count", 0) > 0]
    if len(non_empty) < 2:
        return True
    return min(row["sample_count"] for row in non_empty) < min_bucket_count


def _bucket_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    return dict(Counter(row["features"]["creator_prior_migration_or_graduation_count_bucket"] for row in rows))


def _dominance(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row.get("creator") for row in rows if row.get("creator"))
    if not rows or not counts:
        return {"launch_count": len(rows), "dominant_creator": None, "dominant_creator_count": 0, "dominant_creator_share": 0}
    creator, count = counts.most_common(1)[0]
    return {
        "launch_count": len(rows),
        "dominant_creator": creator,
        "dominant_creator_count": count,
        "dominant_creator_share": count / len(rows),
    }


def _warning_flags(
    base_report: dict[str, Any],
    classification: str,
    source: dict[str, Any],
    concentration: dict[str, Any],
) -> list[str]:
    warnings = ["true_market_cap_claims_blocked", "fdv_proxy_only"]
    if source["depends_mainly_on_dexscreener_proxy"]:
        warnings.append("migration_evidence_depends_mainly_on_dexscreener_proxy")
    if source["pumpfun_only"]["data_limited"]:
        warnings.append("pumpfun_only_source_view_data_limited")
    if concentration["four_plus_bucket"]["dominant_creator_share"] >= 0.5:
        warnings.append("four_plus_bucket_creator_concentrated")
    if base_report["migration_vs_raw_launch_count_read"] == "raw_prior_launch_count_more_informative_descriptively":
        warnings.append("raw_prior_launch_count_more_informative_than_migration_count")
    if classification in {"no_robust_signal", "unstable_weak_signal"}:
        warnings.append("do_not_promote_t008")
    return warnings


def _limitations() -> list[str]:
    return [
        "This is a robustness review only, not validation or thesis promotion.",
        "DexScreener pair detection remains a graduation proxy, not ground-truth Pump.fun migration.",
        "Pump.fun migration-event evidence is sparse.",
        "FDV proxy is not true market cap.",
        "No trading rule, profitability claim, entry logic, or validation claim is made.",
    ]


def _next_recommendation(classification: str) -> str:
    if classification == "stable_weak_signal":
        return "design a formal validation plan later; do not run validation in this sprint"
    return "park T008 or improve migration-label quality before further testing"


def _markdown_summary(report: dict[str, Any]) -> str:
    lines = [
        "# T008 Creator Migration Reputation Robustness",
        "",
        f"- Original T008 classification: `{report['original_t008_classification']}`",
        f"- Robustness classification: `{report['robustness_classification']}`",
        f"- Launch count: `{report['launch_count']}`",
        f"- Full-sample direction: `{report['full_sample_direction']}`",
        f"- Validation recommended: `{report['validation_recommended']}`",
        f"- Warning flags: `{report['warning_flags']}`",
        "",
        "## Source Robustness",
        "",
    ]
    for key, value in report["source_robustness"].items():
        if not isinstance(value, dict):
            continue
        lines.append(
            f"- `{key}`: records `{value['migration_records_used']}`, "
            f"direction `{value['direction']}`, matches full sample `{value['direction_matches_full_sample']}`, "
            f"data limited `{value['data_limited']}`"
        )
    lines.extend([
        "",
        "## Concentration Robustness",
        "",
        f"- Four-plus dominant creator share: `{report['creator_concentration_robustness']['four_plus_bucket']['dominant_creator_share']:.4f}`",
        f"- Two-plus dominant creator share: `{report['creator_concentration_robustness']['two_plus_bucket']['dominant_creator_share']:.4f}`",
        "",
        "## Prior Launch Count Comparison",
        "",
        f"`{report['prior_launch_count_comparison']['read']}`",
        "",
        "## Next Recommendation",
        "",
        report["next_recommendation"],
        "",
        "## Reproducible Command",
        "",
        "```bash",
        report["reproducible_command"],
        "```",
    ])
    return "\n".join(lines) + "\n"


def _status_markdown(report: dict[str, Any], markdown_path: Path, json_path: Path) -> str:
    return "\n".join(
        [
            "# T008 Creator Migration Reputation Robustness Status",
            "",
            f"- Original T008 classification: `{report['original_t008_classification']}`",
            f"- Robustness classification: `{report['robustness_classification']}`",
            f"- Launches analyzed: `{report['launch_count']}`",
            "",
            "## Chronological Stability Result",
            "",
            f"- First/second half matching splits: `{report['chronological_robustness']['first_half_second_half']['matching_direction_count']}`",
            f"- Thirds matching splits: `{report['chronological_robustness']['thirds']['matching_direction_count']}`",
            "",
            "## Source Sensitivity Result",
            "",
            f"- Combined records: `{report['source_robustness']['combined_labels']['migration_records_used']}`",
            f"- Pump.fun-only records: `{report['source_robustness']['pumpfun_only']['migration_records_used']}`",
            f"- DexScreener-only records: `{report['source_robustness']['dexscreener_only']['migration_records_used']}`",
            f"- Depends mainly on DexScreener proxy: `{report['source_robustness']['depends_mainly_on_dexscreener_proxy']}`",
            "",
            "## Creator Concentration Result",
            "",
            f"- Four-plus dominant creator share: `{report['creator_concentration_robustness']['four_plus_bucket']['dominant_creator_share']:.4f}`",
            f"- Two-plus dominant creator share: `{report['creator_concentration_robustness']['two_plus_bucket']['dominant_creator_share']:.4f}`",
            "",
            "## Prior Launch Count Comparison",
            "",
            f"`{report['prior_launch_count_comparison']['read']}`",
            "",
            "## Outlier Sensitivity Result",
            "",
            f"- Exclude top 1% direction matches full sample: `{report['outlier_sensitivity']['exclude_top_1pct_fdv_proxy_runups']['direction_matches_full_sample']}`",
            f"- Exclude top 5% direction matches full sample: `{report['outlier_sensitivity']['exclude_top_5pct_fdv_proxy_runups']['direction_matches_full_sample']}`",
            f"- Exclude extreme drawdowns direction matches full sample: `{report['outlier_sensitivity']['exclude_extreme_drawdowns']['direction_matches_full_sample']}`",
            "",
            "## Validation Recommended",
            "",
            f"`{report['validation_recommended']}`",
            "",
            "## Limitations",
            "",
            *[f"- {item}" for item in report["limitations"]],
            "",
            "## Next Recommendation",
            "",
            report["next_recommendation"],
            "",
            f"- Markdown summary: `{markdown_path}`",
            f"- JSON summary: `{json_path}`",
            "- No thesis promotion was performed.",
            "- No walk-forward validation was run.",
            "- No trading rules were generated.",
            "- No profitability claims were generated.",
            "",
        ]
    )


def _reproducible_command(candidates_path: Path | str, outcomes_path: Path | str, migration_labels_path: Path | str) -> str:
    return (
        "./trading_env/bin/python -m research.mtp_research.validation.run_t008_creator_migration_reputation_robustness "
        f"--candidates-path \"{candidates_path}\" "
        f"--outcomes-path \"{outcomes_path}\" "
        f"--migration-labels-path \"{migration_labels_path}\""
    )


def _creator(row: dict[str, Any]) -> str | None:
    metadata = row.get("metadata_json") or {}
    value = row.get("creator") or row.get("creator_deployer") or row.get("creator_wallet") or metadata.get("creator_deployer")
    return str(value) if value else None


def _outcome_value(row: dict[str, Any], field: str) -> float | None:
    key = "fdv_proxy_runup_120m" if field == "runup" else "fdv_proxy_drawdown_120m"
    value = row["outcomes"].get(key)
    return float(value) if value is not None else None


def _median(values: list[float | None]) -> float | None:
    clean = sorted(value for value in values if value is not None)
    if not clean:
        return None
    midpoint = len(clean) // 2
    if len(clean) % 2:
        return clean[midpoint]
    return (clean[midpoint - 1] + clean[midpoint]) / 2


def _true_rate(values) -> float | None:
    vals = list(values)
    if not vals:
        return None
    return sum(1 for value in vals if bool(value)) / len(vals)


def _quantile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    index = (len(values) - 1) * q
    lower = int(index)
    upper = min(lower + 1, len(values) - 1)
    fraction = index - lower
    return values[lower] * (1 - fraction) + values[upper] * fraction


def _month_key(timestamp: int) -> str:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m")

