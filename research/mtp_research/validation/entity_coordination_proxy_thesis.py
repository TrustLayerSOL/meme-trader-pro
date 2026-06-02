"""Descriptive T007 entity/coordination proxy thesis cycle."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any

from research.mtp_research.validation.robust_return_metrics import winsorized_mean


THESIS_ID = "T007"
THESIS_NAME = "Entity / Coordination Proxy"
FEATURES = [
    "creator_linked_share_proxy",
    "repeated_actor_overlap_proxy",
    "repeated_buyer_overlap_proxy",
    "synchronized_participation_proxy",
    "circularity_proxy",
    "churn_proxy",
]
SECONDARY_FEATURES = ["proxy_confidence", "proxy_missing_reason"]
ALLOWED_CLASSIFICATIONS = {"descriptive_signal_present", "weak_signal", "no_signal", "data_limited"}


def build_t007_entity_coordination_report(
    *,
    candidates_path: Path | str,
    snapshots_path: Path | str,
    outcomes_path: Path | str,
    entity_proxy_path: Path | str,
    bucket_count: int = 5,
) -> dict[str, Any]:
    candidates = _read_jsonl(candidates_path)
    snapshots = _read_jsonl(snapshots_path)
    outcomes_by_mint = {row["token_mint"]: row for row in _read_jsonl(outcomes_path)}
    proxies_by_mint = {
        row.get("mint") or row.get("token_mint"): row
        for row in _read_jsonl(entity_proxy_path)
        if row.get("mint") or row.get("token_mint")
    }
    snapshots_by_mint = _group_by_mint(snapshots)
    launch_rows = [
        _build_launch_row(
            candidate=candidate,
            snapshots=snapshots_by_mint.get(candidate["token_mint"], []),
            outcome=outcomes_by_mint.get(candidate["token_mint"], {}),
            proxy=proxies_by_mint.get(candidate["token_mint"], {}),
        )
        for candidate in sorted(candidates, key=lambda row: (row.get("launch_ts") or 0, row.get("token_mint", "")))
    ]
    proxy_coverage = _proxy_coverage(launch_rows)
    outcome_coverage = _outcome_coverage(launch_rows)
    feature_reports = {feature: _feature_report(launch_rows, feature, bucket_count) for feature in FEATURES}
    sensitivity_checks = _sensitivity_checks(launch_rows, feature_reports, bucket_count)
    warning_flags = _warning_flags(launch_rows, proxy_coverage, outcome_coverage)
    classification = _classify(launch_rows, feature_reports, sensitivity_checks, warning_flags)
    return {
        "thesis_id": THESIS_ID,
        "thesis_name": THESIS_NAME,
        "research_question": (
            "Do deterministic entity proxy and coordination proxy features have a descriptive "
            "relationship with FDV-proxy lifecycle outcomes in the strict launch-regime dataset?"
        ),
        "hypothesis": (
            "Launches with stronger overlap proxy, circularity proxy, churn proxy, and synchronized "
            "participation proxy features may show different FDV-proxy lifecycle outcomes."
        ),
        "dataset": {
            "candidates_path": str(candidates_path),
            "snapshots_path": str(snapshots_path),
            "outcomes_path": str(outcomes_path),
            "entity_proxy_path": str(entity_proxy_path),
            "launch_count": len(launch_rows),
            "snapshot_count": len(snapshots),
            "strict_launch_regime": True,
            "valuation_semantics": "fdv_proxy_only",
            "true_market_cap_claims": "blocked",
        },
        "methodology": {
            "bucket_method": "deterministic_rank_quantile_buckets",
            "bucket_count": bucket_count,
            "candidate_features": FEATURES,
            "secondary_context_features": SECONDARY_FEATURES,
            "classification_options": sorted(ALLOWED_CLASSIFICATIONS),
            "single_feature_independent_analysis": True,
            "combined_scoring": "not_run",
        },
        "methodology_flags": [
            "research_only",
            "descriptive_thesis_cycle",
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
        "feature_semantics": _feature_semantics(),
        "launch_rows": launch_rows,
        "sample_counts": _sample_counts(launch_rows),
        "proxy_coverage": proxy_coverage,
        "proxy_confidence_distribution": dict(sorted(Counter(row["metadata_json"].get("proxy_confidence") for row in launch_rows).items())),
        "proxy_missing_reason_counts": _proxy_missing_reason_counts(launch_rows),
        "outcome_coverage": outcome_coverage,
        "feature_reports": feature_reports,
        "sensitivity_checks": sensitivity_checks,
        "prior_cycle_comparison": {
            "T001": "no_signal",
            "T001_v2": "no_signal",
            "T002": "weak_signal",
            "T002_v2": "weak_signal",
            "T002_v2_chronological_robustness": "no_robust_signal",
            "T003": "no_signal",
            "T004": "no_signal",
            "T005": "weak_signal_baseline_control",
            "T006": "no_signal",
            "entity_proxy_vs_T005": _entity_vs_t005(feature_reports, classification),
            "comparison_note": "Qualitative comparison only; no combined strategy or thesis promotion is made.",
        },
        "blocked_fields": [
            "funding_link_proxy",
            "safe_entity_resolution_groups",
            "grouped_entity_holder_share",
            "true_market_cap",
        ],
        "final_classification": classification,
        "warning_flags": warning_flags,
        "limitations": _limitations(),
        "chronological_robustness_recommended": classification in {"descriptive_signal_present", "weak_signal"},
        "next_recommendation": _next_recommendation(classification),
        "reproducible_command": _reproducible_command(
            candidates_path,
            snapshots_path,
            outcomes_path,
            entity_proxy_path,
            bucket_count,
        ),
    }


def write_t007_report_outputs(
    report: dict[str, Any],
    *,
    output_dir: Path | str,
    status_path: Path | str,
) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "T007_entity_coordination_proxy_summary.json"
    markdown_path = output / "T007_entity_coordination_proxy_summary.md"
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
    proxy: dict[str, Any],
) -> dict[str, Any]:
    ordered = sorted(snapshots, key=lambda row: int(row.get("launch_age_seconds", 0)))
    return {
        "launch_id": candidate.get("launch_id"),
        "token_mint": candidate["token_mint"],
        "launch_ts": candidate.get("launch_ts"),
        "features": {feature: _float_or_none(proxy.get(feature)) for feature in FEATURES},
        "outcomes": _fdv_outcomes(ordered, outcome),
        "metadata_json": {
            "proxy_confidence": proxy.get("proxy_confidence"),
            "proxy_missing_reason": proxy.get("proxy_missing_reason"),
            "entity_proxy_row_available": bool(proxy),
            "max_outcome_snapshot_age_seconds": max((int(row.get("launch_age_seconds", 0)) for row in ordered), default=None),
        },
    }


def _fdv_outcomes(snapshots: list[dict[str, Any]], outcome: dict[str, Any]) -> dict[str, Any]:
    valued = [
        row for row in snapshots
        if row.get("valuation_proxy_available") and _float_or_none(row.get("valuation_proxy_usd")) is not None
    ]
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
        "true_market_cap_available": bool(outcome.get("true_market_cap_available")),
    }


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
        "median_only_summary": _outcome_summary(usable),
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
    usable = sorted(rows, key=lambda row: (_feature_value(row, feature), row.get("launch_ts") or 0, row["token_mint"]))
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
        "launch_count": len(rows),
        "sample_count": len(rows),
        "token_count": len({row["token_mint"] for row in rows}),
        "median_fdv_proxy_runup_120m": _median(runups),
        "median_fdv_proxy_drawdown_120m": _median(drawdowns),
        "price_available_120m_rate": _true_rate(row["outcomes"].get("price_available_120m") for row in rows),
        "liquidity_proxy_available_120m_rate": _true_rate(row["outcomes"].get("liquidity_proxy_available_120m") for row in rows),
    }


def _sensitivity_checks(
    rows: list[dict[str, Any]],
    feature_reports: dict[str, dict[str, Any]],
    bucket_count: int,
) -> dict[str, Any]:
    runups = sorted(
        value for value in (_float_or_none(row["outcomes"].get("fdv_proxy_runup_120m")) for row in rows)
        if value is not None
    )
    drawdowns = sorted(
        value for value in (_float_or_none(row["outcomes"].get("fdv_proxy_drawdown_120m")) for row in rows)
        if value is not None
    )
    runup_p99 = _quantile(runups, 0.99)
    runup_p95 = _quantile(runups, 0.95)
    drawdown_p01 = _quantile(drawdowns, 0.01)
    sorted_rows = sorted(rows, key=lambda row: (row.get("launch_ts") or 0, row["token_mint"]))
    halfway = len(sorted_rows) // 2
    low_confidence = [row for row in rows if row["metadata_json"].get("proxy_confidence") == "low"]
    missing_creator = [row for row in rows if row["features"].get("creator_linked_share_proxy") is None]
    return {
        "bucket_count_audit": {
            feature: {
                "bucket_count": report["bucket_count"],
                "min_bucket_size": min((bucket["sample_count"] for bucket in report["bucket_tables"]), default=0),
            }
            for feature, report in feature_reports.items()
        },
        "tiny_bucket_features": [
            feature for feature, report in feature_reports.items()
            if report["bucket_tables"] and min(bucket["sample_count"] for bucket in report["bucket_tables"]) < 25
        ],
        "exclude_top_1pct_fdv_proxy_runups": _feature_direction_summary(
            [row for row in rows if runup_p99 is None or (row["outcomes"].get("fdv_proxy_runup_120m") or 0) <= runup_p99],
            bucket_count,
        ),
        "exclude_top_5pct_fdv_proxy_runups": _feature_direction_summary(
            [row for row in rows if runup_p95 is None or (row["outcomes"].get("fdv_proxy_runup_120m") or 0) <= runup_p95],
            bucket_count,
        ),
        "exclude_extreme_drawdowns": _feature_direction_summary(
            [row for row in rows if drawdown_p01 is None or (row["outcomes"].get("fdv_proxy_drawdown_120m") or 0) >= drawdown_p01],
            bucket_count,
        ),
        "exclude_missing_creator_linked_share_proxy": _outcome_summary([row for row in rows if row not in missing_creator]),
        "low_confidence_proxy_rows": _outcome_summary(low_confidence),
        "chronological_halves": {
            "first_half": _feature_direction_summary(sorted_rows[:halfway], bucket_count),
            "second_half": _feature_direction_summary(sorted_rows[halfway:], bucket_count),
        },
    }


def _feature_direction_summary(rows: list[dict[str, Any]], bucket_count: int) -> dict[str, Any]:
    directions = {}
    for feature in FEATURES:
        buckets = _bucket_tables([row for row in rows if _feature_value(row, feature) is not None], feature, bucket_count)
        if len(buckets) < 2:
            directions[feature] = "unusable"
            continue
        low = buckets[0]["median_fdv_proxy_runup_120m"]
        high = buckets[-1]["median_fdv_proxy_runup_120m"]
        directions[feature] = _direction(low, high)
    return {"launch_count": len(rows), "feature_directions": directions}


def _classify(
    rows: list[dict[str, Any]],
    feature_reports: dict[str, dict[str, Any]],
    sensitivity_checks: dict[str, Any],
    warning_flags: list[str],
) -> str:
    if len(rows) < 100 or "fdv_proxy_outcomes_missing" in warning_flags:
        return "data_limited"
    signal_count = 0
    usable_count = 0
    for feature in FEATURES:
        buckets = feature_reports[feature]["bucket_tables"]
        if len(buckets) < 2:
            continue
        usable_count += 1
        direction = _direction(buckets[0]["median_fdv_proxy_runup_120m"], buckets[-1]["median_fdv_proxy_runup_120m"])
        if direction != "flat_or_unusable":
            signal_count += 1
    if usable_count == 0:
        return "data_limited"
    chronological = sensitivity_checks["chronological_halves"]
    consistent_half_count = sum(
        1 for half in chronological.values()
        if any(direction != "flat_or_unusable" and direction != "unusable" for direction in half["feature_directions"].values())
    )
    if signal_count >= 4 and consistent_half_count == 2:
        return "descriptive_signal_present"
    if signal_count >= 2 or (signal_count >= 1 and consistent_half_count >= 1):
        return "weak_signal"
    return "no_signal"


def _entity_vs_t005(feature_reports: dict[str, dict[str, Any]], classification: str) -> str:
    if classification == "descriptive_signal_present":
        return "entity_proxies_show_stronger_descriptive_separation_than_T005_baseline_control"
    if classification == "weak_signal":
        useful = sum(1 for report in feature_reports.values() if report["bucket_tables"])
        return "entity_proxies_show_weak_descriptive_separation_similar_to_or_better_than_T005_baseline_control" if useful else "not_comparable"
    return "entity_proxies_do_not_add_clear_descriptive_separation_beyond_T005_baseline_control"


def _warning_flags(
    rows: list[dict[str, Any]],
    proxy_coverage: dict[str, dict[str, Any]],
    outcome_coverage: dict[str, int],
) -> list[str]:
    warnings = ["true_market_cap_claims_blocked"]
    if not rows:
        warnings.append("empty_dataset")
    if any(coverage["missing_count"] for coverage in proxy_coverage.values()):
        warnings.append("entity_proxy_fields_missing")
    if outcome_coverage["fdv_proxy_runup_available"] < len(rows) or outcome_coverage["fdv_proxy_drawdown_available"] < len(rows):
        warnings.append("fdv_proxy_outcomes_missing")
    return warnings


def _proxy_coverage(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    coverage = {}
    for feature in FEATURES:
        available = sum(1 for row in rows if _feature_value(row, feature) is not None)
        values = [_feature_value(row, feature) for row in rows if _feature_value(row, feature) is not None]
        coverage[feature] = {
            "available_count": available,
            "missing_count": len(rows) - available,
            "coverage_pct": (available / len(rows) * 100) if rows else 0,
            "min": min(values) if values else None,
            "median": _median(values),
            "max": max(values) if values else None,
        }
    return coverage


def _sample_counts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"launch_count": len(rows), "token_count": len({row["token_mint"] for row in rows})}


def _outcome_coverage(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "fdv_proxy_runup_available": sum(1 for row in rows if row["outcomes"].get("fdv_proxy_runup_120m") is not None),
        "fdv_proxy_drawdown_available": sum(1 for row in rows if row["outcomes"].get("fdv_proxy_drawdown_120m") is not None),
        "price_available_120m": sum(1 for row in rows if row["outcomes"].get("price_available_120m")),
        "liquidity_proxy_available_120m": sum(1 for row in rows if row["outcomes"].get("liquidity_proxy_available_120m")),
    }


def _proxy_missing_reason_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter()
    for row in rows:
        reason = row["metadata_json"].get("proxy_missing_reason")
        if reason:
            for part in str(reason).split(";"):
                if part:
                    counts[part] += 1
    return dict(sorted(counts.items()))


def _feature_semantics() -> dict[str, str]:
    return {
        "creator_linked_share_proxy": "observed creator-linked holder share proxy from replayed holder-state data",
        "repeated_actor_overlap_proxy": "count of lifecycle actors also appearing in other launches",
        "repeated_buyer_overlap_proxy": "count of first-minute buyer actors also appearing in other launches",
        "synchronized_participation_proxy": "first-minute actor concentration proxy",
        "circularity_proxy": "count of actors with deterministic early buy-then-sell churn",
        "churn_proxy": "early buy-then-sell actor count divided by observed actor count",
    }


def _limitations() -> list[str]:
    return [
        "This is descriptive research only and does not produce trading rules.",
        "FDV proxy is not true market cap because circulating supply remains unavailable.",
        "Actor overlap is not entity resolution.",
        "Funding-link fields remain unavailable.",
        "Grouped entity holder share remains blocked.",
    ]


def _next_recommendation(classification: str) -> str:
    if classification in {"descriptive_signal_present", "weak_signal"}:
        return "run a separate chronological robustness review for T007 before any validation design"
    if classification == "no_signal":
        return "park entity proxies or revisit blocked funding-link fields before expanding this thesis family"
    return "repair data coverage before interpreting T007"


def _public_report(report: dict[str, Any]) -> dict[str, Any]:
    public = dict(report)
    public.pop("launch_rows", None)
    return public


def _markdown_summary(report: dict[str, Any]) -> str:
    lines = [
        "# T007 Entity / Coordination Proxy",
        "",
        f"- Final classification: `{report['final_classification']}`",
        f"- Launch count: `{report['sample_counts']['launch_count']}`",
        f"- Chronological robustness recommended: `{report['chronological_robustness_recommended']}`",
        f"- Warning flags: `{report['warning_flags']}`",
        "",
        "## Proxy Coverage",
        "",
        "| Proxy | Available | Missing | Coverage | Min | Median | Max |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for feature, audit in report["proxy_coverage"].items():
        lines.append(
            f"| `{feature}` | {audit['available_count']} | {audit['missing_count']} | "
            f"{audit['coverage_pct']:.2f}% | {_format_num(audit['min'])} | "
            f"{_format_num(audit['median'])} | {_format_num(audit['max'])} |"
        )
    lines.extend(["", "## Median Outcome Tables", ""])
    for feature, feature_report in report["feature_reports"].items():
        lines.extend([f"### `{feature}`", "", "| Bucket | Samples | Feature Min | Feature Max | Median FDV Runup | Median FDV Drawdown | Price 120m | Liquidity 120m |", "|---|---:|---:|---:|---:|---:|---:|---:|"])
        for bucket in feature_report["bucket_tables"]:
            lines.append(
                f"| {bucket['bucket']} | {bucket['sample_count']} | {_format_num(bucket['feature_min'])} | "
                f"{_format_num(bucket['feature_max'])} | {_format_pct(bucket['median_fdv_proxy_runup_120m'])} | "
                f"{_format_pct(bucket['median_fdv_proxy_drawdown_120m'])} | {_format_pct(bucket['price_available_120m_rate'])} | "
                f"{_format_pct(bucket['liquidity_proxy_available_120m_rate'])} |"
            )
        lines.append("")
    lines.extend(["## Limitations", "", *[f"- {item}" for item in report["limitations"]], "", "## Reproducible Command", "", "```bash", report["reproducible_command"], "```"])
    return "\n".join(lines) + "\n"


def _status_markdown(report: dict[str, Any], markdown_path: Path, json_path: Path) -> str:
    return "\n".join(
        [
            "# T007 Entity / Coordination Proxy Status",
            "",
            "## Thesis Description",
            "",
            report["research_question"],
            "",
            "## Dataset Used",
            "",
            "- Strict launch-regime FDV-proxy lifecycle dataset",
            f"- Entity proxy dataset: `{report['dataset']['entity_proxy_path']}`",
            f"- Launches analyzed: `{report['sample_counts']['launch_count']}`",
            "",
            "## Proxy Coverage",
            "",
            *[f"- `{feature}`: `{audit['available_count']}` available, `{audit['coverage_pct']:.2f}%` coverage" for feature, audit in report["proxy_coverage"].items()],
            "",
            "## Outcome Coverage",
            "",
            *[f"- `{key}`: `{value}`" for key, value in report["outcome_coverage"].items()],
            "",
            "## Comparison To T001-T006",
            "",
            *[f"- `{key}`: `{value}`" for key, value in report["prior_cycle_comparison"].items()],
            "",
            "## Classification",
            "",
            f"`{report['final_classification']}`",
            "",
            "## Limitations",
            "",
            *[f"- {item}" for item in report["limitations"]],
            "",
            "## Blocked Fields",
            "",
            *[f"- `{item}`" for item in report["blocked_fields"]],
            "",
            "## True Market-Cap Blocked Warning",
            "",
            "True market-cap claims remain blocked; this report uses FDV proxy only.",
            "",
            "## Chronological Robustness Recommendation",
            "",
            f"`{report['chronological_robustness_recommended']}`",
            "",
            "## Next Recommendation",
            "",
            report["next_recommendation"],
            "",
            f"- Markdown summary: `{markdown_path}`",
            f"- JSON summary: `{json_path}`",
            "- No thesis promotion was performed.",
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
    entity_proxy_path: Path | str,
    bucket_count: int,
) -> str:
    return (
        "./trading_env/bin/python -m research.mtp_research.validation.run_entity_coordination_proxy_thesis "
        f"--candidates-path \"{candidates_path}\" "
        f"--snapshots-path \"{snapshots_path}\" "
        f"--outcomes-path \"{outcomes_path}\" "
        f"--entity-proxy-path \"{entity_proxy_path}\" "
        f"--bucket-count {bucket_count}"
    )


def _feature_value(row: dict[str, Any], feature: str) -> float | None:
    return _float_or_none(row["features"].get(feature))


def _direction(low: float | None, high: float | None) -> str:
    if low is None or high is None or high == low:
        return "flat_or_unusable"
    return "higher_proxy_higher_runup" if high > low else "higher_proxy_lower_runup"


def _distribution_summary(values: list[float]) -> dict[str, Any]:
    clean = sorted(value for value in values if value is not None)
    if not clean:
        return {"count": 0, "min": None, "p25": None, "median": None, "p75": None, "max": None, "mean": None}
    return {"count": len(clean), "min": clean[0], "p25": _quantile(clean, 0.25), "median": median(clean), "p75": _quantile(clean, 0.75), "max": clean[-1], "mean": mean(clean)}


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
    return median(clean) if clean else None


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
