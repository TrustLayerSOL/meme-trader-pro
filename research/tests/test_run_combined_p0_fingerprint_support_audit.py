import json
from pathlib import Path

from research.mtp_research.validation.run_combined_p0_fingerprint_support_audit import main


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


def test_cli_writes_support_audit(tmp_path: Path, capsys) -> None:
    selection = _write_json(
        tmp_path / "selection.json",
        {
            "selected_candidate_fingerprints": [
                {
                    "fingerprint_id": "FP001",
                    "fingerprint_name": "Test Fingerprint",
                    "visible_features": "fdv_per_event_at_20k",
                    "hidden_structural_features": "shared_funding_proxy",
                    "expected_directions": json.dumps(
                        {"fdv_per_event_at_20k": "higher", "shared_funding_proxy": "lower"},
                        sort_keys=True,
                    ),
                }
            ]
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
                "fdv_per_event_at_20k": 10,
                "shared_funding_proxy": False,
            },
            {
                "launch_id": "b",
                "creator": "creator-b",
                "launch_date": "2026-01-02",
                "milestone_tier": "reached_20k_but_never_50k",
                "is_balanced_sample": False,
                "is_leftover_sample": True,
                "fdv_per_event_at_20k": 1,
                "shared_funding_proxy": True,
            },
        ],
    )

    rc = main(
        [
            "--selection-summary-path",
            str(selection),
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
    assert "report_id=combined_p0_fingerprint_support_audit_v0" in out
    assert "readiness_classification=" in out
    assert "recommended_next_action=" in out
