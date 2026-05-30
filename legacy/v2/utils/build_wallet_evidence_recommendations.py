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

from wallets.wallet_evidence_recommendations import build_wallet_evidence_recommendations  # noqa: E402


DEFAULT_CANDIDATE_TARGETS = ROOT / "data" / "wallet_candidate_backfill_targets.json"
DEFAULT_HISTORY_BACKFILL = ROOT / "data" / "wallet_backfills" / "wallet_history_backfill_report.json"
DEFAULT_READINESS = ROOT / "data" / "reports" / "wallet_backfills" / "wallet_evidence_readiness_report.json"
DEFAULT_REPORT = ROOT / "data" / "reports" / "wallet_backfills" / "wallet_evidence_recommendations_report.json"


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


def write_wallet_evidence_recommendations_report(
    *,
    out_path: Path | str = DEFAULT_REPORT,
    candidate_targets_path: Path | str = DEFAULT_CANDIDATE_TARGETS,
    history_backfill_path: Path | str = DEFAULT_HISTORY_BACKFILL,
    readiness_path: Path | str = DEFAULT_READINESS,
    candidate_backfill_targets: dict[str, Any] | None = None,
    wallet_history_backfill: dict[str, Any] | None = None,
    wallet_evidence_readiness: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out = Path(out_path)
    candidate_targets_path = Path(candidate_targets_path)
    history_backfill_path = Path(history_backfill_path)
    readiness_path = Path(readiness_path)
    report = build_wallet_evidence_recommendations(
        candidate_backfill_targets=(
            candidate_backfill_targets
            if candidate_backfill_targets is not None
            else read_json(candidate_targets_path)
        ),
        wallet_history_backfill=(
            wallet_history_backfill
            if wallet_history_backfill is not None
            else read_json(history_backfill_path)
        ),
        wallet_evidence_readiness=(
            wallet_evidence_readiness
            if wallet_evidence_readiness is not None
            else read_json(readiness_path)
        ),
    )
    report["input_paths"] = {
        "candidate_backfill_targets": relative_path(candidate_targets_path),
        "wallet_history_backfill": relative_path(history_backfill_path),
        "wallet_evidence_readiness": relative_path(readiness_path),
    }
    report["output_paths"] = {"report": relative_path(out)}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build review-only wallet evidence recommendation buckets.")
    parser.add_argument("--candidate-targets", type=Path, default=DEFAULT_CANDIDATE_TARGETS)
    parser.add_argument("--history-backfill", type=Path, default=DEFAULT_HISTORY_BACKFILL)
    parser.add_argument("--readiness", type=Path, default=DEFAULT_READINESS)
    parser.add_argument("--out-path", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_wallet_evidence_recommendations_report(
        out_path=args.out_path,
        candidate_targets_path=args.candidate_targets,
        history_backfill_path=args.history_backfill,
        readiness_path=args.readiness,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
