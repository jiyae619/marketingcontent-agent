#!/usr/bin/env python3
"""Fact/prose split for all six channels: code writes the facts, the model writes prose.

Generalised from scripts/prototype_schema_gen.py after it proved out on LinkedIn.
The reasoning, and the two failed iterations behind it, are in that file's header —
the short version is that a rule in a prompt is a request, and at the 2-3B tier it
is not reliably obeyed, so the rules that CAN be made structural are.

Three stages, and the order is the point:

  1. parse_brief()   code reads `key: value` lines and `- ` bullets. No model, so
                     nothing can be reformatted or invented.
  2. model           writes hook / body / cta / hashtags under a JSON schema. It is
                     never shown a date field, so it has none to fill.
  3. assemble()      code emits the details block from the parsed facts, per channel.

What this makes structurally impossible, rather than merely forbidden:
  invented weekday · invented price · "[Insert Price]" · restyled event type
The event type comes from a code-filled field, which is why restyle — the one class
strip_ungrounded can only FLAG — stops happening here.

What it does not fix: invented characterisations in the prose ("legendary",
"once-in-a-lifetime"). Those are voice defects and belong to the ai_slop flag.

    python3 scripts/schema_gen.py --platform kakaotalk
    python3 scripts/schema_gen.py --all
"""
import argparse, json, os, re, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "testing/core"))
from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(HERE, ".env"))
import providers  # noqa: E402
from evaluators import (evaluate as run_eval, strip_markdown,  # noqa: E402
                        strip_ungrounded, is_korean)
from prototype_schema_gen import (BRIEF, FACTS_SCHEMA, EXTRACT_SYS,  # noqa: E402
                                  PROSE_SCHEMA, call, parse_brief, ground_facts)

# Per-channel assembly. Each entry states what the CODE emits, so the model's brief
# stays the same everywhere and only the template differs. `bullets` False means the
# facts are folded into one line — KakaoTalk and WhatsApp are chat, not posters.
CHANNELS = {
    "linkedin":  dict(body=3, bullets=True,  tags=(3, 5), sentences=None),
    "instagram": dict(body=2, bullets=True,  tags=(3, 5), sentences=None),
    "circle":    dict(body=3, bullets=True,  tags=(0, 0), sentences=None),
    "kakaotalk": dict(body=1, bullets=False, tags=(0, 0), sentences=3),
    "whatsapp":  dict(body=1, bullets=False, tags=(0, 0), sentences=4),
    "x":         dict(body=1, bullets=False, tags=(2, 3), sentences=None, cap=280),
}

LABELS_KO = {"date": "일시", "time": "시간", "location": "장소",
             "person": "연사", "price": "참가비", "topics": "주제"}
LABELS_EN = {"date": "Date", "time": "Time", "location": "Location",
             "person": "Speaker", "price": "Price", "topics": "Topics"}
LABELS_KO["event_type"] = "행사"
LABELS_EN["event_type"] = "Event"

# --- event type as an enum -------------------------------------------------
# `restyle` (a briefed "coaching session" shipping as 세미나 / 워크샵 / 마스터클래스)
# is the last defect class strip_ungrounded can only FLAG, and it survives because
# the event type reaches the model as a free string it is free to paraphrase.
# An enum removes the freedom: the brief selects a key, and the label is looked up.
# Same move as date and location — the model is never asked to produce the value.
#
# Aliases are matched longest-first so "info session" does not resolve via "session".
EVENT_TYPES = {
    "coaching":   ("Coaching session", "코칭 세션",
                   ["coaching session", "coaching", "1:1", "코칭", "멘토링", "mentoring"]),
    "info":       ("Info session", "설명회",
                   ["info session", "information session", "설명회", "오리엔테이션"]),
    "workshop":   ("Workshop", "워크숍",
                   ["workshop", "워크숍", "워크샵", "실습"]),
    "seminar":    ("Seminar", "세미나",
                   ["seminar", "세미나"]),
    "webinar":    ("Webinar", "웨비나",
                   ["webinar", "웨비나", "온라인 세미나"]),
    "talk":       ("Talk", "강연",
                   ["fireside chat", "guest talk", "lecture", "강연", "특강", "talk"]),
    "meetup":     ("Meetup", "모임",
                   ["networking", "meetup", "meet-up", "네트워킹", "모임"]),
    "conference": ("Conference", "컨퍼런스",
                   ["conference", "summit", "컨퍼런스", "콘퍼런스"]),
    "class":      ("Class", "클래스",
                   ["masterclass", "course", "class", "마스터클래스", "클래스", "수업"]),
}
_ALIASES = sorted(((a, k) for k, (_, _, al) in EVENT_TYPES.items() for a in al),
                  key=lambda x: -len(x[0]))
