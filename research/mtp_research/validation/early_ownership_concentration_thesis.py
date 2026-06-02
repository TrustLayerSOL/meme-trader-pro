"""Descriptive T001 early ownership concentration thesis cycle."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any

from research.mtp_research.validation.robust_return_metrics import winsorized_mean


THESIS_ID = "T001"
THESIS_NAME = "Early Ownership Concentration"
DEFAULT_REQUIRED_FEATURES = [
    "first_10_buyer_share",
    "first_20_buyer_share",
    "creator_share",
    "sniper_share",
    "insider_share",
    "bundler_share",
    "top_holder_share",
]
PRIMARY_OUTCOMES = [
    "fdv_proxy_runup_120m",
    "fdv_proxy_drawdown_120m",
    "price_available_120m",
    "liquidity_proxy_available_120m",
]
ALLOWED_CLASSIFICATIONS = {
    "descriptive_signal_present",
    "weak_signal",
    "no_signal",
    "data_limited",
}


def build_t001_early_ownership_report(
    *,
    candidates_path: Path | str,
    events_path: Path | str,
    snapshots_path: Path | str,
    outcomes_path: Path | str,
    holder_state_snapshots_path: Path | str | None = None,
    bucket_count: int = 5,
    observation_window_seconds: int = 120,
) -> dict[str, Any]:
    candidates = _read_jsonl(candidates_path)
    events_by_mint = _group_by_mint(_read_jsonl(events_path))
    snapshots_by_mint = _group_by_mint(_read_jsonl(snapshots_path))
    holder_state_by_mint = _group_by_mint(_read_jsonl(holder_state_snapshots_path)) if holder_state_snapshots_path else {}
    outcomes_by_mint = {row["token_mint"]: row for row in _read_jsonl(outcomes_path)}
    launch_rows = []
    for candidate in sorted(candidates, key=lambda row: (row.get("launch_ts", 0), row.get("token_mint", ""))):
        mint = candidate["token_mint"]
        row = _build_launch_row(
            candidate=candidate,
            events=events_by_mint.get(mint, []),
            snapshots=snapshots_by_mint.get(mint, []),
            holder_state_snapshots=holder_state_by_mint.get(mint, []),
            outcome=outcomes_by_mint.get(mint, {}),
            observation_window_seconds=observation_window_seconds,
        )
        launch_rows.append(row)

    missing_value_audit = _missing_value_audit(launch_rows)
    feature_reports = {
        feature: _feature_report(launch_rows, feature, bucket_count)
        for feature in DEFAULT_REQUIRED_FEATURES
    }
    sensitivity_checks = {
        f"{count}_bucket": {
            feature: _feature_report(launch_rows, feature, count)["bucket_tables"]
            for feature in ("first_10_buyer_share", "first_20_buyer_share", "creator_share", "sniper_share")
        }
        for count in (5, 10)
    }
    warning_flags = _warning_flags(launch_rows, missing_value_audit)
    classification = _classify(feature_reports, warning_flags, len(launch_rows))
    return {
        "thesis_id": THESIS_ID,
        "thesis_name": THESIS_NAME,
        "hypothesis": "Lower early ownership concentration is associated with better lifecycle outcomes.",
        "dataset": {
            "candidates_path": str(candidates_path),
            "events_path": str(events_path),
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
            "observation_window_seconds": observation_window_seconds,
            "required_features": DEFAULT_REQUIRED_FEATURES,
            "primary_outcomes": PRIMARY_OUTCOMES,
            "classification_options": sorted(ALLOWED_CLASSIFICATIONS),
        },
        "methodology_flags": [
            "research_only",
            "no_trading_rules",
            "no_profitability_claims",
            "no_entry_exit_logic",
            "no_threshold_optimization",
            "no_parameter_search",
            "no_future_leakage",
            "fdv_proxy_not_true_market_cap",
            "holder_state_observed_delta_replay_not_full_chain_state" if holder_state_snapshots_path else "holder_state_unavailable",
        ],
        "launch_rows": launch_rows,
        "sample_counts": _sample_counts(launch_rows),
        "missing_value_audit": missing_value_audit,
        "feature_reports": feature_reports,
        "sensitivity_checks": sensitivity_checks,
        "final_classification": classification,
        "warning_flags": warning_flags,
        "data_quality_caveats": _data_quality_caveats(warning_flags),
        "reproducible_command": _reproducible_command(
            candidates_path,
            events_path,
            snapshots_path,
            holder_state_snapshots_path,
            outcomes_path,
            bucket_count,
            observation_window_seconds,
        ),
    }


def write_t001_report_outputs(
    report: dict[str, Any],
    *,
    output_dir: Path | str,
    status_path: Path | str,
) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "T001_early_ownership_concentration_summary.json"
    markdown_path = output / "T001_early_ownership_concentration_summary.md"
    json_path.write_text(json.dumps(_public_report(report), indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(_markdown_summary(report), encoding="utf-8")
    status = Path(status_path)
    status.parent.mkdir(parents=True, exist_ok=True)
    status.write_text(_status_markdown(report, markdown_path, json_path), encoding="utf-8")
    return {
        "json_summary_path": json_path,
        "markdown_summary_path": markdown_path,
        "status_path": status,
    }


def _build_launch_row(
    *,
    candidate: dict[str, Any],
    events: list[dict[str, Any]],
    snapshots: list[dict[str, Any]],
    holder_state_snapshots: list[dict[str, Any]],
    outcome: dict[str, Any],
    observation_window_seconds: int,
) -> dict[str, Any]:
    launch_ts = int(candidate["launch_ts"])
    creator = (candidate.get("metadata_json") or {}).get("creator_deployer")
    eligible_events = [
        event for event in events
        if _event_time(event) is not None
        and launch_ts <= _event_time(event) <= launch_ts + observation_window_seconds
    ]
    buy_events = [
        event for event in eligible_events
        if event.get("venue") == "pumpfun_buy" and _positive_qty(event)
    ]
    create_events = [
        event for event in eligible_events
        if event.get("venue") == "pumpfun_create" and _positive_qty(event)
    ]
    holder_state = _nearest_holder_state_snapshot(holder_state_snapshots, observation_window_seconds)
    features = {
        "first_10_buyer_share": _largest_actor_share(buy_events[:10]),
        "first_20_buyer_share": _largest_actor_share(buy_events[:20]),
        "creator_share": _holder_state_value(holder_state, "creator_holder_share")
        if _holder_state_value(holder_state, "creator_holder_share") is not None
        else _creator_share(create_events + buy_events[:20], creator),
        "sniper_share": _sniper_share(buy_events, launch_ts),
        "insider_share": None,
        "bundler_share": None,
        "top_holder_share": _holder_state_value(holder_state, "top_holder_share"),
    }
    return {
        "launch_id": candidate.get("launch_id"),
        "token_mint": candidate["token_mint"],
        "launch_ts": launch_ts,
        "launch_regime": candidate.get("launch_regime"),
        "features": features,
        "outcomes": _fdv_outcomes(snapshots, outcome),
        "metadata_json": {
            "creator_deployer_available": bool(creator),
            "early_buy_event_count": len(buy_events),
            "early_create_event_count": len(create_events),
            "feature_window_seconds": observation_window_seconds,
            "max_feature_event_block_time": max((_event_time(event) for event in eligible_events), default=None),
            "feature_actor_sample": sorted({str(event.get("actor")) for event in eligible_events if event.get("actor")})[:10],
            "unavailable_feature_reasons": {
                "insider_share": "no_insider_wallet_labels",
                "bundler_share": "no_bundle_detection_labels",
                "top_holder_share": None if features["top_holder_share"] is not None else "no_holder_snapshot_state",
            },
            "holder_state_snapshot_age_seconds": holder_state.get("snapshot_age_seconds") if holder_state else None,
            "holder_state_confidence": holder_state.get("holder_snapshot_confidence") if holder_state else None,
        },
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
        fdv_runup = (max(values) / base) - 1
        fdv_drawdown = (min(values) / base) - 1
        fdv_return = (values[-1] / base) - 1
    else:
        fdv_runup = None
        fdv_drawdown = None
        fdv_return = None
    return {
        "fdv_proxy_runup_120m": fdv_runup,
        "fdv_proxy_drawdown_120m": fdv_drawdown,
        "fdv_proxy_return_120m": fdv_return,
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
        "row_count": len(rows),
        "usable_count": len(usable),
        "missing_count": len(rows) - len(usable),
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
        [row for row in rows if _float_or_none(row["features"].get(feature)) is not None],
        key=lambda row: (
            _float_or_none(row["features"].get(feature)),
            row.get("launch_ts", 0),
            row.get("token_mint", ""),
        ),
    )
    if not usable:
        return []
    buckets: list[list[dict[str, Any]]] = [[] for _ in range(min(bucket_count, len(usable)))]
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
        "price_available_120m_count": sum(1 for row in rows if row["outcomes"].get("price_available_120m")),
        "liquidity_proxy_available_120m_count": sum(
            1 for row in rows if row["outcomes"].get("liquidity_proxy_available_120m")
        ),
    }


def _missing_value_audit(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    audit = {}
    for feature in DEFAULT_REQUIRED_FEATURES:
        missing = sum(1 for row in rows if _float_or_none(row["features"].get(feature)) is None)
        audit[feature] = {
            "missing_count": missing,
            "available_count": len(rows) - missing,
            "missing_rate": (missing / len(rows)) if rows else None,
        }
    return audit


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


def _classify(feature_reports: dict[str, dict[str, Any]], warning_flags: list[str], row_count: int) -> str:
    if row_count < 100 or "fdv_proxy_outcomes_missing" in warning_flags:
        return "data_limited"
    primary = [
        feature_reports["first_10_buyer_share"],
        feature_reports["first_20_buyer_share"],
    ]
    directional = 0
    for report in primary:
        buckets = report["bucket_tables"]
        if len(buckets) < 2:
            continue
        low = buckets[0]["median_fdv_proxy_runup_120m"]
        high = buckets[-1]["median_fdv_proxy_runup_120m"]
        if low is not None and high is not None and low > high:
            directional += 1
    if directional == 2:
        return "descriptive_signal_present"
    if directional == 1:
        return "weak_signal"
    return "no_signal"


def _warning_flags(rows: list[dict[str, Any]], missing_value_audit: dict[str, dict[str, Any]]) -> list[str]:
    warnings = []
    if missing_value_audit["top_holder_share"]["missing_count"]:
        warnings.append("missing_holder_state_features")
    if any(missing_value_audit[name]["missing_count"] for name in ("insider_share", "bundler_share")):
        warnings.append("missing_wallet_label_features")
    if any(not row["outcomes"].get("proxy_threshold_outcomes_usable") for row in rows):
        warnings.append("fdv_proxy_thresholds_not_fully_usable")
    if any(row["outcomes"].get("true_market_cap_available") for row in rows):
        warnings.append("unexpected_true_market_cap_present")
    else:
        warnings.append("true_market_cap_claims_blocked")
    if any(row["outcomes"].get("fdv_proxy_runup_120m") is None for row in rows):
        warnings.append("fdv_proxy_outcomes_missing")
    return warnings


def _data_quality_caveats(warning_flags: list[str]) -> list[str]:
    caveats = [
        "This is descriptive research over strict launch-regime FDV-proxy artifacts only.",
        "FDV proxy is not true market cap because circulating supply is unavailable.",
        "No trading rules, entry logic, exit logic, or profitability claims are produced.",
    ]
    if "missing_holder_state_features" in warning_flags:
        caveats.append("Top-holder share requires replay-safe holder-state snapshots.")
    if "missing_wallet_label_features" in warning_flags:
        caveats.append("Insider and bundler shares require separate wallet labeling.")
    return caveats


def _public_report(report: dict[str, Any]) -> dict[str, Any]:
    public = dict(report)
    public.pop("launch_rows", None)
    return public


def _markdown_summary(report: dict[str, Any]) -> str:
    lines = [
        "# T001 Early Ownership Concentration",
        "",
        f"- Final classification: `{report['final_classification']}`",
        f"- Launch count: `{report['sample_counts']['launch_count']}`",
        f"- Valuation semantics: `{report['dataset']['valuation_semantics']}`",
        f"- True market-cap claims: `{report['dataset']['true_market_cap_claims']}`",
        f"- Warning flags: `{report['warning_flags']}`",
        "",
        "## Method",
        "",
        "- Deterministic quantile buckets only.",
        "- No threshold optimization, parameter search, trading rules, or profitability claims.",
        "",
        "## Missing-Value Audit",
        "",
        "| Feature | Available | Missing | Missing Rate |",
        "|---|---:|---:|---:|",
    ]
    for feature, audit in report["missing_value_audit"].items():
        rate = audit["missing_rate"]
        lines.append(
            f"| `{feature}` | {audit['available_count']} | {audit['missing_count']} | "
            f"{_format_rate(rate)} |"
        )
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
            "## Data-Quality Caveats",
            "",
            *[f"- {caveat}" for caveat in report["data_quality_caveats"]],
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
    audit = report["missing_value_audit"]
    return "\n".join(
        [
            "# T001 Early Ownership Concentration Status",
            "",
            f"- Thesis ID: `{report['thesis_id']}`",
            f"- Current classification: `{report['final_classification']}`",
            f"- Dataset: strict launch-regime FDV-proxy lifecycle dataset",
            f"- Holder-state snapshots: `{report['dataset'].get('holder_state_snapshots_path')}`",
            f"- Launches analyzed: `{report['sample_counts']['launch_count']}`",
            f"- `top_holder_share` available: `{audit['top_holder_share']['available_count']}`",
            f"- `creator_share` available: `{audit['creator_share']['available_count']}`",
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
    events_path: Path | str,
    snapshots_path: Path | str,
    holder_state_snapshots_path: Path | str | None,
    outcomes_path: Path | str,
    bucket_count: int,
    observation_window_seconds: int,
) -> str:
    parts = [
        "./trading_env/bin/python -m research.mtp_research.validation.run_early_ownership_concentration_thesis",
        f"--candidates-path \"{candidates_path}\"",
        f"--events-path \"{events_path}\"",
        f"--snapshots-path \"{snapshots_path}\"",
    ]
    if holder_state_snapshots_path:
        parts.append(f"--holder-state-snapshots-path \"{holder_state_snapshots_path}\"")
    parts.extend([
        f"--outcomes-path \"{outcomes_path}\"",
        f"--bucket-count {bucket_count}",
        f"--observation-window-seconds {observation_window_seconds}",
    ])
    return " ".join(parts)


def _read_jsonl(path: Path | str) -> list[dict[str, Any]]:
    if path is None:
        return []
    rows = []
    with Path(path).open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _group_by_mint(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        mint = row.get("token_mint") or row.get("mint")
        if mint:
            grouped[str(mint)].append(row)
    return grouped


def _nearest_holder_state_snapshot(rows: list[dict[str, Any]], max_age_seconds: int) -> dict[str, Any] | None:
    usable = [
        row for row in rows
        if _holder_age(row) is not None
        and _holder_age(row) <= max_age_seconds
        and row.get("holder_count") is not None
    ]
    if not usable:
        return None
    return max(usable, key=lambda row: int(_holder_age(row) or 0))


def _holder_age(row: dict[str, Any]) -> int | None:
    value = row.get("snapshot_age_seconds")
    if value is None:
        value = row.get("launch_age_seconds")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _holder_state_value(row: dict[str, Any] | None, field: str) -> float | None:
    if not row:
        return None
    return _float_or_none(row.get(field))


def _largest_actor_share(events: list[dict[str, Any]]) -> float | None:
    actor_qty: Counter[str] = Counter()
    for event in events:
        actor = event.get("actor")
        qty = _float_or_none(event.get("base_qty"))
        if actor and qty is not None and qty > 0:
            actor_qty[str(actor)] += qty
    total = sum(actor_qty.values())
    if total <= 0:
        return None
    return max(actor_qty.values()) / total


def _creator_share(events: list[dict[str, Any]], creator: str | None) -> float | None:
    if not creator:
        return None
    total = 0.0
    creator_total = 0.0
    for event in events:
        qty = _float_or_none(event.get("base_qty"))
        if qty is None or qty <= 0:
            continue
        total += qty
        if event.get("actor") == creator:
            creator_total += qty
    if total <= 0:
        return None
    return creator_total / total


def _sniper_share(events: list[dict[str, Any]], launch_ts: int, sniper_window_seconds: int = 30) -> float | None:
    total = 0.0
    sniper_total = 0.0
    for event in events:
        qty = _float_or_none(event.get("base_qty"))
        block_time = _event_time(event)
        if qty is None or qty <= 0 or block_time is None:
            continue
        total += qty
        if block_time <= launch_ts + sniper_window_seconds:
            sniper_total += qty
    if total <= 0:
        return None
    return sniper_total / total


def _event_time(event: dict[str, Any]) -> int | None:
    value = event.get("block_time")
    if value is None:
        return None
    return int(value)


def _positive_qty(event: dict[str, Any]) -> bool:
    value = _float_or_none(event.get("base_qty"))
    return value is not None and value > 0


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


def _format_rate(value: float | None) -> str:
    return _format_pct(value)


def _format_num(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.4f}"
