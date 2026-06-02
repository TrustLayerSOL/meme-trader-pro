import json
from pathlib import Path

import pytest

from research.mtp_research.validation.creator_migration_reputation_thesis import (
    build_t008_creator_migration_reputation_report,
    write_t008_report_outputs,
)


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def _candidate(index: int, creator: str, launch_ts: int) -> dict:
    return {
        "launch_id": f"launch-{index}",
        "token_mint": f"mint-{index}",
        "launch_ts": launch_ts,
        "launch_time_utc": f"1970-01-01T00:{index:02d}:00+00:00",
        "metadata_json": {"creator_deployer": creator},
    }


def _outcome(index: int, *, runup: float = 1.0, drawdown: float = -0.2) -> dict:
    return {
        "launch_id": f"launch-{index}",
        "token_mint": f"mint-{index}",
        "runups": {"max_runup_120m": runup},
        "drawdowns": {"max_drawdown_120m": drawdown},
        "price_available_120m": True,
        "has_liquidity_proxy_at_120m": True,
    }


def _label(index: int, creator: str, migration_ts: int, *, source: str = "helius_json_rpc_pumpfun_migrate_log") -> dict:
    return {
        "mint": f"mint-{index}",
        "creator": creator,
        "migration_time": f"1970-01-01T00:{migration_ts // 60:02d}:{migration_ts % 60:02d}+00:00",
        "migration_signature": f"migration-{index}-{source}",
        "pumpfun_migrate_event_observed": source.startswith("helius"),
        "dex_pair_detected": source.startswith("dexscreener"),
        "graduated_to_pumpswap": source.startswith("dexscreener"),
        "migration_source": source,
    }


def test_builds_leakage_safe_prior_migration_features_and_buckets(tmp_path: Path) -> None:
    candidates = [_candidate(i, "creator-a", i * 60) for i in range(1, 7)]
    labels = [
        _label(1, "creator-a", 70),
        _label(2, "creator-a", 130),
        _label(3, "creator-a", 190),
        _label(4, "creator-a", 250),
        _label(6, "creator-a", 500),  # future label for launch 5; must not leak into launch 5.
    ]

    report = build_t008_creator_migration_reputation_report(
        candidates_path=_write_jsonl(tmp_path / "candidates.jsonl", candidates),
        outcomes_path=_write_jsonl(tmp_path / "outcomes.jsonl", [_outcome(i, runup=i) for i in range(1, 7)]),
        migration_labels_path=_write_jsonl(tmp_path / "labels.jsonl", labels),
    )

    rows = {row["token_mint"]: row for row in report["launch_rows"]}
    assert rows["mint-1"]["features"]["creator_prior_migration_or_graduation_count"] == 0
    assert rows["mint-3"]["features"]["creator_prior_migration_or_graduation_count"] == 2
    assert rows["mint-5"]["features"]["creator_prior_migration_or_graduation_count"] == 4
    assert rows["mint-5"]["features"]["creator_prior_migration_or_graduation_count_bucket"] == "4_plus"
    assert rows["mint-5"]["features"]["creator_has_4plus_prior_migrations_or_graduations"] is True
    assert rows["mint-5"]["features"]["creator_prior_last_migration_or_graduation_age_seconds"] == 50
    assert report["leakage_rule"]["missing_migration_timestamp_counted_as_prior"] is False
    assert "no_future_leakage" in report["methodology_flags"]
    assert "no_threshold_optimization" in report["methodology_flags"]


def test_missing_timestamp_labels_are_not_counted_as_prior_history(tmp_path: Path) -> None:
    candidates = [_candidate(1, "creator-a", 60), _candidate(2, "creator-a", 120)]
    labels = [
        {
            "mint": "mint-1",
            "creator": "creator-a",
            "dex_pair_detected": True,
            "migration_time": None,
            "migration_source": "dexscreener_pair_created_at",
        }
    ]

    report = build_t008_creator_migration_reputation_report(
        candidates_path=_write_jsonl(tmp_path / "candidates.jsonl", candidates),
        outcomes_path=_write_jsonl(tmp_path / "outcomes.jsonl", [_outcome(1), _outcome(2)]),
        migration_labels_path=_write_jsonl(tmp_path / "labels.jsonl", labels),
    )

    rows = {row["token_mint"]: row for row in report["launch_rows"]}
    assert rows["mint-2"]["features"]["creator_prior_migration_or_graduation_count"] == 0
    assert report["feature_audit"]["migration_timestamp_missing_count"] == 1
    assert "missing_migration_timestamps_not_counted" in report["warning_flags"]


