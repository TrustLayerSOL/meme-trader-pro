import json
import subprocess
from pathlib import Path


def test_cli_requires_dry_run(tmp_path: Path) -> None:
    raw_path = tmp_path / "raw.jsonl"
    raw_path.write_text("", encoding="utf-8")

    result = subprocess.run(
        [
            "./trading_env/bin/python",
            "-m",
            "research.mtp_research.validation.run_migration_targeted_discovery_plan",
            "--raw-transactions-path",
            str(raw_path),
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


def test_cli_writes_outputs_without_network_calls(tmp_path: Path) -> None:
    raw_path = tmp_path / "raw.jsonl"
    raw_path.write_text(
        json.dumps(
            {
                "signature": "sig",
                "mint": "mint",
                "raw_json": {
                    "meta": {"logMessages": ["Program log: Instruction: MigrateV2"]},
                    "transaction": {
                        "message": {
                            "accountKeys": [{"pubkey": "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"}],
                            "instructions": [{"programId": "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"}],
                        }
                    },
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "reports"

    result = subprocess.run(
        [
            "./trading_env/bin/python",
            "-m",
            "research.mtp_research.validation.run_migration_targeted_discovery_plan",
            "--raw-transactions-path",
            str(raw_path),
            "--output-dir",
            str(output_dir),
            "--dry-run",
        ],
        cwd=Path(__file__).resolve().parents[2],
        text=True,
        capture_output=True,
        check=True,
    )

    assert "network_calls_used=0" in result.stdout
    assert (output_dir / "migration_targeted_discovery_plan.json").exists()
    assert (output_dir / "migration_targeted_discovery_plan.md").exists()
