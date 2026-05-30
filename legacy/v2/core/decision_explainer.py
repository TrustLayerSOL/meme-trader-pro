import json
from urllib.parse import quote
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from core.redaction import redact_secrets


OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
GOOGLE_GENERATE_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GROQ_CHAT_COMPLETIONS_URL = "https://api.groq.com/openai/v1/chat/completions"


SYSTEM_INSTRUCTIONS = (
    "You are MemeTraderPro's advisory paper-trading reviewer. Explain why this "
    "candidate was bought, skipped, blocked, or closed using only the supplied "
    "decision evidence. Do not recommend live execution and do not tell the "
    "operator to buy or sell. Keep the answer under 180 words, focused on "
    "evidence, blockers, risk, and what to inspect next."
)


def _compact(value):
    if isinstance(value, dict):
        return {key: _compact(item) for key, item in value.items() if item not in (None, "", [], {})}
    if isinstance(value, list):
        return [_compact(item) for item in value if item not in (None, "", [], {})][:12]
    return value


def build_decision_explainer_context(decision):
    decision = decision if isinstance(decision, dict) else {}
    payload = decision.get("payload") if isinstance(decision.get("payload"), dict) else {}
    result = decision.get("result") if isinstance(decision.get("result"), dict) else {}
    inputs = payload.get("inputs") if isinstance(payload.get("inputs"), dict) else {}
    rule_outcomes = payload.get("rule_outcomes") if isinstance(payload.get("rule_outcomes"), dict) else {}
    return _compact({
        "decision_id": decision.get("decision_id"),
        "mint": decision.get("mint"),
        "signal_type": decision.get("signal_type"),
        "scanner_stage": decision.get("scanner_stage"),
        "final_action": decision.get("final_action"),
        "action_reason": decision.get("action_reason"),
        "paper_lane": decision.get("paper_lane"),
        "should_trade": decision.get("should_trade"),
        "score": {
            "total_score": decision.get("total_score"),
            "threshold": decision.get("threshold"),
            "edge_score": decision.get("edge_score"),
            "edge_verdict": decision.get("edge_verdict"),
            "reasons": (rule_outcomes.get("scoring") or {}).get("reasons"),
        },
        "quotes": {
            "buy_quote_pass": decision.get("buy_quote_pass"),
            "sell_quote_pass": decision.get("sell_quote_pass"),
            "quote_details": payload.get("quotes"),
            "route_feasibility": payload.get("route_feasibility"),
        },
        "risk": {
            "risk_label": decision.get("risk_label"),
            "risk_score": decision.get("risk_score"),
            "risk_checks": rule_outcomes.get("risk"),
            "holder_cluster": rule_outcomes.get("holder_cluster"),
        },
        "wallet_signals": {
            "wallets": inputs.get("wallets"),
            "wallet_count": inputs.get("wallet_count"),
            "wallet_quality": inputs.get("wallet_quality"),
        },
        "social_catalyst": {
            "social_match": inputs.get("social_match"),
            "social_catalyst": inputs.get("social_catalyst"),
            "social_matched": payload.get("social_matched"),
        },
        "market_context": inputs.get("market_context"),
        "paper_outcome": {
            "trade_id": decision.get("trade_id"),
            "trade_status": decision.get("trade_status"),
            "entry_time": decision.get("entry_time"),
            "close_time": decision.get("close_time"),
            "pnl": decision.get("pnl"),
            "pnl_pct": decision.get("pnl_pct"),
            "result": result,
        },
    })


def extract_response_text(response_payload):
    if not isinstance(response_payload, dict):
        return ""
    output_text = response_payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()
    parts = []
    for item in response_payload.get("output") or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content") or []:
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                parts.append(content["text"])
    return "\n".join(part.strip() for part in parts if part and part.strip()).strip()


def extract_google_response_text(response_payload):
    if not isinstance(response_payload, dict):
        return ""
    parts = []
    for candidate in response_payload.get("candidates") or []:
        if not isinstance(candidate, dict):
            continue
        content = candidate.get("content") if isinstance(candidate.get("content"), dict) else {}
        for part in content.get("parts") or []:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                parts.append(part["text"])
    return "\n".join(part.strip() for part in parts if part and part.strip()).strip()


