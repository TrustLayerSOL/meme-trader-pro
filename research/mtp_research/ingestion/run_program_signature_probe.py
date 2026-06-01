"""Tiny bounded program-signature probe for launch discovery planning."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from research.mtp_research.ingestion.helius_backfill import HeliusHistoricalAdapter
from research.mtp_research.ingestion.helius_models import HeliusBackfillRequest


def run_probe(
    program_id: str,
    limit: int = 10,
    hydrate_sample: bool = False,
    output_dir: Path | str = "data/backtests/diagnostics/reports",
    execute: bool = False,
    label: str | None = None,
) -> dict[str, Any]:
    safe_limit = max(1, min(limit, 25))
    output_dir = Path(output_dir)
    if not execute:
        return {
            "program_id": program_id,
            "label": label,
            "execute": False,
            "planned_signature_limit": safe_limit,
            "hydrate_sample": hydrate_sample,
            "signatures_found": 0,
            "hydrated_count": 0,
            "likely_launch_related_instructions": [],
            "warning_flags": ["dry_run_no_network_calls"],
            "network_calls": 0,
        }

    adapter = HeliusHistoricalAdapter.from_env()
    signature_result = adapter.fetch_signatures_for_address(
        HeliusBackfillRequest(address=program_id, limit=safe_limit, role="program_signature_probe")
    )
    signatures = [record.signature for record in signature_result.records]
    transactions = adapter.fetch_transactions(signatures[:safe_limit]) if hydrate_sample else []
    likely_launch_instructions = _likely_launch_instruction_summaries(transactions, program_id)
    report = {
        "program_id": program_id,
        "label": label,
        "execute": True,
        "planned_signature_limit": safe_limit,
        "hydrate_sample": hydrate_sample,
        "signatures_found": len(signatures),
        "hydrated_count": len([tx for tx in transactions if tx]),
        "signatures": signatures,
        "likely_launch_related_instructions": likely_launch_instructions,
        "warning_flags": ["tiny_probe_only_do_not_scale_from_this_output"],
        "network_calls": 1 + (len(signatures[:safe_limit]) if hydrate_sample else 0),
    }
    _write_probe_report(report, output_dir)
    return report


def main() -> int:
    args = parse_args()
    result = run_probe(
        program_id=args.program_id,
        limit=args.limit,
        hydrate_sample=args.hydrate_sample,
        output_dir=args.output_dir,
        execute=args.execute,
    )
    if not args.execute:
        print(f"execute={result['execute']}")
        print(f"program_id={result['program_id']}")
        print(f"planned_signature_limit={result['planned_signature_limit']}")
        print(f"hydrate_sample={result['hydrate_sample']}")
        print(f"warning_flags={result['warning_flags']}")
        print("network_calls=0")
        return 0

    print(f"execute={result['execute']}")
    print(f"program_id={result['program_id']}")
    print(f"signatures_found={result['signatures_found']}")
    print(f"hydrated_count={result['hydrated_count']}")
    print(f"likely_launch_related_instructions={result['likely_launch_related_instructions']}")
    print(f"warning_flags={result['warning_flags']}")
    print(f"json_report_path={Path(args.output_dir) / _probe_filename(args.program_id, 'json')}")
    print(f"markdown_report_path={Path(args.output_dir) / _probe_filename(args.program_id, 'md')}")
    print(f"network_calls={result['network_calls']}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a tiny bounded program signature probe.")
    parser.add_argument("--program-id", required=True)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--hydrate-sample", action="store_true")
    parser.add_argument("--output-dir", default="data/backtests/diagnostics/reports")
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args()


def _likely_launch_instruction_summaries(transactions: list[dict[str, Any]], program_id: str) -> list[dict[str, Any]]:
    summaries = []
    for tx in transactions:
        if not tx:
            continue
        message = tx.get("transaction", {}).get("message", {})
        instructions = message.get("instructions", [])
        for instruction in instructions:
            if instruction.get("programId") == program_id:
                parsed = instruction.get("parsed") if isinstance(instruction.get("parsed"), dict) else {}
                summaries.append(
                    {
                        "type": parsed.get("type") or "program_instruction",
                        "program_id": program_id,
                    }
                )
    return summaries[:25]


def _write_probe_report(report: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / _probe_filename(report["program_id"], "json")
    md_path = output_dir / _probe_filename(report["program_id"], "md")
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(_probe_markdown(report), encoding="utf-8")


def _probe_filename(program_id: str, suffix: str) -> str:
    safe = "".join(ch for ch in program_id if ch.isalnum())[:16]
    return f"program_signature_probe_{safe}.{suffix}"


def _probe_markdown(report: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Program Signature Probe",
            "",
            f"- program_id: {report['program_id']}",
            f"- signatures_found: {report['signatures_found']}",
            f"- hydrated_count: {report['hydrated_count']}",
            f"- warning_flags: {report['warning_flags']}",
            "",
            "Tiny probe only. Do not treat this as a launch cohort or validation result.",
            "",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
