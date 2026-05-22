#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.json_store import atomic_write_json
from core.json_store import read_json
from wallets.forward_public_rpc_schedule_proposal import build_forward_public_rpc_schedule_proposal


FORWARD_REPORT_DIR = ROOT / "data" / "reports" / "forward_testing"
DEFAULT_REPORT = FORWARD_REPORT_DIR / "forward_public_rpc_schedule_proposal.json"
DEFAULT_PROVIDER_REPORT = FORWARD_REPORT_DIR / "forward_free_rpc_provider_rotation_report.json"


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def load_recent_canary_reports(*, limit: int = 3, report_dir: Path = FORWARD_REPORT_DIR) -> list[dict[str, Any]]:
    paths = sorted(report_dir.glob("forward_free_rpc_canary_*.json"), reverse=True)
    reports: list[dict[str, Any]] = []
    for path in paths[:limit]:
        report = read_json(path, {})
        if isinstance(report, dict):
            reports.append(report)
    return list(reversed(reports))


def write_forward_public_rpc_schedule_proposal(
    *,
    out_path: Path | str = DEFAULT_REPORT,
    canary_reports: list[dict[str, Any]] | None = None,
    provider_report: dict[str, Any] | None = None,
    generated_at: float | None = None,
    max_rpc_calls_per_day: int = 120_000,
) -> dict[str, Any]:
    canary_reports = canary_reports if canary_reports is not None else load_recent_canary_reports(limit=3)
    provider_report = provider_report if provider_report is not None else read_json(DEFAULT_PROVIDER_REPORT, {})
    report = build_forward_public_rpc_schedule_proposal(
        canary_reports=canary_reports,
        provider_report=provider_report,
        generated_at=generated_at,
        max_rpc_calls_per_day=max_rpc_calls_per_day,
    )
    out = Path(out_path)
    atomic_write_json(out, report)
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(report["generated_at"]))
    snapshot_path = out.parent / f"forward_public_rpc_schedule_proposal_{stamp}.json"
    atomic_write_json(snapshot_path, report)
    report["report_path"] = display_path(out)
    report["snapshot_path"] = display_path(snapshot_path)
    atomic_write_json(out, report)
    atomic_write_json(snapshot_path, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a review-only public RPC recurring schedule proposal.")
    parser.add_argument("--out", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--max-rpc-calls-per-day", type=int, default=120_000)
    args = parser.parse_args()

    report = write_forward_public_rpc_schedule_proposal(
        out_path=args.out,
        max_rpc_calls_per_day=args.max_rpc_calls_per_day,
    )
    print(json.dumps({
        "report_path": report["report_path"],
        "snapshot_path": report["snapshot_path"],
        "recommendation": report["recommendation"],
        "canaries_reviewed": report["canaries_reviewed"],
        "stable_canaries": report["stable_canaries"],
        "schedule_enabled": report["schedule_enabled"],
        "proposed_schedule": report["proposed_schedule"],
        "blockers": report["blockers"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
