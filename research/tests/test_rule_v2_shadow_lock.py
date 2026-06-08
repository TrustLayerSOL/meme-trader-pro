import json
from pathlib import Path

from research.mtp_research.validation.rule_v2_shadow_lock import (
    RULE_V2_VARIANT_1_ID,
    RULE_V2_VARIANT_2_ID,
    SHARED_RULE_V2_EXIT_ID,
    build_rule_v2_shadow_config,
    write_rule_v2_shadow_lock_artifacts,
)


def test_rule_v2_shadow_config_locks_two_buy_variants_and_shared_exit() -> None:
    config = build_rule_v2_shadow_config()

    assert config["mode"] == "paper_shadow_only"
    assert config["no_real_trade"] is True
    assert config["wallet_execution_enabled"] is False
    assert config["live_trading_enabled"] is False
    assert config["starting_paper_cash_usd"] == 300.0
    assert config["position_fraction"] == 0.05
    assert [variant["variant_id"] for variant in config["buy_variants"]] == [
        RULE_V2_VARIANT_1_ID,
        RULE_V2_VARIANT_2_ID,
    ]
    assert config["shared_exit_rule"]["rule_id"] == SHARED_RULE_V2_EXIT_ID
    assert config["entry_gate"]["confirmed_clean_10k_required"] is True
    assert config["entry_gate"]["confirmed_clean_20k_required"] is True
    assert config["entry_gate"]["buy_fdv_band_usd"] == {"min": 20_000.0, "max": 26_000.0}
    assert config["entry_gate"]["holder_gate"]["missing_holder_depth"] == "hard_reject"
    assert config["entry_gate"]["holder_gate"]["holder_count_lte_1"] == "hard_reject"
    assert config["entry_gate"]["hard_reject_risk_labels"] == [
        "dev_pump_suspect",
        "fake_volume_suspect",
        "missing_holder_depth",
    ]
    assert config["buy_variants"][0]["historical_support"]["support_count"] == 136
    assert config["buy_variants"][1]["additional_conditions"] == {"repeated_buyer_count_min": 1}
    assert config["tracking"]["continue_full_path_after_sell"] is True


def test_rule_v2_shadow_lock_artifacts_are_written_without_overwriting_rule_d(tmp_path: Path) -> None:
    data_root = tmp_path / "lake"
    repo_root = tmp_path / "repo"

    result = write_rule_v2_shadow_lock_artifacts(data_root=data_root, repo_root=repo_root)

    shadow_root = data_root / "data" / "forward_observation" / "rule_v2_shadow"
    repo_config_path = repo_root / "configs" / "rule_v2_shadow.json"
    locked_config_path = shadow_root / "rule_v2_shadow_locked_config.json"
    daily_status_path = shadow_root / "rule_v2_shadow_daily_status.md"
    manifest_path = shadow_root / "rule_v2_shadow_lock_manifest.json"

    assert result["locked"] is True
    assert result["current_rule_d_overwritten"] is False
    assert repo_config_path.exists()
    assert locked_config_path.exists()
    assert daily_status_path.exists()
    assert manifest_path.exists()

    locked_config = json.loads(locked_config_path.read_text(encoding="utf-8"))
    repo_config = json.loads(repo_config_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    status_text = daily_status_path.read_text(encoding="utf-8")

    assert locked_config == repo_config
    assert manifest["variant_ids"] == [RULE_V2_VARIANT_1_ID, RULE_V2_VARIANT_2_ID]
    assert manifest["shared_exit_rule_id"] == SHARED_RULE_V2_EXIT_ID
    assert "Current Rule D config overwritten: `False`" in status_text
    assert "No real trades, wallet execution, transaction signing, swaps, or order routing are enabled." in status_text


def test_rule_v2_shadow_lock_files_do_not_contain_execution_logic() -> None:
    guarded = [
        Path("research/mtp_research/validation/rule_v2_shadow_lock.py"),
        Path("research/mtp_research/validation/run_rule_v2_shadow_lock.py"),
    ]
    forbidden = ["send_transaction(", "sign_transaction(", "secret_key", "place_order(", "submit_order(", "swap("]
    for path in guarded:
        text = path.read_text(encoding="utf-8").lower() if path.exists() else ""
        for pattern in forbidden:
            assert pattern not in text
