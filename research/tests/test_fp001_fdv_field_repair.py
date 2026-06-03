import csv
import json
from pathlib import Path

from research.mtp_research.validation.fp001_fdv_field_repair import (
    build_fp001_fdv_field_repair,
    discover_fdv_source,
)


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True))
            handle.write("\n")
    return path


def _write_csv(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=sorted({key for row in rows for key in row}))
        writer.writeheader()
        writer.writerows(rows)
    return path


def _combined_row(launch_id: str) -> dict:
    return {
        "launch_id": launch_id,
        "mint": f"mint-{launch_id}",
        "milestone_tier": "reached_1m_plus",
        "active_wallets_at_20k": 4,
        "shared_funding_proxy": False,
        "time_linked_funding_proxy": False,
        "launches_sharing_funder": 0,
        "creators_sharing_funder": 0,
        "has_all_three_p0_layers": True,
    }


def _source_row(launch_id: str, fdv: float = 20_000) -> dict:
    return {
        "launch_id": launch_id,
        "token_mint": f"mint-{launch_id}",
        "trigger_fdv_proxy": fdv,
        "fdv_per_event_at_20k": fdv / 10,
        "fdv_per_buy_at_20k": fdv / 4,
        "active_wallets_at_20k": 4,
        "event_count_at_20k": 10,
        "buy_count_at_20k": 4,
        "sell_count_at_20k": 1,
        "buy_sell_ratio_at_20k": 4,
        "trigger_age_seconds": 120,
    }


def _support_summary(tmp_path: Path) -> Path:
    selection = tmp_path / "selection.json"
    selection.write_text(
        json.dumps(
            {
                "selected_candidate_fingerprints": [
                    {
                        "fingerprint_id": "FP001",
                        "fingerprint_name": "Efficient Expansion With Clean Funding Structure",
                        "visible_features": "fdv_per_event_at_20k;fdv_per_buy_at_20k;fdv_per_active_wallet_at_20k;active_wallets_at_20k",
                        "hidden_structural_features": "shared_funding_proxy;time_linked_funding_proxy;launches_sharing_funder;creators_sharing_funder",
                        "entry_side_or_exit_side": "entry_side",
                        "expected_directions": json.dumps(
                            {
                                "fdv_per_event_at_20k": "higher",
                                "fdv_per_buy_at_20k": "higher",
                                "fdv_per_active_wallet_at_20k": "higher",
                                "active_wallets_at_20k": "not_zero",
                                "shared_funding_proxy": "lower",
                                "time_linked_funding_proxy": "lower",
                                "launches_sharing_funder": "lower",
                                "creators_sharing_funder": "lower",
                            },
                            sort_keys=True,
                        ),
                    }
                ]
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    support = tmp_path / "support.json"
    support.write_text(
        json.dumps(
            {
                "source_paths": {"selection_summary_path": str(selection)},
                "fingerprint_audits": [
                    {
                        "fingerprint_id": "FP001",
                        "fingerprint_name": "Efficient Expansion With Clean Funding Structure",
                        "features_audited": "fdv_per_event_at_20k;fdv_per_buy_at_20k;fdv_per_active_wallet_at_20k;active_wallets_at_20k;shared_funding_proxy;time_linked_funding_proxy;launches_sharing_funder;creators_sharing_funder",
                        "support_audit_decision": "ready_for_formal_descriptive_thesis",
                        "support_method": "fixed_median_reference_no_threshold_search",
                    }
                ],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return support


def test_discovers_fdv_source_and_derivable_fields(tmp_path: Path) -> None:
    source = _write_csv(tmp_path / "source.csv", [_source_row("a"), _source_row("b")])

    discovery = discover_fdv_source([source])

    assert discovery["selected_source_path"] == str(source)
    assert discovery["row_count"] == 2
    assert discovery["unique_launch_id_count"] == 2
    assert discovery["duplicate_launch_id_count"] == 0
    assert discovery["field_availability"]["fdv_per_active_wallet_at_20k"]["derivable"] is True


def test_repairs_by_launch_id_and_runs_fp001_when_ready(tmp_path: Path) -> None:
    combined = _write_jsonl(tmp_path / "combined.jsonl", [_combined_row("a"), _combined_row("b")])
    source = _write_csv(tmp_path / "source.csv", [_source_row("a"), _source_row("b")])

    report, paths = build_fp001_fdv_field_repair(
        combined_dataset_path=combined,
        source_paths=[source],
        support_summary_path=_support_summary(tmp_path),
        repaired_parquet_path=tmp_path / "repaired.parquet",
        repaired_jsonl_path=tmp_path / "repaired.jsonl",
        output_dir=tmp_path / "reports",
        fp001_output_dir=tmp_path / "fp001",
        status_path=tmp_path / "REPAIR_STATUS.md",
        fp001_status_path=tmp_path / "FP001_STATUS.md",
    )

    assert report["repair_readiness"] == "fdv_repair_ready_for_FP001_rerun"
    assert report["join_audit"]["combined_rows_before_repair"] == 2
    assert report["join_audit"]["rows_matched_on_launch_id"] == 2
    assert report["join_audit"]["rows_with_all_fp001_fields_after_repair"] == 2
    assert report["fp001_rerun"]["rerun_executed"] is True
    repaired_rows = [json.loads(line) for line in paths["repaired_jsonl_path"].read_text(encoding="utf-8").splitlines()]
    assert repaired_rows[0]["fdv_per_active_wallet_at_20k"] == 5_000


def test_duplicate_launch_id_conflicts_block_repair(tmp_path: Path) -> None:
    combined = _write_jsonl(tmp_path / "combined.jsonl", [_combined_row("a")])
    source = _write_csv(tmp_path / "source.csv", [_source_row("a", fdv=20_000), _source_row("a", fdv=30_000)])

    report, _paths = build_fp001_fdv_field_repair(
        combined_dataset_path=combined,
        source_paths=[source],
        support_summary_path=_support_summary(tmp_path),
        repaired_parquet_path=tmp_path / "repaired.parquet",
        repaired_jsonl_path=tmp_path / "repaired.jsonl",
        output_dir=tmp_path / "reports",
        fp001_output_dir=tmp_path / "fp001",
        status_path=tmp_path / "REPAIR_STATUS.md",
        fp001_status_path=tmp_path / "FP001_STATUS.md",
    )

    assert report["repair_readiness"] == "fdv_repair_blocked"
    assert report["join_audit"]["duplicate_conflicts"] == 1
    assert report["fp001_rerun"]["rerun_executed"] is False


def test_does_not_use_fuzzy_or_unproven_fallback_join(tmp_path: Path) -> None:
    combined = _write_jsonl(tmp_path / "combined.jsonl", [_combined_row("a")])
    source = _write_csv(tmp_path / "source.csv", [{**_source_row("other"), "token_mint": "mint-a"}])

    report, _paths = build_fp001_fdv_field_repair(
        combined_dataset_path=combined,
        source_paths=[source],
        support_summary_path=_support_summary(tmp_path),
        repaired_parquet_path=tmp_path / "repaired.parquet",
        repaired_jsonl_path=tmp_path / "repaired.jsonl",
        output_dir=tmp_path / "reports",
        fp001_output_dir=tmp_path / "fp001",
        status_path=tmp_path / "REPAIR_STATUS.md",
        fp001_status_path=tmp_path / "FP001_STATUS.md",
    )

    assert report["join_audit"]["rows_matched_on_launch_id"] == 0
    assert report["join_audit"]["rows_matched_on_fallback_key"] == 0
    assert report["repair_readiness"] == "fdv_repair_blocked"
    assert report["fp001_rerun"]["rerun_executed"] is False
