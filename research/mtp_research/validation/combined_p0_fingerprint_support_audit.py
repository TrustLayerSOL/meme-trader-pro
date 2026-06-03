"""Support/coverage audit for selected combined P0 fingerprints."""

from __future__ import annotations

import csv
import json
import math
from collections import Counter
from pathlib import Path
from statistics import median
from typing import Any

from research.mtp_research.data_paths import data_lake_path


REPORT_ID = "combined_p0_fingerprint_support_audit_v0"
DEFAULT_SELECTION_SUMMARY_PATH = data_lake_path(
    "data",
    "backtests",
    "diagnostics",
    "reports",
    "combined_p0_fingerprint_selection",
    "combined_p0_fingerprint_selection_summary.json",
)
DEFAULT_COMBINED_DATASET_PATH = data_lake_path(
    "data", "backtests", "structural_enrichment", "combined_aligned_p0_structural_fingerprint.parquet"
)
DEFAULT_OUTPUT_DIR = data_lake_path(
    "data", "backtests", "diagnostics", "reports", "combined_p0_fingerprint_support_audit"
)
DEFAULT_STATUS_PATH = Path("theses/COMBINED_P0_FINGERPRINT_SUPPORT_AUDIT_STATUS.md")

HIGH_TIERS = {"reached_500k_but_never_1m", "reached_1m_plus"}
LOW_TIERS = {"reached_20k_but_never_50k", "reached_50k_but_never_100k"}
UNSUPPORTED_TERMS = ("insider", "scammer", "wash trader", "manipulator")


def build_combined_p0_fingerprint_support_audit(
    *,
    selection_summary_path: Path | str = DEFAULT_SELECTION_SUMMARY_PATH,
    combined_dataset_path: Path | str = DEFAULT_COMBINED_DATASET_PATH,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    status_path: Path | str = DEFAULT_STATUS_PATH,
) -> tuple[dict[str, Any], dict[str, Path]]:
    selection = _read_json(Path(selection_summary_path))
    rows = _read_records(Path(combined_dataset_path))
    fingerprints = selection.get("selected_candidate_fingerprints", []) if isinstance(selection, dict) else []
    audits = [_audit_fingerprint(fingerprint, rows) for fingerprint in fingerprints]
    source_counts = _source_counts(rows)
    readiness = _readiness(audits)
    report = {
        "report_id": REPORT_ID,
        "report_type": "combined_p0_fingerprint_support_audit",
        "readiness_classification": readiness,
        "methodology_flags": [
            "support_coverage_audit_only",
            "no_thesis_execution",
            "no_validation_execution",
            "no_backtest",
            "no_walk_forward_validation",
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
            "selection_summary_path": str(selection_summary_path),
            "combined_dataset_path": str(combined_dataset_path),
        },
        "source_counts": source_counts,
        "fingerprint_audits": audits,
        "recommended_next_action": _recommended_next_action(audits, readiness),
        "limitations": [
            "support_uses_fixed_median_reference_not_optimized_thresholds",
            "balanced_and_leftover_samples_are_reported_separately",
            "leftover_sample_is_date_concentrated",
            "true_market_cap_claims_remain_blocked",
            "support_audit_does_not_measure_profitability",
        ],
    }
    _assert_guardrails(report)
    paths = _write_outputs(report, Path(output_dir), Path(status_path))
    return report, paths


