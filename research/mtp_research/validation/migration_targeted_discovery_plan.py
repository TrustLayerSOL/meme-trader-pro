"""Dry-run targeted discovery plan for Pump.fun migration labels."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from research.mtp_research.data_paths import data_lake_path
from research.mtp_research.validation.migration_graduation_enrichment_collection import (
    PUMPFUN_PROGRAM_ID,
    _extract_logs,
    _extract_program_ids,
    _instruction_name,
)


CLASSIFICATION_READY = "migration_targeted_probe_ready"
CLASSIFICATION_NEEDS_FIXTURE = "migration_targeted_probe_needs_known_fixture"
CLASSIFICATION_BLOCKED = "migration_targeted_probe_blocked"

DEFAULT_RAW_TRANSACTIONS_PATH = data_lake_path(
    "data", "backtests", "migration_graduation", "raw", "migration_graduation_raw_transactions.jsonl"
)
DEFAULT_OUTPUT_DIR = data_lake_path(
    "data", "backtests", "diagnostics", "reports", "migration_targeted_discovery_plan"
)


def build_migration_targeted_discovery_plan(
    *,
    raw_transactions_path: Path | str = DEFAULT_RAW_TRANSACTIONS_PATH,
) -> dict[str, Any]:
    raw_path = Path(raw_transactions_path)
    raw_rows = _read_jsonl(raw_path)
    exact_examples: list[dict[str, Any]] = []
    false_positive_examples: list[dict[str, Any]] = []
    instruction_counts: Counter[str] = Counter()
    account_layout_counts: Counter[str] = Counter()

    for row in raw_rows:
        raw_json = row.get("raw_json") or {}
        logs = _extract_logs(raw_json)
        instruction_names = [_instruction_name(log.lower()) for log in logs]
        instruction_names = [name for name in instruction_names if name]
        instruction_counts.update(instruction_names)
        account_layout_counts.update(_program_account_layouts(raw_json))

        if _is_exact_pumpfun_migration(raw_json):
            exact_examples.append(_example(row, raw_json, instruction_names))
            continue
        if any(name and "migrate" in name for name in instruction_names):
            false_positive_examples.append(_example(row, raw_json, instruction_names))

    exact_mints = {row["mint"] for row in exact_examples if row.get("mint")}
    false_positive_mints = {row["mint"] for row in false_positive_examples if row.get("mint")}
    classification = _classification(raw_path, exact_examples)
    return {
        "report_id": "migration_targeted_discovery_plan_v0",
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
        "classification": classification,
        "network_calls_used": 0,
        "helius_calls_used": 0,
        "raw_transactions_path": str(raw_path),
        "evidence_summary": {
            "raw_transaction_rows_scanned": len(raw_rows),
            "exact_migration_event_count": len(exact_examples),
            "exact_migration_mint_count": len(exact_mints),
            "migration_like_false_positive_count": len(false_positive_examples),
            "migration_like_false_positive_mint_count": len(false_positive_mints),
        },
        "known_migration_examples": exact_examples[:10],
        "known_false_positive_examples": false_positive_examples[:10],
        "top_instruction_names": dict(instruction_counts.most_common(25)),
        "top_pumpfun_account_layouts": dict(account_layout_counts.most_common(10)),
        "recommended_next_action": _recommended_next_action(classification),
        "recommended_probe_design": {
            "mode": "targeted_parser_repair_then_capped_probe",
            "why": (
                "Blind mint-window collection produced high transaction volume and sparse exact migration labels; "
                "the next step should target exact Migrate/MigrateV2 evidence and exclude fee-sharing migration-like logs."
            ),
            "dry_run_first": True,
            "candidate_probe_shapes": [
                {
                    "name": "known_migration_fixture_probe",
                    "scope": "hydrate and summarize known exact MigrateV2 signature plus adjacent account layout",
                    "network_calls": "0 if using preserved raw; 1 if refreshing known signature",
                    "purpose": "lock expected account/log layout before scaling",
                },
                {
                    "name": "migration_positive_address_probe",
                    "scope": "query known migrated mint/bonding curve over 24h and 72h with low caps",
                    "network_calls": "expected 20-75",
                    "purpose": "confirm which address strategy retrieves exact MigrateV2 cheaply",
                },
                {
                    "name": "pumpswap_pool_creation_probe",
                    "scope": "tiny PumpSwap program probe with hydration limit 25",
                    "network_calls": "expected 26",
                    "purpose": "test whether graduation is more visible at pool creation than Pump.fun mint windows",
                },
            ],
        },
        "guardrails": {
            "no_network_calls": True,
            "no_t008": True,
            "no_thesis": True,
            "no_backtest": True,
            "no_validation": True,
            "no_paper_trading": True,
            "no_live_trading": True,
            "no_threshold_optimization": True,
            "no_grid_search": True,
            "no_ml": True,
        },
        "warnings": _warnings(raw_path, exact_examples),
    }


def write_migration_targeted_discovery_plan_outputs(
    report: dict[str, Any],
    *,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "migration_targeted_discovery_plan.json"
    markdown_path = output / "migration_targeted_discovery_plan.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(_markdown(report), encoding="utf-8")
    return {"json_path": json_path, "markdown_path": markdown_path}


def _is_exact_pumpfun_migration(raw_json: dict[str, Any]) -> bool:
    program_ids = _extract_program_ids(raw_json)
    if PUMPFUN_PROGRAM_ID not in program_ids:
        return False
    names = [_instruction_name(log.lower()) for log in _extract_logs(raw_json)]
    return any(name in {"migrate", "migratev2"} for name in names)


def _program_account_layouts(raw_json: dict[str, Any]) -> list[str]:
    layouts: list[str] = []
    message = ((raw_json.get("transaction") or {}).get("message") or {})
    instructions = message.get("instructions") or []
    for instruction in instructions:
        if not isinstance(instruction, dict):
            continue
        if instruction.get("programId") != PUMPFUN_PROGRAM_ID:
            continue
        accounts = instruction.get("accounts") or []
        data = instruction.get("data")
        data_len = len(str(data)) if data is not None else 0
        layouts.append(f"accounts={len(accounts)}|data_len={data_len}")
    return layouts


def _example(row: dict[str, Any], raw_json: dict[str, Any], instruction_names: list[str]) -> dict[str, Any]:
    return {
        "mint": row.get("mint"),
        "creator": row.get("creator"),
        "launch_id": row.get("launch_id"),
        "signature": row.get("signature"),
        "block_time": row.get("block_time") or raw_json.get("blockTime"),
        "instruction_names": instruction_names,
        "program_ids": sorted(_extract_program_ids(raw_json) & {PUMPFUN_PROGRAM_ID}),
        "account_layouts": _program_account_layouts(raw_json),
    }


def _classification(raw_path: Path, exact_examples: list[dict[str, Any]]) -> str:
    if not raw_path.exists():
        return CLASSIFICATION_BLOCKED
    if exact_examples:
        return CLASSIFICATION_READY
    return CLASSIFICATION_NEEDS_FIXTURE


def _recommended_next_action(classification: str) -> str:
    if classification == CLASSIFICATION_READY:
        return "build_known_migration_fixture_probe_then_test_positive_address_strategy"
    if classification == CLASSIFICATION_NEEDS_FIXTURE:
        return "obtain_or_refresh_one_known_migrate_signature_before_scaling"
    return "restore_raw_migration_collection_artifact_before_planning"


def _warnings(raw_path: Path, exact_examples: list[dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    if not raw_path.exists():
        warnings.append("raw_migration_transactions_missing")
    if not exact_examples:
        warnings.append("no_exact_migration_fixture_found")
    warnings.append("dry_run_only_no_network_calls")
    return warnings


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rows.append(json.loads(line))
    return rows


def _markdown(report: dict[str, Any]) -> str:
    summary = report["evidence_summary"]
    lines = [
        "# Migration Targeted Discovery Plan",
        "",
        f"- Classification: `{report['classification']}`",
        f"- Raw rows scanned: `{summary['raw_transaction_rows_scanned']}`",
        f"- Exact migration events: `{summary['exact_migration_event_count']}`",
        f"- Exact migration mints: `{summary['exact_migration_mint_count']}`",
        f"- Migration-like false positives: `{summary['migration_like_false_positive_count']}`",
        f"- Network calls used: `{report['network_calls_used']}`",
        "- No network calls were made.",
        "",
        "## Recommended Next Action",
        "",
        f"`{report['recommended_next_action']}`",
        "",
        "## Known Exact Migration Examples",
        "",
        "| Mint | Signature | Block Time | Instructions |",
        "|---|---|---:|---|",
    ]
    for row in report["known_migration_examples"]:
        lines.append(
            f"| `{row.get('mint')}` | `{row.get('signature')}` | {row.get('block_time')} | `{row.get('instruction_names')}` |"
        )
    lines.extend(
        [
            "",
            "## Known False Positive Examples",
            "",
            "| Mint | Signature | Instructions |",
            "|---|---|---|",
        ]
    )
    for row in report["known_false_positive_examples"]:
        lines.append(f"| `{row.get('mint')}` | `{row.get('signature')}` | `{row.get('instruction_names')}` |")
    lines.extend(
        [
            "",
            "This is a data-readiness plan only. No T008, thesis, validation, backtest, paper/live trading, optimization, grid search, or ML was run.",
            "",
        ]
    )
    return "\n".join(lines)
