"""Generator model registry — the writing half, made swappable.

Mirrors judge.py's registry so both halves of the system are model-agnostic and the
same UI pattern (a dropdown reading one registry) works for each. Previously the
generator was hardcoded to gemini-2.5-flash in server.py, which meant it could not
be A/B tested even though /api/compare exists for exactly that purpose.

The judge != generator invariant reads `model` off the generation row, so swapping
the generator automatically re-opens whichever judge was previously excluded — e.g.
generating with Claude frees gemini-flash (the cheapest model) to judge.
"""
import os

import providers

# (key, display label, model_id, provider_fn) — display order.
_CLOUD_GENERATORS = [
    ("gemini-flash",  "Gemini 2.5 Flash",  "gemini-2.5-flash",          providers.call_gemini),
    ("gpt-4o-mini",   "GPT-4o mini",       "gpt-4o-mini",               providers.call_openai),
    ("claude-haiku",  "Claude Haiku 4.5",  "claude-haiku-4-5-20251001", providers.call_anthropic),
    ("claude-sonnet", "Claude Sonnet 4.6", "claude-sonnet-4-6",         providers.call_anthropic),
]

# Default generator. gemini-2.5-flash preserves prior behaviour unless overridden.
DEFAULT_GENERATOR_KEY = os.getenv("GENERATOR_MODEL", "gemini-flash")


def _local_entry():
    """Local-LLM row, reflecting current env. Always offered so the dropdown can
    pick 'run it locally'; the label shows the configured model or a hint."""
    model = os.getenv("LOCAL_LLM_MODEL")
    base = os.getenv("LOCAL_LLM_BASE_URL")
    label = f"Local — {model}" if (model and base) else "Local (set LOCAL_LLM_BASE_URL + LOCAL_LLM_MODEL)"
    return ("local", label, model or "local", providers.call_local)


def generator_models():
    """Full registry: cloud + local. Read fresh each call so an env change to
    LOCAL_LLM_MODEL shows up without a restart. Under LOCAL_ONLY the cloud entries
    are removed so no paid model can be selected or fallen back to."""
    if providers.local_only():
        return [_local_entry()]
    return [*_CLOUD_GENERATORS, _local_entry()]


def available_models():
    """Registry for the UI dropdown (GET /api/generator/models)."""
    return [{"key": k, "label": lb, "model": m}
            for (k, lb, m, _fn) in generator_models()]


def resolve(model_key=None):
    """Resolve a generator key to (key, label, model_id, fn).

    Falls back to the env default, then the first registry entry, so an unknown or
    missing key degrades to working behaviour rather than erroring mid-request.
    """
    reg = {k: (lb, m, fn) for (k, lb, m, fn) in generator_models()}
    for key in (model_key, DEFAULT_GENERATOR_KEY, generator_models()[0][0]):
        if key and key in reg:
            label, model_id, fn = reg[key]
            return key, label, model_id, fn
    raise ValueError("no generator model available")


def generate(prompt, *, model_key=None, system=None):
    """Run one generation. Returns the provider result dict plus which model ran.

    system — the channel template + voice profile. Passed separately so each provider
    can put it in its native slot (Anthropic's `system` field, an OpenAI system
    message); providers that have no native slot concatenate it back on. Flattening
    it into the user turn is what made Claude ask for the brief to be resent.

    Local models get json_mode=False — unlike the judge, generation output is prose,
    not JSON.
    """
    key, label, model_id, fn = resolve(model_key)
    result = fn(prompt, model=model_id, system=system)
    result["generator_key"] = key
    result["generator_label"] = label
    result["generator_model"] = model_id
    return result
