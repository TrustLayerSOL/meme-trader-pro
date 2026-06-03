import json
from pathlib import Path

import pandas as pd

from research.mtp_research.validation.run_tier1_tier2_enrichment import main


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    return path


def test_cli_writes_tier1_tier2_outputs(tmp_path: Path, monkeypatch, capsys) -> None:
    master = tmp_path / "master.parquet"
    events = tmp_path / "events.jsonl"
    status = tmp_path / "TIER1_TIER2_ENRICHMENT_STATUS.md"
    output_root = tmp_path / "orico"
    pd.DataFrame(
        [
            {
                "launch_id": "L1",
                "mint": "Mint1",
                "token_mint": "Mint1",
                "creator": "Creator1",
                "launch_ts": 1_700_000_000,
                "early_buyer_wallet_count": 1,
                "early_buyer_with_prior_runner_count": 1,
            }
        ]
    ).to_parquet(master, index=False)
    _write_jsonl(
        events,
        [
            {
                "token_mint": "Mint1",
                "block_time": 1_700_000_010,
                "actor": "Buyer1",
                "side": "buy",
                "quote_qty": 1.0,
                "base_qty": 10.0,
                "metadata_json": {"liquidity_proxy_sol": 5.0},
            }
        ],
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_tier1_tier2_enrichment",
            "--data-root",
            str(output_root),
            "--master-path",
            str(master),
            "--events-path",
            str(events),
            "--holder-state-path",
            str(tmp_path / "missing_holder.parquet"),
            "--entity-proxy-path",
            str(tmp_path / "missing_entity.parquet"),
            "--visibility-path",
            str(tmp_path / "missing_visibility.parquet"),
            "--metadata-quality-path",
            str(tmp_path / "missing_metadata.parquet"),
            "--topicality-path",
            str(tmp_path / "missing_topicality.parquet"),
            "--status-path",
            str(status),
            "--execute",
        ],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "report_id=tier1_tier2_enrichment_v0" in output
    assert "helius_requests_used=0" in output
    assert "launches_enriched=1" in output
    assert "master_parquet_path=" in output
    assert (
        output_root
        / "data/backtests/structural_enrichment/tier1_tier2_enrichment/master_tier1_tier2_enriched_runner_fingerprint.parquet"
    ).exists()
    assert status.exists()