def _audit_fingerprint(fingerprint: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    features = _split_features(fingerprint.get("visible_features")) + _split_features(
        fingerprint.get("hidden_structural_features")
    )
    expected = _expected_directions(fingerprint.get("expected_directions"))
    balanced_rows = _subset_rows(rows, "balanced")
    leftover_rows = _subset_rows(rows, "leftover")
    combined_support = _support(rows, features, expected)
    balanced_support = _support(balanced_rows, features, expected)
    leftover_support = _support(leftover_rows, features, expected)
    concentration = _concentration(rows, features, expected)
    direction_consistency = _direction_consistency(balanced_rows, leftover_rows, features, expected)
    coverage = _coverage(rows, features)
    decision = _fingerprint_decision(coverage, balanced_support, leftover_support, concentration, direction_consistency)
    return {
        "fingerprint_id": fingerprint.get("fingerprint_id"),
        "fingerprint_name": fingerprint.get("fingerprint_name"),
        "features_audited": ";".join(features),
        "feature_coverage_pct": coverage["coverage_pct"],
        "available_rows": coverage["available_rows"],
        "missing_rows": coverage["missing_rows"],
        "combined_support_rows": combined_support["support_rows"],
        "combined_support_pct": combined_support["support_pct"],
        "combined_high_tier_capture_rows": combined_support["high_tier_capture_rows"],
        "combined_high_tier_capture_pct": combined_support["high_tier_capture_pct"],
        "balanced_support_rows": balanced_support["support_rows"],
        "balanced_support_pct": balanced_support["support_pct"],
        "balanced_high_tier_capture_rows": balanced_support["high_tier_capture_rows"],
        "balanced_high_tier_capture_pct": balanced_support["high_tier_capture_pct"],
        "leftover_support_rows": leftover_support["support_rows"],
        "leftover_support_pct": leftover_support["support_pct"],
        "leftover_high_tier_capture_rows": leftover_support["high_tier_capture_rows"],
        "leftover_high_tier_capture_pct": leftover_support["high_tier_capture_pct"],
        "top_date_share_pct": concentration["top_date_share_pct"],
        "top_creator_share_pct": concentration["top_creator_share_pct"],
        "direction_consistency": direction_consistency,
        "support_audit_decision": decision,
        "formal_thesis_ready": decision == "ready_for_formal_descriptive_thesis",
        "support_method": "fixed_median_reference_no_threshold_search",
    }


def _support(rows: list[dict[str, Any]], features: list[str], expected: dict[str, str]) -> dict[str, Any]:
    if not rows or not features:
        return {
            "eligible_rows": 0,
            "support_rows": 0,
            "support_pct": 0.0,
            "high_tier_capture_rows": 0,
            "high_tier_capture_pct": 0.0,
        }
    baselines = {feature: _median_or_none([_number(row.get(feature)) for row in rows]) for feature in features}
    support_rows = []
    eligible = 0
    for row in rows:
        checks = []
        for feature in features:
            value = _number(row.get(feature))
            baseline = baselines.get(feature)
            if value is None or baseline is None:
                continue
            checks.append(_matches(value, baseline, expected.get(feature)))
        if checks:
            eligible += 1
            if sum(1 for ok in checks if ok) / len(checks) >= 0.6:
                support_rows.append(row)
    high_total = sum(1 for row in rows if str(row.get("milestone_tier")) in HIGH_TIERS)
    high_capture = sum(1 for row in support_rows if str(row.get("milestone_tier")) in HIGH_TIERS)
    return {
        "eligible_rows": eligible,
        "support_rows": len(support_rows),
        "support_pct": _pct(len(support_rows), eligible),
        "high_tier_capture_rows": high_capture,
        "high_tier_capture_pct": _pct(high_capture, high_total),
    }


def _matches(value: float, baseline: float, direction: str | None) -> bool:
    if direction in {"higher", "stable_or_high"}:
        return value >= baseline
    if direction in {"lower", "not_elevated"}:
        return value <= baseline
    if direction == "not_zero":
        return value > 0
    return True


def _direction_consistency(
    balanced_rows: list[dict[str, Any]], leftover_rows: list[dict[str, Any]], features: list[str], expected: dict[str, str]
) -> str:
    if not balanced_rows or not leftover_rows:
        return "sample_missing"
    conflicts = []
    for feature in features:
        balanced = _high_low_direction(balanced_rows, feature)
        leftover = _high_low_direction(leftover_rows, feature)
        if balanced == "coverage_limited" or leftover == "coverage_limited":
            continue
        if balanced != leftover and "flat" not in {balanced, leftover}:
            conflicts.append(feature)
    if conflicts:
        return "conflicting"
    return "consistent_or_flat"


def _high_low_direction(rows: list[dict[str, Any]], feature: str) -> str:
    high = _median_or_none([_number(row.get(feature)) for row in rows if str(row.get("milestone_tier")) in HIGH_TIERS])
    low = _median_or_none([_number(row.get(feature)) for row in rows if str(row.get("milestone_tier")) in LOW_TIERS])
    if high is None or low is None:
        return "coverage_limited"
    if math.isclose(high, low, rel_tol=1e-9, abs_tol=1e-9):
        return "flat"
    return "higher" if high > low else "lower"


def _concentration(rows: list[dict[str, Any]], features: list[str], expected: dict[str, str]) -> dict[str, float]:
    support = _supporting_rows(rows, features, expected)
    date_counts = Counter(str(row.get("launch_date") or "unknown") for row in support)
    creator_counts = Counter(str(row.get("creator") or "unknown") for row in support)
    return {
        "top_date_share_pct": _top_share(date_counts, len(support), 1),
        "top_creator_share_pct": _top_share(creator_counts, len(support), 1),
    }


def _supporting_rows(rows: list[dict[str, Any]], features: list[str], expected: dict[str, str]) -> list[dict[str, Any]]:
    baselines = {feature: _median_or_none([_number(row.get(feature)) for row in rows]) for feature in features}
    output = []
    for row in rows:
        checks = []
        for feature in features:
            value = _number(row.get(feature))
            baseline = baselines.get(feature)
            if value is None or baseline is None:
                continue
            checks.append(_matches(value, baseline, expected.get(feature)))
        if checks and sum(1 for ok in checks if ok) / len(checks) >= 0.6:
            output.append(row)
    return output


def _fingerprint_decision(
    coverage: dict[str, Any],
    balanced_support: dict[str, Any],
    leftover_support: dict[str, Any],
    concentration: dict[str, float],
    direction_consistency: str,
) -> str:
    if coverage["coverage_pct"] < 50:
        return "needs_more_enrichment"
    if direction_consistency == "conflicting":
        return "needs_manual_support_review"
    if concentration["top_date_share_pct"] > 25 or concentration["top_creator_share_pct"] > 15:
        return "needs_concentration_review"
    if balanced_support["high_tier_capture_pct"] >= 35 and leftover_support["high_tier_capture_pct"] >= 25:
        return "ready_for_formal_descriptive_thesis"
    return "needs_more_support_review"


def _readiness(audits: list[dict[str, Any]]) -> str:
    if any(row["support_audit_decision"] == "ready_for_formal_descriptive_thesis" for row in audits):
        return "fingerprint_support_ready_for_formal_thesis"
    if any(row["support_audit_decision"].startswith("needs_") for row in audits):
        return "fingerprint_support_needs_more_review"
    return "fingerprint_support_inconclusive"


def _recommended_next_action(audits: list[dict[str, Any]], readiness: str) -> str:
    ready = [row for row in audits if row["support_audit_decision"] == "ready_for_formal_descriptive_thesis"]
    if readiness == "fingerprint_support_ready_for_formal_thesis" and ready:
        return f"Run formal descriptive thesis design for {ready[0]['fingerprint_id']} only; keep no validation and no trading guardrails."
    if any(row["support_audit_decision"] == "needs_concentration_review" for row in audits):
        return "Review support concentration by date and creator before any formal thesis."
    if any(row["support_audit_decision"] == "needs_manual_support_review" for row in audits):
        return "Review balanced-versus-leftover direction conflicts before any formal thesis."
    return "Keep fingerprints frozen and review support tables manually before any formal thesis."


def _source_counts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "combined_rows": len(rows),
        "balanced_rows": sum(1 for row in rows if _bool(row.get("is_balanced_sample")) and not _bool(row.get("is_leftover_sample"))),
        "leftover_rows": sum(1 for row in rows if _bool(row.get("is_leftover_sample"))),
        "high_tier_rows": sum(1 for row in rows if str(row.get("milestone_tier")) in HIGH_TIERS),
        "low_tier_rows": sum(1 for row in rows if str(row.get("milestone_tier")) in LOW_TIERS),
    }


