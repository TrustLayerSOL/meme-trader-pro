"""FP001 formal descriptive thesis cycle."""

from __future__ import annotations

import csv
import json
import math
from collections import Counter
from pathlib import Path
from statistics import median
from typing import Any

from research.mtp_research.data_paths import data_lake_path


REPORT_ID = "fp001_formal_descriptive_thesis_v0"
FP001_ID = "FP001"
DEFAULT_SUPPORT_SUMMARY_PATH = data_lake_path(
    "data",
    "backtests",
    "diagnostics",
    "reports",
    "combined_p0_fingerprint_support_audit",
    "combined_p0_fingerprint_support_audit_summary.json",
)
DEFAULT_COMBINED_DATASET_PATH = data_lake_path(
    "data", "backtests", "structural_enrichment", "combined_aligned_p0_structural_fingerprint.parquet"
)
DEFAULT_OUTPUT_DIR = data_lake_path(
    "data", "backtests", "diagnostics", "reports", "FP001_formal_descriptive_thesis"
)
DEFAULT_STATUS_PATH = Path("theses/FP001_FORMAL_DESCRIPTIVE_THESIS_STATUS.md")

TIER_ORDER = [
    "reached_20k_but_never_50k",
    "reached_50k_but_never_100k",
    "reached_100k_but_never_200k",
    "reached_200k_but_never_500k",
    "reached_500k_but_never_1m",
    "reached_1m_plus",
]
TARGETS = {
    "100k_plus": {"reached_100k_but_never_200k", "reached_200k_but_never_500k", "reached_500k_but_never_1m", "reached_1m_plus"},
    "500k_plus": {"reached_500k_but_never_1m", "reached_1m_plus"},
    "1m_plus": {"reached_1m_plus"},
    "1m_plus_vs_100k_only_or_lower": {"reached_1m_plus"},
}
UNSUPPORTED_TERMS = ("insider", "scammer", "wash trader", "manipulator")


def build_fp001_formal_descriptive_thesis(
    *,
    support_summary_path: Path | str = DEFAULT_SUPPORT_SUMMARY_PATH,
    combined_dataset_path: Path | str = DEFAULT_COMBINED_DATASET_PATH,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    status_path: Path | str = DEFAULT_STATUS_PATH,
) -> tuple[dict[str, Any], dict[str, Path]]:
    try:
        definition = load_frozen_fp001_definition(support_summary_path)
    except ValueError as exc:
        report = _missing_definition_report(str(exc), support_summary_path, combined_dataset_path)
        paths = _write_outputs(report, [], [], Path(output_dir), Path(status_path))
        return report, paths

    rows = _read_records(Path(combined_dataset_path))
    rows = sorted(rows, key=lambda row: (str(row.get("launch_date") or ""), str(row.get("launch_id") or row.get("mint") or "")))
    required = definition["feature_list"]
    baselines = _feature_baselines(rows, required)
    scored_rows = [_score_row(row, required, definition["expected_directions"], baselines) for row in rows]
    coverage = _feature_coverage(scored_rows, required)
    tier_support = _tier_support_table(scored_rows)
    split_results = {
        "balanced": _split_result(_subset(scored_rows, "balanced")),
        "leftover": _split_result(_subset(scored_rows, "leftover")),
        "combined": _split_result(scored_rows),
    }
    robustness = _robustness_checks(scored_rows)
    classification = _classification(scored_rows, coverage, robustness)
    report = {
        "report_id": REPORT_ID,
        "report_type": "fp001_formal_descriptive_thesis",
        "classification": classification,
        "readiness_classification": "fp001_formal_descriptive_thesis_complete",
        "methodology_flags": [
            "formal_descriptive_thesis_only",
            "fp001_only",
            "no_fp002_or_fp003_thesis_execution",
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
            "no_trading_logic",
            "no_profitability_claims",
            "no_strategy_generation",
            "no_threshold_optimization",
            "no_grid_search",
            "no_ml_black_boxes",
            "neutral_proxy_labels_only",
            "fdv_proxy_not_true_market_cap",
            "no_network_calls",
        ],
        "source_paths": {
            "support_summary_path": str(support_summary_path),
            "combined_dataset_path": str(combined_dataset_path),
        },
        "frozen_fp001_definition": definition,
        "rows_analyzed": len(scored_rows),
        "feature_coverage": coverage,
        "feature_baselines": baselines,
        "tier_support_table": tier_support,
        "balanced_leftover_results": split_results,
        "robustness_checks": robustness,
        "formal_context_note": {
            "fp002_status": "ready_but_deferred_not_tested",
            "fp003_status": "held_back_due_to_direction_conflict_not_tested",
            "why_fp001_first": "fp001_passed_support_gate_and_is_the_first_formal_fingerprint_thesis",
        },
        "next_recommendation": _next_recommendation(classification),
        "limitations": [
            "true_market_cap_claims_remain_blocked",
            "uses_fdv_or_valuation_proxy_fields_only",
            "support_rule_is_fixed_from_prior_support_audit_not_optimized",
            "leftover_sample_is_date_concentrated_and_reported_separately",
            "formal_descriptive_only_no_validation_or_trading_claim",
        ],
    }
    _assert_guardrails(report)
    paths = _write_outputs(report, tier_support, robustness, Path(output_dir), Path(status_path))
    return report, paths


