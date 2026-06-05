import json
from pathlib import Path

from research.mtp_research.validation.buy_exit_start_rule_design import (
    BUY_RULES,
    EXIT_RULES,
    build_buy_candidate_comparison,
    build_design_dataset,
    build_disabled_paper_config,
    build_quality_gate,
    build_snapshot_manifest,
    build_what_if_comparison,
    load_snapshot_rows,
    run_buy_exit_start_rule_design,
)


def test_snapshot_manifest_uses_actionable_main_population(tmp_path: Path) -> None:
    source_root = _write_sample(tmp_path / "source")
    rows = load_snapshot_rows(source_root)

    manifest = build_snapshot_manifest(source_root, rows)

    assert manifest["raw_all_crossed_20k_count"] == 2
    assert manifest["all_crossed_20k_count"] == 1
    assert manifest["actionable_crossed_20k_count"] == 1
    assert manifest["main_analysis_population"] == "confirmed_actionable_crossed_20k"
    assert manifest["secondary_context_population"] == "raw_all_crossed_20k"
    assert manifest["duplicate_mints"] == []


def test_design_dataset_contains_one_actionable_row_per_mint(tmp_path: Path) -> None:
    rows = load_snapshot_rows(_write_sample(tmp_path / "source"))

    dataset = build_design_dataset(rows)

    assert [row["mint"] for row in dataset] == ["mint-a"]
    row = dataset[0]
    assert row["actionable_sample_flag"] is True
    assert row["crossed_10k"] is True
    assert row["crossed_15k"] is True
    assert row["crossed_20k"] is True
    assert row["create_to_20k_seconds"] == 30
    assert row["10k_to_20k_seconds"] == 20
    assert row["fdv_per_event_at_20k"] == 4400
    assert row["max_fdv_after_20k"] == 125000
    assert row["reclaimed_after_30pct_drawdown"] is True


def test_quality_gate_and_fixed_rule_schemas_are_guarded(tmp_path: Path) -> None:
    rows = load_snapshot_rows(_write_sample(tmp_path / "source"))
    dataset = build_design_dataset(rows)

    quality = build_quality_gate(rows, dataset)

    assert quality["actionable_rows"] == 1
    assert quality["non_actionable_rows"] == 1
    assert quality["duplicate_mints"] == []
    assert quality["quality_gate_result"] in {"paper_start_candidate_ready_disabled", "paper_start_candidate_data_limited"}
    assert [rule["rule_id"] for rule in BUY_RULES] == ["B1", "B2", "B3", "B4"]
    assert [rule["rule_id"] for rule in EXIT_RULES] == ["E1", "E2", "E3", "E4"]
    assert all(rule["bucket_method"] == "fixed_high_bucket_no_grid_search" for rule in BUY_RULES)


def test_what_if_comparison_is_descriptive_not_enabled_paper(tmp_path: Path) -> None:
    rows = load_snapshot_rows(_write_sample(tmp_path / "source"))
    dataset = build_design_dataset(rows)

    buy_comparison = build_buy_candidate_comparison(dataset)
    combo = build_what_if_comparison(dataset, BUY_RULES, EXIT_RULES[:3])
    config = build_disabled_paper_config("B3", "E2", quality_result="paper_start_candidate_ready_disabled")

    assert any(row["rule_id"] == "B3" and row["hypothetical_entries"] == 1 for row in buy_comparison)
    assert any(row["buy_rule_id"] == "B3" and row["exit_rule_id"] == "E2" for row in combo)
    assert all(row["label"] == "FDV path multiple, not realized PnL" for row in combo)
    assert config["enabled"] is False
    assert config["selected_buy_rule_id"] == "B3"
    assert config["selected_exit_rule_id"] == "E2"
    assert "no_private_keys" in config["guardrails"]


def test_run_writes_deterministic_reports_and_disabled_config(tmp_path: Path) -> None:
    data_root = tmp_path / "lake"
    source_root = _write_sample(data_root / "data" / "forward_observation" / "combined_samples" / "fixed")

    result = run_buy_exit_start_rule_design(data_root=data_root, source_root=source_root, execute=True)

    report_root = data_root / "data" / "backtests" / "diagnostics" / "reports" / "forward_observation" / "buy_exit_design"
    snapshot_root = data_root / "data" / "forward_observation" / "snapshots" / "combined_actionable_crossed20k_buy_exit_design"
    config_path = data_root / "data" / "forward_observation" / "official_lifecycle_watch_v1" / "paper_shadow_starting_config.json"
    status_path = Path("theses/BUY_EXIT_START_RULE_DESIGN_STATUS.md")

    assert result["execute"] is True
    assert result["actionable_crossed_20k_count"] == 1
    assert result["selected_buy_rule_id"] == "B3"
    assert result["selected_exit_rule_id"] == "E2"
    assert (snapshot_root / "snapshot_manifest.json").exists()
    assert (snapshot_root / "snapshot_manifest.md").exists()
    assert (report_root / "buy_exit_design_dataset.jsonl").exists()
    assert (report_root / "buy_exit_quality_gate.json").exists()
    assert (report_root / "buy_exit_start_rule_design_summary.json").exists()
    assert (report_root / "buy_exit_combo_what_if.csv").exists()
    assert config_path.exists()
    assert json.loads(config_path.read_text(encoding="utf-8"))["enabled"] is False
    assert status_path.exists()


