"""Bounded entity-proxy feasibility audit for strict launch-regime data."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
from typing import Any


FIELD_GROUPS = {
    "launch_fields": [
        "launch_id",
        "token_mint",
        "mint",
        "creator_deployer",
        "creator",
        "block_time",
        "launch_ts",
        "signature",
        "creation_signature",
        "bonding_curve",
        "associated_bonding_curve",
        "pool_address",
    ],
    "event_fields": [
        "actor",
        "wallet",
        "buyer",
        "seller",
        "signer",
        "fee_payer",
        "funding_source_wallet",
        "source_wallet",
        "signature",
        "instruction_index",
        "slot",
        "block_time",
        "venue",
        "event_type",
        "side",
        "base_qty",
        "quote_qty",
        "price_quote",
    ],
    "holder_state_fields": [
        "holder_count",
        "top_holder_share",
        "top_10_holder_share",
        "creator_holder_share",
        "observed_holder_balances",
        "holder_balances_by_wallet",
        "holder_snapshot_confidence",
        "holder_snapshot_state",
        "holder_snapshot_missing_reason",
    ],
}
READINESS_READY = "entity_proxy_ready_for_descriptive_thesis"
READINESS_PARTIAL = "entity_proxy_partial_needs_more_data"
READINESS_BLOCKED = "entity_proxy_blocked"
SUPPORTED_SIDE_VALUES = {"accumulate", "buy", "possible_buy", "distribute", "sell", "possible_sell"}


def build_entity_proxy_feasibility_report(
    *,
    candidates_path: Path | str,
    events_path: Path | str,
    holder_state_snapshots_path: Path | str,
    max_launches: int = 100,
    max_events: int = 10_000,
) -> dict[str, Any]:
    if max_launches > 100:
        raise ValueError("max_launches must be <= 100 for this bounded feasibility pilot")
    if max_events > 10_000:
        raise ValueError("max_events must be <= 10000 for this bounded feasibility pilot")
    candidates = _read_jsonl(candidates_path)
    selected_candidates = candidates[:max_launches]
    selected_mints = {row.get("token_mint") or row.get("mint") for row in selected_candidates}
    selected_mints.discard(None)
    events = _bounded_events(events_path, selected_mints, max_events)
    holder_rows = _read_jsonl(holder_state_snapshots_path)
    holder_by_mint = _holder_state_by_mint(holder_rows, selected_mints)
    events_by_mint = _group_by(events, "token_mint")
    actor_launch_counts = _actor_launch_counts(events)
    actor_creator_counts = _actor_creator_counts(events, selected_candidates)
    signature_launch_counts = _signature_launch_counts(events)
    field_availability = {
        "launch_fields": _field_coverage(selected_candidates, FIELD_GROUPS["launch_fields"]),
        "event_fields": _field_coverage(events, FIELD_GROUPS["event_fields"]),
        "holder_state_fields": _field_coverage(holder_rows, FIELD_GROUPS["holder_state_fields"], mints=selected_mints),
    }
    pilot_rows = []
    for candidate in selected_candidates:
        mint = candidate.get("token_mint") or candidate.get("mint")
        launch_events = sorted(events_by_mint.get(mint, []), key=lambda row: (_event_time(row), row.get("signature") or ""))
        pilot_rows.append(
            _pilot_row(
                candidate,
                launch_events,
                holder_by_mint.get(mint, []),
                actor_launch_counts,
                actor_creator_counts,
                signature_launch_counts,
            )
        )
    coverage_summary = _coverage_summary(pilot_rows)
    readiness = _readiness(field_availability, coverage_summary, len(candidates), len(selected_candidates))
    return {
        "report_id": "entity_proxy_feasibility_v0",
        "scope": {
            "dataset": "strict_launch_regime",
            "launches_available": len(candidates),
            "launches_attempted": len(selected_candidates),
            "events_inspected": len(events),
            "max_launches": max_launches,
            "max_events": max_events,
        },
        "methodology_flags": [
            "research_only",
            "data_readiness_pilot_only",
            "no_thesis_cycle",
            "no_backtest",
            "no_walk_forward_validation",
            "no_trading_rules",
            "no_entry_exit_logic",
            "no_threshold_optimization",
            "no_grid_search",
            "no_ml_black_boxes",
            "no_outcome_based_tuning",
            "fdv_proxy_outcomes_not_used",
        ],
        "data_availability": field_availability,
        "proxy_definitions": _proxy_definitions(),
        "proxy_family_feasibility": _proxy_family_feasibility(field_availability, coverage_summary),
        "coverage_summary": coverage_summary,
        "manual_review_sample": _manual_review_sample(pilot_rows),
        "pilot_rows": pilot_rows,
        "readiness_classification": readiness,
        "next_recommendation": _next_recommendation(readiness),
        "output_caveats": [
            "Actor overlap is an overlap proxy only; it is not entity resolution.",
            "Creator-retained balance uses observed holder-state replay, not confirmed full-chain account state.",
            "Funding links are unavailable unless fee payer, funder, or source wallet fields are present.",
            "FDV-proxy outcomes were not used to tune or test these proxy fields.",
        ],
    }


def write_entity_proxy_feasibility_outputs(report: dict[str, Any], *, output_dir: Path | str) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    availability_md = output / "entity_manipulation_data_availability.md"
    pilot_json = output / "entity_proxy_pilot.json"
    pilot_md = output / "entity_proxy_pilot.md"
    availability_md.write_text(_availability_markdown(report), encoding="utf-8")
    pilot_json.write_text(json.dumps(_pilot_public_report(report), indent=2, sort_keys=True), encoding="utf-8")
    pilot_md.write_text(_pilot_markdown(report), encoding="utf-8")
    return {
        "data_availability_markdown_path": availability_md,
        "pilot_json_path": pilot_json,
        "pilot_markdown_path": pilot_md,
    }


def _pilot_row(
    candidate: dict[str, Any],
    events: list[dict[str, Any]],
    holder_rows: list[dict[str, Any]],
    actor_launch_counts: Counter,
    actor_creator_counts: Counter,
    signature_launch_counts: Counter,
) -> dict[str, Any]:
    mint = candidate.get("token_mint") or candidate.get("mint")
    creator = _creator(candidate)
    early_events = [event for event in events if _launch_age(candidate, event) is not None and _launch_age(candidate, event) <= 60]
    early_actors = _actors(early_events)
    all_actors = _actors(events)
    shared_actors = sorted(actor for actor in all_actors if actor_launch_counts[actor] > 1)
    shared_actors_same_creator = sorted(actor for actor in all_actors if actor_creator_counts[(creator, actor)] > 1)
    repeated_signatures = sorted({event.get("signature") for event in events if event.get("signature") and signature_launch_counts[event.get("signature")] > 1})
    first_minute_concentration = _first_minute_concentration(early_events)
    quick_churn = _quick_churn(events, candidate)
    creator_share = _latest_holder_field(holder_rows, "creator_holder_share")
    proxy_fields = {
        "creator_holder_share_30m_or_latest": creator_share,
        "creator_retained_balance_proxy_available": creator_share is not None,
        "shared_actor_count": len(shared_actors),
        "shared_actor_same_creator_count": len(shared_actors_same_creator),
        "shared_early_buyer_count": len([actor for actor in early_actors if actor_launch_counts[actor] > 1]),
        "repeated_signature_count": len(repeated_signatures),
        "first_minute_actor_count": len(early_actors),
        "first_minute_event_count": len(early_events),
        "first_minute_actor_concentration": first_minute_concentration,
        "quick_buy_sell_churn_actor_count": len(quick_churn),
        "high_event_intensity_small_actor_set": _high_intensity_small_actor_set(events),
    }
    missing_reasons = _proxy_missing_reasons(proxy_fields, events)
    return {
        "launch_id": candidate.get("launch_id"),
        "mint": mint,
        "creator": creator,
        "proxy_fields": proxy_fields,
        "proxy_missing_reasons": missing_reasons,
        "confidence_flags": {
            "uses_outcomes": False,
            "actor_overlap_only_not_entity_resolution": proxy_fields["shared_actor_count"] > 0,
            "creator_holder_share_observed_delta_replay": creator_share is not None,
            "funding_links_unavailable": "funding_link_fields_unavailable" in missing_reasons.values(),
        },
        "manual_review_examples": {
            "shared_actors": shared_actors[:5],
            "shared_actors_same_creator": shared_actors_same_creator[:5],
            "repeated_signatures": repeated_signatures[:5],
            "quick_churn_actors": sorted(quick_churn)[:5],
            "first_event_signatures": [event.get("signature") for event in events[:5] if event.get("signature")],
        },
    }


def _proxy_missing_reasons(proxy_fields: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, str]:
    reasons = {}
    if proxy_fields["creator_holder_share_30m_or_latest"] is None:
        reasons["creator_linked_ownership_proxy"] = "creator_holder_share_unavailable"
    if not any(_field_present(event, "fee_payer") or _field_present(event, "funding_source_wallet") or _field_present(event, "source_wallet") for event in events):
        reasons["funding_link_proxy"] = "funding_link_fields_unavailable"
    if not events:
        reasons["event_based_proxies"] = "no_events_for_launch_in_bounded_pilot"
    return reasons


def _proxy_definitions() -> dict[str, dict[str, Any]]:
    return {
        "creator_linked_ownership_proxy": {
            "fields": ["creator_holder_share_30m_or_latest"],
            "status_rule": "available when observed holder-state replay has creator_holder_share",
        },
        "repeated_participant_overlap_proxy": {
            "fields": ["shared_actor_count", "shared_actor_same_creator_count", "shared_early_buyer_count"],
            "status_rule": "available when actor is present in lifecycle events",
        },
        "common_transaction_source_proxy": {
            "fields": ["repeated_signature_count"],
            "status_rule": "partial when signature is present; signer and fee payer need explicit fields",
        },
        "funding_link_proxy": {
            "fields": ["fee_payer", "funding_source_wallet", "source_wallet"],
            "status_rule": "blocked when funding/source wallet fields are absent",
        },
        "synchronized_participation_proxy": {
            "fields": ["first_minute_actor_count", "first_minute_event_count", "first_minute_actor_concentration"],
            "status_rule": "available when actor and block_time are present",
        },
        "circularity_churn_proxy": {
            "fields": ["quick_buy_sell_churn_actor_count", "high_event_intensity_small_actor_set"],
            "status_rule": "available when actor, side, and block_time are present",
        },
    }


def _proxy_family_feasibility(
    field_availability: dict[str, dict[str, dict[str, Any]]],
    coverage_summary: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    event_fields = field_availability["event_fields"]
    holder_fields = field_availability["holder_state_fields"]
    return {
        "creator_linked_ownership_proxy": _status(
            holder_fields["creator_holder_share"]["available_count"] > 0,
            "creator_holder_share_available",
            "creator_holder_share_unavailable",
        ),
        "repeated_participant_overlap_proxy": _status(
            event_fields["actor"]["available_count"] > 0,
            "actor_field_available",
            "actor_field_unavailable",
        ),
        "common_transaction_source_proxy": {
            "status": "partial" if event_fields["signature"]["available_count"] > 0 else "blocked",
            "reason": "signature_available_but_signer_fee_payer_absent"
            if event_fields["signature"]["available_count"] > 0
            else "signature_unavailable",
        },
        "funding_link_proxy": _status(
            any(event_fields[field]["available_count"] > 0 for field in ("fee_payer", "funding_source_wallet", "source_wallet")),
            "funding_or_source_wallet_field_available",
            "funding_or_source_wallet_fields_unavailable",
        ),
        "synchronized_participation_proxy": _status(
            event_fields["actor"]["available_count"] > 0 and event_fields["block_time"]["available_count"] > 0,
            "actor_and_block_time_available",
            "actor_or_block_time_unavailable",
        ),
        "circularity_churn_proxy": _status(
            event_fields["actor"]["available_count"] > 0 and event_fields["side"]["available_count"] > 0,
            "actor_and_side_available",
            "actor_or_side_unavailable",
        ),
        "entity_proxy_grouped_holder_share": {
            "status": "blocked",
            "reason": "safe_entity_grouping_not_available_from_actor_overlap_alone",
            "launches_with_shared_actors": coverage_summary.get("launches_with_shared_early_buyers", 0),
        },
    }


def _status(condition: bool, yes_reason: str, no_reason: str) -> dict[str, str]:
    return {"status": "feasible" if condition else "blocked", "reason": yes_reason if condition else no_reason}


def _coverage_summary(pilot_rows: list[dict[str, Any]]) -> dict[str, Any]:
    missing_reason_counts = Counter()
    for row in pilot_rows:
        missing_reason_counts.update(row["proxy_missing_reasons"].values())
    return {
        "computed_proxy_coverage": {
            "creator_holder_share": _coverage(pilot_rows, lambda row: row["proxy_fields"]["creator_holder_share_30m_or_latest"] is not None),
            "shared_actor_count": _coverage(pilot_rows, lambda row: row["proxy_fields"]["shared_actor_count"] is not None),
            "first_minute_actor_concentration": _coverage(pilot_rows, lambda row: row["proxy_fields"]["first_minute_actor_concentration"] is not None),
            "quick_buy_sell_churn_actor_count": _coverage(pilot_rows, lambda row: row["proxy_fields"]["quick_buy_sell_churn_actor_count"] is not None),
        },
        "missing_reason_counts": dict(sorted(missing_reason_counts.items())),
        "repeated_actors_across_launches": sum(1 for row in pilot_rows if row["proxy_fields"]["shared_actor_count"] > 0),
        "repeated_actors_with_same_creator": sum(1 for row in pilot_rows if row["proxy_fields"]["shared_actor_same_creator_count"] > 0),
        "launches_with_shared_early_buyers": sum(1 for row in pilot_rows if row["proxy_fields"]["shared_early_buyer_count"] > 0),
        "launches_with_high_first_minute_concentration": sum(
            1 for row in pilot_rows
            if (row["proxy_fields"]["first_minute_actor_concentration"] or 0) >= 0.75
            and row["proxy_fields"]["first_minute_event_count"] >= 4
        ),
        "launches_with_quick_buy_sell_churn": sum(1 for row in pilot_rows if row["proxy_fields"]["quick_buy_sell_churn_actor_count"] > 0),
        "launches_with_creator_retained_balance_data": sum(
            1 for row in pilot_rows if row["proxy_fields"]["creator_retained_balance_proxy_available"]
        ),
    }


def _readiness(
    field_availability: dict[str, dict[str, dict[str, Any]]],
    coverage_summary: dict[str, Any],
    total_launches_available: int,
    launches_attempted: int,
) -> str:
    actor_available = field_availability["event_fields"]["actor"]["available_count"] > 0
    block_time_available = field_availability["event_fields"]["block_time"]["available_count"] > 0
    creator_share_available = coverage_summary["computed_proxy_coverage"]["creator_holder_share"]["available_count"] > 0
    clear_path_to_full = total_launches_available >= 1000 and launches_attempted <= 100
    if actor_available and block_time_available and creator_share_available and clear_path_to_full:
        return READINESS_READY
    if actor_available or creator_share_available:
        return READINESS_PARTIAL
    return READINESS_BLOCKED


def _next_recommendation(readiness: str) -> str:
    if readiness == READINESS_READY:
        return "scale entity-proxy construction to the full strict cohort, then run a separate descriptive thesis only after coverage audit"
    if readiness == READINESS_PARTIAL:
        return "repair missing proxy inputs or inspect manual examples before full-cohort rollout"
    return "do not pursue entity-proxy thesis work until actor or holder-state fields are available"


def _manual_review_sample(pilot_rows: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    scored = sorted(
        pilot_rows,
        key=lambda row: (
            row["proxy_fields"]["shared_actor_count"],
            row["proxy_fields"]["quick_buy_sell_churn_actor_count"],
            row["proxy_fields"]["first_minute_actor_concentration"] or 0,
            row.get("mint") or "",
        ),
        reverse=True,
    )
    return scored[:limit]


def _field_coverage(rows: list[dict[str, Any]], fields: list[str], mints: set[str] | None = None) -> dict[str, dict[str, Any]]:
    if mints is not None:
        rows = [row for row in rows if (row.get("mint") or row.get("token_mint")) in mints]
    total = len(rows)
    return {
        field: {
            "available_count": sum(1 for row in rows if _field_present(row, field)),
            "missing_count": total - sum(1 for row in rows if _field_present(row, field)),
            "coverage_pct": _pct(sum(1 for row in rows if _field_present(row, field)), total),
        }
        for field in fields
    }


def _field_present(row: dict[str, Any], field: str) -> bool:
    if row.get(field) is not None:
        return True
    metadata = row.get("metadata_json") or {}
    if metadata.get(field) is not None:
        return True
    raw_metadata = metadata.get("raw_record_metadata_json") or {}
    return raw_metadata.get(field) is not None


def _bounded_events(path: Path | str, selected_mints: set[str], max_events: int) -> list[dict[str, Any]]:
    events = []
    with Path(path).open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("token_mint") not in selected_mints:
                continue
            events.append(row)
            if len(events) >= max_events:
                break
    return events


def _holder_state_by_mint(rows: list[dict[str, Any]], selected_mints: set[str]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        mint = row.get("mint") or row.get("token_mint")
        if mint in selected_mints:
            grouped[mint].append(row)
    return dict(grouped)


def _actor_launch_counts(events: list[dict[str, Any]]) -> Counter:
    actor_to_mints: dict[str, set[str]] = defaultdict(set)
    for event in events:
        actor = event.get("actor")
        if actor:
            actor_to_mints[str(actor)].add(str(event.get("token_mint")))
    return Counter({actor: len(mints) for actor, mints in actor_to_mints.items()})


def _actor_creator_counts(events: list[dict[str, Any]], candidates: list[dict[str, Any]]) -> Counter:
    creator_by_mint = {row.get("token_mint") or row.get("mint"): _creator(row) for row in candidates}
    actor_creator_mints: dict[tuple[str | None, str], set[str]] = defaultdict(set)
    for event in events:
        actor = event.get("actor")
        mint = event.get("token_mint")
        if actor and mint:
            actor_creator_mints[(creator_by_mint.get(mint), str(actor))].add(str(mint))
    return Counter({key: len(mints) for key, mints in actor_creator_mints.items()})


def _signature_launch_counts(events: list[dict[str, Any]]) -> Counter:
    signature_to_mints: dict[str, set[str]] = defaultdict(set)
    for event in events:
        signature = event.get("signature")
        if signature:
            signature_to_mints[str(signature)].add(str(event.get("token_mint")))
    return Counter({signature: len(mints) for signature, mints in signature_to_mints.items()})


def _group_by(rows: list[dict[str, Any]], field: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        value = row.get(field)
        if value:
            grouped[str(value)].append(row)
    return dict(grouped)


def _creator(candidate: dict[str, Any]) -> str | None:
    metadata = candidate.get("metadata_json") or {}
    return candidate.get("creator_deployer") or candidate.get("creator") or metadata.get("creator_deployer")


def _actors(events: list[dict[str, Any]]) -> set[str]:
    return {str(event["actor"]) for event in events if event.get("actor")}


def _event_time(event: dict[str, Any]) -> int:
    return _int_or_zero(event.get("block_time"))


def _launch_age(candidate: dict[str, Any], event: dict[str, Any]) -> int | None:
    launch_ts = candidate.get("launch_ts")
    block_time = event.get("block_time")
    if launch_ts is None or block_time is None:
        return None
    return _int_or_zero(block_time) - _int_or_zero(launch_ts)


def _first_minute_concentration(events: list[dict[str, Any]]) -> float | None:
    if not events:
        return None
    counts = Counter(event.get("actor") for event in events if event.get("actor"))
    if not counts:
        return None
    return counts.most_common(1)[0][1] / len(events)


def _quick_churn(events: list[dict[str, Any]], candidate: dict[str, Any], max_seconds: int = 120) -> set[str]:
    first_buy: dict[str, int] = {}
    churn = set()
    for event in sorted(events, key=_event_time):
        actor = event.get("actor")
        if not actor:
            continue
        age = _launch_age(candidate, event)
        if age is None or age > max_seconds:
            continue
        side = str(event.get("side") or event.get("event_type") or "").lower()
        if side not in SUPPORTED_SIDE_VALUES:
            continue
        if side in {"accumulate", "buy", "possible_buy"}:
            first_buy.setdefault(str(actor), age)
        elif str(actor) in first_buy:
            churn.add(str(actor))
    return churn


def _high_intensity_small_actor_set(events: list[dict[str, Any]]) -> bool:
    actors = _actors(events)
    return len(events) >= 20 and 0 < len(actors) <= 3


def _latest_holder_field(holder_rows: list[dict[str, Any]], field: str) -> float | None:
    rows = sorted(holder_rows, key=lambda row: _int_or_zero(row.get("snapshot_age_seconds")), reverse=True)
    for row in rows:
        value = row.get(field)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
    return None


def _coverage(rows: list[dict[str, Any]], predicate) -> dict[str, Any]:
    available = sum(1 for row in rows if predicate(row))
    return {"available_count": available, "missing_count": len(rows) - available, "coverage_pct": _pct(available, len(rows))}


def _pct(count: int, total: int) -> float:
    return (count / total * 100) if total else 0.0


def _int_or_zero(value: Any) -> int:
    try:
        if value is None:
            return 0
        return int(value)
    except (TypeError, ValueError):
        return 0


def _read_jsonl(path: Path | str) -> list[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _availability_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Entity Proxy Data Availability",
        "",
        f"- Launches attempted: `{report['scope']['launches_attempted']}`",
        f"- Events inspected: `{report['scope']['events_inspected']}`",
        "- No thesis cycle was run.",
        "- No outcomes were used for tuning or testing.",
        "",
    ]
    for group, fields in report["data_availability"].items():
        lines.extend([f"## {group.replace('_', ' ').title()}", "", "| Field | Available | Missing | Coverage |", "|---|---:|---:|---:|"])
        for field, stats in fields.items():
            lines.append(f"| `{field}` | {stats['available_count']} | {stats['missing_count']} | {stats['coverage_pct']:.2f}% |")
        lines.append("")
    lines.extend(["## Proxy Family Feasibility", ""])
    for family, status in report["proxy_family_feasibility"].items():
        lines.append(f"- `{family}`: `{status['status']}` - {status['reason']}")
    return "\n".join(lines) + "\n"


def _pilot_public_report(report: dict[str, Any]) -> dict[str, Any]:
    return report


def _pilot_markdown(report: dict[str, Any]) -> str:
    coverage = report["coverage_summary"]
    lines = [
        "# Entity Proxy Feasibility Pilot",
        "",
        f"- Readiness classification: `{report['readiness_classification']}`",
        f"- Launches attempted: `{report['scope']['launches_attempted']}`",
        f"- Events inspected: `{report['scope']['events_inspected']}`",
        "- No thesis cycle was run.",
        "- No backtest or walk-forward validation was run.",
        "- No trading rules were generated.",
        "",
        "## Coverage Summary",
        "",
    ]
    for key, value in coverage.items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Manual Review Sample", ""])
    for row in report["manual_review_sample"][:10]:
        lines.append(
            f"- `{row['mint']}` creator `{row['creator']}` shared actors "
            f"`{row['proxy_fields']['shared_actor_count']}`, churn actors "
            f"`{row['proxy_fields']['quick_buy_sell_churn_actor_count']}`"
        )
    lines.extend(["", "## Next Recommendation", "", report["next_recommendation"]])
    return "\n".join(lines) + "\n"
