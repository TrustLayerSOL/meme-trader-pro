"""Materialize strict T012 paper-readiness artifacts from collector evidence.

This module is intentionally rule-agnostic. It converts already-collected
decision-time-safe hot-flow and wallet/dev evidence into the dedicated T012
paper-readiness files required by the gate. It does not create buy/sell
signals, paper trades, private keys, signing paths, or transaction sending.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from research.mtp_research.validation.t012_paper_position_ledger import (
    ensure_paper_position_artifacts,
    validate_paper_position_accounting_schema,
    validate_principal_recovery_schema,
)
from research.mtp_research.validation.t012_paper_snapshot_contract import (
    GUARDRAILS,
    STAGE,
    build_post_entry_hot_flow_snapshot,
    build_pre_entry_decision_snapshot,
    write_t012_paper_snapshot_artifacts,
)

REQUIRED_POST_ENTRY_OFFSETS = (1, 5, 10, 30, 60)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _num(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    number = _num(value)
    return int(number) if number is not None else None


def _bool_or_none(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y"}:
            return True
        if lowered in {"false", "0", "no", "n"}:
            return False
    return None


def _run_id(root: Path, explicit_run_id: str | None) -> str:
    if explicit_run_id:
        return explicit_run_id
    for name in ("collector_summary.json", "live_status.json", "run_config.json"):
        data = _read_json(root / name)
        value = data.get("run_id") or data.get("collector_run_id")
        if value:
            return str(value)
    return root.name


def _real_rows(path: Path) -> list[dict[str, Any]]:
    return [row for row in _read_jsonl(path) if not row.get("schema_marker")]


def _has_required_snapshots(root: Path) -> bool:
    pre_rows = _real_rows(root / "pre_entry_decision_snapshots.jsonl")
    post_rows = _real_rows(root / "post_entry_hot_flow_snapshots.jsonl")
    if not pre_rows:
        return False
    offsets = {int(row.get("snapshot_offset_seconds") or 0) for row in post_rows}
    return all(offset in offsets for offset in REQUIRED_POST_ENTRY_OFFSETS)


def _latest_wallet_rows_by_mint(root: Path) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in _read_jsonl(root / "wallet_dev_checkpoints.jsonl"):
        mint = str(row.get("mint") or "").strip()
        if not mint:
            continue
        prior = latest.get(mint)
        prior_seq = _num(prior.get("db_commit_sequence")) if prior else None
        row_seq = _num(row.get("db_commit_sequence"))
        if prior is None or (row_seq is not None and (prior_seq is None or row_seq >= prior_seq)):
            latest[mint] = row
    return latest


def _legacy_hot_flow_by_mint(root: Path) -> dict[str, dict[int, dict[str, Any]]]:
    by_mint: dict[str, dict[int, dict[str, Any]]] = defaultdict(dict)
    for row in _read_jsonl(root / "near_entry_hot_flow_snapshots.jsonl"):
        mint = str(row.get("mint") or "").strip()
        offset = _int(row.get("window_seconds_after_entry"))
        if not mint or offset is None:
            continue
        if offset not in REQUIRED_POST_ENTRY_OFFSETS:
            continue
        by_mint[mint][offset] = row
    return dict(by_mint)


def materialize_t012_paper_readiness_artifacts(
    run_root: Path | str,
    *,
    run_id: str | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Create strict T012 artifacts from existing run evidence when needed."""
    root = Path(run_root)
    root.mkdir(parents=True, exist_ok=True)
    resolved_run_id = _run_id(root, run_id)
    ledger_paths = ensure_paper_position_artifacts(root, run_id=resolved_run_id)
    had_required = _has_required_snapshots(root)
    materialized = False
    pre_rows: list[dict[str, Any]] = []
    post_rows: list[dict[str, Any]] = []
    skipped_missing_required_windows = 0

    if overwrite or not had_required:
        wallet_by_mint = _latest_wallet_rows_by_mint(root)
        hot_flow_by_mint = _legacy_hot_flow_by_mint(root)
        for mint, rows_by_offset in sorted(hot_flow_by_mint.items()):
            if 30 not in rows_by_offset or 60 not in rows_by_offset:
                skipped_missing_required_windows += 1
                continue
            wallet = wallet_by_mint.get(mint, {})
            entry_received_at = _num(rows_by_offset[60].get("entry_received_at"))
            dev_previous_migrations = (
                wallet.get("dev_previous_migrations")
                if "dev_previous_migrations" in wallet
                else wallet.get("creator_prior_migration_count_before_this_launch")
            )
            creator_sold_before_entry = _bool_or_none(wallet.get("creator_sold_before_entry"))
            pre_rows.append(
                build_pre_entry_decision_snapshot(
                    run_id=resolved_run_id,
                    mint=mint,
                    birth_time=entry_received_at,
                    decision_time=(entry_received_at + 60.0) if entry_received_at is not None else None,
                    decision_slot=_int(rows_by_offset[60].get("first_seen_slot") or rows_by_offset[60].get("confirmed_slot")),
                    birth_verified=True,
                    bonding_curve_verified=True,
                    curve_state_available=True,
                    market_cap_available=None,
                    flow_30s=rows_by_offset[30],
                    flow_60s=rows_by_offset[60],
                    dev_wallet=wallet.get("creator_address"),
                    dev_previous_migrations=_int(dev_previous_migrations),
                    creator_sold_before_entry=creator_sold_before_entry,
                    source_provenance={
                        "source": "t012_paper_artifact_materializer",
                        "legacy_hot_flow_artifact": "near_entry_hot_flow_snapshots.jsonl",
                        "wallet_dev_artifact": "wallet_dev_checkpoints.jsonl",
                    },
                    input_event_ids=[
                        rows_by_offset[60].get("event_id"),
                        rows_by_offset[60].get("domain_event_id"),
                        mint,
                        "pre_entry_30s_60s",
                    ],
                )
            )
            for offset in REQUIRED_POST_ENTRY_OFFSETS:
                legacy = rows_by_offset.get(offset)
                if legacy is None:
                    skipped_missing_required_windows += 1
                    continue
                post_rows.append(
                    build_post_entry_hot_flow_snapshot(
                        run_id=resolved_run_id,
                        mint=mint,
                        paper_candidate_id=f"{resolved_run_id}:{mint}:first_seen_birth",
                        entry_reference_time=entry_received_at,
                        snapshot_offset_seconds=offset,
                        snapshot_time=(entry_received_at + float(offset)) if entry_received_at is not None else None,
                        snapshot_slot=_int(legacy.get("first_seen_slot") or legacy.get("confirmed_slot")),
                        buy_count_since_reference=int(_int(legacy.get("buy_count_after_entry")) or 0),
                        sell_count_since_reference=int(_int(legacy.get("sell_count_after_entry")) or 0),
                        unique_buyers_since_reference=int(_int(legacy.get("unique_buyers_after_entry")) or 0),
                        unique_sellers_since_reference=int(_int(legacy.get("unique_sellers_after_entry")) or 0),
                        largest_buy_quote_since_reference=_num(legacy.get("largest_buy_quote_after_entry")),
                        largest_sell_quote_since_reference=_num(legacy.get("largest_sell_quote_after_entry")),
                        migration_seen=False,
                        near_migration=False,
                        source_provenance={
                            "source": "t012_paper_artifact_materializer",
                            "legacy_artifact": "near_entry_hot_flow_snapshots.jsonl",
                        },
                        input_event_ids=[legacy.get("event_id"), legacy.get("domain_event_id"), mint, f"post_entry_{offset}s"],
                    )
                )

        if pre_rows or post_rows:
            for artifact_name in ("pre_entry_decision_snapshots.jsonl", "post_entry_hot_flow_snapshots.jsonl"):
                path = root / artifact_name
                if path.exists():
                    path.unlink()
            write_t012_paper_snapshot_artifacts(
                root,
                run_id=resolved_run_id,
                pre_entry_rows=pre_rows,
                post_entry_rows=post_rows,
            )
            materialized = True

    accounting_schema = validate_paper_position_accounting_schema(root)
    principal_schema = validate_principal_recovery_schema(root)
    result = {
        **GUARDRAILS,
        "materializer": "t012_paper_artifact_materializer",
        "run_id": resolved_run_id,
        "materialized_snapshot_artifacts": materialized,
        "had_required_snapshots_before": had_required,
        "pre_entry_rows_materialized": len(pre_rows),
        "post_entry_rows_materialized": len(post_rows),
        "skipped_missing_required_windows": skipped_missing_required_windows,
        "paper_position_ledger_path": str(ledger_paths["paper_position_ledger"]),
        "paper_position_accounting_schema_valid": bool(accounting_schema.get("schema_valid")),
        "principal_recovery_tracking_schema_valid": bool(principal_schema.get("schema_valid")),
        "paper_trading_enabled": False,
        "live_trading_enabled": False,
        "wallet_private_key_signing_execution_absent": True,
    }
    (root / "t012_paper_artifact_materialization.json").write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    return result
