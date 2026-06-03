"""Forward efficient-mover observation logger.

Observation-only framework for collecting high-resolution forward rows when a
read-only source reports tokens crossing fixed FDV/valuation-proxy levels.
This module does not contain wallet execution, order routing, paper/live
trading, validation, backtests, or strategy logic.
"""

from __future__ import annotations

import json
import os
import socket
import ssl
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Protocol
from urllib import request as urllib_request
from urllib.parse import parse_qsl, urlparse, urlunparse

from research.mtp_research.data_paths import data_lake_root
from research.mtp_research.ingestion.helius_backfill import _load_project_dotenv_if_needed
from research.mtp_research.ingestion.pumpfun_create_scan_report import write_pumpfun_create_scan_report
from research.mtp_research.ingestion.pumpfun_create_scanner import PumpFunCreateScanner
from research.mtp_research.ingestion.pumpfun_create_scanner_models import PumpFunCreateCandidate
from research.mtp_research.ingestion.raw_transaction_store import RawTransactionRecord
from research.mtp_research.ingestion.solana_transaction_parser import summarize_raw_transaction


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
RAW_SOURCE_FILES = {
    "helius_ws": "helius_ws_raw.jsonl",
    "helius_rpc": "helius_rpc_raw.jsonl",
    "dexscreener": "dexscreener_raw.jsonl",
    "helius_program_probe": "helius_program_probe_raw.jsonl",
}
LIVE_READINESS_JSON = "live_source_readiness.json"
LIVE_READINESS_MD = "live_source_readiness.md"
PUMP_FUN_PROGRAM_ID = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
PUMPSWAP_PROGRAM_ID = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
RAYDIUM_LAUNCHLAB_PROGRAM_ID = "LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj"
RAYDIUM_CPMM_PROGRAM_ID = "CPMMoo8L3F4NbTegBCKVNuxFYvWzqMe9J1KLcXxj3xV"
PUMPFUN_CREATE_V2_DISCRIMINATOR_HEX = "d6904cec5f8b31b4"
SOL_MINT = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
USDT_MINT = "Es9vMFrzaCERmJfrF4H2FYD4FJTPri1BLRGKkzFTFHL"
USD1_MINT = "USD1ttGY1N17NEEHLmELoaybftRBUSErhqYiQzvEmuB"
QUOTE_MINTS = {SOL_MINT, USDC_MINT, USDT_MINT, USD1_MINT}
LIVE_EVENT_SCHEMA_FIELDS = [
    "source",
    "source_adapter",
    "observation_time",
    "slot",
    "block_time",
    "signature",
    "program_id",
    "event_type",
    "mint",
    "pool_address",
    "bonding_curve",
    "associated_bonding_curve",
    "creator",
    "buyer",
    "seller",
    "wallet",
    "side",
    "sol_amount",
    "sol_usd",
    "token_amount",
    "price_proxy",
    "fdv_proxy",
    "liquidity_proxy",
    "token_name",
    "token_symbol",
    "metadata_uri",
    "event_count",
    "buy_count",
    "sell_count",
    "active_wallet_count",
    "raw_message_path",
    "parse_confidence",
    "missing_reason",
]
SUPPORTED_LIVE_EVENT_TYPES = {
    "new_launch_candidate",
    "pumpfun_create",
    "pumpfun_trade",
    "pumpswap_migration",
    "pumpswap_trade",
    "raydium_pool_create",
    "raydium_trade_or_pool_update",
    "candidate_trigger_crossed",
    "metadata_update",
    "holder_snapshot",
    "drawdown_update",
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
    max_helius_credits: int | None = 250_000
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
    perform_live_health_checks: bool = False
    enable_probed_adapters: bool = False
    enable_birth_watch_candidates: bool = False
    birth_scan_max_batches: int = 20
    birth_scan_signatures_per_batch: int = 50
    birth_scan_hydrate_limit_per_batch: int = 50
    birth_scan_target_create_candidates: int = 10
    birth_scan_max_signatures_total: int = 1_000
    birth_scan_min_confidence: str = "medium"
    birth_scan_cursor_before: str | None = None

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


@dataclass(frozen=True)
class ProgramSourceConfig:
    adapter_name: str
    program_ids: list[str]
    event_type: str
    status: str
    notes: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter_name": self.adapter_name,
            "program_ids": self.program_ids,
            "event_type": self.event_type,
            "status": self.status,
            "notes": self.notes,
        }


def default_program_configs() -> dict[str, ProgramSourceConfig]:
    return {
        "helius_program_logs_pumpfun": ProgramSourceConfig(
            adapter_name="helius_program_logs_pumpfun",
            program_ids=[PUMP_FUN_PROGRAM_ID],
            event_type="pumpfun_trade",
            status="ready",
            notes="Pump.fun program ID is repo-verified from the creation scanner.",
        ),
        "helius_program_logs_pumpswap": ProgramSourceConfig(
            adapter_name="helius_program_logs_pumpswap",
            program_ids=[PUMPSWAP_PROGRAM_ID],
            event_type="pumpswap_trade",
            status="needs_probe_verification",
            notes="Program ID exists in the discovery plan but still needs tiny-probe confirmation before full reliance.",
        ),
        "helius_program_logs_raydium": ProgramSourceConfig(
            adapter_name="helius_program_logs_raydium",
            program_ids=[RAYDIUM_LAUNCHLAB_PROGRAM_ID, RAYDIUM_CPMM_PROGRAM_ID],
            event_type="raydium_trade_or_pool_update",
            status="needs_probe_verification",
            notes="Raydium program IDs exist in the discovery plan but should stay source-readiness limited until probes confirm semantics.",
        ),
    }


@dataclass
class HeliusLiveSourceConfig:
    rpc_url: str
    ws_url: str
    rpc_endpoint_masked: str
    ws_endpoint_masked: str
    program_configs: dict[str, ProgramSourceConfig]
    raw_root: Path
    max_helius_credits: int
    source: str = "helius-all"
    adapter_enable_gate: str = "verified_only"
    timeout_sec: int = 10
    limit_per_program_poll: int = 5
    hydrate_transactions: bool = True
    valuation_supply_proxy: float = 1_000_000_000.0
    sol_usd_price: float = 1.0
    include_birth_watch_candidates: bool = False

    @classmethod
    def from_observer_config(
        cls,
        config: ForwardObserverConfig,
        *,
        load_project_dotenv: bool = True,
    ) -> "HeliusLiveSourceConfig":
        rpc_url = resolve_helius_rpc_url(load_project_dotenv=load_project_dotenv)
        ws_url = resolve_helius_ws_url(load_project_dotenv=load_project_dotenv)
        return cls(
            rpc_url=rpc_url,
            ws_url=ws_url,
            rpc_endpoint_masked=mask_helius_endpoint(rpc_url),
            ws_endpoint_masked=mask_helius_endpoint(ws_url),
            program_configs=_program_configs_for_source(config.source, enable_probed_adapters=config.enable_probed_adapters),
            raw_root=config.raw_root,
            max_helius_credits=int(config.max_helius_credits or 0),
            source=config.source,
            adapter_enable_gate="explicit_probed_adapter_enable" if config.enable_probed_adapters else "verified_only",
            sol_usd_price=resolve_forward_sol_usd_price(config.root),
            include_birth_watch_candidates=config.enable_birth_watch_candidates,
        )


class MockHeliusEventClient:
    def __init__(self, events: list[dict[str, Any]]) -> None:
        self.events = [dict(event) for event in events]
        self.requests_used = 0

    def poll_program_events(self, program_configs: dict[str, ProgramSourceConfig], *, limit: int = 5) -> list[dict[str, Any]]:
        self.requests_used += 1
        return [dict(event) for event in self.events[:limit]]


class HeliusRpcPollingClient:
    def __init__(
        self,
        rpc_url: str,
        *,
        timeout_sec: int = 10,
        rpc_post: Any | None = None,
        hydrate_transactions: bool = True,
        valuation_supply_proxy: float = 1_000_000_000.0,
        sol_usd_price: float = 1.0,
    ) -> None:
        self.rpc_url = rpc_url
        self.timeout_sec = timeout_sec
        self._rpc_post = rpc_post or _post_json_rpc
        self.hydrate_transactions = hydrate_transactions
        self.valuation_supply_proxy = valuation_supply_proxy
        self.sol_usd_price = sol_usd_price
        self.requests_used = 0
        self.seen_signatures: set[str] = set()

    def poll_program_events(self, program_configs: dict[str, ProgramSourceConfig], *, limit: int = 5) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for adapter_name, program_config in program_configs.items():
            if program_config.status != "ready":
                continue
            for program_id in program_config.program_ids:
                payload = {
                    "jsonrpc": "2.0",
                    "id": "mtp-forward-observer-get-signatures",
                    "method": "getSignaturesForAddress",
                    "params": [program_id, {"limit": max(1, min(limit, 25))}],
                }
                response = self._rpc_post(self.rpc_url, payload, self.timeout_sec)
                self.requests_used += 1
                rows = response.get("result") if isinstance(response, dict) else None
                if not isinstance(rows, list):
                    continue
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    signature = row.get("signature")
                    if signature and str(signature) in self.seen_signatures:
                        continue
                    if signature:
                        self.seen_signatures.add(str(signature))
                    if self.hydrate_transactions and signature:
                        tx = self._fetch_transaction(str(signature))
                        if tx:
                            events.append(self._normalize_hydrated_event(tx, adapter_name, program_config, program_id))
                            continue
                    events.append(
                        _signature_only_event(
                            source_adapter=adapter_name,
                            program_id=program_id,
                            signature=signature,
                            slot=row.get("slot"),
                            block_time=row.get("blockTime"),
                            event_type=program_config.event_type,
                        )
                    )
        return events

    def _fetch_transaction(self, signature: str) -> dict[str, Any]:
        payload = {
            "jsonrpc": "2.0",
            "id": "mtp-forward-observer-get-transaction",
            "method": "getTransaction",
            "params": [
                signature,
                {
                    "encoding": "jsonParsed",
                    "maxSupportedTransactionVersion": 0,
                },
            ],
        }
        response = self._rpc_post(self.rpc_url, payload, self.timeout_sec)
        self.requests_used += 1
        result = response.get("result") if isinstance(response, dict) else None
        return result if isinstance(result, dict) else {}

    def _normalize_hydrated_event(
        self,
        tx: dict[str, Any],
        adapter_name: str,
        program_config: ProgramSourceConfig,
        program_id: str,
    ) -> dict[str, Any]:
        if adapter_name == "helius_program_logs_pumpfun":
            return normalize_pumpfun_transaction_event(
                tx,
                source_adapter=adapter_name,
                program_id=program_id,
                valuation_supply_proxy=self.valuation_supply_proxy,
                sol_usd_price=self.sol_usd_price,
            )
        if adapter_name in {"helius_program_logs_pumpswap", "helius_program_logs_raydium"}:
            return normalize_amm_transaction_event(
                tx,
                source_adapter=adapter_name,
                program_id=program_id,
                event_type=program_config.event_type,
                valuation_supply_proxy=self.valuation_supply_proxy,
                sol_usd_price=self.sol_usd_price,
            )
        return _signature_only_event(
            source_adapter=adapter_name,
            program_id=program_id,
            signature=_transaction_signature(tx),
            slot=tx.get("slot"),
            block_time=tx.get("blockTime"),
            event_type=program_config.event_type,
        )


