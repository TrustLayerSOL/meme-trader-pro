from types import SimpleNamespace

from research.mtp_research.pipeline import run_post_backfill_rebuild_and_review as module


class _Row:
    token_mint = "token-1"


def test_post_backfill_rebuild_cli_uses_mocked_subprocess_and_no_network(monkeypatch, capsys) -> None:
    calls = []

    def fake_run(command, check, capture_output, text):
        calls.append(command)
        return SimpleNamespace(stdout="ok\n")

    fake_report = SimpleNamespace(
        time_span_seconds=1200,
        best_config_name=None,
        recommended_next_action="scale_bounded_backfill_for_more_time_span",
    )

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(module.RawTransactionStore, "load_all", lambda self: [object(), object()])
    monkeypatch.setattr(module.ResearchDatasetStore, "load_all", lambda self: [_Row()])
    monkeypatch.setattr(module, "real_token_mints_from_registry", lambda: {"token-1"})
    monkeypatch.setattr(module, "build_and_write_report", lambda args: (fake_report, "fold.md", "fold.json"))
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_post_backfill_rebuild_and_review",
            "--max-snapshots",
            "1000",
            "--real-only",
        ],
    )

    assert module.main() == 0
    output = capsys.readouterr().out
    assert len(calls) == 6
    assert all("run_evidence_backfill" not in " ".join(command) for command in calls)
    assert "raw_rows=2" in output
    assert "diagnostic_rows=1" in output
    assert "network_calls=0" in output
