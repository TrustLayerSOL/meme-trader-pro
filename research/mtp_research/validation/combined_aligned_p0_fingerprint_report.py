"""Combined aligned P0 structural fingerprint dataset and report."""

from __future__ import annotations

import csv
import json
import math
from collections import Counter
from pathlib import Path
from statistics import median
from typing import Any

from research.mtp_research.data_paths import data_lake_path


REPORT_ID = "combined_aligned_p0_fingerprint_report_v0"
DEFAULT_ORIGINAL_STRUCTURAL_PATH = data_lake_path(
    "data", "backtests", "structural_enrichment", "aligned_p0_medium_structural_features.parquet"
)
DEFAULT_BALANCED_STRUCTURAL_PATH = Path(
    "/Volumes/ORICO/MemeTraderPro/aux/aligned_p0_second_run_275/data/backtests/structural_enrichment/aligned_p0_medium_structural_features.parquet"
)
DEFAULT_REMAINING_STRUCTURAL_PATH = Path(
    "/Volumes/ORICO/MemeTraderPro/aux/aligned_p0_remaining_available/data/backtests/structural_enrichment/aligned_p0_medium_structural_features.parquet"
)
DEFAULT_OUTPUT_DIR = data_lake_path(
    "data", "backtests", "diagnostics", "reports", "combined_aligned_p0_fingerprint"
)
DEFAULT_DATASET_PARQUET_PATH = data_lake_path(
    "data", "backtests", "structural_enrichment", "combined_aligned_p0_structural_fingerprint.parquet"
)
DEFAULT_DATASET_JSONL_PATH = data_lake_path(
    "data", "backtests", "structural_enrichment", "combined_aligned_p0_structural_fingerprint.jsonl"
)
DEFAULT_STATUS_PATH = Path("theses/COMBINED_ALIGNED_P0_FINGERPRINT_STATUS.md")

TIER_ORDER = [
    "reached_20k_but_never_50k",
    "reached_50k_but_never_100k",
    "reached_100k_but_never_200k",
    "reached_200k_but_never_500k",
    "reached_500k_but_never_1m",
    "reached_1m_plus",
]
VISIBLE_FEATURES = [
    "fdv_per_event_at_20k",
    "fdv_per_buy_at_20k",
    "fdv_per_active_wallet_at_20k",
    "event_count_at_20k",
    "active_wallets_at_20k",
    "buy_sell_ratio_at_20k",
]
EARLY_BUYER_FEATURES = [
    "repeated_buyer_quality_proxy",
    "early_buyer_with_prior_runner_count",
    "early_buyer_with_prior_500k_count",
    "early_buyer_with_prior_1m_count",
    "early_buyer_prior_failure_count",
]
TOP_HOLDER_FEATURES = ["top_holder_share_proxy", "top_10_holder_share_proxy"]
FUNDER_FEATURES = [
    "shared_funding_proxy",
    "time_linked_funding_proxy",
    "launches_sharing_funder",
    "creators_sharing_funder",
]
CREATOR_LINK_FEATURES = ["creator_to_early_buyer_link_proxy", "creator_to_top_holder_link_proxy"]
COMPARISON_FEATURES = VISIBLE_FEATURES + EARLY_BUYER_FEATURES + TOP_HOLDER_FEATURES + FUNDER_FEATURES + CREATOR_LINK_FEATURES
ENTRY_FEATURES = set(VISIBLE_FEATURES + EARLY_BUYER_FEATURES + TOP_HOLDER_FEATURES + FUNDER_FEATURES + CREATOR_LINK_FEATURES)
EXIT_FEATURES = {"top_holder_behavior_proxy_available", "full_chain_holder_snapshot_confirmed"}


