from datetime import datetime, timezone
from pathlib import Path

from research.mtp_research.ingestion.candidate_registry import CandidateRegistry
from research.mtp_research.ingestion.models import LaunchCandidate
from research.mtp_research.pipeline.run_time_span_backfill_execute import main


def test_time_span_backfill_execute_dry_run_does_not_call_helius(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    registry_path = tmp_path / "registry.jsonl"
    raw_path = tmp_path / "raw.jsonl"
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
            "run_time_span_backfill_execute",
            "--registry-path",
            str(registry_path),
            "--raw-path",
            str(raw_path),
            "--candidate-limit",
            "1",
            "--max-signatures-per-target",
            "75",
            "--max-transactions-per-target",
            "75",
            "--stop-after-targets",
            "10",
        ],
    )

    assert main() == 0
    output = capsys.readouterr().out
    assert "dry_run=True" in output
    assert "execute=False" in output
    assert "targets_planned=1" in output
    assert "signatures_seen=0" in output
    assert "no_network_calls_made=True" in output
