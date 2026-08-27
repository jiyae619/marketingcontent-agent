"""Deterministic bug detectors — code answers what code can answer.

Every check here is a fact, not an opinion: it runs a command or asserts an
invariant and reports pass/fail with the output that produced it. No model is
involved, so a run costs nothing and cannot hallucinate a finding.

The model tier only sees what survives this file. That split is CLAUDE.md rule 5
("if code can answer, code answers") — wiring an agent into `npm run build` would
be using a language model for routing.

Each detector returns a Finding dict:

    id        stable key, used to compare runs across the fix loop
    ok        True = passing. The gate only trusts this field.
    severity  high | medium | low — orders the fix queue
    title     one line, what broke
    detail    the evidence: real output, truncated only in the middle
    cmd       the command a human can re-run to see it themselves
    fixable   whether an agent editing files could plausibly repair it
"""

import json
import os
import re
import shutil
import subprocess
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))          # tools/bughunt
REPO = os.path.dirname(os.path.dirname(HERE))              # repo root
BASELINE = os.path.join(HERE, "baseline.json")


def _finding(id, ok, severity, title, detail="", cmd="", fixable=True):
    return {"id": id, "ok": ok, "severity": severity, "title": title,
            "detail": detail, "cmd": cmd, "fixable": fixable}


def _run(cmd, cwd=None, timeout=600, env=None):
    """Run a command, never raise. Returns (rc, combined_output)."""
    e = dict(os.environ)
    if env:
        e.update(env)
    try:
        p = subprocess.run(cmd, cwd=cwd or REPO, shell=isinstance(cmd, str),
                           capture_output=True, text=True, timeout=timeout, env=e)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, f"TIMEOUT after {timeout}s: {cmd}"
    except Exception as ex:  # missing binary, permissions, ...
        return 127, f"could not run {cmd}: {ex}"


def _clip(s, head=1500, tail=800):
    """Truncate the MIDDLE, never the end.

    CLAUDE.md rule 8: never truncate evidence when claiming absence. A `head -N`
    on a failure log hides the error, which is usually at the bottom.
    """
    s = (s or "").strip()
    if len(s) <= head + tail:
        return s
    return f"{s[:head]}\n\n… [{len(s) - head - tail} chars elided] …\n\n{s[-tail:]}"


# --------------------------------------------------------------------------
# Env / build breakage
# --------------------------------------------------------------------------

def check_preflight():
    """The project's own config gate. Non-zero means a hard constraint is violated."""
    rc, out = _run([sys.executable, "scripts/preflight.py"], timeout=120)
    return _finding(
        "env.preflight", rc == 0, "high",
        "preflight reports a config violation" if rc else "preflight OK",
        _clip(out), "python3 scripts/preflight.py",
    )


