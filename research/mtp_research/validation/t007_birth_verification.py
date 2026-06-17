"""Strict Pump.fun birth verification for T007 production collection.

A raw Pump.fun-looking transaction is not thesis-usable until it resolves to a
verified mint/bonding-curve identity. This module is intentionally pure: it does
not fetch RPC, sign, trade, or mutate runtime state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

REQUIRED_STRICT_BIRTH_FIELDS = (
    "mint",
    "creator",
    "bonding_curve",
    "associated_bonding_curve",
)

@dataclass(frozen=True)
class BirthVerificationResult:
    verified: bool
    status: str
    reasons: tuple[str, ...]
    normalized: dict[str, Any]


def _first(row: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value is not None and value != "":
            return value
    return None


def normalize_birth_candidate(row: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    normalized["mint"] = _first(row, "mint", "token_mint", "base_mint")
    normalized["creator"] = _first(row, "creator", "developer", "dev", "creator_wallet", "user")
    normalized["bonding_curve"] = _first(row, "bonding_curve", "bonding_curve_account", "curve_pda", "verified_curve_pda")
    normalized["associated_bonding_curve"] = _first(
        row,
        "associated_bonding_curve",
        "associated_bonding_curve_token_account",
        "bonding_curve_token_account",
        "verified_associated_bonding_curve_token_account",
    )
    normalized["quote_mint"] = _first(row, "quote_mint", "quote_token_mint")
    normalized["quote_asset"] = _first(row, "quote_asset")
    normalized["source_signature"] = _first(row, "source_signature", "signature", "birth_signature")
    normalized["source_route"] = _first(row, "source_route", "route", "decode_route")
    return normalized


def verify_birth_candidate(row: Mapping[str, Any]) -> BirthVerificationResult:
    normalized = normalize_birth_candidate(row)
    reasons: list[str] = []
    for field in REQUIRED_STRICT_BIRTH_FIELDS:
        if not normalized.get(field):
            reasons.append(f"missing_{field}")
    if not normalized.get("source_signature"):
        reasons.append("missing_source_signature")
    if not normalized.get("quote_mint") and not normalized.get("quote_asset"):
        reasons.append("missing_quote_identity")
    derived_curve = _first(row, "derived_bonding_curve", "expected_bonding_curve")
    parsed_curve = normalized.get("bonding_curve")
    if derived_curve and parsed_curve and str(derived_curve) != str(parsed_curve):
        reasons.append("bonding_curve_pda_mismatch")
    derived_ata = _first(row, "derived_associated_bonding_curve", "expected_associated_bonding_curve")
    parsed_ata = normalized.get("associated_bonding_curve")
    if derived_ata and parsed_ata and str(derived_ata) != str(parsed_ata):
        reasons.append("associated_bonding_curve_ata_mismatch")
    explicit_reject = _first(row, "rejected", "sample_rejected", "capacity_rejected", "collector_rejected")
    if explicit_reject is True or str(explicit_reject).lower() == "true":
        reasons.append("candidate_rejected_before_strict_verification")
    verified = not reasons
    status = "verified_create" if verified else "birth_candidate_excluded"
    return BirthVerificationResult(verified=verified, status=status, reasons=tuple(reasons), normalized=normalized)

# --- T007_DERIVED_ASSOCIATED_BONDING_CURVE_V2 -------------------------------
# Production rule: a create row is not automatically unusable when the associated
# bonding curve token account is absent from the parsed instruction. If mint and
# bonding_curve are present, derive the ATA deterministically and mark the source.
# On-chain token-account verification can upgrade this to derived_verified when
# the probe supplies associated_bonding_curve_verified=true.
try:
    from .t007_protocol_codecs import derive_associated_bonding_curve_token_account as _t007_derive_abc_ata
except Exception:  # pragma: no cover
    _t007_derive_abc_ata = None

_original_normalize_birth_candidate_v2 = normalize_birth_candidate
_original_verify_birth_candidate_v2 = verify_birth_candidate

def normalize_birth_candidate(row):  # type: ignore[no-redef]
    normalized = _original_normalize_birth_candidate_v2(row)
    normalized.setdefault('associated_bonding_curve_source', row.get('associated_bonding_curve_source'))
    if not normalized.get('associated_bonding_curve') and normalized.get('bonding_curve') and normalized.get('mint') and _t007_derive_abc_ata is not None:
        try:
            normalized['associated_bonding_curve'] = _t007_derive_abc_ata(str(normalized['bonding_curve']), str(normalized['mint']))
            normalized['associated_bonding_curve_source'] = 'derived'
        except Exception:
            normalized['associated_bonding_curve_source'] = 'derive_failed'
    elif normalized.get('associated_bonding_curve'):
        normalized.setdefault('associated_bonding_curve_source', 'parsed')
    return normalized

def verify_birth_candidate(row):  # type: ignore[no-redef]
    normalized = normalize_birth_candidate(row)
    reasons = []
    for field in REQUIRED_STRICT_BIRTH_FIELDS:
        if not normalized.get(field):
            reasons.append(f"missing_{field}")
    if not normalized.get('source_signature'):
        reasons.append('missing_source_signature')
    if not normalized.get('quote_mint') and not normalized.get('quote_asset'):
        reasons.append('missing_quote_identity')
    derived_curve = _first(row, 'derived_bonding_curve', 'expected_bonding_curve')
    parsed_curve = normalized.get('bonding_curve')
    if derived_curve and parsed_curve and str(derived_curve) != str(parsed_curve):
        reasons.append('bonding_curve_pda_mismatch')
    derived_ata = _first(row, 'derived_associated_bonding_curve', 'expected_associated_bonding_curve')
    parsed_ata = normalized.get('associated_bonding_curve')
    if derived_ata and parsed_ata and str(derived_ata) != str(parsed_ata):
        reasons.append('associated_bonding_curve_ata_mismatch')
    explicit_reject = _first(row, 'rejected', 'sample_rejected', 'capacity_rejected', 'collector_rejected')
    if explicit_reject is True or str(explicit_reject).lower() == 'true':
        reasons.append('candidate_rejected_before_strict_verification')
    verified = not reasons
    source = normalized.get('associated_bonding_curve_source')
    associated_verified = row.get('associated_bonding_curve_verified') is True or str(row.get('associated_bonding_curve_verified')).lower() == 'true'
    if verified and source == 'derived' and associated_verified:
        level = 'derived_strict'
    elif verified and source == 'derived':
        level = 'derived_deterministic_unverified'
    elif verified:
        level = 'strict'
    else:
        level = 'rejected'
    normalized['birth_verification_level'] = level
    normalized['birth_verification_status'] = 'verified_create' if verified else 'birth_candidate_excluded'
    return BirthVerificationResult(verified=verified, status=normalized['birth_verification_status'], reasons=tuple(reasons), normalized=normalized)
