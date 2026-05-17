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

from utils.build_archival_account_state_provider_probe import DEFAULT_REPORT_PATH as DEFAULT_PROVIDER_PROBE_PATH  # noqa: E402
from utils.collect_archival_mint_history import read_json  # noqa: E402
from wallets.archival_account_state_provider_probe_request import build_archival_account_state_provider_probe_request_report  # noqa: E402
from wallets.historical_market_context_backfill import relative_path  # noqa: E402


DEFAULT_REPORT_PATH = ROOT / "data" / "reports" / "historical_backfill" / "archival_account_state_provider_probe_request_report.json"


def write_archival_account_state_provider_probe_request_report(
    *,
    provider_probe_path: Path | str = DEFAULT_PROVIDER_PROBE_PATH,
    report_path: Path | str = DEFAULT_REPORT_PATH,
    generated_at: float | None = None,
) -> dict[str, Any]:
    provider_probe_path = Path(provider_probe_path)
    report_path = Path(report_path)
    report = build_archival_account_state_provider_probe_request_report(
        provider_probe=read_json(provider_probe_path, {}),
        generated_at=generated_at,
    )
    report["input_paths"] = {
        "provider_probe": relative_path(provider_probe_path, ROOT),
    }
    report["output_paths"] = {
        "report": relative_path(report_path, ROOT),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build read-only archival account-state provider probe request bundle.")
    parser.add_argument("--provider-probe-path", type=Path, default=DEFAULT_PROVIDER_PROBE_PATH)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_archival_account_state_provider_probe_request_report(
        provider_probe_path=args.provider_probe_path,
        report_path=args.report_path,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
