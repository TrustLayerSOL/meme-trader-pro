#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.behavioral_intelligence_layer import build_behavioral_intelligence_layer_report


DEFAULT_WALLET_ECOSYSTEM = ROOT / "data" / "reports" / "wallet_ecosystems" / "wallet_ecosystem_intelligence_report.json"
DEFAULT_MARKET_REGIME = ROOT / "data" / "reports" / "market_regimes" / "market_regime_detection_report.json"
DEFAULT_VALIDATION_PROOF = ROOT / "data" / "reports" / "replay_validation" / "validation_proof_layer_report.json"
DEFAULT_OUTPUT = ROOT / "data" / "reports" / "behavioral_intelligence" / "behavioral_intelligence_layer_report.json"


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


def write_behavioral_intelligence_layer_report(
    *,
    wallet_ecosystem_path: Path = DEFAULT_WALLET_ECOSYSTEM,
    market_regime_path: Path = DEFAULT_MARKET_REGIME,
    validation_proof_path: Path = DEFAULT_VALIDATION_PROOF,
    output_path: Path = DEFAULT_OUTPUT,
    generated_at: float | None = None,
) -> dict[str, Any]:
    report = build_behavioral_intelligence_layer_report(
        wallet_ecosystem_intelligence=read_json(wallet_ecosystem_path, {}),
        market_regime_detection=read_json(market_regime_path, {}),
        validation_proof_layer=read_json(validation_proof_path, {}),
        generated_at=generated_at,
    )
    report["input_paths"] = {
        "wallet_ecosystem_intelligence": rel(wallet_ecosystem_path),
        "market_regime_detection": rel(market_regime_path),
        "validation_proof_layer": rel(validation_proof_path),
    }
    report["output_paths"] = {"report": rel(output_path)}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    report = write_behavioral_intelligence_layer_report()
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

