import json
from pathlib import Path

from research.mtp_research.validation.confirmed_rule_discovery import (
    build_confirmed_rule_discovery,
    build_confirmed_rule_layers,
)


def test_confirmed_rule_discovery_rejects_hunter_style_spike(tmp_path: Path) -> None:
    data_root = tmp_path / "lake"
    source_root = _write_sample(data_root / "data" / "forward_observation" / "official_lifecycle_watch_v2")

    result = build_confirmed_rule_discovery(data_root=data_root, source_roots=[source_root], execute=True)

    report_root = Path(result["report_root"])
    actionability = _read_jsonl(report_root / "confirmed_actionability_layer.jsonl")
    labels = _read_csv_dicts(report_root / "confirmed_rule_labels.csv")
    stats = _read_csv_dicts(report_root / "confirmed_baseline_stats.csv")
    config = json.loads(
        (
            data_root
            / "data"
            / "forward_observation"
            / "official_lifecycle_watch_v2"
            / "paper_shadow_starting_config.json"
        ).read_text(encoding="utf-8")
    )

    by_mint = {row["mint"]: row for row in actionability}
    assert by_mint["hunter-style-spike"]["confirmed_crossed_20k"] is False
    assert by_mint["hunter-style-spike"]["has_spike_anomaly"] is True
    assert by_mint["hunter-style-spike"]["confirmed_actionable_crossed_20k"] is False
    assert by_mint["hunter-style-spike"]["actionability_failure_reason"] == "single_row_spike"
    assert by_mint["confirmed-mint"]["confirmed_actionable_crossed_20k"] is True
    assert [row["mint"] for row in labels] == ["confirmed-mint"]
    assert labels[0]["baseline_confirmed_actionable_20k"] == "True"
    assert config["use_confirmed_milestones_only"] is True
    assert config["raw_milestones_allowed_for_entry"] is False
    assert config["private_keys_allowed"] is False
    assert result["raw_crossed_20k_count"] == 3
    assert result["confirmed_crossed_20k_count"] == 2
    assert result["confirmed_actionable_crossed_20k_count"] == 1
    assert stats[0]["sample_family"] == "v2_current"


def test_confirmed_rule_layers_exclude_same_timestamp_major_jump_from_actionability(tmp_path: Path) -> None:
    source_root = _write_sample(tmp_path / "sample")
    births = _read_jsonl(source_root / "births.jsonl")
    paths = _read_jsonl(source_root / "followup_paths.jsonl")

    layers = build_confirmed_rule_layers(
        source_root=source_root,
        births=births,
        paths=paths,
        lifecycle_state={"mints": {}},
        sample_family="v2_current",
        collector_semantics="official_lifecycle_watch_v2",
    )

    jump = next(row for row in layers.actionability_rows if row["mint"] == "same-timestamp-jump")
    assert jump["confirmed_crossed_20k"] is True
    assert jump["has_same_timestamp_major_jump"] is True
    assert jump["confirmed_actionable_crossed_20k"] is False
    assert jump["actionability_failure_reason"] == "same_timestamp_major_jump"


def test_confirmed_rule_discovery_reports_contaminated_raw_manifest(tmp_path: Path) -> None:
    data_root = tmp_path / "lake"
    source_root = _write_sample(data_root / "data" / "forward_observation" / "official_lifecycle_watch_v2")

    result = build_confirmed_rule_discovery(data_root=data_root, source_roots=[source_root], execute=True)

    manifest = json.loads((Path(result["report_root"]) / "contaminated_raw_rule_discovery_manifest.json").read_text(encoding="utf-8"))
    assert "Hunter" in manifest["hunter_false_entry_explanation"]
    assert "final rule selection" in manifest["prohibited_uses"]
    assert "candidate rule shapes" in manifest["still_useful_for"]


def _write_sample(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    births = [
        _birth("hunter-style-spike"),
        _birth("confirmed-mint"),
        _birth("same-timestamp-jump"),
    ]
    paths = [
        _path("hunter-style-spike", 100, 2_400),
        _path("hunter-style-spike", 110, 36_000),
        _path("hunter-style-spike", 120, 2_500),
        _path("confirmed-mint", 200, 12_000),
        _path("confirmed-mint", 210, 22_000),
        _path("confirmed-mint", 240, 24_000),
        _path("confirmed-mint", 260, 54_000),
        _path("confirmed-mint", 285, 56_000),
        _path("same-timestamp-jump", 300, 1_100_000),
        _path("same-timestamp-jump", 300, 1_120_000),
    ]
    for name, rows in {
        "births.jsonl": births,
        "followup_paths.jsonl": paths,
        "events.jsonl": paths,
        "metadata.jsonl": [],
        "drawdowns.jsonl": [],
        "lifecycle_transitions.jsonl": [],
    }.items():
        (root / name).write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    (root / "lifecycle_state.json").write_text(
        json.dumps(
            {
                "mints": {
                    "hunter-style-spike": {"state": "matured_terminal_collapse"},
                    "confirmed-mint": {"state": "trigger_qualified_active_watch"},
                    "same-timestamp-jump": {"state": "trigger_qualified_active_watch"},
                }
            }
        ),
        encoding="utf-8",
    )
    (root / "official_lifecycle_manifest.json").write_text(json.dumps({"sample_label": "official_lifecycle_watch_v2"}), encoding="utf-8")
    return root


def _birth(mint: str) -> dict:
    return {
        "mint": mint,
        "official_accepted_birth": True,
        "fdv_path_before_10k": True,
        "fdv_path_before_15k": True,
        "fdv_path_before_20k": True,
        "valid_fdv_path_provenance": True,
        "first_fdv_path_time": 90,
        "first_fdv_path_fdv": 2_000,
    }


def _path(mint: str, timestamp: float, fdv: float) -> dict:
    return {
        "mint": mint,
        "timestamp": timestamp,
        "fdv_proxy": fdv,
        "crossed_10k": fdv >= 10_000,
        "crossed_15k": fdv >= 15_000,
        "crossed_20k": fdv >= 20_000,
        "crossed_30k": fdv >= 30_000,
        "crossed_50k": fdv >= 50_000,
        "crossed_100k": fdv >= 100_000,
        "crossed_200k": fdv >= 200_000,
        "crossed_500k": fdv >= 500_000,
        "crossed_1m": fdv >= 1_000_000,
        "event_count": 5,
        "buy_count": 4,
        "sell_count": 1,
        "active_wallet_count": 4,
        "fdv_per_event": fdv / 5,
        "fdv_per_buy": fdv / 4,
        "fdv_per_active_wallet": fdv / 4,
        "local_high_fdv": fdv,
    }


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _read_csv_dicts(path: Path) -> list[dict[str, str]]:
    import csv

    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))
