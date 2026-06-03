"""Forward efficient-mover observation logger.

Observation-only framework for collecting high-resolution forward rows when a
read-only source reports tokens crossing fixed FDV/valuation-proxy levels.
This module does not contain wallet execution, order routing, paper/live
trading, validation, backtests, or strategy logic.
"""

from __future__ import annotations

import json
import os
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from research.mtp_research.data_paths import data_lake_root


REPORT_ID = "forward_efficient_mover_observer_v0"
TARGET_MILESTONES = (50, 100, 300, 500)
VALUATION_LEVELS = {
    "10k": 10_000.0,
    "15k": 15_000.0,
    "20k": 20_000.0,
    "30k": 30_000.0,
    "50k": 50_000.0,
    "100k": 100_000.0,
    "200k": 200_000.0,
    "500k": 500_000.0,
    "1m": 1_000_000.0,
}
OUTPUT_FILES = {
    "candidates": "candidates.jsonl",
    "paths": "candidate_paths.jsonl",
    "events": "candidate_events.jsonl",
    "metadata": "candidate_metadata.jsonl",
    "holders": "candidate_holders.jsonl",
    "drawdowns": "candidate_drawdowns.jsonl",
    "checkpoint": "checkpoint.json",
    "status": "status.json",
}
METHODOLOGY_FLAGS = [
    "forward_observation_only",
    "not_paper_trading",
    "not_live_trading",
    "not_a_trading_bot",
    "no_validation",
    "no_backtest",
    "no_auto_buy_sell",
    "no_private_key_logic",
    "no_wallet_execution",
    "no_order_routing",
    "no_strategy_generation",
    "no_threshold_optimization",
    "no_grid_search",
    "no_ml_black_boxes",
    "fdv_proxy_not_true_market_cap",
    "fixed_trigger_levels_not_optimized",
]


class CandidateSource(Protocol):
    source_name: str

    def availability(self) -> dict[str, Any]:
        ...

    def fetch_candidates(self) -> list[dict[str, Any]]:
        ...


@dataclass
class ForwardObserverConfig:
    mode: str = "dry-run"
    data_root: Path | str | None = None
    target_candidates: int = 300
    start_trigger: float = 10_000.0
    poll_seconds: float = 2.0
    status_interval_seconds: int = 30
    max_runtime_minutes: int = 240
    max_api_calls: int = 100_000
    max_helius_credits: int | None = None
    max_dexscreener_calls: int = 10_000
    max_active_watches: int = 50
    metadata_refresh_interval_seconds: int = 60
    holder_refresh_interval_seconds: int = 30
    max_observation_duration_minutes: int = 60
    inactive_timeout_minutes: int = 10
    floor_pct_below_trigger: float = 50.0
    max_observe_iterations: int | None = None
    source: str = "auto"
    local_source_path: Path | str | None = None

    @property
    def root(self) -> Path:
        raw_root = self.data_root
        if raw_root is None:
            raw_root = os.environ.get("MEMETRADER_DATA_ROOT") or data_lake_root()
        return Path(raw_root).expanduser()

    @property
    def observation_root(self) -> Path:
        return self.root / "data" / "forward_observation" / "efficient_movers"

    @property
    def raw_root(self) -> Path:
        return self.root / "data" / "raw" / "forward_observation" / "efficient_movers"

    @property
    def report_root(self) -> Path:
        return self.root / "data" / "backtests" / "diagnostics" / "reports" / "forward_observation" / "efficient_movers"


class MockCandidateSource:
    source_name = "mock"

    def __init__(self, candidates: list[dict[str, Any]] | None = None) -> None:
        self.candidates = candidates or [
            {
                "mint": "mock-mint-efficient-mover",
                "token_symbol": "MOCK",
                "fdv_proxy": 25_000,
                "event_count": 4,
                "buy_count": 3,
                "sell_count": 1,
                "active_wallets": 3,
                "source": "mock",
            }
        ]

    def availability(self) -> dict[str, Any]:
        return {"source": self.source_name, "available": True, "read_only": True, "network_calls": 0}

    def fetch_candidates(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self.candidates]


class LocalJsonlCandidateSource:
    source_name = "local_jsonl"

    def __init__(self, path: Path | str | None) -> None:
        self.path = Path(path).expanduser() if path else None

    def availability(self) -> dict[str, Any]:
        exists = bool(self.path and self.path.exists())
        return {"source": self.source_name, "available": exists, "read_only": True, "path": str(self.path) if self.path else None}

    def fetch_candidates(self) -> list[dict[str, Any]]:
        if not self.path or not self.path.exists():
            return []
        return list(read_jsonl(self.path))


