#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from urllib import request as urllib_request


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wallets.archival_mint_snapshot_collector import build_archival_mint_snapshot_collection_report  # noqa: E402
from wallets.historical_market_context_backfill import relative_path  # noqa: E402


DEFAULT_PLAN_PATH = ROOT / "data" / "reports" / "historical_backfill" / "archival_supply_recovery_plan.json"
DEFAULT_REPORT_PATH = ROOT / "data" / "reports" / "historical_backfill" / "archival_mint_supply_snapshot_collection_report.json"
DEFAULT_SNAPSHOTS_PATH = ROOT / "data" / "reports" / "historical_backfill" / "archival_mint_supply_snapshots.jsonl"


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def post_json(url: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib_request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib_request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def write_archival_mint_snapshot_collection_report(
    *,
    plan_path: Path | str = DEFAULT_PLAN_PATH,
    report_path: Path | str = DEFAULT_REPORT_PATH,
    snapshots_path: Path | str = DEFAULT_SNAPSHOTS_PATH,
    execute: bool = False,
    rpc_url: str | None = None,
    rpc_post=post_json,
    timeout: int = 10,
    generated_at: float | None = None,
) -> dict[str, Any]:
    plan_path = Path(plan_path)
    report_path = Path(report_path)
    snapshots_path = Path(snapshots_path)
    report = build_archival_mint_snapshot_collection_report(
        archival_supply_plan=read_json(plan_path, {"token_requirements": [], "candidate_rows": []}),
        execute=execute,
        rpc_url=rpc_url,
        rpc_post=rpc_post,
        timeout=timeout,
        generated_at=generated_at,
    )
    report["input_paths"] = {
        "plan": relative_path(plan_path, ROOT),
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
    parser = argparse.ArgumentParser(description="Build a read-only archival mint supply snapshot collection report.")
    parser.add_argument("--plan-path", type=Path, default=DEFAULT_PLAN_PATH)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--snapshots-path", type=Path, default=DEFAULT_SNAPSHOTS_PATH)
    parser.add_argument("--execute", action="store_true", help="Opt in to provider calls. Default is dry-run manifest only.")
    parser.add_argument("--rpc-url", default=None)
    parser.add_argument("--timeout", type=int, default=10)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_archival_mint_snapshot_collection_report(
        plan_path=args.plan_path,
        report_path=args.report_path,
        snapshots_path=args.snapshots_path,
        execute=args.execute,
        rpc_url=args.rpc_url,
        timeout=args.timeout,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
