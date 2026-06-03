"""Forward efficient-mover freshness/actionability quality audit.

This audit is read-only. It inspects already-written forward observation
artifacts and does not collect candidates, call Helius, or create trading
signals.
"""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any


REPORT_ID = "forward_50_freshness_quality_audit_v0"
LEVELS = {
    "10k": 10_000.0,
    "15k": 15_000.0,
    "20k": 20_000.0,
    "30k": 30_000.0,
    "50k": 50_000.0,
    "100k": 100_000.0,
    "500k": 500_000.0,
    "1m": 1_000_000.0,
}
QUOTE_MINTS = {
    "So11111111111111111111111111111111111111112",
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "Es9vMFrzaCERmJfrF4H2FYD4FJTPri1BLRGKkzFTFHL",
    "USD1ttGY1N17NEEHLmELoaybftRBUSErhqYiQzvEmuB",
}
OUTPUT_NAMES = {
    "freshness": "forward_50_freshness_audit.csv",
    "source": "forward_50_source_freshness.csv",
    "duplicates": "forward_50_duplicate_transition_audit.csv",
    "fdv": "forward_50_fdv_proxy_sanity.csv",
    "actionability": "forward_50_actionability_timing.csv",
    "completeness": "forward_50_data_completeness.csv",
    "reconciliation": "forward_50_status_reconciliation.csv",
    "summary_json": "forward_50_freshness_quality_summary.json",
    "summary_md": "forward_50_freshness_quality_summary.md",
}
GUARDRAILS = [
    "audit_only",
    "no_network_calls",
    "no_helius_calls",
    "no_paper_trading",
    "no_live_trading",
    "no_wallet_execution",
    "no_order_routing",
    "no_backtest",
    "no_validation",
    "no_strategy_generation",
]


@dataclass(frozen=True)
class LoadedJsonl:
    rows: list[dict[str, Any]]
    malformed_rows: int
    missing: bool


def build_forward_50_freshness_quality_audit(
    data_root: Path | str = "/Volumes/ORICO/MemeTraderPro",
    *,
    max_candidates: int = 50,
    output_dir: Path | str | None = None,
    write_outputs: bool = True,
) -> tuple[dict[str, Any], dict[str, Path]]:
    data_root = Path(data_root).expanduser()
    observation_root = data_root / "data" / "forward_observation" / "efficient_movers"
    raw_root = data_root / "data" / "raw" / "forward_observation" / "efficient_movers"
    report_root = (
        Path(output_dir).expanduser()
        if output_dir
        else data_root / "data" / "backtests" / "diagnostics" / "reports" / "forward_observation" / "efficient_movers"
    )
    files = _load_files(observation_root, raw_root)
    all_candidates = files["candidates"].rows
    candidates = all_candidates[: max(0, int(max_candidates))]
    selected_ids = {str(row.get("observation_id")) for row in candidates if row.get("observation_id")}
    scoped = _scope_files(files, selected_ids)

    freshness_rows = [_candidate_freshness_row(row, scoped) for row in candidates]
    duplicate_rows = [_duplicate_row(row, scoped) for row in candidates]
    fdv_rows = [_fdv_sanity_row(row, scoped) for row in candidates]
    actionability_rows = [_actionability_row(row, scoped) for row in candidates]
    completeness_rows = [_completeness_row(row, scoped) for row in candidates]
    source_rows = _source_summary_rows(freshness_rows, actionability_rows, scoped)
    reconciliation_rows = _status_reconciliation_rows(observation_root, scoped, max_candidates=len(candidates))
    summary = _summary(
        data_root=data_root,
        observation_root=observation_root,
        raw_root=raw_root,
        report_root=report_root,
        files=files,
        candidates=candidates,
        all_candidate_count=len(all_candidates),
        freshness_rows=freshness_rows,
        source_rows=source_rows,
        duplicate_rows=duplicate_rows,
        fdv_rows=fdv_rows,
        actionability_rows=actionability_rows,
        completeness_rows=completeness_rows,
        reconciliation_rows=reconciliation_rows,
    )
    paths: dict[str, Path] = {}
    if write_outputs:
        report_root.mkdir(parents=True, exist_ok=True)
        paths = {
            "freshness_csv": _write_csv(report_root / OUTPUT_NAMES["freshness"], freshness_rows),
            "source_csv": _write_csv(report_root / OUTPUT_NAMES["source"], source_rows),
            "duplicate_transition_csv": _write_csv(report_root / OUTPUT_NAMES["duplicates"], duplicate_rows),
            "fdv_proxy_sanity_csv": _write_csv(report_root / OUTPUT_NAMES["fdv"], fdv_rows),
            "actionability_timing_csv": _write_csv(report_root / OUTPUT_NAMES["actionability"], actionability_rows),
            "data_completeness_csv": _write_csv(report_root / OUTPUT_NAMES["completeness"], completeness_rows),
            "status_reconciliation_csv": _write_csv(report_root / OUTPUT_NAMES["reconciliation"], reconciliation_rows),
            "summary_json": _write_json(report_root / OUTPUT_NAMES["summary_json"], summary),
            "summary_markdown": _write_markdown(report_root / OUTPUT_NAMES["summary_md"], summary),
        }
    return summary, paths