class HeliusProgramProbeClient:
    """Tiny probe client for unverified program semantics.

    This intentionally does not normalize candidates or change adapter
    readiness. It only samples signatures/transactions and summarizes direct
    program instruction shapes for human review.
    """

    def __init__(
        self,
        rpc_url: str,
        *,
        timeout_sec: int = 10,
        rpc_post: Any | None = None,
        valuation_supply_proxy: float = 1_000_000_000.0,
        sol_usd_price: float = 1.0,
    ) -> None:
        self.rpc_url = rpc_url
        self.timeout_sec = timeout_sec
        self._rpc_post = rpc_post or _post_json_rpc
        self.valuation_supply_proxy = valuation_supply_proxy
        self.sol_usd_price = sol_usd_price
        self.requests_used = 0
        self.raw_transactions: list[dict[str, Any]] = []

    def probe_programs(
        self,
        program_configs: dict[str, ProgramSourceConfig],
        *,
        limit: int = 10,
        hydrate_sample: bool = False,
    ) -> dict[str, Any]:
        signatures: list[dict[str, Any]] = []
        transactions: list[dict[str, Any]] = []
        tx_adapter_names: dict[str, str] = {}
        signatures_by_program: dict[str, list[dict[str, Any]]] = {}
        adapter_by_program_id = {
            program_id: adapter_name
            for adapter_name, program_config in program_configs.items()
            for program_id in program_config.program_ids
        }
        program_ids: list[str] = []
        for program_config in program_configs.values():
            program_ids.extend(program_config.program_ids)
            for program_id in program_config.program_ids:
                payload = {
                    "jsonrpc": "2.0",
                    "id": "mtp-forward-observer-probe-signatures",
                    "method": "getSignaturesForAddress",
                    "params": [program_id, {"limit": max(1, min(int(limit), 25))}],
                }
                response = self._rpc_post(self.rpc_url, payload, self.timeout_sec)
                self.requests_used += 1
                rows = response.get("result") if isinstance(response, dict) else None
                if isinstance(rows, list):
                    for row in rows:
                        if isinstance(row, dict):
                            signature = row.get("signature")
                            if signature:
                                tx_adapter_names[str(signature)] = adapter_by_program_id.get(program_id, "")
                            signature_row = {"program_id": program_id, **row}
                            signatures.append(signature_row)
                            signatures_by_program.setdefault(program_id, []).append(signature_row)
        if hydrate_sample:
            seen: set[str] = set()
            per_program_limit = max(1, min(int(limit), 25))
            for program_id in program_ids:
                for row in signatures_by_program.get(program_id, [])[:per_program_limit]:
                    signature = str(row.get("signature") or "")
                    if not signature or signature in seen:
                        continue
                    seen.add(signature)
                    tx = self._fetch_transaction(signature)
                    if tx:
                        transactions.append(tx)
                        self.raw_transactions.append(tx)
        instruction_rows = _extract_program_instruction_rows(transactions, set(program_ids))
        clusters = _instruction_clusters(instruction_rows)
        parsed_events = []
        for tx in transactions:
            signature = _transaction_signature(tx)
            adapter_name = tx_adapter_names.get(str(signature or ""), "")
            event = _normalize_probe_transaction_event(
                tx,
                adapter_name=adapter_name,
                program_configs=program_configs,
                valuation_supply_proxy=self.valuation_supply_proxy,
                sol_usd_price=self.sol_usd_price,
            )
            if event and event.get("mint") and event.get("fdv_proxy") is not None:
                parsed_events.append(event)
        return {
            "signatures_seen": len({str(row.get("signature")) for row in signatures if row.get("signature")}),
            "signature_rows_seen": len(signatures),
            "transactions_hydrated": len(transactions),
            "program_instruction_count": len(instruction_rows),
            "instruction_clusters": clusters,
            "example_signatures": [row.get("signature") for row in signatures[:5] if row.get("signature")],
            "parseable_event_count": len(parsed_events),
            "parsed_event_examples": parsed_events[:5],
            "candidate_rows_created": 0,
            "requests_used": self.requests_used,
        }

    def _fetch_transaction(self, signature: str) -> dict[str, Any]:
        payload = {
            "jsonrpc": "2.0",
            "id": "mtp-forward-observer-probe-transaction",
            "method": "getTransaction",
            "params": [
                signature,
                {
                    "encoding": "jsonParsed",
                    "maxSupportedTransactionVersion": 0,
                },
            ],
        }
        response = self._rpc_post(self.rpc_url, payload, self.timeout_sec)
        self.requests_used += 1
        result = response.get("result") if isinstance(response, dict) else None
        return result if isinstance(result, dict) else {}


class HeliusLiveCandidateSource:
    source_name = "helius"

    def __init__(self, config: HeliusLiveSourceConfig, client: Any | None = None) -> None:
        self.config = config
        self.client = client or HeliusRpcPollingClient(
            config.rpc_url,
            timeout_sec=config.timeout_sec,
            hydrate_transactions=config.hydrate_transactions,
            valuation_supply_proxy=config.valuation_supply_proxy,
            sol_usd_price=config.sol_usd_price,
        )

    def availability(self) -> dict[str, Any]:
        if self.config.max_helius_credits <= 0:
            return {
                "source": self.source_name,
                "available": False,
                "read_only": True,
                "missing_reason": "max_helius_credits_zero_or_negative",
                "rpc_endpoint_masked": self.config.rpc_endpoint_masked,
                "ws_endpoint_masked": self.config.ws_endpoint_masked,
                "program_adapters": {name: item.to_dict() for name, item in self.config.program_configs.items()},
                "adapter_enable_gate": self.config.adapter_enable_gate,
                "include_birth_watch_candidates": self.config.include_birth_watch_candidates,
            }
        ready = [name for name, item in self.config.program_configs.items() if item.status == "ready" and item.program_ids]
        missing = [name for name, item in self.config.program_configs.items() if item.status != "ready" or not item.program_ids]
        return {
            "source": self.source_name,
            "available": bool(ready),
            "read_only": True,
            "rpc_endpoint_masked": self.config.rpc_endpoint_masked,
            "ws_endpoint_masked": self.config.ws_endpoint_masked,
            "ready_adapters": ready,
            "missing_or_unverified_adapters": missing,
            "program_adapters": {name: item.to_dict() for name, item in self.config.program_configs.items()},
            "adapter_enable_gate": self.config.adapter_enable_gate,
            "include_birth_watch_candidates": self.config.include_birth_watch_candidates,
            "missing_reason": None if ready else "no_verified_program_ids_for_selected_helius_source",
        }

    def fetch_candidates(self) -> list[dict[str, Any]]:
        raw_events = self.client.poll_program_events(self.config.program_configs, limit=self.config.limit_per_program_poll)
        if raw_events:
            append_jsonl(self.config.raw_root / RAW_SOURCE_FILES["helius_rpc"], raw_events)
        events = [normalize_live_source_event(event) for event in raw_events]
        candidates = []
        for event in events:
            candidate = build_live_event_candidate(
                event,
                include_birth_watch_candidates=self.config.include_birth_watch_candidates,
            )
            if candidate:
                candidates.append(candidate)
        return candidates

    @property
    def requests_used(self) -> int:
        return int(getattr(self.client, "requests_used", 0))


