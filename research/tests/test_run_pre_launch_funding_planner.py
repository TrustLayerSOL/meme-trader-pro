import json
import subprocess
from pathlib import Path


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def test_cli_requires_dry_run(tmp_path: Path) -> None:
    candidates_path = _write_jsonl(tmp_path / "candidates.jsonl", [])

    result = subprocess.run(
        [
            "./trading_env/bin/python",
            "-m",
            "research.mtp_research.validation.run_pre_launch_funding_planner",
            "--candidates-path",
            str(candidates_path),
            "--output-dir",
            str(tmp_path / "reports"),
        ],
        cwd=Path(__file__).resolve().parents[2],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "--dry-run" in result.stderr


def test_cli_writes_dry_run_outputs_without_network_calls(tmp_path: Path) -> None:
    candidates_path = _write_jsonl(
        tmp_path / "candidates.jsonl",
        [
            {
                "launch_id": "launch-a",
                "token_mint": "mint-a",
                "launch_ts": 1_700_000_000,
                "metadata_json": {"creator_deployer": "creator-a"},
            }
        ],
    )
    output_dir = tmp_path / "reports"

    result = subprocess.run(
        [
            "./trading_env/bin/python",
            "-m",
            "research.mtp_research.validation.run_pre_launch_funding_planner",
            "--candidates-path",
            str(candidates_path),
            "--output-dir",
            str(output_dir),
            "--max-creators",
            "1",
            "--dry-run",
        ],
        cwd=Path(__file__).resolve().parents[2],
        text=True,
        capture_output=True,
        check=True,
    )

    assert "network_calls_used=0" in result.stdout
    assert "helius_calls_used=0" in result.stdout
    assert (output_dir / "pre_launch_funding_dry_run_plan.json").exists()
    assert (output_dir / "pre_launch_funding_dry_run_plan.md").exists()
