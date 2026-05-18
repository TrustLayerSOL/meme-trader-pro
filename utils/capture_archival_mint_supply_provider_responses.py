#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib import request as urllib_request


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.env_loader import load_env  # noqa: E402
from utils.build_archival_mint_snapshot_request_bundle import DEFAULT_REPORT_PATH as DEFAULT_REQUEST_BUNDLE_PATH  # noqa: E402
from utils.collect_archival_mint_history import read_json  # noqa: E402
from wallets.archival_mint_snapshot_provider_capture import (  # noqa: E402
    build_archival_mint_snapshot_provider_capture_report,
)
from wallets.historical_market_context_backfill import relative_path  # noqa: E402


DEFAULT_REPORT_PATH = ROOT / "data" / "reports" / "historical_backfill" / "archival_mint_snapshot_provider_capture_report.json"
DEFAULT_RAW_RESPONSE_PATH = (
    ROOT
    / "data"
    / "reports"
    / "historical_backfill"
    / "raw_provider_responses"
    / "archival_mint_supply_batch_raw.json"
)
ARCHIVAL_PROVIDER_ENV_NAMES = [
    "ARCHIVAL_ACCOUNT_STATE_PROVIDER_RPC_URL",
    "QUICKNODE_ARCHIVAL_RPC_URL",
    "SOLANA_ARCHIVAL_RPC_URL",
]


def post_json(url: str, payload: list[dict[str, Any]], timeout: int) -> Any:
    body = json.dumps(payload).encode("utf-8")
    req = urllib_request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib_request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def resolve_rpc_url(explicit_rpc_url: str | None = None) -> tuple[str | None, str | None]:
    if explicit_rpc_url:
        return explicit_rpc_url, "cli_arg"
    for name in ARCHIVAL_PROVIDER_ENV_NAMES:
        value = os.environ.get(name)
        if value:
            return value, name
    return None, None


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_archival_mint_snapshot_provider_capture_report(
    *,
    request_bundle_path: Path | str = DEFAULT_REQUEST_BUNDLE_PATH,
    report_path: Path | str = DEFAULT_REPORT_PATH,
    raw_response_path: Path | str = DEFAULT_RAW_RESPONSE_PATH,
    execute: bool = False,
    rpc_url: str | None = None,
    rpc_post=post_json,
    timeout: int = 10,
    generated_at: float | None = None,
) -> dict[str, Any]:
    request_bundle_path = Path(request_bundle_path)
    report_path = Path(report_path)
    raw_response_path = Path(raw_response_path)
    request_report = read_json(request_bundle_path, {})
    resolved_rpc_url, rpc_source = resolve_rpc_url(rpc_url)
    report, raw_batch = build_archival_mint_snapshot_provider_capture_report(
        request_bundle_report=request_report,
        execute=execute,
        rpc_url=resolved_rpc_url,
        rpc_post=rpc_post,
        timeout=timeout,
        generated_at=generated_at,
    )
    report["provider_endpoint_source"] = rpc_source if resolved_rpc_url else None
    report["input_paths"] = {
        "request_bundle": relative_path(request_bundle_path, ROOT),
    }
    report["output_paths"] = {
        "report": relative_path(report_path, ROOT),
        "raw_provider_response": relative_path(raw_response_path, ROOT) if raw_batch else None,
    }
    if raw_batch:
        write_json(raw_response_path, raw_batch)
    write_json(report_path, report)
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture archival mint supply provider responses for saved-response import.")
    parser.add_argument("--request-bundle-path", type=Path, default=DEFAULT_REQUEST_BUNDLE_PATH)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--raw-response-path", type=Path, default=DEFAULT_RAW_RESPONSE_PATH)
    parser.add_argument("--execute", action="store_true", help="Opt in to provider calls. Default writes a dry-run/blocked report.")
    parser.add_argument("--rpc-url", default=None)
    parser.add_argument("--timeout", type=int, default=10)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    load_env()
    report = write_archival_mint_snapshot_provider_capture_report(
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
