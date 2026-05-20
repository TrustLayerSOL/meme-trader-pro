#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wallets.historical_market_context_backfill import relative_path  # noqa: E402
from wallets.post_decision_supply_coverage import build_post_decision_supply_coverage_report  # noqa: E402


DEFAULT_PLAN_PATH = ROOT / "data" / "reports" / "historical_backfill" / "archival_supply_recovery_plan.json"
DEFAULT_CURRENT_SUPPLY_SNAPSHOTS_PATH = (
    ROOT / "data" / "reports" / "historical_backfill" / "current_mint_supply_snapshots.jsonl"
)
DEFAULT_SIGNATURE_CHECKPOINT_PATH = (
    ROOT / "data" / "reports" / "historical_backfill" / "archival_mint_history_signature_checkpoint.json"
)
DEFAULT_POST_DECISION_SIGNATURE_CHECKPOINT_PATH = (
    ROOT / "data" / "reports" / "historical_backfill" / "post_decision_supply_signature_checkpoint.json"
)
DEFAULT_RAW_GLOB = str(ROOT / "data" / "wallet_backfills" / "raw_transactions" / "*.jsonl")
DEFAULT_REPORT_PATH = ROOT / "data" / "reports" / "historical_backfill" / "post_decision_supply_coverage_report.json"
DEFAULT_UPDATES_PATH = (
    ROOT / "data" / "reports" / "historical_backfill" / "post_decision_supply_completeness_updates.json"
)


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default
    return value if isinstance(value, dict) else default


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    try:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict):
                    rows.append(row)
    except OSError:
        return []
    return rows


def expand_raw_paths(paths: list[Path] | None = None, raw_glob: str | None = None) -> list[Path]:
    if paths:
        return [Path(path) for path in paths]
    return [Path(path) for path in sorted(glob.glob(raw_glob or DEFAULT_RAW_GLOB))]


def merge_signature_checkpoints(base_checkpoint: dict[str, Any], post_decision_checkpoint: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    if isinstance(base_checkpoint, dict):
        for token, row in base_checkpoint.items():
            if isinstance(row, dict):
                merged[str(token)] = dict(row)
    if isinstance(post_decision_checkpoint, dict):
        for token, row in post_decision_checkpoint.items():
            if isinstance(row, dict):
                merged[str(token)] = dict(row)
    return merged


def write_post_decision_supply_coverage_report(
    *,
    plan_path: Path | str = DEFAULT_PLAN_PATH,
    current_supply_snapshots_path: Path | str = DEFAULT_CURRENT_SUPPLY_SNAPSHOTS_PATH,
    signature_checkpoint_path: Path | str = DEFAULT_SIGNATURE_CHECKPOINT_PATH,
    post_decision_signature_checkpoint_path: Path | str = DEFAULT_POST_DECISION_SIGNATURE_CHECKPOINT_PATH,
    raw_transaction_paths: list[Path] | None = None,
    raw_glob: str | None = DEFAULT_RAW_GLOB,
    report_path: Path | str = DEFAULT_REPORT_PATH,
    completeness_updates_path: Path | str = DEFAULT_UPDATES_PATH,
    generated_at: float | None = None,
) -> dict[str, Any]:
    plan_path = Path(plan_path)
    current_supply_snapshots_path = Path(current_supply_snapshots_path)
    signature_checkpoint_path = Path(signature_checkpoint_path)
    post_decision_signature_checkpoint_path = Path(post_decision_signature_checkpoint_path)
    report_path = Path(report_path)
    completeness_updates_path = Path(completeness_updates_path)
    raw_paths = expand_raw_paths(raw_transaction_paths, raw_glob)
    raw_rows = [row for path in raw_paths for row in read_jsonl(path)]
    signature_checkpoint = merge_signature_checkpoints(
        read_json(signature_checkpoint_path, {}),
        read_json(post_decision_signature_checkpoint_path, {}),
    )
    report = build_post_decision_supply_coverage_report(
        archival_supply_plan=read_json(plan_path, {"token_requirements": []}),
        current_supply_snapshots=read_jsonl(current_supply_snapshots_path),
        signature_checkpoint=signature_checkpoint,
        raw_transactions=raw_rows,
        generated_at=generated_at,
    )
    report["input_paths"] = {
        "plan": relative_path(plan_path, ROOT),
        "current_supply_snapshots": relative_path(current_supply_snapshots_path, ROOT),
        "signature_checkpoint": relative_path(signature_checkpoint_path, ROOT),
        "post_decision_signature_checkpoint": relative_path(post_decision_signature_checkpoint_path, ROOT),
        "raw_transaction_paths": [relative_path(path, ROOT) for path in raw_paths],
    }
    report["output_paths"] = {
        "report": relative_path(report_path, ROOT),
        "history_completeness_updates": relative_path(completeness_updates_path, ROOT),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    completeness_updates_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    completeness_updates_path.write_text(
        json.dumps(report.get("history_completeness_updates") or {}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build review-only post-decision supply stability coverage.")
    parser.add_argument("--plan-path", type=Path, default=DEFAULT_PLAN_PATH)
    parser.add_argument("--current-supply-snapshots", type=Path, default=DEFAULT_CURRENT_SUPPLY_SNAPSHOTS_PATH)
    parser.add_argument("--signature-checkpoint-path", type=Path, default=DEFAULT_SIGNATURE_CHECKPOINT_PATH)
    parser.add_argument("--post-decision-signature-checkpoint-path", type=Path, default=DEFAULT_POST_DECISION_SIGNATURE_CHECKPOINT_PATH)
    parser.add_argument("--raw-glob", default=DEFAULT_RAW_GLOB)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--completeness-updates-path", type=Path, default=DEFAULT_UPDATES_PATH)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_post_decision_supply_coverage_report(
        plan_path=args.plan_path,
        current_supply_snapshots_path=args.current_supply_snapshots,
        signature_checkpoint_path=args.signature_checkpoint_path,
        post_decision_signature_checkpoint_path=args.post_decision_signature_checkpoint_path,
        raw_glob=args.raw_glob,
        report_path=args.report_path,
        completeness_updates_path=args.completeness_updates_path,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
