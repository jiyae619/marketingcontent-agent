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

# A model that fits on disk still cannot RUN if no memory is free to hold it:
# Ollama silently drops to CPU and grinds against swap. Measured on this machine —
# gemma3:4b under pressure 0.28 tok/s, llama3.2:3b on CPU but fitting 4.4 tok/s,
# a healthy GPU offload 20+. At the 2.0 floor the 120s timeout in providers.py
# still allows ~240 output tokens, which covers the shortest channel. Judgement
# call from three measurements, not a limit tested to failure.
MIN_TOK_S = 2.0
CANARY_TOKENS = 5
CANARY_TIMEOUT_S = 25

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


def _in_vram(root, model):
    """True if `model` currently holds weights in VRAM, False if CPU, None if unknown."""
    try:
        with urllib.request.urlopen(root + "/api/ps", timeout=5) as r:
            for m in json.loads(r.read().decode()).get("models") or []:
                if (m.get("name") or m.get("model")) == model:
                    return bool(m.get("size_vram"))
    except Exception:
        pass
    return None


def canary(model):
    """Generate a few tokens with `model` and time them -> (tok_s, in_vram, err).

    tok_s comes from Ollama's own eval_count/eval_duration, so model load time is
    excluded: this is the steady-state speed a real generation will actually get.
    in_vram is probed on the failure path too — when the canary times out, *where
    the model landed* is the whole diagnosis, so it must survive the timeout.
    """
    base = os.getenv("LOCAL_LLM_BASE_URL") or ""
    if not base:
        return None, None, "LOCAL_LLM_BASE_URL not set"
    root = providers._ollama_root(base)
    # Measure what a real call will get, which is a call that evicts its rival first.
    providers._evict_others(base, model)
    try:
        req = urllib.request.Request(
            root + "/api/generate",
            data=json.dumps({"model": model, "prompt": "hi", "stream": False,
                             "options": {"num_predict": CANARY_TOKENS}}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=CANARY_TIMEOUT_S) as r:
            d = json.loads(r.read().decode())
    except Exception as e:
        return None, _in_vram(root, model), f"{type(e).__name__}: {e}"
    n, ns = d.get("eval_count") or 0, d.get("eval_duration") or 0
    tok_s = n / (ns / 1e9) if ns else None
    return tok_s, _in_vram(root, model), None


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

# --- is the judge actually WIRED to generation? ------------------------------
# Resolving a judge says which model would grade; it does not say whether anything
# asks it to. JUDGE_ON_GENERATE decides that, and a resolved-looking judge next to a
# disabled dispatch is precisely the "config looks fine, reality differs" shape this
# script exists to catch.
live_judge = os.getenv("JUDGE_ON_GENERATE", "true").strip().lower() \
    not in ("0", "false", "no", "off")
if live_judge:
    ok("judge on generate", "on — every generation is graded")
else:
    warn("judge on generate", "OFF — nothing grades live; judge is offline-sweep only")

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

# --- voice synthesis: the learning loop's second model ------------------------
# This existed and silently did nothing. It was hard-wired to providers.call_gemini,
# which LOCAL_ONLY refuses outright, so on this project's own default config the
# synthesis half of the loop never ran and the only trace was one print line in a
# background thread. Preflight is where "what actually runs" is supposed to be
# visible, so it belongs here rather than being rediscovered later.
v_model = os.getenv("VOICE_MODEL") or os.getenv("LOCAL_LLM_MODEL")
if not v_model:
    warn("voice synthesis", "no VOICE_MODEL/LOCAL_LLM_MODEL — loop falls back to raw few-shot")
elif local_only and v_model != g_model:
    # Not a failure, but worth seeing: a second model evicts the generator on every
    # approve (CLAUDE.md rule 1 — two models cannot co-reside on 8GB).
    warn("voice synthesis", f"{v_model} differs from generator {g_model} — evicts it on each run")
else:
    ok("voice synthesis", f"{v_model}  (local, same as generator — no eviction)")

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

# --- capacity: can the resolved generator actually RUN, right now? ------------
# Everything above validates configuration. None of it asks whether there is
# memory to run that configuration, which is the failure that actually costs
# sessions: this script printed PREFLIGHT OK sixty seconds before a run that
# could not possibly finish, because Ollama had 1.2GB free, logged
# `offloaded 0/35 layers to GPU`, and fell back to CPU. Config is spotless in
# that state — only a real generation shows it, so do a tiny one.
# Generator only, deliberately: canarying the judge as well would load both
# models at once, causing the co-residency providers._evict_others prevents.
if installed and g_model and g_fn is providers.call_local:
    tok_s, in_vram, err = canary(g_model)
    where = "" if in_vram is None else (" on GPU" if in_vram else " on CPU")
    if err:
        detail = f"loaded{where}, still no tokens" if in_vram is not None else err
        fail("generator runs",
             f"{g_model} produced nothing in {CANARY_TIMEOUT_S}s ({detail}) — free memory, then retry")
    elif tok_s is None:
        warn("generator speed", f"{g_model} answered but reported no timing")
    elif tok_s < MIN_TOK_S:
        fail("generator speed",
             f"{tok_s:.2f} tok/s{where}, under the {MIN_TOK_S} floor — free memory, then retry")
    else:
        ok("generator speed", f"{g_model}  {tok_s:.1f} tok/s{where}")

# --- owed judge work ---------------------------------------------------------
# A `pending` row older than one judge run means the thread died mid-call. Before the
# status column this was invisible: 45 of 49 eligible generations were never judged and
# nothing recorded it. Surfaced here because preflight is what runs before everything.
try:
    import feedback_db  # noqa: E402
    stuck = feedback_db.stuck_judge_results(older_than_s=300)
    if stuck:
        warn("stuck judge rows", f"{len(stuck)} pending >5min — re-drivable")
    else:
        ok("stuck judge rows", "none")
except Exception as e:
    warn("stuck judge rows", f"unreadable: {e}")

# --- summary -----------------------------------------------------------------
print()
if fails:
    print(f"\033[31mPREFLIGHT FAILED\033[0m — {len(fails)} problem(s): {', '.join(fails)}")
    print("Fix these before generating or judging. See CLAUDE.md.\n")
    sys.exit(1)
print(f"\033[32mPREFLIGHT OK\033[0m" + (f" — {len(warns)} warning(s)" if warns else "") + "\n")
sys.exit(0)
