"""Offline funding-link and fee-payer feasibility audit."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


READINESS_READY = "funding_link_ready_for_thesis"
READINESS_PARTIAL = "funding_link_partial_needs_data"
READINESS_BLOCKED = "funding_link_blocked"

FIELD_ORDER = [
    "creator",
    "creation_signature",
    "transaction_metadata",
    "fee_payer",
    "signer",
    "source_wallet",
    "creator_funding_source",
    "creator_prior_funding_wallet",
    "multi_launch_funding_link",
    "launch_financing_trace",
]


def build_funding_link_feasibility_report(
    *,
    candidates_path: Path | str,
    raw_transaction_paths: list[Path | str],
    max_launches: int = 100,
) -> dict[str, Any]:
    """Build a bounded, read-only funding-link availability report."""
    if max_launches > 100:
        raise ValueError("max_launches must be <= 100 for this bounded feasibility audit")
    candidates = _read_jsonl(candidates_path)[:max_launches]
    creation_signatures = {_creation_signature(candidate) for candidate in candidates if _creation_signature(candidate)}
    raw_by_signature = _raw_transactions_by_signature(raw_transaction_paths, creation_signatures)
    rows = []
    for candidate in candidates:
        signature = _creation_signature(candidate)
        raw_row = raw_by_signature.get(signature or "")
        rows.append(_audit_launch(candidate, raw_row))
    field_coverage = _field_coverage(rows)
    linkage_summary = _linkage_summary(rows)
    offline = _offline_reconstruction_summary(field_coverage)
    readiness = _readiness(field_coverage, offline)
    return {
        "report_id": "funding_link_feasibility_v0",
        "scope": {
            "dataset": "strict_launch_regime",
            "launches_available": len(_read_jsonl(candidates_path)),
            "launches_inspected": len(candidates),
            "max_launches": max_launches,
            "raw_transaction_paths": [str(path) for path in raw_transaction_paths],
            "external_api_calls_used": 0,
            "network_calls_used": 0,
        },
        "methodology_flags": [
            "research_only",
            "data_availability_investigation_only",
            "read_only_audit",
            "no_thesis_cycle",
            "no_backtest",
            "no_validation",
            "no_external_api_calls",
            "no_trading_rules",
            "no_threshold_optimization",
            "no_grid_search",
            "no_ml_black_boxes",
            "no_outcome_comparison",
        ],
        "field_definitions": _field_definitions(),
        "field_coverage": field_coverage,
        "linkage_summary": linkage_summary,
        "offline_reconstruction": offline,
        "launch_rows": rows,
        "examples": _examples(rows),
        "readiness_classification": readiness,
        "t008_feasible": readiness == READINESS_READY,
        "new_data_required": offline["new_data_source_required"],
        "next_recommendation": _next_recommendation(readiness),
        "warning_flags": _warning_flags(field_coverage, offline),
    }


def write_funding_link_feasibility_outputs(report: dict[str, Any], *, output_dir: Path | str) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    availability_path = output / "funding_link_data_availability.md"
    feasibility_json_path = output / "funding_link_feasibility.json"
    feasibility_md_path = output / "funding_link_feasibility.md"
    availability_path.write_text(_availability_markdown(report), encoding="utf-8")
    feasibility_json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    feasibility_md_path.write_text(_feasibility_markdown(report), encoding="utf-8")
    return {
        "data_availability_markdown_path": availability_path,
        "feasibility_json_path": feasibility_json_path,
        "feasibility_markdown_path": feasibility_md_path,
    }


def _audit_launch(candidate: dict[str, Any], raw_row: dict[str, Any] | None) -> dict[str, Any]:
    creator = _creator(candidate)
    signature = _creation_signature(candidate)
    raw_json = raw_row.get("raw_json") if raw_row else None
    fee_payer = _fee_payer(raw_json) if raw_json else None
    signers = _signers(raw_json) if raw_json else []
    source_wallets = _source_wallets(raw_json) if raw_json else []
    creator_funding_sources = _creator_funding_sources(raw_json, creator) if raw_json and creator else []
    field_status = {
        "creator": "available" if creator else "unavailable",
        "creation_signature": "available" if signature else "unavailable",
        "transaction_metadata": "available" if raw_json else "unavailable",
        "fee_payer": "available" if fee_payer else "unavailable",
        "signer": "available" if signers else "unavailable",
        "source_wallet": "derivable" if source_wallets else "unavailable",
        "creator_funding_source": "derivable" if creator_funding_sources else "unavailable",
        "creator_prior_funding_wallet": "unavailable",
        "multi_launch_funding_link": "partially_derivable" if fee_payer or source_wallets or signers else "unavailable",
        "launch_financing_trace": "partially_derivable" if source_wallets or fee_payer else "unavailable",
    }
    return {
        "launch_id": candidate.get("launch_id"),
        "mint": candidate.get("token_mint") or candidate.get("mint"),
        "creator": creator,
        "creation_signature": signature,
        "field_status": field_status,
        "fee_payer": fee_payer,
        "signers": signers,
        "source_wallets": source_wallets,
        "creator_funding_sources": creator_funding_sources,
        "transaction_metadata": {
            "slot": raw_row.get("slot") if raw_row else None,
            "block_time": raw_row.get("block_time") if raw_row else candidate.get("launch_ts"),
            "meta_fee_lamports": _meta_fee(raw_json) if raw_json else None,
            "raw_signature_found": raw_row is not None,
        },
        "rejection_reason": None if raw_row else "creation_transaction_raw_missing",
    }


def _field_coverage(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    total = len(rows)
    coverage = {}
    for field in FIELD_ORDER:
        status_counts = Counter(row["field_status"][field] for row in rows)
        covered = sum(count for status, count in status_counts.items() if status != "unavailable")
        coverage[field] = {
            "classification": _classify_status_counts(status_counts, total),
            "covered_count": covered,
            "missing_count": total - covered,
            "coverage_pct": _pct(covered, total),
            "status_counts": dict(sorted(status_counts.items())),
        }
    return coverage


def _classify_status_counts(status_counts: Counter, total: int) -> str:
    if not total or status_counts.get("unavailable", 0) == total:
        return "unavailable"
    if status_counts.get("available", 0) == total:
        return "available"
    if status_counts.get("derivable", 0) == total:
        return "derivable"
    if status_counts.get("partially_derivable", 0) == total:
        return "partially_derivable"
    return "partially_derivable"


def _linkage_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    fee_payer_counts = _value_launch_counts(rows, "fee_payer")
    signer_counts = _list_value_launch_counts(rows, "signers")
    source_wallet_counts = _list_value_launch_counts(rows, "source_wallets")
    creator_funding_counts = _list_value_launch_counts(rows, "creator_funding_sources")
    return {
        "shared_fee_payer_launches": _shared_launch_total(fee_payer_counts),
        "shared_signer_launches": _shared_launch_total(signer_counts),
        "shared_source_wallet_launches": _shared_launch_total(source_wallet_counts),
        "shared_creator_funding_source_launches": _shared_launch_total(creator_funding_counts),
        "top_shared_fee_payers": _top_shared(fee_payer_counts),
        "top_shared_signers": _top_shared(signer_counts),
        "top_shared_source_wallets": _top_shared(source_wallet_counts),
        "top_shared_creator_funding_sources": _top_shared(creator_funding_counts),
        "multi_launch_links_partially_derivable": any(
            counts for counts in (fee_payer_counts, signer_counts, source_wallet_counts)
        ),
    }


def _offline_reconstruction_summary(field_coverage: dict[str, dict[str, Any]]) -> dict[str, Any]:
    fee_payer_available = field_coverage["fee_payer"]["covered_count"] > 0
    signer_available = field_coverage["signer"]["covered_count"] > 0
    source_wallet_available = field_coverage["source_wallet"]["covered_count"] > 0
    creator_funding_available = field_coverage["creator_funding_source"]["covered_count"] > 0
    creator_prior_available = field_coverage["creator_prior_funding_wallet"]["covered_count"] > 0
    deterministic_full = (
        fee_payer_available
        and signer_available
        and source_wallet_available
        and creator_funding_available
        and creator_prior_available
    )
    partial_offline = fee_payer_available or signer_available or source_wallet_available
    return {
        "deterministic_reconstruction_possible": deterministic_full,
        "offline_only_possible": deterministic_full,
        "partial_offline_reconstruction_possible": partial_offline,
        "new_data_source_required": not deterministic_full,
        "reason": "pre_launch_creator_funding_wallets_missing"
        if partial_offline and not deterministic_full
        else "no_local_transaction_metadata_available"
        if not partial_offline
        else "offline_fields_cover_full_reconstruction",
    }


def _readiness(field_coverage: dict[str, dict[str, Any]], offline: dict[str, Any]) -> str:
    if offline["deterministic_reconstruction_possible"]:
        return READINESS_READY
    if field_coverage["fee_payer"]["covered_count"] > 0 or field_coverage["signer"]["covered_count"] > 0:
        return READINESS_PARTIAL
    return READINESS_BLOCKED


def _next_recommendation(readiness: str) -> str:
    if readiness == READINESS_READY:
        return "run a separate T008 design review before any outcome analysis"
    if readiness == READINESS_PARTIAL:
        return "build a bounded pre-launch funding-source data acquisition plan; do not run T008 yet"
    return "stop funding-link thesis work until creation transaction metadata or pre-launch funding data exists"


def _warning_flags(field_coverage: dict[str, dict[str, Any]], offline: dict[str, Any]) -> list[str]:
    flags = ["not_a_thesis_cycle", "no_outcome_analysis"]
    if field_coverage["creator_prior_funding_wallet"]["covered_count"] == 0:
        flags.append("creator_prior_funding_wallet_unavailable")
    if field_coverage["creator_funding_source"]["covered_count"] == 0:
        flags.append("creator_funding_source_unavailable")
    if offline["new_data_source_required"]:
        flags.append("new_data_source_required_for_full_funding_reconstruction")
    return flags


def _field_definitions() -> dict[str, str]:
    return {
        "creator": "Creator/deployer wallet from launch census metadata.",
        "creation_signature": "Pump.fun creation transaction signature from launch census metadata.",
        "transaction_metadata": "Raw local transaction JSON for the creation signature.",
        "fee_payer": "First transaction account key in parsed Solana transaction metadata.",
        "signer": "Parsed transaction account keys marked signer=true.",
        "source_wallet": "Parsed transfer instruction info.source values inside the local creation transaction.",
        "creator_funding_source": "Parsed transfer source to the creator in local transaction data.",
        "creator_prior_funding_wallet": "Wallet funding the creator before launch; requires pre-launch transaction history.",
        "multi_launch_funding_link": "Repeated fee payer, signer, or source wallet across inspected launches.",
        "launch_financing_trace": "At-launch fee payer/source-wallet trace; not complete pre-launch financing.",
    }


def _examples(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    with_fee_payer = [row for row in rows if row.get("fee_payer")]
    with_sources = [row for row in rows if row.get("source_wallets")]
    missing_raw = [row for row in rows if row.get("rejection_reason")]
    shared = _rows_with_shared_values(rows)
    return {
        "fee_payer_examples": _compact_rows(with_fee_payer[:5]),
        "source_wallet_examples": _compact_rows(with_sources[:5]),
        "shared_link_examples": _compact_rows(shared[:5]),
        "missing_raw_examples": _compact_rows(missing_raw[:5]),
    }


def _rows_with_shared_values(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fee_payer_counts = _value_launch_counts(rows, "fee_payer")
    signer_counts = _list_value_launch_counts(rows, "signers")
    source_wallet_counts = _list_value_launch_counts(rows, "source_wallets")
    result = []
    for row in rows:
        if (
            (row.get("fee_payer") and fee_payer_counts[row["fee_payer"]] > 1)
            or any(signer_counts[value] > 1 for value in row.get("signers", []))
            or any(source_wallet_counts[value] > 1 for value in row.get("source_wallets", []))
        ):
            result.append(row)
    return result


def _compact_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "launch_id": row.get("launch_id"),
            "mint": row.get("mint"),
            "creator": row.get("creator"),
            "creation_signature": row.get("creation_signature"),
            "fee_payer": row.get("fee_payer"),
            "signers": row.get("signers", [])[:5],
            "source_wallets": row.get("source_wallets", [])[:5],
            "rejection_reason": row.get("rejection_reason"),
        }
        for row in rows
    ]


def _fee_payer(raw_json: dict[str, Any] | None) -> str | None:
    account_keys = _account_keys(raw_json)
    if not account_keys:
        return None
    first = account_keys[0]
    if isinstance(first, dict):
        return first.get("pubkey")
    return str(first)


def _signers(raw_json: dict[str, Any] | None) -> list[str]:
    signers = []
    for account in _account_keys(raw_json):
        if isinstance(account, dict):
            if account.get("signer") and account.get("pubkey"):
                signers.append(str(account["pubkey"]))
        elif isinstance(account, str):
            continue
    return sorted(set(signers))


def _source_wallets(raw_json: dict[str, Any] | None) -> list[str]:
    sources = []
    for instruction in _all_instructions(raw_json):
        parsed = instruction.get("parsed") if isinstance(instruction, dict) else None
        if not isinstance(parsed, dict):
            continue
        info = parsed.get("info")
        if isinstance(info, dict) and info.get("source"):
            sources.append(str(info["source"]))
    return sorted(set(sources))


def _creator_funding_sources(raw_json: dict[str, Any] | None, creator: str | None) -> list[str]:
    if not creator:
        return []
    sources = []
    for instruction in _all_instructions(raw_json):
        parsed = instruction.get("parsed") if isinstance(instruction, dict) else None
        if not isinstance(parsed, dict):
            continue
        info = parsed.get("info")
        if not isinstance(info, dict):
            continue
        source = info.get("source")
        destination = info.get("destination") or info.get("wallet") or info.get("account")
        if source and destination == creator and source != creator:
            sources.append(str(source))
    return sorted(set(sources))


def _all_instructions(raw_json: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not raw_json:
        return []
    message = raw_json.get("transaction", {}).get("message", {})
    instructions = list(message.get("instructions") or [])
    for group in raw_json.get("meta", {}).get("innerInstructions") or []:
        instructions.extend(group.get("instructions") or [])
    return [instruction for instruction in instructions if isinstance(instruction, dict)]


def _account_keys(raw_json: dict[str, Any] | None) -> list[Any]:
    if not raw_json:
        return []
    return raw_json.get("transaction", {}).get("message", {}).get("accountKeys") or []


def _meta_fee(raw_json: dict[str, Any] | None) -> int | None:
    fee = (raw_json or {}).get("meta", {}).get("fee")
    try:
        return int(fee) if fee is not None else None
    except (TypeError, ValueError):
        return None


def _raw_transactions_by_signature(paths: list[Path | str], needed_signatures: set[str]) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    if not needed_signatures:
        return found
    for path in paths:
        p = Path(path)
        if not p.exists():
            continue
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                signature = row.get("signature") or (row.get("raw_json") or {}).get("transaction", {}).get("signatures", [None])[0]
                if signature in needed_signatures and signature not in found:
                    found[str(signature)] = row
                    if len(found) == len(needed_signatures):
                        return found
    return found


def _value_launch_counts(rows: list[dict[str, Any]], field: str) -> Counter:
    values: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        value = row.get(field)
        if value:
            values[str(value)].add(str(row.get("mint")))
    return Counter({value: len(mints) for value, mints in values.items()})


def _list_value_launch_counts(rows: list[dict[str, Any]], field: str) -> Counter:
    values: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        for value in row.get(field) or []:
            values[str(value)].add(str(row.get("mint")))
    return Counter({value: len(mints) for value, mints in values.items()})


def _shared_launch_total(counts: Counter) -> int:
    return sum(count for count in counts.values() if count > 1)


def _top_shared(counts: Counter, limit: int = 10) -> list[dict[str, Any]]:
    return [
        {"wallet": wallet, "launch_count": count}
        for wallet, count in counts.most_common(limit)
        if count > 1
    ]


def _creator(candidate: dict[str, Any]) -> str | None:
    metadata = candidate.get("metadata_json") or {}
    return candidate.get("creator_deployer") or candidate.get("creator") or metadata.get("creator_deployer")


def _creation_signature(candidate: dict[str, Any]) -> str | None:
    metadata = candidate.get("metadata_json") or {}
    return candidate.get("creation_signature") or candidate.get("signature") or metadata.get("creation_signature")


def _read_jsonl(path: Path | str) -> list[dict[str, Any]]:
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _pct(count: int, total: int) -> float:
    return (count / total * 100) if total else 0.0


def _availability_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Funding Link Data Availability",
        "",
        f"- Launches inspected: `{report['scope']['launches_inspected']}`",
        f"- External API calls used: `{report['scope']['external_api_calls_used']}`",
        "- No thesis cycle was run.",
        "- No backtest or validation was run.",
        "",
        "| Field | Classification | Covered | Missing | Coverage |",
        "|---|---|---:|---:|---:|",
    ]
    for field, stats in report["field_coverage"].items():
        lines.append(
            f"| `{field}` | `{stats['classification']}` | {stats['covered_count']} | "
            f"{stats['missing_count']} | {stats['coverage_pct']:.2f}% |"
        )
    lines.extend(["", "## Field Definitions", ""])
    for field, definition in report["field_definitions"].items():
        lines.append(f"- `{field}`: {definition}")
    return "\n".join(lines) + "\n"


def _feasibility_markdown(report: dict[str, Any]) -> str:
    offline = report["offline_reconstruction"]
    lines = [
        "# Funding Link Feasibility",
        "",
        f"- Readiness classification: `{report['readiness_classification']}`",
        f"- Launches inspected: `{report['scope']['launches_inspected']}`",
        f"- External API calls used: `{report['scope']['external_api_calls_used']}`",
        f"- Deterministic reconstruction possible: `{offline['deterministic_reconstruction_possible']}`",
        f"- Offline only possible: `{offline['offline_only_possible']}`",
        f"- New data source required: `{offline['new_data_source_required']}`",
        f"- T008 feasible: `{report['t008_feasible']}`",
        "- No thesis cycle was run.",
        "- No backtest or validation was run.",
        "",
        "## Field Coverage",
        "",
        "| Field | Classification | Coverage | Status Counts |",
        "|---|---|---:|---|",
    ]
    for field, stats in report["field_coverage"].items():
        lines.append(
            f"| `{field}` | `{stats['classification']}` | {stats['coverage_pct']:.2f}% | "
            f"`{stats['status_counts']}` |"
        )
    lines.extend(
        [
            "",
            "## Linkage Summary",
            "",
            f"- Shared fee-payer launches: `{report['linkage_summary']['shared_fee_payer_launches']}`",
            f"- Shared signer launches: `{report['linkage_summary']['shared_signer_launches']}`",
            f"- Shared source-wallet launches: `{report['linkage_summary']['shared_source_wallet_launches']}`",
            f"- Shared creator-funding-source launches: `{report['linkage_summary']['shared_creator_funding_source_launches']}`",
            "",
            "## Examples",
            "",
        ]
    )
    for group, rows in report["examples"].items():
        lines.append(f"### {group.replace('_', ' ').title()}")
        lines.append("")
        if not rows:
            lines.append("- None")
        for row in rows:
            lines.append(
                f"- `{row['mint']}` creator `{row['creator']}` fee payer `{row['fee_payer']}` "
                f"source wallets `{row['source_wallets']}`"
            )
        lines.append("")
    lines.extend(["## Next Recommendation", "", report["next_recommendation"]])
    return "\n".join(lines) + "\n"
