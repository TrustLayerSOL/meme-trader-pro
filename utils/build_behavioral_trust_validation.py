#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.behavioral_trust_validation import build_behavioral_trust_validation_report


DEFAULT_BEHAVIORAL_INTELLIGENCE = ROOT / "data" / "reports" / "behavioral_intelligence" / "behavioral_intelligence_layer_report.json"
DEFAULT_VALIDATION_PROOF = ROOT / "data" / "reports" / "replay_validation" / "validation_proof_layer_report.json"
DEFAULT_STAGE8 = ROOT / "data" / "reports" / "replay_validation" / "stage8_validation_readiness_report.json"
DEFAULT_EVIDENCE_LAYER = ROOT / "data" / "reports" / "wallet_backfills" / "evidence_layer_completion_report.json"
DEFAULT_OUTPUT = ROOT / "data" / "reports" / "behavioral_validation" / "behavioral_trust_validation_report.json"


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


def write_behavioral_trust_validation_report(
    *,
    behavioral_intelligence_path: Path = DEFAULT_BEHAVIORAL_INTELLIGENCE,
    validation_proof_path: Path = DEFAULT_VALIDATION_PROOF,
    stage8_validation_path: Path = DEFAULT_STAGE8,
    evidence_layer_path: Path = DEFAULT_EVIDENCE_LAYER,
    output_path: Path = DEFAULT_OUTPUT,
    generated_at: float | None = None,
) -> dict[str, Any]:
    report = build_behavioral_trust_validation_report(
        behavioral_intelligence_layer=read_json(behavioral_intelligence_path, {}),
        validation_proof_layer=read_json(validation_proof_path, {}),
        stage8_validation=read_json(stage8_validation_path, {}),
        evidence_layer=read_json(evidence_layer_path, {}),
        generated_at=generated_at,
    )
    report["input_paths"] = {
        "behavioral_intelligence_layer": rel(behavioral_intelligence_path),
        "validation_proof_layer": rel(validation_proof_path),
        "stage8_validation": rel(stage8_validation_path),
        "evidence_layer": rel(evidence_layer_path),
    }
    report["output_paths"] = {"report": rel(output_path)}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    report = write_behavioral_trust_validation_report()
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

