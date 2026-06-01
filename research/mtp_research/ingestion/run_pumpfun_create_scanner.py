"""CLI for bounded Pump.fun create-instruction scanning."""

from __future__ import annotations

import argparse
from pathlib import Path

from research.mtp_research.ingestion.helius_backfill import HeliusHistoricalAdapter
from research.mtp_research.ingestion.pumpfun_create_scan_report import write_pumpfun_create_scan_report
from research.mtp_research.ingestion.pumpfun_create_scanner import PumpFunCreateScanner
from research.mtp_research.ingestion.run_program_signature_probe import PUMP_FUN_PROGRAM_ID


def main() -> int:
    args = parse_args()
    adapter = HeliusHistoricalAdapter.from_env() if args.execute else None
    scanner = PumpFunCreateScanner(adapter=adapter, program_id=args.program_id)
    report = scanner.scan(
        execute=args.execute,
        max_batches=args.max_batches,
        signatures_per_batch=args.signatures_per_batch,
        hydrate_limit_per_batch=args.hydrate_limit_per_batch,
        target_create_candidates=args.target_create_candidates,
        max_signatures_total=args.max_signatures_total,
        cursor_before=args.cursor_before,
        include_low_confidence=args.include_low_confidence,
        emit_rejected_examples=args.emit_rejected_examples,
        min_confidence=args.min_confidence,
    )
    paths = write_pumpfun_create_scan_report(report, Path(args.output_dir))
    print(f"executed={report.executed}")
    print(f"program_id={report.program_id}")
    print(f"max_batches={report.max_batches}")
    print(f"signatures_per_batch={report.signatures_per_batch}")
    print(f"hydrate_limit_per_batch={report.hydrate_limit_per_batch}")
    print(f"signatures_seen_total={report.signatures_seen_total}")
    print(f"transactions_hydrated_total={report.transactions_hydrated_total}")
    print(f"direct_pumpfun_instruction_count={report.direct_pumpfun_instruction_count}")
    print(f"create_candidate_count={report.create_candidate_count}")
    print(f"verified_create_candidate_count={len(report.verified_create_candidates)}")
    print(f"rejected_create_like_count={len(report.rejected_create_like_candidates)}")
    print(f"unknown_pumpfun_instruction_count={len(report.unknown_pumpfun_instructions)}")
    unknown_summary = report.metadata_json.get("unknown_instruction_summary", {})
    cluster_count = len(unknown_summary.get("clusters", [])) if isinstance(unknown_summary, dict) else 0
    print(f"unknown_instruction_clusters={cluster_count}")
    print(f"include_low_confidence={args.include_low_confidence}")
    print(f"emit_rejected_examples={args.emit_rejected_examples}")
    print(f"min_confidence={args.min_confidence}")
    for candidate in report.verified_create_candidates[:5]:
        print(
            "candidate "
            f"signature={candidate.signature} block_time={candidate.block_time} "
            f"token_mint={candidate.token_mint} bonding_curve={candidate.bonding_curve} "
            f"creator_wallet={candidate.creator_wallet} confidence={candidate.extraction_confidence}"
        )
    print(f"viability={report.viability}")
    print(f"recommended_next_action={report.recommended_next_action}")
    print(f"warning_flags={report.warning_flags}")
    print(f"json_report_path={paths['json']}")
    print(f"markdown_report_path={paths['markdown']}")
    print(f"network_calls={report.metadata_json.get('network_calls_estimate', 0)}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bounded Pump.fun create-instruction scanner.")
    parser.add_argument("--program-id", default=PUMP_FUN_PROGRAM_ID)
    parser.add_argument("--max-batches", type=int, default=5)
    parser.add_argument("--signatures-per-batch", type=int, default=25)
    parser.add_argument("--hydrate-limit-per-batch", type=int, default=25)
    parser.add_argument("--target-create-candidates", type=int, default=5)
    parser.add_argument("--max-signatures-total", type=int, default=250)
    parser.add_argument("--cursor-before")
    parser.add_argument("--output-dir", default="data/backtests/diagnostics/reports")
    parser.add_argument("--include-low-confidence", action="store_true")
    parser.add_argument("--emit-rejected-examples", action="store_true")
    parser.add_argument("--min-confidence", choices=["low", "medium", "high"], default="medium")
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
