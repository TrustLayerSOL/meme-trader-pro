"""Aligned medium P0 structural enrichment scale-up coordinator."""

from __future__ import annotations

import csv
import json
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from research.mtp_research.data_paths import data_lake_path
from research.mtp_research.validation.p0_creator_funder_transfer_graph_collection import (
    run_creator_funder_transfer_graph_collection,
)
from research.mtp_research.validation.p0_helius_early_buyer_collection import (
    run_p0_early_buyer_wallet_history_collection,
)
from research.mtp_research.validation.p0_top_holder_replay_pilot import (
    run_p0_top_holder_replay_pilot,
)


REPORT_ID = "aligned_p0_medium_scaleup_v0"
TARGET_TIERS = [
    "reached_20k_but_never_50k",
    "reached_50k_but_never_100k",
    "reached_100k_but_never_200k",
    "reached_200k_but_never_500k",
    "reached_500k_but_never_1m",
    "reached_1m_plus",
]
MILESTONE_FIELDS = {
    "20k": "crossing_20k_age",
    "50k": "crossing_50k_age",
    "100k": "crossing_100k_age",
    "200k": "crossing_200k_age",
    "500k": "crossing_500k_age",
    "1m": "crossing_1m_age",
}
DEFAULT_UNIVERSE_PATH = data_lake_path(
    "data",
    "backtests",
    "diagnostics",
    "reports",
    "repeated_buyer_runner_participation",
    "repeated_buyer_runner_participation_summary.json",
)
DEFAULT_CREATOR_LOOKUP_PATHS = [
    data_lake_path("data", "normalized", "pumpfun_creation_census_lifecycle_collected.jsonl"),
    data_lake_path("data", "normalized", "pumpfun_creation_census.jsonl"),
]
DEFAULT_OUTPUT_ROOT = data_lake_path()
DEFAULT_STATUS_PATH = Path("theses/ALIGNED_P0_MEDIUM_SCALEUP_STATUS.md")


class BudgetExceededError(RuntimeError):
    """Raised when projected aligned scale-up requests exceed the configured cap."""


def build_aligned_p0_medium_scaleup(
    *,
    universe_path: Path | str = DEFAULT_UNIVERSE_PATH,
    event_paths: list[Path | str] | None = None,
    creator_lookup_paths: list[Path | str] | None = None,
    output_root: Path | str = DEFAULT_OUTPUT_ROOT,
    status_path: Path | str = DEFAULT_STATUS_PATH,
    preferred_per_tier: int = 50,
    minimum_total_targets: int = 180,
    max_early_buyer_wallets: int = 3_000,
    credit_cap: int = 100_000,
    execute: bool = False,
    transaction_workers: int = 24,
) -> tuple[dict[str, Any], dict[str, Path]]:
    started = time.time()
    root = Path(output_root)
    paths = _output_paths(root)
    _ensure_output_dirs(paths)
    universe = _read_json(universe_path)
    raw_launch_rows = universe.get("launch_feature_rows") if isinstance(universe, dict) else []
    resolved_event_paths = event_paths
    if resolved_event_paths is None and isinstance(universe, dict):
        resolved_event_paths = [Path(path) for path in (universe.get("dataset") or {}).get("event_paths", [])]
    resolved_creator_paths = creator_lookup_paths or DEFAULT_CREATOR_LOOKUP_PATHS
    creator_lookup = _creator_lookup(resolved_creator_paths)
    launch_rows = _normalize_launch_rows(raw_launch_rows or [], creator_lookup)
    selected = _select_aligned_targets(launch_rows, preferred_per_tier=preferred_per_tier)
    if len(selected) < minimum_total_targets:
        raise ValueError(f"Aligned target set has {len(selected)} launches, below minimum {minimum_total_targets}.")

    early_targets = _early_buyer_targets(selected, resolved_event_paths or [], max_wallets=max_early_buyer_wallets)
    top_targets = _top_holder_targets(selected)
    funder_targets = _creator_funder_targets(selected)
    dry_run_budget = _budget_projection(
        selected=selected,
        early_targets=early_targets,
        top_targets=top_targets,
        funder_targets=funder_targets,
        credit_cap=credit_cap,
    )
    if dry_run_budget["projected_credits"] > credit_cap:
        if execute:
            raise BudgetExceededError(f"Projected credits {dry_run_budget['projected_credits']} exceed cap {credit_cap}.")
        readiness = "aligned_p0_medium_dry_run_blocked_budget"
    else:
        readiness = "aligned_p0_medium_execute_ready" if execute else "aligned_p0_medium_dry_run_ready"

    _write_csv(selected, paths["target_set_path"])
    _write_csv(early_targets, paths["early_targets_path"])
    _write_csv(top_targets, paths["top_targets_path"])
    _write_csv(funder_targets, paths["funder_targets_path"])
    _write_jsonl(paths["aligned_candidates_path"], [_candidate_row(row) for row in selected])

    collection_reports: dict[str, Any] = {}
    combined_rows: list[dict[str, Any]] = []
    if execute:
        if dry_run_budget["projected_credits"] > credit_cap:
            raise BudgetExceededError(f"Projected credits {dry_run_budget['projected_credits']} exceed cap {credit_cap}.")
        collection_reports = _execute_collectors(
            paths=paths,
            selected=selected,
            early_targets=early_targets,
            top_targets=top_targets,
            funder_targets=funder_targets,
            credit_cap=credit_cap,
            transaction_workers=transaction_workers,
        )
        combined_rows = _combined_structural_rows(
            selected,
            early_path=paths["early_jsonl_path"],
            top_path=paths["top_jsonl_path"],
            funder_path=paths["funder_jsonl_path"],
        )
        _write_jsonl(paths["combined_jsonl_path"], combined_rows)
        _write_parquet(combined_rows, paths["combined_parquet_path"])
        readiness = _post_execute_readiness(selected, combined_rows, collection_reports)

    report = _report(
        universe_path=universe_path,
        event_paths=resolved_event_paths or [],
        creator_lookup_paths=resolved_creator_paths,
        selected=selected,
        early_targets=early_targets,
        top_targets=top_targets,
        funder_targets=funder_targets,
        dry_run_budget=dry_run_budget,
        collection_reports=collection_reports,
        combined_rows=combined_rows,
        readiness=readiness,
        execute=execute,
        started=started,
        paths=paths,
    )
    outputs = _write_reports(report, paths=paths, status_path=Path(status_path), execute=execute)
    return report, outputs


