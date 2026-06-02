"""Strict-cohort holder-state rollout from normalized lifecycle event deltas."""

from __future__ import annotations

import json
import time
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
from typing import Any

from research.mtp_research.validation.holder_state_pilot import (
    HOLDER_DISTRIBUTION_SOURCE,
    HOLDER_SNAPSHOT_AGES,
)


SNAPSHOT_LABELS = {
    30: "30s",
    180: "3m",
    600: "10m",
    1800: "30m",
    7200: "120m",
}
READINESS_READY = "holder_state_ready_for_T001_T002_v2"
READINESS_PARTIAL = "holder_state_partial_needs_review"
READINESS_BLOCKED = "holder_state_blocked"
SYSTEM_PROGRAM = "11111111111111111111111111111111"
TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
ASSOCIATED_TOKEN_PROGRAM = "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTnHQuwwXQf"
PUMP_FUN_PROGRAM_ID = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
KNOWN_PROGRAM_ACCOUNTS = {SYSTEM_PROGRAM, TOKEN_PROGRAM, ASSOCIATED_TOKEN_PROGRAM, PUMP_FUN_PROGRAM_ID}


def build_holder_state_rollout(
    *,
    candidates_path: Path | str,
    events_path: Path | str,
    max_launches: int | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    candidates = _select_candidates(_read_jsonl(candidates_path), max_launches=max_launches)
    events_by_mint = _events_by_mint(_read_jsonl(events_path), {row["token_mint"] for row in candidates})
    holder_snapshots: list[dict[str, Any]] = []
    negative_balance_events: list[dict[str, Any]] = []
    balance_warnings: list[dict[str, Any]] = []
    exclusion_events: list[dict[str, Any]] = []
    sell_without_prior_events: list[dict[str, Any]] = []
    duplicate_events: list[dict[str, Any]] = []
    for candidate in candidates:
        snapshots, negatives, warnings, exclusions, sells_without_prior, duplicates = _build_launch_snapshots(
            candidate,
            events_by_mint.get(candidate["token_mint"], []),
        )
        holder_snapshots.extend(snapshots)
        negative_balance_events.extend(negatives)
        balance_warnings.extend(warnings)
        exclusion_events.extend(exclusions)
        sell_without_prior_events.extend(sells_without_prior)
        duplicate_events.extend(duplicates)

    expected = len(candidates) * len(HOLDER_SNAPSHOT_AGES)
    built = sum(1 for row in holder_snapshots if row["holder_count"] is not None)
    missing = expected - built
    field_coverage = {
        "holder_count": _field_coverage(holder_snapshots, "holder_count", expected),
        "top_holder_share": _field_coverage(holder_snapshots, "top_holder_share", expected),
        "top_10_holder_share": _field_coverage(holder_snapshots, "top_10_holder_share", expected),
        "creator_holder_share": _field_coverage(holder_snapshots, "creator_holder_share", expected),
    }
    known_creator_rows = [row for row in holder_snapshots if row.get("creator_wallet")]
    missing_known_creator_share = sum(1 for row in known_creator_rows if row.get("creator_holder_share") is None)
    readiness = _readiness_classification(
        snapshot_coverage=field_coverage["holder_count"]["coverage_pct"],
        suspicious_negative_balance_count=len(negative_balance_events),
        missing_known_creator_share=missing_known_creator_share,
        caveat_present=True,
    )
    sell_without_prior_unique_launches = len({row["launch_id"] for row in sell_without_prior_events})
    sell_without_prior_unique_mints = len({row["mint"] for row in sell_without_prior_events})
    runtime_seconds = time.perf_counter() - started
    return {
        "rollout_id": "strict_cohort_holder_state_rollout_v0",
        "scope": "data_enrichment_rollout_only",
        "methodology_flags": [
            "research_only",
            "data_enrichment_only",
            "no_thesis_rerun",
            "no_backtest",
            "no_walk_forward_validation",
            "no_trading_logic",
            "no_threshold_optimization",
            "no_grid_search",
            "no_ml_black_boxes",
            "observed_delta_replay_not_full_chain_state",
        ],
        "snapshot_ages_seconds": HOLDER_SNAPSHOT_AGES,
        "launches_attempted": len(candidates),
        "launches_completed": len({row["launch_id"] for row in holder_snapshots if row["holder_count"] is not None}),
        "launches_failed": len(candidates) - len({row["launch_id"] for row in holder_snapshots if row["holder_count"] is not None}),
        "snapshots_expected": expected,
        "snapshots_built": built,
        "missing_snapshots": missing,
        "field_coverage": field_coverage,
        "holder_count_coverage_pct": field_coverage["holder_count"]["coverage_pct"],
        "top_holder_share_coverage_pct": field_coverage["top_holder_share"]["coverage_pct"],
        "top_10_holder_share_coverage_pct": field_coverage["top_10_holder_share"]["coverage_pct"],
        "creator_holder_share_coverage_pct": field_coverage["creator_holder_share"]["coverage_pct"],
        "confidence_distribution": dict(sorted(Counter(row["holder_snapshot_confidence"] for row in holder_snapshots).items())),
        "missing_reason_counts": _missing_reason_counts(holder_snapshots),
        "zero_holder_snapshots": sum(1 for row in holder_snapshots if row["holder_count"] in (None, 0)),
        "suspicious_negative_balance_count": len(negative_balance_events),
        "suspicious_negative_balance_examples": negative_balance_events[:10],
        "excluded_ambiguous_event_count": sum(1 for row in exclusion_events if row["excluded_event_reason"] == "ambiguous_swap_direction"),
        "excluded_program_pool_account_event_count": sum(
            1
            for row in exclusion_events
            if row["excluded_event_reason"] in {"program_account_excluded", "bonding_curve_account_excluded", "pool_account_excluded"}
        ),
        "excluded_event_reason_counts": dict(sorted(Counter(row["excluded_event_reason"] for row in exclusion_events).items())),
        "excluded_event_examples": exclusion_events[:20],
        "sell_without_prior_observed_balance_count": len(sell_without_prior_events),
        "sell_without_prior_observed_balance_unique_launches": sell_without_prior_unique_launches,
        "sell_without_prior_observed_balance_unique_mints": sell_without_prior_unique_mints,
        "sell_without_prior_observed_balance_examples": sell_without_prior_events[:20],
        "duplicate_event_skipped_count": len(duplicate_events),
        "duplicate_event_examples": duplicate_events[:20],
        "balance_conservation_warnings": balance_warnings[:20],
        "balance_conservation_warning_count": len(balance_warnings),
        "share_distribution": {
            "top_holder_share": _distribution(row.get("top_holder_share") for row in holder_snapshots),
            "top_10_holder_share": _distribution(row.get("top_10_holder_share") for row in holder_snapshots),
            "creator_holder_share": _distribution(row.get("creator_holder_share") for row in holder_snapshots),
        },
        "examples": {
            "high_concentration_launches": _example_launches(holder_snapshots, reverse=True),
            "low_concentration_launches": _example_launches(holder_snapshots, reverse=False),
        },
        "runtime_seconds": runtime_seconds,
        "storage_size": {},
        "api_calls_used": 0,
        "helius_credits_used": 0,
        "readiness_classification": readiness,
        "readiness_criteria": {
            "min_snapshot_coverage_pct": 95.0,
            "snapshot_coverage_pass": field_coverage["holder_count"]["coverage_pct"] >= 95.0,
            "no_unexplained_negative_balances": len(negative_balance_events) == 0,
            "negative_balances_eliminated_or_classified": len(negative_balance_events) == 0,
            "program_pool_bonding_curve_accounts_excluded": True,
            "no_missing_creator_share_for_known_creator": missing_known_creator_share == 0,
            "observed_delta_replay_caveat_present": True,
        },
        "is_confirmed_full_chain_snapshot": False,
        "caveat": (
            "Holder-state rows are observed delta replay snapshots reconstructed from normalized lifecycle events; "
            "they are not confirmed full-chain account-state snapshots."
        ),
        "t001_v2_feasible": readiness == READINESS_READY,
        "t002_v2_feasible": readiness == READINESS_READY,
        "holder_snapshots": holder_snapshots,
    }


def write_holder_state_rollout_outputs(
    rollout: dict[str, Any],
    *,
    dataset_dir: Path | str,
    report_dir: Path | str,
) -> dict[str, Path]:
    dataset = Path(dataset_dir)
    reports = Path(report_dir)
    dataset.mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)
    jsonl_path = dataset / "strict_cohort_holder_state_snapshots.jsonl"
    parquet_path = dataset / "strict_cohort_holder_state_snapshots.parquet"
    audit_json_path = reports / "holder_state_strict_cohort_audit.json"
    audit_markdown_path = reports / "holder_state_strict_cohort_audit.md"

    with jsonl_path.open("w", encoding="utf-8") as f:
        for row in rollout["holder_snapshots"]:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    _write_parquet(rollout["holder_snapshots"], parquet_path)
    rollout["storage_size"] = {
        "jsonl_bytes": jsonl_path.stat().st_size,
        "parquet_bytes": parquet_path.stat().st_size,
    }
    audit_json_path.write_text(json.dumps(_audit_report(rollout), indent=2, sort_keys=True), encoding="utf-8")
    audit_markdown_path.write_text(_audit_markdown(rollout), encoding="utf-8")
    return {
        "jsonl_path": jsonl_path,
        "parquet_path": parquet_path,
        "audit_json_path": audit_json_path,
        "audit_markdown_path": audit_markdown_path,
    }


