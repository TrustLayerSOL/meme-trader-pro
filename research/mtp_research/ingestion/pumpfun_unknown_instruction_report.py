"""Diagnostics for unknown Pump.fun program instructions."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from research.mtp_research.ingestion.pumpfun_create_scanner_models import PumpFunInstructionDiagnostic


def summarize_unknown_instructions(
    diagnostics: list[PumpFunInstructionDiagnostic],
    *,
    max_examples: int = 5,
) -> dict[str, Any]:
    cluster_map: dict[tuple[str, int, str, int | None], dict[str, Any]] = {}
    layout_counts: Counter[str] = Counter()
    for diagnostic in diagnostics:
        metadata = diagnostic.metadata_json
        discriminator = diagnostic.instruction_discriminator or "missing"
        first_bytes = str(metadata.get("first_8_instruction_data_bytes_hex") or "")
        decoded_length = metadata.get("decoded_instruction_data_length")
        key = (discriminator, diagnostic.account_count, first_bytes, decoded_length)
        cluster = cluster_map.setdefault(
            key,
            {
                "instruction_discriminator_hex": discriminator,
                "instruction_discriminator_base58_prefix": metadata.get("instruction_discriminator_base58_prefix"),
                "account_count": diagnostic.account_count,
                "first_8_instruction_data_bytes_hex": first_bytes,
                "instruction_data_length": metadata.get("instruction_data_length"),
                "decoded_instruction_data_length": decoded_length,
                "count": 0,
                "example_signatures": [],
                "rejection_reasons": [],
            },
        )
        cluster["count"] += 1
        if len(cluster["example_signatures"]) < max_examples:
            cluster["example_signatures"].append(diagnostic.signature)
        for reason in diagnostic.rejection_reasons:
            if reason not in cluster["rejection_reasons"]:
                cluster["rejection_reasons"].append(reason)
        layout_counts[_account_layout_key(diagnostic)] += 1

    clusters = sorted(
        cluster_map.values(),
        key=lambda item: (-item["count"], -item["account_count"], item["instruction_discriminator_hex"]),
    )
    return {
        "total_unknown_instructions": len(diagnostics),
        "clusters": clusters,
        "top_account_layouts": [
            {"layout_key": layout, "count": count}
            for layout, count in layout_counts.most_common(10)
        ],
    }


def _account_layout_key(diagnostic: PumpFunInstructionDiagnostic) -> str:
    accounts = diagnostic.metadata_json.get("accounts", [])
    return f"account_count={diagnostic.account_count};captured_accounts={len(accounts)}"


BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
BASE58_INDEX = {char: index for index, char in enumerate(BASE58_ALPHABET)}


def decode_base58(value: str) -> bytes | None:
    if not value:
        return None
    number = 0
    try:
        for char in value:
            number = number * 58 + BASE58_INDEX[char]
    except KeyError:
        return None
    leading_zeroes = len(value) - len(value.lstrip("1"))
    decoded = number.to_bytes((number.bit_length() + 7) // 8, "big") if number else b""
    return b"\x00" * leading_zeroes + decoded