class PlaceholderReadOnlySource:
    def __init__(self, source_name: str) -> None:
        self.source_name = source_name

    def availability(self) -> dict[str, Any]:
        return {
            "source": self.source_name,
            "available": False,
            "read_only": True,
            "missing_reason": "source_adapter_placeholder_needs_api_or_feed_config",
        }

    def fetch_candidates(self) -> list[dict[str, Any]]:
        return []


def run_dry_run(config: ForwardObserverConfig) -> dict[str, Any]:
    ensure_dirs(config)
    source_reports = source_availability_reports(config)
    report = {
        "report_id": REPORT_ID,
        "mode": "dry-run",
        "created_at": utc_now_iso(),
        "methodology_flags": METHODOLOGY_FLAGS,
        "guardrails": guardrails(),
        "readiness_classification": "forward_observer_ready_for_dry_run",
        "observation_root": str(config.observation_root),
        "raw_root": str(config.raw_root),
        "report_root": str(config.report_root),
        "source_availability": source_reports,
        "target_candidates": config.target_candidates,
        "start_trigger": config.start_trigger,
        "poll_seconds": config.poll_seconds,
        "status_interval_seconds": config.status_interval_seconds,
        "max_runtime_minutes": config.max_runtime_minutes,
        "output_files": output_paths(config),
        "observation_readiness": observation_readiness(source_reports),
        "network_calls_made": 0,
        "next_step": "configure_live_read_only_candidate_source_or_run_mock_observe_for_schema_check",
    }
    write_status_files(config, report)
    return report


def run_observe(config: ForwardObserverConfig, *, source: CandidateSource | None = None) -> dict[str, Any]:
    ensure_dirs(config)
    selected_source = source or build_source(config)
    availability = selected_source.availability()
    checkpoint = read_checkpoint(config.observation_root / OUTPUT_FILES["checkpoint"])
    seen_mints = set(checkpoint.get("seen_mints", []))
    start_time = time.monotonic()
    total_api_calls = int(checkpoint.get("api_calls_used", 0))
    latest_mint = None
    warnings: list[str] = []
    iterations = 0
    if not availability.get("available"):
        warnings.append("candidate_source_unavailable_no_observation_rows_written")
    while availability.get("available"):
        if config.max_observe_iterations is not None and iterations >= config.max_observe_iterations:
            break
        if elapsed_minutes(start_time) >= config.max_runtime_minutes:
            warnings.append("max_runtime_minutes_reached")
            break
        if total_api_calls >= config.max_api_calls:
            warnings.append("max_api_calls_reached")
            break
        candidates = selected_source.fetch_candidates()
        total_api_calls += 1
        for candidate in candidates:
            fdv = safe_float(candidate.get("fdv_proxy"))
            mint = str(candidate.get("mint") or candidate.get("token_mint") or "")
            if not mint or fdv is None or fdv < config.start_trigger or mint in seen_mints:
                continue
            observation_id = make_observation_id(mint)
            observed_at = int(time.time())
            rows = build_observation_rows(candidate, start_trigger=config.start_trigger, observation_id=observation_id, observed_at=observed_at)
            append_jsonl(config.observation_root / OUTPUT_FILES["candidates"], [rows["candidate"]])
            append_jsonl(config.observation_root / OUTPUT_FILES["paths"], [rows["path"]])
            append_jsonl(config.observation_root / OUTPUT_FILES["events"], rows["events"])
            append_jsonl(config.observation_root / OUTPUT_FILES["metadata"], [rows["metadata"]])
            append_jsonl(config.observation_root / OUTPUT_FILES["holders"], [rows["holders"]])
            append_jsonl(config.observation_root / OUTPUT_FILES["drawdowns"], [rows["drawdown"]])
            append_jsonl(config.raw_root / "source_candidates.jsonl", [{**candidate, "observed_at": observed_at, "observation_id": observation_id}])
            seen_mints.add(mint)
            latest_mint = mint
        iterations += 1
        if config.max_observe_iterations is None:
            time.sleep(max(0.0, config.poll_seconds))
    checkpoint_payload = {
        "updated_at": utc_now_iso(),
        "seen_mints": sorted(seen_mints),
        "api_calls_used": total_api_calls,
        "source": availability,
        "warnings": warnings,
    }
    write_checkpoint(config.observation_root / OUTPUT_FILES["checkpoint"], checkpoint_payload)
    tally = calculate_status_tally(config.observation_root, target_candidates=config.target_candidates)
    tally.update(
        {
            "report_id": REPORT_ID,
            "mode": "observe",
            "latest_observed_candidate": latest_mint or tally.get("latest_observed_candidate"),
            "warnings": warnings,
            "output_path": str(config.observation_root),
            "readiness_classification": "forward_observer_ready_for_observation" if availability.get("available") else "forward_observer_needs_source_config",
        }
    )
    write_status_files(config, tally)
    return tally


