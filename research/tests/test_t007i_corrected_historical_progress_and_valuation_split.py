from research.mtp_research.validation.t007i_corrected_historical_progress_and_valuation_split import (
    assign_chronological_splits,
    continuation_to_next_band,
    first_crossing,
    strategy_return,
    valuation_threshold_usd,
)


def test_denominator_threshold_math() -> None:
    assert valuation_threshold_usd(36_000, 72.5) == 26_100
    assert valuation_threshold_usd(69_000, 75) == 51_750


def test_raw_valuation_band_crossing_uses_first_crossing_only() -> None:
    snapshots = [
        {"snapshot_ts": 30, "valuation_proxy_usd": 12_000},
        {"snapshot_ts": 60, "valuation_proxy_usd": 42_000},
        {"snapshot_ts": 90, "valuation_proxy_usd": 38_000},
        {"snapshot_ts": 120, "valuation_proxy_usd": 48_000},
    ]

    crossing = first_crossing(snapshots, 40_000)

    assert crossing is not None
    assert crossing["snapshot_ts"] == 60
    assert crossing["valuation_proxy_usd"] == 42_000


def test_continuation_to_next_band_starts_after_first_band_crossing() -> None:
    snapshots = [
        {"snapshot_ts": 10, "valuation_proxy_usd": 35_000},
        {"snapshot_ts": 20, "valuation_proxy_usd": 37_000},
        {"snapshot_ts": 30, "valuation_proxy_usd": 34_000},
        {"snapshot_ts": 40, "valuation_proxy_usd": 51_000},
    ]

    result = continuation_to_next_band(snapshots, 36_000, 50_000)

    assert result["entry_ts"] == 20
    assert result["next_ts"] == 40
    assert result["continued"] is True
    assert result["seconds_to_next"] == 20


def test_validation_split_does_not_leak_future_data() -> None:
    launches = [{"mint": f"mint-{idx}", "launch_ts": idx} for idx in range(10)]

    split = assign_chronological_splits(launches, discovery_fraction=0.6)

    assert [row["split"] for row in split[:6]] == ["discovery_window"] * 6
    assert [row["split"] for row in split[6:]] == ["validation_window"] * 4
    assert max(row["launch_ts"] for row in split if row["split"] == "discovery_window") < min(
        row["launch_ts"] for row in split if row["split"] == "validation_window"
    )


def test_strategy_return_uses_path_end_for_failures() -> None:
    assert strategy_return(entry_value=40_000, exit_value=60_000, haircut=0.10) == 0.35
    assert strategy_return(entry_value=40_000, exit_value=20_000, haircut=0.10) == -0.55
