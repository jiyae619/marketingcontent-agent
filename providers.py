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


def local_only() -> bool:
    """True when no paid API call may be made, read fresh so it can't be stale."""
    return os.getenv("LOCAL_ONLY", "").strip().lower() in ("1", "true", "yes", "on")


def _refused(model: str) -> dict:
    return _empty_result(model, "LOCAL_ONLY=true — refused a paid API call")


def _gemini_schema(schema: dict):
    """Gemini's responseSchema is an OpenAPI subset and rejects `additionalProperties`.
    Strip it recursively; every other key we emit is valid there."""
    if isinstance(schema, dict):
        return {k: _gemini_schema(v) for k, v in schema.items()
                if k != "additionalProperties"}
    if isinstance(schema, list):
        return [_gemini_schema(v) for v in schema]
    return schema


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


def call_gemini(prompt: str, model: str = "gemini-2.5-flash", system: str = None,
                json_schema: dict = None) -> dict:
    # Single choke point for billing: every paid path goes through here.
    if local_only():
        return _refused(model)
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        return _empty_result(model, "GEMINI_API_KEY not set")
    t0 = time.time()
    try:
        # Gemini is the incumbent generator and the only one with a scored history,
        # so it keeps the flat concatenation it has always had — splitting it into
        # systemInstruction would change the prompt and invalidate that baseline.
        if system:
            prompt = f"{system}\n\n{prompt}"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
        gen_cfg = {"thinkingConfig": {"thinkingBudget": 0}}
        if json_schema:
            gen_cfg["responseMimeType"] = "application/json"
            gen_cfg["responseSchema"] = _gemini_schema(json_schema)
        data = _post_json(url, {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": gen_cfg,
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


def call_openai(prompt: str, model: str = "gpt-4o-mini", system: str = None,
                json_schema: dict = None) -> dict:
    # Single choke point for billing: every paid path goes through here.
    if local_only():
        return _refused(model)
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return _empty_result(model, "OPENAI_API_KEY not set")
    t0 = time.time()
    msgs = ([{"role": "system", "content": system}] if system else []) + \
           [{"role": "user", "content": prompt}]
    payload = {"model": model, "messages": msgs}
    if json_schema:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "verdict", "strict": True, "schema": json_schema},
        }
    try:
        data = _post_json(
            "https://api.openai.com/v1/chat/completions",
            payload,
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


# Claude 4.6+ models run adaptive thinking, and max_tokens caps thinking AND visible
# text together — the same trap that truncated Gemini output before thinkingBudget=0
# (see the voice-profile fix). 2048 was tight enough to cut mid-post; 8192 leaves room.
ANTHROPIC_MAX_TOKENS = 8192


def call_anthropic(prompt: str, model: str = "claude-haiku-4-5-20251001",
                   system: str = None, json_schema: dict = None) -> dict:
    # Single choke point for billing: every paid path goes through here.
    if local_only():
        return _refused(model)
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        return _empty_result(model, "ANTHROPIC_API_KEY not set")
    t0 = time.time()
    # The channel template belongs in `system`, not the user turn. Flattened into one
    # user message it ends with a "## Examples" section, and Claude read those examples
    # as the conversation — gen 71 answered "could you resend the actual content?"
    # instead of writing a post, and scored 36 for a plumbing bug.
    payload = {
        "model": model,
        "max_tokens": ANTHROPIC_MAX_TOKENS,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        payload["system"] = system
    if json_schema:
        # Structured outputs. Supported on Haiku 4.5, Sonnet 5, Opus 5 (and Opus 4.5 /
        # 4.1). NOT verified against claude-sonnet-4-6 — if that model 400s on
        # output_config, either move the judge to claude-haiku or drop the schema.
        payload["output_config"] = {
            "format": {"type": "json_schema", "schema": json_schema}
        }
    try:
        data = _post_json(
            "https://api.anthropic.com/v1/messages",
            payload,
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


def call_local(prompt: str, model: str = None, json_mode: bool = False,
               system: str = None, json_schema: dict = None) -> dict:
    """Call a locally-run LLM via an OpenAI-compatible endpoint.

    Works with Ollama, LM Studio, llama.cpp server, vLLM, etc. — anything that
    serves POST /chat/completions in the OpenAI shape. Configured by env:
        LOCAL_LLM_BASE_URL  e.g. http://localhost:11434/v1  (Ollama)
                            or   http://localhost:1234/v1   (LM Studio)
        LOCAL_LLM_MODEL     e.g. llama3.1:8b, qwen2.5:7b
        LOCAL_LLM_API_KEY   optional; most local servers ignore it
    Cost is 0 — it runs on your machine.
    """
    base = os.getenv("LOCAL_LLM_BASE_URL")
    model = model or os.getenv("LOCAL_LLM_MODEL")
    if not base:
        return _empty_result(model or "local", "LOCAL_LLM_BASE_URL not set")
    if not model:
        return _empty_result("local", "LOCAL_LLM_MODEL not set")
    key = os.getenv("LOCAL_LLM_API_KEY", "not-needed")
    t0 = time.time()
    msgs = ([{"role": "system", "content": system}] if system else []) + \
           [{"role": "user", "content": prompt}]
    payload = {"model": model, "messages": msgs}
    if json_schema:
        # Schema beats bare json_object: it constrains the SHAPE, not just the syntax.
        # A small model can emit perfectly valid JSON with none of the keys we read.
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "verdict", "strict": True, "schema": json_schema},
        }
    elif json_mode:
        # Small local models routinely emit malformed JSON (mismatched braces,
        # out-of-range values) when merely *asked* for it in the prompt. Constraining
        # the decoder is what actually guarantees a parseable object — measured:
        # llama3.2:3b went from unparseable to valid on the first try.
        payload["response_format"] = {"type": "json_object"}
    try:
        data = _post_json(
            base.rstrip("/") + "/chat/completions",
            payload,
            headers={"Authorization": f"Bearer {key}"},
            timeout=120,  # local models can be slower than hosted APIs
        )
        choice = (data.get("choices") or [{}])[0]
        text = choice.get("message", {}).get("content", "")
        usage = data.get("usage", {}) or {}
        return {
            "ok": bool(text), "text": text or None, "model": model,
            "input_tokens": int(usage.get("prompt_tokens", 0)),
            "output_tokens": int(usage.get("completion_tokens", 0)),
            "cost_usd": 0.0,  # local = free
            "latency_ms": int((time.time() - t0) * 1000),
            "error": None if text else "Empty response from local LLM",
        }
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return _empty_result(model, f"Local LLM {e.code}: {body[:200]}")
    except urllib.error.URLError as e:
        return _empty_result(model, f"Local LLM unreachable at {base} ({e.reason}) — is the server running?")
    except Exception as e:
        return _empty_result(model, f"Local LLM error: {e}")


# Models the /api/compare endpoint fans out to. Order matters: it's the display order.
COMPARE_MODELS = [
    ("gemini",            "gemini-2.5-flash",          call_gemini),
    ("openai",            "gpt-4o-mini",               call_openai),
    ("anthropic-haiku",   "claude-haiku-4-5-20251001", call_anthropic),
    ("anthropic-sonnet",  "claude-sonnet-4-6",         call_anthropic),
]