def check_clean_clone_build():
    """Build from a pristine clone of HEAD, with no .env present.

    This is the check that did not exist when it was needed. `vite.config.js`
    threw on a missing API_PORT for every command, but API_PORT only feeds the
    dev-server proxy — so `npm run build` passed locally (where .env is present
    and gitignored) and failed in every clean environment. The Netlify deploy
    stayed red for 19 days because nothing ever built the repo as a stranger.
    """
    tmp = tempfile.mkdtemp(prefix="bughunt-build-")
    try:
        rc, out = _run(["git", "clone", "--quiet", "--no-hardlinks", REPO, tmp], timeout=180)
        if rc != 0:
            return _finding("build.clean_clone", False, "high",
                            "could not clone the repo for a clean build", _clip(out),
                            "git clone <repo> /tmp/x", fixable=False)
        # A clean clone has no .env by construction (it is gitignored), which is
        # exactly the condition CI and Netlify build under.
        rc, out = _run(["npm", "ci", "--no-audit", "--no-fund"], cwd=tmp, timeout=600)
        if rc != 0:
            return _finding("build.clean_clone", False, "high",
                            "npm ci fails on a clean clone (lockfile out of sync?)",
                            _clip(out), "npm ci")
        rc, out = _run(["npm", "run", "build"], cwd=tmp, timeout=600)
        return _finding(
            "build.clean_clone", rc == 0, "high",
            "production build fails from a clean clone" if rc else "clean-clone build OK",
            _clip(out), "git clone . /tmp/x && cd /tmp/x && npm ci && npm run build",
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_lint():
    rc, out = _run(["npm", "run", "lint"], timeout=300)
    return _finding("env.eslint", rc == 0, "low",
                    "eslint reports problems" if rc else "eslint clean",
                    _clip(out), "npm run lint")


def check_data_layer():
    """25-check write-path fixture. Binds its own temp DB, never touches the real one."""
    rc, out = _run([sys.executable, "scripts/test_feedback_db.py"], timeout=300)
    return _finding("data.feedback_db", rc == 0, "high",
                    "feedback_db write-path checks fail" if rc else "feedback_db checks pass",
                    _clip(out), "python3 scripts/test_feedback_db.py")


# --------------------------------------------------------------------------
# Judge-pipeline invariants
#
# These assert the rules that past incidents produced. Each one is a regression
# guard for a bug that was already paid for once.
# --------------------------------------------------------------------------

def check_abstention_contract():
    """An abstained verdict must not also carry a score.

    Abstention exists because two of the four criteria (hallucination, irrelevant)
    are defined against the source brief. With no brief they are unanswerable — but
    llama3.2:3b answered anyway, returning confidence="medium" and overall=80 for
    grounding it could not observe. So the code decides deterministically instead.

    The contract this asserts: when the code abstains, the payload must not still
    assert a number. Today judge.py sets the abstention flags but leaves `overall`
    and `safety_pass` holding the model's values, so the returned dict says both
    "could not verify" and "scored 80". Every in-repo consumer happens to branch on
    `abstained` first, so nothing stored or rendered is currently wrong — this
    guards the next caller, who will not know to.

    The probe swaps providers.call_local for a canned response, so it makes no
    model call and is safe under LOCAL_ONLY.

    It loads .env and pins LOCAL_ONLY=true before importing judge, for a reason
    worth stating: a bare `python3 -c` does NOT load .env, so LOCAL_ONLY is unset,
    and resolve_judge then falls straight through the local entry to the first
    CLOUD one. The first version of this probe resolved to claude-sonnet-4-6 and
    was saved from a paid call only by the absence of an API key. That is the
    fallthrough CLAUDE.md rule 3 exists for, reproduced by a test of it.
    """
    probe = r'''
import json, sys, os
sys.path.insert(0, %r)
from dotenv import load_dotenv
load_dotenv(os.path.join(%r, ".env"))
# Belt and braces: pin it even if .env is missing or says otherwise. A detector
# must never be the thing that reaches a paid API.
os.environ["LOCAL_ONLY"] = "true"

import providers, judge as J
from feedback_db import FLAG_TAXONOMY

for name in ("call_anthropic", "call_openai", "call_gemini"):
    if hasattr(providers, name):
        setattr(providers, name, lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("bughunt probe attempted a paid provider call")))

payload = {"scores": {c: 80 for c in FLAG_TAXONOMY},
           "overall": 80, "safety_pass": True,
           "summary": "canned", "confidence": "medium"}
providers.call_local = lambda *a, **k: {
    "ok": True, "cost_usd": 0.0, "latency_ms": 1, "text": json.dumps(payload)}

import sys as _s
route = _s.argv[1] if len(_s.argv) > 1 else "no-brief"
if route == "low-confidence":
    # The OTHER way to abstain: the model self-reports low confidence, with a
    # brief present. Same contract, different code path.
    payload["confidence"] = "low"
    providers.call_local = lambda *a, **k: {
        "ok": True, "cost_usd": 0.0, "latency_ms": 1, "text": json.dumps(payload)}
    v = J.judge("some content", "kakaotalk",
                generator_model="gemma3:4b", source_brief="a real brief")
else:
    v = J.judge("some content", "kakaotalk",
                generator_model="gemma3:4b", source_brief=None)
print(json.dumps({"judge_model": v.get("judge_model"),
                  "ok": v.get("ok"),
                  "error": v.get("error"),
                  "abstained": v.get("abstained"),
                  "confidence": v.get("confidence"),
                  "overall": v.get("overall"),
                  "safety_pass": v.get("safety_pass"),
                  "reason": v.get("abstain_reason")}))
''' % (REPO, REPO)
    # BOTH routes to abstention, because they are separate code paths and a fix to
    # one is not a fix to the other. An earlier version of this detector probed only
    # `no-brief`; an agent then nulled the score in that branch alone, and the
    # partial fix passed. A contract test has to cover every way in.
    bad, seen = [], {}
    for route, why in (("no-brief", "source_brief=None"),
                       ("low-confidence", 'model returned confidence="low"')):
        rc, out = _run([sys.executable, "-c", probe, route], timeout=120)
        if rc != 0:
            return _finding("judge.abstention_contract", False, "medium",
                            f"abstention probe ({route}) could not run", _clip(out),
                            "see tools/bughunt/detectors.py:check_abstention_contract")
        try:
            v = json.loads(out.strip().splitlines()[-1])
        except Exception:
            return _finding("judge.abstention_contract", False, "medium",
                            f"abstention probe ({route}) returned unreadable output",
                            _clip(out), "")
        # If the judge call itself failed, the abstention path was never reached —
        # say that, rather than reporting a violation the probe did not observe.
        if not v.get("ok"):
            return _finding("judge.abstention_contract", False, "medium",
                            f"abstention probe ({route}) never reached the verdict path",
                            f"judge() returned ok={v.get('ok')} error={v.get('error')!r} "
                            f"model={v.get('judge_model')!r}. The contract is untested, "
                            f"not disproved.", "see detectors.py")
        seen[route] = v
        if not v.get("abstained"):
            bad.append(f"[{route}] did not abstain when {why}")
            continue
        if v.get("overall") is not None:
            bad.append(f'[{route}] abstained but still carries overall={v["overall"]}')
        if v.get("safety_pass") is not None:
            bad.append(f'[{route}] abstained but still carries '
                       f'safety_pass={v["safety_pass"]}')

    return _finding(
        "judge.abstention_contract", not bad, "medium",
        "abstained verdict still asserts a score" if bad else "abstention contract holds",
        ("An abstained verdict must not also report a grade — the payload asserts "
         "both.\n  " + "\n  ".join(bad) + "\n\nprobes returned:\n"
         + json.dumps(seen, indent=2))
        if bad else json.dumps(seen, indent=2),
        "python3 -c '<abstention probe>'  # see detectors.py",
    )


def check_stuck_judge_rows():
    """A judge_results row stuck at `pending` means the judge thread died mid-call.

    Visible instead of silent is the whole point of the status column: 45 of 49
    eligible generations were once never judged and nothing recorded it.
    """
    db = os.path.join(REPO, "testing/results/feedback.db")
    if not os.path.exists(db):
        return _finding("judge.stuck_rows", True, "medium",
                        "no local DB yet — nothing to check", "", "", fixable=False)
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        rows = conn.execute(
            "SELECT COUNT(*) FROM judge_results WHERE status = 'pending'").fetchone()[0]
        bad = conn.execute(
            "SELECT COUNT(*) FROM judge_results "
            "WHERE status = 'abstained' AND overall IS NOT NULL").fetchone()[0]
        conn.close()
    except Exception as e:
        return _finding("judge.stuck_rows", True, "medium",
                        f"could not read judge_results ({e})", "", "", fixable=False)
    problems = []
    if rows:
        problems.append(f"{rows} judge_results row(s) stuck at status='pending'")
    if bad:
        problems.append(f"{bad} abstained row(s) stored with a non-NULL overall")
    return _finding(
        "judge.stuck_rows", not problems, "medium",
        "; ".join(problems) if problems else "no stuck or contradictory judge rows",
        "\n".join(problems),
        "sqlite3 testing/results/feedback.db \"select status, count(*) "
        "from judge_results group by status\"",
    )


# --------------------------------------------------------------------------
# Eval-quality regression
# --------------------------------------------------------------------------

def _parse_gate_metrics(out):
    """Pull the stable numbers out of tune_threshold.py's report."""
    m = {}
    sep = re.search(r"SEPARABILITY:\s*(\d+)/(\d+)", out)
    if sep:
        m["overlap"] = int(sep.group(1))
        m["defective"] = int(sep.group(2))
    for cat, tp, tot in re.findall(r"^\s{4}(\S+)\s+(\d+)/(\d+) caught", out, re.M):
        m[f"recall.{cat}"] = f"{tp}/{tot}"
    return m


def check_eval_quality():
    """Replay the golden set and compare against the recorded baseline.

    This does not assert the gate is *good* — it is known not to be, and that
    finding is the point of the golden set. It asserts the numbers have not
    silently MOVED, which is what happens when a prompt or a scorer band is
    edited without its counterpart (CLAUDE.md rule 5: prompts and scorers are
    one decision in two files).
    """
    golden = os.path.join(REPO, "testing/golden/golden_set_v1.json")
    if not os.path.exists(golden):
        return _finding("eval.gate_metrics", True, "low",
                        "no golden set present — skipped (rebuild: scripts/golden_set.py)",
                        "", "python3 scripts/golden_set.py", fixable=False)
    rc, out = _run([sys.executable, "scripts/tune_threshold.py"], timeout=300)
    if rc != 0:
        return _finding("eval.gate_metrics", False, "medium",
                        "golden-set replay failed to run", _clip(out),
                        "python3 scripts/tune_threshold.py")
    now = _parse_gate_metrics(out)
    if not now:
        return _finding("eval.gate_metrics", False, "low",
                        "could not parse metrics from tune_threshold.py output", _clip(out),
                        "python3 scripts/tune_threshold.py")

    prior = {}
    if os.path.exists(BASELINE):
        try:
            prior = json.load(open(BASELINE)).get("eval.gate_metrics", {})
        except Exception:
            prior = {}
    if not prior:
        # First run records the baseline rather than inventing a verdict about it.
        _save_baseline_key("eval.gate_metrics", now)
        return _finding("eval.gate_metrics", True, "low",
                        f"baseline recorded ({len(now)} metrics) — drift checked from now on",
                        json.dumps(now, indent=2), "python3 scripts/tune_threshold.py")

    drift = [f"{k}: {prior.get(k)} -> {now[k]}" for k in now
             if k in prior and prior[k] != now[k]]
    return _finding(
        "eval.gate_metrics", not drift, "medium",
        "golden-set metrics moved since the baseline" if drift else "golden-set metrics stable",
        ("Prompts and scorers are one decision in two files; a drift here usually "
         "means one was edited without the other.\n  " + "\n  ".join(drift))
        if drift else json.dumps(now, indent=2),
        "python3 scripts/tune_threshold.py",
    )


def _save_baseline_key(key, value):
    data = {}
    if os.path.exists(BASELINE):
        try:
            data = json.load(open(BASELINE))
        except Exception:
            data = {}
    data[key] = value
    with open(BASELINE, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)


# --------------------------------------------------------------------------

ALL = [
    check_preflight,
    check_clean_clone_build,
    check_data_layer,
    check_abstention_contract,
    check_stuck_judge_rows,
    check_eval_quality,
    check_lint,
]

# Slow detectors are skipped by --quick. The clean-clone build dominates a run
# (npm ci from cold), so a tight fix loop can defer it to the final gate.
SLOW = {"build.clean_clone"}


def run_all(quick=False, only=None):
    out = []
    for fn in ALL:
        f = fn.__name__
        probe_id = {
            "check_preflight": "env.preflight",
            "check_clean_clone_build": "build.clean_clone",
            "check_data_layer": "data.feedback_db",
            "check_abstention_contract": "judge.abstention_contract",
            "check_stuck_judge_rows": "judge.stuck_rows",
            "check_eval_quality": "eval.gate_metrics",
            "check_lint": "env.eslint",
        }[f]
        if quick and probe_id in SLOW:
            continue
        if only and probe_id not in only:
            continue
        out.append(fn())
    return out