# "coaching session with 박운영" / "박운영과 함께하는 코칭" -> the name, and the rest.
_WITH = re.compile(r"\s+(?:with|w/|featuring|feat\.?)\s+(.+)$", re.I)
_KO_WITH = re.compile(r"^(.+?)(?:\s*(?:님)?\s*(?:와|과)\s*함께(?:하는)?)\s*(.+)$")


def classify_event_type(raw):
    """Map a briefed phrase onto an enum key. Code only — no model, no inference
    beyond a literal alias match. Returns None when nothing matches, and a None
    event_type emits no line, exactly like any other unknown fact."""
    if not raw:
        return None
    low = str(raw).lower()
    for alias, key in _ALIASES:
        if alias in low:
            return key
    return None


def canonicalize(facts):
    """Split the free-text first line into (person, event_type key).

    parse_brief() puts the whole line in event_type, so "coaching session with
    박운영" left person null and the name buried in a string the model then
    paraphrased. Pulling the name out and resolving the rest to an enum key makes
    both fields code-written.
    """
    raw = facts.get("event_type")
    if isinstance(raw, str) and raw.strip():
        rest = raw.strip()
        m = _KO_WITH.match(rest)
        if m:
            if not facts.get("person"):
                facts["person"] = m.group(1).strip()
            rest = m.group(2).strip()
        else:
            m = _WITH.search(rest)
            if m:
                if not facts.get("person"):
                    facts["person"] = m.group(1).strip()
                rest = _WITH.sub("", rest).strip()
        facts["event_type"] = classify_event_type(rest)
    return facts


def event_label(key, ko):
    en, kr, _ = EVENT_TYPES.get(key or "", (None, None, None))
    return kr if ko else en


def flag_restyle(text, key, ko):
    """After the enum, a rival event-type label in the prose is a restyle by
    definition: the canonical label is the only correct one."""
    if not key:
        return []
    mine = (event_label(key, ko) or "").lower()
    hits = []
    for k, (en, kr, _) in EVENT_TYPES.items():
        if k == key:
            continue
        for lab in (en, kr):
            if lab.lower() != mine and re.search(re.escape(lab), text, re.I):
                hits.append(("restyle", lab))
    return hits


def prose_system(platform, spec):
    """One short instruction per channel. Short on purpose: the ablation measured
    gemma2:2b grounding perfectly at 120 chars and failing at 3,321."""
    s = [f"You write {platform} prose for an UPCOMING event.",
         "You are NOT given the date, time, location or price, and a details "
         "block carrying them is appended after your text. Never state or guess "
         "them, and never name a venue.",
         f"hook: one complete sentence. body: {spec['body']} short paragraph(s). "
         "cta: one sentence inviting the reader to register or reply."]
    lo, hi = spec["tags"]
    s.append(f"hashtags: {hi} tags, no '#'." if hi else "hashtags: return an empty list.")
    if spec.get("sentences"):
        s.append(f"Keep the whole thing under {spec['sentences']} sentences.")
    if spec.get("cap"):
        s.append(f"Keep the whole thing under {spec['cap']} characters.")
    s.append("Write in the SAME language as the facts. Keep names, venues and "
             "time-zone codes exactly as given. Plain text only.")
    return "\n".join(s)


def fact_lines(facts, ko, spec):
    """Emit one line per KNOWN fact. A null field emits nothing — which is where
    '[Insert Price]' becomes unrepresentable: no branch writes a placeholder."""
    L = LABELS_KO if ko else LABELS_EN
    seen, out = [], []
    ev = event_label(facts.get("event_type"), ko)
    if ev:
        seen.append(ev)
        out.append(f"• {L['event_type']}: {ev}" if spec["bullets"]
                   else f"{L['event_type']}: {ev}")
    for k in ("date", "time", "location", "person", "price"):
        v = facts.get(k)
        v = v.strip() if isinstance(v, str) else None
        if not v or any(v in e or e in v for e in seen):
            continue
        seen.append(v)
        out.append(f"• {L[k]}: {v}" if spec["bullets"] else f"{L[k]}: {v}")
    topics = [str(t).strip() for t in (facts.get("topics") or []) if str(t).strip()]
    if topics:
        out += ([f"• {L['topics']}: {t}" for t in topics] if spec["bullets"]
                else [f"{L['topics']}: " + ", ".join(topics)])
    return out


