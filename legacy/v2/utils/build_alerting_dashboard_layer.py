#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.alerting_dashboard_layer import build_alerting_dashboard_layer_report


DEFAULT_EVIDENCE_LAYER = ROOT / "data" / "reports" / "wallet_backfills" / "evidence_layer_completion_report.json"
DEFAULT_REPLAYABLE_TIMELINES = ROOT / "data" / "reports" / "historical_backfill" / "replayable_token_timelines_report.json"
DEFAULT_SIMILAR_RUG = ROOT / "data" / "reports" / "historical_backfill" / "similar_rug_patterns_report.json"
DEFAULT_OUTPUT = ROOT / "data" / "reports" / "dashboard" / "alerting_dashboard_layer_report.json"


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


def write_alerting_dashboard_layer_report(
    *,
    evidence_layer_path: Path = DEFAULT_EVIDENCE_LAYER,
    replayable_timelines_path: Path = DEFAULT_REPLAYABLE_TIMELINES,
    similar_rug_path: Path = DEFAULT_SIMILAR_RUG,
    output_path: Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    report = build_alerting_dashboard_layer_report(
        evidence_layer=read_json(evidence_layer_path, {}),
        replayable_timelines=read_json(replayable_timelines_path, {}),
        similar_rug_patterns=read_json(similar_rug_path, {}),
    )
    report["input_paths"] = {
        "evidence_layer": rel(evidence_layer_path),
        "replayable_token_timelines": rel(replayable_timelines_path),
        "similar_rug_patterns": rel(similar_rug_path),
    }
    report["output_paths"] = {"report": rel(output_path)}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    report = write_alerting_dashboard_layer_report()
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
