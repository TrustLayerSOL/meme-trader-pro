from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.rejection_logger import DEFAULT_REJECT_PATH
from research.outcome_linker import build_later_outcome_from_snapshots
from research.signal_schema import build_record_from_rejection, build_record_from_trade, build_record_from_wallet_signal
from wallets.wallet_outcome_ledger import build_wallet_outcome_ledger


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def read_jsonl(path: Path, limit: int = 5_000) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def paper_trade_rows(paper_state: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for bucket in ("open_trades", "closed_trades", "failed_trades"):
        for trade in paper_state.get(bucket) or []:
            if isinstance(trade, dict):
                row = dict(trade)
                row.setdefault("_bucket", bucket)
                rows.append(row)
    return rows


def snapshot_rows_for_signal(db_path: Path, mint: str, signal_time: Any, horizon_seconds: float) -> list[dict[str, Any]]:
    if not db_path.exists() or not mint or signal_time in (None, ""):
        return []
    try:
        start = float(signal_time)
    except (TypeError, ValueError):
        return []
    end = start + horizon_seconds
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            select time, mint, source, context, price, liquidity, risk_label
            from token_snapshots
            where mint = ? and time >= ? and time <= ?
            order by time asc
            """,
            (mint, start, end),
        ).fetchall()
        conn.close()
    except sqlite3.Error:
        return []
    return [dict(row) for row in rows]


def build_records(
    *,
    paper_path: Path | None = None,
    rejection_path: Path | None = None,
    performance_path: Path | None = None,
    snapshot_db_path: Path | None = None,
    rejection_limit: int = 5_000,
    performance_signal_limit: int = 5_000,
    outcome_horizon_seconds: float = 3600,
) -> list[dict[str, Any]]:
    paper_path = Path(paper_path or ROOT / "data" / "paper_trades.json")
    rejection_path = Path(rejection_path or ROOT / DEFAULT_REJECT_PATH)
    performance_path = Path(performance_path or ROOT / "data" / "wallet_performance.json")
    snapshot_db_path = Path(snapshot_db_path or ROOT / "data" / "memetrader.db")
    records = []

    for trade in paper_trade_rows(read_json(paper_path, {})):
        try:
            records.append(build_record_from_trade(trade))
        except Exception:
            continue

    for rejection in read_jsonl(rejection_path, limit=rejection_limit):
        try:
            records.append(build_record_from_rejection(rejection))
        except Exception:
            continue

    performance = read_json(performance_path, {})
    signals = performance.get("signals") if isinstance(performance, dict) and isinstance(performance.get("signals"), list) else []
    for signal in signals[-performance_signal_limit:]:
        try:
            mint = signal.get("mint") or signal.get("token_mint")
            signal_time = signal.get("time") or signal.get("timestamp")
            outcome = build_later_outcome_from_snapshots(
                mint=str(mint or ""),
                signal_time=signal_time,
                snapshots=snapshot_rows_for_signal(snapshot_db_path, str(mint or ""), signal_time, outcome_horizon_seconds),
                horizon_seconds=outcome_horizon_seconds,
            )
            record = build_record_from_wallet_signal(signal)
            record["later_token_outcome"] = outcome
            records.append(record)
        except Exception:
            continue

    return records


def main() -> int:
    records = build_records()
    report = build_wallet_outcome_ledger(records)
    out = ROOT / "data" / "wallet_outcome_ledger.json"
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(
        "wrote {} wallets={} records={}".format(
            out.relative_to(ROOT),
            report["counts"]["wallets"],
            report["counts"]["records"],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