def load_frozen_fp001_definition(support_summary_path: Path | str) -> dict[str, Any]:
    support_path = Path(support_summary_path)
    support = _read_json(support_path)
    audits = support.get("fingerprint_audits", []) if isinstance(support, dict) else []
    audit = next((row for row in audits if row.get("fingerprint_id") == FP001_ID), None)
    if not audit:
        raise ValueError("fp001_definition_missing_from_support_audit")
    selection_path = ((support.get("source_paths") or {}).get("selection_summary_path")) if isinstance(support, dict) else None
    if not selection_path:
        raise ValueError("fp001_selection_source_missing_from_support_audit")
    selection = _read_json(Path(selection_path))
    selected = selection.get("selected_candidate_fingerprints", []) if isinstance(selection, dict) else []
    design = next((row for row in selected if row.get("fingerprint_id") == FP001_ID), None)
    if not design:
        raise ValueError("fp001_definition_missing_from_selection_report")
    visible = _split_features(design.get("visible_features"))
    hidden = _split_features(design.get("hidden_structural_features"))
    expected = _expected_directions(design.get("expected_directions"))
    audited = _split_features(audit.get("features_audited"))
    feature_list = audited or visible + hidden
    if not feature_list or not expected:
        raise ValueError("fp001_definition_incomplete")
    return {
        "fingerprint_id": FP001_ID,
        "fingerprint_name": audit.get("fingerprint_name") or design.get("fingerprint_name"),
        "feature_list": feature_list,
        "visible_features": visible,
        "hidden_structural_features": hidden,
        "expected_directions": expected,
        "entry_side_or_exit_side": design.get("entry_side_or_exit_side") or "entry_side",
        "required_fields": feature_list,
        "support_counts": {
            "combined_support_rows": _int(audit.get("combined_support_rows"), 0),
            "balanced_support_rows": _int(audit.get("balanced_support_rows"), 0),
            "leftover_support_rows": _int(audit.get("leftover_support_rows"), 0),
            "balanced_high_tier_capture_pct": _number(audit.get("balanced_high_tier_capture_pct")),
            "leftover_high_tier_capture_pct": _number(audit.get("leftover_high_tier_capture_pct")),
        },
        "high_tier_definition_used_by_audit": "reached_500k_but_never_1m;reached_1m_plus",
        "support_method": audit.get("support_method") or "fixed_median_reference_no_threshold_search",
        "support_match_rule": "row_supports_fp001_when_at_least_60pct_of_available_direction_checks_match",
        "support_audit_decision": audit.get("support_audit_decision"),
        "direction_consistency": audit.get("direction_consistency"),
        "missing_fields": design.get("data_still_missing") or "",
        "invalidation_notes": design.get("what_could_invalidate_it") or "",
    }