def assemble(platform, facts, prose):
    spec = CHANNELS[platform]
    cta = (prose.get("cta") or "").strip()
    hook = (prose.get("hook") or "").strip()
    # hyperclovax emitted the literal string "cta" as a body element, which shipped
    # into the post. A body paragraph that is just a schema key name is never prose.
    _KEYS = {"hook", "body", "cta", "hashtags"}
    body = [b.strip() for b in (prose.get("body") or [])
            if b.strip() and b.strip() != cta
            and b.strip().strip("':\"").lower() not in _KEYS]
    ko = is_korean(hook + " ".join(body))
    facts_block = fact_lines(facts, ko, spec)

    if spec["bullets"]:
        parts = [hook, ""] + body[:spec["body"]] + [""] + facts_block + ["", cta]
    else:
        # Chat channels: one compact line of facts, no poster layout.
        parts = [hook] + body[:spec["body"]] + [" · ".join(facts_block), cta]
    lo, hi = spec["tags"]
    if hi:
        tags = [t.lstrip("#").strip().replace(" ", "") for t in (prose.get("hashtags") or []) if t.strip()][:hi]
        if len(tags) >= lo:
            parts += ["", " ".join("#" + t for t in tags)]
    text = "\n".join(p for p in parts if p is not None).strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    if spec.get("cap"):
        text = text[:spec["cap"]].rstrip()
    return text


def flag_prose_contradictions(text, facts, brief):
    """Catch prose that states a fact contradicting the code-written block.

    The split guarantees the FACTS block. It does not stop the prose ALSO stating
    facts, and the prose invents them: on one run the block correctly said
    "장소: seattle university" while the prose above it said 세인트루이스 대학교
    (St. Louis) on instagram and "Seoul University" on circle. Internally
    contradictory output is arguably worse for a reader than a single wrong value,
    because both readings look authoritative.

    The prompt already says "do NOT restate date, time, location" and was ignored —
    the same lesson as everywhere else, so this checks in code. Flagged rather than
    rewritten: which of the two is wrong is a judgement, and guessing is the thing
    this whole design avoids.
    """
    out, nb = [], (brief or "").lower()
    loc = (facts.get("location") or "").strip()
    if loc:
        head = loc.split()[0].lower()
        # A university/campus/school named in prose that is not the briefed venue.
        for m in re.finditer(r"([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)*\s+(?:University|College|School)|"
                             r"[가-힣]{2,10}\s*(?:대학교|대학))", text):
            cand = m.group(0).strip()
            if cand.lower() not in nb and head not in cand.lower():
                out.append(("venue_contradiction", cand))
    # A profession or title attached to the person, absent from the brief.
    person = (facts.get("person") or "").strip()
    if person:
        for m in re.finditer(r"(?:renowned|legendary|famous|top-tier|leading|expert)\s+"
                             r"([a-z ]{3,30}?)\s*" + re.escape(person), text, re.I):
            out.append(("invented_credential", m.group(0).strip()))
    return out


def generate(platform, brief, model_id):
    facts = canonicalize(parse_brief(brief))
    missing = [k for k, v in facts.items()
               if k not in ("topics", "event_type") and not v]
    if missing:
        mf, err = call(model_id, EXTRACT_SYS, f"Input:\n{brief}", FACTS_SCHEMA)
        if not err:
            mf, _ = ground_facts(mf, brief)
            for k in missing:
                if mf.get(k):
                    facts[k] = mf[k]
    facts, _ = ground_facts(facts, brief)
    spec = CHANNELS[platform]
    # The prose is shown ONLY what it needs to write around: who, what kind of
    # thing, and the topics. Date, time, location, price and link are withheld
    # because code emits them — and because the model cannot contradict a fact it
    # was never given. The instruction not to restate them was measured being
    # ignored on 6/6 channels, which is the usual result for a rule in a prompt.
    payload = {"event_type": event_label(facts.get("event_type"), is_korean(brief))
                             or facts.get("event_type"),
               "person": facts.get("person"),
               "topics": facts.get("topics") or []}
    prose, err = call(model_id, prose_system(platform, spec),
                      "Facts:\n" + json.dumps(payload, ensure_ascii=False), PROSE_SCHEMA)
    if err:
        return None, facts, None, err
    text = assemble(platform, facts, prose)
    text, flags = strip_ungrounded(strip_markdown(text), brief)
    flags += flag_prose_contradictions(text, facts, brief)
    flags += flag_restyle(text, facts.get("event_type"), is_korean(text))
    return text, facts, flags, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--platform", default=None)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--model", default=os.getenv("LOCAL_LLM_MODEL", "hyperclovax:1.5b"))
    ap.add_argument("--brief", default=BRIEF)
    a = ap.parse_args()
    plats = list(CHANNELS) if a.all else [a.platform or "linkedin"]
    for p in plats:
        text, facts, flags, err = generate(p, a.brief, a.model)
        print(f"\n{'='*70}\n  {p.upper()}  ·  {a.model}\n{'='*70}")
        if err:
            print(f"  FAILED: {err}"); continue
        print("\n".join("  " + l for l in text.split("\n")))
        ev = run_eval(p, text)
        print(f"\n  rubric {ev['total']}/100 · {len(text)} chars · flags {flags or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