def build_combined_aligned_p0_fingerprint_report(
    *,
    original_structural_path: Path | str = DEFAULT_ORIGINAL_STRUCTURAL_PATH,
    balanced_structural_path: Path | str = DEFAULT_BALANCED_STRUCTURAL_PATH,
    remaining_structural_path: Path | str = DEFAULT_REMAINING_STRUCTURAL_PATH,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    dataset_parquet_path: Path | str = DEFAULT_DATASET_PARQUET_PATH,
    dataset_jsonl_path: Path | str = DEFAULT_DATASET_JSONL_PATH,
    status_path: Path | str = DEFAULT_STATUS_PATH,
) -> tuple[dict[str, Any], dict[str, Path]]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    inputs = [
        ("original_medium", Path(original_structural_path)),
        ("balanced_second_pass", Path(balanced_structural_path)),
        ("remaining_available", Path(remaining_structural_path)),
    ]
    loaded = []
    missing_paths = []
    for source_run, path in inputs:
        rows = _read_records(path)
        if not rows:
            missing_paths.append(str(path))
        loaded.extend(_normalize_row(row, source_run) for row in rows)
    combined, duplicate_count = _dedupe_rows(loaded)
    combined = sorted(combined, key=lambda row: (TIER_ORDER.index(row["milestone_tier"]) if row["milestone_tier"] in TIER_ORDER else 99, row.get("launch_ts") or 0, row["mint"]))
    dataset_jsonl = Path(dataset_jsonl_path)
    dataset_parquet = Path(dataset_parquet_path)
    _write_jsonl(dataset_jsonl, combined)
    _write_parquet(dataset_parquet, combined)

    coverage_rows, coverage = _coverage_audit(combined, duplicate_count)
    tier_rows = _tier_feature_comparison(combined)
    entry_exit_rows = _entry_exit_rows()
    fingerprints = _candidate_fingerprints(combined)
    strongest_visible = _strongest_features(tier_rows, VISIBLE_FEATURES)
    strongest_hidden = _strongest_features(tier_rows, [f for f in COMPARISON_FEATURES if f not in VISIBLE_FEATURES])
    report = {
        "report_id": REPORT_ID,
        "report_type": "combined_aligned_p0_structural_fingerprint",
        "readiness_classification": _readiness(coverage),
        "methodology_flags": [
            "research_only",
            "descriptive_fingerprint_report_only",
            "not_a_thesis",
            "no_thesis_promotion",
            "no_validation_run",
            "no_backtest",
            "no_walk_forward_validation",
            "no_live_trading",
            "no_paper_trading",
            "no_auto_buy_sell",
            "no_private_key_logic",
            "no_wallet_execution",
            "no_order_routing",
            "no_alerts",
            "no_trading_logic",
            "no_profitability_claims",
            "no_strategy_generation",
            "no_entry_exit_logic",
            "no_threshold_optimization",
            "no_grid_search",
            "no_ml_black_boxes",
            "neutral_proxy_labels_only",
            "fdv_proxy_not_true_market_cap",
            "no_helius_calls",
        ],
        "input_paths": {source: str(path) for source, path in inputs},
        "missing_input_paths": missing_paths,
        "dataset_paths": {"parquet": str(dataset_parquet), "jsonl": str(dataset_jsonl)},
        "coverage_audit": coverage,
        "milestone_tier_counts": dict(Counter(row["milestone_tier"] for row in combined)),
        "strongest_visible_features": strongest_visible,
        "strongest_hidden_structural_features": strongest_hidden,
        "candidate_fingerprints": fingerprints,
        "commonality_questions": _commonality_questions(strongest_visible, strongest_hidden),
        "next_recommendation": _next_recommendation(coverage),
        "limitations": _limitations(coverage),
    }
    paths = _write_outputs(
        report=report,
        coverage_rows=coverage_rows,
        tier_rows=tier_rows,
        fingerprints=fingerprints,
        entry_exit_rows=entry_exit_rows,
        output_dir=output,
        status_path=Path(status_path),
    )
    paths["dataset_jsonl_path"] = dataset_jsonl
    paths["dataset_parquet_path"] = dataset_parquet
    return report, paths


