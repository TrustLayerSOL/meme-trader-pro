from __future__ import annotations

import csv
import json
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MODE = "FOCUSED_MANUAL_SUPPLY_RESEARCH_REVIEW_ONLY"
VERSION = "focused_manual_supply_research.v1"

CONFIDENCE_TIERS = [
    "A_FULL_REPLAY_SAFE",
    "B_STRONG_PARTIAL",
    "C_SUGGESTIVE",
    "D_INSUFFICIENT",
]
TIER_STRENGTH = {tier: len(CONFIDENCE_TIERS) - index for index, tier in enumerate(CONFIDENCE_TIERS)}

PACKET_COLUMNS = [
    "request_id",
    "token_mint",
    "max_acceptable_snapshot_slot",
    "requested_snapshot_slot",
    "decision_timestamp",
    "decision_time_utc",
    "wallet_count",
    "row_count",
    "wallets",
    "transaction_signatures",
    "exact_evidence_needed",
    "solscan_token_link",
    "solana_explorer_link",
    "dexscreener_link",
    "notes",
    "manual_status",
]

TEMPLATE_COLUMNS = [
    "request_id",
    "token_mint",
    "max_acceptable_snapshot_slot",
    "raw_supply_base_units",
    "display_supply_optional",
    "decimals",
    "response_slot",
    "evidence_source",
    "evidence_url",
    "confidence_tier",
    "notes",
]


def safe_int(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text or not text.isdigit():
        return None
    return int(text)


def positive_int_text(value: Any) -> str | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value) if value > 0 else None
    if value in (None, ""):
        return None
    text = str(value).strip().replace(",", "")
    if not text or not text.isdigit():
        return None
    parsed = int(text)
    return str(parsed) if parsed > 0 else None


def decision_time_utc(value: Any) -> str:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return ""
    try:
        return datetime.fromtimestamp(parsed, tz=timezone.utc).isoformat()
    except (OSError, OverflowError, ValueError):
        return ""


def request_id(row: dict[str, Any]) -> str:
    payload = row.get("jsonrpc_payload") if isinstance(row.get("jsonrpc_payload"), dict) else {}
    return str(payload.get("id") or row.get("request_id") or "").strip()


