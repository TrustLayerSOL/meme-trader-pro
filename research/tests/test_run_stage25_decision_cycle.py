import subprocess

from research.mtp_research.validation import run_stage25_decision_cycle as cycle


def test_stage25_decision_cycle_runs_mocked_substeps_without_network(monkeypatch, capsys) -> None:
    outputs = {
        "run_diagnostic_walk_forward_review": "recommended_next_action=scale_bounded_backfill_or_refine_rules\n",
        "run_rule_failure_review": (
            "recommended_next_action=scale_candidate_diversity_with_bounded_backfill\n"
            "evidence_scale_recommendation=add_candidates_and_time_span\n"
            "rule_review_recommendation=do_not_optimize_yet_collect_more_evidence\n"
            "markdown_path=rule.md\n"
            "json_path=rule.json\n"
        ),
        "run_fold_sufficiency_report": "best_config_name=best\n",
        "run_dataset_sufficiency_report": "total_rows=10\n",
    }

    def fake_run_step(command):
        module = command[command.index("-m") + 1].split(".")[-1]
        return subprocess.CompletedProcess(command, 0, outputs[module], "")

    monkeypatch.setattr(cycle, "run_step", fake_run_step)
    monkeypatch.setattr("sys.argv", ["run_stage25_decision_cycle"])

    assert cycle.main() == 0

    output = capsys.readouterr().out
    assert "final_decision=add more candidates" in output
    assert "network_calls=0" in output
