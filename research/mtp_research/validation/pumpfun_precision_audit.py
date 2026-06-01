"""Manual precision-audit helpers for Pump.fun creation census rows."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from research.mtp_research.ingestion.helius_backfill import HeliusHistoricalAdapter
from research.mtp_research.ingestion.pumpfun_creation_census import PumpFunCreationCensusRow, load_census_rows
from research.mtp_research.ingestion.pumpfun_create_scanner import (
    PUMPFUN_CREATE_LAYOUTS,
    _instruction_discriminator,
    _is_signer_or_fee_payer,
)
from research.mtp_research.ingestion.run_program_signature_probe import PUMP_FUN_PROGRAM_ID


VALID_REVIEW_LABELS = {"reviewed_valid", "reviewed_invalid", "uncertain"}


@dataclass
class PumpFunPrecisionReview:
    creation_signature: str
    review_label: str
    reviewer_notes: str = ""
    metadata_json: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def deterministic_precision_sample(
    rows: list[PumpFunCreationCensusRow],
    sample_size: int,
) -> list[PumpFunCreationCensusRow]:
    ordered = sorted(rows, key=lambda row: (row.block_time or 0, row.creation_signature, row.instruction_index or -1))
    return ordered[:sample_size]


def write_precision_review_template(
    rows: list[PumpFunCreationCensusRow],
    output_path: Path | str,
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for row in rows:
            review = PumpFunPrecisionReview(
                creation_signature=row.creation_signature,
                review_label="uncertain",
                metadata_json={
                    "mint": row.mint,
                    "creator_deployer": row.creator_deployer,
                    "parser_confidence": row.parser_confidence,
                    "rejection_reason": row.rejection_reason,
                },
            )
            f.write(json.dumps(review.to_dict(), sort_keys=True))
            f.write("\n")
    return output_path


def auto_review_precision_sample(
    rows: list[PumpFunCreationCensusRow],
    *,
    adapter: HeliusHistoricalAdapter,
    sample_size: int,
) -> list[PumpFunPrecisionReview]:
    """Hydrate a deterministic sample and verify create rows against raw tx facts.

    This is intentionally narrow parser QA. It verifies only creation-event
    fields already present in the census and does not collect lifecycle data.
    """
    sample = deterministic_precision_sample(rows, sample_size)
    transactions = adapter.fetch_transactions([row.creation_signature for row in sample])
    return [
        _auto_review_row(row, transaction)
        for row, transaction in zip(sample, transactions, strict=False)
    ]


def write_precision_reviews(
    reviews: list[PumpFunPrecisionReview],
    output_path: Path | str,
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for review in reviews:
            f.write(json.dumps(review.to_dict(), sort_keys=True))
            f.write("\n")
    return output_path


def load_precision_reviews(path: Path | str) -> list[PumpFunPrecisionReview]:
    path = Path(path)
    if not path.exists():
        return []
    reviews = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            text = line.strip()
            if not text:
                continue
            payload = json.loads(text)
            label = payload.get("review_label", "uncertain")
            if label not in VALID_REVIEW_LABELS:
                label = "uncertain"
            reviews.append(
                PumpFunPrecisionReview(
                    creation_signature=payload["creation_signature"],
                    review_label=label,
                    reviewer_notes=payload.get("reviewer_notes", ""),
                    metadata_json=dict(payload.get("metadata_json", {})),
                )
            )
    return reviews


def precision_summary(census_path: Path | str, review_path: Path | str) -> dict[str, Any]:
    rows = load_census_rows(census_path)
    reviews = load_precision_reviews(review_path)
    label_counts = Counter(review.review_label for review in reviews)
    reviewed = label_counts["reviewed_valid"] + label_counts["reviewed_invalid"]
    precision = None
    if reviewed:
        precision = label_counts["reviewed_valid"] / reviewed
    return {
        "census_rows": len(rows),
        "review_rows": len(reviews),
        "review_label_counts": dict(sorted(label_counts.items())),
        "reviewed_precision": precision,
        "acceptable_for_scaling": bool(precision is not None and precision >= 0.95 and reviewed >= 20),
        "warning_flags": _warning_flags(rows, reviews, precision, reviewed),
    }


def _auto_review_row(row: PumpFunCreationCensusRow, transaction: dict[str, Any]) -> PumpFunPrecisionReview:
    if not transaction:
        return PumpFunPrecisionReview(
            creation_signature=row.creation_signature,
            review_label="uncertain",
            reviewer_notes="transaction_missing_or_unavailable",
            metadata_json={"source_method": "auto_hydrated_create_v2_sanity"},
        )

    checks = _auto_review_checks(row, transaction)
    hard_failures = [name for name, passed in checks.items() if passed is False]
    unknowns = [name for name, passed in checks.items() if passed is None]
    if hard_failures:
        label = "reviewed_invalid"
        notes = "failed_checks=" + ",".join(hard_failures)
    elif unknowns:
        label = "uncertain"
        notes = "unknown_checks=" + ",".join(unknowns)
    else:
        label = "reviewed_valid"
        notes = "auto_hydrated_create_v2_sanity_passed"

    return PumpFunPrecisionReview(
        creation_signature=row.creation_signature,
        review_label=label,
        reviewer_notes=notes,
        metadata_json={
            "source_method": "auto_hydrated_create_v2_sanity",
            "mint": row.mint,
            "creator_deployer": row.creator_deployer,
            "bonding_curve": row.bonding_curve,
            "instruction_index": row.instruction_index,
            "instruction_discriminator": row.instruction_discriminator,
            "checks": checks,
        },
    )


def _auto_review_checks(row: PumpFunCreationCensusRow, transaction: dict[str, Any]) -> dict[str, bool | None]:
    instruction = _instruction_at_index(transaction, row.instruction_index)
    if instruction is None:
        return {
            "instruction_present": False,
            "program_id_matches": None,
            "discriminator_matches": None,
            "create_v2_log_present": None,
            "mint_matches_account_0": None,
            "bonding_curve_matches_account_2": None,
            "associated_bonding_curve_matches_account_3": None,
            "creator_matches_account_5": None,
            "creator_is_signer_or_fee_payer": None,
            "slot_matches": transaction.get("slot") == row.slot if row.slot is not None else None,
            "block_time_matches": transaction.get("blockTime") == row.block_time if row.block_time is not None else None,
        }

    accounts = [str(account) for account in instruction.get("accounts", [])]
    layout = PUMPFUN_CREATE_LAYOUTS.get(row.instruction_discriminator or "")
    return {
        "instruction_present": True,
        "program_id_matches": instruction.get("programId") == PUMP_FUN_PROGRAM_ID,
        "discriminator_matches": _instruction_discriminator(instruction) == row.instruction_discriminator,
        "create_v2_log_present": _has_create_v2_log(transaction),
        "mint_matches_account_0": _account_at(accounts, layout, "token_mint_index") == row.mint,
        "bonding_curve_matches_account_2": _account_at(accounts, layout, "bonding_curve_index") == row.bonding_curve,
        "associated_bonding_curve_matches_account_3": _account_at(accounts, layout, "associated_bonding_curve_index") == row.associated_bonding_curve,
        "creator_matches_account_5": _account_at(accounts, layout, "creator_wallet_index") == row.creator_deployer,
        "creator_is_signer_or_fee_payer": _is_signer_or_fee_payer(transaction, row.creator_deployer) if row.creator_deployer else False,
        "slot_matches": transaction.get("slot") == row.slot if row.slot is not None else None,
        "block_time_matches": transaction.get("blockTime") == row.block_time if row.block_time is not None else None,
    }


def _instruction_at_index(transaction: dict[str, Any], instruction_index: int | None) -> dict[str, Any] | None:
    if instruction_index is None:
        return None
    instructions = transaction.get("transaction", {}).get("message", {}).get("instructions", [])
    if not isinstance(instructions, list) or instruction_index < 0 or instruction_index >= len(instructions):
        return None
    instruction = instructions[instruction_index]
    return instruction if isinstance(instruction, dict) else None


def _account_at(accounts: list[str], layout: dict[str, Any] | None, index_name: str) -> str | None:
    if not layout:
        return None
    index = layout[index_name]
    return accounts[index] if len(accounts) > index else None


def _has_create_v2_log(transaction: dict[str, Any]) -> bool | None:
    log_messages = transaction.get("meta", {}).get("logMessages")
    if not isinstance(log_messages, list):
        return None
    return any("Instruction: CreateV2" in str(message) for message in log_messages)


def write_precision_summary(summary: dict[str, Any], output_path: Path | str) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output_path


def write_precision_summary_markdown(summary: dict[str, Any], output_path: Path | str) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Pump.fun Precision Audit Summary",
        "",
        "This is a parser-quality report only. It does not authorize broad scaling, backtests, thesis promotion, paper trading, or live trading.",
        "",
        f"- Census rows: `{summary['census_rows']}`",
        f"- Review rows: `{summary['review_rows']}`",
        f"- Review label counts: `{summary['review_label_counts']}`",
        f"- Reviewed precision: `{summary['reviewed_precision']}`",
        f"- Acceptable for scaling: `{summary['acceptable_for_scaling']}`",
        f"- Warning flags: `{summary['warning_flags']}`",
    ]
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path


def _warning_flags(
    rows: list[PumpFunCreationCensusRow],
    reviews: list[PumpFunPrecisionReview],
    precision: float | None,
    reviewed: int,
) -> list[str]:
    warnings = []
    if not rows:
        warnings.append("empty_census")
    if not reviews:
        warnings.append("no_manual_reviews")
    if reviewed < 20:
        warnings.append("insufficient_reviewed_sample")
    if precision is None or precision < 0.95:
        warnings.append("parser_precision_not_acceptable_for_scaling")
    return warnings