def _load_files(observation_root: Path, raw_root: Path) -> dict[str, LoadedJsonl]:
    return {
        "candidates": _load_jsonl(observation_root / "candidates.jsonl"),
        "paths": _load_jsonl(observation_root / "candidate_paths.jsonl"),
        "events": _load_jsonl(observation_root / "candidate_events.jsonl"),
        "metadata": _load_jsonl(observation_root / "candidate_metadata.jsonl"),
        "holders": _load_jsonl(observation_root / "candidate_holders.jsonl"),
        "drawdowns": _load_jsonl(observation_root / "candidate_drawdowns.jsonl"),
        "source_candidates": _load_jsonl(raw_root / "source_candidates.jsonl"),
        "helius_rpc_raw": _load_jsonl(raw_root / "helius_rpc_raw.jsonl"),
    }


def _load_jsonl(path: Path) -> LoadedJsonl:
    if not path.exists():
        return LoadedJsonl(rows=[], malformed_rows=0, missing=True)
    rows: list[dict[str, Any]] = []
    malformed = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                malformed += 1
                continue
            if isinstance(value, dict):
                rows.append(value)
            else:
                malformed += 1
    return LoadedJsonl(rows=rows, malformed_rows=malformed, missing=False)


def _scope_files(files: dict[str, LoadedJsonl], selected_ids: set[str]) -> dict[str, list[dict[str, Any]]]:
    scoped: dict[str, list[dict[str, Any]]] = {}
    for name, loaded in files.items():
        if name == "helius_rpc_raw":
            scoped[name] = loaded.rows
            continue
        scoped[name] = [row for row in loaded.rows if str(row.get("observation_id")) in selected_ids]
    return scoped


