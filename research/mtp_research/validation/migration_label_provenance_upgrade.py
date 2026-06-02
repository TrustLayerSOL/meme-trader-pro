"""Offline migration-label provenance audit and acquisition plan."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


REPORT_ID = "migration_label_provenance_upgrade"
READINESS_READY = "migration_label_provenance_ready_for_t008_review"
READINESS_NEEDS_EVIDENCE = "migration_label_provenance_needs_non_dexscreener_evidence"
READINESS_BLOCKED = "migration_label_provenance_blocked"


def build_migration_label_provenance_upgrade_report(
    *,
    candidates_path: Path | str,
    migration_labels_path: Path | str,
    max_targets: int = 250,
) -> dict[str, Any]:
    candidates = _read_jsonl(candidates_path)
    labels = _read_jsonl(migration_labels_path)
    candidates_by_mint = {_mint(row): row for row in candidates if _mint(row)}
    classified = [_classify_label(row, candidates_by_mint) for row in labels if _is_positive_label(row)]
    source_quality_counts = dict(Counter(row["source_quality"] for row in classified))
    timestamp_missing_counts = dict(
        Counter(row["source_quality"] for row in classified if row.get("migration_time") is None)
    )
    t008_blockers = _t008_blocker_summary(classified)
    plan = _build_acquisition_plan(classified, candidates_by_mint, max_targets)
    readiness = _readiness(t008_blockers, plan, classified)
    return {
        "report_id": REPORT_ID,
        "scope": {
            "candidates_path": str(candidates_path),
            "migration_labels_path": str(migration_labels_path),
            "candidate_count": len(candidates),
            "positive_label_count": len(classified),
            "max_targets": max_targets,
        },
        "methodology_flags": [
            "offline_only",
            "no_network_calls",
            "no_helius_calls",
            "no_thesis_cycle",
            "no_backtest",
            "no_walk_forward_validation",
            "no_thesis_promotion",
            "no_trading_rules",
            "no_profitability_claims",
            "no_threshold_optimization",
            "no_grid_search",
            "no_ml_black_boxes",
        ],
        "source_quality_counts": source_quality_counts,
        "timestamp_missing_counts": timestamp_missing_counts,
        "creator_coverage": _creator_coverage(classified),
        "source_quality_examples": _examples_by_quality(classified),
        "t008_blocker_summary": t008_blockers,
        "acquisition_plan": plan,
        "readiness_classification": readiness,
        "next_recommendation": _next_recommendation(readiness),
        "warning_flags": _warning_flags(t008_blockers, plan),
    }


def write_migration_label_provenance_upgrade_outputs(
    report: dict[str, Any],
    *,
    output_dir: Path | str,
    status_path: Path | str,
) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "migration_label_provenance_upgrade_summary.json"
    markdown_path = output / "migration_label_provenance_upgrade_summary.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(_markdown_summary(report), encoding="utf-8")
    status = Path(status_path)
    status.parent.mkdir(parents=True, exist_ok=True)
    status.write_text(_status_markdown(report, markdown_path, json_path), encoding="utf-8")
    return {"json_summary_path": json_path, "markdown_summary_path": markdown_path, "status_path": status}


def _classify_label(row: dict[str, Any], candidates_by_mint: dict[str, dict[str, Any]]) -> dict[str, Any]:
    mint = _mint(row)
    candidate = candidates_by_mint.get(mint or "", {})
    source = str(row.get("migration_source") or "")
    pumpfun = bool(row.get("pumpfun_migrate_event_observed")) or "pumpfun_migrate" in source or "migrate_log" in source
    dex = bool(row.get("dex_pair_detected")) or "dexscreener" in source
    if pumpfun:
        quality = "ground_truth_pumpfun_migrate"
    elif dex:
        quality = "source_proxy_dexscreener_pair"
    else:
        quality = "unverified_combined_label"
    migration_time = row.get("migration_time")
    return {
        "mint": mint,
        "launch_id": row.get("launch_id") or candidate.get("launch_id"),
        "creator": row.get("creator") or _creator(candidate),
        "migration_time": migration_time,
        "migration_signature": row.get("migration_signature"),
        "migration_source": source or quality,
        "source_quality": quality,
        "timestamp_available": migration_time is not None,
        "has_pumpfun_signature": bool(row.get("migration_signature")) and pumpfun,
        "has_dex_pair_proxy": dex,
        "launch_ts": row.get("launch_ts") or candidate.get("launch_ts"),
    }


def _build_acquisition_plan(
    classified: list[dict[str, Any]],
    candidates_by_mint: dict[str, dict[str, Any]],
    max_targets: int,
) -> dict[str, Any]:
    target_rows = []
    for row in classified:
        if row["source_quality"] == "ground_truth_pumpfun_migrate" and row["timestamp_available"]:
            continue
        reason = "dexscreener_proxy_needs_pumpfun_confirmation"
        if not row["timestamp_available"]:
            reason = "missing_timestamp_needs_confirmation"
        candidate = candidates_by_mint.get(row.get("mint") or "", {})
        target_rows.append(
            {
                "mint": row.get("mint"),
                "launch_id": row.get("launch_id"),
                "creator": row.get("creator"),
                "launch_ts": row.get("launch_ts"),
                "current_source_quality": row["source_quality"],
                "reason_selected": reason,
                "proposed_window": "7d_post_launch",
                "preferred_evidence": "pumpfun_migrate_transaction_or_pumpswap_creation_transaction",
                "bonding_curve": (candidate.get("metadata_json") or {}).get("bonding_curve"),
                "associated_bonding_curve": (candidate.get("metadata_json") or {}).get("associated_bonding_curve"),
            }
        )
    target_rows.sort(key=lambda row: (_reason_priority(row["reason_selected"]), row.get("launch_ts") or 0, row.get("mint") or ""))
    selected = target_rows[:max_targets]
    return {
        "network_calls_made": 0,
        "selected_targets": selected,
        "selected_target_count": len(selected),
        "candidate_target_count": len(target_rows),
        "estimated_request_equivalent_calls": {
            "base": len(selected),
            "high": len(selected) * 3,
            "assumption": "address-window or mint-window fetch, capped at 3 request-equivalent calls per target",
        },
        "recommended_dry_run_command": (
            "./trading_env/bin/python -m research.mtp_research.validation.run_migration_graduation_enrichment_collection "
            f"--mint-limit {len(selected)} --window 7d --max-signature-pages-per-mint 3 --max-transactions-per-mint 100"
        ),
        "recommended_execute_command": (
            "./trading_env/bin/python -m research.mtp_research.validation.run_migration_graduation_enrichment_collection "
            f"--mint-limit {len(selected)} --window 7d --max-signature-pages-per-mint 3 --max-transactions-per-mint 100 --execute"
        ),
        "stop_go_gates": [
            "execute only after reviewing selected target list",
            "stop if provider errors occur",
            "stop if projected requests exceed explicit ceiling",
            "do not use DexScreener proxy as ground-truth Pump.fun migration",
        ],
    }


def _t008_blocker_summary(classified: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(classified)
    ground = sum(1 for row in classified if row["source_quality"] == "ground_truth_pumpfun_migrate")
    proxy = sum(1 for row in classified if row["source_quality"] == "source_proxy_dexscreener_pair")
    missing_ts = sum(1 for row in classified if not row["timestamp_available"])
    return {
        "positive_label_count": total,
        "ground_truth_pumpfun_migrate_count": ground,
        "dexscreener_proxy_count": proxy,
        "missing_timestamp_count": missing_ts,
        "ground_truth_share": ground / total if total else 0,
        "dexscreener_proxy_share": proxy / total if total else 0,
        "depends_mainly_on_proxy_labels": (proxy / total if total else 0) >= 0.5 and proxy > ground,
        "non_dexscreener_evidence_gap": max(proxy - ground, 0),
    }


def _creator_coverage(classified: list[dict[str, Any]]) -> dict[str, Any]:
    creators_by_quality: dict[str, set[str]] = defaultdict(set)
    for row in classified:
        if row.get("creator"):
            creators_by_quality[row["source_quality"]].add(row["creator"])
    return {
        quality: len(creators)
        for quality, creators in sorted(creators_by_quality.items())
    }


def _examples_by_quality(classified: list[dict[str, Any]], limit: int = 5) -> dict[str, list[dict[str, Any]]]:
    examples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in sorted(classified, key=lambda item: (item["source_quality"], item.get("launch_ts") or 0, item.get("mint") or "")):
        bucket = examples[row["source_quality"]]
        if len(bucket) < limit:
            bucket.append(
                {
                    "mint": row.get("mint"),
                    "creator": row.get("creator"),
                    "migration_time": row.get("migration_time"),
                    "migration_source": row.get("migration_source"),
                }
            )
    return dict(examples)


def _readiness(blockers: dict[str, Any], plan: dict[str, Any], classified: list[dict[str, Any]]) -> str:
    if not classified:
        return READINESS_BLOCKED
    if blockers["depends_mainly_on_proxy_labels"] or blockers["missing_timestamp_count"]:
        return READINESS_NEEDS_EVIDENCE
    if plan["selected_target_count"] == 0:
        return READINESS_READY
    return READINESS_NEEDS_EVIDENCE


def _warning_flags(blockers: dict[str, Any], plan: dict[str, Any]) -> list[str]:
    warnings = []
    if blockers["depends_mainly_on_proxy_labels"]:
        warnings.append("migration_labels_depend_mainly_on_dexscreener_proxy")
    if blockers["missing_timestamp_count"]:
        warnings.append("migration_labels_missing_timestamps")
    if plan["selected_target_count"]:
        warnings.append("non_dexscreener_confirmation_targets_available")
    if not warnings:
        warnings.append("no_immediate_provenance_blockers")
    return warnings


def _next_recommendation(readiness: str) -> str:
    if readiness == READINESS_READY:
        return "rerun T008 robustness review with upgraded provenance labels"
    if readiness == READINESS_NEEDS_EVIDENCE:
        return "review selected targets, then run a bounded non-DexScreener migration confirmation collection"
    return "repair migration label inputs before further T008 work"


def _markdown_summary(report: dict[str, Any]) -> str:
    lines = [
        "# Migration Label Provenance Upgrade",
        "",
        f"- Readiness: `{report['readiness_classification']}`",
        f"- Positive labels: `{report['scope']['positive_label_count']}`",
        f"- Selected confirmation targets: `{report['acquisition_plan']['selected_target_count']}`",
        f"- Network calls made: `{report['acquisition_plan']['network_calls_made']}`",
        "",
        "## Source Quality Counts",
        "",
        *[f"- `{key}`: `{value}`" for key, value in sorted(report["source_quality_counts"].items())],
        "",
        "## T008 Blocker Summary",
        "",
        *[f"- `{key}`: `{value}`" for key, value in report["t008_blocker_summary"].items()],
        "",
        "## Next Recommendation",
        "",
        report["next_recommendation"],
    ]
    return "\n".join(lines) + "\n"


def _status_markdown(report: dict[str, Any], markdown_path: Path, json_path: Path) -> str:
    return "\n".join(
        [
            "# Migration Label Provenance Upgrade Status",
            "",
            f"- Readiness classification: `{report['readiness_classification']}`",
            f"- Ground-truth Pump.fun migrate labels: `{report['source_quality_counts'].get('ground_truth_pumpfun_migrate', 0)}`",
            f"- DexScreener proxy labels: `{report['source_quality_counts'].get('source_proxy_dexscreener_pair', 0)}`",
            f"- Selected confirmation targets: `{report['acquisition_plan']['selected_target_count']}`",
            f"- Estimated request-equivalent calls high: `{report['acquisition_plan']['estimated_request_equivalent_calls']['high']}`",
            "",
            "## Guardrails",
            "",
            "- No network calls were made.",
            "- No Helius calls were made.",
            "- No thesis was promoted.",
            "- No validation, walk-forward, backtest, or trading logic was run.",
            "- DexScreener pair detection remains proxy evidence only.",
            "",
            "## Next Recommendation",
            "",
            report["next_recommendation"],
            "",
            f"- Markdown summary: `{markdown_path}`",
            f"- JSON summary: `{json_path}`",
            "",
        ]
    )


def _is_positive_label(row: dict[str, Any]) -> bool:
    return bool(
        row.get("pumpfun_migrate_event_observed")
        or row.get("graduated_to_pumpswap")
        or row.get("migrated_to_raydium")
        or row.get("dex_pair_detected")
        or row.get("liquidity_pool_created_after_launch")
    )


def _mint(row: dict[str, Any]) -> str | None:
    value = row.get("mint") or row.get("token_mint")
    return str(value) if value else None


def _creator(row: dict[str, Any]) -> str | None:
    metadata = row.get("metadata_json") or {}
    value = row.get("creator") or row.get("creator_deployer") or metadata.get("creator_deployer")
    return str(value) if value else None


def _reason_priority(reason: str) -> int:
    if reason == "missing_timestamp_needs_confirmation":
        return 0
    return 1


def _read_jsonl(path: Path | str) -> list[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
