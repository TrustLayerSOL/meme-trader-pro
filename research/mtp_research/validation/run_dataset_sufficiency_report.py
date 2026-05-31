"""CLI for dataset sufficiency diagnostics."""

from __future__ import annotations

import argparse
from pathlib import Path

from research.mtp_research.pipeline.real_candidate_filter import real_token_mints_from_registry
from research.mtp_research.validation.dataset_sufficiency_report import (
    build_dataset_sufficiency_report,
    write_dataset_sufficiency_json,
    write_dataset_sufficiency_markdown,
)
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Build dataset sufficiency report.")
    parser.add_argument("--dataset-path", default="data/backtests/research_dataset.jsonl")
    parser.add_argument("--real-only", action="store_true")
    parser.add_argument("--min-liquidity-usd", type=float)
    parser.add_argument("--output-dir", default="data/backtests/reports")
    args = parser.parse_args()

    rows = ResearchDatasetStore(args.dataset_path).load_all()
    token_mints = real_token_mints_from_registry(min_liquidity_usd=args.min_liquidity_usd) if args.real_only else None
    report = build_dataset_sufficiency_report(rows, token_mints=token_mints)
    output_dir = Path(args.output_dir)
    markdown_path = write_dataset_sufficiency_markdown(report, output_dir / f"{report['report_id']}.md")
    json_path = write_dataset_sufficiency_json(report, output_dir / f"{report['report_id']}.json")
    sufficiency = report["sufficiency"]
    selectability = report["selectability"]

    print(f"total_rows={sufficiency['total_rows']}")
    print(f"real_only_rows={sufficiency['real_only_rows']}")
    print(f"rows_with_entry_price={sufficiency['rows_with_entry_price']}")
    print(f"rows_with_forward_return={sufficiency['rows_with_forward_return']}")
    print(f"rows_by_label_quality={sufficiency['rows_by_label_quality']}")
    print(f"rows_by_entry_price_source={sufficiency['rows_by_entry_price_source']}")
    print(f"rows_min_label_quality_sparse={selectability['rows_min_label_quality_sparse']}")
    print(f"rows_min_label_quality_good={selectability['rows_min_label_quality_good']}")
    print(f"markdown_path={markdown_path}")
    print(f"json_path={json_path}")
    print("network_calls=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
