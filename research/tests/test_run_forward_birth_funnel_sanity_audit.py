import json
from pathlib import Path

from research.mtp_research.validation.run_forward_birth_funnel_sanity_audit import main


def test_run_forward_birth_funnel_sanity_audit_cli(tmp_path: Path, capsys) -> None:
    root = tmp_path / "lake"
    obs = root / "data" / "forward_observation" / "efficient_movers"
    obs.mkdir(parents=True)
    _write_jsonl(
        obs / "candidates.jsonl",
        [
            {
                "observation_id": "birth-a",
                "mint": "mint-a",
                "freshness_lane": "birth_watch",
                "candidate_classification": "pumpfun_birth_candidate_observed",
                "event_type": "pumpfun_create",
                "observed_at": 100,
                "launch_time": 100,
            }
        ],
    )
    _write_jsonl(
        obs / "candidate_paths.jsonl",
        [
            {
                "observation_id": "follow-a",
                "mint": "mint-a",
                "event_type": "pumpfun_trade",
                "timestamp": 105,
                "source": "helius_birth_watch_followup",
                "fdv_proxy": 21_000,
            }
        ],
    )

    exit_code = main(["--data-root", str(root)])

    captured = capsys.readouterr().out
    assert exit_code == 0
    assert "report_id=forward_birth_funnel_sanity_audit_v0" in captured
    assert "network_calls_made=0" in captured
    assert "strict_deduped_funnel_counts=" in captured
    assert "validity_classification=" in captured


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
