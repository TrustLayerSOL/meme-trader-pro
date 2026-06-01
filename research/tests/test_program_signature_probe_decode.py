from research.mtp_research.ingestion.run_program_signature_probe import (
    PUMP_FUN_PROGRAM_ID,
    summarize_hydrated_transactions,
)


def test_summarize_hydrated_transactions_extracts_pump_fun_create_accounts() -> None:
    tx = {
        "slot": 123,
        "blockTime": 1_780_000_000,
        "transaction": {
            "signatures": ["sig-1"],
            "message": {
                "instructions": [
                    {
                        "programId": PUMP_FUN_PROGRAM_ID,
                        "accounts": [
                            "mint-1",
                            "mint-authority",
                            "bonding-curve-1",
                            "associated-bonding-curve",
                            "global",
                            "metadata-program",
                            "metadata-account",
                            "creator-wallet-1",
                            "system-program",
                            "token-program",
                            "associated-token-program",
                            "rent",
                            "event-authority",
                            PUMP_FUN_PROGRAM_ID,
                        ],
                    }
                ]
            },
        },
    }

    summary = summarize_hydrated_transactions([tx], PUMP_FUN_PROGRAM_ID)

    assert summary["candidate_token_mints"] == ["mint-1"]
    assert summary["bonding_curve_accounts"] == ["bonding-curve-1"]
    assert summary["creator_wallets"] == ["creator-wallet-1"]
    assert summary["verified_block_times"] == [1_780_000_000]
    assert summary["decoded_samples"][0]["instruction_classification"] == "pump_fun_possible_create"
    assert summary["can_extract_candidate_fields"] is True
