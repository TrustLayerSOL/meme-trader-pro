from research.mtp_research.ingestion.run_program_signature_probe import main


def test_tiny_probe_does_not_execute_without_execute(monkeypatch, capsys) -> None:
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("probe attempted a network adapter call in dry-run mode")

    monkeypatch.setattr(
        "research.mtp_research.ingestion.run_program_signature_probe.HeliusHistoricalAdapter.from_env",
        fail_if_called,
    )
    monkeypatch.setattr(
        "sys.argv",
        ["run_program_signature_probe", "--program-id", "Program1111111111111111111111111111111111", "--limit", "5"],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "execute=False" in output
    assert "planned_signature_limit=5" in output
    assert "network_calls=0" in output
