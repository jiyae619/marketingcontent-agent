"""Uniform interface over Gemini / OpenAI / Anthropic.

Each call_* function returns a dict:
    {
        "ok": bool,
        "text": str | None,
        "model": str,
        "input_tokens": int,
        "output_tokens": int,
        "cost_usd": float,        # estimated, NOT billed
        "latency_ms": int,
        "error": str | None,      # human-readable when ok=False
    }

Prices below are current as of 2025-11 and may drift. They are estimates
for showing relative cost in the UI, not for billing.
"""
import json
import os
import time
import urllib.error
import urllib.request


# (input $/Mtok, output $/Mtok)
PRICING = {
    "gemini-2.5-flash":           (0.075, 0.30),
    "claude-haiku-4-5-20251001":  (1.00,  5.00),
    "claude-sonnet-4-6":          (3.00,  15.00),
    "gpt-4o-mini":                (0.15,  0.60),
}


def _cost(model: str, in_tok: int, out_tok: int) -> float:
    rates = PRICING.get(model)
    if not rates:
        return 0.0
    return (in_tok / 1_000_000) * rates[0] + (out_tok / 1_000_000) * rates[1]


def _empty_result(model: str, error: str) -> dict:
    return {
        "ok": False, "text": None, "model": model,
        "input_tokens": 0, "output_tokens": 0,
        "cost_usd": 0.0, "latency_ms": 0,
        "error": error,
    }


def _post_json(url: str, payload: dict, headers: dict, timeout: int = 60):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={**headers, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def call_gemini(prompt: str, model: str = "gemini-2.5-flash") -> dict:
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        return _empty_result(model, "GEMINI_API_KEY not set")
    t0 = time.time()
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
        data = _post_json(url, {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"thinkingConfig": {"thinkingBudget": 0}},
        }, headers={})
        cand = (data.get("candidates") or [{}])[0]
        text = cand.get("content", {}).get("parts", [{}])[0].get("text", "")
        usage = data.get("usageMetadata", {}) or {}
        in_tok = int(usage.get("promptTokenCount", 0))
        out_tok = int(usage.get("candidatesTokenCount", 0))
        return {
            "ok": bool(text), "text": text or None, "model": model,
            "input_tokens": in_tok, "output_tokens": out_tok,
            "cost_usd": _cost(model, in_tok, out_tok),
            "latency_ms": int((time.time() - t0) * 1000),
            "error": None if text else "Empty response from Gemini",
        }
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return _empty_result(model, f"Gemini {e.code}: {body[:200]}")
    except Exception as e:
        return _empty_result(model, f"Gemini error: {e}")


def call_openai(prompt: str, model: str = "gpt-4o-mini") -> dict:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return _empty_result(model, "OPENAI_API_KEY not set")
    t0 = time.time()
    try:
        data = _post_json(
            "https://api.openai.com/v1/chat/completions",
            {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
            },
            headers={"Authorization": f"Bearer {key}"},
        )
        choice = (data.get("choices") or [{}])[0]
        text = choice.get("message", {}).get("content", "")
        usage = data.get("usage", {}) or {}
        in_tok = int(usage.get("prompt_tokens", 0))
        out_tok = int(usage.get("completion_tokens", 0))
        return {
            "ok": bool(text), "text": text or None, "model": model,
            "input_tokens": in_tok, "output_tokens": out_tok,
            "cost_usd": _cost(model, in_tok, out_tok),
            "latency_ms": int((time.time() - t0) * 1000),
            "error": None if text else "Empty response from OpenAI",
        }
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        # Surface billing errors clearly to the UI.
        msg = f"OpenAI {e.code}"
        if e.code == 429 and "quota" in body.lower():
            msg = "OpenAI: billing required (no quota)"
        elif e.code == 401:
            msg = "OpenAI: invalid API key"
        else:
            msg = f"OpenAI {e.code}: {body[:200]}"
        return _empty_result(model, msg)
    except Exception as e:
        return _empty_result(model, f"OpenAI error: {e}")


def call_anthropic(prompt: str, model: str = "claude-haiku-4-5-20251001") -> dict:
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        return _empty_result(model, "ANTHROPIC_API_KEY not set")
    t0 = time.time()
    try:
        data = _post_json(
            "https://api.anthropic.com/v1/messages",
            {
                "model": model,
                "max_tokens": 2048,
                "messages": [{"role": "user", "content": prompt}],
            },
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
            },
        )
        blocks = data.get("content", []) or []
        text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        usage = data.get("usage", {}) or {}
        in_tok = int(usage.get("input_tokens", 0))
        out_tok = int(usage.get("output_tokens", 0))
        return {
            "ok": bool(text), "text": text or None, "model": model,
            "input_tokens": in_tok, "output_tokens": out_tok,
            "cost_usd": _cost(model, in_tok, out_tok),
            "latency_ms": int((time.time() - t0) * 1000),
            "error": None if text else "Empty response from Anthropic",
        }
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        msg = f"Anthropic {e.code}"
        if "credit balance is too low" in body.lower():
            msg = "Anthropic: billing required (no credit)"
        elif e.code == 401:
            msg = "Anthropic: invalid API key"
        else:
            msg = f"Anthropic {e.code}: {body[:200]}"
        return _empty_result(model, msg)
    except Exception as e:
        return _empty_result(model, f"Anthropic error: {e}")


# Models the /api/compare endpoint fans out to. Order matters: it's the display order.
COMPARE_MODELS = [
    ("gemini",            "gemini-2.5-flash",          call_gemini),
    ("openai",            "gpt-4o-mini",               call_openai),
    ("anthropic-haiku",   "claude-haiku-4-5-20251001", call_anthropic),
    ("anthropic-sonnet",  "claude-sonnet-4-6",         call_anthropic),
]
