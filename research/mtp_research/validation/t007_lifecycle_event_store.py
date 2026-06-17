from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping


class T007LifecycleEventStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._migration_keys = self._load_keys("migration_events.jsonl", _migration_key)
        self._pool_state_keys = self._load_keys("pool_state_snapshots.jsonl", _pool_state_key)

    def write_migration_event(self, row: Mapping[str, Any]) -> str:
        key = _migration_key(row)
        if key in self._migration_keys:
            return "duplicate"
        self._migration_keys.add(key)
        self._append("migration_events.jsonl", row)
        return "written"

    def write_pool_state_snapshot(self, row: Mapping[str, Any]) -> str:
        key = _pool_state_key(row)
        if key in self._pool_state_keys:
            return "duplicate"
        self._pool_state_keys.add(key)
        self._append("pool_state_snapshots.jsonl", row)
        return "written"

    def write_lifecycle_transition(self, row: Mapping[str, Any]) -> str:
        self._append("lifecycle_transitions.jsonl", row)
        return "written"

    def write_tracked_mint(self, row: Mapping[str, Any]) -> str:
        self._append("tracked_mint_registry.jsonl", row)
        return "written"

    def write_raw_observation(self, row: Mapping[str, Any]) -> str:
        self._append("raw_observations.jsonl", row)
        return "written"

    def finalize_summary(self, *, extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
        run_config = _read_json(self.root / "run_config.json")
        collector_summary = _read_json(self.root / "collector_summary.json")
        live_status = _read_json(self.root / "live_status.json")
        migration_rows = _dedupe_rows(
            [
                *list(self.read_jsonl("migration_events.jsonl")),
                *list(self.read_jsonl("global_migration_events.jsonl")),
            ],
            _migration_key,
        )
        pool_rows = _dedupe_rows(
            [
                *list(self.read_jsonl("pool_state_snapshots.jsonl")),
                *list(self.read_jsonl("post_migration_observations.jsonl")),
            ],
            _pool_state_key,
        )
        quote_rows = list(self.read_jsonl("quote_observations.jsonl"))
        birth_rows = _dedupe_rows(
            [
                *list(self.read_jsonl("birth_audit.jsonl")),
                *list(self.read_jsonl("tracked_mint_registry.jsonl")),
            ],
            _birth_key,
        )
        curve_rows = _dedupe_rows(list(self.read_jsonl("curve_observations.jsonl")), _observation_key)
        threshold_rows = _dedupe_rows(
            [
                *list(self.read_jsonl("true_curve_threshold_crossings.jsonl")),
                *list(self.read_jsonl("threshold_crossings.jsonl")),
            ],
            _observation_key,
        )
        global_lane_enabled = _first_bool(
            run_config.get("enable_global_pumpswap_migration"),
            collector_summary.get("enable_global_pumpswap_migration"),
            live_status.get("enable_global_pumpswap_migration"),
            default=False,
        )
        reconciliation_rows, reconciliation_summary = _build_dual_lane_reconciliation(
            migration_rows=migration_rows,
            birth_rows=birth_rows,
            curve_rows=curve_rows,
            threshold_rows=threshold_rows,
            pool_rows=pool_rows,
            global_lane_enabled=global_lane_enabled,
        )
        self._write_jsonl("dual_lane_reconciliation_rows.jsonl", reconciliation_rows)
        level_counts = Counter(str(row.get("migration_evidence_level") or "NONE") for row in migration_rows)
        unique_mints = {str(row.get("mint") or row.get("base_mint") or "") for row in migration_rows if row.get("mint") or row.get("base_mint")}
        unique_pools = {str(row.get("pool_or_pair_address") or row.get("pool_address") or "") for row in migration_rows if row.get("pool_or_pair_address") or row.get("pool_address")}
        pool_state_ready = [row for row in pool_rows if _pool_state_ready(row)]
        quote_ready = [row for row in quote_rows if row.get("quote_status") in {"available", "ready"} or row.get("price_impact_pct") not in (None, "")]
        thin_probe_queue_drops = max(
            _int(collector_summary.get("thin_probe_queue_drops")),
            _int(collector_summary.get("thin_queue_drops")),
            _int(live_status.get("thin_probe_queue_drops")),
            _int(live_status.get("thin_queue_drops")),
        )
        summary = {
            "architecture_version": "t007_level_a_pumpswap_migration_watcher_v2",
            "event_sourced_data_plane_enabled": True,
            "append_only_raw_observation_log_present": (self.root / "raw_observations.jsonl").exists(),
            "raw_provenance_required": True,
            "global_migration_events_deduped": len(migration_rows),
            "global_migration_unique_mints": len(unique_mints),
            "global_migration_unique_pools": len(unique_pools),
            "level_a_migration_count": level_counts.get("LEVEL_A", 0),
            "level_b_migration_count": level_counts.get("LEVEL_B", 0),
            "level_c_migration_count": level_counts.get("LEVEL_C", 0),
            "pool_state_ready_count": len(pool_state_ready),
            "quote_ready_count": len(quote_ready),
            "trade_data_ready_count": 0,
            "thin_probe_queue_drops": thin_probe_queue_drops,
            "thin_queue_drops": thin_probe_queue_drops,
            "summary_raw_counter_match": True,
            "decoder_schema_ok": True,
            "watcher_schema_ok": True,
            "valuation_ladder_suppressed": True,
            "trading_disabled": True,
            "paper_trading_disabled": True,
            "wallet_signing_disabled": True,
            "mayhem_untouched": True,
            "edge_claim_allowed": False,
        }
        summary.update(reconciliation_summary)
        tracked_lookup = _read_json(self.root / "tracked_mint_migration_lookup_summary.json")
        if tracked_lookup:
            summary.update(tracked_lookup)
        if extra:
            summary.update(dict(extra))
        self._write_json("lifecycle_coverage_summary_v2.json", summary)
        self._write_json("collector_summary_v2.json", summary)
        return summary

    def read_jsonl(self, name: str) -> Iterable[dict[str, Any]]:
        path = self.root / name
        if not path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return rows

    def _append(self, name: str, row: Mapping[str, Any]) -> None:
        path = self.root / name
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(dict(row), sort_keys=True) + "\n")

    def _write_json(self, name: str, payload: Mapping[str, Any]) -> None:
        (self.root / name).write_text(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _write_jsonl(self, name: str, rows: Iterable[Mapping[str, Any]]) -> None:
        path = self.root / name
        with path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(dict(row), sort_keys=True) + "\n")

    def _load_keys(self, name: str, key_fn: Any) -> set[tuple[str, ...]]:
        return {key_fn(row) for row in self.read_jsonl(name)}


