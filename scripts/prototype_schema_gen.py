#!/usr/bin/env python3
"""Prototype — the model writes PROSE, code writes FACTS.

Why this shape. Seven local models on one brief invented a weekday, a price, a
placeholder or a restyled event type. All four rules were stated explicitly, in
Korean and English, in every channel prompt. The failures survive because the model
is the thing producing the facts, so nothing structurally prevents it inventing one.

This inverts that. Two model calls, both with a tiny prompt — which is the regime
the ablation showed actually works (gemma2:2b grounded perfectly under a
120-character instruction, cleanly at 221, and failed at 3,321):

  1. EXTRACT   facts from the brief, schema-constrained. The one thing small models
               were measured doing perfectly.
  2. WRITE     hook / body / cta / hashtags, schema-constrained. Prose only — the
               model never sees a date field to fill.
  3. ASSEMBLE  in code. The details block is built FROM THE EXTRACTED FACTS, so a
               weekday the brief never stated has nowhere to enter, and a missing
               price yields a missing line rather than "[Insert Price]".

What this cannot fix: restyling inside prose. That stays a flag (strip_ungrounded).

    python3 scripts/prototype_schema_gen.py --model local:llama3.2:3b
    python3 scripts/prototype_schema_gen.py --model local:hyperclovax:1.5b --compare
"""
import argparse, json, os, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "testing/core"))
from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(HERE, ".env"))
import providers  # noqa: E402
from evaluators import evaluate as run_eval, strip_markdown, strip_ungrounded, is_korean  # noqa: E402

BRIEF = """coaching session with 박운영
location: seattle university
time: sep 14th, 2026, 3PM PST

content
- 커리어 레쥬메
- 인터뷰 전략
- 네트워킹 전략"""

# --- 1. EXTRACT ------------------------------------------------------------
# Every field nullable on purpose: a null becomes an omitted line downstream,
# which is what "if a detail is missing, OMIT it" actually looks like in code.
FACTS_SCHEMA = {
    "type": "object",
    "properties": {
        "event_type": {"type": ["string", "null"]},
        "person":     {"type": ["string", "null"]},
        "location":   {"type": ["string", "null"]},
        "date":       {"type": ["string", "null"]},
        "time":       {"type": ["string", "null"]},
        "price":      {"type": ["string", "null"]},
        "topics":     {"type": "array", "items": {"type": "string"}},
        "link":       {"type": ["string", "null"]},
    },
    "required": ["event_type", "person", "location", "date", "time", "price", "topics", "link"],
    "additionalProperties": False,
}
EXTRACT_SYS = ("Copy fields out of the input verbatim. Use null for anything the input "
               "does not state. Never infer, translate or reformat a value.")

