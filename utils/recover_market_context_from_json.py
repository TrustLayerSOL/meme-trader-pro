#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.storage import EventStore


DEFAULT_DB_PATH = ROOT / "data" / "memetrader.db"
DEFAULT_REPORT_PATH = ROOT / "data" / "wallet_backfills" / "market_context_recovery_report.json"
RECOVERY_VERSION = "market_context_recovery.v1"
MODE = "MARKET_CONTEXT_RECOVERY_REVIEW_ONLY"


def safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def first_float(*values: Any) -> float | None:
    for value in values:
        number = safe_float(value, None)
        if number is not None:
            return number
    return None


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return default


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open() as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                rows.append(parsed)
    return rows


def market_snapshot(
    *,
    mint: Any,
    timestamp: Any,
    market: dict[str, Any],
    source: str,
    context_type: str,
    risk_label: Any = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    mint = str(mint or "").strip()
    snapshot_time = safe_float(timestamp, None)
    if not mint or snapshot_time is None:
        return None
    price = first_float(market.get("price"), market.get("price_usd"), market.get("entry_price"), market.get("close_price"))
    liquidity = first_float(
        market.get("liquidity"),
        market.get("liquidity_usd"),
        market.get("entry_liquidity_usd"),
        market.get("current_liquidity_usd"),
    )
    market_cap = first_float(
        market.get("market_cap"),
        market.get("marketCap"),
        market.get("fdv"),
        market.get("entry_market_cap"),
        market.get("current_market_cap"),
        market.get("exit_market_cap"),
        market.get("market_cap_at_entry"),
        market.get("market_cap_at_exit"),
    )
    if price is None and liquidity is None and market_cap is None:
        return None
    context = {
        "context_type": context_type,
        "decision_time_safe": True,
        "recovered": True,
        "recovery_version": RECOVERY_VERSION,
    }
    payload = {
        "mint": mint,
        "time": snapshot_time,
        "price": price,
        "liquidity": liquidity,
        "market_cap": market_cap,
        "token_age_seconds": first_float(market.get("token_age_seconds"), market.get("age_seconds")),
        "risk_label": risk_label,
        "source": source,
        "context_type": context_type,
        "decision_time_safe": True,
        "recovered": True,
        "recovery_version": RECOVERY_VERSION,
    }
    for key, value in (extra or {}).items():
        if value is not None:
            payload[key] = value
    return {
        "time": snapshot_time,
        "mint": mint,
        "source": source,
        "context": json.dumps(context, sort_keys=True),
        "price": price,
        "liquidity": liquidity,
        "risk_label": risk_label,
        "payload": payload,
    }


def append_snapshot(snapshots: list[dict[str, Any]], seen: set[tuple[Any, ...]], snapshot: dict[str, Any] | None) -> None:
    if not snapshot:
        return
    key = snapshot_key(snapshot)
    if key in seen:
        return
    seen.add(key)
    snapshots.append(snapshot)


def snapshot_key(snapshot: dict[str, Any]) -> tuple[Any, ...]:
    return (
        str(snapshot.get("mint") or ""),
        round(float(snapshot.get("time") or 0.0), 6),
        str(snapshot.get("source") or ""),
        str(snapshot.get("context") or ""),
    )


def enriched_evidence_rows(root: Path) -> list[dict[str, Any]]:
    rows = read_jsonl(root / "data" / "wallet_evidence" / "wallet_history_evidence_enriched.jsonl")
    report_paths = [root / "data" / "wallet_backfills" / "wallet_evidence_enrichment_report.json"]
    report_paths.extend(sorted((root / "data" / "reports" / "wallet_backfills").glob("wallet_evidence_enrichment_*.json")))
    for path in report_paths:
        report = read_json(path, {})
        report_rows = report.get("evidence_records") if isinstance(report, dict) else None
        if not isinstance(report_rows, list):
            continue
        for row in report_rows:
            if not isinstance(row, dict):
                continue
            rows.append(row)
    return rows


def build_from_enriched_evidence(root: Path, snapshots: list[dict[str, Any]], seen: set[tuple[Any, ...]]) -> None:
    rows = enriched_evidence_rows(root)
    for row in rows:
        mint = row.get("token_mint") or row.get("mint")
        entry = as_dict(row.get("estimated_entry_context"))
        append_snapshot(
            snapshots,
            seen,
            market_snapshot(
                mint=mint,
                timestamp=entry.get("snapshot_time") or row.get("timestamp"),
                market=entry,
                source=entry.get("source") or "wallet_evidence_enriched",
                context_type="wallet_evidence_entry_context",
                extra={
                    "wallet": row.get("wallet"),
                    "transaction_signature": row.get("transaction_signature"),
                    "observed_action": row.get("observed_action"),
                    "evidence_timestamp": row.get("timestamp"),
                },
            ),
        )
        exit_context = as_dict(row.get("estimated_exit_context"))
        append_snapshot(
            snapshots,
            seen,
            market_snapshot(
                mint=mint,
                timestamp=exit_context.get("snapshot_time") or exit_context.get("timestamp"),
                market=exit_context,
                source=exit_context.get("source") or "wallet_evidence_enriched_exit",
                context_type="wallet_evidence_exit_context",
                extra={
                    "wallet": row.get("wallet"),
                    "transaction_signature": row.get("transaction_signature"),
                    "observed_action": row.get("observed_action"),
                    "evidence_timestamp": row.get("timestamp"),
                },
            ),
        )


def build_from_replay_events(root: Path, snapshots: list[dict[str, Any]], seen: set[tuple[Any, ...]]) -> None:
    rows = read_jsonl(root / "data" / "historical_replay" / "replay_events.jsonl")
    for row in rows:
        context = as_dict(row.get("decision_context"))
        risk = as_dict(context.get("risk"))
        append_snapshot(
            snapshots,
            seen,
            market_snapshot(
                mint=row.get("mint"),
                timestamp=row.get("signal_timestamp") or as_dict(row.get("decision")).get("decision_timestamp") or context.get("entry_timestamp"),
                market=as_dict(context.get("market")),
                source="historical_replay_decision_context",
                context_type="historical_replay_signal_market",
                risk_label=risk.get("risk_label"),
                extra={
                    "source_record_type": row.get("source_record_type"),
                    "source_record_source": row.get("source"),
                    "event_id": row.get("event_id"),
                },
            ),
        )


def trade_rows(trades: Any) -> Iterable[tuple[str, dict[str, Any]]]:
    trades = trades if isinstance(trades, dict) else {}
    for bucket in ("open_trades", "closed_trades", "failed_trades"):
        rows = trades.get(bucket)
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict):
                    yield bucket, row


