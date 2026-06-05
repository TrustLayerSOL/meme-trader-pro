import json
from pathlib import Path

from research.mtp_research.validation.run_buy_exit_start_rule_design import main


def test_run_buy_exit_start_rule_design_cli_execute(tmp_path: Path, monkeypatch) -> None:
    data_root = tmp_path / "lake"
    source_root = _write_sample(data_root / "data" / "forward_observation" / "combined_samples" / "fixed")
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_buy_exit_start_rule_design",
            "--data-root",
            str(data_root),
            "--source-root",
            str(source_root),
            "--execute",
        ],
    )

    exit_code = main()

    assert exit_code == 0
    assert (
        data_root
        / "data"
        / "backtests"
        / "diagnostics"
        / "reports"
        / "forward_observation"
        / "buy_exit_design"
        / "buy_exit_start_rule_design_summary.json"
    ).exists()


def test_buy_exit_design_uses_confirmed_actionable_20k_population(tmp_path: Path, monkeypatch) -> None:
    data_root = tmp_path / "lake"
    source_root = _write_spike_and_confirmed_sample(data_root / "data" / "forward_observation" / "combined_samples" / "spike-filter")
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_buy_exit_start_rule_design",
            "--data-root",
            str(data_root),
            "--source-root",
            str(source_root),
            "--execute",
        ],
    )

    assert main() == 0

    report_root = data_root / "data" / "backtests" / "diagnostics" / "reports" / "forward_observation" / "buy_exit_design"
    summary = json.loads((report_root / "buy_exit_start_rule_design_summary.json").read_text(encoding="utf-8"))
    dataset = [
        json.loads(line)
        for line in (report_root / "buy_exit_design_dataset.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    manifest = json.loads(
        (
            data_root
            / "data"
            / "forward_observation"
            / "snapshots"
            / "combined_actionable_crossed20k_buy_exit_design"
            / "snapshot_manifest.json"
        ).read_text(encoding="utf-8")
    )

    assert summary["raw_all_crossed_20k_count"] == 2
    assert summary["all_crossed_20k_count"] == 1
    assert summary["actionable_crossed_20k_count"] == 1
    assert manifest["unconfirmed_crossed_20k_count"] == 1
    assert manifest["unconfirmed_crossed_20k_mints"] == ["spike-mint"]
    assert [row["mint"] for row in dataset] == ["confirmed-mint"]
    assert dataset[0]["confirmed_crossed_20k"] is True


def test_run_buy_exit_start_rule_design_cli_dry_run(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("sys.argv", ["run_buy_exit_start_rule_design", "--data-root", str(tmp_path)])

    exit_code = main()

    assert exit_code == 0


def _write_sample(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    births = [
        {
            "mint": "mint-a",
            "sample_label": "fixed_sample",
            "source_provenance": "helius_birth_watch_followup",
            "create_time": 100,
            "observed_time": 101,
            "first_followup_attempt_time": 102,
            "freshness_class": "fresh",
            "fdv_path_before_10k": True,
            "fdv_path_before_20k": True,
            "first_followup_before_10k": True,
            "first_followup_before_20k": True,
        }
    ]
    paths = [
        {
            "mint": "mint-a",
            "timestamp": 130,
            "fdv_proxy": 22_000,
            "sample_label": "fixed_sample",
            "source_provenance": "helius_birth_watch_followup",
            "crossed_10k": True,
            "crossed_15k": True,
            "crossed_20k": True,
            "event_count": 5,
            "buy_count": 4,
            "sell_count": 1,
            "active_wallet_count": 4,
            "fdv_per_event": 4400,
            "fdv_per_active_wallet": 5500,
            "drawdown_pct": 0,
            "local_high_fdv": 22_000,
        },
        {
            "mint": "mint-a",
            "timestamp": 150,
            "fdv_proxy": 24_000,
            "sample_label": "fixed_sample",
            "source_provenance": "helius_birth_watch_followup",
            "crossed_10k": True,
            "crossed_15k": True,
            "crossed_20k": True,
            "event_count": 6,
            "buy_count": 5,
            "sell_count": 1,
            "active_wallet_count": 5,
            "fdv_per_event": 4000,
            "fdv_per_active_wallet": 4800,
            "drawdown_pct": 0,
            "local_high_fdv": 24_000,
        }
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
    (root / "lifecycle_state.json").write_text(json.dumps({"mints": {"mint-a": {"state": "trigger_qualified_active_watch"}}}), encoding="utf-8")
    (root / "official_lifecycle_manifest.json").write_text(json.dumps({"sample_label": "fixed_sample"}), encoding="utf-8")
    return root


def _write_spike_and_confirmed_sample(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    births = [
        {
            "mint": mint,
            "sample_label": "spike_filter_sample",
            "source_provenance": "helius_birth_watch_followup",
            "create_time": 100,
            "observed_time": 101,
            "first_followup_attempt_time": 102,
            "freshness_class": "fresh",
            "fdv_path_before_10k": True,
            "fdv_path_before_20k": True,
            "first_followup_before_10k": True,
            "first_followup_before_20k": True,
        }
        for mint in ["spike-mint", "confirmed-mint"]
    ]
    paths = [
        {
            "mint": "spike-mint",
            "timestamp": 130,
            "fdv_proxy": 3_000,
            "sample_label": "spike_filter_sample",
            "source_provenance": "helius_birth_watch_followup",
            "crossed_10k": False,
            "crossed_15k": False,
            "crossed_20k": False,
            "event_count": 5,
            "buy_count": 4,
            "sell_count": 1,
            "active_wallet_count": 4,
            "fdv_per_event": 600,
            "fdv_per_active_wallet": 750,
            "drawdown_pct": 0,
            "local_high_fdv": 3_000,
        },
        {
            "mint": "spike-mint",
            "timestamp": 140,
            "fdv_proxy": 36_000,
            "sample_label": "spike_filter_sample",
            "source_provenance": "helius_birth_watch_followup",
            "crossed_10k": True,
            "crossed_15k": True,
            "crossed_20k": True,
            "event_count": 1,
            "buy_count": 0,
            "sell_count": 1,
            "active_wallet_count": 1,
            "fdv_per_event": 36_000,
            "fdv_per_active_wallet": 36_000,
            "drawdown_pct": 0,
            "local_high_fdv": 36_000,
        },
        {
            "mint": "spike-mint",
            "timestamp": 143,
            "fdv_proxy": 3_100,
            "sample_label": "spike_filter_sample",
            "source_provenance": "helius_birth_watch_followup",
            "crossed_10k": False,
            "crossed_15k": False,
            "crossed_20k": False,
            "event_count": 6,
            "buy_count": 4,
            "sell_count": 2,
            "active_wallet_count": 4,
            "fdv_per_event": 516.67,
            "fdv_per_active_wallet": 775,
            "drawdown_pct": 91,
            "local_high_fdv": 36_000,
        },
        {
            "mint": "confirmed-mint",
            "timestamp": 230,
            "fdv_proxy": 22_000,
            "sample_label": "spike_filter_sample",
            "source_provenance": "helius_birth_watch_followup",
            "crossed_10k": True,
            "crossed_15k": True,
            "crossed_20k": True,
            "event_count": 5,
            "buy_count": 4,
            "sell_count": 1,
            "active_wallet_count": 4,
            "fdv_per_event": 4400,
            "fdv_per_active_wallet": 5500,
            "drawdown_pct": 0,
            "local_high_fdv": 22_000,
        },
        {
            "mint": "confirmed-mint",
            "timestamp": 250,
            "fdv_proxy": 24_000,
            "sample_label": "spike_filter_sample",
            "source_provenance": "helius_birth_watch_followup",
            "crossed_10k": True,
            "crossed_15k": True,
            "crossed_20k": True,
            "event_count": 6,
            "buy_count": 5,
            "sell_count": 1,
            "active_wallet_count": 5,
            "fdv_per_event": 4000,
            "fdv_per_active_wallet": 4800,
            "drawdown_pct": 0,
            "local_high_fdv": 24_000,
        },
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
                    "spike-mint": {"state": "matured_terminal_collapse"},
                    "confirmed-mint": {"state": "trigger_qualified_active_watch"},
                }
            }
        ),
        encoding="utf-8",
    )
    (root / "official_lifecycle_manifest.json").write_text(json.dumps({"sample_label": "spike_filter_sample"}), encoding="utf-8")
    return root