def extract_chat_completion_text(response_payload):
    if not isinstance(response_payload, dict):
        return ""
    parts = []
    for choice in response_payload.get("choices") or []:
        if not isinstance(choice, dict):
            continue
        message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
        content = message.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    parts.append(item["text"])
    return "\n".join(part.strip() for part in parts if part and part.strip()).strip()


def generate_google_decision_explanation(decision, api_key=None, model=None, timeout=20):
    if not api_key:
        raise ValueError("GOOGLE_AI_API_KEY is required for decision explanations.")
    model = model or "gemini-2.5-flash"
    context = build_decision_explainer_context(decision)
    request_payload = {
        "systemInstruction": {
            "parts": [{"text": SYSTEM_INSTRUCTIONS}],
        },
        "contents": [{
            "role": "user",
            "parts": [{
                "text": "Explain this MemeTraderPro paper-trading decision:\n" + json.dumps(context, sort_keys=True, default=str),
            }],
        }],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 350,
        },
    }
    request = Request(
        GOOGLE_GENERATE_URL_TEMPLATE.format(model=quote(model, safe="-_.~")),
        data=json.dumps(request_payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            response_payload = json.loads(response.read().decode("utf-8") or "{}")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(redact_secrets(f"Google AI request failed with HTTP {exc.code}: {detail}")) from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(redact_secrets(f"Google AI request failed: {exc}")) from exc

    text = extract_google_response_text(response_payload)
    if not text:
        raise RuntimeError("Google AI response did not include advisory text.")
    return {
        "text": text,
        "model": response_payload.get("modelVersion") or model,
        "response_id": response_payload.get("responseId"),
    }


def generate_groq_decision_explanation(decision, api_key=None, model=None, timeout=20):
    if not api_key:
        raise ValueError("GROQ_API_KEY is required for decision explanations.")
    model = model or "llama-3.3-70b-versatile"
    context = build_decision_explainer_context(decision)
    request_payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_INSTRUCTIONS},
            {
                "role": "user",
                "content": "Explain this MemeTraderPro paper-trading decision:\n" + json.dumps(context, sort_keys=True, default=str),
            },
        ],
        "temperature": 0.2,
        "max_tokens": 350,
        "stream": False,
    }
    request = Request(
        GROQ_CHAT_COMPLETIONS_URL,
        data=json.dumps(request_payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            response_payload = json.loads(response.read().decode("utf-8") or "{}")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(redact_secrets(f"Groq request failed with HTTP {exc.code}: {detail}")) from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(redact_secrets(f"Groq request failed: {exc}")) from exc

    text = extract_chat_completion_text(response_payload)
    if not text:
        raise RuntimeError("Groq response did not include advisory text.")
    return {
        "text": text,
        "model": response_payload.get("model") or model,
        "response_id": response_payload.get("id"),
    }


def generate_decision_explanation(decision, api_key=None, model=None, timeout=20):
    if not api_key:
        raise ValueError("OPENAI_API_KEY is required for decision explanations.")
    model = model or "gpt-4.1-mini"
    context = build_decision_explainer_context(decision)
    request_payload = {
        "model": model,
        "instructions": SYSTEM_INSTRUCTIONS,
        "input": "Explain this MemeTraderPro paper-trading decision:\n" + json.dumps(context, sort_keys=True, default=str),
        "max_output_tokens": 350,
        "temperature": 0.2,
        "store": False,
    }
    request = Request(
        OPENAI_RESPONSES_URL,
        data=json.dumps(request_payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            response_payload = json.loads(response.read().decode("utf-8") or "{}")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(redact_secrets(f"OpenAI request failed with HTTP {exc.code}: {detail}")) from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(redact_secrets(f"OpenAI request failed: {exc}")) from exc

    text = extract_response_text(response_payload)
    if not text:
        raise RuntimeError("OpenAI response did not include advisory text.")
    return {
        "text": text,
        "model": response_payload.get("model") or model,
        "response_id": response_payload.get("id"),
    }
