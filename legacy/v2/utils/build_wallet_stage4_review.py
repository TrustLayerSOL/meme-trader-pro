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

from wallets.wallet_stage4_review import build_wallet_stage4_review_report  # noqa: E402


DEFAULT_SCORECARD = ROOT / "data" / "reports" / "wallet_backfills" / "wallet_evidence_scorecard_report.json"
DEFAULT_REPORT = ROOT / "data" / "reports" / "wallet_backfills" / "wallet_stage4_review_report.json"


def read_json(path: Path | str) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        parsed = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def relative_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def write_wallet_stage4_review_report(
    *,
    out_path: Path | str = DEFAULT_REPORT,
    scorecard_path: Path | str = DEFAULT_SCORECARD,
    wallet_evidence_scorecard: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out = Path(out_path)
    scorecard_path = Path(scorecard_path)
    report = build_wallet_stage4_review_report(
        wallet_evidence_scorecard=wallet_evidence_scorecard if wallet_evidence_scorecard is not None else read_json(scorecard_path),
    )
    report["input_paths"] = {"wallet_evidence_scorecard": relative_path(scorecard_path)}
    report["output_paths"] = {"report": relative_path(out)}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build review-only Stage 4 wallet promotion/demotion recommendations.")
    parser.add_argument("--scorecard", type=Path, default=DEFAULT_SCORECARD)
    parser.add_argument("--out-path", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_wallet_stage4_review_report(
        out_path=args.out_path,
        scorecard_path=args.scorecard,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
