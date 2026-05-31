"""Local candidate seed loading for evidence population."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from research.mtp_research.ingestion.candidate_registry import CandidateRegistry
from research.mtp_research.ingestion.models import LaunchCandidate


def load_candidate_seeds(path: Path | str) -> list[LaunchCandidate]:
    seed_path = Path(path)
    if not seed_path.exists():
        return []
    candidates: list[LaunchCandidate] = []
    with seed_path.open("r", encoding="utf-8") as f:
        for line in f:
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
                if not payload.get("token_mint"):
                    continue
                candidates.append(_candidate_from_seed(payload))
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue
    return candidates


def write_example_seed_file(path: Path | str) -> Path:
    seed_path = Path(path)
    seed_path.parent.mkdir(parents=True, exist_ok=True)
    examples = [
        {
            "token_mint": "MockMint111111111111111111111111111111111111",
            "source": "manual_example",
            "venue": "mock",
            "first_seen_ts": "2026-05-31T00:00:00+00:00",
            "first_tradeable_ts": "2026-05-31T00:01:00+00:00",
            "pool_address": "MockPool111111111111111111111111111111111111",
            "creator_wallet": "MockCreator111111111111111111111111111111111",
            "quote_mint": "So11111111111111111111111111111111111111112",
            "metadata_json": {"example_only": True, "note": "fake/mock seed row"},
        }
    ]
    with seed_path.open("w", encoding="utf-8") as f:
        for example in examples:
            f.write(json.dumps(example, sort_keys=True))
            f.write("\n")
    return seed_path


def seed_registry_from_file(
    seed_path: Path | str,
    registry_path: Path | str | None = None,
) -> dict[str, int]:
    registry = CandidateRegistry(path=registry_path) if registry_path else CandidateRegistry()
    candidates = load_candidate_seeds(seed_path)
    counts = {"inserted": 0, "updated": 0, "skipped": 0}
    raw_rows = _count_nonempty_lines(seed_path)
    counts["skipped"] = max(raw_rows - len(candidates), 0)
    for candidate in candidates:
        counts[registry.upsert(candidate)] += 1
    return counts


def _candidate_from_seed(payload: dict[str, Any]) -> LaunchCandidate:
    return LaunchCandidate(
        token_mint=payload["token_mint"],
        source=payload.get("source", "manual_seed"),
        first_seen_ts=_parse_dt(payload.get("first_seen_ts")),
        venue=payload.get("venue"),
        first_tradeable_ts=_parse_dt(payload.get("first_tradeable_ts")) if payload.get("first_tradeable_ts") else None,
        pool_address=payload.get("pool_address"),
        creator_wallet=payload.get("creator_wallet"),
        quote_mint=payload.get("quote_mint"),
        liquidity_usd=payload.get("liquidity_usd"),
        market_cap=payload.get("market_cap"),
        dexscreener_url=payload.get("dexscreener_url"),
        jupiter_recent_seen=bool(payload.get("jupiter_recent_seen", False)),
        raydium_seen=bool(payload.get("raydium_seen", False)),
        pump_seen=bool(payload.get("pump_seen", False)),
        status=payload.get("status", "candidate"),
        metadata_json=dict(payload.get("metadata_json", {})),
    )


def _parse_dt(value: Any) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _count_nonempty_lines(path: Path | str) -> int:
    seed_path = Path(path)
    if not seed_path.exists():
        return 0
    return sum(1 for line in seed_path.read_text(encoding="utf-8").splitlines() if line.strip())
