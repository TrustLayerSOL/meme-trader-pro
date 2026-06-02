"""Descriptive T003 creator-archetype history thesis cycle."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any

from research.mtp_research.validation.robust_return_metrics import winsorized_mean


THESIS_ID = "T003"
THESIS_NAME = "Creator Archetype History"
ALLOWED_CLASSIFICATIONS = {
    "descriptive_signal_present",
    "weak_signal",
    "no_signal",
    "data_limited",
}
HISTORY_FEATURES = [
    "creator_prior_launch_count",
    "creator_prior_launches_last_24h",
    "creator_prior_launches_last_7d",
    "creator_prior_launches_last_30d",
    "time_since_creator_previous_launch",
    "creator_launch_velocity_24h",
    "creator_launch_velocity_7d",
    "creator_launch_velocity_30d",
    "creator_prior_median_fdv_proxy_runup",
    "creator_prior_median_fdv_proxy_drawdown",
    "creator_prior_price_availability_rate",
    "creator_prior_liquidity_proxy_availability_rate",
]
FIELD_AUDIT_FIELDS = [
    "creator",
    "deployer",
    "mint",
    "launch_id",
    "block_time",
    "FDV-proxy outcomes",
    "FDV-proxy runup",
    "FDV-proxy drawdown",
    "120m price availability",
    "120m liquidity-proxy availability",
]


def build_t003_creator_archetype_report(
    *,
    candidates_path: Path | str,
    snapshots_path: Path | str,
    outcomes_path: Path | str,
    bucket_count: int = 5,
) -> dict[str, Any]:
    candidates = _read_jsonl(candidates_path)
    snapshots_by_mint = _group_by_mint(_read_jsonl(snapshots_path))
    outcomes_by_mint = {row["token_mint"]: row for row in _read_jsonl(outcomes_path)}
    base_rows = [
        _base_launch_row(
            candidate=candidate,
            snapshots=snapshots_by_mint.get(candidate["token_mint"], []),
            outcome=outcomes_by_mint.get(candidate["token_mint"], {}),
        )
        for candidate in candidates
    ]
    base_rows = sorted(base_rows, key=lambda row: (row.get("block_time") or 0, row.get("token_mint", "")))
    launch_rows = _attach_creator_history(base_rows)
    feature_reports = {feature: _feature_report(launch_rows, feature, bucket_count) for feature in HISTORY_FEATURES}
    creator_cohort_report = _creator_cohort_report(launch_rows)
    field_audit = _field_coverage_audit(launch_rows)
    missing_value_audit = _missing_value_audit(launch_rows)
    creator_counts = _creator_counts(launch_rows)
    sensitivity_checks = _sensitivity_checks(launch_rows, feature_reports)
    warning_flags = _warning_flags(launch_rows, field_audit)
    classification = _classify(
        launch_rows=launch_rows,
        feature_reports=feature_reports,
        creator_cohort_report=creator_cohort_report,
        warning_flags=warning_flags,
    )
    return {
        "thesis_id": THESIS_ID,
        "thesis_name": THESIS_NAME,
        "research_question": (
            "Do creators/deployers leave repeatable historical fingerprints that are "
            "associated with launch outcomes?"
        ),
        "hypothesis": (
            "Creators with prior launch history may exhibit different lifecycle outcome "
            "distributions than creators without prior history."
        ),
        "dataset": {
            "candidates_path": str(candidates_path),
            "snapshots_path": str(snapshots_path),
            "outcomes_path": str(outcomes_path),
            "launch_count": len(launch_rows),
            "strict_launch_regime": True,
            "valuation_semantics": "fdv_proxy_only",
            "true_market_cap_claims": "blocked",
        },
        "methodology": {
            "bucket_method": "deterministic_rank_quantile_buckets",
            "bucket_count": bucket_count,
            "creator_cohorts": {
                "A_0_prior_launches": "0 prior launches",
                "B_1_prior_launch": "1 prior launch",
                "C_2_to_4_prior_launches": "2-4 prior launches",
                "D_5_plus_prior_launches": "5+ prior launches",
            },
            "history_rule": "creator history only uses launches with block_time strictly earlier than current launch",
            "candidate_features": HISTORY_FEATURES,
            "classification_options": sorted(ALLOWED_CLASSIFICATIONS),
        },
        "methodology_flags": [
            "research_only",
            "no_trading_rules",
            "no_profitability_claims",
            "no_entry_exit_logic",
            "no_threshold_optimization",
            "no_grid_search",
            "no_ml_black_boxes",
            "no_future_leakage",
            "fdv_proxy_not_true_market_cap",
        ],
        "field_coverage_audit": field_audit,
        "launch_rows": launch_rows,
        "sample_counts": _sample_counts(launch_rows),
        "creator_counts": creator_counts,
        "outcome_coverage": _outcome_coverage(launch_rows),
        "missing_value_audit": missing_value_audit,
        "feature_reports": feature_reports,
        "creator_cohort_report": creator_cohort_report,
        "sensitivity_checks": sensitivity_checks,
        "final_classification": classification,
        "warning_flags": warning_flags,
        "limitations": _limitations(warning_flags),
        "leakage_controls": [
            "Rows are sorted by block_time before history construction.",
            "A creator's current launch is added to history only after its features are computed.",
            "Creator quality history uses only prior rows where prior.block_time < current.block_time.",
            "Same-timestamp launches do not count as prior history.",
        ],
        "next_recommendation": _next_recommendation(warning_flags, classification),
        "reproducible_command": _reproducible_command(candidates_path, snapshots_path, outcomes_path, bucket_count),
    }


def write_t003_report_outputs(
    report: dict[str, Any],
    *,
    output_dir: Path | str,
    status_path: Path | str,
) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "T003_creator_archetype_history_summary.json"
    markdown_path = output / "T003_creator_archetype_history_summary.md"
    json_path.write_text(json.dumps(_public_report(report), indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(_markdown_summary(report), encoding="utf-8")
    status = Path(status_path)
    status.parent.mkdir(parents=True, exist_ok=True)
    status.write_text(_status_markdown(report, markdown_path, json_path), encoding="utf-8")
    return {"json_summary_path": json_path, "markdown_summary_path": markdown_path, "status_path": status}


def _base_launch_row(
    *,
    candidate: dict[str, Any],
    snapshots: list[dict[str, Any]],
    outcome: dict[str, Any],
) -> dict[str, Any]:
    mint = candidate["token_mint"]
    block_time = _int_or_none(candidate.get("block_time") or candidate.get("launch_ts"))
    creator = _creator(candidate)
    deployer = _deployer(candidate)
    return {
        "launch_id": candidate.get("launch_id"),
        "token_mint": mint,
        "mint": candidate.get("mint") or mint,
        "creator": creator,
        "deployer": deployer,
        "block_time": block_time,
        "launch_ts": _int_or_none(candidate.get("launch_ts")) or block_time,
        "launch_regime": candidate.get("launch_regime"),
        "outcomes": _fdv_outcomes(snapshots, outcome),
        "metadata_json": {
            "creator_source": _creator_source(candidate),
            "deployer_source": _deployer_source(candidate),
            "source_candidate_metadata": candidate.get("metadata_json") or {},
        },
    }


def _attach_creator_history(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    history_by_creator: dict[str, list[dict[str, Any]]] = defaultdict(list)
    output = []
    for row in rows:
        creator = row.get("creator")
        block_time = row.get("block_time")
        prior = [
            prior_row for prior_row in history_by_creator.get(str(creator), [])
            if creator and block_time is not None and prior_row.get("block_time") is not None
            and prior_row["block_time"] < block_time
        ]
        features = _creator_history_features(prior, block_time)
        enriched = dict(row)
        enriched["features"] = features
        enriched["creator_cohort"] = _creator_cohort(features["creator_prior_launch_count"])
        metadata = dict(row.get("metadata_json") or {})
        metadata.update(
            {
                "history_launch_ids": [prior_row.get("launch_id") for prior_row in prior],
                "history_max_block_time": max((prior_row.get("block_time") for prior_row in prior), default=None),
                "leakage_rule": "strict_prior_block_time_only",
            }
        )
        enriched["metadata_json"] = metadata
        output.append(enriched)
        if creator and block_time is not None:
            history_by_creator[str(creator)].append(enriched)
    return output


def _creator_history_features(prior: list[dict[str, Any]], block_time: int | None) -> dict[str, Any]:
    prior_times = [row["block_time"] for row in prior if row.get("block_time") is not None]
    last_time = max(prior_times) if prior_times else None
    return {
        "creator_prior_launch_count": len(prior),
        "creator_is_repeat_before_launch": bool(prior),
        "creator_prior_launches_last_24h": _prior_count_since(prior_times, block_time, 24 * 3600),
        "creator_prior_launches_last_7d": _prior_count_since(prior_times, block_time, 7 * 24 * 3600),
        "creator_prior_launches_last_30d": _prior_count_since(prior_times, block_time, 30 * 24 * 3600),
        "time_since_creator_previous_launch": (block_time - last_time) if block_time is not None and last_time else None,
        "creator_launch_velocity_24h": _velocity(prior_times, block_time, 24 * 3600),
        "creator_launch_velocity_7d": _velocity(prior_times, block_time, 7 * 24 * 3600),
        "creator_launch_velocity_30d": _velocity(prior_times, block_time, 30 * 24 * 3600),
        "creator_prior_median_fdv_proxy_runup": _median(
            [_float_or_none(row["outcomes"].get("fdv_proxy_runup_120m")) for row in prior]
        ),
        "creator_prior_median_fdv_proxy_drawdown": _median(
            [_float_or_none(row["outcomes"].get("fdv_proxy_drawdown_120m")) for row in prior]
        ),
        "creator_prior_price_availability_rate": _true_rate(
            row["outcomes"].get("price_available_120m") for row in prior
        ),
        "creator_prior_liquidity_proxy_availability_rate": _true_rate(
            row["outcomes"].get("liquidity_proxy_available_120m") for row in prior
        ),
    }


def _fdv_outcomes(snapshots: list[dict[str, Any]], outcome: dict[str, Any]) -> dict[str, Any]:
    valued = sorted(
        [
            row for row in snapshots
            if row.get("valuation_proxy_available") and _float_or_none(row.get("valuation_proxy_usd")) is not None
        ],
        key=lambda row: int(row.get("launch_age_seconds", 0)),
    )
    values = [_float_or_none(row.get("valuation_proxy_usd")) for row in valued]
    values = [value for value in values if value is not None]
    if values and values[0] not in (None, 0):
        base = values[0]
        runup = (max(values) / base) - 1
        drawdown = (min(values) / base) - 1
        ret = (values[-1] / base) - 1
    else:
        runup = None
        drawdown = None
        ret = None
    return {
        "fdv_proxy_runup_120m": runup,
        "fdv_proxy_drawdown_120m": drawdown,
        "fdv_proxy_return_120m": ret,
        "price_available_120m": bool(outcome.get("price_available_120m") or outcome.get("has_price_at_120m")),
        "liquidity_proxy_available_120m": bool(
            outcome.get("has_liquidity_proxy_at_120m") or outcome.get("liquidity_survival_120m")
        ),
        "proxy_threshold_outcomes_usable": bool(outcome.get("proxy_threshold_outcomes_usable")),
        "true_market_cap_available": bool(outcome.get("true_market_cap_available")),
    }


def _field_coverage_audit(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    total = len(rows)
    checks = {
        "creator": lambda row: row.get("creator") is not None,
        "deployer": lambda row: row.get("deployer") is not None,
        "mint": lambda row: row.get("mint") is not None or row.get("token_mint") is not None,
        "launch_id": lambda row: row.get("launch_id") is not None,
        "block_time": lambda row: row.get("block_time") is not None,
        "FDV-proxy outcomes": lambda row: row["outcomes"].get("fdv_proxy_runup_120m") is not None
        or row["outcomes"].get("fdv_proxy_drawdown_120m") is not None,
        "FDV-proxy runup": lambda row: row["outcomes"].get("fdv_proxy_runup_120m") is not None,
        "FDV-proxy drawdown": lambda row: row["outcomes"].get("fdv_proxy_drawdown_120m") is not None,
        "120m price availability": lambda row: row["outcomes"].get("price_available_120m") is not None,
        "120m liquidity-proxy availability": lambda row: row["outcomes"].get("liquidity_proxy_available_120m") is not None,
    }
    audit = {}
    for field in FIELD_AUDIT_FIELDS:
        available = sum(1 for row in rows if checks[field](row))
        audit[field] = {
            "available_rows": available,
            "missing_rows": total - available,
            "coverage_pct": (available / total * 100) if total else 0,
        }
    return audit


def _feature_report(rows: list[dict[str, Any]], feature: str, bucket_count: int) -> dict[str, Any]:
    usable = [row for row in rows if _feature_value(row, feature) is not None]
    values = [_feature_value(row, feature) for row in usable]
    values = [value for value in values if value is not None]
    buckets = _bucket_tables(usable, feature, bucket_count)
    return {
        "feature": feature,
        "sample_count": len(rows),
        "usable_count": len(usable),
        "missing_count": len(rows) - len(usable),
        "bucket_count": len(buckets),
        "quantile_definitions": "deterministic rank buckets over non-missing values",
        "distribution_summary": _distribution_summary(values),
        "bucket_tables": buckets,
        "robust_median_summary": _outcome_summary(usable),
        "outlier_adjusted_summary": {
            "winsorized_mean_fdv_proxy_runup_120m": winsorized_mean(
                [_float_or_none(row["outcomes"].get("fdv_proxy_runup_120m")) for row in usable]
            ),
            "winsorized_mean_fdv_proxy_drawdown_120m": winsorized_mean(
                [_float_or_none(row["outcomes"].get("fdv_proxy_drawdown_120m")) for row in usable]
            ),
        },
    }


def _creator_cohort_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[row["creator_cohort"]].append(row)
    ordered = {}
    for cohort in (
        "A_0_prior_launches",
        "B_1_prior_launch",
        "C_2_to_4_prior_launches",
        "D_5_plus_prior_launches",
    ):
        ordered[cohort] = _outcome_summary(groups.get(cohort, []))
    return ordered


def _bucket_tables(rows: list[dict[str, Any]], feature: str, bucket_count: int) -> list[dict[str, Any]]:
    usable = sorted(
        rows,
        key=lambda row: (
            _feature_value(row, feature),
            row.get("block_time") or 0,
            row.get("token_mint", ""),
        ),
    )
    if not usable:
        return []
    buckets = [[] for _ in range(min(bucket_count, len(usable)))]
    for index, row in enumerate(usable):
        bucket_index = min(len(buckets) - 1, int(index * len(buckets) / len(usable)))
        buckets[bucket_index].append(row)
    return [_summarize_bucket(feature, index + 1, bucket) for index, bucket in enumerate(buckets)]


def _summarize_bucket(feature: str, bucket_number: int, rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [_feature_value(row, feature) for row in rows]
    values = [value for value in values if value is not None]
    summary = _outcome_summary(rows)
    summary.update(
        {
            "bucket": f"q{bucket_number}",
            "feature_min": min(values) if values else None,
            "feature_max": max(values) if values else None,
        }
    )
    return summary


def _outcome_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    runups = [_float_or_none(row["outcomes"].get("fdv_proxy_runup_120m")) for row in rows]
    drawdowns = [_float_or_none(row["outcomes"].get("fdv_proxy_drawdown_120m")) for row in rows]
    return {
        "sample_count": len(rows),
        "token_count": len({row["token_mint"] for row in rows}),
        "creator_count": len({row.get("creator") for row in rows if row.get("creator")}),
        "median_fdv_proxy_runup_120m": _median(runups),
        "median_fdv_proxy_drawdown_120m": _median(drawdowns),
        "price_available_120m_rate": _true_rate(row["outcomes"].get("price_available_120m") for row in rows),
        "liquidity_proxy_available_120m_rate": _true_rate(
            row["outcomes"].get("liquidity_proxy_available_120m") for row in rows
        ),
    }


def _sample_counts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "launch_count": len(rows),
        "token_count": len({row["token_mint"] for row in rows}),
        "launch_regime_counts": dict(sorted(Counter(row.get("launch_regime") for row in rows).items())),
    }


def _creator_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    creator_counter = Counter(row.get("creator") for row in rows if row.get("creator"))
    return {
        "creator_count": len(creator_counter),
        "repeat_creator_count": sum(1 for count in creator_counter.values() if count > 1),
        "launches_from_repeat_creators": sum(count for count in creator_counter.values() if count > 1),
    }


def _outcome_coverage(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "fdv_proxy_runup_available": sum(1 for row in rows if row["outcomes"].get("fdv_proxy_runup_120m") is not None),
        "fdv_proxy_drawdown_available": sum(
            1 for row in rows if row["outcomes"].get("fdv_proxy_drawdown_120m") is not None
        ),
        "price_available_120m": sum(1 for row in rows if row["outcomes"].get("price_available_120m")),
        "liquidity_proxy_available_120m": sum(
            1 for row in rows if row["outcomes"].get("liquidity_proxy_available_120m")
        ),
    }


def _missing_value_audit(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    audit = {}
    for feature in HISTORY_FEATURES:
        missing = sum(1 for row in rows if _feature_value(row, feature) is None)
        audit[feature] = {
            "available_count": len(rows) - missing,
            "missing_count": missing,
            "missing_rate": (missing / len(rows)) if rows else None,
        }
    return audit


def _sensitivity_checks(rows: list[dict[str, Any]], feature_reports: dict[str, dict[str, Any]]) -> dict[str, Any]:
    creator_counter = Counter(row.get("creator") for row in rows if row.get("creator"))
    top_creators = [creator for creator, _ in creator_counter.most_common(5)]
    return {
        "minimum_bucket_size_audit": {
            feature: min((bucket["sample_count"] for bucket in report["bucket_tables"]), default=0)
            for feature, report in feature_reports.items()
        },
        "creator_concentration_audit": {
            "top_creator": top_creators[0] if top_creators else None,
            "top_creator_launch_count": creator_counter[top_creators[0]] if top_creators else 0,
            "top_5_creator_launch_count": sum(creator_counter[creator] for creator in top_creators),
            "top_5_creator_share": (sum(creator_counter[creator] for creator in top_creators) / len(rows)) if rows else None,
        },
        "exclude_top_creator": _outcome_summary([row for row in rows if row.get("creator") not in top_creators[:1]]),
        "exclude_top_5_creators": _outcome_summary([row for row in rows if row.get("creator") not in top_creators]),
        "observed_signal_survives_concentration_checks": _signal_survives_concentration(rows, top_creators),
    }


def _warning_flags(rows: list[dict[str, Any]], field_audit: dict[str, dict[str, Any]]) -> list[str]:
    warnings = []
    if field_audit["creator"]["missing_rows"]:
        warnings.append("creator_missing")
    if field_audit["block_time"]["missing_rows"]:
        warnings.append("block_time_missing")
    if field_audit["FDV-proxy runup"]["missing_rows"] or field_audit["FDV-proxy drawdown"]["missing_rows"]:
        warnings.append("fdv_proxy_outcomes_missing")
    if not any(row["outcomes"].get("true_market_cap_available") for row in rows):
        warnings.append("true_market_cap_claims_blocked")
    if not any(row["features"].get("creator_is_repeat_before_launch") for row in rows):
        warnings.append("repeat_creator_history_unavailable")
    return warnings


def _classify(
    *,
    launch_rows: list[dict[str, Any]],
    feature_reports: dict[str, dict[str, Any]],
    creator_cohort_report: dict[str, Any],
    warning_flags: list[str],
) -> str:
    if len(launch_rows) < 100 or "fdv_proxy_outcomes_missing" in warning_flags or "block_time_missing" in warning_flags:
        return "data_limited"
    cohort_a = creator_cohort_report["A_0_prior_launches"]
    repeat_rows = [
        row for row in launch_rows
        if row["creator_cohort"] in {"B_1_prior_launch", "C_2_to_4_prior_launches", "D_5_plus_prior_launches"}
    ]
    repeat_summary = _outcome_summary(repeat_rows)
    if repeat_summary["sample_count"] < 25 or cohort_a["sample_count"] < 25:
        return "data_limited"
    signals = 0
    if _better_runup(repeat_summary, cohort_a):
        signals += 1
    prior_quality_report = feature_reports["creator_prior_median_fdv_proxy_runup"]
    buckets = prior_quality_report["bucket_tables"]
    if len(buckets) >= 2 and _better_runup(buckets[-1], buckets[0]):
        signals += 1
    if signals >= 2:
        return "descriptive_signal_present"
    if signals == 1:
        return "weak_signal"
    return "no_signal"


def _better_runup(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_runup = _float_or_none(left.get("median_fdv_proxy_runup_120m"))
    right_runup = _float_or_none(right.get("median_fdv_proxy_runup_120m"))
    return left_runup is not None and right_runup is not None and left_runup > right_runup


def _signal_survives_concentration(rows: list[dict[str, Any]], top_creators: list[str]) -> bool | None:
    if not rows:
        return None
    full = _repeat_vs_new_runup_delta(rows)
    without_top = _repeat_vs_new_runup_delta([row for row in rows if row.get("creator") not in top_creators[:1]])
    without_top5 = _repeat_vs_new_runup_delta([row for row in rows if row.get("creator") not in top_creators])
    if full is None:
        return None
    return (without_top is not None and without_top > 0) and (without_top5 is not None and without_top5 > 0)


def _repeat_vs_new_runup_delta(rows: list[dict[str, Any]]) -> float | None:
    new_rows = [row for row in rows if row["creator_cohort"] == "A_0_prior_launches"]
    repeat_rows = [row for row in rows if row["creator_cohort"] != "A_0_prior_launches"]
    new_runup = _outcome_summary(new_rows)["median_fdv_proxy_runup_120m"]
    repeat_runup = _outcome_summary(repeat_rows)["median_fdv_proxy_runup_120m"]
    if new_runup is None or repeat_runup is None:
        return None
    return repeat_runup - new_runup


def _limitations(warning_flags: list[str]) -> list[str]:
    limitations = [
        "FDV proxy is not true market cap because circulating supply is unavailable.",
        "This cycle is descriptive research only and does not produce trading rules.",
        "Creator/deployer history is limited to creators visible in the strict launch-regime dataset.",
    ]
    if "creator_missing" in warning_flags:
        limitations.append("Some launches are missing creator/deployer identity fields.")
    if "repeat_creator_history_unavailable" in warning_flags:
        limitations.append("Repeat-creator history is unavailable or too sparse for cohort claims.")
    return limitations


def _next_recommendation(warning_flags: list[str], classification: str) -> str:
    if "creator_missing" in warning_flags:
        return "improve creator/deployer extraction before relying on archetype comparisons"
    if classification == "data_limited":
        return "increase creator-history coverage before rerunning T003"
    return "rerun with broader chronological launch census before any thesis status change"


def _public_report(report: dict[str, Any]) -> dict[str, Any]:
    public = dict(report)
    public.pop("launch_rows", None)
    return public


def _markdown_summary(report: dict[str, Any]) -> str:
    lines = [
        "# T003 Creator Archetype History",
        "",
        f"- Final classification: `{report['final_classification']}`",
        f"- Launch count: `{report['sample_counts']['launch_count']}`",
        f"- Creator count: `{report['creator_counts']['creator_count']}`",
        f"- Repeat creator count: `{report['creator_counts']['repeat_creator_count']}`",
        f"- Warning flags: `{report['warning_flags']}`",
        "",
        "## Feature Coverage Audit",
        "",
        "| Field | Available Rows | Missing Rows | Coverage |",
        "|---|---:|---:|---:|",
    ]
    for field, audit in report["field_coverage_audit"].items():
        lines.append(
            f"| `{field}` | {audit['available_rows']} | {audit['missing_rows']} | {audit['coverage_pct']:.2f}% |"
        )
    lines.extend(["", "## Creator Cohorts", ""])
    lines.extend(_summary_table(report["creator_cohort_report"]))
    lines.extend(["", "## Creator History Feature Buckets", ""])
    for feature, feature_report in report["feature_reports"].items():
        lines.extend([f"### `{feature}`", ""])
        lines.extend(_summary_table({"bucket": bucket for bucket in feature_report["bucket_tables"]}))
        if not feature_report["bucket_tables"]:
            lines.append("No usable buckets.")
        lines.append("")
    lines.extend(
        [
            "## Robustness Checks",
            "",
            f"- Top creator: `{report['sensitivity_checks']['creator_concentration_audit']['top_creator']}`",
            f"- Top creator launch count: `{report['sensitivity_checks']['creator_concentration_audit']['top_creator_launch_count']}`",
            f"- Top 5 creator share: `{_format_pct(report['sensitivity_checks']['creator_concentration_audit']['top_5_creator_share'])}`",
            f"- Signal survives concentration checks: `{report['sensitivity_checks']['observed_signal_survives_concentration_checks']}`",
            "",
            "## Leakage Controls",
            "",
            *[f"- {item}" for item in report["leakage_controls"]],
            "",
            "## Limitations",
            "",
            *[f"- {item}" for item in report["limitations"]],
            "",
            "## Reproducible Command",
            "",
            "```bash",
            report["reproducible_command"],
            "```",
        ]
    )
    return "\n".join(lines) + "\n"


def _summary_table(items: dict[str, dict[str, Any]]) -> list[str]:
    lines = [
        "| Group | Samples | Median FDV Runup | Median FDV Drawdown | Price 120m | Liquidity 120m |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for key, summary in items.items():
        lines.append(
            f"| `{key}` | {summary.get('sample_count', 0)} | "
            f"{_format_pct(summary.get('median_fdv_proxy_runup_120m'))} | "
            f"{_format_pct(summary.get('median_fdv_proxy_drawdown_120m'))} | "
            f"{_format_pct(summary.get('price_available_120m_rate'))} | "
            f"{_format_pct(summary.get('liquidity_proxy_available_120m_rate'))} |"
        )
    return lines


def _status_markdown(report: dict[str, Any], markdown_path: Path, json_path: Path) -> str:
    return "\n".join(
        [
            "# T003 Creator Archetype History Status",
            "",
            "## Thesis Description",
            "",
            "Do creators/deployers leave repeatable historical fingerprints that are associated with launch outcomes?",
            "",
            "## Dataset Used",
            "",
            "- Strict launch-regime FDV-proxy lifecycle dataset",
            f"- Launches analyzed: `{report['sample_counts']['launch_count']}`",
            f"- Creator count: `{report['creator_counts']['creator_count']}`",
            f"- Repeat creator count: `{report['creator_counts']['repeat_creator_count']}`",
            "",
            "## Feature Coverage",
            "",
            *[
                f"- `{field}`: `{audit['coverage_pct']:.2f}%`"
                for field, audit in report["field_coverage_audit"].items()
            ],
            "",
            "## Outcome Coverage",
            "",
            *[f"- `{key}`: `{value}`" for key, value in report["outcome_coverage"].items()],
            "",
            "## Classification",
            "",
            f"`{report['final_classification']}`",
            "",
            "## Limitations",
            "",
            *[f"- {item}" for item in report["limitations"]],
            "",
            "## Leakage Controls",
            "",
            *[f"- {item}" for item in report["leakage_controls"]],
            "",
            "## Next Recommendation",
            "",
            report["next_recommendation"],
            "",
            f"- Markdown summary: `{markdown_path}`",
            f"- JSON summary: `{json_path}`",
            "- No trading rules were generated.",
            "- No profitability claims were generated.",
            "- True market-cap claims remain blocked.",
            "",
        ]
    )


def _reproducible_command(
    candidates_path: Path | str,
    snapshots_path: Path | str,
    outcomes_path: Path | str,
    bucket_count: int,
) -> str:
    return (
        "./trading_env/bin/python -m research.mtp_research.validation.run_creator_archetype_history_thesis "
        f"--candidates-path \"{candidates_path}\" "
        f"--snapshots-path \"{snapshots_path}\" "
        f"--outcomes-path \"{outcomes_path}\" "
        f"--bucket-count {bucket_count}"
    )


def _creator(candidate: dict[str, Any]) -> str | None:
    metadata = candidate.get("metadata_json") or {}
    return _first_present(
        candidate.get("creator"),
        candidate.get("creator_wallet"),
        candidate.get("deployer"),
        metadata.get("creator_deployer"),
        metadata.get("creator"),
        metadata.get("creator_wallet"),
        metadata.get("deployer"),
    )


def _deployer(candidate: dict[str, Any]) -> str | None:
    metadata = candidate.get("metadata_json") or {}
    return _first_present(
        candidate.get("deployer"),
        candidate.get("creator"),
        candidate.get("creator_wallet"),
        metadata.get("deployer"),
        metadata.get("creator_deployer"),
        metadata.get("creator"),
        metadata.get("creator_wallet"),
    )


def _creator_source(candidate: dict[str, Any]) -> str | None:
    metadata = candidate.get("metadata_json") or {}
    for key in ("creator", "creator_wallet", "deployer"):
        if candidate.get(key):
            return key
    for key in ("creator_deployer", "creator", "creator_wallet", "deployer"):
        if metadata.get(key):
            return f"metadata_json.{key}"
    return None


def _deployer_source(candidate: dict[str, Any]) -> str | None:
    metadata = candidate.get("metadata_json") or {}
    for key in ("deployer", "creator", "creator_wallet"):
        if candidate.get(key):
            return key
    for key in ("deployer", "creator_deployer", "creator", "creator_wallet"):
        if metadata.get(key):
            return f"metadata_json.{key}"
    return None


def _creator_cohort(prior_count: int) -> str:
    if prior_count == 0:
        return "A_0_prior_launches"
    if prior_count == 1:
        return "B_1_prior_launch"
    if prior_count <= 4:
        return "C_2_to_4_prior_launches"
    return "D_5_plus_prior_launches"


def _prior_count_since(prior_times: list[int], block_time: int | None, seconds: int) -> int | None:
    if block_time is None:
        return None
    return sum(1 for prior_time in prior_times if 0 < block_time - prior_time <= seconds)


def _velocity(prior_times: list[int], block_time: int | None, seconds: int) -> float | None:
    count = _prior_count_since(prior_times, block_time, seconds)
    return None if count is None else count / (seconds / 86400)


def _feature_value(row: dict[str, Any], feature: str) -> float | None:
    value = row["features"].get(feature)
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    return _float_or_none(value)


def _distribution_summary(values: list[float]) -> dict[str, Any]:
    clean = sorted(value for value in values if value is not None)
    if not clean:
        return {"count": 0, "min": None, "p25": None, "median": None, "p75": None, "max": None, "mean": None}
    return {
        "count": len(clean),
        "min": clean[0],
        "p25": _quantile(clean, 0.25),
        "median": median(clean),
        "p75": _quantile(clean, 0.75),
        "max": clean[-1],
        "mean": mean(clean),
    }


def _read_jsonl(path: Path | str) -> list[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _group_by_mint(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        mint = row.get("token_mint")
        if mint:
            grouped[str(mint)].append(row)
    return grouped


def _first_present(*values: Any) -> str | None:
    for value in values:
        if value not in (None, ""):
            return str(value)
    return None


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _median(values: list[float | None]) -> float | None:
    clean = [float(value) for value in values if value is not None]
    if not clean:
        return None
    return median(clean)


def _true_rate(values) -> float | None:
    clean = list(values)
    if not clean:
        return None
    return sum(1 for value in clean if value) / len(clean)


def _quantile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    index = min(len(values) - 1, max(0, round((len(values) - 1) * pct)))
    return values[index]


def _format_pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.2f}%"