class PumpFunCreateScannerCandidateSource:
    source_name = "helius"

    def __init__(
        self,
        config: ForwardObserverConfig,
        scanner: Any | None = None,
    ) -> None:
        self.config = config
        self.scanner = scanner or PumpFunCreateScanner()
        self.cursor_before = config.birth_scan_cursor_before
        self._requests_used = 0

    def availability(self) -> dict[str, Any]:
        rpc_url = resolve_helius_rpc_url()
        key_present = bool(resolve_helius_api_key(load_project_dotenv=False))
        projected_requests = _projected_birth_scan_requests(self.config)
        if int(self.config.max_helius_credits or 0) <= 0:
            return {
                "source": self.source_name,
                "available": False,
                "read_only": True,
                "missing_reason": "max_helius_credits_zero_or_negative",
                "source_adapter": "helius_pumpfun_create_scanner",
                "projected_requests": projected_requests,
            }
        if projected_requests > int(self.config.max_helius_credits or 0):
            return {
                "source": self.source_name,
                "available": False,
                "read_only": True,
                "missing_reason": "projected_birth_scan_requests_exceed_helius_credit_cap",
                "source_adapter": "helius_pumpfun_create_scanner",
                "projected_requests": projected_requests,
                "max_helius_credits": int(self.config.max_helius_credits or 0),
            }
        if not self.config.enable_birth_watch_candidates:
            return {
                "source": self.source_name,
                "available": False,
                "read_only": True,
                "missing_reason": "birth_watch_candidates_not_enabled",
                "source_adapter": "helius_pumpfun_create_scanner",
                "projected_requests": projected_requests,
            }
        if not rpc_url and not key_present:
            return {
                "source": self.source_name,
                "available": False,
                "read_only": True,
                "missing_reason": "live_source_blocked_no_helius_config",
                "source_adapter": "helius_pumpfun_create_scanner",
                "projected_requests": projected_requests,
            }
        return {
            "source": self.source_name,
            "available": True,
            "read_only": True,
            "source_adapter": "helius_pumpfun_create_scanner",
            "candidate_lane": "pumpfun_birth_watch",
            "include_birth_watch_candidates": self.config.enable_birth_watch_candidates,
            "projected_requests": projected_requests,
            "max_batches": self.config.birth_scan_max_batches,
            "signatures_per_batch": self.config.birth_scan_signatures_per_batch,
            "hydrate_limit_per_batch": self.config.birth_scan_hydrate_limit_per_batch,
            "target_create_candidates": self.config.birth_scan_target_create_candidates,
            "max_signatures_total": self.config.birth_scan_max_signatures_total,
            "min_confidence": self.config.birth_scan_min_confidence,
        }

    def fetch_candidates(self) -> list[dict[str, Any]]:
        report = self.scanner.scan(
            execute=True,
            max_batches=self.config.birth_scan_max_batches,
            signatures_per_batch=self.config.birth_scan_signatures_per_batch,
            hydrate_limit_per_batch=self.config.birth_scan_hydrate_limit_per_batch,
            target_create_candidates=self.config.birth_scan_target_create_candidates,
            max_signatures_total=self.config.birth_scan_max_signatures_total,
            cursor_before=self.cursor_before,
            min_confidence=self.config.birth_scan_min_confidence,
            emit_rejected_examples=False,
        )
        write_pumpfun_create_scan_report(report, self.config.report_root / "birth_watch_create_scanner")
        self._requests_used += int(report.metadata_json.get("network_calls_estimate") or 0)
        if report.batches:
            self.cursor_before = report.batches[-1].next_cursor_before
        return [
            build_birth_watch_candidate_from_create_candidate(candidate)
            for candidate in report.verified_create_candidates
            if candidate.token_mint
        ]

    @property
    def requests_used(self) -> int:
        return self._requests_used


def build_birth_watch_candidate_from_create_candidate(candidate: PumpFunCreateCandidate) -> dict[str, Any]:
    return {
        "mint": candidate.token_mint,
        "token_mint": candidate.token_mint,
        "source": "helius_program_logs_pumpfun_create_scanner",
        "event_type": "pumpfun_create",
        "fdv_proxy": None,
        "event_count": 1,
        "buy_count": 0,
        "sell_count": 0,
        "active_wallets": 1 if candidate.creator_wallet else 0,
        "slot": candidate.slot,
        "block_time": candidate.block_time,
        "transaction_signature": candidate.signature,
        "creator": candidate.creator_wallet,
        "pool_address": candidate.bonding_curve,
        "bonding_curve": candidate.bonding_curve,
        "associated_bonding_curve": candidate.associated_bonding_curve,
        "launch_time": candidate.block_time,
        "freshness_lane": "birth_watch",
        "candidate_classification": "pumpfun_birth_candidate_observed",
        "status": "watching_pre_trigger",
        "missing_reason": "pre_trigger_birth_candidate_fdv_pending",
        "parse_confidence": candidate.extraction_confidence,
        "instruction_index": candidate.instruction_index,
        "instruction_discriminator": candidate.instruction_discriminator,
        "instruction_type": candidate.metadata_json.get("instruction_type"),
        "warning_flags": candidate.warning_flags,
    }


def _projected_birth_scan_requests(config: ForwardObserverConfig) -> int:
    max_batches = max(0, int(config.birth_scan_max_batches or 0))
    hydrate_per_batch = max(
        0,
        min(
            int(config.birth_scan_signatures_per_batch or 0),
            int(config.birth_scan_hydrate_limit_per_batch or 0),
        ),
    )
    max_hydrated = min(
        max(0, int(config.birth_scan_max_signatures_total or 0)),
        max_batches * hydrate_per_batch,
    )
    return max_batches + max_hydrated


def resolve_helius_api_key(*, load_project_dotenv: bool = True) -> str | None:
    if load_project_dotenv:
        _load_project_dotenv_if_needed()
    return os.getenv("HELIUS_API_KEY")


def resolve_helius_rpc_url(*, load_project_dotenv: bool = True) -> str:
    if load_project_dotenv:
        _load_project_dotenv_if_needed()
    explicit = os.getenv("HELIUS_RPC_URL") or os.getenv("HELIUS_ENDPOINT")
    if explicit:
        return explicit
    api_key = resolve_helius_api_key(load_project_dotenv=False)
    if not api_key:
        return ""
    return f"https://mainnet.helius-rpc.com/?api-key={api_key}"


def resolve_helius_ws_url(*, load_project_dotenv: bool = True) -> str:
    if load_project_dotenv:
        _load_project_dotenv_if_needed()
    explicit = os.getenv("HELIUS_WS_URL")
    if explicit:
        return explicit
    rpc_url = resolve_helius_rpc_url(load_project_dotenv=False)
    if rpc_url.startswith("https://"):
        return "wss://" + rpc_url.removeprefix("https://")
    if rpc_url.startswith("http://"):
        return "ws://" + rpc_url.removeprefix("http://")
    api_key = resolve_helius_api_key(load_project_dotenv=False)
    if not api_key:
        return ""
    return f"wss://mainnet.helius-rpc.com/?api-key={api_key}"


def resolve_forward_sol_usd_price(root: Path | str | None = None) -> float:
    env_value = safe_float(os.getenv("MEMETRADER_FORWARD_SOL_USD_PRICE"))
    if env_value and env_value > 0:
        return env_value
    data_root = Path(root or data_lake_root()).expanduser()
    path = data_root / "data" / "normalized" / "valuation_inputs" / "sol_usd_coingecko.jsonl"
    rows = read_jsonl(path)
    for row in reversed(rows):
        value = safe_float(row.get("sol_usd"))
        if value and value > 0:
            return value
    return 1.0


def mask_helius_endpoint(endpoint: str | None) -> str:
    if not endpoint:
        return ""
    parsed = urlparse(endpoint)
    query = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        query.append((key, "***masked***" if key.lower() in {"api-key", "apikey", "key"} else value))
    masked_query = "&".join(f"{key}={value}" for key, value in query)
    return urlunparse(parsed._replace(query=masked_query))


def run_live_source_readiness(
    config: ForwardObserverConfig,
    *,
    perform_network_checks: bool = True,
    load_project_dotenv: bool = True,
) -> dict[str, Any]:
    ensure_dirs(config)
    api_key = resolve_helius_api_key(load_project_dotenv=load_project_dotenv)
    rpc_url = resolve_helius_rpc_url(load_project_dotenv=False)
    ws_url = resolve_helius_ws_url(load_project_dotenv=False)
    program_configs = _program_configs_for_source(
        config.source if config.source.startswith("helius") else "helius-all",
        enable_probed_adapters=config.enable_probed_adapters,
    )
    rpc_check = _helius_rpc_health_check(rpc_url) if perform_network_checks and rpc_url else {"status": "not_checked"}
    ws_check = _helius_ws_health_check(ws_url) if perform_network_checks and ws_url else {"status": "not_checked"}
    output_writable = _check_output_writable(config.report_root)
    ready_programs = [name for name, item in program_configs.items() if item.status == "ready" and item.program_ids]
    missing_programs = [name for name, item in program_configs.items() if item.status != "ready" or not item.program_ids]
    if not api_key and not (os.getenv("HELIUS_RPC_URL") or os.getenv("HELIUS_ENDPOINT")):
        classification = "live_source_blocked_no_helius_config"
    elif rpc_check.get("status") == "blocked" or ws_check.get("status") == "blocked":
        classification = "live_source_blocked_connection_error"
    elif missing_programs:
        classification = "live_source_partial_missing_program_ids"
    else:
        classification = "live_source_ready_for_smoke_test"
    report = {
        "report_id": "forward_efficient_mover_live_source_readiness_v0",
        "created_at": utc_now_iso(),
        "readiness_classification": classification,
        "observation_root": str(config.observation_root),
        "raw_root": str(config.raw_root),
        "report_root": str(config.report_root),
        "helius": {
            "api_key_present": bool(api_key),
            "rpc_endpoint_masked": mask_helius_endpoint(rpc_url),
            "ws_endpoint_masked": mask_helius_endpoint(ws_url),
            "rpc_health": rpc_check,
            "ws_health": ws_check,
            "max_helius_credits": int(config.max_helius_credits or 0),
            "adapter_enable_gate": "explicit_probed_adapter_enable" if config.enable_probed_adapters else "verified_only",
            "include_birth_watch_candidates": config.enable_birth_watch_candidates,
        },
        "source_adapters": {name: item.to_dict() for name, item in program_configs.items()},
        "ready_adapters": ready_programs,
        "missing_or_unverified_adapters": missing_programs,
        "dexscreener_metadata_free": {"status": "disabled", "notes": "secondary metadata enrichment only; not primary discovery"},
        "output_paths_writable": output_writable,
        "budget_caps": {
            "monthly_observation_budget_target": 5_000_000,
            "short_live_smoke_cap": 25_000,
            "default_observe_cap": int(config.max_helius_credits or 0),
        },
        "guardrails": guardrails(),
        "network_checks_performed": perform_network_checks,
    }
    _write_live_readiness_report(config, report)
    return report


