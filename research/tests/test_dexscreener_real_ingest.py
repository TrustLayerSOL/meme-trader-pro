from datetime import datetime
from pathlib import Path

from research.mtp_research.ingestion.candidate_registry import CandidateRegistry
from research.mtp_research.ingestion.dexscreener_real_ingest import DexScreenerRealIngestor
from research.mtp_research.ingestion.discovery_models import DiscoveryRunConfig


WSOL = "So11111111111111111111111111111111111111112"


class FakeHttpClient:
    def __init__(self, responses):
        self.responses = responses
        self.urls = []

    def get_json(self, url: str, timeout_sec: int = 20):
        self.urls.append(url)
        for fragment, payload in self.responses.items():
            if fragment in url:
                return payload
        return []


def _pair(token="Token111111111111111111111111111111111111", liquidity=25_000):
    return {
        "chainId": "solana",
        "dexId": "raydium",
        "url": "https://dexscreener.com/solana/pair1",
        "pairAddress": "Pair111111111111111111111111111111111111",
        "pairCreatedAt": 1_700_000_000_000,
        "baseToken": {"address": token, "symbol": "MEME"},
        "quoteToken": {"address": WSOL, "symbol": "SOL"},
        "liquidity": {"usd": liquidity},
        "marketCap": 500_000,
        "fdv": 450_000,
        "priceUsd": "0.001",
        "volume": {"h24": 1000},
        "txns": {"h24": {"buys": 10, "sells": 5}},
        "boosts": {"active": 1},
    }


def test_discover_token_addresses_keeps_solana_dedupes_and_respects_limit() -> None:
    client = FakeHttpClient(
        {
            "token-profiles": [
                {"chainId": "solana", "tokenAddress": "token-a"},
                {"chainId": "ethereum", "tokenAddress": "token-b"},
            ],
            "token-boosts/latest": [
                {"chainId": "solana", "tokenAddress": "token-a"},
                {"chainId": "solana", "tokenAddress": "token-c"},
            ],
            "token-boosts/top": [{"chainId": "solana", "tokenAddress": "token-d"}],
        }
    )

    addresses = DexScreenerRealIngestor(client).discover_token_addresses(DiscoveryRunConfig("dex", limit=2))

    assert addresses == ["token-a", "token-c"]


def test_fetch_token_pairs_uses_expected_url() -> None:
    client = FakeHttpClient({"token-pairs": []})
    DexScreenerRealIngestor(client).fetch_token_pairs("token-a")

    assert client.urls == ["https://api.dexscreener.com/token-pairs/v1/solana/token-a"]


def test_pair_to_candidate_creates_candidate_with_pool_liquidity_and_metadata() -> None:
    candidate = DexScreenerRealIngestor().pair_to_candidate(_pair())

    assert candidate is not None
    assert candidate.token_mint == "Token111111111111111111111111111111111111"
    assert candidate.pool_address == "Pair111111111111111111111111111111111111"
    assert candidate.quote_mint == WSOL
    assert candidate.venue == "raydium"
    assert candidate.liquidity_usd == 25_000
    assert candidate.market_cap == 500_000
    assert candidate.first_tradeable_ts == datetime.fromtimestamp(1_700_000_000, tz=candidate.first_tradeable_ts.tzinfo)
    assert candidate.metadata_json["is_mock"] is False
    assert candidate.metadata_json["discovery_source"] == "dexscreener_real"


def test_pair_to_candidate_skips_missing_pair_address() -> None:
    pair = _pair()
    pair.pop("pairAddress")

    assert DexScreenerRealIngestor().pair_to_candidate(pair) is None


def test_pair_to_candidate_handles_quote_token_as_base_token() -> None:
    pair = _pair(token=WSOL)
    pair["quoteToken"] = {"address": "Token222222222222222222222222222222222222", "symbol": "MEME"}

    candidate = DexScreenerRealIngestor().pair_to_candidate(pair)

    assert candidate is not None
    assert candidate.token_mint == "Token222222222222222222222222222222222222"
    assert candidate.quote_mint == WSOL


def test_min_liquidity_filter_works() -> None:
    client = FakeHttpClient(
        {
            "token-profiles": [{"chainId": "solana", "tokenAddress": "token-a"}],
            "token-pairs": [_pair(liquidity=100)],
        }
    )

    candidates = DexScreenerRealIngestor(client).build_candidates(
        DiscoveryRunConfig("dexscreener", limit=1, include_boosts=False, include_top_boosts=False, min_liquidity_usd=10_000)
    )

    assert candidates == []


def test_run_discovery_dry_run_does_not_write(tmp_path: Path) -> None:
    client = FakeHttpClient(
        {
            "token-profiles": [{"chainId": "solana", "tokenAddress": "token-a"}],
            "token-pairs": [_pair()],
        }
    )
    registry = CandidateRegistry(tmp_path / "registry.jsonl")

    summary = DexScreenerRealIngestor(client).run_discovery(
        DiscoveryRunConfig("dexscreener", limit=1, include_boosts=False, include_top_boosts=False, dry_run=True, write=True),
        registry,
    )

    assert summary.candidates_built == 1
    assert summary.candidates_inserted == 0
    assert registry.load_all() == []


def test_run_discovery_write_mode_upserts_candidates(tmp_path: Path) -> None:
    client = FakeHttpClient(
        {
            "token-profiles": [{"chainId": "solana", "tokenAddress": "token-a"}],
            "token-pairs": [_pair()],
        }
    )
    registry = CandidateRegistry(tmp_path / "registry.jsonl")

    summary = DexScreenerRealIngestor(client).run_discovery(
        DiscoveryRunConfig("dexscreener", limit=1, include_boosts=False, include_top_boosts=False, dry_run=False, write=True),
        registry,
    )

    assert summary.candidates_inserted == 1
    assert registry.load_all()[0].metadata_json["is_mock"] is False
