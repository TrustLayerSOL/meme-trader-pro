import json
from pathlib import Path

from research.mtp_research.validation.run_entry_price_coverage_comparison import main


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_entry_price_coverage_comparison_cli_runs_with_temp_paths(tmp_path: Path, monkeypatch, capsys) -> None:
    clean = tmp_path / "clean.jsonl"
    fallback = tmp_path / "fallback.jsonl"
    output_dir = tmp_path / "reports"
    base = {
        "snapshot_id": "snapshot-1",
        "token_mint": "token-a",
        "snapshot_ts": 100,
        "horizon_name": "5m",
        "horizon_seconds": 300,
        "label_quality": "no_price",
    }
    _write_jsonl(clean, [{**base, "outcome_id": "o1"}])
    _write_jsonl(
        fallback,
        [
            {
                **base,
                "outcome_id": "o1",
                "entry_price": 1.0,
                "forward_return": 0.1,
                "entry_price_source": "nearest_research_fallback",
                "label_quality": "sparse",
            }
        ],
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_entry_price_coverage_comparison",
            "--clean-outcomes-path",
            str(clean),
            "--fallback-outcomes-path",
            str(fallback),
            "--output-dir",
            str(output_dir),
        ],
    )

    assert main() == 0
    output = capsys.readouterr().out
    assert "entry_price_gain=1" in output
    assert "no_price_reduction=1" in output
    assert list(output_dir.glob("entry_price_coverage_*.md"))
    assert list(output_dir.glob("entry_price_coverage_*.json"))
