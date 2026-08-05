"""Print the RESOLVED model config and refuse to proceed on a known-bad one.

Every config bug this catches was a real one. They shared a shape: `.env` looked
plausible, the resolved values did not match it, and nothing said so until output was
already wrong. Reading `.env` is not enough — both registries have fallbacks.

    python3 scripts/preflight.py

Exit 0 = safe to run. Exit 1 = at least one FAIL; fix before generating or judging.
"""
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(HERE, ".env"))

import providers    # noqa: E402
import generators   # noqa: E402
import judge        # noqa: E402

MAX_LOCAL_GB = 4.0   # 8GB M3: a 4B (~3.3GB) fits; 7B+ swaps. See CLAUDE.md.

fails, warns = [], []


def ok(label, value):
    print(f"  \033[32m✓\033[0m {label:34} {value}")


def fail(label, value):
    print(f"  \033[31m✗ FAIL\033[0m {label:30} {value}")
    fails.append(label)


def warn(label, value):
    print(f"  \033[33m!\033[0m {label:34} {value}")
    warns.append(label)


def ollama_models():
    """Installed local models -> {name: size_gb}. Empty dict if unreachable."""
    base = (os.getenv("LOCAL_LLM_BASE_URL") or "").replace("/v1", "")
    if not base:
        return {}
    try:
        with urllib.request.urlopen(base + "/api/tags", timeout=5) as r:
            data = json.loads(r.read().decode())
        return {m["name"]: m.get("size", 0) / 1e9 for m in data.get("models", [])}
    except Exception:
        return {}


print("\nRESOLVED CONFIG  (not .env — what the code actually picks)\n")

# --- billing -----------------------------------------------------------------
local_only = providers.local_only()
if local_only:
    ok("LOCAL_ONLY", "true — paid providers refuse")
else:
    warn("LOCAL_ONLY", "NOT set — cloud calls will bill")

# --- generator ---------------------------------------------------------------
try:
    g_key, g_label, g_model, g_fn = generators.resolve(None)
    ok("generator", f"{g_model}  ({g_fn.__name__})")
except Exception as e:
    fail("generator", f"unresolvable: {e}")
    g_model, g_fn = None, None

# --- judge, resolved against the REAL generator ------------------------------
# Passing the true generator_model is the whole point: a hand-typed value here is
# what let a model grade its own output.
j_model = j_fn = None
if g_model:
    try:
        j_key, j_label, j_model, j_fn = judge.resolve_judge(None, generator_model=g_model)
        ok("judge", f"{j_model}  ({j_fn.__name__})")
    except ValueError as e:
        fail("judge", str(e))

# --- the invariant -----------------------------------------------------------
if g_model and j_model:
    if g_model == j_model:
        fail("judge != generator", f"BOTH are {g_model} — a model would grade itself")
    else:
        ok("judge != generator", f"{g_model}  vs  {j_model}")

# --- no paid path when LOCAL_ONLY -------------------------------------------
if local_only:
    for name, fn in (("generator", g_fn), ("judge", j_fn)):
        if fn is not None and fn is not providers.call_local:
            fail(f"{name} is local", f"resolves to {fn.__name__} despite LOCAL_ONLY")
    refused = [f.__name__ for f in (providers.call_gemini, providers.call_openai,
                                    providers.call_anthropic)
               if not f("ping", model="preflight").get("ok")]
    if len(refused) == 3:
        ok("paid providers refuse", "gemini, openai, anthropic")
    else:
        fail("paid providers refuse", f"only {refused} refused")

# --- local models installed and small enough ---------------------------------
installed = ollama_models()
if not installed:
    warn("ollama", "unreachable — local calls will fail")
else:
    for name, model in (("generator", g_model), ("judge", j_model)):
        if not model or (g_fn if name == "generator" else j_fn) is not providers.call_local:
            continue
        if model not in installed:
            fail(f"{name} installed", f"{model} not in ollama ({len(installed)} present)")
        elif installed[model] > MAX_LOCAL_GB:
            fail(f"{name} size", f"{model} is {installed[model]:.1f}GB > {MAX_LOCAL_GB}GB cap")
        else:
            ok(f"{name} size", f"{model}  {installed[model]:.1f}GB")

# --- summary -----------------------------------------------------------------
print()
if fails:
    print(f"\033[31mPREFLIGHT FAILED\033[0m — {len(fails)} problem(s): {', '.join(fails)}")
    print("Fix these before generating or judging. See CLAUDE.md.\n")
    sys.exit(1)
print(f"\033[32mPREFLIGHT OK\033[0m" + (f" — {len(warns)} warning(s)" if warns else "") + "\n")
sys.exit(0)
