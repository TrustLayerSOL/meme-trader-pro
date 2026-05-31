"""Outlier-adjusted diagnostic metrics for exploratory rules."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from statistics import mean
from typing import Any

from research.mtp_research.backtest.rule_backtest_models import RuleDefinition
from research.mtp_research.backtest.rule_backtester import RuleBacktester
from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow
from research.mtp_research.validation.robust_return_metrics import summarize_robust_returns


EXCLUDED_CLASSIFICATIONS = {
    "fallback_dependent",
    "isolated_price_print",
    "suspicious_price_jump",
    "unusable_for_validation",
}


def build_outlier_adjusted_report(
    rows: list[ResearchDatasetRow],
    rules: list[RuleDefinition],
    rule_ids: list[str],
    outlier_report_path: Path | str | None,
    return_cap: float = 1.0,
    dataset_path: str = "",
) -> dict[str, Any]:
    outlier_classifications = load_outlier_classifications(outlier_report_path)
    backtester = RuleBacktester()
    selected_rule_ids = set(rule_ids)
    rule_summaries = []
    for rule in rules:
        if selected_rule_ids and rule.rule_id not in selected_rule_ids:
            continue
        selected_rows = [
            row for row in rows
            if row.forward_return is not None and backtester.row_passes_rule(row, rule)
        ]
        raw_values = [row.forward_return for row in selected_rows if row.forward_return is not None]
        included_values = [
            row.forward_return
            for row in selected_rows
            if row.forward_return is not None
            and outlier_classifications.get(row.row_id) not in EXCLUDED_CLASSIFICATIONS
        ]
        excluded_rows = [
            row for row in selected_rows
            if outlier_classifications.get(row.row_id) in EXCLUDED_CLASSIFICATIONS
        ]
        capped_values = [
            min(max(value, -return_cap), return_cap)
            for value in raw_values
        ]
        excluded_counts = Counter(outlier_classifications.get(row.row_id) for row in excluded_rows)
        rule_summaries.append(
            {
                "rule_id": rule.rule_id,
                "rule_name": rule.name,
                "selected_count": len(selected_rows),
                "excluded_outlier_count": len(excluded_rows),
                "excluded_outlier_rate": (len(excluded_rows) / len(selected_rows)) if selected_rows else None,
                "excluded_classification_counts": dict(sorted(excluded_counts.items())),
                "raw_metrics": summarize_robust_returns(raw_values),
                "capped_metrics": _mean_summary(capped_values),
                "included_metrics": _mean_summary(included_values),
                "warning_flags": _rule_warnings(raw_values, included_values, excluded_rows),
            }
        )
    report = {
        "report_id": make_outlier_adjusted_report_id(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset_path": dataset_path,
        "outlier_report_path": str(outlier_report_path) if outlier_report_path else "",
        "return_cap": return_cap,
        "rule_summaries": rule_summaries,
        "recommended_next_action": recommend_next_action(rule_summaries),
        "warning_flags": ["diagnostic_only_not_trading_signal"],
    }
    return report


def load_outlier_classifications(outlier_report_path: Path | str | None) -> dict[str, str]:
    if not outlier_report_path:
        return {}
    path = Path(outlier_report_path)
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        str(review.get("row_id")): str(review.get("outlier_classification"))
        for review in payload.get("reviews", [])
        if review.get("row_id") and review.get("outlier_classification")
    }


def find_latest_outlier_report(output_dir: Path | str) -> Path | None:
    paths = sorted(Path(output_dir).glob("outlier_price_path_*.json"), key=lambda item: item.stat().st_mtime)
    return paths[-1] if paths else None


def write_outlier_adjusted_json(report: dict[str, Any], output_path: Path | str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_outlier_adjusted_markdown(report: dict[str, Any], output_path: Path | str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Outlier-Adjusted Rule Metrics",
        "",
        "> Warning: Outlier-adjusted metrics are diagnostic only. They are not trading signals.",
        "",
        f"- Dataset path: `{report['dataset_path']}`",
        f"- Outlier report path: `{report['outlier_report_path']}`",
        f"- Return cap: `{report['return_cap']}`",
        f"- Recommended next action: `{report['recommended_next_action']}`",
        "",
        "| Rule | Selected | Excluded | Raw Mean | Raw Median | Capped Mean | Included Mean | Warnings |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for summary in report["rule_summaries"]:
        lines.append(
            "| "
            f"`{summary['rule_id']}` | "
            f"{summary['selected_count']} | "
            f"{summary['excluded_outlier_count']} | "
            f"{_fmt(summary['raw_metrics']['mean'])} | "
            f"{_fmt(summary['raw_metrics']['median'])} | "
            f"{_fmt(summary['capped_metrics']['mean'])} | "
            f"{_fmt(summary['included_metrics']['mean'])} | "
            f"`{summary['warning_flags']}` |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def recommend_next_action(rule_summaries: list[dict[str, Any]]) -> str:
    if any("excluded_outliers_present" in summary["warning_flags"] for summary in rule_summaries):
        return "separate_outlier_metrics_before_scaling"
    if any("raw_mean_outlier_sensitive" in summary["warning_flags"] for summary in rule_summaries):
        return "separate_outlier_metrics_before_scaling"
    if any((summary.get("excluded_outlier_rate") or 0.0) > 0.25 for summary in rule_summaries):
        return "tighten_price_quality_filters_before_scaling"
    return "bounded_evidence_expansion_with_outlier_separation"


def make_outlier_adjusted_report_id(prefix: str = "outlier_adjusted_rule") -> str:
    created = datetime.now(timezone.utc).isoformat()
    digest = sha256(f"{prefix}|{created}".encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _mean_summary(values: list[float]) -> dict[str, Any]:
    return {
        "count": len(values),
        "mean": mean(values) if values else None,
        "robust": summarize_robust_returns(values),
    }


def _rule_warnings(
    raw_values: list[float],
    included_values: list[float],
    excluded_rows: list[ResearchDatasetRow],
) -> list[str]:
    warnings: list[str] = []
    if excluded_rows:
        warnings.append("excluded_outliers_present")
    raw = summarize_robust_returns(raw_values)
    if raw["mean"] is not None and raw["median"] is not None and abs(raw["mean"] - raw["median"]) > 0.5:
        warnings.append("raw_mean_outlier_sensitive")
    if raw_values and not included_values:
        warnings.append("all_selected_rows_excluded_after_outlier_review")
    return warnings


def _fmt(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.6f}"