def _output_paths(root: Path) -> dict[str, Path]:
    structural = root / "data" / "backtests" / "structural_enrichment"
    raw = root / "data" / "raw" / "structural_enrichment" / "aligned_p0_medium"
    report_dir = root / "data" / "backtests" / "diagnostics" / "reports" / "aligned_p0_medium_scaleup"
    return {
        "structural_dir": structural,
        "raw_dir": raw,
        "report_dir": report_dir,
        "target_set_path": structural / "aligned_p0_medium_targets.csv",
        "early_targets_path": report_dir / "aligned_p0_medium_early_buyer_targets.csv",
        "top_targets_path": report_dir / "aligned_p0_medium_top_holder_targets.csv",
        "funder_targets_path": report_dir / "aligned_p0_medium_creator_funder_targets.csv",
        "aligned_candidates_path": report_dir / "aligned_p0_medium_candidates.jsonl",
        "early_raw_path": raw / "early_buyer_wallet_history_raw_transactions.jsonl",
        "top_raw_path": raw / "top_holder_replay_raw_transactions.jsonl",
        "funder_raw_dir": raw / "creator_funder_graph",
        "early_jsonl_path": structural / "aligned_p0_medium_early_buyer_wallet_history.jsonl",
        "early_parquet_path": structural / "aligned_p0_medium_early_buyer_wallet_history.parquet",
        "top_jsonl_path": structural / "aligned_p0_medium_top_holder_replay.jsonl",
        "top_parquet_path": structural / "aligned_p0_medium_top_holder_replay.parquet",
        "funder_jsonl_path": structural / "aligned_p0_medium_creator_funder_graph.jsonl",
        "funder_parquet_path": structural / "aligned_p0_medium_creator_funder_graph.parquet",
        "combined_jsonl_path": structural / "aligned_p0_medium_structural_features.jsonl",
        "combined_parquet_path": structural / "aligned_p0_medium_structural_features.parquet",
        "checkpoint_path": structural / "aligned_p0_medium_checkpoint.json",
        "early_checkpoint_path": structural / "checkpoints" / "aligned_p0_medium_early_buyer_wallet_history.json",
        "top_checkpoint_path": structural / "checkpoints" / "aligned_p0_medium_top_holder_replay.json",
        "funder_checkpoint_path": structural / "checkpoints" / "aligned_p0_medium_creator_funder_graph.json",
        "dry_run_json_path": report_dir / "aligned_p0_medium_dry_run.json",
        "dry_run_markdown_path": report_dir / "aligned_p0_medium_dry_run.md",
        "summary_json_path": report_dir / "aligned_p0_medium_scaleup_summary.json",
        "summary_markdown_path": report_dir / "aligned_p0_medium_scaleup_summary.md",
        "coverage_by_tier_path": report_dir / "aligned_p0_medium_coverage_by_tier.csv",
        "target_set_report_path": report_dir / "aligned_p0_medium_target_set.csv",
        "missing_reasons_path": report_dir / "aligned_p0_medium_missing_reasons.csv",
    }


def _ensure_output_dirs(paths: dict[str, Path]) -> None:
    for key in ("structural_dir", "raw_dir", "report_dir"):
        paths[key].mkdir(parents=True, exist_ok=True)