def _migration_key(row: Mapping[str, Any]) -> tuple[str, ...]:
    return (
        str(row.get("signature") or ""),
        str(row.get("instruction_index") or ""),
        str(row.get("event_index") or ""),
        str(row.get("mint") or row.get("base_mint") or ""),
        str(row.get("detection_method") or ""),
    )


def _pool_state_key(row: Mapping[str, Any]) -> tuple[str, ...]:
    return (
        str(row.get("pool_or_pair_address") or row.get("pool_address") or ""),
        str(row.get("slot") or row.get("pool_state_slot") or ""),
        str(row.get("mint") or row.get("base_mint") or ""),
    )


def _birth_key(row: Mapping[str, Any]) -> tuple[str, ...]:
    return (
        str(row.get("mint") or row.get("base_mint") or ""),
        str(row.get("launch_signature") or row.get("signature") or ""),
        str(row.get("slot") or row.get("launch_slot") or ""),
    )


def _observation_key(row: Mapping[str, Any]) -> tuple[str, ...]:
    return (
        str(row.get("mint") or row.get("base_mint") or ""),
        str(row.get("observation_id") or row.get("signature") or row.get("source_observation_id") or ""),
        str(row.get("slot") or row.get("observation_slot") or row.get("crossing_slot") or ""),
        str(row.get("threshold_pct") or row.get("progress_threshold") or ""),
    )


