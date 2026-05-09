import os
import re


def redact_secrets(value):
    text = str(value)
    for env_name in ("HELIUS_API_KEY", "JUPITER_API_KEY"):
        secret = os.getenv(env_name)
        if secret:
            text = text.replace(secret, "[REDACTED]")
    text = re.sub(r"api-key=([^&\\s]+)", "api-key=[REDACTED]", text)
    text = re.sub(r"x-api-key['\"]?\\s*[:=]\\s*['\"]?([^,'\"\\s}]+)", "x-api-key=[REDACTED]", text)
    return text
