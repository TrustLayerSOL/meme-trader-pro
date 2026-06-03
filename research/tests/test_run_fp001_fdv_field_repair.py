import csv
import json
from pathlib import Path

from research.mtp_research.validation.run_fp001_fdv_field_repair import main


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


def test_cli_runs_fdv_field_repair(tmp_path: Path, capsys) -> None:
    selection = _write_jsonl(tmp_path / "unused.jsonl", [])
    selection_json = tmp_path / "selection.json"
    selection_json.write_text(
        json.dumps(
            {
                "selected_candidate_fingerprints": [
                    {
                        "fingerprint_id": "FP001",
                        "fingerprint_name": "Efficient Expansion With Clean Funding Structure",
                        "visible_features": "fdv_per_event_at_20k;active_wallets_at_20k",
                        "hidden_structural_features": "shared_funding_proxy",
                        "entry_side_or_exit_side": "entry_side",
                        "expected_directions": json.dumps(
                            {"fdv_per_event_at_20k": "higher", "active_wallets_at_20k": "not_zero", "shared_funding_proxy": "lower"},
                            sort_keys=True,
                        ),
                    }
                ]
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    support_json = tmp_path / "support.json"
    support_json.write_text(
        json.dumps(
            {
                "source_paths": {"selection_summary_path": str(selection_json)},
                "fingerprint_audits": [
                    {
                        "fingerprint_id": "FP001",
                        "fingerprint_name": "Efficient Expansion With Clean Funding Structure",
                        "features_audited": "fdv_per_event_at_20k;active_wallets_at_20k;shared_funding_proxy",
                        "support_audit_decision": "ready_for_formal_descriptive_thesis",
                    }
                ],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    assert selection.exists()
    combined = _write_jsonl(
        tmp_path / "combined.jsonl",
        [
            {
                "launch_id": "a",
                "mint": "mint-a",
                "milestone_tier": "reached_1m_plus",
                "active_wallets_at_20k": 4,
                "shared_funding_proxy": False,
                "time_linked_funding_proxy": False,
                "launches_sharing_funder": 0,
                "creators_sharing_funder": 0,
            }
        ],
    )
    source = _write_csv(
        tmp_path / "source.csv",
        [
            {
                "launch_id": "a",
                "token_mint": "mint-a",
                "trigger_fdv_proxy": 20_000,
                "fdv_per_event_at_20k": 2_000,
                "fdv_per_buy_at_20k": 5_000,
                "active_wallets_at_20k": 4,
            }
        ],
    )

    rc = main(
        [
            "--combined-dataset-path",
            str(combined),
            "--source-path",
            str(source),
            "--support-summary-path",
            str(support_json),
            "--repaired-parquet-path",
            str(tmp_path / "repaired.parquet"),
            "--repaired-jsonl-path",
            str(tmp_path / "repaired.jsonl"),
            "--output-dir",
            str(tmp_path / "reports"),
            "--fp001-output-dir",
            str(tmp_path / "fp001"),
            "--status-path",
            str(tmp_path / "REPAIR_STATUS.md"),
            "--fp001-status-path",
            str(tmp_path / "FP001_STATUS.md"),
        ]
    )

    out = capsys.readouterr().out
    assert rc == 0
    assert "report_id=fp001_fdv_field_repair_v0" in out
    assert "repair_readiness=fdv_repair_ready_for_FP001_rerun" in out
    assert "rows_matched=1" in out
    assert "fp001_rerun_executed=True" in out
