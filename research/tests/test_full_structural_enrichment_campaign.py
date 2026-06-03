import json
from pathlib import Path

import pandas as pd

from research.mtp_research.validation.full_structural_enrichment_campaign import (
    READINESS_READY_WITH_GAPS,
    build_layer_coverage,
    estimate_campaign_budget,
    run_full_structural_enrichment_campaign,
)


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


def _write_parquet(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_budget_estimate_allows_local_only_campaign_under_cap() -> None:
    estimate = estimate_campaign_budget(
        launch_count=1_143,
        execute_helius=False,
        execute_dexscreener=False,
        max_helius_credits=500_000,
    )

    assert estimate["helius_execute_requested"] is False
    assert estimate["projected_helius_credits"] == 0
    assert estimate["budget_gate_status"] == "within_budget_local_only"
    assert estimate["safe_to_execute"] is True


def test_budget_estimate_plans_batched_dexscreener_visibility_calls() -> None:
    estimate = estimate_campaign_budget(
        launch_count=1_143,
        execute_helius=False,
        execute_dexscreener=True,
        max_helius_credits=500_000,
    )

    assert estimate["dexscreener_execute_requested"] is True
    assert estimate["projected_helius_credits"] == 0
    assert estimate["projected_dexscreener_calls"] == 39
    assert estimate["budget_gate_status"] == "within_budget_dexscreener_visibility_batched"
    assert estimate["external_collection_reason"] == "dexscreener_tokens_batch_visibility_context"
    assert estimate["safe_to_execute"] is True


def test_budget_estimate_plans_batched_contract_authority_calls() -> None:
    estimate = estimate_campaign_budget(
        launch_count=1_143,
        execute_helius=True,
        execute_dexscreener=False,
        max_helius_credits=500_000,
    )

    assert estimate["projected_helius_credits"] == 12
    assert estimate["budget_gate_status"] == "within_budget_contract_authority_batched"
    assert estimate["external_collection_reason"] == "contract_authority_getMultipleAccounts_batched"
    assert estimate["safe_to_execute"] is True


class FakeContractAuthorityAdapter:
    def __init__(self):
        self.calls = []

    def fetch_mint_accounts(self, mints, *, workers=1, batch_size=100):
        self.calls.append({"mints": list(mints), "workers": workers, "batch_size": batch_size})
        return {
            "requests_used": 1,
            "raw_responses": [{"batch_index": 0, "mint_count": len(mints)}],
            "rows": [
                {
                    "mint": mint,
                    "mint_authority": f"authority-{mint}",
                    "freeze_authority": None,
                    "decimals": 6,
                    "supply": "1000000",
                    "contract_authority_context_available": True,
                    "contract_authority_source": "helius_getMultipleAccounts_jsonParsed",
                    "contract_authority_missing_reason": None,
                }
                for mint in mints
            ],
            "errors": [],
        }


class FakeDexScreenerTokenAdapter:
    def __init__(self):
        self.calls = []

    def fetch_tokens_for_mints(self, mints, *, workers=1, batch_size=30):
        self.calls.append({"mints": list(mints), "workers": workers, "batch_size": batch_size})
        return {
            "requests_used": 1,
            "raw_responses": [{"batch_index": 0, "mint_count": len(mints)}],
            "rows": [
                {
                    "chainId": "solana",
                    "dexId": "pumpswap",
                    "pairAddress": f"pair-{mint}",
                    "pairCreatedAt": 1_700_000_030_000,
                    "url": f"https://dexscreener.com/solana/pair-{mint}",
                    "baseToken": {"address": mint, "name": "AI Agent 2026", "symbol": "AIA"},
                    "quoteToken": {"address": "So11111111111111111111111111111111111111112", "symbol": "SOL"},
                    "info": {
                        "imageUrl": "https://example.com/logo.png",
                        "websites": [{"label": "Website", "url": "https://example.com"}],
                        "socials": [
                            {"type": "twitter", "url": "https://x.com/example"},
                            {"type": "telegram", "url": "https://t.me/example"},
                        ],
                    },
                    "boosts": {"active": 1},
                }
                for mint in mints
            ],
            "errors": [],
        }


def test_full_campaign_can_execute_batched_contract_authority_enrichment(tmp_path: Path) -> None:
    trigger_path = tmp_path / "trigger_rows.csv"
    combined_path = tmp_path / "combined.parquet"
    output_root = tmp_path / "orico"
    adapter = FakeContractAuthorityAdapter()

    _write_csv(
        trigger_path,
        [
            {
                "launch_id": "L1",
                "token_mint": "Mint1",
                "launch_ts": 1_700_000_000,
                "trigger_fdv_proxy": 20_000,
                "event_count_at_20k": 2,
                "buy_count_at_20k": 1,
                "active_wallets_at_20k": 1,
            }
        ],
    )
    _write_parquet(
        combined_path,
        [
            {
                "launch_id": "L1",
                "mint": "Mint1",
                "fdv_per_event_at_20k": 10000.0,
                "fdv_per_buy_at_20k": 20000.0,
                "fdv_per_active_wallet_at_20k": 20000.0,
            }
        ],
    )

    report, paths = run_full_structural_enrichment_campaign(
        data_root=output_root,
        input_paths={
            "trigger_rows": trigger_path,
            "combined_repaired": combined_path,
            "top_holder_layers": [],
            "early_buyer_layers": [],
            "creator_funder_layers": [],
            "holder_state": None,
            "entity_proxy": None,
            "events": None,
            "sol_usd": None,
            "candidates": None,
            "migration_labels": None,
        },
        output_paths={"status_path": tmp_path / "FULL_STRUCTURAL_ENRICHMENT_CAMPAIGN_STATUS.md"},
        execute_helius=True,
        contract_authority_adapter=adapter,
    )

    master = pd.read_parquet(paths["master_parquet_path"])

    assert report["helius"]["execute_completed"] is True
    assert report["helius"]["requests_used"] == 1
    assert report["helius"]["credits_used"] == 1
    assert "external_gap_contract_authority_context" not in report["warnings"]
    assert adapter.calls[0]["workers"] >= 1
    assert bool(master["has_contract_layer"].iloc[0]) is True
    assert master["mint_authority"].iloc[0] == "authority-Mint1"
    assert paths["contract_authority_raw_path"].exists()


def test_full_campaign_can_execute_batched_dexscreener_visibility_enrichment(tmp_path: Path) -> None:
    trigger_path = tmp_path / "trigger_rows.csv"
    combined_path = tmp_path / "combined.parquet"
    output_root = tmp_path / "orico"
    adapter = FakeDexScreenerTokenAdapter()

    _write_csv(
        trigger_path,
        [
            {
                "launch_id": "L1",
                "token_mint": "Mint1",
                "launch_ts": 1_700_000_000,
                "trigger_fdv_proxy": 20_000,
                "event_count_at_20k": 2,
                "buy_count_at_20k": 1,
                "active_wallets_at_20k": 1,
            }
        ],
    )
    _write_parquet(
        combined_path,
        [
            {
                "launch_id": "L1",
                "mint": "Mint1",
                "fdv_per_event_at_20k": 10000.0,
                "fdv_per_buy_at_20k": 20000.0,
                "fdv_per_active_wallet_at_20k": 20000.0,
            }
        ],
    )

    report, paths = run_full_structural_enrichment_campaign(
        data_root=output_root,
        input_paths={
            "trigger_rows": trigger_path,
            "combined_repaired": combined_path,
            "top_holder_layers": [],
            "early_buyer_layers": [],
            "creator_funder_layers": [],
            "holder_state": None,
            "entity_proxy": None,
            "events": None,
            "sol_usd": None,
            "candidates": None,
            "migration_labels": None,
            "dexscreener_pairs": None,
        },
        output_paths={"status_path": tmp_path / "FULL_STRUCTURAL_ENRICHMENT_CAMPAIGN_STATUS.md"},
        execute_helius=False,
        execute_dexscreener=True,
        dexscreener_token_adapter=adapter,
    )

    master = pd.read_parquet(paths["master_parquet_path"])
    row = master.iloc[0]

    assert report["dexscreener"]["execute_completed"] is True
    assert report["dexscreener"]["calls_used"] == 1
    assert adapter.calls[0]["workers"] >= 1
    assert row["token_name"] == "AI Agent 2026"
    assert row["token_symbol"] == "AIA"
    assert row["topicality_category"] == "AI"
    assert bool(row["twitter_present"]) is True
    assert bool(row["telegram_present"]) is True
    assert bool(row["dexscreener_boost_present"]) is True
    assert bool(row["has_topicality_layer"]) is True
    assert bool(row["has_visibility_layer"]) is True
    assert bool(row["has_metadata_quality_layer"]) is True
    assert "external_gap_visibility_attention_context" not in report["warnings"]
    assert paths["dexscreener_token_raw_path"].exists()
    assert paths["topicality_context_parquet_path"].exists()
    assert paths["visibility_context_parquet_path"].exists()
    assert paths["metadata_quality_context_parquet_path"].exists()
    assert paths["attention_visibility_summary_json_path"].exists()


def test_full_campaign_builds_master_and_reports_from_local_sources(tmp_path: Path) -> None:
    trigger_path = tmp_path / "trigger_rows.csv"
    combined_path = tmp_path / "combined.parquet"
    top_holder_path = tmp_path / "top_holder.parquet"
    early_buyer_path = tmp_path / "early_buyer.parquet"
    funder_path = tmp_path / "funder.parquet"
    output_root = tmp_path / "orico"

    _write_csv(
        trigger_path,
        [
            {
                "launch_id": "L1",
                "token_mint": "Mint1",
                "creator": "Creator1",
                "launch_ts": 1_700_000_000,
                "milestone_tier": "20k",
                "trigger_fdv_proxy": 20_500,
                "peak_fdv_proxy": 100_000,
                "event_count_at_20k": 10,
                "buy_count_at_20k": 7,
                "sell_count_at_20k": 3,
                "active_wallets_at_20k": 5,
                "holder_count_at_20k": 4,
                "top_holder_share_at_20k": 0.33,
                "top_10_holder_share_at_20k": 0.75,
                "creator_holder_share_at_20k": 0.10,
                "repeated_actor_overlap_proxy": 0.2,
                "repeated_buyer_overlap_proxy": 0.1,
                "synchronized_participation_proxy": 0.0,
                "circularity_proxy": 0.0,
                "churn_proxy": 0.5,
            },
            {
                "launch_id": "L2",
                "token_mint": "Mint2",
                "creator": "Creator2",
                "launch_ts": 1_700_010_000,
                "milestone_tier": "50k",
                "trigger_fdv_proxy": 50_100,
                "peak_fdv_proxy": 80_000,
                "event_count_at_20k": 4,
                "buy_count_at_20k": 2,
                "sell_count_at_20k": 2,
                "active_wallets_at_20k": 2,
                "holder_count_at_20k": 2,
                "top_holder_share_at_20k": 0.50,
                "top_10_holder_share_at_20k": 1.0,
                "creator_holder_share_at_20k": 0.0,
                "repeated_actor_overlap_proxy": 0.0,
                "repeated_buyer_overlap_proxy": 0.0,
                "synchronized_participation_proxy": 0.0,
                "circularity_proxy": 0.0,
                "churn_proxy": 0.0,
            },
        ],
    )
    _write_parquet(
        combined_path,
        [
            {
                "launch_id": "L1",
                "mint": "Mint1",
                "fdv_per_event_at_20k": 2050.0,
                "fdv_per_buy_at_20k": 2928.57,
                "fdv_per_active_wallet_at_20k": 4100.0,
                "early_buyer_wallet_count": 3,
                "early_buyer_with_prior_history_count": 1,
                "top_holder_share_proxy": 0.31,
                "top_10_holder_share_proxy": 0.72,
                "candidate_funder": "Funder1",
                "candidate_funder_confidence": "medium",
                "launches_sharing_funder": 2,
                "creators_sharing_funder": 2,
            }
        ],
    )
    _write_parquet(
        top_holder_path,
        [
            {
                "launch_id": "L1",
                "mint": "Mint1",
                "top_holder_share_proxy": 0.31,
                "top_10_holder_share_proxy": 0.72,
                "holder_snapshot_confidence": "observed_delta_replay",
            }
        ],
    )
    _write_parquet(
        early_buyer_path,
        [
            {
                "current_launch_id": "L1",
                "wallet": "Wallet1",
                "prior_transaction_count": 5,
                "wallet_history_source_confidence": "bounded_history",
            }
        ],
    )
    _write_parquet(
        funder_path,
        [
            {
                "launch_id": "L1",
                "mint": "Mint1",
                "candidate_funder": "Funder1",
                "candidate_funder_confidence": "medium",
                "launches_sharing_funder": 2,
                "creators_sharing_funder": 2,
            }
        ],
    )

    report, paths = run_full_structural_enrichment_campaign(
        data_root=output_root,
        input_paths={
            "trigger_rows": trigger_path,
            "combined_repaired": combined_path,
            "top_holder_layers": [top_holder_path],
            "early_buyer_layers": [early_buyer_path],
            "creator_funder_layers": [funder_path],
            "holder_state": None,
            "entity_proxy": None,
            "events": None,
            "sol_usd": None,
        },
        output_paths={"status_path": tmp_path / "FULL_STRUCTURAL_ENRICHMENT_CAMPAIGN_STATUS.md"},
        execute_helius=False,
        execute_dexscreener=False,
    )

    master = pd.read_parquet(paths["master_parquet_path"])
    summary = json.loads(paths["coverage_json_path"].read_text(encoding="utf-8"))

    assert report["readiness_classification"] == READINESS_READY_WITH_GAPS
    assert report["master_rows"] == 2
    assert master["launch_id"].tolist() == ["L1", "L2"]
    assert bool(master.loc[master["launch_id"] == "L1", "has_core_hidden_structure_layers"].iloc[0]) is True
    assert bool(master.loc[master["launch_id"] == "L2", "has_core_hidden_structure_layers"].iloc[0]) is False
    assert paths["master_jsonl_path"].exists()
    assert paths["preflight_json_path"].exists()
    assert summary["helius"]["credits_used"] == 0
    assert "no_live_trading" in json.dumps(summary)


def test_full_campaign_adds_visible_attention_and_flow_features(tmp_path: Path) -> None:
    trigger_path = tmp_path / "trigger_rows.csv"
    combined_path = tmp_path / "combined.parquet"
    events_path = tmp_path / "events.jsonl"
    sol_usd_path = tmp_path / "sol_usd.jsonl"
    candidates_path = tmp_path / "candidates.jsonl"
    migration_labels_path = tmp_path / "migration_labels.jsonl"
    dexscreener_pairs_path = tmp_path / "dexscreener_pairs.parquet"
    output_root = tmp_path / "orico"

    _write_csv(
        trigger_path,
        [
            {
                "launch_id": "L1",
                "token_mint": "Mint1",
                "creator": "Creator1",
                "launch_ts": 1_700_000_000,
                "trigger_fdv_proxy": 20_000,
                "trigger_age_seconds": 90,
                "buy_count_at_20k": 3,
                "event_count_at_20k": 4,
                "active_wallets_at_20k": 2,
                "top_holder_share_at_20k": 0.42,
                "creator_prior_migration_or_graduation_count": 5,
            },
            {
                "launch_id": "L2",
                "token_mint": "Mint2",
                "creator": "Creator2",
                "launch_ts": 1_700_000_000,
                "trigger_fdv_proxy": 20_000,
                "trigger_age_seconds": 400,
                "buy_count_at_20k": 1,
                "event_count_at_20k": 1,
                "active_wallets_at_20k": 1,
                "top_holder_share_at_20k": 0.25,
            },
            {
                "launch_id": "L3",
                "token_mint": "Mint3",
                "launch_ts": 1_700_000_000,
                "trigger_fdv_proxy": 20_000,
                "trigger_age_seconds": 500,
                "buy_count_at_20k": 1,
                "event_count_at_20k": 1,
                "active_wallets_at_20k": 1,
            },
        ],
    )
    _write_parquet(
        combined_path,
        [
            {
                "launch_id": "L1",
                "mint": "Mint1",
                "fdv_per_event_at_20k": 5000.0,
                "fdv_per_buy_at_20k": 6666.67,
                "fdv_per_active_wallet_at_20k": 10000.0,
            },
            {
                "launch_id": "L2",
                "mint": "Mint2",
                "fdv_per_event_at_20k": 20000.0,
                "fdv_per_buy_at_20k": 20000.0,
                "fdv_per_active_wallet_at_20k": 20000.0,
            },
            {
                "launch_id": "L3",
                "mint": "Mint3",
                "fdv_per_event_at_20k": 20000.0,
                "fdv_per_buy_at_20k": 20000.0,
                "fdv_per_active_wallet_at_20k": 20000.0,
            },
        ],
    )
    _write_jsonl(
        events_path,
        [
            {
                "token_mint": "Mint1",
                "block_time": 1_700_000_010,
                "side": "accumulate",
                "venue": "pumpfun_buy",
                "actor": "BuyerA",
                "quote_qty": 2.0,
                "signature": "sig-a",
            },
            {
                "token_mint": "Mint1",
                "block_time": 1_700_000_020,
                "side": "accumulate",
                "venue": "pumpfun_buy",
                "actor": "BuyerB",
                "quote_qty": 1.0,
                "signature": "sig-b",
            },
            {
                "token_mint": "Mint1",
                "block_time": 1_700_000_080,
                "side": "accumulate",
                "venue": "pumpfun_buy",
                "actor": "LateBuyer",
                "quote_qty": 5.0,
                "signature": "sig-late",
            },
            {
                "token_mint": "Mint2",
                "block_time": 1_700_000_020,
                "side": "distribute",
                "venue": "pumpfun_sell",
                "actor": "SellerA",
                "quote_qty": 1.0,
                "signature": "sig-sell",
            },
        ],
    )
    _write_jsonl(sol_usd_path, [{"ts": 1_700_000_000, "sol_usd": 100.0, "source": "test"}])
    _write_jsonl(
        candidates_path,
        [
            {
                "token_mint": "Mint2",
                "launch_id": "different-launch-id-from-census",
                "launch_ts": 1_700_000_000,
                "metadata_json": {
                    "creator_deployer": "Creator2",
                    "token_name": "Dog Sports 99",
                    "token_symbol": "DOG99",
                    "metadata_uri": "ipfs://metadata",
                    "image_uri": "https://example.com/dog.png",
                    "website": "https://example.com",
                    "twitter": "https://x.com/dog",
                    "telegram": "https://t.me/dog",
                },
            }
        ],
    )
    _write_parquet(
        dexscreener_pairs_path,
        [
            {
                "launch_id": "different-launch-id-from-census",
                "mint": "Mint2",
                "dex_pair_detected": True,
                "dexscreener_url": "https://dexscreener.com/solana/pair-mint2",
                "pair_created_at": 1_700_000_045_000,
                "liquidity_usd": 25_000,
            }
        ],
    )
    _write_jsonl(
        migration_labels_path,
        [
            {
                "mint": "PriorMint",
                "creator": "Creator2",
                "migration_time": "2023-11-14T22:00:00+00:00",
                "migration_source": "helius_json_rpc_pumpfun_migrate_log",
            },
            {
                "mint": "FutureMint",
                "creator": "Creator2",
                "migration_time": "2023-11-14T23:00:01+00:00",
                "migration_source": "helius_json_rpc_pumpfun_migrate_log",
            },
        ],
    )

    report, paths = run_full_structural_enrichment_campaign(
        data_root=output_root,
        input_paths={
            "trigger_rows": trigger_path,
            "combined_repaired": combined_path,
            "top_holder_layers": [],
            "early_buyer_layers": [],
            "creator_funder_layers": [],
            "holder_state": None,
            "entity_proxy": None,
            "events": events_path,
            "sol_usd": sol_usd_path,
            "candidates": candidates_path,
            "migration_labels": migration_labels_path,
            "dexscreener_pairs": dexscreener_pairs_path,
        },
        output_paths={"status_path": tmp_path / "FULL_STRUCTURAL_ENRICHMENT_CAMPAIGN_STATUS.md"},
        execute_helius=False,
        execute_dexscreener=False,
    )

    master = pd.read_parquet(paths["master_parquet_path"])
    l1 = master[master["launch_id"] == "L1"].iloc[0]
    l2 = master[master["launch_id"] == "L2"].iloc[0]
    l3 = master[master["launch_id"] == "L3"].iloc[0]

    assert l1["first_minute_usd_volume"] == 300.0
    assert l1["first_60s_buy_count"] == 2
    assert l1["first_60s_unique_buyers"] == 2
    assert l1["whale_buy_sequence_proxy"] == 2.0 / 3.0
    assert l1["early_holder_concentration"] == 0.42
    assert l1["deployer_prior_migration_count"] == 5
    assert l2["creator"] == "Creator2"
    assert l2["deployer_prior_migration_count"] == 1
    assert l2["token_name"] == "Dog Sports 99"
    assert l2["token_symbol"] == "DOG99"
    assert bool(l2["has_number_in_name"]) is True
    assert bool(l2["has_number_in_symbol"]) is True
    assert l2["topicality_category"] == "animal"
    assert bool(l2["website_present"]) is True
    assert bool(l2["twitter_present"]) is True
    assert bool(l2["telegram_present"]) is True
    assert bool(l2["pair_visible_on_dexscreener"]) is True
    assert l2["visibility_lag_from_launch"] == 45
    assert l2["metadata_quality_bucket"] == "complete"
    assert bool(l2["has_topicality_layer"]) is True
    assert bool(l2["has_visibility_layer"]) is True
    assert bool(l2["has_metadata_quality_layer"]) is True
    assert pd.isna(l3["creator"])
    assert pd.isna(l3["deployer_prior_migration_count"])
    assert l3["deployer_prior_migration_count_source"] == "creator_missing"
    assert bool(l3["has_topicality_layer"]) is False
    assert bool(l3["has_visibility_layer"]) is False
    assert bool(l3["has_metadata_quality_layer"]) is False
    assert l1["pair_migration_liquidity_delay_proxy"] == 90
    assert bool(l1["topicality_flag"]) is False
    assert l1["topicality_category"] == "unknown"
    assert bool(l1["has_visible_attention_and_flow_layer"]) is True
    assert l2["first_60s_buy_count"] == 0
    assert report["layer_coverage"]["visible_attention_and_flow"]["covered_rows"] == 3
    assert report["layer_coverage"]["topicality_context"]["covered_rows"] == 1
    assert report["layer_coverage"]["visibility_attention_context"]["covered_rows"] == 1
    assert report["layer_coverage"]["metadata_quality_context"]["covered_rows"] == 1
    assert paths["visibility_source_audit_json_path"].exists()
    assert paths["attention_visibility_summary_markdown_path"].exists()


def test_layer_coverage_is_deterministic() -> None:
    frame = pd.DataFrame(
        [
            {"has_fdv_efficiency_layer": True, "has_top_holder_layer": False},
            {"has_fdv_efficiency_layer": True, "has_top_holder_layer": True},
        ]
    )

    first = build_layer_coverage(frame)
    second = build_layer_coverage(frame)

    assert first == second
    assert first["fdv_efficiency"]["covered_rows"] == 2
    assert first["top_holder_behavior"]["covered_rows"] == 1
