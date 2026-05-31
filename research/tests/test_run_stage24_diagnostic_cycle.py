import subprocess

from research.mtp_research.validation import run_stage24_diagnostic_cycle as cycle


def test_stage24_cycle_runs_mocked_substeps_without_network(monkeypatch, capsys) -> None:
    outputs = {
        "run_best_diagnostic_walk_forward": "best_config_name=best\nnetwork_calls=0\n",
        "run_diagnostic_walk_forward_review": (
            "rules_with_valid_folds=2\n"
            "best_rule_by_consistency=positive_flow_basic\n"
            "best_rule_by_avg_test_net=positive_flow_basic\n"
            "recommended_next_action=improve_clean_price_inference\n"
            "markdown_path=review.md\n"
            "json_path=review.json\n"
            "network_calls=0\n"
        ),
        "run_diagnostic_validation_review": "thesis_status_changes={}\nnetwork_calls=0\n",
        "run_thesis_evaluation": "recommended_status_counts={'needs_more_data': 1}\n",
    }

    def fake_run_step(command):
        module = command[command.index("-m") + 1].split(".")[-1]
        return subprocess.CompletedProcess(command, 0, outputs[module], "")

    monkeypatch.setattr(cycle, "run_step", fake_run_step)
    monkeypatch.setattr("sys.argv", ["run_stage24_diagnostic_cycle"])

    assert cycle.main() == 0

    output = capsys.readouterr().out
    assert "best_fold_config=best" in output
    assert "diagnostic_rules_with_valid_folds=2" in output
    assert "network_calls=0" in output
