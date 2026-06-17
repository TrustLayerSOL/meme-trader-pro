from research.mtp_research.validation.t007_thesis_ready_gate import t007_production_gate_decision


def test_10m_gate_does_not_fail_only_for_zero_migrations():
    result = t007_production_gate_decision({
        "source_duration_seconds": 600,
        "db_writer_alive": True,
        "db_ledger_consistent": True,
        "queue_dropped_total": 0,
        "curve_state_decoded": 10,
        "market_cap_available": 10,
        "global_migrations_seen": 0,
    })
    assert result["decision_label"] == "T007_PRODUCTION_LIFECYCLE_READY_FOR_10M_PROOF"


def test_migrations_without_full_path_block_controlled_window():
    result = t007_production_gate_decision({
        "source_duration_seconds": 3600,
        "db_writer_alive": True,
        "db_ledger_consistent": True,
        "queue_dropped_total": 0,
        "curve_state_decoded": 10,
        "market_cap_available": 10,
        "global_migrations_seen": 5,
        "migrations_with_decision_safe_full_path": 0,
    })
    assert result["decision_label"] == "T007_PRODUCTION_LIFECYCLE_BLOCKED"
    assert "migrations_not_linked_to_decision_safe_full_path" in result["blockers"]
