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

from research.replay_realism_readiness import build_replay_realism_readiness_report  # noqa: E402
from wallets.onchain_market_context_recovery import relative_path  # noqa: E402


DEFAULT_REPLAY_SUMMARY_PATH = ROOT / "data" / "historical_replay" / "summary.json"
DEFAULT_TRUSTED_MARKET_CONTEXT_REPORT_PATH = (
    ROOT / "data" / "reports" / "historical_backfill" / "trusted_onchain_market_context_report.json"
)
DEFAULT_SUPPLY_EVIDENCE_REPORT_PATH = (
    ROOT / "data" / "reports" / "historical_backfill" / "onchain_supply_evidence_report.json"
)
DEFAULT_REPORT_PATH = ROOT / "data" / "reports" / "historical_backfill" / "replay_realism_readiness_report.json"


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def write_replay_realism_readiness_report(
    *,
    replay_summary_path: Path | str = DEFAULT_REPLAY_SUMMARY_PATH,
    trusted_market_context_report_path: Path | str = DEFAULT_TRUSTED_MARKET_CONTEXT_REPORT_PATH,
    supply_evidence_report_path: Path | str = DEFAULT_SUPPLY_EVIDENCE_REPORT_PATH,
    report_path: Path | str = DEFAULT_REPORT_PATH,
    generated_at: float | None = None,
) -> dict[str, Any]:
    replay_summary_path = Path(replay_summary_path)
    trusted_market_context_report_path = Path(trusted_market_context_report_path)
    supply_evidence_report_path = Path(supply_evidence_report_path)
    report_path = Path(report_path)

    report = build_replay_realism_readiness_report(
        replay_summary=read_json(replay_summary_path),
        trusted_market_context_report=read_json(trusted_market_context_report_path),
        supply_evidence_report=read_json(supply_evidence_report_path),
        generated_at=generated_at,
    )
    report["input_paths"] = {
        "replay_summary": relative_path(replay_summary_path, ROOT),
        "trusted_market_context_report": relative_path(trusted_market_context_report_path, ROOT),
        "supply_evidence_report": relative_path(supply_evidence_report_path, ROOT),
    }
    report["output_paths"] = {"report": relative_path(report_path, ROOT)}
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the read-only Stage 6 replay realism readiness report.")
    parser.add_argument("--replay-summary", type=Path, default=DEFAULT_REPLAY_SUMMARY_PATH)
    parser.add_argument("--trusted-market-context-report", type=Path, default=DEFAULT_TRUSTED_MARKET_CONTEXT_REPORT_PATH)
    parser.add_argument("--supply-evidence-report", type=Path, default=DEFAULT_SUPPLY_EVIDENCE_REPORT_PATH)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_replay_realism_readiness_report(
        replay_summary_path=args.replay_summary,
        trusted_market_context_report_path=args.trusted_market_context_report,
        supply_evidence_report_path=args.supply_evidence_report,
        report_path=args.report_path,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