def normalize_live_source_event(payload: dict[str, Any]) -> dict[str, Any]:
    event = {field: None for field in LIVE_EVENT_SCHEMA_FIELDS}
    event.update(
        {
            "source": payload.get("source") or "helius",
            "source_adapter": payload.get("source_adapter"),
            "observation_time": payload.get("observation_time") or int(time.time()),
            "slot": payload.get("slot"),
            "block_time": payload.get("block_time", payload.get("blockTime")),
            "signature": payload.get("signature"),
            "program_id": payload.get("program_id"),
            "event_type": _safe_event_type(payload.get("event_type")),
            "mint": payload.get("mint") or payload.get("token_mint"),
            "pool_address": payload.get("pool_address"),
            "bonding_curve": payload.get("bonding_curve"),
            "associated_bonding_curve": payload.get("associated_bonding_curve"),
            "creator": payload.get("creator") or payload.get("deployer"),
            "buyer": payload.get("buyer"),
            "seller": payload.get("seller"),
            "wallet": payload.get("wallet"),
            "side": payload.get("side"),
            "sol_amount": payload.get("sol_amount"),
            "sol_usd": payload.get("sol_usd"),
            "token_amount": payload.get("token_amount"),
            "price_proxy": payload.get("price_proxy"),
            "fdv_proxy": payload.get("fdv_proxy"),
            "liquidity_proxy": payload.get("liquidity_proxy"),
            "token_name": payload.get("token_name"),
            "token_symbol": payload.get("token_symbol"),
            "metadata_uri": payload.get("metadata_uri"),
            "event_count": payload.get("event_count"),
            "buy_count": payload.get("buy_count"),
            "sell_count": payload.get("sell_count"),
            "active_wallet_count": payload.get("active_wallet_count") or payload.get("active_wallets"),
            "raw_message_path": payload.get("raw_message_path"),
            "parse_confidence": payload.get("parse_confidence") or "event_payload",
            "missing_reason": payload.get("missing_reason"),
        }
    )
    if event["fdv_proxy"] is None and event["missing_reason"] is None:
        event["missing_reason"] = "fdv_proxy_unavailable"
    if event["mint"] is None and event["missing_reason"] is None:
        event["missing_reason"] = "mint_unavailable"
    return event


def normalize_pumpfun_transaction_event(
    tx: dict[str, Any],
    *,
    source_adapter: str,
    program_id: str,
    valuation_supply_proxy: float,
    sol_usd_price: float = 1.0,
) -> dict[str, Any]:
    signature = _transaction_signature(tx)
    event_type, side = _pumpfun_event_type_and_side(tx)
    if event_type == "pumpfun_create":
        create_fields = _pumpfun_create_fields(tx, program_id)
        if create_fields is None:
            return normalize_live_source_event(
                {
                    "source_adapter": source_adapter,
                    "program_id": program_id,
                    "signature": signature,
                    "slot": tx.get("slot"),
                    "block_time": tx.get("blockTime"),
                    "event_type": event_type,
                    "side": side,
                    "parse_confidence": "hydrated_pumpfun_create_layout_rejected",
                    "missing_reason": "invalid_pumpfun_create_account_layout",
                }
            )
        return normalize_live_source_event(
            {
                "source_adapter": source_adapter,
                "program_id": program_id,
                "signature": signature,
                "slot": tx.get("slot"),
                "block_time": tx.get("blockTime"),
                "event_type": event_type,
                "mint": create_fields["mint"],
                "pool_address": create_fields["bonding_curve"],
                "bonding_curve": create_fields["bonding_curve"],
                "associated_bonding_curve": create_fields["associated_bonding_curve"],
                "creator": create_fields["creator"],
                "side": side,
                "event_count": 1,
                "buy_count": 0,
                "sell_count": 0,
                "active_wallet_count": 1 if create_fields.get("creator") else 0,
                "parse_confidence": "hydrated_pumpfun_create_layout",
                "missing_reason": "pre_trigger_birth_candidate_fdv_pending",
            }
        )
    summary = summarize_raw_transaction(
        RawTransactionRecord(
            signature=signature or "",
            slot=tx.get("slot"),
            block_time=tx.get("blockTime"),
            success=(tx.get("meta") or {}).get("err") is None,
            address=program_id,
            role="forward_efficient_mover_observer",
            raw_json=tx,
            source="helius_rpc",
        )
    )
    token_delta = _primary_token_delta(summary.token_balance_deltas)
    sol_delta = _primary_native_delta_sol(summary.native_balance_deltas)
    if token_delta is None or sol_delta is None:
        return normalize_live_source_event(
            {
                "source_adapter": source_adapter,
                "program_id": program_id,
                "signature": signature,
                "slot": tx.get("slot"),
                "block_time": tx.get("blockTime"),
                "event_type": event_type,
                "side": side,
                "parse_confidence": "hydrated_transaction_missing_price_inputs",
                "missing_reason": "missing_token_or_native_delta_for_fdv_proxy",
            }
        )
    token_amount = abs(float(token_delta.delta or 0.0))
    sol_amount = abs(float(sol_delta.delta_sol or 0.0))
    if token_amount <= 0 or sol_amount <= 0:
        return normalize_live_source_event(
            {
                "source_adapter": source_adapter,
                "program_id": program_id,
                "signature": signature,
                "slot": tx.get("slot"),
                "block_time": tx.get("blockTime"),
                "event_type": event_type,
                "side": side,
                "parse_confidence": "hydrated_transaction_zero_delta",
                "missing_reason": "zero_token_or_native_delta_for_fdv_proxy",
            }
        )
    price_proxy = sol_amount / token_amount
    fdv_proxy = price_proxy * float(valuation_supply_proxy) * max(float(sol_usd_price or 1.0), 1.0)
    wallet = token_delta.owner or token_delta.account
    return normalize_live_source_event(
        {
            "source_adapter": source_adapter,
            "program_id": program_id,
            "signature": signature,
            "slot": tx.get("slot"),
            "block_time": tx.get("blockTime"),
            "event_type": event_type,
            "mint": token_delta.mint,
            "buyer": wallet if side == "buy" else None,
            "seller": wallet if side == "sell" else None,
            "wallet": wallet,
            "side": side,
            "sol_amount": round(sol_amount, 12),
            "sol_usd": round(float(sol_usd_price or 1.0), 8),
            "token_amount": round(token_amount, 12),
            "price_proxy": round(price_proxy, 12),
            "fdv_proxy": round(fdv_proxy, 6),
            "event_count": 1,
            "buy_count": 1 if side == "buy" else 0,
            "sell_count": 1 if side == "sell" else 0,
            "active_wallet_count": 1 if wallet else 0,
            "parse_confidence": "hydrated_transaction_token_native_delta",
            "missing_reason": None,
        }
    )


def normalize_amm_transaction_event(
    tx: dict[str, Any],
    *,
    source_adapter: str,
    program_id: str,
    event_type: str,
    valuation_supply_proxy: float,
    sol_usd_price: float = 1.0,
) -> dict[str, Any]:
    signature = _transaction_signature(tx)
    summary = summarize_raw_transaction(
        RawTransactionRecord(
            signature=signature or "",
            slot=tx.get("slot"),
            block_time=tx.get("blockTime"),
            success=(tx.get("meta") or {}).get("err") is None,
            address=program_id,
            role="forward_efficient_mover_observer",
            raw_json=tx,
            source="helius_rpc",
        )
    )
    pair = _single_amm_token_quote_pair(
        summary.token_balance_deltas,
        native_deltas=summary.native_balance_deltas,
        signer_pubkeys=_signer_pubkeys(tx),
        side_hint=_single_direction_side_hint(tx),
    )
    if pair is None:
        return normalize_live_source_event(
            {
                "source_adapter": source_adapter,
                "program_id": program_id,
                "signature": signature,
                "slot": tx.get("slot"),
                "block_time": tx.get("blockTime"),
                "event_type": event_type,
                "pool_address": _program_pool_address(tx, program_id),
                "parse_confidence": "hydrated_amm_ambiguous_token_quote_delta",
                "missing_reason": "ambiguous_amm_token_or_quote_delta",
            }
        )
    token_delta, quote_delta = pair
    token_amount = abs(float(token_delta.delta or 0.0))
    quote_amount = abs(float(quote_delta.delta or 0.0))
    if token_amount <= 0 or quote_amount <= 0:
        return normalize_live_source_event(
            {
                "source_adapter": source_adapter,
                "program_id": program_id,
                "signature": signature,
                "slot": tx.get("slot"),
                "block_time": tx.get("blockTime"),
                "event_type": event_type,
                "pool_address": _program_pool_address(tx, program_id),
                "parse_confidence": "hydrated_amm_zero_delta",
                "missing_reason": "zero_token_or_quote_delta_for_fdv_proxy",
            }
        )
    quote_usd = float(sol_usd_price or 1.0) if quote_delta.mint == SOL_MINT else 1.0
    price_proxy = quote_amount / token_amount
    fdv_proxy = price_proxy * quote_usd * float(valuation_supply_proxy)
    side = "buy" if float(token_delta.delta or 0.0) > 0 else "sell"
    wallet = token_delta.owner or token_delta.account
    return normalize_live_source_event(
        {
            "source_adapter": source_adapter,
            "program_id": program_id,
            "signature": signature,
            "slot": tx.get("slot"),
            "block_time": tx.get("blockTime"),
            "event_type": event_type,
            "mint": token_delta.mint,
            "pool_address": _program_pool_address(tx, program_id),
            "buyer": wallet if side == "buy" else None,
            "seller": wallet if side == "sell" else None,
            "wallet": wallet,
            "side": side,
            "sol_amount": round(quote_amount, 12) if quote_delta.mint == SOL_MINT else None,
            "sol_usd": round(float(sol_usd_price or 1.0), 8) if quote_delta.mint == SOL_MINT else None,
            "token_amount": round(token_amount, 12),
            "price_proxy": round(price_proxy, 12),
            "fdv_proxy": round(fdv_proxy, 6),
            "event_count": 1,
            "buy_count": 1 if side == "buy" else 0,
            "sell_count": 1 if side == "sell" else 0,
            "active_wallet_count": 1 if wallet else 0,
            "parse_confidence": "hydrated_amm_token_quote_delta",
            "missing_reason": None,
        }
    )


