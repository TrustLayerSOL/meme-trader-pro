"""Structural wallet/dev/cluster proxy anatomy report for explosive runners."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

from research.mtp_research.data_paths import data_lake_path
from research.mtp_research.validation.explosive_runner_winner_anatomy_report import (
    DEFAULT_ENTITY_PROXY_PATH,
    DEFAULT_FUNDING_LINK_PATH,
    DEFAULT_HOLDER_STATE_PATH,
    DEFAULT_MIGRATION_LABELS_PATH,
    DEFAULT_SNAPSHOT_PATHS,
    MILESTONES,
    TIER_ORDER,
    write_combined_expanded_snapshots,
)


REPORT_ID = "structural_wallet_anatomy_report_v0"
REPORT_JSON = "structural_wallet_anatomy_summary.json"
REPORT_MD = "structural_wallet_anatomy_summary.md"
AVAILABILITY_JSON = "structural_wallet_data_availability.json"
AVAILABILITY_MD = "structural_wallet_data_availability.md"
DEFAULT_OUTPUT_DIR = data_lake_path("data", "backtests", "diagnostics", "reports", "structural_wallet_anatomy")
DEFAULT_STATUS_PATH = Path("theses/STRUCTURAL_WALLET_ANATOMY_REPORT_STATUS.md")
DEFAULT_EVENT_PATHS = [
    data_lake_path(
        "data",
        "backtests",
        "explosive_runner_expanded",
        "parallel_wide_1",
        "pumpfun_lifecycle_events_parallel_wide_1.jsonl",
    ),
    data_lake_path(
        "data",
        "backtests",
        "explosive_runner_expanded",
        "parallel_deep_2026",
        "pumpfun_lifecycle_events_parallel_deep_2026.jsonl",
    ),
    data_lake_path(
        "data",
        "backtests",
        "explosive_runner_expanded",
        "parallel_pilot",
        "pumpfun_lifecycle_events_parallel_pilot.jsonl",
    ),
]

FEATURE_ROWS = [
    "creator_holder_share_at_20k",
    "top_holder_share_at_20k",
    "top_10_holder_share_at_20k",
    "creator_linked_share_proxy",
    "repeated_actor_overlap_proxy",
    "repeated_buyer_overlap_proxy",
    "synchronized_participation_proxy",
    "circularity_proxy",
    "churn_proxy",
    "fdv_per_event_at_20k",
    "fdv_per_buy_at_20k",
    "fdv_per_active_wallet_at_20k",
    "valuation_growth_per_event_at_20k",
    "valuation_growth_per_buy_at_20k",
    "funding_source_available",
    "repeated_funder_flag",
    "creator_funder_reuse_count",
    "launches_sharing_funder",
    "funding_age_seconds",
    "creator_prior_migration_or_graduation_count",
    "time_to_20k_seconds",
    "time_to_100k_seconds",
    "time_to_500k_seconds",
    "time_to_1m_seconds",
    "event_actor_count",
    "early_buyer_count_proxy",
    "early_buyer_seen_in_prior_launches_count",
]
ENTRY_SIDE_FEATURES = {
    "creator_holder_share_at_20k",
    "top_holder_share_at_20k",
    "top_10_holder_share_at_20k",
    "creator_linked_share_proxy",
    "repeated_actor_overlap_proxy",
    "repeated_buyer_overlap_proxy",
    "synchronized_participation_proxy",
    "circularity_proxy",
    "churn_proxy",
    "fdv_per_event_at_20k",
    "fdv_per_buy_at_20k",
    "fdv_per_active_wallet_at_20k",
    "valuation_growth_per_event_at_20k",
    "valuation_growth_per_buy_at_20k",
    "funding_source_available",
    "repeated_funder_flag",
    "creator_funder_reuse_count",
    "launches_sharing_funder",
    "funding_age_seconds",
    "creator_prior_migration_or_graduation_count",
    "event_actor_count",
    "early_buyer_count_proxy",
    "early_buyer_seen_in_prior_launches_count",
}
EXIT_SIDE_FEATURES = {
    "creator_holder_share_drop_after_20k",
    "top_holder_share_drop_after_20k",
    "top_10_holder_share_drop_after_20k",
    "creator_sell_count_after_20k",
    "sell_pressure_from_early_buyers_after_20k",
    "distribution_before_drawdown_proxy",
}


def build_structural_wallet_anatomy_report(
    *,
    snapshot_paths: list[Path | str],
    output_dir: Path | str,
    status_path: Path | str = DEFAULT_STATUS_PATH,
    holder_state_snapshots_path: Path | str | None = DEFAULT_HOLDER_STATE_PATH,
    entity_proxy_path: Path | str | None = DEFAULT_ENTITY_PROXY_PATH,
    migration_labels_path: Path | str | None = DEFAULT_MIGRATION_LABELS_PATH,
    funding_link_path: Path | str | None = DEFAULT_FUNDING_LINK_PATH,
    event_paths: list[Path | str] | None = None,
) -> tuple[dict[str, Any], dict[str, Path]]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    combined_path = output / "combined_expanded_lifecycle_snapshots.jsonl"
    combine_summary = write_combined_expanded_snapshots(snapshot_paths, combined_path)
    snapshots = _read_jsonl(combined_path)
    holder_rows = _read_jsonl(holder_state_snapshots_path)
    entity_rows = _read_jsonl(entity_proxy_path)
    migration_rows = _read_jsonl(migration_labels_path)
    funding_rows = _read_table(funding_link_path)
    resolved_event_paths = DEFAULT_EVENT_PATHS if event_paths is None else event_paths
    grouped_snapshots = _group_by_mint(snapshots)
    holder_by_mint = _group_by_mint(holder_rows)
    entity_by_mint = _group_by_mint(entity_rows)
    migration_by_mint = {str(_mint(row)): row for row in migration_rows if _mint(row)}
    funding_by_mint = _group_by_mint(funding_rows)
    event_audit = _stream_event_audit(resolved_event_paths, grouped_snapshots)
    event_summaries = event_audit["event_summaries"]

    launch_rows = [
        _launch_structural_row(
            mint,
            rows,
            holder_by_mint.get(mint, []),
            entity_by_mint.get(mint, []),
            migration_by_mint.get(mint, {}),
            funding_by_mint.get(mint, []),
            event_summaries.get(mint, {}),
        )
        for mint, rows in sorted(grouped_snapshots.items())
    ]
    field_availability = _field_availability(
        snapshots=snapshots,
        holder_rows=holder_rows,
        entity_rows=entity_rows,
        funding_rows=funding_rows,
        migration_rows=migration_rows,
        event_field_availability=event_audit["field_availability"],
    )
    coverage = _coverage_report(launch_rows, snapshots, holder_rows, entity_rows, funding_rows, event_audit)
    feasibility_rows = _feature_family_feasibility(field_availability, coverage)
    tier_summary = _tier_summary(launch_rows)
    tier_comparison = _tier_comparison(launch_rows)
    entry_exit_rows = _entry_exit_feature_rows(feasibility_rows)
    data_gap_rows = _data_gap_plan(field_availability, feasibility_rows)
    commonalities = _strongest_commonalities(tier_comparison)
    recommendations = _recommended_next_reports(feasibility_rows, data_gap_rows, commonalities)
    readiness = _readiness(feasibility_rows, commonalities)
    report = {
        "report_id": REPORT_ID,
        "report_type": "structural_wallet_dev_cluster_proxy_anatomy",
        "readiness_classification": readiness,
        "methodology_flags": [
            "research_only",
            "descriptive_discovery_report_only",
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
        ],
        "dataset": {
            "snapshot_paths": [str(path) for path in snapshot_paths],
            "combined_snapshot_path": str(combined_path),
            "combine_summary": combine_summary,
            "event_paths": [str(path) for path in resolved_event_paths],
            "valuation_semantics": "fdv_proxy_only",
            "true_market_cap_claims": "blocked",
        },
        "coverage_report": coverage,
        "field_availability": field_availability,
        "feature_family_feasibility": feasibility_rows,
        "milestone_tier_summary": tier_summary,
        "strongest_hidden_structural_commonalities": commonalities,
        "entry_exit_feature_separation": entry_exit_rows,
        "data_gap_plan": data_gap_rows,
        "recommended_next_reports_or_theses": recommendations,
        "structural_questions": _structural_questions(commonalities, feasibility_rows),
        "limitations": _limitations(coverage),
        "next_action": _next_action(readiness, recommendations),
    }
    paths = write_structural_wallet_anatomy_outputs(
        report,
        feasibility_rows=feasibility_rows,
        tier_rows=tier_comparison,
        entry_exit_rows=entry_exit_rows,
        data_gap_rows=data_gap_rows,
        output_dir=output,
        status_path=status_path,
    )
    return report, paths


def write_structural_wallet_anatomy_outputs(
    report: dict[str, Any],
    *,
    feasibility_rows: list[dict[str, Any]],
    tier_rows: list[dict[str, Any]],
    entry_exit_rows: list[dict[str, Any]],
    data_gap_rows: list[dict[str, Any]],
    output_dir: Path | str,
    status_path: Path | str,
) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / REPORT_JSON
    md_path = output / REPORT_MD
    availability_json = output / AVAILABILITY_JSON
    availability_md = output / AVAILABILITY_MD
    feasibility_csv = output / "structural_feature_feasibility.csv"
    tier_csv = output / "structural_milestone_tier_comparison.csv"
    entry_exit_csv = output / "entry_vs_exit_structural_features.csv"
    gap_csv = output / "structural_data_gap_plan.csv"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_markdown(report), encoding="utf-8")
    availability_json.write_text(json.dumps(report["field_availability"], indent=2, sort_keys=True), encoding="utf-8")
    availability_md.write_text(_availability_markdown(report), encoding="utf-8")
    _write_csv(feasibility_rows, feasibility_csv)
    _write_csv(tier_rows, tier_csv)
    _write_csv(entry_exit_rows, entry_exit_csv)
    _write_csv(data_gap_rows, gap_csv)
    status = Path(status_path)
    status.parent.mkdir(parents=True, exist_ok=True)
    status.write_text(_status_markdown(report, json_path, md_path, availability_md, feasibility_csv, tier_csv, entry_exit_csv, gap_csv), encoding="utf-8")
    return {
        "json_summary_path": json_path,
        "markdown_summary_path": md_path,
        "data_availability_json_path": availability_json,
        "data_availability_markdown_path": availability_md,
        "structural_feature_feasibility_path": feasibility_csv,
        "structural_milestone_tier_comparison_path": tier_csv,
        "entry_vs_exit_structural_features_path": entry_exit_csv,
        "structural_data_gap_plan_path": gap_csv,
        "status_path": status,
    }


def _launch_structural_row(
    mint: str,
    snapshots: list[dict[str, Any]],
    holder_rows: list[dict[str, Any]],
    entity_rows: list[dict[str, Any]],
    migration_row: dict[str, Any],
    funding_rows: list[dict[str, Any]],
    event_summary: dict[str, Any],
) -> dict[str, Any]:
    priced = sorted([row for row in snapshots if _value(row) is not None], key=_age)
    crossings = {name: _first_crossing(priced, value) for name, value in MILESTONES.items()}
    at_20k = _snapshot_before(priced, _age(crossings["20k"])) if crossings.get("20k") else None
    prior = at_20k.get("_prior_snapshot") if at_20k else None
    holder_20k = _nearest_holder(holder_rows, _age(at_20k)) if at_20k else None
    holder_100k = _nearest_holder(holder_rows, _age(crossings["100k"])) if crossings.get("100k") else None
    entity = entity_rows[0] if entity_rows else {}
    funding = funding_rows[0] if funding_rows else {}
    creator = _first_present(*(row.get("creator") or row.get("creator_deployer") for row in snapshots), entity.get("creator"), funding.get("creator"))
    launch_ts = _int_or_none(_first_present(*(row.get("launch_ts") for row in snapshots), funding.get("launch_ts")))
    fdv = _value(at_20k) if at_20k else None
    event_count = _event_count(at_20k) if at_20k else None
    buy_count = _float_or_none(at_20k.get("buy_count")) if at_20k else None
    active = _float_or_none(at_20k.get("active_wallets")) if at_20k else None
    row = {
        "mint": mint,
        "launch_id": _first_present(*(row.get("launch_id") for row in snapshots), funding.get("launch_id")),
        "creator": creator,
        "launch_ts": launch_ts,
        "launch_date": _launch_date(launch_ts),
        "milestone_tier": _highest_tier(crossings),
        "peak_fdv_proxy": max((_value(row) or 0 for row in priced), default=None),
        "creator_holder_share_at_20k": _float_or_none(holder_20k.get("creator_holder_share")) if holder_20k else None,
        "top_holder_share_at_20k": _float_or_none(holder_20k.get("top_holder_share")) if holder_20k else None,
        "top_10_holder_share_at_20k": _float_or_none(holder_20k.get("top_10_holder_share")) if holder_20k else None,
        "creator_holder_share_change_20k_to_100k": _holder_delta(holder_100k, holder_20k, "creator_holder_share"),
        "top_holder_share_change_20k_to_100k": _holder_delta(holder_100k, holder_20k, "top_holder_share"),
        "top_10_holder_share_change_20k_to_100k": _holder_delta(holder_100k, holder_20k, "top_10_holder_share"),
        "creator_linked_share_proxy": _first_float(entity.get("creator_linked_share_proxy"), holder_20k.get("creator_linked_share") if holder_20k else None),
        "repeated_actor_overlap_proxy": _float_or_none(entity.get("repeated_actor_overlap_proxy")),
        "repeated_buyer_overlap_proxy": _float_or_none(entity.get("repeated_buyer_overlap_proxy")),
        "synchronized_participation_proxy": _float_or_none(entity.get("synchronized_participation_proxy")),
        "circularity_proxy": _float_or_none(entity.get("circularity_proxy")),
        "churn_proxy": _first_float(entity.get("churn_proxy"), holder_20k.get("holder_churn_proxy") if holder_20k else None),
        "fdv_per_event_at_20k": _ratio(fdv, event_count),
        "fdv_per_buy_at_20k": _ratio(fdv, buy_count),
        "fdv_per_active_wallet_at_20k": _ratio(fdv, active),
        "valuation_growth_per_event_at_20k": _ratio(_delta_value(at_20k, prior), event_count) if at_20k and prior else None,
        "valuation_growth_per_buy_at_20k": _ratio(_delta_value(at_20k, prior), buy_count) if at_20k and prior else None,
        "funding_source_available": _bool_float(bool(funding.get("candidate_funding_wallet"))) if funding else None,
        "repeated_funder_flag": _bool_float((_float_or_none(funding.get("launches_sharing_funder")) or 0) > 1) if funding else None,
        "creator_funder_reuse_count": _float_or_none(funding.get("creator_funder_reuse_count")),
        "launches_sharing_funder": _float_or_none(funding.get("launches_sharing_funder")),
        "funding_age_seconds": _float_or_none(funding.get("funding_age_seconds")),
        "creator_prior_migration_or_graduation_count": _float_or_none(migration_row.get("creator_prior_migration_or_graduation_count")),
        "event_actor_count": _float_or_none(event_summary.get("event_actor_count")),
        "early_buyer_count_proxy": _float_or_none(event_summary.get("early_buyer_count_proxy")),
        "early_buyer_seen_in_prior_launches_count": _float_or_none(event_summary.get("early_buyer_seen_in_prior_launches_count")),
    }
    for milestone in ["20k", "100k", "500k", "1m"]:
        row[f"time_to_{milestone}_seconds"] = _age(crossings[milestone]) if crossings.get(milestone) else None
    return row


def _field_availability(
    *,
    snapshots: list[dict[str, Any]],
    holder_rows: list[dict[str, Any]],
    entity_rows: list[dict[str, Any]],
    funding_rows: list[dict[str, Any]],
    migration_rows: list[dict[str, Any]],
    event_field_availability: dict[str, dict[str, Any]],
) -> dict[str, dict[str, dict[str, Any]]]:
    return {
        "launch_identity": {
            "launch_id": _field_status(snapshots, ["launch_id"]),
            "mint": _field_status(snapshots, ["token_mint", "mint"]),
            "creator": _field_status(snapshots, ["creator", "creator_deployer"]),
            "launch_time": _field_status(snapshots, ["launch_ts"]),
            "creation_signature": event_field_availability["creation_signature"],
            "bonding_curve_or_pool_address": _field_status(holder_rows + snapshots, ["pool_address", "bonding_curve", "pool"]),
        },
        "event_wallet_data": {
            "actor_wallet": event_field_availability["actor_wallet"],
            "buyer_seller_side": event_field_availability["buyer_seller_side"],
            "token_amount": event_field_availability["token_amount"],
            "sol_amount": event_field_availability["sol_amount"],
            "event_type": event_field_availability["event_type"],
            "event_time": event_field_availability["event_time"],
            "transaction_signature": event_field_availability["transaction_signature"],
            "slot": event_field_availability["slot"],
            "instruction_index": event_field_availability["instruction_index"],
        },
        "holder_state": {
            "holder_count": _field_status(holder_rows + snapshots, ["holder_count"]),
            "holder_balances_by_wallet": _field_status(holder_rows, ["holder_balances_by_wallet", "holder_balances"]),
            "top_holder_share": _field_status(holder_rows, ["top_holder_share"]),
            "top_10_holder_share": _field_status(holder_rows, ["top_10_holder_share"]),
            "creator_holder_share": _field_status(holder_rows, ["creator_holder_share"]),
            "top_holder_addresses": _field_status(holder_rows, ["top_holder_address", "top_holder_addresses", "top_10_holder_addresses"]),
            "confidence_flags": _field_status(holder_rows, ["holder_snapshot_confidence", "holder_snapshot_missing_reason"]),
        },
        "funding_data": {
            "fee_payer": _field_status(funding_rows, ["fee_payer"]),
            "signer": _field_status(funding_rows, ["signer"]),
            "candidate_funding_wallet": _field_status(funding_rows, ["candidate_funding_wallet"]),
            "common_funder_candidate_id": _field_status(funding_rows, ["common_funder_candidate_id"]),
            "funding_age": _field_status(funding_rows, ["funding_age_seconds"]),
            "funding_amount": _field_status(funding_rows, ["funding_amount_sol", "funding_amount_token"]),
            "funding_confidence": _field_status(funding_rows, ["funding_source_confidence"]),
        },
        "entity_proxy_data": {
            "repeated_actor_overlap_proxy": _field_status(entity_rows, ["repeated_actor_overlap_proxy"]),
            "repeated_buyer_overlap_proxy": _field_status(entity_rows, ["repeated_buyer_overlap_proxy"]),
            "synchronized_participation_proxy": _field_status(entity_rows, ["synchronized_participation_proxy"]),
            "circularity_proxy": _field_status(entity_rows, ["circularity_proxy"]),
            "churn_proxy": _field_status(entity_rows, ["churn_proxy"]),
            "creator_linked_share_proxy": _field_status(entity_rows, ["creator_linked_share_proxy"]),
        },
        "milestone_outcome_data": {
            "valuation_proxy": _field_status(snapshots, ["valuation_proxy_usd", "fdv_usd"]),
            "launch_age_seconds": _field_status(snapshots, ["launch_age_seconds", "snapshot_age_seconds"]),
            "buy_count": _field_status(snapshots, ["buy_count"]),
            "sell_count": _field_status(snapshots, ["sell_count"]),
            "active_wallets": _field_status(snapshots, ["active_wallets", "unique_actors"]),
            "creator_migration_labels": _field_status(migration_rows, ["creator_prior_migration_or_graduation_count"]),
        },
    }


def _coverage_report(
    launch_rows: list[dict[str, Any]],
    snapshots: list[dict[str, Any]],
    holder_rows: list[dict[str, Any]],
    entity_rows: list[dict[str, Any]],
    funding_rows: list[dict[str, Any]],
    event_audit: dict[str, Any],
) -> dict[str, Any]:
    launch_count = len(launch_rows)
    return {
        "total_launches": launch_count,
        "snapshot_count": len(snapshots),
        "event_count": event_audit["event_count"],
        "unique_launch_dates": len({row.get("launch_date") for row in launch_rows if row.get("launch_date")}),
        "date_range": _date_range(row.get("launch_date") for row in launch_rows),
        "holder_state_launches": len({_mint(row) for row in holder_rows if _mint(row)}),
        "entity_proxy_launches": len({_mint(row) for row in entity_rows if _mint(row)}),
        "funding_link_launches": len({_mint(row) for row in funding_rows if _mint(row)}),
        "event_launches": event_audit["event_launches"],
        "holder_state_coverage_pct": _pct(len({_mint(row) for row in holder_rows if _mint(row)}), launch_count),
        "entity_proxy_coverage_pct": _pct(len({_mint(row) for row in entity_rows if _mint(row)}), launch_count),
        "funding_link_coverage_pct": _pct(len({_mint(row) for row in funding_rows if _mint(row)}), launch_count),
        "event_coverage_pct": _pct(event_audit["event_launches"], launch_count),
    }


def _feature_family_feasibility(
    availability: dict[str, dict[str, dict[str, Any]]],
    coverage: dict[str, Any],
) -> list[dict[str, Any]]:
    holder_cov = coverage["holder_state_coverage_pct"]
    entity_cov = coverage["entity_proxy_coverage_pct"]
    funding_cov = coverage["funding_link_coverage_pct"]
    event_cov = coverage["event_coverage_pct"]
    snapshot_cov = 1.0 if coverage["snapshot_count"] else 0.0
    rows = [
        _family("creator_linked_ownership", holder_cov, ["creator_holder_share", "creator_linked_share_proxy"], "entry_and_exit", holder_cov > 0, "creator_link_proxy"),
        _family("top_holder_structure", holder_cov, ["top_holder_share", "top_10_holder_share"], "entry_and_exit", holder_cov > 0, "distribution_proxy"),
        _family("top_holder_address_behavior", 0.0, ["top_holder_addresses", "per_wallet_balances"], "entry_and_exit", False, "cluster_proxy", "blocked_requires_external_fetch"),
        _family("repeated_buyer_wallet_overlap", max(entity_cov, event_cov), ["repeated_buyer_overlap_proxy", "actor_wallet"], "entry_side", max(entity_cov, event_cov) > 0, "repeated_buyer_proxy"),
        _family("wallet_quality_proxy", max(entity_cov, event_cov), ["actor_wallet", "prior_runner_participation_proxy"], "entry_side", max(entity_cov, event_cov) > 0, "wallet_structure_proxy"),
        _family("funder_lineage", funding_cov, ["candidate_funding_wallet", "common_funder_candidate_id"], "entry_side", funding_cov > 0, "funder_link_proxy"),
        _family("creator_to_wallet_relationship_proxy", max(entity_cov, funding_cov), ["creator_linked_share_proxy", "candidate_funding_wallet"], "entry_side", max(entity_cov, funding_cov) > 0, "creator_link_proxy"),
        _family("cluster_coordination_proxy", entity_cov, ["repeated_actor_overlap_proxy", "synchronized_participation_proxy", "circularity_proxy"], "entry_side", entity_cov > 0, "cluster_proxy"),
        _family("distribution_behavior", holder_cov, ["share_change_after_20k", "churn_proxy"], "exit_side", holder_cov > 0, "distribution_proxy"),
        _family("valuation_efficiency_context", snapshot_cov, ["fdv_per_event", "fdv_per_buy", "fdv_per_active_wallet"], "entry_side", snapshot_cov > 0, "wallet_structure_proxy"),
    ]
    for row in rows:
        if row["classification"] == "blocked_requires_external_fetch":
            continue
        if row["coverage_estimate"] >= 0.2:
            row["classification"] = "ready_for_anatomy_report"
        elif row["can_compute_now"]:
            row["classification"] = "partial_needs_more_data"
        else:
            row["classification"] = "blocked_requires_parser_repair"
    _attach_blockers(rows, availability)
    return rows


def _family(
    name: str,
    coverage: float,
    required: list[str],
    side: str,
    can_compute: bool,
    neutral_label: str,
    classification: str = "partial_needs_more_data",
) -> dict[str, Any]:
    return {
        "feature_family": name,
        "neutral_label": neutral_label,
        "can_compute_now": can_compute,
        "required_input_fields": ";".join(required),
        "coverage_estimate": coverage,
        "expected_sample_size": None,
        "available_scope": "expanded_subset" if coverage and coverage < 0.95 else "all_expanded_launches",
        "pre_trigger_safe": side in {"entry_side", "entry_and_exit"},
        "uses_post_trigger_behavior": side in {"exit_side", "entry_and_exit"},
        "usable_for_entry_side_research": side in {"entry_side", "entry_and_exit"},
        "usable_for_exit_side_research": side in {"exit_side", "entry_and_exit"},
        "classification": classification,
        "missing_blockers": "",
    }


def _attach_blockers(rows: list[dict[str, Any]], availability: dict[str, dict[str, dict[str, Any]]]) -> None:
    holder_address_status = availability["holder_state"]["top_holder_addresses"]["status"]
    for row in rows:
        blockers = []
        if row["classification"].startswith("blocked"):
            blockers.append("required_address_or_graph_fields_missing")
        if row["feature_family"] == "top_holder_address_behavior" and holder_address_status != "available_now":
            blockers.append("top_holder_addresses_unavailable")
        if row["feature_family"] == "funder_lineage" and row["coverage_estimate"] < 0.2:
            blockers.append("funding_link_pilot_partial_coverage")
        row["missing_blockers"] = ";".join(blockers)


def _tier_summary(launch_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    output = {}
    for tier in TIER_ORDER:
        rows = [row for row in launch_rows if row["milestone_tier"] == tier]
        dates = Counter(row.get("launch_date") for row in rows if row.get("launch_date"))
        creators = Counter(row.get("creator") or "unknown" for row in rows)
        output[tier] = {
            "launch_count": len(rows),
            "unique_date_count": len(dates),
            "unique_creator_count": len(creators),
            "top_date_concentration": _top_share(dates, len(rows), 1),
            "top_creator_concentration": _top_share(creators, len(rows), 1),
        }
    return output


def _tier_comparison(launch_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for tier in TIER_ORDER:
        members = [row for row in launch_rows if row["milestone_tier"] == tier]
        for feature in FEATURE_ROWS:
            values = [_float_or_none(row.get(feature)) for row in members]
            numeric = [value for value in values if value is not None]
            rows.append(
                {
                    "comparison_group": "milestone_tier",
                    "milestone_tier": tier,
                    "feature": feature,
                    **_distribution(numeric),
                    "missing_count": len(members) - len(numeric),
                    "coverage_pct": _pct(len(numeric), len(members)),
                }
            )
    for label, positive_tiers in {
        "100k_plus_vs_sub_100k": {"reached_100k_but_never_200k", "reached_200k_but_never_500k", "reached_500k_but_never_1m", "reached_1m_plus"},
        "500k_plus_vs_sub_500k": {"reached_500k_but_never_1m", "reached_1m_plus"},
        "1m_plus_vs_sub_1m": {"reached_1m_plus"},
        "500k_1m_vs_100k_only": {"reached_500k_but_never_1m", "reached_1m_plus"},
    }.items():
        positives = [row for row in launch_rows if row["milestone_tier"] in positive_tiers]
        if label == "500k_1m_vs_100k_only":
            negatives = [row for row in launch_rows if row["milestone_tier"] == "reached_100k_but_never_200k"]
        else:
            negatives = [row for row in launch_rows if row["milestone_tier"] not in positive_tiers]
        for feature in FEATURE_ROWS:
            pos = [_float_or_none(row.get(feature)) for row in positives]
            neg = [_float_or_none(row.get(feature)) for row in negatives]
            pos_vals = [value for value in pos if value is not None]
            neg_vals = [value for value in neg if value is not None]
            pos_med = median(pos_vals) if pos_vals else None
            neg_med = median(neg_vals) if neg_vals else None
            rows.append(
                {
                    "comparison_group": label,
                    "milestone_tier": "comparison",
                    "feature": feature,
                    "positive_sample_count": len(pos_vals),
                    "negative_sample_count": len(neg_vals),
                    "positive_median": pos_med,
                    "negative_median": neg_med,
                    "median_difference": pos_med - neg_med if pos_med is not None and neg_med is not None else None,
                    "direction": _direction(pos_med, neg_med),
                    "classification": _difference_classification(pos_med, neg_med, len(pos_vals), len(neg_vals)),
                }
            )
    return rows


def _entry_exit_feature_rows(feasibility_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    family_by_feature = {
        "creator_holder_share_at_20k": "creator_linked_ownership",
        "top_holder_share_at_20k": "top_holder_structure",
        "top_10_holder_share_at_20k": "top_holder_structure",
        "repeated_buyer_overlap_proxy": "repeated_buyer_wallet_overlap",
        "fdv_per_event_at_20k": "valuation_efficiency_context",
        "fdv_per_buy_at_20k": "valuation_efficiency_context",
        "fdv_per_active_wallet_at_20k": "valuation_efficiency_context",
        "funding_source_available": "funder_lineage",
        "creator_holder_share_drop_after_20k": "creator_linked_ownership",
        "top_holder_share_drop_after_20k": "top_holder_structure",
        "top_10_holder_share_drop_after_20k": "top_holder_structure",
        "creator_sell_count_after_20k": "creator_linked_ownership",
        "sell_pressure_from_early_buyers_after_20k": "repeated_buyer_wallet_overlap",
        "distribution_before_drawdown_proxy": "distribution_behavior",
    }
    feasibility = {row["feature_family"]: row for row in feasibility_rows}
    rows = []
    for feature in sorted(ENTRY_SIDE_FEATURES | EXIT_SIDE_FEATURES):
        family = family_by_feature.get(feature, "wallet_quality_proxy")
        family_row = feasibility.get(family, {})
        rows.append(
            {
                "feature_name": feature,
                "feature_family": family,
                "feature_side": "entry_side" if feature in ENTRY_SIDE_FEATURES else "exit_side",
                "available_now": family_row.get("can_compute_now", False),
                "classification": family_row.get("classification", "partial_needs_more_data"),
                "notes": "descriptive candidate only; no rule or trading claim",
            }
        )
    return rows


def _data_gap_plan(
    availability: dict[str, dict[str, dict[str, Any]]],
    feasibility_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "missing_feature": "top_holder_addresses",
            "why_it_matters": "Needed to test whether early top holders recur across runner tiers.",
            "current_proxy": "top_holder_share and top_10_holder_share only",
            "source_needed": "holder address snapshots or replayed per-wallet holder balances",
            "estimated_cost": "medium",
            "implementation_complexity": "medium",
            "expected_value": "high",
            "priority": 1,
            "current_status": availability["holder_state"]["top_holder_addresses"]["status"],
        },
        {
            "missing_feature": "complete_creator_funder_graph",
            "why_it_matters": "Needed to link launches through repeated funding sources beyond the current pilot subset.",
            "current_proxy": "funding_link_pilot candidate_funding_wallet",
            "source_needed": "bounded pre-launch funding enrichment over expanded creators",
            "estimated_cost": "medium",
            "implementation_complexity": "medium",
            "expected_value": "high",
            "priority": 2,
            "current_status": "partially_available",
        },
        {
            "missing_feature": "bundle_or_execution_group_ids",
            "why_it_matters": "Could separate synchronized participation from ordinary repeated participation.",
            "current_proxy": "synchronized_participation_proxy",
            "source_needed": "transaction metadata enrichment with bundle or execution grouping if available",
            "estimated_cost": "unknown",
            "implementation_complexity": "high",
            "expected_value": "medium",
            "priority": 3,
            "current_status": "requires_external_fetch",
        },
        {
            "missing_feature": "per_wallet_realized_behavior_after_trigger",
            "why_it_matters": "Needed for exit-side distribution and churn anatomy after milestone crossings.",
            "current_proxy": "churn_proxy and observed holder share changes",
            "source_needed": "per-wallet event replay keyed to milestone crossing time",
            "estimated_cost": "low_to_medium",
            "implementation_complexity": "medium",
            "expected_value": "medium",
            "priority": 4,
            "current_status": "partially_available",
        },
    ]


def _strongest_commonalities(tier_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    comparisons = [
        row for row in tier_rows
        if row.get("comparison_group") in {"100k_plus_vs_sub_100k", "500k_plus_vs_sub_500k", "1m_plus_vs_sub_1m", "500k_1m_vs_100k_only"}
        and row.get("classification") not in {None, "data_limited", "no_clear_difference"}
    ]
    comparisons.sort(key=lambda row: abs(_float_or_none(row.get("median_difference")) or 0), reverse=True)
    return comparisons[:10]


def _recommended_next_reports(
    feasibility_rows: list[dict[str, Any]],
    data_gap_rows: list[dict[str, Any]],
    commonalities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    ready = {row["feature_family"]: row for row in feasibility_rows if row["classification"] == "ready_for_anatomy_report"}
    recommendations = []
    if "repeated_buyer_wallet_overlap" in ready:
        recommendations.append(
            {
                "name": "Repeated Buyer Runner Participation Descriptive Report",
                "feature_family": "repeated_buyer_wallet_overlap",
                "entry_or_exit_side": "entry_side",
                "data_readiness": ready["repeated_buyer_wallet_overlap"]["classification"],
                "expected_value": "high",
                "blocker": "needs robustness review before any thesis",
                "next_step": "formal descriptive report with frozen proxy definitions",
            }
        )
    if "funder_lineage" in {row["feature_family"]: row for row in feasibility_rows if row["can_compute_now"]}:
        recommendations.append(
            {
                "name": "Funder Link Proxy Expansion Sprint",
                "feature_family": "funder_lineage",
                "entry_or_exit_side": "entry_side",
                "data_readiness": "partial_needs_more_data",
                "expected_value": "high",
                "blocker": "pilot coverage is partial",
                "next_step": "scale bounded funding-link enrichment before thesis work",
            }
        )
    recommendations.append(
        {
            "name": "Structural Runner Fingerprint Report With Visible And Hidden Layers",
            "feature_family": "valuation_efficiency_context_plus_cluster_proxy",
            "entry_or_exit_side": "entry_side",
            "data_readiness": "ready_for_anatomy_report" if commonalities else "partial_needs_more_data",
            "expected_value": "high",
            "blocker": "descriptive only until robustness design is frozen",
            "next_step": "combine valuation efficiency with available structural proxies",
        }
    )
    if data_gap_rows:
        recommendations.append(
            {
                "name": "Full Holder Address Enrichment Sprint",
                "feature_family": "top_holder_address_behavior",
                "entry_or_exit_side": "entry_and_exit",
                "data_readiness": "blocked_requires_external_fetch",
                "expected_value": data_gap_rows[0]["expected_value"],
                "blocker": data_gap_rows[0]["missing_feature"],
                "next_step": "design bounded holder-address acquisition plan",
            }
        )
    return recommendations[:3]


def _structural_questions(commonalities: list[dict[str, Any]], feasibility_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_family = {row["feature_family"]: row for row in feasibility_rows}
    return [
        {"question": "Do explosive runners share creator-linked ownership patterns?", "answer": _answer_for_family(by_family, "creator_linked_ownership")},
        {"question": "Do explosive runners share top-holder concentration patterns?", "answer": _answer_for_family(by_family, "top_holder_structure")},
        {"question": "Do explosive runners involve repeated early buyer wallets?", "answer": _answer_for_family(by_family, "repeated_buyer_wallet_overlap")},
        {"question": "Do repeated funders appear in explosive runners?", "answer": _answer_for_family(by_family, "funder_lineage")},
        {"question": "Does hidden structure explain valuation efficiency?", "answer": "partially_observable_descriptive_candidate" if commonalities else "not_proven"},
    ]


def _answer_for_family(by_family: dict[str, dict[str, Any]], family: str) -> str:
    row = by_family.get(family, {})
    if row.get("classification") == "ready_for_anatomy_report":
        return "observable_as_proxy"
    if row.get("can_compute_now"):
        return "partially_observable_as_proxy"
    return "blocked_with_current_data"


def _readiness(feasibility_rows: list[dict[str, Any]], commonalities: list[dict[str, Any]]) -> str:
    ready_count = sum(1 for row in feasibility_rows if row["classification"] == "ready_for_anatomy_report")
    if ready_count >= 3 and commonalities:
        return "structural_wallet_report_ready_for_next_thesis"
    if ready_count >= 1:
        return "structural_wallet_report_needs_enrichment"
    return "structural_wallet_report_blocked"


def _limitations(coverage: dict[str, Any]) -> list[str]:
    return [
        "This is a descriptive discovery report, not a thesis or validation result.",
        "All valuation language uses FDV proxy, not true market capitalization.",
        "Holder-state rows are observed delta replay when present, not confirmed full-chain snapshots.",
        "Funding-link data is partial pilot data unless coverage reaches the expanded cohort.",
        "Address-level top-holder and complete graph features remain blocked when address lists are unavailable.",
        f"Funding-link coverage is {coverage['funding_link_coverage_pct']:.4f}.",
    ]


def _next_action(readiness: str, recommendations: list[dict[str, Any]]) -> str:
    if readiness == "structural_wallet_report_ready_for_next_thesis" and recommendations:
        return recommendations[0]["next_step"]
    if readiness == "structural_wallet_report_needs_enrichment":
        return "complete the highest-priority structural data gap before formal thesis work"
    return "repair or enrich structural input data before rerunning this report"


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Structural Wallet Anatomy Report",
        "",
        f"Readiness: `{report['readiness_classification']}`",
        "",
        "This is a descriptive discovery report only. It does not create trading rules or promote a thesis.",
        "",
        "## Dataset",
        f"- Launches analyzed: {report['coverage_report']['total_launches']}",
        f"- Snapshots: {report['coverage_report']['snapshot_count']}",
        f"- Events loaded: {report['coverage_report']['event_count']}",
        f"- True market-cap claims: {report['dataset']['true_market_cap_claims']}",
        "",
        "## Milestone Tiers",
    ]
    for tier, row in report["milestone_tier_summary"].items():
        lines.append(f"- {tier}: {row['launch_count']} launches")
    lines.extend(["", "## Computable Structural Families"])
    for row in report["feature_family_feasibility"]:
        lines.append(f"- {row['feature_family']}: {row['classification']} ({row['neutral_label']})")
    lines.extend(["", "## Strongest Hidden Structural Commonalities"])
    if report["strongest_hidden_structural_commonalities"]:
        for row in report["strongest_hidden_structural_commonalities"][:8]:
            lines.append(
                f"- {row['comparison_group']} / {row['feature']}: {row['direction']} "
                f"({row['classification']})"
            )
    else:
        lines.append("- No robust descriptive structural commonality cleared the sample/coverage filters.")
    lines.extend(["", "## Recommended Next Work"])
    for row in report["recommended_next_reports_or_theses"]:
        lines.append(f"- {row['name']}: {row['next_step']}")
    lines.extend(["", "## Limitations"])
    for item in report["limitations"]:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def _availability_markdown(report: dict[str, Any]) -> str:
    lines = ["# Structural Wallet Data Availability", ""]
    for group, fields in report["field_availability"].items():
        lines.append(f"## {group}")
        for name, detail in fields.items():
            lines.append(f"- {name}: {detail['status']} ({detail['coverage_pct']:.4f})")
        lines.append("")
    return "\n".join(lines)


def _status_markdown(
    report: dict[str, Any],
    json_path: Path,
    md_path: Path,
    availability_md: Path,
    feasibility_csv: Path,
    tier_csv: Path,
    entry_exit_csv: Path,
    gap_csv: Path,
) -> str:
    return "\n".join(
        [
            "# Structural Wallet Anatomy Report Status",
            "",
            "## Why This Report Was Created",
            "The previous winner anatomy report found visible valuation-efficiency separation. This report checks whether hidden wallet/dev/cluster proxy structure is observable before explosive FDV-proxy milestones.",
            "",
            f"Readiness classification: `{report['readiness_classification']}`",
            "",
            "## Data Availability Summary",
            f"- Launches analyzed: {report['coverage_report']['total_launches']}",
            f"- Holder-state coverage: {report['coverage_report']['holder_state_coverage_pct']:.4f}",
            f"- Entity-proxy coverage: {report['coverage_report']['entity_proxy_coverage_pct']:.4f}",
            f"- Funding-link coverage: {report['coverage_report']['funding_link_coverage_pct']:.4f}",
            f"- Event coverage: {report['coverage_report']['event_coverage_pct']:.4f}",
            "",
            "## Structural Feature Families",
            *[f"- {row['feature_family']}: {row['classification']}" for row in report["feature_family_feasibility"]],
            "",
            "## What Is Blocked",
            *[f"- {row['missing_feature']}: {row['source_needed']}" for row in report["data_gap_plan"]],
            "",
            "## Entry-Side Candidate Features",
            *[f"- {row['feature_name']}" for row in report["entry_exit_feature_separation"] if row["feature_side"] == "entry_side" and row["available_now"]],
            "",
            "## Exit-Side Candidate Features",
            *[f"- {row['feature_name']}" for row in report["entry_exit_feature_separation"] if row["feature_side"] == "exit_side"],
            "",
            "## Recommended Next Reports/Theses",
            *[f"- {row['name']}: {row['next_step']}" for row in report["recommended_next_reports_or_theses"]],
            "",
            "## Limitations",
            *[f"- {item}" for item in report["limitations"]],
            "",
            "## Artifacts",
            f"- Summary JSON: {json_path}",
            f"- Summary Markdown: {md_path}",
            f"- Availability Markdown: {availability_md}",
            f"- Feasibility CSV: {feasibility_csv}",
            f"- Tier comparison CSV: {tier_csv}",
            f"- Entry/exit CSV: {entry_exit_csv}",
            f"- Gap plan CSV: {gap_csv}",
            "",
            f"Next action: {report['next_action']}",
            "",
        ]
    )


def _first_crossing(rows: list[dict[str, Any]], threshold: float) -> dict[str, Any] | None:
    for row in rows:
        if (_value(row) or 0) >= threshold:
            return row
    return None


def _snapshot_before(rows: list[dict[str, Any]], age: int) -> dict[str, Any] | None:
    eligible = [row for row in rows if _age(row) <= age]
    if not eligible:
        return None
    selected = max(eligible, key=_age)
    prior_candidates = [row for row in rows if _age(row) < _age(selected)]
    if prior_candidates:
        selected = dict(selected)
        selected["_prior_snapshot"] = max(prior_candidates, key=_age)
    return selected


def _highest_tier(crossings: dict[str, dict[str, Any] | None]) -> str:
    if crossings.get("1m"):
        return "reached_1m_plus"
    if crossings.get("500k"):
        return "reached_500k_but_never_1m"
    if crossings.get("200k"):
        return "reached_200k_but_never_500k"
    if crossings.get("100k"):
        return "reached_100k_but_never_200k"
    if crossings.get("50k"):
        return "reached_50k_but_never_100k"
    if crossings.get("20k"):
        return "reached_20k_but_never_50k"
    return "never_reached_20k"


def _field_status(rows: list[dict[str, Any]], keys: list[str]) -> dict[str, Any]:
    total = len(rows)
    present = sum(1 for row in rows if any(row.get(key) not in (None, "") for key in keys))
    if present == total and total:
        status = "available_now"
    elif present:
        status = "partially_available"
    else:
        status = "unavailable"
    return {"status": status, "rows_available": present, "rows_total": total, "coverage_pct": _pct(present, total)}


def _nested_field_status(rows: list[dict[str, Any]], parent: str, keys: list[str]) -> dict[str, Any]:
    total = len(rows)
    present = 0
    for row in rows:
        nested = row.get(parent) or {}
        if any(row.get(key) not in (None, "") or nested.get(key) not in (None, "") for key in keys):
            present += 1
    if present == total and total:
        status = "available_now"
    elif present:
        status = "partially_available"
    else:
        status = "unavailable"
    return {"status": status, "rows_available": present, "rows_total": total, "coverage_pct": _pct(present, total)}


def _stream_event_audit(paths: list[Path | str], snapshots_by_mint: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    total = 0
    mints_seen: set[str] = set()
    field_counts = Counter()
    actors_by_mint: dict[str, set[str]] = defaultdict(set)
    early_buyers_by_mint: dict[str, set[str]] = defaultdict(set)
    launch_ts_by_mint = {
        mint: _int_or_none(_first_present(*(row.get("launch_ts") for row in rows)))
        for mint, rows in snapshots_by_mint.items()
    }
    for path in paths:
        value = Path(path)
        if not value.exists():
            continue
        with value.open("r", encoding="utf-8") as f:
            for line in f:
                text = line.strip()
                if not text:
                    continue
                try:
                    row = json.loads(text)
                except json.JSONDecodeError:
                    continue
                total += 1
                mint = _mint(row)
                if mint:
                    mints_seen.add(mint)
                _count_event_fields(row, field_counts)
                actor = row.get("actor")
                if not mint or not actor:
                    continue
                actor_text = str(actor)
                actors_by_mint[mint].add(actor_text)
                launch_ts = launch_ts_by_mint.get(mint)
                age = _event_age(row, launch_ts)
                side = str(row.get("side") or row.get("event_type") or "").lower()
                if age is not None and age <= 1_200 and side in {"buy", "accumulate", "token_accumulation"}:
                    early_buyers_by_mint[mint].add(actor_text)
    seen_actors: set[str] = set()
    summaries: dict[str, dict[str, float]] = {}
    for mint, launch_ts in sorted(launch_ts_by_mint.items(), key=lambda item: item[1] or 0):
        actors = actors_by_mint.get(mint, set())
        early_buyers = early_buyers_by_mint.get(mint, set())
        summaries[mint] = {
            "event_actor_count": float(len(actors)),
            "early_buyer_count_proxy": float(len(early_buyers)),
            "early_buyer_seen_in_prior_launches_count": float(len(early_buyers & seen_actors)),
        }
        seen_actors.update(actors)
    return {
        "event_count": total,
        "event_launches": len(mints_seen),
        "event_summaries": summaries,
        "field_availability": {
            "creation_signature": _status_from_counts(field_counts["creation_signature"], total),
            "actor_wallet": _status_from_counts(field_counts["actor_wallet"], total),
            "buyer_seller_side": _status_from_counts(field_counts["buyer_seller_side"], total),
            "token_amount": _status_from_counts(field_counts["token_amount"], total),
            "sol_amount": _status_from_counts(field_counts["sol_amount"], total),
            "event_type": _status_from_counts(field_counts["event_type"], total),
            "event_time": _status_from_counts(field_counts["event_time"], total),
            "transaction_signature": _status_from_counts(field_counts["transaction_signature"], total),
            "slot": _status_from_counts(field_counts["slot"], total),
            "instruction_index": _status_from_counts(field_counts["instruction_index"], total),
        },
    }


def _count_event_fields(row: dict[str, Any], counts: Counter) -> None:
    metadata = row.get("metadata_json") or {}
    raw_metadata = metadata.get("raw_record_metadata_json") or {}
    checks = {
        "creation_signature": row.get("source_signature") or metadata.get("source_signature") or raw_metadata.get("creation_signature"),
        "actor_wallet": row.get("actor"),
        "buyer_seller_side": row.get("side") or row.get("event_type"),
        "token_amount": row.get("base_qty") or row.get("token_amount"),
        "sol_amount": row.get("quote_qty") or row.get("sol_amount"),
        "event_type": row.get("event_type") or row.get("venue"),
        "event_time": row.get("block_time"),
        "transaction_signature": row.get("signature"),
        "slot": row.get("slot"),
        "instruction_index": row.get("instruction_index"),
    }
    for name, value in checks.items():
        if value not in (None, ""):
            counts[name] += 1


def _status_from_counts(present: int, total: int) -> dict[str, Any]:
    if present == total and total:
        status = "available_now"
    elif present:
        status = "partially_available"
    else:
        status = "unavailable"
    return {"status": status, "rows_available": present, "rows_total": total, "coverage_pct": _pct(present, total)}


def _read_many_jsonl(paths: list[Path | str]) -> list[dict[str, Any]]:
    rows = []
    for path in paths:
        rows.extend(_read_jsonl(path))
    return rows


def _read_table(path: Path | str | None) -> list[dict[str, Any]]:
    if not path:
        return []
    value = Path(path)
    if not value.exists():
        return []
    if value.suffix == ".parquet":
        import pandas as pd

        return pd.read_parquet(value).to_dict(orient="records")
    return _read_jsonl(value)


def _read_jsonl(path: Path | str | None) -> list[dict[str, Any]]:
    if not path:
        return []
    value = Path(path)
    if not value.exists():
        return []
    rows = []
    with value.open("r", encoding="utf-8") as f:
        for line in f:
            text = line.strip()
            if text:
                rows.append(json.loads(text))
    return rows


def _write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    keys = sorted({key for row in rows for key in row}) or ["empty"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def _group_by_mint(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        mint = _mint(row)
        if mint:
            grouped[mint].append(row)
    return dict(grouped)


def _event_actor_summaries(
    events_by_mint: dict[str, list[dict[str, Any]]],
    snapshots_by_mint: dict[str, list[dict[str, Any]]],
) -> dict[str, dict[str, float]]:
    launch_ts_by_mint = {
        mint: _int_or_none(_first_present(*(row.get("launch_ts") for row in rows)))
        for mint, rows in snapshots_by_mint.items()
    }
    seen_actors: set[str] = set()
    output: dict[str, dict[str, float]] = {}
    for mint, launch_ts in sorted(launch_ts_by_mint.items(), key=lambda item: item[1] or 0):
        mint_events = events_by_mint.get(mint, [])
        actors = {str(row.get("actor")) for row in mint_events if row.get("actor")}
        early_buyers = {
            str(row.get("actor"))
            for row in mint_events
            if row.get("actor")
            and _event_age(row, launch_ts) is not None
            and (_event_age(row, launch_ts) or 0) <= 1_200
            and str(row.get("side") or row.get("event_type") or "").lower() in {"buy", "accumulate", "token_accumulation"}
        }
        output[mint] = {
            "event_actor_count": float(len(actors)),
            "early_buyer_count_proxy": float(len(early_buyers)),
            "early_buyer_seen_in_prior_launches_count": float(len(early_buyers & seen_actors)),
        }
        for row in events_by_mint.get(mint, []):
            if row.get("actor"):
                seen_actors.add(str(row["actor"]))
    return output


def _nearest_holder(rows: list[dict[str, Any]], age: int) -> dict[str, Any] | None:
    return min(rows, key=lambda row: abs(_age(row) - age)) if rows else None


def _holder_delta(newer: dict[str, Any] | None, older: dict[str, Any] | None, field: str) -> float | None:
    if not newer or not older:
        return None
    return _delta(newer, older, field)


def _distribution(values: list[float | None]) -> dict[str, Any]:
    vals = sorted(value for value in values if value is not None)
    if not vals:
        return {"sample_count": 0, "median": None, "iqr": None, "p10": None, "p90": None}
    return {
        "sample_count": len(vals),
        "median": median(vals),
        "iqr": [vals[len(vals) // 4], vals[(len(vals) * 3) // 4]],
        "p10": vals[int((len(vals) - 1) * 0.1)],
        "p90": vals[int((len(vals) - 1) * 0.9)],
    }


def _difference_classification(pos_med: float | None, neg_med: float | None, pos_count: int, neg_count: int) -> str:
    if pos_count < 30 or neg_count < 30 or pos_med is None or neg_med is None:
        return "data_limited"
    base = abs(neg_med) if abs(neg_med) > 1e-9 else 1.0
    rel = abs(pos_med - neg_med) / base
    if rel >= 1.0:
        return "strong_descriptive_difference"
    if rel >= 0.35:
        return "moderate_descriptive_difference"
    if rel >= 0.1:
        return "weak_descriptive_difference"
    return "no_clear_difference"


def _direction(pos_med: float | None, neg_med: float | None) -> str | None:
    if pos_med is None or neg_med is None:
        return None
    if pos_med > neg_med:
        return "higher"
    if pos_med < neg_med:
        return "lower"
    return "same"


def _event_age(row: dict[str, Any], launch_ts: int | None) -> int | None:
    block_time = _int_or_none(row.get("block_time"))
    if block_time is None or launch_ts is None:
        return None
    return block_time - launch_ts


def _event_count(row: dict[str, Any] | None) -> float | None:
    if not row:
        return None
    return _first_float(row.get("event_count"), row.get("tx_count"), (row.get("metadata_json") or {}).get("event_count"))


def _value(row: dict[str, Any] | None) -> float | None:
    if not row:
        return None
    return _first_float(row.get("valuation_proxy_usd"), row.get("fdv_usd"))


def _age(row: dict[str, Any] | None) -> int:
    if not row:
        return 0
    return _int_or_none(row.get("launch_age_seconds") or row.get("snapshot_age_seconds")) or 0


def _mint(row: dict[str, Any]) -> str | None:
    value = row.get("token_mint") or row.get("mint")
    return str(value) if value else None


def _launch_date(ts: int | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()


def _date_range(values: Any) -> dict[str, str | None]:
    dates = sorted(value for value in values if value)
    return {"start": dates[0] if dates else None, "end": dates[-1] if dates else None}


def _top_share(counter: Counter, total: int, n: int) -> float:
    if not total:
        return 0.0
    return sum(count for _, count in counter.most_common(n)) / total


def _first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _first_float(*values: Any) -> float | None:
    for value in values:
        parsed = _float_or_none(value)
        if parsed is not None:
            return parsed
    return None


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _delta(row: dict[str, Any], prior: dict[str, Any], field: str) -> float | None:
    a = _float_or_none(row.get(field))
    b = _float_or_none(prior.get(field))
    if a is None or b is None:
        return None
    return a - b


def _delta_value(row: dict[str, Any] | None, prior: dict[str, Any] | None) -> float | None:
    a = _value(row)
    b = _value(prior)
    if a is None or b is None:
        return None
    return a - b


def _ratio(a: Any, b: Any) -> float | None:
    num = _float_or_none(a)
    den = _float_or_none(b)
    if num is None or den in (None, 0):
        return None
    return num / den


def _pct(num: int, den: int) -> float:
    return num / den if den else 0.0


def _bool_float(value: bool) -> float:
    return 1.0 if value else 0.0