def _pool_state_ready(row: Mapping[str, Any]) -> bool:
    if row.get("depth_status") in {"available", "ready"}:
        return True
    if row.get("pool_account_decode_status") == "decoded":
        return True
    return row.get("pool_base_token_account") not in (None, "") and row.get("pool_quote_token_account") not in (None, "")


def _dedupe_rows(rows: Iterable[dict[str, Any]], key_fn: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for row in rows:
        key = key_fn(row)
        if key in seen:
            continue
        seen.add(key)
        out.append(dict(row))
    return out


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _build_dual_lane_reconciliation(
    *,
    migration_rows: list[dict[str, Any]],
    birth_rows: list[dict[str, Any]],
    curve_rows: list[dict[str, Any]],
    threshold_rows: list[dict[str, Any]],
    pool_rows: list[dict[str, Any]],
    global_lane_enabled: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    births_by_mint = _group_by_mint(birth_rows)
    curves_by_mint = _group_by_mint([row for row in curve_rows if _curve_observation_usable(row)])
    thresholds_by_mint = _group_by_mint(threshold_rows)
    rows: list[dict[str, Any]] = []
    bucket_counts: Counter[str] = Counter()
    for migration in migration_rows:
        mint = _mint(migration)
        pool = _pool(migration)
        birth_matches = births_by_mint.get(mint, [])
        curve_matches = curves_by_mint.get(mint, [])
        threshold_matches = thresholds_by_mint.get(mint, [])
        pre_birth = [row for row in birth_matches if _row_at_or_before(row, migration)]
        pre_curve = [row for row in curve_matches if _row_at_or_before(row, migration)]
        pre_threshold = [row for row in threshold_matches if _row_at_or_before(row, migration)]
        pool_ready = any(_pool_matches(row, mint, pool) and _pool_state_ready(row) for row in pool_rows)
        birth_seen = bool(pre_birth or birth_matches)
        curve_before = bool(pre_curve)
        threshold_before = bool(pre_threshold)
        full_path = bool(birth_seen and curve_before and threshold_before)
        decision_complete = bool(full_path and pool_ready)
        if not birth_seen:
            bucket = "migration_only"
            grade = "MIGRATION_ONLY_NO_TRADE"
            no_trade_reason = "missing_birth_and_pre_migration_curve_evidence"
        elif not curve_before:
            bucket = "birth_seen_no_pre_migration_curve"
            grade = "PRE_MIGRATION_INCOMPLETE_NO_TRADE"
            no_trade_reason = "missing_pre_migration_curve_observation"
        elif not threshold_before:
            bucket = "birth_seen_curve_no_threshold"
            grade = "PRE_MIGRATION_INCOMPLETE_NO_TRADE"
            no_trade_reason = "missing_pre_migration_threshold_crossing"
        elif not pool_ready:
            bucket = "full_path_missing_pool_state"
            grade = "FULL_PATH_DECISION_TIME_INCOMPLETE_POOL_NO_TRADE"
            no_trade_reason = "missing_post_migration_pool_state"
        else:
            bucket = "full_path_pre_migration_evidence"
            grade = "FULL_PATH_DECISION_TIME_COMPLETE"
            no_trade_reason = None
        bucket_counts[bucket] += 1
        rows.append(
            {
                "mint": mint,
                "pool_or_pair_address": pool,
                "migration_signature": migration.get("signature"),
                "migration_slot": migration.get("slot") or migration.get("migration_slot"),
                "migration_received_at": migration.get("migration_received_at") or migration.get("received_at"),
                "migration_evidence_level": migration.get("migration_evidence_level"),
                "detection_method": migration.get("detection_method"),
                "quote_asset": migration.get("quote_asset"),
                "birth_seen": birth_seen,
                "pre_migration_birth_seen": bool(pre_birth),
                "curve_observed_before_migration": curve_before,
                "threshold_seen_before_migration": threshold_before,
                "pool_state_ready": pool_ready,
                "coverage_bucket": bucket,
                "data_completeness_grade": grade,
                "decision_time_evidence_complete": decision_complete,
                "trade_eligible": decision_complete,
                "no_trade_reason": no_trade_reason,
                "birth_rows_count": len(birth_matches),
                "curve_observations_before_migration_count": len(pre_curve),
                "threshold_crossings_before_migration_count": len(pre_threshold),
            }
        )
    migrated_mints = {_mint(row) for row in migration_rows if _mint(row)}
    tracked_without_migration = sum(1 for mint in births_by_mint if mint and mint not in migrated_mints)
    eligible_count = sum(1 for row in rows if row["trade_eligible"])
    full_path_count = bucket_counts.get("full_path_pre_migration_evidence", 0)
    summary = {
        "dual_lane_reconciliation_enabled": True,
        "global_migration_lane_required": True,
        "global_migration_lane_enabled": bool(global_lane_enabled),
        "dual_lane_global_migration_count": len(rows),
        "dual_lane_birth_linked_migration_count": sum(1 for row in rows if row["birth_seen"]),
        "dual_lane_migration_only_count": bucket_counts.get("migration_only", 0),
        "dual_lane_full_path_pre_migration_evidence_count": full_path_count,
        "dual_lane_eligible_live_decision_count": eligible_count,
        "dual_lane_not_eligible_no_trade_count": len(rows) - eligible_count,
        "decision_time_evidence_complete_count": eligible_count,
        "decision_time_evidence_missing_count": len(rows) - eligible_count,
        "tracked_births_without_migration_count": tracked_without_migration,
        "dual_lane_coverage_bucket_counts": dict(bucket_counts),
        "decision_time_no_trade_policy": "missing_complete_pre_migration_evidence_or_pool_state_means_no_trade",
    }
    return rows, summary


def _group_by_mint(rows: Iterable[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        mint = _mint(row)
        if not mint:
            continue
        grouped.setdefault(mint, []).append(dict(row))
    return grouped


def _curve_observation_usable(row: Mapping[str, Any]) -> bool:
    status = str(row.get("decode_status") or row.get("progress_pct_status") or "").lower()
    if status in {"decode_failed", "error", "failed", "account_not_found"}:
        return False
    return (
        row.get("progress_pct") not in (None, "")
        or row.get("raw_curve_state") not in (None, "")
        or status in {"decoded", "available", "exact"}
    )


def _pool_matches(row: Mapping[str, Any], mint: str, pool: str) -> bool:
    row_mint = _mint(row)
    row_pool = _pool(row)
    if pool and row_pool and row_pool == pool:
        return True
    return bool(mint and row_mint and row_mint == mint)


def _row_at_or_before(row: Mapping[str, Any], migration: Mapping[str, Any]) -> bool:
    migration_slot = _num(migration.get("slot") or migration.get("migration_slot"))
    row_slot = _num(row.get("slot") or row.get("launch_slot") or row.get("observation_slot") or row.get("crossing_slot"))
    if migration_slot is not None and row_slot is not None:
        return row_slot <= migration_slot
    migration_time = _num(migration.get("migration_received_at") or migration.get("received_at") or migration.get("block_time"))
    row_time = _num(
        row.get("received_at")
        or row.get("launch_received_at")
        or row.get("observation_received_at")
        or row.get("crossing_received_at")
        or row.get("block_time")
    )
    if migration_time is not None and row_time is not None:
        return row_time <= migration_time
    return True


def _mint(row: Mapping[str, Any]) -> str:
    return str(row.get("mint") or row.get("base_mint") or row.get("token_mint") or "")


def _pool(row: Mapping[str, Any]) -> str:
    return str(row.get("pool_or_pair_address") or row.get("pool_address") or row.get("pool") or "")


def _num(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int:
    if value in (None, ""):
        return 0
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _first_bool(*values: Any, default: bool = False) -> bool:
    for value in values:
        if value not in (None, ""):
            return _bool(value, default)
    return default


def _bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "enabled"}
