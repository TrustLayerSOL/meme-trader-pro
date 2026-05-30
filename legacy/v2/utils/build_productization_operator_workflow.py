#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.productization_operator_workflow import build_productization_operator_workflow_report


DEFAULT_EVIDENCE_LAYER = ROOT / "data" / "reports" / "wallet_backfills" / "evidence_layer_completion_report.json"
DEFAULT_REPLAYABLE_TIMELINES = ROOT / "data" / "reports" / "historical_backfill" / "replayable_token_timelines_report.json"
DEFAULT_SIMILAR_RUG = ROOT / "data" / "reports" / "historical_backfill" / "similar_rug_patterns_report.json"
DEFAULT_ALERTING_DASHBOARD = ROOT / "data" / "reports" / "dashboard" / "alerting_dashboard_layer_report.json"
DEFAULT_VALIDATION_PROOF = ROOT / "data" / "reports" / "replay_validation" / "validation_proof_layer_report.json"
DEFAULT_OUTPUT = ROOT / "data" / "reports" / "productization" / "operator_workflow_report.json"


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


def write_productization_operator_workflow_report(
    *,
    evidence_layer_path: Path = DEFAULT_EVIDENCE_LAYER,
    replayable_timelines_path: Path = DEFAULT_REPLAYABLE_TIMELINES,
    similar_rug_path: Path = DEFAULT_SIMILAR_RUG,
    alerting_dashboard_path: Path = DEFAULT_ALERTING_DASHBOARD,
    validation_proof_path: Path = DEFAULT_VALIDATION_PROOF,
    output_path: Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    report = build_productization_operator_workflow_report(
        evidence_layer=read_json(evidence_layer_path, {}),
        replayable_timelines=read_json(replayable_timelines_path, {}),
        similar_rug_patterns=read_json(similar_rug_path, {}),
        alerting_dashboard_layer=read_json(alerting_dashboard_path, {}),
        validation_proof_layer=read_json(validation_proof_path, {}),
    )
    report["input_paths"] = {
        "evidence_layer": rel(evidence_layer_path),
        "replayable_token_timelines": rel(replayable_timelines_path),
        "similar_rug_patterns": rel(similar_rug_path),
        "alerting_dashboard_layer": rel(alerting_dashboard_path),
        "validation_proof_layer": rel(validation_proof_path),
    }
    report["output_paths"] = {"report": rel(output_path)}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    report = write_productization_operator_workflow_report()
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
