"""Creator metadata repair and second-run planning for aligned P0 scale-up."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import shutil
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from research.mtp_research.data_paths import data_lake_path
from research.mtp_research.validation.aligned_p0_medium_scaleup import (
    DEFAULT_CREATOR_LOOKUP_PATHS,
    DEFAULT_UNIVERSE_PATH,
    MILESTONE_FIELDS,
    TARGET_TIERS,
    _budget_projection,
    _creator_lookup,
    _early_buyer_targets,
    _is_buy_event,
    _normalize_launch_rows,
    _target_quality,
    _top_holder_targets,
)


REPORT_ID = "aligned_p0_creator_metadata_repair_v0"
DEFAULT_SUMMARY_PATH = data_lake_path(
    "data",
    "backtests",
    "diagnostics",
    "reports",
    "aligned_p0_medium_scaleup",
    "aligned_p0_medium_scaleup_summary.json",
)
DEFAULT_STRUCTURAL_FEATURES_PATH = data_lake_path(
    "data",
    "backtests",
    "structural_enrichment",
    "aligned_p0_medium_structural_features.parquet",
)
DEFAULT_ALIGNED_TARGET_PATH = data_lake_path("data", "backtests", "structural_enrichment", "aligned_p0_medium_targets.csv")
DEFAULT_OUTPUT_ROOT = data_lake_path()
DEFAULT_STATUS_PATH = Path("theses/ALIGNED_P0_CREATOR_METADATA_REPAIR_STATUS.md")
DEFAULT_REPO_LOCAL_ARTIFACTS = [
    Path("data/backtests/diagnostics/reports/program_signature_discovery_plan.json"),
    Path("data/backtests/diagnostics/research_dataset_price_quality_gated.jsonl"),
]


def build_aligned_p0_creator_metadata_repair(
    *,
    summary_path: Path | str = DEFAULT_SUMMARY_PATH,
    structural_features_path: Path | str = DEFAULT_STRUCTURAL_FEATURES_PATH,
    aligned_target_path: Path | str = DEFAULT_ALIGNED_TARGET_PATH,
    universe_path: Path | str = DEFAULT_UNIVERSE_PATH,
    creator_lookup_paths: list[Path | str] | None = None,
    event_paths: list[Path | str] | None = None,
    repo_root: Path | str = Path("."),
    repo_local_artifacts: list[Path | str] | None = None,
    output_root: Path | str = DEFAULT_OUTPUT_ROOT,
    status_path: Path | str = DEFAULT_STATUS_PATH,
    second_run_per_tier: int = 50,
    credit_cap: int = 100_000,
) -> tuple[dict[str, Any], dict[str, Path]]:
    started = time.time()
    root = Path(output_root)
    paths = _output_paths(root)
    for directory in (paths["report_dir"], paths["structural_dir"], paths["manifest_dir"]):
        directory.mkdir(parents=True, exist_ok=True)

    summary = _read_json(summary_path)
    structural_rows = _read_records(structural_features_path)
    target_rows = _read_csv(aligned_target_path)
    creator_paths = creator_lookup_paths or DEFAULT_CREATOR_LOOKUP_PATHS
    creator_index = _creator_candidates(creator_paths)
    repaired_rows, recovery_preview = _repair_creator_rows(structural_rows, creator_index)
    joined_preview = _repaired_join_preview(structural_rows, repaired_rows)
    overlap_rows = _overlap_failure_rows(structural_rows, repaired_rows)
    second_plan, second_estimate = _second_run_plan(
        universe_path=universe_path,
        creator_lookup_paths=creator_paths,
        event_paths=event_paths or _event_paths_from_summary(summary),
        existing_rows=structural_rows,
        per_tier=second_run_per_tier,
        credit_cap=credit_cap,
    )
    cleanup = _cleanup_repo_local_artifacts(
        repo_root=Path(repo_root),
        artifacts=repo_local_artifacts if repo_local_artifacts is not None else DEFAULT_REPO_LOCAL_ARTIFACTS,
        output_root=root,
    )

    audit = _creator_audit(structural_rows, repaired_rows, target_rows)
    recovery = _recovery_summary(repaired_rows)
    overlap = _overlap_summary(overlap_rows, summary)
    report = {
        "report_id": REPORT_ID,
        "report_type": "aligned_p0_creator_metadata_repair",
        "methodology_flags": [
            "research_only",
            "data_quality_only",
            "storage_hygiene_only",
            "no_helius_calls",
            "no_network_calls",
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
        "network_calls_made": 0,
        "execution": {"mode": "offline_repair", "started_at": _timestamp(int(started)), "elapsed_seconds": round(time.time() - started, 3)},
        "input_paths": {
            "summary_path": str(summary_path),
            "structural_features_path": str(structural_features_path),
            "aligned_target_path": str(aligned_target_path),
            "universe_path": str(universe_path),
            "creator_lookup_paths": [str(path) for path in creator_paths],
            "event_paths": [str(path) for path in (event_paths or _event_paths_from_summary(summary))],
        },
        "creator_audit": audit,
        "creator_recovery": recovery,
        "overlap_failure_audit": overlap,
        "repo_local_artifact_cleanup": cleanup,
        "second_run_plan": second_estimate,
        "warnings": _warnings(audit, recovery, overlap, cleanup, second_estimate),
        "outputs": {key: str(path) for key, path in paths.items() if key.endswith("_path")},
    }

    outputs = _write_outputs(
        report=report,
        paths=paths,
        repaired_rows=repaired_rows,
        recovery_preview=recovery_preview,
        joined_preview=joined_preview,
        overlap_rows=overlap_rows,
        second_plan=second_plan,
        cleanup=cleanup,
        status_path=Path(status_path),
    )
    return report, outputs


def _output_paths(root: Path) -> dict[str, Path]:
    report_dir = root / "data" / "backtests" / "diagnostics" / "reports" / "aligned_p0_creator_metadata_repair"
    structural_dir = root / "data" / "backtests" / "structural_enrichment"
    manifest_dir = root / "manifests"
    return {
        "report_dir": report_dir,
        "structural_dir": structural_dir,
        "manifest_dir": manifest_dir,
        "audit_json_path": report_dir / "aligned_p0_creator_metadata_audit.json",
        "audit_md_path": report_dir / "aligned_p0_creator_metadata_audit.md",
        "recovery_preview_path": report_dir / "creator_recovery_preview.csv",
        "repaired_parquet_path": structural_dir / "aligned_p0_medium_creator_metadata_repaired.parquet",
        "repaired_jsonl_path": structural_dir / "aligned_p0_medium_creator_metadata_repaired.jsonl",
        "repaired_join_preview_path": report_dir / "aligned_p0_repaired_join_preview.csv",
        "overlap_failure_audit_path": report_dir / "all_three_overlap_failure_audit.csv",
        "second_run_targets_path": report_dir / "aligned_p0_second_run_targets.csv",
        "second_run_estimate_path": report_dir / "aligned_p0_second_run_dry_run_estimate.json",
        "cleanup_report_json_path": manifest_dir / "repo_local_artifact_cleanup_report.json",
        "cleanup_report_md_path": manifest_dir / "repo_local_artifact_cleanup_report.md",
    }


def _creator_candidates(paths: list[Path | str]) -> dict[str, list[dict[str, Any]]]:
    candidates: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for path in paths:
        source = _source_label(path)
        for row in _iter_jsonl(path):
            mint = row.get("mint") or row.get("token_mint")
            creator = row.get("creator_deployer") or row.get("creator") or row.get("deployer")
            if not mint and isinstance(row.get("metadata_json"), dict):
                mint = row["metadata_json"].get("mint")
            if not creator and isinstance(row.get("metadata_json"), dict):
                creator = row["metadata_json"].get("creator") or row["metadata_json"].get("creator_deployer")
            if mint and creator:
                candidates[str(mint)].append({"creator": str(creator), "source": source, "path": str(path)})
    return dict(candidates)


def _repair_creator_rows(rows: list[dict[str, Any]], creator_index: dict[str, list[dict[str, Any]]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    repaired = []
    preview = []
    for row in rows:
        original = _clean_creator(row.get("creator"))
        mint = str(row.get("mint") or "")
        candidates = creator_index.get(mint, [])
        unique = sorted({candidate["creator"] for candidate in candidates if candidate.get("creator")})
        source = candidates[0]["source"] if candidates else None
        if original:
            repaired_creator = original
            classification = "already_known_creator"
            confidence = "existing"
            missing = None
            reason = "creator_present_in_aligned_structural_features"
        elif len(unique) == 1:
            repaired_creator = unique[0]
            classification = source or "recovered_from_sidecar"
            confidence = "high"
            missing = None
            reason = f"single_creator_for_mint_from_{classification}"
        elif len(unique) > 1:
            repaired_creator = None
            classification = "ambiguous_multiple_creators"
            confidence = "none"
            missing = "ambiguous_multiple_creators"
            reason = "multiple_distinct_creators_for_mint"
        else:
            repaired_creator = None
            classification = "truly_missing_creator"
            confidence = "none"
            missing = "truly_missing_creator"
            reason = "no_local_creator_mapping_found"
        out = {
            "launch_id": row.get("launch_id"),
            "mint": mint,
            "original_creator": original,
            "repaired_creator": repaired_creator,
            "creator_recovery_source": classification,
            "creator_recovery_confidence": confidence,
            "creator_recovery_reason": reason,
            "creator_recovery_missing_reason": missing,
        }
        repaired.append(out)
        preview.append({**out, "candidate_creators": "|".join(unique)})
    return repaired, preview


def _creator_audit(structural_rows: list[dict[str, Any]], repaired_rows: list[dict[str, Any]], target_rows: list[dict[str, Any]]) -> dict[str, Any]:
    before_unknown = [row for row in structural_rows if not _clean_creator(row.get("creator"))]
    after_unknown = [row for row in repaired_rows if not row.get("repaired_creator")]
    repaired_by_launch = {row["launch_id"]: row for row in repaired_rows}
    all_three_known = 0
    all_three_unknown = 0
    for row in structural_rows:
        if _truthy(row.get("has_all_three_p0_layers")):
            if (repaired_by_launch.get(row.get("launch_id")) or {}).get("repaired_creator"):
                all_three_known += 1
            else:
                all_three_unknown += 1
    return {
        "selected_launches": len(structural_rows),
        "target_rows": len(target_rows),
        "known_creator_count_before": len(structural_rows) - len(before_unknown),
        "unknown_creator_count_before": len(before_unknown),
        "unknown_creator_share_before_pct": _pct(len(before_unknown), len(structural_rows)),
        "known_creator_count_after": len(structural_rows) - len(after_unknown),
        "unknown_creator_count_after": len(after_unknown),
        "unknown_creator_share_after_pct": _pct(len(after_unknown), len(structural_rows)),
        "unknown_creator_count_by_milestone_tier": dict(Counter(row.get("milestone_tier") or "unknown" for row in before_unknown)),
        "unknown_creator_count_by_date": dict(Counter(str(row.get("launch_date") or _date_from_ts(row.get("launch_ts"))) for row in before_unknown)),
        "unknown_creator_count_by_source_dataset": {"aligned_p0_medium_structural_features": len(before_unknown)},
        "unknown_creator_count_by_enrichment_layer": _unknown_by_layer(before_unknown),
        "all_three_layer_count_with_known_creator": all_three_known,
        "all_three_layer_count_with_unknown_creator": all_three_unknown,
    }


def _recovery_summary(repaired_rows: list[dict[str, Any]]) -> dict[str, Any]:
    recovered = [row for row in repaired_rows if not row.get("original_creator") and row.get("repaired_creator")]
    unknown_after = [row for row in repaired_rows if not row.get("repaired_creator")]
    return {
        "recovered_count": len(recovered),
        "unknown_count_after": len(unknown_after),
        "classification_counts": dict(Counter(row.get("creator_recovery_source") for row in repaired_rows)),
        "confidence_counts": dict(Counter(row.get("creator_recovery_confidence") for row in repaired_rows)),
    }


def _overlap_failure_rows(structural_rows: list[dict[str, Any]], repaired_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    repaired_by_launch = {row["launch_id"]: row for row in repaired_rows}
    output = []
    for row in structural_rows:
        repair = repaired_by_launch.get(row.get("launch_id"), {})
        has_top = _truthy(row.get("has_top_holder_replay"))
        has_early = _truthy(row.get("has_early_buyer_wallet_history"))
        has_funder = _truthy(row.get("has_creator_funder_graph"))
        known_creator = bool(repair.get("repaired_creator"))
        if not known_creator:
            cause = "unknown_creator"
        elif has_top and has_early and has_funder:
            cause = "none"
        elif not has_early:
            cause = "no_early_buyers_before_trigger"
        elif not has_top:
            cause = "no_top_holder_replay_target"
        elif not has_funder:
            cause = "no_creator_funder_target"
        else:
            cause = "other"
        output.append(
            {
                "launch_id": row.get("launch_id"),
                "mint": row.get("mint"),
                "milestone_tier": row.get("milestone_tier"),
                "known_creator": known_creator,
                "has_top_holder_layer": has_top,
                "has_early_buyer_layer": has_early,
                "has_creator_funder_layer": has_funder,
                "missing_top_holder_reason": None if has_top else "no_top_holder_replay_target",
                "missing_early_buyer_reason": None if has_early else "no_early_buyers_before_trigger",
                "missing_creator_funder_reason": None if has_funder else ("unknown_creator" if not known_creator else "no_creator_funder_target"),
                "missing_overlap_cause": cause,
            }
        )
    return output


def _overlap_summary(overlap_rows: list[dict[str, Any]], summary: dict[str, Any]) -> dict[str, Any]:
    before = (summary.get("overlap_audit") or {}).get("launches_with_all_three_p0_layers")
    all_three = [row for row in overlap_rows if row["has_top_holder_layer"] and row["has_early_buyer_layer"] and row["has_creator_funder_layer"]]
    return {
        "all_three_layer_overlap_before": before if before is not None else len(all_three),
        "all_three_layer_overlap_after_metadata_repair": len(all_three),
        "cause_counts": dict(Counter(row["missing_overlap_cause"] for row in overlap_rows if row["missing_overlap_cause"] != "none")),
    }


def _second_run_plan(
    *,
    universe_path: Path | str,
    creator_lookup_paths: list[Path | str],
    event_paths: list[Path | str],
    existing_rows: list[dict[str, Any]],
    per_tier: int,
    credit_cap: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    universe = _read_json(universe_path)
    launch_rows = _normalize_launch_rows(universe.get("launch_feature_rows") or [], _creator_lookup(creator_lookup_paths))
    all_three_existing = {row.get("launch_id") for row in existing_rows if _truthy(row.get("has_all_three_p0_layers"))}
    early_counts = _early_event_counts(launch_rows, event_paths)
    selected = []
    seen_mints: set[str] = set()
    for tier in TARGET_TIERS:
        candidates = [
            row
            for row in launch_rows
            if row["milestone_tier"] == tier
            and row.get("creator")
            and row.get("crossing_20k_age") is not None
            and early_counts.get(row["mint"], 0) > 0
            and row.get("launch_id") not in all_three_existing
        ]
        candidates = sorted(candidates, key=lambda row: (row.get("launch_date") or "", row.get("creator") or "", row.get("launch_ts") or 0, row["mint"]))
        tier_selected = []
        date_counts: Counter[str] = Counter()
        creator_counts: Counter[str] = Counter()
        for row in candidates:
            if row["mint"] in seen_mints:
                continue
            if date_counts[row["launch_date"]] >= max(1, per_tier // 4):
                continue
            if creator_counts[row["creator"]] >= max(1, per_tier // 5):
                continue
            tier_selected.append(row)
            seen_mints.add(row["mint"])
            date_counts[row["launch_date"]] += 1
            creator_counts[row["creator"]] += 1
            if len(tier_selected) >= per_tier:
                break
        if len(tier_selected) < per_tier:
            for row in candidates:
                if row["mint"] in seen_mints:
                    continue
                tier_selected.append(row)
                seen_mints.add(row["mint"])
                if len(tier_selected) >= per_tier:
                    break
        selected.extend({**row, "early_buyer_event_count_before_20k": early_counts.get(row["mint"], 0), "reason_selected": "known_creator_with_trigger_and_early_buyer_support"} for row in tier_selected)
    top_targets = _top_holder_targets(selected)
    early_targets = _early_buyer_targets(selected, event_paths, max_wallets=3_000)
    funder_targets = [{"creator": row["creator"], "launch_id": row["launch_id"]} for row in selected if row.get("creator")]
    budget = _budget_projection(
        selected=selected,
        early_targets=early_targets,
        top_targets=top_targets,
        funder_targets=funder_targets,
        credit_cap=credit_cap,
    )
    quality = _target_quality(selected) if selected else {
        "top_date_share_pct": 0.0,
        "top_creator_share_pct": 0.0,
        "top_3_creator_share_pct": 0.0,
        "unknown_creator_share_pct": 0.0,
        "unique_dates": 0,
        "unique_creators": 0,
    }
    minimum_viable_target_count = per_tier * len(TARGET_TIERS)
    estimate = {
        "target_count": len(selected),
        "minimum_viable_target_count": minimum_viable_target_count,
        "known_creator_share_pct": _pct(sum(1 for row in selected if row.get("creator")), len(selected)),
        "projected_all_three_layer_eligibility": len(selected),
        "tier_balance": dict(Counter(row["milestone_tier"] for row in selected)),
        "date_balance": {"unique_dates": len({row["launch_date"] for row in selected}), "top_date_share_pct": quality.get("top_date_share_pct", 0.0)},
        "creator_balance": {
            "unique_creators": len({row["creator"] for row in selected if row.get("creator")}),
            "top_creator_share_pct": quality.get("top_creator_share_pct", 0.0),
            "top_3_creator_share_pct": quality.get("top_3_creator_share_pct", 0.0),
        },
        "projected_requests": budget["projected_requests"],
        "projected_credits": budget["projected_credits"],
        "request_ceiling_status": budget["request_ceiling_status"],
        "another_helius_run_recommended": len(selected) >= minimum_viable_target_count and budget["projected_credits"] <= credit_cap,
    }
    return selected, estimate


def _early_event_counts(launch_rows: list[dict[str, Any]], event_paths: list[Path | str]) -> dict[str, int]:
    by_mint = {row["mint"]: row for row in launch_rows}
    counts: Counter[str] = Counter()
    for event in _iter_jsonl_multi(event_paths):
        mint = event.get("token_mint") or event.get("mint")
        if not mint or str(mint) not in by_mint or not _is_buy_event(event):
            continue
        row = by_mint[str(mint)]
        block_time = _int_or_none(event.get("block_time") or event.get("timestamp"))
        if block_time is None:
            continue
        age = block_time - int(row["launch_ts"])
        if 0 <= age <= int(row.get("crossing_20k_age") or 0):
            counts[str(mint)] += 1
    return dict(counts)


def _cleanup_repo_local_artifacts(*, repo_root: Path, artifacts: list[Path | str], output_root: Path) -> dict[str, Any]:
    manifest_dir = output_root / "manifests" / "repo_local_artifacts"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for artifact in artifacts:
        source = Path(artifact)
        if not source.is_absolute():
            source = repo_root / source
        rel = source.relative_to(repo_root) if _is_relative_to(source, repo_root) else Path(source.name)
        orico_path = output_root / rel
        row = {
            "repo_path": str(source),
            "relative_path": str(rel),
            "exists": source.exists(),
            "size_bytes": source.stat().st_size if source.exists() else 0,
            "classification": "missing",
            "needed_by_tests": False,
            "already_exists_on_orico": orico_path.exists(),
            "action_taken": "none",
            "checksum_verified": False,
            "orico_path": str(orico_path),
        }
        if not source.exists() and orico_path.exists():
            row["classification"] = "generated_repo_local_artifact"
            row["action_taken"] = "repo_duplicate_absent_or_already_moved_to_orico"
            row["checksum_verified"] = True
        elif source.exists():
            row["classification"] = _artifact_classification(rel, source)
            if row["classification"] == "generated_repo_local_artifact":
                source_hash = _sha256(source)
                orico_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, orico_path)
                row["checksum_verified"] = source_hash == _sha256(orico_path)
                if row["checksum_verified"]:
                    source.unlink()
                    row["action_taken"] = "moved_to_orico_and_removed_repo_duplicate"
                else:
                    row["action_taken"] = "copied_to_orico_but_left_repo_copy_checksum_mismatch"
            else:
                row["action_taken"] = "left_in_place_manual_review"
        rows.append(row)
    return {"artifacts": rows, "manual_review_required": any(row["action_taken"].endswith("manual_review") for row in rows)}


def _artifact_classification(rel: Path, source: Path) -> str:
    text = str(rel)
    if text.startswith("data/backtests/diagnostics/") and source.suffix in {".json", ".jsonl", ".csv", ".parquet"}:
        return "generated_repo_local_artifact"
    return "manual_review_required"


def _write_outputs(
    *,
    report: dict[str, Any],
    paths: dict[str, Path],
    repaired_rows: list[dict[str, Any]],
    recovery_preview: list[dict[str, Any]],
    joined_preview: list[dict[str, Any]],
    overlap_rows: list[dict[str, Any]],
    second_plan: list[dict[str, Any]],
    cleanup: dict[str, Any],
    status_path: Path,
) -> dict[str, Path]:
    paths["audit_json_path"].write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    paths["audit_md_path"].write_text(_markdown(report), encoding="utf-8")
    _write_jsonl(paths["repaired_jsonl_path"], repaired_rows)
    _write_parquet(repaired_rows, paths["repaired_parquet_path"])
    _write_csv(recovery_preview, paths["recovery_preview_path"])
    _write_csv(joined_preview, paths["repaired_join_preview_path"])
    _write_csv(overlap_rows, paths["overlap_failure_audit_path"])
    _write_csv(second_plan, paths["second_run_targets_path"])
    paths["second_run_estimate_path"].write_text(json.dumps(report["second_run_plan"], indent=2, sort_keys=True), encoding="utf-8")
    paths["cleanup_report_json_path"].write_text(json.dumps(cleanup, indent=2, sort_keys=True), encoding="utf-8")
    paths["cleanup_report_md_path"].write_text(_cleanup_markdown(cleanup), encoding="utf-8")
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(_status_markdown(report, paths), encoding="utf-8")
    return {
        **{key: value for key, value in paths.items() if key.endswith("_path")},
        "status_path": status_path,
    }


def _repaired_join_preview(structural_rows: list[dict[str, Any]], repaired_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    repaired_by_launch = {row["launch_id"]: row for row in repaired_rows}
    return [
        {
            **row,
            "repaired_creator": (repaired_by_launch.get(row.get("launch_id")) or {}).get("repaired_creator"),
            "creator_recovery_source": (repaired_by_launch.get(row.get("launch_id")) or {}).get("creator_recovery_source"),
        }
        for row in structural_rows
    ]


def _unknown_by_layer(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "has_top_holder_layer": sum(1 for row in rows if _truthy(row.get("has_top_holder_replay"))),
        "has_early_buyer_layer": sum(1 for row in rows if _truthy(row.get("has_early_buyer_wallet_history"))),
        "has_creator_funder_layer": sum(1 for row in rows if _truthy(row.get("has_creator_funder_graph"))),
        "has_all_three_layers": sum(1 for row in rows if _truthy(row.get("has_all_three_p0_layers"))),
    }


def _warnings(audit: dict[str, Any], recovery: dict[str, Any], overlap: dict[str, Any], cleanup: dict[str, Any], second_plan: dict[str, Any]) -> list[str]:
    warnings = []
    if audit["unknown_creator_count_after"] > 0:
        warnings.append("creator_metadata_still_incomplete")
    if overlap["all_three_layer_overlap_after_metadata_repair"] < audit["selected_launches"]:
        warnings.append("all_three_overlap_still_incomplete")
    if cleanup.get("manual_review_required"):
        warnings.append("repo_local_artifact_manual_review_required")
    if not second_plan.get("another_helius_run_recommended"):
        warnings.append("second_aligned_run_not_recommended_yet")
    return warnings


def _markdown(report: dict[str, Any]) -> str:
    audit = report["creator_audit"]
    recovery = report["creator_recovery"]
    overlap = report["overlap_failure_audit"]
    second = report["second_run_plan"]
    return "\n".join(
        [
            "# Aligned P0 Creator Metadata Repair",
            "",
            f"- Selected launches: `{audit['selected_launches']}`",
            f"- Unknown creators before: `{audit['unknown_creator_count_before']}`",
            f"- Recovered creators: `{recovery['recovered_count']}`",
            f"- Unknown creators after: `{audit['unknown_creator_count_after']}`",
            f"- All-three overlap before: `{overlap['all_three_layer_overlap_before']}`",
            f"- All-three overlap after metadata repair: `{overlap['all_three_layer_overlap_after_metadata_repair']}`",
            f"- Second-run target count: `{second['target_count']}`",
            f"- Second-run projected credits: `{second['projected_credits']}`",
            f"- Second aligned run recommended: `{second['another_helius_run_recommended']}`",
            f"- Warnings: `{report['warnings']}`",
            "",
            "No Helius calls, thesis, validation, backtest, paper/live trading, trading logic, optimization, grid search, or ML was run.",
        ]
    ) + "\n"


def _cleanup_markdown(cleanup: dict[str, Any]) -> str:
    lines = ["# Repo-Local Artifact Cleanup", ""]
    for row in cleanup["artifacts"]:
        lines.append(f"- `{row['relative_path']}`: {row['action_taken']} ({row['classification']})")
    return "\n".join(lines) + "\n"


def _status_markdown(report: dict[str, Any], paths: dict[str, Path]) -> str:
    return "\n".join(
        [
            "# Aligned P0 Creator Metadata Repair Status",
            "",
            "## Why Repair Was Needed",
            "The aligned P0 medium scale-up had low creator coverage and low all-three structural overlap.",
            "",
            "## Creator Coverage",
            f"- Unknown before: `{report['creator_audit']['unknown_creator_count_before']}`",
            f"- Recovered: `{report['creator_recovery']['recovered_count']}`",
            f"- Unknown after: `{report['creator_audit']['unknown_creator_count_after']}`",
            "",
            "## All-Three Overlap",
            f"- Before: `{report['overlap_failure_audit']['all_three_layer_overlap_before']}`",
            f"- After metadata repair: `{report['overlap_failure_audit']['all_three_layer_overlap_after_metadata_repair']}`",
            f"- Cause counts: `{report['overlap_failure_audit']['cause_counts']}`",
            "",
            "## Repo-Local Artifact Cleanup",
            f"- Artifacts handled: `{len(report['repo_local_artifact_cleanup']['artifacts'])}`",
            "",
            "## Second Aligned Target Plan",
            f"- Target count: `{report['second_run_plan']['target_count']}`",
            f"- Known creator share: `{report['second_run_plan']['known_creator_share_pct']}`",
            f"- Projected credits: `{report['second_run_plan']['projected_credits']}`",
            f"- Recommended: `{report['second_run_plan']['another_helius_run_recommended']}`",
            "",
            "## Next Action",
            "Review the second-run target plan. Do not execute another Helius run until the plan is approved.",
            "",
            "## Reports",
            f"- Audit JSON: {paths['audit_json_path']}",
            f"- Audit Markdown: {paths['audit_md_path']}",
            f"- Second-run targets: {paths['second_run_targets_path']}",
            f"- Cleanup report: {paths['cleanup_report_json_path']}",
        ]
    ) + "\n"


def _source_label(path: Path | str) -> str:
    name = str(path).lower()
    if "creation_census" in name or "create" in name:
        return "recovered_from_create_event"
    if "launch" in name and "census" in name:
        return "recovered_from_launch_census"
    if "event" in name:
        return "recovered_from_normalized_event"
    if "raw" in name or "transaction" in name:
        return "recovered_from_raw_transaction"
    return "recovered_from_sidecar"


def _event_paths_from_summary(summary: dict[str, Any]) -> list[Path]:
    paths = (summary.get("input_paths") or {}).get("event_paths") or (summary.get("dataset") or {}).get("event_paths") or []
    return [Path(path) for path in paths]


def _read_json(path: Path | str) -> Any:
    value = Path(path)
    if not value.exists():
        return {}
    return json.loads(value.read_text(encoding="utf-8"))


def _read_csv(path: Path | str) -> list[dict[str, Any]]:
    value = Path(path)
    if not value.exists():
        return []
    with value.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _read_records(path: Path | str) -> list[dict[str, Any]]:
    value = Path(path)
    if not value.exists():
        return []
    if value.suffix == ".parquet":
        import pandas as pd

        return pd.read_parquet(value).to_dict(orient="records")
    with value.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _iter_jsonl(path: Path | str):
    value = Path(path)
    if not value.exists():
        return
    with value.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if text:
                yield json.loads(text)


def _iter_jsonl_multi(paths: list[Path | str]):
    for path in paths:
        yield from _iter_jsonl(path)


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


def _write_parquet(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import pandas as pd
    except Exception:
        path.with_suffix(".parquet.unavailable.json").write_text(json.dumps({"row_count": len(rows)}, indent=2), encoding="utf-8")
        return
    pd.DataFrame(rows).to_parquet(path, index=False)


def _clean_creator(value: Any) -> str | None:
    if value in (None, "", "None", "nan"):
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    return str(value)


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"true", "1", "yes"}


def _date_from_ts(value: Any) -> str:
    parsed = _int_or_none(value)
    return datetime.fromtimestamp(parsed, tz=timezone.utc).date().isoformat() if parsed is not None else "unknown"


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


def _pct(numerator: int, denominator: int) -> float:
    return round(numerator / denominator * 100, 4) if denominator else 0.0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
