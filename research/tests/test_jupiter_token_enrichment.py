from datetime import datetime, timezone

from research.mtp_research.ingestion.jupiter_token_enrichment import JupiterTokenEnricher
from research.mtp_research.ingestion.models import LaunchCandidate


class FakeHttpClient:
    def __init__(self, payloads=None, fail=False):
        self.payloads = payloads or {}
        self.fail = fail

    def get_json(self, url: str, timeout_sec: int = 20):
        if self.fail:
            raise RuntimeError("network blocked in test")
        token = url.rsplit("/", 1)[-1]
        return self.payloads.get(token, {})


def _candidate(token_mint="mint-1") -> LaunchCandidate:
    return LaunchCandidate(
        token_mint=token_mint,
        source="dexscreener_real",
        first_seen_ts=datetime(2026, 5, 31, tzinfo=timezone.utc),
    )


def test_enrich_candidate_merges_jupiter_quality_metadata() -> None:
    enricher = JupiterTokenEnricher(
        FakeHttpClient(
            {
                "mint-1": {
                    "organicScore": 88,
                    "verification": {"status": "verified"},
                    "holderCount": 1234,
                    "liquidity": 99_000,
                    "marketCap": 1_000_000,
                    "stats": {"volume24h": 5000},
                }
            }
        )
    )

    enriched = enricher.enrich_candidate(_candidate())

    assert enriched.metadata_json["jupiter_enriched"] is True
    assert enriched.metadata_json["organic_score"] == 88
    assert enriched.metadata_json["verification_status"] == "verified"
    assert enriched.metadata_json["holder_count"] == 1234
    assert enriched.metadata_json["jupiter_liquidity"] == 99_000
    assert enriched.metadata_json["jupiter_market_cap"] == 1_000_000
    assert enriched.metadata_json["trading_stats"] == {"volume24h": 5000}


def test_enrichment_failure_does_not_crash_all_candidates() -> None:
    enriched = JupiterTokenEnricher(FakeHttpClient(fail=True)).enrich_candidates([_candidate("mint-1")])

    assert len(enriched) == 1
    assert enriched[0].metadata_json["jupiter_enrichment_failed"] is True
