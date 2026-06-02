"""Positive-control probe for Pump.fun migration address strategies."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from research.mtp_research.data_paths import data_lake_path
from research.mtp_research.ingestion.helius_backfill import HeliusHistoricalAdapter
from research.mtp_research.ingestion.helius_models import HeliusBackfillRequest
from research.mtp_research.validation.migration_graduation_enrichment_collection import (
    _detect_migration_candidate,
    _window_seconds,
)


CLASSIFICATION_READY = "migration_positive_control_ready"
CLASSIFICATION_STRATEGY_FOUND = "migration_positive_control_strategy_found"
CLASSIFICATION_NOT_FOUND = "migration_positive_control_strategy_not_found"
CLASSIFICATION_BLOCKED = "migration_positive_control_blocked"

DEFAULT_CANDIDATES_PATH = data_lake_path(
    "data", "normalized", "launch_lifecycle_collected_classified", "launch_regime_candidates.jsonl"
)
DEFAULT_OUTPUT_DIR = data_lake_path(
    "data", "backtests", "diagnostics", "reports", "migration_positive_control_probe"
)
DEFAULT_KNOWN_MINT = "ER7HP8rTB6DBpXhYs7RBczpRYF23oHwsbwtonY5Xpump"
DEFAULT_KNOWN_SIGNATURE = "4Cdnaakz7MmVsRRQFasCLbo8LUKS4HaKWf4w7qp9Yf4UYfT7bxaJbCR8kW11h24zLAb4pii5b8oeQAyLN5r4vbCc"


def build_migration_positive_control_probe(
    *,
    candidates_path: Path | str = DEFAULT_CANDIDATES_PATH,
    known_mint: str = DEFAULT_KNOWN_MINT,
    known_signature: str = DEFAULT_KNOWN_SIGNATURE,
    window: str = "24h",
    max_signature_pages_per_strategy: int = 3,
    request_ceiling: int = 100,
    execute: bool = False,
    client: Any | None = None,
) -> dict[str, Any]:
    candidate = _find_candidate(Path(candidates_path), known_mint)
    if not candidate:
        return _blocked_report(candidates_path, known_mint, known_signature, "known_mint_missing_from_candidates")
    strategies = _strategies(candidate)
    base = {
        "report_id": "migration_positive_control_probe_v0",
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
        "execute": execute,
        "network_calls_used": 0,
        "helius_calls_used": 0,
        "known_mint": known_mint,
        "known_signature": known_signature,
        "window": window,
        "request_ceiling": request_ceiling,
        "candidate": candidate,
        "strategies": strategies,
        "guardrails": _guardrails(execute),
    }
    if not execute:
        return {
            **base,
            "classification": CLASSIFICATION_READY,
            "positive_control": {
                "known_signature_found": False,
                "best_strategy": None,
                "hydrated_exact_migration": False,
            },
            "strategy_results": [],
            "warnings": ["dry_run_only_no_network_calls"],
            "recommended_next_action": "run_bounded_positive_control_execute",
        }

    rpc = client or HeliusHistoricalAdapter.from_env()
    requests_used = 0
    strategy_results: list[dict[str, Any]] = []
    found_strategy: str | None = None
    hydrated_exact = False
    provider_errors: list[str] = []
    start_time = int(candidate["launch_ts"])
    end_time = start_time + _window_seconds(window)

    for strategy in strategies:
        if requests_used >= request_ceiling:
            break
        before = None
        signatures_seen: list[str] = []
        found = False
        try:
            for _ in range(max_signature_pages_per_strategy):
                if requests_used + 1 > request_ceiling:
                    break
                result = rpc.fetch_signatures_for_address(
                    HeliusBackfillRequest(
                        address=strategy["address"],
                        token_mint=known_mint,
                        role=f"migration_positive_control_{strategy['name']}",
                        start_time=start_time,
                        end_time=end_time,
                        before=before,
                        limit=1000,
                        include_failed=False,
                    )
                )
                requests_used += 1
                records = list(getattr(result, "records", []))
                signatures_seen.extend([record.signature for record in records if getattr(record, "signature", None)])
                if known_signature in signatures_seen:
                    found = True
                    found_strategy = strategy["name"]
                    break
                before = getattr(result, "next_before", None)
                if not before or not records:
                    break
        except Exception as exc:
            provider_errors.append(f"{strategy['name']}: {exc}")
        strategy_results.append(
            {
                "strategy": strategy["name"],
                "address": strategy["address"],
                "signature_pages_checked": min(max_signature_pages_per_strategy, requests_used),
                "signatures_seen": len(set(signatures_seen)),
                "known_signature_found": found,
            }
        )
        if found:
            break

    if found_strategy and requests_used + 1 <= request_ceiling:
        try:
            tx = rpc.fetch_transaction(known_signature)
            requests_used += 1
            detected = _detect_migration_candidate(known_signature, tx)
            hydrated_exact = bool(detected["pumpfun_migrate_event_observed"] and detected["migration_time"])
        except Exception as exc:
            provider_errors.append(f"hydrate_known_signature: {exc}")

    classification = _classification(found_strategy, hydrated_exact, provider_errors)
    return {
        **base,
        "classification": classification,
        "network_calls_used": requests_used,
        "helius_calls_used": requests_used,
        "positive_control": {
            "known_signature_found": found_strategy is not None,
            "best_strategy": found_strategy,
            "hydrated_exact_migration": hydrated_exact,
        },
        "strategy_results": strategy_results,
        "provider_errors": provider_errors,
        "warnings": _warnings(found_strategy, hydrated_exact, provider_errors),
        "recommended_next_action": _recommended_next_action(classification, found_strategy),
    }


def write_migration_positive_control_probe_outputs(report: dict[str, Any], *, output_dir: Path | str = DEFAULT_OUTPUT_DIR) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "migration_positive_control_probe.json"
    markdown_path = output / "migration_positive_control_probe.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(_markdown(report), encoding="utf-8")
    return {"json_path": json_path, "markdown_path": markdown_path}


def _find_candidate(candidates_path: Path, known_mint: str) -> dict[str, Any] | None:
    if not candidates_path.exists():
        return None
    with candidates_path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("token_mint") == known_mint or row.get("mint") == known_mint:
                metadata = row.get("metadata_json") or {}
                return {
                    "launch_id": row.get("launch_id"),
                    "mint": known_mint,
                    "creator": row.get("creator") or row.get("creator_deployer") or metadata.get("creator_deployer"),
                    "launch_ts": row.get("launch_ts") or row.get("block_time"),
                    "launch_time": row.get("launch_time_utc") or row.get("launch_time"),
                    "bonding_curve": metadata.get("bonding_curve") or row.get("pool_address"),
                    "associated_bonding_curve": metadata.get("associated_bonding_curve"),
                }
    return None


def _strategies(candidate: dict[str, Any]) -> list[dict[str, str]]:
    candidates = [
        ("mint", candidate.get("mint")),
        ("bonding_curve", candidate.get("bonding_curve")),
        ("associated_bonding_curve", candidate.get("associated_bonding_curve")),
        ("creator", candidate.get("creator")),
    ]
    output = []
    seen = set()
    for name, address in candidates:
        if not address or address in seen:
            continue
        seen.add(address)
        output.append({"name": name, "address": address})
    return output


def _classification(found_strategy: str | None, hydrated_exact: bool, provider_errors: list[str]) -> str:
    if provider_errors and not found_strategy:
        return CLASSIFICATION_BLOCKED
    if found_strategy and hydrated_exact:
        return CLASSIFICATION_STRATEGY_FOUND
    return CLASSIFICATION_NOT_FOUND


def _blocked_report(candidates_path: Path | str, known_mint: str, known_signature: str, reason: str) -> dict[str, Any]:
    return {
        "report_id": "migration_positive_control_probe_v0",
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
        "classification": CLASSIFICATION_BLOCKED,
        "execute": False,
        "network_calls_used": 0,
        "helius_calls_used": 0,
        "known_mint": known_mint,
        "known_signature": known_signature,
        "candidates_path": str(candidates_path),
        "positive_control": {"known_signature_found": False, "best_strategy": None, "hydrated_exact_migration": False},
        "strategy_results": [],
        "warnings": [reason],
        "recommended_next_action": "restore_known_migration_candidate_metadata",
        "guardrails": _guardrails(False),
    }


def _warnings(found_strategy: str | None, hydrated_exact: bool, provider_errors: list[str]) -> list[str]:
    warnings = []
    if provider_errors:
        warnings.append("provider_errors_seen")
    if not found_strategy:
        warnings.append("known_signature_not_found_by_tested_strategies")
    if found_strategy and not hydrated_exact:
        warnings.append("known_signature_found_but_hydration_not_exact_migration")
    return warnings


def _recommended_next_action(classification: str, found_strategy: str | None) -> str:
    if classification == CLASSIFICATION_STRATEGY_FOUND:
        return f"scale_capped_migration_collection_using_{found_strategy}_strategy"
    if classification == CLASSIFICATION_NOT_FOUND:
        return "try_pumpswap_pool_creation_probe_or_refresh_known_signature"
    return "stop_and_fix_provider_or_candidate_metadata"


def _guardrails(execute: bool) -> dict[str, Any]:
    return {
        "dry_run_only": not execute,
        "no_t008": True,
        "no_thesis": True,
        "no_backtest": True,
        "no_validation": True,
        "no_paper_trading": True,
        "no_live_trading": True,
        "no_threshold_optimization": True,
        "no_grid_search": True,
        "no_ml": True,
    }


def _markdown(report: dict[str, Any]) -> str:
    control = report["positive_control"]
    lines = [
        "# Migration Positive-Control Probe",
        "",
        f"- Classification: `{report['classification']}`",
        f"- Execute: `{report['execute']}`",
        f"- Known mint: `{report['known_mint']}`",
        f"- Known signature found: `{control['known_signature_found']}`",
        f"- Best strategy: `{control['best_strategy']}`",
        f"- Hydrated exact migration: `{control['hydrated_exact_migration']}`",
        f"- Network calls used: `{report['network_calls_used']}`",
        f"- Recommended next action: `{report['recommended_next_action']}`",
        "",
        "## Strategy Results",
        "",
        "| Strategy | Address | Signatures Seen | Found |",
        "|---|---|---:|---|",
    ]
    for row in report.get("strategy_results", []):
        lines.append(
            f"| `{row['strategy']}` | `{row['address']}` | {row['signatures_seen']} | `{row['known_signature_found']}` |"
        )
    lines.extend(
        [
            "",
            "No thesis, backtest, validation, paper/live trading, optimization, grid search, or ML was run.",
            "",
        ]
    )
    return "\n".join(lines)
