from research.mtp_research.validation.run_stage33_expansion_decision_cycle import main


def test_stage33_cycle_runs_with_mocked_subcommands(monkeypatch, capsys) -> None:
    calls = []

    def fake_run_command(label, command):
        calls.append((label, command))
        if label == "evidence_expansion_decision":
            return (
                "recommended_next_action=run_bounded_evidence_expansion\n"
                "recommended_command=./trading_env/bin/python -m research.mtp_research.pipeline.run_time_span_backfill_execute --execute\n"
                "rule_signal_classifications={'rule-1': 'weak_noisy'}\n"
                "markdown_path=report.md\n"
                "json_path=report.json\n"
                "network_calls=0\n"
            )
        return "network_calls=0\n"

    monkeypatch.setattr(
        "sys.argv",
        ["run_stage33_expansion_decision_cycle", "--real-only"],
    )
    monkeypatch.setattr(
        "research.mtp_research.validation.run_stage33_expansion_decision_cycle.run_command",
        fake_run_command,
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "final_recommended_next_action=run_bounded_evidence_expansion" in output
    assert "bounded_command=./trading_env/bin/python" in output
    assert "network_calls=0" in output
    assert [label for label, _ in calls][-1] == "evidence_expansion_decision"
