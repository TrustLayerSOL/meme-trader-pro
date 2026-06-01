"""Reviewed Pump.fun create-fixture parsing.

This module evaluates one known create signature or transaction fixture at a
time. It fails closed when the parser cannot verify the layout.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from research.mtp_research.ingestion.helius_backfill import HeliusHistoricalAdapter
from research.mtp_research.ingestion.pumpfun_create_scanner import PumpFunCreateScanner


def review_known_create_transaction(
    transaction: dict[str, Any],
    *,
    expected_mint: str,
    expected_creator: str,
    expected_bonding_curve: str,
    min_confidence: str = "medium",
) -> dict[str, Any]:
    scanner = PumpFunCreateScanner()
    candidates, rejected, unknown, direct_count = scanner._extract_candidates(
        [transaction],
        remaining_target=1,
        include_low_confidence=False,
        min_confidence=min_confidence,
    )
    if not candidates:
        return {
            "accepted": False,
            "direct_pumpfun_instruction_count": direct_count,
            "parser_confidence": None,
            "rejection_reason": "no_verified_create_candidate",
            "candidate": None,
            "rejected_count": len(rejected),
            "unknown_count": len(unknown),
        }

    candidate = candidates[0]
    reasons = []
    if candidate.token_mint != expected_mint:
        reasons.append("mint_mismatch")
    if candidate.creator_wallet != expected_creator:
        reasons.append("creator_mismatch")
    if candidate.bonding_curve != expected_bonding_curve:
        reasons.append("bonding_curve_mismatch")

    return {
        "accepted": not reasons,
        "direct_pumpfun_instruction_count": direct_count,
        "parser_confidence": candidate.extraction_confidence,
        "rejection_reason": ";".join(reasons) if reasons else None,
        "candidate": candidate.to_dict(),
        "rejected_count": len(rejected),
        "unknown_count": len(unknown),
    }


def review_known_create_signature(
    signature: str,
    *,
    expected_mint: str,
    expected_creator: str,
    expected_bonding_curve: str,
    min_confidence: str = "medium",
) -> dict[str, Any]:
    adapter = HeliusHistoricalAdapter.from_env()
    transactions = adapter.fetch_transactions([signature])
    transaction = transactions[0] if transactions else {}
    result = review_known_create_transaction(
        transaction,
        expected_mint=expected_mint,
        expected_creator=expected_creator,
        expected_bonding_curve=expected_bonding_curve,
        min_confidence=min_confidence,
    )
    result["known_create_signature"] = signature
    result["network_calls"] = 1
    return result


def write_fixture_review_report(result: dict[str, Any], output_path: Path | str) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output_path
