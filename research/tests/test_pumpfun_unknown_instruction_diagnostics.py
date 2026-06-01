from research.mtp_research.ingestion.pumpfun_create_scanner import PumpFunCreateScanner
from research.mtp_research.ingestion.pumpfun_create_scanner_models import PumpFunInstructionDiagnostic
from research.mtp_research.ingestion.pumpfun_unknown_instruction_report import summarize_unknown_instructions
from research.tests.test_pumpfun_create_scanner import FakeAdapter, _create_tx


def test_unknown_instruction_diagnostic_captures_decoded_data_shape() -> None:
    tx = _create_tx("sig-1")
    tx["transaction"]["message"]["instructions"][0]["data"] = "111111111"
    adapter = FakeAdapter(batches=[["sig-1"]], transactions_by_signature={"sig-1": tx})

    report = PumpFunCreateScanner(adapter=adapter).scan(execute=True, max_batches=1, signatures_per_batch=1)

    diagnostic = report.unknown_pumpfun_instructions[0]
    assert diagnostic.rejection_reasons == ["unknown_discriminator"]
    assert diagnostic.instruction_discriminator == "0000000000000000"
    assert diagnostic.metadata_json["first_8_instruction_data_bytes_hex"] == "0000000000000000"
    assert diagnostic.metadata_json["instruction_data_length"] == 9
    assert diagnostic.metadata_json["decoded_instruction_data_length"] == 9


def test_unknown_summary_clusters_by_discriminator_account_count_and_layout() -> None:
    diagnostics = [
        PumpFunInstructionDiagnostic(
            signature="sig-a",
            account_count=14,
            instruction_discriminator="disc-a",
            rejection_reasons=["unknown_discriminator"],
            metadata_json={
                "first_8_instruction_data_bytes_hex": "aaaaaaaaaaaaaaaa",
                "instruction_data_length": 12,
                "decoded_instruction_data_length": 9,
                "accounts": ["mint-a", "auth", "curve-a"],
            },
        ),
        PumpFunInstructionDiagnostic(
            signature="sig-b",
            account_count=14,
            instruction_discriminator="disc-a",
            rejection_reasons=["unknown_discriminator"],
            metadata_json={
                "first_8_instruction_data_bytes_hex": "aaaaaaaaaaaaaaaa",
                "instruction_data_length": 12,
                "decoded_instruction_data_length": 9,
                "accounts": ["mint-b", "auth", "curve-b"],
            },
        ),
        PumpFunInstructionDiagnostic(
            signature="sig-c",
            account_count=5,
            instruction_discriminator="disc-b",
            rejection_reasons=["unknown_discriminator"],
            metadata_json={
                "first_8_instruction_data_bytes_hex": "bbbbbbbbbbbbbbbb",
                "instruction_data_length": 7,
                "decoded_instruction_data_length": 6,
                "accounts": ["fee-payer"],
            },
        ),
    ]

    summary = summarize_unknown_instructions(diagnostics)

    assert summary["total_unknown_instructions"] == 3
    assert summary["clusters"][0]["instruction_discriminator_hex"] == "disc-a"
    assert summary["clusters"][0]["account_count"] == 14
    assert summary["clusters"][0]["count"] == 2
    assert summary["clusters"][0]["example_signatures"] == ["sig-a", "sig-b"]
    assert summary["top_account_layouts"][0]["count"] == 2