def build_from_paper_trades(root: Path, snapshots: list[dict[str, Any]], seen: set[tuple[Any, ...]]) -> None:
    trades = read_json(root / "data" / "paper_trades.json", {})
    for bucket, trade in trade_rows(trades):
        mint = trade.get("mint") or trade.get("token_mint")
        append_snapshot(
            snapshots,
            seen,
            market_snapshot(
                mint=mint,
                timestamp=trade.get("entry_time"),
                market={
                    **as_dict(trade.get("market_info")),
                    "price": trade.get("entry_price") or trade.get("quoted_entry_price"),
                    "liquidity": trade.get("entry_liquidity_usd") or trade.get("liquidity_usd"),
                    "market_cap": trade.get("entry_market_cap") or trade.get("market_cap_at_entry"),
                },
                source="paper_trade_entry",
                context_type="paper_trade_entry_market",
                risk_label=trade.get("risk_label"),
                extra={"trade_bucket": bucket, "decision_id": trade.get("decision_id"), "paper_lane": trade.get("paper_lane")},
            ),
        )
        append_snapshot(
            snapshots,
            seen,
            market_snapshot(
                mint=mint,
                timestamp=trade.get("close_time") or trade.get("exit_time"),
                market={
                    **as_dict(trade.get("market_info")),
                    "price": trade.get("exit_price") or trade.get("close_price") or trade.get("current_price"),
                    "liquidity": trade.get("current_liquidity_usd") or trade.get("liquidity_usd"),
                    "market_cap": trade.get("exit_market_cap") or trade.get("market_cap_at_exit") or trade.get("current_market_cap"),
                },
                source="paper_trade_exit",
                context_type="paper_trade_exit_market",
                risk_label=trade.get("risk_label"),
                extra={"trade_bucket": bucket, "decision_id": trade.get("decision_id"), "paper_lane": trade.get("paper_lane")},
            ),
        )
        append_snapshot(
            snapshots,
            seen,
            market_snapshot(
                mint=mint,
                timestamp=trade.get("last_price_update") or trade.get("entry_time"),
                market=as_dict(trade.get("market_info")),
                source="paper_trade_market_info",
                context_type="paper_trade_latest_market_info",
                risk_label=trade.get("risk_label"),
                extra={"trade_bucket": bucket, "decision_id": trade.get("decision_id"), "paper_lane": trade.get("paper_lane")},
            ),
        )