def run_status(config: ForwardObserverConfig) -> dict[str, Any]:
    ensure_dirs(config)
    tally = calculate_status_tally(config.observation_root, target_candidates=config.target_candidates)
    tally.update(
        {
            "report_id": REPORT_ID,
            "mode": "status",
            "methodology_flags": METHODOLOGY_FLAGS,
            "guardrails": guardrails(),
            "observation_root": str(config.observation_root),
            "report_root": str(config.report_root),
            "output_files": output_paths(config),
        }
    )
    write_status_files(config, tally)
    return tally


def build_observation_rows(candidate: dict[str, Any], *, start_trigger: float, observation_id: str, observed_at: int) -> dict[str, Any]:
    mint = str(candidate.get("mint") or candidate.get("token_mint"))
    fdv = safe_float(candidate.get("fdv_proxy")) or 0.0
    events = safe_float(candidate.get("event_count")) or 0.0
    buys = safe_float(candidate.get("buy_count")) or 0.0
    sells = safe_float(candidate.get("sell_count")) or 0.0
    active_wallets = safe_float(candidate.get("active_wallets")) or 0.0
    trigger_level = trigger_label(fdv)
    base = {
        "observation_id": observation_id,
        "mint": mint,
        "token_mint": mint,
        "source": candidate.get("source", "unknown"),
        "observed_at": observed_at,
    }
    candidate_row = {
        **base,
        "launch_id": candidate.get("launch_id"),
        "creator": candidate.get("creator") or candidate.get("deployer"),
        "launch_time": candidate.get("launch_time"),
        "first_seen_time": observed_at,
        "token_name": candidate.get("token_name"),
        "token_symbol": candidate.get("token_symbol"),
        "start_trigger": start_trigger,
        "trigger_level": trigger_level,
        "trigger_timestamp": observed_at,
        "status": "active",
        "candidate_classification": "efficient_mover_candidate_observed",
    }
    path_row = {
        **base,
        "timestamp": observed_at,
        "slot": candidate.get("slot"),
        "block_time": candidate.get("block_time"),
        "fdv_proxy": fdv,
        "price_proxy": candidate.get("price_proxy"),
        "liquidity_proxy": candidate.get("liquidity_proxy"),
        "event_count": events,
        "buy_count": buys,
        "sell_count": sells,
        "active_wallets": active_wallets,
        "holder_count": candidate.get("holder_count"),
        "fdv_per_event": ratio(fdv, events),
        "fdv_per_buy": ratio(fdv, buys),
        "fdv_per_active_wallet": ratio(fdv, active_wallets),
        "buy_sell_ratio": ratio(buys, sells),
        **crossed_fields(fdv),
    }
    metadata_row = {
        **base,
        "token_name": candidate.get("token_name"),
        "token_symbol": candidate.get("token_symbol"),
        "metadata_uri": candidate.get("metadata_uri"),
        "image_uri": candidate.get("image_uri"),
        "description": candidate.get("description"),
        "website_url": candidate.get("website_url"),
        "twitter_x_url": candidate.get("twitter_x_url"),
        "telegram_url": candidate.get("telegram_url"),
        "discord_url": candidate.get("discord_url"),
        "metadata_completeness_score": metadata_completeness(candidate),
        "metadata_source": candidate.get("metadata_source", candidate.get("source", "unknown")),
        "metadata_observed_at": observed_at,
    }
    holder_row = {
        **base,
        "timestamp": observed_at,
        "holder_count": candidate.get("holder_count"),
        "top_holder_share_proxy": candidate.get("top_holder_share_proxy"),
        "top_10_holder_share_proxy": candidate.get("top_10_holder_share_proxy"),
        "top_holder_addresses": candidate.get("top_holder_addresses"),
        "top_10_holder_addresses": candidate.get("top_10_holder_addresses"),
        "creator_holder_share": candidate.get("creator_holder_share"),
        "holder_snapshot_source": candidate.get("holder_snapshot_source", "not_available_in_current_source"),
    }
    drawdown_row = {
        **base,
        "timestamp": observed_at,
        "current_local_high_fdv": fdv,
        "current_drawdown_pct_from_local_high": 0.0,
        "first_20pct_drawdown_time": None,
        "first_30pct_drawdown_time": None,
        "first_40pct_drawdown_time": None,
        "first_50pct_drawdown_time": None,
        "reclaim_prior_high_time": None,
        "new_high_after_drawdown_time": None,
        "bounce_pct_30s": None,
        "bounce_pct_60s": None,
        "bounce_pct_2m": None,
        "bounce_pct_5m": None,
        "no_reclaim_after_5m": False,
        "no_reclaim_after_10m": False,
    }
    event_row = {
        **base,
        "timestamp": observed_at,
        "wallet_address": candidate.get("wallet_address"),
        "transaction_signature": candidate.get("transaction_signature"),
        "transaction_slot": candidate.get("slot"),
        "transaction_time": candidate.get("block_time", observed_at),
        "buy_size": candidate.get("buy_size"),
        "sell_size": candidate.get("sell_size"),
        "cumulative_buy_amount": candidate.get("cumulative_buy_amount"),
        "cumulative_sell_amount": candidate.get("cumulative_sell_amount"),
        "net_flow": candidate.get("net_flow"),
        "early_buyer_list": candidate.get("early_buyer_list"),
        "first_5_buyers": candidate.get("first_5_buyers"),
        "first_10_buyers": candidate.get("first_10_buyers"),
        "first_20_buyers": candidate.get("first_20_buyers"),
    }
    return {"candidate": candidate_row, "path": path_row, "events": [event_row], "metadata": metadata_row, "holders": holder_row, "drawdown": drawdown_row}


