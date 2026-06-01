import json
from datetime import datetime, timezone
from pathlib import Path

from research.mtp_research.ingestion.candidate_registry import CandidateRegistry
from research.mtp_research.ingestion.models import LaunchCandidate
from research.mtp_research.launch_regime.models import LaunchRegimeCandidate
from research.mtp_research.launch_regime.store import JsonlArtifactStore
from research.mtp_research.validation.discovery_source_bias_audit import run_discovery_source_bias_audit


def _candidate(token: str, source: str, pool: str | None = "pool") -> LaunchCandidate:
    return LaunchCandidate(
        token_mint=token,
        source=source,
        first_seen_ts=datetime(2026, 6, 1, 13, tzinfo=timezone.utc),
        venue="pumpswap",
        pool_address=pool,
        metadata_json={"is_mock": source == "mock"},
    )


def _launch(token: str, source: str, metadata: dict | None = None) -> LaunchRegimeCandidate:
    return LaunchRegimeCandidate(
        launch_id=f"launch-{token}",
        token_mint=token,
        launch_ts=1_780_000_000,
        launch_time_utc="2026-06-01T13:00:00+00:00",
        launch_weekday="Monday",
        launch_hour_local=6,
        launch_minute_local=0,
        launch_day_of_week=0,
        launch_is_weekend=False,
        launch_regime="mon_tue_wed_0600_1200_pt",
        source=source,
        pool_address="pool" if token != "no-pool" else None,
        venue="pumpswap",
        metadata_json=metadata or {},
    )


def test_source_bias_audit_counts_source_venue_regime_and_writes_reports(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.jsonl"
    lifecycle_path = tmp_path / "launches.jsonl"
    output_dir = tmp_path / "reports"
    registry = CandidateRegistry(registry_path)
    registry.upsert(_candidate("mint-1", "dexscreener_real"))
    registry.upsert(_candidate("mint-2", "jupiter_recent", pool=None))
    JsonlArtifactStore(lifecycle_path).write_all(
        [
            _launch("mint-1", "dexscreener_real", {"launch_timestamp_source": "verified_pair_creation"}),
            _launch(
                "no-pool",
                "normalized_event_first_seen",
                {"launch_timestamp_quality": "first_observed_event_not_verified_pair_creation"},
            ),
        ]
    )

    report = run_discovery_source_bias_audit(registry_path, lifecycle_path, output_dir)

    assert report["registry_source_counts"]["dexscreener_real"] == 1
    assert report["registry_source_counts"]["jupiter_recent"] == 1
    assert report["lifecycle_source_counts"]["event_inferred"] == 1
    assert report["venue_counts"]["pumpswap"] == 2
    assert report["launch_regime_counts"]["mon_tue_wed_0600_1200_pt"] == 2
    assert report["pool_address_counts"]["with_pool_address"] == 1
    assert report["launch_timestamp_confidence_counts"]["verified"] == 1
    assert report["launch_timestamp_confidence_counts"]["inferred"] == 1
    assert (output_dir / "discovery_source_bias_audit.md").exists()
    assert json.loads((output_dir / "discovery_source_bias_audit.json").read_text(encoding="utf-8"))["lifecycle_launch_count"] == 2


def test_dexscreener_concentration_warning_fires(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.jsonl"
    lifecycle_path = tmp_path / "launches.jsonl"
    output_dir = tmp_path / "reports"
    registry = CandidateRegistry(registry_path)
    for idx in range(4):
        registry.upsert(_candidate(f"mint-{idx}", "dexscreener_real"))
    JsonlArtifactStore(lifecycle_path).write_all([_launch(f"mint-{idx}", "dexscreener_real") for idx in range(4)])

    report = run_discovery_source_bias_audit(registry_path, lifecycle_path, output_dir)

    assert "dexscreener_survivorship_risk" in report["warning_flags"]
    assert "source_concentration_dexscreener_visible" in report["warning_flags"]
