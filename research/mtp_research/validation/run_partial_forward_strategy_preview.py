"""CLI for the partial forward strategy preview."""

from __future__ import annotations

import argparse
from pathlib import Path

from research.mtp_research.validation.partial_forward_strategy_preview import (
    run_partial_forward_strategy_preview,
)


def main() -> int:
    args = parse_args()
    result = run_partial_forward_strategy_preview(
        data_root=Path(args.data_root).expanduser() if args.data_root else None,
        source_root=Path(args.source_root).expanduser() if args.source_root else None,
        execute=args.execute,
    )
    print("## Partial Forward Strategy Preview")
    print(f"execute={result.get('execute')}")
    print(f"sample_label={result.get('sample_label')}")
    print(f"source_root={result.get('source_root')}")
    print(f"rows_mints_analyzed={result.get('rows_mints_analyzed', 0)}")
    print(f"readiness={result.get('readiness')}")
    print(f"quality_warnings={result.get('quality_warnings', [])}")
    print(f"report_root={result.get('report_root') or result.get('output_paths', {}).get('manifest_json')}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a diagnostic partial forward strategy preview.")
    parser.add_argument("--data-root", default=None)
    parser.add_argument("--source-root", default=None)
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
