from research.mtp_research.ingestion.backfill_jobs import make_target_id


def test_make_target_id_is_deterministic() -> None:
    first = make_target_id("address-1", "wallet", "mint-1")
    second = make_target_id("address-1", "wallet", "mint-1")
    different = make_target_id("address-1", "pool", "mint-1")

    assert first == second
    assert first.startswith("wallet-")
    assert first != different
