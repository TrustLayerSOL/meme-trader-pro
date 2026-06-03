"""CLI for forward 50 freshness/actionability quality audit."""

from __future__ import annotations

import argparse
from pathlib import Path

from research.mtp_research.validation.forward_50_freshness_quality_audit import (
    build_forward_50_freshness_quality_audit,
)


def main() -> int:
    args = parse_args()
    summary, paths = build_forward_50_freshness_quality_audit(
        args.data_root,
        max_candidates=args.max_candidates,
        output_dir=args.output_dir,
        write_outputs=True,
    )
    print(f"report_id={summary['report_id']}")
    print(f"candidates_audited={summary['candidates_audited']}")
    print(f"all_current_candidate_rows_present={summary['all_current_candidate_rows_present']}")
    print(f"unique_mints={summary['unique_mints']}")
    print(f"source_mix={summary['source_mix']}")
    print(f"freshness_class_distribution={summary['freshness_class_distribution']}")
    print(f"actionability_class_distribution={summary['actionability_class_distribution']}")
    print(f"fdv_sanity_distribution={summary['fdv_sanity_distribution']}")
    print(f"duplicate_class_distribution={summary['duplicate_class_distribution']}")
    print(f"readiness_classification={summary['readiness_classification']}")
    print(f"recommendation={summary['recommendation']}")
    print(f"summary_json={paths['summary_json']}")
    print(f"summary_markdown={paths['summary_markdown']}")
    print("network_calls_made=0")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit first forward efficient-mover observations for freshness.")
    parser.add_argument("--data-root", default="/Volumes/ORICO/MemeTraderPro")
    parser.add_argument("--max-candidates", type=int, default=50)
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
