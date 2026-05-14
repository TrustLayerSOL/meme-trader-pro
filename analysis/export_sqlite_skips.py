"""Backfill / batch-export: SQLite decision_records skips → rejections JSONL.

Use when you want parity with ledger history without replaying the bot. Idempotent by decision_id.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Set

from analysis.rejection_logger import DEFAULT_REJECT_PATH
from core.storage import DB_FILE


def load_exported_decision_ids(path: Path) -> Set[str]:
    ids: Set[str] = set()
    if not path.exists():
        return ids
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        did = row.get("decision_id")
        if did:
            ids.add(str(did))
    return ids


def _compact_from_row(row: sqlite3.Row) -> Dict[str, Any]:
    payload = {}
    raw = row["payload_json"]
    if raw:
        try:
            payload = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            payload = {}

    ro = payload.get("rule_outcomes") if isinstance(payload.get("rule_outcomes"), dict) else {}
    scoring = ro.get("scoring") if isinstance(ro.get("scoring"), dict) else {}
    reasons = scoring.get("reasons") if isinstance(scoring.get("reasons"), list) else []

    risk = ro.get("risk") if isinstance(ro.get("risk"), dict) else {}
    inputs = payload.get("inputs") if isinstance(payload.get("inputs"), dict) else {}
    candidate = payload.get("candidate") if isinstance(payload.get("candidate"), dict) else {}

    try:
        from core.signal_context import build_signal_context
    except Exception:
        signal_context = {}
    else:
        source_payload = {
            "mint": row["mint"],
            "signal_type": row["signal_type"],
            "paper_lane": row["paper_lane"],
            "timestamp": candidate.get("timestamp") or row["updated_at"],
            "wallets": inputs.get("wallets"),
            "wallet_count": inputs.get("wallet_count"),
            "weighted_wallet_score": inputs.get("weighted_wallet_score"),
            "wallet_quality": inputs.get("wallet_quality"),
            "wallet_performance": inputs.get("wallet_performance"),
            "market_info": inputs.get("market_info"),
            "holder_concentration_risk": (ro.get("holder_cluster") or {}).get("holder_risk_label")
            if isinstance(ro.get("holder_cluster"), dict)
            else None,
            "risk_label": row["risk_label"],
            "hard_block": risk.get("hard_block"),
            "hard_block_reason": risk.get("hard_block_reason"),
            "score_reasons": reasons,
            "total_score": row["total_score"],
            "score_threshold": row["threshold"],
            "edge_score": row["edge_score"],
        }
        signal_context = build_signal_context(
            source_payload,
            {"decision_id": row["decision_id"], "paper_lane": row["paper_lane"]},
            source="sqlite_skip_export",
        )

    out = {
        **signal_context,
        "mint": row["mint"],
        "signal_type": row["signal_type"],
        "paper_lane": row["paper_lane"],
        "total_score": row["total_score"],
        "threshold": row["threshold"],
        "edge_score": row["edge_score"],
        "risk_label": row["risk_label"],
        "final_action": row["final_action"],
        "action_reason": row["action_reason"],
        "updated_at": row["updated_at"],
        "scoring_reasons_full": reasons,
        "scoring_reasons_tail": reasons[-12:] if reasons else [],
        "hard_block": bool(risk.get("hard_block")),
        "hard_block_reason": risk.get("hard_block_reason"),
    }
    return out


def _pick_rejection_reason(row: sqlite3.Row, ctx: Dict[str, Any]) -> str:
    from analysis.rejection_reason_pick import pick_ranked_rejection_reason

    return pick_ranked_rejection_reason(
        action_reason=row["action_reason"],
        scoring_reasons=ctx.get("scoring_reasons_full") or [],
        hard_block=bool(ctx.get("hard_block")),
        hard_block_reason=ctx.get("hard_block_reason"),
        default="sqlite_should_trade_false",
    )


def export_sqlite_skips_to_rejections(
    *,
    db_path: Optional[Path] = None,
    output_path: Optional[Path] = None,
    limit: int = 10_000,
    dry_run: bool = False,
) -> Dict[str, Any]:
    db_path = Path(db_path or DB_FILE)
    output_path = Path(output_path or DEFAULT_REJECT_PATH)

    stats = {
        "db_path": str(db_path),
        "output_path": str(output_path),
        "limit": limit,
        "dry_run": dry_run,
        "rows_scanned": 0,
        "appended": 0,
        "skipped_duplicate": 0,
        "skipped_missing_db": False,
    }

    if not db_path.exists():
        stats["skipped_missing_db"] = True
        return stats

    existing = load_exported_decision_ids(output_path)

    sql = """
        SELECT decision_id, mint, signal_type, final_action, action_reason, paper_lane,
               should_trade, total_score, threshold, edge_score, risk_label,
               updated_at, payload_json
        FROM decision_records
        WHERE COALESCE(should_trade, 0) = 0
        ORDER BY updated_at DESC
        LIMIT ?
    """

    rows = []
    with sqlite3.connect(str(db_path), timeout=30) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, (limit,)).fetchall()

    from analysis.rejection_logger import record_rejection

    stats["rows_scanned"] = len(rows)
    for row in rows:
        did = row["decision_id"]
        if not did or did in existing:
            stats["skipped_duplicate"] += 1
            continue
        ctx = _compact_from_row(row)
        reason = _pick_rejection_reason(row, ctx)
        if dry_run:
            stats["appended"] += 1
            continue
        try:
            record_rejection(
                str(reason)[:500],
                ctx,
                mint=row["mint"],
                decision_id=str(did),
                lane=row["paper_lane"],
                source="sqlite_skip_export",
                path=output_path,
            )
        except Exception:
            continue
        stats["appended"] += 1
        existing.add(str(did))

    return stats


def main(argv: Optional[list] = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(
        description="Append no-trade rows from decision_records (should_trade=0) into rejections JSONL.",
    )
    parser.add_argument("--db", type=Path, default=DB_FILE, help="SQLite database path")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_REJECT_PATH,
        help="Append-only rejections JSONL",
    )
    parser.add_argument("--limit", type=int, default=10_000, help="Max recent skip rows to process")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count rows that would be appended (no file writes)",
    )
    ns = parser.parse_args(argv)
    stats = export_sqlite_skips_to_rejections(
        db_path=ns.db,
        output_path=ns.output,
        limit=ns.limit,
        dry_run=ns.dry_run,
    )
    print(json.dumps(stats, indent=2))
    return 0 if not stats.get("skipped_missing_db") else 2


if __name__ == "__main__":
    raise SystemExit(main())
