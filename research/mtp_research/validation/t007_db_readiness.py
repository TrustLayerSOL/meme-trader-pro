"""DB-backed readiness and consistency checks for T007 proof runs."""

from __future__ import annotations

from pathlib import Path
import json
import sqlite3
from typing import Any, Mapping


def load_canonical_db_path(output_root: str | Path) -> Path:
    root = Path(output_root)
    pointer = root / "canonical_sqlite_db_pointer.json"
    if pointer.exists():
        data = json.loads(pointer.read_text())
        return Path(data["canonical_db_path"])
    return root / "t007_lifecycle_state.sqlite"


def canonical_counts(db_path: str | Path) -> dict[str, int]:
    db = Path(db_path)
    if not db.exists():
        return {}
    with sqlite3.connect(db) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        out: dict[str, int] = {}
        for table in (
            "raw_source_envelopes",
            "domain_events",
            "mint_identity",
            "pool_identity",
            "run_manifest",
            "protocol_layout_versions",
            "lifecycle_invariant_violations",
            "run_consistency_checks",
            "latency_histograms",
        ):
            if table in tables:
                out[table] = int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        if "domain_events" in tables:
            for event_type, count in connection.execute("SELECT event_type, COUNT(*) FROM domain_events GROUP BY event_type"):
                out[f"domain_event:{event_type}"] = int(count)
        return out


def sqlite_integrity_status(db_path: str | Path) -> str:
    db = Path(db_path)
    if not db.exists():
        return "missing"
    with sqlite3.connect(db) as connection:
        row = connection.execute("PRAGMA integrity_check").fetchone()
        return str(row[0]) if row else "missing"


def build_db_readiness_summary(output_root: str | Path, artifact_summary: Mapping[str, Any] | None = None) -> dict[str, Any]:
    artifact = dict(artifact_summary or {})
    db_path = load_canonical_db_path(output_root)
    counts = canonical_counts(db_path)
    raw_expected = int(artifact.get("raw_notifications") or artifact.get("raw_transaction_notifications") or artifact.get("total_births_detected") or 0)
    births_expected = int(artifact.get("unique_birth_mints_live_source") or artifact.get("birth_rows_live_source") or artifact.get("total_births_detected") or 0)
    migrations_expected = int(artifact.get("global_migration_events_deduped") or artifact.get("deduped_pumpswap_migration_events") or artifact.get("global_migration_unique_pools") or 0)
    curve_expected = int(artifact.get("decode_success_count") or artifact.get("progress_decoded_candidate_count") or artifact.get("curve_observations_written") or 0)
    trade_expected = int(artifact.get("trade_flow_events_written") or 0)
    holder_expected = int(artifact.get("holder_distribution_snapshots_written") or artifact.get("holder_distribution_available_count") or 0)
    raw_observed = counts.get("raw_source_envelopes", 0)
    birth_observed = counts.get("mint_identity", 0)
    pool_observed = counts.get("pool_identity", 0)
    curve_observed = counts.get("domain_event:curve_state_decoded", 0) or counts.get("domain_event:curve_observed", 0)
    trade_observed = counts.get("domain_event:trade_flow_window_updated", 0) or counts.get("domain_event:trade_flow_observed", 0)
    holder_observed = counts.get("domain_event:holder_dev_snapshot_seen", 0) or counts.get("domain_event:holder_dev_observed", 0)
    def ratio(observed: int, expected: int) -> float | None:
        return None if expected <= 0 else observed / expected
    return {
        "canonical_db_path": str(db_path),
        "db_integrity_check_status": sqlite_integrity_status(db_path) if db_path.exists() else "missing",
        "db_counts": counts,
        "db_raw_envelope_capture_ratio": ratio(raw_observed, raw_expected),
        "db_birth_capture_ratio": ratio(birth_observed, births_expected),
        "db_pool_capture_ratio": ratio(pool_observed, migrations_expected),
        "db_curve_capture_ratio": ratio(curve_observed, curve_expected),
        "db_trade_flow_capture_ratio": ratio(trade_observed, trade_expected),
        "db_holder_capture_ratio": ratio(holder_observed, holder_expected),
        "raw_notifications_expected": raw_expected,
        "raw_source_envelopes_observed": raw_observed,
        "births_expected": births_expected,
        "mint_identity_observed": birth_observed,
        "migrations_expected": migrations_expected,
        "pool_identity_observed": pool_observed,
        "curve_expected": curve_expected,
        "curve_domain_observed": curve_observed,
        "trade_flow_expected": trade_expected,
        "trade_flow_domain_observed": trade_observed,
        "holder_expected": holder_expected,
        "holder_domain_observed": holder_observed,
        "run_manifest_present": counts.get("run_manifest", 0) == 1,
        "protocol_layout_registry_present": counts.get("protocol_layout_versions", 0) >= 2,
        "latency_histograms_present": counts.get("latency_histograms", 0) > 0,
        "invariant_violation_count": counts.get("lifecycle_invariant_violations", 0),
    }