def build_live_event_candidate(event: dict[str, Any], *, include_birth_watch_candidates: bool = False) -> dict[str, Any] | None:
    mint = event.get("mint")
    fdv = safe_float(event.get("fdv_proxy"))
    event_type = event.get("event_type")
    if not mint:
        return None
    if is_quote_mint(mint):
        return None
    is_birth_watch_candidate = event_type == "pumpfun_create" and fdv is None
    if fdv is None and not (include_birth_watch_candidates and is_birth_watch_candidate):
        return None
    classification = (
        "pumpfun_birth_candidate_observed"
        if is_birth_watch_candidate
        else "efficient_mover_candidate_observed"
    )
    status = "watching_pre_trigger" if is_birth_watch_candidate else "active"
    return {
        "mint": mint,
        "token_mint": mint,
        "source": event.get("source_adapter") or event.get("source") or "helius",
        "token_name": event.get("token_name"),
        "token_symbol": event.get("token_symbol"),
        "fdv_proxy": fdv,
        "event_type": event_type,
        "event_count": event.get("event_count") or 1,
        "buy_count": event.get("buy_count") or (1 if event.get("side") == "buy" else 0),
        "sell_count": event.get("sell_count") or (1 if event.get("side") == "sell" else 0),
        "active_wallets": event.get("active_wallet_count") or (1 if event.get("wallet") or event.get("buyer") or event.get("seller") else 0),
        "slot": event.get("slot"),
        "block_time": event.get("block_time"),
        "transaction_signature": event.get("signature"),
        "liquidity_proxy": event.get("liquidity_proxy"),
        "price_proxy": event.get("price_proxy"),
        "creator": event.get("creator"),
        "pool_address": event.get("pool_address"),
        "bonding_curve": event.get("bonding_curve"),
        "associated_bonding_curve": event.get("associated_bonding_curve"),
        "metadata_uri": event.get("metadata_uri"),
        "freshness_lane": "birth_watch" if is_birth_watch_candidate else "fdv_trigger",
        "candidate_classification": classification,
        "status": status,
        "missing_reason": event.get("missing_reason"),
        "parse_confidence": event.get("parse_confidence"),
    }


def run_dry_run(config: ForwardObserverConfig) -> dict[str, Any]:
    ensure_dirs(config)
    source_reports = source_availability_reports(config)
    live_readiness = run_live_source_readiness(
        config,
        perform_network_checks=config.perform_live_health_checks,
    )
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
        "live_source_readiness": live_readiness,
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
    current_observed = len(unique_by(read_jsonl(config.observation_root / OUTPUT_FILES["candidates"]), "observation_id"))
    if not availability.get("available"):
        warnings.append("candidate_source_unavailable_no_observation_rows_written")
    while availability.get("available"):
        if current_observed >= config.target_candidates:
            break
        if config.max_observe_iterations is not None and iterations >= config.max_observe_iterations:
            break
        if elapsed_minutes(start_time) >= config.max_runtime_minutes:
            warnings.append("max_runtime_minutes_reached")
            break
        if total_api_calls >= config.max_api_calls:
            warnings.append("max_api_calls_reached")
            break
        if availability.get("source") == "helius" and config.max_helius_credits is not None and total_api_calls >= config.max_helius_credits:
            warnings.append("max_helius_credits_reached")
            break
        before_source_requests = int(getattr(selected_source, "requests_used", 0))
        candidates = selected_source.fetch_candidates()
        after_source_requests = int(getattr(selected_source, "requests_used", before_source_requests))
        total_api_calls += max(1, after_source_requests - before_source_requests)
        for candidate in candidates:
            fdv = safe_float(candidate.get("fdv_proxy"))
            mint = str(candidate.get("mint") or candidate.get("token_mint") or "")
            is_birth_watch_candidate = _candidate_is_birth_watch(candidate)
            if not mint or is_quote_mint(mint) or mint in seen_mints:
                continue
            if not is_birth_watch_candidate and (fdv is None or fdv < config.start_trigger):
                continue
            if is_birth_watch_candidate and not config.enable_birth_watch_candidates:
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
            current_observed += 1
            if current_observed >= config.target_candidates:
                break
        iterations += 1
        if config.max_observe_iterations is None:
            time.sleep(max(0.0, config.poll_seconds))
    checkpoint_payload = {
        "updated_at": utc_now_iso(),
        "seen_mints": sorted(seen_mints),
        "api_calls_used": total_api_calls,
        "source": availability,
        "warnings": warnings,
        "helius_requests_used": total_api_calls if availability.get("source") == "helius" else 0,
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
            "helius_requests_used": total_api_calls if availability.get("source") == "helius" else 0,
            "estimated_helius_credits_used": total_api_calls if availability.get("source") == "helius" else 0,
            "readiness_classification": "forward_observer_ready_for_observation" if availability.get("available") else "forward_observer_needs_source_config",
        }
    )
    write_status_files(config, tally)
    return tally


def run_status(config: ForwardObserverConfig) -> dict[str, Any]:
    ensure_dirs(config)
    tally = calculate_status_tally(config.observation_root, target_candidates=config.target_candidates)
    checkpoint = read_checkpoint(config.observation_root / OUTPUT_FILES["checkpoint"])
    helius_requests_used = int(checkpoint.get("helius_requests_used") or 0)
    tally.update(
        {
            "report_id": REPORT_ID,
            "mode": "status",
            "methodology_flags": METHODOLOGY_FLAGS,
            "guardrails": guardrails(),
            "source_readiness": source_availability_reports(config),
            "estimated_helius_requests_used": helius_requests_used,
            "estimated_helius_credits_used": helius_requests_used,
            "observation_root": str(config.observation_root),
            "report_root": str(config.report_root),
            "output_files": output_paths(config),
        }
    )
    write_status_files(config, tally)
    return tally


def run_live_program_probe(
    config: ForwardObserverConfig,
    *,
    source: str | None = None,
    limit: int = 10,
    hydrate_sample: bool = False,
    rpc_post: Any | None = None,
    load_project_dotenv: bool = True,
    ) -> dict[str, Any]:
    ensure_dirs(config)
    selected_source = source or config.source
    live_config = HeliusLiveSourceConfig.from_observer_config(
        ForwardObserverConfig(
            data_root=config.data_root,
            source=selected_source,
            max_helius_credits=config.max_helius_credits,
            enable_probed_adapters=config.enable_probed_adapters,
        ),
        load_project_dotenv=load_project_dotenv,
    )
    if live_config.max_helius_credits <= 0:
        report = {
            "report_id": "forward_efficient_mover_live_program_probe_v0",
            "created_at": utc_now_iso(),
            "source": selected_source,
            "readiness_classification": "program_probe_blocked_budget_cap",
            "network_calls_made": 0,
            "candidate_rows_created": 0,
            "warnings": ["max_helius_credits_zero_or_negative"],
            "guardrails": guardrails(),
        }
        _write_live_program_probe_report(config, selected_source, report)
        return report
    client = HeliusProgramProbeClient(
        live_config.rpc_url,
        timeout_sec=live_config.timeout_sec,
        rpc_post=rpc_post,
        valuation_supply_proxy=live_config.valuation_supply_proxy,
        sol_usd_price=live_config.sol_usd_price,
    )
    probe = client.probe_programs(
        live_config.program_configs,
        limit=max(1, min(int(limit), 25)),
        hydrate_sample=hydrate_sample,
    )
    if client.raw_transactions:
        append_jsonl(config.raw_root / RAW_SOURCE_FILES["helius_program_probe"], client.raw_transactions)
    report = {
        "report_id": "forward_efficient_mover_live_program_probe_v0",
        "created_at": utc_now_iso(),
        "source": selected_source,
        "source_adapters": {name: item.to_dict() for name, item in live_config.program_configs.items()},
        "rpc_endpoint_masked": live_config.rpc_endpoint_masked,
        "limit": max(1, min(int(limit), 25)),
        "hydrate_sample": hydrate_sample,
        "signatures_seen": probe["signatures_seen"],
        "signature_rows_seen": probe["signature_rows_seen"],
        "transactions_hydrated": probe["transactions_hydrated"],
        "program_instruction_count": probe["program_instruction_count"],
        "instruction_clusters": probe["instruction_clusters"],
        "example_signatures": probe["example_signatures"],
        "parseable_event_count": probe.get("parseable_event_count", 0),
        "parsed_event_examples": probe.get("parsed_event_examples", []),
        "candidate_rows_created": 0,
        "network_calls_made": client.requests_used,
        "estimated_helius_credits_used": client.requests_used,
        "readiness_classification": _program_probe_readiness(probe),
        "next_recommendation": _program_probe_next_recommendation(probe),
        "warnings": _program_probe_warnings(probe),
        "raw_output_path": str(config.raw_root / RAW_SOURCE_FILES["helius_program_probe"]),
        "guardrails": guardrails(),
    }
    _write_live_program_probe_report(config, selected_source, report)
    return report