def build_negative_balance_diagnostics(
    *,
    candidates_path: Path | str,
    events_path: Path | str,
    max_launches: int | None = None,
) -> dict[str, Any]:
    """Summarize the legacy negative-balance failure mode before repaired replay rules."""
    candidates = _select_candidates(_read_jsonl(candidates_path), max_launches=max_launches)
    events_by_mint = _events_by_mint(_read_jsonl(events_path), {row["token_mint"] for row in candidates})
    negative_events: list[dict[str, Any]] = []
    duplicate_keys: Counter[tuple[str | None, str | None]] = Counter()
    for candidate in candidates:
        balances: dict[str, float] = {}
        positive_seen: set[str] = set()
        for event in events_by_mint.get(candidate["token_mint"], []):
            duplicate_keys[(event.get("signature"), event.get("event_id"))] += 1
            actor = event.get("actor")
            delta = _event_balance_delta(event)
            if not actor or delta is None:
                continue
            actor = str(actor)
            before = balances.get(actor, 0.0)
            after = before + delta
            if after < -1e-9:
                negative_events.append({
                    "launch_id": candidate["launch_id"],
                    "mint": candidate["token_mint"],
                    "signature": event.get("signature"),
                    "event_id": event.get("event_id"),
                    "block_time": event.get("block_time"),
                    "snapshot_window": _snapshot_window(candidate, event),
                    "classification": _event_classification(event),
                    "event_type": event.get("event_type"),
                    "venue": event.get("venue"),
                    "source": event.get("source"),
                    "actor": actor,
                    "actor_role": _actor_role(candidate, actor),
                    "base_qty": event.get("base_qty"),
                    "balance_before": before,
                    "delta": delta,
                    "balance_after": after,
                    "appears_before_positive_balance_seed": actor not in positive_seen,
                    "metadata_reasons": (event.get("metadata_json") or {}).get("reasons") or [],
                })
                after = 0.0
            balances[actor] = after
            if delta > 0:
                positive_seen.add(actor)
            if balances.get(actor, 0.0) <= 0:
                balances.pop(actor, None)

    duplicated = {key: count for key, count in duplicate_keys.items() if count > 1}
    first_by_launch: dict[str, dict[str, Any]] = {}
    for event in negative_events:
        first_by_launch.setdefault(event["launch_id"], event)
    return {
        "report_id": "holder_state_negative_balance_diagnostics_v0",
        "scope": "diagnostic_only",
        "total_negative_balance_events": len(negative_events),
        "unique_launches_affected": len({row["launch_id"] for row in negative_events}),
        "unique_mints_affected": len({row["mint"] for row in negative_events}),
        "negative_events_by_classification": _counter_dict(row["classification"] for row in negative_events),
        "negative_events_by_snapshot_window": _counter_dict(row["snapshot_window"] for row in negative_events),
        "negative_events_by_actor_role": _counter_dict(row["actor_role"] for row in negative_events),
        "negative_events_by_source": _counter_dict(row["source"] for row in negative_events),
        "top_repeated_negative_actors": _top_counts(row["actor"] for row in negative_events),
        "top_repeated_negative_mints": _top_counts(row["mint"] for row in negative_events),
        "before_positive_balance_seed_count": sum(1 for row in negative_events if row["appears_before_positive_balance_seed"]),
        "duplicate_event_signature_instruction_count": len(duplicated),
        "duplicate_event_signature_instruction_examples": [
            {"signature": key[0], "event_id": key[1], "count": count}
            for key, count in list(duplicated.items())[:20]
        ],
        "first_negative_event_per_affected_launch": list(first_by_launch.values())[:50],
        "negative_balance_event_examples": negative_events[:50],
    }


