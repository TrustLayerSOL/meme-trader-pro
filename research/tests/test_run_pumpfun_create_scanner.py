from research.mtp_research.ingestion.run_pumpfun_create_scanner import main


def test_cli_dry_run_works_without_network(monkeypatch, tmp_path, capsys) -> None:
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("dry-run attempted to create a Helius adapter")

    monkeypatch.setattr(
        "research.mtp_research.ingestion.run_pumpfun_create_scanner.HeliusHistoricalAdapter.from_env",
        fail_if_called,
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_pumpfun_create_scanner",
            "--output-dir",
            str(tmp_path),
            "--max-batches",
            "2",
            "--emit-rejected-examples",
            "--min-confidence",
            "medium",
        ],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "executed=False" in output
    assert "max_batches=2" in output
    assert "min_confidence=medium" in output
    assert "network_calls=0" in output
    assert (tmp_path / "pumpfun_create_scan_plan.json").exists()
