"""CLI for forward birth funnel sanity audit."""

from __future__ import annotations

import argparse
from pathlib import Path

from research.mtp_research.validation.forward_birth_funnel_sanity_audit import (
    build_forward_birth_funnel_sanity_audit,
)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    summary, paths = build_forward_birth_funnel_sanity_audit(
        args.data_root,
        output_dir=args.output_dir,
        write_outputs=True,
    )
    print(f"report_id={summary['report_id']}")
    print(f"total_forward_candidates={summary['total_forward_candidates']}")
    print(f"raw_funnel_counts={summary['raw_funnel_counts']}")
    print(f"strict_deduped_funnel_counts={summary['strict_deduped_funnel_counts']}")
    print(f"observed_followup_only_funnel_counts={summary['observed_followup_only_funnel_counts']}")
    print(f"true_near_birth_funnel_counts={summary['true_near_birth_funnel_counts']}")
    print(f"duplicate_counts={summary['duplicate_counts']}")
    print(f"milestone_provenance_summary={summary['milestone_provenance_summary']}")
    print(f"milestone_ordering_summary={summary['milestone_ordering_summary']}")
    print(f"freshness_summary={summary['freshness_summary']}")
    print(f"followup_bias_summary={summary['followup_bias_summary']}")
    print(f"validity_classification={summary['validity_classification']}")
    print(f"recommendation={summary['recommendation']}")
    for key in sorted(paths):
        print(f"{key}={paths[key]}")
    print("network_calls_made=0")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a read-only forward birth funnel sanity audit.")
    parser.add_argument("--data-root", default="/Volumes/ORICO/MemeTraderPro")
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