def write_negative_balance_diagnostics(
    diagnostics: dict[str, Any],
    *,
    output_dir: Path | str,
) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "negative_balance_diagnostics.json"
    markdown_path = output / "negative_balance_diagnostics.md"
    json_path.write_text(json.dumps(diagnostics, indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(_negative_balance_markdown(diagnostics), encoding="utf-8")
    return {"negative_balance_json_path": json_path, "negative_balance_markdown_path": markdown_path}


def _select_candidates(rows: list[dict[str, Any]], max_launches: int | None = None) -> list[dict[str, Any]]:
    eligible = [row for row in rows if row.get("launch_id") and row.get("token_mint") and row.get("launch_ts")]
    ordered = sorted(eligible, key=lambda row: (int(row["launch_ts"]), row["token_mint"]))
    if max_launches is not None:
        return ordered[:max(0, int(max_launches))]
    return ordered


def _event_classification(event: dict[str, Any]) -> str:
    venue = str(event.get("venue") or "")
    event_type = str(event.get("event_type") or "")
    for label in ["pumpfun_buy", "pumpfun_sell", "pumpfun_swap", "pumpfun_create", "pumpfun_migrate"]:
        if venue == label or event_type == label:
            return label
    return "other"


def _snapshot_window(candidate: dict[str, Any], event: dict[str, Any]) -> str:
    block_time = event.get("block_time")
    if block_time is None:
        return "missing_block_time"
    age = int(block_time) - int(candidate["launch_ts"])
    for snapshot_age in HOLDER_SNAPSHOT_AGES:
        if age <= snapshot_age:
            return SNAPSHOT_LABELS[snapshot_age]
    return "after_120m"


def _counter_dict(values) -> dict[str, int]:
    return dict(sorted(Counter(str(value) for value in values).items()))


def _top_counts(values, limit: int = 15) -> list[dict[str, Any]]:
    return [{"value": value, "count": count} for value, count in Counter(str(value) for value in values).most_common(limit)]


def _events_by_mint(rows: list[dict[str, Any]], mints: set[str]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        mint = row.get("token_mint")
        if mint in mints:
            grouped[mint].append(row)
    return {
        mint: sorted(events, key=lambda row: (int(row.get("block_time") or 0), row.get("signature") or ""))
        for mint, events in grouped.items()
    }


def _build_launch_snapshots(
    candidate: dict[str, Any],
    events: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    launch_ts = int(candidate["launch_ts"])
    balances: dict[str, float] = {}
    previous_holders: set[str] | None = None
    event_index = 0
    negatives: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    sells_without_prior: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []
    snapshots: list[dict[str, Any]] = []
    observed_count = 0
    seen_event_keys: set[tuple[str | None, str | None]] = set()
    for age in HOLDER_SNAPSHOT_AGES:
        snapshot_ts = launch_ts + age
        while event_index < len(events) and int(events[event_index].get("block_time") or 0) <= snapshot_ts:
            event = events[event_index]
            event_key = (event.get("signature"), event.get("event_id"))
            if event_key in seen_event_keys:
                duplicates.append(_excluded_event(candidate, event, "duplicate_event_skipped"))
                event_index += 1
                continue
            seen_event_keys.add(event_key)
            actor = event.get("actor")
            exclusion_reason = _event_exclusion_reason(candidate, event)
            if exclusion_reason:
                exclusions.append(_excluded_event(candidate, event, exclusion_reason))
                observed_count += 1
                event_index += 1
                continue
            delta = _event_balance_delta(event)
            if actor and delta is not None:
                before = balances.get(str(actor), 0.0)
                after = before + delta
                if after < -1e-9:
                    reason = "sell_without_prior_observed_balance" if before <= 0 else "insufficient_prior_state"
                    sells_without_prior.append({
                        "launch_id": candidate["launch_id"],
                        "mint": candidate["token_mint"],
                        "actor": str(actor),
                        "signature": event.get("signature"),
                        "block_time": event.get("block_time"),
                        "event_type": event.get("event_type"),
                        "venue": event.get("venue"),
                        "balance_before": before,
                        "delta": delta,
                        "balance_after": after,
                        "negative_balance_reason": reason,
                        "raw_pre_clamp_balance": before,
                        "negative_balance_flag": True,
                    })
                    after = 0.0
                balances[str(actor)] = after
                if balances[str(actor)] <= 0:
                    balances.pop(str(actor), None)
            observed_count += 1
            event_index += 1
        snapshot = _snapshot_row(candidate, age, snapshot_ts, balances, previous_holders, observed_count)
        if snapshot["observed_holder_balance_sum"] is not None and snapshot["observed_holder_balance_sum"] < 0:
            warnings.append({"launch_id": candidate["launch_id"], "mint": candidate["token_mint"], "reason": "negative_balance_sum"})
        snapshots.append(snapshot)
        current_holders = {holder for holder, balance in balances.items() if balance > 0}
        if current_holders:
            previous_holders = current_holders
    return snapshots, negatives, warnings, exclusions, sells_without_prior, duplicates


def _snapshot_row(
    candidate: dict[str, Any],
    age: int,
    snapshot_ts: int,
    balances: dict[str, float],
    previous_holders: set[str] | None,
    observed_count: int,
) -> dict[str, Any]:
    positive = {holder: balance for holder, balance in balances.items() if balance > 0}
    total = sum(positive.values())
    creator = _creator_wallet(candidate)
    base = {
        "launch_id": candidate["launch_id"],
        "mint": candidate["token_mint"],
        "snapshot_label": SNAPSHOT_LABELS[age],
        "snapshot_age_seconds": age,
        "snapshot_time": snapshot_ts,
        "pool_address": candidate.get("pool_address"),
        "venue": candidate.get("venue"),
        "creator_wallet": creator,
        "holder_snapshot_source": HOLDER_DISTRIBUTION_SOURCE,
        "is_observed_delta_replay": True,
        "is_confirmed_full_chain_snapshot": False,
        "observed_event_count_through_snapshot": observed_count,
    }
    if not positive or total <= 0:
        return base | {
            "holder_count": None,
            "top_holder_share": None,
            "top_10_holder_share": None,
            "creator_holder_share": None,
            "observed_holder_balance_sum": None,
            "holder_snapshot_confidence": "missing",
            "holder_snapshot_missing_reason": "no_observed_holder_balances_at_snapshot",
            "holder_retention_proxy": None,
            "holder_churn_proxy": None,
            "net_new_holders": None,
            "exited_holder_count": None,
            "new_holder_count": None,
            "creator_linked_share": None,
        }
    sorted_balances = sorted(positive.values(), reverse=True)
    current_holders = set(positive)
    retention = _retention_proxy(previous_holders, current_holders)
    exited = len(previous_holders - current_holders) if previous_holders else None
    new = len(current_holders - previous_holders) if previous_holders else None
    return base | {
        "holder_count": len(positive),
        "top_holder_share": sorted_balances[0] / total,
        "top_10_holder_share": sum(sorted_balances[:10]) / total,
        "creator_holder_share": _creator_share(positive, total, creator),
        "observed_holder_balance_sum": total,
        "holder_snapshot_confidence": "medium",
        "holder_snapshot_missing_reason": None,
        "holder_retention_proxy": retention,
        "holder_churn_proxy": (1.0 - retention) if retention is not None else None,
        "net_new_holders": (new - exited) if new is not None and exited is not None else None,
        "exited_holder_count": exited,
        "new_holder_count": new,
        "creator_linked_share": _creator_share(positive, total, creator),
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


def _event_exclusion_reason(candidate: dict[str, Any], event: dict[str, Any]) -> str | None:
    event_type = str(event.get("event_type") or "").lower()
    side = str(event.get("side") or "").lower()
    venue = str(event.get("venue") or "").lower()
    if event_type in {"pumpfun_swap", "swap_candidate"} or (venue == "pumpfun_swap" and side not in {"buy", "sell"}):
        return "ambiguous_swap_direction"
    actor = event.get("actor")
    role = _actor_role(candidate, actor)
    if role in {"bonding_curve", "associated_bonding_curve"}:
        return "bonding_curve_account_excluded"
    if role == "pool_address":
        return "pool_account_excluded"
    if role in {"program_account", "mint_account"}:
        return "program_account_excluded"
    return None


def _actor_role(candidate: dict[str, Any], actor: object) -> str:
    if not actor:
        return "unknown"
    actor = str(actor)
    metadata = candidate.get("metadata_json") or {}
    if actor == _creator_wallet(candidate):
        return "creator"
    if actor == metadata.get("bonding_curve"):
        return "bonding_curve"
    if actor == metadata.get("associated_bonding_curve"):
        return "associated_bonding_curve"
    if actor == candidate.get("pool_address"):
        return "pool_address"
    if actor == candidate.get("token_mint"):
        return "mint_account"
    if actor in KNOWN_PROGRAM_ACCOUNTS:
        return "program_account"
    return "unknown"


def _excluded_event(candidate: dict[str, Any], event: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "launch_id": candidate["launch_id"],
        "mint": candidate["token_mint"],
        "signature": event.get("signature"),
        "event_id": event.get("event_id"),
        "block_time": event.get("block_time"),
        "event_type": event.get("event_type"),
        "venue": event.get("venue"),
        "actor": event.get("actor"),
        "actor_role": _actor_role(candidate, event.get("actor")),
        "excluded_event_reason": reason,
    }


def _creator_wallet(candidate: dict[str, Any]) -> str | None:
    metadata = candidate.get("metadata_json") or {}
    return candidate.get("creator_wallet") or candidate.get("creator_deployer") or metadata.get("creator_deployer") or metadata.get("creator_wallet")


def _creator_share(positive: dict[str, float], total: float, creator: str | None) -> float | None:
    if not creator or total <= 0:
        return None
    return positive.get(str(creator), 0.0) / total


def _retention_proxy(previous_holders: set[str] | None, current_holders: set[str]) -> float | None:
    if not previous_holders:
        return None
    return len(previous_holders & current_holders) / len(previous_holders)


def _readiness_classification(
    *,
    snapshot_coverage: float,
    suspicious_negative_balance_count: int,
    missing_known_creator_share: int,
    caveat_present: bool,
) -> str:
    if snapshot_coverage >= 95.0 and suspicious_negative_balance_count == 0 and missing_known_creator_share == 0 and caveat_present:
        return READINESS_READY
    if snapshot_coverage == 0 or suspicious_negative_balance_count > 0:
        return READINESS_BLOCKED
    return READINESS_PARTIAL


def _audit_report(rollout: dict[str, Any]) -> dict[str, Any]:
    public = dict(rollout)
    public.pop("holder_snapshots", None)
    return public


def _audit_markdown(rollout: dict[str, Any]) -> str:
    lines = [
        "# Holder-State Strict Cohort Audit",
        "",
        f"- Readiness classification: `{rollout['readiness_classification']}`",
        f"- Launches attempted: `{rollout['launches_attempted']}`",
        f"- Launches completed: `{rollout['launches_completed']}`",
        f"- Launches failed: `{rollout['launches_failed']}`",
        f"- Snapshots expected: `{rollout['snapshots_expected']}`",
        f"- Snapshots built: `{rollout['snapshots_built']}`",
        f"- Missing snapshots: `{rollout['missing_snapshots']}`",
        f"- Holder count coverage: `{rollout['holder_count_coverage_pct']:.2f}%`",
        f"- Top holder share coverage: `{rollout['top_holder_share_coverage_pct']:.2f}%`",
        f"- Top 10 holder share coverage: `{rollout['top_10_holder_share_coverage_pct']:.2f}%`",
        f"- Creator holder share coverage: `{rollout['creator_holder_share_coverage_pct']:.2f}%`",
        f"- Suspicious negative balance count: `{rollout['suspicious_negative_balance_count']}`",
        f"- Excluded ambiguous event count: `{rollout['excluded_ambiguous_event_count']}`",
        f"- Excluded program/pool/bonding curve event count: `{rollout['excluded_program_pool_account_event_count']}`",
        f"- Sell without prior observed balance count: `{rollout['sell_without_prior_observed_balance_count']}`",
        f"- Sell without prior observed balance unique launches: `{rollout['sell_without_prior_observed_balance_unique_launches']}`",
        f"- Duplicate event skipped count: `{rollout['duplicate_event_skipped_count']}`",
        f"- Balance conservation warning count: `{rollout['balance_conservation_warning_count']}`",
        f"- Runtime seconds: `{rollout['runtime_seconds']:.4f}`",
        f"- Storage size: `{rollout['storage_size']}`",
        "",
        "## Caveat",
        "",
        rollout["caveat"],
        "",
        "These rows are not full-chain holder-state snapshots.",
        "",
        "## Share Distributions",
        "",
        f"- Top holder share: `{rollout['share_distribution']['top_holder_share']}`",
        f"- Top 10 holder share: `{rollout['share_distribution']['top_10_holder_share']}`",
        f"- Creator holder share: `{rollout['share_distribution']['creator_holder_share']}`",
        "",
        "## Examples",
        "",
        f"- High concentration launches: `{rollout['examples']['high_concentration_launches']}`",
        f"- Low concentration launches: `{rollout['examples']['low_concentration_launches']}`",
        "",
        "No T001/T002 rerun was performed.",
        "",
    ]
    return "\n".join(lines)


def _negative_balance_markdown(diagnostics: dict[str, Any]) -> str:
    lines = [
        "# Holder-State Negative Balance Diagnostics",
        "",
        f"- Total negative balance events: `{diagnostics['total_negative_balance_events']}`",
        f"- Unique launches affected: `{diagnostics['unique_launches_affected']}`",
        f"- Unique mints affected: `{diagnostics['unique_mints_affected']}`",
        f"- Before positive balance seed count: `{diagnostics['before_positive_balance_seed_count']}`",
        f"- Duplicate signature/instruction count: `{diagnostics['duplicate_event_signature_instruction_count']}`",
        "",
        "## Counts",
        "",
        f"- By classification: `{diagnostics['negative_events_by_classification']}`",
        f"- By snapshot window: `{diagnostics['negative_events_by_snapshot_window']}`",
        f"- By actor role: `{diagnostics['negative_events_by_actor_role']}`",
        f"- By source: `{diagnostics['negative_events_by_source']}`",
        "",
        "## Top Repeats",
        "",
        f"- Actors: `{diagnostics['top_repeated_negative_actors']}`",
        f"- Mints: `{diagnostics['top_repeated_negative_mints']}`",
        "",
        "## Interpretation",
        "",
        "This report describes the legacy replay failure mode before conservative holder-delta repair rules are applied.",
        "It is diagnostic evidence only and does not make thesis or trading claims.",
        "",
    ]
    return "\n".join(lines)


def _write_parquet(rows: list[dict[str, Any]], output_path: Path) -> None:
    import pandas as pd

    output_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(output_path, index=False)


def _field_coverage(rows: list[dict[str, Any]], field: str, total: int) -> dict[str, Any]:
    available = sum(1 for row in rows if row.get(field) is not None)
    return {"available_snapshots": available, "missing_snapshots": total - available, "coverage_pct": _pct(available, total)}


def _missing_reason_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counter = Counter(row["holder_snapshot_missing_reason"] for row in rows if row.get("holder_snapshot_missing_reason"))
    return dict(sorted(counter.items()))


def _distribution(values) -> dict[str, float | None]:
    clean = sorted(float(value) for value in values if value is not None)
    if not clean:
        return {"min": None, "median": None, "max": None}
    return {"min": clean[0], "median": median(clean), "max": clean[-1]}


def _example_launches(rows: list[dict[str, Any]], *, reverse: bool) -> list[dict[str, Any]]:
    usable = [row for row in rows if row.get("top_holder_share") is not None]
    ordered = sorted(usable, key=lambda row: (row["top_holder_share"], row["launch_id"], row["snapshot_age_seconds"]), reverse=reverse)
    return [
        {
            "launch_id": row["launch_id"],
            "mint": row["mint"],
            "snapshot_label": row["snapshot_label"],
            "top_holder_share": row["top_holder_share"],
            "holder_count": row["holder_count"],
        }
        for row in ordered[:5]
    ]


def _pct(available: int, total: int) -> float:
    return (available / total * 100) if total else 0.0


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _read_jsonl(path: Path | str) -> list[dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
