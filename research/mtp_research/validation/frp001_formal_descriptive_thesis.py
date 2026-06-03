"""FRP-001 formal descriptive thesis cycle.

This module tests the frozen FRP-001 runner fingerprint definition from the
final runner-fingerprint artifact. It is descriptive only: no validation,
backtest, optimization, trading logic, or thesis promotion.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from research.mtp_research.data_paths import data_lake_path


REPORT_ID = "frp001_formal_descriptive_thesis_v0"
FINGERPRINT_ID = "FRP-001"
CLASSIFICATION_DEFINITION_MISSING = "definition_missing"

DEFAULT_CANDIDATE_FINGERPRINTS_PATH = data_lake_path(
    "data",
    "backtests",
    "diagnostics",
    "reports",
    "final_runner_fingerprint",
    "final_runner_candidate_fingerprints.csv",
)
DEFAULT_MASTER_PATH = data_lake_path(
    "data",
    "backtests",
    "structural_enrichment",
    "tier1_tier2_enrichment",
    "master_tier1_tier2_enriched_runner_fingerprint.parquet",
)
DEFAULT_MASTER_JSONL_PATH = data_lake_path(
    "data",
    "backtests",
    "structural_enrichment",
    "tier1_tier2_enrichment",
    "master_tier1_tier2_enriched_runner_fingerprint.jsonl",
)
DEFAULT_OUTPUT_DIR = data_lake_path(
    "data", "backtests", "diagnostics", "reports", "FRP001_formal_descriptive_thesis"
)
DEFAULT_STATUS_PATH = Path("theses/FRP001_FORMAL_DESCRIPTIVE_THESIS_STATUS.md")

TIER_ORDER = [
    "reached_20k_but_never_50k",
    "reached_50k_but_never_100k",
    "reached_100k_but_never_200k",
    "reached_200k_but_never_500k",
    "reached_500k_but_never_1m",
    "reached_1m_plus",
]
HIGH_100K = {
    "reached_100k_but_never_200k",
    "reached_200k_but_never_500k",
    "reached_500k_but_never_1m",
    "reached_1m_plus",
}
HIGH_500K = {"reached_500k_but_never_1m", "reached_1m_plus"}
HIGH_1M = {"reached_1m_plus"}
CONTRASTS = [
    ("100k_plus_vs_sub_100k", HIGH_100K),
    ("500k_plus_vs_sub_500k", HIGH_500K),
    ("1m_plus_vs_sub_1m", HIGH_1M),
    ("500k_or_1m_vs_100k_only", HIGH_500K),
]

METHODOLOGY_FLAGS = [
    "formal_descriptive_thesis_only",
    "frp001_only",
    "definition_loaded_from_final_candidate_fingerprint_table",
    "no_frp002_or_frp003_or_frp004_execution",
    "no_validation_execution",
    "no_walk_forward_validation",
    "no_backtest",
    "no_paper_trading",
    "no_live_trading",
    "no_auto_buy_sell",
    "no_private_key_logic",
    "no_wallet_execution",
    "no_order_routing",
    "no_alerts",
    "no_buy_rules",
    "no_sell_rules",
    "no_trading_logic",
    "no_profitability_claims",
    "no_strategy_generation",
    "no_threshold_optimization",
    "no_grid_search",
    "no_ml_black_boxes",
    "fdv_proxy_not_true_market_cap",
    "fixed_tertile_buckets_not_tuned",
]


def load_frp001_definition(candidate_fingerprints_path: Path | str = DEFAULT_CANDIDATE_FINGERPRINTS_PATH) -> dict[str, Any]:
    path = Path(candidate_fingerprints_path)
    if not path.exists():
        raise ValueError("frp001_definition_missing")
    table = pd.read_csv(path)
    if "fingerprint_id" not in table.columns:
        raise ValueError("frp001_definition_missing")
    rows = table[table["fingerprint_id"] == FINGERPRINT_ID]
    if len(rows) != 1:
        raise ValueError("frp001_definition_missing")
    row = rows.iloc[0].to_dict()
    features = _split_semicolon(row.get("specific_features"))
    families = _split_semicolon(row.get("feature_families_included"))
    directions = _parse_json_dict(row.get("expected_direction"))
    coverage = _parse_json_dict(row.get("coverage"))
    if not features or not directions:
        raise ValueError("frp001_definition_missing")
    visible = [feature for feature in features if feature.startswith("fdv_") or feature in {"active_wallets_at_20k"}]
    wallet = [feature for feature in features if feature not in visible]
    return {
        "fingerprint_id": row.get("fingerprint_id"),
        "fingerprint_name": row.get("fingerprint_name"),
        "description": row.get("description"),
        "feature_families_included": families,
        "specific_features": features,
        "visible_features": visible,
        "wallet_quality_features": wallet,
        "expected_direction": directions,
        "entry_side_vs_path_side_vs_exit_side": row.get("entry_side_vs_path_side_vs_exit_side"),
        "coverage_from_selection_report": coverage,
        "missing_fields": row.get("missing_fields"),
        "limitations": row.get("limitations"),
        "what_would_invalidate_it": row.get("what_would_invalidate_it"),
        "suggested_formal_testing_note": "Use fixed descriptive tertile buckets; do not optimize thresholds or combine with FRP-002/FRP-003/FRP-004.",
    }


def build_frp001_formal_descriptive_thesis(
    *,
    candidate_fingerprints_path: Path | str = DEFAULT_CANDIDATE_FINGERPRINTS_PATH,
    master_path: Path | str = DEFAULT_MASTER_PATH,
    jsonl_fallback: Path | str = DEFAULT_MASTER_JSONL_PATH,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    status_path: Path | str = DEFAULT_STATUS_PATH,
) -> tuple[dict[str, Any], dict[str, Path]]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    try:
        definition = load_frp001_definition(candidate_fingerprints_path)
    except ValueError as exc:
        report = _definition_missing_report(str(exc), candidate_fingerprints_path, master_path)
        paths = _write_outputs(report, [], [], [], [], output, Path(status_path))
        return report, paths

    master = _load_master(master_path, jsonl_fallback)
    master = master[master["milestone_tier"].isin(TIER_ORDER)].copy()
    master = master.sort_values(["launch_date", "launch_id"], na_position="last").reset_index(drop=True)
    features = definition["specific_features"]
    coverage_table, coverage_summary = _feature_coverage(master, features, definition)
    scored = _build_indicators(master, definition)
    tier_support = _tier_support_table(scored, features)
    visible_vs_wallet = _visible_vs_wallet_quality(scored, definition)
    robustness = _robustness_table(scored, definition)
    robustness_summary = _robustness_summary(robustness)
    classification = _classify(coverage_summary, tier_support, visible_vs_wallet, robustness_summary)
    report = {
        "report_id": REPORT_ID,
        "report_type": "frp001_formal_descriptive_thesis",
        "classification": classification,
        "readiness_classification": "frp001_formal_descriptive_thesis_complete",
        "methodology_flags": METHODOLOGY_FLAGS,
        "guardrails": _guardrails(),
        "source_paths": {
            "candidate_fingerprints_path": str(candidate_fingerprints_path),
            "master_path": str(master_path),
            "jsonl_fallback": str(jsonl_fallback),
        },
        "frozen_definition": definition,
        "rows_analyzed": int(len(scored)),
        "feature_coverage": coverage_summary,
        "tier_support_table": tier_support,
        "visible_vs_wallet_quality_comparison": visible_vs_wallet,
        "robustness_table": robustness,
        "robustness_summary": robustness_summary,
        "limitations": [
            "FDV-proxy only; true market-cap claims remain blocked.",
            "Formal descriptive thesis only; no validation, backtest, optimization, or trading logic.",
            "Wallet-quality proxy fields are descriptive proxies and are not identity or intent labels.",
            "FRP-002, FRP-003, and FRP-004 were not tested in this sprint.",
        ],
        "next_recommendation": _next_recommendation(classification),
    }
    _assert_guardrails(report)
    paths = _write_outputs(report, tier_support, coverage_table, [visible_vs_wallet], robustness, output, Path(status_path))
    return report, paths


def _definition_missing_report(reason: str, candidate_path: Path | str, master_path: Path | str) -> dict[str, Any]:
    return {
        "report_id": REPORT_ID,
        "report_type": "frp001_formal_descriptive_thesis",
        "classification": CLASSIFICATION_DEFINITION_MISSING,
        "readiness_classification": "frp001_definition_missing",
        "methodology_flags": METHODOLOGY_FLAGS + ["fail_closed_definition_missing"],
        "guardrails": _guardrails(),
        "source_paths": {"candidate_fingerprints_path": str(candidate_path), "master_path": str(master_path)},
        "definition_missing_reason": reason,
        "frozen_definition": {},
        "rows_analyzed": 0,
        "feature_coverage": {},
        "tier_support_table": [],
        "visible_vs_wallet_quality_comparison": {},
        "robustness_table": [],
        "robustness_summary": {},
        "limitations": ["FRP-001 definition missing or ambiguous; no thesis analysis was run."],
        "next_recommendation": "repair_final_runner_candidate_fingerprints_before_frp001_analysis",
    }


def _load_master(master_path: Path | str, jsonl_fallback: Path | str) -> pd.DataFrame:
    path = Path(master_path)
    fallback = Path(jsonl_fallback)
    if path.exists():
        return pd.read_parquet(path)
    if fallback.exists():
        return pd.read_json(fallback, orient="records", lines=True)
    raise FileNotFoundError(f"missing enriched master {path} and fallback {fallback}")


def _feature_coverage(master: pd.DataFrame, features: list[str], definition: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = []
    for feature in features:
        present = feature in master.columns
        series = master[feature] if present else pd.Series([pd.NA] * len(master))
        by_tier = {}
        for tier in TIER_ORDER:
            tier_series = series[master["milestone_tier"] == tier] if present else pd.Series(dtype=object)
            by_tier[tier] = {
                "rows": int((master["milestone_tier"] == tier).sum()),
                "non_null_rows": int(tier_series.notna().sum()),
                "coverage_pct": _pct(int(tier_series.notna().sum()), int((master["milestone_tier"] == tier).sum())),
            }
        non_null = int(series.notna().sum()) if present else 0
        rows.append(
            {
                "feature": feature,
                "feature_group": _feature_group(feature, definition),
                "total_rows": int(len(master)),
                "non_null_rows": non_null,
                "coverage_pct": _pct(non_null, len(master)),
                "coverage_by_milestone_tier_json": json.dumps(by_tier, sort_keys=True),
                "top_dates_json": json.dumps(_top_counts(master.loc[series.notna(), "launch_date"] if present and "launch_date" in master else []), sort_keys=True),
                "top_creators_json": json.dumps(_top_counts(master.loc[series.notna(), "creator"] if present and "creator" in master else []), sort_keys=True),
                "missing_reason_counts_json": json.dumps(_missing_reason_counts(master, feature, present), sort_keys=True),
                "entry_side_observable": definition.get("entry_side_vs_path_side_vs_exit_side") == "entry_side",
                "path_or_exit_side": definition.get("entry_side_vs_path_side_vs_exit_side") != "entry_side",
                "fdv_proxy_only": feature.startswith("fdv_"),
                "hidden_structural_proxy": feature in definition.get("wallet_quality_features", []),
            }
        )
    complete = master[[feature for feature in features if feature in master.columns]].notna().all(axis=1) if features else pd.Series(False, index=master.index)
    summary = {
        "total_rows": int(len(master)),
        "rows_with_all_frp001_fields": int(complete.sum()) if len(features) else 0,
        "coverage_pct": _pct(int(complete.sum()) if len(features) else 0, len(master)),
        "features": {row["feature"]: row for row in rows},
    }
    return rows, summary


def _build_indicators(master: pd.DataFrame, definition: dict[str, Any]) -> pd.DataFrame:
    frame = master.copy()
    all_features = definition["specific_features"]
    visible = definition["visible_features"]
    wallet = definition["wallet_quality_features"]
    for feature in all_features:
        if feature not in frame:
            frame[feature] = pd.NA
        numeric = _numeric(frame[feature])
        frame[f"{feature}__tertile"] = _tertile_bucket(numeric)
        frame[f"{feature}__high_bucket"] = frame[f"{feature}__tertile"] == "high"
        frame[f"{feature}__direction_support"] = _direction_support(numeric, definition["expected_direction"].get(feature))
    frame["frp001_visible_high_count"] = frame[[f"{feature}__high_bucket" for feature in visible if feature in all_features]].sum(axis=1)
    frame["frp001_wallet_quality_high_count"] = frame[[f"{feature}__high_bucket" for feature in wallet if feature in all_features]].sum(axis=1)
    frame["frp001_visible_features_available"] = frame[visible].notna().sum(axis=1) if visible else 0
    frame["frp001_wallet_quality_features_available"] = frame[wallet].notna().sum(axis=1) if wallet else 0
    frame["frp001_visible_support"] = frame["frp001_visible_high_count"] >= max(1, len(visible) // 2)
    frame["frp001_wallet_quality_support"] = frame["frp001_wallet_quality_high_count"] >= max(1, len(wallet) // 2)
    frame["frp001_support"] = frame["frp001_visible_support"] & frame["frp001_wallet_quality_support"]
    frame["frp001_visible_only_support"] = frame["frp001_visible_support"]
    frame["frp001_visible_score"] = frame[[f"{feature}__high_bucket" for feature in visible]].mean(axis=1) if visible else 0.0
    frame["frp001_wallet_quality_score"] = frame[[f"{feature}__high_bucket" for feature in wallet]].mean(axis=1) if wallet else 0.0
    frame["frp001_combined_score"] = frame[["frp001_visible_score", "frp001_wallet_quality_score"]].mean(axis=1)
    return frame


def _tier_support_table(scored: pd.DataFrame, features: list[str]) -> list[dict[str, Any]]:
    total_support = int(scored["frp001_support"].sum()) if not scored.empty else 0
    rows = []
    for tier in TIER_ORDER:
        group = scored[scored["milestone_tier"] == tier]
        support = int(group["frp001_support"].sum()) if not group.empty else 0
        row = {
            "milestone_tier": tier,
            "rows": int(len(group)),
            "support_count": support,
            "support_rate_pct": _pct(support, len(group)),
            "capture_rate_pct": _pct(support, total_support),
            "missing_count": int(group[features].isna().any(axis=1).sum()) if features else 0,
            "date_concentration_top_date_count": _top_count(group.get("launch_date")),
            "creator_concentration_top_creator_count": _top_count(group.get("creator")),
        }
        for feature in features:
            row[f"median_{feature}"] = _median(group[feature]) if feature in group else None
        rows.append(row)
    return rows


def _visible_vs_wallet_quality(scored: pd.DataFrame, definition: dict[str, Any]) -> dict[str, Any]:
    comparisons = []
    for name, high_tiers in CONTRASTS[:3]:
        lower = scored[~scored["milestone_tier"].isin(high_tiers)]
        higher = scored[scored["milestone_tier"].isin(high_tiers)]
        comparisons.append(
            {
                "contrast": name,
                "visible_only_separation": _median(higher["frp001_visible_score"]) - _median(lower["frp001_visible_score"]),
                "wallet_quality_separation": _median(higher["frp001_wallet_quality_score"]) - _median(lower["frp001_wallet_quality_score"]),
                "combined_frp001_separation": _median(higher["frp001_combined_score"]) - _median(lower["frp001_combined_score"]),
                "visible_only_support_rate_higher_pct": _pct(int(higher["frp001_visible_only_support"].sum()), len(higher)),
                "frp001_support_rate_higher_pct": _pct(int(higher["frp001_support"].sum()), len(higher)),
                "wallet_quality_coverage_pct": _pct(int(scored[definition["wallet_quality_features"]].notna().all(axis=1).sum()), len(scored)) if definition["wallet_quality_features"] else 0.0,
            }
        )
    primary = next(row for row in comparisons if row["contrast"] == "500k_plus_vs_sub_500k")
    return {
        "comparison_method": "fixed_tertile_bucket_scores_no_threshold_search",
        "primary_contrast": primary,
        "all_contrasts": comparisons,
        "wallet_quality_adds_information": bool(primary["combined_frp001_separation"] > primary["visible_only_separation"] and primary["wallet_quality_separation"] > 0),
        "wallet_quality_coverage_limited": bool(primary["wallet_quality_coverage_pct"] < 70),
        "wallet_quality_most_useful_tier_hint": _best_wallet_contrast(comparisons),
    }


def _robustness_table(scored: pd.DataFrame, definition: dict[str, Any]) -> list[dict[str, Any]]:
    checks = [("full_sample", scored)]
    if len(scored) >= 4:
        midpoint = len(scored) // 2
        checks.extend([("chronological_first_half", scored.iloc[:midpoint]), ("chronological_second_half", scored.iloc[midpoint:])])
    if len(scored) >= 9:
        cut = len(scored) // 3
        checks.extend([("chronological_first_third", scored.iloc[:cut]), ("chronological_middle_third", scored.iloc[cut : 2 * cut]), ("chronological_last_third", scored.iloc[2 * cut :])])
    checks.append(("exclude_top_date", _exclude_top(scored, "launch_date", 1)))
    checks.append(("exclude_top_3_dates", _exclude_top(scored, "launch_date", 3)))
    checks.append(("exclude_top_creator", _exclude_top(scored, "creator", 1)))
    checks.append(("exclude_top_3_creators", _exclude_top(scored, "creator", 3)))
    checks.append(("exclude_missing_critical_fields", scored.dropna(subset=definition["specific_features"])))
    if definition["wallet_quality_features"]:
        checks.append(("exclude_sparse_wallet_quality", scored.dropna(subset=definition["wallet_quality_features"])))
    rows = []
    for check_name, subset in checks:
        rows.append(_robustness_row(check_name, subset))
    return rows


def _robustness_row(name: str, subset: pd.DataFrame) -> dict[str, Any]:
    high = subset[subset["milestone_tier"].isin(HIGH_500K)]
    low = subset[~subset["milestone_tier"].isin(HIGH_500K)]
    high_rate = _pct(int(high["frp001_support"].sum()), len(high))
    low_rate = _pct(int(low["frp001_support"].sum()), len(low))
    return {
        "check_name": name,
        "rows": int(len(subset)),
        "high_group_rows": int(len(high)),
        "low_group_rows": int(len(low)),
        "high_group_support_rate_pct": high_rate,
        "low_group_support_rate_pct": low_rate,
        "directionally_consistent": bool(high_rate > low_rate) if len(high) and len(low) else False,
        "note": "descriptive_robustness_only_no_validation",
    }


def _robustness_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [row for row in rows if row["high_group_rows"] and row["low_group_rows"]]
    consistent = [row for row in valid if row["directionally_consistent"]]
    return {
        "checks_run": len(rows),
        "checks_with_both_groups": len(valid),
        "directionally_consistent_checks": len(consistent),
        "directional_consistency_pct": _pct(len(consistent), len(valid)),
    }


def _classify(coverage: dict[str, Any], tier_support: list[dict[str, Any]], visible_wallet: dict[str, Any], robustness: dict[str, Any]) -> str:
    if not coverage or coverage.get("coverage_pct", 0) < 50:
        return "data_limited"
    by_tier = {row["milestone_tier"]: row for row in tier_support}
    low_rate = _weighted_rate([by_tier[tier] for tier in ["reached_20k_but_never_50k", "reached_50k_but_never_100k"]])
    high_rate = _weighted_rate([by_tier[tier] for tier in ["reached_500k_but_never_1m", "reached_1m_plus"]])
    if high_rate <= low_rate:
        return "no_signal"
    if visible_wallet.get("wallet_quality_adds_information") and robustness.get("directional_consistency_pct", 0) >= 60:
        return "descriptive_signal_present"
    return "weak_signal"


def _next_recommendation(classification: str) -> str:
    if classification == "descriptive_signal_present":
        return "consider_frp001_robustness_or_validation_design_later_without_trading_promotion"
    if classification == "weak_signal":
        return "review_wallet_quality_contribution_before_any_validation_design"
    if classification == "data_limited":
        return "improve_frp001_field_coverage_before_interpretation"
    if classification == CLASSIFICATION_DEFINITION_MISSING:
        return "repair_final_runner_candidate_fingerprints_before_frp001_analysis"
    return "park_frp001_or_compare_next_selected_fingerprint"


def _write_outputs(
    report: dict[str, Any],
    tier_support: list[dict[str, Any]],
    coverage_rows: list[dict[str, Any]],
    visible_wallet_rows: list[dict[str, Any]],
    robustness_rows: list[dict[str, Any]],
    output: Path,
    status_path: Path,
) -> dict[str, Path]:
    paths = {
        "summary_json_path": output / "FRP001_formal_descriptive_thesis_summary.json",
        "summary_markdown_path": output / "FRP001_formal_descriptive_thesis_summary.md",
        "tier_support_table_path": output / "FRP001_tier_support_table.csv",
        "feature_coverage_table_path": output / "FRP001_feature_coverage_table.csv",
        "visible_vs_wallet_quality_comparison_path": output / "FRP001_visible_vs_wallet_quality_comparison.csv",
        "robustness_table_path": output / "FRP001_robustness_table.csv",
        "status_path": status_path,
    }
    paths["summary_json_path"].write_text(json.dumps(report, indent=2, sort_keys=True, default=_json_default), encoding="utf-8")
    paths["summary_markdown_path"].write_text(_summary_markdown(report), encoding="utf-8")
    pd.DataFrame(tier_support).to_csv(paths["tier_support_table_path"], index=False)
    pd.DataFrame(coverage_rows).to_csv(paths["feature_coverage_table_path"], index=False)
    pd.DataFrame(visible_wallet_rows).to_csv(paths["visible_vs_wallet_quality_comparison_path"], index=False)
    pd.DataFrame(robustness_rows).to_csv(paths["robustness_table_path"], index=False)
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(_status_markdown(report), encoding="utf-8")
    return paths


def _summary_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# FRP-001 Formal Descriptive Thesis",
        "",
        f"- Classification: `{report['classification']}`",
        f"- Rows analyzed: `{report['rows_analyzed']}`",
        "- Scope: formal descriptive thesis only; no validation, backtest, paper/live trading, or trading logic.",
        "",
        "## Frozen Definition",
        f"- `{report.get('frozen_definition', {}).get('fingerprint_name', '')}`",
        f"- Features: `{';'.join(report.get('frozen_definition', {}).get('specific_features', []))}`",
        "",
        "## Next Recommendation",
        f"- `{report['next_recommendation']}`",
        "",
    ]
    return "\n".join(lines)


def _status_markdown(report: dict[str, Any]) -> str:
    definition = report.get("frozen_definition", {})
    lines = [
        "# FRP-001 Formal Descriptive Thesis Status",
        "",
        "This status file records the formal descriptive cycle for FRP-001 only. It does not promote a thesis and does not create trading logic.",
        "",
        "## Frozen FRP-001 Definition",
        f"- Fingerprint: `{definition.get('fingerprint_id')}`",
        f"- Name: `{definition.get('fingerprint_name')}`",
        f"- Features: `{';'.join(definition.get('specific_features', []))}`",
        f"- Expected directions: `{json.dumps(definition.get('expected_direction', {}), sort_keys=True)}`",
        "",
        "## Dataset",
        f"- Master: `{report.get('source_paths', {}).get('master_path')}`",
        f"- Rows analyzed: `{report.get('rows_analyzed')}`",
        "",
        "## Feature Coverage",
        f"- Rows with all FRP-001 fields: `{report.get('feature_coverage', {}).get('rows_with_all_frp001_fields')}`",
        f"- Coverage: `{report.get('feature_coverage', {}).get('coverage_pct')}`",
        "",
        "## Milestone Tier Results",
    ]
    for row in report.get("tier_support_table", []):
        lines.append(f"- {row['milestone_tier']}: support `{row['support_count']} / {row['rows']}` ({row['support_rate_pct']}%)")
    lines.extend(
        [
            "",
            "## Visible-Only Comparison",
            f"- `{report.get('visible_vs_wallet_quality_comparison', {})}`",
            "",
            "## Robustness Checks",
            f"- `{report.get('robustness_summary', {})}`",
            "",
            "## Classification",
            f"- `{report.get('classification')}`",
            "",
            "## Limitations",
            *[f"- {item}" for item in report.get("limitations", [])],
            "",
            "No FRP-002, FRP-003, or FRP-004 execution was run. No validation, walk-forward validation, backtest, paper/live trading, alerts, buy/sell rules, wallet execution, optimization, ML, or strategy logic was run.",
            "",
            "## Next Recommendation",
            f"- `{report.get('next_recommendation')}`",
            "",
        ]
    )
    return "\n".join(lines)


def _guardrails() -> dict[str, Any]:
    return {
        "frp001_runs": 1,
        "frp002_runs": 0,
        "frp003_runs": 0,
        "frp004_runs": 0,
        "validation_runs": 0,
        "walk_forward_runs": 0,
        "backtests_run": 0,
        "paper_trading_runs": 0,
        "live_trading_runs": 0,
        "trading_logic_added": False,
        "buy_rules_created": False,
        "sell_rules_created": False,
        "threshold_optimization": False,
        "grid_search": False,
        "ml": False,
    }


def _assert_guardrails(report: dict[str, Any]) -> None:
    text = json.dumps(report, default=_json_default).lower()
    for blocked in ("insider", "scammer", "wash trader", "manipulator", "guaranteed smart money"):
        if blocked in text:
            raise ValueError(f"unsupported label leaked into report: {blocked}")
    guardrails = report.get("guardrails", {})
    if guardrails.get("validation_runs") or guardrails.get("trading_logic_added"):
        raise ValueError("guardrail violation")


def _split_semicolon(value: Any) -> list[str]:
    if not _present(value):
        return []
    return [part.strip() for part in str(value).split(";") if part.strip()]


def _parse_json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not _present(value):
        return {}
    try:
        parsed = json.loads(str(value))
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _feature_group(feature: str, definition: dict[str, Any]) -> str:
    if feature in definition.get("visible_features", []):
        return "visible_feature"
    if feature in definition.get("wallet_quality_features", []):
        return "wallet_quality_proxy"
    return "structural_proxy"


def _missing_reason_counts(master: pd.DataFrame, feature: str, present: bool) -> dict[str, int]:
    if not present:
        return {"feature_missing_from_dataset": int(len(master))}
    column = f"{feature}_missing_reason"
    if column in master.columns:
        return dict(Counter(str(value) if _present(value) else "none" for value in master[column].tolist()))
    return {"none": int(master[feature].notna().sum()), "missing_without_specific_reason": int(master[feature].isna().sum())}


def _direction_support(series: pd.Series, direction: str | None) -> pd.Series:
    numeric = _numeric(series)
    median = numeric.median()
    if pd.isna(median):
        return pd.Series(False, index=series.index)
    if direction == "lower_in_stronger_runners":
        return numeric <= median
    if direction == "higher_in_stronger_runners":
        return numeric >= median
    return numeric.notna()


def _tertile_bucket(series: pd.Series) -> pd.Series:
    numeric = _numeric(series)
    ranked = numeric.rank(method="average", pct=True)
    return pd.Series(
        ["missing" if pd.isna(value) else "low" if value <= 1 / 3 else "medium" if value <= 2 / 3 else "high" for value in ranked],
        index=series.index,
    )


def _exclude_top(frame: pd.DataFrame, column: str, count: int) -> pd.DataFrame:
    if column not in frame.columns:
        return frame
    top = [value for value, _ in Counter(value for value in frame[column].dropna().tolist()).most_common(count)]
    return frame[~frame[column].isin(top)]


def _weighted_rate(rows: list[dict[str, Any]]) -> float:
    total = sum(row["rows"] for row in rows)
    support = sum(row["support_count"] for row in rows)
    return support / total if total else 0.0


def _best_wallet_contrast(rows: list[dict[str, Any]]) -> str:
    best = max(rows, key=lambda row: row["wallet_quality_separation"]) if rows else None
    return best["contrast"] if best else "unknown"


def _top_counts(values: Any, limit: int = 5) -> dict[str, int]:
    if values is None:
        return {}
    return {str(key): int(value) for key, value in Counter(value for value in pd.Series(values).dropna().tolist()).most_common(limit)}


def _top_count(values: Any) -> int:
    counts = _top_counts(values, 1)
    return next(iter(counts.values()), 0)


def _numeric(series: Any) -> pd.Series:
    if not isinstance(series, pd.Series):
        series = pd.Series(series)
    return pd.to_numeric(series, errors="coerce").astype("float64")


def _median(series: Any) -> float:
    numeric = _numeric(series).dropna()
    return float(numeric.median()) if not numeric.empty else 0.0


def _pct(num: int | float, den: int | float) -> float:
    return round((float(num) / float(den)) * 100, 4) if den else 0.0


def _present(value: Any) -> bool:
    if value is None:
        return False
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    return str(value).strip().lower() not in {"", "none", "nan", "null"}


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        return value.item()
    return str(value)
