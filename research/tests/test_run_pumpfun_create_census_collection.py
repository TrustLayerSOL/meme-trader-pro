from pathlib import Path

from research.mtp_research.ingestion.run_pumpfun_create_census_collection import _load_checkpoint, _write_checkpoint


def test_checkpoint_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "checkpoint.json"

    _write_checkpoint(path, {"cursor_before": "sig-1", "accepted_launches": 3})

    assert _load_checkpoint(path) == {"cursor_before": "sig-1", "accepted_launches": 3}


def test_missing_checkpoint_loads_empty_dict(tmp_path: Path) -> None:
    assert _load_checkpoint(tmp_path / "missing.json") == {}
