import json
from pathlib import Path

from research.mtp_research.validation.t008_creator_migration_reputation_robustness import (
    build_t008_creator_migration_reputation_robustness_report,
    write_t008_robustness_outputs,
)


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def _candidate(index: int, creator: str, launch_ts: int) -> dict:
    return {
        "launch_id": f"launch-{index}",
        "token_mint": f"mint-{index}",
        "launch_ts": launch_ts,
        "metadata_json": {"creator_deployer": creator},
    }


def _outcome(index: int, runup: float, drawdown: float = -0.2) -> dict:
    return {
        "launch_id": f"launch-{index}",
        "token_mint": f"mint-{index}",
        "runups": {"max_runup_120m": runup},
        "drawdowns": {"max_drawdown_120m": drawdown},
        "price_available_120m": True,
        "has_liquidity_proxy_at_120m": True,
    }


def _label(index: int, creator: str, migration_ts: int, source: str) -> dict:
    return {
        "mint": f"mint-{index}",
        "creator": creator,
        "migration_time": f"1970-01-01T00:{migration_ts // 60:02d}:{migration_ts % 60:02d}+00:00",
        "migration_signature": f"migration-{index}-{source}",
        "pumpfun_migrate_event_observed": source == "pumpfun",
        "dex_pair_detected": source == "dexscreener",
        "graduated_to_pumpswap": source == "dexscreener",
        "migration_source": (
            "helius_json_rpc_pumpfun_migrate_log"
            if source == "pumpfun"
            else "dexscreener_pair_created_at"
        ),
    }


def test_robustness_report_builds_chronological_source_and_concentration_views(tmp_path: Path) -> None:
    candidates = []
    outcomes = []
    labels = []
    for index in range(1, 13):
        creator = "dominant" if index <= 7 else f"creator-{index}"
        candidates.append(_candidate(index, creator, index * 60))
        outcomes.append(_outcome(index, runup=float(index)))
        if index <= 4:
            labels.append(_label(index, creator, index * 60 + 5, "dexscreener"))
        if index in {5, 8}:
            labels.append(_label(index, creator, index * 60 + 5, "pumpfun"))

    report = build_t008_creator_migration_reputation_robustness_report(
        candidates_path=_write_jsonl(tmp_path / "candidates.jsonl", candidates),
        outcomes_path=_write_jsonl(tmp_path / "outcomes.jsonl", outcomes),
        migration_labels_path=_write_jsonl(tmp_path / "labels.jsonl", labels),
        min_split_bucket_count=1,
        data_limited_min_launches=10,
    )

    assert report["launch_count"] == 12
    assert report["original_t008_classification"] in {"weak_signal", "data_limited"}
    assert "first_half_second_half" in report["chronological_robustness"]
    assert "thirds" in report["chronological_robustness"]
    assert report["source_robustness"]["combined_labels"]["migration_records_used"] == 6
    assert report["source_robustness"]["pumpfun_only"]["migration_records_used"] == 2
    assert report["source_robustness"]["dexscreener_only"]["migration_records_used"] == 4
    assert report["source_robustness"]["exclude_dexscreener_only"]["migration_records_used"] == 2
    assert report["creator_concentration_robustness"]["four_plus_bucket"]["dominant_creator_share"] >= 0
    assert report["creator_concentration_robustness"]["exclude_top_1_creator_by_4plus_share"]["launch_count"] <= 12
    assert report["prior_launch_count_comparison"]["read"] in {
        "migration_graduation_more_informative",
        "raw_prior_launch_count_more_informative",
        "both_weak_or_noisy",
        "migration_reputation_may_proxy_prolific_creator_visibility",
    }
    assert "no_thesis_promotion" in report["methodology_flags"]


def test_outlier_sensitivity_and_outputs_are_deterministic(tmp_path: Path) -> None:
    candidates = [_candidate(index, "creator-a", index * 60) for index in range(1, 10)]
    outcomes = [_outcome(index, runup=1000.0 if index == 9 else float(index)) for index in range(1, 10)]
    labels = [_label(index, "creator-a", index * 60 + 5, "dexscreener") for index in range(1, 5)]
    paths = {
        "candidates_path": _write_jsonl(tmp_path / "candidates.jsonl", candidates),
        "outcomes_path": _write_jsonl(tmp_path / "outcomes.jsonl", outcomes),
        "migration_labels_path": _write_jsonl(tmp_path / "labels.jsonl", labels),
        "min_split_bucket_count": 1,
        "data_limited_min_launches": 8,
    }

    first = build_t008_creator_migration_reputation_robustness_report(**paths)
    second = build_t008_creator_migration_reputation_robustness_report(**paths)
    output_paths = write_t008_robustness_outputs(
        first,
        output_dir=tmp_path / "reports",
        status_path=tmp_path / "T008_ROBUSTNESS_STATUS.md",
    )

    assert first["outlier_sensitivity"] == second["outlier_sensitivity"]
    assert first["outlier_sensitivity"]["exclude_top_1pct_fdv_proxy_runups"]["launch_count"] < 9
    assert first["robustness_classification"] in {
        "stable_weak_signal",
        "unstable_weak_signal",
        "no_robust_signal",
        "data_limited",
    }
    assert output_paths["json_summary_path"].exists()
    assert output_paths["markdown_summary_path"].exists()
    assert output_paths["status_path"].exists()
    assert "No thesis promotion was performed" in output_paths["status_path"].read_text(encoding="utf-8")