def _coverage(rows: list[dict[str, Any]], features: list[str]) -> dict[str, Any]:
    if not rows:
        return {"available_rows": 0, "missing_rows": 0, "coverage_pct": 0.0}
    available = sum(1 for row in rows if any(_has_value(row.get(feature)) for feature in features))
    return {"available_rows": available, "missing_rows": len(rows) - available, "coverage_pct": _pct(available, len(rows))}


def _write_outputs(report: dict[str, Any], output_dir: Path, status_path: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "summary_json_path": output_dir / "combined_p0_fingerprint_support_audit_summary.json",
        "summary_md_path": output_dir / "combined_p0_fingerprint_support_audit_summary.md",
        "fingerprint_support_table_path": output_dir / "fingerprint_support_audit_table.csv",
        "status_path": status_path,
    }
    paths["summary_json_path"].write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")
    paths["summary_md_path"].write_text(_markdown(report), encoding="utf-8")
    _write_csv(report["fingerprint_audits"], paths["fingerprint_support_table_path"])
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(_status_markdown(report), encoding="utf-8")
    return paths


def _markdown(report: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Combined P0 Fingerprint Support Audit",
            "",
            f"- Readiness: `{report['readiness_classification']}`",
            f"- Combined rows: `{report['source_counts']['combined_rows']}`",
            f"- Recommended next action: {report['recommended_next_action']}",
            "",
            "This is a support/coverage audit only. It does not run a thesis, validation, backtest, or trading workflow.",
        ]
    ) + "\n"