def _normalize_row(row: dict[str, Any], source_run: str) -> dict[str, Any]:
    buy = _first_number(row, "buy_count_at_20k", "buy_count", "early_buyer_wallet_count")
    sell = _first_number(row, "sell_count_at_20k", "sell_count")
    event_count = _first_number(row, "event_count_at_20k", "tx_count")
    active = _first_number(row, "active_wallets_at_20k", "active_wallets", "early_buyer_wallet_count")
    early_prior = _first_number(row, "early_buyer_with_prior_history_count")
    early_count = _first_number(row, "early_buyer_wallet_count")
    shared = _bool(row.get("shared_funding_proxy"))
    timed = _bool(row.get("time_linked_funding_proxy"))
    all_three = _bool(row.get("has_all_three_p0_layers"))
    return {
        "launch_id": str(row.get("launch_id") or row.get("mint") or ""),
        "mint": str(row.get("mint") or row.get("token_mint") or ""),
        "creator": _clean(row.get("creator")),
        "launch_time": row.get("launch_time_utc") or row.get("launch_time") or row.get("launch_ts"),
        "launch_ts": _int_or_none(row.get("launch_ts")),
        "launch_date": str(row.get("launch_date") or "")[:10],
        "milestone_tier": str(row.get("milestone_tier") or "unknown"),
        "peak_fdv_proxy": _first_number(row, "peak_fdv_proxy", "peak_valuation_proxy", "fdv_proxy"),
        "trigger_20k_time": row.get("trigger_20k_time") or row.get("crossing_20k_age"),
        "source_run": source_run,
        "is_balanced_sample": source_run in {"original_medium", "balanced_second_pass"},
        "is_leftover_sample": source_run == "remaining_available",
        "is_date_concentrated_sample": source_run == "remaining_available",
        "has_early_buyer_history": _bool(row.get("has_early_buyer_wallet_history")),
        "has_top_holder_replay": _bool(row.get("has_top_holder_replay")),
        "has_creator_funder_graph": _bool(row.get("has_creator_funder_graph")),
        "has_all_three_p0_layers": all_three,
        "fdv_per_event_at_20k": _first_number(row, "fdv_per_event_at_20k"),
        "fdv_per_buy_at_20k": _first_number(row, "fdv_per_buy_at_20k"),
        "fdv_per_active_wallet_at_20k": _first_number(row, "fdv_per_active_wallet_at_20k"),
        "event_count_at_20k": event_count,
        "buy_count_at_20k": buy,
        "sell_count_at_20k": sell,
        "active_wallets_at_20k": active,
        "buy_sell_ratio_at_20k": _ratio(buy, sell),
        "early_buyer_wallet_count": early_count,
        "early_buyer_with_prior_history_count": early_prior,
        "early_buyer_with_prior_runner_count": _first_number(row, "early_buyer_with_prior_runner_count", "early_buyer_with_prior_history_count"),
        "early_buyer_with_prior_100k_count": _first_number(row, "early_buyer_with_prior_100k_count"),
        "early_buyer_with_prior_500k_count": _first_number(row, "early_buyer_with_prior_500k_count"),
        "early_buyer_with_prior_1m_count": _first_number(row, "early_buyer_with_prior_1m_count"),
        "early_buyer_prior_failure_count": _first_number(row, "early_buyer_prior_failure_count"),
        "repeated_buyer_quality_proxy": _ratio(early_prior, early_count),
        "early_buyer_history_confidence": "medium" if _bool(row.get("has_early_buyer_wallet_history")) else "none",
        "top_holder_share_proxy": _first_number(row, "top_holder_share_proxy"),
        "top_10_holder_share_proxy": _first_number(row, "top_10_holder_share_proxy"),
        "top_holder_addresses_available": False,
        "top_10_holder_addresses_available": False,
        "top_holder_behavior_proxy_available": _first_number(row, "top_holder_share_proxy") is not None,
        "top_holder_replay_confidence": row.get("top_holder_replay_confidence") or "none",
        "full_chain_holder_snapshot_confirmed": _bool(row.get("is_confirmed_full_chain_snapshot")),
        "candidate_funder_available": bool(_clean(row.get("candidate_funder"))),
        "candidate_funder": _clean(row.get("candidate_funder")),
        "candidate_funder_confidence": row.get("candidate_funder_confidence") or "none",
        "shared_funding_proxy": shared,
        "time_linked_funding_proxy": timed,
        "launches_sharing_funder": _first_number(row, "launches_sharing_funder") or (2 if shared else 0),
        "creators_sharing_funder": _first_number(row, "creators_sharing_funder") or (2 if shared else 0),
        "common_funder_candidate_id": row.get("common_funder_candidate_id") or (_clean(row.get("candidate_funder")) if shared else None),
        "creator_to_early_buyer_link_proxy": _first_number(row, "creator_to_early_buyer_link_proxy"),
        "creator_to_top_holder_link_proxy": _first_number(row, "creator_to_top_holder_link_proxy"),
        "funder_graph_confidence": row.get("candidate_funder_confidence") or "none",
        "p0_structural_complete": all_three,
        "p0_structural_confidence": "high" if all_three else "partial",
        "p0_structural_missing_reason": _missing_reason(row),
    }