def calculate_status_tally(observation_root: Path | str, *, target_candidates: int = 300) -> dict[str, Any]:
    root = Path(observation_root)
    candidates = list(read_jsonl(root / OUTPUT_FILES["candidates"]))
    paths = list(read_jsonl(root / OUTPUT_FILES["paths"]))
    drawdowns = list(read_jsonl(root / OUTPUT_FILES["drawdowns"]))
    metadata = list(read_jsonl(root / OUTPUT_FILES["metadata"]))
    holders = list(read_jsonl(root / OUTPUT_FILES["holders"]))
    events = list(read_jsonl(root / OUTPUT_FILES["events"]))
    total = len(unique_by(candidates, "observation_id"))
    active = sum(1 for row in candidates if row.get("status") == "active")
    completed = sum(1 for row in candidates if row.get("status") == "completed")
    first_time = min([row.get("observed_at") or row.get("first_seen_time") for row in candidates if row.get("observed_at") or row.get("first_seen_time")] or [None])
    latest_time = max([row.get("observed_at") or row.get("timestamp") for row in paths + candidates if row.get("observed_at") or row.get("timestamp")] or [None])
    latest_candidate = (candidates[-1].get("mint") if candidates else None)
    tally = {
        "first_observation_time": first_time,
        "latest_observation_time": latest_time,
        "total_candidates_observed": total,
        "active_candidates_currently_watched": active,
        "completed_candidates": completed,
        "candidates_by_start_trigger": dict(Counter(str(row.get("start_trigger")) for row in candidates if row.get("start_trigger") is not None)),
        "candidates_by_trigger_level": dict(Counter(str(row.get("trigger_level")) for row in candidates if row.get("trigger_level") is not None)),
        "latest_observed_candidate": latest_candidate,
        "candidates_that_reached_20k": count_crossed(paths, "crossed_20k"),
        "candidates_that_reached_50k": count_crossed(paths, "crossed_50k"),
        "candidates_that_reached_100k": count_crossed(paths, "crossed_100k"),
        "candidates_that_reached_500k": count_crossed(paths, "crossed_500k"),
        "candidates_that_reached_1m": count_crossed(paths, "crossed_1m"),
        "candidates_with_20pct_drawdown": count_non_null(drawdowns, "first_20pct_drawdown_time"),
        "candidates_with_30pct_drawdown": count_non_null(drawdowns, "first_30pct_drawdown_time"),
        "candidates_with_recoveries_after_30pct_drawdown": count_non_null(drawdowns, "reclaim_prior_high_time"),
        "candidates_with_no_reclaim_after_5m": sum(1 for row in drawdowns if row.get("no_reclaim_after_5m") is True),
        "metadata_snapshots_collected": len(metadata),
        "holder_snapshots_collected": len(holders),
        "event_rows_collected": len(events),
        "current_target_sample_size": target_candidates,
        "remaining_until_target": max(0, target_candidates - total),
        "sample_milestones_reached": [milestone for milestone in TARGET_MILESTONES if total >= milestone],
        "target_reached": total >= target_candidates,
        "data_files_written": {key: str(root / name) for key, name in OUTPUT_FILES.items()},
        "recommended_stop_review_flag": recommend_stop_review(total, target_candidates),
    }
    return tally


