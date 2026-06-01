from research.mtp_research.ingestion.program_signature_discovery_plan import (
    build_default_program_signature_discovery_plan,
)
from research.mtp_research.ingestion.run_program_signature_discovery_plan import main


def test_program_signature_plan_has_candidate_sources_and_is_dry_run_by_default() -> None:
    plan = build_default_program_signature_discovery_plan()

    target_names = {target.name for target in plan.targets}
    assert "pump_fun_token_creation" in target_names
    assert "pumpswap_pool_creation" in target_names
    assert "raydium_launchlab_pool_creation" in target_names
    assert "dry_run_default_no_network_calls" in plan.warning_flags


def test_program_signature_plan_cli_does_not_probe_without_execute(monkeypatch, capsys) -> None:
    monkeypatch.setattr("sys.argv", ["run_program_signature_discovery_plan"])

    assert main() == 0

    output = capsys.readouterr().out
    assert "execute_probe=False" in output
    assert "network_calls=0" in output
    assert "pump_fun_token_creation" in output
