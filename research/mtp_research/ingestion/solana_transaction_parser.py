"""Conservative Solana jsonParsed transaction parser."""

from __future__ import annotations

from typing import Any

from research.mtp_research.ingestion.raw_transaction_store import RawTransactionRecord
from research.mtp_research.ingestion.transaction_parser_models import (
    ProgramInvocation,
    TokenBalanceDelta,
    TransactionAccountSummary,
    TransactionSummary,
)


def extract_signature(raw_json: dict) -> str | None:
    signatures = (
        raw_json.get("transaction", {})
        .get("signatures", [])
    )
    if signatures:
        return signatures[0]
    return raw_json.get("signature")


def extract_account_summaries(raw_json: dict) -> list[TransactionAccountSummary]:
    account_keys = (
        raw_json.get("transaction", {})
        .get("message", {})
        .get("accountKeys", [])
    )
    summaries: list[TransactionAccountSummary] = []

    for account in account_keys:
        if isinstance(account, str):
            summaries.append(TransactionAccountSummary(pubkey=account))
        elif isinstance(account, dict):
            pubkey = account.get("pubkey")
            if pubkey:
                summaries.append(
                    TransactionAccountSummary(
                        pubkey=pubkey,
                        signer=bool(account.get("signer", False)),
                        writable=bool(account.get("writable", False)),
                        source=account.get("source"),
                    )
                )
    return summaries


def extract_program_invocations(raw_json: dict) -> list[ProgramInvocation]:
    message = raw_json.get("transaction", {}).get("message", {})
    top_level = message.get("instructions", [])
    programs: list[ProgramInvocation] = []

    for index, instruction in enumerate(top_level):
        invocation = _program_invocation_from_instruction(instruction, index=index)
        if invocation:
            programs.append(invocation)

    inner_groups = raw_json.get("meta", {}).get("innerInstructions", []) or []
    for group in inner_groups:
        parent_index = group.get("index")
        for inner_index, instruction in enumerate(group.get("instructions", []) or []):
            invocation = _program_invocation_from_instruction(
                instruction,
                index=parent_index,
                inner_index=inner_index,
            )
            if invocation:
                programs.append(invocation)

    return programs


def extract_token_balance_deltas(raw_json: dict) -> list[TokenBalanceDelta]:
    meta = raw_json.get("meta") or {}
    account_summaries = extract_account_summaries(raw_json)
    pre_by_key = _token_balance_map(meta.get("preTokenBalances", []) or [])
    post_by_key = _token_balance_map(meta.get("postTokenBalances", []) or [])
    keys = sorted(set(pre_by_key) | set(post_by_key), key=lambda key: (key[0], key[1]))

    deltas: list[TokenBalanceDelta] = []
    for account_index, mint in keys:
        pre = pre_by_key.get((account_index, mint))
        post = post_by_key.get((account_index, mint))
        pre_amount = _ui_amount(pre)
        post_amount = _ui_amount(post)
        delta = None
        if pre_amount is not None and post_amount is not None:
            delta = post_amount - pre_amount
        elif post_amount is not None:
            delta = post_amount
        elif pre_amount is not None:
            delta = -pre_amount

        owner = _first_non_null(pre, post, field_name="owner")
        decimals = _decimals(pre) if pre else _decimals(post)
        account = None
        if account_index is not None and account_index < len(account_summaries):
            account = account_summaries[account_index].pubkey

        deltas.append(
            TokenBalanceDelta(
                owner=owner,
                account=account,
                mint=mint,
                pre_amount=pre_amount,
                post_amount=post_amount,
                delta=delta,
                decimals=decimals,
                ui_amount_string_pre=_ui_amount_string(pre),
                ui_amount_string_post=_ui_amount_string(post),
            )
        )

    return deltas


def summarize_raw_transaction(record: RawTransactionRecord) -> TransactionSummary:
    raw_json = record.raw_json or {}
    signature = extract_signature(raw_json) or record.signature
    meta = raw_json.get("meta") if isinstance(raw_json.get("meta"), dict) else {}
    success = record.success
    if success is None and meta:
        success = meta.get("err") is None

    return TransactionSummary(
        signature=signature,
        slot=raw_json.get("slot", record.slot),
        block_time=raw_json.get("blockTime", record.block_time),
        success=success,
        fee_lamports=meta.get("fee") if meta else None,
        accounts=extract_account_summaries(raw_json),
        programs=extract_program_invocations(raw_json),
        token_balance_deltas=extract_token_balance_deltas(raw_json),
        raw_json=raw_json,
    )


def _program_invocation_from_instruction(
    instruction: Any,
    index: int | None,
    inner_index: int | None = None,
) -> ProgramInvocation | None:
    if not isinstance(instruction, dict):
        return None
    program_id = instruction.get("programId")
    if not program_id:
        return None
    parsed = instruction.get("parsed") if isinstance(instruction.get("parsed"), dict) else {}
    return ProgramInvocation(
        program_id=program_id,
        program=instruction.get("program"),
        instruction_type=parsed.get("type") if parsed else instruction.get("type"),
        index=index,
        inner_index=inner_index,
        raw_json=dict(instruction),
    )


def _token_balance_map(rows: list[dict[str, Any]]) -> dict[tuple[int, str], dict[str, Any]]:
    output: dict[tuple[int, str], dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        account_index = row.get("accountIndex")
        mint = row.get("mint")
        if isinstance(account_index, int) and mint:
            output[(account_index, mint)] = row
    return output


def _ui_amount(row: dict[str, Any] | None) -> float | None:
    if not row:
        return None
    ui_token_amount = row.get("uiTokenAmount") or {}
    ui_amount_string = ui_token_amount.get("uiAmountString")
    if ui_amount_string is not None:
        try:
            return float(ui_amount_string)
        except ValueError:
            return None
    ui_amount = ui_token_amount.get("uiAmount")
    return float(ui_amount) if ui_amount is not None else None


def _ui_amount_string(row: dict[str, Any] | None) -> str | None:
    if not row:
        return None
    return (row.get("uiTokenAmount") or {}).get("uiAmountString")


def _decimals(row: dict[str, Any] | None) -> int | None:
    if not row:
        return None
    decimals = (row.get("uiTokenAmount") or {}).get("decimals")
    return int(decimals) if decimals is not None else None


def _first_non_null(
    first: dict[str, Any] | None,
    second: dict[str, Any] | None,
    field_name: str,
) -> Any:
    if first and first.get(field_name) is not None:
        return first[field_name]
    if second and second.get(field_name) is not None:
        return second[field_name]
    return None
