"""CLI for the Axiom historical parity mapper."""

from __future__ import annotations

import argparse

from research.mtp_research.validation.axiom_historical_parity_mapper import (
    DEFAULT_OUTPUT_DIR,
    DEFAULT_STATUS_PATH,
    build_axiom_historical_parity_report,
)


def main() -> int:
    args = parse_args()
    report, paths = build_axiom_historical_parity_report(
        output_dir=args.output_dir,
        status_path=args.status_path,
    )
    summary = report["summary"]
    recommendation = report["recommended_next_execution"]
    print(f"report_id={report['report_id']}")
    print(f"readiness_classification={report['readiness_classification']}")
    print(f"axiom_concepts_mapped={summary['axiom_concepts_mapped']}")
    print(f"historical_fields_mapped={summary['historical_fields_mapped']}")
    print(f"ready_now_or_with_local_join_count={summary['ready_now_or_with_local_join_count']}")
    print(f"helius_needed_field_count={summary['helius_needed_field_count']}")
    print(f"blocked_field_count={summary['blocked_field_count']}")
    print(f"recommended_next_execution={recommendation['action']}")
    for key, path in paths.items():
        print(f"{key}={path}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Axiom-style historical parity mapping reports.")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--status-path", default=DEFAULT_STATUS_PATH)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