def request_rows(request_bundle_report: dict[str, Any]) -> list[dict[str, Any]]:
    rows = request_bundle_report.get("requests") if isinstance(request_bundle_report, dict) else []
    filtered: list[dict[str, Any]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        rid = request_id(row)
        mint = str(row.get("token_mint") or "").strip()
        max_slot = safe_int(row.get("max_acceptable_snapshot_slot"))
        if rid and mint and max_slot:
            filtered.append(row)
    filtered.sort(key=lambda row: (str(row.get("token_mint") or ""), safe_int(row.get("max_acceptable_snapshot_slot")) or 0, request_id(row)))
    return filtered


def links_for(mint: str) -> dict[str, str]:
    return {
        "solscan_token_link": f"https://solscan.io/token/{mint}",
        "solana_explorer_link": f"https://explorer.solana.com/address/{mint}",
        "dexscreener_link": f"https://dexscreener.com/solana/{mint}",
    }


def packet_row(row: dict[str, Any]) -> dict[str, Any]:
    mint = str(row.get("token_mint") or "").strip()
    timestamp = row.get("requested_snapshot_time") or row.get("latest_decision_time")
    return {
        "request_id": request_id(row),
        "token_mint": mint,
        "max_acceptable_snapshot_slot": safe_int(row.get("max_acceptable_snapshot_slot")),
        "requested_snapshot_slot": safe_int(row.get("requested_snapshot_slot") or row.get("latest_decision_slot")),
        "decision_timestamp": timestamp,
        "decision_time_utc": decision_time_utc(timestamp),
        "wallet_count": safe_int(row.get("wallet_count")) or len(row.get("wallets") or []),
        "row_count": safe_int(row.get("row_count")) or 0,
        "wallets": ";".join(str(wallet) for wallet in row.get("wallets") or []),
        "transaction_signatures": ";".join(str(signature) for signature in row.get("transaction_signatures") or []),
        "exact_evidence_needed": "token supply and decimals at or before max_acceptable_snapshot_slot",
        **links_for(mint),
    }


def build_focused_manual_supply_packet(
    *,
    request_bundle_report: dict[str, Any],
    output_dir: Path | str,
    limit: int | None = None,
    generated_at: float | None = None,
) -> dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = [packet_row(row) for row in request_rows(request_bundle_report)]
    if limit is not None:
        rows = rows[: max(0, int(limit))]

    packet_csv = output_dir / "focused_manual_supply_research_packet.csv"
    packet_json = output_dir / "focused_manual_supply_research_packet.json"
    template_csv = output_dir / "focused_manual_supply_template.csv"

    with packet_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=PACKET_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in PACKET_COLUMNS})

    with template_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=TEMPLATE_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "request_id": row.get("request_id"),
                    "token_mint": row.get("token_mint"),
                    "max_acceptable_snapshot_slot": row.get("max_acceptable_snapshot_slot"),
                }
            )

    report = {
        "generated_at": time.time() if generated_at is None else float(generated_at),
        "mode": MODE,
        "version": VERSION,
        "review_only": True,
        "read_only": True,
        "live_execution_locked": True,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "auto_trust_mutation_allowed": False,
        "wallet_trust_mutation_allowed": False,
        "summary": {
            "requests_available": len(request_rows(request_bundle_report)),
            "requests_exported": len(rows),
            "target_tokens_exported": len({row.get("token_mint") for row in rows if row.get("token_mint")}),
        },
        "output_paths": {
            "packet_csv": str(packet_csv),
            "packet_json": str(packet_json),
            "manual_supply_template": str(template_csv),
        },
        "template_columns": TEMPLATE_COLUMNS,
        "requests": rows,
        "operator_note": (
            "This packet is for manual/free-source supply research only. Only Tier A imports can emit "
            "replay-safe supply snapshots; lower tiers remain review evidence."
        ),
    }
    packet_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def request_index(request_bundle_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {request_id(row): row for row in request_rows(request_bundle_report)}


def stronger_or_equal(existing: dict[str, Any], incoming: dict[str, Any]) -> bool:
    return TIER_STRENGTH.get(str(existing.get("confidence_tier")), 0) >= TIER_STRENGTH.get(
        str(incoming.get("confidence_tier")), 0
    )


def validate_import_row(row: dict[str, Any], requests_by_id: dict[str, dict[str, Any]]) -> tuple[dict[str, Any] | None, list[str]]:
    rid = str(row.get("request_id") or "").strip()
    mint = str(row.get("token_mint") or "").strip()
    source = str(row.get("evidence_source") or "").strip()
    url = str(row.get("evidence_url") or "").strip()
    notes = str(row.get("notes") or "").strip()
    tier = str(row.get("confidence_tier") or "").strip()
    raw_supply = positive_int_text(row.get("raw_supply_base_units"))
    decimals = safe_int(row.get("decimals"))
    response_slot = safe_int(row.get("response_slot"))
    max_slot = safe_int(row.get("max_acceptable_snapshot_slot"))
    errors: list[str] = []

    if not rid:
        errors.append("missing_request_id")
    request = requests_by_id.get(rid)
    if rid and request is None:
        errors.append("unknown_request_id")
    if not mint:
        errors.append("missing_token_mint")
    if request and mint and mint != str(request.get("token_mint") or "").strip():
        errors.append("token_mint_does_not_match_request")
    request_max_slot = safe_int(request.get("max_acceptable_snapshot_slot")) if request else None
    if max_slot is None:
        errors.append("missing_max_acceptable_snapshot_slot")
    if request_max_slot is not None and max_slot is not None and max_slot != request_max_slot:
        errors.append("max_acceptable_snapshot_slot_does_not_match_request")
    if raw_supply is None:
        if row.get("verified_supply") not in (None, ""):
            errors.append("legacy_verified_supply_not_allowed_use_raw_supply_base_units")
        else:
            errors.append("missing_or_invalid_raw_supply_base_units")
    if decimals is None or decimals < 0:
        errors.append("missing_or_invalid_decimals")
    if response_slot is None or response_slot <= 0:
        errors.append("missing_or_invalid_response_slot")
    if response_slot is not None and max_slot is not None and response_slot > max_slot:
        errors.append("response_slot_after_decision_boundary")
    if tier not in CONFIDENCE_TIERS:
        errors.append("invalid_confidence_tier")
    if not source:
        errors.append("missing_evidence_source")
    if not url:
        errors.append("missing_evidence_url")
    if not notes:
        errors.append("missing_notes")
    if tier == "A_FULL_REPLAY_SAFE" and response_slot is not None and max_slot is not None and response_slot != max_slot:
        errors.append("tier_a_requires_exact_decision_slot_snapshot")

    if errors:
        return None, errors

    assert request is not None
    return {
        "version": VERSION,
        "request_id": rid,
        "token_mint": mint,
        "max_acceptable_snapshot_slot": max_slot,
        "raw_supply_base_units": raw_supply,
        "display_supply_optional": str(row.get("display_supply_optional") or "").strip(),
        "decimals": decimals,
        "response_slot": response_slot,
        "evidence_source": source,
        "evidence_url": url,
        "confidence_tier": tier,
        "notes": notes,
        "proof_unblock_allowed": tier == "A_FULL_REPLAY_SAFE",
        "decision_time_safe": tier == "A_FULL_REPLAY_SAFE",
        "wallets": request.get("wallets") or [],
        "transaction_signatures": request.get("transaction_signatures") or [],
        "can_mutate_wallet_trust": False,
        "imported_at": time.time(),
    }, []


def snapshot_from_record(row: dict[str, Any]) -> dict[str, Any] | None:
    if row.get("confidence_tier") != "A_FULL_REPLAY_SAFE" or row.get("proof_unblock_allowed") is not True:
        return None
    return {
        "version": "focused_manual_supply_snapshot.v1",
        "token_mint": row.get("token_mint"),
        "slot": row.get("response_slot"),
        "raw_supply": str(row.get("raw_supply_base_units")),
        "decimals": row.get("decimals"),
        "source": "focused_manual_supply_research",
        "source_file": "data/manual_research/focused_manual_supply_evidence_imported.jsonl",
        "request_id": row.get("request_id"),
        "max_acceptable_snapshot_slot": row.get("max_acceptable_snapshot_slot"),
        "evidence_url": row.get("evidence_url"),
        "confidence_tier": row.get("confidence_tier"),
        "notes": row.get("notes"),
        "decision_time_safe": True,
        "can_mutate_wallet_trust": False,
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                rows.append(parsed)
    return rows


def import_focused_manual_supply_evidence(
    csv_path: Path | str,
    *,
    request_bundle_report: dict[str, Any],
    output_dir: Path | str,
    generated_at: float | None = None,
) -> dict[str, Any]:
    csv_path = Path(csv_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    imported_path = output_dir / "focused_manual_supply_evidence_imported.jsonl"
    rejected_path = output_dir / "focused_manual_supply_evidence_rejected.csv"
    snapshots_path = output_dir / "focused_manual_supply_snapshots.jsonl"
    report_path = output_dir / "focused_manual_supply_import_report.json"
    requests_by_id = request_index(request_bundle_report)
    existing_by_id = {str(row.get("request_id") or ""): row for row in read_jsonl(imported_path)}
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    preserved_stronger = 0

    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row_number, row in enumerate(reader, start=2):
            if not any(str(value or "").strip() for value in row.values()):
                continue
            record, errors = validate_import_row(row, requests_by_id)
            if errors or record is None:
                rejected.append({**row, "row_number": row_number, "rejection_reasons": ";".join(errors)})
                continue
            existing = existing_by_id.get(str(record["request_id"]))
            if existing and stronger_or_equal(existing, record):
                preserved_stronger += 1
                continue
            existing_by_id[str(record["request_id"])] = record
            accepted.append(record)

    stored = sorted(existing_by_id.values(), key=lambda row: str(row.get("request_id") or ""))
    snapshots = [row for row in (snapshot_from_record(row) for row in stored) if row is not None]
    write_jsonl(imported_path, stored)
    write_jsonl(snapshots_path, snapshots)

    with rejected_path.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = TEMPLATE_COLUMNS + ["row_number", "rejection_reasons"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rejected:
            writer.writerow({field: row.get(field, "") for field in fieldnames})

    tier_counts = Counter(str(row.get("confidence_tier") or "UNKNOWN") for row in stored)
    report = {
        "generated_at": time.time() if generated_at is None else float(generated_at),
        "mode": MODE,
        "version": VERSION,
        "review_only": True,
        "read_only": True,
        "live_execution_locked": True,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "auto_trust_mutation_allowed": False,
        "wallet_trust_mutation_allowed": False,
        "summary": {
            "rows_scanned": len(accepted) + len(rejected) + preserved_stronger,
            "accepted_rows": len(accepted),
            "rejected_rows": len(rejected),
            "preserved_stronger_rows": preserved_stronger,
            "stored_manual_rows": len(stored),
            "tier_counts": dict(sorted(tier_counts.items())),
            "tier_a_snapshot_rows": len(snapshots),
            "proof_unblock_allowed_rows": len(snapshots),
            "wallet_list_mutations": 0,
            "auto_trust_mutations": 0,
        },
        "output_paths": {
            "manual_evidence_imported": str(imported_path),
            "manual_supply_snapshots": str(snapshots_path),
            "manual_evidence_rejected": str(rejected_path),
            "report": str(report_path),
        },
        "rejected_rows": rejected,
        "operator_note": (
            "Focused manual supply evidence is stored separately from provider evidence. Only Tier A rows emit "
            "decision-time-safe supply snapshots; B/C/D rows remain review evidence."
        ),
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report
