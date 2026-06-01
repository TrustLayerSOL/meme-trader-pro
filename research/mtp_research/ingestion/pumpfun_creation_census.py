"""Pump.fun creation-event census artifacts.

The census is a parser-quality artifact. It is not a launch dataset, signal
feed, registry importer, or validation result.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PumpFunCreationCensusRow:
    mint: str | None
    creator_deployer: str | None
    creation_signature: str
    slot: int | None
    block_time: int | None
    parser_confidence: str
    instruction_type: str
    source_method: str
    accepted: bool = False
    rejection_reason: str | None = None
    bonding_curve: str | None = None
    associated_bonding_curve: str | None = None
    instruction_index: int | None = None
    instruction_discriminator: str | None = None
    metadata_json: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_creation_census_from_scan_report(report: dict[str, Any]) -> list[PumpFunCreationCensusRow]:
    rows: list[PumpFunCreationCensusRow] = []
    for candidate in report.get("verified_create_candidates", []):
        rows.append(
            PumpFunCreationCensusRow(
                mint=candidate.get("token_mint"),
                creator_deployer=candidate.get("creator_wallet"),
                creation_signature=candidate.get("signature", ""),
                slot=candidate.get("slot"),
                block_time=candidate.get("block_time"),
                parser_confidence=candidate.get("extraction_confidence", "unknown"),
                instruction_type=candidate.get("metadata_json", {}).get("instruction_type", "program_instruction"),
                source_method="pumpfun_create_scanner_verified",
                accepted=True,
                bonding_curve=candidate.get("bonding_curve"),
                associated_bonding_curve=candidate.get("associated_bonding_curve"),
                instruction_index=candidate.get("instruction_index"),
                instruction_discriminator=candidate.get("instruction_discriminator"),
                metadata_json={"warning_flags": candidate.get("warning_flags", [])},
            )
        )
    for diagnostic in report.get("rejected_create_like_candidates", []):
        rows.append(_diagnostic_to_row(diagnostic, "pumpfun_create_scanner_rejected"))
    for diagnostic in report.get("unknown_pumpfun_instructions", []):
        rows.append(_diagnostic_to_row(diagnostic, "pumpfun_create_scanner_unknown"))
    return rows


def write_creation_census(rows: list[PumpFunCreationCensusRow], output_path: Path | str) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row.to_dict(), sort_keys=True))
            f.write("\n")
    return output_path


def write_creation_census_csv(rows: list[PumpFunCreationCensusRow], output_path: Path | str) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "mint",
        "creator_deployer",
        "creation_signature",
        "slot",
        "block_time",
        "parser_confidence",
        "instruction_type",
        "source_method",
        "accepted",
        "rejection_reason",
        "bonding_curve",
        "associated_bonding_curve",
        "instruction_index",
        "instruction_discriminator",
    ]
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            payload = row.to_dict()
            writer.writerow({field: payload.get(field) for field in fields})
    return output_path


def load_census_rows(path: Path | str) -> list[PumpFunCreationCensusRow]:
    path = Path(path)
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            text = line.strip()
            if text:
                rows.append(PumpFunCreationCensusRow(**json.loads(text)))
    return rows


def _diagnostic_to_row(diagnostic: dict[str, Any], source_method: str) -> PumpFunCreationCensusRow:
    reasons = diagnostic.get("rejection_reasons", [])
    return PumpFunCreationCensusRow(
        mint=None,
        creator_deployer=None,
        creation_signature=diagnostic.get("signature", ""),
        slot=None,
        block_time=None,
        parser_confidence="rejected",
        instruction_type=diagnostic.get("instruction_classification", "unknown_pumpfun_instruction"),
        source_method=source_method,
        accepted=False,
        rejection_reason=";".join(reasons) if reasons else "unknown",
        instruction_index=diagnostic.get("instruction_index"),
        instruction_discriminator=diagnostic.get("instruction_discriminator"),
        metadata_json=diagnostic.get("metadata_json", {}),
    )
