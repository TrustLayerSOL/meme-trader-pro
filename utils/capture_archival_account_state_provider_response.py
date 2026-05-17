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
from utils.build_archival_account_state_provider_probe_request import DEFAULT_REPORT_PATH as DEFAULT_REQUEST_BUNDLE_PATH  # noqa: E402
from utils.collect_archival_mint_history import read_json  # noqa: E402
from wallets.archival_account_state_provider_response_capture import (  # noqa: E402
    build_archival_account_state_provider_response_capture_report,
    execute_provider_request,
    get_request_bundle,
)
from wallets.historical_market_context_backfill import relative_path  # noqa: E402


DEFAULT_REPORT_PATH = ROOT / "data" / "reports" / "historical_backfill" / "archival_account_state_provider_response_capture_report.json"
DEFAULT_RAW_RESPONSE_PATH = (
    ROOT
    / "data"
    / "reports"
    / "historical_backfill"
    / "raw_provider_responses"
    / "archival_account_state_provider_probe_raw.json"
)
ARCHIVAL_PROVIDER_ENV_NAMES = [
    "ARCHIVAL_ACCOUNT_STATE_PROVIDER_RPC_URL",
    "QUICKNODE_ARCHIVAL_RPC_URL",
    "SOLANA_ARCHIVAL_RPC_URL",
]


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


def resolve_rpc_url(explicit_rpc_url: str | None = None) -> tuple[str | None, str | None]:
    if explicit_rpc_url:
        return explicit_rpc_url, "cli_arg"
    for name in ARCHIVAL_PROVIDER_ENV_NAMES:
        value = os.environ.get(name)
        if value:
            return value, name
    return None, None


def raw_path_from_request(request_report: dict[str, Any], fallback: Path) -> Path:
    bundle = get_request_bundle(request_report)
    if not bundle:
        return fallback
    raw = str(bundle.get("raw_response_save_path") or "").strip()
    if not raw:
        return fallback
    path = Path(raw)
    if not path.is_absolute():
        path = ROOT / path
    return path


def preserve_raw_response(path: Path, raw_response: dict[str, Any] | None) -> bool:
    if raw_response is None:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(raw_response, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return True


def read_saved_raw_response(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    raw = read_json(path, None)
    return raw if isinstance(raw, dict) else None


def write_archival_account_state_provider_response_capture_report(
    *,
    request_bundle_path: Path | str = DEFAULT_REQUEST_BUNDLE_PATH,
    report_path: Path | str = DEFAULT_REPORT_PATH,
    raw_response_path: Path | str | None = None,
    execute: bool = False,
    rpc_url: str | None = None,
    rpc_post=post_json,
    timeout: int = 10,
    validate_saved_raw_response: bool = False,
    generated_at: float | None = None,
) -> dict[str, Any]:
    request_bundle_path = Path(request_bundle_path)
    report_path = Path(report_path)
    request_report = read_json(request_bundle_path, {})
    resolved_rpc_url, rpc_source = resolve_rpc_url(rpc_url)
    raw_response_output_path = Path(raw_response_path) if raw_response_path else raw_path_from_request(request_report, DEFAULT_RAW_RESPONSE_PATH)

    raw_provider_response: dict[str, Any] | None = None
    provider_call_error: str | None = None
    provider_call_performed = False
    raw_provider_response_preserved = False
    bundle = get_request_bundle(request_report)
    if validate_saved_raw_response and not execute:
        raw_provider_response = read_saved_raw_response(raw_response_output_path)
        raw_provider_response_preserved = raw_provider_response is not None
    elif execute and resolved_rpc_url and bundle:
        provider_call_performed = True
        raw_provider_response, provider_call_error = execute_provider_request(
            rpc_url=resolved_rpc_url,
            payload=bundle["jsonrpc_payload"],
            rpc_post=rpc_post,
            timeout=timeout,
        )
        if provider_call_error is None:
            raw_provider_response_preserved = preserve_raw_response(raw_response_output_path, raw_provider_response)

    report = build_archival_account_state_provider_response_capture_report(
        request_report=request_report,
        execute=execute,
        rpc_url=resolved_rpc_url,
        rpc_post=None,
        timeout=timeout,
        raw_provider_response=raw_provider_response,
        raw_provider_response_preserved=raw_provider_response_preserved,
        validate_saved_raw_response=validate_saved_raw_response,
        generated_at=generated_at,
    )
    if provider_call_performed and raw_provider_response is None:
        report["capture_status"] = "blocked_provider_call_failed"
        report["provider_call_error"] = provider_call_error or "provider_call_failed"
        report["blockers"] = ["provider_call_failed"]
        report["validation_status"] = None
        report["validation"] = {"version": report.get("version"), "decision_time_safe": False}
        report["summary"]["blocked_captures"] = 1
        report["summary"]["provider_calls_performed"] = 1
    report["provider_call_performed"] = bool(provider_call_performed)
    report["provider_endpoint_source"] = rpc_source if resolved_rpc_url else None
    report["input_paths"] = {
        "request_bundle": relative_path(request_bundle_path, ROOT),
    }
    report["output_paths"] = {
        "report": relative_path(report_path, ROOT),
        "raw_provider_response": relative_path(raw_response_output_path, ROOT) if raw_provider_response_preserved else None,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture one read-only archival account-state provider response for review.")
    parser.add_argument("--request-bundle-path", type=Path, default=DEFAULT_REQUEST_BUNDLE_PATH)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--raw-response-path", type=Path, default=None)
    parser.add_argument("--execute", action="store_true", help="Opt in to one provider call. Default writes a blocked/dry-run report.")
    parser.add_argument("--rpc-url", default=None)
    parser.add_argument("--timeout", type=int, default=10)
    parser.add_argument(
        "--validate-saved-raw-response",
        action="store_true",
        help="Validate an already saved raw provider response without calling a provider.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    load_env()
    report = write_archival_account_state_provider_response_capture_report(
        request_bundle_path=args.request_bundle_path,
        report_path=args.report_path,
        raw_response_path=args.raw_response_path,
        execute=args.execute,
        rpc_url=args.rpc_url,
        timeout=args.timeout,
        validate_saved_raw_response=args.validate_saved_raw_response,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
