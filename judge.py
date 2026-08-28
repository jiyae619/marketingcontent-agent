"""LLM-as-judge: grade generated content against the shared flag taxonomy.

The judge model is SWAPPABLE — `JUDGE_MODELS` is the single registry the UI
dropdown reads (via GET /api/judge/models) — and it must never be the same model
that produced the content (judge != generator). Model calls reuse providers.py.

Scaffold: runs and returns a structured verdict in memory; no persistence yet.
The categories come from feedback_db.FLAG_TAXONOMY so human flags (captured later
in the review UI) and the judge's criteria stay one shared vocabulary.
"""
import json
import os
import re

import providers
from feedback_db import FLAG_TAXONOMY


# Cloud judge models. (key, display label, model_id, provider_fn), display order.
_CLOUD_JUDGE_MODELS = [
    ("claude-sonnet", "Claude Sonnet 4.6", "claude-sonnet-4-6",         providers.call_anthropic),
    ("gpt-4o-mini",   "GPT-4o mini",       "gpt-4o-mini",               providers.call_openai),
    ("claude-haiku",  "Claude Haiku 4.5",  "claude-haiku-4-5-20251001", providers.call_anthropic),
    ("gemini-flash",  "Gemini 2.5 Flash",  "gemini-2.5-flash",          providers.call_gemini),
]

# Default judge when the caller doesn't pick one. Overridable via env.
DEFAULT_JUDGE_KEY = os.getenv("JUDGE_MODEL", "claude-sonnet")


def _local_judge_entry():
    """Local-LLM registry row, reflecting current env config. Always offered so the
    dropdown can pick 'run it locally'; label shows the configured model or a hint.

    Reads LOCAL_JUDGE_MODEL first so the local judge can be a DIFFERENT model from the
    local generator. Sharing one env var made both registries resolve to the same
    model_id, so judge != generator skipped local entirely and fell through to the
    first cloud entry — running the generator locally silently billed every judge call
    to Claude Sonnet. Falls back to LOCAL_LLM_MODEL when unset (cloud generator).
    """
    model = os.getenv("LOCAL_JUDGE_MODEL") or os.getenv("LOCAL_LLM_MODEL")
    base = os.getenv("LOCAL_LLM_BASE_URL")
    label = f"Local — {model}" if (model and base) else "Local (set LOCAL_LLM_BASE_URL + LOCAL_LLM_MODEL)"
    return ("local", label, model or "local", providers.call_local)


def judge_models():
    """The full judge registry: cloud models + the local option. Read fresh each
    call so a change to LOCAL_LLM_MODEL shows up without a restart. This is the
    ONE source of truth the UI dropdown reads (GET /api/judge/models).

    Under LOCAL_ONLY the cloud entries are removed entirely. Filtering here (not just
    at the provider) matters because resolve_judge falls through the registry in order
    when judge != generator excludes a candidate — with cloud entries present, a local
    judge that collides with the local generator silently lands on a paid model.
    """
    if providers.local_only():
        return [_local_judge_entry()]
    return [*_CLOUD_JUDGE_MODELS, _local_judge_entry()]

# What the judge scores. Categories are keyed to FLAG_TAXONOMY; each string tells
# the judge what the category means. The family (grounding/voice) comes from the
# taxonomy. Extend alongside FLAG_TAXONOMY — no schema change needed.
JUDGE_RUBRIC = {
    "hallucination":  "States facts about the speaker/event NOT supported by the brief — fabricated names, dates, titles, quotes, numbers, or claims. High = fully grounded, nothing invented.",
    "irrelevant":     "Generic or off-brief — fails to capture what is actually notable about THIS speaker/event. High = specific and on-brief.",
    "ai_slop":        "Robotic, generic 'AI' prose needing humanizing — cliches, hollow hype, template phrasing. High = natural and human.",
    "kr_en_register": "Wrong Korean/English language or formality register for the channel, when the brief implies one. High = correct register.",
}


