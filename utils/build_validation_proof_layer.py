#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.validation_proof_layer import build_validation_proof_layer_report


DEFAULT_ALERTING_DASHBOARD = ROOT / "data" / "reports" / "dashboard" / "alerting_dashboard_layer_report.json"
DEFAULT_STAGE8 = ROOT / "data" / "reports" / "replay_validation" / "stage8_validation_readiness_report.json"
DEFAULT_OUTPUT = ROOT / "data" / "reports" / "replay_validation" / "validation_proof_layer_report.json"


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


def write_validation_proof_layer_report(
    *,
    alerting_dashboard_path: Path = DEFAULT_ALERTING_DASHBOARD,
    stage8_path: Path = DEFAULT_STAGE8,
    output_path: Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    report = build_validation_proof_layer_report(
        alerting_dashboard_layer=read_json(alerting_dashboard_path, {}),
        stage8_validation=read_json(stage8_path, {}),
    )
    report["input_paths"] = {
        "alerting_dashboard_layer": rel(alerting_dashboard_path),
        "stage8_validation": rel(stage8_path),
    }
    report["output_paths"] = {"report": rel(output_path)}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    report = write_validation_proof_layer_report()
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
