"""CLI for creator-net-flow efficient-mover formal descriptive thesis."""

from __future__ import annotations

import argparse
from pathlib import Path

from research.mtp_research.validation.creator_net_flow_efficient_mover_thesis import (
    DEFAULT_FEATURE_COMPARISON_PATH,
    DEFAULT_MASTER_JSONL_PATH,
    DEFAULT_MASTER_PATH,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_STATUS_PATH,
    build_creator_net_flow_efficient_mover_thesis,
)


def main() -> int:
    args = parse_args()
    report, paths = build_creator_net_flow_efficient_mover_thesis(
        master_path=Path(args.master_path),
        jsonl_fallback=Path(args.jsonl_fallback),
        feature_comparison_path=Path(args.feature_comparison_path),
        output_dir=Path(args.output_dir),
        status_path=Path(args.status_path),
    )
    print(f"report_id={report['report_id']}")
    print(f"classification={report['classification']}")
    print(f"efficient_mover_rows={report['efficient_mover_rows_analyzed']}")
    print(f"creator_net_flow_coverage_pct={report.get('coverage_audit', {}).get('creator_net_flow_coverage_pct')}")
    print(f"expected_direction={report.get('frozen_definition', {}).get('expected_direction')}")
    print(f"validation_runs={report['guardrails']['validation_runs']}")
    print(f"thesis_runs={report['guardrails']['thesis_runs']}")
    print(f"next_recommendation={report['next_recommendation']['action']}")
    print(f"summary_json_path={paths['summary_json_path']}")
    print(f"summary_markdown_path={paths['summary_markdown_path']}")
    print(f"tier_comparison_path={paths['tier_comparison_path']}")
    print(f"robustness_table_path={paths['robustness_table_path']}")
    print(f"fdv_relationship_path={paths['fdv_relationship_path']}")
    print(f"status_path={paths['status_path']}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run creator-net-flow efficient-mover descriptive thesis.")
    parser.add_argument("--master-path", default=DEFAULT_MASTER_PATH)
    parser.add_argument("--jsonl-fallback", default=DEFAULT_MASTER_JSONL_PATH)
    parser.add_argument("--feature-comparison-path", default=DEFAULT_FEATURE_COMPARISON_PATH)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--status-path", default=DEFAULT_STATUS_PATH)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
