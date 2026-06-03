"""CLI for the full structural enrichment campaign."""

from __future__ import annotations

import argparse
from pathlib import Path

from research.mtp_research.validation.full_structural_enrichment_campaign import (
    DEFAULT_COMBINED_REPAIRED_PATH,
    DEFAULT_TRIGGER_ROWS_PATH,
    run_full_structural_enrichment_campaign,
)


def main() -> int:
    args = parse_args()
    input_paths = {
        "trigger_rows": Path(args.trigger_rows_path),
        "combined_repaired": Path(args.combined_repaired_path),
    }
    if args.events_path is not None:
        input_paths["events"] = Path(args.events_path)
    if args.sol_usd_path is not None:
        input_paths["sol_usd"] = Path(args.sol_usd_path)
    report, paths = run_full_structural_enrichment_campaign(
        data_root=Path(args.data_root) if args.data_root else None,
        input_paths=input_paths,
        output_paths={"status_path": Path(args.status_path)} if args.status_path else None,
        execute_helius=args.execute_helius,
        execute_dexscreener=args.execute_dexscreener,
        max_helius_credits=args.max_helius_credits,
        contract_authority_workers=args.contract_authority_workers,
    )
    print(f"report_id={report['report_id']}")
    print(f"readiness_classification={report['readiness_classification']}")
    print(f"helius_execute={report['helius']['execute_completed']}")
    print(f"dexscreener_execute={report['dexscreener']['execute_completed']}")
    print(f"credits_used={report['helius']['credits_used']}")
    print(f"dexscreener_calls_used={report['dexscreener']['calls_used']}")
    print(f"launches_enriched={report['launches_enriched']}")
    print(f"master_rows={report['master_rows']}")
    print(f"warnings={report['warnings']}")
    print(f"master_parquet_path={paths['master_parquet_path']}")
    print(f"master_jsonl_path={paths['master_jsonl_path']}")
    print(f"coverage_json_path={paths['coverage_json_path']}")
    print(f"coverage_markdown_path={paths['coverage_markdown_path']}")
    print(f"status_path={paths['status_path']}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run full structural enrichment campaign.")
    parser.add_argument("--data-root", default=None)
    parser.add_argument("--trigger-rows-path", default=DEFAULT_TRIGGER_ROWS_PATH)
    parser.add_argument("--combined-repaired-path", default=DEFAULT_COMBINED_REPAIRED_PATH)
    parser.add_argument("--events-path", default=None)
    parser.add_argument("--sol-usd-path", default=None)
    parser.add_argument("--status-path", default=None)
    parser.add_argument("--max-helius-credits", type=int, default=500_000)
    parser.add_argument("--execute-helius", action="store_true")
    parser.add_argument("--execute-dexscreener", action="store_true")
    parser.add_argument("--contract-authority-workers", type=int, default=8)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
