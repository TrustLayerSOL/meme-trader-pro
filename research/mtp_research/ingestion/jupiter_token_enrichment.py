"""Optional Jupiter token metadata enrichment for v3 candidates."""

from __future__ import annotations

from research.mtp_research.ingestion.http_client import SimpleJsonHttpClient
from research.mtp_research.ingestion.models import LaunchCandidate


class JupiterTokenEnricher:
    """Conservative, mockable Jupiter token metadata enrichment.

    TODO: Verify the final production Jupiter token endpoint contract before
    relying on these fields for research quality filters.
    """

    BASE_URL = "https://lite-api.jup.ag/tokens/v2/token"

    def __init__(self, http_client: SimpleJsonHttpClient | None = None):
        self.http_client = http_client or SimpleJsonHttpClient()

    def fetch_token_info(self, token_mint: str) -> dict:
        payload = self.http_client.get_json(f"{self.BASE_URL}/{token_mint}")
        return payload if isinstance(payload, dict) else {}

    def enrich_candidate(self, candidate: LaunchCandidate) -> LaunchCandidate:
        try:
            info = self.fetch_token_info(candidate.token_mint)
            metadata = dict(candidate.metadata_json)
            metadata.update(
                {
                    "jupiter_enriched": True,
                    "organic_score": info.get("organicScore") or info.get("organic_score"),
                    "verification_status": _verification_status(info),
                    "holder_count": info.get("holderCount") or info.get("holder_count"),
                    "jupiter_liquidity": info.get("liquidity"),
                    "jupiter_market_cap": info.get("marketCap") or info.get("market_cap"),
                    "trading_stats": info.get("stats") or info.get("tradingStats") or info.get("trading_stats"),
                }
            )
            return LaunchCandidate(
                **{
                    **candidate.to_dict(),
                    "first_seen_ts": candidate.first_seen_ts,
                    "first_tradeable_ts": candidate.first_tradeable_ts,
                    "metadata_json": metadata,
                }
            )
        except Exception as exc:  # noqa: BLE001 - enrichment must not kill discovery batches
            metadata = dict(candidate.metadata_json)
            metadata["jupiter_enrichment_failed"] = True
            metadata["jupiter_enrichment_error"] = str(exc)
            return LaunchCandidate(
                **{
                    **candidate.to_dict(),
                    "first_seen_ts": candidate.first_seen_ts,
                    "first_tradeable_ts": candidate.first_tradeable_ts,
                    "metadata_json": metadata,
                }
            )

    def enrich_candidates(
        self,
        candidates: list[LaunchCandidate],
        limit: int | None = None,
    ) -> list[LaunchCandidate]:
        selected = candidates[:limit] if limit is not None else candidates
        enriched = [self.enrich_candidate(candidate) for candidate in selected]
        if limit is not None:
            enriched.extend(candidates[limit:])
        return enriched


def _verification_status(payload: dict) -> str | None:
    verification = payload.get("verification")
    if isinstance(verification, dict):
        status = verification.get("status")
        return str(status) if status is not None else None
    status = payload.get("verificationStatus") or payload.get("verification_status")
    return str(status) if status is not None else None
