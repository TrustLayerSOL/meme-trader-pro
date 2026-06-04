import json
import sys
from pathlib import Path

from research.mtp_research.validation.run_pre_lifecycle_forward_pattern_preview import main


def test_cli_writes_pre_lifecycle_pattern_preview(tmp_path: Path, monkeypatch, capsys) -> None:
    root = tmp_path / "lake"
    obs = root / "data" / "forward_observation" / "efficient_movers"
    obs.mkdir(parents=True)
    _write_jsonl(
        obs / "candidates.jsonl",
        [
            {
                "observation_id": "birth-a",
                "mint": "mint-a",
                "token_mint": "mint-a",
                "creator": "creator-a",
                "event_type": "pumpfun_create",
                "freshness_lane": "birth_watch",
                "candidate_classification": "pumpfun_birth_candidate_observed",
                "create_time": 100,
                "observed_at": 101,
                "seconds_create_to_first_followup_attempt": 2,
                "first_followup_before_10k": True,
                "first_followup_before_20k": True,
            }
        ],
    )
    _write_jsonl(
        obs / "birth_watch_mints.jsonl",
        [
            {
                "observation_id": "birth-a",
                "mint": "mint-a",
                "event_type": "pumpfun_create",
                "freshness_lane": "birth_watch",
                "create_time": 100,
                "observed_at": 101,
            }
        ],
    )
    _write_jsonl(
        obs / "candidate_paths.jsonl",
        [
            {
                "observation_id": "birth-a",
                "mint": "mint-a",
                "timestamp": 105,
                "fdv_proxy": 12_000,
                "event_count": 1,
                "buy_count": 1,
                "sell_count": 0,
                "active_wallets": 1,
            },
            {
                "observation_id": "birth-a",
                "mint": "mint-a",
                "timestamp": 110,
                "fdv_proxy": 22_000,
                "event_count": 2,
                "buy_count": 2,
                "sell_count": 0,
                "active_wallets": 2,
            },
        ],
    )
    for name in ["candidate_events", "candidate_metadata", "candidate_holders", "candidate_drawdowns", "birth_followup_paths", "birth_followup_events"]:
        _write_jsonl(obs / f"{name}.jsonl", [])
    for name in ["birth_followup_status", "checkpoint", "status"]:
        (obs / f"{name}.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_pre_lifecycle_forward_pattern_preview",
            "--data-root",
            str(root),
            "--status-path",
            str(tmp_path / "STATUS.md"),
        ],
    )

    exit_code = main()
    captured = capsys.readouterr().out

    assert exit_code == 0
    assert "report_id=pre_lifecycle_forward_pattern_preview_v0" in captured
    assert "quarantine_label=pre_lifecycle_watch_forward_sample" in captured
    assert "network_calls_made=0" in captured
    assert "rows_mints_analyzed=1" in captured
    assert "crossed_20k=1" in captured
    assert (
        root
        / "data"
        / "backtests"
        / "diagnostics"
        / "reports"
        / "forward_observation"
        / "pre_lifecycle_watch_pattern_preview"
        / "pre_lifecycle_watch_pattern_preview_summary.json"
    ).exists()


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
