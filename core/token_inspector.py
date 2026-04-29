CLASSIC_SPL_TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN_2022_PROGRAM = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"


BENIGN_TOKEN_2022_EXTENSIONS = {
    "metadataPointer",
    "tokenMetadata",
}


HARD_REJECT_EXTENSIONS = {
    "nonTransferable",
    "permanentDelegate",
}


CAUTION_EXTENSIONS = {
    "transferHook",
    "transferFeeConfig",
    "confidentialTransferMint",
    "confidentialTransferFeeConfig",
    "pausable",
}


class TokenInspector:
    def analyze_account_info(self, mint, account_info):
        value = (account_info or {}).get("result", {}).get("value")
        if not value:
            return self.unavailable(mint, "mint account not found")

        owner = value.get("owner")
        data = value.get("data") or {}
        parsed = data.get("parsed") or {}
        info = parsed.get("info") or {}

        extensions = []
        for extension in info.get("extensions", []) or []:
            if isinstance(extension, dict) and extension.get("extension"):
                extensions.append(extension.get("extension"))

        mint_authority = info.get("mintAuthority")
        freeze_authority = info.get("freezeAuthority")
        default_state = self.default_account_state(info)

        token_standard = "CLASSIC_SPL"
        if owner == TOKEN_2022_PROGRAM or data.get("program") == "spl-token-2022":
            token_standard = "TOKEN_2022"
        elif owner != CLASSIC_SPL_TOKEN_PROGRAM:
            token_standard = "UNKNOWN_PROGRAM"

        hard_reasons = []
        caution_reasons = []

        dangerous = sorted(set(extensions) & HARD_REJECT_EXTENSIONS)
        caution = sorted(set(extensions) & CAUTION_EXTENSIONS)
        unknown = sorted(
            set(extensions)
            - BENIGN_TOKEN_2022_EXTENSIONS
            - HARD_REJECT_EXTENSIONS
            - CAUTION_EXTENSIONS
        )

        if dangerous:
            hard_reasons.append("Dangerous Token-2022 extension(s): " + ", ".join(dangerous))

        if default_state == "frozen":
            hard_reasons.append("Default account state is frozen")

        if token_standard == "UNKNOWN_PROGRAM":
            caution_reasons.append(f"Unknown mint owner program: {owner}")

        if caution:
            caution_reasons.append("Caution Token-2022 extension(s): " + ", ".join(caution))

        if unknown:
            caution_reasons.append("Unknown Token-2022 extension(s): " + ", ".join(unknown))

        if mint_authority:
            caution_reasons.append("Mint authority is still present")

        if freeze_authority:
            caution_reasons.append("Freeze authority is still present")

        hard_block = bool(hard_reasons)
        if hard_block:
            risk_label = "BLOCKED"
        elif caution_reasons:
            risk_label = "CAUTION"
        else:
            risk_label = "PASS"

        return {
            "mint": mint,
            "available": True,
            "owner": owner,
            "program": data.get("program"),
            "token_standard": token_standard,
            "extensions": extensions,
            "dangerous_extensions": dangerous,
            "caution_extensions": caution,
            "unknown_extensions": unknown,
            "mint_authority": mint_authority,
            "freeze_authority": freeze_authority,
            "default_account_state": default_state,
            "hard_block": hard_block,
            "risk_label": risk_label,
            "reasons": hard_reasons + caution_reasons or ["No dangerous token mechanics detected"],
        }

    async def inspect_with_rpc(self, rpc, mint):
        try:
            account_info = await rpc.rpc_call(
                "getAccountInfo",
                [
                    mint,
                    {
                        "encoding": "jsonParsed",
                        "commitment": "confirmed",
                    },
                ],
            )
            return self.analyze_account_info(mint, account_info)
        except Exception as exc:
            return self.unavailable(mint, str(exc))

    def unavailable(self, mint, reason):
        return {
            "mint": mint,
            "available": False,
            "owner": None,
            "program": None,
            "token_standard": "UNKNOWN",
            "extensions": [],
            "dangerous_extensions": [],
            "caution_extensions": [],
            "unknown_extensions": [],
            "mint_authority": None,
            "freeze_authority": None,
            "default_account_state": None,
            "hard_block": False,
            "risk_label": "UNKNOWN",
            "reasons": [reason],
        }

    def default_account_state(self, info):
        for extension in info.get("extensions", []) or []:
            if not isinstance(extension, dict):
                continue
            if extension.get("extension") != "defaultAccountState":
                continue
            state = extension.get("state") or {}
            return str(state.get("state") or state.get("accountState") or "").lower()
        return None
