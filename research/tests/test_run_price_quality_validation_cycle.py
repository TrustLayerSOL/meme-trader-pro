import subprocess

from research.mtp_research.validation.run_price_quality_validation_cycle import main


def test_validation_cycle_runs_mocked_substeps_without_network(monkeypatch, capsys) -> None:
    commands: list[list[str]] = []

    def fake_run(command, check, capture_output, text):
        commands.append(command)
        module = command[2]
        stdout_by_module = {
            "research.mtp_research.validation.run_price_quality_gate": (
                "input_row_count=10\n"
                "passed_row_count=5\n"
                "pass_rate=0.5\n"
                "token_count_passed=3\n"
                "failure_reason_counts={'stale_entry_price': 5}\n"
                "markdown_path=gate.md\n"
                "json_path=gate.json\n"
                "network_calls=0\n"
            ),
            "research.mtp_research.validation.run_fold_sufficiency_report": (
                "best_config_name=ultra_short_15m_train_5m_test\n"
                "config_summary[ultra_short_15m_train_5m_test]=folds:2,valid_folds:1,valid_rule_folds:1,test_selected:5,warnings:[]\n"
                "json_path=fold.json\n"
                "network_calls=0\n"
            ),
            "research.mtp_research.validation.run_stage33_expansion_decision_cycle": (
                "rule_classifications={'positive_flow_basic': 'weak_noisy'}\n"
                "final_recommended_next_action=manual_review\n"
                "network_calls=0\n"
            ),
        }
        return subprocess.CompletedProcess(command, 0, stdout_by_module.get(module, "json_path=data/backtests/diagnostics/reports/mock.json\nnetwork_calls=0\n"), "")

    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setattr("sys.argv", ["run_price_quality_validation_cycle"])

    assert main() == 0

    output = capsys.readouterr().out
    assert "gated_row_count=5" in output
    assert "best_fold_config=ultra_short_15m_train_5m_test" in output
    assert "network_calls=0" in output
    assert len(commands) >= 8
