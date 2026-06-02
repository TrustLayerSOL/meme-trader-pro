"""DexScreener pair-detection enrichment for migration/graduation readiness."""

from __future__ import annotations

import json
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from research.mtp_research.data_paths import data_lake_path
from research.mtp_research.ingestion.dexscreener_real_ingest import DexScreenerRealIngestor, KNOWN_QUOTE_MINTS


READINESS_READY = "dexscreener_pair_labels_ready_for_readiness_audit"
READINESS_DRY_RUN = "dexscreener_pair_labels_dry_run"
READINESS_BLOCKED = "dexscreener_pair_labels_blocked"

DEFAULT_CANDIDATES_PATH = data_lake_path(
    "data", "normalized", "launch_lifecycle_collected_classified", "launch_regime_candidates.jsonl"
)
DEFAULT_JSONL_PATH = data_lake_path(
    "data", "backtests", "migration_graduation", "dexscreener_pair_graduation_labels.jsonl"
)
DEFAULT_PARQUET_PATH = data_lake_path(
    "data", "backtests", "migration_graduation", "dexscreener_pair_graduation_labels.parquet"
)
DEFAULT_REPORT_DIR = data_lake_path(
    "data", "backtests", "diagnostics", "reports", "dexscreener_pair_graduation_enrichment"
)


def run_dexscreener_pair_graduation_enrichment(
    *,
    candidates_path: Path | str = DEFAULT_CANDIDATES_PATH,
    mint_limit: int = 3000,
    batch_size: int = 30,
    request_ceiling: int = 150,
    execute: bool = False,
    output_paths: dict[str, Path | str] | None = None,
    ingestor: Any | None = None,
) -> dict[str, Any]:
    started = time.time()
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")
    if request_ceiling < 1:
        raise ValueError("request_ceiling must be >= 1")
    paths = _resolve_paths(output_paths)
    candidates = _read_candidates(Path(candidates_path))[:mint_limit]
    batches = [candidates[i : i + batch_size] for i in range(0, len(candidates), batch_size)]
    projected_requests = len(batches)
    base = _base_report(
        candidates_path=candidates_path,
        paths=paths,
        execute=execute,
        mint_limit=mint_limit,
        batch_size=batch_size,
        candidates=candidates,
        projected_requests=projected_requests,
        request_ceiling=request_ceiling,
        started=started,
    )
    if not execute:
        report = {
            **base,
            "readiness_classification": READINESS_DRY_RUN,
            "warnings": ["dry_run_only_no_network_calls"],
        }
        _write_reports(report, paths)
        return report
    if projected_requests > request_ceiling:
        report = {
            **base,
            "readiness_classification": READINESS_BLOCKED,
            "requests": {**base["requests"], "stopped_due_ceiling": True},
            "warnings": ["projected_requests_above_request_ceiling"],
        }
        _write_reports(report, paths)
        return report

    client = ingestor or DexScreenerRealIngestor()
    pair_rows_by_mint: dict[str, list[dict[str, Any]]] = {}
    requests_used = 0
    provider_errors: list[str] = []
    for batch in batches:
        mints = [row["mint"] for row in batch]
        if requests_used + 1 > request_ceiling:
            break
        try:
            pair_rows = list(client.fetch_tokens(mints))
        except Exception as exc:
            provider_errors.append(str(exc))
            break
        requests_used += 1
        for pair in pair_rows:
            mint = _pair_token_mint(pair)
            if mint:
                pair_rows_by_mint.setdefault(mint, []).append(pair)

    labels = [_label_for_candidate(candidate, pair_rows_by_mint.get(candidate["mint"], [])) for candidate in candidates]
    _write_jsonl(paths["jsonl_path"], labels)
    _write_parquet(labels, paths["parquet_path"])
    report = _final_report(
        base=base,
        labels=labels,
        requests_used=requests_used,
        provider_errors=provider_errors,
        started=started,
    )
    _write_reports(report, paths)
    return report


