"""Report writer for bounded Pump.fun create scans."""

from __future__ import annotations

import json
from pathlib import Path

from research.mtp_research.ingestion.pumpfun_create_scanner_models import PumpFunCreateScanReport


def write_pumpfun_create_scan_report(
    report: PumpFunCreateScanReport,
    output_dir: Path | str,
) -> dict[str, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    base_name = report.report_id
    if not report.executed:
        base_name = "pumpfun_create_scan_plan"
    json_path = output_dir / f"{base_name}.json"
    markdown_path = output_dir / f"{base_name}.md"
    json_path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(_markdown(report), encoding="utf-8")
    return {"json": json_path, "markdown": markdown_path}


def _markdown(report: PumpFunCreateScanReport) -> str:
    lines = [
        "# Pump.fun Create-Instruction Scan",
        "",
        "**Warning:** This is a bounded discovery probe, not a launch dataset.",
        "",
        f"- Program ID: `{report.program_id}`",
        f"- Executed: `{report.executed}`",
        f"- Max batches: `{report.max_batches}`",
        f"- Signatures per batch: `{report.signatures_per_batch}`",
        f"- Hydrate limit per batch: `{report.hydrate_limit_per_batch}`",
        f"- Signatures seen: `{report.signatures_seen_total}`",
        f"- Transactions hydrated: `{report.transactions_hydrated_total}`",
        f"- Direct Pump.fun instructions: `{report.direct_pumpfun_instruction_count}`",
        f"- Verified create candidates: `{report.create_candidate_count}`",
        f"- Rejected create-like candidates: `{len(report.rejected_create_like_candidates)}`",
        f"- Unknown Pump.fun instructions: `{len(report.unknown_pumpfun_instructions)}`",
        f"- Viability: `{report.viability}`",
        f"- Recommended next action: `{report.recommended_next_action}`",
        f"- Warning flags: `{report.warning_flags}`",
        "",
        "## Batch Summary",
        "",
        "| Batch | Signatures | Hydrated | Direct Instructions | Create Candidates | Next Cursor | Warnings |",
        "|---:|---:|---:|---:|---:|---|---|",
    ]
    if report.batches:
        for batch in report.batches:
            lines.append(
                "| "
                f"{batch.batch_index} | {batch.signatures_seen} | {batch.transactions_hydrated} | "
                f"{batch.direct_pumpfun_instruction_count} | {batch.create_candidate_count} | "
                f"{batch.next_cursor_before or ''} | {', '.join(batch.warning_flags)} |"
            )
    else:
        lines.append("|  | 0 | 0 | 0 | 0 |  |  |")
    lines.extend(
        [
            "",
            "## Verified Create Candidates",
            "",
            "| Signature | Block Time | Token Mint | Bonding Curve | Associated Bonding Curve | Creator Wallet | Accounts | Confidence | Warnings |",
            "|---|---:|---|---|---|---|---:|---|---|",
        ]
    )
    if report.verified_create_candidates:
        for candidate in report.verified_create_candidates:
            lines.append(
                "| "
                f"{candidate.signature} | {candidate.block_time or ''} | {candidate.token_mint or ''} | "
                f"{candidate.bonding_curve or ''} | {candidate.associated_bonding_curve or ''} | "
                f"{candidate.creator_wallet or ''} | {candidate.account_count} | "
                f"{candidate.extraction_confidence} | {', '.join(candidate.warning_flags)} |"
            )
    else:
        lines.append("|  |  |  |  |  |  | 0 |  |  |")
    lines.extend(
        [
            "",
            "## Rejected Create-Like Candidates",
            "",
            "| Signature | Instruction | Accounts | Discriminator | Reasons |",
            "|---|---:|---:|---|---|",
        ]
    )
    if report.rejected_create_like_candidates:
        for diagnostic in report.rejected_create_like_candidates:
            lines.append(
                "| "
                f"{diagnostic.signature} | {diagnostic.instruction_index or 0} | "
                f"{diagnostic.account_count} | {diagnostic.instruction_discriminator or ''} | "
                f"{', '.join(diagnostic.rejection_reasons)} |"
            )
    else:
        lines.append("|  |  | 0 |  |  |")
    lines.extend(
        [
            "",
            "## Unknown Pump.fun Instructions",
            "",
            "| Signature | Instruction | Accounts | Discriminator | Reasons |",
            "|---|---:|---:|---|---|",
        ]
    )
    if report.unknown_pumpfun_instructions:
        for diagnostic in report.unknown_pumpfun_instructions:
            lines.append(
                "| "
                f"{diagnostic.signature} | {diagnostic.instruction_index or 0} | "
                f"{diagnostic.account_count} | {diagnostic.instruction_discriminator or ''} | "
                f"{', '.join(diagnostic.rejection_reasons)} |"
            )
    else:
        lines.append("|  |  | 0 |  |  |")
    lines.append("")
    return "\n".join(lines)
