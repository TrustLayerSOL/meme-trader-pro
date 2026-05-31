from pathlib import Path

from research.mtp_research.validation.thesis_decision_store import ThesisDecisionStore
from research.mtp_research.validation.thesis_models import ThesisDecision


def _decision(decision_id: str = "decision-1", status: str = "needs_more_data") -> ThesisDecision:
    return ThesisDecision(
        decision_id=decision_id,
        thesis_id="MTP-T999",
        created_at="2026-05-31T00:00:00+00:00",
        prior_status="active",
        recommended_status=status,
        confidence=0.5,
        reason="test",
    )


def test_inserts_decision(tmp_path: Path) -> None:
    store = ThesisDecisionStore(tmp_path / "decisions.jsonl")
    assert store.upsert(_decision()) == "inserted"
    assert store.path.exists()


def test_updates_existing_decision_by_decision_id(tmp_path: Path) -> None:
    store = ThesisDecisionStore(tmp_path / "decisions.jsonl")
    store.upsert(_decision(status="needs_more_data"))
    assert store.upsert(_decision(status="watchlist")) == "updated"
    assert store.get_by_decision_id("decision-1").recommended_status == "watchlist"


def test_upsert_many_counts_inserted_and_updated(tmp_path: Path) -> None:
    store = ThesisDecisionStore(tmp_path / "decisions.jsonl")
    store.upsert(_decision("decision-1"))
    counts = store.upsert_many([_decision("decision-1"), _decision("decision-2")])
    assert counts == {"inserted": 1, "updated": 1}


def test_load_all_returns_decisions_and_get_by_decision_id_works(tmp_path: Path) -> None:
    store = ThesisDecisionStore(tmp_path / "decisions.jsonl")
    store.upsert(_decision("decision-1"))
    store.upsert(_decision("decision-2"))
    assert [decision.decision_id for decision in store.load_all()] == ["decision-1", "decision-2"]
    assert store.get_by_decision_id("decision-2").decision_id == "decision-2"
