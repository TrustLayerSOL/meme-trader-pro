import json
from pathlib import Path

from research.mtp_research.validation.official_lifecycle_watch import (
    OFFICIAL_V2_SAMPLE_LABEL,
    OfficialLifecycleStateMachine,
    OfficialLifecycleV2Config,
    build_official_lifecycle_quality_audit,
    freeze_mixed_forward_campaign_pre_v2,
    format_official_lifecycle_status,
    initialize_official_lifecycle_namespace,
    official_lifecycle_status,
)


def test_v2_namespace_starts_from_zero_and_creates_disabled_shadow_files(tmp_path: Path) -> None:
    old = tmp_path / "data" / "forward_observation" / "official_lifecycle_watch_v1"
    old.mkdir(parents=True)
    (old / "births.jsonl").write_text('{"mint":"old-mint"}\n', encoding="utf-8")
    config = OfficialLifecycleV2Config(data_root=tmp_path)

    manifest = initialize_official_lifecycle_namespace(config)

    assert manifest["sample_label"] == OFFICIAL_V2_SAMPLE_LABEL
    assert manifest["starts_from_zero"] is True
    assert manifest["previous_samples_excluded"] is True
    assert manifest["paper_shadow_status"] == "disabled"
    assert manifest["entry_universe_definition"] == "baseline_all_actionable_crossed_20k_mints"
    assert config.observation_root.name == OFFICIAL_V2_SAMPLE_LABEL
    assert config.births_path.read_text(encoding="utf-8") == ""
    assert config.paper_shadow_labels_path.exists()
    assert config.paper_shadow_exit_labels_path.exists()
    disabled_config = json.loads(config.paper_shadow_v2_config_path.read_text(encoding="utf-8"))
    assert disabled_config["enabled"] is False
    assert disabled_config["paper_entries_enabled"] is False
    assert disabled_config["paper_exits_enabled"] is False
    assert disabled_config["pnl_enabled"] is False
    assert disabled_config["execution_enabled"] is False
    assert disabled_config["private_keys_allowed"] is False
    assert old.exists()


def test_freeze_mixed_forward_campaign_writes_manifest_without_deleting_sources(tmp_path: Path) -> None:
    v1 = tmp_path / "data" / "forward_observation" / "official_lifecycle_watch_v1"
    raw = tmp_path / "data" / "raw" / "forward_observation" / "official_lifecycle_watch_v1"
    reports = tmp_path / "data" / "backtests" / "diagnostics" / "reports" / "forward_observation" / "official_lifecycle_watch_v1"
    logs = tmp_path / "data" / "forward_observation" / "collector_logs"
    for path in [v1, raw, reports, logs]:
        path.mkdir(parents=True)
    (v1 / "births.jsonl").write_text('{"mint":"mint-a"}\n', encoding="utf-8")
    (v1 / "followup_paths.jsonl").write_text(
        '{"mint":"mint-a","crossed_20k":true,"fdv_proxy":22000}\n',
        encoding="utf-8",
    )
    (raw / "helius_rpc_raw.jsonl").write_text('{"signature":"sig-a"}\n', encoding="utf-8")
    (reports / "official_lifecycle_quality_audit.json").write_text('{"quality_status":"old"}\n', encoding="utf-8")
    (logs / "official_lifecycle_watch_v1_run.log").write_text("old log\n", encoding="utf-8")

    manifest = freeze_mixed_forward_campaign_pre_v2(data_root=tmp_path, copy_sources=True)

    quarantine_root = tmp_path / "data" / "forward_observation" / "quarantined" / "mixed_forward_campaign_pre_v2"
    assert manifest["quarantine_label"] == "mixed_forward_campaign_pre_v2"
    assert manifest["row_counts"]["forward_observation/official_lifecycle_watch_v1/births.jsonl"] == 1
    assert manifest["crossed_20k_counts"]["forward_observation/official_lifecycle_watch_v1/followup_paths.jsonl"] == 1
    assert "official paper-shadow evidence" in manifest["prohibited_uses"]
    assert (quarantine_root / "quarantine_manifest.json").exists()
    assert (quarantine_root / "quarantine_manifest.md").exists()
    assert (quarantine_root / "snapshot" / "forward_observation" / "official_lifecycle_watch_v1" / "births.jsonl").exists()
    assert (v1 / "births.jsonl").exists()