def test_design_files_do_not_contain_runtime_execution_logic() -> None:
    guarded = [
        Path("research/mtp_research/validation/buy_exit_start_rule_design.py"),
        Path("research/mtp_research/validation/run_buy_exit_start_rule_design.py"),
    ]
    forbidden = ["send_transaction(", "sign_transaction(", "secret_key", "place_order(", "submit_order("]
    for path in guarded:
        text = path.read_text(encoding="utf-8").lower()
        for pattern in forbidden:
            assert pattern not in text


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
            "token_name": "Alpha",
            "token_symbol": "A",
        },
        {
            "mint": "mint-b",
            "sample_label": "fixed_sample",
            "source_provenance": "helius_birth_watch_followup",
            "create_time": 100,
            "observed_time": 101,
            "first_followup_attempt_time": 102,
            "freshness_class": "stale",
            "fdv_path_before_10k": False,
            "fdv_path_before_20k": False,
            "first_followup_before_10k": False,
            "first_followup_before_20k": False,
        },
    ]
    paths = [
        _path("mint-a", 110, 10_500, crossed_10k=True, event_count=3, buy_count=2, sell_count=1, active_wallet_count=2),
        _path("mint-a", 120, 15_500, crossed_10k=True, crossed_15k=True, event_count=4, buy_count=3, sell_count=1, active_wallet_count=3),
        _path("mint-a", 130, 22_000, crossed_10k=True, crossed_15k=True, crossed_20k=True, event_count=5, buy_count=4, sell_count=1, active_wallet_count=4),
        _path("mint-a", 160, 120_000, crossed_10k=True, crossed_15k=True, crossed_20k=True, crossed_30k=True, crossed_50k=True, crossed_100k=True, event_count=10, buy_count=8, sell_count=2, active_wallet_count=8),
        _path("mint-a", 180, 80_000, crossed_10k=True, crossed_15k=True, crossed_20k=True, crossed_30k=True, crossed_50k=True, drawdown_pct=33.4, local_high_fdv=120_000),
        _path("mint-a", 220, 125_000, crossed_10k=True, crossed_15k=True, crossed_20k=True, crossed_30k=True, crossed_50k=True, crossed_100k=True, local_high_fdv=125_000),
        _path("mint-b", 130, 25_000, crossed_10k=True, crossed_15k=True, crossed_20k=True, event_count=2, buy_count=1, sell_count=1, active_wallet_count=1),
    ]
    metadata = [{"mint": "mint-a", "token_name": "Alpha", "token_symbol": "A", "twitter": "x", "telegram": "t"}]
    state = {"mints": {"mint-a": {"state": "matured_reached_1m"}, "mint-b": {"state": "data_limited"}}}
    for name, rows in {
        "births.jsonl": births,
        "followup_paths.jsonl": paths,
        "events.jsonl": paths,
        "metadata.jsonl": metadata,
        "drawdowns.jsonl": [],
        "lifecycle_transitions.jsonl": [],
    }.items():
        (root / name).write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    (root / "lifecycle_state.json").write_text(json.dumps(state), encoding="utf-8")
    (root / "official_lifecycle_manifest.json").write_text(json.dumps({"sample_label": "fixed_sample"}), encoding="utf-8")
    return root


def _path(mint: str, timestamp: int, fdv: float, **overrides):
    row = {
        "mint": mint,
        "timestamp": timestamp,
        "fdv_proxy": fdv,
        "sample_label": "fixed_sample",
        "source_provenance": "helius_birth_watch_followup",
        "crossed_10k": False,
        "crossed_15k": False,
        "crossed_20k": False,
        "crossed_30k": False,
        "crossed_50k": False,
        "crossed_100k": False,
        "crossed_200k": False,
        "crossed_500k": False,
        "crossed_1m": False,
        "event_count": 1,
        "buy_count": 1,
        "sell_count": 0,
        "active_wallet_count": 1,
        "drawdown_pct": 0,
        "local_high_fdv": fdv,
    }
    row.update(overrides)
    buy_count = row.get("buy_count") or 0
    row["fdv_per_event"] = fdv / max(row.get("event_count") or 1, 1)
    row["fdv_per_buy"] = fdv / buy_count if buy_count else None
    row["fdv_per_active_wallet"] = fdv / max(row.get("active_wallet_count") or 1, 1)
    row["buy_sell_ratio"] = buy_count / max(row.get("sell_count") or 1, 1)
    return row