# --- 2. WRITE --------------------------------------------------------------
PROSE_SCHEMA = {
    "type": "object",
    "properties": {
        "hook":     {"type": "string"},
        "body":     {"type": "array", "items": {"type": "string"}},
        "cta":      {"type": "string"},
        "hashtags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["hook", "body", "cta", "hashtags"],
    "additionalProperties": False,
}
PROSE_SYS = (
    "You write LinkedIn prose for an UPCOMING event. You are given the facts; do not "
    "restate the date, time or location — they are added separately.\n"
    "hook: one complete sentence, no teaser.\n"
    "body: 2-3 short paragraphs about why it is worth attending.\n"
    "cta: one sentence inviting the reader to register or reply.\n"
    "hashtags: 4 tags, no '#'.\n"
    "Write in the SAME language as the facts. Keep names, venues and time-zone codes "
    "exactly as given. Plain text only."
)


def parse_brief(brief):
    """Parse what the brief states STRUCTURALLY. No model involved.

    This is the level above schema-constrained extraction, and it is the lesson of
    the two runs before it. Asking the model to extract, then rejecting ungrounded
    values, dropped the real date and time as collateral: hyperclovax re-typed
    "sep 14th, 2026, 3PM PST" as "2026-09-14" / "15:00 PST", neither of which is a
    substring of the brief, so both were discarded and the post shipped with no date.
    An event announcement without a date is not shippable.

    A brief written as `key: value` lines and `- ` bullets does not need a model to
    read it. Code takes those verbatim and cannot reformat or invent them. The model
    extractor is then only a fallback for whatever this misses.
    """
    import re as _re
    facts = {k: None for k in ("event_type", "person", "location", "date", "time",
                               "price", "link")}
    facts["topics"] = []
    lines = [l.rstrip() for l in (brief or "").split("\n")]
    for l in lines:
        m = _re.match(r"^\s*([A-Za-z가-힣 ]{2,20})\s*:\s*(.+)$", l)
        if m:
            key, val = m.group(1).strip().lower(), m.group(2).strip()
            slot = {"location": "location", "장소": "location",
                    "time": "time", "시간": "time", "when": "time",
                    "date": "date", "일시": "date", "날짜": "date",
                    "price": "price", "참가비": "price", "cost": "price",
                    "link": "link", "url": "link", "링크": "link"}.get(key)
            if slot and not facts[slot]:
                facts[slot] = val
            continue
        if _re.match(r"^\s*[-*•]\s+\S", l):
            facts["topics"].append(_re.sub(r"^\s*[-*•]\s+", "", l).strip())
    # First non-empty, non-key line describes what it is and who is involved.
    for l in lines:
        if l.strip() and ":" not in l and not _re.match(r"^\s*[-*•]", l):
            facts["event_type"] = l.strip()
            break
    return facts


def _norm(x):
    """Case/space/punctuation-insensitive form, for substring grounding."""
    import re as _re
    return _re.sub(r"[^0-9a-z가-힣]", "", (x or "").lower())


def ground_facts(facts, brief):
    """Drop every extracted value that does not appear verbatim in the brief.

    This exists because the prototype's first run was WORSE than the thing it
    replaced. hyperclovax:1.5b extracted price="10000" from a brief that mentions no
    price, and the template rendered it as "• Price: 10000" — a fabrication with the
    authority of a structured field, in a post the rubric scored 97.7/100. Schema
    constraint guarantees the SHAPE of a fact, never its truth.

    So the value has to be checked against the source, in code. Strict and lossy on
    purpose: a value the extractor re-typed or reformatted ("15:00 PST" for "3PM PST")
    is dropped too. A dropped field emits no line, so the failure mode is a MISSING
    detail rather than a WRONG one — the same trade the prompts' own "if a detail is
    missing, OMIT it" rule already makes.

    The principled version of this is to have extraction return character offsets into
    the brief and slice the value in code, so an invented value is unrepresentable
    rather than merely rejected. Small models are poor at counting characters, so this
    approximates it with a substring test.
    """
    nb, out, dropped = _norm(brief), {}, []
    for k, v in facts.items():
        if k == "topics":
            kept = [t for t in (v or []) if _norm(t) and _norm(t) in nb]
            dropped += [f"topics:{t}" for t in (v or []) if t not in kept]
            out[k] = kept
        elif isinstance(v, str) and v.strip():
            if _norm(v) and _norm(v) in nb:
                out[k] = v
            else:
                out[k] = None
                dropped.append(f"{k}:{v!r}")
        else:
            out[k] = v
    return out, dropped


def call(model_id, system, prompt, schema):
    r = providers.call_local(prompt, model=model_id, system=system,
                             json_schema=schema, json_mode=True, temperature=0)
    if not r.get("ok"):
        return None, r.get("error")
    t = (r.get("text") or "").strip()
    try:
        return json.loads(t), None
    except Exception:
        import re
        m = re.search(r"\{.*\}", t, re.S)
        if not m:
            return None, f"unparseable: {t[:120]}"
        try:
            return json.loads(m.group(0)), None
        except Exception as e:
            return None, f"unparseable: {e}"


def assemble(facts, prose):
    """Code writes every fact. The model's words never touch the details block."""
    cta = prose["cta"].strip()
    parts = [prose["hook"].strip(), ""]
    # Drop body items that merely repeat the cta — models overfill the array, and a
    # duplicated call to action reads like a bug to a human reviewer.
    body = [b.strip() for b in prose.get("body", []) if b.strip() and b.strip() != cta]
    parts += body[:3]
    parts.append("")
    ko = is_korean(prose["hook"] + " ".join(prose.get("body", [])))
    L = {"date": "일시" if ko else "Date", "time": "시간" if ko else "Time",
         "location": "장소" if ko else "Location", "person": "연사" if ko else "Speaker",
         "price": "참가비" if ko else "Price", "topics": "주제" if ko else "Topics"}
    # A null field emits no line at all. This is where "[Insert Price]" becomes
    # structurally impossible: there is no branch that writes a placeholder.
    emitted = []
    for k in ("date", "time", "location", "person", "price"):
        v = (facts.get(k) or "").strip() if isinstance(facts.get(k), str) else None
        if not v:
            continue
        # Extractors routinely put the whole "sep 14th, 2026, 3PM PST" string in
        # `date`, which then rendered a Time line repeating what Date already said.
        if any(v in e or e in v for e in emitted):
            continue
        emitted.append(v)
        parts.append(f"• {L[k]}: {v}")
    for t in (facts.get("topics") or []):
        if str(t).strip():
            parts.append(f"• {L['topics']}: {str(t).strip()}")
    parts += ["", cta]
    tags = [t.lstrip("#").strip() for t in prose.get("hashtags", []) if t.strip()][:5]
    if len(tags) >= 3:
        parts += ["", " ".join("#" + t.replace(" ", "") for t in tags)]
    return "\n".join(parts).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="local:llama3.2:3b")
    ap.add_argument("--brief", default=BRIEF)
    ap.add_argument("--compare", action="store_true", help="also run the current one-shot path")
    a = ap.parse_args()
    tag = a.model.split("local:")[-1]

    # Level 1: code reads what the brief states structurally.
    facts = parse_brief(a.brief)
    missing = [k for k, v in facts.items() if k != "topics" and not v]
    # Level 2: the model fills only what code could not, schema-constrained, then
    # every value it returns is grounded against the brief before use.
    if missing:
        mf, err = call(tag, EXTRACT_SYS, f"Input:\n{a.brief}", FACTS_SCHEMA)
        if err:
            print(f"  (model extraction unavailable: {err}; continuing with parsed facts)")
        else:
            mf, _ = ground_facts(mf, a.brief)
            for k in missing:
                if mf.get(k):
                    facts[k] = mf[k]
    facts, dropped = ground_facts(facts, a.brief)
    print("=== 1. FACTS (code-parsed first, model only for gaps, all grounded) ===")
    print("  " + json.dumps(facts, ensure_ascii=False, indent=2).replace("\n", "\n  "))
    if dropped:
        print("  DROPPED as ungrounded: " + ", ".join(dropped))

    prose, err = call(tag, PROSE_SYS, "Facts:\n" + json.dumps(facts, ensure_ascii=False),
                      PROSE_SCHEMA)
    if err:
        print(f"  PROSE failed: {err}"); return 1
    print("\n=== 2. PROSE (model, no fact fields exposed) ===")
    print("  " + json.dumps(prose, ensure_ascii=False, indent=2).replace("\n", "\n  "))

    post = assemble(facts, prose)
    post, flags = strip_ungrounded(strip_markdown(post), a.brief)
    print("\n=== 3. ASSEMBLED POST (code writes the facts) ===")
    print("\n".join("  " + l for l in post.split("\n")))
    ev = run_eval("linkedin", post)
    print(f"\n  rubric {ev['total']}/100 · {len(post)} chars · flags {flags or 'none'}")
    for c in ev["criteria"]:
        print(f"    {c['criterion']:10} {round(c['score']):3}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