def test_freeze_mixed_forward_campaign_ignores_binary_sidecar_files(tmp_path: Path) -> None:
    v1 = tmp_path / "data" / "forward_observation" / "official_lifecycle_watch_v1"
    v1.mkdir(parents=True)
    (v1 / "births.jsonl").write_text('{"mint":"mint-a"}\n', encoding="utf-8")
    (v1 / "binary-artifact.bin").write_bytes(b"\xa2\x00\xff")

    manifest = freeze_mixed_forward_campaign_pre_v2(data_root=tmp_path, copy_sources=False)

    assert manifest["row_counts"]["forward_observation/official_lifecycle_watch_v1/births.jsonl"] == 1
    assert manifest["row_counts"]["forward_observation/official_lifecycle_watch_v1/binary-artifact.bin"] == 0


def test_v2_actionable_crossed_20k_writes_baseline_and_e2_label_only_rows(tmp_path: Path) -> None:
    config = OfficialLifecycleV2Config(data_root=tmp_path)
    initialize_official_lifecycle_namespace(config)
    machine = OfficialLifecycleStateMachine(config)

    machine.record_birth(
        {
            "mint": "mint-a",
            "creator": "creator-a",
            "create_signature": "sig-a",
            "create_time": 100,
            "observed_time": 101,
            "first_followup_attempt_time": 102,
            "first_followup_before_10k": True,
            "first_followup_before_20k": True,
            "official_accepted_birth": True,
            "valid_fdv_path_provenance": True,
        }
    )
    machine.record_path({"mint": "mint-a", "timestamp": 103, "fdv_proxy": 12_000, "event_count": 1, "buy_count": 1})
    machine.record_path({"mint": "mint-a", "timestamp": 104, "fdv_proxy": 22_000, "event_count": 2, "buy_count": 2})
    machine.record_path({"mint": "mint-a", "timestamp": 105, "fdv_proxy": 13_000, "event_count": 3, "buy_count": 2, "sell_count": 1})

    labels = _read_jsonl(config.paper_shadow_labels_path)
    exits = _read_jsonl(config.paper_shadow_exit_labels_path)
    assert len(labels) == 1
    assert labels[0]["mint"] == "mint-a"
    assert labels[0]["official_baseline_entry_eligible"] is True
    assert labels[0]["baseline_all_actionable_20k"] is True
    assert labels[0]["selected_exit_candidate_label"] == "E2"
    assert labels[0]["no_real_trade"] is True
    assert labels[0]["no_paper_trade_enabled"] is True
    assert {key for key in labels[0] if key.endswith("_pass")} == {"B1_pass", "B2_pass", "B3_pass", "B4_pass"}
    assert len(exits) >= 2
    assert exits[-1]["shadow_exit_label_only"] is True
    assert exits[-1]["no_real_trade"] is True
    assert exits[-1]["no_enabled_paper_trade"] is True
    assert exits[-1]["E2_state"] in {"tracking", "hypothetical_exit_condition_met"}


def test_v2_quality_audit_and_status_include_baseline_label_counts(tmp_path: Path) -> None:
    config = OfficialLifecycleV2Config(data_root=tmp_path)
    initialize_official_lifecycle_namespace(config)
    machine = OfficialLifecycleStateMachine(config)
    machine.record_birth(
        {
            "mint": "mint-a",
            "create_time": 100,
            "observed_time": 101,
            "first_followup_attempt_time": 102,
            "first_followup_before_20k": True,
            "valid_fdv_path_provenance": True,
        }
    )
    machine.record_path({"mint": "mint-a", "timestamp": 103, "fdv_proxy": 21_000})

    audit, paths = build_official_lifecycle_quality_audit(config)
    status = official_lifecycle_status(config)
    text = format_official_lifecycle_status(status)

    assert paths["json"].name == "official_lifecycle_v2_quality_audit.json"
    assert audit["sample_label"] == OFFICIAL_V2_SAMPLE_LABEL
    assert audit["funnel"]["official_baseline_entry_eligible"] == 1
    assert status["official_baseline_entry_eligible"] == 1
    assert status["B_label_counts"]["B1"] >= 0
    assert status["E2_labels_active"] >= 1
    assert "## Official Lifecycle Watch v2 Status" in text
    assert "Previous samples excluded: yes" in text
    assert "Official baseline entry eligible: 1" in text
    assert "B1/B2/B3/B4 label counts:" in text


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