def available_models():
    """Registry for the UI dropdown (GET /api/judge/models)."""
    return [{"key": key, "label": label, "model": model_id}
            for (key, label, model_id, _fn) in judge_models()]


def _by_key():
    return {key: (label, model_id, fn) for (key, label, model_id, fn) in judge_models()}


def resolve_judge(model_key=None, generator_model=None):
    """Choose the judge model. Preference order: requested key -> env default ->
    registry order. Enforces judge != generator by skipping any candidate whose
    model id equals the generator's model. Returns (key, label, model_id, fn), or
    raises ValueError if every model is excluded.
    """
    reg = _by_key()
    tried = []
    for key in [model_key, DEFAULT_JUDGE_KEY, *[k for (k, *_rest) in judge_models()]]:
        if not key or key in tried:
            continue
        tried.append(key)
        if key not in reg:
            continue
        label, model_id, fn = reg[key]
        if generator_model and model_id == generator_model:
            continue  # judge must differ from the generator
        return key, label, model_id, fn
    raise ValueError("no judge model available (all excluded by judge != generator)")


def _build_prompt(platform, content, source_brief=None):
    criteria = "\n".join(
        f'- "{cat}" ({family}): {JUDGE_RUBRIC.get(cat, cat)}'
        for cat, family in FLAG_TAXONOMY.items()
    )
    # The grounding criteria are defined relative to the brief ("facts NOT supported
    # by the brief"). Without it the judge can only guess at hallucination — it has
    # no way to know an invented topic or date was never asked for.
    brief_block = (
        f'The ORIGINAL BRIEF the content was written from:\n"""\n{source_brief}\n"""\n\n'
        "Judge grounding STRICTLY against this brief: any speaker, topic, date, time, "
        "location, price, or statistic in the content that is not in the brief is "
        "invented and must lower the grounding scores.\n\n"
        if source_brief else
        "NOTE: the original brief is unavailable, so grounding cannot be verified. "
        "Score grounding conservatively and say so in the reason.\n\n"
    )
    return (
        "You are a strict quality-and-safety judge for marketing content.\n"
        f"Platform: {platform}\n\n"
        + brief_block +
        "For EACH criterion, give a substantive reason (1-3 sentences): quote the "
        "specific words in the content that drive the score and explain WHY it earns "
        "that score — do not just restate the criterion. Then score 0-100 "
        "(0 = fails badly, 100 = perfect).\n"
        "Then give an overall 0-100, a safety_pass boolean (false if any grounding "
        "criterion is a serious fail), and a `summary`: 2-4 sentences covering the "
        "main strength, the main problem, and the single change that would most raise "
        "the score.\n\n"
        "Finally give a `confidence`: \"high\", \"medium\", or \"low\". Use \"low\" when "
        "you cannot actually verify what you were asked to judge — the brief is missing "
        "or too thin to check facts against, the content is in a language you cannot "
        "assess, or you would be guessing at a score. A \"low\" verdict is DISCARDED and "
        "the content is sent to a human instead, which is the correct outcome when you "
        "are unsure. Do not invent a confident score to avoid saying you don't know.\n\n"
        "Return ONLY a JSON object, no prose or markdown fences, of the form:\n"
        '{"scores": {"<category>": {"score": <int>, "reason": "<1-3 sentences citing specific text>"}, ...}, '
        '"overall": <int>, "safety_pass": <bool>, "summary": "<2-4 sentence rationale>"}\n\n'
        f"Criteria:\n{criteria}\n\n"
        f'Content to judge:\n"""\n{content}\n"""\n'
    )


