"""Tiny bounded program-signature probe for launch discovery planning."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from research.mtp_research.ingestion.helius_backfill import HeliusHistoricalAdapter
from research.mtp_research.ingestion.helius_models import HeliusBackfillRequest


PUMP_FUN_PROGRAM_ID = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"


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
    transaction_summary = summarize_hydrated_transactions(transactions, program_id)
    report = {
        "program_id": program_id,
        "label": label,
        "execute": True,
        "planned_signature_limit": safe_limit,
        "hydrate_sample": hydrate_sample,
        "signatures_found": len(signatures),
        "hydrated_count": len([tx for tx in transactions if tx]),
        "signatures": signatures,
        "likely_launch_related_instructions": transaction_summary["likely_launch_related_instructions"],
        "decoded_samples": transaction_summary["decoded_samples"],
        "candidate_token_mints": transaction_summary["candidate_token_mints"],
        "bonding_curve_accounts": transaction_summary["bonding_curve_accounts"],
        "creator_wallets": transaction_summary["creator_wallets"],
        "verified_block_times": transaction_summary["verified_block_times"],
        "can_extract_candidate_fields": transaction_summary["can_extract_candidate_fields"],
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
    print(f"candidate_token_mints={result.get('candidate_token_mints', [])}")
    print(f"bonding_curve_accounts={result.get('bonding_curve_accounts', [])}")
    print(f"creator_wallets={result.get('creator_wallets', [])}")
    print(f"verified_block_times={result.get('verified_block_times', [])}")
    print(f"can_extract_candidate_fields={result.get('can_extract_candidate_fields', False)}")
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


def summarize_hydrated_transactions(transactions: list[dict[str, Any]], program_id: str) -> dict[str, Any]:
    decoded_samples = []
    likely_launch_instructions = []
    candidate_token_mints: set[str] = set()
    bonding_curve_accounts: set[str] = set()
    creator_wallets: set[str] = set()
    verified_block_times: set[int] = set()
    for tx in transactions:
        if not tx:
            continue
        signature = _signature(tx)
        block_time = tx.get("blockTime")
        if isinstance(block_time, int):
            verified_block_times.add(block_time)
        message = tx.get("transaction", {}).get("message", {})
        instructions = message.get("instructions", [])
        for instruction in instructions:
            if instruction.get("programId") == program_id:
                sample = _summarize_program_instruction(tx, instruction, program_id, signature)
                decoded_samples.append(sample)
                likely_launch_instructions.append(
                    {
                        "type": sample["instruction_type"],
                        "program_id": program_id,
                        "classification": sample["instruction_classification"],
                    }
                )
                if sample.get("candidate_token_mint"):
                    candidate_token_mints.add(sample["candidate_token_mint"])
                if sample.get("bonding_curve_account"):
                    bonding_curve_accounts.add(sample["bonding_curve_account"])
                if sample.get("creator_wallet"):
                    creator_wallets.add(sample["creator_wallet"])
    return {
        "decoded_samples": decoded_samples[:25],
        "likely_launch_related_instructions": likely_launch_instructions[:25],
        "candidate_token_mints": sorted(candidate_token_mints),
        "bonding_curve_accounts": sorted(bonding_curve_accounts),
        "creator_wallets": sorted(creator_wallets),
        "verified_block_times": sorted(verified_block_times),
        "can_extract_candidate_fields": bool(candidate_token_mints or bonding_curve_accounts or creator_wallets),
    }


def _summarize_program_instruction(
    tx: dict[str, Any],
    instruction: dict[str, Any],
    program_id: str,
    signature: str | None,
) -> dict[str, Any]:
    parsed = instruction.get("parsed") if isinstance(instruction.get("parsed"), dict) else {}
    accounts = [str(account) for account in instruction.get("accounts", [])]
    classification = _classify_program_instruction(program_id, accounts, parsed)
    summary = {
        "signature": signature,
        "slot": tx.get("slot"),
        "block_time": tx.get("blockTime"),
        "program_id": program_id,
        "instruction_type": parsed.get("type") or "program_instruction",
        "instruction_classification": classification,
        "account_count": len(accounts),
        "accounts": accounts[:16],
    }
    if program_id == PUMP_FUN_PROGRAM_ID and len(accounts) >= 8 and classification == "pump_fun_possible_create":
        summary.update(
            {
                "candidate_token_mint": accounts[0],
                "bonding_curve_account": accounts[2],
                "associated_bonding_curve_account": accounts[3] if len(accounts) > 3 else None,
                "creator_wallet": accounts[7],
                "launch_timestamp_source": "verified_bonding_curve_creation",
            }
        )
    return summary


def _classify_program_instruction(program_id: str, accounts: list[str], parsed: dict[str, Any]) -> str:
    parsed_type = str(parsed.get("type", "")).lower()
    if parsed_type:
        return f"parsed_{parsed_type}"
    if program_id == PUMP_FUN_PROGRAM_ID and len(accounts) >= 14:
        return "pump_fun_possible_create"
    return "program_instruction"


def _signature(tx: dict[str, Any]) -> str | None:
    signatures = tx.get("transaction", {}).get("signatures", [])
    if signatures:
        return signatures[0]
    return tx.get("signature")


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
            f"- candidate_token_mints: {report.get('candidate_token_mints', [])}",
            f"- bonding_curve_accounts: {report.get('bonding_curve_accounts', [])}",
            f"- creator_wallets: {report.get('creator_wallets', [])}",
            f"- verified_block_times: {report.get('verified_block_times', [])}",
            f"- can_extract_candidate_fields: {report.get('can_extract_candidate_fields', False)}",
            f"- warning_flags: {report['warning_flags']}",
            "",
            "Tiny probe only. Do not treat this as a launch cohort or validation result.",
            "",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