def build_observation_rows(candidate: dict[str, Any], *, start_trigger: float, observation_id: str, observed_at: int) -> dict[str, Any]:
    mint = str(candidate.get("mint") or candidate.get("token_mint"))
    fdv_value = safe_float(candidate.get("fdv_proxy"))
    fdv_for_ratios = fdv_value or 0.0
    events = safe_float(candidate.get("event_count")) or 0.0
    buys = safe_float(candidate.get("buy_count")) or 0.0
    sells = safe_float(candidate.get("sell_count")) or 0.0
    active_wallets = safe_float(candidate.get("active_wallets")) or 0.0
    is_birth_watch_candidate = _candidate_is_birth_watch(candidate)
    trigger_level = None if fdv_value is None else trigger_label(fdv_value)
    trigger_timestamp = None if is_birth_watch_candidate else observed_at
    base = {
        "observation_id": observation_id,
        "mint": mint,
        "token_mint": mint,
        "source": candidate.get("source", "unknown"),
        "observed_at": observed_at,
        "freshness_lane": candidate.get("freshness_lane") or ("birth_watch" if is_birth_watch_candidate else "fdv_trigger"),
        "event_type": candidate.get("event_type"),
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
        "trigger_timestamp": trigger_timestamp,
        "status": candidate.get("status") or ("watching_pre_trigger" if is_birth_watch_candidate else "active"),
        "candidate_classification": candidate.get("candidate_classification") or "efficient_mover_candidate_observed",
    }
    path_row = {
        **base,
        "timestamp": observed_at,
        "slot": candidate.get("slot"),
        "block_time": candidate.get("block_time"),
        "fdv_proxy": fdv_value,
        "price_proxy": candidate.get("price_proxy"),
        "liquidity_proxy": candidate.get("liquidity_proxy"),
        "event_count": events,
        "buy_count": buys,
        "sell_count": sells,
        "active_wallets": active_wallets,
        "holder_count": candidate.get("holder_count"),
        "fdv_per_event": ratio(fdv_for_ratios, events) if fdv_value is not None else None,
        "fdv_per_buy": ratio(fdv_for_ratios, buys) if fdv_value is not None else None,
        "fdv_per_active_wallet": ratio(fdv_for_ratios, active_wallets) if fdv_value is not None else None,
        "buy_sell_ratio": ratio(buys, sells),
        **crossed_fields(fdv_for_ratios),
    }
    metadata_row = {
        **base,
        "token_name": candidate.get("token_name"),
        "token_symbol": candidate.get("token_symbol"),
        "metadata_uri": candidate.get("metadata_uri"),
        "parse_confidence": candidate.get("parse_confidence"),
        "missing_reason": candidate.get("missing_reason"),
        "freshness_lane": candidate.get("freshness_lane"),
        "bonding_curve": candidate.get("bonding_curve"),
        "associated_bonding_curve": candidate.get("associated_bonding_curve"),
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
        "current_local_high_fdv": fdv_value,
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
        "path_rows_collected": len(paths),
        "drawdown_rows_collected": len(drawdowns),
        "raw_ws_rows_collected": line_count(root.parent.parent / "raw" / "forward_observation" / "efficient_movers" / RAW_SOURCE_FILES["helius_ws"]),
        "raw_rpc_rows_collected": line_count(root.parent.parent / "raw" / "forward_observation" / "efficient_movers" / RAW_SOURCE_FILES["helius_rpc"]),
        "dexscreener_calls_used": 0,
        "estimated_helius_requests_used": 0,
        "estimated_helius_credits_used": 0,
        "current_target_sample_size": target_candidates,
        "remaining_until_target": max(0, target_candidates - total),
        "sample_milestones_reached": [milestone for milestone in TARGET_MILESTONES if total >= milestone],
        "target_reached": total >= target_candidates,
        "data_files_written": {key: str(root / name) for key, name in OUTPUT_FILES.items()},
        "recommended_stop_review_flag": recommend_stop_review(total, target_candidates),
    }
    return tally


def source_availability_reports(config: ForwardObserverConfig) -> list[dict[str, Any]]:
    helius_report = _safe_helius_availability(config)
    return [
        PlaceholderReadOnlySource("pumpfun_pumpswap_feed").availability(),
        PlaceholderReadOnlySource("dexscreener_latest_pairs").availability(),
        helius_report,
        LocalJsonlCandidateSource(config.local_source_path).availability(),
        MockCandidateSource().availability(),
    ]


def build_source(config: ForwardObserverConfig) -> CandidateSource:
    if config.source == "mock":
        return MockCandidateSource()
    if config.source == "local":
        return LocalJsonlCandidateSource(config.local_source_path)
    if config.source == "helius-pumpfun-create-scanner":
        return PumpFunCreateScannerCandidateSource(config)
    if config.source.startswith("helius"):
        try:
            return HeliusLiveCandidateSource(HeliusLiveSourceConfig.from_observer_config(config))
        except Exception as exc:
            return PlaceholderReadOnlySource(f"{config.source}_blocked_{type(exc).__name__}")
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
            "Source readiness:",
            *_format_source_readiness(tally.get("source_readiness") or []),
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
            f"Path rows: {tally.get('path_rows_collected', 0)}",
            f"Drawdown rows: {tally.get('drawdown_rows_collected', 0)}",
            f"Raw WS rows: {tally.get('raw_ws_rows_collected', 0)}",
            f"Raw RPC rows: {tally.get('raw_rpc_rows_collected', 0)}",
            f"Estimated Helius requests/credits used: {tally.get('estimated_helius_credits_used', 0)}",
            f"DexScreener calls used: {tally.get('dexscreener_calls_used', 0)}",
            f"Target reached: {tally.get('target_reached', False)}",
            f"Remaining until target: {tally.get('remaining_until_target', 0)}",
            f"Stop/review flag: {tally.get('recommended_stop_review_flag')}",
        ]
    )


def _program_configs_for_source(source: str, *, enable_probed_adapters: bool = False) -> dict[str, ProgramSourceConfig]:
    configs = default_program_configs()
    if enable_probed_adapters:
        configs = {
            name: (
                ProgramSourceConfig(
                    adapter_name=config.adapter_name,
                    program_ids=config.program_ids,
                    event_type=config.event_type,
                    status="ready" if config.status == "needs_probe_verification" else config.status,
                    notes=f"{config.notes} Explicit probed-adapter enable gate is active.",
                )
                if config.status == "needs_probe_verification"
                else config
            )
            for name, config in configs.items()
        }
    if source in {"helius", "helius-all", "auto"}:
        return configs
    if source == "helius-pumpfun":
        return {"helius_program_logs_pumpfun": configs["helius_program_logs_pumpfun"]}
    if source == "helius-pumpswap":
        return {"helius_program_logs_pumpswap": configs["helius_program_logs_pumpswap"]}
    if source == "helius-raydium":
        return {"helius_program_logs_raydium": configs["helius_program_logs_raydium"]}
    return configs


def _safe_helius_availability(config: ForwardObserverConfig) -> dict[str, Any]:
    try:
        if config.source == "helius-pumpfun-create-scanner":
            return PumpFunCreateScannerCandidateSource(config).availability()
        live_config = HeliusLiveSourceConfig.from_observer_config(
            ForwardObserverConfig(
                data_root=config.data_root,
                source="helius-all",
                max_helius_credits=config.max_helius_credits,
                enable_probed_adapters=config.enable_probed_adapters,
            )
        )
        return HeliusLiveCandidateSource(live_config).availability()
    except Exception as exc:
        return {
            "source": "helius",
            "available": False,
            "read_only": True,
            "missing_reason": f"helius_config_error:{type(exc).__name__}",
        }


def _safe_event_type(value: Any) -> str:
    event_type = str(value or "new_launch_candidate")
    if event_type in SUPPORTED_LIVE_EVENT_TYPES:
        return event_type
    return "new_launch_candidate"


def _signature_only_event(
    *,
    source_adapter: str,
    program_id: str,
    signature: Any,
    slot: Any,
    block_time: Any,
    event_type: str,
) -> dict[str, Any]:
    return {
        "source_adapter": source_adapter,
        "event_type": event_type,
        "program_id": program_id,
        "signature": signature,
        "slot": slot,
        "block_time": block_time,
        "parse_confidence": "signature_only",
        "missing_reason": "mint_and_fdv_not_available_without_hydration_or_metadata_feed",
    }


def _transaction_signature(tx: dict[str, Any]) -> str | None:
    signatures = tx.get("transaction", {}).get("signatures", [])
    if signatures:
        return signatures[0]
    return tx.get("signature")


def _pumpfun_event_type_and_side(tx: dict[str, Any]) -> tuple[str, str | None]:
    logs = (tx.get("meta") or {}).get("logMessages") or []
    instruction_names = _program_log_instruction_names(logs)
    if any(name in {"create", "createv2"} for name in instruction_names):
        return "pumpfun_create", None
    if any(name.startswith("migrate") for name in instruction_names):
        return "pumpswap_migration", None
    if any(name.startswith("sell") for name in instruction_names):
        return "pumpfun_trade", "sell"
    if any(name.startswith("buy") for name in instruction_names):
        return "pumpfun_trade", "buy"
    return "pumpfun_trade", None


def _program_log_instruction_names(logs: list[Any]) -> list[str]:
    names: list[str] = []
    for log in logs:
        text = str(log).strip().lower()
        marker = "instruction:"
        if marker not in text:
            continue
        names.append(text.split(marker, 1)[1].strip())
    return names


def _pumpfun_create_fields(tx: dict[str, Any], program_id: str) -> dict[str, Any] | None:
    message = (tx.get("transaction") or {}).get("message") or {}
    for instruction in message.get("instructions") or []:
        if not isinstance(instruction, dict):
            continue
        if (instruction.get("programId") or instruction.get("program_id")) != program_id:
            continue
        accounts = instruction.get("accounts") or []
        if not isinstance(accounts, list) or len(accounts) < 6:
            continue
        data_bytes = _instruction_data_bytes(instruction.get("data"))
        if data_bytes and len(data_bytes) >= 8 and data_bytes[:8].hex() != PUMPFUN_CREATE_V2_DISCRIMINATOR_HEX:
            continue
        mint = _account_string(accounts, 0)
        bonding_curve = _account_string(accounts, 2)
        associated_bonding_curve = _account_string(accounts, 3)
        creator = _account_string(accounts, 5) or _first_signer_pubkey(tx)
        if not mint or not bonding_curve or is_quote_mint(mint) or mint == program_id:
            continue
        return {
            "mint": mint,
            "bonding_curve": bonding_curve,
            "associated_bonding_curve": associated_bonding_curve,
            "creator": creator,
        }
    return None


