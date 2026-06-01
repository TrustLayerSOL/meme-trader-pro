from datetime import datetime, timezone
from pathlib import Path

from research.mtp_research.ingestion.candidate_registry import CandidateRegistry
from research.mtp_research.ingestion.models import LaunchCandidate
from research.mtp_research.pipeline.run_time_span_backfill_plan import main


def test_time_span_backfill_plan_cli_runs_without_network(tmp_path: Path, monkeypatch, capsys) -> None:
    registry_path = tmp_path / "registry.jsonl"
    raw_path = tmp_path / "raw.jsonl"
    event_path = tmp_path / "events.jsonl"
    feature_path = tmp_path / "features.jsonl"
    outcome_path = tmp_path / "outcomes.jsonl"
    dataset_path = tmp_path / "dataset.jsonl"
    output_dir = tmp_path / "reports"
    CandidateRegistry(registry_path).upsert(
        LaunchCandidate(
            token_mint="token-1",
            source="dexscreener",
            first_seen_ts=datetime(2026, 5, 31, tzinfo=timezone.utc),
            venue="raydium",
            pool_address="pool-1",
            liquidity_usd=20000,
        )
    )

    monkeypatch.setattr(
        "sys.argv",
        [
            "run_time_span_backfill_plan",
            "--registry-path",
            str(registry_path),
            "--raw-store-path",
            str(raw_path),
            "--event-store-path",
            str(event_path),
            "--feature-store-path",
            str(feature_path),
            "--outcome-store-path",
            str(outcome_path),
            "--dataset-path",
            str(dataset_path),
            "--output-dir",
            str(output_dir),
            "--candidate-limit",
            "1",
        ],
    )

    assert main() == 0
    output = capsys.readouterr().out
    assert "real_candidates_found=1" in output
    assert "plan_item_count=1" in output
    assert "network_calls=0" in output
    assert list(output_dir.glob("time_span_backfill_plan_*.md"))
    assert list(output_dir.glob("time_span_backfill_plan_*.json"))
