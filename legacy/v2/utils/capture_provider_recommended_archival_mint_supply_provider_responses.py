#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.env_loader import load_env  # noqa: E402
from utils.build_provider_recommended_archival_mint_snapshot_request_bundle import (  # noqa: E402
    DEFAULT_RAW_RESPONSE_PATH,
    DEFAULT_REPORT_PATH as DEFAULT_REQUEST_BUNDLE_PATH,
)
from utils.capture_archival_mint_supply_provider_responses import (  # noqa: E402
    post_json,
    write_archival_mint_snapshot_provider_capture_report,
)


DEFAULT_REPORT_PATH = (
    ROOT / "data" / "reports" / "historical_backfill" / "provider_recommended_archival_mint_snapshot_provider_capture_report.json"
)


def write_provider_recommended_archival_mint_snapshot_provider_capture_report(
    *,
    request_bundle_path: Path | str = DEFAULT_REQUEST_BUNDLE_PATH,
    report_path: Path | str = DEFAULT_REPORT_PATH,
    raw_response_path: Path | str = ROOT / DEFAULT_RAW_RESPONSE_PATH,
    execute: bool = False,
    rpc_url: str | None = None,
    rpc_post=post_json,
    timeout: int = 10,
    generated_at: float | None = None,
) -> dict:
    return write_archival_mint_snapshot_provider_capture_report(
        request_bundle_path=request_bundle_path,
        report_path=report_path,
        raw_response_path=raw_response_path,
        execute=execute,
        rpc_url=rpc_url,
        rpc_post=rpc_post,
        timeout=timeout,
        generated_at=generated_at,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture provider responses for the focused provider-recommended archival mint batch.")
    parser.add_argument("--request-bundle-path", type=Path, default=DEFAULT_REQUEST_BUNDLE_PATH)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--raw-response-path", type=Path, default=ROOT / DEFAULT_RAW_RESPONSE_PATH)
    parser.add_argument("--execute", action="store_true", help="Opt in to provider calls. Default writes a dry-run/blocked report.")
    parser.add_argument("--rpc-url", default=None)
    parser.add_argument("--timeout", type=int, default=10)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    load_env()
    report = write_provider_recommended_archival_mint_snapshot_provider_capture_report(
        request_bundle_path=args.request_bundle_path,
        report_path=args.report_path,
        raw_response_path=args.raw_response_path,
        execute=args.execute,
        rpc_url=args.rpc_url,
        timeout=args.timeout,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
