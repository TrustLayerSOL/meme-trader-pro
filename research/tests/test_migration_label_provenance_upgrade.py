import json
from pathlib import Path

from research.mtp_research.validation.migration_label_provenance_upgrade import (
    build_migration_label_provenance_upgrade_report,
    write_migration_label_provenance_upgrade_outputs,
)


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def _candidate(index: int, creator: str) -> dict:
    return {
        "launch_id": f"launch-{index}",
        "token_mint": f"mint-{index}",
        "launch_ts": 1_700_000_000 + index,
        "metadata_json": {"creator_deployer": creator},
    }


def test_provenance_upgrade_separates_ground_truth_from_proxy_labels(tmp_path: Path) -> None:
    candidates = [_candidate(index, "creator-a") for index in range(1, 5)]
    labels = [
        {
            "mint": "mint-1",
            "creator": "creator-a",
            "migration_time": "2026-05-25T13:37:31+00:00",
            "migration_signature": "pumpfun-migration-1",
            "pumpfun_migrate_event_observed": True,
            "migration_source": "helius_json_rpc_pumpfun_migrate_log",
        },
        {
            "mint": "mint-2",
            "creator": "creator-a",
            "migration_time": "2026-05-25T13:38:31+00:00",
            "dex_pair_detected": True,
            "graduated_to_pumpswap": True,
            "migration_source": "dexscreener_pair_created_at",
        },
        {
            "mint": "mint-3",
            "creator": "creator-a",
            "dex_pair_detected": True,
            "migration_source": "dexscreener_pair_created_at",
        },
    ]

    report = build_migration_label_provenance_upgrade_report(
        candidates_path=_write_jsonl(tmp_path / "candidates.jsonl", candidates),
        migration_labels_path=_write_jsonl(tmp_path / "labels.jsonl", labels),
        max_targets=2,
    )

    assert report["source_quality_counts"]["ground_truth_pumpfun_migrate"] == 1
    assert report["source_quality_counts"]["source_proxy_dexscreener_pair"] == 2
    assert report["timestamp_missing_counts"]["source_proxy_dexscreener_pair"] == 1
    assert report["t008_blocker_summary"]["depends_mainly_on_proxy_labels"] is True
    assert report["readiness_classification"] == "migration_label_provenance_needs_non_dexscreener_evidence"
    assert report["acquisition_plan"]["network_calls_made"] == 0
    assert len(report["acquisition_plan"]["selected_targets"]) == 2
    assert report["acquisition_plan"]["selected_targets"][0]["reason_selected"] in {
        "dexscreener_proxy_needs_pumpfun_confirmation",
        "missing_timestamp_needs_confirmation",
    }


def test_outputs_and_guardrails_are_deterministic(tmp_path: Path) -> None:
    candidates = [_candidate(index, f"creator-{index}") for index in range(1, 4)]
    labels = [
        {
            "mint": "mint-1",
            "creator": "creator-1",
            "migration_time": "2026-05-25T13:37:31+00:00",
            "dex_pair_detected": True,
            "migration_source": "dexscreener_pair_created_at",
        }
    ]
    paths = {
        "candidates_path": _write_jsonl(tmp_path / "candidates.jsonl", candidates),
        "migration_labels_path": _write_jsonl(tmp_path / "labels.jsonl", labels),
        "max_targets": 5,
    }

    first = build_migration_label_provenance_upgrade_report(**paths)
    second = build_migration_label_provenance_upgrade_report(**paths)
    output_paths = write_migration_label_provenance_upgrade_outputs(
        first,
        output_dir=tmp_path / "reports",
        status_path=tmp_path / "MIGRATION_LABEL_PROVENANCE_STATUS.md",
    )

    assert first["acquisition_plan"] == second["acquisition_plan"]
    assert "no_network_calls" in first["methodology_flags"]
    assert "no_thesis_promotion" in first["methodology_flags"]
    assert output_paths["json_summary_path"].exists()
    assert output_paths["markdown_summary_path"].exists()
    assert output_paths["status_path"].exists()
    assert "No network calls were made" in output_paths["status_path"].read_text(encoding="utf-8")
