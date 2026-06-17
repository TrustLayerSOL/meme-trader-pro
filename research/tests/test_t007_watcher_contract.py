from research.mtp_research.validation.t007_watcher_contract import normalize_watcher_payload, production_readiness_from_watcher_payload


def test_watcher_contract_shows_disjoint_migration_linkage_counts():
    payload = normalize_watcher_payload({"global_migrations_seen": 53, "linked_to_any_persistent_birth": 1, "decision_safe_full_path_count": 0})
    assert payload["global_migration_mints_seen"] == 53
    assert payload["linked_to_any_persistent_birth"] == 1
    assert payload["decision_safe_full_paths"] == 0
    assert payload["true_source_miss_count"] == 52
    assert payload["misleading_rate_fields_suppressed"] is True


def test_controlled_run_blocks_when_migrations_do_not_link_to_full_paths():
    result = production_readiness_from_watcher_payload({
        "source_duration_seconds": 3600,
        "global_migrations_seen": 10,
        "decision_safe_full_path_count": 0,
        "curve_state_decoded": 100,
        "market_cap_available": 100,
        "db_writer_alive": True,
        "db_ledger_consistent": True,
    })
    assert result["decision_label"] == "T007_PRODUCTION_BLOCKED"
    assert "migrations_not_linked_to_decision_safe_full_path" in result["blockers"]
