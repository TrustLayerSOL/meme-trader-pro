"""CLI for quarantined pre-lifecycle forward pattern preview."""

from __future__ import annotations

import argparse
from pathlib import Path

from research.mtp_research.validation.pre_lifecycle_forward_pattern_preview import (
    build_pre_lifecycle_forward_pattern_preview,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build quarantined pre-lifecycle forward pattern preview.")
    parser.add_argument("--data-root", default="/Volumes/ORICO/MemeTraderPro")
    parser.add_argument("--status-path", default=str(Path("theses") / "PRE_LIFECYCLE_FORWARD_PATTERN_PREVIEW_STATUS.md"))
    parser.add_argument("--no-write", action="store_true", help="Build summary in memory without writing reports.")
    args = parser.parse_args(argv)

    summary, paths = build_pre_lifecycle_forward_pattern_preview(
        Path(args.data_root),
        status_path=Path(args.status_path),
        write_outputs=not args.no_write,
    )
    counts = summary["funnel_stats"]["counts"]
    print(f"report_id={summary['report_id']}")
    print(f"quarantine_label={summary['quarantine_label']}")
    print(f"rows_mints_analyzed={summary['rows_mints_analyzed']}")
    print(f"crossed_10k={counts.get('crossed_10k', 0)}")
    print(f"crossed_20k={counts.get('crossed_20k', 0)}")
    print(f"crossed_50k={counts.get('crossed_50k', 0)}")
    print(f"crossed_100k={counts.get('crossed_100k', 0)}")
    print(f"crossed_500k={counts.get('crossed_500k', 0)}")
    print(f"crossed_1m={counts.get('crossed_1m', 0)}")
    print(f"fdv_signal_forward_read={summary['fdv_signal_sanity']['appears_forward']}")
    print(f"network_calls_made={summary['network_calls_made']}")
    if paths:
        print(f"summary_json={paths['summary_json']}")
        print(f"summary_markdown={paths['summary_markdown']}")
        print(f"analysis_dataset_jsonl={paths['analysis_dataset_jsonl']}")
        print(f"status_markdown={paths['status_markdown']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