def _read_candidates(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            mint = row.get("token_mint") or row.get("mint")
            if not mint:
                continue
            metadata = row.get("metadata_json") or {}
            rows.append(
                {
                    "launch_id": row.get("launch_id"),
                    "mint": mint,
                    "creator": row.get("creator") or row.get("creator_deployer") or metadata.get("creator_deployer"),
                    "launch_ts": _int_or_none(row.get("launch_ts") or row.get("block_time")),
                    "launch_time": row.get("launch_time_utc") or row.get("launch_time"),
                }
            )
    return rows


def _label_for_candidate(candidate: dict[str, Any], pairs: list[dict[str, Any]]) -> dict[str, Any]:
    pair = _best_pair(candidate, pairs)
    base = {
        "launch_id": candidate.get("launch_id"),
        "mint": candidate["mint"],
        "creator": candidate.get("creator"),
        "launch_ts": candidate.get("launch_ts"),
        "launch_time": candidate.get("launch_time"),
        "pumpfun_migrate_event_observed": False,
        "graduated_to_pumpswap": False,
        "migrated_to_raydium": False,
        "dex_pair_detected": False,
        "liquidity_pool_created_after_launch": False,
        "migration_time": None,
        "migration_signature": None,
        "migration_source": None,
        "migration_confidence": 0.0,
        "migration_missing_reason": "no_dexscreener_pair_detected",
        "pair_address": None,
        "dex_id": None,
        "dexscreener_url": None,
        "pair_created_at": None,
        "liquidity_usd": None,
        "fdv": None,
        "market_cap": None,
    }
    if not pair:
        return base
    pair_created_ts = _pair_created_ts(pair)
    dex_id = str(pair.get("dexId") or "").lower()
    liquidity_pool_after_launch = (
        pair_created_ts is not None
        and candidate.get("launch_ts") is not None
        and pair_created_ts >= int(candidate["launch_ts"])
    )
    migration_time = _timestamp(pair_created_ts) if pair_created_ts is not None else None
    return {
        **base,
        "graduated_to_pumpswap": "pump" in dex_id,
        "migrated_to_raydium": "raydium" in dex_id,
        "dex_pair_detected": True,
        "liquidity_pool_created_after_launch": liquidity_pool_after_launch,
        "migration_time": migration_time,
        "migration_source": "dexscreener_pair_created_at",
        "migration_confidence": 0.55 if migration_time else 0.35,
        "migration_missing_reason": None if migration_time else "dex_pair_detected_missing_pair_created_at",
        "pair_address": pair.get("pairAddress"),
        "dex_id": pair.get("dexId"),
        "dexscreener_url": pair.get("url"),
        "pair_created_at": pair.get("pairCreatedAt"),
        "liquidity_usd": _nested_float(pair, "liquidity", "usd"),
        "fdv": _float_or_none(pair.get("fdv")),
        "market_cap": _float_or_none(pair.get("marketCap")),
    }


def _best_pair(candidate: dict[str, Any], pairs: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidate_mint = candidate["mint"]
    matching = [pair for pair in pairs if _pair_token_mint(pair) == candidate_mint and pair.get("chainId") == "solana"]
    if not matching:
        return None
    launch_ts = candidate.get("launch_ts")
    after_launch = [
        pair for pair in matching
        if launch_ts is not None and _pair_created_ts(pair) is not None and _pair_created_ts(pair) >= int(launch_ts)
    ]
    pool = after_launch or matching
    return sorted(pool, key=lambda pair: (_pair_created_ts(pair) is None, _pair_created_ts(pair) or 0, -(_nested_float(pair, "liquidity", "usd") or 0)))[0]


def _pair_token_mint(pair: dict[str, Any]) -> str | None:
    base = pair.get("baseToken") if isinstance(pair.get("baseToken"), dict) else {}
    quote = pair.get("quoteToken") if isinstance(pair.get("quoteToken"), dict) else {}
    base_address = base.get("address")
    quote_address = quote.get("address")
    if base_address in KNOWN_QUOTE_MINTS:
        return quote_address
    return base_address or quote_address


def _final_report(
    *,
    base: dict[str, Any],
    labels: list[dict[str, Any]],
    requests_used: int,
    provider_errors: list[str],
    started: float,
) -> dict[str, Any]:
    detected = [row for row in labels if row.get("dex_pair_detected")]
    after_launch = [row for row in labels if row.get("liquidity_pool_created_after_launch")]
    by_dex = Counter(str(row.get("dex_id") or "none") for row in detected)
    missing_reasons = Counter(row.get("migration_missing_reason") or "none" for row in labels)
    return {
        **base,
        "readiness_classification": READINESS_BLOCKED if provider_errors else READINESS_READY,
        "execution": {**base["execution"], "elapsed_seconds": round(time.time() - started, 3)},
        "requests": {**base["requests"], "requests_used": requests_used, "stopped_due_ceiling": False},
        "collection": {
            "candidate_rows_written": len(labels),
            "dex_pair_detected_count": len(detected),
            "liquidity_pool_created_after_launch_count": len(after_launch),
            "unique_pair_mints_detected": len({row["mint"] for row in detected}),
            "dex_counts": dict(by_dex),
            "missing_reason_counts": dict(missing_reasons),
        },
        "provider": {"errors": provider_errors},
        "warnings": ["provider_errors_seen"] if provider_errors else [],
    }


def _base_report(
    *,
    candidates_path: Path | str,
    paths: dict[str, Path],
    execute: bool,
    mint_limit: int,
    batch_size: int,
    candidates: list[dict[str, Any]],
    projected_requests: int,
    request_ceiling: int,
    started: float,
) -> dict[str, Any]:
    return {
        "report_id": "dexscreener_pair_graduation_enrichment_v0",
        "execution": {
            "mode": "execute" if execute else "dry_run",
            "started_at": _timestamp(int(started)),
            "elapsed_seconds": 0.0,
        },
        "scope": {
            "candidates_path": str(candidates_path),
            "mint_limit": mint_limit,
            "selected_mints": len(candidates),
            "batch_size": batch_size,
        },
        "requests": {
            "projected_requests": projected_requests,
            "request_ceiling": request_ceiling,
            "request_ceiling_status": "within_ceiling" if projected_requests <= request_ceiling else "above_ceiling",
            "requests_used": 0,
            "stopped_due_ceiling": False,
        },
        "outputs": {key: str(value) for key, value in paths.items()},
        "guardrails": {
            "thesis_runs": 0,
            "backtests_run": 0,
            "validation_runs": 0,
            "paper_trading_runs": 0,
            "live_trading_runs": 0,
            "trading_logic_added": False,
            "threshold_optimization": False,
            "grid_search": False,
            "ml": False,
        },
    }


def _write_reports(report: dict[str, Any], paths: dict[str, Path]) -> None:
    paths["report_dir"].mkdir(parents=True, exist_ok=True)
    (paths["report_dir"] / "dexscreener_pair_graduation_enrichment.json").write_text(
        json.dumps(report, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (paths["report_dir"] / "dexscreener_pair_graduation_enrichment.md").write_text(_markdown(report), encoding="utf-8")


def _markdown(report: dict[str, Any]) -> str:
    collection = report.get("collection", {})
    lines = [
        "# DexScreener Pair Graduation Enrichment",
        "",
        f"- Readiness classification: `{report.get('readiness_classification')}`",
        f"- Mode: `{report['execution']['mode']}`",
        f"- Selected mints: `{report['scope']['selected_mints']}`",
        f"- Requests used: `{report['requests']['requests_used']}`",
        f"- Dex pair detected: `{collection.get('dex_pair_detected_count', 0)}`",
        f"- Liquidity pool created after launch: `{collection.get('liquidity_pool_created_after_launch_count', 0)}`",
        f"- Dex counts: `{collection.get('dex_counts', {})}`",
        f"- Warnings: `{report.get('warnings', [])}`",
        "",
        "This is pair-detection enrichment only. It is not a thesis, backtest, validation, paper/live trading, or strategy workflow.",
    ]
    return "\n".join(lines) + "\n"


def _resolve_paths(output_paths: dict[str, Path | str] | None) -> dict[str, Path]:
    supplied = output_paths or {}
    return {
        "jsonl_path": Path(supplied.get("jsonl_path", DEFAULT_JSONL_PATH)),
        "parquet_path": Path(supplied.get("parquet_path", DEFAULT_PARQUET_PATH)),
        "report_dir": Path(supplied.get("report_dir", DEFAULT_REPORT_DIR)),
    }


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")


def _write_parquet(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    import pandas as pd

    pd.DataFrame(rows).to_parquet(path, index=False)


def _pair_created_ts(pair: dict[str, Any]) -> int | None:
    value = _int_or_none(pair.get("pairCreatedAt"))
    if value is None:
        return None
    return value // 1000 if value > 10_000_000_000 else value


def _timestamp(value: int | None) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _nested_float(row: dict[str, Any], *keys: str) -> float | None:
    value: Any = row
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return _float_or_none(value)
