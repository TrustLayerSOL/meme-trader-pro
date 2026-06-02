"""Descriptive T008 creator migration reputation thesis cycle."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean, median
from typing import Any

from research.mtp_research.validation.robust_return_metrics import winsorized_mean


THESIS_ID = "T008"
THESIS_NAME = "Creator Migration Reputation"
ALLOWED_CLASSIFICATIONS = {"descriptive_signal_present", "weak_signal", "no_signal", "data_limited"}
PRIMARY_BUCKETS = ("0", "1", "2_to_3", "4_plus")
PRIOR_LAUNCH_BUCKETS = ("0", "1", "2_to_4", "5_to_19", "20_plus")
RATE_BUCKETS = ("no_prior_launches", "zero_rate", "low_rate", "medium_rate", "high_rate")


def build_t008_creator_migration_reputation_report(
    *,
    candidates_path: Path | str,
    outcomes_path: Path | str,
    migration_labels_path: Path | str,
    dataset_scope: str = "all_collected",
) -> dict[str, Any]:
    if dataset_scope != "all_collected":
        raise ValueError("T008 must use all-collected dataset only because strict 4+ prior count is empty")
    candidates = _read_jsonl(candidates_path)
    outcomes_by_mint = {_mint(row): row for row in _read_jsonl(outcomes_path) if _mint(row)}
    labels = _read_jsonl(migration_labels_path)
    migration_records = _migration_records(labels)
    launch_rows = _build_launch_rows(candidates, outcomes_by_mint, migration_records)
    primary_bucket_table = _bucket_table(launch_rows, "creator_prior_migration_or_graduation_count_bucket")
    boolean_feature_tables = _boolean_tables(launch_rows)
    prior_launch_bucket_table = _bucket_table(launch_rows, "creator_prior_launch_count_bucket")
    rate_bucket_table = _bucket_table(launch_rows, "creator_prior_migration_or_graduation_rate_bucket")
    source_sensitivity = _source_sensitivity(candidates, outcomes_by_mint, labels, launch_rows)
    robustness = _robustness_checks(launch_rows, source_sensitivity)
    feature_audit = _feature_audit(launch_rows, migration_records, labels)
    outcome_coverage = _outcome_coverage(launch_rows)
    warning_flags = _warning_flags(launch_rows, feature_audit, outcome_coverage)
    classification = _classify(
        launch_rows,
        primary_bucket_table,
        boolean_feature_tables,
        robustness,
        warning_flags,
    )
    return {
        "thesis_id": THESIS_ID,
        "thesis_name": THESIS_NAME,
        "research_question": (
            "Does leakage-safe creator migration/graduation history show a descriptive relationship "
            "with all-collected FDV-proxy lifecycle outcomes?"
        ),
        "hypothesis": (
            "Creators with stronger prior migration or graduation records may have launches with "
            "different FDV-proxy lifecycle outcomes than creators without that history."
        ),
        "dataset": {
            "dataset_scope": dataset_scope,
            "candidates_path": str(candidates_path),
            "outcomes_path": str(outcomes_path),
            "migration_labels_path": str(migration_labels_path),
            "launch_count": len(launch_rows),
            "all_collected_dataset_required": True,
            "strict_only_run": False,
            "valuation_semantics": "fdv_proxy_only",
            "true_market_cap_claims": "blocked",
            "migration_graduation_semantics": (
                "combined Pump.fun migrate events and DexScreener pair detection are used as "
                "migration/graduation evidence, with source-specific sensitivity checks"
            ),
        },
        "methodology": {
            "primary_bucket": "creator_prior_migration_or_graduation_count_bucket",
            "primary_bucket_definitions": list(PRIMARY_BUCKETS),
            "secondary_buckets": {
                "creator_prior_launch_count_bucket": list(PRIOR_LAUNCH_BUCKETS),
                "creator_prior_migration_or_graduation_rate_bucket": list(RATE_BUCKETS),
            },
            "classification_options": sorted(ALLOWED_CLASSIFICATIONS),
            "descriptive_only": True,
            "predefined_buckets_only": True,
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
        "leakage_rule": {
            "same_creator_required": True,
            "migration_or_graduation_timestamp_required": True,
            "strictly_before_current_launch": True,
            "missing_migration_timestamp_counted_as_prior": False,
            "current_launch_outcome_separated_from_prior_history": True,
        },
        "feature_semantics": _feature_semantics(),
        "launch_rows": launch_rows,
        "sample_counts": {"launch_count": len(launch_rows), "token_count": len({row["token_mint"] for row in launch_rows})},
        "feature_audit": feature_audit,
        "outcome_coverage": outcome_coverage,
        "primary_bucket_table": primary_bucket_table,
        "boolean_feature_tables": boolean_feature_tables,
        "prior_launch_bucket_table": prior_launch_bucket_table,
        "prior_migration_rate_bucket_table": rate_bucket_table,
        "migration_vs_raw_launch_count_read": _migration_vs_raw_launch_count_read(primary_bucket_table, prior_launch_bucket_table),
        "sensitivity_checks": source_sensitivity,
        "robustness_checks": robustness,
        "final_classification": classification,
        "chronological_source_robustness_recommended": classification in {"descriptive_signal_present", "weak_signal"},
        "warning_flags": warning_flags,
        "limitations": _limitations(),
        "next_recommendation": _next_recommendation(classification),
        "reproducible_command": _reproducible_command(candidates_path, outcomes_path, migration_labels_path),
    }


def write_t008_report_outputs(
    report: dict[str, Any],
    *,
    output_dir: Path | str,
    status_path: Path | str,
) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "T008_creator_migration_reputation_summary.json"
    markdown_path = output / "T008_creator_migration_reputation_summary.md"
    json_path.write_text(json.dumps(_public_report(report), indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(_markdown_summary(report), encoding="utf-8")
    status = Path(status_path)
    status.parent.mkdir(parents=True, exist_ok=True)
    status.write_text(_status_markdown(report, markdown_path, json_path), encoding="utf-8")
    return {"json_summary_path": json_path, "markdown_summary_path": markdown_path, "status_path": status}


def _build_launch_rows(
    candidates: list[dict[str, Any]],
    outcomes_by_mint: dict[str, dict[str, Any]],
    migration_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    migrations_by_creator: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in migration_records:
        if record.get("creator") and record.get("migration_ts") is not None:
            migrations_by_creator[str(record["creator"])].append(record)
    for rows in migrations_by_creator.values():
        rows.sort(key=lambda row: (row["migration_ts"], row.get("mint") or "", row.get("source") or ""))
    prior_launch_counts: Counter[str] = Counter()
    rows = []
    for candidate in sorted(candidates, key=lambda row: (_launch_ts(row) or 0, _mint(row) or "")):
        mint = _mint(candidate)
        creator = _creator(candidate)
        launch_ts = _launch_ts(candidate)
        prior_records = []
        if creator and launch_ts is not None:
            prior_records = [
                record for record in migrations_by_creator.get(creator, [])
                if record["migration_ts"] < launch_ts
            ]
        prior_migration_count = sum(1 for record in prior_records if record["evidence_type"] == "pumpfun_migration_event")
        prior_graduation_count = sum(1 for record in prior_records if record["evidence_type"] == "dexscreener_pair_detection")
        combined_count = len(prior_records)
        prior_launch_count = prior_launch_counts[creator] if creator else 0
        prior_rate = combined_count / prior_launch_count if prior_launch_count else None
        current_records = [record for record in migration_records if record.get("mint") == mint]
        outcome = outcomes_by_mint.get(mint or "", {})
        rows.append(
            {
                "launch_id": candidate.get("launch_id"),
                "token_mint": mint,
                "creator": creator,
                "launch_ts": launch_ts,
                "features": {
                    "creator_prior_migration_count": prior_migration_count,
                    "creator_prior_graduation_count": prior_graduation_count,
                    "creator_prior_migration_or_graduation_count": combined_count,
                    "creator_has_prior_migration_or_graduation": combined_count >= 1,
                    "creator_has_2plus_prior_migrations_or_graduations": combined_count >= 2,
                    "creator_has_4plus_prior_migrations_or_graduations": combined_count >= 4,
                    "creator_prior_launch_count": prior_launch_count,
                    "creator_prior_migration_or_graduation_rate": prior_rate,
                    "creator_prior_last_migration_or_graduation_age_seconds": (
                        launch_ts - prior_records[-1]["migration_ts"]
                        if prior_records and launch_ts is not None else None
                    ),
                    "creator_prior_migration_or_graduation_count_bucket": _combined_count_bucket(combined_count),
                    "creator_prior_launch_count_bucket": _prior_launch_bucket(prior_launch_count),
                    "creator_prior_migration_or_graduation_rate_bucket": _rate_bucket(prior_rate, prior_launch_count),
                },
                "outcomes": _fdv_outcomes(outcome),
                "current_launch_migration_graduation": _current_migration_outcome(current_records),
                "metadata_json": {
                    "prior_evidence_sources": sorted({record["source"] for record in prior_records if record.get("source")}),
                    "current_evidence_sources": sorted({record["source"] for record in current_records if record.get("source")}),
                    "prior_migration_or_graduation_mints": [record.get("mint") for record in prior_records],
                },
            }
        )
        if creator:
            prior_launch_counts[creator] += 1
    return rows


def _migration_records(labels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records = []
    seen: set[tuple[str | None, str | None, str | None]] = set()
    for label in labels:
        if not _is_positive_migration_or_graduation(label):
            continue
        mint = _mint(label)
        source = str(label.get("migration_source") or "")
        evidence_type = _evidence_type(label)
        signature = label.get("migration_signature") or label.get("pair_address") or label.get("dexscreener_url")
        key = (mint, signature, source or evidence_type)
        if key in seen:
            continue
        seen.add(key)
        records.append(
            {
                "mint": mint,
                "creator": label.get("creator"),
                "migration_ts": _timestamp_to_int(label.get("migration_time")),
                "source": source or evidence_type,
                "evidence_type": evidence_type,
                "signature": signature,
                "timestamp_available": _timestamp_to_int(label.get("migration_time")) is not None,
                "pumpfun_migrate_event_observed": bool(label.get("pumpfun_migrate_event_observed")),
                "dex_pair_detected": bool(label.get("dex_pair_detected")),
            }
        )
    return records


def _fdv_outcomes(outcome: dict[str, Any]) -> dict[str, Any]:
    runups = outcome.get("runups") or {}
    drawdowns = outcome.get("drawdowns") or {}
    return {
        "fdv_proxy_runup_120m": _float_or_none(
            _first_present(runups.get("max_runup_120m"), outcome.get("fdv_proxy_runup_120m"))
        ),
        "fdv_proxy_drawdown_120m": _float_or_none(
            _first_present(drawdowns.get("max_drawdown_120m"), outcome.get("fdv_proxy_drawdown_120m"))
        ),
        "price_available_120m": bool(outcome.get("price_available_120m") or outcome.get("has_price_at_120m")),
        "liquidity_proxy_available_120m": bool(outcome.get("has_liquidity_proxy_at_120m") or outcome.get("liquidity_survival_120m")),
        "true_market_cap_available": bool(outcome.get("true_market_cap_available") or outcome.get("market_cap_available")),
    }


def _current_migration_outcome(records: list[dict[str, Any]]) -> dict[str, Any]:
    timestamped = [record for record in records if record.get("migration_ts") is not None]
    return {
        "current_launch_migration_or_graduation_observed": bool(records),
        "current_launch_migration_or_graduation_time_available": bool(timestamped),
        "current_launch_evidence_types": sorted({record["evidence_type"] for record in records}),
    }


def _bucket_table(rows: list[dict[str, Any]], feature: str) -> list[dict[str, Any]]:
    return [_summarize_bucket(bucket, [row for row in rows if row["features"].get(feature) == bucket]) for bucket in _bucket_order(feature)]


def _boolean_tables(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    return {
        "creator_has_prior_migration_or_graduation": [
            _summarize_named_group("false", [row for row in rows if not row["features"]["creator_has_prior_migration_or_graduation"]]),
            _summarize_named_group("true", [row for row in rows if row["features"]["creator_has_prior_migration_or_graduation"]]),
        ],
        "creator_has_2plus_prior_migrations_or_graduations": [
            _summarize_named_group("fewer_than_2", [row for row in rows if not row["features"]["creator_has_2plus_prior_migrations_or_graduations"]]),
            _summarize_named_group("2_plus", [row for row in rows if row["features"]["creator_has_2plus_prior_migrations_or_graduations"]]),
        ],
        "creator_has_4plus_prior_migrations_or_graduations": [
            _summarize_named_group("fewer_than_4", [row for row in rows if not row["features"]["creator_has_4plus_prior_migrations_or_graduations"]]),
            _summarize_named_group("4_plus", [row for row in rows if row["features"]["creator_has_4plus_prior_migrations_or_graduations"]]),
        ],
    }


def _summarize_bucket(bucket: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    summary = _outcome_summary(rows)
    summary["bucket"] = bucket
    return summary


def _summarize_named_group(name: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    summary = _outcome_summary(rows)
    summary["group"] = name
    return summary


def _outcome_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    runups = [_float_or_none(row["outcomes"].get("fdv_proxy_runup_120m")) for row in rows]
    drawdowns = [_float_or_none(row["outcomes"].get("fdv_proxy_drawdown_120m")) for row in rows]
    return {
        "launch_count": len(rows),
        "sample_count": len(rows),
        "token_count": len({row["token_mint"] for row in rows if row.get("token_mint")}),
        "median_fdv_proxy_runup_120m": _median(runups),
        "median_fdv_proxy_drawdown_120m": _median(drawdowns),
        "price_available_120m_rate": _true_rate(row["outcomes"].get("price_available_120m") for row in rows),
        "liquidity_proxy_available_120m_rate": _true_rate(row["outcomes"].get("liquidity_proxy_available_120m") for row in rows),
        "current_migration_or_graduation_observed_rate": _true_rate(
            row["current_launch_migration_graduation"].get("current_launch_migration_or_graduation_observed")
            for row in rows
        ),
    }


def _source_sensitivity(
    candidates: list[dict[str, Any]],
    outcomes_by_mint: dict[str, dict[str, Any]],
    labels: list[dict[str, Any]],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    pumpfun_labels = [label for label in labels if bool(label.get("pumpfun_migrate_event_observed"))]
    dex_labels = [label for label in labels if bool(label.get("dex_pair_detected")) and not bool(label.get("pumpfun_migrate_event_observed"))]
    no_dex_labels = [label for label in labels if not (bool(label.get("dex_pair_detected")) and not bool(label.get("pumpfun_migrate_event_observed")))]
    return {
        "exclude_dexscreener_only": _sensitivity_run(candidates, outcomes_by_mint, no_dex_labels),
        "pumpfun_only": _sensitivity_run(candidates, outcomes_by_mint, pumpfun_labels),
        "dexscreener_only": _sensitivity_run(candidates, outcomes_by_mint, dex_labels),
        "exclude_top_1pct_fdv_proxy_runups": _outlier_run(rows, 0.99),
        "exclude_top_5pct_fdv_proxy_runups": _outlier_run(rows, 0.95),
        "four_plus_bucket_creator_dominance": _creator_dominance(
            [row for row in rows if row["features"]["creator_prior_migration_or_graduation_count_bucket"] == "4_plus"]
        ),
        "two_plus_bucket_creator_dominance": _creator_dominance(
            [row for row in rows if row["features"]["creator_has_2plus_prior_migrations_or_graduations"]]
        ),
    }


def _sensitivity_run(
    candidates: list[dict[str, Any]],
    outcomes_by_mint: dict[str, dict[str, Any]],
    labels: list[dict[str, Any]],
) -> dict[str, Any]:
    records = _migration_records(labels)
    rows = _build_launch_rows(candidates, outcomes_by_mint, records)
    return {
        "launch_count": len(rows),
        "migration_records_used": len(records),
        "primary_bucket_table": _bucket_table(rows, "creator_prior_migration_or_graduation_count_bucket"),
        "boolean_feature_tables": _boolean_tables(rows),
    }


def _outlier_run(rows: list[dict[str, Any]], quantile: float) -> dict[str, Any]:
    values = sorted(
        value for value in (_float_or_none(row["outcomes"].get("fdv_proxy_runup_120m")) for row in rows)
        if value is not None
    )
    cutoff = _quantile(values, quantile)
    filtered = [
        row for row in rows
        if cutoff is None or _float_or_none(row["outcomes"].get("fdv_proxy_runup_120m")) is None
        or (_float_or_none(row["outcomes"].get("fdv_proxy_runup_120m")) or 0) <= cutoff
    ]
    return {
        "launch_count": len(filtered),
        "cutoff": cutoff,
        "primary_bucket_table": _bucket_table(filtered, "creator_prior_migration_or_graduation_count_bucket"),
    }


def _robustness_checks(rows: list[dict[str, Any]], source_sensitivity: dict[str, Any]) -> dict[str, Any]:
    return {
        "four_plus_bucket_creator_dominance": _creator_dominance(
            [row for row in rows if row["features"]["creator_prior_migration_or_graduation_count_bucket"] == "4_plus"]
        ),
        "two_plus_bucket_creator_dominance": _creator_dominance(
            [row for row in rows if row["features"]["creator_has_2plus_prior_migrations_or_graduations"]]
        ),
        "massive_prior_launch_creator_check": _massive_prior_launch_check(rows),
        "outlier_adjusted_summary": {
            "winsorized_mean_fdv_proxy_runup_120m": winsorized_mean(
                [_float_or_none(row["outcomes"].get("fdv_proxy_runup_120m")) for row in rows]
            ),
            "winsorized_mean_fdv_proxy_drawdown_120m": winsorized_mean(
                [_float_or_none(row["outcomes"].get("fdv_proxy_drawdown_120m")) for row in rows]
            ),
        },
        "source_sensitivity_interpretation": _source_sensitivity_interpretation(source_sensitivity),
    }


def _creator_dominance(rows: list[dict[str, Any]]) -> dict[str, Any]:
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


def _massive_prior_launch_check(rows: list[dict[str, Any]]) -> dict[str, Any]:
    massive = [row for row in rows if (row["features"].get("creator_prior_launch_count") or 0) >= 20]
    return {
        "launch_count": len(massive),
        "share_of_dataset": len(massive) / len(rows) if rows else 0,
        "outcome_summary": _outcome_summary(massive),
    }


def _feature_audit(
    rows: list[dict[str, Any]],
    migration_records: list[dict[str, Any]],
    labels: list[dict[str, Any]],
) -> dict[str, Any]:
    feature_names = [
        "creator_prior_migration_count",
        "creator_prior_graduation_count",
        "creator_prior_migration_or_graduation_count",
        "creator_has_prior_migration_or_graduation",
        "creator_has_2plus_prior_migrations_or_graduations",
        "creator_has_4plus_prior_migrations_or_graduations",
        "creator_prior_launch_count",
        "creator_prior_migration_or_graduation_rate",
        "creator_prior_last_migration_or_graduation_age_seconds",
    ]
    return {
        "features": {
            feature: _coverage(rows, lambda row, f=feature: row["features"].get(f) is not None)
            for feature in feature_names
        },
        "primary_bucket_counts": dict(Counter(row["features"]["creator_prior_migration_or_graduation_count_bucket"] for row in rows)),
        "prior_launch_bucket_counts": dict(Counter(row["features"]["creator_prior_launch_count_bucket"] for row in rows)),
        "migration_rate_bucket_counts": dict(Counter(row["features"]["creator_prior_migration_or_graduation_rate_bucket"] for row in rows)),
        "migration_timestamp_missing_count": sum(1 for record in migration_records if record.get("migration_ts") is None),
        "positive_label_count": sum(1 for label in labels if _is_positive_migration_or_graduation(label)),
        "migration_records_used": len(migration_records),
        "source_split": {
            "pumpfun_migration_event": sum(1 for record in migration_records if record["evidence_type"] == "pumpfun_migration_event"),
            "dexscreener_pair_detection": sum(1 for record in migration_records if record["evidence_type"] == "dexscreener_pair_detection"),
            "other_combined_label": sum(1 for record in migration_records if record["evidence_type"] == "other_combined_label"),
        },
    }


def _outcome_coverage(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "fdv_proxy_runup_available": sum(1 for row in rows if row["outcomes"].get("fdv_proxy_runup_120m") is not None),
        "fdv_proxy_drawdown_available": sum(1 for row in rows if row["outcomes"].get("fdv_proxy_drawdown_120m") is not None),
        "price_available_120m": sum(1 for row in rows if row["outcomes"].get("price_available_120m")),
        "liquidity_proxy_available_120m": sum(1 for row in rows if row["outcomes"].get("liquidity_proxy_available_120m")),
    }


def _classify(
    rows: list[dict[str, Any]],
    primary_table: list[dict[str, Any]],
    boolean_tables: dict[str, list[dict[str, Any]]],
    robustness: dict[str, Any],
    warning_flags: list[str],
) -> str:
    if len(rows) < 100 or "fdv_proxy_outcomes_missing" in warning_flags:
        return "data_limited"
    non_empty = [bucket for bucket in primary_table if bucket["sample_count"] > 0]
    if len(non_empty) < 3:
        return "data_limited"
    prior_vs_none = boolean_tables["creator_has_prior_migration_or_graduation"]
    four_plus = boolean_tables["creator_has_4plus_prior_migrations_or_graduations"]
    deltas = [
        _runup_delta(prior_vs_none[0], prior_vs_none[1]),
        _runup_delta(four_plus[0], four_plus[1]),
        _runup_delta(non_empty[0], non_empty[-1]),
    ]
    meaningful = sum(1 for delta in deltas if delta is not None and abs(delta) >= 0.1)
    dominance = robustness["four_plus_bucket_creator_dominance"]["dominant_creator_share"]
    source_read = robustness["source_sensitivity_interpretation"]
    if meaningful >= 3 and dominance < 0.6 and source_read != "source_sensitivity_unusable":
        return "descriptive_signal_present"
    if meaningful >= 1:
        return "weak_signal"
    return "no_signal"


def _warning_flags(rows: list[dict[str, Any]], feature_audit: dict[str, Any], outcome_coverage: dict[str, int]) -> list[str]:
    warnings = ["true_market_cap_claims_blocked", "fdv_proxy_only"]
    if not rows:
        warnings.append("empty_dataset")
    if feature_audit["migration_timestamp_missing_count"]:
        warnings.append("missing_migration_timestamps_not_counted")
    if outcome_coverage["fdv_proxy_runup_available"] < len(rows) or outcome_coverage["fdv_proxy_drawdown_available"] < len(rows):
        warnings.append("fdv_proxy_outcomes_missing")
    if feature_audit["primary_bucket_counts"].get("4_plus", 0) == 0:
        warnings.append("four_plus_bucket_empty")
    if feature_audit["source_split"]["dexscreener_pair_detection"] and not feature_audit["source_split"]["pumpfun_migration_event"]:
        warnings.append("dexscreener_only_migration_evidence")
    return warnings


def _migration_vs_raw_launch_count_read(primary_table: list[dict[str, Any]], launch_table: list[dict[str, Any]]) -> str:
    migration_delta = _first_last_runup_delta(primary_table)
    launch_delta = _first_last_runup_delta(launch_table)
    if migration_delta is None and launch_delta is None:
        return "not_comparable"
    if migration_delta is not None and (launch_delta is None or abs(migration_delta) > abs(launch_delta)):
        return "migration_graduation_count_more_informative_descriptively"
    if launch_delta is not None and (migration_delta is None or abs(launch_delta) > abs(migration_delta)):
        return "raw_prior_launch_count_more_informative_descriptively"
    return "similar_descriptive_information"


def _source_sensitivity_interpretation(source_sensitivity: dict[str, Any]) -> str:
    pumpfun_used = source_sensitivity["pumpfun_only"]["migration_records_used"]
    dex_used = source_sensitivity["dexscreener_only"]["migration_records_used"]
    if not pumpfun_used and not dex_used:
        return "source_sensitivity_unusable"
    if pumpfun_used and dex_used:
        return "both_source_sensitivities_available"
    if pumpfun_used:
        return "pumpfun_only_sensitivity_available"
    return "dexscreener_only_sensitivity_available"


def _public_report(report: dict[str, Any]) -> dict[str, Any]:
    public = dict(report)
    public.pop("launch_rows", None)
    return public


def _markdown_summary(report: dict[str, Any]) -> str:
    lines = [
        "# T008 Creator Migration Reputation",
        "",
        f"- Final classification: `{report['final_classification']}`",
        f"- Dataset scope: `{report['dataset']['dataset_scope']}`",
        f"- Launch count: `{report['sample_counts']['launch_count']}`",
        f"- Migration vs raw launch count read: `{report['migration_vs_raw_launch_count_read']}`",
        f"- Chronological/source robustness recommended: `{report['chronological_source_robustness_recommended']}`",
        f"- Warning flags: `{report['warning_flags']}`",
        "",
        "## Primary Bucket Table",
        "",
        "| Bucket | Samples | Median FDV Runup | Median FDV Drawdown | Price 120m | Liquidity 120m | Current Migration/Graduation |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for bucket in report["primary_bucket_table"]:
        lines.append(
            f"| `{bucket['bucket']}` | {bucket['sample_count']} | {_format_pct(bucket['median_fdv_proxy_runup_120m'])} | "
            f"{_format_pct(bucket['median_fdv_proxy_drawdown_120m'])} | {_format_pct(bucket['price_available_120m_rate'])} | "
            f"{_format_pct(bucket['liquidity_proxy_available_120m_rate'])} | {_format_pct(bucket['current_migration_or_graduation_observed_rate'])} |"
        )
    lines.extend(["", "## Source Split", ""])
    for key, value in report["feature_audit"]["source_split"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Sensitivity Checks", ""])
    for key in ["exclude_dexscreener_only", "pumpfun_only", "dexscreener_only"]:
        check = report["sensitivity_checks"][key]
        lines.append(f"- `{key}`: `{check['migration_records_used']}` migration/graduation records used")
    lines.extend(["", "## Limitations", "", *[f"- {item}" for item in report["limitations"]], "", "## Reproducible Command", "", "```bash", report["reproducible_command"], "```"])
    return "\n".join(lines) + "\n"


def _status_markdown(report: dict[str, Any], markdown_path: Path, json_path: Path) -> str:
    return "\n".join(
        [
            "# T008 Creator Migration Reputation Status",
            "",
            "## Thesis Description",
            "",
            report["research_question"],
            "",
            "## Dataset Used",
            "",
            "- All-collected 3,000-launch FDV-proxy lifecycle dataset",
            "- Strict-only T008 was not run because strict 4+ prior history remains empty.",
            f"- Launches analyzed: `{report['sample_counts']['launch_count']}`",
            "",
            "## Feature Coverage",
            "",
            *[
                f"- `{feature}`: `{audit['available_count']}` available, `{audit['coverage_pct']:.2f}%` coverage"
                for feature, audit in report["feature_audit"]["features"].items()
            ],
            "",
            "## Prior Migration / Graduation Bucket Counts",
            "",
            *[
                f"- `{bucket}`: `{count}`"
                for bucket, count in sorted(report["feature_audit"]["primary_bucket_counts"].items())
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
            "## Migration Versus Raw Prior Launch Count",
            "",
            f"`{report['migration_vs_raw_launch_count_read']}`",
            "",
            "## Source Split",
            "",
            *[
                f"- `{key}`: `{value}`"
                for key, value in report["feature_audit"]["source_split"].items()
            ],
            "",
            "## Robustness Caveats",
            "",
            f"- `four_plus_bucket_dominant_creator_share`: `{report['robustness_checks']['four_plus_bucket_creator_dominance']['dominant_creator_share']:.4f}`",
            f"- `two_plus_bucket_dominant_creator_share`: `{report['robustness_checks']['two_plus_bucket_creator_dominance']['dominant_creator_share']:.4f}`",
            f"- `source_sensitivity_interpretation`: `{report['robustness_checks']['source_sensitivity_interpretation']}`",
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
            "- No trading rules were generated.",
            "- No profitability claims were generated.",
            "- True market-cap claims remain blocked.",
            "",
        ]
    )


def _feature_semantics() -> dict[str, str]:
    return {
        "creator_prior_migration_count": "prior same-creator Pump.fun migrate event count with timestamp before current launch",
        "creator_prior_graduation_count": "prior same-creator DexScreener pair-detected graduation proxy count with timestamp before current launch",
        "creator_prior_migration_or_graduation_count": "combined leakage-safe prior migration/graduation evidence count",
        "creator_prior_launch_count": "prior same-creator launch count in the all-collected cohort",
        "creator_prior_migration_or_graduation_rate": "combined prior migration/graduation count divided by prior launch count",
    }


def _limitations() -> list[str]:
    return [
        "This is descriptive research only and does not produce trading rules.",
        "DexScreener pair detection is a graduation proxy and may carry survivorship/source bias.",
        "Pump.fun migration labels are sparse relative to DexScreener pair-detected labels.",
        "FDV proxy is not true market cap because circulating supply remains unavailable.",
        "Current launch migration/graduation outcome is reported separately from prior-history features.",
    ]


def _next_recommendation(classification: str) -> str:
    if classification in {"descriptive_signal_present", "weak_signal"}:
        return "run a separate chronological and source-robustness review for T008 before any validation design"
    if classification == "no_signal":
        return "park T008 or improve migration label provenance before further thesis work"
    return "repair source coverage before interpreting T008"


def _reproducible_command(candidates_path: Path | str, outcomes_path: Path | str, migration_labels_path: Path | str) -> str:
    return (
        "./trading_env/bin/python -m research.mtp_research.validation.run_creator_migration_reputation_thesis "
        f"--candidates-path \"{candidates_path}\" "
        f"--outcomes-path \"{outcomes_path}\" "
        f"--migration-labels-path \"{migration_labels_path}\""
    )


def _is_positive_migration_or_graduation(row: dict[str, Any]) -> bool:
    return bool(
        row.get("pumpfun_migrate_event_observed")
        or row.get("graduated_to_pumpswap")
        or row.get("migrated_to_raydium")
        or row.get("dex_pair_detected")
        or row.get("liquidity_pool_created_after_launch")
    )


def _evidence_type(row: dict[str, Any]) -> str:
    source = str(row.get("migration_source") or "").lower()
    if row.get("pumpfun_migrate_event_observed") or "pumpfun_migrate" in source or "migrate_log" in source:
        return "pumpfun_migration_event"
    if row.get("dex_pair_detected") or "dexscreener" in source:
        return "dexscreener_pair_detection"
    return "other_combined_label"


def _combined_count_bucket(count: int) -> str:
    if count <= 0:
        return "0"
    if count == 1:
        return "1"
    if count <= 3:
        return "2_to_3"
    return "4_plus"


def _prior_launch_bucket(count: int) -> str:
    if count <= 0:
        return "0"
    if count == 1:
        return "1"
    if count <= 4:
        return "2_to_4"
    if count <= 19:
        return "5_to_19"
    return "20_plus"


def _rate_bucket(rate: float | None, prior_launch_count: int) -> str:
    if prior_launch_count <= 0:
        return "no_prior_launches"
    if rate is None or rate == 0:
        return "zero_rate"
    if rate < 0.25:
        return "low_rate"
    if rate < 0.75:
        return "medium_rate"
    return "high_rate"


def _bucket_order(feature: str) -> tuple[str, ...]:
    if feature == "creator_prior_migration_or_graduation_count_bucket":
        return PRIMARY_BUCKETS
    if feature == "creator_prior_launch_count_bucket":
        return PRIOR_LAUNCH_BUCKETS
    if feature == "creator_prior_migration_or_graduation_rate_bucket":
        return RATE_BUCKETS
    return ()


def _coverage(rows: list[dict[str, Any]], predicate) -> dict[str, Any]:
    available = sum(1 for row in rows if predicate(row))
    return {
        "available_count": available,
        "missing_count": len(rows) - available,
        "coverage_pct": available / len(rows) * 100 if rows else 0,
    }


def _runup_delta(left: dict[str, Any], right: dict[str, Any]) -> float | None:
    low = _float_or_none(left.get("median_fdv_proxy_runup_120m"))
    high = _float_or_none(right.get("median_fdv_proxy_runup_120m"))
    if low is None or high is None:
        return None
    return high - low


def _first_last_runup_delta(table: list[dict[str, Any]]) -> float | None:
    non_empty = [row for row in table if row.get("sample_count", 0) > 0]
    if len(non_empty) < 2:
        return None
    return _runup_delta(non_empty[0], non_empty[-1])


def _read_jsonl(path: Path | str) -> list[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _mint(row: dict[str, Any]) -> str | None:
    value = row.get("token_mint") or row.get("mint")
    return str(value) if value else None


def _creator(row: dict[str, Any]) -> str | None:
    metadata = row.get("metadata_json") or {}
    value = row.get("creator") or row.get("creator_deployer") or row.get("creator_wallet") or metadata.get("creator_deployer")
    return str(value) if value else None


def _launch_ts(row: dict[str, Any]) -> int | None:
    return _int_or_none(row.get("launch_ts") or row.get("block_time"))


def _timestamp_to_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value)
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        pass
    try:
        return int(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _median(values: list[float | None]) -> float | None:
    clean = [value for value in values if value is not None]
    return median(clean) if clean else None


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


def _format_pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.4f}"