def _account_string(accounts: list[Any], index: int) -> str | None:
    if index >= len(accounts):
        return None
    value = accounts[index]
    if isinstance(value, dict):
        value = value.get("pubkey") or value.get("account") or value.get("address")
    value = str(value or "")
    return value or None


def _first_signer_pubkey(tx: dict[str, Any]) -> str | None:
    message = (tx.get("transaction") or {}).get("message") or {}
    for account in message.get("accountKeys") or []:
        if isinstance(account, dict) and account.get("signer"):
            pubkey = str(account.get("pubkey") or "")
            if pubkey:
                return pubkey
    return None


def _candidate_is_birth_watch(candidate: dict[str, Any]) -> bool:
    return (
        candidate.get("freshness_lane") == "birth_watch"
        or candidate.get("candidate_classification") == "pumpfun_birth_candidate_observed"
        or (candidate.get("event_type") == "pumpfun_create" and safe_float(candidate.get("fdv_proxy")) is None)
    )


def _primary_token_delta(deltas: list[Any]) -> Any | None:
    candidates = [
        delta
        for delta in deltas
        if getattr(delta, "mint", None)
        and not is_quote_mint(str(getattr(delta, "mint", "")))
        and abs(float(getattr(delta, "delta", 0.0) or 0.0)) > 0
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda delta: abs(float(delta.delta or 0.0)))


def is_quote_mint(mint: str | None) -> bool:
    return str(mint or "") in QUOTE_MINTS


def _primary_native_delta_sol(deltas: list[Any]) -> Any | None:
    candidates = [
        delta
        for delta in deltas
        if getattr(delta, "delta_sol", None) is not None and abs(float(delta.delta_sol or 0.0)) > 0
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda delta: abs(float(delta.delta_sol or 0.0)))


def _single_amm_token_quote_pair(
    deltas: list[Any],
    *,
    native_deltas: list[Any] | None = None,
    signer_pubkeys: set[str] | None = None,
    side_hint: str | None = None,
) -> tuple[Any, Any] | None:
    nonzero = [delta for delta in deltas if abs(float(getattr(delta, "delta", 0.0) or 0.0)) > 0 and getattr(delta, "mint", None)]
    token_mints = {delta.mint for delta in nonzero if delta.mint not in QUOTE_MINTS}
    quote_deltas = [delta for delta in nonzero if delta.mint in QUOTE_MINTS]
    if len(token_mints) != 1:
        return None
    token_mint = next(iter(token_mints))
    token_deltas = [delta for delta in nonzero if delta.mint == token_mint]
    owner_pairs = []
    for token_delta in token_deltas:
        token_owner = getattr(token_delta, "owner", None) or getattr(token_delta, "account", None)
        token_value = float(getattr(token_delta, "delta", 0.0) or 0.0)
        if not token_owner or token_value == 0:
            continue
        for quote_delta in quote_deltas:
            quote_owner = getattr(quote_delta, "owner", None) or getattr(quote_delta, "account", None)
            quote_value = float(getattr(quote_delta, "delta", 0.0) or 0.0)
            if quote_owner == token_owner and quote_value and token_value * quote_value < 0:
                owner_pairs.append((token_delta, quote_delta))
    signer_pairs = [
        pair
        for pair in owner_pairs
        if ((getattr(pair[0], "owner", None) or getattr(pair[0], "account", None)) in (signer_pubkeys or set()))
    ]
    if len(signer_pairs) == 1:
        return signer_pairs[0]
    if side_hint in {"buy", "sell"}:
        desired_sign = 1 if side_hint == "buy" else -1
        side_pairs = [
            pair
            for pair in owner_pairs
            if (float(getattr(pair[0], "delta", 0.0) or 0.0) > 0) == (desired_sign > 0)
        ]
        if len(side_pairs) == 1:
            return side_pairs[0]
    native_pair = _native_sol_signer_pair(token_deltas, native_deltas or [], signer_pubkeys or set(), side_hint=side_hint)
    if native_pair:
        return native_pair
    if len(owner_pairs) != 1:
        return None
    return owner_pairs[0]


def _native_sol_signer_pair(
    token_deltas: list[Any],
    native_deltas: list[Any],
    signer_pubkeys: set[str],
    *,
    side_hint: str | None,
) -> tuple[Any, Any] | None:
    pairs = []
    for token_delta in token_deltas:
        token_owner = getattr(token_delta, "owner", None) or getattr(token_delta, "account", None)
        token_value = float(getattr(token_delta, "delta", 0.0) or 0.0)
        if token_owner not in signer_pubkeys or token_value == 0:
            continue
        if side_hint == "buy" and token_value < 0:
            continue
        if side_hint == "sell" and token_value > 0:
            continue
        for native_delta in native_deltas:
            native_owner = getattr(native_delta, "owner", None) or getattr(native_delta, "account", None)
            native_value = float(getattr(native_delta, "delta_sol", 0.0) or 0.0)
            if native_owner == token_owner and native_value and token_value * native_value < 0:
                quote_delta = SimpleNamespace(
                    mint=SOL_MINT,
                    owner=native_owner,
                    account=getattr(native_delta, "account", None),
                    delta=native_value,
                )
                pairs.append((token_delta, quote_delta))
    if len(pairs) == 1:
        return pairs[0]
    return None


def _single_direction_side_hint(tx: dict[str, Any]) -> str | None:
    logs = (tx.get("meta") or {}).get("logMessages") or []
    lowered = " ".join(str(log).lower() for log in logs)
    buy_seen = "instruction: buy" in lowered or "buyexact" in lowered
    sell_seen = "instruction: sell" in lowered or "sellexact" in lowered
    if buy_seen and not sell_seen:
        return "buy"
    if sell_seen and not buy_seen:
        return "sell"
    return None


def _signer_pubkeys(tx: dict[str, Any]) -> set[str]:
    account_keys = ((tx.get("transaction") or {}).get("message") or {}).get("accountKeys") or []
    signers = set()
    for account in account_keys:
        if isinstance(account, dict) and account.get("signer") and account.get("pubkey"):
            signers.add(str(account["pubkey"]))
    return signers


def _program_pool_address(tx: dict[str, Any], program_id: str) -> str | None:
    message = (tx.get("transaction") or {}).get("message") or {}
    for instruction in message.get("instructions") or []:
        if instruction.get("programId") != program_id:
            continue
        accounts = instruction.get("accounts") or []
        if isinstance(accounts, list) and len(accounts) > 1:
            return str(accounts[1])
    return None