def source_availability_reports(config: ForwardObserverConfig) -> list[dict[str, Any]]:
    return [
        PlaceholderReadOnlySource("pumpfun_pumpswap_feed").availability(),
        PlaceholderReadOnlySource("dexscreener_latest_pairs").availability(),
        PlaceholderReadOnlySource("helius_read_only_monitor").availability(),
        LocalJsonlCandidateSource(config.local_source_path).availability(),
        MockCandidateSource().availability(),
    ]


def build_source(config: ForwardObserverConfig) -> CandidateSource:
    if config.source == "mock":
        return MockCandidateSource()
    if config.source == "local":
        return LocalJsonlCandidateSource(config.local_source_path)
    return PlaceholderReadOnlySource("auto_unconfigured_live_source")


def observation_readiness(source_reports: list[dict[str, Any]]) -> str:
    live = [row for row in source_reports if row["source"] != "mock" and row.get("available")]
    if live:
        return "forward_observer_ready_for_observation"
    return "forward_observer_needs_source_config"


def ensure_dirs(config: ForwardObserverConfig) -> None:
    config.observation_root.mkdir(parents=True, exist_ok=True)
    config.raw_root.mkdir(parents=True, exist_ok=True)
    config.report_root.mkdir(parents=True, exist_ok=True)


def write_status_files(config: ForwardObserverConfig, payload: dict[str, Any]) -> None:
    (config.observation_root / OUTPUT_FILES["status"]).write_text(json.dumps(payload, indent=2, sort_keys=True, default=json_default), encoding="utf-8")
    (config.report_root / "forward_observation_status.md").write_text(status_markdown(payload), encoding="utf-8")


def status_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Forward Efficient Mover Observation Status",
        "",
        f"- Mode: `{payload.get('mode')}`",
        f"- Readiness: `{payload.get('readiness_classification') or payload.get('observation_readiness')}`",
        f"- Total candidates observed: `{payload.get('total_candidates_observed', 0)}` / `{payload.get('current_target_sample_size') or payload.get('target_candidates')}` target",
        f"- Active watches: `{payload.get('active_candidates_currently_watched', 0)}`",
        f"- Completed: `{payload.get('completed_candidates', 0)}`",
        f"- Reached 20k: `{payload.get('candidates_that_reached_20k', 0)}`",
        f"- Reached 50k: `{payload.get('candidates_that_reached_50k', 0)}`",
        f"- Reached 100k: `{payload.get('candidates_that_reached_100k', 0)}`",
        f"- Reached 500k: `{payload.get('candidates_that_reached_500k', 0)}`",
        f"- Reached 1m: `{payload.get('candidates_that_reached_1m', 0)}`",
        f"- 30pct drawdowns: `{payload.get('candidates_with_30pct_drawdown', 0)}`",
        f"- 30pct drawdown recoveries: `{payload.get('candidates_with_recoveries_after_30pct_drawdown', 0)}`",
        f"- No-reclaim after 5m: `{payload.get('candidates_with_no_reclaim_after_5m', 0)}`",
        f"- Metadata snapshots: `{payload.get('metadata_snapshots_collected', 0)}`",
        f"- Holder snapshots: `{payload.get('holder_snapshots_collected', 0)}`",
        f"- Event rows: `{payload.get('event_rows_collected', 0)}`",
        f"- Recommendation: `{payload.get('recommended_stop_review_flag') or payload.get('next_step')}`",
        "",
        "Observation only. No paper/live trading, wallet execution, order routing, validation, backtest, alerts, or strategy logic.",
    ]
    return "\n".join(lines) + "\n"


def append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, default=json_default) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def write_checkpoint(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=json_default), encoding="utf-8")


