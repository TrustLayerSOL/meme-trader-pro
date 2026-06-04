import json
from pathlib import Path

from research.mtp_research.validation.forward_paper_shadow import initialize_forward_paper_shadow
from research.mtp_research.validation.partial_forward_strategy_preview import (
    SAMPLE_LABEL,
    build_analysis_dataset,
    build_entry_feature_preview,
    build_exit_path_preview,
    run_partial_forward_strategy_preview,
)


def test_analysis_dataset_uses_partial_sample_label_and_milestones() -> None:
    rows = _sample_rows()

    analysis = build_analysis_dataset(rows)

    assert len(analysis) == 2
    mint_a = next(row for row in analysis if row["mint"] == "mint-a")
    assert mint_a["sample_label"] == SAMPLE_LABEL
    assert mint_a["crossed_10k"] is True
    assert mint_a["crossed_20k"] is True
    assert mint_a["fdv_per_event_at_20k"] == 5000
    assert mint_a["create_to_20k_seconds"] == 30


def test_entry_and_exit_previews_are_deterministic_and_labeled_data_limited() -> None:
    analysis = build_analysis_dataset(_sample_rows())

    entry = build_entry_feature_preview(analysis)
    exit_rows = build_exit_path_preview(analysis)

    assert any(row["feature"] == "fdv_per_event_at_20k" for row in entry)
    assert all("classification" in row for row in entry)
    assert any(row["feature"] == "max_drawdown_after_20k" for row in exit_rows)
    assert all(row["data_limited"] is True for row in exit_rows)


def test_partial_preview_writes_reports_from_quarantined_source(tmp_path: Path) -> None:
    source_root = tmp_path / "data" / "forward_observation" / "quarantined" / "official_lifecycle_watch_v1_old"
    _write_sample(source_root)

    result = run_partial_forward_strategy_preview(data_root=tmp_path, source_root=source_root, execute=True)

    report_root = tmp_path / "data" / "backtests" / "diagnostics" / "reports" / "forward_observation" / "official_lifecycle_watch_v1"
    assert result["sample_label"] == SAMPLE_LABEL
    assert result["source_root"] == str(source_root)
    assert (report_root / "partial_birth_coverage_sample_manifest.json").exists()
    assert (report_root / "partial_sample_quality_audit.json").exists()
    assert (report_root / "partial_sample_analysis_dataset.jsonl").exists()
    assert (report_root / "partial_sample_analysis_dataset.parquet").exists()
    assert (report_root / "tentative_buy_rule_candidates.csv").exists()
    assert Path("theses/PARTIAL_FORWARD_STRATEGY_PREVIEW_STATUS.md").exists()


def test_forward_paper_shadow_scaffold_is_disabled_by_default(tmp_path: Path) -> None:
    result = initialize_forward_paper_shadow(data_root=tmp_path, execute=True)

    config = json.loads(Path(result["config_path"]).read_text(encoding="utf-8"))
    assert result["enabled"] is False
    assert config["enabled"] is False
    assert config["no_real_trade_flag"] is True
    assert "no_transaction_signing" in config["guardrails"]
    assert Path(result["decisions_path"]).exists()
    assert Path(result["status_path"]).exists()


def test_new_scaffold_files_do_not_contain_forbidden_runtime_logic() -> None:
    guarded = [
        Path("research/mtp_research/validation/partial_forward_strategy_preview.py"),
        Path("research/mtp_research/validation/forward_paper_shadow.py"),
    ]
    forbidden = ["place_order", "submit_order", "send_transaction", "secret_key", "auto_buy", "auto_sell", "grid_search"]
    for path in guarded:
        text = path.read_text(encoding="utf-8").lower()
        for pattern in forbidden:
            assert pattern not in text


def _sample_rows() -> dict:
    return {
        "births": [
            {
                "mint": "mint-a",
                "creator": "creator-a",
                "create_time": 100,
                "observed_time": 101,
                "first_followup_attempt_time": 102,
                "create_to_first_followup_seconds": 2,
                "first_followup_before_10k": True,
                "first_followup_before_20k": True,
                "freshness_class": "fresh_birth_observed",
                "observation_id": "obs-a",
            },
            {
                "mint": "mint-b",
                "creator": "creator-b",
                "create_time": 100,
                "observed_time": 101,
                "first_followup_attempt_time": 103,
                "create_to_first_followup_seconds": 3,
                "first_followup_before_10k": True,
                "first_followup_before_20k": True,
                "freshness_class": "fresh_birth_observed",
                "observation_id": "obs-b",
            },
        ],
        "paths": [
            {
                "mint": "mint-a",
                "timestamp": 110,
                "fdv_proxy": 12_000,
                "event_count": 3,
                "buy_count": 2,
                "sell_count": 1,
                "active_wallet_count": 2,
                "fdv_per_event": 4000,
                "fdv_per_buy": 6000,
                "fdv_per_active_wallet": 6000,
                "buy_sell_ratio": 2,
                "drawdown_pct": 0,
            },
            {
                "mint": "mint-a",
                "timestamp": 130,
                "fdv_proxy": 25_000,
                "event_count": 5,
                "buy_count": 4,
                "sell_count": 1,
                "active_wallet_count": 4,
                "fdv_per_event": 5000,
                "fdv_per_buy": 6250,
                "fdv_per_active_wallet": 6250,
                "buy_sell_ratio": 4,
                "drawdown_pct": 0,
            },
            {"mint": "mint-b", "timestamp": 120, "fdv_proxy": 5_000, "event_count": 1, "buy_count": 1, "sell_count": 0},
        ],
        "events": [{"mint": "mint-a"}, {"mint": "mint-b"}],
        "metadata": [{"mint": "mint-a", "token_name": "Token A", "token_symbol": "A"}],
        "drawdowns": [{"mint": "mint-a", "timestamp": 140, "drawdown_pct": 30, "local_high_fdv": 25_000}],
        "transitions": [],
        "state": {
            "mints": {
                "mint-a": {"state": "trigger_qualified_active_watch", "create_time": 100},
                "mint-b": {"state": "fdv_followup_started", "create_time": 100},
            }
        },
        "status": {},
    }


def _write_sample(source_root: Path) -> None:
    source_root.mkdir(parents=True, exist_ok=True)
    rows = _sample_rows()
    for name, key in [
        ("births.jsonl", "births"),
        ("followup_paths.jsonl", "paths"),
        ("events.jsonl", "events"),
        ("metadata.jsonl", "metadata"),
        ("drawdowns.jsonl", "drawdowns"),
        ("lifecycle_transitions.jsonl", "transitions"),
    ]:
        (source_root / name).write_text("".join(json.dumps(row) + "\n" for row in rows[key]), encoding="utf-8")
    (source_root / "lifecycle_state.json").write_text(json.dumps(rows["state"]), encoding="utf-8")
    (source_root / "status.json").write_text(json.dumps(rows["status"]), encoding="utf-8")