def _extract_program_instruction_rows(transactions: list[dict[str, Any]], program_ids: set[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for tx in transactions:
        signature = _transaction_signature(tx)
        slot = tx.get("slot")
        block_time = tx.get("blockTime")
        message = (tx.get("transaction") or {}).get("message") or {}
        for instruction in message.get("instructions") or []:
            row = _program_instruction_row(
                instruction,
                signature=signature,
                slot=slot,
                block_time=block_time,
                program_ids=program_ids,
                instruction_location="outer",
            )
            if row:
                rows.append(row)
        for inner_group in (tx.get("meta") or {}).get("innerInstructions") or []:
            for instruction in inner_group.get("instructions") or []:
                row = _program_instruction_row(
                    instruction,
                    signature=signature,
                    slot=slot,
                    block_time=block_time,
                    program_ids=program_ids,
                    instruction_location="inner",
                )
                if row:
                    rows.append(row)
    return rows


def _program_instruction_row(
    instruction: dict[str, Any],
    *,
    signature: str | None,
    slot: Any,
    block_time: Any,
    program_ids: set[str],
    instruction_location: str,
) -> dict[str, Any] | None:
    program_id = instruction.get("programId") or instruction.get("program_id")
    if program_id not in program_ids:
        return None
    accounts = instruction.get("accounts") or []
    data = instruction.get("data")
    data_bytes = _instruction_data_bytes(data)
    parsed_type = ((instruction.get("parsed") or {}) if isinstance(instruction.get("parsed"), dict) else {}).get("type")
    return {
        "signature": signature,
        "slot": slot,
        "block_time": block_time,
        "program_id": program_id,
        "instruction_location": instruction_location,
        "account_count": len(accounts) if isinstance(accounts, list) else 0,
        "data_length": len(data_bytes) if data_bytes is not None else None,
        "first_8_data_bytes_hex": data_bytes[:8].hex() if data_bytes is not None else None,
        "instruction_data_prefix": str(data)[:16] if data is not None else None,
        "parsed_type": parsed_type,
    }


def _instruction_clusters(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    clusters: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in rows:
        key = (
            row.get("program_id"),
            row.get("first_8_data_bytes_hex"),
            row.get("account_count"),
            row.get("data_length"),
            row.get("parsed_type"),
        )
        cluster = clusters.setdefault(
            key,
            {
                "program_id": row.get("program_id"),
                "first_8_data_bytes_hex": row.get("first_8_data_bytes_hex"),
                "instruction_data_prefix": row.get("instruction_data_prefix"),
                "account_count": row.get("account_count"),
                "data_length": row.get("data_length"),
                "parsed_type": row.get("parsed_type"),
                "count": 0,
                "example_signatures": [],
            },
        )
        cluster["count"] += 1
        signature = row.get("signature")
        if signature and signature not in cluster["example_signatures"] and len(cluster["example_signatures"]) < 5:
            cluster["example_signatures"].append(signature)
    return sorted(clusters.values(), key=lambda item: (-int(item["count"]), str(item.get("program_id") or "")))


def _normalize_probe_transaction_event(
    tx: dict[str, Any],
    *,
    adapter_name: str,
    program_configs: dict[str, ProgramSourceConfig],
    valuation_supply_proxy: float,
    sol_usd_price: float,
) -> dict[str, Any] | None:
    program_config = program_configs.get(adapter_name)
    if not program_config:
        return None
    program_id = _first_direct_program_id(tx, set(program_config.program_ids))
    if not program_id:
        return None
    if adapter_name == "helius_program_logs_pumpfun":
        return normalize_pumpfun_transaction_event(
            tx,
            source_adapter=adapter_name,
            program_id=program_id,
            valuation_supply_proxy=valuation_supply_proxy,
            sol_usd_price=sol_usd_price,
        )
    if adapter_name in {"helius_program_logs_pumpswap", "helius_program_logs_raydium"}:
        return normalize_amm_transaction_event(
            tx,
            source_adapter=adapter_name,
            program_id=program_id,
            event_type=program_config.event_type,
            valuation_supply_proxy=valuation_supply_proxy,
            sol_usd_price=sol_usd_price,
        )
    return None


def _first_direct_program_id(tx: dict[str, Any], program_ids: set[str]) -> str | None:
    message = (tx.get("transaction") or {}).get("message") or {}
    for instruction in message.get("instructions") or []:
        program_id = instruction.get("programId") or instruction.get("program_id")
        if program_id in program_ids:
            return str(program_id)
    return None


def _instruction_data_bytes(data: Any) -> bytes | None:
    if data is None:
        return None
    if isinstance(data, list):
        try:
            return bytes(int(item) & 0xFF for item in data)
        except (TypeError, ValueError):
            return None
    if isinstance(data, str):
        return _base58_decode(data)
    return None


def _base58_decode(value: str) -> bytes | None:
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    decoded = 0
    try:
        for char in value:
            decoded = decoded * 58 + alphabet.index(char)
    except ValueError:
        return None
    leading_zeroes = len(value) - len(value.lstrip("1"))
    payload = decoded.to_bytes((decoded.bit_length() + 7) // 8, "big") if decoded else b""
    return b"\x00" * leading_zeroes + payload


def _program_probe_readiness(probe: dict[str, Any]) -> str:
    if int(probe.get("signatures_seen") or 0) <= 0:
        return "program_probe_no_recent_signatures"
    if int(probe.get("transactions_hydrated") or 0) <= 0:
        return "program_probe_signatures_only"
    if int(probe.get("program_instruction_count") or 0) <= 0:
        return "program_probe_no_direct_program_instructions"
    if int(probe.get("parseable_event_count") or 0) > 0:
        return "program_probe_candidate_fields_parseable"
    return "program_probe_semantics_maybe_viable"


def _program_probe_next_recommendation(probe: dict[str, Any]) -> str:
    readiness = _program_probe_readiness(probe)
    if readiness == "program_probe_candidate_fields_parseable":
        return "run_tiny_observe_with_adapter_still_under_review_or_add_adapter_enable_gate"
    if readiness == "program_probe_semantics_maybe_viable":
        return "review_instruction_clusters_before_enabling_adapter"
    if readiness == "program_probe_signatures_only":
        return "rerun_tiny_probe_with_hydrate_sample"
    if readiness == "program_probe_no_recent_signatures":
        return "try_known_active_time_window_or_alternate_program_id"
    return "inspect_raw_transactions_or_try_alternate_source"


def _program_probe_warnings(probe: dict[str, Any]) -> list[str]:
    warnings = ["probe_only_no_candidate_rows_created", "adapter_readiness_not_changed"]
    if int(probe.get("transactions_hydrated") or 0) <= 0:
        warnings.append("no_hydrated_transactions_available")
    if int(probe.get("program_instruction_count") or 0) <= 0:
        warnings.append("program_instruction_semantics_not_confirmed")
    if int(probe.get("parseable_event_count") or 0) <= 0:
        warnings.append("candidate_field_extraction_not_confirmed")
    return warnings


def _post_json_rpc(url: str, payload: dict[str, Any], timeout_sec: int) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib_request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib_request.urlopen(request, timeout=timeout_sec) as response:
        return json.loads(response.read().decode("utf-8"))


def _helius_rpc_health_check(rpc_url: str) -> dict[str, Any]:
    if not rpc_url:
        return {"status": "blocked", "reason": "missing_rpc_url"}
    try:
        response = _post_json_rpc(
            rpc_url,
            {"jsonrpc": "2.0", "id": "mtp-forward-observer-health", "method": "getHealth", "params": []},
            8,
        )
    except Exception as exc:
        return {"status": "blocked", "reason": type(exc).__name__}
    if response.get("error"):
        return {"status": "blocked", "reason": "rpc_error", "error_code": (response.get("error") or {}).get("code")}
    return {"status": "ready", "method": "getHealth", "result": response.get("result")}


def _helius_ws_health_check(ws_url: str) -> dict[str, Any]:
    if not ws_url:
        return {"status": "blocked", "reason": "missing_ws_url"}
    parsed = urlparse(ws_url)
    host = parsed.hostname
    if not host:
        return {"status": "blocked", "reason": "missing_ws_host"}
    port = parsed.port or (443 if parsed.scheme == "wss" else 80)
    try:
        raw = socket.create_connection((host, port), timeout=8)
        if parsed.scheme == "wss":
            context = ssl.create_default_context()
            with context.wrap_socket(raw, server_hostname=host):
                pass
        else:
            raw.close()
    except Exception as exc:
        return {"status": "blocked", "reason": type(exc).__name__}
    return {"status": "ready", "method": "tls_socket_connect", "host": host, "port": port}


def _check_output_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".forward_observer_write_probe"
        probe.write_text("ok\n", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def _write_live_readiness_report(config: ForwardObserverConfig, report: dict[str, Any]) -> None:
    config.report_root.mkdir(parents=True, exist_ok=True)
    (config.report_root / LIVE_READINESS_JSON).write_text(json.dumps(report, indent=2, sort_keys=True, default=json_default) + "\n", encoding="utf-8")
    (config.report_root / LIVE_READINESS_MD).write_text(_live_readiness_markdown(report), encoding="utf-8")


def _write_live_program_probe_report(config: ForwardObserverConfig, source: str, report: dict[str, Any]) -> None:
    config.report_root.mkdir(parents=True, exist_ok=True)
    safe_source = source.replace("/", "_")
    (config.report_root / f"live_program_probe_{safe_source}.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, default=json_default) + "\n",
        encoding="utf-8",
    )
    (config.report_root / f"live_program_probe_{safe_source}.md").write_text(
        _live_program_probe_markdown(report),
        encoding="utf-8",
    )


def _live_readiness_markdown(report: dict[str, Any]) -> str:
    helius = report.get("helius") or {}
    lines = [
        "# Forward Efficient Mover Live Source Readiness",
        "",
        f"- Readiness classification: `{report.get('readiness_classification')}`",
        f"- Helius API key present: `{helius.get('api_key_present')}`",
        f"- Helius RPC: `{(helius.get('rpc_health') or {}).get('status')}`",
        f"- Helius WS: `{(helius.get('ws_health') or {}).get('status')}`",
        f"- RPC endpoint: `{helius.get('rpc_endpoint_masked')}`",
        f"- WS endpoint: `{helius.get('ws_endpoint_masked')}`",
        f"- Ready adapters: `{report.get('ready_adapters')}`",
        f"- Missing/unverified adapters: `{report.get('missing_or_unverified_adapters')}`",
        f"- Output paths writable: `{report.get('output_paths_writable')}`",
        f"- Max Helius credits: `{(report.get('budget_caps') or {}).get('default_observe_cap')}`",
        "",
        "This is read-only observation infrastructure. It does not contain paper trading, live trading, order routing, transaction signing, or buy/sell rules.",
    ]
    return "\n".join(lines) + "\n"


def _live_program_probe_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Forward Efficient Mover Live Program Probe",
        "",
        f"- Source: `{report.get('source')}`",
        f"- Readiness classification: `{report.get('readiness_classification')}`",
        f"- Limit: `{report.get('limit')}`",
        f"- Hydrate sample: `{report.get('hydrate_sample')}`",
        f"- Signatures seen: `{report.get('signatures_seen', 0)}`",
        f"- Transactions hydrated: `{report.get('transactions_hydrated', 0)}`",
        f"- Direct program instructions: `{report.get('program_instruction_count', 0)}`",
        f"- Parseable candidate-field events: `{report.get('parseable_event_count', 0)}`",
        f"- Candidate rows created: `{report.get('candidate_rows_created', 0)}`",
        f"- Network calls made: `{report.get('network_calls_made', 0)}`",
        f"- Next recommendation: `{report.get('next_recommendation')}`",
        f"- Warnings: `{report.get('warnings', [])}`",
        "",
        "## Instruction Clusters",
        "",
    ]
    clusters = report.get("instruction_clusters") or []
    if not clusters:
        lines.append("- No direct instruction clusters observed.")
    for cluster in clusters[:20]:
        lines.append(
            "- "
            f"program=`{cluster.get('program_id')}` "
            f"count=`{cluster.get('count')}` "
            f"first_8_data_bytes_hex=`{cluster.get('first_8_data_bytes_hex')}` "
            f"account_count=`{cluster.get('account_count')}` "
            f"data_length=`{cluster.get('data_length')}` "
            f"examples=`{cluster.get('example_signatures')}`"
        )
    lines.extend(
        [
            "",
            "Probe only. No candidate rows, no strategy logic, no paper/live trading, no order routing, and no adapter readiness changes.",
        ]
    )
    return "\n".join(lines) + "\n"


def _format_source_readiness(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["- No source readiness rows available."]
    output = []
    for row in rows:
        source = row.get("source")
        status = "ready" if row.get("available") else "blocked"
        reason = row.get("missing_reason")
        output.append(f"- {source}: {status}" + (f" ({reason})" if reason else ""))
        if source == "helius":
            ready = row.get("ready_adapters") or []
            missing = row.get("missing_or_unverified_adapters") or []
            output.append(f"  ready_adapters={ready}")
            output.append(f"  missing_or_unverified_adapters={missing}")
    return output


def line_count(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


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
