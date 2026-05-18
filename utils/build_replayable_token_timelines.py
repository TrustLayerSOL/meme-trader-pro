#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.replayable_token_timelines import build_replayable_token_timelines_report


DEFAULT_EVIDENCE_LAYER = ROOT / "data" / "reports" / "wallet_backfills" / "evidence_layer_completion_report.json"
DEFAULT_CLOSEOUT = ROOT / "data" / "reports" / "wallet_reviews" / "wallet_candidate_context_recovery_closeout.json"
DEFAULT_MISSING_MARKET = ROOT / "data" / "wallet_backfills" / "wallet_missing_market_context_report.json"
DEFAULT_ONCHAIN_CONTEXT = ROOT / "data" / "reports" / "historical_backfill" / "onchain_market_context_recovery_report.json"
DEFAULT_SCORE_READY_CONTEXT = ROOT / "data" / "reports" / "historical_backfill" / "score_ready_market_context_report.json"
DEFAULT_SUPPLY = ROOT / "data" / "reports" / "historical_backfill" / "archival_supply_evidence_report.json"
DEFAULT_STAGE6 = ROOT / "data" / "reports" / "historical_backfill" / "replay_realism_readiness_report.json"
DEFAULT_STAGE8 = ROOT / "data" / "reports" / "replay_validation" / "stage8_validation_readiness_report.json"
DEFAULT_OUTPUT = ROOT / "data" / "reports" / "historical_backfill" / "replayable_token_timelines_report.json"


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


def merged_market_context(*, onchain_context: dict[str, Any], score_ready_context: dict[str, Any]) -> dict[str, Any]:
    if not score_ready_context:
        return onchain_context
    merged = dict(onchain_context)
    summary = dict(read_json_summary(onchain_context))
    score_summary = read_json_summary(score_ready_context)
    for key in (
        "records_scanned",
        "score_ready_records",
        "near_score_ready_records",
        "blocked_missing_price_rows",
        "blocked_missing_liquidity_rows",
        "tokens_needing_archival_supply",
        "wallets_needing_archival_supply",
    ):
        if key in score_summary:
            summary[key] = score_summary[key]
    merged["summary"] = summary
    merged["live_execution_locked"] = (
        onchain_context.get("live_execution_locked") is True
        and score_ready_context.get("live_execution_locked") is True
    )
    return merged


def read_json_summary(report: dict[str, Any]) -> dict[str, Any]:
    summary = report.get("summary")
    return summary if isinstance(summary, dict) else {}


def write_replayable_token_timelines_report(
    *,
    evidence_layer_path: Path = DEFAULT_EVIDENCE_LAYER,
    recovery_closeout_path: Path = DEFAULT_CLOSEOUT,
    missing_market_context_path: Path = DEFAULT_MISSING_MARKET,
    onchain_market_context_path: Path = DEFAULT_ONCHAIN_CONTEXT,
    score_ready_market_context_path: Path = DEFAULT_SCORE_READY_CONTEXT,
    supply_evidence_path: Path = DEFAULT_SUPPLY,
    stage6_readiness_path: Path = DEFAULT_STAGE6,
    stage8_readiness_path: Path = DEFAULT_STAGE8,
    output_path: Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    report = build_replayable_token_timelines_report(
        evidence_layer_completion=read_json(evidence_layer_path, {}),
        recovery_closeout=read_json(recovery_closeout_path, {}),
        missing_market_context=read_json(missing_market_context_path, {}),
        onchain_market_context=merged_market_context(
            onchain_context=read_json(onchain_market_context_path, {}),
            score_ready_context=read_json(score_ready_market_context_path, {}),
        ),
        supply_evidence=read_json(supply_evidence_path, {}),
        stage6_readiness=read_json(stage6_readiness_path, {}),
        stage8_readiness=read_json(stage8_readiness_path, {}),
    )
    report["input_paths"] = {
        "evidence_layer_completion": rel(evidence_layer_path),
        "recovery_closeout": rel(recovery_closeout_path),
        "missing_market_context": rel(missing_market_context_path),
        "onchain_market_context": rel(onchain_market_context_path),
        "score_ready_market_context": rel(score_ready_market_context_path),
        "supply_evidence": rel(supply_evidence_path),
        "stage6_readiness": rel(stage6_readiness_path),
        "stage8_readiness": rel(stage8_readiness_path),
    }
    report["output_paths"] = {"report": rel(output_path)}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    report = write_replayable_token_timelines_report()
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
