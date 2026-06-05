"""Forward metadata/profile enrichment for official lifecycle observation.

This module is read-only enrichment infrastructure. It captures token identity,
profile, social, media-quality, and deterministic narrative fields for later
diagnostics. It does not contain live trading, paper trading, wallet execution,
private-key logic, validation, backtests, buy/sell rules, or PnL logic.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any
from urllib.parse import urlparse
import json
import re
import threading
import time
import urllib.error
import urllib.request

from research.mtp_research.validation.forward_efficient_mover_observer import _post_json_rpc, resolve_helius_rpc_url
from research.mtp_research.validation.official_lifecycle_watch import (
    OfficialLifecycleConfig,
    _append_jsonl,
    _read_jsonl,
    _utc_now_iso,
    _write_json,
)


METADATA_POINTS = {
    "birth",
    "first_fdv_path",
    "crossed_10k",
    "crossed_15k",
    "crossed_20k",
    "crossed_50k",
    "crossed_100k",
    "crossed_500k",
    "crossed_1m",
    "matured_reached_1m",
    "matured_terminal_collapse",
    "matured_inactive_timeout",
    "matured_max_age",
}


@dataclass(frozen=True)
class ForwardMetadataConfig:
    max_metadata_workers: int = 4
    metadata_fetch_timeout_seconds: float = 2.0
    max_metadata_uri_bytes: int = 128_000
    max_metadata_jobs_per_mint_per_hour: int = 12
    enable_dexscreener_metadata: bool = False
    enable_public_uri_fetch: bool = True


class ForwardMetadataEnrichmentQueue:
    def __init__(
        self,
        lifecycle_config: OfficialLifecycleConfig,
        *,
        metadata_config: ForwardMetadataConfig | None = None,
        resolver: "ForwardMetadataResolver | None" = None,
    ) -> None:
        self.lifecycle_config = lifecycle_config
        self.metadata_config = metadata_config or ForwardMetadataConfig()
        self.resolver = resolver or ForwardMetadataResolver(lifecycle_config, metadata_config=self.metadata_config)
        self.executor = ThreadPoolExecutor(max_workers=max(1, int(self.metadata_config.max_metadata_workers)))
        self._futures: dict[Future, dict[str, Any]] = {}
        self._submitted_by_mint: dict[str, list[float]] = defaultdict(list)
        self._seen_keys: set[tuple[str, str]] = set()
        self._lock = threading.Lock()
        self.jobs_submitted = 0
        self.jobs_written = 0
        self.jobs_rejected = 0

    @property
    def pending_count(self) -> int:
        with self._lock:
            return len(self._futures)

    def enqueue(
        self,
        *,
        mint: str,
        lifecycle_point: str,
        source_dataset: str,
        observed_at: float | None = None,
        create_metadata: dict[str, Any] | None = None,
        metadata_backfilled_after_collection: bool = False,
    ) -> bool:
        if not mint:
            return False
        point = _normalize_lifecycle_point(lifecycle_point)
        key = (str(mint), point)
        now = time.time()
        with self._lock:
            if key in self._seen_keys:
                self.jobs_rejected += 1
                return False
            recent = [value for value in self._submitted_by_mint[str(mint)] if now - value < 3600]
            self._submitted_by_mint[str(mint)] = recent
            if len(recent) >= max(1, int(self.metadata_config.max_metadata_jobs_per_mint_per_hour)):
                self.jobs_rejected += 1
                return False
            self._seen_keys.add(key)
            self._submitted_by_mint[str(mint)].append(now)
            future = self.executor.submit(
                self.resolver.resolve_snapshot,
                mint=str(mint),
                lifecycle_point=point,
                source_dataset=source_dataset,
                observed_at=observed_at,
                create_metadata=dict(create_metadata or {}),
                metadata_backfilled_after_collection=metadata_backfilled_after_collection,
            )
            self._futures[future] = {"mint": str(mint), "lifecycle_point": point}
            self.jobs_submitted += 1
        self.drain_completed(limit=50)
        return True

    def drain_completed(self, *, limit: int = 100) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        with self._lock:
            futures = list(self._futures)
        for future in futures:
            if len(rows) >= max(1, int(limit)):
                break
            if not future.done():
                continue
            with self._lock:
                context = self._futures.pop(future, {})
            try:
                row = future.result(timeout=0)
            except Exception as exc:
                row = build_metadata_snapshot(
                    self.lifecycle_config,
                    mint=str(context.get("mint") or ""),
                    lifecycle_point=str(context.get("lifecycle_point") or "unknown"),
                    source_dataset=self.lifecycle_config.sample_label,
                    metadata_fetch_status="failed",
                    metadata_fetch_error=f"metadata_job_failed:{type(exc).__name__}",
                )
            _append_jsonl(self.lifecycle_config.metadata_snapshots_path, [row])
            _append_jsonl(self.lifecycle_config.metadata_path, [_metadata_summary_row(row)])
            self.jobs_written += 1
            rows.append(row)
        if rows:
            summarize_metadata_coverage(self.lifecycle_config)
        _write_metadata_status(self.lifecycle_config, self)
        return rows

    def close(self, *, wait: bool = False) -> None:
        if wait:
            for future in list(self._futures):
                try:
                    future.result(timeout=max(0.1, float(self.metadata_config.metadata_fetch_timeout_seconds) + 0.5))
                except Exception:
                    pass
            self.drain_completed(limit=100_000)
        self.executor.shutdown(wait=False, cancel_futures=True)
        _write_metadata_status(self.lifecycle_config, self)


class ForwardMetadataResolver:
    def __init__(
        self,
        lifecycle_config: OfficialLifecycleConfig,
        *,
        metadata_config: ForwardMetadataConfig | None = None,
        rpc_url: str | None = None,
        rpc_post: Any | None = None,
        urlopen: Any | None = None,
    ) -> None:
        self.lifecycle_config = lifecycle_config
        self.metadata_config = metadata_config or ForwardMetadataConfig()
        self.rpc_url = rpc_url if rpc_url is not None else resolve_helius_rpc_url()
        self._rpc_post = rpc_post or _post_json_rpc
        self._urlopen = urlopen or urllib.request.urlopen
        self.requests_used = 0

    def resolve_snapshot(
        self,
        *,
        mint: str,
        lifecycle_point: str,
        source_dataset: str,
        observed_at: float | None,
        create_metadata: dict[str, Any],
        metadata_backfilled_after_collection: bool = False,
    ) -> dict[str, Any]:
        raw_parts: dict[str, Any] = {}
        status = "success"
        error: str | None = None
        source_priority = 1
        metadata_source = "pumpfun_create_transaction"
        metadata_is_point_in_time = True
        metadata_is_latest_only = False
        payload = dict(create_metadata or {})
        if not _has_identity_or_profile(payload):
            source_priority = 2
            metadata_source = "helius_das"
            metadata_is_point_in_time = False
            metadata_is_latest_only = True
            das = self._resolve_helius_das(mint)
            raw_parts["helius_das"] = das.get("_raw") if das else None
            if das:
                payload.update({key: value for key, value in das.items() if key != "_raw" and value is not None})
            else:
                status = "partial"
                error = "helius_das_metadata_unavailable"
        uri = str(payload.get("metadata_uri") or payload.get("uri") or "")
        if self.metadata_config.enable_public_uri_fetch and uri:
            uri_payload = self._resolve_public_metadata_uri(uri)
            raw_parts["metadata_uri"] = uri_payload.get("_raw") if uri_payload else None
            if uri_payload:
                payload.update({key: value for key, value in uri_payload.items() if key != "_raw" and value is not None})
                if metadata_source != "pumpfun_create_transaction":
                    metadata_source = "public_metadata_uri"
                    source_priority = 3
            elif status == "success" and metadata_source != "pumpfun_create_transaction":
                status = "partial"
                error = "metadata_uri_unavailable_or_invalid"
        if self.metadata_config.enable_dexscreener_metadata:
            dex = self._resolve_dexscreener(mint)
            raw_parts["dexscreener"] = dex.get("_raw") if dex else None
            if dex:
                payload.update({key: value for key, value in dex.items() if key != "_raw" and value is not None})
        snapshot = build_metadata_snapshot(
            self.lifecycle_config,
            mint=mint,
            lifecycle_point=lifecycle_point,
            source_dataset=source_dataset,
            observed_at=observed_at,
            source_priority=source_priority,
            metadata_source=metadata_source,
            metadata_is_point_in_time=metadata_is_point_in_time and not metadata_backfilled_after_collection,
            metadata_is_latest_only=metadata_is_latest_only or metadata_backfilled_after_collection,
            metadata_fetch_status=status,
            metadata_fetch_error=error,
            metadata_backfilled_after_collection=metadata_backfilled_after_collection,
            create_metadata=payload,
        )
        self._write_raw(raw_parts, snapshot)
        return snapshot

    def _resolve_helius_das(self, mint: str) -> dict[str, Any] | None:
        if not self.rpc_url or not mint:
            return None
        payload = {"jsonrpc": "2.0", "id": "mtp-forward-metadata-get-asset", "method": "getAsset", "params": {"id": mint}}
        try:
            response = self._rpc_post(self.rpc_url, payload, int(self.metadata_config.metadata_fetch_timeout_seconds))
            self.requests_used += 1
        except Exception:
            return None
        result = response.get("result") if isinstance(response, dict) else None
        if not isinstance(result, dict):
            return None
        content = result.get("content") if isinstance(result.get("content"), dict) else {}
        metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
        content_metadata = content.get("metadata") if isinstance(content.get("metadata"), dict) else {}
        links = content.get("links") if isinstance(content.get("links"), dict) else {}
        return {
            "_raw": response,
            "token_name": metadata.get("name") or content_metadata.get("name"),
            "token_symbol": metadata.get("symbol") or content_metadata.get("symbol"),
            "token_description": metadata.get("description") or content_metadata.get("description"),
            "metadata_uri": links.get("metadata") or content.get("json_uri"),
            "image_uri": links.get("image"),
            "external_url": links.get("external_url") or content_metadata.get("external_url"),
        }

    def _resolve_public_metadata_uri(self, uri: str) -> dict[str, Any] | None:
        if not _safe_public_metadata_uri(uri):
            return None
        try:
            with self._urlopen(uri, timeout=float(self.metadata_config.metadata_fetch_timeout_seconds)) as response:
                raw = response.read(max(1, int(self.metadata_config.max_metadata_uri_bytes)) + 1)
        except Exception:
            return None
        if len(raw) > int(self.metadata_config.max_metadata_uri_bytes):
            return None
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        self.requests_used += 1
        return {
            "_raw": payload,
            "token_name": payload.get("name"),
            "token_symbol": payload.get("symbol"),
            "token_description": payload.get("description"),
            "image_uri": payload.get("image"),
            "external_url": payload.get("external_url") or payload.get("website"),
            "seller_fee_basis_points": payload.get("seller_fee_basis_points"),
            "collection_name": _collection_name(payload),
            **_extract_socials(payload),
            "metadata_json_available": True,
            "metadata_json_valid": True,
            "metadata_json_size_bytes": len(raw),
        }

    def _resolve_dexscreener(self, mint: str) -> dict[str, Any] | None:
        if not mint:
            return None
        url = f"https://api.dexscreener.com/latest/dex/tokens/{mint}"
        try:
            with self._urlopen(url, timeout=float(self.metadata_config.metadata_fetch_timeout_seconds)) as response:
                raw = response.read(128_000)
        except Exception:
            return None
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            return None
        pairs = payload.get("pairs") if isinstance(payload, dict) else None
        pair = pairs[0] if isinstance(pairs, list) and pairs and isinstance(pairs[0], dict) else {}
        info = pair.get("info") if isinstance(pair.get("info"), dict) else {}
        socials = info.get("socials") if isinstance(info.get("socials"), list) else []
        return {
            "_raw": payload,
            "dexscreener_pair_present": bool(pair),
            "dexscreener_profile_present": bool(info),
            "dexscreener_socials_present": bool(socials),
            "dexscreener_url": pair.get("url"),
            "dexscreener_observed_at": time.time(),
            "dexscreener_context_is_latest_only": True,
        }

    def _write_raw(self, raw_parts: dict[str, Any], snapshot: dict[str, Any]) -> None:
        base = {"mint": snapshot.get("mint"), "lifecycle_point": snapshot.get("lifecycle_point"), "observed_at": snapshot.get("observed_at")}
        if raw_parts.get("helius_das") is not None:
            _append_jsonl(self.lifecycle_config.metadata_helius_das_raw_path, [{**base, "raw": raw_parts["helius_das"]}])
        if raw_parts.get("metadata_uri") is not None:
            _append_jsonl(self.lifecycle_config.metadata_uri_raw_path, [{**base, "raw": raw_parts["metadata_uri"]}])
        if raw_parts.get("dexscreener") is not None:
            _append_jsonl(self.lifecycle_config.metadata_dexscreener_raw_path, [{**base, "raw": raw_parts["dexscreener"]}])


def build_metadata_snapshot(
    config: OfficialLifecycleConfig,
    *,
    mint: str,
    lifecycle_point: str,
    source_dataset: str,
    observed_at: float | None = None,
    source_priority: int = 1,
    metadata_source: str | None = None,
    metadata_is_point_in_time: bool = True,
    metadata_is_latest_only: bool = False,
    metadata_fetch_status: str = "success",
    metadata_fetch_error: str | None = None,
    metadata_backfilled_after_collection: bool = False,
    create_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = dict(create_metadata or {})
    identity = _identity_fields(payload)
    socials = _social_fields(payload)
    media = _media_fields(payload)
    name_features = _name_features(identity["token_name"], identity["token_symbol"])
    narrative = classify_narrative(identity["token_name"], identity["token_symbol"], identity["token_description"])
    completeness = _metadata_completeness(identity, socials, media)
    return {
        "sample_label": config.sample_label,
        "mint": mint,
        "observed_at": observed_at if observed_at is not None else time.time(),
        "lifecycle_point": _normalize_lifecycle_point(lifecycle_point),
        "source_dataset": source_dataset,
        "source_priority": int(source_priority),
        "metadata_source": metadata_source or _metadata_source_from_payload(payload),
        "metadata_is_point_in_time": bool(metadata_is_point_in_time),
        "metadata_is_latest_only": bool(metadata_is_latest_only),
        "metadata_backfilled_after_collection": bool(metadata_backfilled_after_collection),
        "metadata_fetch_status": metadata_fetch_status,
        "metadata_fetch_error": metadata_fetch_error,
        **identity,
        **socials,
        **media,
        "metadata_completeness_score": completeness,
        "metadata_quality_bucket": _metadata_quality_bucket(completeness),
        **name_features,
        **narrative,
        "dexscreener_pair_present": bool(payload.get("dexscreener_pair_present", False)),
        "dexscreener_profile_present": bool(payload.get("dexscreener_profile_present", False)),
        "dexscreener_boost_present": bool(payload.get("dexscreener_boost_present", False)),
        "dexscreener_paid_order_present": bool(payload.get("dexscreener_paid_order_present", False)),
        "dexscreener_socials_present": bool(payload.get("dexscreener_socials_present", False)),
        "dexscreener_url": payload.get("dexscreener_url"),
        "dexscreener_observed_at": payload.get("dexscreener_observed_at"),
        "dexscreener_context_is_latest_only": bool(payload.get("dexscreener_context_is_latest_only", False)),
        "no_private_key_logic": True,
        "no_live_trading": True,
        "no_paper_trading": True,
        "no_pnl": True,
    }


def load_metadata_snapshots(config: OfficialLifecycleConfig) -> list[dict[str, Any]]:
    return _read_jsonl(config.metadata_snapshots_path)


def latest_metadata_before(rows: list[dict[str, Any]], mint: str, timestamp: float) -> dict[str, Any] | None:
    candidates = [
        row
        for row in rows
        if row.get("mint") == mint and _num(row.get("observed_at")) is not None and (_num(row.get("observed_at")) or 0) <= timestamp
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda row: _num(row.get("observed_at")) or 0)


def metadata_at_lifecycle_point(rows: list[dict[str, Any]], mint: str, lifecycle_point: str) -> dict[str, Any] | None:
    point = _normalize_lifecycle_point(lifecycle_point)
    candidates = [row for row in rows if row.get("mint") == mint and row.get("lifecycle_point") == point]
    if not candidates:
        return None
    return max(candidates, key=lambda row: _num(row.get("observed_at")) or 0)


def summarize_metadata_coverage(config: OfficialLifecycleConfig) -> tuple[dict[str, Any], dict[str, Path]]:
    rows = load_metadata_snapshots(config)
    rows_by_point = Counter(str(row.get("lifecycle_point") or "unknown") for row in rows)
    score_values = [_num(row.get("metadata_completeness_score")) for row in rows if _num(row.get("metadata_completeness_score")) is not None]
    summary = {
        "report_id": "official_lifecycle_v2_metadata_coverage_audit_v0",
        "sample_label": config.sample_label,
        "created_at": _utc_now_iso(),
        "metadata_snapshots": len(rows),
        "unique_mints_with_metadata": len({row.get("mint") for row in rows if row.get("mint")}),
        "birth_metadata_coverage": rows_by_point["birth"],
        "10k_metadata_coverage": rows_by_point["crossed_10k"],
        "20k_metadata_coverage": rows_by_point["crossed_20k"],
        "maturity_metadata_coverage": sum(count for point, count in rows_by_point.items() if point.startswith("matured_")),
        "token_name_coverage": sum(1 for row in rows if row.get("token_name")),
        "symbol_coverage": sum(1 for row in rows if row.get("token_symbol")),
        "metadata_uri_coverage": sum(1 for row in rows if row.get("metadata_uri")),
        "image_uri_coverage": sum(1 for row in rows if row.get("image_uri")),
        "website_coverage": sum(1 for row in rows if row.get("has_website") is True),
        "twitter_x_coverage": sum(1 for row in rows if row.get("has_twitter_x") is True),
        "telegram_coverage": sum(1 for row in rows if row.get("has_telegram") is True),
        "discord_coverage": sum(1 for row in rows if row.get("has_discord") is True),
        "any_social_coverage": sum(1 for row in rows if row.get("has_any_social") is True),
        "metadata_completeness_median": median(score_values) if score_values else None,
        "metadata_source_mix": dict(Counter(str(row.get("metadata_source") or "unknown") for row in rows)),
        "metadata_latest_only_count": sum(1 for row in rows if row.get("metadata_is_latest_only") is True),
        "metadata_point_in_time_count": sum(1 for row in rows if row.get("metadata_is_point_in_time") is True),
        "metadata_failures": sum(1 for row in rows if str(row.get("metadata_fetch_status") or "") in {"failed", "error"}),
        "dexscreener_coverage": sum(1 for row in rows if row.get("dexscreener_pair_present") is True),
        "lifecycle_point_counts": dict(rows_by_point),
    }
    paths = {
        "json": config.report_root / "metadata_coverage_audit.json",
        "markdown": config.report_root / "metadata_coverage_audit.md",
    }
    _write_json(paths["json"], summary)
    paths["markdown"].write_text(_metadata_coverage_markdown(summary), encoding="utf-8")
    _write_json(config.metadata_status_path, summary)
    return summary, paths


def classify_narrative(name: str | None, symbol: str | None, description: str | None) -> dict[str, Any]:
    text = " ".join(str(value or "").lower() for value in [name, symbol, description])
    buckets = {
        "ai": [" ai ", "gpt", "bot", "agent", "robot", "neural"],
        "animal": ["dog", "cat", "frog", "pepe", "shib", "doge", "monkey", "ape"],
        "politics": ["trump", "biden", "maga", "president", "election", "senate"],
        "celebrity": ["elon", "taylor", "kanye", "drake", "celebrity"],
        "crypto_meta": ["solana", "bitcoin", "ethereum", "pump", "degen", "hodl"],
        "internet_culture": ["meme", "viral", "tiktok", "reddit", "wojak", "chad"],
        "event_driven": ["breaking", "launch", "event", "news", "war", "world cup"],
        "generic_meme": ["moon", "safe", "baby", "inu"],
    }
    flags = {key: any(term in f" {text} " for term in terms) for key, terms in buckets.items()}
    ordered = ["ai", "animal", "politics", "celebrity", "crypto_meta", "internet_culture", "event_driven", "generic_meme"]
    bucket = next((key for key in ordered if flags[key]), "unknown")
    confidence = 0.0 if bucket == "unknown" else min(1.0, 0.45 + 0.1 * sum(1 for value in flags.values() if value))
    return {
        "narrative_bucket": bucket,
        "topicality_bucket": "topical" if bucket in {"politics", "celebrity", "event_driven"} else ("evergreen_meme" if bucket != "unknown" else "unknown"),
        "animal_flag": flags["animal"],
        "ai_flag": flags["ai"],
        "politics_flag": flags["politics"],
        "celebrity_flag": flags["celebrity"],
        "crypto_meta_flag": flags["crypto_meta"],
        "internet_culture_flag": flags["internet_culture"],
        "event_driven_flag": flags["event_driven"],
        "generic_meme_flag": flags["generic_meme"],
        "narrative_confidence": confidence,
        "narrative_method": "deterministic_keyword_rules",
    }


def _identity_fields(payload: dict[str, Any]) -> dict[str, Any]:
    collection = payload.get("collection") if isinstance(payload.get("collection"), dict) else {}
    return {
        "token_name": payload.get("token_name") or payload.get("name"),
        "token_symbol": payload.get("token_symbol") or payload.get("symbol"),
        "token_description": payload.get("token_description") or payload.get("description"),
        "metadata_uri": payload.get("metadata_uri") or payload.get("uri"),
        "image_uri": payload.get("image_uri") or payload.get("image"),
        "external_url": payload.get("external_url") or payload.get("website"),
        "seller_fee_basis_points": payload.get("seller_fee_basis_points"),
        "collection_name": payload.get("collection_name") or collection.get("name"),
        "token_standard": payload.get("token_standard"),
    }


def _social_fields(payload: dict[str, Any]) -> dict[str, Any]:
    extracted = _extract_socials(payload)
    urls = [
        extracted.get("website_url"),
        extracted.get("twitter_x_url"),
        extracted.get("telegram_url"),
        extracted.get("discord_url"),
        extracted.get("github_url"),
        extracted.get("medium_url"),
        extracted.get("instagram_url"),
        extracted.get("tiktok_url"),
        extracted.get("youtube_url"),
        extracted.get("linktree_url"),
        payload.get("external_url"),
    ]
    other = extracted.get("other_social_urls") or []
    count = len({str(url) for url in urls + other if url})
    return {
        **extracted,
        "social_link_count": count,
        "has_website": bool(extracted.get("website_url") or payload.get("external_url") or payload.get("website")),
        "has_twitter_x": bool(extracted.get("twitter_x_url")),
        "has_telegram": bool(extracted.get("telegram_url")),
        "has_discord": bool(extracted.get("discord_url")),
        "has_any_social": count > 0,
        "has_external_url": bool(payload.get("external_url")),
    }


def _media_fields(payload: dict[str, Any]) -> dict[str, Any]:
    identity = _identity_fields(payload)
    image_uri = str(identity.get("image_uri") or "")
    metadata_uri = str(identity.get("metadata_uri") or "")
    return {
        "image_present": bool(image_uri),
        "image_uri_present": bool(image_uri),
        "image_uri_scheme": _scheme(image_uri),
        "image_domain": _domain(image_uri),
        "metadata_uri_scheme": _scheme(metadata_uri),
        "metadata_domain": _domain(metadata_uri),
        "metadata_json_available": bool(payload.get("metadata_json_available", False)),
        "metadata_json_valid": bool(payload.get("metadata_json_valid", False)),
        "metadata_json_size_bytes": payload.get("metadata_json_size_bytes"),
    }


def _name_features(name: str | None, symbol: str | None) -> dict[str, Any]:
    name_text = str(name or "")
    symbol_text = str(symbol or "")
    return {
        "token_name_length": len(name_text),
        "token_symbol_length": len(symbol_text),
        "token_name_has_emoji_like_text": bool(re.search(r":[a-z0-9_+-]+:", name_text.lower())),
        "token_symbol_has_emoji_like_text": bool(re.search(r":[a-z0-9_+-]+:", symbol_text.lower())),
        "token_name_has_number": any(char.isdigit() for char in name_text),
        "token_symbol_has_number": any(char.isdigit() for char in symbol_text),
        "token_name_uppercase_ratio": _uppercase_ratio(name_text),
        "token_symbol_uppercase_ratio": _uppercase_ratio(symbol_text),
        "name_symbol_similarity": _simple_similarity(name_text, symbol_text),
        "name_contains_ticker_style": bool(re.search(r"\$[a-z0-9]{2,12}", name_text.lower())),
        "symbol_contains_dollar_sign": "$" in symbol_text,
        "symbol_is_generic": symbol_text.lower().strip("$") in {"meme", "coin", "token", "sol", "moon", "pump", "baby"},
        "name_is_generic": name_text.lower().strip() in {"meme", "coin", "token", "solana", "moon", "pump"},
    }


def _extract_socials(payload: dict[str, Any]) -> dict[str, Any]:
    values = dict(payload)
    links = values.get("links") if isinstance(values.get("links"), dict) else {}
    extensions = values.get("extensions") if isinstance(values.get("extensions"), dict) else {}
    values.update({key: value for key, value in links.items() if key not in values})
    values.update({key: value for key, value in extensions.items() if key not in values})
    socials = values.get("socials") if isinstance(values.get("socials"), list) else []
    for item in socials:
        if not isinstance(item, dict):
            continue
        platform = str(item.get("type") or item.get("platform") or "").lower()
        url = item.get("url")
        if platform and url:
            values.setdefault(platform, url)
    urls = {
        "website_url": values.get("website_url") or values.get("website"),
        "twitter_x_url": values.get("twitter_x_url") or values.get("twitter") or values.get("x"),
        "telegram_url": values.get("telegram_url") or values.get("telegram"),
        "discord_url": values.get("discord_url") or values.get("discord"),
        "github_url": values.get("github_url") or values.get("github"),
        "medium_url": values.get("medium_url") or values.get("medium"),
        "instagram_url": values.get("instagram_url") or values.get("instagram"),
        "tiktok_url": values.get("tiktok_url") or values.get("tiktok"),
        "youtube_url": values.get("youtube_url") or values.get("youtube"),
        "linktree_url": values.get("linktree_url") or values.get("linktree"),
    }
    other = values.get("other_social_urls")
    if not isinstance(other, list):
        other = []
    return {**urls, "other_social_urls": other}


def _metadata_completeness(identity: dict[str, Any], socials: dict[str, Any], media: dict[str, Any]) -> int:
    checks = [
        identity.get("token_name"),
        identity.get("token_symbol"),
        identity.get("token_description"),
        identity.get("metadata_uri"),
        identity.get("image_uri"),
        identity.get("external_url"),
        socials.get("has_any_social"),
        media.get("metadata_json_valid"),
        identity.get("collection_name"),
        identity.get("token_standard"),
    ]
    return sum(1 for value in checks if bool(value))


def _metadata_quality_bucket(score: int) -> str:
    if score >= 8:
        return "high"
    if score >= 5:
        return "medium"
    if score >= 2:
        return "low"
    return "missing_or_sparse"


def _metadata_summary_row(snapshot: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "sample_label",
        "mint",
        "observed_at",
        "lifecycle_point",
        "metadata_source",
        "metadata_fetch_status",
        "token_name",
        "token_symbol",
        "metadata_uri",
        "image_uri",
        "website_url",
        "twitter_x_url",
        "telegram_url",
        "discord_url",
        "social_link_count",
        "metadata_completeness_score",
        "metadata_quality_bucket",
        "narrative_bucket",
        "metadata_is_point_in_time",
        "metadata_is_latest_only",
        "metadata_backfilled_after_collection",
    ]
    return {key: snapshot.get(key) for key in keys}


def _write_metadata_status(config: OfficialLifecycleConfig, queue: ForwardMetadataEnrichmentQueue) -> None:
    payload = {
        "sample_label": config.sample_label,
        "updated_at": _utc_now_iso(),
        "metadata_queue_pending": queue.pending_count,
        "metadata_jobs_submitted": queue.jobs_submitted,
        "metadata_jobs_written": queue.jobs_written,
        "metadata_jobs_rejected": queue.jobs_rejected,
        "metadata_queue_enabled": True,
    }
    _write_json(config.metadata_status_path, payload)


def _metadata_coverage_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Metadata Coverage Audit",
        "",
        f"Metadata snapshots: {summary['metadata_snapshots']}",
        f"Unique mints with metadata: {summary['unique_mints_with_metadata']}",
        f"Birth metadata coverage: {summary['birth_metadata_coverage']}",
        f"10k metadata coverage: {summary['10k_metadata_coverage']}",
        f"20k metadata coverage: {summary['20k_metadata_coverage']}",
        f"Maturity metadata coverage: {summary['maturity_metadata_coverage']}",
        f"Token name coverage: {summary['token_name_coverage']}",
        f"Symbol coverage: {summary['symbol_coverage']}",
        f"Image URI coverage: {summary['image_uri_coverage']}",
        f"Any social coverage: {summary['any_social_coverage']}",
        f"Metadata completeness median: {summary['metadata_completeness_median']}",
        f"Metadata source mix: {summary['metadata_source_mix']}",
        f"Metadata failures: {summary['metadata_failures']}",
        f"DexScreener coverage: {summary['dexscreener_coverage']}",
    ]
    return "\n".join(lines) + "\n"


def _normalize_lifecycle_point(point: str) -> str:
    point = str(point or "unknown").lower()
    aliases = {"10k": "crossed_10k", "15k": "crossed_15k", "20k": "crossed_20k", "50k": "crossed_50k", "100k": "crossed_100k", "500k": "crossed_500k", "1m": "crossed_1m"}
    return aliases.get(point, point)


def _has_identity_or_profile(payload: dict[str, Any]) -> bool:
    return any(payload.get(key) for key in ["token_name", "name", "token_symbol", "symbol", "metadata_uri", "uri", "image_uri", "image"])


def _metadata_source_from_payload(payload: dict[str, Any]) -> str:
    if _has_identity_or_profile(payload):
        return "pumpfun_create_transaction"
    return "missing"


def _safe_public_metadata_uri(uri: str) -> bool:
    parsed = urlparse(uri)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _collection_name(payload: dict[str, Any]) -> str | None:
    collection = payload.get("collection") if isinstance(payload.get("collection"), dict) else {}
    return collection.get("name") or payload.get("collection_name")


def _scheme(uri: str) -> str | None:
    return urlparse(uri).scheme or None if uri else None


def _domain(uri: str) -> str | None:
    return urlparse(uri).netloc or None if uri else None


def _uppercase_ratio(text: str) -> float | None:
    letters = [char for char in text if char.isalpha()]
    if not letters:
        return None
    return sum(1 for char in letters if char.isupper()) / len(letters)


def _simple_similarity(name: str, symbol: str) -> float | None:
    left = set(re.sub(r"[^a-z0-9]", "", name.lower()))
    right = set(re.sub(r"[^a-z0-9]", "", symbol.lower().strip("$")))
    if not left or not right:
        return None
    return len(left & right) / len(left | right)


def _num(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
