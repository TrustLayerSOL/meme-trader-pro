from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PUMP_FUN_PROGRAM_ID = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
PUMPSWAP_PROGRAM_ID = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
PROTOCOL_IDL_DIR = Path(__file__).with_name("protocol_idls")
EXPECTED_IDL_CHECKSUMS = {
    "pump": "b90bc471327f671449271d5d1d42354d1fae6f5a06502f5834459a3108138e49",
    "pump_amm": "cd5c58a5dded23632aedb993b08cc0d2ba91bda2bb084560913464274d3bee50",
}


@dataclass(frozen=True)
class IdlElement:
    program: str
    kind: str
    name: str
    discriminator: bytes
    account_names: tuple[str, ...] = ()
    fields: tuple[str, ...] = ()

    @property
    def discriminator_hex(self) -> str:
        return self.discriminator.hex()


class ProtocolIdlRegistry:
    def __init__(self, idls: dict[str, dict[str, Any]], checksums: dict[str, str]) -> None:
        self._idls = idls
        self._checksums = checksums
        self._instructions_by_name: dict[tuple[str, str], IdlElement] = {}
        self._instructions_by_disc: dict[tuple[str, bytes], IdlElement] = {}
        self._events_by_name: dict[tuple[str, str], IdlElement] = {}
        self._events_by_disc: dict[tuple[str, bytes], IdlElement] = {}
        self._accounts_by_name: dict[tuple[str, str], IdlElement] = {}
        self._accounts_by_disc: dict[tuple[str, bytes], IdlElement] = {}
        self._load_elements()

    def _load_elements(self) -> None:
        for program, idl in self._idls.items():
            for item in idl.get("instructions") or []:
                element = IdlElement(
                    program=program,
                    kind="instruction",
                    name=str(item.get("name") or ""),
                    discriminator=_discriminator_bytes(item, fallback_prefix="global"),
                    account_names=tuple(_account_names(item.get("accounts") or [])),
                )
                self._instructions_by_name[(program, element.name)] = element
                self._instructions_by_disc[(program, element.discriminator)] = element
            type_fields = _type_fields_by_name(idl)
            for item in idl.get("events") or []:
                name = str(item.get("name") or "")
                element = IdlElement(
                    program=program,
                    kind="event",
                    name=name,
                    discriminator=_discriminator_bytes(item, fallback_prefix="event"),
                    fields=tuple(type_fields.get(name, ())),
                )
                self._events_by_name[(program, element.name)] = element
                self._events_by_disc[(program, element.discriminator)] = element
            for item in idl.get("accounts") or []:
                name = str(item.get("name") or "")
                element = IdlElement(
                    program=program,
                    kind="account",
                    name=name,
                    discriminator=_discriminator_bytes(item, fallback_prefix="account"),
                    fields=tuple(type_fields.get(name, ())),
                )
                self._accounts_by_name[(program, element.name)] = element
                self._accounts_by_disc[(program, element.discriminator)] = element

    def idl_checksum(self, program: str) -> str:
        return self._checksums[_program_key(program)]

    def program_id(self, program: str) -> str:
        key = _program_key(program)
        if key == "pump":
            return str(self._idls[key].get("address") or PUMP_FUN_PROGRAM_ID)
        if key == "pump_amm":
            return str(self._idls[key].get("address") or PUMPSWAP_PROGRAM_ID)
        raise KeyError(program)

    def instruction_by_name(self, program: str, name: str) -> IdlElement:
        return self._instructions_by_name[(_program_key(program), name)]

    def event_by_name(self, program: str, name: str) -> IdlElement:
        return self._events_by_name[(_program_key(program), name)]

    def account_by_name(self, program: str, name: str) -> IdlElement:
        return self._accounts_by_name[(_program_key(program), name)]

    def classify_instruction(self, program: str, discriminator: bytes) -> IdlElement:
        return self._instructions_by_disc[(_program_key(program), bytes(discriminator[:8]))]

    def classify_event(self, program: str, discriminator: bytes) -> IdlElement:
        return self._events_by_disc[(_program_key(program), bytes(discriminator[:8]))]

    def classify_account(self, program: str, discriminator: bytes) -> IdlElement:
        return self._accounts_by_disc[(_program_key(program), bytes(discriminator[:8]))]

    def require_instruction(self, program: str, name: str) -> IdlElement:
        return self.instruction_by_name(program, name)

    def require_event(self, program: str, name: str) -> IdlElement:
        return self.event_by_name(program, name)

    def require_account(self, program: str, name: str) -> IdlElement:
        return self.account_by_name(program, name)


def load_protocol_idl_registry(idl_dir: str | Path | None = None) -> ProtocolIdlRegistry:
    root = Path(idl_dir) if idl_dir is not None else PROTOCOL_IDL_DIR
    files = {
        "pump": root / "pump.json",
        "pump_amm": root / "pump_amm.json",
    }
    idls: dict[str, dict[str, Any]] = {}
    checksums: dict[str, str] = {}
    for program, path in files.items():
        data = path.read_bytes()
        checksums[program] = hashlib.sha256(data).hexdigest()
        idls[program] = json.loads(data.decode("utf-8"))
    return ProtocolIdlRegistry(idls, checksums)


def _program_key(program: str) -> str:
    if program in {"pump", PUMP_FUN_PROGRAM_ID}:
        return "pump"
    if program in {"pump_amm", "pumpswap", PUMPSWAP_PROGRAM_ID}:
        return "pump_amm"
    return str(program)


def _discriminator_bytes(item: dict[str, Any], *, fallback_prefix: str) -> bytes:
    raw = item.get("discriminator")
    if isinstance(raw, list):
        return bytes(int(value) & 0xFF for value in raw[:8])
    name = str(item.get("name") or "")
    return hashlib.sha256(f"{fallback_prefix}:{name}".encode("utf-8")).digest()[:8]


def _account_names(accounts: list[Any]) -> list[str]:
    names: list[str] = []
    for account in accounts:
        if isinstance(account, dict):
            name = account.get("name")
            if name:
                names.append(str(name))
            nested = account.get("accounts")
            if isinstance(nested, list):
                names.extend(_account_names(nested))
        elif account:
            names.append(str(account))
    return names


def _type_fields_by_name(idl: dict[str, Any]) -> dict[str, tuple[str, ...]]:
    out: dict[str, tuple[str, ...]] = {}
    for item in idl.get("types") or []:
        name = str(item.get("name") or "")
        fields = (((item.get("type") or {}).get("fields")) or []) if isinstance(item, dict) else []
        out[name] = tuple(str(field.get("name") or "") for field in fields if isinstance(field, dict) and field.get("name"))
    return out

