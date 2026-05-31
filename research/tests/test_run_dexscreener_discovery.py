from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from research.mtp_research.ingestion.candidate_registry import CandidateRegistry
from research.mtp_research.ingestion.discovery_models import DiscoveryRunSummary
from research.mtp_research.ingestion.models import LaunchCandidate
from research.mtp_research.ingestion.run_dexscreener_discovery import main


@dataclass
class FakeIngestor:
    candidate: LaunchCandidate = field(
        default_factory=lambda: LaunchCandidate(
            token_mint="real-mint",
            source="dexscreener_real",
            first_seen_ts=datetime(2026, 5, 31, tzinfo=timezone.utc),
            venue="raydium",
            pool_address="real-pool",
            liquidity_usd=25_000,
            dexscreener_url="https://dexscreener.com/solana/real-pool",
            metadata_json={"is_mock": False},
        )
    )

    def build_candidates(self, _config):
        return [self.candidate]

    def run_discovery(self, config, registry=None):
        summary = DiscoveryRunSummary(
            source="dexscreener",
            dry_run=config.dry_run,
            write=config.write,
            raw_items_seen=1,
            solana_items_seen=1,
            token_addresses_seen=1,
            pair_records_seen=1,
            candidates_built=1,
            candidates_after_filters=1,
            metadata_json={"candidate_summaries": [self.candidate.to_dict()]},
        )
        if config.write and not config.dry_run and registry is not None:
            result = registry.upsert(self.candidate)
            summary.candidates_inserted = 1 if result == "inserted" else 0
        return summary


def test_dexscreener_discovery_dry_run_does_not_write(tmp_path: Path, monkeypatch, capsys) -> None:
    registry_path = tmp_path / "registry.jsonl"
    monkeypatch.setattr("research.mtp_research.ingestion.run_dexscreener_discovery.DexScreenerRealIngestor", FakeIngestor)
    monkeypatch.setattr(
        "sys.argv",
        ["run_dexscreener_discovery", "--registry-path", str(registry_path), "--limit", "1"],
    )

    assert main() == 0
    output = capsys.readouterr().out
    assert "candidates_built=1" in output
    assert "candidate token_mint=real-mint venue=raydium pool_address=real-pool liquidity_usd=25000" in output
    assert CandidateRegistry(registry_path).load_all() == []


def test_dexscreener_discovery_write_mode_writes_temp_registry(tmp_path: Path, monkeypatch) -> None:
    registry_path = tmp_path / "registry.jsonl"
    monkeypatch.setattr("research.mtp_research.ingestion.run_dexscreener_discovery.DexScreenerRealIngestor", FakeIngestor)
    monkeypatch.setattr(
        "sys.argv",
        ["run_dexscreener_discovery", "--registry-path", str(registry_path), "--limit", "1", "--write"],
    )

    assert main() == 0
    assert CandidateRegistry(registry_path).load_all()[0].token_mint == "real-mint"