def build_from_rejected_signals(root: Path, snapshots: list[dict[str, Any]], seen: set[tuple[Any, ...]]) -> None:
    rows = read_jsonl(root / "data" / "rejected_signals" / "rejections.jsonl")
    for row in rows:
        context = as_dict(row.get("signal context") or row.get("signal_context"))
        append_snapshot(
            snapshots,
            seen,
            market_snapshot(
                mint=row.get("mint") or context.get("mint"),
                timestamp=context.get("entry_timestamp") or row.get("recorded_at"),
                market=as_dict(context.get("market_info") or context.get("market")),
                source="rejected_signal_context",
                context_type="rejected_signal_market",
                risk_label=context.get("risk_label") or as_dict(context.get("risk")).get("risk_label"),
                extra={
                    "decision_id": row.get("decision_id"),
                    "rejection_reason": row.get("rejection reason") or row.get("rejection_reason"),
                    "lane": row.get("lane"),
                },
            ),
        )


def build_from_signal_contexts(root: Path, snapshots: list[dict[str, Any]], seen: set[tuple[Any, ...]]) -> None:
    rows = read_jsonl(root / "data" / "signal_contexts" / "contexts.jsonl")
    for row in rows:
        append_snapshot(
            snapshots,
            seen,
            market_snapshot(
                mint=row.get("mint"),
                timestamp=row.get("entry_timestamp") or row.get("captured_at"),
                market=as_dict(row.get("market_info") or row.get("market")),
                source="signal_context_capture",
                context_type="signal_context_market",
                risk_label=as_dict(row.get("risk")).get("risk_label"),
                extra={
                    "decision_id": row.get("decision_id"),
                    "signal_type": row.get("signal_type"),
                    "source_record_source": row.get("source"),
                },
            ),
        )


def build_market_context_snapshots(root: Path | str = ROOT) -> list[dict[str, Any]]:
    root = Path(root)
    snapshots: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    build_from_enriched_evidence(root, snapshots, seen)
    build_from_replay_events(root, snapshots, seen)
    build_from_paper_trades(root, snapshots, seen)
    build_from_rejected_signals(root, snapshots, seen)
    build_from_signal_contexts(root, snapshots, seen)
    snapshots.sort(key=lambda row: (str(row.get("mint") or ""), float(row.get("time") or 0.0), str(row.get("source") or "")))
    return snapshots


def existing_recovered_keys(connection: sqlite3.Connection) -> set[tuple[Any, ...]]:
    rows = connection.execute(
        """
        SELECT time, mint, source, context
        FROM token_snapshots
        WHERE payload_json LIKE '%"recovery_version": "market_context_recovery.v1"%'
        """
    ).fetchall()
    return {
        (
            str(row[1] or ""),
            round(float(row[0] or 0.0), 6),
            str(row[2] or ""),
            str(row[3] or ""),
        )
        for row in rows
    }


def insert_snapshot(connection: sqlite3.Connection, snapshot: dict[str, Any]) -> None:
    connection.execute(
        """
        INSERT INTO token_snapshots (
            time, mint, source, context, price, liquidity, risk_label, payload_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            snapshot.get("time"),
            snapshot.get("mint"),
            snapshot.get("source"),
            snapshot.get("context"),
            safe_float(snapshot.get("price"), None),
            safe_float(snapshot.get("liquidity"), None),
            snapshot.get("risk_label"),
            json.dumps(snapshot.get("payload") or {}, sort_keys=True),
        ),
    )


def recover_market_context_snapshots(
    *,
    root: Path | str = ROOT,
    db_path: Path | str = DEFAULT_DB_PATH,
    report_path: Path | str | None = DEFAULT_REPORT_PATH,
) -> dict[str, Any]:
    root = Path(root)
    db_path = Path(db_path)
    report_path = Path(report_path) if report_path is not None else None
    snapshots = build_market_context_snapshots(root)
    store = EventStore(db_path)
    inserted = 0
    skipped_existing = 0
    source_counts = Counter(row.get("source") or "unknown" for row in snapshots)
    with store.connect() as connection:
        existing = existing_recovered_keys(connection)
        for snapshot in snapshots:
            key = snapshot_key(snapshot)
            if key in existing:
                skipped_existing += 1
                continue
            insert_snapshot(connection, snapshot)
            existing.add(key)
            inserted += 1
    report = {
        "generated_at": time.time(),
        "mode": MODE,
        "review_only": True,
        "live_execution_locked": True,
        "recovery_version": RECOVERY_VERSION,
        "candidate_snapshots": len(snapshots),
        "inserted": inserted,
        "skipped_existing": skipped_existing,
        "unique_mints": len({row.get("mint") for row in snapshots if row.get("mint")}),
        "sources": dict(sorted(source_counts.items())),
        "db_path": str(db_path),
    }
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Recover decision-time market snapshots from surviving JSON artifacts.")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = recover_market_context_snapshots(root=args.root, db_path=args.db_path, report_path=args.report_path)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
