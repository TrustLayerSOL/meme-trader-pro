from pathlib import Path

from research.mtp_research.backtest.rule_backtest_models import (
    RuleBacktestConfig,
    RuleBacktestResult,
    RuleBacktestSummary,
    RuleDefinition,
)
from research.mtp_research.backtest.rule_backtest_store import RuleBacktestStore


def _result(result_id: str = "result-1", selected_count: int = 1) -> RuleBacktestResult:
    return RuleBacktestResult(
        result_id=result_id,
        created_at="2026-05-30T00:00:00+00:00",
        rule=RuleDefinition(rule_id="rule-1", name="Rule 1"),
        config=RuleBacktestConfig(config_id="cfg-1"),
        summary=RuleBacktestSummary(selected_count=selected_count),
    )


def test_inserts_result(tmp_path: Path) -> None:
    store = RuleBacktestStore(tmp_path / "results.jsonl")
    assert store.upsert(_result()) == "inserted"
    assert store.path.exists()


def test_updates_existing_result_by_result_id(tmp_path: Path) -> None:
    store = RuleBacktestStore(tmp_path / "results.jsonl")
    store.upsert(_result(selected_count=1))
    assert store.upsert(_result(selected_count=2)) == "updated"
    assert store.get_by_result_id("result-1").summary.selected_count == 2


def test_upsert_many_counts_inserted_and_updated(tmp_path: Path) -> None:
    store = RuleBacktestStore(tmp_path / "results.jsonl")
    store.upsert(_result("result-1"))
    counts = store.upsert_many([_result("result-1"), _result("result-2")])
    assert counts == {"inserted": 1, "updated": 1}


def test_load_all_returns_results_and_get_by_result_id_works(tmp_path: Path) -> None:
    store = RuleBacktestStore(tmp_path / "results.jsonl")
    store.upsert(_result("result-1"))
    store.upsert(_result("result-2"))
    assert [result.result_id for result in store.load_all()] == ["result-1", "result-2"]
    assert store.get_by_result_id("result-2").result_id == "result-2"
