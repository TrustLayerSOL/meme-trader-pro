#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.signal_context_layer import build_signal_context_layer_report
from utils.build_wallet_outcome_ledger import build_records


DEFAULT_OUTPUT = ROOT / "data" / "reports" / "signal_context" / "signal_context_layer_report.json"


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def write_signal_context_layer_report(
    *,
    output_path: Path = DEFAULT_OUTPUT,
    records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    report = build_signal_context_layer_report(records if records is not None else build_records())
    report["input_paths"] = {
        "paper_trades": "data/paper_trades.json",
        "rejected_signals": "data/rejected_signals/rejections.jsonl",
        "wallet_performance": "data/wallet_performance.json",
        "sqlite_snapshots": "data/memetrader.db:token_snapshots",
    }
    report["output_paths"] = {"report": rel(output_path)}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    report = write_signal_context_layer_report()
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
