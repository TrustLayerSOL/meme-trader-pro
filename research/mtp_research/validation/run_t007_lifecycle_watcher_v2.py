"""T007 Level-A PumpSwap migration watcher V2 runner.

This runner defaults to offline finalization. It intentionally does not start a
live scan unless a future explicit live mode is implemented and requested.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from research.mtp_research.validation.t007_lifecycle_event_store import T007LifecycleEventStore
from research.mtp_research.validation.t007_lifecycle_readiness_gate_v2 import (
    write_t007_lifecycle_readiness_gate_v2,
)
from research.mtp_research.validation.t007_pumpswap_gap_backfill import run_pumpswap_gap_backfill
from research.mtp_research.validation.t007_tracked_mint_migration_lookup import run_tracked_mint_migration_lookup


def finalize_offline_lifecycle_root(output_root: str | Path) -> dict[str, Any]:
    root = Path(output_root)
    store = T007LifecycleEventStore(root)
    source_gap = _source_gap_health(root)
    summary = store.finalize_summary(extra=source_gap)
    gate = write_t007_lifecycle_readiness_gate_v2(root, summary)
    return {
        "live_scan_started": False,
        "output_root": str(root),
        "summary": summary,
        "gate": gate,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Finalize or run T007 lifecycle watcher V2.")
    parser.add_argument("--mode", choices=["finalize-offline", "live-proof-10m", "backfill-pumpswap-gaps", "tracked-mint-lookup"], default="finalize-offline")
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--duration-seconds", type=int, default=600)
    parser.add_argument("--max-signatures", type=int, default=100)
    parser.add_argument("--max-transactions-per-address", type=int, default=100)
    parser.add_argument("--explicit-read-only-rpc", action="store_true")
    args = parser.parse_args(argv)
    if args.mode == "live-proof-10m":
        raise SystemExit("live-proof-10m is intentionally not implemented in this speed-run architecture pass; run finalize-offline only")
    if args.mode == "backfill-pumpswap-gaps":
        try:
            result = run_pumpswap_gap_backfill(
                args.output_root,
                explicit_read_only_rpc_flag=bool(args.explicit_read_only_rpc),
                max_signatures=int(args.max_signatures),
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.mode == "tracked-mint-lookup":
        try:
            result = run_tracked_mint_migration_lookup(
                args.output_root,
                explicit_read_only_rpc_flag=bool(args.explicit_read_only_rpc),
                max_transactions_per_address=int(args.max_transactions_per_address),
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        final = finalize_offline_lifecycle_root(args.output_root)
        print(json.dumps({"lookup": result, "gate": final["gate"]}, indent=2, sort_keys=True))
        return 0
    result = finalize_offline_lifecycle_root(args.output_root)
    print(json.dumps(result["gate"], indent=2, sort_keys=True))
    return 0


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _source_gap_health(root: Path) -> dict[str, Any]:
    explicit = _read_json(root / "source_gap_health.json")
    if explicit:
        return explicit
    live = _read_json(root / "live_status.json")
    summary = _read_json(root / "collector_summary.json")
    payload = {**live, **summary}
    requested = _float(
        payload.get("requested_source_duration_seconds")
        or payload.get("source_duration_seconds")
        or payload.get("duration_seconds")
    )
    actual = _float(payload.get("actual_source_duration_seconds"))
    duration_ratio = actual / requested if requested and actual else 0.0
    reconnects = _int(payload.get("websocket_reconnect_count"))
    keepalive_timeouts = _int(payload.get("websocket_keepalive_timeout_count"))
    duration_status = str(payload.get("source_duration_quality_status") or "")
    blocking: list[str] = []
    if requested and duration_ratio < 0.98:
        blocking.append("source_duration_ratio_below_0_98")
    if duration_status in {"partial", "failed"}:
        blocking.append(f"source_duration_{duration_status}")
    if reconnects > 0:
        blocking.append("websocket_reconnects_without_backfill")
    if keepalive_timeouts > 0:
        blocking.append("websocket_keepalive_timeouts_without_backfill")
    unbackfilled = max(reconnects, keepalive_timeouts)
    result = {
        "source_gap_gate_passed": not blocking,
        "unbackfilled_gap_count": unbackfilled,
        "source_gap_blocking_reasons": blocking,
        "source_duration_ratio": duration_ratio,
        "websocket_reconnect_count": reconnects,
        "websocket_keepalive_timeout_count": keepalive_timeouts,
        "source_gap_health_source": "derived_from_live_status_and_collector_summary",
    }
    (root / "source_gap_health.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def _int(value: Any) -> int:
    if value in (None, ""):
        return 0
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


if __name__ == "__main__":
    raise SystemExit(main())
