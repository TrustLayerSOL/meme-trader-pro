#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.similar_rug_patterns import build_similar_rug_patterns_report


DEFAULT_WALLET_EVIDENCE = ROOT / "data" / "wallet_backfills" / "wallet_evidence_enrichment_report.json"
DEFAULT_WALLET_LEDGER = ROOT / "data" / "wallet_outcome_ledger.json"
DEFAULT_WALLET_SCORECARD = ROOT / "data" / "wallet_replay_scorecard.json"
DEFAULT_REPLAYABLE_TIMELINES = ROOT / "data" / "reports" / "historical_backfill" / "replayable_token_timelines_report.json"
DEFAULT_OUTPUT = ROOT / "data" / "reports" / "historical_backfill" / "similar_rug_patterns_report.json"


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default
    return value if isinstance(value, dict) else default


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def write_similar_rug_patterns_report(
    *,
    wallet_evidence_path: Path = DEFAULT_WALLET_EVIDENCE,
    wallet_ledger_path: Path = DEFAULT_WALLET_LEDGER,
    wallet_scorecard_path: Path = DEFAULT_WALLET_SCORECARD,
    replayable_timelines_path: Path = DEFAULT_REPLAYABLE_TIMELINES,
    output_path: Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    report = build_similar_rug_patterns_report(
        wallet_evidence_enrichment=read_json(wallet_evidence_path, {}),
        wallet_outcome_ledger=read_json(wallet_ledger_path, {}),
        wallet_replay_scorecard=read_json(wallet_scorecard_path, {}),
        replayable_token_timelines=read_json(replayable_timelines_path, {}),
    )
    report["input_paths"] = {
        "wallet_evidence_enrichment": rel(wallet_evidence_path),
        "wallet_outcome_ledger": rel(wallet_ledger_path),
        "wallet_replay_scorecard": rel(wallet_scorecard_path),
        "replayable_token_timelines": rel(replayable_timelines_path),
    }
    report["output_paths"] = {"report": rel(output_path)}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    report = write_similar_rug_patterns_report()
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
