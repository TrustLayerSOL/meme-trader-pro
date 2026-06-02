"""Descriptive T002 holder-growth tempo thesis cycle."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any

from research.mtp_research.validation.robust_return_metrics import winsorized_mean


THESIS_ID = "T002"
THESIS_NAME = "Holder Growth Tempo"
FIELD_AUDIT_FIELDS = [
    "holder_count",
    "buyer_count",
    "seller_count",
    "unique_wallet_count",
    "unique_buyer_count",
    "unique_seller_count",
    "trader_count",
    "active_wallets",
    "unique_actors",
    "tx_count",
    "liquidity_proxy",
    "bonding_curve_progress",
    "event_count",
    "buy_count",
    "sell_count",
]
FEATURES = [
    "holder_growth_30s_to_3m",
    "holder_growth_3m_to_10m",
    "holder_growth_10m_to_30m",
    "holder_growth_30s_to_30m",
    "holder_growth_velocity",
    "active_wallet_growth_30s_to_3m",
    "active_wallet_growth_3m_to_10m",
    "active_wallet_growth_10m_to_30m",
    "active_wallet_growth_30s_to_30m",
    "active_wallet_growth_velocity",
    "unique_actor_growth_30s_to_3m",
    "unique_actor_growth_3m_to_10m",
    "unique_actor_growth_10m_to_30m",
    "buyer_growth_30s_to_3m",
    "buyer_growth_3m_to_10m",
    "buyer_growth_10m_to_30m",
    "active_wallets_per_buyer_30m",
    "active_wallets_per_trade_30m",
    "active_wallet_buyer_ratio_30m",
    "buyer_active_wallet_conversion_rate_30m",
    "active_wallet_retention_3m_to_10m",
    "active_wallet_retention_10m_to_30m",
    "active_wallet_retention_proxy",
]
HOLDER_FEATURES = [feature for feature in FEATURES if feature.startswith("holder_growth")]


def build_t002_holder_growth_report(
    *,
    candidates_path: Path | str,
    snapshots_path: Path | str,
    outcomes_path: Path | str,
    holder_state_snapshots_path: Path | str | None = None,
    bucket_count: int = 5,
) -> dict[str, Any]:
    candidates = _read_jsonl(candidates_path)
    snapshots = _read_jsonl(snapshots_path)
    if holder_state_snapshots_path:
        snapshots = _merge_holder_state_snapshots(snapshots, _read_jsonl(holder_state_snapshots_path))
    snapshots_by_mint = _group_by_mint(snapshots)
    outcomes_by_mint = {row["token_mint"]: row for row in _read_jsonl(outcomes_path)}
    field_audit = _field_coverage_audit(snapshots, FIELD_AUDIT_FIELDS)
    launch_rows = []
    for candidate in sorted(candidates, key=lambda row: (row.get("launch_ts", 0), row.get("token_mint", ""))):
        mint = candidate["token_mint"]
        launch_rows.append(
            _build_launch_row(
                candidate=candidate,
                snapshots=snapshots_by_mint.get(mint, []),
                outcome=outcomes_by_mint.get(mint, {}),
            )
        )
    missing_value_audit = _missing_value_audit(launch_rows)
    feature_reports = {feature: _feature_report(launch_rows, feature, bucket_count) for feature in FEATURES}
    warning_flags = _warning_flags(field_audit, missing_value_audit, launch_rows)
    classification = _classify(feature_reports, warning_flags, len(launch_rows))
    return {
        "thesis_id": THESIS_ID,
        "thesis_name": THESIS_NAME,
        "research_question": (
            "Do healthier launches exhibit different holder-growth and participation-growth "
            "trajectories than unhealthy launches?"
        ),
        "hypothesis": (
            "Launches that attract and retain holders early may have healthier lifecycle "
            "trajectories than launches that merely generate transaction activity."
        ),
        "dataset": {
            "candidates_path": str(candidates_path),
            "snapshots_path": str(snapshots_path),
            "holder_state_snapshots_path": str(holder_state_snapshots_path) if holder_state_snapshots_path else None,
            "outcomes_path": str(outcomes_path),
            "launch_count": len(launch_rows),
            "strict_launch_regime": True,
            "valuation_semantics": "fdv_proxy_only",
            "true_market_cap_claims": "blocked",
        },
        "methodology": {
            "bucket_method": "deterministic_rank_quantile_buckets",
            "bucket_count": bucket_count,
            "feature_windows_seconds": [30, 180, 600, 1800],
            "candidate_features": FEATURES,
            "holder_count_policy": "do_not_fabricate_missing_holder_count",
            "holder_state_semantics": "observed_delta_replay_not_full_chain_state" if holder_state_snapshots_path else "not_provided",
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
            "holder_state_observed_delta_replay_not_full_chain_state" if holder_state_snapshots_path else "holder_state_unavailable",
        ],
        "field_coverage_audit": field_audit,
        "launch_rows": launch_rows,
        "sample_counts": _sample_counts(launch_rows),
        "outcome_coverage": _outcome_coverage(launch_rows),
        "missing_value_audit": missing_value_audit,
        "feature_reports": feature_reports,
        "sensitivity_checks": _sensitivity_checks(feature_reports),
        "final_classification": classification,
        "warning_flags": warning_flags,
        "limitations": _limitations(warning_flags),
        "next_recommendation": _next_recommendation(warning_flags),
        "reproducible_command": _reproducible_command(
            candidates_path,
            snapshots_path,
            holder_state_snapshots_path,
            outcomes_path,
            bucket_count,
        ),
    }


def write_t002_report_outputs(
    report: dict[str, Any],
    *,
    output_dir: Path | str,
    status_path: Path | str,
) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "T002_holder_growth_tempo_summary.json"
    markdown_path = output / "T002_holder_growth_tempo_summary.md"
    json_path.write_text(json.dumps(_public_report(report), indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(_markdown_summary(report), encoding="utf-8")
    status = Path(status_path)
    status.parent.mkdir(parents=True, exist_ok=True)
    status.write_text(_status_markdown(report, markdown_path, json_path), encoding="utf-8")
    return {"json_summary_path": json_path, "markdown_summary_path": markdown_path, "status_path": status}


def _build_launch_row(
    *,
    candidate: dict[str, Any],
    snapshots: list[dict[str, Any]],
    outcome: dict[str, Any],
) -> dict[str, Any]:
    by_age = {int(row.get("launch_age_seconds", 0)): row for row in snapshots}
    feature_snapshots = {age: _nearest_snapshot(by_age, age) for age in (30, 180, 600, 1800)}
    features, missing_reasons = _build_features(feature_snapshots)
    return {
        "launch_id": candidate.get("launch_id"),
        "token_mint": candidate["token_mint"],
        "launch_ts": candidate.get("launch_ts"),
        "launch_regime": candidate.get("launch_regime"),
        "features": features,
        "feature_missing_reasons": missing_reasons,
        "outcomes": _fdv_outcomes(snapshots, outcome),
        "metadata_json": {
            "max_feature_snapshot_age_seconds": max((age for age, row in feature_snapshots.items() if row), default=None),
            "feature_snapshot_ages": sorted(age for age, row in feature_snapshots.items() if row),
        },
    }


def _build_features(snapshots: dict[int, dict[str, Any] | None]) -> tuple[dict[str, Any], dict[str, str]]:
    values = {
        "holder_count": {age: _field_value(row, "holder_count") for age, row in snapshots.items()},
        "active_wallets": {age: _field_value(row, "active_wallets") for age, row in snapshots.items()},
        "unique_actors": {age: _field_value(row, "unique_actors") for age, row in snapshots.items()},
        "buy_count": {age: _field_value(row, "buy_count") for age, row in snapshots.items()},
        "tx_count": {age: _field_value(row, "tx_count") for age, row in snapshots.items()},
    }
    features = {
        "holder_growth_30s_to_3m": _growth(values["holder_count"], 30, 180),
        "holder_growth_3m_to_10m": _growth(values["holder_count"], 180, 600),
        "holder_growth_10m_to_30m": _growth(values["holder_count"], 600, 1800),
        "holder_growth_30s_to_30m": _growth(values["holder_count"], 30, 1800),
        "holder_growth_velocity": _velocity(values["holder_count"], 30, 1800),
        "active_wallet_growth_30s_to_3m": _growth(values["active_wallets"], 30, 180),
        "active_wallet_growth_3m_to_10m": _growth(values["active_wallets"], 180, 600),
        "active_wallet_growth_10m_to_30m": _growth(values["active_wallets"], 600, 1800),
        "active_wallet_growth_30s_to_30m": _growth(values["active_wallets"], 30, 1800),
        "active_wallet_growth_velocity": _velocity(values["active_wallets"], 30, 1800),
        "unique_actor_growth_30s_to_3m": _growth(values["unique_actors"], 30, 180),
        "unique_actor_growth_3m_to_10m": _growth(values["unique_actors"], 180, 600),
        "unique_actor_growth_10m_to_30m": _growth(values["unique_actors"], 600, 1800),
        "buyer_growth_30s_to_3m": _growth(values["buy_count"], 30, 180),
        "buyer_growth_3m_to_10m": _growth(values["buy_count"], 180, 600),
        "buyer_growth_10m_to_30m": _growth(values["buy_count"], 600, 1800),
        "active_wallets_per_buyer_30m": _ratio(values["active_wallets"].get(1800), values["buy_count"].get(1800)),
        "active_wallets_per_trade_30m": _ratio(values["active_wallets"].get(1800), values["tx_count"].get(1800)),
        "active_wallet_buyer_ratio_30m": _ratio(values["active_wallets"].get(1800), values["buy_count"].get(1800)),
        "buyer_active_wallet_conversion_rate_30m": _ratio(values["buy_count"].get(1800), values["active_wallets"].get(1800)),
        "active_wallet_retention_3m_to_10m": _retention(values["active_wallets"], 180, 600),
        "active_wallet_retention_10m_to_30m": _retention(values["active_wallets"], 600, 1800),
        "active_wallet_retention_proxy": _retention(values["active_wallets"], 180, 1800),
    }
    missing_reasons = {}
    for feature, value in features.items():
        if value is None:
            missing_reasons[feature] = "holder_count_unavailable" if feature in HOLDER_FEATURES else "required_snapshot_field_unavailable"
    return features, missing_reasons


def _merge_holder_state_snapshots(
    valuation_snapshots: list[dict[str, Any]],
    holder_state_snapshots: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    holder_by_key = {
        (row.get("mint") or row.get("token_mint"), _holder_age(row)): row
        for row in holder_state_snapshots
        if (row.get("mint") or row.get("token_mint")) and _holder_age(row) is not None
    }
    merged = []
    for row in valuation_snapshots:
        copy = dict(row)
        key = (copy.get("token_mint"), _holder_age(copy))
        holder = holder_by_key.get(key)
        if holder:
            copy["holder_count"] = holder.get("holder_count")
            copy["top_holder_share"] = holder.get("top_holder_share")
            copy["top_10_holder_share"] = holder.get("top_10_holder_share")
            copy["creator_holder_share"] = holder.get("creator_holder_share")
            copy["holder_snapshot_confidence"] = holder.get("holder_snapshot_confidence")
            copy["holder_snapshot_state"] = holder.get("holder_snapshot_state")
            copy["holder_snapshot_missing_reason"] = holder.get("holder_snapshot_missing_reason")
            metadata = dict(copy.get("metadata_json") or {})
            metadata["holder_state_source"] = holder.get("holder_snapshot_source")
            metadata["holder_state_is_observed_delta_replay"] = holder.get("is_observed_delta_replay")
            metadata["holder_state_is_confirmed_full_chain_snapshot"] = holder.get("is_confirmed_full_chain_snapshot")
            copy["metadata_json"] = metadata
        merged.append(copy)
    return merged


def _holder_age(row: dict[str, Any]) -> int | None:
    value = row.get("launch_age_seconds")
    if value is None:
        value = row.get("snapshot_age_seconds")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _field_coverage_audit(rows: list[dict[str, Any]], fields: list[str]) -> dict[str, dict[str, Any]]:
    total = len(rows)
    audit = {}
    for field in fields:
        available = sum(1 for row in rows if _snapshot_field_present(row, field))
        audit[field] = {
            "available_rows": available,
            "missing_rows": total - available,
            "coverage_pct": (available / total * 100) if total else 0,
        }
    return audit


def _snapshot_field_present(row: dict[str, Any], field: str) -> bool:
    if field in row and row.get(field) is not None:
        return True
    metadata = row.get("metadata_json") or {}
    return field in metadata and metadata.get(field) is not None


def _field_value(row: dict[str, Any] | None, field: str) -> float | None:
    if not row:
        return None
    value = row.get(field)
    if value is None:
        value = (row.get("metadata_json") or {}).get(field)
    return _float_or_none(value)


def _growth(values: dict[int, float | None], start: int, end: int) -> float | None:
    if values.get(start) is None or values.get(end) is None:
        return None
    return values[end] - values[start]


def _velocity(values: dict[int, float | None], start: int, end: int) -> float | None:
    growth = _growth(values, start, end)
    if growth is None or end == start:
        return None
    return growth / (end - start)


def _retention(values: dict[int, float | None], start: int, end: int) -> float | None:
    if values.get(start) is None or values.get(end) is None or values[start] == 0:
        return None
    return values[end] / values[start]


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def _nearest_snapshot(by_age: dict[int, dict[str, Any]], age: int) -> dict[str, Any] | None:
    if age in by_age:
        return by_age[age]
    return None


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


def _feature_report(rows: list[dict[str, Any]], feature: str, bucket_count: int) -> dict[str, Any]:
    usable = [row for row in rows if _float_or_none(row["features"].get(feature)) is not None]
    values = [_float_or_none(row["features"].get(feature)) for row in usable]
    values = [value for value in values if value is not None]
    return {
        "feature": feature,
        "sample_count": len(rows),
        "usable_count": len(usable),
        "missing_count": len(rows) - len(usable),
        "quantile_definitions": "deterministic rank buckets over non-missing values",
        "distribution_summary": _distribution_summary(values),
        "bucket_tables": _bucket_tables(usable, feature, bucket_count),
        "outlier_adjusted_summary": {
            "winsorized_mean_fdv_proxy_runup_120m": winsorized_mean(
                [_float_or_none(row["outcomes"].get("fdv_proxy_runup_120m")) for row in usable]
            ),
            "winsorized_mean_fdv_proxy_drawdown_120m": winsorized_mean(
                [_float_or_none(row["outcomes"].get("fdv_proxy_drawdown_120m")) for row in usable]
            ),
        },
    }


def _bucket_tables(rows: list[dict[str, Any]], feature: str, bucket_count: int) -> list[dict[str, Any]]:
    usable = sorted(
        rows,
        key=lambda row: (
            _float_or_none(row["features"].get(feature)),
            row.get("launch_ts", 0) or 0,
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
    values = [_float_or_none(row["features"].get(feature)) for row in rows]
    values = [value for value in values if value is not None]
    runups = [_float_or_none(row["outcomes"].get("fdv_proxy_runup_120m")) for row in rows]
    drawdowns = [_float_or_none(row["outcomes"].get("fdv_proxy_drawdown_120m")) for row in rows]
    return {
        "bucket": f"q{bucket_number}",
        "sample_count": len(rows),
        "token_count": len({row["token_mint"] for row in rows}),
        "feature_min": min(values) if values else None,
        "feature_max": max(values) if values else None,
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


def _outcome_coverage(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "fdv_proxy_runup_available": sum(1 for row in rows if row["outcomes"].get("fdv_proxy_runup_120m") is not None),
        "fdv_proxy_drawdown_available": sum(1 for row in rows if row["outcomes"].get("fdv_proxy_drawdown_120m") is not None),
        "price_available_120m": sum(1 for row in rows if row["outcomes"].get("price_available_120m")),
        "liquidity_proxy_available_120m": sum(
            1 for row in rows if row["outcomes"].get("liquidity_proxy_available_120m")
        ),
    }


def _missing_value_audit(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    audit = {}
    for feature in FEATURES:
        missing = sum(1 for row in rows if _float_or_none(row["features"].get(feature)) is None)
        audit[feature] = {
            "available_count": len(rows) - missing,
            "missing_count": missing,
            "missing_rate": (missing / len(rows)) if rows else None,
        }
    return audit


def _sensitivity_checks(feature_reports: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "exclude_missing_feature_values": "all bucket tables exclude missing feature values",
        "tiny_bucket_features": [
            feature for feature, report in feature_reports.items()
            if report["bucket_tables"] and min(bucket["sample_count"] for bucket in report["bucket_tables"]) < 25
        ],
        "features_without_usable_buckets": [
            feature for feature, report in feature_reports.items()
            if not report["bucket_tables"]
        ],
    }


def _warning_flags(
    field_audit: dict[str, dict[str, Any]],
    missing_value_audit: dict[str, dict[str, Any]],
    rows: list[dict[str, Any]],
) -> list[str]:
    warnings = []
    if field_audit["holder_count"]["available_rows"] == 0:
        warnings.append("holder_count_unavailable")
    if any(missing_value_audit[feature]["available_count"] == 0 for feature in HOLDER_FEATURES):
        warnings.append("holder_growth_features_unavailable")
    if any(not row["outcomes"].get("proxy_threshold_outcomes_usable") for row in rows):
        warnings.append("fdv_proxy_thresholds_not_fully_usable")
    if not any(row["outcomes"].get("true_market_cap_available") for row in rows):
        warnings.append("true_market_cap_claims_blocked")
    if any(row["outcomes"].get("fdv_proxy_runup_120m") is None for row in rows):
        warnings.append("fdv_proxy_outcomes_missing")
    return warnings


def _classify(feature_reports: dict[str, dict[str, Any]], warning_flags: list[str], row_count: int) -> str:
    if row_count < 100 or "fdv_proxy_outcomes_missing" in warning_flags:
        return "data_limited"
    primary = [
        feature_reports["active_wallet_growth_30s_to_30m"],
        feature_reports["buyer_growth_30s_to_3m"],
        feature_reports["active_wallet_retention_proxy"],
    ]
    direction_count = 0
    usable_primary = 0
    for report in primary:
        buckets = report["bucket_tables"]
        if len(buckets) < 2:
            continue
        usable_primary += 1
        low = buckets[0]["median_fdv_proxy_runup_120m"]
        high = buckets[-1]["median_fdv_proxy_runup_120m"]
        if low is not None and high is not None and high > low:
            direction_count += 1
    if usable_primary == 0:
        return "data_limited"
    if direction_count >= 2:
        return "descriptive_signal_present"
    if direction_count == 1:
        return "weak_signal"
    return "no_signal"


def _limitations(warning_flags: list[str]) -> list[str]:
    limitations = [
        "FDV proxy is not true market cap because circulating supply is unavailable.",
        "This cycle is descriptive research only and does not produce trading rules.",
    ]
    if "holder_count_unavailable" in warning_flags:
        limitations.append("True holder-count growth is unavailable; participation proxies are reported separately.")
    return limitations


def _next_recommendation(warning_flags: list[str]) -> str:
    if "holder_count_unavailable" in warning_flags:
        return "add replay-safe holder-count snapshots before rerunning true holder-growth analysis"
    return "rerun with chronological validation before changing thesis status"


def _public_report(report: dict[str, Any]) -> dict[str, Any]:
    public = dict(report)
    public.pop("launch_rows", None)
    return public


def _markdown_summary(report: dict[str, Any]) -> str:
    lines = [
        "# T002 Holder Growth Tempo",
        "",
        f"- Final classification: `{report['final_classification']}`",
        f"- Launch count: `{report['sample_counts']['launch_count']}`",
        f"- Warning flags: `{report['warning_flags']}`",
        "",
        "## Feature Coverage Audit",
        "",
        "| Field | Available Rows | Missing Rows | Coverage |",
        "|---|---:|---:|---:|",
    ]
    for field, audit in report["field_coverage_audit"].items():
        lines.append(
            f"| `{field}` | {audit['available_rows']} | {audit['missing_rows']} | "
            f"{audit['coverage_pct']:.2f}% |"
        )
    lines.extend(["", "## Outcome Coverage", ""])
    lines.extend([f"- `{key}`: `{value}`" for key, value in report["outcome_coverage"].items()])
    lines.extend(["", "## Median Outcome Tables", ""])
    for feature, feature_report in report["feature_reports"].items():
        lines.extend(
            [
                f"### `{feature}`",
                "",
                "| Bucket | Samples | Feature Min | Feature Max | Median FDV Runup | Median FDV Drawdown | Price 120m | Liquidity 120m |",
                "|---|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for bucket in feature_report["bucket_tables"]:
            lines.append(
                f"| {bucket['bucket']} | {bucket['sample_count']} | {_format_num(bucket['feature_min'])} | "
                f"{_format_num(bucket['feature_max'])} | {_format_pct(bucket['median_fdv_proxy_runup_120m'])} | "
                f"{_format_pct(bucket['median_fdv_proxy_drawdown_120m'])} | "
                f"{_format_pct(bucket['price_available_120m_rate'])} | "
                f"{_format_pct(bucket['liquidity_proxy_available_120m_rate'])} |"
            )
        if not feature_report["bucket_tables"]:
            lines.append("| n/a | 0 | n/a | n/a | n/a | n/a | n/a | n/a |")
        lines.append("")
    lines.extend(
        [
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


def _status_markdown(report: dict[str, Any], markdown_path: Path, json_path: Path) -> str:
    coverage = report["field_coverage_audit"]
    missing = report["missing_value_audit"]
    return "\n".join(
        [
            "# T002 Holder Growth Tempo Status",
            "",
            "## Thesis Description",
            "",
            "Do healthier launches exhibit different holder-growth and participation-growth trajectories than unhealthy launches?",
            "",
            "## Dataset Used",
            "",
            "- Strict launch-regime FDV-proxy lifecycle dataset",
            f"- Holder-state snapshots: `{report['dataset'].get('holder_state_snapshots_path')}`",
            f"- Launches analyzed: `{report['sample_counts']['launch_count']}`",
            "",
            "## Feature Coverage",
            "",
            f"- `holder_count`: `{coverage['holder_count']['coverage_pct']:.2f}%`",
            f"- `active_wallets`: `{coverage.get('active_wallets', {}).get('coverage_pct', 0):.2f}%`",
            f"- `buy_count`: `{coverage['buy_count']['coverage_pct']:.2f}%`",
            f"- `event_count`: `{coverage['event_count']['coverage_pct']:.2f}%`",
            f"- `holder_growth_30s_to_3m` available launches: `{missing['holder_growth_30s_to_3m']['available_count']}`",
            f"- `holder_growth_30s_to_30m` available launches: `{missing['holder_growth_30s_to_30m']['available_count']}`",
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
    holder_state_snapshots_path: Path | str | None,
    outcomes_path: Path | str,
    bucket_count: int,
) -> str:
    parts = [
        "./trading_env/bin/python -m research.mtp_research.validation.run_holder_growth_tempo_thesis",
        f"--candidates-path \"{candidates_path}\"",
        f"--snapshots-path \"{snapshots_path}\"",
    ]
    if holder_state_snapshots_path:
        parts.append(f"--holder-state-snapshots-path \"{holder_state_snapshots_path}\"")
    parts.extend([
        f"--outcomes-path \"{outcomes_path}\"",
        f"--bucket-count {bucket_count}",
    ])
    return " ".join(parts)


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


def _format_num(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.4f}"
