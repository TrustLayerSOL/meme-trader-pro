import json


RISK_PASS = "PASS"
RISK_WARNING = "WARNING"
RISK_DANGER = "DANGER"
RISK_UNKNOWN = "UNKNOWN"


class HolderConcentrationAnalyzer:
    """Pure holder concentration analyzer for already-fetched holder rows."""

    ADDRESS_FIELDS = (
        "address",
        "owner",
        "wallet",
        "pubkey",
        "account",
        "holder",
    )
    AMOUNT_FIELDS = (
        "ui_amount",
        "uiAmount",
        "amount",
        "balance",
        "token_amount",
        "tokenAmount",
    )

    def analyze(self, holder_rows):
        rows = self.extract_rows(holder_rows)
        warnings = []
        holders = []
        malformed_count = 0

        for index, row in enumerate(rows):
            holder = self.normalize_holder(row, index)
            if holder is None:
                malformed_count += 1
                continue
            holders.append(holder)

        if malformed_count:
            warnings.append(
                "{} malformed or zero-balance holder row(s) ignored".format(malformed_count)
            )

        total_amount = sum(holder["amount"] for holder in holders)
        if not holders or total_amount <= 0:
            warnings.append("No usable positive holder balances supplied")
            return self.empty_result(warnings)

        holders = sorted(holders, key=lambda holder: holder["amount"], reverse=True)
        holder_count = len(holders)

        metrics = {
            "holder_count": holder_count,
            "top_1_pct": self.top_pct(holders, total_amount, 1),
            "top_5_pct": self.top_pct(holders, total_amount, 5),
            "top_10_pct": self.top_pct(holders, total_amount, 10),
            "top_20_pct": self.top_pct(holders, total_amount, 20),
            "top_holder_address": holders[0]["address"],
            "total_amount": self.round_amount(total_amount),
        }

        risk_label = self.classify(metrics, warnings)

        return {
            "risk_label": risk_label,
            "hard_block": False,
            "warnings": warnings,
            "metrics": metrics,
        }

    def extract_rows(self, holder_rows):
        if holder_rows is None:
            return []
        if isinstance(holder_rows, list):
            return holder_rows
        if isinstance(holder_rows, tuple):
            return list(holder_rows)
        if isinstance(holder_rows, dict):
            for key in ("holders", "accounts", "rows", "data", "result"):
                value = holder_rows.get(key)
                if isinstance(value, list):
                    return value
            return [holder_rows]
        return []

    def normalize_holder(self, row, index):
        address = None
        amount = None

        if isinstance(row, dict):
            address = self.pick_address(row)
            amount = self.pick_amount(row)
        elif isinstance(row, (list, tuple)):
            address, amount = self.pick_from_sequence(row, index)
        else:
            return None

        amount = self.safe_float(amount)
        if amount <= 0:
            return None

        return {
            "address": self.clean_address(address, index),
            "amount": amount,
        }

    def pick_address(self, row):
        for field in self.ADDRESS_FIELDS:
            value = row.get(field)
            if value:
                return value

        owner = row.get("ownerAddress")
        if owner:
            return owner

        return None

    def pick_amount(self, row):
        for field in self.AMOUNT_FIELDS:
            value = row.get(field)
            if isinstance(value, dict):
                nested = self.pick_amount(value)
                if nested is not None:
                    return nested
            elif value not in (None, ""):
                return value

        for field in ("uiTokenAmount", "tokenAmount"):
            value = row.get(field)
            if isinstance(value, dict):
                nested = self.pick_amount(value)
                if nested is not None:
                    return nested

        return None

    def pick_from_sequence(self, row, index):
        if len(row) < 2:
            return "holder_{}".format(index + 1), None

        first = row[0]
        second = row[1]

        if self.safe_float(first, None) is not None and self.safe_float(second, None) is None:
            return second, first

        return first, second

    def classify(self, metrics, warnings):
        holder_count = metrics["holder_count"]
        top_1_pct = metrics["top_1_pct"]
        top_5_pct = metrics["top_5_pct"]
        top_10_pct = metrics["top_10_pct"]
        top_20_pct = metrics["top_20_pct"]

        if holder_count < 3:
            warnings.append("Fewer than 3 usable holders")
            return RISK_DANGER

        danger_reasons = []
        if top_1_pct >= 50:
            danger_reasons.append("Top holder controls at least 50%")
        if top_5_pct >= 80:
            danger_reasons.append("Top 5 holders control at least 80%")
        if top_10_pct >= 90:
            danger_reasons.append("Top 10 holders control at least 90%")
        if holder_count < 10 and top_1_pct >= 35:
            danger_reasons.append("Small holder set with a dominant top holder")

        if danger_reasons:
            warnings.extend(danger_reasons)
            return RISK_DANGER

        warning_reasons = []
        if holder_count < 20:
            warning_reasons.append("Fewer than 20 usable holders")
        if top_1_pct >= 20:
            warning_reasons.append("Top holder controls at least 20%")
        if top_5_pct >= 50:
            warning_reasons.append("Top 5 holders control at least 50%")
        if top_10_pct >= 70:
            warning_reasons.append("Top 10 holders control at least 70%")
        if top_20_pct >= 85:
            warning_reasons.append("Top 20 holders control at least 85%")

        if warning_reasons:
            warnings.extend(warning_reasons)
            return RISK_WARNING

        return RISK_PASS

    def empty_result(self, warnings):
        return {
            "risk_label": RISK_UNKNOWN,
            "hard_block": False,
            "warnings": warnings,
            "metrics": {
                "holder_count": 0,
                "top_1_pct": 0,
                "top_5_pct": 0,
                "top_10_pct": 0,
                "top_20_pct": 0,
                "top_holder_address": None,
                "total_amount": 0,
            },
        }

    def top_pct(self, holders, total_amount, limit):
        if total_amount <= 0:
            return 0
        amount = sum(holder["amount"] for holder in holders[:limit])
        return round((amount / total_amount) * 100, 2)

    def clean_address(self, value, index):
        value = str(value or "").strip()
        if not value:
            return "unknown_holder_{}".format(index + 1)
        return value

    def safe_float(self, value, default=0):
        try:
            if isinstance(value, bool) or value in (None, ""):
                return default
            if isinstance(value, str):
                value = value.replace(",", "").strip()
                if value == "":
                    return default
            return float(value)
        except Exception:
            return default

    def round_amount(self, value):
        value = self.safe_float(value)
        rounded = round(value, 8)
        if rounded == int(rounded):
            return int(rounded)
        return rounded


def analyze_holder_concentration(holder_rows):
    return HolderConcentrationAnalyzer().analyze(holder_rows)


if __name__ == "__main__":
    sample_rows = [
        {"owner": "wallet_alpha", "uiAmount": 4200},
        {"owner": "wallet_beta", "ui_amount": "1800"},
        {"owner": "wallet_gamma", "amount": 1200},
        ["wallet_delta", 900],
        {"address": "wallet_epsilon", "tokenAmount": {"uiAmount": 700}},
        {"owner": "wallet_zeta", "balance": 500},
        {"owner": "wallet_eta", "amount": 400},
        {"owner": "wallet_theta", "amount": 300},
    ]
    print(json.dumps(analyze_holder_concentration(sample_rows), indent=2, sort_keys=True))
