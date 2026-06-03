from pathlib import Path

import pandas as pd

from research.mtp_research.validation.run_full_structural_enrichment_campaign import main


def test_cli_writes_full_structural_enrichment_campaign(tmp_path: Path, monkeypatch, capsys) -> None:
    trigger_path = tmp_path / "trigger_rows.csv"
    combined_path = tmp_path / "combined.parquet"
    output_root = tmp_path / "orico"
    pd.DataFrame(
        [
            {
                "launch_id": "L1",
                "token_mint": "Mint1",
                "creator": "Creator1",
                "launch_ts": 1_700_000_000,
                "trigger_fdv_proxy": 20_000,
                "peak_fdv_proxy": 75_000,
                "event_count_at_20k": 10,
                "buy_count_at_20k": 5,
                "sell_count_at_20k": 5,
                "active_wallets_at_20k": 4,
                "holder_count_at_20k": 3,
                "top_holder_share_at_20k": 0.4,
                "top_10_holder_share_at_20k": 0.9,
                "creator_holder_share_at_20k": 0.0,
            }
        ]
    ).to_csv(trigger_path, index=False)
    pd.DataFrame(
        [
            {
                "launch_id": "L1",
                "mint": "Mint1",
                "fdv_per_event_at_20k": 2000.0,
                "fdv_per_buy_at_20k": 4000.0,
                "fdv_per_active_wallet_at_20k": 5000.0,
            }
        ]
    ).to_parquet(combined_path, index=False)
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_full_structural_enrichment_campaign",
            "--data-root",
            str(output_root),
            "--trigger-rows-path",
            str(trigger_path),
            "--combined-repaired-path",
            str(combined_path),
            "--events-path",
            str(tmp_path / "missing_events.jsonl"),
            "--sol-usd-path",
            str(tmp_path / "missing_sol_usd.jsonl"),
            "--status-path",
            str(tmp_path / "FULL_STRUCTURAL_ENRICHMENT_CAMPAIGN_STATUS.md"),
            "--max-helius-credits",
            "500000",
        ],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "report_id=full_structural_enrichment_campaign_v0" in output
    assert "helius_execute=False" in output
    assert "credits_used=0" in output
    assert "master_rows=1" in output
    assert (
        output_root
        / "data/backtests/structural_enrichment/full_campaign/master_enriched_runner_fingerprint.parquet"
    ).exists()
