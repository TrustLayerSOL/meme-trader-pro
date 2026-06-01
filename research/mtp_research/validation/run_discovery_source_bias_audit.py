"""CLI for discovery-source bias audit."""

from __future__ import annotations

import argparse

from research.mtp_research.validation.discovery_source_bias_audit import (
    DEFAULT_LIFECYCLE_LAUNCHES_PATH,
    DEFAULT_REGISTRY_PATH,
    DEFAULT_REPORT_DIR,
    run_discovery_source_bias_audit,
)


def main() -> int:
    args = parse_args()
    report = run_discovery_source_bias_audit(
        registry_path=args.registry_path,
        lifecycle_launches_path=args.lifecycle_launches_path,
        output_dir=args.output_dir,
    )
    print(f"registry_candidate_count={report['registry_candidate_count']}")
    print(f"lifecycle_launch_count={report['lifecycle_launch_count']}")
    print(f"registry_source_counts={report['registry_source_counts']}")
    print(f"lifecycle_source_counts={report['lifecycle_source_counts']}")
    print(f"venue_counts={report['venue_counts']}")
    print(f"launch_regime_counts={report['launch_regime_counts']}")
    print(f"pool_address_counts={report['pool_address_counts']}")
    print(f"launch_timestamp_source_counts={report['launch_timestamp_source_counts']}")
    print(f"launch_timestamp_confidence_counts={report['launch_timestamp_confidence_counts']}")
    print(f"recommended_next_source={report['recommended_next_source']}")
    print(f"warning_flags={report['warning_flags']}")
    print(f"json_report_path={args.output_dir}/discovery_source_bias_audit.json")
    print(f"markdown_report_path={args.output_dir}/discovery_source_bias_audit.md")
    print("network_calls=0")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit launch discovery source concentration and timestamp confidence.")
    parser.add_argument("--registry-path", default=str(DEFAULT_REGISTRY_PATH))
    parser.add_argument("--lifecycle-launches-path", default=str(DEFAULT_LIFECYCLE_LAUNCHES_PATH))
    parser.add_argument("--output-dir", default=str(DEFAULT_REPORT_DIR))
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
