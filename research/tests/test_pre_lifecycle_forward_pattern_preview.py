import json
from pathlib import Path

from research.mtp_research.validation.pre_lifecycle_forward_pattern_preview import (
    PROHIBITED_USES,
    QUARANTINE_LABEL,
    build_analysis_dataset,
    build_broad_behavior_comparison_table,
    build_fdv_signal_sanity_table,
    build_new_behavior_candidates,
    build_pre_lifecycle_forward_pattern_preview,
    calculate_funnel_stats,
)


def test_builds_quarantine_manifest_and_dataset_outputs(tmp_path: Path) -> None:
    root = tmp_path / "lake"
    _seed_forward_files(root)

    summary, paths = build_pre_lifecycle_forward_pattern_preview(root, status_path=tmp_path / "STATUS.md")

    assert summary["quarantine_label"] == QUARANTINE_LABEL
    assert summary["network_calls_made"] == 0
    assert summary["rows_mints_analyzed"] == 5
    assert summary["funnel_stats"]["counts"]["crossed_10k"] == 5
    assert summary["funnel_stats"]["counts"]["crossed_20k"] == 5
    assert summary["funnel_stats"]["counts"]["crossed_50k"] == 4
    assert summary["funnel_stats"]["counts"]["crossed_100k"] == 3
    assert summary["funnel_stats"]["counts"]["crossed_500k"] == 2
    assert summary["funnel_stats"]["counts"]["crossed_1m"] == 1
    assert "validation" in summary["prohibited_uses"]
    assert "live trading" in summary["prohibited_uses"]
    assert "paper trading" in summary["prohibited_uses"]
    assert paths["quarantine_manifest_json"].exists()
    assert paths["quarantine_manifest_md"].exists()
    assert paths["analysis_dataset_jsonl"].exists()
    assert paths["analysis_dataset_parquet"].exists()
    manifest = json.loads(paths["quarantine_manifest_json"].read_text(encoding="utf-8"))
    assert manifest["quarantine_label"] == QUARANTINE_LABEL
    assert manifest["current_funnel_counts"]["crossed_20k"] == 5


def test_one_row_per_mint_dataset_has_required_forward_fields(tmp_path: Path) -> None:
    root = tmp_path / "lake"
    _seed_forward_files(root)
    summary, paths = build_pre_lifecycle_forward_pattern_preview(root, status_path=tmp_path / "STATUS.md")

    rows = [json.loads(line) for line in paths["analysis_dataset_jsonl"].read_text(encoding="utf-8").splitlines()]

    assert summary["rows_mints_analyzed"] == 5
    assert len(rows) == 5
    row = next(item for item in rows if item["mint"] == "mint-a")
    assert row["quarantine_label"] == QUARANTINE_LABEL
    assert row["creator"] == "creator-a"
    assert row["first_followup_before_10k"] is True
    assert row["first_followup_before_20k"] is True
    assert row["crossed_1m"] is True
    assert row["fdv_per_event_at_10k"] == 12_000
    assert row["fdv_per_buy_at_20k"] == 25_000
    assert row["create_to_first_followup_seconds"] == 2
    assert row["create_to_20k_seconds"] == 10
    assert row["10k_to_20k_seconds"] == 5
    assert row["social_link_count"] == 2
    assert row["metadata_completeness_score"] >= 4
    assert row["top_holder_share_proxy"] == 0.2


def test_funnel_fdv_behavior_and_new_behavior_tables_are_deterministic(tmp_path: Path) -> None:
    root = tmp_path / "lake"
    _seed_forward_files(root)
    summary, paths = build_pre_lifecycle_forward_pattern_preview(root, status_path=tmp_path / "STATUS.md")

    dataset = [json.loads(line) for line in paths["analysis_dataset_jsonl"].read_text(encoding="utf-8").splitlines()]
    assert calculate_funnel_stats(dataset) == summary["funnel_stats"]
    assert build_fdv_signal_sanity_table(dataset) == build_fdv_signal_sanity_table(dataset)
    behavior = build_broad_behavior_comparison_table(dataset)
    new_behavior = build_new_behavior_candidates(dataset)
    assert behavior == build_broad_behavior_comparison_table(dataset)
    assert new_behavior == build_new_behavior_candidates(dataset)
    assert paths["fdv_signal_csv"].exists()
    assert paths["behavior_csv"].exists()
    assert paths["new_behavior_csv"].exists()
    assert {row["classification"] for row in behavior} <= {
        "forward_promising_candidate",
        "possible_risk_filter",
        "path_or_exit_candidate",
        "data_limited",
        "no_clear_difference",
    }
    assert any(row["behavior"] == "first_followup_freshness" for row in new_behavior)


def test_guardrails_do_not_include_trading_or_validation_claims(tmp_path: Path) -> None:
    root = tmp_path / "lake"
    _seed_forward_files(root)

    summary, paths = build_pre_lifecycle_forward_pattern_preview(root, status_path=tmp_path / "STATUS.md")

    combined = json.dumps(summary, sort_keys=True).lower() + paths["status_markdown"].read_text(encoding="utf-8").lower()
    assert "no_validation" in summary["guardrails"]
    assert "no_backtest" in summary["guardrails"]
    for phrase in ("no_buy_orders", "no_sell_orders", "no_profitability_claims", "no_paper_trading", "no_live_trading"):
        assert phrase in combined
    for prohibited in PROHIBITED_USES:
        assert prohibited.lower() in combined