def verdict_schema():
    """JSON Schema for a verdict, derived from FLAG_TAXONOMY so it cannot drift.

    Constrains the decoder instead of asking politely. "Return ONLY JSON" was the only
    guarantee before, and llama3.2:3b wrote three unparseable verdicts that landed as
    all-NULL rows. No `minimum`/`maximum` on the scores — Anthropic's structured
    outputs reject numeric constraints, and the range is stated in the prompt.
    """
    category = {
        "type": "object",
        "properties": {"score": {"type": "integer"}, "reason": {"type": "string"}},
        "required": ["score", "reason"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "scores": {
                "type": "object",
                "properties": {cat: category for cat in FLAG_TAXONOMY},
                "required": list(FLAG_TAXONOMY),
                "additionalProperties": False,
            },
            "overall": {"type": "integer"},
            "safety_pass": {"type": "boolean"},
            "summary": {"type": "string"},
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        },
        "required": ["scores", "overall", "safety_pass", "summary", "confidence"],
        "additionalProperties": False,
    }


def _extract_json(text):
    """Backstop parser. With a schema enforced this should be a no-op, but it still
    runs: not every model honours the schema, and a bare json_object mode (Ollama's
    fallback) constrains syntax without constraining shape."""
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def judge(content, platform, *, model=None, generator_model=None, source_brief=None):
    """Grade `content` against the flag taxonomy with a swappable judge model.

    model            — a JUDGE_MODELS key (from the dropdown); default via env/registry.
    generator_model  — the model that produced `content`; the judge is guaranteed
                       to differ from it (judge != generator).
    source_brief     — the original input the content was written from. Required for
                       the grounding criteria to mean anything: hallucination is
                       defined as facts NOT in the brief, so without it the judge is
                       guessing. Omitting it is allowed but degrades grounding.

    Returns a structured verdict: which model judged, ok/cost/latency, and on
    success the per-category scores, overall, and safety_pass.
    """
    key, label, model_id, fn = resolve_judge(model, generator_model)
    # Every provider gets the schema — a verdict that won't parse is a verdict lost,
    # and the discarded-NULL guard downstream only hides the failure, it doesn't stop
    # it. Each provider translates the schema to its own native form.
    kwargs = {"model": model_id, "json_schema": verdict_schema()}
    if fn is providers.call_local:
        kwargs["json_mode"] = True  # fallback if the runtime ignores the schema
    result = fn(_build_prompt(platform, content, source_brief), **kwargs)
    verdict = {
        "judge_key": key,
        "judge_label": label,
        "judge_model": model_id,
        "ok": bool(result.get("ok")),
        "cost_usd": result.get("cost_usd"),
        "latency_ms": result.get("latency_ms"),
    }
    if not result.get("ok"):
        verdict["error"] = result.get("error")
        return verdict
    parsed = _extract_json(result.get("text"))
    if parsed is None:
        verdict["error"] = "judge returned unparseable output"
        verdict["raw"] = (result.get("text") or "")[:500]
        return verdict
    verdict["scores"] = parsed.get("scores", {})
    verdict["overall"] = parsed.get("overall")
    verdict["safety_pass"] = parsed.get("safety_pass")
    verdict["summary"] = parsed.get("summary")
    # Abstention. The schema now guarantees `overall` is present, so the old
    # "discard when overall is None" guard can no longer catch a bad verdict — a
    # confidently wrong grade would persist and render in the review UI as real.
    # An unsure judge must route to a human instead of manufacturing a number.
    verdict["confidence"] = parsed.get("confidence")
    verdict["abstained"] = (verdict["confidence"] == "low")
    # Deterministic abstention. Whether a brief exists is a fact the code knows, so it
    # is not left to the model — and the model does not do it: llama3.2:3b returned
    # confidence="medium" and overall=80 for this same content with source_brief=None,
    # grading grounding it had no way to verify. Two of the four criteria
    # (hallucination, irrelevant) are defined relative to the brief, and safety_pass
    # is defined off the grounding family, so without a brief the verdict cannot mean
    # what the review UI would show it as.
    if not (source_brief or "").strip():
        verdict["abstained"] = True
        verdict["confidence"] = "low"
        verdict["abstain_reason"] = "no source brief — grounding unverifiable"
    if verdict["abstained"]:
        verdict["overall"] = None
        verdict["safety_pass"] = None
    return verdict
