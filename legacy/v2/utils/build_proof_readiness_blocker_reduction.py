#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.proof_readiness_blocker_reduction import build_proof_readiness_blocker_reduction_report


DEFAULT_BEHAVIORAL_TRUST = ROOT / "data" / "reports" / "behavioral_validation" / "behavioral_trust_validation_report.json"
DEFAULT_VALIDATION_PROOF = ROOT / "data" / "reports" / "replay_validation" / "validation_proof_layer_report.json"
DEFAULT_STAGE8 = ROOT / "data" / "reports" / "replay_validation" / "stage8_validation_readiness_report.json"
DEFAULT_EVIDENCE_LAYER = ROOT / "data" / "reports" / "wallet_backfills" / "evidence_layer_completion_report.json"
DEFAULT_REPLAYABLE_TIMELINES = ROOT / "data" / "reports" / "historical_backfill" / "replayable_token_timelines_report.json"
DEFAULT_ONCHAIN_MARKET_CONTEXT = ROOT / "data" / "reports" / "historical_backfill" / "onchain_market_context_recovery_report.json"
DEFAULT_SUPPLY_EVIDENCE = ROOT / "data" / "reports" / "historical_backfill" / "archival_supply_evidence_report.json"
DEFAULT_OUTPUT = ROOT / "data" / "reports" / "replay_validation" / "proof_readiness_blocker_reduction_report.json"


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


def write_proof_readiness_blocker_reduction_report(
    *,
    behavioral_trust_validation_path: Path = DEFAULT_BEHAVIORAL_TRUST,
    validation_proof_path: Path = DEFAULT_VALIDATION_PROOF,
    stage8_validation_path: Path = DEFAULT_STAGE8,
    evidence_layer_path: Path = DEFAULT_EVIDENCE_LAYER,
    replayable_token_timelines_path: Path = DEFAULT_REPLAYABLE_TIMELINES,
    onchain_market_context_path: Path = DEFAULT_ONCHAIN_MARKET_CONTEXT,
    supply_evidence_path: Path = DEFAULT_SUPPLY_EVIDENCE,
    output_path: Path = DEFAULT_OUTPUT,
    generated_at: float | None = None,
) -> dict[str, Any]:
    report = build_proof_readiness_blocker_reduction_report(
        behavioral_trust_validation=read_json(behavioral_trust_validation_path, {}),
        validation_proof_layer=read_json(validation_proof_path, {}),
        stage8_validation=read_json(stage8_validation_path, {}),
        evidence_layer=read_json(evidence_layer_path, {}),
        replayable_token_timelines=read_json(replayable_token_timelines_path, {}),
        onchain_market_context=read_json(onchain_market_context_path, {}),
        supply_evidence=read_json(supply_evidence_path, {}),
        generated_at=generated_at,
    )
    report["input_paths"] = {
        "behavioral_trust_validation": rel(behavioral_trust_validation_path),
        "validation_proof_layer": rel(validation_proof_path),
        "stage8_validation": rel(stage8_validation_path),
        "evidence_layer": rel(evidence_layer_path),
        "replayable_token_timelines": rel(replayable_token_timelines_path),
        "onchain_market_context": rel(onchain_market_context_path),
        "supply_evidence": rel(supply_evidence_path),
    }
    report["output_paths"] = {"report": rel(output_path)}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    report = write_proof_readiness_blocker_reduction_report()
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