def _dedupe_rows(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    priority = {"remaining_available": 3, "balanced_second_pass": 2, "original_medium": 1}
    by_launch: dict[str, dict[str, Any]] = {}
    source_sets: dict[str, set[str]] = {}
    for row in rows:
        key = row["launch_id"] or row["mint"]
        if not key:
            continue
        source_sets.setdefault(key, set()).add(row["source_run"])
        current = by_launch.get(key)
        if current is None or (
            int(row["has_all_three_p0_layers"]) > int(current["has_all_three_p0_layers"])
            or priority[row["source_run"]] > priority[current["source_run"]]
        ):
            by_launch[key] = row
    duplicates = sum(max(0, len(sources) - 1) for sources in source_sets.values())
    output = []
    for key, row in by_launch.items():
        sources = source_sets[key]
        if len(sources) > 1:
            row = {**row, "source_run": "duplicate_resolved", "is_balanced_sample": True, "is_leftover_sample": "remaining_available" in sources}
        output.append(row)
    return output, duplicates


def _coverage_audit(rows: list[dict[str, Any]], duplicate_count: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    date_counts = Counter(row["launch_date"] for row in rows if row.get("launch_date"))
    creator_counts = Counter(row.get("creator") or "unknown" for row in rows)
    source_counts = Counter(row["source_run"] for row in rows)
    tier_counts = Counter(row["milestone_tier"] for row in rows)
    coverage = {
        "total_unique_launches": len(rows),
        "all_three_p0_launches": sum(1 for row in rows if row["has_all_three_p0_layers"]),
        "duplicate_rows_resolved": duplicate_count,
        "rows_by_source_run": dict(source_counts),
        "rows_by_milestone_tier": dict(tier_counts),
        "top_date_share": _top_share(date_counts, len(rows), 1),
        "top_3_date_share": _top_share(date_counts, len(rows), 3),
        "top_creator_share": _top_share(creator_counts, len(rows), 1),
        "top_3_creator_share": _top_share(creator_counts, len(rows), 3),
        "balanced_sample_rows": sum(1 for row in rows if row["is_balanced_sample"]),
        "leftover_sample_rows": sum(1 for row in rows if row["is_leftover_sample"]),
        "all_three_coverage_pct": _pct(sum(1 for row in rows if row["has_all_three_p0_layers"]), len(rows)),
    }
    csv_rows = []
    for source in sorted(source_counts):
        members = [row for row in rows if row["source_run"] == source]
        csv_rows.append({"audit_type": "source_run", "name": source, "row_count": len(members), "all_three_count": sum(1 for row in members if row["has_all_three_p0_layers"])})
    for tier in TIER_ORDER:
        members = [row for row in rows if row["milestone_tier"] == tier]
        csv_rows.append({"audit_type": "milestone_tier", "name": tier, "row_count": len(members), "all_three_count": sum(1 for row in members if row["has_all_three_p0_layers"])})
    for date, count in date_counts.most_common(20):
        csv_rows.append({"audit_type": "launch_date", "name": date, "row_count": count, "all_three_count": ""})
    return csv_rows, coverage


def _tier_feature_comparison(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    subsets = {
        "balanced_sample": [row for row in rows if row["is_balanced_sample"] and not row["is_leftover_sample"]],
        "leftover_sample": [row for row in rows if row["is_leftover_sample"]],
        "combined_sample": rows,
    }
    for subset_name, subset_rows in subsets.items():
        for tier in TIER_ORDER:
            tier_rows = [row for row in subset_rows if row["milestone_tier"] == tier]
            for feature in COMPARISON_FEATURES:
                vals = [_number(row.get(feature)) for row in tier_rows]
                numeric = [value for value in vals if value is not None]
                output.append(
                    {
                        "evidence_subset": subset_name,
                        "milestone_tier": tier,
                        "feature": feature,
                        **_distribution(numeric),
                        "missing_count": len(tier_rows) - len(numeric),
                        "coverage_pct": _pct(len(numeric), len(tier_rows)),
                    }
                )
    return output


def _candidate_fingerprints(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    high_tiers = {"reached_500k_but_never_1m", "reached_1m_plus"}
    configs = [
        ("High FDV efficiency + repeated runner buyers", ["fdv_per_buy_at_20k"], ["repeated_buyer_quality_proxy"]),
        ("High FDV efficiency + shared funder/time-linked funding", ["fdv_per_event_at_20k"], ["shared_funding_proxy", "time_linked_funding_proxy"]),
        ("Low event density + stable top-holder structure", ["event_count_at_20k"], ["top_holder_share_proxy", "top_10_holder_share_proxy"]),
        ("Fast expansion + low early-buyer failure history", ["fdv_per_active_wallet_at_20k"], ["early_buyer_prior_failure_count"]),
        ("High runner-wallet quality + low creator distribution", ["buy_sell_ratio_at_20k"], ["repeated_buyer_quality_proxy", "top_10_holder_share_proxy"]),
    ]
    output = []
    for name, visible, hidden in configs:
        support_rows = [row for row in rows if row["milestone_tier"] in high_tiers and all(row.get(f) is not None for f in visible + hidden)]
        output.append(
            {
                "name": name,
                "visible_features": ";".join(visible),
                "hidden_structural_features": ";".join(hidden),
                "milestone_tiers_where_it_appears": ";".join(sorted({row["milestone_tier"] for row in support_rows})),
                "sample_support": len(support_rows),
                "balanced_support": sum(1 for row in support_rows if row["is_balanced_sample"] and not row["is_leftover_sample"]),
                "leftover_support": sum(1 for row in support_rows if row["is_leftover_sample"]),
                "entry_side_or_exit_side": "entry_side",
                "missing_fields": "true_market_cap;top_holder_addresses" if "top_holder" in name.lower() else "true_market_cap",
                "why_it_might_matter": "descriptive structural_proxy candidate for later formal testing",
                "what_needs_formal_testing_later": "frozen thesis design with validation and no threshold search",
            }
        )
    return output


def _entry_exit_rows() -> list[dict[str, Any]]:
    rows = []
    for feature in sorted(ENTRY_FEATURES | EXIT_FEATURES):
        rows.append(
            {
                "feature_name": feature,
                "feature_side": "entry_side" if feature in ENTRY_FEATURES else "exit_or_path_side",
                "neutral_label": _neutral_label(feature),
                "available_now": True,
                "notes": "descriptive only; no rule, validation, or trading claim",
            }
        )
    return rows


def _strongest_features(tier_rows: list[dict[str, Any]], features: list[str]) -> list[dict[str, Any]]:
    by_feature = {}
    for feature in features:
        high = [row for row in tier_rows if row["evidence_subset"] == "combined_sample" and row["feature"] == feature and row["milestone_tier"] in {"reached_500k_but_never_1m", "reached_1m_plus"}]
        low = [row for row in tier_rows if row["evidence_subset"] == "combined_sample" and row["feature"] == feature and row["milestone_tier"] in {"reached_20k_but_never_50k", "reached_50k_but_never_100k"}]
        high_vals = [_number(row.get("median")) for row in high if _number(row.get("median")) is not None]
        low_vals = [_number(row.get("median")) for row in low if _number(row.get("median")) is not None]
        if not high_vals or not low_vals:
            continue
        diff = median(high_vals) - median(low_vals)
        by_feature[feature] = {
            "feature": feature,
            "high_tier_median": median(high_vals),
            "low_tier_median": median(low_vals),
            "median_difference": diff,
            "direction": "higher_in_high_tiers" if diff > 0 else "lower_in_high_tiers" if diff < 0 else "flat",
        }
    return sorted(by_feature.values(), key=lambda item: abs(item["median_difference"]), reverse=True)[:8]


def _commonality_questions(visible: list[dict[str, Any]], hidden: list[dict[str, Any]]) -> dict[str, str]:
    return {
        "100k_plus_vs_sub_100k": "descriptive structural differences are summarized by tier tables; no edge claim made",
        "500k_plus_vs_sub_500k": "visible and hidden proxy differences require formal thesis testing before interpretation",
        "1m_plus_vs_lower": "candidate fingerprints are descriptive only",
        "balanced_vs_leftover": "balanced evidence is separated from leftover/date-concentrated evidence in all tier tables",
        "hidden_vs_visible": "hidden structural proxies are reported alongside FDV efficiency proxies without promotion claims",
        "strongest_visible_feature": visible[0]["feature"] if visible else "data_limited",
        "strongest_hidden_feature": hidden[0]["feature"] if hidden else "data_limited",
    }


def _next_recommendation(coverage: dict[str, Any]) -> str:
    if coverage["all_three_p0_launches"] >= 500 and coverage["balanced_sample_rows"] >= 250:
        return "A. Full runner fingerprint report is ready for formal thesis selection."
    if coverage["balanced_sample_rows"] < 250:
        return "B. Need one more medium scale-up to improve balanced all-three coverage."
    return "C. Need specific missing field enrichment before fingerprint report."


def _readiness(coverage: dict[str, Any]) -> str:
    if coverage["all_three_p0_launches"] >= 500 and coverage["balanced_sample_rows"] >= 250:
        return "combined_p0_fingerprint_ready_for_formal_thesis_selection"
    if coverage["balanced_sample_rows"] < 250:
        return "combined_p0_fingerprint_needs_more_balanced_scale"
    if coverage["all_three_p0_launches"] < 100:
        return "combined_p0_fingerprint_inconclusive"
    return "combined_p0_fingerprint_needs_field_repair"


def _limitations(coverage: dict[str, Any]) -> list[str]:
    return [
        "true_market_cap_claims_remain_blocked",
        "fdv_proxy_only",
        "top_holder_addresses_unavailable",
        "leftover_sample_is_date_concentrated",
        "descriptive_only_no_validation_or_trading_claim",
    ]


def _write_outputs(
    *,
    report: dict[str, Any],
    coverage_rows: list[dict[str, Any]],
    tier_rows: list[dict[str, Any]],
    fingerprints: list[dict[str, Any]],
    entry_exit_rows: list[dict[str, Any]],
    output_dir: Path,
    status_path: Path,
) -> dict[str, Path]:
    paths = {
        "summary_json_path": output_dir / "combined_aligned_p0_fingerprint_summary.json",
        "summary_md_path": output_dir / "combined_aligned_p0_fingerprint_summary.md",
        "coverage_audit_path": output_dir / "combined_p0_coverage_audit.csv",
        "tier_feature_comparison_path": output_dir / "combined_p0_tier_feature_comparison.csv",
        "candidate_fingerprints_path": output_dir / "combined_p0_candidate_fingerprints.csv",
        "entry_vs_exit_features_path": output_dir / "combined_p0_entry_vs_exit_features.csv",
        "status_path": status_path,
    }
    paths["summary_json_path"].write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    paths["summary_md_path"].write_text(_markdown(report), encoding="utf-8")
    _write_csv(coverage_rows, paths["coverage_audit_path"])
    _write_csv(tier_rows, paths["tier_feature_comparison_path"])
    _write_csv(fingerprints, paths["candidate_fingerprints_path"])
    _write_csv(entry_exit_rows, paths["entry_vs_exit_features_path"])
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(_status_markdown(report), encoding="utf-8")
    return paths


def _read_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    if path.suffix == ".parquet":
        import pandas as pd

        return pd.read_parquet(path).to_dict("records")
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if path.suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        return [row for row in payload.get("rows", []) if isinstance(row, dict)] if isinstance(payload, dict) else []
    if path.suffix == ".csv":
        with path.open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    return []


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, default=str))
            handle.write("\n")


def _write_parquet(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    import pandas as pd

    pd.DataFrame(rows).to_parquet(path, index=False)


def _write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        if not rows:
            return
        writer = csv.DictWriter(handle, fieldnames=sorted({key for row in rows for key in row}))
        writer.writeheader()
        writer.writerows(rows)


def _distribution(values: list[float]) -> dict[str, Any]:
    values = sorted(values)
    if not values:
        return {"sample_count": 0, "median": None, "iqr": None, "p10": None, "p90": None}
    return {
        "sample_count": len(values),
        "median": median(values),
        "iqr": f"[{_percentile(values, 0.25)}, {_percentile(values, 0.75)}]",
        "p10": _percentile(values, 0.10),
        "p90": _percentile(values, 0.90),
    }


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    idx = min(len(values) - 1, max(0, round((len(values) - 1) * q)))
    return values[idx]


def _missing_reason(row: dict[str, Any]) -> str | None:
    missing = []
    if not _bool(row.get("has_early_buyer_wallet_history")):
        missing.append("missing_early_buyer_history")
    if not _bool(row.get("has_top_holder_replay")):
        missing.append("missing_top_holder_replay")
    if not _bool(row.get("has_creator_funder_graph")):
        missing.append("missing_creator_funder_graph")
    return ";".join(missing) if missing else None


def _neutral_label(feature: str) -> str:
    if "funder" in feature or "funding" in feature:
        return "funder_link_proxy"
    if "top_holder" in feature:
        return "top_holder_behavior_proxy"
    if "buyer" in feature:
        return "repeated_buyer_proxy"
    if "creator" in feature:
        return "creator_link_proxy"
    if "fdv" in feature or "event" in feature or "buy" in feature:
        return "structural_proxy"
    return "distribution_proxy"


def _markdown(report: dict[str, Any]) -> str:
    c = report["coverage_audit"]
    return "\n".join(
        [
            "# Combined Aligned P0 Structural Fingerprint",
            "",
            f"- Readiness: `{report['readiness_classification']}`",
            f"- Unique launches: `{c['total_unique_launches']}`",
            f"- All-three P0 launches: `{c['all_three_p0_launches']}`",
            f"- Balanced sample rows: `{c['balanced_sample_rows']}`",
            f"- Leftover sample rows: `{c['leftover_sample_rows']}`",
            f"- Next recommendation: {report['next_recommendation']}",
            "",
            "This is descriptive only. It does not run validation, create rules, or make trading claims.",
        ]
    ) + "\n"


def _status_markdown(report: dict[str, Any]) -> str:
    c = report["coverage_audit"]
    return "\n".join(
        [
            "# Combined Aligned P0 Fingerprint Status",
            "",
            "## Why This Exists",
            "Combines original, balanced second-pass, and leftover aligned P0 structural enrichment into one descriptive fingerprint dataset.",
            "",
            "## Coverage",
            f"- Unique launches: `{c['total_unique_launches']}`",
            f"- All-three P0 launches: `{c['all_three_p0_launches']}`",
            f"- Balanced sample rows: `{c['balanced_sample_rows']}`",
            f"- Leftover sample rows: `{c['leftover_sample_rows']}`",
            f"- Duplicate rows resolved: `{c['duplicate_rows_resolved']}`",
            "",
            "## Findings",
            f"- Strongest visible features: `{[row['feature'] for row in report['strongest_visible_features'][:5]]}`",
            f"- Strongest hidden structural features: `{[row['feature'] for row in report['strongest_hidden_structural_features'][:5]]}`",
            f"- Candidate fingerprints: `{[row['name'] for row in report['candidate_fingerprints']]}`",
            "",
            "## Limitations",
            f"- `{report['limitations']}`",
            "",
            "## Next Recommendation",
            report["next_recommendation"],
        ]
    ) + "\n"


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return None
    return text


def _number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(value) else value


def _first_number(row: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _number(row.get(key))
        if value is not None:
            return value
    return None


def _int_or_none(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    return bool(value)


def _ratio(num: float | None, den: float | None) -> float | None:
    if num is None or den in {None, 0}:
        return None
    return num / den


def _pct(num: int, den: int) -> float:
    return round(num / den * 100, 4) if den else 0.0


def _top_share(counts: Counter, total: int, n: int) -> float:
    if not total:
        return 0.0
    return round(sum(count for _key, count in counts.most_common(n)) / total * 100, 4)