def _candidate_freshness_row(candidate: dict[str, Any], scoped: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    oid = str(candidate.get("observation_id") or "")
    paths = _rows_for(scoped["paths"], oid)
    source_rows = _rows_for(scoped["source_candidates"], oid)
    first_path = min(paths, key=lambda row: _num(row.get("timestamp") or row.get("observed_at") or 0), default={})
    source = candidate.get("source") or first_path.get("source")
    first_fdv = _num(first_path.get("fdv_proxy") if first_path else None)
    first_seen_time = _num(candidate.get("first_seen_time") or candidate.get("observed_at") or first_path.get("timestamp"))
    first_cross = {level: _first_cross_time(paths, threshold) for level, threshold in LEVELS.items()}
    classification = classify_freshness(source=source, first_seen_fdv_proxy=first_fdv, first_cross_times=first_cross)
    return {
        "observation_id": oid,
        "mint": candidate.get("mint") or candidate.get("token_mint"),
        "pool_address": _first_non_null(source_rows + paths, "pool_address"),
        "source_adapter": source,
        "source": source,
        "token_name": candidate.get("token_name"),
        "token_symbol": candidate.get("token_symbol"),
        "first_seen_time": first_seen_time,
        "first_seen_source": source,
        "first_seen_fdv_proxy": first_fdv,
        "first_seen_price_proxy": _num(first_path.get("price_proxy")) if first_path else None,
        "first_seen_liquidity_proxy": _num(first_path.get("liquidity_proxy")) if first_path else None,
        "first_seen_event_count": _num(first_path.get("event_count")) if first_path else None,
        "first_seen_buy_count": _num(first_path.get("buy_count")) if first_path else None,
        "first_seen_sell_count": _num(first_path.get("sell_count")) if first_path else None,
        "first_seen_active_wallets": _num(first_path.get("active_wallets")) if first_path else None,
        **{f"first_crossed_{level}_time": value for level, value in first_cross.items()},
        "birth_observed_candidate": classification == "birth_observed_candidate",
        "pre_10k_observed_candidate": _pre_observed(first_fdv, first_cross["10k"], 10_000.0),
        "pre_15k_observed_candidate": _pre_observed(first_fdv, first_cross["15k"], 15_000.0),
        "pre_20k_observed_candidate": _pre_observed(first_fdv, first_cross["20k"], 20_000.0),
        "already_above_10k_at_first_seen": _gte(first_fdv, 10_000.0),
        "already_above_15k_at_first_seen": _gte(first_fdv, 15_000.0),
        "already_above_20k_at_first_seen": _gte(first_fdv, 20_000.0),
        "already_above_50k_at_first_seen": _gte(first_fdv, 50_000.0),
        "already_above_100k_at_first_seen": _gte(first_fdv, 100_000.0),
        "late_detection_flag": bool(first_fdv is not None and first_fdv >= 100_000.0),
        "missing_first_seen_fdv": first_fdv is None,
        "candidate_freshness_class": classification,
    }


def classify_freshness(
    *,
    source: Any,
    first_seen_fdv_proxy: float | None,
    first_cross_times: dict[str, Any] | None = None,
) -> str:
    source_text = str(source or "").lower()
    crosses = first_cross_times or {}
    if first_seen_fdv_proxy is None:
        if "create" in source_text or "birth" in source_text or "launch" in source_text:
            return "birth_observed_candidate"
        return "unknown_freshness"
    if ("create" in source_text or "birth" in source_text or "launch" in source_text) and first_seen_fdv_proxy < 10_000:
        return "birth_observed_candidate"
    if first_seen_fdv_proxy < 10_000 and crosses.get("10k"):
        return "pre_10k_observed_candidate"
    if first_seen_fdv_proxy < 15_000 and crosses.get("15k"):
        return "pre_15k_observed_candidate"
    if first_seen_fdv_proxy < 20_000 and crosses.get("20k"):
        return "pre_20k_observed_candidate"
    if first_seen_fdv_proxy >= 100_000:
        return "already_above_100k_candidate"
    if first_seen_fdv_proxy >= 50_000:
        return "already_above_50k_candidate"
    if first_seen_fdv_proxy >= 20_000:
        return "already_above_20k_candidate"
    return "unknown_freshness"


def _duplicate_row(candidate: dict[str, Any], scoped: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    mint = candidate.get("mint") or candidate.get("token_mint")
    oid = str(candidate.get("observation_id") or "")
    candidate_sources = sorted({str(row.get("source")) for row in scoped["candidates"] if (row.get("mint") or row.get("token_mint")) == mint})
    source_rows = [row for row in scoped["source_candidates"] if (row.get("mint") or row.get("token_mint")) == mint]
    source_emits = len(source_rows)
    repeated_trigger_rows = len(_rows_for(scoped["paths"], oid))
    if len(candidate_sources) > 1:
        duplicate_class = "legitimate_source_transition"
    elif source_emits > 1:
        duplicate_class = "duplicate_trigger_update"
    else:
        duplicate_class = "unique_candidate"
    return {
        "observation_id": oid,
        "mint": mint,
        "pool_address": _first_non_null(source_rows, "pool_address"),
        "source_adapters": "|".join(candidate_sources),
        "same_mint_candidate_count": sum(1 for row in scoped["candidates"] if (row.get("mint") or row.get("token_mint")) == mint),
        "same_mint_source_candidate_count": source_emits,
        "same_mint_across_multiple_source_adapters": len(candidate_sources) > 1,
        "same_mint_pumpfun_then_pumpswap": "helius_program_logs_pumpfun" in candidate_sources and "helius_program_logs_pumpswap" in candidate_sources,
        "same_mint_pumpswap_then_raydium": "helius_program_logs_pumpswap" in candidate_sources and "helius_program_logs_raydium" in candidate_sources,
        "same_mint_with_repeated_trigger_rows": repeated_trigger_rows > 1,
        "duplicate_classification": duplicate_class,
    }


def _fdv_sanity_row(candidate: dict[str, Any], scoped: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    oid = str(candidate.get("observation_id") or "")
    paths = _rows_for(scoped["paths"], oid)
    fdvs = [_num(row.get("fdv_proxy")) for row in paths]
    fdvs = [value for value in fdvs if value is not None]
    first_fdv = fdvs[0] if fdvs else None
    extreme_jumps = _extreme_jump_count(fdvs)
    zero_count = sum(1 for value in fdvs if value == 0)
    negative_count = sum(1 for value in fdvs if value < 0)
    if not fdvs:
        sanity = "missing_fdv_proxy"
    elif zero_count or negative_count:
        sanity = "invalid_fdv_proxy"
    elif extreme_jumps:
        sanity = "suspicious_fdv_jump"
    else:
        sanity = "valid_fdv_proxy"
    return {
        "observation_id": oid,
        "mint": candidate.get("mint") or candidate.get("token_mint"),
        "first_seen_fdv_proxy": first_fdv,
        "min_fdv_proxy": min(fdvs) if fdvs else None,
        "max_fdv_proxy": max(fdvs) if fdvs else None,
        "trigger_fdv_proxy": first_fdv,
        "fdv_proxy_zero_count": zero_count,
        "fdv_proxy_negative_count": negative_count,
        "fdv_proxy_extreme_jump_count": extreme_jumps,
        "fdv_proxy_monotonicity_notes": _monotonicity(fdvs),
        "impossible_fdv_jump_flag": extreme_jumps > 0,
        "missing_fdv_proxy_reason": None if fdvs else "no_path_fdv_proxy",
        "valid_fdv_proxy_candidate": sanity == "valid_fdv_proxy",
        "fdv_sanity_class": sanity,
    }


def classify_actionability(first_seen_fdv_proxy: float | None) -> str:
    if first_seen_fdv_proxy is None:
        return "insufficient_path_data"
    if first_seen_fdv_proxy < 10_000:
        return "actionable_pre_10k_observed"
    if first_seen_fdv_proxy < 15_000:
        return "actionable_pre_15k_observed"
    if first_seen_fdv_proxy < 20_000:
        return "actionable_pre_20k_observed"
    if first_seen_fdv_proxy < 30_000:
        return "observed_at_20k"
    if first_seen_fdv_proxy < 100_000:
        return "observed_after_20k_before_100k"
    if first_seen_fdv_proxy < 500_000:
        return "observed_after_100k"
    return "detected_too_late"


def _actionability_row(candidate: dict[str, Any], scoped: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    oid = str(candidate.get("observation_id") or "")
    paths = _rows_for(scoped["paths"], oid)
    times = [_num(row.get("timestamp") or row.get("observed_at")) for row in paths]
    first_path = min(paths, key=lambda row: _num(row.get("timestamp") or row.get("observed_at") or 0), default={})
    first_fdv = _num(first_path.get("fdv_proxy")) if first_path else None
    first_seen_time = _num(candidate.get("first_seen_time") or candidate.get("observed_at") or first_path.get("timestamp"))
    crosses = {level: _first_cross_time(paths, threshold) for level, threshold in LEVELS.items()}
    return {
        "observation_id": oid,
        "mint": candidate.get("mint") or candidate.get("token_mint"),
        "first_seen_time": first_seen_time,
        "first_seen_fdv_proxy": first_fdv,
        **{f"first_crossed_{level}_time": value for level, value in crosses.items()},
        "time_first_seen_to_10k": _delta(first_seen_time, crosses["10k"]),
        "time_first_seen_to_15k": _delta(first_seen_time, crosses["15k"]),
        "time_first_seen_to_20k": _delta(first_seen_time, crosses["20k"]),
        "time_10k_to_20k": _delta(crosses["10k"], crosses["20k"]),
        "time_15k_to_20k": _delta(crosses["15k"], crosses["20k"]),
        "time_20k_to_50k": _delta(crosses["20k"], crosses["50k"]),
        "time_20k_to_100k": _delta(crosses["20k"], crosses["100k"]),
        "time_20k_to_500k": _delta(crosses["20k"], crosses["500k"]),
        "time_trigger_to_local_high": 0 if first_seen_time is not None and first_fdv is not None else None,
        "path_rows_before_10k": _path_rows_below(paths, 10_000.0),
        "path_rows_before_15k": _path_rows_below(paths, 15_000.0),
        "path_rows_before_20k": _path_rows_below(paths, 20_000.0),
        "path_rows_between_20k_and_100k": _path_rows_between(paths, 20_000.0, 100_000.0),
        "median_path_sampling_interval_seconds": _median_interval(times),
        "actionability_class": classify_actionability(first_fdv),
    }


def _completeness_row(candidate: dict[str, Any], scoped: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    oid = str(candidate.get("observation_id") or "")
    paths = _rows_for(scoped["paths"], oid)
    events = _rows_for(scoped["events"], oid)
    metadata = _rows_for(scoped["metadata"], oid)
    holders = _rows_for(scoped["holders"], oid)
    drawdowns = _rows_for(scoped["drawdowns"], oid)
    source_rows = _rows_for(scoped["source_candidates"], oid)
    first_path = paths[0] if paths else {}
    first_meta = metadata[0] if metadata else {}
    return {
        "observation_id": oid,
        "mint": candidate.get("mint") or candidate.get("token_mint"),
        "has_candidate_summary": True,
        "has_path_rows": bool(paths),
        "has_event_rows": bool(events),
        "has_metadata_rows": bool(metadata),
        "has_holder_rows": bool(holders),
        "has_drawdown_rows": bool(drawdowns),
        "has_raw_source_rows": bool(source_rows),
        "has_fdv_proxy": _num(first_path.get("fdv_proxy")) is not None,
        "has_active_wallets": _num(first_path.get("active_wallets")) is not None,
        "has_buy_sell_counts": _num(first_path.get("buy_count")) is not None and _num(first_path.get("sell_count")) is not None,
        "has_metadata_name_symbol": bool(first_meta.get("token_name") or first_meta.get("token_symbol")),
        "has_social_links": bool(first_meta.get("website_url") or first_meta.get("twitter_x_url") or first_meta.get("telegram_url") or first_meta.get("discord_url")),
        "has_drawdown_tracking": bool(drawdowns),
        "has_source_transition_data": False,
    }


def _source_summary_rows(
    freshness_rows: list[dict[str, Any]],
    actionability_rows: list[dict[str, Any]],
    scoped: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    action_by_id = {row["observation_id"]: row for row in actionability_rows}
    for row in freshness_rows:
        by_source[str(row.get("source_adapter"))].append(row)
    rows = []
    for source, items in sorted(by_source.items()):
        classes = Counter(row["candidate_freshness_class"] for row in items)
        fdvs = [_num(row.get("first_seen_fdv_proxy")) for row in items]
        fdvs = [value for value in fdvs if value is not None]
        delays_20 = [_num(action_by_id[row["observation_id"]].get("time_first_seen_to_20k")) for row in items if row["observation_id"] in action_by_id]
        delays_100 = [_num(action_by_id[row["observation_id"]].get("time_first_seen_to_100k")) for row in items if row["observation_id"] in action_by_id]
        rows.append(
            {
                "source_adapter": source,
                "candidate_count": len(items),
                "unique_mints": len({row.get("mint") for row in items}),
                "birth_observed_count": classes["birth_observed_candidate"],
                "pre_10k_count": classes["pre_10k_observed_candidate"],
                "pre_15k_count": classes["pre_15k_observed_candidate"],
                "pre_20k_count": classes["pre_20k_observed_candidate"],
                "already_above_20k_count": classes["already_above_20k_candidate"],
                "already_above_50k_count": classes["already_above_50k_candidate"],
                "already_above_100k_count": classes["already_above_100k_candidate"],
                "late_detected_count": sum(1 for row in items if row.get("late_detection_flag")),
                "unknown_freshness_count": classes["unknown_freshness"],
                "median_first_seen_fdv_proxy": median(fdvs) if fdvs else None,
                "median_trigger_fdv": median(fdvs) if fdvs else None,
                "median_delay_first_seen_to_20k": _safe_median(delays_20),
                "median_delay_first_seen_to_100k": _safe_median(delays_100),
                "malformed_or_unparseable_row_count": sum(1 for row in scoped["helius_rpc_raw"] if row.get("source_adapter") == source and row.get("mint") is None),
            }
        )
    return rows


def _status_reconciliation_rows(observation_root: Path, scoped: dict[str, list[dict[str, Any]]], *, max_candidates: int) -> list[dict[str, Any]]:
    status_path = observation_root / "status.json"
    status = {}
    if status_path.exists():
        try:
            status = json.loads(status_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            status = {"__malformed__": True}
    paths = scoped["paths"]
    fields = {
        "total_candidates_observed": len(scoped["candidates"]),
        "event_rows_collected": len(scoped["events"]),
        "path_rows_collected": len(paths),
        "metadata_snapshots_collected": len(scoped["metadata"]),
        "holder_snapshots_collected": len(scoped["holders"]),
        "drawdown_rows_collected": len(scoped["drawdowns"]),
        "current_target_sample_size": max_candidates,
        "candidates_that_reached_10k": _count_crossed(paths, 10_000.0),
        "candidates_that_reached_15k": _count_crossed(paths, 15_000.0),
        "candidates_that_reached_20k": _count_crossed(paths, 20_000.0),
        "candidates_that_reached_30k": _count_crossed(paths, 30_000.0),
        "candidates_that_reached_50k": _count_crossed(paths, 50_000.0),
        "candidates_that_reached_100k": _count_crossed(paths, 100_000.0),
        "candidates_that_reached_500k": _count_crossed(paths, 500_000.0),
        "candidates_that_reached_1m": _count_crossed(paths, 1_000_000.0),
    }
    rows = []
    for key, loaded in fields.items():
        status_value = status.get(key)
        rows.append(
            {
                "field": key,
                "status_value": status_value,
                "loaded_file_value": loaded,
                "matches": status_value == loaded,
                "note": "status_file_global_may_include_rows_beyond_first_50" if status_value != loaded else None,
            }
        )
    rows.append(
        {
            "field": "recommended_stop_review_flag",
            "status_value": status.get("recommended_stop_review_flag"),
            "loaded_file_value": "audit_scoped_to_first_50",
            "matches": False,
            "note": "status_file_reflects_latest_global_observation_state_not_first_50_scope",
        }
    )
    return rows


def _summary(
    *,
    data_root: Path,
    observation_root: Path,
    raw_root: Path,
    report_root: Path,
    files: dict[str, LoadedJsonl],
    candidates: list[dict[str, Any]],
    all_candidate_count: int,
    freshness_rows: list[dict[str, Any]],
    source_rows: list[dict[str, Any]],
    duplicate_rows: list[dict[str, Any]],
    fdv_rows: list[dict[str, Any]],
    actionability_rows: list[dict[str, Any]],
    completeness_rows: list[dict[str, Any]],
    reconciliation_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    freshness = Counter(row["candidate_freshness_class"] for row in freshness_rows)
    actionability = Counter(row["actionability_class"] for row in actionability_rows)
    fdv = Counter(row["fdv_sanity_class"] for row in fdv_rows)
    duplicate_classes = Counter(row["duplicate_classification"] for row in duplicate_rows)
    completeness = _coverage(completeness_rows)
    source_mix = Counter(row.get("source") for row in candidates)
    quote_count = sum(1 for row in candidates if (row.get("mint") or row.get("token_mint")) in QUOTE_MINTS)
    readiness = classify_scale_readiness(
        candidate_count=len(candidates),
        valid_fdv_count=fdv["valid_fdv_proxy"],
        duplicate_classes=duplicate_classes,
        freshness_classes=freshness,
        status_mismatches=sum(1 for row in reconciliation_rows if not row["matches"]),
        quote_false_positive_count=quote_count,
    )
    recommendation = _recommendation(readiness, freshness, source_rows)
    return {
        "report_id": REPORT_ID,
        "data_root": str(data_root),
        "observation_root": str(observation_root),
        "raw_root": str(raw_root),
        "report_root": str(report_root),
        "candidate_scope": "first_50_forward_observed_candidates",
        "candidates_audited": len(candidates),
        "all_current_candidate_rows_present": all_candidate_count,
        "unique_observation_ids": len({row.get("observation_id") for row in candidates}),
        "unique_mints": len({row.get("mint") or row.get("token_mint") for row in candidates}),
        "unique_pools": len({row.get("pool_address") for row in files["source_candidates"].rows[: len(candidates)] if row.get("pool_address")}),
        "source_mix": dict(source_mix),
        "freshness_class_distribution": dict(freshness),
        "actionability_class_distribution": dict(actionability),
        "fdv_sanity_distribution": dict(fdv),
        "duplicate_class_distribution": dict(duplicate_classes),
        "data_completeness": completeness,
        "source_freshness": source_rows,
        "file_row_counts": {name: len(loaded.rows) for name, loaded in files.items()},
        "malformed_row_counts": {name: loaded.malformed_rows for name, loaded in files.items()},
        "missing_files": [name for name, loaded in files.items() if loaded.missing],
        "status_reconciliation_mismatch_count": sum(1 for row in reconciliation_rows if not row["matches"]),
        "known_quote_false_positive_count": quote_count,
        "readiness_classification": readiness,
        "recommendation": recommendation,
        "answer_questions": _answer_questions(source_rows, freshness, actionability),
        "guardrails": GUARDRAILS,
        "network_calls_made": 0,
    }


def classify_scale_readiness(
    *,
    candidate_count: int,
    valid_fdv_count: int,
    duplicate_classes: Counter[str],
    freshness_classes: Counter[str],
    status_mismatches: int,
    quote_false_positive_count: int = 0,
) -> str:
    if quote_false_positive_count:
        return "forward_50_needs_fdv_proxy_repair"
    if candidate_count <= 0:
        return "forward_50_inconclusive"
    if valid_fdv_count / candidate_count < 0.9:
        return "forward_50_needs_fdv_proxy_repair"
    bad_duplicates = _count(duplicate_classes, "duplicate_candidate_should_collapse") + _count(duplicate_classes, "suspicious_duplicate")
    if bad_duplicates:
        return "forward_50_needs_duplicate_repair"
    early_count = (
        _count(freshness_classes, "birth_observed_candidate")
        + _count(freshness_classes, "pre_10k_observed_candidate")
        + _count(freshness_classes, "pre_15k_observed_candidate")
        + _count(freshness_classes, "pre_20k_observed_candidate")
    )
    already_late = (
        _count(freshness_classes, "already_above_20k_candidate")
        + _count(freshness_classes, "already_above_50k_candidate")
        + _count(freshness_classes, "already_above_100k_candidate")
    )
    if early_count == 0 or already_late / candidate_count >= 0.5:
        return "forward_50_needs_source_freshness_repair"
    if status_mismatches:
        return "forward_50_inconclusive"
    return "forward_50_ready_to_scale_to_100"


def _count(counts: Counter[str] | dict[str, int], key: str) -> int:
    return int(counts.get(key, 0))


def _recommendation(readiness: str, freshness: Counter[str], source_rows: list[dict[str, Any]]) -> str:
    if readiness == "forward_50_ready_to_scale_to_100":
        return "A. Scale to 100 candidates with late-detected candidates separated from main actionability tally."
    if readiness == "forward_50_needs_source_freshness_repair":
        pumpswap = next((row for row in source_rows if row["source_adapter"] == "helius_program_logs_pumpswap"), {})
        if pumpswap and pumpswap.get("candidate_count", 0) > 0:
            return "B/C. Prioritize Pump.fun birth/new-launch feed and keep PumpSwap as a separate post-migration observation lane."
        return "B. Prioritize a birth/new-launch feed before scaling."
    if readiness == "forward_50_needs_duplicate_repair":
        return "E. Repair dedup/source-transition handling before scaling."
    if readiness == "forward_50_needs_fdv_proxy_repair":
        return "D. Repair FDV proxy before scaling."
    return "G. Stop and review manually."


def _answer_questions(source_rows: list[dict[str, Any]], freshness: Counter[str], actionability: Counter[str]) -> dict[str, str]:
    pumpfun = next((row for row in source_rows if row["source_adapter"] == "helius_program_logs_pumpfun"), {})
    pumpswap = next((row for row in source_rows if row["source_adapter"] == "helius_program_logs_pumpswap"), {})
    raydium = next((row for row in source_rows if row["source_adapter"] == "helius_program_logs_raydium"), {})
    return {
        "is_pumpfun_producing_genuinely_early_candidates": "not_proven" if pumpfun.get("pre_20k_count", 0) == 0 and pumpfun.get("birth_observed_count", 0) == 0 else "partially",
        "is_pumpswap_mostly_already_active_or_post_migration": "yes" if pumpswap.get("candidate_count", 0) and pumpswap.get("pre_20k_count", 0) == 0 else "not_enough_evidence",
        "is_raydium_underrepresented": "yes_low_sample_adapter_or_market_mix_unclear" if raydium.get("candidate_count", 0) <= 1 else "no",
        "should_pumpswap_be_main_or_separate": "separate_as_post_migration_observation_lane",
        "should_raydium_be_separate_lane": "yes_until_direct_launch_coverage_is_proven",
        "overall_actionability": "not_actionability_ready" if actionability["actionable_pre_20k_observed"] == 0 and actionability["actionable_pre_10k_observed"] == 0 else "partially_actionable",
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = sorted({key for row in rows for key in row.keys()})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _write_markdown(path: Path, summary: dict[str, Any]) -> Path:
    lines = [
        "# Forward 50 Freshness Quality Audit",
        "",
        "- Guardrail: audit-only; no collection, trading, backtest, validation, or strategy work.",
        f"- Candidates audited: `{summary['candidates_audited']}`",
        f"- Current total candidate rows present: `{summary['all_current_candidate_rows_present']}`",
        f"- Source mix: `{summary['source_mix']}`",
        f"- Freshness classes: `{summary['freshness_class_distribution']}`",
        f"- Actionability classes: `{summary['actionability_class_distribution']}`",
        f"- FDV sanity: `{summary['fdv_sanity_distribution']}`",
        f"- Duplicate classes: `{summary['duplicate_class_distribution']}`",
        f"- Completeness: `{summary['data_completeness']}`",
        f"- Readiness classification: `{summary['readiness_classification']}`",
        f"- Recommendation: `{summary['recommendation']}`",
        "",
        "## Source Answers",
        "",
        *[f"- {key}: `{value}`" for key, value in summary["answer_questions"].items()],
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _rows_for(rows: list[dict[str, Any]], observation_id: str) -> list[dict[str, Any]]:
    return [row for row in rows if str(row.get("observation_id")) == observation_id]


def _first_cross_time(paths: list[dict[str, Any]], threshold: float) -> float | None:
    times = [
        _num(row.get("timestamp") or row.get("observed_at"))
        for row in paths
        if (_num(row.get("fdv_proxy")) is not None and _num(row.get("fdv_proxy")) >= threshold)
    ]
    times = [value for value in times if value is not None]
    return min(times) if times else None


def _first_non_null(rows: list[dict[str, Any]], key: str) -> Any:
    for row in rows:
        if row.get(key) not in (None, ""):
            return row.get(key)
    return None


def _num(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _gte(value: float | None, threshold: float) -> bool:
    return value is not None and value >= threshold


def _pre_observed(value: float | None, cross_time: Any, threshold: float) -> bool:
    return value is not None and value < threshold and cross_time is not None


def _delta(start: float | None, end: float | None) -> float | None:
    if start is None or end is None:
        return None
    return end - start


def _path_rows_below(paths: list[dict[str, Any]], threshold: float) -> int:
    return sum(1 for row in paths if (_num(row.get("fdv_proxy")) is not None and _num(row.get("fdv_proxy")) < threshold))


def _path_rows_between(paths: list[dict[str, Any]], low: float, high: float) -> int:
    return sum(1 for row in paths if (_num(row.get("fdv_proxy")) is not None and low <= _num(row.get("fdv_proxy")) < high))


def _median_interval(times: list[float | None]) -> float | None:
    values = sorted(value for value in times if value is not None)
    if len(values) < 2:
        return None
    return median([right - left for left, right in zip(values, values[1:])])


def _safe_median(values: list[float | None]) -> float | None:
    clean = [value for value in values if value is not None]
    return median(clean) if clean else None


def _count_crossed(paths: list[dict[str, Any]], threshold: float) -> int:
    by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in paths:
        by_id[str(row.get("observation_id"))].append(row)
    return sum(1 for rows in by_id.values() if any((_num(row.get("fdv_proxy")) or 0) >= threshold for row in rows))


def _extreme_jump_count(fdvs: list[float]) -> int:
    count = 0
    for left, right in zip(fdvs, fdvs[1:]):
        if left > 0 and right / left >= 100:
            count += 1
    return count


def _monotonicity(fdvs: list[float]) -> str:
    if len(fdvs) < 2:
        return "single_point_path"
    if all(right >= left for left, right in zip(fdvs, fdvs[1:])):
        return "non_decreasing"
    return "mixed_path"


def _coverage(rows: list[dict[str, Any]]) -> dict[str, float]:
    total = max(1, len(rows))
    fields = [
        "has_path_rows",
        "has_event_rows",
        "has_metadata_rows",
        "has_holder_rows",
        "has_drawdown_rows",
        "has_raw_source_rows",
        "has_fdv_proxy",
        "has_active_wallets",
        "has_buy_sell_counts",
    ]
    return {field: round(sum(1 for row in rows if row.get(field)) / total, 4) for field in fields}
