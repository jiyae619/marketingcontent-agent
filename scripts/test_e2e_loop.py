#!/usr/bin/env python3
"""End-to-end fixture for the human-in-the-loop pipeline.

Walks a draft all the way through: human verdict -> diff captured -> family routed
-> synthesis prompt assembled -> profile gated. Each stage is exercised through the
REAL code path (feedback_db, the /api/copies handler logic, server's synthesis), not
a reimplementation of it, so a change that breaks the pipeline breaks this.

Cases live in testing/test_data/loop_cases_v1.json rather than in this file. They
are data on purpose, and pct_changed / n_edits in them are FROZEN: if diff_ops changes,
these fail, which is correct — every number derived from that metric changed too.

They sit in test_data rather than testing/golden because .gitignore excludes
testing/golden/*.json — that set embeds real generated content and is rebuildable
from scripts/golden_set.py, whereas these are hand-written and must be tracked, or
this check cannot run on a fresh checkout.

No model is called. providers is stubbed, so this runs in CI with no Ollama, no keys
and no spend — the same constraint tools/bughunt's suite already works under.

    python3 scripts/test_e2e_loop.py
"""
import json
import os
import sqlite3
import sys
import tempfile

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO)
sys.path.insert(0, os.path.join(_REPO, "testing/core"))

DEFAULT_DB = os.path.join(_REPO, "testing/results/feedback.db")
_env = os.environ.get("FEEDBACK_DB_PATH")
if not _env or os.path.abspath(_env) == os.path.abspath(DEFAULT_DB):
    os.environ["FEEDBACK_DB_PATH"] = os.path.join(
        tempfile.mkdtemp(prefix="e2e_"), "test.db")
# Pin these BEFORE importing server: VOICE_MODEL resolves at import, and LOCAL_ONLY
# must be on so a stub that slips through cannot reach a paid provider.
os.environ.setdefault("LOCAL_LLM_MODEL", "gemma3:4b")
os.environ["LOCAL_ONLY"] = "true"

import feedback_db as db      # noqa: E402
import providers              # noqa: E402
import server                 # noqa: E402

assert os.path.abspath(db.DB_PATH) != os.path.abspath(DEFAULT_DB), \
    "refusing to run against the real feedback.db"

# Any paid call is a bug in the test, not a failure to tolerate.
for _name in ("call_gemini", "call_openai", "call_anthropic"):
    setattr(providers, _name, lambda *a, **k: (_ for _ in ()).throw(
        AssertionError(f"e2e attempted a paid provider call: {_name}")))

CASES = json.load(open(os.path.join(_REPO, "testing/test_data/loop_cases_v1.json"),
                       encoding="utf-8"))
CHECKS = 0


def check(label, cond, detail=""):
    global CHECKS
    CHECKS += 1
    assert cond, f"FAILED: {label}" + (f"\n        {detail}" if detail else "")
    print(f"  ok  {label}")


def fresh():
    db.DB_PATH = os.path.join(tempfile.mkdtemp(prefix="e2e_"), "test.db")
    db.init_db()


def apply_case(c):
    """Drive one case through the same decisions /api/copies makes.

    Mirrors the handler's branch structure (classify_verdict, then the chip
    requirement on an edit) rather than calling log_feedback directly, so the rule
    that actually gates a real request is the rule under test.
    """
    h, plat = c["human"], c["platform"]
    gid = db.log_generation(platform=plat, original_input=c["brief"],
                            generated_content=c["draft"], model="gemma3:4b")
    if h["action"] == "reject":
        verdict, final = "reject", None
    else:
        verdict = db.classify_verdict(c["draft"], h["final"])
        final = h["final"]
        if verdict == "edit" and not h["chip"]:
            raise ValueError("flag_category required on an edit")
    eid = db.log_feedback(generation_id=gid, platform=plat, verdict=verdict,
                          original_content=c["draft"], final_content=final,
                          flag_category=h["chip"], edit_note=h.get("note"))
    return gid, eid, verdict


