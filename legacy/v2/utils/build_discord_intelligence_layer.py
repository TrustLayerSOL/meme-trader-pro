#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.discord_intelligence_layer import build_discord_intelligence_layer_report


DEFAULT_WALLET_PROMOTION = ROOT / "data" / "reports" / "wallet_reviews" / "wallet_promotion_demotion_system_report.json"
DEFAULT_BEHAVIORAL_INTELLIGENCE = ROOT / "data" / "reports" / "behavioral_intelligence" / "behavioral_intelligence_layer_report.json"
DEFAULT_BEHAVIORAL_TRUST = ROOT / "data" / "reports" / "behavioral_validation" / "behavioral_trust_validation_report.json"
DEFAULT_PROOF_READINESS = ROOT / "data" / "reports" / "replay_validation" / "proof_readiness_blocker_reduction_report.json"
DEFAULT_MARKET_REGIME = ROOT / "data" / "reports" / "market_regimes" / "market_regime_detection_report.json"
DEFAULT_OUTPUT = ROOT / "data" / "reports" / "notifications" / "discord_intelligence_layer_report.json"


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


def write_discord_intelligence_layer_report(
    *,
    wallet_promotion_path: Path = DEFAULT_WALLET_PROMOTION,
    behavioral_intelligence_path: Path = DEFAULT_BEHAVIORAL_INTELLIGENCE,
    behavioral_trust_path: Path = DEFAULT_BEHAVIORAL_TRUST,
    proof_readiness_path: Path = DEFAULT_PROOF_READINESS,
    market_regime_path: Path = DEFAULT_MARKET_REGIME,
    output_path: Path = DEFAULT_OUTPUT,
    generated_at: float | None = None,
) -> dict[str, Any]:
    report = build_discord_intelligence_layer_report(
        wallet_promotion_demotion=read_json(wallet_promotion_path, {}),
        behavioral_intelligence=read_json(behavioral_intelligence_path, {}),
        behavioral_trust_validation=read_json(behavioral_trust_path, {}),
        proof_readiness_blocker_reduction=read_json(proof_readiness_path, {}),
        market_regime_detection=read_json(market_regime_path, {}),
        generated_at=generated_at,
    )
    report["input_paths"] = {
        "wallet_promotion_demotion": rel(wallet_promotion_path),
        "behavioral_intelligence": rel(behavioral_intelligence_path),
        "behavioral_trust_validation": rel(behavioral_trust_path),
        "proof_readiness_blocker_reduction": rel(proof_readiness_path),
        "market_regime_detection": rel(market_regime_path),
    }
    report["output_paths"] = {"report": rel(output_path)}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    report = write_discord_intelligence_layer_report()
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

