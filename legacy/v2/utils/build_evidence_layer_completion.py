#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.evidence_layer_completion import build_evidence_layer_completion_report


DEFAULT_READINESS = ROOT / "data" / "reports" / "wallet_backfills" / "wallet_evidence_readiness_report.json"
DEFAULT_SCORECARD = ROOT / "data" / "reports" / "wallet_backfills" / "wallet_evidence_scorecard_report.json"
DEFAULT_CLOSEOUT = ROOT / "data" / "reports" / "wallet_reviews" / "wallet_candidate_context_recovery_closeout.json"
DEFAULT_OUTPUT = ROOT / "data" / "reports" / "wallet_backfills" / "evidence_layer_completion_report.json"


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default
    return parsed if isinstance(parsed, dict) else default


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def write_report(
    *,
    readiness_path: Path = DEFAULT_READINESS,
    scorecard_path: Path = DEFAULT_SCORECARD,
    closeout_path: Path = DEFAULT_CLOSEOUT,
    output_path: Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    report = build_evidence_layer_completion_report(
        wallet_evidence_readiness=read_json(readiness_path, {}),
        wallet_evidence_scorecard=read_json(scorecard_path, {}),
        recovery_closeout=read_json(closeout_path, {}),
    )
    report["input_paths"] = {
        "wallet_evidence_readiness": rel(readiness_path),
        "wallet_evidence_scorecard": rel(scorecard_path),
        "context_recovery_closeout": rel(closeout_path),
    }
    report["output_paths"] = {"report": rel(output_path)}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    report = write_report()
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