def read_checkpoint(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def output_paths(config: ForwardObserverConfig) -> dict[str, str]:
    return {key: str(config.observation_root / name) for key, name in OUTPUT_FILES.items()}


def print_status(tally: dict[str, Any]) -> str:
    return "\n".join(
        [
            "## Forward Efficient Mover Observation Status",
            "",
            f"Observation root: {tally.get('observation_root') or tally.get('output_path')}",
            f"First observation time: {tally.get('first_observation_time')}",
            f"Latest observation time: {tally.get('latest_observation_time')}",
            f"Total candidates observed: {tally.get('total_candidates_observed', 0)} / {tally.get('current_target_sample_size', 0)} target",
            f"Active watches: {tally.get('active_candidates_currently_watched', 0)}",
            f"Completed: {tally.get('completed_candidates', 0)}",
            f"By start trigger: {tally.get('candidates_by_start_trigger', {})}",
            f"By trigger level: {tally.get('candidates_by_trigger_level', {})}",
            f"Reached 20k: {tally.get('candidates_that_reached_20k', 0)}",
            f"Reached 50k: {tally.get('candidates_that_reached_50k', 0)}",
            f"Reached 100k: {tally.get('candidates_that_reached_100k', 0)}",
            f"Reached 500k: {tally.get('candidates_that_reached_500k', 0)}",
            f"Reached 1m: {tally.get('candidates_that_reached_1m', 0)}",
            f"20% drawdowns: {tally.get('candidates_with_20pct_drawdown', 0)}",
            f"30% drawdowns: {tally.get('candidates_with_30pct_drawdown', 0)}",
            f"30% drawdown recoveries: {tally.get('candidates_with_recoveries_after_30pct_drawdown', 0)}",
            f"No-reclaim after 5m: {tally.get('candidates_with_no_reclaim_after_5m', 0)}",
            f"Metadata snapshots: {tally.get('metadata_snapshots_collected', 0)}",
            f"Holder snapshots: {tally.get('holder_snapshots_collected', 0)}",
            f"Event rows: {tally.get('event_rows_collected', 0)}",
            f"Target reached: {tally.get('target_reached', False)}",
            f"Remaining until target: {tally.get('remaining_until_target', 0)}",
            f"Stop/review flag: {tally.get('recommended_stop_review_flag')}",
        ]
    )


def guardrails() -> dict[str, Any]:
    return {
        "private_key_logic": False,
        "wallet_execution": False,
        "order_routing": False,
        "paper_trading": False,
        "live_trading": False,
        "validation": False,
        "backtest": False,
        "strategy_generation": False,
        "threshold_optimization": False,
        "ml": False,
        "alerts": False,
    }


def crossed_fields(fdv: float) -> dict[str, bool]:
    return {f"crossed_{label}": fdv >= value for label, value in VALUATION_LEVELS.items()}


def trigger_label(fdv: float) -> str | None:
    crossed = [label for label, value in VALUATION_LEVELS.items() if fdv >= value]
    return crossed[-1] if crossed else None


def metadata_completeness(candidate: dict[str, Any]) -> int:
    fields = ["token_name", "token_symbol", "metadata_uri", "image_uri", "website_url", "twitter_x_url", "telegram_url", "discord_url"]
    return sum(1 for field in fields if candidate.get(field))


def count_crossed(rows: list[dict[str, Any]], field: str) -> int:
    return len({row.get("observation_id") for row in rows if row.get(field) is True and row.get("observation_id")})


def count_non_null(rows: list[dict[str, Any]], field: str) -> int:
    return len({row.get("observation_id") for row in rows if row.get(field) not in {None, ""} and row.get("observation_id")})


def unique_by(rows: list[dict[str, Any]], field: str) -> dict[Any, dict[str, Any]]:
    result = {}
    for row in rows:
        key = row.get(field)
        if key is not None:
            result[key] = row
    return result


def recommend_stop_review(total: int, target: int) -> str:
    if total >= target:
        return "target_reached_review_before_continuing"
    if total >= 500:
        return "stronger_review_milestone_reached"
    if total >= 300:
        return "meaningful_review_milestone_reached"
    if total >= 100:
        return "early_pattern_review_milestone_reached"
    if total >= 50:
        return "sanity_check_milestone_reached"
    return "continue_collecting_until_50_candidate_sanity_check"


def make_observation_id(mint: str) -> str:
    return f"fem-{mint[:12]}-{int(time.time() * 1000)}"


def ratio(num: float, den: float) -> float | None:
    if den == 0:
        return None
    return round(num / den, 8)


def safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def elapsed_minutes(start_time: float) -> float:
    return (time.monotonic() - start_time) / 60


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    return str(value)
