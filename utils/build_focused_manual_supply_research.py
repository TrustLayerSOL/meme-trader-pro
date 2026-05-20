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

from wallets.focused_manual_supply_research import (  # noqa: E402
    build_focused_manual_supply_packet,
    import_focused_manual_supply_evidence,
)
from wallets.historical_market_context_backfill import relative_path  # noqa: E402


DEFAULT_REQUEST_BUNDLE_PATH = (
    ROOT / "data" / "reports" / "historical_backfill" / "provider_recommended_archival_mint_snapshot_request_bundle_report.json"
)
DEFAULT_OUTPUT_DIR = ROOT / "data" / "manual_research"


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default
    return parsed if isinstance(parsed, dict) else default


def write_focused_manual_supply_packet(
    *,
    request_bundle_path: Path | str = DEFAULT_REQUEST_BUNDLE_PATH,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    limit: int | None = None,
    generated_at: float | None = None,
) -> dict[str, Any]:
    request_bundle_path = Path(request_bundle_path)
    output_dir = Path(output_dir)
    report = build_focused_manual_supply_packet(
        request_bundle_report=read_json(request_bundle_path, {"requests": []}),
        output_dir=output_dir,
        limit=limit,
        generated_at=generated_at,
    )
    report["input_paths"] = {"request_bundle": relative_path(request_bundle_path, ROOT)}
    return report


def import_focused_manual_supply_template(
    *,
    csv_path: Path | str,
    request_bundle_path: Path | str = DEFAULT_REQUEST_BUNDLE_PATH,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    generated_at: float | None = None,
) -> dict[str, Any]:
    request_bundle_path = Path(request_bundle_path)
    report = import_focused_manual_supply_evidence(
        csv_path,
        request_bundle_report=read_json(request_bundle_path, {"requests": []}),
        output_dir=output_dir,
        generated_at=generated_at,
    )
    report["input_paths"] = {
        "csv": relative_path(Path(csv_path), ROOT),
        "request_bundle": relative_path(request_bundle_path, ROOT),
    }
    Path(report["output_paths"]["report"]).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export or import focused manual supply research packets.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    export_parser = subparsers.add_parser("export", help="Export focused manual supply research CSV/template.")
    export_parser.add_argument("--request-bundle-path", type=Path, default=DEFAULT_REQUEST_BUNDLE_PATH)
    export_parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    export_parser.add_argument("--limit", type=int, default=None)

    import_parser = subparsers.add_parser("import", help="Import a focused manual supply evidence template.")
    import_parser.add_argument("csv_path", type=Path)
    import_parser.add_argument("--request-bundle-path", type=Path, default=DEFAULT_REQUEST_BUNDLE_PATH)
    import_parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command == "export":
        report = write_focused_manual_supply_packet(
            request_bundle_path=args.request_bundle_path,
            output_dir=args.output_dir,
            limit=args.limit,
        )
        print(json.dumps(report["summary"], indent=2, sort_keys=True))
        print(f"Packet CSV: {report['output_paths']['packet_csv']}")
        print(f"Template CSV: {report['output_paths']['manual_supply_template']}")
        return 0

    report = import_focused_manual_supply_template(
        csv_path=args.csv_path,
        request_bundle_path=args.request_bundle_path,
        output_dir=args.output_dir,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    print(f"Manual snapshots: {report['output_paths']['manual_supply_snapshots']}")
    print(f"Report: {report['output_paths']['report']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
