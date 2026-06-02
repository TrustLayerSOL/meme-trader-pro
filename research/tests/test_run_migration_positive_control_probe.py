import json
import subprocess
from pathlib import Path


def test_cli_dry_run_writes_outputs_without_network_calls(tmp_path: Path) -> None:
    candidates_path = tmp_path / "candidates.jsonl"
    candidates_path.write_text(
        json.dumps(
            {
                "token_mint": "mint-a",
                "launch_ts": 1_700_000_000,
                "metadata_json": {
                    "bonding_curve": "curve-a",
                    "associated_bonding_curve": "assoc-a",
                    "creator_deployer": "creator-a",
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
            "research.mtp_research.validation.run_migration_positive_control_probe",
            "--candidates-path",
            str(candidates_path),
            "--known-mint",
            "mint-a",
            "--known-signature",
            "sig-a",
            "--output-dir",
            str(output_dir),
        ],
        cwd=Path(__file__).resolve().parents[2],
        text=True,
        capture_output=True,
        check=True,
    )

    assert "execute=False" in result.stdout
    assert "network_calls_used=0" in result.stdout
    assert (output_dir / "migration_positive_control_probe.json").exists()
    assert (output_dir / "migration_positive_control_probe.md").exists()