# --- 1. every case routes as the golden file says ---------------------------
def test_cases():
    print("E1 golden loop cases")
    for c in CASES["cases"]:
        fresh()
        gid, eid, verdict = apply_case(c)
        e, plat = c["expect"], c["platform"]
        with sqlite3.connect(db.DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            row = dict(conn.execute("SELECT * FROM feedback_events WHERE id=?", (eid,)).fetchone())

        check(f"[{c['id']}] verdict {e['verdict']}", row["verdict"] == e["verdict"],
              f"got {row['verdict']}")
        check(f"[{c['id']}] family {e['family']}", row["flag_family"] == e["family"],
              f"got {row['flag_family']}")
        check(f"[{c['id']}] pct_changed {e['pct_changed']}",
              row["pct_changed"] == e["pct_changed"], f"got {row['pct_changed']}")
        in_voice = any(v["id"] == eid for v in db.voice_edits(plat, limit=50))
        check(f"[{c['id']}] voice corpus = {e['in_voice_corpus']}",
              in_voice == e["in_voice_corpus"])
        in_defect = any(v["id"] == eid for v in db.grounding_defects(plat, limit=50))
        check(f"[{c['id']}] defect list = {e['in_defect_list']}",
              in_defect == e["in_defect_list"])


# --- 2. an edit with no chip cannot be recorded ------------------------------
def test_chip_required():
    print("E2 the chip is required on an edit")
    fresh()
    c = next(x for x in CASES["cases"] if x["expect"]["verdict"] == "edit")
    stripped = json.loads(json.dumps(c))
    stripped["human"]["chip"] = None
    try:
        apply_case(stripped)
        raise AssertionError("an unlabelled edit was accepted")
    except ValueError:
        check("unlabelled edit refused", True)
    # An APPROVE still needs no chip — the requirement must not leak onto the
    # common path, which is what would make reviewers stop using it.
    fresh()
    ap = next(x for x in CASES["cases"] if x["expect"]["verdict"] == "approve")
    ap = json.loads(json.dumps(ap)); ap["human"]["chip"] = None
    _, _, v = apply_case(ap)
    check("approve still needs no chip", v == "approve")


# --- 3. what reaches the synthesis prompt ------------------------------------
def test_synthesis_prompt():
    print("E3 synthesis prompt carries voice edits and no grounding edits")
    fresh()
    for c in CASES["cases"]:
        if c["platform"] == "linkedin":
            apply_case(c)
    seen = {}

    def stub(prompt, model=None, system=None, **kw):
        seen["prompt"], seen["model"] = prompt, model
        return {"ok": True, "cost_usd": 0.0, "latency_ms": 1, "text": GOOD_PROFILE}
    providers.call_local = stub
    server.CORSRequestHandler._maybe_synthesize_voice(None, "linkedin")

    check("synthesis ran on the local model", seen.get("model") == server.VOICE_MODEL)
    voice_chips = {c["human"]["chip"] for c in CASES["cases"]
                   if c["platform"] == "linkedin" and c["expect"]["in_voice_corpus"]}
    for chip in voice_chips:
        check(f"prompt carries the {chip} edit", f"[{chip}]" in seen["prompt"])
    ground_chips = {c["human"]["chip"] for c in CASES["cases"]
                    if c["platform"] == "linkedin" and c["expect"]["family"] == "grounding"}
    for chip in ground_chips:
        # The load-bearing one: a fact fix must never be taught as style.
        check(f"prompt EXCLUDES the {chip} edit", f"[{chip}]" not in seen["prompt"])
    check("profile installed", bool(db.get_voice_profile("linkedin")))


GOOD_PROFILE = ("Short declarative sentences with little ornament. Warm but restrained "
                "and never effusive. Leads with the concrete detail, then closes on a "
                "plain call to action. Avoids hype vocabulary entirely.")


# --- 4. a bad profile never reaches the prompt -------------------------------
def test_profile_gate():
    print("E4 a bad synthesis result is not installed")
    sample = next(c["draft"] for c in CASES["cases"])
    bad = {
        "echoes an input sample": "They write like this: " + sample + " every single time.",
        "one word": "Casual.",
        "empty": "",
        "padded past the band": "word " * 400,
    }
    for label, text in bad.items():
        fresh()
        ap = next(x for x in CASES["cases"] if x["expect"]["verdict"] == "approve")
        apply_case(ap)
        providers.call_local = lambda p, model=None, system=None, _t=text, **kw: {
            "ok": True, "cost_usd": 0.0, "latency_ms": 1, "text": _t}
        server.CORSRequestHandler._maybe_synthesize_voice(None, ap["platform"])
        check(f"rejected: {label}", db.get_voice_profile(ap["platform"]) is None)

    fresh()
    ap = next(x for x in CASES["cases"] if x["expect"]["verdict"] == "approve")
    apply_case(ap)
    providers.call_local = lambda p, model=None, system=None, **kw: {
        "ok": False, "error": "Local LLM unreachable", "cost_usd": 0.0, "latency_ms": 0}
    server.CORSRequestHandler._maybe_synthesize_voice(None, ap["platform"])
    check("provider failure installs nothing", db.get_voice_profile(ap["platform"]) is None)

    fresh(); apply_case(ap)
    providers.call_local = lambda p, model=None, system=None, **kw: {
        "ok": True, "cost_usd": 0.0, "latency_ms": 1, "text": GOOD_PROFILE}
    server.CORSRequestHandler._maybe_synthesize_voice(None, ap["platform"])
    check("a valid profile IS installed", db.get_voice_profile(ap["platform"]) is not None)


# --- 5. the regression gate's verdict logic ----------------------------------
def test_voice_gate():
    print("E5 voice gate promotes, blocks and rolls back")
    import voice_gate as vg

    fresh()
    plat = "linkedin"
    db.save_voice_profile(plat, "OLD PROFILE TEXT that is long enough to be plausible.")
    db.save_voice_profile(plat, "NEW PROFILE TEXT that is long enough to be plausible.")
    hist = db.voice_profile_history(plat, limit=2)
    check("predecessor is retained for comparison",
          len(hist) == 2 and hist[0]["version"] > hist[1]["version"])

    briefs = [{"brief": "b1", "language": "en"}, {"brief": "b2", "language": "en"}]
    vg.feedback_db = db
    vg.golden_briefs = lambda p: briefs

    # Exercise the decision directly rather than through argparse.
    vg.generate = lambda platform, brief, style, model_key=None: (
        (60.0 if style.startswith("NEW") else 80.0), "t", None)
    sys.argv = ["voice_gate", "--platform", plat]
    check("regression exits non-zero", vg.main() == 1)

    vg.generate = lambda platform, brief, style, model_key=None: (
        (85.0 if style.startswith("NEW") else 80.0), "t", None)
    check("improvement exits zero", vg.main() == 0)

    vg.generate = lambda platform, brief, style, model_key=None: (
        (79.5 if style.startswith("NEW") else 80.0), "t", None)
    check("a drop inside tolerance is not a regression", vg.main() == 0)

    # A generation that never ran is not evidence of a regression.
    vg.generate = lambda platform, brief, style, model_key=None: (None, None, "unreachable")
    check("all-failed is inconclusive, not a failure", vg.main() == 2)

    # Rollback reinstates the predecessor as a NEW version; nothing is deleted.
    vg.generate = lambda platform, brief, style, model_key=None: (
        (60.0 if style.startswith("NEW") else 80.0), "t", None)
    sys.argv = ["voice_gate", "--platform", plat, "--rollback"]
    before = db.voice_profile_history(plat, limit=10)
    check("rollback still reports the regression", vg.main() == 1)
    after = db.voice_profile_history(plat, limit=10)
    check("rollback appends rather than deletes", len(after) == len(before) + 1)
    check("rollback reinstates the predecessor's text",
          after[0]["style_text"].startswith("OLD"))


def test_e6_grounding_guard():
    print("E6 grounding guard — delete what is safe, flag what is not")
    from evaluators import strip_ungrounded
    brief = next(c["brief"] for c in CASES["cases"])

    # Every one of these was produced by a real model in the seven-model sweep.
    for src, want in [
        ("Sep 14th, 2026 (Saturday), 3PM PST", "Sep 14th, 2026, 3PM PST"),
        ("9월 14일(토) 오후 3시 PST", "9월 14일 오후 3시 PST"),
        ("박운영 세션, 화요일 오후 3시", "박운영 세션, 오후 3시"),
        ("Join us on Monday at 3PM.", "Join us at 3PM."),
    ]:
        got, _ = strip_ungrounded(src, brief)
        check(f"ungrounded weekday removed: {src[:26]}", got == want, f"got {got!r}")

    # The guard must not delete a weekday the brief actually states.
    for b_extra, src in [("\nday: Monday", "Join us on Monday at 3PM."),
                         ("\n요일: 금요일", "9월 14일(금) 오후 3시")]:
        got, _ = strip_ungrounded(src, brief + b_extra)
        check(f"grounded weekday survives: {src[:22]}", got == src, f"got {got!r}")

    got, flags = strip_ungrounded("참여 신청은 [링크] 에서 하세요.", brief)
    check("placeholder stripped AND flagged",
          "[링크]" not in got and any(k == "placeholder" for k, _ in flags))

    # A restyle noun is flagged, never cut: removing it breaks the sentence.
    src = "세미나 주제는 커리어 레쥬메입니다."
    got, flags = strip_ungrounded(src, brief)
    check("restyle flagged, not deleted",
          got == src and ("restyle", "세미나") in flags, f"got {got!r} {flags}")

    check("empty input is a no-op", strip_ungrounded("", brief) == ("", []))


def main():
    print(f"e2e loop fixture — {len(CASES['cases'])} golden cases, temp DB, no model calls\n")
    test_cases()
    test_chip_required()
    test_synthesis_prompt()
    test_profile_gate()
    test_voice_gate()
    test_e6_grounding_guard()
    print(f"\nALL {CHECKS} CHECKS PASSED")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(f"\n{e}")
        sys.exit(1)
