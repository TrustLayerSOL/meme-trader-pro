"""Replay-safe holder-state feasibility pilot from normalized lifecycle events."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


HOLDER_SNAPSHOT_AGES = [30, 180, 600, 1800, 7200]
MAX_LAUNCHES = 50
MAX_HOLDER_SNAPSHOTS = 250
HOLDER_DISTRIBUTION_SOURCE = "offline_normalized_event_delta_replay_v0"


def build_holder_state_pilot_report(
    *,
    candidates_path: Path | str,
    events_path: Path | str,
    launch_limit: int = MAX_LAUNCHES,
) -> dict[str, Any]:
    candidates = _select_candidates(_read_jsonl(candidates_path), launch_limit)
    events_by_mint = _events_by_mint(_read_jsonl(events_path), {row["token_mint"] for row in candidates})
    holder_snapshots: list[dict[str, Any]] = []
    for candidate in candidates:
        holder_snapshots.extend(_build_launch_holder_snapshots(candidate, events_by_mint.get(candidate["token_mint"], [])))

    attempted = len(candidates) * len(HOLDER_SNAPSHOT_AGES)
    built = sum(1 for row in holder_snapshots if row["holder_count"] is not None)
    missing = attempted - built
    missing_reasons = Counter(
        row["holder_snapshot_missing_reason"] for row in holder_snapshots if row["holder_snapshot_missing_reason"]
    )
    scale_snapshots = 1500 * len(HOLDER_SNAPSHOT_AGES)
    report = {
        "pilot_id": "holder_state_feasibility_pilot_v0",
        "scope": "data_readiness_pilot_only",
        "hard_limits": {
            "max_launches": MAX_LAUNCHES,
            "max_holder_snapshots": MAX_HOLDER_SNAPSHOTS,
            "snapshot_ages_seconds": HOLDER_SNAPSHOT_AGES,
        },
        "methodology_flags": [
            "research_only",
            "data_readiness_only",
            "no_thesis_rerun",
            "no_backtest",
            "no_walk_forward_validation",
            "no_trading_logic",
            "no_threshold_optimization",
            "no_grid_search",
            "no_ml_black_boxes",
            "no_silent_holder_state_inference",
        ],
        "offline_reconstruction_audit": _offline_reconstruction_audit(events_by_mint),
        "launches_attempted": len(candidates),
        "snapshots_attempted": attempted,
        "snapshots_built": built,
        "missing_snapshots": missing,
        "missing_reasons": dict(sorted(missing_reasons.items())),
        "holder_count_coverage_pct": _coverage_pct(built, attempted),
        "top_holder_share_coverage_pct": _coverage_pct(
            sum(1 for row in holder_snapshots if row["top_holder_share"] is not None),
            attempted,
        ),
        "top_10_holder_share_coverage_pct": _coverage_pct(
            sum(1 for row in holder_snapshots if row["top_10_holder_share"] is not None),
            attempted,
        ),
        "api_calls_used": 0,
        "api_requirements": {
            "used_in_pilot": False,
            "api_calls_used": 0,
            "estimated_historical_holder_snapshots_for_1500_launches": scale_snapshots,
            "estimated_minimum_calls_if_external_snapshot_endpoint_exists": scale_snapshots,
            "cost_note": (
                "No API calls were used. If historical holder snapshots require an external indexed endpoint, "
                "a naive scale-up is one holder-state request per launch-age snapshot."
            ),
        },
        "estimated_cost_to_scale_to_1500_launches": {
            "launches": 1500,
            "holder_snapshots": scale_snapshots,
            "offline_event_replay_api_calls": 0,
            "external_snapshot_api_calls_if_required": scale_snapshots,
        },
        "holder_distribution_source": HOLDER_DISTRIBUTION_SOURCE,
        "holder_snapshots": holder_snapshots,
        "feasibility_result": _feasibility_result(built, attempted),
        "t001_t002_v2_feasible": built == attempted,
        "next_recommendation": _next_recommendation(built, attempted),
    }
    return report


def write_holder_state_pilot_outputs(report: dict[str, Any], *, output_dir: Path | str) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "holder_state_pilot_summary.json"
    markdown_path = output / "holder_state_pilot_summary.md"
    snapshots_path = output / "holder_state_snapshots.jsonl"
    json_path.write_text(json.dumps(_public_report(report), indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(_markdown_report(report), encoding="utf-8")
    with snapshots_path.open("w", encoding="utf-8") as f:
        for row in report["holder_snapshots"]:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return {
        "json_summary_path": json_path,
        "markdown_summary_path": markdown_path,
        "holder_snapshots_path": snapshots_path,
    }


def _select_candidates(rows: list[dict[str, Any]], launch_limit: int) -> list[dict[str, Any]]:
    limit = min(MAX_LAUNCHES, max(0, int(launch_limit)))
    eligible = [row for row in rows if row.get("token_mint") and row.get("launch_ts")]
    return sorted(eligible, key=lambda row: (int(row["launch_ts"]), row["token_mint"]))[:limit]


def _events_by_mint(rows: list[dict[str, Any]], mints: set[str]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        mint = row.get("token_mint")
        if mint in mints:
            grouped[mint].append(row)
    return {mint: sorted(events, key=lambda row: (int(row.get("block_time") or 0), row.get("signature") or "")) for mint, events in grouped.items()}


def _build_launch_holder_snapshots(candidate: dict[str, Any], events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    launch_ts = int(candidate["launch_ts"])
    token_mint = candidate["token_mint"]
    balances: dict[str, float] = {}
    event_index = 0
    previous_holders: set[str] | None = None
    snapshots: list[dict[str, Any]] = []
    for age in HOLDER_SNAPSHOT_AGES:
        snapshot_ts = launch_ts + age
        while event_index < len(events) and int(events[event_index].get("block_time") or 0) <= snapshot_ts:
            event = events[event_index]
            actor = event.get("actor")
            delta = _event_balance_delta(event)
            if actor and delta is not None:
                balances[str(actor)] = balances.get(str(actor), 0.0) + delta
                if balances[str(actor)] <= 0:
                    balances.pop(str(actor), None)
            event_index += 1
        current_holders = {holder for holder, balance in balances.items() if balance > 0}
        snapshot = _snapshot_row(
            candidate=candidate,
            launch_age_seconds=age,
            snapshot_ts=snapshot_ts,
            balances=balances,
            previous_holders=previous_holders,
            observed_events=len([event for event in events if int(event.get("block_time") or 0) <= snapshot_ts]),
        )
        snapshots.append(snapshot)
        if current_holders:
            previous_holders = current_holders
    return snapshots


def _snapshot_row(
    *,
    candidate: dict[str, Any],
    launch_age_seconds: int,
    snapshot_ts: int,
    balances: dict[str, float],
    previous_holders: set[str] | None,
    observed_events: int,
) -> dict[str, Any]:
    positive = {holder: balance for holder, balance in balances.items() if balance > 0}
    total = sum(positive.values())
    if not positive or total <= 0:
        return _base_snapshot(candidate, launch_age_seconds, snapshot_ts, observed_events) | {
            "holder_count": None,
            "top_holder_share": None,
            "top_10_holder_share": None,
            "holder_distribution_source": HOLDER_DISTRIBUTION_SOURCE,
            "holder_snapshot_confidence": "missing",
            "holder_snapshot_missing_reason": "no_observed_holder_balances_at_snapshot",
            "holder_retention_proxy": None,
        }
    sorted_balances = sorted(positive.values(), reverse=True)
    current_holders = set(positive)
    return _base_snapshot(candidate, launch_age_seconds, snapshot_ts, observed_events) | {
        "holder_count": len(positive),
        "top_holder_share": sorted_balances[0] / total,
        "top_10_holder_share": sum(sorted_balances[:10]) / total,
        "holder_distribution_source": HOLDER_DISTRIBUTION_SOURCE,
        "holder_snapshot_confidence": "medium",
        "holder_snapshot_missing_reason": None,
        "holder_retention_proxy": _retention_proxy(previous_holders, current_holders),
    }


def _base_snapshot(candidate: dict[str, Any], launch_age_seconds: int, snapshot_ts: int, observed_events: int) -> dict[str, Any]:
    return {
        "launch_id": candidate["launch_id"],
        "token_mint": candidate["token_mint"],
        "pool_address": candidate.get("pool_address"),
        "venue": candidate.get("venue"),
        "launch_ts": int(candidate["launch_ts"]),
        "snapshot_ts": snapshot_ts,
        "launch_age_seconds": launch_age_seconds,
        "observed_event_count_through_snapshot": observed_events,
    }


def _event_balance_delta(event: dict[str, Any]) -> float | None:
    qty = _float_or_none(event.get("base_qty"))
    if qty is None:
        return None
    side = str(event.get("side") or "").lower()
    event_type = str(event.get("event_type") or "").lower()
    if side in {"buy", "accumulate"} or event_type in {"possible_buy", "token_accumulation", "pumpfun_buy"}:
        return abs(qty)
    if side in {"sell", "distribute"} or event_type in {"possible_sell", "token_distribution", "pumpfun_sell"}:
        return -abs(qty)
    return None


def _retention_proxy(previous_holders: set[str] | None, current_holders: set[str]) -> float | None:
    if not previous_holders:
        return None
    return len(previous_holders & current_holders) / len(previous_holders)


def _offline_reconstruction_audit(events_by_mint: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    total_events = sum(len(events) for events in events_by_mint.values())
    events_with_actor = sum(1 for events in events_by_mint.values() for event in events if event.get("actor"))
    events_with_qty = sum(1 for events in events_by_mint.values() for event in events if _float_or_none(event.get("base_qty")) is not None)
    usable_events = sum(
        1
        for events in events_by_mint.values()
        for event in events
        if event.get("actor") and _event_balance_delta(event) is not None
    )
    return {
        "source": HOLDER_DISTRIBUTION_SOURCE,
        "tokens_with_events": len(events_by_mint),
        "total_events": total_events,
        "events_with_actor": events_with_actor,
        "events_with_base_qty": events_with_qty,
        "usable_balance_delta_events": usable_events,
        "offline_possible": usable_events > 0,
        "quality_note": (
            "This reconstructs observed holder balances from normalized lifecycle event deltas. "
            "It is replay-safe but not a confirmed full chain account-state snapshot."
        ),
    }


def _feasibility_result(built: int, attempted: int) -> str:
    if attempted == 0 or built == 0:
        return "blocked"
    coverage = built / attempted
    if coverage >= 0.8:
        return "feasible_offline"
    return "feasible_with_api"


def _next_recommendation(built: int, attempted: int) -> str:
    result = _feasibility_result(built, attempted)
    if result == "feasible_offline":
        return "scale offline holder-state replay to the strict cohort, then rerun T001/T002 v2 after coverage audit"
    if result == "feasible_with_api":
        return "use offline replay where available and evaluate an indexed historical holder-state API for missing snapshots"
    return "blocked until historical holder-state snapshots can be sourced or normalized event coverage is repaired"


def _public_report(report: dict[str, Any]) -> dict[str, Any]:
    public = dict(report)
    public.pop("holder_snapshots", None)
    return public


def _markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# Holder-State Enrichment Feasibility Pilot",
        "",
        f"- Feasibility result: `{report['feasibility_result']}`",
        f"- Launches attempted: `{report['launches_attempted']}`",
        f"- Snapshots attempted: `{report['snapshots_attempted']}`",
        f"- Snapshots built: `{report['snapshots_built']}`",
        f"- Missing snapshots: `{report['missing_snapshots']}`",
        f"- Holder count coverage: `{report['holder_count_coverage_pct']:.2f}%`",
        f"- Top holder share coverage: `{report['top_holder_share_coverage_pct']:.2f}%`",
        f"- Top 10 holder share coverage: `{report['top_10_holder_share_coverage_pct']:.2f}%`",
        f"- API calls used: `{report['api_calls_used']}`",
        f"- Holder distribution source: `{report['holder_distribution_source']}`",
        "",
        "## Missing Reasons",
        "",
    ]
    if report["missing_reasons"]:
        lines.extend(f"- `{reason}`: `{count}`" for reason, count in report["missing_reasons"].items())
    else:
        lines.append("- None")
    lines.extend(
        [
            "",
            "## Scale Estimate",
            "",
            f"- 1,500-launch holder snapshots: `{report['estimated_cost_to_scale_to_1500_launches']['holder_snapshots']}`",
            f"- Offline event-replay API calls: `{report['estimated_cost_to_scale_to_1500_launches']['offline_event_replay_api_calls']}`",
            f"- External snapshot calls if required: `{report['estimated_cost_to_scale_to_1500_launches']['external_snapshot_api_calls_if_required']}`",
            "",
            "## Feasibility For T001/T002 v2",
            "",
            f"- Feasible now: `{report['t001_t002_v2_feasible']}`",
            f"- Next recommendation: {report['next_recommendation']}",
            "",
            "## Quality Note",
            "",
            report["offline_reconstruction_audit"]["quality_note"],
            "",
            "No thesis was rerun. No strategy, execution, optimization, or promotion logic was generated.",
            "",
        ]
    )
    return "\n".join(lines)


def _coverage_pct(available: int, total: int) -> float:
    return (available / total * 100) if total else 0.0


def _read_jsonl(path: Path | str) -> list[dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
