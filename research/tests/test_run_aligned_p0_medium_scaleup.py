import json
from pathlib import Path

from research.mtp_research.validation.run_aligned_p0_medium_scaleup import main


TIERS = [
    "reached_20k_but_never_50k",
    "reached_50k_but_never_100k",
    "reached_100k_but_never_200k",
    "reached_200k_but_never_500k",
    "reached_500k_but_never_1m",
    "reached_1m_plus",
]


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


def test_cli_dry_run_outputs_summary_lines(tmp_path: Path, capsys) -> None:
    launch_rows = []
    census_rows = []
    event_rows = []
    for tier_idx, tier in enumerate(TIERS):
        mint = f"mint-{tier_idx}"
        launch_ts = 1_760_000_000 + tier_idx * 86_400
        launch_rows.append(
            {
                "launch_id": f"launch-{tier_idx}",
                "mint": mint,
                "launch_ts": launch_ts,
                "launch_date": f"2026-01-{tier_idx + 1:02d}",
                "milestone_tier": tier,
                "crossing_20k_age": 30,
                "crossing_50k_age": 60,
                "crossing_100k_age": 90,
                "crossing_200k_age": 120,
                "crossing_500k_age": 150,
                "crossing_1m_age": 180,
            }
        )
        census_rows.append({"mint": mint, "creator_deployer": f"creator-{tier_idx}", "accepted": True})
        event_rows.append({"token_mint": mint, "actor": f"wallet-{tier_idx}", "block_time": launch_ts + 10, "side": "buy"})
    universe = _write_json(tmp_path / "universe.json", {"launch_feature_rows": launch_rows, "dataset": {"event_paths": []}})
    census = _write_jsonl(tmp_path / "census.jsonl", census_rows)
    events = _write_jsonl(tmp_path / "events.jsonl", event_rows)

    rc = main(
        [
            "--universe-path",
            str(universe),
            "--event-path",
            str(events),
            "--creator-lookup-path",
            str(census),
            "--output-root",
            str(tmp_path / "lake"),
            "--status-path",
            str(tmp_path / "STATUS.md"),
            "--preferred-per-tier",
            "1",
            "--minimum-total-targets",
            "6",
        ]
    )

    out = capsys.readouterr().out
    assert rc == 0
    assert "report_id=aligned_p0_medium_scaleup_v0" in out
    assert "mode=dry_run" in out
    assert "launches_selected=6" in out
    assert "request_ceiling_status=within_cap" in out
