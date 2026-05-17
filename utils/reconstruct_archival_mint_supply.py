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

from wallets.archival_mint_supply_reconstruction import build_archival_mint_supply_reconstruction_report  # noqa: E402
from wallets.historical_market_context_backfill import relative_path  # noqa: E402


DEFAULT_PLAN_PATH = ROOT / "data" / "reports" / "historical_backfill" / "archival_supply_recovery_plan.json"
DEFAULT_RAW_GLOB = str(ROOT / "data" / "wallet_backfills" / "raw_transactions" / "*.jsonl")
DEFAULT_COMPLETENESS_PATH = ROOT / "data" / "reports" / "historical_backfill" / "archival_mint_history_completeness.json"
DEFAULT_REPORT_PATH = ROOT / "data" / "reports" / "historical_backfill" / "archival_mint_supply_reconstruction_report.json"
DEFAULT_SNAPSHOTS_PATH = ROOT / "data" / "reports" / "historical_backfill" / "archival_mint_supply_reconstruction_snapshots.jsonl"


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
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


def write_archival_mint_supply_reconstruction_report(
    *,
    plan_path: Path | str = DEFAULT_PLAN_PATH,
    raw_transaction_paths: list[Path] | None = None,
    raw_glob: str | None = DEFAULT_RAW_GLOB,
    completeness_path: Path | str = DEFAULT_COMPLETENESS_PATH,
    report_path: Path | str = DEFAULT_REPORT_PATH,
    snapshots_path: Path | str = DEFAULT_SNAPSHOTS_PATH,
    generated_at: float | None = None,
) -> dict[str, Any]:
    plan_path = Path(plan_path)
    completeness_path = Path(completeness_path)
    report_path = Path(report_path)
    snapshots_path = Path(snapshots_path)
    raw_paths = expand_raw_paths(raw_transaction_paths, raw_glob)
    raw_rows = [row for path in raw_paths for row in read_jsonl(path)]
    report = build_archival_mint_supply_reconstruction_report(
        archival_supply_plan=read_json(plan_path, {"token_requirements": []}),
        raw_transactions=raw_rows,
        history_completeness=read_json(completeness_path, {}),
        generated_at=generated_at,
    )
    report["input_paths"] = {
        "plan": relative_path(plan_path, ROOT),
        "history_completeness": relative_path(completeness_path, ROOT),
        "raw_transaction_paths": [relative_path(path, ROOT) for path in raw_paths],
    }
    report["output_paths"] = {
        "report": relative_path(report_path, ROOT),
        "snapshots": relative_path(snapshots_path, ROOT),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    snapshots_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with snapshots_path.open("w", encoding="utf-8") as handle:
        for snapshot in report.get("snapshots") or []:
            handle.write(json.dumps(snapshot, sort_keys=True) + "\n")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reconstruct historical mint supply from complete mint/burn history.")
    parser.add_argument("--plan-path", type=Path, default=DEFAULT_PLAN_PATH)
    parser.add_argument("--raw-glob", default=DEFAULT_RAW_GLOB)
    parser.add_argument("--completeness-path", type=Path, default=DEFAULT_COMPLETENESS_PATH)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--snapshots-path", type=Path, default=DEFAULT_SNAPSHOTS_PATH)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_archival_mint_supply_reconstruction_report(
        plan_path=args.plan_path,
        raw_glob=args.raw_glob,
        completeness_path=args.completeness_path,
        report_path=args.report_path,
        snapshots_path=args.snapshots_path,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
