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
from research.outcome_linker import build_later_outcome_from_snapshots, build_windowed_outcomes_from_snapshots
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


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value in (None, ""):
            return default
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number == number else default


def snapshot_context_at_or_before_signal(
    db_path: Path,
    mint: str,
    signal_time: Any,
    *,
    max_age_seconds: float = 300,
) -> dict[str, Any]:
    if not db_path.exists() or not mint or signal_time in (None, ""):
        return {}
    signal_ts = safe_float(signal_time, None)
    if signal_ts is None:
        return {}
    min_ts = signal_ts - max(0.0, float(max_age_seconds))
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            select time, mint, source, context, price, liquidity, risk_label, payload_json
            from token_snapshots
            where mint = ? and time <= ? and time >= ?
            order by time desc
            limit 1
            """,
            (mint, signal_ts, min_ts),
        ).fetchone()
        conn.close()
    except sqlite3.Error:
        return {}
    if row is None:
        return {}
    snap = dict(row)
    payload = read_payload_json(snap.get("payload_json"))
    market_cap = first_present(
        payload.get("market_cap"),
        payload.get("market_cap_usd"),
        as_dict(payload.get("market")).get("market_cap"),
        as_dict(payload.get("market_info")).get("market_cap"),
    )
    return {
        "market_info": {
            "price": snap.get("price"),
            "liquidity": snap.get("liquidity"),
            "market_cap": market_cap,
            "snapshot_time": snap.get("time"),
            "snapshot_source": snap.get("source"),
            "snapshot_context": snap.get("context"),
        },
        "risk_label": snap.get("risk_label"),
    }


def read_payload_json(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


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
            record = build_record_from_trade(trade)
            attach_snapshot_outcomes(record, snapshot_db_path, outcome_horizon_seconds)
            records.append(record)
        except Exception:
            continue

    for rejection in read_jsonl(rejection_path, limit=rejection_limit):
        try:
            record = build_record_from_rejection(rejection)
            attach_snapshot_outcomes(record, snapshot_db_path, outcome_horizon_seconds)
            records.append(record)
        except Exception:
            continue

    performance = read_json(performance_path, {})
    signals = performance.get("signals") if isinstance(performance, dict) and isinstance(performance.get("signals"), list) else []
    for signal in signals[-performance_signal_limit:]:
        try:
            mint = signal.get("mint") or signal.get("token_mint")
            signal_time = signal.get("time") or signal.get("timestamp")
            enriched_signal = dict(signal)
            if not as_dict(enriched_signal.get("market_info")):
                decision_context = snapshot_context_at_or_before_signal(snapshot_db_path, str(mint or ""), signal_time)
                if decision_context:
                    enriched_signal["market_info"] = decision_context.get("market_info")
                    enriched_signal.setdefault("risk_label", decision_context.get("risk_label"))
            later_snapshots = snapshot_rows_for_signal(snapshot_db_path, str(mint or ""), signal_time, outcome_horizon_seconds)
            outcome = build_later_outcome_from_snapshots(
                mint=str(mint or ""),
                signal_time=signal_time,
                snapshots=later_snapshots,
                horizon_seconds=outcome_horizon_seconds,
            )
            outcome["windows"] = build_windowed_outcomes_from_snapshots(
                mint=str(mint or ""),
                signal_time=signal_time,
                snapshots=later_snapshots,
            )
            record = build_record_from_wallet_signal(enriched_signal)
            record["later_token_outcome"] = outcome
            records.append(record)
        except Exception:
            continue

    return records


def attach_snapshot_outcomes(record: dict[str, Any], db_path: Path, horizon_seconds: float) -> None:
    mint = first_present(record.get("mint"), as_dict(record.get("signal_context")).get("mint"))
    signal_time = first_present(
        as_dict(record.get("decision")).get("decision_timestamp"),
        as_dict(record.get("signal_context")).get("entry_timestamp"),
        as_dict(record.get("signal_context")).get("captured_at"),
    )
    later_snapshots = snapshot_rows_for_signal(db_path, str(mint or ""), signal_time, horizon_seconds)
    if not later_snapshots:
        return
    snapshot_outcome = build_later_outcome_from_snapshots(
        mint=str(mint or ""),
        signal_time=signal_time,
        snapshots=later_snapshots,
        horizon_seconds=horizon_seconds,
    )
    snapshot_windows = build_windowed_outcomes_from_snapshots(
        mint=str(mint or ""),
        signal_time=signal_time,
        snapshots=later_snapshots,
    )
    current = as_dict(record.get("later_token_outcome"))
    current_outcome_type = str(current.get("outcome_type") or "unknown").lower()
    if current_outcome_type in {"", "unknown", "open"}:
        merged = dict(snapshot_outcome)
        if current:
            merged.setdefault("original_outcome_reference", current)
    else:
        merged = dict(current)
    merged["windows"] = snapshot_windows
    merged["outcome_windows_source"] = "token_snapshots"
    record["later_token_outcome"] = merged


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