def _normalize_launch_rows(rows: list[dict[str, Any]], creator_lookup: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for row in rows:
        mint = row.get("mint") or row.get("token_mint")
        tier = row.get("milestone_tier")
        launch_ts = _int_or_none(row.get("launch_ts"))
        if not mint or tier not in TARGET_TIERS or launch_ts is None:
            continue
        lookup = creator_lookup.get(str(mint), {})
        normalized.append(
            {
                "launch_id": row.get("launch_id") or f"launch-{mint}",
                "mint": str(mint),
                "creator": row.get("creator") or lookup.get("creator") or "",
                "creation_signature": lookup.get("creation_signature") or "",
                "launch_ts": launch_ts,
                "launch_time_utc": _timestamp(launch_ts),
                "launch_date": row.get("launch_date") or _timestamp(launch_ts)[:10],
                "milestone_tier": tier,
                **{field: _int_or_none(row.get(field)) for field in MILESTONE_FIELDS.values()},
            }
        )
    return normalized


def _select_aligned_targets(rows: list[dict[str, Any]], *, preferred_per_tier: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen_mints: set[str] = set()
    for tier in TARGET_TIERS:
        tier_rows = [row for row in rows if row["milestone_tier"] == tier and row.get("crossing_20k_age") is not None]
        tier_rows = sorted(tier_rows, key=lambda row: _selection_sort_key(row))
        selected_for_tier: list[dict[str, Any]] = []
        dates_seen: Counter[str] = Counter()
        creators_seen: Counter[str] = Counter()
        for row in tier_rows:
            if row["mint"] in seen_mints:
                continue
            if dates_seen[row["launch_date"]] >= max(1, preferred_per_tier // 4):
                continue
            creator = row.get("creator") or "unknown"
            if creator != "unknown" and creators_seen[creator] >= max(1, preferred_per_tier // 5):
                continue
            selected_for_tier.append(row)
            seen_mints.add(row["mint"])
            dates_seen[row["launch_date"]] += 1
            creators_seen[creator] += 1
            if len(selected_for_tier) >= preferred_per_tier:
                break
        if len(selected_for_tier) < preferred_per_tier:
            for row in tier_rows:
                if row["mint"] in seen_mints:
                    continue
                selected_for_tier.append(row)
                seen_mints.add(row["mint"])
                if len(selected_for_tier) >= preferred_per_tier:
                    break
        selected.extend({**row, "reason_selected": "aligned_medium_balanced_milestone_tier"} for row in selected_for_tier)
    return sorted(selected, key=lambda row: (TARGET_TIERS.index(row["milestone_tier"]), row["launch_ts"], row["mint"]))


def _selection_sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    creator_missing_rank = 1 if not row.get("creator") else 0
    return (creator_missing_rank, row.get("launch_date") or "", row.get("creator") or "", row.get("launch_ts") or 0, row.get("mint") or "")


def _early_buyer_targets(selected: list[dict[str, Any]], event_paths: list[Path | str], *, max_wallets: int) -> list[dict[str, Any]]:
    launches = {row["mint"]: row for row in selected}
    by_wallet: dict[str, dict[str, Any]] = {}
    for event in _iter_jsonl(event_paths):
        mint = event.get("token_mint") or event.get("mint")
        actor = event.get("actor") or event.get("wallet") or event.get("buyer")
        if not mint or str(mint) not in launches or not actor or not _is_buy_event(event):
            continue
        launch = launches[str(mint)]
        age = _event_age(event, launch["launch_ts"])
        if age is None or age < 0 or age > (launch.get("crossing_20k_age") or 0):
            continue
        wallet = str(actor)
        if wallet in by_wallet:
            continue
        by_wallet[wallet] = {
            "wallet": wallet,
            "current_launch_id": launch["launch_id"],
            "current_mint": launch["mint"],
            "current_milestone_tier": launch["milestone_tier"],
            "first_seen_in_launch_time": event.get("block_time") or event.get("timestamp") or "",
            "launch_age_seconds": age,
            "reason_selected": "aligned_medium_early_buyer_before_20k_trigger",
        }
        if len(by_wallet) >= max_wallets:
            break
    return sorted(by_wallet.values(), key=lambda row: (row["current_launch_id"], row["wallet"]))


def _top_holder_targets(selected: list[dict[str, Any]]) -> list[dict[str, Any]]:
    targets = []
    for row in selected:
        for milestone, field in MILESTONE_FIELDS.items():
            age = row.get(field)
            if age is None:
                continue
            targets.append(
                {
                    "launch_id": row["launch_id"],
                    "mint": row["mint"],
                    "creator": row.get("creator") or "",
                    "milestone": milestone,
                    "milestone_time": row["launch_ts"] + int(age),
                    "milestone_age_seconds": int(age),
                    "milestone_tier": row["milestone_tier"],
                    "reason_selected": "aligned_medium_milestone_replay",
                }
            )
    return sorted(targets, key=lambda row: (row["launch_id"], _milestone_rank(row["milestone"])))


def _creator_funder_targets(selected: list[dict[str, Any]]) -> list[dict[str, Any]]:
    targets = []
    for row in selected:
        if not row.get("creator"):
            continue
        targets.append(
            {
                "launch_id": row["launch_id"],
                "mint": row["mint"],
                "creator": row["creator"],
                "milestone_tier": row["milestone_tier"],
                "candidate_funder": "",
                "funding_signature": "",
                "common_funder_candidate_id": "",
                "reason_selected": "aligned_medium_creator_history",
            }
        )
    return sorted(targets, key=lambda row: (row["creator"], row["launch_id"]))


def _budget_projection(
    *,
    selected: list[dict[str, Any]],
    early_targets: list[dict[str, Any]],
    top_targets: list[dict[str, Any]],
    funder_targets: list[dict[str, Any]],
    credit_cap: int,
) -> dict[str, Any]:
    early_requests = len({row["wallet"] for row in early_targets})
    top_requests = len({row["mint"] for row in top_targets}) * 2
    funder_requests = len({row["creator"] for row in funder_targets if row.get("creator")}) * 2
    projected = early_requests + top_requests + funder_requests
    return {
        "selected_launches": len(selected),
        "early_buyer_projected_requests": early_requests,
        "top_holder_projected_requests": top_requests,
        "creator_funder_projected_requests": funder_requests,
        "projected_requests": projected,
        "projected_credits": projected,
        "credit_cap": credit_cap,
        "request_ceiling_status": "within_cap" if projected <= credit_cap else "over_cap",
        "network_calls_made": 0,
    }


def _execute_collectors(
    *,
    paths: dict[str, Path],
    selected: list[dict[str, Any]],
    early_targets: list[dict[str, Any]],
    top_targets: list[dict[str, Any]],
    funder_targets: list[dict[str, Any]],
    credit_cap: int,
    transaction_workers: int,
) -> dict[str, Any]:
    remaining_after_top = max(1, credit_cap - (len({row["wallet"] for row in early_targets}) + len({row["creator"] for row in funder_targets}) * 2))
    top_report = run_p0_top_holder_replay_pilot(
        target_csv_path=paths["top_targets_path"],
        execute=True,
        max_mints=len({row["mint"] for row in top_targets}),
        max_pages_per_mint=2,
        max_transactions_per_mint=250,
        max_total_transactions=max(1, len(selected) * 250),
        request_ceiling=remaining_after_top,
        transaction_workers=transaction_workers,
        output_paths={
            "raw_path": paths["top_raw_path"],
            "jsonl_path": paths["top_jsonl_path"],
            "parquet_path": paths["top_parquet_path"],
            "checkpoint_path": paths["top_checkpoint_path"],
            "report_dir": paths["report_dir"] / "top_holder_replay",
        },
    )
    used_top = _requests_used(top_report)
    early_cap = max(1, credit_cap - used_top)
    early_report = run_p0_early_buyer_wallet_history_collection(
        target_csv_path=paths["early_targets_path"],
        execute=True,
        max_wallets=len({row["wallet"] for row in early_targets}),
        lookback_days=30,
        max_pages_per_wallet=1,
        max_transactions_per_wallet=25,
        max_total_transactions=max(1, len(early_targets) * 25),
        request_ceiling=early_cap,
        transaction_workers=transaction_workers,
        output_paths={
            "raw_path": paths["early_raw_path"],
            "jsonl_path": paths["early_jsonl_path"],
            "parquet_path": paths["early_parquet_path"],
            "checkpoint_path": paths["early_checkpoint_path"],
            "report_dir": paths["report_dir"] / "early_buyer_wallet_history",
        },
    )
    used_early = _requests_used(early_report)
    funder_cap = max(1, credit_cap - used_top - used_early)
    funder_report = run_creator_funder_transfer_graph_collection(
        target_path=paths["funder_targets_path"],
        candidates_path=paths["aligned_candidates_path"],
        early_buyer_path=paths["early_jsonl_path"],
        top_holder_path=paths["top_jsonl_path"],
        execute=True,
        lookback_hours=24,
        max_pages_per_address=2,
        max_transactions_per_address=200,
        max_total_transactions=max(1, len(funder_targets) * 200),
        request_ceiling=funder_cap,
        credit_cap=funder_cap,
        transaction_workers=transaction_workers,
        output_paths={
            "raw_dir": paths["funder_raw_dir"],
            "jsonl_path": paths["funder_jsonl_path"],
            "parquet_path": paths["funder_parquet_path"],
            "checkpoint_path": paths["funder_checkpoint_path"],
            "report_dir": paths["report_dir"] / "creator_funder_graph",
        },
    )
    return {"top_holder": top_report, "early_buyer": early_report, "creator_funder": funder_report}


def _combined_structural_rows(
    selected: list[dict[str, Any]],
    *,
    early_path: Path,
    top_path: Path,
    funder_path: Path,
) -> list[dict[str, Any]]:
    early_by_launch = _early_by_launch(_read_records(early_path))
    top_by_launch = _top_by_launch(_read_records(top_path))
    funder_by_launch = {row["launch_id"]: row for row in _read_records(funder_path) if row.get("launch_id")}
    output = []
    for row in selected:
        launch_id = row["launch_id"]
        early = early_by_launch.get(launch_id, {})
        top = top_by_launch.get(launch_id, {})
        funder = funder_by_launch.get(launch_id, {})
        has_early = bool(early)
        has_top = bool(top)
        has_funder = bool(funder)
        output.append(
            {
                "launch_id": launch_id,
                "mint": row["mint"],
                "creator": row.get("creator") or None,
                "launch_ts": row["launch_ts"],
                "launch_time_utc": row["launch_time_utc"],
                "launch_date": row["launch_date"],
                "milestone_tier": row["milestone_tier"],
                "early_buyer_wallet_count": early.get("early_buyer_wallet_count", 0),
                "early_buyer_with_prior_history_count": early.get("early_buyer_with_prior_history_count", 0),
                "top_holder_share_proxy": top.get("top_holder_share_proxy"),
                "top_10_holder_share_proxy": top.get("top_10_holder_share_proxy"),
                "top_holder_replay_confidence": top.get("holder_snapshot_confidence") or "none",
                "is_confirmed_full_chain_snapshot": False,
                "candidate_funder": funder.get("candidate_funder"),
                "candidate_funder_confidence": funder.get("candidate_funder_confidence") or "none",
                "shared_funding_proxy": bool(funder.get("shared_funding_proxy")),
                "time_linked_funding_proxy": bool(funder.get("time_linked_funding_proxy")),
                "has_early_buyer_wallet_history": has_early,
                "has_top_holder_replay": has_top,
                "has_creator_funder_graph": has_funder,
                "has_all_three_p0_layers": has_early and has_top and has_funder,
                "semantic_label": "aligned_p0_structural_proxy",
            }
        )
    return sorted(output, key=lambda item: (TARGET_TIERS.index(item["milestone_tier"]), item["launch_ts"], item["mint"]))


def _early_by_launch(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        launch_id = row.get("current_launch_id") or row.get("launch_id")
        if launch_id:
            grouped[launch_id].append(row)
    output = {}
    for launch_id, items in grouped.items():
        output[launch_id] = {
            "early_buyer_wallet_count": len({row.get("wallet") for row in items if row.get("wallet")}),
            "early_buyer_with_prior_history_count": sum(1 for row in items if (_int_or_none(row.get("prior_transaction_count")) or 0) > 0),
        }
    return output


def _top_by_launch(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("launch_id"):
            grouped[row["launch_id"]].append(row)
    output = {}
    for launch_id, items in grouped.items():
        output[launch_id] = max(items, key=lambda row: _milestone_rank(row.get("milestone")))
    return output


def _report(
    *,
    universe_path: Path | str,
    event_paths: list[Path | str],
    creator_lookup_paths: list[Path | str],
    selected: list[dict[str, Any]],
    early_targets: list[dict[str, Any]],
    top_targets: list[dict[str, Any]],
    funder_targets: list[dict[str, Any]],
    dry_run_budget: dict[str, Any],
    collection_reports: dict[str, Any],
    combined_rows: list[dict[str, Any]],
    readiness: str,
    execute: bool,
    started: float,
    paths: dict[str, Path],
) -> dict[str, Any]:
    coverage_by_tier = _coverage_by_tier(selected, combined_rows)
    overlap = _overlap(combined_rows)
    target_quality = _target_quality(selected)
    collection_summary = _collection_summary(collection_reports)
    warnings = _warnings(selected, dry_run_budget, collection_reports, combined_rows)
    return {
        "report_id": REPORT_ID,
        "report_type": "aligned_medium_p0_structural_enrichment_scaleup",
        "readiness_classification": readiness,
        "methodology_flags": [
            "research_only",
            "data_enrichment_only",
            "not_a_thesis",
            "no_thesis_promotion",
            "no_validation_run",
            "no_backtest",
            "no_walk_forward_validation",
            "no_paper_trading",
            "no_live_trading",
            "no_auto_buy_sell",
            "no_private_key_logic",
            "no_wallet_execution",
            "no_order_routing",
            "no_trading_logic",
            "no_profitability_claims",
            "no_strategy_generation",
            "no_threshold_optimization",
            "no_grid_search",
            "no_ml_black_boxes",
            "neutral_proxy_labels_only",
            "observed_replay_not_full_chain_holder_state",
        ],
        "execution": {
            "mode": "execute" if execute else "dry_run",
            "execute_completed": bool(execute and collection_reports),
            "started_at": _timestamp(int(started)),
            "elapsed_seconds": round(time.time() - started, 3),
        },
        "network_calls_made": collection_summary["total_requests_used"] if execute else 0,
        "input_paths": {
            "universe_path": str(universe_path),
            "event_paths": [str(path) for path in event_paths],
            "creator_lookup_paths": [str(path) for path in creator_lookup_paths],
        },
        "target_cohort": {
            "launches_selected": len(selected),
            "target_launch_ids": [row["launch_id"] for row in selected],
            "unique_mints": len({row["mint"] for row in selected}),
            "unique_dates": len({row["launch_date"] for row in selected}),
            "unique_creators": len({row["creator"] for row in selected if row.get("creator")}),
            "never_reached_20k_included": sum(1 for row in selected if row["milestone_tier"] == "never_reached_20k"),
            **target_quality,
        },
        "layer_targets": {
            "early_buyer_wallet_targets": len(early_targets),
            "top_holder_milestone_targets": len(top_targets),
            "creator_funder_launch_targets": len(funder_targets),
        },
        "dry_run_budget": dry_run_budget,
        "coverage_by_tier": coverage_by_tier,
        "overlap_audit": overlap,
        "collection_summary": collection_summary,
        "collection_reports": collection_reports,
        "warnings": warnings,
        "outputs": {key: str(path) for key, path in paths.items() if key.endswith("_path") or key.endswith("_dir")},
    }


def _target_quality(selected: list[dict[str, Any]]) -> dict[str, Any]:
    date_counts = Counter(row["launch_date"] for row in selected)
    creator_counts = Counter(row.get("creator") or "unknown" for row in selected)
    total = len(selected)
    return {
        "top_date": date_counts.most_common(1)[0][0] if date_counts else None,
        "top_date_share_pct": _pct(date_counts.most_common(1)[0][1], total) if date_counts else 0.0,
        "top_creator_share_pct": _pct(creator_counts.most_common(1)[0][1], total) if creator_counts else 0.0,
        "top_3_creator_share_pct": _pct(sum(count for _creator, count in creator_counts.most_common(3)), total) if creator_counts else 0.0,
        "unknown_creator_share_pct": _pct(creator_counts.get("unknown", 0), total),
    }


def _coverage_by_tier(selected: list[dict[str, Any]], combined_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    combined_by_launch = {row["launch_id"]: row for row in combined_rows}
    output = []
    for tier in TARGET_TIERS:
        tier_rows = [row for row in selected if row["milestone_tier"] == tier]
        combined = [combined_by_launch[row["launch_id"]] for row in tier_rows if row["launch_id"] in combined_by_launch]
        output.append(
            {
                "milestone_tier": tier,
                "selected_launches": len(tier_rows),
                "combined_rows": len(combined),
                "early_buyer_rows": sum(1 for row in combined if row.get("has_early_buyer_wallet_history")),
                "top_holder_rows": sum(1 for row in combined if row.get("has_top_holder_replay")),
                "creator_funder_rows": sum(1 for row in combined if row.get("has_creator_funder_graph")),
                "all_three_rows": sum(1 for row in combined if row.get("has_all_three_p0_layers")),
                "all_three_coverage_pct": _pct(sum(1 for row in combined if row.get("has_all_three_p0_layers")), len(tier_rows)),
            }
        )
    return output


def _overlap(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "launches_with_any_p0_layer": 0,
            "launches_with_all_three_p0_layers": 0,
            "launches_with_exactly_one_p0_layer": 0,
            "launches_with_exactly_two_p0_layers": 0,
            "all_three_coverage_pct": 0.0,
        }
    any_layer = []
    all_three = []
    exactly_one = []
    exactly_two = []
    for row in rows:
        count = sum([row.get("has_early_buyer_wallet_history"), row.get("has_top_holder_replay"), row.get("has_creator_funder_graph")])
        if count:
            any_layer.append(row)
        if count == 3:
            all_three.append(row)
        if count == 1:
            exactly_one.append(row)
        if count == 2:
            exactly_two.append(row)
    return {
        "launches_with_any_p0_layer": len(any_layer),
        "launches_with_all_three_p0_layers": len(all_three),
        "launches_with_exactly_one_p0_layer": len(exactly_one),
        "launches_with_exactly_two_p0_layers": len(exactly_two),
        "all_three_coverage_pct": _pct(len(all_three), len(rows)),
    }


def _post_execute_readiness(selected: list[dict[str, Any]], combined_rows: list[dict[str, Any]], collection_reports: dict[str, Any]) -> str:
    provider_errors = [
        error
        for report in collection_reports.values()
        for error in ((report.get("provider") or {}).get("errors") or [])
    ]
    if provider_errors or not combined_rows:
        return "aligned_p0_medium_blocked"
    quality = _target_quality(selected)
    overlap = _overlap(combined_rows)
    if (
        len(selected) >= 180
        and overlap["all_three_coverage_pct"] >= 80.0
        and quality["top_date_share_pct"] <= 25.0
        and quality["unknown_creator_share_pct"] <= 25.0
    ):
        return "aligned_p0_medium_ready_for_fingerprint_report"
    return "aligned_p0_medium_partial_needs_review"


def _collection_summary(collection_reports: dict[str, Any]) -> dict[str, Any]:
    total_requests = sum(_requests_used(report) for report in collection_reports.values())
    total_transactions = sum(_transactions_fetched(report) for report in collection_reports.values())
    return {
        "total_requests_used": total_requests,
        "total_helius_credits_estimate": total_requests,
        "total_transactions_fetched": total_transactions,
        "reports_completed": len(collection_reports),
    }


def _warnings(
    selected: list[dict[str, Any]],
    dry_run_budget: dict[str, Any],
    collection_reports: dict[str, Any],
    combined_rows: list[dict[str, Any]],
) -> list[str]:
    warnings = []
    if dry_run_budget["request_ceiling_status"] != "within_cap":
        warnings.append("projected_credit_cap_exceeded")
    if not selected:
        warnings.append("missing_aligned_targets")
    if selected and _target_quality(selected)["top_date_share_pct"] > 25.0:
        warnings.append("target_date_concentration_above_25_pct")
    if selected and _target_quality(selected)["unknown_creator_share_pct"] > 25.0:
        warnings.append("creator_unknown_share_above_25_pct")
    for report in collection_reports.values():
        warnings.extend(report.get("warnings") or [])
        provider_errors = (report.get("provider") or {}).get("errors") or []
        if provider_errors:
            warnings.append("provider_or_auth_error")
    if collection_reports and combined_rows and _overlap(combined_rows)["all_three_coverage_pct"] < 80.0:
        warnings.append("all_three_structural_layer_coverage_below_80_pct")
    return sorted(set(warnings))


def _write_reports(report: dict[str, Any], *, paths: dict[str, Path], status_path: Path, execute: bool) -> dict[str, Path]:
    paths["report_dir"].mkdir(parents=True, exist_ok=True)
    dry_payload = {key: value for key, value in report.items() if key not in {"collection_reports"}}
    paths["dry_run_json_path"].write_text(json.dumps(dry_payload, indent=2, sort_keys=True), encoding="utf-8")
    paths["dry_run_markdown_path"].write_text(_markdown(report), encoding="utf-8")
    if execute:
        paths["summary_json_path"].write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        paths["summary_markdown_path"].write_text(_markdown(report), encoding="utf-8")
    else:
        paths["summary_json_path"].write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        paths["summary_markdown_path"].write_text(_markdown(report), encoding="utf-8")
    _write_csv(report["coverage_by_tier"], paths["coverage_by_tier_path"])
    _copy_csv(paths["target_set_path"], paths["target_set_report_path"])
    _write_csv(_missing_reason_rows(report), paths["missing_reasons_path"])
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(_status_markdown(report, paths), encoding="utf-8")
    return {
        "target_set_path": paths["target_set_path"],
        "dry_run_json_path": paths["dry_run_json_path"],
        "dry_run_markdown_path": paths["dry_run_markdown_path"],
        "summary_json_path": paths["summary_json_path"],
        "summary_markdown_path": paths["summary_markdown_path"],
        "coverage_by_tier_path": paths["coverage_by_tier_path"],
        "target_set_report_path": paths["target_set_report_path"],
        "missing_reasons_path": paths["missing_reasons_path"],
        "combined_jsonl_path": paths["combined_jsonl_path"],
        "combined_parquet_path": paths["combined_parquet_path"],
        "status_path": status_path,
    }


def _missing_reason_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for layer, key in [
        ("early_buyer_wallet_history", "early_buyer_wallet_targets"),
        ("top_holder_replay", "top_holder_milestone_targets"),
        ("creator_funder_graph", "creator_funder_launch_targets"),
    ]:
        count = report["layer_targets"][key]
        if count == 0:
            rows.append({"layer": layer, "missing_reason": "no_targets_selected", "count": 1})
    if not rows:
        rows.append({"layer": "aligned_medium", "missing_reason": "none", "count": 0})
    return rows


def _markdown(report: dict[str, Any]) -> str:
    cohort = report["target_cohort"]
    budget = report["dry_run_budget"]
    overlap = report["overlap_audit"]
    lines = [
        "# Aligned P0 Medium Scale-Up",
        "",
        f"- Readiness classification: `{report['readiness_classification']}`",
        f"- Execution mode: `{report['execution']['mode']}`",
        f"- Launches selected: `{cohort['launches_selected']}`",
        f"- Unique dates: `{cohort['unique_dates']}`",
        f"- Top date share: `{cohort['top_date_share_pct']}`%",
        f"- Unique creators: `{cohort['unique_creators']}`",
        f"- Unknown creator share: `{cohort['unknown_creator_share_pct']}`%",
        f"- Projected credits: `{budget['projected_credits']}` / `{budget['credit_cap']}`",
        f"- Request ceiling status: `{budget['request_ceiling_status']}`",
        f"- All-three-layer launches: `{overlap['launches_with_all_three_p0_layers']}`",
        f"- Warnings: `{report['warnings']}`",
        "",
        "No thesis, validation, backtest, walk-forward validation, paper trading, live trading, strategy generation, optimization, grid search, or ML was run.",
    ]
    return "\n".join(lines) + "\n"


def _status_markdown(report: dict[str, Any], paths: dict[str, Path]) -> str:
    return "\n".join(
        [
            "# Aligned P0 Medium Scale-Up Status",
            "",
            f"Readiness classification: `{report['readiness_classification']}`",
            f"Execution mode: `{report['execution']['mode']}`",
            f"Launches selected: `{report['target_cohort']['launches_selected']}`",
            f"Projected credits: `{report['dry_run_budget']['projected_credits']}`",
            f"Requests used: `{report['collection_summary']['total_requests_used']}`",
            f"Transactions fetched: `{report['collection_summary']['total_transactions_fetched']}`",
            "",
            "## Guardrails",
            "This is a data-enrichment sprint only. No thesis, validation, backtest, paper/live trading, execution logic, optimization, grid search, or ML was run.",
            "",
            "## Artifacts",
            f"- Target set: {paths['target_set_path']}",
            f"- Dry-run JSON: {paths['dry_run_json_path']}",
            f"- Dry-run Markdown: {paths['dry_run_markdown_path']}",
            f"- Summary JSON: {paths['summary_json_path']}",
            f"- Summary Markdown: {paths['summary_markdown_path']}",
            f"- Combined JSONL: {paths['combined_jsonl_path']}",
            f"- Combined Parquet: {paths['combined_parquet_path']}",
        ]
    ) + "\n"


def _creator_lookup(paths: list[Path | str]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for row in _iter_jsonl(paths):
        mint = row.get("mint") or row.get("token_mint")
        creator = row.get("creator_deployer") or row.get("creator") or row.get("deployer")
        if mint and creator and str(mint) not in lookup:
            lookup[str(mint)] = {
                "creator": str(creator),
                "creation_signature": row.get("creation_signature") or "",
            }
    return lookup


def _candidate_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "launch_id": row["launch_id"],
        "token_mint": row["mint"],
        "launch_ts": row["launch_ts"],
        "launch_time_utc": row["launch_time_utc"],
        "creator": row.get("creator") or "",
        "metadata_json": {"source": "aligned_p0_medium_scaleup"},
    }


def _read_json(path: Path | str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _read_records(path: Path | str) -> list[dict[str, Any]]:
    value = Path(path)
    if not value.exists():
        return []
    if value.suffix == ".parquet":
        import pandas as pd

        return pd.read_parquet(value).to_dict(orient="records")
    with value.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _iter_jsonl(paths: list[Path | str]) -> Any:
    for path in paths:
        value = Path(path)
        if not value.exists():
            continue
        with value.open("r", encoding="utf-8") as handle:
            for line in handle:
                text = line.strip()
                if text:
                    yield json.loads(text)


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True))
            handle.write("\n")


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


def _copy_csv(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")


def _write_parquet(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import pandas as pd
    except Exception:
        path.with_suffix(".parquet.unavailable.json").write_text(
            json.dumps({"row_count": len(rows), "reason": "pandas_or_parquet_engine_unavailable"}, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return
    pd.DataFrame(rows).to_parquet(path, index=False)


def _is_buy_event(event: dict[str, Any]) -> bool:
    venue = str(event.get("venue") or "").lower()
    if venue == "pumpfun_create":
        return False
    labels = {
        str(event.get("event_type") or "").lower(),
        str(event.get("classification") or "").lower(),
        str(event.get("side") or "").lower(),
        venue,
    }
    if labels & {"buy", "pumpfun_buy", "accumulate", "token_accumulation"}:
        return True
    if event.get("is_buy") is True:
        return True
    buy_amount = _float_or_none(event.get("buy_amount") or event.get("token_amount_in"))
    return buy_amount is not None and buy_amount > 0


def _event_age(event: dict[str, Any], launch_ts: int | None) -> int | None:
    block_time = _int_or_none(event.get("block_time") or event.get("timestamp"))
    if launch_ts is None or block_time is None:
        return None
    return block_time - launch_ts


def _milestone_rank(value: Any) -> int:
    return {"20k": 1, "50k": 2, "100k": 3, "200k": 4, "500k": 5, "1m": 6}.get(str(value), 0)


def _requests_used(report: dict[str, Any]) -> int:
    return int((report.get("requests") or {}).get("requests_used") or report.get("network_calls_made") or 0)


def _transactions_fetched(report: dict[str, Any]) -> int:
    collection = report.get("collection") or {}
    return int(collection.get("transactions_fetched") or 0)


def _timestamp(value: int | None) -> str:
    if value is None:
        return ""
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()


def _int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pct(numerator: int, denominator: int) -> float:
    return round(numerator / denominator * 100, 4) if denominator else 0.0