def _seed_forward_files(root: Path) -> None:
    obs = root / "data" / "forward_observation" / "efficient_movers"
    obs.mkdir(parents=True)
    specs = [
        ("mint-a", "creator-a", 1_000, [12_000, 25_000, 60_000, 120_000, 600_000, 1_100_000]),
        ("mint-b", "creator-b", 2_000, [11_000, 22_000, 55_000, 130_000, 520_000]),
        ("mint-c", "creator-c", 3_000, [10_500, 24_000, 80_000, 110_000]),
        ("mint-d", "creator-d", 4_000, [10_500, 21_000, 51_000]),
        ("mint-e", "creator-e", 5_000, [10_500, 20_500]),
    ]
    candidates = []
    paths = []
    metadata = []
    holders = []
    events = []
    for idx, (mint, creator, create_time, fdvs) in enumerate(specs, start=1):
        candidates.append(
            {
                "observation_id": f"birth-{mint}",
                "mint": mint,
                "token_mint": mint,
                "creator": creator,
                "source_adapter": "helius_birth_watch",
                "source": "helius_birth_watch",
                "event_type": "pumpfun_create",
                "candidate_classification": "pumpfun_birth_candidate_observed",
                "freshness_lane": "birth_watch",
                "freshness_class": "true_birth_observed",
                "create_time": create_time,
                "observed_at": create_time + 1,
                "seconds_create_to_first_followup_attempt": 2,
                "first_followup_before_10k": True,
                "first_followup_before_20k": True,
                "token_name": f"Token {idx}",
                "token_symbol": f"T{idx}",
            }
        )
        for path_idx, fdv in enumerate(fdvs, start=1):
            paths.append(
                {
                    "observation_id": f"birth-{mint}",
                    "mint": mint,
                    "token_mint": mint,
                    "timestamp": create_time + path_idx * 5,
                    "fdv_proxy": fdv,
                    "event_count": path_idx,
                    "buy_count": max(1, path_idx - 1),
                    "sell_count": 1,
                    "active_wallets": max(1, path_idx),
                    "liquidity_proxy": 1.0,
                    "source": "helius_birth_watch_followup",
                }
            )
            events.append(
                {
                    "mint": mint,
                    "token_mint": mint,
                    "event_type": "pumpfun_buy",
                    "timestamp": create_time + path_idx * 5,
                    "slot": 100 + path_idx,
                }
            )
        metadata.append(
            {
                "mint": mint,
                "token_mint": mint,
                "token_name": f"Token {idx}",
                "token_symbol": f"T{idx}",
                "metadata_uri": f"https://example.invalid/{mint}.json",
                "image_uri": f"https://example.invalid/{mint}.png",
                "website_url": "https://example.invalid",
                "twitter_x_url": "https://x.example.invalid",
                "telegram_url": None,
                "observed_at": create_time + 60,
            }
        )
        holders.append(
            {
                "mint": mint,
                "token_mint": mint,
                "holder_count": 10 + idx,
                "top_holder_share_proxy": 0.1 + idx / 10,
                "top_10_holder_share_proxy": 0.5 + idx / 20,
                "observed_at": create_time + 60,
            }
        )
    thin_candidates = [dict(row) for row in candidates]
    thin_candidates[0].pop("seconds_create_to_first_followup_attempt")
    thin_candidates[0].pop("first_followup_before_10k")
    thin_candidates[0].pop("first_followup_before_20k")
    birth_watch_rows = [dict(row) for row in candidates]
    for row in birth_watch_rows:
        row["create_observed_at"] = row.pop("observed_at")
        row["create_signature"] = f"sig-{row['mint']}"
        row.pop("freshness_lane")
        row.pop("candidate_classification")
        row.pop("event_type")
    _write_jsonl(obs / "candidates.jsonl", thin_candidates)
    _write_jsonl(obs / "birth_watch_mints.jsonl", birth_watch_rows)
    _write_jsonl(obs / "candidate_paths.jsonl", paths)
    _write_jsonl(obs / "candidate_metadata.jsonl", metadata)
    _write_jsonl(obs / "candidate_holders.jsonl", holders)
    _write_jsonl(obs / "candidate_events.jsonl", events)
    _write_jsonl(obs / "candidate_drawdowns.jsonl", [])
    _write_jsonl(obs / "birth_followup_paths.jsonl", [])
    _write_jsonl(obs / "birth_followup_events.jsonl", [])
    (obs / "birth_followup_status.json").write_text(json.dumps({"network_calls_made": 0}), encoding="utf-8")
    (obs / "checkpoint.json").write_text(json.dumps({"api_calls_used": 0}), encoding="utf-8")
    (obs / "status.json").write_text(json.dumps({"estimated_helius_credits_used": 0}), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
