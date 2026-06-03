"""CLI for birth-watch to trigger follow-up audit."""

from __future__ import annotations

import argparse
from pathlib import Path

from research.mtp_research.validation.forward_birth_to_trigger_followup_audit import (
    build_birth_to_trigger_followup_audit,
)


def main() -> int:
    args = parse_args()
    summary, paths = build_birth_to_trigger_followup_audit(
        args.data_root,
        output_dir=args.output_dir,
        write_outputs=True,
    )
    print(f"report_id={summary['report_id']}")
    print(f"total_birth_watch_candidates={summary['total_birth_watch_candidates']}")
    print(f"unique_birth_watch_mints={summary['unique_birth_watch_mints']}")
    print(f"birth_mints_with_followup_fdv={summary['birth_mints_with_followup_fdv']}")
    print(f"birth_mints_with_any_trigger_cross={summary['birth_mints_with_any_trigger_cross']}")
    print(f"trigger_cross_counts={summary['trigger_cross_counts']}")
    print(f"conversion_funnel={summary['conversion_funnel']}")
    print(f"target_trigger_qualified_progress_10k={summary['conversion_funnel']['target_trigger_qualified_progress_10k']}")
    print(f"target_trigger_qualified_progress_20k={summary['conversion_funnel']['target_trigger_qualified_progress_20k']}")
    print(f"estimated_births_needed_for_300_crossed_10k={summary['conversion_funnel']['estimated_births_needed_for_300_crossed_10k']}")
    print(f"followup_status_counts={summary['followup_status_counts']}")
    print(f"readiness_classification={summary['readiness_classification']}")
    print(f"recommendation={summary['recommendation']}")
    print(f"summary_json={paths['summary_json']}")
    print(f"summary_markdown={paths['summary_markdown']}")
    print(f"per_mint_csv={paths['per_mint_csv']}")
    print("network_calls_made=0")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit birth-watch candidates for later FDV trigger evidence.")
    parser.add_argument("--data-root", default="/Volumes/ORICO/MemeTraderPro")
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
