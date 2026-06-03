import json
from pathlib import Path

from research.mtp_research.validation.run_fp001_formal_descriptive_thesis import main


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True))
            handle.write("\n")
    return path


def test_cli_writes_fp001_formal_descriptive_thesis(tmp_path: Path, capsys) -> None:
    selection = _write_json(
        tmp_path / "selection.json",
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
                    "data_still_missing": "true_market_cap",
                    "what_could_invalidate_it": "If evidence is not stable.",
                }
            ]
        },
    )
    support = _write_json(
        tmp_path / "support.json",
        {
            "source_paths": {"selection_summary_path": str(selection)},
            "fingerprint_audits": [
                {
                    "fingerprint_id": "FP001",
                    "fingerprint_name": "Efficient Expansion With Clean Funding Structure",
                    "features_audited": "fdv_per_event_at_20k;active_wallets_at_20k;shared_funding_proxy",
                    "support_audit_decision": "ready_for_formal_descriptive_thesis",
                    "support_method": "fixed_median_reference_no_threshold_search",
                }
            ],
        },
    )
    dataset = _write_jsonl(
        tmp_path / "dataset.jsonl",
        [
            {
                "launch_id": "a",
                "creator": "creator-a",
                "launch_date": "2026-01-01",
                "milestone_tier": "reached_1m_plus",
                "is_balanced_sample": True,
                "is_leftover_sample": False,
                "has_all_three_p0_layers": True,
                "fdv_per_event_at_20k": 10,
                "active_wallets_at_20k": 3,
                "shared_funding_proxy": False,
            },
            {
                "launch_id": "b",
                "creator": "creator-b",
                "launch_date": "2026-01-02",
                "milestone_tier": "reached_20k_but_never_50k",
                "is_balanced_sample": False,
                "is_leftover_sample": True,
                "has_all_three_p0_layers": True,
                "fdv_per_event_at_20k": 1,
                "active_wallets_at_20k": 2,
                "shared_funding_proxy": True,
            },
        ],
    )

    rc = main(
        [
            "--support-summary-path",
            str(support),
            "--combined-dataset-path",
            str(dataset),
            "--output-dir",
            str(tmp_path / "reports"),
            "--status-path",
            str(tmp_path / "STATUS.md"),
        ]
    )

    out = capsys.readouterr().out
    assert rc == 0
    assert "report_id=fp001_formal_descriptive_thesis_v0" in out
    assert "classification=" in out
    assert "rows_analyzed=2" in out
    assert "next_recommendation=" in out