def _status_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Combined P0 Fingerprint Support Audit Status",
        "",
        "## Scope",
        "Support and coverage audit for frozen combined P0 fingerprints before any formal descriptive thesis.",
        "",
        "## Readiness",
        f"- `{report['readiness_classification']}`",
        "",
        "## Fingerprint Decisions",
    ]
    for row in report["fingerprint_audits"]:
        lines.append(
            f"- `{row['fingerprint_id']}`: {row['support_audit_decision']} "
            f"(balanced high-tier capture `{row['balanced_high_tier_capture_pct']}`, "
            f"leftover high-tier capture `{row['leftover_high_tier_capture_pct']}`)"
        )
    lines.extend(
        [
            "",
            "## Recommended Next Action",
            report["recommended_next_action"],
            "",
            "## Guardrails",
            "No thesis, validation, backtest, paper/live trading, threshold search, or strategy generation was run.",
            "",
            "## Limitations",
            *[f"- `{item}`" for item in report["limitations"]],
        ]
    )
    return "\n".join(lines) + "\n"


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


def _subset_rows(rows: list[dict[str, Any]], subset: str) -> list[dict[str, Any]]:
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
    if path.suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        return [row for row in payload if isinstance(row, dict)] if isinstance(payload, list) else []
    if path.suffix == ".csv":
        with path.open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    return []


def _write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        if not rows:
            return
        writer = csv.DictWriter(handle, fieldnames=sorted({key for row in rows for key in row}))
        writer.writeheader()
        writer.writerows(rows)


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


def _median_or_none(values: list[float | None]) -> float | None:
    numeric = [value for value in values if value is not None]
    return median(numeric) if numeric else None


def _pct(num: int, den: int) -> float:
    return round(num / den * 100, 4) if den else 0.0


def _top_share(counts: Counter, total: int, n: int) -> float:
    if not total:
        return 0.0
    return round(sum(count for _key, count in counts.most_common(n)) / total * 100, 4)
