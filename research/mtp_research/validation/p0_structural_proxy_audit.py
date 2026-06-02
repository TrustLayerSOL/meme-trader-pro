"""Combined P0 structural proxy audit for completed enrichment pilots."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from research.mtp_research.data_paths import data_lake_path


REPORT_ID = "p0_structural_proxy_audit_v0"
READINESS_READY = "p0_structural_layer_ready_for_fingerprint_report"
READINESS_SCALE = "p0_structural_layer_needs_scaleup"
READINESS_REPAIR = "p0_structural_layer_needs_repair"
READINESS_BLOCKED = "p0_structural_layer_blocked"

DEFAULT_UNIVERSE_PATH = data_lake_path(
    "data",
    "backtests",
    "diagnostics",
    "reports",
    "repeated_buyer_runner_participation",
    "repeated_buyer_runner_participation_summary.json",
)
DEFAULT_EARLY_BUYER_PATH = data_lake_path(
    "data",
    "backtests",
    "structural_enrichment",
    "early_buyer_wallet_history_pilot.jsonl",
)
DEFAULT_TOP_HOLDER_PATH = data_lake_path(
    "data",
    "backtests",
    "structural_enrichment",
    "top_holder_replay_pilot.jsonl",
)
DEFAULT_CREATOR_FUNDER_PATH = data_lake_path(
    "data",
    "backtests",
    "structural_enrichment",
    "creator_funder_transfer_graph_pilot.jsonl",
)
DEFAULT_AXIOM_PARITY_PATH = data_lake_path(
    "data",
    "backtests",
    "diagnostics",
    "reports",
    "axiom_historical_parity",
    "axiom_historical_parity_summary.json",
)
DEFAULT_OUTPUT_DIR = data_lake_path(
    "data",
    "backtests",
    "diagnostics",
    "reports",
    "p0_structural_proxy_audit",
)
DEFAULT_STATUS_PATH = Path("theses/P0_STRUCTURAL_PROXY_AUDIT_STATUS.md")

MILESTONE_TIERS = [
    "never_reached_20k",
    "reached_20k_but_never_50k",
    "reached_50k_but_never_100k",
    "reached_100k_but_never_200k",
    "reached_200k_but_never_500k",
    "reached_500k_but_never_1m",
    "reached_1m_plus",
]
TIER_RANK = {tier: idx for idx, tier in enumerate(MILESTONE_TIERS)}


def build_p0_structural_proxy_audit(
    *,
    universe_path: Path | str = DEFAULT_UNIVERSE_PATH,
    early_buyer_path: Path | str = DEFAULT_EARLY_BUYER_PATH,
    top_holder_path: Path | str = DEFAULT_TOP_HOLDER_PATH,
    creator_funder_path: Path | str = DEFAULT_CREATOR_FUNDER_PATH,
    axiom_parity_path: Path | str = DEFAULT_AXIOM_PARITY_PATH,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    status_path: Path | str = DEFAULT_STATUS_PATH,
) -> tuple[dict[str, Any], dict[str, Path]]:
    universe_rows = _load_universe_rows(universe_path)
    early_rows = _read_records(early_buyer_path)
    top_rows = _read_records(top_holder_path)
    funder_rows = _read_records(creator_funder_path)
    axiom_summary = _read_json(axiom_parity_path) if Path(axiom_parity_path).exists() else {}

    early_by_launch = _summarize_early_buyers(early_rows)
    top_by_launch = _summarize_top_holders(top_rows)
    funder_by_launch = _summarize_funders(funder_rows)
    joined_rows = _joined_rows(universe_rows, early_by_launch, top_by_launch, funder_by_launch)
    coverage_by_tier = _coverage_by_tier(universe_rows, joined_rows)
    overlap = _overlap_audit(joined_rows)
    readiness_by_family = _structural_proxy_readiness(joined_rows, overlap)
    readiness = _overall_readiness(readiness_by_family, overlap)
    scaleup = _scaleup_recommendation(readiness, overlap, len(universe_rows))
    tier_context = _tier_context(joined_rows)
    report = {
        "report_id": REPORT_ID,
        "report_type": "combined_p0_structural_proxy_audit",
        "readiness_classification": readiness,
        "methodology_flags": [
            "research_only",
            "offline_consolidation_only",
            "no_helius_calls",
            "no_network_calls",
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
            "no_threshold_optimization",
            "no_grid_search",
            "no_ml_black_boxes",
            "neutral_proxy_labels_only",
            "fdv_proxy_not_true_market_cap",
        ],
        "input_paths": {
            "universe_path": str(universe_path),
            "early_buyer_path": str(early_buyer_path),
            "top_holder_path": str(top_holder_path),
            "creator_funder_path": str(creator_funder_path),
            "axiom_parity_path": str(axiom_parity_path),
        },
        "pilot_input_counts": {
            "universe_launches": len(universe_rows),
            "early_buyer_rows": len(early_rows),
            "top_holder_rows": len(top_rows),
            "creator_funder_rows": len(funder_rows),
        },
        "launch_coverage": _launch_coverage(joined_rows),
        "coverage_by_tier": coverage_by_tier,
        "overlap_audit": overlap,
        "structural_proxy_readiness": readiness_by_family,
        "tier_descriptive_context": tier_context,
        "scaleup_recommendation": scaleup,
        "axiom_parity_context": _axiom_context(axiom_summary),
        "joined_preview_rows": joined_rows[:250],
        "limitations": [
            "P0 pilot datasets are deliberately bounded and should not be generalized without scale-up.",
            "Top-holder replay is observed mint transaction balance-delta replay, not confirmed full-chain historical account state.",
            "Creator/funder graph fields are structural proxies, not identity labels.",
            "This audit does not compare structural fields to outcomes as a thesis.",
            "True market-cap claims remain blocked; only FDV/valuation proxy labels are allowed.",
        ],
    }
    outputs = write_p0_structural_proxy_audit_outputs(report, output_dir=output_dir, status_path=status_path)
    return report, outputs


def write_p0_structural_proxy_audit_outputs(
    report: dict[str, Any],
    *,
    output_dir: Path | str,
    status_path: Path | str,
) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    summary_json = output / "p0_structural_proxy_audit_summary.json"
    summary_md = output / "p0_structural_proxy_audit_summary.md"
    coverage_csv = output / "p0_structural_proxy_coverage_by_tier.csv"
    overlap_csv = output / "p0_structural_proxy_overlap.csv"
    preview_csv = output / "p0_structural_proxy_joined_preview.csv"
    scale_csv = output / "p0_structural_scaleup_recommendation.csv"
    status = Path(status_path)

    summary_json.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    summary_md.write_text(_markdown(report), encoding="utf-8")
    _write_csv(report["coverage_by_tier"], coverage_csv)
    _write_csv([report["overlap_audit"]], overlap_csv)
    _write_csv(report["joined_preview_rows"], preview_csv)
    _write_csv(report["scaleup_recommendation"]["options"], scale_csv)
    status.parent.mkdir(parents=True, exist_ok=True)
    status.write_text(_status_markdown(report, summary_json, summary_md, coverage_csv, overlap_csv, preview_csv, scale_csv), encoding="utf-8")
    return {
        "summary_json_path": summary_json,
        "summary_markdown_path": summary_md,
        "coverage_by_tier_csv_path": coverage_csv,
        "overlap_csv_path": overlap_csv,
        "joined_preview_csv_path": preview_csv,
        "scaleup_recommendation_csv_path": scale_csv,
        "status_path": status,
    }


def _load_universe_rows(path: Path | str) -> list[dict[str, Any]]:
    obj = _read_json(path)
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        rows = obj.get("launch_feature_rows")
        if isinstance(rows, list):
            return rows
    return []


def _summarize_early_buyers(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        launch_id = row.get("current_launch_id") or row.get("launch_id")
        if launch_id:
            grouped[launch_id].append(row)
    out = {}
    for launch_id, items in grouped.items():
        with_history = [row for row in items if (_num(row.get("prior_transaction_count")) or 0) > 0 or row.get("history_missing_reason") is None]
        out[launch_id] = {
            "mint": _first_value(items, "current_mint") or _first_value(items, "mint"),
            "milestone_tier": _first_value(items, "current_milestone_tier") or _first_value(items, "milestone_tier"),
            "early_buyer_wallet_count": len({row.get("wallet") for row in items if row.get("wallet")}),
            "early_buyer_with_prior_history_count": len({row.get("wallet") for row in with_history if row.get("wallet")}),
            "early_buyer_with_prior_runner_count": int(sum(_num(row.get("wallet_prior_runner_count") or row.get("prior_runner_count")) for row in items)),
            "early_buyer_with_prior_100k_count": int(sum(_num(row.get("wallet_prior_100k_runner_count") or row.get("prior_100k_runner_count")) for row in items)),
            "early_buyer_with_prior_500k_count": int(sum(_num(row.get("wallet_prior_500k_runner_count") or row.get("prior_500k_runner_count")) for row in items)),
            "early_buyer_with_prior_1m_count": int(sum(_num(row.get("wallet_prior_1m_runner_count") or row.get("prior_1m_runner_count")) for row in items)),
            "early_buyer_prior_failure_count": int(sum(_num(row.get("wallet_prior_failure_count") or row.get("prior_failure_count")) for row in items)),
            "repeated_buyer_quality_proxy": any((_num(row.get("prior_transaction_count")) or 0) > 0 for row in items),
            "early_buyer_history_confidence": _confidence([row.get("wallet_history_source_confidence") for row in items]),
        }
    return out


def _summarize_top_holders(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("launch_id"):
            grouped[row["launch_id"]].append(row)
    out = {}
    for launch_id, items in grouped.items():
        selected = max(items, key=lambda row: _milestone_rank(row.get("milestone")))
        out[launch_id] = {
            "mint": selected.get("mint"),
            "milestone_tier": selected.get("milestone_tier"),
            "top_holder_share_proxy": _num(selected.get("top_holder_share_proxy")),
            "top_10_holder_share_proxy": _num(selected.get("top_10_holder_share_proxy")),
            "top_holder_addresses_available": bool(selected.get("top_holder_owner")),
            "top_10_holder_addresses_available": bool(selected.get("top_10_holder_addresses") or selected.get("top_10_holder_owners")),
            "top_holder_behavior_proxy_available": True,
            "top_holder_replay_confidence": selected.get("holder_snapshot_confidence") or "unknown",
            "full_chain_holder_snapshot_confirmed": bool(selected.get("is_confirmed_full_chain_snapshot")),
        }
    return out


def _summarize_funders(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {row["launch_id"]: row for row in rows if row.get("launch_id")}


def _joined_rows(
    universe_rows: list[dict[str, Any]],
    early_by_launch: dict[str, dict[str, Any]],
    top_by_launch: dict[str, dict[str, Any]],
    funder_by_launch: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    launch_ids = {row.get("launch_id") for row in universe_rows if row.get("launch_id")}
    launch_ids.update(early_by_launch)
    launch_ids.update(top_by_launch)
    launch_ids.update(funder_by_launch)
    universe_by_launch = {row.get("launch_id"): row for row in universe_rows if row.get("launch_id")}
    out = []
    for launch_id in sorted(launch_ids):
        base = universe_by_launch.get(launch_id, {})
        early = early_by_launch.get(launch_id, {})
        top = top_by_launch.get(launch_id, {})
        funder = funder_by_launch.get(launch_id, {})
        tier = base.get("milestone_tier") or early.get("milestone_tier") or top.get("milestone_tier") or funder.get("milestone_tier")
        has_early = bool(early)
        has_top = bool(top)
        has_funder = bool(funder)
        row = {
            "launch_id": launch_id,
            "mint": base.get("mint") or base.get("token_mint") or early.get("mint") or top.get("mint") or funder.get("mint"),
            "creator": base.get("creator") or funder.get("creator"),
            "launch_time": base.get("launch_time") or base.get("launch_time_utc") or funder.get("launch_time") or _timestamp(_int_or_none(base.get("launch_ts") or funder.get("launch_ts"))),
            "launch_ts": _int_or_none(base.get("launch_ts") or funder.get("launch_ts")),
            "milestone_tier": tier,
            "peak_fdv_proxy": base.get("peak_fdv_proxy") or base.get("peak_valuation_proxy_usd"),
            "highest_milestone_reached": _highest_milestone(tier),
            "early_buyer_history_available": has_early,
            "early_buyer_wallet_count": int(early.get("early_buyer_wallet_count") or 0),
            "early_buyer_with_prior_history_count": int(early.get("early_buyer_with_prior_history_count") or 0),
            "early_buyer_with_prior_runner_count": int(early.get("early_buyer_with_prior_runner_count") or 0),
            "early_buyer_with_prior_100k_count": int(early.get("early_buyer_with_prior_100k_count") or 0),
            "early_buyer_with_prior_500k_count": int(early.get("early_buyer_with_prior_500k_count") or 0),
            "early_buyer_with_prior_1m_count": int(early.get("early_buyer_with_prior_1m_count") or 0),
            "early_buyer_prior_failure_count": int(early.get("early_buyer_prior_failure_count") or 0),
            "repeated_buyer_quality_proxy": bool(early.get("repeated_buyer_quality_proxy")),
            "early_buyer_history_confidence": early.get("early_buyer_history_confidence") or "none",
            "top_holder_replay_available": has_top,
            "top_holder_share_proxy": top.get("top_holder_share_proxy"),
            "top_10_holder_share_proxy": top.get("top_10_holder_share_proxy"),
            "top_holder_addresses_available": bool(top.get("top_holder_addresses_available")),
            "top_10_holder_addresses_available": bool(top.get("top_10_holder_addresses_available")),
            "top_holder_behavior_proxy_available": bool(top.get("top_holder_behavior_proxy_available")),
            "top_holder_replay_confidence": top.get("top_holder_replay_confidence") or "none",
            "full_chain_holder_snapshot_confirmed": bool(top.get("full_chain_holder_snapshot_confirmed")),
            "creator_funder_graph_available": has_funder,
            "candidate_funder_available": bool(funder.get("candidate_funder") and not funder.get("funding_missing_reason")),
            "candidate_funder": funder.get("candidate_funder"),
            "candidate_funder_confidence": funder.get("candidate_funder_confidence") or "none",
            "shared_funding_proxy": bool(funder.get("shared_funding_proxy")),
            "time_linked_funding_proxy": bool(funder.get("time_linked_funding_proxy")),
            "launches_sharing_funder": int(funder.get("launches_sharing_funder") or 0),
            "creators_sharing_funder": int(funder.get("creators_sharing_funder") or 0),
            "common_funder_candidate_id": funder.get("common_funder_candidate_id"),
            "creator_to_early_buyer_link_proxy": bool(funder.get("creator_to_early_buyer_transfer_link_proxy")),
            "creator_to_top_holder_link_proxy": bool(funder.get("creator_to_top_holder_transfer_link_proxy")),
            "funder_graph_confidence": funder.get("candidate_funder_confidence") or "none",
            "has_early_buyer_pilot_data": has_early,
            "has_top_holder_pilot_data": has_top,
            "has_creator_funder_pilot_data": has_funder,
            "has_any_p0_structural_data": has_early or has_top or has_funder,
            "has_all_three_p0_structural_layers": has_early and has_top and has_funder,
        }
        out.append(row)
    return out


def _coverage_by_tier(universe_rows: list[dict[str, Any]], joined_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_tier: dict[str, list[dict[str, Any]]] = defaultdict(list)
    universe_by_tier: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in joined_rows:
        by_tier[row.get("milestone_tier") or "unknown"].append(row)
    for row in universe_rows:
        universe_by_tier[row.get("milestone_tier") or "unknown"].append(row)
    rows = []
    for tier in MILESTONE_TIERS:
        tier_rows = by_tier.get(tier, [])
        universe_count = len(universe_by_tier.get(tier, [])) or len(tier_rows)
        early = sum(1 for row in tier_rows if row["has_early_buyer_pilot_data"])
        top = sum(1 for row in tier_rows if row["has_top_holder_pilot_data"])
        funder = sum(1 for row in tier_rows if row["has_creator_funder_pilot_data"])
        all_three = sum(1 for row in tier_rows if row["has_all_three_p0_structural_layers"])
        rows.append(
            {
                "milestone_tier": tier,
                "total_launches_in_tier": universe_count,
                "launches_with_early_buyer_history": early,
                "launches_with_top_holder_replay": top,
                "launches_with_creator_funder_graph": funder,
                "all_three_layers": all_three,
                "early_buyer_coverage_pct": _pct(early, universe_count),
                "top_holder_coverage_pct": _pct(top, universe_count),
                "creator_funder_coverage_pct": _pct(funder, universe_count),
                "all_three_coverage_pct": _pct(all_three, universe_count),
                "top_date_share": _top_date_share(tier_rows),
                "top_creator_share": _top_creator_share(tier_rows),
            }
        )
    return rows


def _overlap_audit(rows: list[dict[str, Any]]) -> dict[str, Any]:
    any_rows = [row for row in rows if row["has_any_p0_structural_data"]]
    all_three = [row for row in rows if row["has_all_three_p0_structural_layers"]]
    exactly_one = [row for row in any_rows if sum([row["has_early_buyer_pilot_data"], row["has_top_holder_pilot_data"], row["has_creator_funder_pilot_data"]]) == 1]
    exactly_two = [row for row in any_rows if sum([row["has_early_buyer_pilot_data"], row["has_top_holder_pilot_data"], row["has_creator_funder_pilot_data"]]) == 2]
    return {
        "launches_with_any_p0_structural_data": len(any_rows),
        "mints_with_any_p0_structural_data": len({row.get("mint") for row in any_rows if row.get("mint")}),
        "launches_covered_by_exactly_one_pilot": len(exactly_one),
        "launches_covered_by_exactly_two_pilots": len(exactly_two),
        "launches_covered_by_all_three_pilots": len(all_three),
        "mints_covered_by_all_three_pilots": len({row.get("mint") for row in all_three if row.get("mint")}),
        "runners_100k_plus_covered_by_all_three": sum(1 for row in all_three if _tier_at_least(row.get("milestone_tier"), "reached_100k_but_never_200k")),
        "runners_500k_plus_covered_by_all_three": sum(1 for row in all_three if _tier_at_least(row.get("milestone_tier"), "reached_500k_but_never_1m")),
        "runners_1m_plus_covered_by_all_three": sum(1 for row in all_three if row.get("milestone_tier") == "reached_1m_plus"),
        "failed_20k_triggers_covered_by_all_three": sum(1 for row in all_three if row.get("milestone_tier") == "never_reached_20k"),
    }


def _launch_coverage(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    any_rows = [row for row in rows if row["has_any_p0_structural_data"]]
    return {
        "universe_launches": total,
        "launches_with_any_p0_structural_data": len(any_rows),
        "coverage_pct": _pct(len(any_rows), total),
        "early_buyer_launches": sum(1 for row in rows if row["has_early_buyer_pilot_data"]),
        "top_holder_launches": sum(1 for row in rows if row["has_top_holder_pilot_data"]),
        "creator_funder_launches": sum(1 for row in rows if row["has_creator_funder_pilot_data"]),
        "all_three_layer_launches": sum(1 for row in rows if row["has_all_three_p0_structural_layers"]),
    }


def _structural_proxy_readiness(rows: list[dict[str, Any]], overlap: dict[str, Any]) -> dict[str, dict[str, Any]]:
    total = len(rows)
    families = {
        "early_buyer_wallet_quality_proxy": sum(1 for row in rows if row["has_early_buyer_pilot_data"]),
        "repeated_runner_buyer_proxy": sum(1 for row in rows if row["repeated_buyer_quality_proxy"]),
        "top_holder_share_proxy": sum(1 for row in rows if row["has_top_holder_pilot_data"]),
        "top_holder_address_behavior_proxy": sum(1 for row in rows if row["top_holder_behavior_proxy_available"]),
        "creator_funder_link_proxy": sum(1 for row in rows if row["has_creator_funder_pilot_data"]),
        "shared_funding_proxy": sum(1 for row in rows if row["shared_funding_proxy"]),
        "time_linked_funding_proxy": sum(1 for row in rows if row["time_linked_funding_proxy"]),
        "creator_to_wallet_link_proxy": sum(1 for row in rows if row["creator_to_early_buyer_link_proxy"] or row["creator_to_top_holder_link_proxy"]),
        "combined_p0_structural_proxy": overlap["launches_covered_by_all_three_pilots"],
    }
    out = {}
    for family, count in families.items():
        if family == "creator_to_wallet_link_proxy" and count == 0:
            classification = "pilot_only_needs_scale"
            reason = "no_creator_to_wallet_links_detected_in_bounded_pilot"
        elif count == 0:
            classification = "blocked"
            reason = "no_coverage"
        elif count >= 500 and _pct(count, total) >= 10.0:
            classification = "ready_for_full_fingerprint_report"
            reason = "coverage_broad_enough_for_descriptive_fingerprint_context"
        else:
            classification = "pilot_only_needs_scale"
            reason = "bounded_pilot_coverage_not_broad_enough_to_generalize"
        out[family] = {
            "covered_launches": count,
            "coverage_pct": _pct(count, total),
            "classification": classification,
            "reason": reason,
        }
    return out


def _overall_readiness(readiness: dict[str, dict[str, Any]], overlap: dict[str, Any]) -> str:
    classifications = {row["classification"] for row in readiness.values()}
    if "blocked" in classifications and overlap["launches_with_any_p0_structural_data"] == 0:
        return READINESS_BLOCKED
    if "needs_parser_repair" in classifications:
        return READINESS_REPAIR
    if readiness["combined_p0_structural_proxy"]["classification"] == "ready_for_full_fingerprint_report":
        return READINESS_READY
    return READINESS_SCALE


def _tier_context(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for tier in MILESTONE_TIERS:
        tier_rows = [row for row in rows if row.get("milestone_tier") == tier and row["has_any_p0_structural_data"]]
        out.append(
            {
                "milestone_tier": tier,
                "p0_rows": len(tier_rows),
                "repeated_runner_buyer_presence_count": sum(1 for row in tier_rows if row["repeated_buyer_quality_proxy"]),
                "shared_funding_proxy_count": sum(1 for row in tier_rows if row["shared_funding_proxy"]),
                "time_linked_funding_proxy_count": sum(1 for row in tier_rows if row["time_linked_funding_proxy"]),
                "median_top_holder_share_proxy": _median([row["top_holder_share_proxy"] for row in tier_rows if row["top_holder_share_proxy"] is not None]),
                "combined_structural_layer_count": sum(1 for row in tier_rows if row["has_all_three_p0_structural_layers"]),
            }
        )
    return out


def _scaleup_recommendation(readiness: str, overlap: dict[str, Any], universe_count: int) -> dict[str, Any]:
    options = [
        _option("A", "scale_early_buyer_wallet_history", "adds wallet quality coverage", 100_000, "moderate", "medium", "Useful but incomplete alone."),
        _option("B", "scale_top_holder_replay", "adds holder concentration/behavior coverage", 100_000, "moderate", "medium", "Useful but should align with other structural layers."),
        _option("C", "scale_creator_funder_graph", "adds shared/time-linked funding coverage", 100_000, "moderate", "medium", "Strong structural value but incomplete alone."),
        _option("D", "scale_all_three_medium_enrichment", "adds aligned combined structural coverage", 300_000, "high", "medium_high", "Best next step if combined-layer overlap is too small."),
        _option("E", "build_fingerprint_report_with_current_pilot_data", "uses current bounded pilot only", 0, "low", "low", "Can be a preview but not broad enough for full fingerprint report."),
        _option("F", "stop_and_repair_data_issue", "repair source/parser issue", 0, "low", "low", "No repair blocker identified in this audit."),
    ]
    selection = "E" if readiness == READINESS_READY else "D"
    selected = next(row for row in options if row["selection"] == selection)
    return {
        "selection": selection,
        "recommended_action": selected["action"],
        "reason": (
            "All three P0 pilots succeeded, but combined overlap is too small for a full runner-fingerprint report."
            if selection == "D"
            else "Combined P0 coverage is broad enough for a descriptive fingerprint report."
        ),
        "pilot_already_used_credits": 1_174,
        "projected_medium_run_credits": selected["estimated_helius_credits"],
        "projected_full_run_credits": 500_000,
        "within_500k_cap": selected["estimated_helius_credits"] <= 500_000,
        "universe_launches": universe_count,
        "current_all_three_overlap": overlap["launches_covered_by_all_three_pilots"],
        "options": options,
    }


def _option(selection: str, action: str, gain: str, credits: int, storage: str, runtime: str, risk: str) -> dict[str, Any]:
    return {
        "selection": selection,
        "action": action,
        "expected_added_coverage": gain,
        "estimated_helius_credits": credits,
        "estimated_storage": storage,
        "estimated_runtime": runtime,
        "value_gained": gain,
        "risk": risk,
        "within_500k_cap": credits <= 500_000,
    }


def _axiom_context(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "report_id": summary.get("report_id"),
        "historical_fields_mapped": (summary.get("summary") or {}).get("historical_fields_mapped"),
        "helius_needed_field_count": (summary.get("summary") or {}).get("helius_needed_field_count"),
        "blocked_field_count": (summary.get("summary") or {}).get("blocked_field_count"),
    }


def _markdown(report: dict[str, Any]) -> str:
    coverage = report["launch_coverage"]
    overlap = report["overlap_audit"]
    rec = report["scaleup_recommendation"]
    return "\n".join(
        [
            "# P0 Structural Proxy Audit",
            "",
            f"- Readiness classification: `{report['readiness_classification']}`",
            f"- Universe launches: `{coverage['universe_launches']}`",
            f"- Launches with any P0 structural data: `{coverage['launches_with_any_p0_structural_data']}`",
            f"- Early-buyer pilot launches: `{coverage['early_buyer_launches']}`",
            f"- Top-holder pilot launches: `{coverage['top_holder_launches']}`",
            f"- Creator/funder pilot launches: `{coverage['creator_funder_launches']}`",
            f"- All-three-layer launches: `{coverage['all_three_layer_launches']}`",
            f"- 100k+ all-three coverage: `{overlap['runners_100k_plus_covered_by_all_three']}`",
            f"- 500k+ all-three coverage: `{overlap['runners_500k_plus_covered_by_all_three']}`",
            f"- 1M+ all-three coverage: `{overlap['runners_1m_plus_covered_by_all_three']}`",
            f"- Recommended next action: `{rec['recommended_action']}`",
            "",
            "No thesis, validation, backtest, paper trading, live trading, optimization, grid search, ML, or Helius call was run.",
        ]
    ) + "\n"


def _status_markdown(report: dict[str, Any], summary_json: Path, summary_md: Path, coverage_csv: Path, overlap_csv: Path, preview_csv: Path, scale_csv: Path) -> str:
    coverage = report["launch_coverage"]
    overlap = report["overlap_audit"]
    rec = report["scaleup_recommendation"]
    return "\n".join(
        [
            "# P0 Structural Proxy Audit Status",
            "",
            "## Why This Audit Was Created",
            "This audit joins the completed P0 structural enrichment pilots into one offline coverage view before any runner-fingerprint report or thesis work.",
            "",
            "## P0 Pilots Included",
            "- Early-buyer wallet history pilot",
            "- Top-holder replay pilot",
            "- Creator/funder transfer graph pilot",
            "",
            "## Launch And Mint Coverage",
            f"- Universe launches: `{coverage['universe_launches']}`",
            f"- Launches with any P0 structural data: `{coverage['launches_with_any_p0_structural_data']}`",
            f"- All-three-layer launches: `{coverage['all_three_layer_launches']}`",
            f"- Mints covered by all three pilots: `{overlap['mints_covered_by_all_three_pilots']}`",
            "",
            "## Milestone Tier Coverage",
            f"- 100k+ runners covered by all three: `{overlap['runners_100k_plus_covered_by_all_three']}`",
            f"- 500k+ runners covered by all three: `{overlap['runners_500k_plus_covered_by_all_three']}`",
            f"- 1M+ runners covered by all three: `{overlap['runners_1m_plus_covered_by_all_three']}`",
            f"- Failed 20k triggers covered by all three: `{overlap['failed_20k_triggers_covered_by_all_three']}`",
            "",
            "## Readiness",
            f"- Classification: `{report['readiness_classification']}`",
            "- Fields ready for the next report remain bounded-pilot fields unless scale-up is run.",
            "- Top-holder fields remain observed replay proxies, not confirmed full-chain snapshots.",
            "- Creator/funder fields remain neutral structural proxies.",
            "",
            "## Recommended Next Action",
            f"`{rec['recommended_action']}`",
            "",
            "## Limitations",
            "- No thesis was run.",
            "- No outcome validation was run.",
            "- No Helius calls were made.",
            "- No trading or profitability claim is supported by this audit.",
            "",
            "## Reports",
            f"- Summary JSON: {summary_json}",
            f"- Summary Markdown: {summary_md}",
            f"- Coverage By Tier CSV: {coverage_csv}",
            f"- Overlap CSV: {overlap_csv}",
            f"- Joined Preview CSV: {preview_csv}",
            f"- Scale-Up Recommendation CSV: {scale_csv}",
        ]
    ) + "\n"


def _read_json(path: Path | str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _read_records(path: Path | str) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    if p.suffix == ".parquet":
        import pandas as pd

        return pd.read_parquet(p).to_dict(orient="records")
    with p.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _first_value(rows: list[dict[str, Any]], key: str) -> Any:
    for row in rows:
        if row.get(key) is not None:
            return row.get(key)
    return None


def _confidence(values: list[Any]) -> str:
    clean = {str(value) for value in values if value}
    if "high" in clean:
        return "high"
    if "medium" in clean:
        return "medium"
    if "low" in clean:
        return "low"
    return "none"


def _num(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _median(values: list[Any]) -> float | None:
    nums = sorted(_num(value) for value in values if value is not None)
    if not nums:
        return None
    mid = len(nums) // 2
    if len(nums) % 2:
        return nums[mid]
    return round((nums[mid - 1] + nums[mid]) / 2, 8)


def _pct(numerator: int, denominator: int) -> float:
    return round((numerator / denominator * 100), 4) if denominator else 0.0


def _milestone_rank(milestone: Any) -> int:
    order = {"20k": 1, "50k": 2, "100k": 3, "200k": 4, "500k": 5, "1m": 6}
    return order.get(str(milestone), 0)


def _highest_milestone(tier: Any) -> str | None:
    mapping = {
        "never_reached_20k": "below_20k",
        "reached_20k_but_never_50k": "20k",
        "reached_50k_but_never_100k": "50k",
        "reached_100k_but_never_200k": "100k",
        "reached_200k_but_never_500k": "200k",
        "reached_500k_but_never_1m": "500k",
        "reached_1m_plus": "1m_plus",
    }
    return mapping.get(str(tier))


def _tier_at_least(tier: Any, minimum: str) -> bool:
    return TIER_RANK.get(str(tier), -1) >= TIER_RANK[minimum]


def _top_date_share(rows: list[dict[str, Any]]) -> float:
    dates = []
    for row in rows:
        if row.get("launch_time"):
            dates.append(str(row["launch_time"])[:10])
        elif row.get("launch_ts"):
            dates.append(_timestamp(_int_or_none(row["launch_ts"]))[:10])
    return _pct(max(Counter(dates).values(), default=0), len(rows))


def _top_creator_share(rows: list[dict[str, Any]]) -> float:
    creators = [row.get("creator") for row in rows if row.get("creator")]
    return _pct(max(Counter(creators).values(), default=0), len(rows))


def _timestamp(value: int | None) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()
