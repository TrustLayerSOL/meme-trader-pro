import json
import subprocess
from pathlib import Path

from research.mtp_research.launch_regime.valuation_enrichment import (
    enrich_outcome_row,
    enrich_snapshot_row,
    run_valuation_enrichment,
)


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")
    return path


def test_snapshot_enrichment_keeps_market_cap_null_without_supply_and_sol_usd() -> None:
    enriched = enrich_snapshot_row(
        {
            "token_mint": "mint-a",
            "snapshot_ts": 1_000,
            "launch_age_seconds": 30,
            "liquidity_proxy": 2.5,
            "metadata_json": {"liquidity_proxy_source": "bonding_curve_post_balance"},
        }
    )

    assert enriched["true_market_cap_available"] is False
    assert enriched["true_market_cap_usd"] is None
    assert enriched["fdv_available"] is False
    assert enriched["fdv_usd"] is None
    assert enriched["valuation_proxy_available"] is False
    assert enriched["valuation_proxy_usd"] is None
    assert enriched["bonding_curve_liquidity_proxy_sol"] == 2.5
    assert enriched["valuation_source"] == "bonding_curve_post_balance"
    assert enriched["threshold_outcomes_usable"] is False
    assert enriched["threshold_outcomes_source"] is None
    assert enriched["threshold_outcomes_missing_reason"] == "usd_valuation_unavailable"
    assert enriched["ever_hit_valuation_proxy_15k"] is None


def test_outcome_enrichment_keeps_thresholds_unusable_when_valuation_unavailable() -> None:
    enriched = enrich_outcome_row(
        {
            "token_mint": "mint-a",
            "market_cap_available": False,
            "threshold_outcomes_usable": False,
            "ever_hit_15k": None,
            "ever_hit_35k": None,
            "ever_hit_50k": None,
            "ever_hit_100k": None,
            "metadata_json": {
                "liquidity_proxy_at_120m": 2.8,
                "liquidity_proxy_source_120m": "bonding_curve_post_balance",
            },
        }
    )

    assert enriched["market_cap_available"] is False
    assert enriched["true_market_cap_usd"] is None
    assert enriched["fdv_usd"] is None
    assert enriched["bonding_curve_liquidity_proxy_sol"] == 2.8
    assert enriched["ever_hit_15k"] is None
    assert enriched["ever_hit_valuation_proxy_100k"] is None
    assert enriched["threshold_outcomes_semantics"] == "unusable_no_usd_valuation"


def test_outcome_enrichment_reads_price_sol_at_120m_but_blocks_usd_without_sol_usd() -> None:
    enriched = enrich_outcome_row(
        {
            "token_mint": "mint-a",
            "metadata_json": {
                "price_sol_at_120m": 0.000002,
                "price_source_120m": "balance_delta_quote_over_base_v0",
                "liquidity_proxy_at_120m": 2.8,
            },
        }
    )

    assert enriched["price_sol_available"] is True
    assert enriched["price_usd_available"] is False
    assert enriched["sol_usd_available"] is False
    assert enriched["true_market_cap_usd"] is None
    assert enriched["fdv_usd"] is None
    assert enriched["threshold_outcomes_usable"] is False
    assert enriched["valuation_missing_reason"] == "missing_supply_and_sol_usd"


def test_enrichment_blocks_usd_fields_without_sol_usd_even_when_price_sol_is_present() -> None:
    enriched = enrich_snapshot_row(
        {
            "token_mint": "mint-a",
            "price_sol": 0.000001,
            "liquidity_proxy": 3.0,
            "metadata_json": {"liquidity_proxy_source": "bonding_curve_post_balance"},
        }
    )

    assert enriched["price_sol_available"] is True
    assert enriched["price_usd_available"] is False
    assert enriched["sol_usd_available"] is False
    assert enriched["true_market_cap_available"] is False
    assert enriched["fdv_available"] is False
    assert enriched["valuation_missing_reason"] == "missing_supply_and_sol_usd"


def test_run_valuation_enrichment_is_offline_and_writes_proxy_threshold_fields(tmp_path: Path) -> None:
    snapshots_path = _write_jsonl(
        tmp_path / "snapshots.jsonl",
        [{"token_mint": "mint-a", "liquidity_proxy": 2.5, "metadata_json": {"liquidity_proxy_source": "bonding_curve_post_balance"}}],
    )
    outcomes_path = _write_jsonl(
        tmp_path / "outcomes.jsonl",
        [{"token_mint": "mint-a", "metadata_json": {"liquidity_proxy_at_120m": 2.5}}],
    )

    report = run_valuation_enrichment(
        snapshots_path=snapshots_path,
        outcomes_path=outcomes_path,
        output_dir=tmp_path / "enriched",
    )

    assert report["network_calls"] == 0
    assert report["snapshot_count"] == 1
    assert report["outcome_count"] == 1
    assert report["true_market_cap_available_count"] == 0
    assert report["fdv_available_count"] == 0
    assert report["valuation_proxy_available_count"] == 0
    enriched_snapshot = json.loads((tmp_path / "enriched" / "launch_lifecycle_snapshots_valuation_enriched.jsonl").read_text().splitlines()[0])
    assert "ever_hit_valuation_proxy_15k" in enriched_snapshot
    assert enriched_snapshot["ever_hit_valuation_proxy_15k"] is None


