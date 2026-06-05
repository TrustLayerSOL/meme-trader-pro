from __future__ import annotations

import json
import time
from pathlib import Path

from research.mtp_research.validation.forward_metadata_enrichment import (
    ForwardMetadataConfig,
    ForwardMetadataEnrichmentQueue,
    build_metadata_snapshot,
    classify_narrative,
    latest_metadata_before,
    load_metadata_snapshots,
    metadata_at_lifecycle_point,
    summarize_metadata_coverage,
)
from research.mtp_research.validation.official_lifecycle_watch import OfficialLifecycleV2Config


def test_build_metadata_snapshot_extracts_identity_socials_quality_and_narrative(tmp_path: Path) -> None:
    config = OfficialLifecycleV2Config(data_root=tmp_path)
    snapshot = build_metadata_snapshot(
        config,
        mint="mint-ai-dog",
        lifecycle_point="birth",
        source_dataset="unit_test",
        observed_at=100.0,
        create_metadata={
            "token_name": "AI Dog 100",
            "token_symbol": "$AIDOG",
            "token_description": "AI dog meme with Telegram and X",
            "metadata_uri": "https://example.com/meta.json",
            "image_uri": "ipfs://image-cid",
            "external_url": "https://aidog.example",
            "twitter_x_url": "https://x.com/aidog",
            "telegram_url": "https://t.me/aidog",
        },
    )

    assert snapshot["mint"] == "mint-ai-dog"
    assert snapshot["lifecycle_point"] == "birth"
    assert snapshot["metadata_source"] == "pumpfun_create_transaction"
    assert snapshot["metadata_is_point_in_time"] is True
    assert snapshot["metadata_is_latest_only"] is False
    assert snapshot["token_name"] == "AI Dog 100"
    assert snapshot["token_symbol"] == "$AIDOG"
    assert snapshot["has_website"] is True
    assert snapshot["has_twitter_x"] is True
    assert snapshot["has_telegram"] is True
    assert snapshot["has_any_social"] is True
    assert snapshot["social_link_count"] == 3
    assert snapshot["image_present"] is True
    assert snapshot["image_uri_scheme"] == "ipfs"
    assert snapshot["metadata_domain"] == "example.com"
    assert snapshot["token_name_has_number"] is True
    assert snapshot["symbol_contains_dollar_sign"] is True
    assert snapshot["animal_flag"] is True
    assert snapshot["ai_flag"] is True
    assert snapshot["narrative_method"] == "deterministic_keyword_rules"
    assert snapshot["metadata_completeness_score"] > 0


def test_metadata_queue_does_not_block_and_writes_fail_closed_snapshot(tmp_path: Path) -> None:
    config = OfficialLifecycleV2Config(data_root=tmp_path)
    metadata_config = ForwardMetadataConfig(max_metadata_workers=1, metadata_fetch_timeout_seconds=0.01)
    queue = ForwardMetadataEnrichmentQueue(config, metadata_config=metadata_config)
    started = time.monotonic()
    queue.enqueue(
        mint="mint-queued",
        lifecycle_point="birth",
        source_dataset="unit_test",
        observed_at=111.0,
        create_metadata={"token_name": "Queued", "metadata_uri": "https://example.com/meta.json"},
    )
    elapsed = time.monotonic() - started
    queue.close(wait=True)

    rows = load_metadata_snapshots(config)
    assert elapsed < 0.1
    assert len(rows) == 1
    assert rows[0]["mint"] == "mint-queued"
    assert rows[0]["metadata_fetch_status"] == "success"
    assert config.metadata_status_path.exists()


def test_metadata_coverage_summary_and_lookup_helpers(tmp_path: Path) -> None:
    config = OfficialLifecycleV2Config(data_root=tmp_path)
    config.metadata_snapshots_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "mint": "mint-a",
            "observed_at": 100.0,
            "lifecycle_point": "birth",
            "token_name": "Alpha",
            "token_symbol": "ALP",
            "metadata_uri": "https://example.com/a.json",
            "image_uri": "https://example.com/a.png",
            "has_any_social": True,
            "has_website": True,
            "has_twitter_x": False,
            "has_telegram": False,
            "has_discord": False,
            "metadata_completeness_score": 7,
            "metadata_source": "pumpfun_create_transaction",
            "metadata_is_point_in_time": True,
            "metadata_is_latest_only": False,
            "metadata_fetch_status": "success",
        },
        {
            "mint": "mint-a",
            "observed_at": 120.0,
            "lifecycle_point": "crossed_20k",
            "token_name": "Alpha",
            "token_symbol": "ALP",
            "metadata_completeness_score": 5,
            "metadata_source": "helius_das",
            "metadata_is_point_in_time": False,
            "metadata_is_latest_only": True,
            "metadata_fetch_status": "success",
        },
        {
            "mint": "mint-b",
            "observed_at": 130.0,
            "lifecycle_point": "birth",
            "metadata_fetch_status": "failed",
            "metadata_fetch_error": "metadata_unavailable",
        },
    ]
    with config.metadata_snapshots_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")

    loaded = load_metadata_snapshots(config)
    summary, paths = summarize_metadata_coverage(config)

    assert latest_metadata_before(loaded, "mint-a", 119.0)["lifecycle_point"] == "birth"
    assert metadata_at_lifecycle_point(loaded, "mint-a", "crossed_20k")["metadata_source"] == "helius_das"
    assert summary["metadata_snapshots"] == 3
    assert summary["unique_mints_with_metadata"] == 2
    assert summary["birth_metadata_coverage"] == 2
    assert summary["20k_metadata_coverage"] == 1
    assert summary["token_name_coverage"] == 2
    assert summary["metadata_latest_only_count"] == 1
    assert summary["metadata_point_in_time_count"] == 1
    assert summary["metadata_failures"] == 1
    assert paths["json"].exists()
    assert paths["markdown"].exists()


def test_deterministic_narrative_classification_marks_unknown_when_no_keywords() -> None:
    classified = classify_narrative("Plain Token", "PLN", "")

    assert classified["narrative_bucket"] == "unknown"
    assert classified["topicality_bucket"] == "unknown"
    assert classified["narrative_confidence"] == 0.0
