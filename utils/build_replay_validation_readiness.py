#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.replay_validation_readiness import build_replay_validation_readiness_report  # noqa: E402
from wallets.onchain_market_context_recovery import relative_path  # noqa: E402


DEFAULT_REPLAY_SUMMARY_PATH = ROOT / "data" / "historical_replay" / "summary.json"
DEFAULT_STAGE6_READINESS_PATH = ROOT / "data" / "reports" / "historical_backfill" / "replay_realism_readiness_report.json"
DEFAULT_WALLET_REPLAY_SCORECARD_PATH = ROOT / "data" / "wallet_replay_scorecard.json"
DEFAULT_WALLET_OUTCOME_LEDGER_PATH = ROOT / "data" / "wallet_outcome_ledger.json"
DEFAULT_WALLET_CANDIDATE_BACKFILL_TARGETS_PATH = ROOT / "data" / "wallet_candidate_backfill_targets.json"
DEFAULT_FORWARD_OUTCOME_RESOLUTION_PATH = (
    ROOT / "data" / "reports" / "forward_testing" / "forward_outcome_resolution_report.json"
)
DEFAULT_DAILY_FORWARD_CALIBRATION_PATH = (
    ROOT / "data" / "reports" / "forward_testing" / "daily_forward_calibration_report.json"
)
DEFAULT_REPORT_PATH = ROOT / "data" / "reports" / "replay_validation" / "stage8_validation_readiness_report.json"


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def write_replay_validation_readiness_report(
    *,
    replay_summary_path: Path | str = DEFAULT_REPLAY_SUMMARY_PATH,
    stage6_readiness_path: Path | str = DEFAULT_STAGE6_READINESS_PATH,
    wallet_replay_scorecard_path: Path | str = DEFAULT_WALLET_REPLAY_SCORECARD_PATH,
    wallet_outcome_ledger_path: Path | str = DEFAULT_WALLET_OUTCOME_LEDGER_PATH,
    wallet_candidate_backfill_targets_path: Path | str = DEFAULT_WALLET_CANDIDATE_BACKFILL_TARGETS_PATH,
    forward_outcome_resolution_path: Path | str = DEFAULT_FORWARD_OUTCOME_RESOLUTION_PATH,
    daily_forward_calibration_path: Path | str = DEFAULT_DAILY_FORWARD_CALIBRATION_PATH,
    report_path: Path | str = DEFAULT_REPORT_PATH,
    generated_at: float | None = None,
) -> dict[str, Any]:
    replay_summary_path = Path(replay_summary_path)
    stage6_readiness_path = Path(stage6_readiness_path)
    wallet_replay_scorecard_path = Path(wallet_replay_scorecard_path)
    wallet_outcome_ledger_path = Path(wallet_outcome_ledger_path)
    wallet_candidate_backfill_targets_path = Path(wallet_candidate_backfill_targets_path)
    forward_outcome_resolution_path = Path(forward_outcome_resolution_path)
    daily_forward_calibration_path = Path(daily_forward_calibration_path)
    report_path = Path(report_path)

    report = build_replay_validation_readiness_report(
        replay_summary=read_json(replay_summary_path),
        stage6_readiness=read_json(stage6_readiness_path),
        wallet_replay_scorecard=read_json(wallet_replay_scorecard_path),
        wallet_outcome_ledger=read_json(wallet_outcome_ledger_path),
        wallet_candidate_backfill_targets=read_json(wallet_candidate_backfill_targets_path),
        forward_outcome_resolution=read_json(forward_outcome_resolution_path),
        daily_forward_calibration=read_json(daily_forward_calibration_path),
        generated_at=generated_at,
    )
    report["input_paths"] = {
        "replay_summary": relative_path(replay_summary_path, ROOT),
        "stage6_readiness": relative_path(stage6_readiness_path, ROOT),
        "wallet_replay_scorecard": relative_path(wallet_replay_scorecard_path, ROOT),
        "wallet_outcome_ledger": relative_path(wallet_outcome_ledger_path, ROOT),
        "wallet_candidate_backfill_targets": relative_path(wallet_candidate_backfill_targets_path, ROOT),
        "forward_outcome_resolution": relative_path(forward_outcome_resolution_path, ROOT),
        "daily_forward_calibration": relative_path(daily_forward_calibration_path, ROOT),
    }
    report["output_paths"] = {"report": relative_path(report_path, ROOT)}
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the read-only Stage 8 replay validation readiness report.")
    parser.add_argument("--replay-summary", type=Path, default=DEFAULT_REPLAY_SUMMARY_PATH)
    parser.add_argument("--stage6-readiness", type=Path, default=DEFAULT_STAGE6_READINESS_PATH)
    parser.add_argument("--wallet-replay-scorecard", type=Path, default=DEFAULT_WALLET_REPLAY_SCORECARD_PATH)
    parser.add_argument("--wallet-outcome-ledger", type=Path, default=DEFAULT_WALLET_OUTCOME_LEDGER_PATH)
    parser.add_argument("--wallet-candidate-backfill-targets", type=Path, default=DEFAULT_WALLET_CANDIDATE_BACKFILL_TARGETS_PATH)
    parser.add_argument("--forward-outcome-resolution", type=Path, default=DEFAULT_FORWARD_OUTCOME_RESOLUTION_PATH)
    parser.add_argument("--daily-forward-calibration", type=Path, default=DEFAULT_DAILY_FORWARD_CALIBRATION_PATH)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_replay_validation_readiness_report(
        replay_summary_path=args.replay_summary,
        stage6_readiness_path=args.stage6_readiness,
        wallet_replay_scorecard_path=args.wallet_replay_scorecard,
        wallet_outcome_ledger_path=args.wallet_outcome_ledger,
        wallet_candidate_backfill_targets_path=args.wallet_candidate_backfill_targets,
        forward_outcome_resolution_path=args.forward_outcome_resolution,
        daily_forward_calibration_path=args.daily_forward_calibration,
        report_path=args.report_path,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
