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


# The judge models offered to the UI dropdown. ONE registry, one source of truth:
# add/remove a row here and the dropdown updates with it — no other change needed.
# (key, display label, model_id, provider_fn). Order = display order.
JUDGE_MODELS = [
    ("claude-sonnet", "Claude Sonnet 4.6", "claude-sonnet-4-6",         providers.call_anthropic),
    ("gpt-4o-mini",   "GPT-4o mini",       "gpt-4o-mini",               providers.call_openai),
    ("claude-haiku",  "Claude Haiku 4.5",  "claude-haiku-4-5-20251001", providers.call_anthropic),
    ("gemini-flash",  "Gemini 2.5 Flash",  "gemini-2.5-flash",          providers.call_gemini),
]

# Default judge when the caller doesn't pick one. Overridable via env.
DEFAULT_JUDGE_KEY = os.getenv("JUDGE_MODEL", "claude-sonnet")

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
            for (key, label, model_id, _fn) in JUDGE_MODELS]


def _by_key():
    return {key: (label, model_id, fn) for (key, label, model_id, fn) in JUDGE_MODELS}


def resolve_judge(model_key=None, generator_model=None):
    """Choose the judge model. Preference order: requested key -> env default ->
    registry order. Enforces judge != generator by skipping any candidate whose
    model id equals the generator's model. Returns (key, label, model_id, fn), or
    raises ValueError if every model is excluded.
    """
    reg = _by_key()
    tried = []
    for key in [model_key, DEFAULT_JUDGE_KEY, *[k for (k, *_rest) in JUDGE_MODELS]]:
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


def _build_prompt(platform, content):
    criteria = "\n".join(
        f'- "{cat}" ({family}): {JUDGE_RUBRIC.get(cat, cat)}'
        for cat, family in FLAG_TAXONOMY.items()
    )
    return (
        "You are a strict quality-and-safety judge for marketing content.\n"
        f"Platform: {platform}\n\n"
        "For each criterion, reason in one short phrase, then score 0-100 "
        "(0 = fails badly, 100 = perfect). Then give an overall 0-100 and a "
        "safety_pass boolean (false if any grounding criterion is a serious fail).\n\n"
        "Return ONLY a JSON object, no prose or markdown fences, of the form:\n"
        '{"scores": {"<category>": {"score": <int>, "reason": "<phrase>"}, ...}, '
        '"overall": <int>, "safety_pass": <bool>}\n\n'
        f"Criteria:\n{criteria}\n\n"
        f'Content to judge:\n"""\n{content}\n"""\n'
    )


def _extract_json(text):
    """Judges sometimes wrap JSON in prose or ``` fences — pull out the object."""
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def judge(content, platform, *, model=None, generator_model=None):
    """Grade `content` against the flag taxonomy with a swappable judge model.

    model            — a JUDGE_MODELS key (from the dropdown); default via env/registry.
    generator_model  — the model that produced `content`; the judge is guaranteed
                       to differ from it (judge != generator).

    Returns a structured verdict: which model judged, ok/cost/latency, and on
    success the per-category scores, overall, and safety_pass.
    """
    key, label, model_id, fn = resolve_judge(model, generator_model)
    result = fn(_build_prompt(platform, content), model=model_id)
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
    return verdict
