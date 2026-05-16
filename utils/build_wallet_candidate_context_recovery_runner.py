#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wallets.wallet_candidate_context_recovery_runner import build_wallet_candidate_context_recovery_report


DEFAULT_QUEUE = ROOT / "data" / "reports" / "wallet_reviews" / "wallet_candidate_context_recovery_queue.json"
DEFAULT_ENRICHED_EVIDENCE = ROOT / "data" / "wallet_evidence" / "wallet_history_evidence_enriched.jsonl"
DEFAULT_MISSING_MARKET_CONTEXT = ROOT / "data" / "wallet_backfills" / "wallet_missing_market_context_report.json"
DEFAULT_REPLAY_EVENTS = ROOT / "data" / "historical_replay" / "replay_events.jsonl"
DEFAULT_HISTORICAL_BACKFILL = ROOT / "data" / "reports" / "historical_backfill" / "historical_market_context_backfill_records.jsonl"
DEFAULT_OUTPUT = ROOT / "data" / "reports" / "wallet_reviews" / "wallet_candidate_context_recovery_runner.json"


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
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


def write_report(
    *,
    queue_path: Path = DEFAULT_QUEUE,
    enriched_evidence_path: Path = DEFAULT_ENRICHED_EVIDENCE,
    missing_market_context_path: Path = DEFAULT_MISSING_MARKET_CONTEXT,
    replay_events_path: Path = DEFAULT_REPLAY_EVENTS,
    historical_backfill_path: Path = DEFAULT_HISTORICAL_BACKFILL,
    output_path: Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    report = build_wallet_candidate_context_recovery_report(
        recovery_queue=read_json(queue_path, {}),
        enriched_evidence=read_jsonl(enriched_evidence_path),
        missing_market_context=read_json(missing_market_context_path, {}),
        replay_events=read_jsonl(replay_events_path),
        historical_backfill_records=read_jsonl(historical_backfill_path),
        limit=500,
    )
    report["input_paths"] = {
        "recovery_queue": str(queue_path.relative_to(ROOT)),
        "enriched_evidence": str(enriched_evidence_path.relative_to(ROOT)),
        "missing_market_context": str(missing_market_context_path.relative_to(ROOT)),
        "replay_events": str(replay_events_path.relative_to(ROOT)),
        "historical_backfill_records": str(historical_backfill_path.relative_to(ROOT)),
    }
    report["output_paths"] = {"report": str(output_path.relative_to(ROOT))}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    report = write_report()
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