def test_zero_fdv_proxy_outcomes_are_available_not_missing(tmp_path: Path) -> None:
    candidates = [_candidate(1, "creator-a", 60)]
    outcomes = [_outcome(1, runup=0.0, drawdown=0.0)]

    report = build_t008_creator_migration_reputation_report(
        candidates_path=_write_jsonl(tmp_path / "candidates.jsonl", candidates),
        outcomes_path=_write_jsonl(tmp_path / "outcomes.jsonl", outcomes),
        migration_labels_path=_write_jsonl(tmp_path / "labels.jsonl", []),
    )

    assert report["outcome_coverage"]["fdv_proxy_runup_available"] == 1
    assert report["outcome_coverage"]["fdv_proxy_drawdown_available"] == 1
    assert "fdv_proxy_outcomes_missing" not in report["warning_flags"]


def test_source_sensitivity_keeps_dexscreener_and_pumpfun_evidence_separate(tmp_path: Path) -> None:
    candidates = [_candidate(i, "creator-a", i * 60) for i in range(1, 8)]
    labels = [
        _label(1, "creator-a", 70, source="helius_json_rpc_pumpfun_migrate_log"),
        _label(2, "creator-a", 130, source="helius_json_rpc_pumpfun_migrate_log"),
        _label(3, "creator-a", 190, source="dexscreener_pair_created_at"),
        _label(4, "creator-a", 250, source="dexscreener_pair_created_at"),
    ]

    report = build_t008_creator_migration_reputation_report(
        candidates_path=_write_jsonl(tmp_path / "candidates.jsonl", candidates),
        outcomes_path=_write_jsonl(tmp_path / "outcomes.jsonl", [_outcome(i, runup=i) for i in range(1, 8)]),
        migration_labels_path=_write_jsonl(tmp_path / "labels.jsonl", labels),
    )

    assert report["feature_audit"]["source_split"]["pumpfun_migration_event"] == 2
    assert report["feature_audit"]["source_split"]["dexscreener_pair_detection"] == 2
    assert report["sensitivity_checks"]["exclude_dexscreener_only"]["launch_count"] == 7
    assert report["sensitivity_checks"]["pumpfun_only"]["migration_records_used"] == 2
    assert report["sensitivity_checks"]["dexscreener_only"]["migration_records_used"] == 2
    assert report["sensitivity_checks"]["four_plus_bucket_creator_dominance"]["dominant_creator_share"] >= 0


def test_outputs_are_deterministic_and_guarded(tmp_path: Path) -> None:
    candidates = [_candidate(i, "creator-a" if i <= 6 else "creator-b", i * 60) for i in range(1, 10)]
    labels = [_label(i, "creator-a", i * 60 + 10) for i in range(1, 5)]
    paths = {
        "candidates_path": _write_jsonl(tmp_path / "candidates.jsonl", candidates),
        "outcomes_path": _write_jsonl(tmp_path / "outcomes.jsonl", [_outcome(i, runup=i) for i in range(1, 10)]),
        "migration_labels_path": _write_jsonl(tmp_path / "labels.jsonl", labels),
    }

    first = build_t008_creator_migration_reputation_report(**paths)
    second = build_t008_creator_migration_reputation_report(**paths)
    output_paths = write_t008_report_outputs(
        first,
        output_dir=tmp_path / "reports",
        status_path=tmp_path / "T008_STATUS.md",
    )

    assert first["primary_bucket_table"] == second["primary_bucket_table"]
    assert first["final_classification"] in {"descriptive_signal_present", "weak_signal", "no_signal", "data_limited"}
    assert "no_thesis_promotion" in first["methodology_flags"]
    assert "no_trading_rules" in first["methodology_flags"]
    assert "no_profitability_claims" in first["methodology_flags"]
    assert output_paths["json_summary_path"].exists()
    assert output_paths["markdown_summary_path"].exists()
    assert output_paths["status_path"].exists()
    assert "No thesis promotion was performed" in output_paths["status_path"].read_text(encoding="utf-8")


def test_strict_only_mode_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="T008 must use all-collected"):
        build_t008_creator_migration_reputation_report(
            candidates_path=_write_jsonl(tmp_path / "candidates.jsonl", []),
            outcomes_path=_write_jsonl(tmp_path / "outcomes.jsonl", []),
            migration_labels_path=_write_jsonl(tmp_path / "labels.jsonl", []),
            dataset_scope="strict",
        )
