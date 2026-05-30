from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wallets.wallet_evidence_enrichment import (
    build_wallet_evidence_enrichment_report,
    write_wallet_evidence_enrichment_outputs,
)


DEFAULT_EVIDENCE_PATH = ROOT / "data" / "wallet_evidence" / "wallet_history_evidence.jsonl"
DEFAULT_ENRICHED_EVIDENCE_PATH = ROOT / "data" / "wallet_evidence" / "wallet_history_evidence_enriched.jsonl"
DEFAULT_DB_PATH = ROOT / "data" / "memetrader.db"
DEFAULT_REPLAY_EVENTS_PATH = ROOT / "data" / "historical_replay" / "replay_events.jsonl"
DEFAULT_REPORT_PATH = ROOT / "data" / "wallet_backfills" / "wallet_evidence_enrichment_report.json"
DEFAULT_SNAPSHOT_DIR = ROOT / "data" / "reports" / "wallet_backfills"


def read_jsonl(path: Path, *, limit: int | None = None) -> list[dict[str, Any]]:
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
            if limit is not None and len(rows) >= limit:
                break
    return rows


def evidence_time_bounds(records: list[dict[str, Any]]) -> tuple[set[str], dict[str, float], dict[str, float]]:
    mints: set[str] = set()
    min_time_by_mint: dict[str, float] = {}
    max_time_by_mint: dict[str, float] = {}
    for row in records:
        mint = str(row.get("token_mint") or row.get("mint") or "").strip()
        if not mint:
            continue
        try:
            timestamp = float(row.get("timestamp"))
        except (TypeError, ValueError):
            continue
        mints.add(mint)
        min_time_by_mint[mint] = min(timestamp, min_time_by_mint.get(mint, timestamp))
        max_time_by_mint[mint] = max(timestamp, max_time_by_mint.get(mint, timestamp))
    return mints, min_time_by_mint, max_time_by_mint


def sqlite_table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def load_market_snapshots(
    db_path: Path,
    *,
    mints: set[str],
    min_time_by_mint: dict[str, float],
    max_time_by_mint: dict[str, float],
    before_seconds: float = 3600.0,
    after_seconds: float = 3600.0,
) -> list[dict[str, Any]]:
    if not db_path.exists() or not mints:
        return []
    rows: list[dict[str, Any]] = []
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        has_snapshots = sqlite_table_exists(connection, "token_snapshots")
        has_ticks = sqlite_table_exists(connection, "swap_ticks")
        for mint in sorted(mints):
            start = float(min_time_by_mint.get(mint, 0.0)) - max(0.0, float(before_seconds))
            end = float(max_time_by_mint.get(mint, 0.0)) + max(0.0, float(after_seconds))
            if has_snapshots:
                for row in connection.execute(
                    """
                    SELECT time, mint, source, context, price, liquidity, risk_label, payload_json
                    FROM token_snapshots
                    WHERE mint = ? AND time BETWEEN ? AND ?
                    ORDER BY time ASC
                    """,
                    (mint, start, end),
                ):
                    rows.append(dict(row))
            if has_ticks:
                for row in connection.execute(
                    """
                    SELECT time, mint, source, price, market_cap, liquidity, payload_json
                    FROM swap_ticks
                    WHERE mint = ? AND time BETWEEN ? AND ?
                    ORDER BY time ASC
                    """,
                    (mint, start, end),
                ):
                    rows.append(dict(row))
    finally:
        connection.close()
    rows.sort(key=lambda item: (str(item.get("mint") or ""), float(item.get("time") or 0.0)))
    return rows


def build_report_from_paths(
    *,
    evidence_path: Path = DEFAULT_EVIDENCE_PATH,
    db_path: Path = DEFAULT_DB_PATH,
    replay_events_path: Path = DEFAULT_REPLAY_EVENTS_PATH,
    report_path: Path = DEFAULT_REPORT_PATH,
    enriched_evidence_path: Path = DEFAULT_ENRICHED_EVIDENCE_PATH,
    snapshot_dir: Path = DEFAULT_SNAPSHOT_DIR,
    before_seconds: float = 3600.0,
    after_seconds: float = 3600.0,
    limit: int | None = None,
    generated_at: float | None = None,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    evidence = read_jsonl(evidence_path, limit=limit)
    mints, min_time_by_mint, max_time_by_mint = evidence_time_bounds(evidence)
    market_snapshots = load_market_snapshots(
        db_path,
        mints=mints,
        min_time_by_mint=min_time_by_mint,
        max_time_by_mint=max_time_by_mint,
        before_seconds=before_seconds,
        after_seconds=after_seconds,
    )
    replay_events = read_jsonl(replay_events_path)
    report = build_wallet_evidence_enrichment_report(
        evidence_records=evidence,
        market_snapshots=market_snapshots,
        replay_events=replay_events,
        generated_at=generated_at,
    )
    paths = write_wallet_evidence_enrichment_outputs(
        report,
        report_path=report_path,
        evidence_path=enriched_evidence_path,
        snapshot_dir=snapshot_dir,
        generated_at=generated_at,
    )
    report["output_paths"] = {key: str(value.relative_to(ROOT)) if value.is_relative_to(ROOT) else str(value) for key, value in paths.items()}
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Enrich wallet-history evidence with decision-time-safe market context.")
    parser.add_argument("--evidence-path", type=Path, default=DEFAULT_EVIDENCE_PATH)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--replay-events-path", type=Path, default=DEFAULT_REPLAY_EVENTS_PATH)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--enriched-evidence-path", type=Path, default=DEFAULT_ENRICHED_EVIDENCE_PATH)
    parser.add_argument("--snapshot-dir", type=Path, default=DEFAULT_SNAPSHOT_DIR)
    parser.add_argument("--before-seconds", type=float, default=3600.0)
    parser.add_argument("--after-seconds", type=float, default=3600.0)
    parser.add_argument("--limit", type=int, default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_report_from_paths(
        evidence_path=args.evidence_path,
        db_path=args.db_path,
        replay_events_path=args.replay_events_path,
        report_path=args.report_path,
        enriched_evidence_path=args.enriched_evidence_path,
        snapshot_dir=args.snapshot_dir,
        before_seconds=args.before_seconds,
        after_seconds=args.after_seconds,
        limit=args.limit,
    )
    print(json.dumps(report.get("summary", {}), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