def _missing_definition_report(reason: str, support_summary_path: Path | str, combined_dataset_path: Path | str) -> dict[str, Any]:
    return {
        "report_id": REPORT_ID,
        "report_type": "fp001_formal_descriptive_thesis",
        "classification": "definition_missing",
        "readiness_classification": "fp001_definition_missing",
        "methodology_flags": [
            "formal_descriptive_thesis_only",
            "fp001_only",
            "fail_closed_definition_missing",
            "no_thesis_execution",
            "no_validation_execution",
            "no_backtest",
            "no_trading_logic",
        ],
        "source_paths": {
            "support_summary_path": str(support_summary_path),
            "combined_dataset_path": str(combined_dataset_path),
        },
        "definition_missing_reason": reason,
        "frozen_fp001_definition": {},
        "rows_analyzed": 0,
        "feature_coverage": {},
        "tier_support_table": [],
        "balanced_leftover_results": {},
        "robustness_checks": [],
        "formal_context_note": {},
        "next_recommendation": "repair_support_audit_before_thesis_execution",
        "limitations": ["fp001_definition_missing_so_no_formal_thesis_was_run"],
    }


def _score_row(row: dict[str, Any], features: list[str], expected: dict[str, str], baselines: dict[str, float | None]) -> dict[str, Any]:
    checks = []
    for feature in features:
        value = _number(row.get(feature))
        baseline = baselines.get(feature)
        if value is None or baseline is None:
            continue
        checks.append(_matches_direction(value, baseline, expected.get(feature)))
    score = sum(1 for check in checks if check) / len(checks) if checks else 0.0
    eligible = bool(checks) and all(_has_value(row.get(feature)) for feature in features)
    return {
        **row,
        "fp001_eligible": eligible,
        "fp001_match_score": round(score, 6),
        "fp001_supports": eligible and score >= 0.60,
        "fp001_checks_available": len(checks),
    }


def _matches_direction(value: float, baseline: float, direction: str | None) -> bool:
    if direction in {"higher", "stable_or_high"}:
        return value >= baseline
    if direction in {"lower", "not_elevated"}:
        return value <= baseline
    if direction == "not_zero":
        return value > 0
    return True


def _feature_baselines(rows: list[dict[str, Any]], features: list[str]) -> dict[str, float | None]:
    return {feature: _median_or_none([_number(row.get(feature)) for row in rows]) for feature in features}


def _feature_coverage(rows: list[dict[str, Any]], features: list[str]) -> dict[str, Any]:
    all_fields = [row for row in rows if all(_has_value(row.get(feature)) for feature in features)]
    tier_counts = {}
    for tier in TIER_ORDER:
        tier_rows = [row for row in rows if row.get("milestone_tier") == tier]
        tier_complete = [row for row in tier_rows if all(_has_value(row.get(feature)) for feature in features)]
        tier_counts[tier] = {
            "rows": len(tier_rows),
            "rows_with_all_fp001_fields": len(tier_complete),
            "coverage_pct": _pct(len(tier_complete), len(tier_rows)),
        }
    date_counts = Counter(str(row.get("launch_date") or "unknown") for row in all_fields)
    creator_counts = Counter(str(row.get("creator") or "unknown") for row in all_fields)
    missing = Counter()
    for row in rows:
        missing_features = [feature for feature in features if not _has_value(row.get(feature))]
        if not missing_features:
            missing["none"] += 1
        else:
            missing[";".join(missing_features)] += 1
    return {
        "total_rows": len(rows),
        "rows_with_all_fp001_fields": len(all_fields),
        "coverage_pct": _pct(len(all_fields), len(rows)),
        "balanced_sample_rows": sum(1 for row in rows if _bool(row.get("is_balanced_sample")) and not _bool(row.get("is_leftover_sample"))),
        "leftover_sample_rows": sum(1 for row in rows if _bool(row.get("is_leftover_sample"))),
        "all_three_p0_rows": sum(1 for row in rows if _bool(row.get("has_all_three_p0_layers"))),
        "coverage_by_milestone_tier": tier_counts,
        "top_dates": dict(date_counts.most_common(10)),
        "top_creators": dict(creator_counts.most_common(10)),
        "missing_reason_counts": dict(missing),
    }