def test_enrichment_uses_supply_and_sol_usd_for_fdv_proxy_thresholds(tmp_path: Path) -> None:
    snapshots_path = _write_jsonl(
        tmp_path / "snapshots.jsonl",
        [
            {
                "token_mint": "mint-a",
                "metadata_json": {"price_sol": 0.0002, "price_event_block_time": 1_000},
            }
        ],
    )
    outcomes_path = _write_jsonl(tmp_path / "outcomes.jsonl", [])
    supply_path = _write_jsonl(
        tmp_path / "supply.jsonl",
        [{"mint": "mint-a", "total_supply": 1_000_000_000, "supply_source": "helius_getTokenSupply"}],
    )
    sol_usd_path = _write_jsonl(
        tmp_path / "sol_usd.jsonl",
        [{"ts": 1_000, "sol_usd": 100.0, "source": "coingecko_solana_market_chart_range"}],
    )

    report = run_valuation_enrichment(
        snapshots_path=snapshots_path,
        outcomes_path=outcomes_path,
        output_dir=tmp_path / "enriched",
        supply_path=supply_path,
        sol_usd_path=sol_usd_path,
    )

    assert report["fdv_available_count"] == 1
    assert report["valuation_proxy_available_count"] == 1
    assert report["proxy_threshold_outcomes_usable_count"] == 1
    row = json.loads((tmp_path / "enriched" / "launch_lifecycle_snapshots_valuation_enriched.jsonl").read_text().splitlines()[0])
    assert row["price_usd_available"] is True
    assert row["fdv_usd"] == 20_000_000
    assert row["true_market_cap_usd"] is None
    assert row["valuation_proxy_usd"] == 20_000_000
    assert row["threshold_outcomes_usable"] is False
    assert row["proxy_threshold_outcomes_usable"] is True
    assert row["ever_hit_valuation_proxy_100k"] is True


def test_valuation_report_handles_mixed_missing_reason_keys(tmp_path: Path) -> None:
    snapshots_path = _write_jsonl(
        tmp_path / "snapshots.jsonl",
        [
            {"token_mint": "mint-a", "metadata_json": {"price_sol": 0.0002, "price_event_block_time": 1_000}},
            {"token_mint": "mint-b", "metadata_json": {"price_sol": 0.0002, "price_event_block_time": 1_000}},
        ],
    )
    outcomes_path = _write_jsonl(tmp_path / "outcomes.jsonl", [])
    supply_path = _write_jsonl(
        tmp_path / "supply.jsonl",
        [{"mint": "mint-a", "total_supply": 1_000_000_000, "supply_source": "helius_getTokenSupply"}],
    )
    sol_usd_path = _write_jsonl(
        tmp_path / "sol_usd.jsonl",
        [{"ts": 1_000, "sol_usd": 100.0, "source": "coingecko_solana_market_chart_range"}],
    )

    report = run_valuation_enrichment(
        snapshots_path=snapshots_path,
        outcomes_path=outcomes_path,
        output_dir=tmp_path / "enriched",
        supply_path=supply_path,
        sol_usd_path=sol_usd_path,
    )

    assert report["valuation_missing_reason_counts"]["none"] == 1
    assert report["valuation_missing_reason_counts"]["missing_supply"] == 1


def test_valuation_enrichment_cli_runs_without_network(tmp_path: Path) -> None:
    snapshots_path = _write_jsonl(tmp_path / "snapshots.jsonl", [{"token_mint": "mint-a"}])
    outcomes_path = _write_jsonl(tmp_path / "outcomes.jsonl", [{"token_mint": "mint-a"}])

    result = subprocess.run(
        [
            "./trading_env/bin/python",
            "-m",
            "research.mtp_research.launch_regime.run_valuation_enrichment",
            "--snapshots-path",
            str(snapshots_path),
            "--outcomes-path",
            str(outcomes_path),
            "--output-dir",
            str(tmp_path / "enriched"),
        ],
        cwd=Path(__file__).resolve().parents[2],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "network_calls=0" in result.stdout
    assert "threshold_outcomes_usable_count=0" in result.stdout
