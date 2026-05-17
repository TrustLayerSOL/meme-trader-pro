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

from utils.collect_archival_mint_history import DEFAULT_PLAN_PATH, DEFAULT_SIGNATURE_CHECKPOINT_PATH, read_json  # noqa: E402
from wallets.archival_mint_history_progress import build_archival_mint_history_progress_report  # noqa: E402
from wallets.historical_market_context_backfill import relative_path  # noqa: E402


DEFAULT_REPORT_PATH = ROOT / "data" / "reports" / "historical_backfill" / "archival_mint_history_progress_report.json"


def write_archival_mint_history_progress_report(
    *,
    plan_path: Path | str = DEFAULT_PLAN_PATH,
    signature_checkpoint_path: Path | str = DEFAULT_SIGNATURE_CHECKPOINT_PATH,
    report_path: Path | str = DEFAULT_REPORT_PATH,
    generated_at: float | None = None,
) -> dict[str, Any]:
    plan_path = Path(plan_path)
    signature_checkpoint_path = Path(signature_checkpoint_path)
    report_path = Path(report_path)
    report = build_archival_mint_history_progress_report(
        archival_supply_plan=read_json(plan_path, {"token_requirements": []}),
        signature_checkpoint=read_json(signature_checkpoint_path, {}),
        generated_at=generated_at,
    )
    report["input_paths"] = {
        "plan": relative_path(plan_path, ROOT),
        "signature_checkpoint": relative_path(signature_checkpoint_path, ROOT),
    }
    report["output_paths"] = {"report": relative_path(report_path, ROOT)}
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build review-only mint history checkpoint progress report.")
    parser.add_argument("--plan-path", type=Path, default=DEFAULT_PLAN_PATH)
    parser.add_argument("--signature-checkpoint-path", type=Path, default=DEFAULT_SIGNATURE_CHECKPOINT_PATH)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_archival_mint_history_progress_report(
        plan_path=args.plan_path,
        signature_checkpoint_path=args.signature_checkpoint_path,
        report_path=args.report_path,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