def _tier_support_table(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for tier in TIER_ORDER:
        tier_rows = [row for row in rows if row.get("milestone_tier") == tier]
        support = [row for row in tier_rows if row.get("fp001_supports")]
        output.append(
            {
                "milestone_tier": tier,
                "row_count": len(tier_rows),
                "support_count": len(support),
                "capture_rate_pct": _pct(len(support), len(tier_rows)),
                "precision_like_descriptive_rate_pct": _pct(len(support), sum(1 for row in rows if row.get("fp001_supports"))),
                "balanced_support_count": sum(1 for row in support if _bool(row.get("is_balanced_sample")) and not _bool(row.get("is_leftover_sample"))),
                "leftover_support_count": sum(1 for row in support if _bool(row.get("is_leftover_sample"))),
            }
        )
    return output


def _split_result(rows: list[dict[str, Any]]) -> dict[str, Any]:
    support = [row for row in rows if row.get("fp001_supports")]
    return {
        "rows": len(rows),
        "support_rows": len(support),
        "support_pct": _pct(len(support), len(rows)),
        "date_concentration": _concentration(support, "launch_date"),
        "creator_concentration": _concentration(support, "creator"),
        "targets": {name: _target_result(rows, support, tiers) for name, tiers in TARGETS.items()},
    }


def _target_result(rows: list[dict[str, Any]], support_rows: list[dict[str, Any]], target_tiers: set[str]) -> dict[str, Any]:
    target_rows = [row for row in rows if str(row.get("milestone_tier")) in target_tiers]
    target_support = [row for row in support_rows if str(row.get("milestone_tier")) in target_tiers]
    baseline_rate = _pct(len(target_rows), len(rows))
    support_rate = _pct(len(target_support), len(support_rows))
    return {
        "target_rows": len(target_rows),
        "target_support_rows": len(target_support),
        "target_capture_pct": _pct(len(target_support), len(target_rows)),
        "support_precision_like_rate_pct": support_rate,
        "baseline_target_rate_pct": baseline_rate,
        "support_minus_baseline_pct": round(support_rate - baseline_rate, 4),
    }


def _robustness_checks(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    checks = {
        "combined_sample": rows,
        "balanced_sample_only": _subset(rows, "balanced"),
        "leftover_sample_only": _subset(rows, "leftover"),
    }
    top_dates = [key for key, _count in Counter(str(row.get("launch_date") or "unknown") for row in rows).most_common(3)]
    top_creators = [key for key, _count in Counter(str(row.get("creator") or "unknown") for row in rows).most_common(3)]
    if top_dates:
        checks["exclude_top_date"] = [row for row in rows if str(row.get("launch_date") or "unknown") != top_dates[0]]
        checks["exclude_top_3_dates"] = [row for row in rows if str(row.get("launch_date") or "unknown") not in set(top_dates)]
    if top_creators:
        checks["exclude_top_creator"] = [row for row in rows if str(row.get("creator") or "unknown") != top_creators[0]]
        checks["exclude_top_3_creators"] = [row for row in rows if str(row.get("creator") or "unknown") not in set(top_creators)]
    output = []
    for name, check_rows in checks.items():
        support = [row for row in check_rows if row.get("fp001_supports")]
        one_m = _target_result(check_rows, support, TARGETS["1m_plus"])
        five_hundred = _target_result(check_rows, support, TARGETS["500k_plus"])
        hundred = _target_result(check_rows, support, TARGETS["100k_plus"])
        output.append(
            {
                "check_name": name,
                "rows": len(check_rows),
                "support_rows": len(support),
                "support_pct": _pct(len(support), len(check_rows)),
                "target_100k_plus_support_minus_baseline_pct": hundred["support_minus_baseline_pct"],
                "target_500k_plus_support_minus_baseline_pct": five_hundred["support_minus_baseline_pct"],
                "target_1m_plus_support_minus_baseline_pct": one_m["support_minus_baseline_pct"],
                "leftover_rows_driving_result": name == "leftover_sample_only" and five_hundred["support_minus_baseline_pct"] > one_m["support_minus_baseline_pct"],
            }
        )
    return output


def _classification(rows: list[dict[str, Any]], coverage: dict[str, Any], robustness: list[dict[str, Any]]) -> str:
    if len(rows) < 100:
        return "data_limited"
    if coverage.get("coverage_pct", 0.0) < 50 or not any(row.get("fp001_eligible") for row in rows):
        return "data_limited"
    combined = next((row for row in robustness if row["check_name"] == "combined_sample"), {})
    balanced = next((row for row in robustness if row["check_name"] == "balanced_sample_only"), {})
    leftover = next((row for row in robustness if row["check_name"] == "leftover_sample_only"), {})
    combined_delta = _number(combined.get("target_500k_plus_support_minus_baseline_pct")) or 0.0
    balanced_delta = _number(balanced.get("target_500k_plus_support_minus_baseline_pct")) or 0.0
    leftover_delta = _number(leftover.get("target_500k_plus_support_minus_baseline_pct")) or 0.0
    if combined_delta > 5 and balanced_delta > 0 and leftover_delta > 0:
        return "descriptive_signal_present"
    if combined_delta > 0 or balanced_delta > 0:
        return "weak_signal"
    return "no_signal"


def _next_recommendation(classification: str) -> str:
    if classification == "definition_missing":
        return "repair_support_audit_before_thesis_execution"
    if classification in {"descriptive_signal_present", "weak_signal"}:
        return "design robustness review before any validation; do not promote thesis"
    if classification == "data_limited":
        return "expand descriptive coverage before interpretation"
    return "park FP001 or review alternative frozen fingerprint"


def _write_outputs(
    report: dict[str, Any],
    tier_rows: list[dict[str, Any]],
    robustness_rows: list[dict[str, Any]],
    output_dir: Path,
    status_path: Path,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "summary_json_path": output_dir / "FP001_formal_descriptive_thesis_summary.json",
        "summary_md_path": output_dir / "FP001_formal_descriptive_thesis_summary.md",
        "tier_support_table_path": output_dir / "FP001_tier_support_table.csv",
        "robustness_table_path": output_dir / "FP001_robustness_table.csv",
        "status_path": status_path,
    }
    paths["summary_json_path"].write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")
    paths["summary_md_path"].write_text(_markdown(report), encoding="utf-8")
    _write_csv(tier_rows, paths["tier_support_table_path"])
    _write_csv(robustness_rows, paths["robustness_table_path"])
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(_status_markdown(report), encoding="utf-8")
    return paths


def _markdown(report: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# FP001 Formal Descriptive Thesis",
            "",
            f"- Classification: `{report['classification']}`",
            f"- Rows analyzed: `{report['rows_analyzed']}`",
            f"- Feature coverage: `{report.get('feature_coverage', {}).get('coverage_pct', 0.0)}`",
            f"- Next recommendation: {report['next_recommendation']}",
            "",
            "This is descriptive only. It does not run validation, backtest, paper/live trading, or strategy generation.",
        ]
    ) + "\n"


def _status_markdown(report: dict[str, Any]) -> str:
    definition = report.get("frozen_fp001_definition") or {}
    lines = [
        "# FP001 Formal Descriptive Thesis Status",
        "",
        "## Frozen FP001 Definition",
        f"- Fingerprint: `{definition.get('fingerprint_name', 'missing')}`",
        f"- Features: `{definition.get('feature_list', [])}`",
        f"- Expected directions: `{definition.get('expected_directions', {})}`",
        "",
        "## Dataset Used",
        f"- Rows analyzed: `{report.get('rows_analyzed', 0)}`",
        "",
        "## Feature Coverage",
        f"- `{report.get('feature_coverage', {})}`",
        "",
        "## Milestone Tier Results",
        *[
            f"- `{row['milestone_tier']}`: support `{row['support_count']}` / rows `{row['row_count']}`"
            for row in report.get("tier_support_table", [])
        ],
        "",
        "## Balanced Vs Leftover Results",
        f"- `{report.get('balanced_leftover_results', {})}`",
        "",
        "## Robustness Checks",
        f"- `{report.get('robustness_checks', [])}`",
        "",
        "## Classification",
        f"- `{report['classification']}`",
        "",
        "## Later Robustness Or Validation",
        "Robustness design can be considered later. No validation was run here.",
        "",
        "## Limitations",
        *[f"- `{item}`" for item in report.get("limitations", [])],
        "",
        "## Next Recommendation",
        report["next_recommendation"],
    ]
    return "\n".join(lines) + "\n"


def _concentration(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    counts = Counter(str(row.get(key) or "unknown") for row in rows)
    return {"top_value": counts.most_common(1)[0][0] if counts else None, "top_share_pct": _top_share(counts, len(rows), 1)}


def _subset(rows: list[dict[str, Any]], subset: str) -> list[dict[str, Any]]:
    if subset == "balanced":
        return [row for row in rows if _bool(row.get("is_balanced_sample")) and not _bool(row.get("is_leftover_sample"))]
    if subset == "leftover":
        return [row for row in rows if _bool(row.get("is_leftover_sample"))]
    return rows


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _read_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    if path.suffix == ".parquet":
        import pandas as pd

        return pd.read_parquet(path).to_dict("records")
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if path.suffix == ".csv":
        with path.open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    if path.suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        return [row for row in payload if isinstance(row, dict)] if isinstance(payload, list) else []
    return []


def _write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        if not rows:
            return
        writer = csv.DictWriter(handle, fieldnames=sorted({key for row in rows for key in row}))
        writer.writeheader()
        writer.writerows(rows)


def _split_features(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value is None:
        return []
    return [item.strip() for item in str(value).split(";") if item.strip()]


def _expected_directions(value: Any) -> dict[str, str]:
    if isinstance(value, dict):
        return {str(key): str(val) for key, val in value.items()}
    if not value:
        return {}
    try:
        payload = json.loads(str(value))
    except json.JSONDecodeError:
        return {}
    return {str(key): str(val) for key, val in payload.items()} if isinstance(payload, dict) else {}


def _assert_guardrails(report: dict[str, Any]) -> None:
    text = json.dumps(report, sort_keys=True, default=str).lower()
    for term in UNSUPPORTED_TERMS:
        if term in text:
            raise ValueError(f"Unsupported label found in report: {term}")


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    return bool(value)


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, float) and math.isnan(value):
        return False
    if isinstance(value, str) and value.strip().lower() in {"", "none", "nan", "null"}:
        return False
    return True


def _number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) else number


def _int(value: Any, default: int) -> int:
    number = _number(value)
    return int(number) if number is not None else default


def _median_or_none(values: list[float | None]) -> float | None:
    numeric = [value for value in values if value is not None]
    return median(numeric) if numeric else None


def _pct(num: int, den: int) -> float:
    return round(num / den * 100, 4) if den else 0.0


def _top_share(counts: Counter, total: int, n: int) -> float:
    if not total:
        return 0.0
    return round(sum(count for _key, count in counts.most_common(n)) / total * 100, 4)
