import json
from pathlib import Path

import pandas as pd

from research.mtp_research.validation.run_historical_rule_discovery import main


def test_run_historical_rule_discovery_cli_execute(tmp_path: Path, monkeypatch, capsys) -> None:
    _write_minimal_lake(tmp_path)
    monkeypatch.setattr("sys.argv", ["run_historical_rule_discovery", "--data-root", str(tmp_path), "--execute"])

    assert main() == 0

    output = capsys.readouterr().out
    assert "## Historical Rule Discovery" in output
    report_root = tmp_path / "data" / "backtests" / "diagnostics" / "reports" / "historical_rule_discovery"
    assert (report_root / "historical_rule_discovery_summary.json").exists()
    summary = json.loads((report_root / "historical_rule_discovery_summary.json").read_text(encoding="utf-8"))
    assert summary["live_trading_enabled"] is False


def test_run_historical_rule_discovery_cli_dry_run(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr("sys.argv", ["run_historical_rule_discovery", "--data-root", str(tmp_path)])

    assert main() == 0

    output = capsys.readouterr().out
    assert "execute=False" in output


def _write_minimal_lake(root: Path) -> None:
    full = root / "data" / "backtests" / "structural_enrichment" / "full_campaign"
    full.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "launch_id": "launch-a",
                "mint": "mint-a",
                "launch_date": "2026-01-01",
                "launch_ts": 1767225600,
                "milestone_tier": "reached_100k_but_never_500k",
                "peak_fdv_proxy": 120_000,
                "fdv_per_event_at_20k": 7_000,
                "fdv_per_buy_at_20k": 9_000,
                "event_count_at_20k": 4,
                "buy_count_at_20k": 3,
                "sell_count_at_20k": 1,
                "active_wallets_at_20k": 3,
            }
        ]
    ).to_parquet(full / "master_enriched_runner_fingerprint.parquet", index=False)
